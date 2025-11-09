"""
✅ JWT Authentication Middleware للتتبع والـ Logging
تم تفعيله في المرحلة 2 من الإصلاحات الأمنية
"""
import logging
from django.utils.deprecation import MiddlewareMixin
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

logger = logging.getLogger(__name__)


class JWTLoggingMiddleware(MiddlewareMixin):
    """
    Middleware لتتبع وتسجيل استخدام JWT tokens
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.jwt_auth = JWTAuthentication()
        
        # قائمة المسارات المستثناة من التتبع
        self.exempt_paths = [
            '/static/',
            '/media/',
            '/admin/',
            '/favicon.ico',
        ]
    
    def process_request(self, request):
        """معالجة الطلب وتتبع JWT"""
        path = request.path_info
        
        # تجاهل المسارات المستثناة
        for exempt_path in self.exempt_paths:
            if path.startswith(exempt_path):
                return None
        
        # محاولة الحصول على JWT token
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        
        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            
            try:
                # التحقق من الـ token
                validated_token = self.jwt_auth.get_validated_token(token)
                user = self.jwt_auth.get_user(validated_token)
                
                # تسجيل استخدام ناجح
                logger.info(
                    f"JWT Auth Success: User={user.username}, "
                    f"Path={path}, Method={request.method}, "
                    f"IP={self.get_client_ip(request)}"
                )
                
                # إضافة معلومات للـ request
                request.jwt_user = user
                request.jwt_token = validated_token
                
            except (InvalidToken, TokenError) as e:
                # تسجيل محاولة فاشلة
                logger.warning(
                    f"JWT Auth Failed: Error={str(e)}, "
                    f"Path={path}, Method={request.method}, "
                    f"IP={self.get_client_ip(request)}"
                )
                request.jwt_error = str(e)
        
        return None
    
    def get_client_ip(self, request):
        """الحصول على IP address للمستخدم"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
