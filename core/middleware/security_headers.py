"""
🔒 Security Headers Middleware المتقدم
حماية شاملة من XSS, Clickjacking, وهجمات أخرى
"""

from django.utils.deprecation import MiddlewareMixin
from django.conf import settings
import hashlib
import secrets
from core.csp_config import build_csp_policy
from core.csp_config_advanced import build_csp_policy_advanced, should_use_nonce


class AdvancedSecurityHeadersMiddleware(MiddlewareMixin):
    """
    ✅ إضافة Security Headers متقدمة لجميع الاستجابات
    """
    
    def __init__(self, get_response):
        super().__init__(get_response)
        self.nonce_cache = {}
    
    def process_response(self, request, response):
        """إضافة Security Headers للاستجابة"""
        
        # 1. Content Security Policy متقدمة
        if should_use_nonce():
            nonce = self._generate_nonce()
            csp_policy = build_csp_policy_advanced(nonce)
            # إضافة nonce للاستخدام في templates
            if hasattr(request, 'META'):
                request.csp_nonce = nonce
        else:
            # في التطوير، استخدم CSP بسيطة بدون nonce
            csp_policy = build_csp_policy_advanced()
        
        response['Content-Security-Policy'] = csp_policy
        
        # 2. X-Frame-Options - منع Clickjacking
        response['X-Frame-Options'] = 'DENY'
        
        # 3. X-Content-Type-Options - منع MIME sniffing
        response['X-Content-Type-Options'] = 'nosniff'
        
        # 4. X-XSS-Protection - حماية من XSS (للمتصفحات القديمة)
        response['X-XSS-Protection'] = '1; mode=block'
        
        # 5. Referrer Policy - التحكم في معلومات Referrer
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        # 6. Permissions Policy - تقييد APIs الحساسة
        permissions_policy = [
            'geolocation=()',
            'microphone=()',
            'camera=()',
            'payment=()',
            'usb=()',
            'magnetometer=()',
            'gyroscope=()',
            'accelerometer=()'
        ]
        response['Permissions-Policy'] = ', '.join(permissions_policy)
        
        # 7. Strict-Transport-Security (HSTS) - فرض HTTPS
        if not settings.DEBUG:
            response['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
        
        # 8. Cross-Origin-Embedder-Policy - حماية من Spectre
        # تعطيل COEP في التطوير للسماح بتحميل CDN resources
        if not settings.DEBUG:
            response['Cross-Origin-Embedder-Policy'] = 'require-corp'
        
        # 9. Cross-Origin-Opener-Policy - عزل النوافذ
        # تعطيل COOP في التطوير للسماح بتحميل CDN resources
        if not settings.DEBUG:
            response['Cross-Origin-Opener-Policy'] = 'same-origin'
        
        # 10. Cross-Origin-Resource-Policy - حماية الموارد
        # تعطيل CORP في التطوير للسماح بتحميل CDN resources
        if not settings.DEBUG:
            response['Cross-Origin-Resource-Policy'] = 'same-origin'
        
        # 11. إضافة nonce للاستخدام في templates (فقط في الإنتاج)
        if should_use_nonce() and hasattr(request, 'META') and hasattr(request, 'csp_nonce'):
            pass  # تم إضافة nonce أعلاه
        
        return response
    
    def _generate_nonce(self):
        """إنشاء nonce عشوائي آمن"""
        return secrets.token_urlsafe(16)
    
    def _build_csp_policy(self, nonce):
        """بناء Content Security Policy متقدمة"""
        return build_csp_policy(nonce)


class SecurityEventLoggerMiddleware(MiddlewareMixin):
    """
    ✅ تسجيل الأحداث الأمنية المشبوهة
    """
    
    def process_request(self, request):
        """فحص الطلبات للبحث عن أنشطة مشبوهة"""
        
        # فحص User-Agent المشبوه
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        if self._is_suspicious_user_agent(user_agent):
            self._log_security_event(request, 'SUSPICIOUS_USER_AGENT', {
                'user_agent': user_agent,
                'ip': self._get_client_ip(request)
            })
        
        # فحص محاولات Path Traversal
        if self._detect_path_traversal(request.path):
            self._log_security_event(request, 'PATH_TRAVERSAL_ATTEMPT', {
                'path': request.path,
                'ip': self._get_client_ip(request)
            })
        
        # فحص محاولات SQL Injection في parameters
        if self._detect_sql_injection(request):
            self._log_security_event(request, 'SQL_INJECTION_ATTEMPT', {
                'method': request.method,
                'path': request.path,
                'ip': self._get_client_ip(request)
            })
        
        return None
    
    def _is_suspicious_user_agent(self, user_agent):
        """التحقق من User-Agent مشبوه"""
        suspicious_patterns = [
            'sqlmap',
            'nikto',
            'nmap',
            'masscan',
            'burp',
            'owasp',
            'dirbuster',
            'gobuster',
            'wfuzz',
            'hydra',
        ]
        
        user_agent_lower = user_agent.lower()
        return any(pattern in user_agent_lower for pattern in suspicious_patterns)
    
    def _detect_path_traversal(self, path):
        """اكتشاف محاولات Path Traversal"""
        traversal_patterns = [
            '../',
            '..\\',
            '%2e%2e%2f',
            '%2e%2e%5c',
            '..%2f',
            '..%5c',
        ]
        
        path_lower = path.lower()
        return any(pattern in path_lower for pattern in traversal_patterns)
    
    def _detect_sql_injection(self, request):
        """اكتشاف محاولات SQL Injection"""
        sql_patterns = [
            'union select',
            'drop table',
            'insert into',
            'delete from',
            'update set',
            'exec(',
            'execute(',
            'sp_',
            'xp_',
            '--',
            '/*',
            '*/',
            'char(',
            'ascii(',
            'substring(',
            'waitfor delay',
        ]
        
        # فحص GET parameters
        for key, value in request.GET.items():
            value_lower = str(value).lower()
            if any(pattern in value_lower for pattern in sql_patterns):
                return True
        
        # فحص POST data (إذا كان نص)
        if hasattr(request, 'body') and request.content_type == 'application/x-www-form-urlencoded':
            try:
                body_str = request.body.decode('utf-8').lower()
                if any(pattern in body_str for pattern in sql_patterns):
                    return True
            except:
                pass
        
        return False
    
    def _get_client_ip(self, request):
        """الحصول على IP الحقيقي للعميل"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def _log_security_event(self, request, event_type, details):
        """تسجيل حدث أمني"""
        import logging
        
        security_logger = logging.getLogger('security')
        security_logger.warning(
            f"🚨 Security Event: {event_type}",
            extra={
                'event_type': event_type,
                'details': details,
                'user': getattr(request, 'user', None),
                'session_key': getattr(request.session, 'session_key', None),
                'timestamp': __import__('datetime').datetime.now().isoformat(),
            }
        )