"""
Celery tasks for HR module
مهام Celery لوحدة الموارد البشرية
"""
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def process_biometric_logs_task(self):
    """
    معالجة سجلات البصمة تلقائياً
    
    هذه المهمة تعمل بشكل دوري لمعالجة سجلات البصمة الجديدة
    وتحويلها إلى سجلات حضور
    """
    try:
        from .models import BiometricLog
        from .utils.biometric_utils import process_biometric_logs
        
        # جلب السجلات غير المعالجة
        unprocessed_logs = BiometricLog.objects.filter(
            is_processed=False,
            employee__isnull=False  # فقط السجلات المربوطة بموظفين
        ).count()
        
        if unprocessed_logs == 0:
            return {
                'success': True,
                'message': 'لا توجد سجلات جديدة',
                'processed': 0
            }
        
        
        # معالجة السجلات
        result = process_biometric_logs()
        
        
        return {
            'success': True,
            'processed': result.get('processed', 0),
            'created_attendance': result.get('created', 0),
            'updated_attendance': result.get('updated', 0)
        }
        
    except Exception as e:
        logger.error(f"خطأ في معالجة سجلات البصمة: {str(e)}", exc_info=True)
        # إعادة المحاولة بعد 5 دقائق
        raise self.retry(exc=e, countdown=300)


@shared_task
def cleanup_old_biometric_logs(months=6):
    """
    حذف سجلات البصمة القديمة
    
    Args:
        months: عدد الشهور (الافتراضي 6)
    """
    try:
        from .models import BiometricLog
        
        cutoff_date = timezone.now() - timedelta(days=months * 30)
        
        old_logs = BiometricLog.objects.filter(timestamp__lt=cutoff_date)
        count = old_logs.count()
        
        if count > 0:
            old_logs.delete()
            return {'success': True, 'deleted': count}
        else:
            return {'success': True, 'deleted': 0}
            
    except Exception as e:
        logger.error(f"خطأ في حذف السجلات القديمة: {str(e)}")
        return {'success': False, 'error': str(e)}


@shared_task
def sync_biometric_devices():
    """
    مزامنة جميع أجهزة البصمة النشطة
    
    هذه المهمة تقوم بجلب السجلات الجديدة من جميع أجهزة البصمة
    """
    try:
        from .models import BiometricDevice
        from .services.biometric_service import BiometricService
        
        active_devices = BiometricDevice.objects.filter(
            is_active=True,
            status='active'
        )
        
        results = []
        for device in active_devices:
            try:
                result = BiometricService.sync_device(device)
                results.append({
                    'device': device.device_name,
                    'success': result.get('success', False),
                    'records': result.get('records_fetched', 0)
                })
            except Exception as e:
                logger.error(f"خطأ في مزامنة جهاز {device.device_name}: {str(e)}")
                results.append({
                    'device': device.device_name,
                    'success': False,
                    'error': str(e)
                })
        
        total_records = sum(r.get('records', 0) for r in results)
        
        return {
            'success': True,
            'devices_synced': len(active_devices),
            'total_records': total_records,
            'results': results
        }
        
    except Exception as e:
        logger.error(f"خطأ في مزامنة الأجهزة: {str(e)}")
        return {'success': False, 'error': str(e)}
