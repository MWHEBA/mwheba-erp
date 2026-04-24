"""
Middleware للتحكم في الوصول للتطبيقات المعطلة
"""
from django.http import Http404
from django.shortcuts import redirect
from django.urls import resolve
from django.contrib import messages
from django.utils import timezone
from django.core.cache import cache


class ModuleAccessMiddleware:
    """
    Middleware للتحكم في الوصول للتطبيقات المعطلة
    """
    
    # التطبيقات الأساسية التي لا يمكن تعطيلها
    CORE_MODULES = ['core', 'users', 'governance', 'utils', 'api', 'admin', 'select2']
    
    def __init__(self, get_response):
        self.get_response = get_response
        self._enabled_modules_cache = None
        self._cache_time = None
    
    def __call__(self, request):
        # تحديث الكاش كل 5 دقائق
        if not self._cache_time or \
           (timezone.now() - self._cache_time).seconds > 300:
            self._update_cache()
        
        # التحقق من الوصول للتطبيق
        try:
            resolved = resolve(request.path)
            app_name = resolved.app_name
            
            if app_name and app_name not in self.CORE_MODULES:
                if not self._is_module_enabled(app_name):
                    messages.error(request, f'التطبيق "{app_name}" غير مفعّل حالياً')
                    return redirect('core:dashboard')
        except Exception:
            pass
        
        response = self.get_response(request)
        return response
    
    def _update_cache(self):
        """تحديث كاش التطبيقات المفعلة"""
        try:
            from core.models import SystemModule
            
            # محاولة الحصول من الكاش أولاً
            cache_key = 'enabled_modules_set'
            self._enabled_modules_cache = cache.get(cache_key)
            
            if self._enabled_modules_cache is None:
                self._enabled_modules_cache = set(
                    SystemModule.objects.filter(is_enabled=True).values_list('code', flat=True)
                )
                cache.set(cache_key, self._enabled_modules_cache, 300)
            
            self._cache_time = timezone.now()
        except Exception:
            # في حالة عدم وجود الجدول، افترض أن كل شيء مفعّل
            self._enabled_modules_cache = set()
    
    def _is_module_enabled(self, module_code):
        """التحقق من تفعيل التطبيق"""
        if not self._enabled_modules_cache:
            return True
        return module_code in self._enabled_modules_cache
