from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q


class EmailOrUsernameModelBackend(ModelBackend):
    """
    Backend لمصادقة المستخدم سواء باستخدام اسم المستخدم أو البريد الإلكتروني (غير حساس لحالة الأحرف).
    Authenticates against settings.AUTH_USER_MODEL using either username or email.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if not username or not password:
            return None

        username_clean = str(username).strip()
        users = UserModel._default_manager.filter(
            Q(username__iexact=username_clean) | Q(email__iexact=username_clean)
        )

        for user in users:
            if user.check_password(password) and self.user_can_authenticate(user):
                return user

        if not users.exists():
            # Run the default password hasher once to reduce timing differences
            UserModel().set_password(password)

        return None


class RolePermissionBackend:
    """
    Backend يضيف Role-based permissions لـ Django's has_perm() system.
    بيشتغل جنب EmailOrUsernameModelBackend.
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

        # استخراج الـ codename من الـ perm (مثال: 'client.view_customer' → 'view_customer')
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
