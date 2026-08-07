# -*- coding: utf-8 -*-
"""
نماذج أسعار الموردين
يحتوي على: SupplierProductPrice, PriceHistory
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from django.conf import settings
from django.utils import timezone
from decimal import Decimal


class SupplierProductPrice(models.Model):
    """
    نموذج أسعار المنتجات حسب المورد
    يربط كل منتج بمورد وسعره الحالي
    """

    product = models.ForeignKey(
        "Product",
        on_delete=models.CASCADE,
        related_name="supplier_prices",
        verbose_name=_("المنتج"),
    )
    supplier = models.ForeignKey(
        "supplier.Supplier",
        on_delete=models.CASCADE,
        related_name="product_prices",
        verbose_name=_("المورد"),
    )
    cost_price = models.DecimalField(
        _("سعر التكلفة"),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.1"))],
    )
    is_active = models.BooleanField(_("نشط"), default=True)
    is_default = models.BooleanField(
        _("المورد الافتراضي"),
        default=False,
        help_text=_("هل هذا هو المورد الافتراضي لهذا المنتج؟"),
    )
    last_purchase_date = models.DateField(_("تاريخ آخر شراء"), null=True, blank=True)
    last_purchase_quantity = models.PositiveIntegerField(
        _("كمية آخر شراء"), null=True, blank=True
    )
    notes = models.TextField(_("ملاحظات"), blank=True, null=True)

    # تواريخ التتبع
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_("أنشئ بواسطة"),
        related_name="supplier_prices_created",
    )

    class Meta:
        verbose_name = _("سعر المنتج للمورد")
        verbose_name_plural = _("أسعار المنتجات للموردين")
        unique_together = ("product", "supplier")
        ordering = ["-is_default", "-last_purchase_date", "supplier__name"]
        indexes = [
            models.Index(fields=["product", "supplier"]),
            models.Index(fields=["product", "is_default"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        default_text = " (افتراضي)" if self.is_default else ""
        return f"{self.product.name} - {self.supplier.name} - {self.cost_price}{default_text}"

    def save(self, *args, **kwargs):
        """
        حفظ السعر مع التأكد من وجود مورد افتراضي واحد فقط لكل منتج
        """
        # إذا تم تعيين هذا المورد كافتراضي، إلغاء الافتراضي من الموردين الآخرين
        if self.is_default:
            SupplierProductPrice.objects.filter(
                product=self.product, is_default=True
            ).exclude(pk=self.pk).update(is_default=False)

        # إذا لم يكن هناك مورد افتراضي لهذا المنتج، اجعل هذا افتراضي
        elif (
            not SupplierProductPrice.objects.filter(
                product=self.product, is_default=True
            )
            .exclude(pk=self.pk)
            .exists()
        ):
            self.is_default = True

        super().save(*args, **kwargs)

        # تحديث سعر التكلفة الرئيسي للمنتج إذا كان هذا المورد افتراضي
        if self.is_default and self.product.cost_price != self.cost_price:
            from .product_core import Product
            Product.objects.filter(pk=self.product.pk).update(
                cost_price=self.cost_price
            )

    @property
    def price_difference_from_main(self):
        """
        الفرق بين سعر هذا المورد وسعر التكلفة الرئيسي للمنتج
        """
        if self.product.cost_price:
            return self.cost_price - self.product.cost_price
        return Decimal("0")

    @property
    def price_difference_percentage(self):
        """
        نسبة الفرق بين سعر هذا المورد وسعر التكلفة الرئيسي للمنتج
        """
        if self.product.cost_price and self.product.cost_price > 0:
            return (
                (self.cost_price - self.product.cost_price) / self.product.cost_price
            ) * 100
        return Decimal("0")

    @property
    def days_since_last_purchase(self):
        """
        عدد الأيام منذ آخر شراء من هذا المورد
        """
        if self.last_purchase_date:
            return (timezone.now().date() - self.last_purchase_date).days
        return None


class PriceHistory(models.Model):
    """
    نموذج سجل تاريخ أسعار المنتجات الموحد (الموردين، الكتالوج بالعملات، الفواتير)
    يسجل كل تغيير في السعر والتكلفة مع السبب، العملة، سعر الصرف، والمستند المرجعي
    """

    CHANGE_REASONS = (
        ("purchase", _("شراء جديد")),
        ("manual_update", _("تحديث يدوي")),
        ("supplier_notification", _("إشعار من المورد")),
        ("market_change", _("تغيير السوق")),
        ("bulk_update", _("تحديث جماعي")),
        ("system_sync", _("مزامنة النظام")),
        ("sale", _("بيع")),
    )

    SOURCE_TYPES = (
        ("CATALOG_BASE", _("كتالوج - السعر الأساسي EGP")),
        ("CATALOG_FX", _("كتالوج - سعر عملة أجنبية")),
        ("SUPPLIER_PRICE", _("سعر مورد")),
        ("PURCHASE_INVOICE", _("فاتورة مشتريات")),
        ("SALE_INVOICE", _("فاتورة مبيعات")),
    )

    supplier_product_price = models.ForeignKey(
        SupplierProductPrice,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="price_history",
        verbose_name=_("سعر المنتج للمورد"),
    )
    product = models.ForeignKey(
        "Product",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="price_history",
        verbose_name=_("المنتج"),
    )
    currency = models.ForeignKey(
        "financial.Currency",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="price_histories",
        verbose_name=_("العملة"),
    )
    exchange_rate = models.DecimalField(
        _("سعر الصرف"), max_digits=18, decimal_places=6, null=True, blank=True
    )
    source_type = models.CharField(
        _("مصدر التغيير"), max_length=30, choices=SOURCE_TYPES, default="CATALOG_BASE"
    )
    document_reference = models.CharField(
        _("مرجع المستند"),
        max_length=100,
        null=True,
        blank=True,
        help_text=_("رقم الفاتورة أو المستند المرجعي"),
    )
    old_price = models.DecimalField(
        _("السعر القديم"), max_digits=15, decimal_places=4, null=True, blank=True
    )
    new_price = models.DecimalField(
        _("السعر الجديد"),
        max_digits=15,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0"))],
    )
    change_amount = models.DecimalField(
        _("مقدار التغيير"), max_digits=15, decimal_places=4, null=True, blank=True
    )
    change_percentage = models.DecimalField(
        _("نسبة التغيير"), max_digits=8, decimal_places=4, null=True, blank=True
    )
    change_reason = models.CharField(
        _("سبب التغيير"), max_length=30, choices=CHANGE_REASONS, default="manual_update"
    )
    purchase_reference = models.CharField(
        _("مرجع الشراء القديم"),
        max_length=50,
        null=True,
        blank=True,
        help_text=_("رقم فاتورة الشراء إذا كان التغيير بسبب شراء جديد"),
    )
    notes = models.TextField(_("ملاحظات"), blank=True, null=True)

    # تواريخ التتبع
    change_date = models.DateTimeField(_("تاريخ التغيير"), auto_now_add=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_("غُير بواسطة"),
        related_name="price_changes_made",
    )

    class Meta:
        verbose_name = _("تاريخ تغيير السعر")
        verbose_name_plural = _("تاريخ تغيير الأسعار")
        ordering = ["-change_date"]
        indexes = [
            models.Index(fields=["supplier_product_price", "-change_date"]),
            models.Index(fields=["product", "-change_date"]),
            models.Index(fields=["change_reason"]),
            models.Index(fields=["change_date"]),
            models.Index(fields=["source_type"]),
        ]

    def __str__(self):
        p_name = self.product.name if self.product else (self.supplier_product_price.product.name if self.supplier_product_price else "منتج")
        curr_code = self.currency.code if self.currency else "EGP"
        return f"{p_name} ({curr_code}): {self.old_price or 0} → {self.new_price}"

    def save(self, *args, **kwargs):
        """
        حفظ تاريخ التغيير مع حساب مقدار ونسبة التغيير تلقائياً وتحديد المنتج
        """
        if self.supplier_product_price and not self.product:
            self.product = self.supplier_product_price.product

        if self.old_price is not None and self.new_price is not None:
            self.change_amount = self.new_price - self.old_price
            if self.old_price > 0:
                self.change_percentage = (self.change_amount / self.old_price) * 100
            else:
                self.change_percentage = Decimal("0")

        super().save(*args, **kwargs)

    @property
    def is_price_increase(self):
        return self.change_amount and self.change_amount > 0

    @property
    def is_price_decrease(self):
        return self.change_amount and self.change_amount < 0

    @property
    def change_direction_display(self):
        if self.is_price_increase:
            return _("زيادة")
        elif self.is_price_decrease:
            return _("نقصان")
        return _("بدون تغيير")

        if self.is_price_increase:
            return "زيادة"
        elif self.is_price_decrease:
            return "نقصان"
        else:
            return "بدون تغيير"