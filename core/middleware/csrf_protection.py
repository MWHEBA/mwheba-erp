"""
CSRF Protection Middleware - حماية شاملة ومحسنة من هجمات CSRF
"""
import logging
import hashlib
import time
from django.middleware.csrf import CsrfViewMiddleware
from django.conf import settings
from django.http import HttpResponseForbidden, JsonResponse
from django.utils.deprecation import MiddlewareMixin
from django.core.cache import cache
from django.utils.html import escape
from django.urls import reverse
from django.shortcuts import render

logger = logging.getLogger(__name__)


class EnhancedCSRFMiddleware(CsrfViewMiddleware):
    """
    ✅ CSRF Middleware محسن مع logging، rate limiting، وحماية متقدمة
    """
    
    def __init__(self, get_response):
        super().__init__(get_response)
        self.attack_cache_timeout = 300  # 5 دقائق
        self.max_attacks_per_ip = 10  # حد أقصى 10 محاولات لكل IP
    
    def process_view(self, request, callback, callback_args, callback_kwargs):
        """
        معالجة الطلبات مع تسجيل وحماية متقدمة من محاولات CSRF
        """
        response = super().process_view(request, callback, callback_args, callback_kwargs)
        
        # إذا كان هناك خطأ CSRF، سجل المحاولة وطبق rate limiting
        if isinstance(response, HttpResponseForbidden):
            client_ip = self.get_client_ip(request)
            self._log_csrf_attack(request, client_ip)
            
            # تطبيق rate limiting على IP المهاجم
            if self._is_ip_blocked(client_ip):
                return self._create_blocked_response(request)
            
            self._increment_attack_counter(client_ip)
            
            # إرجاع response مخصص للـ CSRF error
            return self._create_csrf_error_response(request)
        
        return response
    
    def _log_csrf_attack(self, request, client_ip):
        """
        تسجيل مفصل لمحاولة هجوم CSRF
        """
        user_info = "Anonymous"
        if hasattr(request, 'user') and request.user.is_authenticated:
            user_info = f"{request.user.username} (ID: {request.user.id})"
        
        attack_info = {
            'ip': client_ip,
            'user': user_info,
            'path': request.path,
            'method': request.method,
            'referer': request.META.get('HTTP_REFERER', 'None'),
            'user_agent': request.META.get('HTTP_USER_AGENT', 'None'),
            'timestamp': time.time(),
            'session_key': request.session.session_key if hasattr(request, 'session') else 'None'
        }
        
        logger.warning(
            f"🚨 CSRF Attack Attempt - "
            f"IP: {client_ip}, "
            f"User: {user_info}, "
            f"Path: {request.path}, "
            f"Method: {request.method}, "
            f"Referer: {attack_info['referer']}, "
            f"User-Agent: {attack_info['user_agent'][:100]}..."
        )
        
        # حفظ تفاصيل الهجوم في cache للتحليل
        cache_key = f"csrf_attack_{hashlib.md5(client_ip.encode()).hexdigest()}_{int(time.time())}"
        cache.set(cache_key, attack_info, self.attack_cache_timeout)
    
    def _is_ip_blocked(self, client_ip):
        """
        التحقق من حظر IP بسبب محاولات CSRF متكررة
        """
        cache_key = f"csrf_attacks_{hashlib.md5(client_ip.encode()).hexdigest()}"
        attack_count = cache.get(cache_key, 0)
        return attack_count >= self.max_attacks_per_ip
    
    def _increment_attack_counter(self, client_ip):
        """
        زيادة عداد محاولات الهجوم لـ IP معين
        """
        cache_key = f"csrf_attacks_{hashlib.md5(client_ip.encode()).hexdigest()}"
        current_count = cache.get(cache_key, 0)
        cache.set(cache_key, current_count + 1, self.attack_cache_timeout)
        
        if current_count + 1 >= self.max_attacks_per_ip:
            logger.critical(
                f"🔒 IP BLOCKED due to repeated CSRF attacks: {client_ip} "
                f"({current_count + 1} attempts)"
            )
    
    def _create_blocked_response(self, request):
        """
        إنشاء response للـ IP المحظور
        """
        if request.headers.get('Accept', '').startswith('application/json'):
            return JsonResponse({
                'error': 'IP blocked due to security violations',
                'code': 'IP_BLOCKED',
                'retry_after': self.attack_cache_timeout
            }, status=429)
        
        context = {
            'title': 'IP محظور',
            'message': 'تم حظر عنوان IP الخاص بك مؤقتاً بسبب محاولات أمنية مشبوهة',
            'retry_after': self.attack_cache_timeout // 60,  # بالدقائق
        }
        
        return render(request, 'errors/ip_blocked.html', context, status=429)
    
    def _create_csrf_error_response(self, request):
        """
        إنشاء response مخصص لخطأ CSRF
        """
        if request.headers.get('Accept', '').startswith('application/json'):
            return JsonResponse({
                'error': 'CSRF token missing or invalid',
                'code': 'CSRF_ERROR',
                'message': 'Please refresh the page and try again'
            }, status=403)
        
        context = {
            'title': 'خطأ في الأمان',
            'message': 'انتهت صلاحية الجلسة أو هناك مشكلة في الأمان. يرجى تحديث الصفحة والمحاولة مرة أخرى.',
            'refresh_url': request.path,
        }
        
        return render(request, 'errors/csrf_error.html', context, status=403)
    
    def get_client_ip(self, request):
        """
        الحصول على IP الحقيقي للعميل مع دعم proxy headers
        """
        # ترتيب الأولوية للـ headers
        ip_headers = [
            'HTTP_CF_CONNECTING_IP',  # Cloudflare
            'HTTP_X_FORWARDED_FOR',   # Standard proxy
            'HTTP_X_REAL_IP',         # Nginx
            'HTTP_X_FORWARDED',       # Alternative
            'HTTP_FORWARDED_FOR',     # Alternative
            'HTTP_FORWARDED',         # RFC 7239
            'REMOTE_ADDR'             # Direct connection
        ]
        
        for header in ip_headers:
            ip = request.META.get(header)
            if ip:
                # أخذ أول IP في حالة وجود قائمة
                ip = ip.split(',')[0].strip()
                if self._is_valid_ip(ip):
                    return ip
        
        return '0.0.0.0'  # fallback
    
    def _is_valid_ip(self, ip):
        """
        التحقق من صحة عنوان IP
        """
        import ipaddress
        try:
            ipaddress.ip_address(ip)
            return True
        except ValueError:
            return False


