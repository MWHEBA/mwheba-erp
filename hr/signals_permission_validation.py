"""
✅ Signals للـ validation + cache invalidation
"""
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)


@receiver(pre_save, sender='hr.PermissionRequest')
def validate_permission_quota(sender, instance, **kwargs):
    """التحقق من الحصة قبل الحفظ"""
    if instance.is_extra or instance.pk or instance.status != 'pending':
        return

    from hr.services.permission_quota_service import PermissionQuotaService

    can_request, error_msg, _ = PermissionQuotaService.check_can_request(
        employee=instance.employee,
        target_date=instance.date,
        duration_hours=instance.duration_hours,
        is_extra=False
    )

    if not can_request:
        raise ValidationError({'date': error_msg})


def _clear_permission_limits_cache(instance):
    """مسح الـ cache لكل أيام الفترة المتأثرة"""
    try:
        from datetime import timedelta
        current = instance.start_date
        while current <= instance.end_date:
            cache.delete(f'permission_limits_{current.isoformat()}')
            current += timedelta(days=1)
        logger.info(f"✅ Cleared permission limits cache for Ramadan {instance.hijri_year}")
    except Exception as e:
        logger.error(f"❌ Failed to clear permission limits cache: {e}")


@receiver(post_save, sender='hr.RamadanSettings')
def invalidate_ramadan_cache_on_save(sender, instance, **kwargs):
    """مسح الـ cache عند تعديل إعدادات رمضان"""
    _clear_permission_limits_cache(instance)


@receiver(post_delete, sender='hr.RamadanSettings')
def invalidate_ramadan_cache_on_delete(sender, instance, **kwargs):
    """مسح الـ cache عند حذف إعدادات رمضان"""
    _clear_permission_limits_cache(instance)
