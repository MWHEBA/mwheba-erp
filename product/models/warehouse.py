"""
نماذج المخازن المحسنة
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.core.validators import MinValueValidator
from django.utils import timezone
from decimal import Decimal

# استيراد النموذج الموحد
from .stock_management import Stock


class StockTransfer(models.Model):
    """
    نموذج تحويل المخزون بين المخازن
    """

    TRANSFER_STATUS = (
        ("draft", _("مسودة")),
        ("pending", _("معلق")),
        ("in_transit", _("في الطريق")),
        ("completed", _("مكتمل")),
        ("cancelled", _("ملغي")),
    )

    transfer_number = models.CharField(
        _("رقم التحويل"), max_length=50, unique=True, blank=True
    )
    from_warehouse = models.ForeignKey(
        "Warehouse",
        on_delete=models.PROTECT,
        related_name="transfers_out",
        verbose_name=_("من المخزن"),
    )
    to_warehouse = models.ForeignKey(
        "Warehouse",
        on_delete=models.PROTECT,
        related_name="transfers_in",
        verbose_name=_("إلى المخزن"),
    )
    product = models.ForeignKey(
        "Product",
        on_delete=models.PROTECT,
        related_name="transfers",
        verbose_name=_("المنتج"),
    )
    quantity = models.PositiveIntegerField(_("الكمية"))
    transfer_cost = models.DecimalField(
        _("تكلفة التحويل"),
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    status = models.CharField(
        _("الحالة"), max_length=20, choices=TRANSFER_STATUS, default="draft"
    )
    notes = models.TextField(_("ملاحظات"), blank=True, null=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="requested_transfers",
        verbose_name=_("طلب بواسطة"),
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="approved_transfers",
        verbose_name=_("وافق عليه"),
        null=True,
        blank=True,
    )
    shipped_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="shipped_transfers",
        verbose_name=_("شحن بواسطة"),
        null=True,
        blank=True,
    )
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="received_transfers",
        verbose_name=_("استلم بواسطة"),
        null=True,
        blank=True,
    )
    request_date = models.DateTimeField(_("تاريخ الطلب"), auto_now_add=True)
    approval_date = models.DateTimeField(_("تاريخ الموافقة"), null=True, blank=True)
    ship_date = models.DateTimeField(_("تاريخ الشحن"), null=True, blank=True)
    receive_date = models.DateTimeField(_("تاريخ الاستلام"), null=True, blank=True)
    expected_arrival = models.DateTimeField(
        _("تاريخ الوصول المتوقع"), null=True, blank=True
    )

    class Meta:
        verbose_name = _("تحويل مخزون")
        verbose_name_plural = _("تحويلات المخزون")
        ordering = ["-request_date"]
        indexes = [
            models.Index(fields=["from_warehouse", "to_warehouse"]),
            models.Index(fields=["status", "request_date"]),
            models.Index(fields=["product"]),
        ]

    def __str__(self):
        return f"{self.transfer_number} - {self.product.name} ({self.quantity})"

    def save(self, *args, **kwargs):
        if not self.transfer_number:
            # توليد رقم التحويل تلقائياً
            from .system_utils import SerialNumber

            serial = SerialNumber.objects.get_or_create(
                document_type="stock_transfer",
                year=timezone.now().year,
                defaults={"prefix": "TRF"},
            )[0]
            next_number = serial.get_next_number()
            self.transfer_number = f"{serial.prefix}{next_number:04d}"

        super().save(*args, **kwargs)

    def can_approve(self):
        """هل يمكن الموافقة على التحويل؟"""
        return self.status == "draft"

    def can_ship(self):
        """هل يمكن شحن التحويل؟"""
        return self.status == "pending"

    def can_receive(self):
        """هل يمكن استلام التحويل؟"""
        return self.status == "in_transit"

    def can_cancel(self):
        """هل يمكن إلغاء التحويل؟"""
        return self.status in ["draft", "pending"]

    def approve(self, user):
        """الموافقة على التحويل"""
        if self.can_approve():
            self.status = "pending"
            self.approved_by = user
            self.approval_date = timezone.now()
            self.save()
            return True
        return False

    def ship(self, user):
        """شحن التحويل"""
        if self.can_ship():
            # التحقق من توفر الكمية في المخزن المرسل
            try:
                from .stock_management import Stock
                stock = Stock.objects.get(
                    product=self.product, warehouse=self.from_warehouse
                )
                if stock.available_quantity >= self.quantity:
                    # حجز الكمية
                    stock.reserve_quantity(self.quantity)
                    self.status = "in_transit"
                    self.shipped_by = user
                    self.ship_date = timezone.now()
                    self.save()
                    return True
            except Stock.DoesNotExist:
                pass
        return False

    def receive(self, user, received_quantity=None):
        """استلام التحويل"""
        if self.can_receive():
            received_qty = received_quantity or self.quantity

            # تحديث المخزون في المخزن المستلم
            from .stock_management import Stock
            to_stock, created = Stock.objects.get_or_create(
                product=self.product,
                warehouse=self.to_warehouse,
                defaults={"quantity": 0, "average_cost": self.product.cost_price},
            )
            to_stock.quantity += received_qty
            to_stock.last_movement_date = timezone.now()
            to_stock.save()

            # تحديث المخزون في المخزن المرسل
            try:
                from .stock_management import Stock
                from_stock = Stock.objects.get(
                    product=self.product, warehouse=self.from_warehouse
                )
                from_stock.quantity -= received_qty
                from_stock.release_quantity(received_qty)
                from_stock.save()
            except Stock.DoesNotExist:
                pass

            self.status = "completed"
            self.received_by = user
            self.receive_date = timezone.now()
            self.save()
            return True
        return False

    def cancel(self, user, reason=None):
        """إلغاء التحويل"""
        if self.can_cancel():
            if self.status == "in_transit":
                # إلغاء حجز الكمية
                try:
                    from .stock_management import Stock
                    stock = Stock.objects.get(
                        product=self.product, warehouse=self.from_warehouse
                    )
                    stock.release_quantity(self.quantity)
                except Stock.DoesNotExist:
                    pass

            self.status = "cancelled"
            if reason:
                self.notes = (
                    f"{self.notes}\nسبب الإلغاء: {reason}"
                    if self.notes
                    else f"سبب الإلغاء: {reason}"
                )
            self.save()
            return True
        return False


class StockSnapshot(models.Model):
    """
    نموذج لقطة المخزون - لحفظ حالة المخزون في وقت معين
    """

    snapshot_date = models.DateTimeField(_("تاريخ اللقطة"), auto_now_add=True)
    warehouse = models.ForeignKey(
        "Warehouse", on_delete=models.CASCADE, verbose_name=_("المخزن")
    )
    product = models.ForeignKey(
        "Product", on_delete=models.CASCADE, verbose_name=_("المنتج")
    )
    quantity = models.PositiveIntegerField(_("الكمية"))
    average_cost = models.DecimalField(
        _("متوسط التكلفة"), max_digits=12, decimal_places=2
    )
    total_value = models.DecimalField(
        _("القيمة الإجمالية"), max_digits=15, decimal_places=2
    )
    snapshot_type = models.CharField(
        _("نوع اللقطة"),
        max_length=20,
        choices=[
            ("daily", _("يومية")),
            ("monthly", _("شهرية")),
            ("yearly", _("سنوية")),
            ("manual", _("يدوية")),
        ],
        default="daily",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("أنشئ بواسطة"),
    )

    class Meta:
        verbose_name = _("لقطة مخزون")
        verbose_name_plural = _("لقطات المخزون")
        ordering = ["-snapshot_date"]
        indexes = [
            models.Index(fields=["snapshot_date", "warehouse"]),
            models.Index(fields=["product", "snapshot_date"]),
        ]

    def __str__(self):
        return f"{self.product.name} - {self.warehouse.name} - {self.snapshot_date.strftime('%Y-%m-%d')}"
