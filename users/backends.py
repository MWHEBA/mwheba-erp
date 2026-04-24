"""
Custom Authentication Backend
يخلي has_perm() تشوف Role permissions تلقائياً في كل مكان في المشروع
"""


class RolePermissionBackend:
    """
    Backend يضيف Role-based permissions لـ Django's has_perm() system.
    بيشتغل جنب ModelBackend الأصلي.
    """

    def authenticate(self, request, **kwargs):
        # مش بنعمل authentication هنا
        return None

    def has_perm(self, user_obj, perm, obj=None):
        if not user_obj.is_active:
            return False

        # superuser و admin عندهم كل الصلاحيات
        if user_obj.is_superuser or getattr(user_obj, 'is_admin', False):
            return True

        # استخراج الـ codename من الـ perm (مثال: 'students.view_student' → 'view_student')
        codename = perm.split('.')[-1] if '.' in perm else perm

        # التحقق من Role permissions
        if hasattr(user_obj, 'role') and user_obj.role:
            if user_obj.role.permissions.filter(codename=codename).exists():
                return True

        # التحقق من custom_permissions
        if hasattr(user_obj, 'custom_permissions'):
            if user_obj.custom_permissions.filter(codename=codename).exists():
                return True

        return False

    def has_module_perms(self, user_obj, app_label):
        if not user_obj.is_active:
            return False

        if user_obj.is_superuser or getattr(user_obj, 'is_admin', False):
            return True

        # التحقق من وجود أي permission للـ app في الـ Role
        if hasattr(user_obj, 'role') and user_obj.role:
            if user_obj.role.permissions.filter(
                content_type__app_label=app_label
            ).exists():
                return True

        if hasattr(user_obj, 'custom_permissions'):
            if user_obj.custom_permissions.filter(
                content_type__app_label=app_label
            ).exists():
                return True

        return False
