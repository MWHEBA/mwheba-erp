# -*- coding: utf-8 -*-
"""
Unified Permission Decorators

This module provides decorators for view-level permission checking
integrated with the governance system.
"""

from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.core.cache import cache
from django.utils import timezone
from typing import List, Union, Callable, Any
import logging

from .services.permission_service import PermissionService

logger = logging.getLogger('users.decorators')


def require_reception_or_admin(view_func: Callable) -> Callable:
    """
    Decorator للتحقق من صلاحيات الريسيبشن أو الإدارة
    يعتمد على الصلاحيات الفعلية مش hardcoded roles
    """
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        user = request.user
        
        # السماح للمدير العام والمدير
        if user.is_superuser or user.is_admin:
            return view_func(request, *args, **kwargs)
        
        # التحقق من صلاحيات التقديمات
        if user.can_view_applications():
            return view_func(request, *args, **kwargs)
        
        # رفض الوصول للآخرين
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'message': 'ليس لديك صلاحية للوصول - مطلوب صلاحيات التقديمات'
            }, status=403)
        
        raise PermissionDenied("ليس لديك صلاحية للوصول - مطلوب صلاحيات التقديمات")
    
    return wrapper


def require_applications_permission(permission_type: str = 'view'):
    """
    Decorator للتحقق من صلاحيات التقديمات
    
    Args:
        permission_type: نوع الصلاحية ('view', 'add', 'change')
    """
    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            user = request.user
            
            # السماح للمدير العام
            if user.is_superuser:
                return view_func(request, *args, **kwargs)
            
            # التحقق من الصلاحية المطلوبة
            permission_map = {
                'view': user.can_view_applications,
                'add': user.can_add_applications,
                'change': user.can_change_applications
            }
            
            if permission_type in permission_map and permission_map[permission_type]():
                return view_func(request, *args, **kwargs)
            
            # رفض الوصول
            error_message = f"ليس لديك صلاحية {permission_type} للتقديمات"
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': error_message
                }, status=403)
            
            raise PermissionDenied(error_message)
        
        return wrapper
    return decorator


def require_permission(permission_name: str, return_json: bool = False):
    """
    Decorator to require specific permission for view access.
    
    Args:
        permission_name: Permission codename required
        return_json: Whether to return JSON response for AJAX requests
        
    Usage:
        @require_permission('can_manage_users')
    """
    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            user = request.user
            
            # Check permission using PermissionService
            if not PermissionService.check_user_permission(user, permission_name):
                error_message = f"ليس لديك صلاحية: {permission_name}"
                
                if return_json or request.headers.get('Content-Type') == 'application/json':
                    return JsonResponse({
                        'success': False,
                        'error': 'permission_denied',
                        'message': error_message
                    }, status=403)
                
                return render(request, 'core/permission_denied.html', {
                    'title': 'غير مصرح',
                    'message': error_message
                })
            
            return view_func(request, *args, **kwargs)
        
        return wrapper
    return decorator


def require_admin(return_json: bool = False):
    """
    Decorator to require admin role for view access.
    
    Args:
        return_json: Whether to return JSON response for AJAX requests
        
    Usage:
        @require_admin()
    """
    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            user = request.user
            
            if not (user.is_superuser or user.is_admin):
                error_message = f"يتطلب الوصول صلاحيات المدير. نوع المستخدم الحالي: {user.user_type}"
                
                if return_json or request.headers.get('Content-Type') == 'application/json' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'error': 'admin_required',
                        'message': error_message
                    }, status=403)
                
                return render(request, 'core/permission_denied.html', {
                    'title': 'غير مصرح',
                    'message': error_message
                })
            
            return view_func(request, *args, **kwargs)
        
        return wrapper
    return decorator


def require_superuser(return_json: bool = False):
    """
    Decorator to require superuser for view access.
    
    Args:
        return_json: Whether to return JSON response for AJAX requests
        
    Usage:
        @require_superuser()
    """
    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            user = request.user
            
            if not user.is_superuser:
                error_message = "يتطلب الوصول صلاحيات المدير العام"
                
                if return_json or request.headers.get('Content-Type') == 'application/json':
                    return JsonResponse({
                        'success': False,
                        'error': 'superuser_required',
                        'message': error_message
                    }, status=403)
                
                return render(request, 'core/permission_denied.html', {
                    'title': 'غير مصرح',
                    'message': error_message
                })
            
            return view_func(request, *args, **kwargs)
        
        return wrapper
    return decorator


