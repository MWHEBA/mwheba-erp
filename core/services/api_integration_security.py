"""
خدمة تأمين تكامل APIs - API Integration Security Service
تتضمن التحقق من التوقيعات، الحد من المعدل، وتسجيل الطلبات/الاستجابات
"""

import logging
import time
import hashlib
import hmac
import json
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from django.core.cache import cache
from django.conf import settings
from django.utils import timezone
from governance.services import AuditService
from core.services.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


class APIIntegrationSecurityService:
    """
    خدمة تأمين تكامل APIs مع معالجة شاملة للأمان
    """
    
    # إعدادات الحد من المعدل (Rate Limiting)
    DEFAULT_RATE_LIMITS = {
        'webhook': {'requests': 100, 'window': 3600},  # 100 طلب/ساعة
        'api_call': {'requests': 1000, 'window': 3600},  # 1000 طلب/ساعة
        'financial_api': {'requests': 500, 'window': 3600}  # 500 طلب/ساعة
    }
    
    # إعدادات الطلبات الخارجية
    REQUEST_TIMEOUT = 30  # ثانية
    MAX_RETRIES = 3
    RETRY_DELAYS = [1, 3, 9]  # ثواني
    
    def __init__(self):
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60,
            name="api_integration"
        )
    
    @classmethod
    def validate_webhook_signature(
        cls,
        payload: bytes,
        signature: str,
        secret: str,
        algorithm: str = 'sha256'
    ) -> bool:
        """
        التحقق من توقيع webhook
        
        Args:
            payload: محتوى الطلب
            signature: التوقيع المرسل
            secret: المفتاح السري
            algorithm: خوارزمية التشفير
            
        Returns:
            bool: صحة التوقيع
        """
        try:
            # إنشاء التوقيع المتوقع
            if algorithm == 'sha256':
                expected_signature = hmac.new(
                    secret.encode('utf-8'),
                    payload,
                    hashlib.sha256
                ).hexdigest()
            elif algorithm == 'sha1':
                expected_signature = hmac.new(
                    secret.encode('utf-8'),
                    payload,
                    hashlib.sha1
                ).hexdigest()
            else:
                raise ValueError(f"خوارزمية غير مدعومة: {algorithm}")
            
            # مقارنة آمنة للتوقيعات
            signature_clean = signature.replace('sha256=', '').replace('sha1=', '')
            is_valid = hmac.compare_digest(expected_signature, signature_clean)
            
            # تسجيل محاولة التحقق
            AuditService.log_operation(
                operation_type='webhook_signature_validation',
                details={
                    'algorithm': algorithm,
                    'signature_valid': is_valid,
                    'payload_size': len(payload),
                    'timestamp': timezone.now().isoformat()
                }
            )
            
            return is_valid
            
        except Exception as e:
            logger.error(f"خطأ في التحقق من توقيع webhook: {e}")
            return False
    
    @classmethod
    def check_rate_limit(
        cls,
        identifier: str,
        operation_type: str = 'api_call',
        custom_limits: Optional[Dict[str, int]] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        فحص حدود المعدل للطلبات
        
        Args:
            identifier: معرف فريد (IP, user_id, etc.)
            operation_type: نوع العملية
            custom_limits: حدود مخصصة
            
        Returns:
            Tuple: (مسموح, معلومات الحد)
        """
        # الحصول على حدود المعدل
        limits = custom_limits or cls.DEFAULT_RATE_LIMITS.get(
            operation_type, 
            cls.DEFAULT_RATE_LIMITS['api_call']
        )
        
        max_requests = limits['requests']
        window_seconds = limits['window']
        
        # مفتاح cache
        cache_key = f"rate_limit:{operation_type}:{identifier}"
        
        # الحصول على العدد الحالي
        current_count = cache.get(cache_key, 0)
        
        # معلومات الحد
        limit_info = {
            'limit': max_requests,
            'remaining': max(0, max_requests - current_count - 1),
            'reset_time': timezone.now() + timedelta(seconds=window_seconds),
            'window_seconds': window_seconds
        }
        
        # فحص الحد
        if current_count >= max_requests:
            # تسجيل تجاوز الحد
            AuditService.log_operation(
                operation_type='rate_limit_exceeded',
                details={
                    'identifier': identifier,
                    'operation_type': operation_type,
                    'current_count': current_count,
                    'limit': max_requests,
                    'timestamp': timezone.now().isoformat()
                }
            )
            
            return False, limit_info
        
        # زيادة العداد
        cache.set(cache_key, current_count + 1, timeout=window_seconds)
        
        return True, limit_info
    
    @classmethod
    def make_secure_api_call(
        cls,
        url: str,
        method: str = 'GET',
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        auth_token: Optional[str] = None,
        rate_limit_key: Optional[str] = None,
        log_request: bool = True
    ) -> Dict[str, Any]:
        """
        إجراء استدعاء API آمن مع تسجيل وحماية
        
        Args:
            url: رابط API
            method: طريقة HTTP
            data: بيانات الطلب
            headers: رؤوس HTTP
            auth_token: رمز المصادقة
            rate_limit_key: مفتاح حد المعدل
            log_request: تسجيل الطلب والاستجابة
            
        Returns:
            Dict: نتيجة الاستدعاء
        """
        service = cls()
        
        # فحص حد المعدل
        if rate_limit_key:
            allowed, limit_info = cls.check_rate_limit(
                rate_limit_key, 'api_call'
            )
            if not allowed:
                return {
                    'success': False,
                    'error': 'تم تجاوز حد المعدل المسموح',
                    'rate_limit_info': limit_info
                }
        
        # إعداد الرؤوس
        request_headers = headers or {}
        if auth_token:
            request_headers['Authorization'] = f'Bearer {auth_token}'
        
        request_headers.setdefault('Content-Type', 'application/json')
        request_headers.setdefault('User-Agent', 'CorporateERP/1.0')
        
        # معلومات الطلب للتسجيل
        request_info = {
            'url': url,
            'method': method,
            'headers': {k: v for k, v in request_headers.items() 
                       if k.lower() not in ['authorization', 'x-api-key']},
            'data_size': len(json.dumps(data)) if data else 0,
            'timestamp': timezone.now().isoformat()
        }
        
        start_time = time.time()
        
        try:
            # استخدام Circuit Breaker
            with service.circuit_breaker:
                # إجراء الطلب
                response = requests.request(
                    method=method.upper(),
                    url=url,
                    json=data if method.upper() in ['POST', 'PUT', 'PATCH'] else None,
                    params=data if method.upper() == 'GET' else None,
                    headers=request_headers,
                    timeout=cls.REQUEST_TIMEOUT
                )
                
                execution_time = time.time() - start_time
                
                # معلومات الاستجابة
                response_info = {
                    'status_code': response.status_code,
                    'response_size': len(response.content),
                    'execution_time': execution_time,
                    'success': response.status_code < 400
                }
                
                # تسجيل الطلب والاستجابة
                if log_request:
                    cls._log_api_call(request_info, response_info, response)
                
                # معالجة الاستجابة
                if response.status_code < 400:
                    try:
                        response_data = response.json()
                    except ValueError:
                        response_data = {'raw_response': response.text}
                    
                    return {
                        'success': True,
                        'data': response_data,
                        'status_code': response.status_code,
                        'execution_time': execution_time
                    }
                else:
                    return {
                        'success': False,
                        'error': f'HTTP {response.status_code}: {response.text}',
                        'status_code': response.status_code,
                        'execution_time': execution_time
                    }
                    
        except requests.exceptions.Timeout:
            execution_time = time.time() - start_time
            error_msg = f'انتهت مهلة الطلب ({cls.REQUEST_TIMEOUT}s)'
            
            if log_request:
                cls._log_api_call(request_info, {
                    'error': error_msg,
                    'execution_time': execution_time,
                    'success': False
                })
            
            return {
                'success': False,
                'error': error_msg,
                'execution_time': execution_time
            }
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f'خطأ في استدعاء API: {str(e)}'
            
            if log_request:
                cls._log_api_call(request_info, {
                    'error': error_msg,
                    'execution_time': execution_time,
                    'success': False
                })
            
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'execution_time': execution_time
            }
    
    @classmethod
    def _log_api_call(
        cls,
        request_info: Dict[str, Any],
        response_info: Dict[str, Any],
        response: Optional[requests.Response] = None
    ):
        """
        تسجيل استدعاء API للتشخيص
        """
        log_data = {
            'request': request_info,
            'response': response_info,
            'timestamp': timezone.now().isoformat()
        }
        
        # إضافة عينة من الاستجابة للتشخيص (بدون بيانات حساسة)
        if response and response_info.get('success'):
            try:
                response_sample = response.text[:500]  # أول 500 حرف
                log_data['response']['sample'] = response_sample
            except:
                pass
        
        # تسجيل في نظام التدقيق
        AuditService.log_operation(
            operation_type='api_call_log',
            details=log_data
        )
        
        # تسجيل في cache للمراقبة السريعة
        cache_key = f"api_calls_log:{timezone.now().strftime('%Y%m%d%H')}"
        calls_log = cache.get(cache_key, [])
        calls_log.append({
            'url': request_info['url'],
            'method': request_info['method'],
            'status': response_info.get('status_code', 'error'),
            'time': response_info.get('execution_time', 0),
            'timestamp': timezone.now().isoformat()
        })
        
        # الاحتفاظ بآخر 100 استدعاء فقط
        if len(calls_log) > 100:
            calls_log = calls_log[-100:]
        
        cache.set(cache_key, calls_log, timeout=3600)  # ساعة واحدة
    
    @classmethod
    def create_webhook_endpoint_security(
        cls,
        endpoint_name: str,
        allowed_ips: Optional[List[str]] = None,
        required_headers: Optional[Dict[str, str]] = None,
        rate_limit: Optional[Dict[str, int]] = None
    ) -> Dict[str, Any]:
        """
        إنشاء إعدادات أمان لنقطة webhook
        
        Args:
            endpoint_name: اسم نقطة النهاية
            allowed_ips: قائمة IPs المسموحة
            required_headers: رؤوس مطلوبة
            rate_limit: حدود المعدل المخصصة
            
        Returns:
            Dict: إعدادات الأمان
        """
        security_config = {
            'endpoint_name': endpoint_name,
            'allowed_ips': allowed_ips or [],
            'required_headers': required_headers or {},
            'rate_limit': rate_limit or cls.DEFAULT_RATE_LIMITS['webhook'],
            'created_at': timezone.now().isoformat(),
            'enabled': True
        }
        
        # حفظ الإعدادات
        cache_key = f"webhook_security:{endpoint_name}"
        cache.set(cache_key, security_config, timeout=86400)  # 24 ساعة
        
        # تسجيل إنشاء الإعدادات
        AuditService.log_operation(
            operation_type='webhook_security_config_created',
            details={
                'endpoint_name': endpoint_name,
                'config': security_config
            }
        )
        
        return security_config
    
    @classmethod
    def validate_webhook_request(
        cls,
        endpoint_name: str,
        request_ip: str,
        request_headers: Dict[str, str],
        payload: bytes,
        signature: Optional[str] = None,
        secret: Optional[str] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        التحقق من صحة طلب webhook
        
        Returns:
            Tuple: (صالح, تفاصيل التحقق)
        """
        validation_result = {
            'valid': False,
            'checks': {},
            'timestamp': timezone.now().isoformat()
        }
        
        # الحصول على إعدادات الأمان
        cache_key = f"webhook_security:{endpoint_name}"
        security_config = cache.get(cache_key)
        
        if not security_config:
            validation_result['checks']['config_found'] = False
            validation_result['error'] = 'إعدادات الأمان غير موجودة'
            return False, validation_result
        
        validation_result['checks']['config_found'] = True
        
        # فحص IP المسموح
        allowed_ips = security_config.get('allowed_ips', [])
        if allowed_ips and request_ip not in allowed_ips:
            validation_result['checks']['ip_allowed'] = False
            validation_result['error'] = f'IP غير مسموح: {request_ip}'
            return False, validation_result
        
        validation_result['checks']['ip_allowed'] = True
        
        # فحص الرؤوس المطلوبة
        required_headers = security_config.get('required_headers', {})
        for header_name, expected_value in required_headers.items():
            actual_value = request_headers.get(header_name)
            if actual_value != expected_value:
                validation_result['checks']['headers_valid'] = False
                validation_result['error'] = f'رأس مطلوب مفقود أو خاطئ: {header_name}'
                return False, validation_result
        
        validation_result['checks']['headers_valid'] = True
        
        # فحص حد المعدل
        rate_limit_key = f"webhook:{endpoint_name}:{request_ip}"
        allowed, limit_info = cls.check_rate_limit(
            rate_limit_key, 'webhook', security_config.get('rate_limit')
        )
        
        validation_result['checks']['rate_limit_ok'] = allowed
        validation_result['rate_limit_info'] = limit_info
        
        if not allowed:
            validation_result['error'] = 'تم تجاوز حد المعدل'
            return False, validation_result
        
        # فحص التوقيع (إذا كان متوفراً)
        if signature and secret:
            signature_valid = cls.validate_webhook_signature(
                payload, signature, secret
            )
            validation_result['checks']['signature_valid'] = signature_valid
            
            if not signature_valid:
                validation_result['error'] = 'توقيع غير صحيح'
                return False, validation_result
        
        # جميع الفحوصات نجحت
        validation_result['valid'] = True
        
        # تسجيل الطلب الصالح
        AuditService.log_operation(
            operation_type='webhook_request_validated',
            details={
                'endpoint_name': endpoint_name,
                'request_ip': request_ip,
                'validation_result': validation_result
            }
        )
        
        return True, validation_result
    
    @classmethod
    def get_api_integration_health(cls) -> Dict[str, Any]:
        """
        الحصول على حالة صحة تكامل APIs
        """
        service = cls()
        
        # إحصائيات الاستدعاءات الحديثة
        current_hour = timezone.now().strftime('%Y%m%d%H')
        cache_key = f"api_calls_log:{current_hour}"
        recent_calls = cache.get(cache_key, [])
        
        # تحليل الإحصائيات
        total_calls = len(recent_calls)
        successful_calls = len([call for call in recent_calls 
                              if str(call.get('status', '')).startswith('2')])
        
        error_rate = 0.0
        avg_response_time = 0.0
        
        if total_calls > 0:
            error_rate = (total_calls - successful_calls) / total_calls
            avg_response_time = sum(call.get('time', 0) for call in recent_calls) / total_calls
        
        health_status = {
            'status': 'healthy',
            'timestamp': timezone.now().isoformat(),
            'circuit_breaker': service.circuit_breaker.get_status(),
            'statistics': {
                'total_calls_last_hour': total_calls,
                'successful_calls': successful_calls,
                'error_rate': error_rate,
                'average_response_time': avg_response_time
            },
            'recommendations': []
        }
        
        # تحليل الحالة
        if service.circuit_breaker.state == 'open':
            health_status['status'] = 'critical'
            health_status['recommendations'].append('Circuit breaker مفتوح - فحص الخدمات الخارجية')
        
        if error_rate > 0.1:  # أكثر من 10% أخطاء
            health_status['status'] = 'warning'
            health_status['recommendations'].append(f'معدل أخطاء عالي: {error_rate:.1%}')
        
        if avg_response_time > 10:  # أكثر من 10 ثواني
            health_status['status'] = 'warning'
            health_status['recommendations'].append(f'متوسط وقت الاستجابة عالي: {avg_response_time:.1f}s')
        
        return health_status