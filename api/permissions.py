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

        # السماح بالكتابة فقط للمالك
        return obj.created_by == request.user or request.user.is_staff


class IsSuperuser(permissions.BasePermission):
    """
    صلاحية مخصصة تسمح فقط لمدير النظام (superuser) بالوصول.
    """

    def has_permission(self, request, view):
        return request.user and request.user.is_superuser

    def has_object_permission(self, request, view, obj):
        return request.user and request.user.is_superuser


class IsManagerOrReadOnly(permissions.BasePermission):
    """
    صلاحية مخصصة تسمح للمديرين بالوصول الكامل ولغيرهم بالقراءة فقط.
    """

    def has_permission(self, request, view):
        # السماح بطلبات القراءة لأي مستخدم مسجل
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated

        # السماح بالكتابة فقط للمديرين
        return request.user and request.user.is_staff

    def has_object_permission(self, request, view, obj):
        # السماح بطلبات القراءة لأي مستخدم مسجل
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated

        # السماح بالكتابة فقط للمديرين
        return request.user and request.user.is_staff


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