from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from product.models.stock_ledger import StockLedgerEntry
from financial.models.journal_entry import JournalEntry


class LandedCostDocument(models.Model):
    """
    نموذج مستند التكاليف الإضافية الشحن والجمارك (Landed Cost Voucher - FIN-INV-001)
    """
    ALLOCATION_METHODS = (
        ("QUANTITY", _("حسب الكمية")),
        ("WEIGHT", _("حسب الوزن")),
        ("VALUE", _("حسب القيمة المالية")),
    )
    STATUS_CHOICES = (
        ("DRAFT", _("مسودة")),
        ("POSTED", _("مرحل وموزع")),
        ("CANCELLED", _("ملغى")),
    )

    voucher_number = models.CharField(_("رقم مستند التكاليف الإضافية"), max_length=50, unique=True)
    shipment_reference = models.CharField(_("مرجع الشحنة/دورة الاستيراد"), max_length=100, blank=True)
    supplier = models.ForeignKey(
        "supplier.Supplier",
        on_delete=models.PROTECT,
        verbose_name=_("المورد/شركة الشحن"),
        null=True,
        blank=True
    )
    allocation_method = models.CharField(_("طريقة التوزيع"), max_length=20, choices=ALLOCATION_METHODS, default="VALUE")
    total_landed_cost = models.DecimalField(_("إجمالي التكاليف الإضافية"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(_("الحالة"), max_length=20, choices=STATUS_CHOICES, default="DRAFT")

    journal_entry = models.ForeignKey(
        JournalEntry,
        on_delete=models.PROTECT,
        verbose_name=_("قيد التسوية المالي المرتبط"),
        null=True,
        blank=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_("أنشئ بواسطة")
    )
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        verbose_name = _("مستند تكاليف إضافية")
        verbose_name_plural = _("مستندات التكاليف الإضافية")
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"LandedCost #{self.voucher_number}: {self.total_landed_cost} EGP ({self.get_status_display()})"


class LandedCostAllocation(models.Model):
    """
    سجل تخصيص التكاليف الإضافية على بنود أستاذ المخزون والشحنات
    مع معالجة فروقات التكلفة للبضائع المباعة سابقاً (COGS Variance)
    """
    landed_cost_doc = models.ForeignKey(
        LandedCostDocument,
        on_delete=models.CASCADE,
        verbose_name=_("مستند التكاليف الإضافية"),
        related_name="allocations"
    )
    stock_ledger_entry = models.ForeignKey(
        StockLedgerEntry,
        on_delete=models.PROTECT,
        verbose_name=_("سطر استلام الشحنة بأستاذ المخزون"),
        related_name="landed_cost_allocations"
    )
    allocated_cost = models.DecimalField(_("التكلفة المخصصة الكلية"), max_digits=15, decimal_places=2)
    allocated_to_asset = models.DecimalField(_("المبلغ المحمل على أصل المخزون المتبقي"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    allocated_to_variance = models.DecimalField(_("المبلغ المحمل على فروقات COGS للبضاعة المباعة"), max_digits=15, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        verbose_name = _("سجل تخصيص تكاليف إضافية")
        verbose_name_plural = _("سجلات تخصيص التكاليف الإضافية")

    def __str__(self):
        return f"LC-Alloc #{self.id}: Doc#{self.landed_cost_doc_id} -> StkLedger#{self.stock_ledger_entry_id} ({self.allocated_cost})"
