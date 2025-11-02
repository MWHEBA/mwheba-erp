"""
وظائف Cron لفحص التنبيهات دورياً
يمكن استخدامها مع django-crontab أو Celery Beat
"""
from django.utils import timezone
from .services.notification_service import NotificationService
import logging

logger = logging.getLogger(__name__)


def check_low_stock_alerts():
    """
    فحص تنبيهات المخزون المنخفض
    يُنفذ كل ساعة
    """
    try:
        logger.info("🔍 بدء فحص تنبيهات المخزون المنخفض...")
        alerts = NotificationService.check_low_stock_alerts()
        logger.info(f"✅ تم إنشاء {len(alerts)} تنبيه مخزون منخفض")
        return len(alerts)
    except Exception as e:
        logger.error(f"❌ خطأ في فحص تنبيهات المخزون: {e}")
        return 0


def check_due_invoices_alerts():
    """
    فحص تنبيهات الفواتير المستحقة
    يُنفذ يومياً
    """
    try:
        logger.info("🔍 بدء فحص تنبيهات الفواتير المستحقة...")
        alerts = NotificationService.check_due_invoices_alerts()
        logger.info(f"✅ تم إنشاء {len(alerts)} تنبيه فواتير مستحقة")
        return len(alerts)
    except Exception as e:
        logger.error(f"❌ خطأ في فحص تنبيهات الفواتير: {e}")
        return 0


def check_all_alerts():
    """
    فحص جميع التنبيهات
    يُنفذ كل 6 ساعات
    """
    try:
        logger.info("🔍 بدء فحص جميع التنبيهات...")
        alerts = NotificationService.check_all_alerts()
        logger.info(f"✅ تم إنشاء {len(alerts)} تنبيه إجمالي")
        return len(alerts)
    except Exception as e:
        logger.error(f"❌ خطأ في فحص جميع التنبيهات: {e}")
        return 0


def cleanup_old_notifications(days=30):
    """
    حذف الإشعارات القديمة المقروءة
    يُنفذ أسبوعياً
    """
    from core.models import Notification
    from datetime import timedelta
    
    try:
        logger.info(f"🧹 بدء تنظيف الإشعارات القديمة (أكثر من {days} يوم)...")
        cutoff_date = timezone.now() - timedelta(days=days)
        
        # حذف الإشعارات المقروءة القديمة فقط
        deleted_count = Notification.objects.filter(
            is_read=True,
            created_at__lt=cutoff_date
        ).delete()[0]
        
        logger.info(f"✅ تم حذف {deleted_count} إشعار قديم")
        return deleted_count
    except Exception as e:
        logger.error(f"❌ خطأ في تنظيف الإشعارات: {e}")
        return 0
