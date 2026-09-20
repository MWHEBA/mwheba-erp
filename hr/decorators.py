"""
Decorators للصلاحيات في نظام HR
متوافق بالكامل مع RolePermissionBackend والكاش السريع O(1)
ويدعم إرجاع JSON 403 لطلبات الـ AJAX بدلاً من رمي استثناء خام.
"""
from functools import wraps
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.utils.translation import gettext_lazy as _


def _is_ajax(request):
    """التحقق مما إذا كان الطلب عبر AJAX"""
    return (
        request.headers.get('x-requested-with') == 'XMLHttpRequest' or
        request.headers.get('accept', '').startswith('application/json')
    )


def _deny_access(request, message):
    """إرجاع استجابة رفض موحدة وآمنة للـ AJAX أو رفع PermissionDenied"""
    if _is_ajax(request):
        return JsonResponse({
            'success': False,
            'error': 'permission_denied',
            'message': str(message)
        }, status=403)
    raise PermissionDenied(str(message))


def _is_hr_manager(user):
    """Helper: التحقق من صلاحيات إدارة الموارد البشرية"""
    if not user.is_authenticated:
        return False
    if user.is_superuser or getattr(user, 'is_admin', False):
        return True
    return (
        user.has_perm('hr.can_manage_employees') or
        user.has_perm('hr.change_employee') or
        user.has_perm('hr.delete_employee')
    )


def hr_manager_required(view_func):
    """
    يتطلب صلاحيات إدارة الموارد البشرية
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())

        if not _is_hr_manager(request.user):
            return _deny_access(request, _("صلاحيات إدارة الموارد البشرية مطلوبة للوصول لهذه الصفحة"))

        return view_func(request, *args, **kwargs)
    return wrapper


def can_view_salaries(view_func):
    """يتطلب صلاحية رؤية الرواتب"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        user = request.user
        if not (user.is_superuser or getattr(user, 'is_admin', False) or
                user.has_perm('hr.view_payroll') or
                user.has_perm('hr.can_process_payroll')):
            return _deny_access(request, _("ليس لديك صلاحية رؤية الرواتب"))
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
                user.has_perm('hr.can_approve_leaves') or
                user.has_perm('hr.change_leave') or
                user.has_perm('hr.can_manage_employees')):
            return _deny_access(request, _("ليس لديك صلاحية اعتماد الإجازات"))
        return view_func(request, *args, **kwargs)
    return wrapper


def can_process_payroll(view_func):
    """يتطلب صلاحية معالجة مسيرات الرواتب"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        user = request.user
        if not (user.is_superuser or getattr(user, 'is_admin', False) or
                user.has_perm('hr.can_process_payroll')):
            return _deny_access(request, _("ليس لديك صلاحية معالجة الرواتب"))
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
                user.has_perm('hr.can_manage_contracts') or
                user.has_perm('hr.change_contract')):
            return _deny_access(request, _("ليس لديك صلاحية إدارة العقود"))
        return view_func(request, *args, **kwargs)
    return wrapper


def can_pay_payroll(view_func):
    """يتطلب صلاحية دفع وصرف الرواتب"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        user = request.user
        if not (user.is_superuser or getattr(user, 'is_admin', False) or
                user.has_perm('hr.can_pay_payroll') or
                user.has_perm('financial.add_paymentvoucher')):
            return _deny_access(request, _("ليس لديك صلاحية دفع الرواتب"))
        return view_func(request, *args, **kwargs)
    return wrapper


def require_hr(view_func):
    """يتطلب أن يكون المستخدم من الموارد البشرية"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        user = request.user
        if not (user.is_superuser or getattr(user, 'is_admin', False) or
                user.has_perm('hr.view_employee') or
                user.has_perm('hr.add_employee') or
                user.has_perm('hr.change_employee') or
                user.has_perm('hr.can_manage_employees')):
            return _deny_access(request, _("يجب أن تكون من الموارد البشرية للوصول لهذه الصفحة"))
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
                user.has_perm('hr.change_permission') or
                user.has_perm('hr.can_manage_employees')):
            return _deny_access(request, _("ليس لديك صلاحية اعتماد الأذونات"))
        return view_func(request, *args, **kwargs)
    return wrapper
