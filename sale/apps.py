from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class SaleConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'sale'
    verbose_name = _('المبيعات')
    
    def ready(self):
        """
        تحميل ملف الإشارات (signals) عند بدء التطبيق
        """
        import sale.signals
