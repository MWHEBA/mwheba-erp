"""
Decorators للصلاحيات في نظام HR
"""
from functools import wraps
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required


def hr_manager_required(view_func):
    """
    يتطلب أن يكون المستخدم HR Manager
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        
        if not (request.user.is_superuser or 
                request.user.groups.filter(name='HR Manager').exists()):
            raise PermissionDenied("صلاحيات HR Manager مطلوبة للوصول لهذه الصفحة")
        
        return view_func(request, *args, **kwargs)
    return wrapper


def can_view_salaries(view_func):
    """
    يتطلب صلاحية رؤية الرواتب
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        
        if not (request.user.is_superuser or 
                request.user.groups.filter(name__in=['HR Manager', 'Finance']).exists()):
            raise PermissionDenied("ليس لديك صلاحية رؤية الرواتب")
        
        return view_func(request, *args, **kwargs)
    return wrapper


def can_approve_leaves(view_func):
    """
    يتطلب صلاحية اعتماد الإجازات
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        
        if not (request.user.is_superuser or 
                request.user.groups.filter(name__in=['HR Manager', 'Department Manager']).exists()):
            raise PermissionDenied("ليس لديك صلاحية اعتماد الإجازات")
        
        return view_func(request, *args, **kwargs)
    return wrapper


def can_process_payroll(view_func):
    """
    يتطلب صلاحية معالجة الرواتب
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        
        if not (request.user.is_superuser or 
                request.user.groups.filter(name__in=['HR Manager', 'Finance']).exists()):
            raise PermissionDenied("ليس لديك صلاحية معالجة الرواتب")
        
        return view_func(request, *args, **kwargs)
    return wrapper


def can_manage_contracts(view_func):
    """
    يتطلب صلاحية إدارة العقود
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        
        if not (request.user.is_superuser or 
                request.user.groups.filter(name='HR Manager').exists()):
            raise PermissionDenied("ليس لديك صلاحية إدارة العقود")
        
        return view_func(request, *args, **kwargs)
    return wrapper


def can_pay_payroll(view_func):
    """
    يتطلب صلاحية دفع الرواتب (Finance فقط)
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        
        if not (request.user.is_superuser or 
                request.user.groups.filter(name='Finance').exists()):
            raise PermissionDenied("ليس لديك صلاحية دفع الرواتب - Finance فقط")
        
        return view_func(request, *args, **kwargs)
    return wrapper
