from functools import wraps
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseForbidden
from governance.signals.security_signals import permission_violation, suspicious_activity_detected
import logging

logger = logging.getLogger(__name__)


def monitor_security(resource_name=None):
    """
    Decorator to monitor security events in views
    Logs permission violations and suspicious activities
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            resource = resource_name or f"{view_func.__module__}.{view_func.__name__}"
            
            try:
                return view_func(request, *args, **kwargs)
            except PermissionDenied as e:
                # Log permission violation
                permission_violation.send(
                    sender=view_func,
                    request=request,
                    user=request.user if hasattr(request, 'user') else None,
                    resource=resource
                )
                raise
            except Exception as e:
                # Log unexpected errors
                logger.error(f"Unexpected error in {resource}: {e}", exc_info=True)
                raise
        
        return wrapper
    return decorator


def require_security_clearance(min_clearance_level='standard'):
    """
    Decorator to require minimum security clearance level
    Levels: 'basic', 'standard', 'elevated', 'admin'
    """
    clearance_levels = {
        'basic': 1,
        'standard': 2,
        'elevated': 3,
        'admin': 4
    }
    
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            user = request.user
            
            if not user.is_authenticated:
                raise PermissionDenied("Authentication required")
            
            # Check user clearance level
            user_level = 'basic'
            if user.is_superuser:
                user_level = 'admin'
            elif user.is_staff:
                user_level = 'elevated'
            elif user.groups.filter(name__in=['Managers', 'Supervisors']).exists():
                user_level = 'standard'
            
            required_level = clearance_levels.get(min_clearance_level, 2)
            actual_level = clearance_levels.get(user_level, 1)
            
            if actual_level < required_level:
                # Log security violation
                permission_violation.send(
                    sender=view_func,
                    request=request,
                    user=user,
                    resource=f"{view_func.__module__}.{view_func.__name__}",
                    required_clearance=min_clearance_level,
                    actual_clearance=user_level
                )
                raise PermissionDenied(f"Insufficient security clearance. Required: {min_clearance_level}")
            
            return view_func(request, *args, **kwargs)
        
        return wrapper
    return decorator


def log_sensitive_access(resource_type='sensitive_data'):
    """
    Decorator to log access to sensitive resources
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Log the access
            from governance.models import SecurityIncident
            from governance.middleware.security_middleware import BlockedIPMiddleware
            
            ip_address = BlockedIPMiddleware.get_client_ip(request)
            user = request.user if hasattr(request, 'user') and request.user.is_authenticated else None
            
            SecurityIncident.log_incident(
                incident_type='SUSPICIOUS_ACTIVITY',
                ip_address=ip_address,
                severity='LOW',
                user=user,
                username_attempted=user.username if user else 'anonymous',
                description=f'وصول إلى مورد حساس: {resource_type}',
                request=request,
                resource_type=resource_type,
                view_name=f"{view_func.__module__}.{view_func.__name__}"
            )
            
            return view_func(request, *args, **kwargs)
        
        return wrapper
    return decorator
