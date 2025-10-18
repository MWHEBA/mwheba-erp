from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PrintingPricingConfig(AppConfig):
    """
    إعدادات وحدة التسعير الجديدة
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'printing_pricing'
    verbose_name = _('التسعير المحسن')
    
    def ready(self):
        """
        تهيئة الوحدة عند بدء التشغيل
        """
        # يمكن إضافة signals هنا لاحقاً
        pass
