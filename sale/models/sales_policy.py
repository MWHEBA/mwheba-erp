from django.db import models
from django.utils.translation import gettext_lazy as _


class SalesMode(models.TextChoices):
    FAST_CASH = "FAST_CASH", _("نقدي سريع بدون ائتمان")
    FAST_CREDIT = "FAST_CREDIT", _("آجل سريع محوكم بالائتمان")
    STANDARD = "STANDARD", _("معياري متعدد المراحل")


class SalesPolicy(models.Model):
    """
    FIN-SAL-001 / FIN-AR-001: Sales Policy Master Model
    نموذج سياسة المبيعات المزدوجة المحوكمة
    """
    name = models.CharField(_("اسم السياسة"), max_length=100, unique=True)
    sales_mode = models.CharField(_("نمط المبيعات"), max_length=20, choices=SalesMode.choices, default=SalesMode.STANDARD)
    require_credit_check = models.BooleanField(_("يتطلب فحص الائتمان"), default=True)
    allow_fast_invoice = models.BooleanField(_("إصدار فاتورة سريعة مباشرة"), default=False)
    is_active = models.BooleanField(_("نشط"), default=True)

    class Meta:
        verbose_name = _("سياسة مبيعات")
        verbose_name_plural = _("سياسات المبيعات")

    def __str__(self):
        return f"{self.name} ({self.sales_mode})"
