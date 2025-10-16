from django.apps import AppConfig


class PricingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "pricing"
    
    def ready(self):
        # استيراد admin للزنكات
        try:
            import pricing.admin_plates
        except ImportError:
            pass
