from django.db import models
from django.utils.translation import gettext_lazy as _
from decimal import Decimal


class PartnerCurrencyBalanceSnapshot(models.Model):
    """
    نموذج لقطات الأرصدة المجمعة لشركاء الأعمال (الموردين والعملاء) حسب العملة (Enterprise Snapshot Architecture)
    """
    PARTNER_TYPES = (
        ("supplier", _("مورد")),
        ("customer", _("عميل")),
    )

    partner_type = models.CharField(_("نوع الشريك"), max_length=20, choices=PARTNER_TYPES)
    partner_id = models.PositiveIntegerField(_("معرف الشريك"))
    currency = models.CharField(_("كود العملة"), max_length=10, default="EGP")
    
    debit_amount = models.DecimalField(
        _("إجمالي الجانب المدين بالعملة الأصلي"),
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00")
    )
    credit_amount = models.DecimalField(
        _("إجمالي الجانب الدائن بالعملة الأصلي"),
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00")
    )
    net_balance = models.DecimalField(
        _("الرصيد الصافي المتبقي"),
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00")
    )
    functional_net_balance = models.DecimalField(
        _("المعادل بالعملة الوظيفية (EGP)"),
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00")
    )
    nature = models.CharField(_("الطبيعة المحاسبية"), max_length=20, default="PAYABLE") # PAYABLE / RECEIVABLE
    
    updated_at = models.DateTimeField(_("تاريخ آخر تحديث"), auto_now=True)

    class Meta:
        verbose_name = _("لقطة انكشاف عملة شريك الأعمال")
        verbose_name_plural = _("لقطات انكشافات عملات شركاء الأعمال")
        unique_together = ("partner_type", "partner_id", "currency")
        indexes = [
            models.Index(fields=["partner_type", "partner_id"]),
            models.Index(fields=["currency"]),
        ]

    def __str__(self):
        return f"{self.get_partner_type_display()} #{self.partner_id} [{self.currency}]: Net={self.net_balance} ({self.nature})"
