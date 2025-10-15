"""
نماذج تتبع حركات المخزون
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from django.utils import timezone
from decimal import Decimal

User = get_user_model()


class InventoryMovement(models.Model):
    """
    نموذج حركات المخزون
    """

    MOVEMENT_TYPES = (
        ("in", _("دخول")),
        ("out", _("خروج")),
        ("transfer", _("تحويل")),
        ("adjustment", _("تسوية")),
        ("return", _("إرجاع")),
        ("damage", _("تالف")),
        ("expired", _("منتهي الصلاحية")),
    )

    SOURCES = (
        ("purchase", _("فاتورة شراء")),
        ("sale", _("فاتورة بيع")),
        ("manual", _("يدوي")),
        ("transfer", _("تحويل بين المخازن")),
        ("adjustment", _("تسوية جرد")),
        ("return_in", _("إرجاع من عميل")),
        ("return_out", _("إرجاع لمورد")),
        ("damage", _("إتلاف")),
        ("expired", _("انتهاء صلاحية")),
        ("opening_balance", _("رصيد افتتاحي")),
    )

    product = models.ForeignKey(
        "product.Product",
        on_delete=models.CASCADE,
        related_name="movements",
        verbose_name=_("المنتج"),
    )

    warehouse = models.ForeignKey(
        "product.Warehouse",
        on_delete=models.CASCADE,
        related_name="movements",
        verbose_name=_("المخزن"),
        null=True,
        blank=True,
    )

    movement_type = models.CharField(
        _("نوع الحركة"), max_length=20, choices=MOVEMENT_TYPES
    )

    source = models.CharField(
        _("المصدر"), max_length=20, choices=SOURCES, default="manual"
    )

    quantity = models.DecimalField(
        _("الكمية"), max_digits=12, decimal_places=3, validators=[MinValueValidator(0)]
    )

    unit_cost = models.DecimalField(
        _("تكلفة الوحدة"),
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )

    total_cost = models.DecimalField(
        _("إجمالي التكلفة"),
        max_digits=15,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )

    reference_number = models.CharField(
        _("رقم المرجع"),
        max_length=100,
        blank=True,
        null=True,
        help_text=_("رقم الفاتورة أو المرجع المرتبط بالحركة"),
    )

    notes = models.TextField(_("ملاحظات"), blank=True, null=True)

    date = models.DateTimeField(_("تاريخ الحركة"), default=timezone.now)

    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="inventory_movements",
        verbose_name=_("أنشئ بواسطة"),
    )

    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    # حقول للربط مع الوثائق الأصلية
    purchase_id = models.PositiveIntegerField(
        _("معرف فاتورة الشراء"), null=True, blank=True
    )

    sale_id = models.PositiveIntegerField(_("معرف فاتورة البيع"), null=True, blank=True)

    # رصيد المنتج بعد الحركة
    balance_after = models.DecimalField(_("الرصيد بعد الحركة"), default=0)

    class Meta:
        app_label = "product"
        verbose_name = _("حركة مخزون")
        verbose_name_plural = _("حركات المخزون")
        ordering = ["-date"]
        indexes = [
            models.Index(fields=["product", "date"]),
            models.Index(fields=["warehouse", "date"]),
            models.Index(fields=["movement_type", "date"]),
            models.Index(fields=["source", "date"]),
            models.Index(fields=["reference_number"]),
        ]

    def __str__(self):
        return f"{self.get_movement_type_display()} - {self.product.name} ({self.quantity})"


class StockSnapshot(models.Model):
    """
    نموذج لقطات المخزون اليومية
    """

    product = models.ForeignKey(
        "product.Product",
        on_delete=models.CASCADE,
        related_name="snapshots",
        verbose_name=_("المنتج"),
    )

    warehouse = models.ForeignKey(
        "product.Warehouse",
        on_delete=models.CASCADE,
        related_name="snapshots",
        verbose_name=_("المخزن"),
    )

    snapshot_date = models.DateField(_("تاريخ اللقطة"), default=timezone.now)

    quantity = models.DecimalField(
        _("الكمية"), max_digits=12, decimal_places=3, default=0
    )

    average_cost = models.DecimalField(
        _("متوسط التكلفة"), max_digits=12, decimal_places=2, default=0
    )

    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        app_label = "product"
        verbose_name = _("لقطة مخزون")
        verbose_name_plural = _("لقطات المخزون")
        unique_together = ["product", "warehouse", "snapshot_date"]
        ordering = ["-snapshot_date", "product__name"]
        indexes = [
            models.Index(fields=["product", "snapshot_date"]),
            models.Index(fields=["warehouse", "snapshot_date"]),
            models.Index(fields=["snapshot_date"]),
        ]

    def __str__(self):
        return (
            f"لقطة {self.product.name} - {self.warehouse.name} ({self.snapshot_date})"
        )


class InventoryAdjustment(models.Model):
    """
    نموذج تعديلات المخزون
    """

    ADJUSTMENT_TYPE_CHOICES = [
        ("increase", _("زيادة")),
        ("decrease", _("نقص")),
        ("correction", _("تصحيح")),
        ("damage", _("تلف")),
        ("theft", _("سرقة")),
        ("expired", _("منتهي الصلاحية")),
        ("other", _("أخرى")),
    ]

    product = models.ForeignKey(
        "product.Product",
        on_delete=models.CASCADE,
        related_name="adjustments",
        verbose_name=_("المنتج"),
    )

    warehouse = models.ForeignKey(
        "product.Warehouse",
        on_delete=models.CASCADE,
        related_name="adjustments",
        verbose_name=_("المخزن"),
    )

    adjustment_type = models.CharField(
        _("نوع التعديل"), max_length=20, choices=ADJUSTMENT_TYPE_CHOICES
    )

    expected_quantity = models.DecimalField(
        _("الكمية المتوقعة"), max_digits=12, decimal_places=3, default=0
    )

    actual_quantity = models.DecimalField(
        _("الكمية الفعلية"), max_digits=12, decimal_places=3, default=0
    )

    difference = models.DecimalField(
        _("الفرق"), max_digits=12, decimal_places=3, default=0
    )

    unit_cost = models.DecimalField(
        _("تكلفة الوحدة"), max_digits=12, decimal_places=2, default=0
    )

    total_cost_impact = models.DecimalField(
        _("تأثير التكلفة الإجمالي"), max_digits=15, decimal_places=2, default=0
    )

    reason = models.TextField(_("السبب"), blank=True, null=True)

    adjustment_date = models.DateTimeField(_("تاريخ التعديل"), default=timezone.now)

    is_approved = models.BooleanField(_("موافق عليه"), default=False)

    approved_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="approved_adjustments",
        verbose_name=_("وافق عليه"),
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="created_adjustments",
        verbose_name=_("أنشئ بواسطة"),
    )

    inventory_movement = models.OneToOneField(
        InventoryMovement,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="adjustment",
        verbose_name=_("حركة المخزون"),
    )

    class Meta:
        app_label = "product"
        verbose_name = _("تعديل مخزون")
        verbose_name_plural = _("تعديلات المخزون")
        ordering = ["-adjustment_date", "-created_at"]
        indexes = [
            models.Index(fields=["product", "adjustment_date"]),
            models.Index(fields=["warehouse", "adjustment_date"]),
            models.Index(fields=["adjustment_type", "adjustment_date"]),
            models.Index(fields=["is_approved", "adjustment_date"]),
        ]

    def __str__(self):
        return f"تسوية {self.product.name} - {self.get_adjustment_type_display()} ({self.difference})"

    def save(self, *args, **kwargs):
        # حساب الفرق
        self.difference = self.actual_quantity - self.expected_quantity

        # حساب تأثير التكلفة
        if self.unit_cost:
            self.total_cost_impact = abs(self.difference) * self.unit_cost

        super().save(*args, **kwargs)
