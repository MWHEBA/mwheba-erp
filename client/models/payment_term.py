from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _


class PaymentTerm(models.Model):
    """
    FIN-AR-001: Payment Term Master Model
    نموذج شروط وتسهيلات الدفع المحوكمة
    """
    name = models.CharField(_("اسم شرط الدفع"), max_length=100, unique=True)
    code = models.CharField(_("كود الشرط"), max_length=20, unique=True)
    days = models.IntegerField(_("عدد أيام الإمهال"), default=30)
    is_credit = models.BooleanField(_("يعتبر بيعاً ائتمانياً"), default=True)
    discount_percentage = models.DecimalField(_("نسبة خصم التعجيل %"), max_digits=5, decimal_places=2, default=Decimal("0.00"))
    discount_days = models.IntegerField(_("أيام خصم التعجيل"), default=0)
    is_active = models.BooleanField(_("نشط"), default=True)

    class Meta:
        verbose_name = _("شرط دفع")
        verbose_name_plural = _("شروط الدفع")
        ordering = ["days", "name"]

    def __str__(self):
        return f"{self.name} ({self.code} - {self.days} days)"
