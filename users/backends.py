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


from django.core.cache import cache
from django.contrib.auth.models import Permission


class RolePermissionBackend(ModelBackend):
    """
    الباك إند المعياري الحقيقي لـ MWHEBA ERP.
    - متوافق 100% مع عقد جانغو القياسي.
    - كاش ثنائي الطبقات: Tier-1 (Request Cache) + Tier-2 (django.core.cache).
    - حقن تلقائي لتبعيات المبيعات والمشتريات التشغيلية $O(1)$.
    - مطابقة صريحة على مستوى (app_label.codename) بدون أي تجريد.
    - صفر استعلامات إضافية للـ Superuser/Admin.
    """

    from users.services.permission_dependency import PermissionDependencyService
    IMPLICIT_DEPENDENCIES = PermissionDependencyService.DEPENDENCY_MAP

    def authenticate(self, request, **kwargs):
        return None

    def get_group_permissions(self, user_obj, obj=None):
        if not user_obj.is_authenticated or not user_obj.is_active:
            return set()
        if not hasattr(user_obj, '_cached_group_permissions'):
            roles_to_inspect = []
            if hasattr(user_obj, 'role') and user_obj.role:
                roles_to_inspect.append(user_obj.role)
            if hasattr(user_obj, 'secondary_roles'):
                roles_to_inspect.extend(list(user_obj.secondary_roles.all()))

            # دعم هرمية الأدوار وتوريث الصلاحيات من الدور الأب (Role Hierarchy)
            visited_role_ids = set()
            while roles_to_inspect:
                current_role = roles_to_inspect.pop()
                if not current_role or current_role.id in visited_role_ids:
                    continue
                visited_role_ids.add(current_role.id)
                if current_role.parent_role_id and current_role.parent_role_id not in visited_role_ids:
                    roles_to_inspect.append(current_role.parent_role)

            if visited_role_ids:
                perms_tuples = Permission.objects.filter(
                    user_roles__in=visited_role_ids
                ).values_list('content_type__app_label', 'codename')
                perms = {f"{app}.{code}" for app, code in perms_tuples}
            else:
                perms = set()

            user_obj._cached_group_permissions = perms
        return user_obj._cached_group_permissions

    def get_user_permissions(self, user_obj, obj=None):
        if not user_obj.is_authenticated or not user_obj.is_active:
            return set()
        if not hasattr(user_obj, '_cached_user_permissions'):
            perms = set()
            if hasattr(user_obj, 'custom_permissions'):
                perms.update(
                    f"{app}.{code}"
                    for app, code in user_obj.custom_permissions.values_list('content_type__app_label', 'codename')
                )
            if hasattr(user_obj, 'user_permissions'):
                perms.update(
                    f"{app}.{code}"
                    for app, code in user_obj.user_permissions.values_list('content_type__app_label', 'codename')
                )
            user_obj._cached_user_permissions = perms
        return user_obj._cached_user_permissions

    def get_all_permissions(self, user_obj, obj=None):
        if not user_obj.is_authenticated or not user_obj.is_active:
            return set()

        # 1. فحص كاش الطلب (Tier-1 Cache)
        if hasattr(user_obj, '_cached_permissions'):
            return user_obj._cached_permissions

        # 2. للمدير والسوبر يوزر: استرجاع الصلاحيات دون كويريز ثقيلة متكررة
        if user_obj.is_superuser or getattr(user_obj, 'is_admin', False):
            # كاش الـ Admin / Superuser
            admin_cache_key = "all_system_permissions_set"
            all_perms = cache.get(admin_cache_key)
            if all_perms is None:
                all_perms = {
                    f"{p.content_type.app_label}.{p.codename}"
                    for p in Permission.objects.select_related('content_type').all()
                }
                cache.set(admin_cache_key, all_perms, 3600)
            user_obj._cached_permissions = all_perms
            return user_obj._cached_permissions

        # 3. فحص كاش السيرفر (Tier-2 Cache) للمستخدم العادي
        cache_key = f"user_perms_{user_obj.id}"
        cached_perms = cache.get(cache_key)
        if cached_perms is not None:
            user_obj._cached_permissions = cached_perms
            return user_obj._cached_permissions

        # 4. حساب الصلاحيات من الدور والمستخدم
        raw_perms = self.get_group_permissions(user_obj, obj) | self.get_user_permissions(user_obj, obj)
        resolved_perms = set(raw_perms)

        # 5. حقن التبعيات التشغيلية تلقائياً
        for parent_perm, deps in self.IMPLICIT_DEPENDENCIES.items():
            if parent_perm in raw_perms:
                resolved_perms.update(deps)

        # 6. طرح الصلاحيات المستثناة أو المحجوبة صراحة (Revocations Subtraction)
        if hasattr(user_obj, 'revoked_permissions'):
            revoked_set = {
                f"{app}.{code}"
                for app, code in user_obj.revoked_permissions.values_list('content_type__app_label', 'codename')
            }
            resolved_perms.difference_update(revoked_set)

        # حفظ في Tier-2 Cache (5 دقائق)
        cache.set(cache_key, resolved_perms, 300)
        user_obj._cached_permissions = resolved_perms
        return user_obj._cached_permissions

    def has_perm(self, user_obj, perm, obj=None):
        if not user_obj.is_authenticated or not user_obj.is_active:
            return False
        if user_obj.is_superuser or getattr(user_obj, 'is_admin', False):
            return True

        user_perms = self.get_all_permissions(user_obj, obj)
        return perm in user_perms

    def has_module_perms(self, user_obj, app_label):
        if not user_obj.is_authenticated or not user_obj.is_active:
            return False
        if user_obj.is_superuser or getattr(user_obj, 'is_admin', False):
            return True
        return any(p.startswith(f"{app_label}.") for p in self.get_all_permissions(user_obj))