def check_object_permission(permission_name: str, obj_param: str = 'pk', return_json: bool = False):
    """
    Decorator to check object-level permissions.
    
    Args:
        permission_name: Permission codename required
        obj_param: Parameter name containing object ID
        return_json: Whether to return JSON response for AJAX requests
        
    Usage:
        @check_object_permission('can_edit_user', 'user_id')
    """
    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            user = request.user
            
            # Get object ID from kwargs
            obj_id = kwargs.get(obj_param)
            if not obj_id:
                error_message = f"معرف الكائن مطلوب: {obj_param}"
                
                if return_json or request.headers.get('Content-Type') == 'application/json':
                    return JsonResponse({
                        'success': False,
                        'error': 'invalid_request',
                        'message': error_message
                    }, status=400)
                
                return render(request, 'core/permission_denied.html', {
                    'title': 'طلب غير صحيح',
                    'message': error_message
                })
            
            # Check permission (object-level checking can be implemented here)
            if not PermissionService.check_user_permission(user, permission_name, obj_id):
                error_message = f"ليس لديك صلاحية: {permission_name}"
                
                if return_json or request.headers.get('Content-Type') == 'application/json':
                    return JsonResponse({
                        'success': False,
                        'error': 'permission_denied',
                        'message': error_message
                    }, status=403)
                
                return render(request, 'core/permission_denied.html', {
                    'title': 'غير مصرح',
                    'message': error_message
                })
            
            return view_func(request, *args, **kwargs)
        
        return wrapper
    return decorator


# Convenience decorators for common use cases
def admin_required(view_func: Callable = None, *, return_json: bool = False):
    """
    Convenience decorator for admin requirement.
    Can be used with or without parentheses.
    
    Usage:
        @admin_required
        @admin_required(return_json=True)
    """
    def decorator(func):
        return require_admin(return_json)(func)
    
    if view_func is None:
        return decorator
    else:
        return decorator(view_func)


def rate_limit_permission_check(max_attempts: int = 100, window: int = 3600):
    """
    Rate limiting decorator for permission-sensitive operations.
    
    Args:
        max_attempts: Maximum attempts per window
        window: Time window in seconds
        
    Usage:
        @rate_limit_permission_check(max_attempts=50, window=1800)
        @require_admin()
        def sensitive_view(request):
            pass
    """
    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return view_func(request, *args, **kwargs)
            
            # Create rate limit key
            cache_key = f'perm_rate_limit_{request.user.id}'
            current_attempts = cache.get(cache_key, 0)
            
            if current_attempts >= max_attempts:
                logger.warning(
                    f"Rate limit exceeded for user {request.user.username} "
                    f"({current_attempts} attempts in {window}s window)"
                )
                
                if request.headers.get('Content-Type') == 'application/json':
                    return JsonResponse({
                        'success': False,
                        'error': 'rate_limit_exceeded',
                        'message': 'تم تجاوز الحد المسموح من المحاولات'
                    }, status=429)
                
                return HttpResponse(
                    "تم تجاوز الحد المسموح من المحاولات. يرجى المحاولة لاحقاً.",
                    status=429
                )
            
            # Increment counter
            cache.set(cache_key, current_attempts + 1, window)
            
            return view_func(request, *args, **kwargs)
        
        return wrapper
    return decorator


def audit_sensitive_operation(operation_name: str):
    """
    Decorator to audit sensitive operations.
    
    Args:
        operation_name: Name of the operation for audit trail
        
    Usage:
        @audit_sensitive_operation('user_role_assignment')
        @require_admin()
        def assign_role_view(request):
            pass
    """
    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            from governance.services.audit_service import AuditService
            
            # Log operation start
            start_time = timezone.now()
            
            try:
                result = view_func(request, *args, **kwargs)
                
                # Log successful operation
                AuditService.log_operation(
                    model_name='sensitive_operation',
                    object_id=0,
                    operation=f'{operation_name}_success',
                    source_service='WebInterface',
                    user=request.user,
                    execution_time=(timezone.now() - start_time).total_seconds(),
                    request_path=request.path,
                    request_method=request.method
                )
                
                return result
                
            except Exception as e:
                # Log failed operation
                AuditService.log_operation(
                    model_name='sensitive_operation',
                    object_id=0,
                    operation=f'{operation_name}_failed',
                    source_service='WebInterface',
                    user=request.user,
                    execution_time=(timezone.now() - start_time).total_seconds(),
                    error=str(e),
                    request_path=request.path,
                    request_method=request.method
                )
                raise
        
        return wrapper
    return decorator


def superuser_required(view_func: Callable = None, *, return_json: bool = False):
    """
    Convenience decorator for superuser requirement.
    Can be used with or without parentheses.
    
    Usage:
        @superuser_required
        @superuser_required(return_json=True)
    """
    def decorator(func):
        return require_superuser(return_json)(func)
    
    if view_func is None:
        return decorator
    else:
        return decorator(view_func)


def secure_admin_operation(operation_name: str = None):
    """
    Combined decorator for secure admin operations with rate limiting and audit.
    
    Args:
        operation_name: Name for audit trail
        
    Usage:
        @secure_admin_operation('role_management')
        def admin_view(request):
            pass
    """
    def decorator(view_func: Callable) -> Callable:
        op_name = operation_name or view_func.__name__
        
        # Apply multiple decorators in order
        decorated = view_func
        decorated = audit_sensitive_operation(op_name)(decorated)
        decorated = rate_limit_permission_check(max_attempts=50, window=1800)(decorated)
        decorated = require_admin(return_json=True)(decorated)
        
        return decorated
    
    return decorator


# Export all decorators
__all__ = [
    'require_reception_or_admin',
    'require_applications_permission',
    'require_permission', 
    'require_admin',
    'require_superuser',
    'check_object_permission',
    'admin_required',
    'superuser_required',
    'rate_limit_permission_check',
    'audit_sensitive_operation',
    'secure_admin_operation'
]