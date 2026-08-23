from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.contrib.auth import get_user_model

from product.models.product_core import Product, Category
from client.models import Customer

User = get_user_model()


class PriceList(models.Model):
    """
    FIN-SAL-004: Enterprise Sales Price List Master Model
    قوائم أسعار المبيعات متعددة العملات والمحوكمة بتاريخ السريان
    """
    STATUS_CHOICES = (
        ("ACTIVE", _("نشطة")),
        ("INACTIVE", _("غير نشطة")),
    )

    name = models.CharField(_("اسم قائمة الأسعار"), max_length=100, unique=True)
    currency = models.CharField(_("العملة"), max_length=3, default="EGP")
    customer_type = models.CharField(_("تصنيف العملاء المستهدف"), max_length=50, blank=True, default="ALL")
    effective_from = models.DateField(_("تاريخ بدء السريان"), default=timezone.now)
    effective_to = models.DateField(_("تاريخ نهاية السريان"), null=True, blank=True)
    status = models.CharField(_("الحالة"), max_length=20, choices=STATUS_CHOICES, default="ACTIVE")
    is_active = models.BooleanField(_("نشط"), default=True)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        verbose_name = _("قائمة أسعار")
        verbose_name_plural = _("قوائم الأسعار")
        ordering = ["name"]
        indexes = [
            models.Index(fields=["is_active", "effective_from", "effective_to"]),
            models.Index(fields=["customer_type", "is_active"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.currency})"


class PriceListItem(models.Model):
    """
    FIN-SAL-004: Price List Item Model
    سعر المنتج في قائمة أسعار معينة
    """
    price_list = models.ForeignKey(PriceList, on_delete=models.CASCADE, related_name="items", verbose_name=_("قائمة الأسعار"))
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="price_list_items", verbose_name=_("المنتج"))
    unit_price = models.DecimalField(_("سعر الوحدة"), max_digits=15, decimal_places=2)
    min_quantity = models.DecimalField(_("الحد الأدنى للكمية"), max_digits=12, decimal_places=4, default=Decimal("1.0000"))
    effective_date = models.DateField(_("تاريخ السريان"), default=timezone.now)
    is_active = models.BooleanField(_("نشط"), default=True)

    class Meta:
        verbose_name = _("سعر بند في القائمة")
        verbose_name_plural = _("أسعار البنود في القوائم")
        unique_together = ("price_list", "product", "min_quantity")
        indexes = [
            models.Index(fields=["price_list", "product", "is_active", "effective_date"]),
            models.Index(fields=["product", "is_active"]),
        ]

    def __str__(self):
        return f"{self.product.name} @ {self.unit_price} ({self.price_list.name})"


class DiscountRule(models.Model):
    """
    FIN-SAL-004: Customer & Product Category Discount Rules
    قواعد الخصم للعملاء وفئات ومنتجات المبيعات
    """
    RULE_TYPES = (
        ("PERCENTAGE", _("نسبة مئوية")),
        ("FIXED_AMOUNT", _("مبلغ ثابت")),
        ("TIERED_QUANTITY", _("شريحة كمية")),
    )

    SCOPE_CHOICES = (
        ("ITEM", _("خصم تجاري على مستوى البند")),
        ("INVOICE", _("خصم تسوية إجمالي على الفاتورة")),
    )

    AGGREGATION_CHOICES = (
        ("LINE_ONLY", _("على مستوى السطر المنفرد")),
        ("CATEGORY_TOTAL", _("تجميع كميات نفس الفئة في السلة")),
    )

    rule_name = models.CharField(_("اسم قاعدة الخصم"), max_length=100)
    rule_type = models.CharField(_("نوع القاعدة"), max_length=20, choices=RULE_TYPES, default="PERCENTAGE")
    scope = models.CharField(_("نطاق الخصم"), max_length=20, choices=SCOPE_CHOICES, default="ITEM")
    aggregation_type = models.CharField(_("طريقة تجميع الكميات"), max_length=20, choices=AGGREGATION_CHOICES, default="LINE_ONLY")
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, null=True, blank=True, related_name="discount_rules", verbose_name=_("العميل (اختياري)"))
    category = models.ForeignKey(Category, on_delete=models.CASCADE, null=True, blank=True, related_name="discount_rules", verbose_name=_("فئة المنتج (اختياري)"))
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, blank=True, related_name="discount_rules", verbose_name=_("المنتج المحدد (اختياري)"))
    discount_percentage = models.DecimalField(_("نسبة الخصم %"), max_digits=5, decimal_places=2, default=Decimal("0.00"))
    value = models.DecimalField(_("قيمة الخصم الثابتة"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    min_order_amount = models.DecimalField(_("الحد الأدنى لقيمة الطلب"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    priority = models.IntegerField(_("الأولوية"), default=10)
    effective_date = models.DateField(_("تاريخ البدء"), default=timezone.now)
    expiry_date = models.DateField(_("تاريخ الانتهاء"), null=True, blank=True)
    is_active = models.BooleanField(_("نشط"), default=True)

    class Meta:
        verbose_name = _("قاعدة خصم")
        verbose_name_plural = _("قواعد الخصم")
        indexes = [
            models.Index(fields=["customer", "category", "product", "is_active", "effective_date"]),
            models.Index(fields=["product", "is_active"]),
            models.Index(fields=["category", "is_active"]),
            models.Index(fields=["is_active", "priority"]),
        ]

    def __str__(self):
        target = self.product.name if self.product else (self.category.name if self.category else (self.customer.name if self.customer else _("عام لكافة العملاء")))
        return f"{self.rule_name} [{target}] ({self.discount_percentage}%)"


class PricingAuditLog(models.Model):
    """
    FIN-SAL-004: Pricing Audit Log
    سجل تدقيق وتتبع التغييرات التاريخية لأسعار المنتجات
    """
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="pricing_audit_logs", verbose_name=_("المنتج"))
    price_list = models.ForeignKey(PriceList, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("قائمة الأسعار"))
    old_price = models.DecimalField(_("السعر القديم"), max_digits=15, decimal_places=2)
    new_price = models.DecimalField(_("السعر الجديد"), max_digits=15, decimal_places=2)
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("تغيير بواسطة"))
    reason = models.TextField(_("سبب التغيير"), blank=True)
    timestamp = models.DateTimeField(_("الوقت والتاريخ"), auto_now_add=True)

    class Meta:
        verbose_name = _("سجل تدقيق الأسعار")
        verbose_name_plural = _("سجلات تدقيق الأسعار")
        ordering = ["-timestamp"]

    def __str__(self):
        return f"Pricing Change: {self.product.name} ({self.old_price} -> {self.new_price})"
