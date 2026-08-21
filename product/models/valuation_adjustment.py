from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from product.models.product_core import Product
from product.models.stock_management import Warehouse
from financial.models.journal_entry import JournalEntry, AccountingPeriod


class InventoryValuationAdjustment(models.Model):
    """
    نموذج حوكمة تسويات وتعديلات تقييم المخزون (FIN-INV-002)
    يتكفل بالحركات التاريخية والإتلاف والتلفيات وإعادة التقييم دون تعديل السجلات التاريخية
    """
    ADJUSTMENT_TYPES = (
        ("COST_REVALUATION", _("إعادة تقييم تكلفة")),
        ("DAMAGE_WRITE_OFF", _("شطب تلفيات/أضرار")),
        ("EXPIRY_SCRAP", _("إتلاف انتهاء صلاحية")),
        ("COUNT_VARIANCE", _("تسوية فروق جرد")),
    )

    adjustment_number = models.CharField(_("رقم مستند التسوية"), max_length=50, unique=True)
    adjustment_type = models.CharField(_("نوع التسوية"), max_length=30, choices=ADJUSTMENT_TYPES)

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        verbose_name=_("المنتج"),
        related_name="valuation_adjustments"
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        verbose_name=_("المخزن"),
        related_name="valuation_adjustments"
    )

    qty_adjusted = models.DecimalField(_("الكمية المعدلة بالوحدة الأساسية"), max_digits=15, decimal_places=4, default=Decimal("0.0000"))
    cost_adjusted = models.DecimalField(_("مبلغ التكلفة المعدل"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    reason = models.TextField(_("سبب التسوية"))

    accounting_period = models.ForeignKey(
        AccountingPeriod,
        on_delete=models.PROTECT,
        verbose_name=_("الفترة المحاسبية المفتوحة"),
        null=True,
        blank=True
    )
    journal_entry = models.ForeignKey(
        JournalEntry,
        on_delete=models.PROTECT,
        verbose_name=_("قيد تسوية تقييم المخزون المالي"),
        null=True,
        blank=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_("أنشئ بواسطة")
    )
    created_at = models.DateTimeField(_("تاريخ التسجيل"), auto_now_add=True)

    class Meta:
        verbose_name = _("تسوية تقييم مخزون")
        verbose_name_plural = _("تسويات تقييم المخزون")
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"ValuationAdj #{self.adjustment_number}: {self.product.name} ({self.adjustment_type} -> {self.cost_adjusted})"
