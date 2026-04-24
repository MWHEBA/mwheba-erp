"""
Middleware لتأمين webhooks والتحقق من التوقيعات
Webhook Security Middleware for signature validation and protection
"""

import logging
from django.http import JsonResponse, HttpResponseForbidden
from django.utils.deprecation import MiddlewareMixin
from django.utils import timezone
from django.conf import settings
from core.services.api_integration_security import APIIntegrationSecurityService
import json

logger = logging.getLogger(__name__)


class WebhookSecurityMiddleware(MiddlewareMixin):
    """
    Middleware لتأمين نقاط webhook
    """
    
    # نقاط webhook المحمية
    PROTECTED_WEBHOOK_PATHS = getattr(settings, 'PROTECTED_WEBHOOK_PATHS', [
        '/api/webhooks/',
        '/webhooks/',
        '/financial/webhooks/',
        '/payments/webhooks/'
    ])
    
    def process_request(self, request):
        """
        معالجة الطلب للتحقق من أمان webhook
        """
        
        # فحص إذا كان الطلب لنقطة webhook محمية
        if not self._is_webhook_path(request.path):
            return None
        
        # الحصول على معلومات الطلب
        client_ip = self._get_client_ip(request)
        request_headers = dict(request.headers)
        
        try:
            # قراءة محتوى الطلب
            request_body = request.body
            
            # تحديد نوع webhook من المسار
            endpoint_name = self._extract_endpoint_name(request.path)
            
            # التحقق من صحة الطلب
            is_valid, validation_result = APIIntegrationSecurityService.validate_webhook_request(
                endpoint_name=endpoint_name,
                request_ip=client_ip,
                request_headers=request_headers,
                payload=request_body,
                signature=request_headers.get('X-Signature') or request_headers.get('X-Hub-Signature-256'),
                secret=self._get_webhook_secret(endpoint_name)
            )
            
            if not is_valid:
                # تسجيل محاولة الوصول غير المصرح بها
                logger.warning(
                    f'محاولة وصول غير مصرح بها لـ webhook: {endpoint_name} من IP: {client_ip}'
                )
                
                # إرجاع استجابة خطأ
                error_response = {
                    'error': 'Unauthorized',
                    'message': validation_result.get('error', 'طلب غير مصرح به'),
                    'timestamp': validation_result.get('timestamp')
                }
                
                # إضافة معلومات حد المعدل إذا كان السبب
                if validation_result.get('rate_limit_info'):
                    error_response['rate_limit'] = validation_result['rate_limit_info']
                
                return JsonResponse(error_response, status=403)
            
            # إضافة معلومات التحقق للطلب
            request.webhook_validation = validation_result
            request.webhook_endpoint = endpoint_name
            
            return None
            
        except Exception as e:
            logger.error(f'خطأ في middleware تأمين webhook: {e}')
            
            # في حالة الخطأ، رفض الطلب للأمان
            return JsonResponse({
                'error': 'Internal Server Error',
                'message': 'خطأ في معالجة الطلب'
            }, status=500)
    
    def _is_webhook_path(self, path):
        """
        فحص إذا كان المسار لنقطة webhook محمية
        """
        return any(path.startswith(webhook_path) for webhook_path in self.PROTECTED_WEBHOOK_PATHS)
    
    def _get_client_ip(self, request):
        """
        الحصول على IP العميل الحقيقي
        """
        # فحص رؤوس proxy المختلفة
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        
        return ip
    
    def _extract_endpoint_name(self, path):
        """
        استخراج اسم نقطة النهاية من المسار
        """
        # إزالة البادئات الشائعة
        path = path.replace('/api/webhooks/', '').replace('/webhooks/', '')
        path = path.replace('/financial/webhooks/', '').replace('/payments/webhooks/', '')
        
        # إزالة الشرطة المائلة النهائية
        path = path.rstrip('/')
        
        # إذا كان المسار فارغ، استخدم اسم افتراضي
        if not path:
            path = 'default'
        
        return path
    
    def _get_webhook_secret(self, endpoint_name):
        """
        الحصول على المفتاح السري لنقطة webhook
        """
        # البحث في إعدادات Django
        webhook_secrets = getattr(settings, 'WEBHOOK_SECRETS', {})
        
        # محاولة الحصول على المفتاح المحدد أو الافتراضي
        secret = webhook_secrets.get(endpoint_name) or webhook_secrets.get('default')
        
        return secret


