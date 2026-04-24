"""
Rate Limiting Middleware for Production Security
"""
import time
from django.core.cache import cache
from django.http import JsonResponse
from django.conf import settings
from django.utils.deprecation import MiddlewareMixin
import logging

logger = logging.getLogger(__name__)

class RateLimitingMiddleware(MiddlewareMixin):
    """
    ✅ SECURITY: Rate limiting middleware for API endpoints
    Prevents brute force attacks and DoS attempts
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.enabled = getattr(settings, 'RATE_LIMIT_ENABLED', True)
        super().__init__(get_response)
    
    def process_request(self, request):
        if not self.enabled:
            return None
            
        # Skip rate limiting for static files and admin
        if request.path.startswith('/static/') or request.path.startswith('/admin/'):
            return None
        
        # Get client IP
        client_ip = self.get_client_ip(request)
        
        # Different rate limits for different endpoints
        rate_limit = self.get_rate_limit(request.path, request.method)
        
        if rate_limit:
            if self.is_rate_limited(client_ip, request.path, rate_limit):
                logger.warning(f"Rate limit exceeded for IP {client_ip} on {request.path}")
                return JsonResponse({
                    'error': 'Rate limit exceeded',
                    'message': 'Too many requests. Please try again later.',
                    'retry_after': 60
                }, status=429)
        
        return None
    
    def get_client_ip(self, request):
        """Get the real client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def get_rate_limit(self, path, method):
        """Get rate limit configuration for specific path and method"""
        # API authentication endpoints - strict limits
        if '/api/auth/' in path or '/api/token/' in path:
            return {'requests': 5, 'window': 300}  # 5 requests per 5 minutes

        # Biometric API - moderate limits
        elif '/api/biometric/' in path or 'biometric_bridge_sync' in path:
            return {'requests': 10, 'window': 60}  # 10 requests per minute

        # Notifications endpoint - relaxed limits (polling every 2 minutes)
        elif '/api/notifications/count/' in path:
            return {'requests': 60, 'window': 60}  # 60 requests per minute (very relaxed)

        # General API endpoints
        elif path.startswith('/api/'):
            if method == 'POST':
                return {'requests': 30, 'window': 60}  # 30 POST requests per minute
            else:
                return {'requests': 100, 'window': 60}  # 100 GET requests per minute

        # Login attempts - only limit POST (actual login attempts, not page loads)
        elif '/login/' in path and method == 'POST':
            return {'requests': 10, 'window': 300}  # 10 login attempts per 5 minutes

        return None

    
    def is_rate_limited(self, client_ip, path, rate_limit):
        """Check if client has exceeded rate limit"""
        cache_key = f"rate_limit:{client_ip}:{path}"
        
        # Get current request count
        current_requests = cache.get(cache_key, 0)
        
        if current_requests >= rate_limit['requests']:
            return True
        
        # Increment counter only if not yet rate limited
        if current_requests == 0:
            cache.set(cache_key, 1, rate_limit['window'])
        else:
            cache.incr(cache_key)
        
        return False


class SecurityEventMiddleware(MiddlewareMixin):
    """
    ✅ SECURITY: Log security events for monitoring
    """
    
    def process_request(self, request):
        # Log suspicious patterns
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        # Check for common attack patterns
        suspicious_patterns = [
            'sqlmap', 'nikto', 'nmap', 'masscan', 'zap',
            'burp', 'w3af', 'acunetix', 'nessus'
        ]
        
        if any(pattern in user_agent.lower() for pattern in suspicious_patterns):
            logger.warning(f"Suspicious user agent detected: {user_agent} from IP {self.get_client_ip(request)}")
        
        # Log failed authentication attempts
        if request.path in ['/login/', '/api/auth/login/'] and request.method == 'POST':
            logger.info(f"Authentication attempt from IP {self.get_client_ip(request)}")
        
        return None
    
    def get_client_ip(self, request):
        """Get the real client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip