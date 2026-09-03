"""
Signals لإدارة التطبيقات
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from core.models import SystemModule, SystemSetting
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=SystemModule)
def clear_module_cache_on_save(sender, instance, **kwargs):
    """
    مسح الكاش الشامل عند حفظ أو تعديل تطبيق
    """
    try:
        # مسح الكاش العام للموديولات والإعدادات
        cache.delete('enabled_modules_dict')
        cache.delete('enabled_modules_dict_v2')
        cache.delete('enabled_modules_set')
        SystemSetting.invalidate_all_system_caches()
        
        # مسح كاش التطبيق المحدد
        cache.delete(f'module_enabled_{instance.code}')
        
        try:
            cache.delete_pattern('module_enabled_*')
        except AttributeError:
            pass
        
        logger.info(f"Cache cleared for module: {instance.code}")

        # ✅ تهيئة جداول التسعير وبيئة الموردين تلقائياً عند تفعيل موديول تسعير الطباعة
        if instance.code == 'printing_pricing' and instance.is_enabled:
            try:
                from printing_pricing.services.pricing_lookup_seeder_service import PricingLookupSeederService
                from printing_pricing.services.supplier_seeder_service import PricingSupplierSeederService
                
                pricing_res = PricingLookupSeederService.seed_all()
                supplier_res = PricingSupplierSeederService.seed_all()
                logger.info(f"تم تفعيل موديول التسعير وبذر بيئة التسعير والموردين بنجاح: تسعير={pricing_res['summary']}, موردين={supplier_res}")
            except Exception as seeder_err:
                logger.error(f"فشل بذر بيئة التسعير والموردين عند تفعيل موديول التسعير: {seeder_err}")
    except Exception as e:
        logger.error(f"Error clearing cache for module {instance.code}: {str(e)}")


@receiver(post_delete, sender=SystemModule)
def clear_module_cache_on_delete(sender, instance, **kwargs):
    """
    مسح الكاش الشامل عند حذف تطبيق
    """
    try:
        cache.delete('enabled_modules_dict')
        cache.delete('enabled_modules_dict_v2')
        cache.delete('enabled_modules_set')
        SystemSetting.invalidate_all_system_caches()
        
        cache.delete(f'module_enabled_{instance.code}')
        
        try:
            cache.delete_pattern('module_enabled_*')
        except AttributeError:
            pass
        
        logger.info(f"Cache cleared after deleting module: {instance.code}")
    except Exception as e:
        logger.error(f"Error clearing cache after deleting module {instance.code}: {str(e)}")
