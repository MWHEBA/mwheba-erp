"""
اختبارات شاملة للمرحلة 3:
1. حساب المسافات الجغرافية الدقيقة (Haversine Formula)
2. التحقق من النطاق الجغرافي للبصمة (Geofencing Inside/Outside Radius)
3. الموظفون المتنقلون بين المقرات (Roaming Employees)
4. بصمات الزيارات الميدانية والمأموريات (Field Visits)
5. كشف ومكافحة برامج تزييف الموقع (Anti-Mock Location & Fake GPS)
6. حوكمة وربط عتاد الأجهزة (Hardware Device Binding & Reset)
7. التوكنات المشفرة ومنع هجمات إعادة الإرسال (Anti-Replay Security Tokens)
8. إدارة مقرات العمل عبر الـ Views (WorkLocation CRUD)
"""
import json
import pytest
from datetime import date, time, datetime, timedelta
from decimal import Decimal

from django.test import RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache

from hr.models import (
    Employee, Department, JobTitle, Shift, WorkLocation, Contract
)
from hr.services.geofencing_service import GeofencingService
from hr.views.work_location_views import (
    work_location_save,
    work_location_toggle,
    work_location_delete,
    reset_employee_device_binding,
)

User = get_user_model()


@pytest.fixture
def phase3_setup(db):
    """إعداد بيانات الاختبار الأساسية للمرحلة 3"""
    cache.clear()
    dept = Department.objects.create(name_ar='إدارة العمليات الميدانية', code='OPS')
    job = JobTitle.objects.create(title_ar='مهندس موقع', department=dept)
    shift = Shift.objects.create(
        name='وردية نهارية',
        start_time=time(9, 0),
        end_time=time(17, 0)
    )

    user = User.objects.create_user(username='hr_admin_phase3', password='password123', is_staff=True)
    
    # منح الصلاحيات
    content_type_loc = ContentType.objects.get_for_model(WorkLocation)
    perm_change_loc, _ = Permission.objects.get_or_create(
        codename='change_worklocation',
        content_type=content_type_loc,
        defaults={'name': 'تعديل مقر العمل'}
    )
    perm_delete_loc, _ = Permission.objects.get_or_create(
        codename='delete_worklocation',
        content_type=content_type_loc,
        defaults={'name': 'حذف مقر العمل'}
    )
    
    content_type_emp = ContentType.objects.get_for_model(Employee)
    perm_reset_dev, _ = Permission.objects.get_or_create(
        codename='can_reset_device_binding',
        content_type=content_type_emp,
        defaults={'name': 'فك ارتباط عتاد هاتف الموظف'}
    )
    user.user_permissions.add(perm_change_loc, perm_delete_loc, perm_reset_dev)

    # مقر رئيسي (التجمع الخامس بالقاهرة: 30.012000, 31.432000) بنصف قطر 100 متر
    hq_location = WorkLocation.objects.create(
        name_ar='المقر الرئيسي - التجمع الخامس',
        name_en='HQ New Cairo',
        latitude=Decimal('30.0120000'),
        longitude=Decimal('31.4320000'),
        radius_meters=100,
        is_active=True,
        is_default=True,
    )

    # فرع ثان (المهندسين بالجيزة: 30.055000, 31.205000) بنصف قطر 150 متر
    branch_location = WorkLocation.objects.create(
        name_ar='فرع المهندسين',
        name_en='Mohandessin Branch',
        latitude=Decimal('30.0550000'),
        longitude=Decimal('31.2050000'),
        radius_meters=150,
        is_active=True,
        is_default=False,
    )

    # موظف 1: مقر محدد في المقر الرئيسي
    emp_hq = Employee.objects.create(
        name='كريم أحمد فؤاد',
        employee_number='EMP-GEO-001',
        national_id='29501011234581',
        birth_date=date(1995, 3, 15),
        gender='male',
        marital_status='single',
        mobile_phone='01011112222',
        created_by=user,
        department=dept,
        job_title=job,
        shift=shift,
        work_location=hq_location,
        allow_mobile_attendance=True,
        allowed_all_locations=False,
        allow_field_visits=False,
        status='active',
        hire_date=date(2025, 1, 1),
    )

    # موظف 2: موظف متنقل بين الفروع
    emp_roaming = Employee.objects.create(
        name='سارة طارق إبراهيم',
        employee_number='EMP-GEO-002',
        national_id='29701011234582',
        birth_date=date(1997, 7, 20),
        gender='female',
        marital_status='single',
        mobile_phone='01033334444',
        created_by=user,
        department=dept,
        job_title=job,
        shift=shift,
        work_location=hq_location,
        allow_mobile_attendance=True,
        allowed_all_locations=True,
        allow_field_visits=False,
        status='active',
        hire_date=date(2025, 1, 1),
    )

    # موظف 3: مندوب زيارات ميدانية
    emp_field = Employee.objects.create(
        name='ياسر عادل منصور',
        employee_number='EMP-GEO-003',
        national_id='29301011234583',
        birth_date=date(1993, 11, 10),
        gender='male',
        marital_status='married',
        mobile_phone='01055556666',
        created_by=user,
        department=dept,
        job_title=job,
        shift=shift,
        allow_mobile_attendance=True,
        allowed_all_locations=False,
        allow_field_visits=True,
        status='active',
        hire_date=date(2025, 1, 1),
    )

    Contract.objects.create(
        employee=emp_hq,
        contract_number='CNT-GEO-001',
        basic_salary=Decimal('7000.00'),
        start_date=date(2025, 1, 1),
        status='active',
        created_by=user
    )

    return {
        'dept': dept,
        'job': job,
        'shift': shift,
        'user': user,
        'hq_loc': hq_location,
        'branch_loc': branch_location,
        'emp_hq': emp_hq,
        'emp_roaming': emp_roaming,
        'emp_field': emp_field,
        'rf': RequestFactory(),
    }


