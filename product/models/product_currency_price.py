# -*- coding: utf-8 -*-
"""
نموذج أسعار المنتجات بالعملات المخصصة الاسترشادية
ProductCurrencyPrice: Indicative List Prices per Currency (FIN-CORE & IAS 21 Compliant)
"""
from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from django.conf import settings


class ProductCurrencyPrice(models.Model):
    """
    نموذج أسعار المنتجات المخصصة والاسترشادية بالعملات الأجنبية
    تستخدم لتحديد سعر بيع وتكلفة مثبت لكل عملة مفعلة بالشركة
    """

    product = models.ForeignKey(
        "Product",
        on_delete=models.CASCADE,
        related_name="currency_prices",
        verbose_name=_("المنتج"),
    )
    currency = models.ForeignKey(
        "financial.Currency",
        on_delete=models.CASCADE,
        related_name="product_prices",
        verbose_name=_("العملة"),
    )
    indicative_selling_price = models.DecimalField(
        _("سعر البيع"),
        max_digits=15,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("سعر البيع المعتمد بالعملة المحددة"),
    )
    indicative_cost_price = models.DecimalField(
        _("سعر التكلفة"),
        max_digits=15,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("سعر التكلفة المعتمد بالعملة المحددة"),
    )
    notes = models.TextField(_("ملاحظات"), blank=True, null=True)

    # تواريخ ومستخدمين للتتبع
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("أنشئ بواسطة"),
        related_name="product_currency_prices_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("عُدل بواسطة"),
        related_name="product_currency_prices_updated",
    )

    class Meta:
        verbose_name = _("سعر المنتج بالعملة")
        verbose_name_plural = _("أسعار المنتجات بالعملات")
        unique_together = ("product", "currency")
        ordering = ["product", "currency__code"]
        indexes = [
            models.Index(fields=["product", "currency"]),
        ]

    def __str__(self):
        return f"{self.product.name} - {self.currency.code}: {self.indicative_selling_price or 0}"
