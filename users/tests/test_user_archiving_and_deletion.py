import pytest
from django.contrib.auth import get_user_model, authenticate
from django.urls import reverse
from users.models import Role, ActivityLog
from users.services.user_management_service import UserManagementService
from hr.models import Employee, Department, JobTitle
from hr.services.employee_service import EmployeeService
from core.models import SystemModule
from decimal import Decimal

User = get_user_model()


@pytest.fixture
def admin_role(db):
    return Role.objects.create(name='admin', display_name='مدير النظام', is_active=True)


@pytest.fixture
def viewer_role(db):
    return Role.objects.create(name='viewer', display_name='مشاهد', is_active=True)


@pytest.fixture
def superuser(db, admin_role):
    return User.objects.create_superuser(
        username='superadmin',
        email='super@company.com',
        password='Password123!',
        first_name='مدير',
        last_name='رئيسي',
        role=admin_role,
        is_active=True
    )


@pytest.fixture
def second_admin(db, admin_role):
    return User.objects.create_user(
        username='admin2',
        email='admin2@company.com',
        password='Password123!',
        first_name='مدير',
        last_name='ثان',
        role=admin_role,
        is_active=True
    )


@pytest.fixture
def standard_user(db, viewer_role):
    return User.objects.create_user(
        username='emp1',
        email='emp1@company.com',
        password='Password123!',
        first_name='أحمد',
        last_name='علي',
        role=viewer_role,
        is_active=True
    )


@pytest.fixture
def hr_setup(db, superuser, standard_user):
    """تهيئة بيئة الموارد البشرية وربط موظف بمستخدم قياسي"""
    SystemModule.objects.update_or_create(code='hr', defaults={'is_enabled': True, 'name': 'الموارد البشرية'})
    dept = Department.objects.create(name_ar='المبيعات', code='SALES')
    job = JobTitle.objects.create(title_ar='مندوب مبيعات', code='REP', department=dept)
    employee = Employee.objects.create(
        user=standard_user,
        name='أحمد علي محمد',
        national_id='29001011234567',
        birth_date='1990-01-01',
        gender='male',
        marital_status='single',
        employee_number='EMP-001',
        department=dept,
        job_title=job,
        hire_date='2026-01-01',
        status='active',
        created_by=superuser
    )
    return {'dept': dept, 'job': job, 'employee': employee}


@pytest.mark.django_db
class TestUserArchivingAndStatusToggle:
    def test_toggle_user_deactivation_and_synchronization(self, superuser, standard_user):
        """اختبار تعطيل المستخدم ونقله للأرشيف ومزامنة status مع is_active"""
        res = UserManagementService.toggle_user_status(standard_user, current_user=superuser)
        assert res['success'] is True
        assert res['action'] == 'archived'
        assert res['is_active'] is False

        standard_user.refresh_from_db()
        assert standard_user.is_active is False
        assert standard_user.status == 'inactive'

        # التحقق من تسجيل الحركة في سجل النشاطات
        log = ActivityLog.objects.filter(object_id=standard_user.id, action__contains='تعطيل').first()
        assert log is not None

    def test_toggle_user_reactivation(self, superuser, standard_user):
        """اختبار استعادة وتفعيل مستخدم مؤرشف"""
        standard_user.is_active = False
        standard_user.status = 'inactive'
        standard_user.save()

        res = UserManagementService.toggle_user_status(standard_user, current_user=superuser)
        assert res['success'] is True
        assert res['action'] == 'activated'
        assert res['is_active'] is True

        standard_user.refresh_from_db()
        assert standard_user.is_active is True
        assert standard_user.status == 'active'

    def test_cannot_deactivate_self(self, superuser):
        """منع تعطيل الحساب الشخصي"""
        res = UserManagementService.toggle_user_status(superuser, current_user=superuser)
        assert res['success'] is False
        assert "لا يمكنك تعطيل حسابك الخاص" in res['message']

    def test_cannot_deactivate_last_active_superuser(self, superuser, standard_user):
        """منع تعطيل آخر سوبر يوزر نشط في النظام"""
        res = UserManagementService.toggle_user_status(superuser, current_user=standard_user)
        assert res['success'] is False
        assert "المدير النشط الوحيد" in res['message']


