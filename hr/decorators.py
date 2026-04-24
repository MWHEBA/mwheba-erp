"""
Decorators للصلاحيات في نظام HR
"""
from functools import wraps
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required


def _is_hr_manager(user):
    """Helper: التحقق من صلاحيات HR Manager عبر كل الأنظمة"""
    if user.is_superuser or getattr(user, 'is_admin', False):
        return True
    # hr role تحديداً ممنوع من إدارة العقود - hr_manager فقط
    if hasattr(user, 'role') and user.role and user.role.name == 'hr':
        return False
    # Django Groups
    if user.groups.filter(name='HR Manager').exists():
        return True
    # Role-based permissions
    if hasattr(user, 'role') and user.role:
        if user.role.permissions.filter(codename__in=[
            'change_employee', 'add_employee', 'delete_employee', 'can_manage_employees'
        ]).exists():
            return True
    # Custom permissions
    if hasattr(user, 'custom_permissions'):
        if user.custom_permissions.filter(codename__in=[
            'change_employee', 'add_employee', 'delete_employee', 'can_manage_employees'
        ]).exists():
            return True
    return False


def hr_manager_required(view_func):
    """
    يتطلب أن يكون المستخدم HR Manager
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())

        if not _is_hr_manager(request.user):
            raise PermissionDenied("صلاحيات HR Manager مطلوبة للوصول لهذه الصفحة")

        return view_func(request, *args, **kwargs)
    return wrapper


def can_view_salaries(view_func):
    """يتطلب صلاحية رؤية الرواتب - ممنوع على hr role"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        user = request.user
        # hr role ممنوع صراحةً من رؤية الرواتب
        if hasattr(user, 'role') and user.role and user.role.name == 'hr':
            raise PermissionDenied("ليس لديك صلاحية رؤية الرواتب")
        if not (user.is_superuser or getattr(user, 'is_admin', False) or
                user.groups.filter(name__in=['HR Manager', 'Finance']).exists() or
                user.has_perm('hr.view_payroll') or
                (hasattr(user, 'role') and user.role and user.role.permissions.filter(codename__in=['view_payroll', 'can_process_payroll']).exists())):
            raise PermissionDenied("ليس لديك صلاحية رؤية الرواتب")
        return view_func(request, *args, **kwargs)
    return wrapper


def can_approve_leaves(view_func):
    """يتطلب صلاحية اعتماد الإجازات"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        user = request.user
        if not (user.is_superuser or getattr(user, 'is_admin', False) or
                user.groups.filter(name__in=['HR Manager', 'Department Manager']).exists() or
                (hasattr(user, 'role') and user.role and user.role.permissions.filter(codename__in=['change_leave', 'can_manage_employees']).exists())):
            raise PermissionDenied("ليس لديك صلاحية اعتماد الإجازات")
        return view_func(request, *args, **kwargs)
    return wrapper


def can_process_payroll(view_func):
    """يتطلب صلاحية معالجة الرواتب"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        user = request.user
        if not (user.is_superuser or getattr(user, 'is_admin', False) or
                user.groups.filter(name__in=['HR Manager', 'Finance']).exists() or
                (hasattr(user, 'role') and user.role and user.role.permissions.filter(codename='can_process_payroll').exists())):
            raise PermissionDenied("ليس لديك صلاحية معالجة الرواتب")
        return view_func(request, *args, **kwargs)
    return wrapper


def can_manage_contracts(view_func):
    """يتطلب صلاحية إدارة العقود"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        user = request.user
        if not (user.is_superuser or getattr(user, 'is_admin', False) or
                user.groups.filter(name='HR Manager').exists() or
                (hasattr(user, 'role') and user.role and user.role.permissions.filter(codename__in=['can_manage_contracts', 'change_contract']).exists())):
            raise PermissionDenied("ليس لديك صلاحية إدارة العقود")
        return view_func(request, *args, **kwargs)
    return wrapper


def can_pay_payroll(view_func):
    """يتطلب صلاحية دفع الرواتب (Finance فقط)"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        user = request.user
        if not (user.is_superuser or getattr(user, 'is_admin', False) or
                user.groups.filter(name='Finance').exists() or
                (hasattr(user, 'role') and user.role and user.role.permissions.filter(codename='can_process_payroll').exists())):
            raise PermissionDenied("ليس لديك صلاحية دفع الرواتب - Finance فقط")
        return view_func(request, *args, **kwargs)
    return wrapper


def require_hr(view_func):
    """يتطلب أن يكون المستخدم من HR"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        user = request.user
        if not (user.is_superuser or getattr(user, 'is_admin', False) or
                user.groups.filter(name__in=['HR', 'HR Manager']).exists() or
                (hasattr(user, 'role') and user.role and user.role.name in ['hr', 'hr_manager']) or
                (hasattr(user, 'role') and user.role and user.role.permissions.filter(codename__in=['add_employee', 'change_employee', 'can_manage_employees']).exists())):
            raise PermissionDenied("يجب أن تكون من الموارد البشرية للوصول لهذه الصفحة")
        return view_func(request, *args, **kwargs)
    return wrapper


def can_approve_permissions(view_func):
    """يتطلب صلاحية اعتماد الأذونات"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        user = request.user
        if not (user.is_superuser or getattr(user, 'is_admin', False) or
                user.groups.filter(name__in=['HR Manager', 'Department Manager']).exists() or
                (hasattr(user, 'role') and user.role and user.role.permissions.filter(codename__in=['change_permission', 'can_manage_employees']).exists())):
            raise PermissionDenied("ليس لديك صلاحية اعتماد الأذونات")
        return view_func(request, *args, **kwargs)
    return wrapper
