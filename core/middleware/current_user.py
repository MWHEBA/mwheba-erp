"""
Middleware لتخزين المستخدم الحالي في thread local
يسمح للـ Signals بالوصول للمستخدم الحالي
"""
from threading import local

_thread_locals = local()


def get_current_user():
    """الحصول على المستخدم الحالي من thread local"""
    return getattr(_thread_locals, 'user', None)


def get_current_impersonator():
    """الحصول على المستخدم المنتحل (الأصل) من thread local إن وجد"""
    return getattr(_thread_locals, 'impersonator', None)


def get_current_request():
    """الحصول على الـ request الحالي من thread local"""
    return getattr(_thread_locals, 'request', None)


class CurrentUserMiddleware:
    """Middleware لتخزين المستخدم الحالي ومتابع الانتحال إن وجد"""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # تخزين المستخدم والـ request في thread local
        user = getattr(request, 'user', None)
        _thread_locals.user = user
        _thread_locals.request = request
        
        impersonator = None
        request.is_impersonating = False
        request.impersonator = None
        
        # فحص وجود جلسة انتحال هوية
        if user and user.is_authenticated and hasattr(request, 'session'):
            impersonator_id = request.session.get('impersonated_by')
            if impersonator_id:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                try:
                    impersonator = User.objects.filter(id=impersonator_id).first()
                    if impersonator:
                        request.is_impersonating = True
                        request.impersonator = impersonator
                except Exception:
                    impersonator = None
        
        _thread_locals.impersonator = impersonator
        
        response = self.get_response(request)
        
        # إضافة ترويسة أمنية في حالة انتحال الهوية
        if impersonator and response:
            response['X-Impersonated-By'] = impersonator.username
        
        # تنظيف بعد الانتهاء
        if hasattr(_thread_locals, 'user'):
            del _thread_locals.user
        if hasattr(_thread_locals, 'impersonator'):
            del _thread_locals.impersonator
        if hasattr(_thread_locals, 'request'):
            del _thread_locals.request
        
        return response