@pytest.mark.django_db
class TestBidirectionalHRAndUserSync:
    def test_user_deactivation_suspends_linked_employee(self, superuser, standard_user, hr_setup):
        """عند تعطيل المستخدم يتم تعليق/إيقاف ملف الموظف في HR تلقائياً"""
        emp = hr_setup['employee']
        assert emp.status == 'active'

        res = UserManagementService.toggle_user_status(standard_user, current_user=superuser, target_active=False)
        assert res['success'] is True

        emp.refresh_from_db()
        assert emp.status == 'suspended'

    def test_user_reactivation_restores_suspended_employee(self, superuser, standard_user, hr_setup):
        """عند إعادة تفعيل المستخدم يتم إعادة تفعيل الموظف الموقوف في HR"""
        emp = hr_setup['employee']
        UserManagementService.toggle_user_status(standard_user, current_user=superuser, target_active=False)
        emp.refresh_from_db()
        assert emp.status == 'suspended'

        # إعادة تفعيل المستخدم
        res = UserManagementService.toggle_user_status(standard_user, current_user=superuser, target_active=True)
        assert res['success'] is True

        emp.refresh_from_db()
        assert emp.status == 'active'

    def test_employee_suspension_in_hr_deactivates_user(self, superuser, standard_user, hr_setup):
        """عند إيقاف الموظف في HR يتم تعطيل حساب المستخدم وإنهاء جلساته"""
        emp = hr_setup['employee']
        emp.status = 'suspended'
        emp.save()

        standard_user.refresh_from_db()
        assert standard_user.is_active is False
        assert standard_user.status == 'inactive'

    def test_employee_termination_in_hr_deactivates_user(self, superuser, standard_user, hr_setup):
        """عند إنهاء خدمة الموظف في HR يتم تعطيل حساب المستخدم تلقائياً"""
        emp = hr_setup['employee']
        termination_data = {
            'termination_date': '2026-09-20',
            'reason': 'استقالة'
        }
        EmployeeService.terminate_employee(emp, termination_data, terminated_by=superuser)

        emp.refresh_from_db()
        assert emp.status == 'terminated'

        standard_user.refresh_from_db()
        assert standard_user.is_active is False
        assert standard_user.status == 'inactive'

    def test_employee_on_leave_does_not_deactivate_user(self, superuser, standard_user, hr_setup):
        """وضع الموظف في إجازة رسمية لا يعطل دخوله للنظام"""
        emp = hr_setup['employee']
        emp.status = 'on_leave'
        emp.save()

        standard_user.refresh_from_db()
        assert standard_user.is_active is True
        assert standard_user.status == 'active'

    def test_employee_reinstate_reactivates_user(self, superuser, standard_user, hr_setup):
        """عند إعادة الموظف للخدمة يتم تفعيل حسابه كمستخدم تلقائياً"""
        emp = hr_setup['employee']
        termination_data = {
            'termination_date': '2026-09-20',
            'reason': 'استقالة'
        }
        EmployeeService.terminate_employee(emp, termination_data, terminated_by=superuser)
        standard_user.refresh_from_db()
        assert standard_user.is_active is False

        # إعادة الموظف للخدمة
        EmployeeService.reinstate_employee(emp, reinstated_by=superuser)

        emp.refresh_from_db()
        assert emp.status == 'active'

        standard_user.refresh_from_db()
        assert standard_user.is_active is True
        assert standard_user.status == 'active'


@pytest.mark.django_db
class TestSuperuserPasswordChangeInUserEdit:
    def test_superuser_can_change_user_password(self, client, superuser, standard_user):
        """قدرة السوبر أدمن على تغيير كلمة مرور المستخدم وتوثيقها في سجل النشاطات"""
        client.force_login(superuser)

        post_data = {
            'first_name': 'أحمد',
            'last_name': 'علي المعدل',
            'email': 'emp1_new@company.com',
            'phone': '01012345678',
            'address': 'القاهرة',
            'is_active': 'on',
            'new_password': 'BrandNewPassword999!'
        }

        resp = client.post(reverse('users:user_edit', args=[standard_user.id]), data=post_data)
        assert resp.status_code == 200
        data = resp.json()
        assert data['success'] is True

        # التحقق من إمكانية تسجيل الدخول بكلمة المرور الجديدة
        auth_user = authenticate(username=standard_user.username, password='BrandNewPassword999!')
        assert auth_user is not None
        assert auth_user.id == standard_user.id

        # التحقق من توثيق تغيير كلمة المرور في ActivityLog
        log = ActivityLog.objects.filter(
            object_id=standard_user.id,
            action="تغيير كلمة مرور المستخدم"
        ).first()
        assert log is not None
        assert log.user == superuser

    def test_non_superuser_cannot_change_password(self, client, second_admin, standard_user):
        """منع غير السوبر أدمن من تغيير كلمة المرور وإرجاع 403 Forbidden"""
        client.force_login(second_admin)

        post_data = {
            'first_name': 'أحمد',
            'last_name': 'علي',
            'email': 'emp1@company.com',
            'phone': '',
            'address': '',
            'is_active': 'on',
            'new_password': 'HackedPassword123!'
        }

        resp = client.post(reverse('users:user_edit', args=[standard_user.id]), data=post_data)
        assert resp.status_code == 403
        data = resp.json()
        assert data['success'] is False
        assert "مخصصة لمدير النظام الرئيسي" in data['message']

    def test_short_password_rejected(self, client, superuser, standard_user):
        """رفض كلمات المرور التي تقل عن 6 أحرف بـ 400 Bad Request"""
        client.force_login(superuser)

        post_data = {
            'first_name': 'أحمد',
            'last_name': 'علي',
            'email': 'emp1@company.com',
            'phone': '',
            'address': '',
            'is_active': 'on',
            'new_password': '123'
        }

        resp = client.post(reverse('users:user_edit', args=[standard_user.id]), data=post_data)
        assert resp.status_code == 400
        data = resp.json()
        assert data['success'] is False
        assert "لا تقل عن 6 أحرف" in data['message']


