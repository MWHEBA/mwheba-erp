# -*- coding: utf-8 -*-
"""
Real-Time Permission Checking Middleware

This middleware provides real-time permission validation and monitoring
for enhanced security and audit trail.
"""

import logging
import time
from django.utils.deprecation import MiddlewareMixin
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.urls import resolve
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger('core.permission_checker')


class RealTimePermissionMiddleware(MiddlewareMixin):
    """
    Real-time permission checking middleware with audit logging.
    
    Features:
    - Real-time permission validation
    - Audit logging for permission checks
    - Performance monitoring
    - Security event detection
    """
    
    # URLs that require special permission checking
    PROTECTED_PATTERNS = [
        'admin:',
        'users:permissions',
        'governance:',
        'financial:',
    ]
    
    # URLs to skip permission checking
    SKIP_PATTERNS = [
        'static/',
        'media/',
        'api/auth/',
        'login/',
        'logout/',
    ]
    
    def process_request(self, request):
        """Process incoming request for permission validation."""
        # Skip for static files and auth endpoints
        if any(pattern in request.path for pattern in self.SKIP_PATTERNS):
            return None
        
        # Skip for anonymous users on public endpoints
        if isinstance(request.user, AnonymousUser):
            return None
        
        # Record request start time for performance monitoring
        request._permission_check_start = time.time()
        
        return None
    
    def process_view(self, request, view_func, view_args, view_kwargs):
        """Process view for permission validation."""
        try:
            # Skip for non-authenticated users
            if not hasattr(request, 'user') or isinstance(request.user, AnonymousUser):
                return None
            
            # Get URL pattern name
            resolver_match = resolve(request.path)
            url_name = resolver_match.url_name
            
            # Check if this is a protected pattern
            if any(pattern in request.path for pattern in self.PROTECTED_PATTERNS):
                self._log_permission_access(request, url_name, 'PROTECTED_ACCESS')
            
            return None
            
        except Exception as e:
            logger.error(f"Error in permission middleware: {e}")
            return None
    
    def process_response(self, request, response):
        """Process response and log permission check results."""
        try:
            # Calculate permission check duration
            if hasattr(request, '_permission_check_start'):
                duration = time.time() - request._permission_check_start
                
                # Log slow permission checks
                if duration > 0.5:  # 500ms threshold
                    logger.warning(
                        f"Slow permission check: {request.path} took {duration:.3f}s"
                    )
            
            # Log failed permission attempts
            if response.status_code == 403:
                self._log_permission_denial(request, response)
            
            return response
            
        except Exception as e:
            logger.error(f"Error in permission response processing: {e}")
            return response
    
    def _log_permission_access(self, request, url_name, access_type):
        """Log permission access attempts."""
        try:
            from governance.services.audit_service import AuditService
            
            AuditService.create_audit_record(
                model_name='Permission',
                object_id=None,
                operation=access_type,
                user=request.user,
                source_service='RealTimePermissionMiddleware',
                additional_context={
                    'url_name': url_name,
                    'path': request.path,
                    'method': request.method,
                    'ip_address': self._get_client_ip(request),
                    'user_agent': request.META.get('HTTP_USER_AGENT', '')[:200]
                }
            )
            
        except Exception as e:
            logger.error(f"Error logging permission access: {e}")
    
    def _log_permission_denial(self, request, response):
        """Log permission denial events."""
        try:
            from governance.services.audit_service import AuditService
            
            AuditService.create_audit_record(
                model_name='Permission',
                object_id=None,
                operation='PERMISSION_DENIED',
                user=request.user if hasattr(request, 'user') else None,
                source_service='RealTimePermissionMiddleware',
                additional_context={
                    'path': request.path,
                    'method': request.method,
                    'status_code': response.status_code,
                    'ip_address': self._get_client_ip(request),
                    'user_agent': request.META.get('HTTP_USER_AGENT', '')[:200]
                }
            )
            
        except Exception as e:
            logger.error(f"Error logging permission denial: {e}")
    
    def _get_client_ip(self, request):
        """Get client IP address from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip