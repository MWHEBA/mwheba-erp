from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.utils.deprecation import MiddlewareMixin
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver
from django.utils import timezone
from governance.models import BlockedIP, ActiveSession, SecurityIncident
import logging

logger = logging.getLogger(__name__)


class BlockedIPMiddleware(MiddlewareMixin):
    """Middleware to block requests from blocked IP addresses"""
    
    def process_request(self, request):
        # Get client IP
        ip_address = self.get_client_ip(request)
        
        # Check if IP is blocked
        if BlockedIP.is_blocked(ip_address):
            # Increment attempts counter
            try:
                blocked_ip = BlockedIP.objects.get(ip_address=ip_address, is_active=True)
                blocked_ip.increment_attempts()
                
                # Log incident (without user since auth middleware hasn't run yet)
                SecurityIncident.log_incident(
                    incident_type='SUSPICIOUS_ACTIVITY',
                    ip_address=ip_address,
                    severity='HIGH',
                    description=f'محاولة وصول من IP محجوب: {blocked_ip.get_reason_display()}',
                    request=request
                )
            except BlockedIP.DoesNotExist:
                pass
            
            # Return forbidden response
            return HttpResponseForbidden(
                render(request, 'errors/blocked_ip.html', {
                    'ip_address': ip_address,
                    'message': 'عنوان IP الخاص بك محجوب بسبب نشاط مشبوه. يرجى الاتصال بالدعم الفني.'
                }).content
            )
        
        return None
    
    @staticmethod
    def get_client_ip(request):
        """Extract client IP from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class SessionTrackingMiddleware(MiddlewareMixin):
    """Middleware to track active user sessions"""
    
    def process_request(self, request):
        # Only track authenticated users (check if user attribute exists and is authenticated)
        if hasattr(request, 'user') and request.user.is_authenticated and hasattr(request, 'session'):
            session_key = request.session.session_key
            
            if session_key:
                # Update or create active session
                ip_address = BlockedIPMiddleware.get_client_ip(request)
                user_agent = request.META.get('HTTP_USER_AGENT', '')
                
                try:
                    session = ActiveSession.objects.get(session_key=session_key)
                    # Update last activity
                    session.last_activity = timezone.now()
                    session.save(update_fields=['last_activity'])
                except ActiveSession.DoesNotExist:
                    # Create new session record
                    ActiveSession.objects.create(
                        user=request.user,
                        session_key=session_key,
                        ip_address=ip_address,
                        user_agent=user_agent,
                        is_active=True
                    )
        
        return None


# Signal handlers for authentication events
@receiver(user_logged_in)
def handle_user_login(sender, request, user, **kwargs):
    """Handle successful user login"""
    ip_address = BlockedIPMiddleware.get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    
    # Create active session
    if hasattr(request, 'session') and request.session.session_key:
        ActiveSession.create_session(
            user=user,
            session_key=request.session.session_key,
            ip_address=ip_address,
            user_agent=user_agent
        )
    
    logger.info(f"User {user.username} logged in from {ip_address}")


@receiver(user_logged_out)
def handle_user_logout(sender, request, user, **kwargs):
    """Handle user logout"""
    if user and hasattr(request, 'session') and request.session.session_key:
        try:
            session = ActiveSession.objects.get(
                session_key=request.session.session_key,
                is_active=True
            )
            session.terminate()
        except ActiveSession.DoesNotExist:
            pass
    
    if user:
        logger.info(f"User {user.username} logged out")


@receiver(user_login_failed)
def handle_login_failed(sender, credentials, request, **kwargs):
    """Handle failed login attempts"""
    ip_address = BlockedIPMiddleware.get_client_ip(request)
    username = credentials.get('username', 'unknown')
    
    # Log security incident
    incident = SecurityIncident.log_incident(
        incident_type='FAILED_LOGIN',
        ip_address=ip_address,
        severity='MEDIUM',
        username_attempted=username,
        description=f'محاولة دخول فاشلة للمستخدم: {username}',
        request=request
    )
    
    # Check for brute force attack
    recent_failures = SecurityIncident.objects.filter(
        incident_type='FAILED_LOGIN',
        ip_address=ip_address,
        detected_at__gte=timezone.now() - timezone.timedelta(minutes=15)
    ).count()
    
    # Auto-block after 5 failed attempts in 15 minutes
    if recent_failures >= 5:
        BlockedIP.block_ip(
            ip_address=ip_address,
            description=f'حجب تلقائي بعد {recent_failures} محاولة دخول فاشلة',
            reason='BRUTE_FORCE'
        )
        
        # Update incident severity
        if incident:
            incident.severity = 'CRITICAL'
            incident.incident_type = 'BRUTE_FORCE'
            incident.description = f'هجوم بروت فورس - {recent_failures} محاولة فاشلة'
            incident.save(update_fields=['severity', 'incident_type', 'description'])
        
        logger.warning(f"IP {ip_address} blocked due to brute force attack")
    
    logger.warning(f"Failed login attempt for {username} from {ip_address}")
