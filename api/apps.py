from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api'
    verbose_name = 'API'

    def ready(self):
        # استيراد إشارات التطبيق هنا
        try:
            import api.signals
        except ImportError:
            pass 