@pytest.mark.django_db
class TestPhase3GeofencingEngine:
    """اختبارات محرك التحقق الجغرافي والمسافات"""

    def test_haversine_distance_calculation(self):
        """اختبار دقة حساب المسافات الجغرافية بمعادلة هافرسين"""
        # المسافة بين برج القاهرة وميدان التحرير تقريباً 1100 - 1200 متر
        lat1, lon1 = 30.0459, 31.2243  # برج القاهرة
        lat2, lon2 = 30.0444, 31.2357  # ميدان التحرير

        distance = GeofencingService.calculate_distance(lat1, lon1, lat2, lon2)
        assert 1000 <= distance <= 1300

        # المسافة بين النقطة ونفسها تساوي 0
        dist_zero = GeofencingService.calculate_distance(lat1, lon1, lat1, lon1)
        assert dist_zero == 0.0

    def test_geofence_inside_radius_approved(self, phase3_setup):
        """البصمة داخل نطاق المقر المعتمد مقبولة بنجاح"""
        emp = phase3_setup['emp_hq']
        hq = phase3_setup['hq_loc']

        # إحداثيات تبعد 25 متر فقط عن مركز المقر
        user_lat = 30.012150
        user_lng = 31.432100

        is_valid, matched_loc, dist, err = GeofencingService.validate_location(
            employee=emp,
            latitude=user_lat,
            longitude=user_lng,
            is_field_visit=False,
            accuracy_meters=15.0
        )
        assert is_valid is True
        assert matched_loc == hq
        assert dist <= hq.radius_meters
        assert err is None

    def test_geofence_outside_radius_rejected(self, phase3_setup):
        """البصمة خارج نطاق المقر المعتمد مرفوضة مع ذكر المسافة"""
        emp = phase3_setup['emp_hq']
        hq = phase3_setup['hq_loc']

        # إحداثيات تبعد 500 متر عن المقر
        user_lat = 30.016000
        user_lng = 31.435000

        is_valid, matched_loc, dist, err = GeofencingService.validate_location(
            employee=emp,
            latitude=user_lat,
            longitude=user_lng,
            is_field_visit=False,
            accuracy_meters=10.0
        )
        assert is_valid is False
        assert dist > hq.radius_meters
        assert "أنت خارج نطاق مقر العمل" in err

    def test_roaming_employee_allowed_at_any_active_location(self, phase3_setup):
        """الموظف المتنقل (allowed_all_locations) تقبل بصمته في أي فرع نشط"""
        emp_roaming = phase3_setup['emp_roaming']
        branch = phase3_setup['branch_loc']

        # إحداثيات قريبة من فرع المهندسين (يبعد 30 متر فقط)
        user_lat = 30.055200
        user_lng = 31.205100

        is_valid, matched_loc, dist, err = GeofencingService.validate_location(
            employee=emp_roaming,
            latitude=user_lat,
            longitude=user_lng,
            is_field_visit=False
        )
        assert is_valid is True
        assert matched_loc == branch
        assert dist <= branch.radius_meters

    def test_field_visit_allowed_for_authorized_employee(self, phase3_setup):
        """الموظف المصرح له بالزيارات الميدانية تقبل بصمته في أي موقع خارج المقرات"""
        emp_field = phase3_setup['emp_field']

        # إحداثيات في مدينة نصر بعيداً عن أي مقر
        user_lat = 30.060000
        user_lng = 31.330000

        is_valid, matched_loc, dist, err = GeofencingService.validate_location(
            employee=emp_field,
            latitude=user_lat,
            longitude=user_lng,
            is_field_visit=True
        )
        assert is_valid is True
        assert matched_loc is None
        assert err == "زيارة ميدانية معتمدة"

    def test_field_visit_denied_for_unauthorized_employee(self, phase3_setup):
        """محاولة تسجيل زيارة ميدانية لموظف غير مصرح له ترفض فوراً"""
        emp_hq = phase3_setup['emp_hq']

        is_valid, matched_loc, dist, err = GeofencingService.validate_location(
            employee=emp_hq,
            latitude=30.060000,
            longitude=31.330000,
            is_field_visit=True
        )
        assert is_valid is False
        assert "غير مصرح له" in err


