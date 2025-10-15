"""
نظام حجز المخزون للطلبات المعلقة
يسمح بحجز كميات من المنتجات لطلبات معينة
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from django.conf import settings
from django.utils import timezone
from decimal import Decimal
import uuid


class StockReservation(models.Model):
    """
    نموذج حجز المخزون
    يحجز كمية معينة من منتج في مخزن لطلب معين
    """

    RESERVATION_STATUS = (
        ("active", _("نشط")),
        ("fulfilled", _("مُنفذ")),
        ("cancelled", _("ملغي")),
        ("expired", _("منتهي الصلاحية")),
    )

    RESERVATION_TYPE = (
        ("sale_order", _("طلب مبيعات")),
        ("purchase_order", _("طلب شراء")),
        ("transfer_order", _("طلب تحويل")),
        ("manual", _("حجز يدوي")),
    )

    # معرف فريد للحجز
    reservation_id = models.UUIDField(
        _("معرف الحجز"), default=uuid.uuid4, unique=True, editable=False
    )

    # المنتج والمخزن
    product = models.ForeignKey(
        "product.Product",
        on_delete=models.CASCADE,
        related_name="reservations",
        verbose_name=_("المنتج"),
    )
    warehouse = models.ForeignKey(
        "product.Warehouse",
        on_delete=models.CASCADE,
        related_name="reservations",
        verbose_name=_("المخزن"),
    )

    # تفاصيل الحجز
    quantity_reserved = models.PositiveIntegerField(
        _("الكمية المحجوزة"), validators=[MinValueValidator(1)]
    )
    quantity_fulfilled = models.PositiveIntegerField(_("الكمية المُنفذة"), default=0)

    # نوع وحالة الحجز
    reservation_type = models.CharField(
        _("نوع الحجز"), max_length=20, choices=RESERVATION_TYPE, default="manual"
    )
    status = models.CharField(
        _("حالة الحجز"), max_length=20, choices=RESERVATION_STATUS, default="active"
    )

    # ربط بالطلبات
    sale_order_id = models.PositiveIntegerField(
        _("رقم طلب المبيعات"), null=True, blank=True
    )
    purchase_order_id = models.PositiveIntegerField(
        _("رقم طلب الشراء"), null=True, blank=True
    )
    reference_number = models.CharField(
        _("رقم المرجع"), max_length=100, blank=True, null=True
    )

    # تواريخ مهمة
    reserved_at = models.DateTimeField(_("تاريخ الحجز"), auto_now_add=True)
    expires_at = models.DateTimeField(
        _("تاريخ انتهاء الحجز"),
        null=True,
        blank=True,
        help_text=_("الحجز سينتهي تلقائياً في هذا التاريخ"),
    )
    fulfilled_at = models.DateTimeField(_("تاريخ التنفيذ"), null=True, blank=True)

    # معلومات إضافية
    notes = models.TextField(_("ملاحظات"), blank=True, null=True)
    priority = models.PositiveIntegerField(
        _("الأولوية"), default=5, help_text=_("1 = أولوية عالية، 10 = أولوية منخفضة")
    )

    # تتبع المستخدمين
    reserved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="stock_reservations_created",
        verbose_name=_("محجوز بواسطة"),
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_reservations_updated",
        verbose_name=_("آخر تحديث بواسطة"),
    )
    updated_at = models.DateTimeField(_("تاريخ آخر تحديث"), auto_now=True)

    class Meta:
        verbose_name = _("حجز مخزون")
        verbose_name_plural = _("حجوزات المخزون")
        ordering = ["-reserved_at"]
        indexes = [
            models.Index(fields=["product", "warehouse", "status"]),
            models.Index(fields=["status", "expires_at"]),
            models.Index(fields=["reservation_type", "status"]),
        ]

    def __str__(self):
        return f"حجز {self.product.name} - {self.quantity_reserved} - {self.get_status_display()}"

    @property
    def quantity_remaining(self):
        """الكمية المتبقية للتنفيذ"""
        return self.quantity_reserved - self.quantity_fulfilled

    @property
    def is_expired(self):
        """هل انتهت صلاحية الحجز؟"""
        if self.expires_at and timezone.now() > self.expires_at:
            return True
        return False

    @property
    def is_fully_fulfilled(self):
        """هل تم تنفيذ الحجز بالكامل؟"""
        return self.quantity_fulfilled >= self.quantity_reserved

    def fulfill_quantity(self, quantity, user=None):
        """
        تنفيذ كمية من الحجز
        """
        if quantity <= 0:
            raise ValueError("الكمية يجب أن تكون أكبر من صفر")

        if quantity > self.quantity_remaining:
            raise ValueError(
                f"الكمية المطلوبة ({quantity}) أكبر من المتبقية ({self.quantity_remaining})"
            )

        self.quantity_fulfilled += quantity

        if user:
            self.updated_by = user

        # تحديث الحالة إذا تم التنفيذ بالكامل
        if self.is_fully_fulfilled:
            self.status = "fulfilled"
            self.fulfilled_at = timezone.now()

        self.save()

        # تحديث المخزون المحجوز
        try:
            from ..models.warehouse import ProductStock

            stock = ProductStock.objects.get(
                product=self.product, warehouse=self.warehouse
            )
            stock.reserved_quantity = max(0, stock.reserved_quantity - quantity)
            stock.save()
        except ProductStock.DoesNotExist:
            pass

        # إنشاء سجل تنفيذ
        ReservationFulfillment.objects.create(
            reservation=self,
            quantity_fulfilled=quantity,
            fulfilled_by=user,
            notes=f"تنفيذ {quantity} من الحجز",
        )

    def cancel_reservation(self, reason=None, user=None):
        """
        إلغاء الحجز
        """
        if self.status == "cancelled":
            raise ValueError("الحجز ملغي مسبقاً")

        self.status = "cancelled"
        if user:
            self.updated_by = user

        if reason:
            self.notes = f"{self.notes or ''}\nسبب الإلغاء: {reason}"

        self.save()

        # إنشاء سجل إلغاء
        ReservationFulfillment.objects.create(
            reservation=self,
            quantity_fulfilled=0,
            fulfilled_by=user,
            notes=f"إلغاء الحجز - {reason or 'بدون سبب محدد'}",
        )

    def extend_expiry(self, new_expiry_date, user=None):
        """
        تمديد تاريخ انتهاء الحجز
        """
        old_expiry = self.expires_at
        self.expires_at = new_expiry_date

        if user:
            self.updated_by = user

        self.save()

        # إنشاء سجل تمديد
        ReservationFulfillment.objects.create(
            reservation=self,
            quantity_fulfilled=0,
            fulfilled_by=user,
            notes=f"تمديد الحجز من {old_expiry} إلى {new_expiry_date}",
        )


class ReservationFulfillment(models.Model):
    """
    سجل تنفيذ الحجوزات
    يتتبع جميع العمليات على الحجز
    """

    reservation = models.ForeignKey(
        StockReservation,
        on_delete=models.CASCADE,
        related_name="fulfillments",
        verbose_name=_("الحجز"),
    )

    quantity_fulfilled = models.PositiveIntegerField(_("الكمية المُنفذة"), default=0)

    fulfilled_at = models.DateTimeField(_("تاريخ التنفيذ"), auto_now_add=True)

    fulfilled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("نُفذ بواسطة"),
    )

    notes = models.TextField(_("ملاحظات"), blank=True, null=True)

    # ربط بحركة المخزون إذا وجدت
    inventory_movement = models.ForeignKey(
        "product.InventoryMovement",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("حركة المخزون المرتبطة"),
    )

    class Meta:
        verbose_name = _("سجل تنفيذ الحجز")
        verbose_name_plural = _("سجلات تنفيذ الحجوزات")
        ordering = ["-fulfilled_at"]

    def __str__(self):
        return f"تنفيذ {self.quantity_fulfilled} من حجز {self.reservation.product.name}"


class ReservationRule(models.Model):
    """
    قواعد الحجز التلقائي
    تحدد متى وكيف يتم إنشاء حجوزات تلقائية
    """

    RULE_TYPE = (
        ("auto_reserve_on_order", _("حجز تلقائي عند الطلب")),
        ("auto_expire_after_days", _("انتهاء صلاحية تلقائي")),
        ("priority_based_allocation", _("تخصيص حسب الأولوية")),
    )

    name = models.CharField(_("اسم القاعدة"), max_length=100)

    rule_type = models.CharField(_("نوع القاعدة"), max_length=30, choices=RULE_TYPE)

    # فلاتر القاعدة
    product_category = models.ForeignKey(
        "product.Category",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_("فئة المنتج"),
    )

    warehouse = models.ForeignKey(
        "product.Warehouse",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_("المخزن"),
    )

    # إعدادات القاعدة
    auto_reserve_enabled = models.BooleanField(_("تفعيل الحجز التلقائي"), default=False)

    default_expiry_days = models.PositiveIntegerField(
        _("أيام انتهاء الصلاحية الافتراضية"),
        default=7,
        help_text=_("عدد الأيام قبل انتهاء صلاحية الحجز"),
    )

    max_reservation_percentage = models.DecimalField(
        _("أقصى نسبة حجز من المخزون"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("80.00"),
        help_text=_("أقصى نسبة يمكن حجزها من المخزون المتاح"),
    )

    priority_threshold = models.PositiveIntegerField(
        _("عتبة الأولوية"),
        default=5,
        help_text=_("الحجوزات بأولوية أقل من هذا الرقم لها أولوية عالية"),
    )

    is_active = models.BooleanField(_("نشط"), default=True)

    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_("أنشئ بواسطة"),
    )

    class Meta:
        verbose_name = _("قاعدة حجز")
        verbose_name_plural = _("قواعد الحجز")
        ordering = ["name"]

    def __str__(self):
        return self.name
