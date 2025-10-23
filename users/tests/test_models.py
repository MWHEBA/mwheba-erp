"""
اختبارات نماذج المستخدمين والصلاحيات
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

User = get_user_model()


class UserModelTest(TestCase):
    """اختبارات نموذج المستخدمين"""
    
    def test_create_user(self):
        """اختبار إنشاء مستخدم عادي"""
        user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
            first_name="أحمد",
            last_name="محمد"
        )
        
        self.assertEqual(user.username, "testuser")
        self.assertEqual(user.email, "test@example.com")
        self.assertEqual(user.first_name, "أحمد")
        self.assertEqual(user.last_name, "محمد")
        self.assertTrue(user.check_password("testpass123"))
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        
    def test_create_superuser(self):
        """اختبار إنشاء مستخدم مدير"""
        admin = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="adminpass123"
        )
        
        self.assertEqual(admin.username, "admin")
        self.assertTrue(admin.is_active)
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        
    def test_user_str_method(self):
        """اختبار طريقة __str__ للمستخدم"""
        user = User.objects.create_user(
            username="testuser",
            first_name="أحمد",
            last_name="محمد"
        )
        
        # يجب أن تعرض الاسم الكامل أو اسم المستخدم
        str_result = str(user)
        self.assertTrue(
            "أحمد محمد" in str_result or "testuser" in str_result
        )
        
    def test_user_full_name(self):
        """اختبار الحصول على الاسم الكامل"""
        user = User.objects.create_user(
            username="testuser",
            first_name="أحمد",
            last_name="محمد"
        )
        
        full_name = user.get_full_name()
        self.assertEqual(full_name, "أحمد محمد")
        
    def test_user_short_name(self):
        """اختبار الحصول على الاسم المختصر"""
        user = User.objects.create_user(
            username="testuser",
            first_name="أحمد"
        )
        
        short_name = user.get_short_name()
        self.assertEqual(short_name, "أحمد")


class UserPermissionsTest(TestCase):
    """اختبارات صلاحيات المستخدمين"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.user = User.objects.create_user(
            username="testuser",
            password="test123"
        )
        
        # إنشاء صلاحيات للاختبار
        content_type = ContentType.objects.get_for_model(User)
        self.permission = Permission.objects.create(
            codename='test_permission',
            name='Test Permission',
            content_type=content_type,
        )
        
    def test_user_permissions(self):
        """اختبار صلاحيات المستخدم المباشرة"""
        # إضافة صلاحية للمستخدم
        self.user.user_permissions.add(self.permission)
        
        # التحقق من وجود الصلاحية
        self.assertTrue(
            self.user.has_perm('auth.test_permission')
        )
        
    def test_user_groups(self):
        """اختبار مجموعات المستخدم"""
        # إنشاء مجموعة
        group = Group.objects.create(name='Test Group')
        group.permissions.add(self.permission)
        
        # إضافة المستخدم للمجموعة
        self.user.groups.add(group)
        
        # التحقق من عضوية المجموعة
        self.assertTrue(
            self.user.groups.filter(name='Test Group').exists()
        )
        
        # التحقق من الصلاحية عبر المجموعة
        self.assertTrue(
            self.user.has_perm('auth.test_permission')
        )
        
    def test_superuser_permissions(self):
        """اختبار صلاحيات المدير العام"""
        admin = User.objects.create_superuser(
            username="admin",
            password="admin123"
        )
        
        # المدير العام يجب أن يملك جميع الصلاحيات
        self.assertTrue(admin.has_perm('any.permission'))
        self.assertTrue(admin.has_module_perms('any_app'))


