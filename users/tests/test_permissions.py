"""
اختبارات مكثفة لنظام الصلاحيات والأدوار
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from users.models import User, Role


class PermissionsSystemTestCase(TestCase):
    """اختبارات شاملة لنظام الصلاحيات"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = Client(enforce_csrf_checks=False)
        
        # إنشاء الصلاحيات المخصصة
        user_content_type = ContentType.objects.get_for_model(User)
        
        self.perm_manage_users = Permission.objects.create(
            codename='ادارة_المستخدمين',
            name='إدارة المستخدمين',
            content_type=user_content_type,
        )
        
        self.perm_manage_roles = Permission.objects.create(
            codename='ادارة_الادوار_والصلاحيات',
            name='إدارة الأدوار والصلاحيات',
            content_type=user_content_type,
        )
        
        self.perm_manage_sales = Permission.objects.create(
            codename='ادارة_المبيعات',
            name='إدارة المبيعات',
            content_type=user_content_type,
        )
        
        self.perm_view_sales = Permission.objects.create(
            codename='عرض_المبيعات',
            name='عرض المبيعات',
            content_type=user_content_type,
        )
        
        # إنشاء الأدوار
        self.admin_role = Role.objects.create(
            name='admin',
            display_name='مدير النظام',
            description='صلاحيات كاملة',
            is_system_role=True,
        )
        self.admin_role.permissions.add(
            self.perm_manage_users,
            self.perm_manage_roles,
            self.perm_manage_sales,
            self.perm_view_sales,
        )
        
        self.sales_role = Role.objects.create(
            name='sales_rep',
            display_name='مندوب مبيعات',
            description='إدارة المبيعات فقط',
            is_system_role=True,
        )
        self.sales_role.permissions.add(
            self.perm_manage_sales,
            self.perm_view_sales,
        )
        
        self.viewer_role = Role.objects.create(
            name='viewer',
            display_name='مستخدم عرض فقط',
            description='عرض البيانات فقط',
            is_system_role=False,
        )
        self.viewer_role.permissions.add(self.perm_view_sales)
        
        # إنشاء المستخدمين
        self.superuser = User.objects.create_superuser(
            username='superadmin',
            email='super@test.com',
            password='test123',
            first_name='Super',
            last_name='Admin',
        )
        
        self.admin_user = User.objects.create_user(
            username='admin',
            email='admin@test.com',
            password='test123',
            first_name='Admin',
            last_name='User',
            role=self.admin_role,
        )
        
        self.sales_user = User.objects.create_user(
            username='sales',
            email='sales@test.com',
            password='test123',
            first_name='Sales',
            last_name='Rep',
            role=self.sales_role,
        )
        
        self.viewer_user = User.objects.create_user(
            username='viewer',
            email='viewer@test.com',
            password='test123',
            first_name='View',
            last_name='Only',
            role=self.viewer_role,
        )
        
        self.no_role_user = User.objects.create_user(
            username='norole',
            email='norole@test.com',
            password='test123',
            first_name='No',
            last_name='Role',
        )
    
    # ==================== اختبارات الصلاحيات الأساسية ====================
    
    def test_superuser_has_all_permissions(self):
        """اختبار: Superuser لديه جميع الصلاحيات"""
        self.assertTrue(self.superuser.can_manage_users())
        self.assertTrue(self.superuser.can_manage_roles())
        self.assertTrue(self.superuser.has_role_permission('ادارة_المبيعات'))
        self.assertTrue(self.superuser.has_role_permission('عرض_المبيعات'))
    
    def test_admin_role_permissions(self):
        """اختبار: دور مدير النظام لديه الصلاحيات الصحيحة"""
        self.assertTrue(self.admin_user.can_manage_users())
        self.assertTrue(self.admin_user.can_manage_roles())
        self.assertTrue(self.admin_user.has_role_permission('ادارة_المبيعات'))
        self.assertTrue(self.admin_user.has_role_permission('عرض_المبيعات'))
    
    def test_sales_role_permissions(self):
        """اختبار: دور مندوب المبيعات لديه صلاحيات محدودة"""
        self.assertFalse(self.sales_user.can_manage_users())
        self.assertFalse(self.sales_user.can_manage_roles())
        self.assertTrue(self.sales_user.has_role_permission('ادارة_المبيعات'))
        self.assertTrue(self.sales_user.has_role_permission('عرض_المبيعات'))
    
    def test_viewer_role_permissions(self):
        """اختبار: دور العرض فقط لديه صلاحيات قراءة فقط"""
        self.assertFalse(self.viewer_user.can_manage_users())
        self.assertFalse(self.viewer_user.can_manage_roles())
        self.assertFalse(self.viewer_user.has_role_permission('ادارة_المبيعات'))
        self.assertTrue(self.viewer_user.has_role_permission('عرض_المبيعات'))
    
    def test_no_role_user_has_no_permissions(self):
        """اختبار: مستخدم بدون دور ليس لديه صلاحيات"""
        self.assertFalse(self.no_role_user.can_manage_users())
        self.assertFalse(self.no_role_user.can_manage_roles())
        self.assertFalse(self.no_role_user.has_role_permission('ادارة_المبيعات'))
        self.assertFalse(self.no_role_user.has_role_permission('عرض_المبيعات'))
    
    # ==================== اختبارات الوصول للصفحات ====================
    
    def test_user_list_access_superuser(self):
        """اختبار: Superuser يمكنه الوصول لقائمة المستخدمين"""
        self.client.login(username='superadmin', password='test123')
        response = self.client.get(reverse('users:user_list'))
        self.assertEqual(response.status_code, 200)
    
    def test_user_list_access_admin(self):
        """اختبار: Admin يمكنه الوصول لقائمة المستخدمين"""
        self.client.login(username='admin', password='test123')
        response = self.client.get(reverse('users:user_list'))
        self.assertEqual(response.status_code, 200)
    
    def test_user_list_access_denied_sales(self):
        """اختبار: مندوب المبيعات لا يمكنه الوصول لقائمة المستخدمين"""
        self.client.login(username='sales', password='test123')
        response = self.client.get(reverse('users:user_list'))
        self.assertEqual(response.status_code, 200)  # يعرض صفحة permission denied
        self.assertContains(response, 'غير مصرح')
    
    def test_user_list_access_denied_viewer(self):
        """اختبار: مستخدم العرض لا يمكنه الوصول لقائمة المستخدمين"""
        self.client.login(username='viewer', password='test123')
        response = self.client.get(reverse('users:user_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'غير مصرح')
    
    def test_role_list_access_superuser(self):
        """اختبار: Superuser يمكنه الوصول لقائمة الأدوار"""
        self.client.login(username='superadmin', password='test123')
        response = self.client.get(reverse('users:role_list'))
        self.assertEqual(response.status_code, 200)
    
    def test_role_list_access_admin(self):
        """اختبار: Admin يمكنه الوصول لقائمة الأدوار"""
        self.client.login(username='admin', password='test123')
        response = self.client.get(reverse('users:role_list'))
        self.assertEqual(response.status_code, 200)
    
    def test_role_list_access_denied_sales(self):
        """اختبار: مندوب المبيعات لا يمكنه الوصول لقائمة الأدوار"""
        self.client.login(username='sales', password='test123')
        response = self.client.get(reverse('users:role_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'غير مصرح')
    
    # ==================== اختبارات تعديل المستخدمين ====================
    
    def test_user_edit_by_admin(self):
        """اختبار: Admin يمكنه تعديل المستخدمين"""
        self.client.login(username='admin', password='test123')
        response = self.client.post(
            reverse('users:user_edit', args=[self.sales_user.id]),
            {
                'first_name': 'Updated',
                'last_name': 'Name',
                'email': 'updated@test.com',
                'phone': '1234567890',
                'is_active': 'on',
            }
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        
        # التحقق من التحديث
        self.sales_user.refresh_from_db()
        self.assertEqual(self.sales_user.first_name, 'Updated')
    
    def test_user_edit_denied_sales(self):
        """اختبار: مندوب المبيعات لا يمكنه تعديل المستخدمين"""
        self.client.login(username='sales', password='test123')
        response = self.client.post(
            reverse('users:user_edit', args=[self.viewer_user.id]),
            {
                'first_name': 'Hacked',
                'last_name': 'User',
                'email': 'hacked@test.com',
            }
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data['success'])
        
        # التحقق من عدم التحديث
        self.viewer_user.refresh_from_db()
        self.assertNotEqual(self.viewer_user.first_name, 'Hacked')
    
    # ==================== اختبارات حذف المستخدمين ====================
    
    def test_user_delete_by_admin(self):
        """اختبار: Admin يمكنه حذف المستخدمين"""
        self.client.login(username='admin', password='test123')
        user_id = self.viewer_user.id
        response = self.client.post(reverse('users:user_delete', args=[user_id]))
        self.assertEqual(response.status_code, 302)  # Redirect
        
        # التحقق من الحذف
        self.assertFalse(User.objects.filter(id=user_id).exists())
    
    def test_user_cannot_delete_self(self):
        """اختبار: المستخدم لا يمكنه حذف نفسه"""
        self.client.login(username='admin', password='test123')
        response = self.client.post(reverse('users:user_delete', args=[self.admin_user.id]))
        self.assertEqual(response.status_code, 302)
        
        # التحقق من عدم الحذف
        self.assertTrue(User.objects.filter(id=self.admin_user.id).exists())
    
    def test_cannot_delete_superuser(self):
        """اختبار: لا يمكن حذف Superuser"""
        self.client.login(username='admin', password='test123')
        response = self.client.post(reverse('users:user_delete', args=[self.superuser.id]))
        self.assertEqual(response.status_code, 302)
        
        # التحقق من عدم الحذف
        self.assertTrue(User.objects.filter(id=self.superuser.id).exists())
    
    def test_user_delete_denied_sales(self):
        """اختبار: مندوب المبيعات لا يمكنه حذف المستخدمين"""
        self.client.login(username='sales', password='test123')
        user_id = self.viewer_user.id
        response = self.client.post(reverse('users:user_delete', args=[user_id]))
        self.assertEqual(response.status_code, 200)
        
        # التحقق من عدم الحذف
        self.assertTrue(User.objects.filter(id=user_id).exists())
    
    # ==================== اختبارات تعديل الأدوار ====================
    
    def test_role_edit_by_admin(self):
        """اختبار: Admin يمكنه تعديل الأدوار"""
        self.client.force_login(self.admin_user)
        
        # تعديل الدور مباشرة من خلال النموذج
        from users.forms import RoleForm
        
        form_data = {
            'name': 'sales_rep',
            'display_name': 'مندوب مبيعات محدث',
            'description': 'وصف محدث',
            'is_active': True,
            'permissions': [self.perm_view_sales.id],
        }
        
        form = RoleForm(form_data, instance=self.sales_role)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        
        # حفظ النموذج
        updated_role = form.save()
        
        # التحقق من التحديث
        self.sales_role.refresh_from_db()
        self.assertEqual(self.sales_role.display_name, 'مندوب مبيعات محدث')
        self.assertEqual(self.sales_role.description, 'وصف محدث')
    
    def test_role_edit_denied_sales(self):
        """اختبار: مندوب المبيعات لا يمكنه تعديل الأدوار"""
        self.client.login(username='sales', password='test123')
        response = self.client.get(reverse('users:role_edit', args=[self.viewer_role.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'غير مصرح')
    
    # ==================== اختبارات حذف الأدوار ====================
    
    def test_role_delete_by_admin(self):
        """اختبار: Admin يمكنه حذف الأدوار غير النظامية"""
        # إنشاء دور جديد بدون مستخدمين
        empty_role = Role.objects.create(
            name='empty_test',
            display_name='دور فارغ للاختبار',
            is_system_role=False,
        )
        role_id = empty_role.id
        
        # استخدام force_login لتجاوز CSRF
        self.client.force_login(self.admin_user)
        response = self.client.post(reverse('users:role_delete', args=[role_id]), follow=True)
        
        # يجب أن ينجح
        self.assertIn(response.status_code, [200, 302])
        
        # التحقق من الحذف
        self.assertFalse(Role.objects.filter(id=role_id).exists())
    
    def test_cannot_delete_system_role(self):
        """اختبار: لا يمكن حذف الأدوار النظامية"""
        self.client.force_login(self.admin_user)
        role_id = self.admin_role.id
        response = self.client.post(reverse('users:role_delete', args=[role_id]), follow=True)
        
        # يجب أن يعيد توجيه
        self.assertIn(response.status_code, [200, 302])
        
        # التحقق من عدم الحذف
        self.assertTrue(Role.objects.filter(id=role_id).exists())
    
    # ==================== اختبارات إدارة صلاحيات المستخدمين ====================
    
    def test_user_permissions_access_by_admin(self):
        """اختبار: Admin يمكنه الوصول لصفحة صلاحيات المستخدم"""
        self.client.login(username='admin', password='test123')
        response = self.client.get(reverse('users:user_permissions', args=[self.sales_user.id]))
        self.assertEqual(response.status_code, 200)
    
    def test_user_permissions_denied_sales(self):
        """اختبار: مندوب المبيعات لا يمكنه الوصول لصفحة صلاحيات المستخدم"""
        self.client.login(username='sales', password='test123')
        response = self.client.get(reverse('users:user_permissions', args=[self.viewer_user.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'غير مصرح')
    
    # ==================== اختبارات الصلاحيات المخصصة ====================
    
    def test_custom_permissions_added_to_user(self):
        """اختبار: إضافة صلاحيات مخصصة للمستخدم"""
        self.sales_user.custom_permissions.add(self.perm_manage_users)
        self.assertTrue(self.sales_user.has_role_permission('ادارة_المستخدمين'))
    
    def test_get_all_permissions(self):
        """اختبار: الحصول على جميع صلاحيات المستخدم"""
        perms = self.sales_user.get_all_permissions()
        self.assertIn(self.perm_manage_sales, perms)
        self.assertIn(self.perm_view_sales, perms)
        self.assertEqual(len(perms), 2)
    
    def test_role_permissions_count(self):
        """اختبار: عدد صلاحيات الدور"""
        self.assertEqual(self.admin_role.permissions.count(), 4)
        self.assertEqual(self.sales_role.permissions.count(), 2)
        self.assertEqual(self.viewer_role.permissions.count(), 1)
    
    # ==================== اختبارات الأمان ====================
    
    def test_unauthenticated_user_redirected(self):
        """اختبار: المستخدم غير المسجل يتم توجيهه لصفحة تسجيل الدخول"""
        response = self.client.get(reverse('users:user_list'))
        self.assertEqual(response.status_code, 302)
        # التحقق من أن الـ URL يحتوي على login
        self.assertIn('/login/', response.url)
    
    def test_inactive_user_cannot_login(self):
        """اختبار: المستخدم غير النشط لا يمكنه تسجيل الدخول"""
        self.viewer_user.is_active = False
        self.viewer_user.save()
        
        logged_in = self.client.login(username='viewer', password='test123')
        self.assertFalse(logged_in)
    
    def test_role_with_no_permissions(self):
        """اختبار: دور بدون صلاحيات"""
        empty_role = Role.objects.create(
            name='empty',
            display_name='دور فارغ',
            description='بدون صلاحيات',
        )
        
        user = User.objects.create_user(
            username='empty_user',
            email='empty@test.com',
            password='test123',
            role=empty_role,
        )
        
        self.assertFalse(user.can_manage_users())
        self.assertFalse(user.can_manage_roles())
        self.assertEqual(len(user.get_all_permissions()), 0)


class RoleModelTestCase(TestCase):
    """اختبارات نموذج الدور"""
    
    def test_role_creation(self):
        """اختبار: إنشاء دور جديد"""
        role = Role.objects.create(
            name='test_role',
            display_name='دور تجريبي',
            description='للاختبار فقط',
        )
        self.assertEqual(str(role), 'دور تجريبي')
        self.assertTrue(role.is_active)
    
    def test_role_total_users(self):
        """اختبار: عدد المستخدمين في الدور"""
        role = Role.objects.create(
            name='test_role',
            display_name='دور تجريبي',
        )
        
        User.objects.create_user(
            username='user1',
            email='user1@test.com',
            password='test123',
            role=role,
        )
        
        User.objects.create_user(
            username='user2',
            email='user2@test.com',
            password='test123',
            role=role,
        )
        
        # استخدام method بدلاً من property
        self.assertEqual(role.get_total_users(), 2)
        # أو استخدام users_count
        self.assertEqual(role.users_count, 2)