@pytest.mark.django_db
class TestPhase3AntiFraudAndSecurity:
    """اختبارات ترسانة مكافحة التحايل وربط الأجهزة والتوكنات"""

    def test_mock_location_rejection(self):
        """كشف ورفض محاولات تزييف الموقع Fake GPS"""
        is_mock, msg = GeofencingService.detect_mock_location(is_mock_flag=True)
        assert is_mock is True
        assert "Mock Location" in msg

        # فحص سرعة غير واقعية
        is_mock_speed, speed_msg = GeofencingService.detect_mock_location(is_mock_flag=False, speed_kmh=450.0)
        assert is_mock_speed is True
        assert "سرعة انتقال غير واقعية" in speed_msg

    def test_device_binding_lifecycle(self, phase3_setup):
        """اختبار دورة حياة ربط عتاد الهاتف: ربط تلقائي أول مرة، مطابقة، حظر جهاز غريب، وفك الارتباط"""
        emp = phase3_setup['emp_hq']
        admin_user = phase3_setup['user']
        assert emp.registered_device_uuid is None

        device_a = "DEVICE-UUID-AAAA-1111"
        device_b = "DEVICE-UUID-BBBB-2222"

        # 1. أول تسجيل دخول -> ربط تلقائي
        valid, is_new, msg = GeofencingService.validate_device_binding(emp, device_a)
        assert valid is True
        assert is_new is True
        emp.refresh_from_db()
        assert emp.registered_device_uuid == device_a
        assert emp.device_bound_at is not None

        # 2. بصمة لاحقة من نفس الجهاز -> قبول مباشر
        valid2, is_new2, msg2 = GeofencingService.validate_device_binding(emp, device_a)
        assert valid2 is True
        assert is_new2 is False

        # 3. محاولة بصم من جهاز مختلف (Device B) -> رفض أمني
        valid3, is_new3, msg3 = GeofencingService.validate_device_binding(emp, device_b, is_emergency=False)
        assert valid3 is False
        assert "مرتبط بجهاز هاتف آخر" in msg3

        # 4. بصمة طوارئ من جهاز مختلف -> قبول مشروط مع وسم
        valid4, is_new4, msg4 = GeofencingService.validate_device_binding(emp, device_b, is_emergency=True)
        assert valid4 is True
        assert "بصمة طوارئ" in msg4

        # 5. قيام مسؤول HR بفك الارتباط
        GeofencingService.reset_device_binding(emp, admin_user, reason="الموظف قام بتغيير هاتفه التالف")
        emp.refresh_from_db()
        assert emp.registered_device_uuid is None

        # 6. الموظف يربط جهازه الجديد (Device B)
        valid5, is_new5, _ = GeofencingService.validate_device_binding(emp, device_b)
        assert valid5 is True
        assert is_new5 is True
        emp.refresh_from_db()
        assert emp.registered_device_uuid == device_b

    def test_secure_punch_token_replay_protection(self, phase3_setup):
        """اختبار التوكنات المشفرة ومكافحة هجمات إعادة الإرسال Replay Protection"""
        emp = phase3_setup['emp_hq']
        user = phase3_setup['user']

        token = GeofencingService.generate_secure_punch_token(emp.id, user.id)
        assert token is not None

        # أول استخدام للتوكن -> صالح
        is_valid, err = GeofencingService.verify_secure_punch_token(token, emp.id)
        assert is_valid is True
        assert err is None

        # محاولة إعادة إرسال نفس التوكن مرة أخرى (Replay Attack) -> مرفوض
        is_valid_replay, err_replay = GeofencingService.verify_secure_punch_token(token, emp.id)
        assert is_valid_replay is False
        assert "Replay Attack Detected" in err_replay or "تم استخدام هذا التوكن مسبقاً" in err_replay