class APIRateLimitMiddleware(MiddlewareMixin):
    """
    Middleware للحد من معدل استدعاءات API
    """
    
    # مسارات API المحمية
    PROTECTED_API_PATHS = getattr(settings, 'PROTECTED_API_PATHS', [
        '/api/',
        '/financial/api/',
        '/clients/api/'
    ])
    
    # حدود المعدل الافتراضية
    DEFAULT_RATE_LIMITS = {
        'authenticated': {'requests': 1000, 'window': 3600},  # 1000/ساعة للمستخدمين المسجلين
        'anonymous': {'requests': 100, 'window': 3600}        # 100/ساعة للمستخدمين المجهولين
    }
    
    def process_request(self, request):
        """
        معالجة الطلب للتحقق من حدود المعدل
        """
        
        # فحص إذا كان الطلب لمسار API محمي
        if not self._is_api_path(request.path):
            return None
        
        # تحديد نوع المستخدم
        if hasattr(request, 'user') and request.user.is_authenticated:
            user_type = 'authenticated'
            identifier = f"user_{request.user.id}"
        else:
            user_type = 'anonymous'
            identifier = f"ip_{self._get_client_ip(request)}"
        
        # الحصول على حدود المعدل
        rate_limits = getattr(settings, 'API_RATE_LIMITS', self.DEFAULT_RATE_LIMITS)
        limits = rate_limits.get(user_type, self.DEFAULT_RATE_LIMITS[user_type])
        
        # فحص حد المعدل
        allowed, limit_info = APIIntegrationSecurityService.check_rate_limit(
            identifier=identifier,
            operation_type='api_call',
            custom_limits=limits
        )
        
        if not allowed:
            # تسجيل تجاوز الحد
            logger.warning(
                f'تجاوز حد المعدل: {identifier} على {request.path}'
            )
            
            # إرجاع استجابة تجاوز الحد
            response = JsonResponse({
                'error': 'Rate Limit Exceeded',
                'message': 'تم تجاوز الحد المسموح من الطلبات',
                'rate_limit': limit_info
            }, status=429)
            
            # إضافة رؤوس حد المعدل
            response['X-RateLimit-Limit'] = str(limit_info['limit'])
            response['X-RateLimit-Remaining'] = str(limit_info['remaining'])
            response['X-RateLimit-Reset'] = str(int(limit_info['reset_time'].timestamp()))
            
            return response
        
        # إضافة معلومات حد المعدل للاستجابة
        request.rate_limit_info = limit_info
        
        return None
    
    def process_response(self, request, response):
        """
        إضافة رؤوس حد المعدل للاستجابة
        """
        
        # إضافة رؤوس حد المعدل إذا كانت متوفرة
        if hasattr(request, 'rate_limit_info') and self._is_api_path(request.path):
            limit_info = request.rate_limit_info
            
            response['X-RateLimit-Limit'] = str(limit_info['limit'])
            response['X-RateLimit-Remaining'] = str(limit_info['remaining'])
            response['X-RateLimit-Reset'] = str(int(limit_info['reset_time'].timestamp()))
        
        return response
    
    def _is_api_path(self, path):
        """
        فحص إذا كان المسار لـ API محمي
        """
        return any(path.startswith(api_path) for api_path in self.PROTECTED_API_PATHS)
    
    def _get_client_ip(self, request):
        """
        الحصول على IP العميل الحقيقي
        """
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        
        return ip


class RequestLoggingMiddleware(MiddlewareMixin):
    """
    Middleware لتسجيل الطلبات والاستجابات للتشخيص
    """
    
    # مسارات يتم تسجيلها
    LOGGED_PATHS = getattr(settings, 'LOGGED_API_PATHS', [
        '/api/',
        '/webhooks/',
        '/financial/api/'
    ])
    
    def process_request(self, request):
        """
        تسجيل معلومات الطلب
        """
        
        if not self._should_log_path(request.path):
            return None
        
        # حفظ وقت بداية الطلب
        request._start_time = timezone.now()
        
        # تسجيل معلومات الطلب (بدون بيانات حساسة)
        request_info = {
            'method': request.method,
            'path': request.path,
            'user': request.user.username if hasattr(request, 'user') and request.user.is_authenticated else 'anonymous',
            'ip': self._get_client_ip(request),
            'user_agent': request.META.get('HTTP_USER_AGENT', ''),
            'content_type': request.content_type,
            'content_length': len(request.body) if hasattr(request, 'body') else 0
        }
        
        logger.info(f'API Request: {json.dumps(request_info, ensure_ascii=False)}')
        
        return None
    
    def process_response(self, request, response):
        """
        تسجيل معلومات الاستجابة
        """
        
        if not self._should_log_path(request.path):
            return response
        
        # حساب وقت التنفيذ
        if hasattr(request, '_start_time'):
            execution_time = (timezone.now() - request._start_time).total_seconds()
        else:
            execution_time = 0
        
        # تسجيل معلومات الاستجابة
        response_info = {
            'method': request.method,
            'path': request.path,
            'status_code': response.status_code,
            'execution_time': execution_time,
            'response_size': len(response.content) if hasattr(response, 'content') else 0
        }
        
        # تحديد مستوى التسجيل حسب حالة الاستجابة
        if response.status_code >= 500:
            logger.error(f'API Response: {json.dumps(response_info, ensure_ascii=False)}')
        elif response.status_code >= 400:
            logger.warning(f'API Response: {json.dumps(response_info, ensure_ascii=False)}')
        else:
            logger.info(f'API Response: {json.dumps(response_info, ensure_ascii=False)}')
        
        return response
    
    def _should_log_path(self, path):
        """
        فحص إذا كان يجب تسجيل هذا المسار
        """
        return any(path.startswith(logged_path) for logged_path in self.LOGGED_PATHS)
    
    def _get_client_ip(self, request):
        """
        الحصول على IP العميل الحقيقي
        """
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        
        return ip