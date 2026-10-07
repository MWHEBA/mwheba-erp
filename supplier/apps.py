from django.apps import AppConfig


class SupplierConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "supplier"

    def ready(self):
        """تحميل الـ signals عند بدء التطبيق"""
        import supplier.signals  # noqa
