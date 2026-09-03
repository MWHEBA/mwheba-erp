from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PrintingPricingConfig(AppConfig):
    """
    إعدادات وحدة التسعير الجديدة
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'printing_pricing'
    verbose_name = _('تسعير المطبوعات والخدمات الإعلانية')
    
    def ready(self):
        """
        تهيئة الوحدة عند بدء التشغيل وربط إشارة ترحيل قاعدة البيانات
        """
        from django.db.models.signals import post_migrate

        def on_post_migrate(sender, **kwargs):
            try:
                from core.models import SystemModule
                if SystemModule.objects.filter(code='printing_pricing', is_enabled=True).exists():
                    from printing_pricing.services.supplier_seeder_service import PricingSupplierSeederService
                    PricingSupplierSeederService.seed_all()
            except Exception:
                pass

        post_migrate.connect(on_post_migrate, sender=self)
