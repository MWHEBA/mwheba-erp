"""
Signals لإدارة التطبيقات
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from core.models import SystemModule
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=SystemModule)
def clear_module_cache_on_save(sender, instance, **kwargs):
    """
    مسح الكاش عند حفظ أو تعديل تطبيق
    """
    try:
        # مسح الكاش العام
        cache.delete('enabled_modules_dict')
        cache.delete('enabled_modules_set')
        
        # مسح كاش التطبيق المحدد
        cache.delete(f'module_enabled_{instance.code}')
        
        # محاولة مسح جميع الكاش المتعلق بالتطبيقات
        try:
            cache.delete_pattern('module_enabled_*')
        except AttributeError:
            # LocMemCache لا يدعم delete_pattern
            pass
        
        logger.info(f"Cache cleared for module: {instance.code}")
    except Exception as e:
        logger.error(f"Error clearing cache for module {instance.code}: {str(e)}")


@receiver(post_delete, sender=SystemModule)
def clear_module_cache_on_delete(sender, instance, **kwargs):
    """
    مسح الكاش عند حذف تطبيق
    """
    try:
        cache.delete('enabled_modules_dict')
        cache.delete('enabled_modules_set')
        cache.delete(f'module_enabled_{instance.code}')
        
        try:
            cache.delete_pattern('module_enabled_*')
        except AttributeError:
            pass
        
        logger.info(f"Cache cleared after deleting module: {instance.code}")
    except Exception as e:
        logger.error(f"Error clearing cache after deleting module {instance.code}: {str(e)}")
