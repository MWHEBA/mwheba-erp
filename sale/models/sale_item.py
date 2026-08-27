from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator


class SaleItem(models.Model):
    """
    نموذج بنود فاتورة المبيعات
    """

    sale = models.ForeignKey(
        "sale.Sale",
        on_delete=models.CASCADE,
        verbose_name=_("الفاتورة"),
        related_name="items",
    )
    product = models.ForeignKey(
        "product.Product", on_delete=models.PROTECT, verbose_name=_("المنتج")
    )
    quantity = models.DecimalField(
        _("الكمية"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
    )
    unit_price = models.DecimalField(_("سعر الوحدة"), max_digits=12, decimal_places=2)
    discount = models.DecimalField(
        _("الخصم"), max_digits=12, decimal_places=2, default=0
    )
    cost_center = models.ForeignKey(
        "financial.CostCenter",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("مركز التكلفة"),
        related_name="sale_items",
    )
    price_snapshot = models.JSONField(
        _("لقطة تفاصيل السعر والخصم"),
        default=dict,
        blank=True,
        help_text=_("تفاصيل وحيثيات احتساب السعر وقواعد الخصم المطبقة للتدقيق المالي")
    )
    total = models.DecimalField(_("الإجمالي"), max_digits=12, decimal_places=2)
    tax_rate = models.DecimalField(
        _("نسبة الضريبة"),
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=_("نسبة ضريبة القيمة المضافة للبند")
    )
    tax_amount = models.DecimalField(
        _("مبلغ الضريبة"),
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=_("قيمة الضريبة المحسوبة للبند")
    )
    is_taxable = models.BooleanField(
        _("خاضع للضريبة"),
        default=True,
        help_text=_("هل البند خاضع لضريبة القيمة المضافة")
    )
    table_tax_rate = models.DecimalField(
        _("نسبة ضريبة الجدول"),
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00")
    )
    table_tax_amount = models.DecimalField(
        _("مبلغ ضريبة الجدول"),
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00")
    )

    class Meta:
        verbose_name = _("بند الفاتورة")
        verbose_name_plural = _("بنود الفاتورة")
        indexes = [
            models.Index(fields=["sale", "product"]),
        ]

    def __str__(self):
        return f"{self.product} x {self.quantity}"

    def save(self, *args, **kwargs):
        self.total = (self.quantity * self.unit_price) - self.discount
        super().save(*args, **kwargs)
