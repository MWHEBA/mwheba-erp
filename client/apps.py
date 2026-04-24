from django.apps import AppConfig


class ClientConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "client"

    def ready(self):
        """تحميل الـ signals عند بدء التطبيق"""
        import client.signals  # noqa
