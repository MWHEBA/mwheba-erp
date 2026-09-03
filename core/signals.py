"""
Core Signals - Notification System

ملاحظة: تم تعطيل جميع الإشعارات التلقائية للأحداث التالية:
- إضافة عميل/مورد/منتج/مستخدم جديد
- إنشاء فواتير المشتريات
- استلام/سداد الدفعات
- مرتجعات المشتريات

الإشعارات المتبقية النشطة:
- تنبيهات المخزون المنخفض (في product/signals.py)
- إشعارات العقود (في hr/signals.py)
- إشعارات التسويات المالية (في customer/services/)

يمكن إعادة تفعيل أي إشعار عند الحاجة من خلال إلغاء التعليق على الكود المناسب.
"""

# Placeholder file - all notification signals have been disabled
# Keep this file to maintain app structure and avoid import errors


# ============================================================
# MODULE MANAGEMENT SIGNALS
# ============================================================

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender='core.SystemModule')
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

        # ✅ تهيئة بيئة الموردين تلقائياً عند تفعيل موديول تسعير الطباعة
        if instance.code == 'printing_pricing' and instance.is_enabled:
            try:
                from printing_pricing.services.supplier_seeder_service import PricingSupplierSeederService
                result = PricingSupplierSeederService.seed_all()
                logger.info(f"تم تفعيل موديول التسعير وبذر بيئة الموردين بنجاح: {result}")
            except Exception as seeder_err:
                logger.error(f"فشل بذر بيئة الموردين عند تفعيل موديول التسعير: {seeder_err}")
    except Exception as e:
        logger.error(f"Error clearing cache for module {instance.code}: {str(e)}")


@receiver(post_delete, sender='core.SystemModule')
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


from django.db.models.signals import post_migrate

@receiver(post_migrate)
def auto_init_system_modules(sender, **kwargs):
    """
    تهيئة تطبيقات النظام تلقائياً بعد كل migrate لضمان وجودها وتفعيلها لأي عميل جديد
    """
    if sender.name == 'core':
        try:
            from django.core.management import call_command
            call_command('init_modules')
        except Exception as e:
            logger.error(f"Error auto initializing system modules: {str(e)}")

