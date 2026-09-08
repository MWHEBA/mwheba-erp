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


from django.contrib.auth.models import Permission


class RolePermissionBackend(ModelBackend):
    """
    الباك إند المعياري الحقيقي لـ MWHEBA ERP.
    - متوافق 100% مع عقد جانغو.
    - كاش لحظي فائق السرعة O(1) على مستوى الطلب بصفر استعلامات متكررة.
    - مطابقة صريحة على مستوى (app_label.codename) بدون أي تجريد أو ترقيع.
    """

    def authenticate(self, request, **kwargs):
        return None

    def get_group_permissions(self, user_obj, obj=None):
        if not user_obj.is_authenticated or not user_obj.is_active:
            return set()
        if not hasattr(user_obj, '_cached_group_permissions'):
            if hasattr(user_obj, 'role') and user_obj.role:
                user_obj._cached_group_permissions = {
                    f"{p.content_type.app_label}.{p.codename}"
                    for p in user_obj.role.permissions.select_related('content_type')
                }
            else:
                user_obj._cached_group_permissions = set()
        return user_obj._cached_group_permissions

    def get_user_permissions(self, user_obj, obj=None):
        if not user_obj.is_authenticated or not user_obj.is_active:
            return set()
        if not hasattr(user_obj, '_cached_user_permissions'):
            perms = set()
            if hasattr(user_obj, 'custom_permissions'):
                perms.update(
                    f"{p.content_type.app_label}.{p.codename}"
                    for p in user_obj.custom_permissions.select_related('content_type')
                )
            if hasattr(user_obj, 'user_permissions'):
                perms.update(
                    f"{p.content_type.app_label}.{p.codename}"
                    for p in user_obj.user_permissions.select_related('content_type')
                )
            user_obj._cached_user_permissions = perms
        return user_obj._cached_user_permissions

    def get_all_permissions(self, user_obj, obj=None):
        if not user_obj.is_authenticated or not user_obj.is_active:
            return set()

        if not hasattr(user_obj, '_cached_permissions'):
            if user_obj.is_superuser or getattr(user_obj, 'is_admin', False):
                user_obj._cached_permissions = {
                    f"{p.content_type.app_label}.{p.codename}"
                    for p in Permission.objects.select_related('content_type').all()
                }
            else:
                user_obj._cached_permissions = (
                    self.get_group_permissions(user_obj, obj) |
                    self.get_user_permissions(user_obj, obj)
                )

        return user_obj._cached_permissions

    def has_perm(self, user_obj, perm, obj=None):
        if not user_obj.is_authenticated or not user_obj.is_active:
            return False
        if user_obj.is_superuser or getattr(user_obj, 'is_admin', False):
            return True
        return perm in self.get_all_permissions(user_obj, obj)

    def has_module_perms(self, user_obj, app_label):
        if not user_obj.is_authenticated or not user_obj.is_active:
            return False
        if user_obj.is_superuser or getattr(user_obj, 'is_admin', False):
            return True
        return any(p.startswith(f"{app_label}.") for p in self.get_all_permissions(user_obj))

