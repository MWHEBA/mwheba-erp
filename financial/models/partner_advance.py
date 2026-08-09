from django.db import models
from django.utils.translation import gettext_lazy as _
from decimal import Decimal


class PartnerCurrencyBalanceSnapshot(models.Model):
    """
    جدول اللقطة السريعة للأرصدة المسبقة المتاحة للشركاء (عملاء / موردين) حسب العملة
    Indexed Query SLA < 300ms دون بطء أو N+1 Queries
    """
    PARTNER_TYPE_CHOICES = (
        ("customer", _("عميل")),
        ("supplier", _("مورد")),
    )

    partner_type = models.CharField(_("نوع الشريك"), max_length=20, choices=PARTNER_TYPE_CHOICES)
    partner_id = models.PositiveIntegerField(_("معرف الشريك"))
    currency = models.ForeignKey(
        "financial.Currency",
        on_delete=models.PROTECT,
        verbose_name=_("العملة"),
        related_name="partner_advance_snapshots",
    )
    advance_balance = models.DecimalField(
        _("الرصيد المسبق المتاح"),
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    last_processed_entry_id = models.BigIntegerField(
        _("معرف آخر قيد اليومية عولج"),
        null=True,
        blank=True,
    )
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)

    class Meta:
        verbose_name = _("لقطة الرصيد المسبق للشريك")
        verbose_name_plural = _("لقطات الأرصدة المسبقة للشركاء")
        unique_together = ("partner_type", "partner_id", "currency")
        indexes = [
            models.Index(fields=["partner_type", "partner_id", "currency"], name="idx_partner_curr_snap"),
        ]

    def __str__(self):
        return f"Snapshot [{self.get_partner_type_display()} #{self.partner_id}] {self.advance_balance} {self.currency.code if self.currency else ''}"


class PartnerAdvanceSettlement(models.Model):
    """
    جدول تسويات وتخصيص الدفعات المسبقة على الفواتير
    """
    STATUS_CHOICES = (
        ("APPLIED", _("مطبق")),
        ("REVERSED", _("معكوس")),
    )

    customer_payment = models.ForeignKey(
        "client.CustomerPayment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer_settlements",
        verbose_name=_("دفعة العميل المقدمة"),
    )
    supplier_payment = models.ForeignKey(
        "supplier.SupplierAdvancePayment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supplier_settlements",
        verbose_name=_("دفعة المورد المقدمة"),
    )
    sale = models.ForeignKey(
        "sale.Sale",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="advance_settlements",
        verbose_name=_("فاتورة المبيعات"),
    )
    purchase = models.ForeignKey(
        "purchase.Purchase",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="advance_settlements",
        verbose_name=_("فاتورة المشتريات"),
    )
    allocated_amount = models.DecimalField(
        _("المبلغ المخصص والتسوية"),
        max_digits=15,
        decimal_places=2,
    )
    currency = models.ForeignKey(
        "financial.Currency",
        on_delete=models.PROTECT,
        verbose_name=_("عملة التسوية"),
        related_name="partner_settlements",
    )
    exchange_rate_snapshot = models.DecimalField(
        _("لقطة سعر الصرف"),
        max_digits=12,
        decimal_places=6,
        default=Decimal("1.000000"),
    )
    realized_fx_difference = models.DecimalField(
        _("فروق عملة محققة"),
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
    )
    fx_gain_loss_account = models.ForeignKey(
        "financial.ChartOfAccounts",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_("حساب فروق العملة المحققة"),
    )
    journal_entry = models.ForeignKey(
        "financial.JournalEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("القيد المحاسبي المرفق"),
    )
    status = models.CharField(
        _("حالة التسوية"),
        max_length=20,
        choices=STATUS_CHOICES,
        default="APPLIED",
    )
    created_by = models.ForeignKey(
        "users.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_("أنشئ بواسطة"),
    )
    created_at = models.DateTimeField(_("تاريخ التسوية"), auto_now_add=True)

    class Meta:
        verbose_name = _("تسوية رصيد مسبق")
        verbose_name_plural = _("تسويات الأرصدة المسبقة")
        ordering = ["-created_at"]

    def __str__(self):
        target = self.sale or self.purchase
        return f"Settlement #{self.id} - {self.allocated_amount} {self.currency.code if self.currency else ''} -> {target}"

