"""
Middleware للتحكم في الوصول للتطبيقات المعطلة
ModuleAccessMiddleware - Hardened Fail-Closed Distributed Module Guard
"""
import logging
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import resolve
from django.contrib import messages
from django.core.cache import cache

logger = logging.getLogger(__name__)


class ModuleAccessMiddleware:
    """
    Middleware مركزي للتحكم في الوصول للتطبيقات والـ APIs وحظر التطبيقات المعطلة
    يدعم Redis المشترك، سياسة الحظر الافتراضي Fail-Closed، وخريطة الـ Namespaces
    """
    
    # التطبيقات الأساسية التي لا يمكن تعطيلها أبداً
    CORE_MODULES = {'core', 'users', 'governance', 'utils', 'admin', 'select2', 'django_select2', 'api'}
    
    # خريطة معيارية صريحة لربط URL Namespaces بأكواد SystemModule في قاعدة البيانات
    DEFAULT_NAMESPACE_TO_MODULE_MAP = {
        'sale': 'customers_sales',
        'customer': 'customers_sales',
        'purchase': 'suppliers_purchases',
        'supplier': 'suppliers_purchases',
        'product': 'warehouses',
        'work_order': 'work_orders',
        'printing_pricing': 'printing_pricing',
        'hr': 'hr',
        'financial': 'financial',
        'cheques': 'financial',
        'real_estate': 'real_estate',
    }
    
    # خريطة بادئات API للتحقق من الموديولات التابعة للـ REST API
    API_PREFIX_TO_MODULE_MAP = {
        '/api/real-estate/': 'real_estate',
        '/real-estate/api/': 'real_estate',
        '/api/products/': 'warehouses',
        '/api/stocks/': 'warehouses',
        '/api/stock-movements/': 'warehouses',
        '/api/warehouses/': 'warehouses',
        '/api/categories/': 'warehouses',
        '/api/purchases/': 'suppliers_purchases',
        '/api/suppliers/': 'suppliers_purchases',
        '/api/supplier-types/': 'suppliers_purchases',
        '/api/accounts/': 'financial',
        '/api/journal-entries/': 'financial',
    }
    
    CACHE_KEY_MODULES = 'enabled_modules_set'
    CACHE_KEY_NS_MAP = 'module_namespace_map'
    CACHE_TIMEOUT = 300  # 5 دقائق مع إبطال فوري عند التحديث
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        path = request.path_info or request.path
        
        # 1. فحص مسارات الـ API ذات البادئات المحددة
        for prefix, module_code in self.API_PREFIX_TO_MODULE_MAP.items():
            if path.startswith(prefix):
                if not self._is_module_enabled(module_code):
                    logger.warning(f"Blocked API request to disabled module [{module_code}] at {path}")
                    return JsonResponse({
                        'error': 'MODULE_DISABLED',
                        'module': module_code,
                        'message': f'التطبيق "{module_code}" غير مفعّل حالياً في النظام'
                    }, status=403)
                # إذا كانت البادئة تابعة لموديول مفعل، يُسمح بالوصول الفوري
                return self.get_response(request)

        # إذا كان المسار يبدأ بـ /api/ ولم يتم حظره ببادئة سابقة، فهو مسار API أساسي (مثل /api/token/ أو /api/users/)
        if path.startswith('/api/'):
            return self.get_response(request)
        
        # 2. التحقق من مسارات صفحات الويب عبر URL Resolver
        try:
            resolved = resolve(path)
            app_name = resolved.app_name
            
            # إذا كان التطبيق من التطبيقات الأساسية (Core)، اسمح بالمرور فوراً
            if app_name and app_name in self.CORE_MODULES:
                return self.get_response(request)
            
            if app_name:
                ns_map = self._get_namespace_map()
                module_code = ns_map.get(app_name, app_name)
                
                # تخطي لو الموديول الأساسي core
                if module_code in self.CORE_MODULES:
                    return self.get_response(request)
                
                if not self._is_module_enabled(module_code):
                    logger.warning(f"Blocked request to disabled module [{module_code}] (namespace: {app_name}) at {path}")
                    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
                        return JsonResponse({
                            'error': 'MODULE_DISABLED',
                            'module': module_code,
                            'message': f'التطبيق "{module_code}" غير مفعّل حالياً'
                        }, status=403)
                    
                    messages.error(request, f'التطبيق "{module_code}" غير مفعّل حالياً')
                    return redirect('core:dashboard')
        except Exception as e:
            # في حالة الفشل في التعرف على المسار، دع Django يكمل (404 / 500)
            logger.debug(f"ModuleAccessMiddleware resolve bypass for {path}: {e}")
        
        return self.get_response(request)
    
    @classmethod
    def _get_enabled_modules(cls) -> set:
        """جلب التطبيقات المفعلة من الكاش المشترك أو قاعدة البيانات (Fail-Closed)"""
        enabled = cache.get(cls.CACHE_KEY_MODULES)
        if enabled is not None:
            return enabled
        
        try:
            from core.models import SystemModule
            enabled = set(SystemModule.objects.filter(is_enabled=True).values_list('code', flat=True))
            # تأمين التطبيقات الأساسية دائماً ضمن المفعل
            enabled.update(cls.CORE_MODULES)
            cache.set(cls.CACHE_KEY_MODULES, enabled, cls.CACHE_TIMEOUT)
            return enabled
        except Exception as e:
            logger.error(f"Error loading SystemModule in ModuleAccessMiddleware: {e}")
            # Fail-closed: السماح فقط بالـ CORE_MODULES
            return cls.CORE_MODULES.copy()
    
    @classmethod
    def _get_namespace_map(cls) -> dict:
        """جلب خريطة الـ Namespaces من الكاش المشترك أو بنائها"""
        ns_map = cache.get(cls.CACHE_KEY_NS_MAP)
        if ns_map is not None:
            return ns_map
        
        mapping = cls.DEFAULT_NAMESPACE_TO_MODULE_MAP.copy()
        try:
            from core.models import SystemModule
            for mod in SystemModule.objects.all():
                if mod.url_namespace:
                    for ns in mod.url_namespace.split(','):
                        ns_clean = ns.strip()
                        if ns_clean:
                            mapping[ns_clean] = mod.code
            cache.set(cls.CACHE_KEY_NS_MAP, mapping, cls.CACHE_TIMEOUT)
        except Exception as e:
            logger.error(f"Error loading url_namespaces from SystemModule: {e}")
        
        return mapping
    
    @classmethod
    def _is_module_enabled(cls, module_code: str) -> bool:
        """التحقق الذري من تفعيل التطبيق"""
        if module_code in cls.CORE_MODULES:
            return True
        enabled_modules = cls._get_enabled_modules()
        return module_code in enabled_modules
    
    @classmethod
    def invalidate_cache(cls):
        """إبطال الكاش فوراً عند تبديل حالة أي تطبيق في لوحة التحكم"""
        cache.delete(cls.CACHE_KEY_MODULES)
        cache.delete(cls.CACHE_KEY_NS_MAP)
