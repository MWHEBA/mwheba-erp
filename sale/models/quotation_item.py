from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator


class QuotationItem(models.Model):
    """
    نموذج بنود عرض السعر
    """
    quotation = models.ForeignKey(
        "sale.Quotation",
        on_delete=models.CASCADE,
        verbose_name=_("عرض السعر"),
        related_name="items",
    )
    product = models.ForeignKey(
        "product.Product",
        on_delete=models.PROTECT,
        verbose_name=_("المنتج"),
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
    price_snapshot = models.JSONField(
        _("لقطة تفاصيل السعر والخصم"),
        default=dict,
        blank=True,
        help_text=_("تفاصيل وحيثيات احتساب السعر وقواعد الخصم المطبقة للتدقيق المالي")
    )
    total = models.DecimalField(_("الإجمالي"), max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = _("بند عرض السعر")
        verbose_name_plural = _("بنود عرض السعر")

    def __str__(self):
        return f"{self.product} x {self.quantity}"

    @property
    def discount_percentage(self):
        """احتساب نسبة الخصم المئوية ديناميكياً من قيمة الخصم"""
        from decimal import Decimal
        sub = self.quantity * self.unit_price
        if sub and sub > Decimal("0.00") and self.discount:
            return ((self.discount / sub) * Decimal("100.00")).quantize(Decimal("0.01"))
        return Decimal("0.00")

    def save(self, *args, **kwargs):
        self.total = (self.quantity * self.unit_price) - (self.discount or 0)
        super().save(*args, **kwargs)