@pytest.mark.django_db
class TestUserDeletionRestrictions:
    def test_cannot_delete_active_user(self, superuser, standard_user):
        """منع حذف المستخدم النشط ووجوب أرشفته أولاً"""
        can_del, summary, msg = UserManagementService.can_delete_user(standard_user, current_user=superuser)
        assert can_del is False
        assert "حالة 'نشط'" in msg

        # محاولة الحذف المباشر
        res = UserManagementService.delete_user(standard_user, current_user=superuser)
        assert res['success'] is False
        assert "حالة 'نشط'" in res['message']

    def test_cannot_delete_superuser(self, superuser, second_admin):
        """منع حذف مدير النظام الرئيسي"""
        superuser.is_active = False
        superuser.status = 'inactive'
        superuser.save()

        can_del, summary, msg = UserManagementService.can_delete_user(superuser, current_user=second_admin)
        assert can_del is False
        assert "مدير النظام الرئيسي" in msg

    def test_cannot_delete_user_with_hr_employee(self, superuser, standard_user, hr_setup):
        """منع حذف مستخدم مربوط بملف موظف في الموارد البشرية"""
        standard_user.is_active = False
        standard_user.status = 'inactive'
        standard_user.save()

        can_del, summary, msg = UserManagementService.can_delete_user(standard_user, current_user=superuser)
        assert can_del is False
        assert len(summary) > 0
        assert any("الموارد البشرية" in s['label'] for s in summary)

    def test_cannot_delete_user_with_activity_logs(self, superuser, standard_user):
        """منع حذف مستخدم لديه سجلات نشاطات مسجلة باسمه"""
        standard_user.is_active = False
        standard_user.status = 'inactive'
        standard_user.save()

        ActivityLog.objects.create(
            user=standard_user,
            action='تعديل عميل',
            model_name='Customer',
            object_id=1
        )

        can_del, summary, msg = UserManagementService.can_delete_user(standard_user, current_user=superuser)
        assert can_del is False
        assert len(summary) > 0
        assert any("سجلات نشاطات" in s['label'] for s in summary)

    def test_can_delete_inactive_user_with_zero_operations(self, superuser, standard_user):
        """السماح بالحذف النهائي فقط لمستخدم معطل وليس لديه أي عمليات نهائياً"""
        standard_user.is_active = False
        standard_user.status = 'inactive'
        standard_user.save()

        user_id = standard_user.id
        can_del, summary, msg = UserManagementService.can_delete_user(standard_user, current_user=superuser)
        assert can_del is True
        assert len(summary) == 0

        res = UserManagementService.delete_user(standard_user, current_user=superuser)
        assert res['success'] is True
        assert not User.objects.filter(id=user_id).exists()


@pytest.mark.django_db
class TestUserViewsAndHRColumn:
    def test_hr_employee_column_appears_when_hr_enabled(self, client, superuser, standard_user, hr_setup):
        """ظهور عامود الموظف وبياناته عند تفعيل تطبيق HR"""
        client.force_login(superuser)

        resp = client.get(reverse('users:user_list'))
        assert resp.status_code == 200
        headers = resp.context['headers']
        assert any(h['key'] == 'employee_profile' for h in headers)
        assert "EMP-001" in resp.content.decode('utf-8')
        assert "أحمد علي محمد" in resp.content.decode('utf-8')

    def test_hr_employee_column_hidden_when_hr_disabled(self, client, superuser, standard_user, hr_setup):
        """اختفاء عامود الموظف كلياً عند تعطيل تطبيق HR في SystemModule"""
        SystemModule.objects.filter(code='hr').update(is_enabled=False)
        client.force_login(superuser)

        resp = client.get(reverse('users:user_list'))
        assert resp.status_code == 200
        headers = resp.context['headers']
        assert not any(h['key'] == 'employee_profile' for h in headers)

    def test_search_by_employee_number_and_name(self, client, superuser, standard_user, hr_setup):
        """البحث في قائمة المستخدمين بكود الموظف واسم الموظف الكامل"""
        client.force_login(superuser)

        # بحث برقم الموظف
        resp1 = client.get(reverse('users:user_list') + '?q=EMP-001')
        assert resp1.status_code == 200
        assert standard_user in resp1.context['users']

        # بحث باسم الموظف الكامل
        resp2 = client.get(reverse('users:user_list') + '?q=أحمد علي محمد')
        assert resp2.status_code == 200
        assert standard_user in resp2.context['users']

    def test_excel_export_includes_hr_data(self, client, superuser, standard_user, hr_setup):
        """تضمين بيانات الموظف في تصدير Excel عند تفعيل تطبيق HR"""
        client.force_login(superuser)

        resp = client.get(reverse('users:user_list') + '?export=excel')
        assert resp.status_code == 200
        assert resp['Content-Type'] == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
