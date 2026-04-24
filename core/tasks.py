# ✅ SIMPLIFIED MONITORING TASKS
# Basic maintenance tasks for SMB-scale deployment

from celery import shared_task
from django.utils import timezone
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2)
def basic_health_check_task(self):
    """
    Basic system health check task
    Simplified version for SMB-scale deployment
    """
    try:
        from core.monitoring import SimpleMonitoringService
        
        service = SimpleMonitoringService()
        health_status = service.check_system_health()
        
        # Log basic health status
        if not health_status.get('healthy', True):
            logger.warning(f"System health check failed: {health_status}")
        
        return {
            'success': True,
            'status': health_status,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as exc:
        logger.error(f"Health check task failed: {exc}")
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True, max_retries=1)
def cleanup_old_logs_task(self, days_to_keep=30):
    """
    Clean up old log entries
    Basic maintenance task for log retention
    """
    try:
        from core.models import UnifiedLog
        from datetime import timedelta
        
        cutoff_date = timezone.now() - timedelta(days=days_to_keep)
        
        # Delete old logs
        deleted_count, _ = UnifiedLog.objects.filter(
            timestamp__lt=cutoff_date
        ).delete()
        
        logger.info(f"Cleaned up {deleted_count} old log entries")
        
        return {
            'success': True,
            'deleted_count': deleted_count,
            'cutoff_date': cutoff_date.isoformat()
        }
        
    except Exception as exc:
        logger.error(f"Log cleanup task failed: {exc}")
        return {'success': False, 'error': str(exc)}