class CSRFTokenValidationMiddleware(MiddlewareMixin):
    """
    ✅ التحقق الشامل من وجود وصحة CSRF tokens
    """
    
    def __init__(self, get_response):
        super().__init__(get_response)
        self.exempt_paths = [
            '/api/',           # API endpoints تستخدم JWT
            '/admin/jsi18n/',  # Django admin i18n
            '/health/',        # Health check endpoints
            '/metrics/',       # Monitoring endpoints
        ]
        self.warning_cache_timeout = 60  # دقيقة واحدة
    
    def process_request(self, request):
        """
        التحقق الشامل من CSRF tokens في POST requests
        """
        # تخطي الفحص في DEBUG mode أو للمسارات المستثناة
        if settings.DEBUG or request.method != 'POST':
            return None
        
        # تخطي المسارات المستثناة
        if any(request.path.startswith(path) for path in self.exempt_paths):
            return None
        
        # البحث عن CSRF token في أماكن مختلفة
        csrf_token = self._extract_csrf_token(request)
        
        if not csrf_token:
            self._log_missing_csrf_token(request)
            return None  # السماح للـ Django CSRF middleware بالتعامل مع الخطأ
        
        # التحقق من صحة format الـ token
        if not self._is_valid_csrf_format(csrf_token):
            self._log_invalid_csrf_format(request, csrf_token)
        
        return None
    
    def _extract_csrf_token(self, request):
        """
        استخراج CSRF token من مصادر متعددة
        """
        # البحث في POST data
        csrf_token = request.POST.get('csrfmiddlewaretoken')
        if csrf_token:
            return csrf_token
        
        # البحث في headers
        csrf_headers = [
            'HTTP_X_CSRFTOKEN',
            'HTTP_X_CSRF_TOKEN',
            'HTTP_CSRF_TOKEN',
        ]
        
        for header in csrf_headers:
            csrf_token = request.META.get(header)
            if csrf_token:
                return csrf_token
        
        return None
    
    def _is_valid_csrf_format(self, token):
        """
        التحقق من صحة format الـ CSRF token
        """
        if not token or not isinstance(token, str):
            return False
        
        # Django CSRF tokens عادة 64 حرف hex أو 32 حرف base64
        if len(token) in [32, 64] and all(c in '0123456789abcdefABCDEF-_' for c in token):
            return True
        
        return False
    
    def _log_missing_csrf_token(self, request):
        """
        تسجيل POST requests بدون CSRF token
        """
        client_ip = self._get_client_ip(request)
        
        # تجنب spam الـ logs بنفس الـ IP
        cache_key = f"csrf_warning_{hashlib.md5(client_ip.encode()).hexdigest()}"
        if cache.get(cache_key):
            return
        
        cache.set(cache_key, True, self.warning_cache_timeout)
        
        user_info = "Anonymous"
        if hasattr(request, 'user') and request.user.is_authenticated:
            user_info = f"{request.user.username} (ID: {request.user.id})"
        
        logger.warning(
            f"⚠️ Missing CSRF Token - "
            f"IP: {client_ip}, "
            f"User: {user_info}, "
            f"Path: {request.path}, "
            f"Content-Type: {request.content_type}, "
            f"User-Agent: {request.META.get('HTTP_USER_AGENT', 'None')[:100]}..."
        )
    
    def _log_invalid_csrf_format(self, request, token):
        """
        تسجيل CSRF tokens بـ format غير صحيح
        """
        client_ip = self._get_client_ip(request)
        
        logger.warning(
            f"🔍 Invalid CSRF Token Format - "
            f"IP: {client_ip}, "
            f"Path: {request.path}, "
            f"Token: {token[:10]}... (length: {len(token)})"
        )
    
    def _get_client_ip(self, request):
        """
        الحصول على IP الحقيقي للعميل
        """
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', '0.0.0.0')
        return ip


