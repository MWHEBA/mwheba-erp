from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "النظام الأساسي"

    def ready(self):
        """
        تحميل الإشارات (Signals) عند بدء التطبيق
        """
        # استيراد الإشارات لتفعيل الإشعارات التلقائية
        import core.signals
