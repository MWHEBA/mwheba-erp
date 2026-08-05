from django.db import models
from django.utils.translation import gettext_lazy as _

class SalesMode(models.TextChoices):
    FAST_CASH = "FAST_CASH", _("مبيعات سريعة نقدية")
    FAST_CREDIT = "FAST_CREDIT", _("مبيعات سريعة أجل")
    STANDARD = "STANDARD", _("مبيعات مؤسسية معيارية")

class SalesPolicy(models.Model):
    """
    FIN-SAL-001 / FIN-AR-001: Sales & Credit Policy Governance Model
    """
    name = models.CharField(_("اسم السياسة"), max_length=100)
    sales_mode = models.CharField(_("نمط البيع"), max_length=20, choices=SalesMode.choices, default=SalesMode.STANDARD)
    require_credit_check = models.BooleanField(_("يتطلب فحص ائتلاف السقف"), default=True)
    is_active = models.BooleanField(_("نشط"), default=True)

    class Meta:
        verbose_name = _("سياسة مبيعات")
        verbose_name_plural = _("سياسات المبيعات")

    def __str__(self):
        return f"{self.name} ({self.get_sales_mode_display()})"
