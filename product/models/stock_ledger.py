from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from product.models.product_core import Product, ProductVariant, Unit
from product.models.stock_management import Warehouse
from financial.models.journal_entry import JournalEntry


class StockLedgerEntry(models.Model):
    """
    سجل أستاذ المخزون المحاسبي غير القابل للتعديل (Immutable Inventory Ledger - FIN-INV-001)
    يمثل المعادل المالي لجدول JournalEntryLine للمخزون
    """
    MOVEMENT_TYPES = (
        ("RECEIPT", _("استلام مشتريات/توريد")),
        ("ISSUE", _("صرف مبيعات/تصدير")),
        ("TRANSFER_IN", _("تحويل وارد")),
        ("TRANSFER_OUT", _("تحويل صادر")),
        ("ADJUSTMENT_IN", _("تسوية تسليم/زيادة")),
        ("ADJUSTMENT_OUT", _("تسوية صرف/عجز")),
        ("SCRAP", _("تخريد/إتلاف")),
        ("REVALUATION", _("إعادة تقييم تكلفة")),
    )

    entry_number = models.CharField(_("رقم سطر أستاذ المخزون"), max_length=50, unique=True)
    movement_service_ref = models.CharField(_("مرجع خدمة الحركة"), max_length=100, db_index=True)

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        verbose_name=_("المنتج"),
        related_name="stock_ledger_entries"
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        verbose_name=_("النوع/التباين"),
        null=True,
        blank=True,
        related_name="stock_ledger_entries"
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        verbose_name=_("المخزن"),
        related_name="stock_ledger_entries"
    )
    base_uom = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        verbose_name=_("وحدة القياس الأساسية"),
        null=True,
        blank=True
    )

    movement_type = models.CharField(_("نوع الحركة"), max_length=30, choices=MOVEMENT_TYPES)
    quantity = models.DecimalField(
        _("الكمية بوحدة القياس الأساسية"),
        max_digits=15,
        decimal_places=4,
        help_text=_("موجب للوارد، سالب للمنصرف")
    )
    unit_cost = models.DecimalField(
        _("تكلفة الوحدة بالعملة الوظيفية"),
        max_digits=15,
        decimal_places=4,
        default=Decimal("0.0000")
    )
    total_cost = models.DecimalField(
        _("إجمالي التكلفة"),
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00")
    )

    # Derived/Cache fields ONLY (Source of truth is aggregate sum)
    qty_balance_after = models.DecimalField(_("رصيد الكمية بعد الحركة (كاش)"), max_digits=15, decimal_places=4, default=Decimal("0.0000"))
    val_balance_after = models.DecimalField(_("رصيد التقييم بعد الحركة (كاش)"), max_digits=15, decimal_places=2, default=Decimal("0.00"))

    journal_entry = models.ForeignKey(
        JournalEntry,
        on_delete=models.PROTECT,
        verbose_name=_("قيد اليومية المالي المرتبط"),
        null=True,
        blank=True,
        related_name="stock_ledger_entries"
    )
    created_at = models.DateTimeField(_("تاريخ التسجيل"), auto_now_add=True)

    class Meta:
        verbose_name = _("سطر أستاذ المخزون")
        verbose_name_plural = _("أسطر أستاذ المخزون")
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["product", "warehouse", "created_at"]),
            models.Index(fields=["movement_service_ref"]),
        ]

    def __str__(self):
        return f"StockLedger #{self.entry_number}: {self.product.name} ({self.quantity} @ {self.unit_cost})"
