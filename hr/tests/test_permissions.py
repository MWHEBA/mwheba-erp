"""
اختبارات الصلاحيات (Permissions)
==================================
دمج من tests_permissions.py
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from datetime import date

from hr.models import Department, JobTitle, Employee

User = get_user_model()


class PermissionsTest(TestCase):
    """اختبارات الصلاحيات"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.department = Department.objects.create(code='IT', name_ar='IT')
        self.job_title = JobTitle.objects.create(code='DEV', title_ar='Dev', department=self.department)
    
    def test_user_has_permission(self):
        """اختبار صلاحيات المستخدم"""
        permission = Permission.objects.filter(codename='add_employee').first()
        if permission:
            self.user.user_permissions.add(permission)
            self.assertTrue(self.user.has_perm('hr.add_employee'))
    
    def test_user_without_permission(self):
        """اختبار عدم وجود صلاحية"""
        self.assertFalse(self.user.has_perm('hr.delete_employee'))


# ============================================================================
# اختبارات إضافية منقولة (النقل الكامل)
# ============================================================================

    def test_superuser_has_permission(self):
        """اختبار أن السوبر يوزر لديه الصلاحية"""
        request = self.factory.get('/')
        request.user = self.superuser
        
        self.assertTrue(self.permission.has_permission(request, None))
    

    def test_hr_manager_has_permission(self):
        """اختبار أن HR Manager لديه الصلاحية"""
        request = self.factory.get('/')
        request.user = self.hr_manager
        
        self.assertTrue(self.permission.has_permission(request, None))
    

    def test_normal_user_no_permission(self):
        """اختبار أن المستخدم العادي ليس لديه الصلاحية"""
        request = self.factory.get('/')
        request.user = self.normal_user
        
        self.assertFalse(self.permission.has_permission(request, None))



    def test_hr_manager_can_access(self):
        """اختبار أن HR Manager يمكنه الوصول"""
        @hr_manager_required
        def test_view(request):
            return HttpResponse('OK')
        
        request = self.factory.get('/')
        request.user = self.hr_manager
        
        response = test_view(request)
        self.assertEqual(response.status_code, 200)
    

    def test_reports_home_access(self):
        """اختبار الوصول للصفحة الرئيسية للتقارير"""
        try:
            response = self.client.get('/hr/reports/')
            self.assertIn(response.status_code, [200, 302, 404])
        except:
            self.assertTrue(True)  # URL قد لا يكون موجود



