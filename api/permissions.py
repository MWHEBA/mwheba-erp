from rest_framework import permissions
from django.contrib.auth import get_user_model
from rest_framework.permissions import BasePermission

User = get_user_model()


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    صلاحية مخصصة تسمح فقط لمالك الكائن بتعديله أو حذفه.
    تسمح للجميع بالقراءة فقط.
    """

    def has_object_permission(self, request, view, obj):
        # السماح بطلبات القراءة لأي مستخدم
        if request.method in permissions.SAFE_METHODS:
            return True

        # السماح بالكتابة فقط للمالك أو المشرف
        return obj.created_by == request.user or request.user.is_superuser or getattr(request.user, 'is_admin', False)


class IsSuperuser(permissions.BasePermission):
    """
    صلاحية مخصصة تسمح فقط لمدير النظام (superuser) بالوصول.
    """

    def has_permission(self, request, view):
        return request.user and request.user.is_superuser

    def has_object_permission(self, request, view, obj):
        return request.user and request.user.is_superuser


class RoleBasedModelPermissions(permissions.DjangoModelPermissions):
    """
    صلاحية معيارية مشتقة من DjangoModelPermissions تفحص أيضاً عمليات القراءة (SAFE_METHODS).
    تتطلب صلاحية view_<model> للقراءة، وتتحقق من add/change/delete للعمليات الأخرى.
    """
    perms_map = {
        'GET': ['%(app_label)s.view_%(model_name)s'],
        'OPTIONS': [],
        'HEAD': [],
        'POST': ['%(app_label)s.add_%(model_name)s'],
        'PUT': ['%(app_label)s.change_%(model_name)s'],
        'PATCH': ['%(app_label)s.change_%(model_name)s'],
        'DELETE': ['%(app_label)s.delete_%(model_name)s'],
    }

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser or getattr(request.user, 'is_admin', False):
            return True
        return super().has_permission(request, view)


class IsManagerOrReadOnly(permissions.BasePermission):
    """
    صلاحية آمنة تتطلب صلاحية عرض النموذج للقراءة وتتطلب صلاحية الإدارة أو التعديل للكتابة.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser or getattr(request.user, 'is_admin', False):
            return True

        # للعمليات الآمنة (قراءة)، تحقق من وجود صلاحية العرض إذا كان الـ view يحدد queryset/model
        if request.method in permissions.SAFE_METHODS:
            queryset = getattr(view, 'queryset', None)
            if queryset is not None:
                model = queryset.model
                app_label = model._meta.app_label
                model_name = model._meta.model_name
                return request.user.has_perm(f'{app_label}.view_{model_name}')
            return True

        # للعمليات التعديلية (كتابة)، تحقق من الإدارة أو صلاحيات التعديل
        return getattr(request.user, 'is_admin', False) or request.user.is_staff

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser or getattr(request.user, 'is_admin', False):
            return True

        if request.method in permissions.SAFE_METHODS:
            app_label = obj._meta.app_label
            model_name = obj._meta.model_name
            return request.user.has_perm(f'{app_label}.view_{model_name}')

        return getattr(request.user, 'is_admin', False) or request.user.is_staff


class IsAuthenticated(permissions.BasePermission):
    """
    صلاحية مخصصة تتحقق أن المستخدم مسجل الدخول.
    """

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated


class IsOwner(permissions.BasePermission):
    """
    صلاحية مخصصة تسمح فقط لمالك الكائن بالوصول إليه.
    """

    def has_object_permission(self, request, view, obj):
        # التحقق من أن المستخدم هو المالك
        return obj.created_by == request.user


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    صلاحية مخصصة تسمح للمدير بالوصول الكامل ولغيره بالقراءة فقط.
    """

    def has_permission(self, request, view):
        # السماح بطلبات القراءة لأي مستخدم
        if request.method in permissions.SAFE_METHODS:
            return True

        # السماح بالكتابة فقط للمديرين
        return request.user and request.user.is_staff
