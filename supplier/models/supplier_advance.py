from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from decimal import Decimal
from django.utils import timezone

from supplier.models import Supplier


class SupplierAdvancePayment(models.Model):
    """
    نموذج الدفعات المقدمة للموردين (عربون/سداد تحت الحساب قبل صدور الفواتير)
    """
    PAYMENT_METHODS = (
        ("cash", _("نقدي")),
        ("bank_transfer", _("تحويل بنكي")),
        ("check", _("شيك")),
    )

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        verbose_name=_("المورد"),
        related_name="advance_payments",
    )
    amount = models.DecimalField(_("المبلغ الأصلي"), max_digits=12, decimal_places=2)
    allocated_amount = models.DecimalField(_("المبلغ المخصص على الفواتير"), max_digits=12, decimal_places=2, default=Decimal("0.00"))
    payment_date = models.DateField(_("تاريخ الصرف"), default=timezone.now)
    payment_method = models.CharField(
        _("طريقة الصرف"), max_length=20, choices=PAYMENT_METHODS, default="cash"
    )
    reference_number = models.CharField(
        _("رقم المرجع / الشيك"), max_length=50, blank=True, null=True
    )
    currency = models.ForeignKey(
        "financial.Currency",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_("العملة"),
    )
    financial_account = models.ForeignKey(
        "financial.ChartOfAccounts",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("الخزينة / البنك المصدر"),
    )
    journal_entry = models.ForeignKey(
        "financial.JournalEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("القيد المحاسبي المرتبط"),
    )
    notes = models.TextField(_("ملاحظات / السبب"), blank=True, null=True)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("أنشئ بواسطة"),
    )

    class Meta:
        verbose_name = _("دفعة مقدمة للمورد")
        verbose_name_plural = _("الدفعات المقدمة للموردين")
        ordering = ["-payment_date", "-created_at"]

    def __str__(self):
        return f"Supplier Advance #{self.id} - {self.supplier.name} ({self.amount} EGP)"

    @property
    def remaining_amount(self) -> Decimal:
        """المبلغ المتبقي المتاح للتخصيص من هذه الدفعة"""
        return max(Decimal("0.00"), self.amount - self.allocated_amount)
