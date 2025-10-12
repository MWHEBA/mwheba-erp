from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class FinancialConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'financial'
    verbose_name = _('الحسابات المالية')
    
    def ready(self):
        """تحميل الإشارات عند جاهزية التطبيق"""
        try:
            # استيراد الإشارات لضمان تسجيلها
            from . import signals
        except ImportError:
            pass
