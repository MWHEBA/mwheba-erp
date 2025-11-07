"""
Middleware لتخزين المستخدم الحالي في thread local
يسمح للـ Signals بالوصول للمستخدم الحالي
"""
from threading import local

_thread_locals = local()


def get_current_user():
    """الحصول على المستخدم الحالي من thread local"""
    return getattr(_thread_locals, 'user', None)


def get_current_request():
    """الحصول على الـ request الحالي من thread local"""
    return getattr(_thread_locals, 'request', None)


class CurrentUserMiddleware:
    """Middleware لتخزين المستخدم الحالي"""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # تخزين المستخدم والـ request في thread local
        _thread_locals.user = getattr(request, 'user', None)
        _thread_locals.request = request
        
        response = self.get_response(request)
        
        # تنظيف بعد الانتهاء
        if hasattr(_thread_locals, 'user'):
            del _thread_locals.user
        if hasattr(_thread_locals, 'request'):
            del _thread_locals.request
        
        return response
