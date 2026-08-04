from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.conf import settings


class InventoryReservation(models.Model):
    """
    FIN-SAL-003: Inventory Reservation Model (v2.0 Locked Master Final)
    حجز المخزون غير المباشر (Soft Commitment) لأسطر أمر البيع مع دعم التسليم الجزئي
    """
    STATUS_CHOICES = (
        ("ACTIVE", _("نشط")),
        ("PARTIALLY_FULFILLED", _("مستوفى جزئياً")),
        ("FULFILLED", _("مستوفى بالكامل")),
        ("RELEASED", _("محرر")),
        ("CANCELLED", _("ملغي")),
    )

    sales_order = models.ForeignKey("sale.SalesOrder", on_delete=models.CASCADE, related_name="inventory_reservations", verbose_name=_("أمر البيع"))
    sales_order_line = models.ForeignKey("sale.SalesOrderItem", on_delete=models.CASCADE, related_name="inventory_reservations", verbose_name=_("سطر أمر البيع"))
    product = models.ForeignKey("product.Product", on_delete=models.PROTECT, related_name="inventory_reservations", verbose_name=_("المنتج"))
    warehouse = models.ForeignKey("product.Warehouse", on_delete=models.PROTECT, related_name="inventory_reservations", verbose_name=_("المخزن"))
    quantity = models.DecimalField(_("الكمية المحجوزة الكلية"), max_digits=15, decimal_places=4)
    fulfilled_quantity = models.DecimalField(_("الكمية المستوفاة/المسلمة"), max_digits=15, decimal_places=4, default=Decimal("0.0000"))
    reservation_status = models.CharField(_("حالة الحجز"), max_length=25, choices=STATUS_CHOICES, default="ACTIVE")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("أنشئ بواسطة"))
    created_at = models.DateTimeField(_("تاريخ الحجز"), auto_now_add=True)
    released_at = models.DateTimeField(_("تاريخ الإفراج/الإلغاء"), null=True, blank=True)

    class Meta:
        verbose_name = _("حجز مخزون أمر البيع")
        verbose_name_plural = _("حجوزات مخزون أوامر البيع")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["warehouse", "product", "reservation_status"]),
            models.Index(fields=["sales_order", "reservation_status"]),
            models.Index(fields=["product", "warehouse", "created_at"], name="idx_inv_res_active_sweep", condition=models.Q(reservation_status="ACTIVE")),
        ]

    @property
    def remaining_reserved_quantity(self) -> Decimal:
        if self.reservation_status in ["FULFILLED", "RELEASED", "CANCELLED"]:
            return Decimal("0.0000")
        rem = self.quantity - self.fulfilled_quantity
        return max(Decimal("0.0000"), rem)

    def __str__(self):
        return f"Reservation #{self.id} for SO #{self.sales_order.order_number} - {self.product.name} ({self.quantity} {self.reservation_status})"


class InventoryReservationAudit(models.Model):
    """
    FIN-SAL-003: Immutable Inventory Reservation Audit Log Model
    سجل تدقيق وإثبات التغييرات التاريخية غير القابل للتعديل لحجوزات المخزون
    """
    ACTION_CHOICES = (
        ("CREATED", _("إنشاء حجز")),
        ("UPDATED", _("تعديل حجز")),
        ("PARTIALLY_FULFILLED", _("استيفاء جزئي")),
        ("FULFILLED", _("استيفاء كامل")),
        ("RELEASED", _("إفراج عن حجز")),
        ("CANCELLED", _("إلغاء حجز")),
    )

    reservation = models.ForeignKey(InventoryReservation, on_delete=models.CASCADE, related_name="audit_logs", verbose_name=_("الحجز المرتبط"))
    action = models.CharField(_("نوع الإجراء"), max_length=25, choices=ACTION_CHOICES)
    previous_quantity = models.DecimalField(_("الكمية السابقة"), max_digits=15, decimal_places=4, default=Decimal("0.0000"))
    new_quantity = models.DecimalField(_("الكمية الجديدة"), max_digits=15, decimal_places=4, default=Decimal("0.0000"))
    reason = models.TextField(_("السبب / الملاحظات"), blank=True, null=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("المستخدم"))
    created_at = models.DateTimeField(_("تاريخ الإجراء"), auto_now_add=True)

    class Meta:
        verbose_name = _("تدقيق حجز المخزون")
        verbose_name_plural = _("سجلات تدقيق حجوزات المخزون")
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("FIN-SAL-003 Immutability Guard: InventoryReservationAudit records are strictly INSERT-ONLY and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("FIN-SAL-003 Immutability Guard: InventoryReservationAudit records cannot be deleted.")

    def __str__(self):
        return f"Reservation Audit [{self.action}]: Reservation #{self.reservation.id} ({self.previous_quantity} -> {self.new_quantity})"