@pytest.mark.django_db
class TestPhase3WorkLocationViews:
    """اختبارات الـ Views والتحكم في مقرات العمل وفك ارتباط الأجهزة"""

    def test_work_location_save_create_and_edit(self, phase3_setup):
        """إنشاء وتعديل مقر عمل عبر الـ View"""
        rf = phase3_setup['rf']
        user = phase3_setup['user']

        # 1. إنشاء مقر جديد
        request_create = rf.post('/hr/work-locations/save/', {
            'name_ar': 'فرع الإسكندرية - سموحة',
            'name_en': 'Alexandria Branch',
            'address': 'سموحة، شارع فوزي معاذ',
            'latitude': '31.2150000',
            'longitude': '29.9550000',
            'radius_meters': '200',
            'is_active': 'on',
        })
        request_create.user = user

        response = work_location_save(request_create)
        assert response.status_code == 200
        data = json.loads(response.content.decode('utf-8'))
        assert data['success'] is True
        loc_id = data['data']['id']

        loc = WorkLocation.objects.get(pk=loc_id)
        assert loc.name_ar == 'فرع الإسكندرية - سموحة'
        assert loc.radius_meters == 200

        # 2. تعديل المقر
        request_edit = rf.post('/hr/work-locations/save/', {
            'location_id': loc_id,
            'name_ar': 'فرع الإسكندرية الرئيسي',
            'latitude': '31.2150000',
            'longitude': '29.9550000',
            'radius_meters': '250',
            'is_active': 'on',
        })
        request_edit.user = user

        response_edit = work_location_save(request_edit)
        assert response_edit.status_code == 200
        loc.refresh_from_db()
        assert loc.name_ar == 'فرع الإسكندرية الرئيسي'
        assert loc.radius_meters == 250

    def test_work_location_toggle_and_delete(self, phase3_setup):
        """تبديل حالة التفعيل وحذف مقر عمل غير مخصص له موظفون"""
        rf = phase3_setup['rf']
        user = phase3_setup['user']

        temp_loc = WorkLocation.objects.create(
            name_ar='مقر مؤقت للحذف',
            latitude=Decimal('30.0100000'),
            longitude=Decimal('31.2000000'),
            radius_meters=100,
            is_active=True,
            is_default=False
        )

        # تبديل الحالة
        request_toggle = rf.post(f'/hr/work-locations/{temp_loc.pk}/toggle/')
        request_toggle.user = user
        res_toggle = work_location_toggle(request_toggle, temp_loc.pk)
        assert res_toggle.status_code == 200
        temp_loc.refresh_from_db()
        assert temp_loc.is_active is False

        # حذف المقر
        request_del = rf.post(f'/hr/work-locations/{temp_loc.pk}/delete/')
        request_del.user = user
        res_del = work_location_delete(request_del, temp_loc.pk)
        assert res_del.status_code == 200
        assert not WorkLocation.objects.filter(pk=temp_loc.pk).exists()

    def test_reset_employee_device_binding_view(self, phase3_setup):
        """فك ارتباط هاتف الموظف عبر الـ View مع الصلاحية الأمنية"""
        rf = phase3_setup['rf']
        user = phase3_setup['user']
        emp = phase3_setup['emp_hq']

        # تعيين جهاز للموظف أولاً
        emp.registered_device_uuid = "DEVICE-TEST-VIEW-999"
        emp.save(update_fields=['registered_device_uuid'])

        request = rf.post(f'/hr/employees/{emp.id}/reset-device-binding/', {
            'reason': 'الموظف اشترى هاتف جديد'
        })
        request.user = user

        response = reset_employee_device_binding(request, emp.id)
        assert response.status_code == 200
        data = json.loads(response.content.decode('utf-8'))
        assert data['success'] is True

        emp.refresh_from_db()
        assert emp.registered_device_uuid is None
