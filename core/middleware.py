from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.views import redirect_to_login
from django.utils.deprecation import MiddlewareMixin
import re
import time
import pytz
import logging

logger = logging.getLogger(__name__)


class LoginRequiredMiddleware(MiddlewareMixin):
    """
    وسيط للتحقق من تسجيل الدخول لجميع الصفحات ماعدا المستثناة
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        # قائمة URL المستثناة من التحقق
        self.exempt_urls = [
            r'^/login/$',
            r'^/logout/$',
            r'^/signup/$',
            r'^/password-reset/',
            r'^/static/',
            r'^/media/',
            r'^/api/',
        ]
        # إضافة URLs مخصصة من الإعدادات
        if hasattr(settings, 'LOGIN_EXEMPT_URLS'):
            self.exempt_urls.extend(settings.LOGIN_EXEMPT_URLS)
    
    def process_request(self, request):
        """
        معالجة الطلب والتحقق من تسجيل الدخول
        """
        # التحقق مما إذا كان المستخدم مسجل الدخول
        if not request.user.is_authenticated:
            path = request.path_info
            
            # التحقق مما إذا كان المسار معفى
            for exempt_url in self.exempt_urls:
                if re.match(exempt_url, path):
                    return None
            
            # إعادة توجيه المستخدم غير المسجل
            if request.is_ajax():
                return JsonResponse({'redirect': settings.LOGIN_URL}, status=401)
            else:
                return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
        
        return None


class MaintenanceModeMiddleware(MiddlewareMixin):
    """
    وسيط لوضع الصيانة
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        # قائمة URL المسموح بها في وضع الصيانة
        self.allowed_urls = [
            r'^/login/$',
            r'^/admin/',
            r'^/maintenance/',
            r'^/static/',
            r'^/media/',
        ]
        # إضافة URLs مخصصة من الإعدادات
        if hasattr(settings, 'MAINTENANCE_ALLOWED_URLS'):
            self.allowed_urls.extend(settings.MAINTENANCE_ALLOWED_URLS)
    
    def process_request(self, request):
        """
        معالجة الطلب والتحقق من وضع الصيانة
        """
        # التحقق مما إذا كان وضع الصيانة مفعل
        maintenance_mode = getattr(settings, 'MAINTENANCE_MODE', False)
        
        if maintenance_mode:
            # السماح للمشرفين بالوصول خلال وضع الصيانة
            if request.user.is_superuser or request.user.is_staff:
                return None
            
            path = request.path_info
            
            # التحقق مما إذا كان المسار مسموحًا به
            for allowed_url in self.allowed_urls:
                if re.match(allowed_url, path):
                    return None
            
            # عرض صفحة الصيانة
            return HttpResponse('النظام في وضع الصيانة. يرجى المحاولة لاحقًا.', status=503)
        
        return None


class ActivityTrackingMiddleware(MiddlewareMixin):
    """
    وسيط لتتبع نشاط المستخدمين
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        # قائمة URL المستثناة من التتبع
        self.exempt_urls = [
            r'^/static/',
            r'^/media/',
            r'^/favicon.ico',
        ]
        # إضافة URLs مخصصة من الإعدادات
        if hasattr(settings, 'ACTIVITY_EXEMPT_URLS'):
            self.exempt_urls.extend(settings.ACTIVITY_EXEMPT_URLS)
    
    def process_request(self, request):
        """
        معالجة الطلب وتتبع النشاط
        """
        if request.user.is_authenticated:
            path = request.path_info
            
            # التحقق مما إذا كان المسار معفى
            for exempt_url in self.exempt_urls:
                if re.match(exempt_url, path):
                    return None
            
            # تحديث آخر نشاط للمستخدم
            request.user.last_activity = timezone.now()
            request.user.save(update_fields=['last_activity'])
            
            # تسجيل النشاط في قاعدة البيانات
            from core.models import UserActivity
            UserActivity.objects.create(
                user=request.user,
                url=path,
                method=request.method,
                ip_address=self.get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
        
        return None
    
    def get_client_ip(self, request):
        """
        الحصول على عنوان IP للمستخدم
        """
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class TimezoneMiddleware(MiddlewareMixin):
    """
    وسيط لتعيين المنطقة الزمنية
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def process_request(self, request):
        """
        معالجة الطلب وتعيين المنطقة الزمنية
        """
        tzname = None
        
        # محاولة الحصول على المنطقة الزمنية من جلسة المستخدم
        if 'timezone' in request.session:
            tzname = request.session['timezone']
        
        # محاولة الحصول على المنطقة الزمنية من ملف تعريف المستخدم
        elif request.user.is_authenticated and hasattr(request.user, 'profile') and hasattr(request.user.profile, 'timezone'):
            tzname = request.user.profile.timezone
            request.session['timezone'] = tzname
        
        # استخدام المنطقة الزمنية الافتراضية
        else:
            tzname = settings.TIME_ZONE
        
        # تعيين المنطقة الزمنية
        if tzname:
            timezone.activate(pytz.timezone(tzname))
        else:
            timezone.deactivate()
        
        return None


