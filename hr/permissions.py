"""
Permissions لوحدة الموارد البشرية
تعتمد على نظام الأدوار والصلاحيات المخصص (RolePermissionBackend)
"""
from rest_framework import permissions
import logging

logger = logging.getLogger(__name__)


class IsHRStaff(permissions.BasePermission):
    """
    صلاحية الوصول لموارد HR - تعتمد على نظام الأدوار والصلاحيات المخصص
    تستخدم has_perm() اللي بيمر على RolePermissionBackend تلقائياً
    """
    hr_permissions = [
        'view_employee', 'add_employee', 'change_employee', 'delete_employee',
        'view_attendance', 'change_attendance',
        'view_leave', 'add_leave', 'change_leave',
        'view_payroll', 'change_payroll',
        'view_advance', 'add_advance', 'change_advance',
    ]

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser or getattr(request.user, 'is_admin', False):
            return True
        # يكفي أي صلاحية HR واحدة للوصول
        return any(request.user.has_perm(f'hr.{perm}') for perm in self.hr_permissions)


class IsHRManager(permissions.BasePermission):
    """
    صلاحية مدير الموارد البشرية - للعمليات الحساسة
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser or getattr(request.user, 'is_admin', False):
            return True
        return (
            request.user.has_perm('hr.change_employee') and
            request.user.has_perm('hr.delete_employee')
        )


class CanViewEmployee(permissions.BasePermission):
    """
    صلاحية عرض بيانات الموظفين
    للقراءة: view_employee
    للكتابة: change_employee أو add_employee
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser or getattr(request.user, 'is_admin', False):
            return True
        if request.method in permissions.SAFE_METHODS:
            return request.user.has_perm('hr.view_employee')
        return (
            request.user.has_perm('hr.change_employee') or
            request.user.has_perm('hr.add_employee')
        )


class IsEmployeeOrHR(permissions.BasePermission):
    """
    صلاحية الموظف نفسه أو من عنده view_employee
    """
    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser or getattr(request.user, 'is_admin', False):
            return True
        # الموظف يشوف بياناته
        if hasattr(request.user, 'employee') and obj == request.user.employee:
            return True
        return request.user.has_perm('hr.view_employee')


class CanApproveLeave(permissions.BasePermission):
    """
    صلاحية اعتماد الإجازات
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser or getattr(request.user, 'is_admin', False):
            return True
        return request.user.has_perm('hr.can_approve_leaves')


class CanProcessPayroll(permissions.BasePermission):
    """
    صلاحية معالجة الرواتب
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser or getattr(request.user, 'is_admin', False):
            return True
        return (
            request.user.has_perm('hr.view_payroll') or
            request.user.has_perm('hr.change_payroll')
        )


class CanViewAttendance(permissions.BasePermission):
    """
    صلاحية عرض الحضور
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser or getattr(request.user, 'is_admin', False):
            return True
        if hasattr(request.user, 'employee') and obj.employee == request.user.employee:
            return True
        return request.user.has_perm('hr.view_attendance')


class CanManageDepartment(permissions.BasePermission):
    """
    صلاحية إدارة الأقسام
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser or getattr(request.user, 'is_admin', False):
            return True
        return (
            request.user.has_perm('hr.add_department') or
            request.user.has_perm('hr.change_department')
        )


class IsDirectManager(permissions.BasePermission):
    """
    صلاحية المدير المباشر
    """
    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser or getattr(request.user, 'is_admin', False):
            return True
        if hasattr(request.user, 'employee'):
            if hasattr(obj, 'direct_manager') and obj.direct_manager == request.user.employee:
                return True
            if hasattr(obj, 'department') and obj.department.manager == request.user.employee:
                return True
        return False


class CanRequestAdvance(permissions.BasePermission):
    """
    صلاحية طلب سلفة - الموظف النشط فقط
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if not hasattr(request.user, 'employee'):
            return False
        return request.user.employee.status == 'active'


class CanTerminateEmployee(permissions.BasePermission):
    """
    صلاحية إنهاء خدمة الموظفين
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser or getattr(request.user, 'is_admin', False):
            return True
        if not request.user.has_perm('hr.delete_employee'):
            logger.warning(
                f"User {request.user.username} attempted to terminate employee without permission"
            )
            return False
        return True


class CanViewSensitiveData(permissions.BasePermission):
    """
    صلاحية عرض البيانات الحساسة (الرقم القومي، الهاتف، البريد الشخصي)
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser or getattr(request.user, 'is_admin', False):
            return True
        return request.user.has_perm('hr.view_employee')

    def has_object_permission(self, request, view, obj):
        if hasattr(request.user, 'employee') and obj == request.user.employee:
            return True
        return self.has_permission(request, view)
