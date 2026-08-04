from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _

from product.models.product_core import Product
from product.models.stock_management import Warehouse
from product.models.stock_ledger import StockLedgerEntry


class InventoryCostLayer(models.Model):
    """
    نموذج طبقات التكلفة للوارد FIFO (FIN-INV-001 & FIN-INV-004)
    تتتبع التكلفة الأصلية والكمية المتبقية لطبقة الاستلام
    """
    STATUS_CHOICES = (
        ("OPEN", _("مفتوحة")),
        ("DEPLETED", _("مستهلكة بالكامل")),
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        verbose_name=_("المنتج"),
        related_name="cost_layers"
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        verbose_name=_("المستودع"),
        related_name="cost_layers"
    )
    receipt_date = models.DateTimeField(_("تاريخ الاستلام"), db_index=True)

    stock_ledger_entry = models.ForeignKey(
        StockLedgerEntry,
        on_delete=models.PROTECT,
        verbose_name=_("سطر الاستلام بأستاذ المخزون"),
        related_name="cost_layers"
    )

    original_qty = models.DecimalField(_("الكمية الأصلية بالوحدة الأساسية"), max_digits=15, decimal_places=4)
    remaining_qty = models.DecimalField(_("الكمية المتبقية بالوحدة الأساسية"), max_digits=15, decimal_places=4)
    unit_cost = models.DecimalField(_("تكلفة الوحدة بالعملة الوظيفية"), max_digits=15, decimal_places=4)

    status = models.CharField(_("الحالة"), max_length=20, choices=STATUS_CHOICES, default="OPEN", db_index=True)

    class Meta:
        verbose_name = _("طبقة تكلفة مخزون")
        verbose_name_plural = _("طبقات تكلفة المخزون")
        ordering = ["receipt_date", "id"]
        indexes = [
            models.Index(fields=["product", "warehouse", "status", "receipt_date"]),
        ]

    def __str__(self):
        return f"CostLayer #{self.id}: {self.product.name} ({self.remaining_qty}/{self.original_qty} @ {self.unit_cost})"


class InventoryCostConsumption(models.Model):
    """
    نموذج تتبع استهلاك طبقات التكلفة لحركات الصرف وتكلفة البضاعة المباعة (FIN-INV-004)
    يربط سطر الصرف بأستاذ المخزون بطبقة الاستلام FIFO المصروف منها
    """
    consumption_number = models.CharField(_("رقم تتبع الاستهلاك"), max_length=50, unique=True)
    cost_layer = models.ForeignKey(
        InventoryCostLayer,
        on_delete=models.PROTECT,
        verbose_name=_("طبقة التكلفة المصروف منها"),
        related_name="consumptions"
    )
    stock_ledger_entry = models.ForeignKey(
        StockLedgerEntry,
        on_delete=models.PROTECT,
        verbose_name=_("سطر الصرف بأستاذ المخزون"),
        related_name="cost_consumptions"
    )
    consumed_qty = models.DecimalField(_("الكمية المستهلكة"), max_digits=15, decimal_places=4)
    unit_cost = models.DecimalField(_("تكلفة الوحدة المصروفة"), max_digits=15, decimal_places=4)
    total_cost = models.DecimalField(_("إجمالي تكلفة الصرف (COGS)"), max_digits=15, decimal_places=2)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        verbose_name = _("سجل استهلاك تكلفة")
        verbose_name_plural = _("سجلات استهلاك التكلفة")
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"Consumption #{self.consumption_number}: Layer#{self.cost_layer_id} -> StkLedger#{self.stock_ledger_entry_id} ({self.consumed_qty} @ {self.unit_cost})"