class AuditLogMiddleware(MiddlewareMixin):
    """
    وسيط لتسجيل سجلات المراقبة
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        # قائمة URL المستثناة من التسجيل
        self.exempt_urls = [
            r'^/static/',
            r'^/media/',
            r'^/favicon.ico',
        ]
        # إضافة URLs مخصصة من الإعدادات
        if hasattr(settings, 'AUDIT_EXEMPT_URLS'):
            self.exempt_urls.extend(settings.AUDIT_EXEMPT_URLS)
    
    def process_request(self, request):
        """
        معالجة الطلب وتسجيل المراقبة
        """
        path = request.path_info
        
        # التحقق مما إذا كان المسار معفى
        for exempt_url in self.exempt_urls:
            if re.match(exempt_url, path):
                return None
        
        # تسجيل المراقبة في قاعدة البيانات
        from core.models import AuditLog
        AuditLog.objects.create(
            user=request.user if request.user.is_authenticated else None,
            url=path,
            method=request.method,
            ip_address=self.get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            data=dict(request.GET) if request.method == 'GET' else dict(request.POST)
        )
        
        return None
    
    def get_client_ip(self, request):
        """
        الحصول على عنوان IP للمستخدم
        """
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class SecurityHeadersMiddleware(MiddlewareMixin):
    """
    وسيط لإضافة رؤوس أمان HTTP
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def process_response(self, request, response):
        """
        معالجة الاستجابة وإضافة رؤوس الأمان
        """
        # منع تخمين نوع المحتوى
        response['X-Content-Type-Options'] = 'nosniff'
        
        # منع تضمين الصفحة في إطار
        response['X-Frame-Options'] = 'DENY'
        
        # تفعيل حماية XSS
        response['X-XSS-Protection'] = '1; mode=block'
        
        # سياسة أمان المحتوى
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self'"
        )
        response['Content-Security-Policy'] = csp
        
        # سياسة الإحالة
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        return response


class PerformanceMonitoringMiddleware(MiddlewareMixin):
    """
    وسيط لمراقبة أداء الطلبات
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        # قائمة URL المستثناة من المراقبة
        self.exempt_urls = [
            r'^/static/',
            r'^/media/',
            r'^/favicon.ico',
        ]
        # إضافة URLs مخصصة من الإعدادات
        if hasattr(settings, 'PERF_MONITORING_IGNORE_URLS'):
            self.exempt_urls.extend(settings.PERF_MONITORING_IGNORE_URLS)
        
        # عتبة الطلبات البطيئة (بالثانية)
        self.slow_threshold = getattr(settings, 'PERF_SLOW_THRESHOLD', 1.0)
    
    def process_request(self, request):
        """
        معالجة الطلب وبدء مراقبة الأداء
        """
        path = request.path_info
        
        # التحقق مما إذا كان المسار معفى
        for exempt_url in self.exempt_urls:
            if re.match(exempt_url, path):
                return None
        
        # تسجيل وقت بدء الطلب
        request.start_time = time.time()
        
        return None
    
    def process_response(self, request, response):
        """
        معالجة الاستجابة وتسجيل أداء الطلب
        """
        if hasattr(request, 'start_time'):
            # حساب وقت المعالجة
            total_time = time.time() - request.start_time
            
            # تسجيل بيانات الأداء في الاستجابة
            response.performance_data = {
                'total_time': total_time,
                'url': request.path_info,
                'method': request.method,
            }
            
            # تسجيل الطلبات البطيئة
            if total_time > self.slow_threshold:
                user_info = f"User: {request.user.username}" if request.user.is_authenticated else "Anonymous"
                logger.warning(
                    f"Slow request: {request.method} {request.path_info} took {total_time:.2f}s. {user_info}"
                )
        
        return response


class AjaxRedirectMiddleware(MiddlewareMixin):
    """
    وسيط للتعامل مع طلبات AJAX لإعادة التوجيه
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def process_response(self, request, response):
        """
        معالجة الاستجابة والتعامل مع طلبات AJAX
        """
        if request.is_ajax() and response.status_code in [302, 301]:
            # تحويل الاستجابة إلى JSON للتعامل مع إعادة التوجيه في الجانب الأمامي
            return JsonResponse({
                'redirect': response.url
            })
        
        return response 