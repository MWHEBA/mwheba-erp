from .logs import create_log, ACTION_LOGIN, ACTION_LOGOUT
from django.utils.deprecation import MiddlewareMixin
import re

class SystemLogMiddleware(MiddlewareMixin):
    """
    وسيط لتسجيل دخول وخروج المستخدمين في النظام بشكل تلقائي
    """
    def process_request(self, request):
        # حفظ حالة المصادقة الحالية للمستخدم
        self._is_authenticated = request.user.is_authenticated
        # حفظ هوية المستخدم الحالية إذا كان مصادق عليه
        if self._is_authenticated:
            self._current_user_id = request.user.id
        return None

    def process_response(self, request, response):
        # التحقق من مسار تسجيل الدخول - تم تسجيل الدخول
        if request.path == '/accounts/login/' and request.method == 'POST' and not self._is_authenticated and request.user.is_authenticated:
            create_log(
                request=request,
                action=ACTION_LOGIN,
                details="تم تسجيل الدخول بنجاح"
            )
        
        # التحقق من مسار تسجيل الخروج - تم تسجيل الخروج
        if request.path == '/accounts/logout/' and self._is_authenticated and not request.user.is_authenticated:
            # نستخدم هوية المستخدم التي حفظناها قبل تسجيل الخروج
            from django.contrib.auth.models import User
            user = User.objects.get(id=self._current_user_id)
            
            # إنشاء طلب مؤقت يحتوي على المستخدم والبيانات الأساسية
            from django.http import HttpRequest
            temp_request = HttpRequest()
            temp_request.user = user
            temp_request.META = request.META.copy()
            
            create_log(
                request=temp_request,
                action=ACTION_LOGOUT,
                details="تم تسجيل الخروج بنجاح"
            )
        
        return response 