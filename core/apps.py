from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "النظام الأساسي"

    def ready(self):
        """
        تحميل templatetags عند بدء التطبيق
        """
        # استيراد ال templatetags - معلق مؤقتاً
        # import core.templatetags
        pass
