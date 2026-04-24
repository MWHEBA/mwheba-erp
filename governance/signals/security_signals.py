from django.dispatch import Signal, receiver
from django.core.exceptions import PermissionDenied
from django.http import Http404
from governance.models import SecurityIncident
from governance.middleware.security_middleware import BlockedIPMiddleware
import logging

logger = logging.getLogger(__name__)

# Custom signals
permission_violation = Signal()
suspicious_activity_detected = Signal()


@receiver(permission_violation)
def handle_permission_violation(sender, request, user, resource, **kwargs):
    """Handle permission violations"""
    ip_address = BlockedIPMiddleware.get_client_ip(request)
    
    SecurityIncident.log_incident(
        incident_type='PERMISSION_VIOLATION',
        ip_address=ip_address,
        severity='HIGH',
        user=user if user.is_authenticated else None,
        username_attempted=user.username if user.is_authenticated else 'anonymous',
        description=f'محاولة وصول غير مصرح إلى: {resource}',
        request=request,
        resource=resource
    )
    
    logger.warning(f"Permission violation by {user} for {resource} from {ip_address}")


@receiver(suspicious_activity_detected)
def handle_suspicious_activity(sender, request, activity_type, description, **kwargs):
    """Handle suspicious activity detection"""
    ip_address = BlockedIPMiddleware.get_client_ip(request)
    user = request.user if hasattr(request, 'user') and request.user.is_authenticated else None
    
    SecurityIncident.log_incident(
        incident_type='SUSPICIOUS_ACTIVITY',
        ip_address=ip_address,
        severity=kwargs.get('severity', 'MEDIUM'),
        user=user,
        username_attempted=user.username if user else 'anonymous',
        description=description,
        request=request,
        activity_type=activity_type
    )
    
    logger.warning(f"Suspicious activity detected: {activity_type} from {ip_address}")


class SecurityMonitoringMixin:
    """Mixin to add security monitoring to views"""
    
    def dispatch(self, request, *args, **kwargs):
        try:
            return super().dispatch(request, *args, **kwargs)
        except PermissionDenied as e:
            # Log permission violation
            permission_violation.send(
                sender=self.__class__,
                request=request,
                user=request.user,
                resource=request.path
            )
            raise
        except Http404:
            # Don't log 404s as security incidents
            raise
        except Exception as e:
            # Log unexpected errors as potential security issues
            logger.error(f"Unexpected error in {self.__class__.__name__}: {e}")
            raise