class CSRFSecurityHeadersMiddleware(MiddlewareMixin):
    """
    ✅ إضافة security headers متعلقة بـ CSRF
    """
    
    def process_response(self, request, response):
        """
        إضافة security headers للحماية من CSRF وهجمات أخرى
        """
        # منع embedding في iframes من domains أخرى
        if not response.get('X-Frame-Options'):
            response['X-Frame-Options'] = 'SAMEORIGIN'
        
        # منع MIME type sniffing
        if not response.get('X-Content-Type-Options'):
            response['X-Content-Type-Options'] = 'nosniff'
        
        # تفعيل XSS protection في المتصفح
        if not response.get('X-XSS-Protection'):
            response['X-XSS-Protection'] = '1; mode=block'
        
        # Referrer Policy للحماية من تسريب معلومات
        if not response.get('Referrer-Policy'):
            response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        # Content Security Policy أساسي
        if not response.get('Content-Security-Policy') and not settings.DEBUG:
            csp_directives = [
                "default-src 'self'",
                "script-src 'self' 'unsafe-inline' 'unsafe-eval'",  # مؤقت للتوافق
                "style-src 'self' 'unsafe-inline'",
                "img-src 'self' data: https:",
                "font-src 'self' https:",
                "connect-src 'self'",
                "frame-ancestors 'self'",
                "base-uri 'self'",
                "form-action 'self'"
            ]
            response['Content-Security-Policy'] = '; '.join(csp_directives)
        
        return response