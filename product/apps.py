from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ProductConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "product"
    verbose_name = _("المنتجات والمخزون")

    def ready(self):
        """
        استدعاء الإشارات و templatetags عند تشغيل التطبيق
        """
        # استيراد الإشارات
        import product.signals

        # استيراد إشارات الحوكمة (تحديث المخزون)
        try:
            import product.signals_governed
        except ImportError:
            pass

        # استيراد إشارات المحاسبة
        try:
            import product.signals_accounting
        except ImportError:
            pass

        # استيراد إشارات إعادة حساب مخزون المنتجات المجمعة
        try:
            import product.signals_bundle_stock
        except ImportError:
            pass

        # استيراد دوال القوالب المخصصة
        import product.templatetags