class UserGroupsTest(TestCase):
    """اختبارات مجموعات المستخدمين"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.user = User.objects.create_user(
            username="testuser",
            password="test123"
        )
        
    def test_create_group(self):
        """اختبار إنشاء مجموعة"""
        group = Group.objects.create(name='محاسبين')
        
        self.assertEqual(group.name, 'محاسبين')
        
    def test_add_user_to_group(self):
        """اختبار إضافة مستخدم لمجموعة"""
        group = Group.objects.create(name='مندوبي مبيعات')
        
        # إضافة المستخدم للمجموعة
        self.user.groups.add(group)
        
        # التحقق من العضوية
        self.assertTrue(
            self.user.groups.filter(name='مندوبي مبيعات').exists()
        )
        
    def test_remove_user_from_group(self):
        """اختبار إزالة مستخدم من مجموعة"""
        group = Group.objects.create(name='أمناء مخازن')
        
        # إضافة ثم إزالة
        self.user.groups.add(group)
        self.user.groups.remove(group)
        
        # التحقق من عدم العضوية
        self.assertFalse(
            self.user.groups.filter(name='أمناء مخازن').exists()
        )
        
    def test_group_permissions(self):
        """اختبار صلاحيات المجموعة"""
        group = Group.objects.create(name='مراجعين')
        
        # إضافة صلاحيات للمجموعة
        content_type = ContentType.objects.get_for_model(User)
        permission = Permission.objects.create(
            codename='view_reports',
            name='View Reports',
            content_type=content_type,
        )
        
        group.permissions.add(permission)
        
        # التحقق من صلاحيات المجموعة
        self.assertTrue(
            group.permissions.filter(codename='view_reports').exists()
        )


class UserRolesTest(TestCase):
    """اختبارات أدوار المستخدمين"""
    
    def test_admin_role(self):
        """اختبار دور المدير"""
        admin = User.objects.create_user(
            username="admin",
            password="admin123",
            is_staff=True,
            is_superuser=True
        )
        
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        
    def test_staff_role(self):
        """اختبار دور الموظف"""
        staff = User.objects.create_user(
            username="staff",
            password="staff123",
            is_staff=True
        )
        
        self.assertTrue(staff.is_staff)
        self.assertFalse(staff.is_superuser)
        
    def test_regular_user_role(self):
        """اختبار دور المستخدم العادي"""
        user = User.objects.create_user(
            username="user",
            password="user123"
        )
        
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)


class UserBusinessLogicTest(TestCase):
    """اختبارات منطق الأعمال للمستخدمين"""
    
    def test_user_activation(self):
        """اختبار تفعيل/إلغاء تفعيل المستخدم"""
        user = User.objects.create_user(
            username="testuser",
            password="test123"
        )
        
        # المستخدم نشط افتراضياً
        self.assertTrue(user.is_active)
        
        # إلغاء التفعيل
        user.is_active = False
        user.save()
        
        self.assertFalse(user.is_active)
        
        # إعادة التفعيل
        user.is_active = True
        user.save()
        
        self.assertTrue(user.is_active)
        
    def test_password_change(self):
        """اختبار تغيير كلمة المرور"""
        user = User.objects.create_user(
            username="testuser",
            password="oldpass123"
        )
        
        # التحقق من كلمة المرور القديمة
        self.assertTrue(user.check_password("oldpass123"))
        
        # تغيير كلمة المرور
        user.set_password("newpass123")
        user.save()
        
        # التحقق من كلمة المرور الجديدة
        self.assertTrue(user.check_password("newpass123"))
        self.assertFalse(user.check_password("oldpass123"))
        
    def test_user_profile_update(self):
        """اختبار تحديث ملف المستخدم"""
        user = User.objects.create_user(
            username="testuser",
            first_name="أحمد",
            last_name="محمد",
            email="old@example.com"
        )
        
        # تحديث البيانات
        user.first_name = "محمد"
        user.last_name = "أحمد"
        user.email = "new@example.com"
        user.save()
        
        # التحقق من التحديث
        updated_user = User.objects.get(username="testuser")
        self.assertEqual(updated_user.first_name, "محمد")
        self.assertEqual(updated_user.last_name, "أحمد")
        self.assertEqual(updated_user.email, "new@example.com")


class UserSecurityTest(TestCase):
    """اختبارات أمان المستخدمين"""
    
    def test_password_hashing(self):
        """اختبار تشفير كلمة المرور"""
        user = User.objects.create_user(
            username="testuser",
            password="plaintext123"
        )
        
        # كلمة المرور يجب أن تكون مشفرة
        self.assertNotEqual(user.password, "plaintext123")
        self.assertTrue(user.password.startswith('pbkdf2_'))
        
    def test_invalid_login(self):
        """اختبار تسجيل الدخول بكلمة مرور خاطئة"""
        user = User.objects.create_user(
            username="testuser",
            password="correct123"
        )
        
        # كلمة مرور صحيحة
        self.assertTrue(user.check_password("correct123"))
        
        # كلمة مرور خاطئة
        self.assertFalse(user.check_password("wrong123"))
        
    def test_inactive_user_permissions(self):
        """اختبار صلاحيات المستخدم غير النشط"""
        user = User.objects.create_user(
            username="testuser",
            password="test123",
            is_active=False
        )
        
        # المستخدم غير النشط لا يجب أن يملك صلاحيات
        self.assertFalse(user.is_active)
        
        # حتى لو كان له صلاحيات، فهو غير نشط
        content_type = ContentType.objects.get_for_model(User)
        permission = Permission.objects.create(
            codename='test_perm',
            name='Test Permission',
            content_type=content_type,
        )
        
        user.user_permissions.add(permission)
        
        # الصلاحية موجودة لكن المستخدم غير نشط
        self.assertTrue(
            user.user_permissions.filter(codename='test_perm').exists()
        )
        self.assertFalse(user.is_active)
