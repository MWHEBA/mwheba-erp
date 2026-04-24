"""
✅ PHASE 7: Simplified Monitoring Middleware
Basic request logging without complex monitoring features
"""

import logging
import time
from django.http import HttpRequest, HttpResponse
from django.contrib.auth.models import AnonymousUser
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)


class SimpleMonitoringMiddleware(MiddlewareMixin):
    """
    ✅ SIMPLIFIED: Basic monitoring middleware
    Logs only essential request information without complex performance monitoring
    """
    
    def process_request(self, request: HttpRequest) -> None:
        """Record request start time"""
        request._monitoring_start_time = time.time()
    
    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        """Log basic request information"""
        try:
            # Calculate response time
            start_time = getattr(request, '_monitoring_start_time', time.time())
            response_time = (time.time() - start_time) * 1000  # Convert to milliseconds
            
            # Log slow requests only (>2 seconds)
            if response_time > 2000:
                user_info = f"user:{request.user.username}" if hasattr(request, 'user') and not isinstance(request.user, AnonymousUser) else "anonymous"
                logger.warning(f"Slow request: {request.method} {request.path} took {response_time/1000:.2f}s ({user_info})")
            
            # Log errors
            if response.status_code >= 400:
                user_info = f"user:{request.user.username}" if hasattr(request, 'user') and not isinstance(request.user, AnonymousUser) else "anonymous"
                level = logging.ERROR if response.status_code >= 500 else logging.WARNING
                logger.log(level, f"HTTP {response.status_code}: {request.method} {request.path} ({user_info})")
                
        except Exception as e:
            logger.error(f"Error in monitoring middleware: {e}")
        
        return response
    
    def _get_client_ip(self, request: HttpRequest) -> str:
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', 'unknown')
    
    def _is_sensitive_endpoint(self, path: str) -> bool:
        """Check if endpoint is sensitive (simplified)"""
        sensitive_patterns = ['/admin/', '/api/', '/financial/', '/clients/']
        return any(pattern in path for pattern in sensitive_patterns)