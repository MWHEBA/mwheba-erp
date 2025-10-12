"""
نماذج حركات المخزون والتسويات
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.core.validators import MinValueValidator
from django.utils import timezone
from decimal import Decimal


class InventoryMovement(models.Model):
    """
    نموذج حركات المخزون المتقدم
    يسجل جميع حركات المخزون مع تفاصيل شاملة
    """

    MOVEMENT_TYPES = (
        ("in", _("وارد")),
        ("out", _("صادر")),
        ("transfer_out", _("تحويل صادر")),
        ("transfer_in", _("تحويل وارد")),
        ("adjustment_in", _("تسوية زيادة")),
        ("adjustment_out", _("تسوية نقص")),
        ("return_in", _("مرتجع وارد")),
        ("return_out", _("مرتجع صادر")),
        ("damaged", _("تالف")),
        ("expired", _("منتهي الصلاحية")),
        ("lost", _("مفقود")),
        ("found", _("موجود")),
    )

    DOCUMENT_TYPES = (
        ("purchase", _("شراء")),
        ("sale", _("بيع")),
        ("transfer", _("تحويل")),
        ("adjustment", _("تسوية")),
        ("return", _("مرتجع")),
        ("damage", _("إتلاف")),
        ("opening", _("رصيد افتتاحي")),
        ("manual", _("يدوي")),
    )

    movement_number = models.CharField(
        _("رقم الحركة"), max_length=50, unique=True, blank=True
    )
    product = models.ForeignKey(
        "product.Product",
        on_delete=models.PROTECT,
        related_name="inventory_movements",
        verbose_name=_("المنتج"),
    )
    warehouse = models.ForeignKey(
        "product.Warehouse",
        on_delete=models.PROTECT,
        related_name="inventory_movements",
        verbose_name=_("المخزن"),
    )
    movement_type = models.CharField(
        _("نوع الحركة"), max_length=20, choices=MOVEMENT_TYPES
    )
    document_type = models.CharField(
        _("نوع المستند"), max_length=20, choices=DOCUMENT_TYPES, default="manual"
    )
    document_number = models.CharField(
        _("رقم المستند"), max_length=50, blank=True, null=True
    )
    quantity = models.PositiveIntegerField(_("الكمية"))
    unit_cost = models.DecimalField(
        _("تكلفة الوحدة"),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    total_cost = models.DecimalField(
        _("التكلفة الإجمالية"),
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    quantity_before = models.PositiveIntegerField(_("الكمية قبل الحركة"), default=0)
    quantity_after = models.PositiveIntegerField(_("الكمية بعد الحركة"), default=0)
    average_cost_before = models.DecimalField(
        _("متوسط التكلفة قبل"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    average_cost_after = models.DecimalField(
        _("متوسط التكلفة بعد"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    reference_movement = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="related_movements",
        verbose_name=_("الحركة المرجعية"),
        help_text=_("الحركة المرتبطة (مثل التحويل المقابل)"),
    )
    batch_number = models.CharField(
        _("رقم الدفعة"), max_length=50, blank=True, null=True
    )
    expiry_date = models.DateField(_("تاريخ انتهاء الصلاحية"), null=True, blank=True)
    location_code = models.CharField(
        _("كود الموقع"), max_length=50, blank=True, null=True
    )
    notes = models.TextField(_("ملاحظات"), blank=True, null=True)
    movement_date = models.DateTimeField(_("تاريخ الحركة"), default=timezone.now)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_("أنشئ بواسطة"),
        related_name="inventory_movements_created",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("وافق عليه"),
        related_name="inventory_movements_approved",
    )
    approval_date = models.DateTimeField(_("تاريخ الموافقة"), null=True, blank=True)
    is_approved = models.BooleanField(_("معتمد"), default=False)
    is_reversed = models.BooleanField(_("معكوس"), default=False)
    reversal_movement = models.OneToOneField(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="original_movement",
        verbose_name=_("حركة العكس"),
    )

    # ربط بالقيد المحاسبي
    journal_entry = models.ForeignKey(
        "financial.JournalEntry",
        on_delete=models.SET_NULL,
        verbose_name=_("القيد المحاسبي"),
        related_name="inventory_movements",
        blank=True,
        null=True,
    )

    class Meta:
        verbose_name = _("حركة مخزون")
        verbose_name_plural = _("حركات المخزون")
        ordering = ["-movement_date", "-created_at"]
        indexes = [
            models.Index(fields=["product", "warehouse"]),
            models.Index(fields=["movement_date", "movement_type"]),
            models.Index(fields=["document_type", "document_number"]),
            models.Index(fields=["is_approved", "is_reversed"]),
        ]

    def __str__(self):
        return f"{self.movement_number} - {self.product.name} ({self.quantity})"

    def save(self, *args, **kwargs):
        if not self.movement_number:
            # توليد رقم الحركة تلقائياً
            from ..models import SerialNumber

            serial = SerialNumber.objects.get_or_create(
                document_type="inventory_movement",
                year=timezone.now().year,
                defaults={"prefix": "INV"},
            )[0]
            next_number = serial.get_next_number()
            self.movement_number = f"{serial.prefix}{next_number:06d}"

        # حساب التكلفة الإجمالية
        self.total_cost = self.quantity * self.unit_cost

        super().save(*args, **kwargs)

    def can_approve(self):
        """هل يمكن اعتماد الحركة؟"""
        return not self.is_approved and not self.is_reversed

    def can_reverse(self):
        """هل يمكن عكس الحركة؟"""
        return self.is_approved and not self.is_reversed

    def approve(self, user):
        """اعتماد الحركة وتطبيقها على المخزون"""
        if not self.can_approve():
            return False

        try:
            from .warehouse import ProductStock

            # الحصول على أو إنشاء سجل المخزون
            stock, created = ProductStock.objects.get_or_create(
                product=self.product,
                warehouse=self.warehouse,
                defaults={
                    "quantity": 0,
                    "average_cost": self.product.cost_price or Decimal("0.00"),
                },
            )

            # حفظ الحالة قبل التغيير
            self.quantity_before = stock.quantity
            self.average_cost_before = stock.average_cost

            # تطبيق الحركة حسب النوع
            if self.movement_type in [
                "in",
                "transfer_in",
                "adjustment_in",
                "return_in",
                "found",
            ]:
                # حركة وارد - زيادة المخزون
                if self.movement_type == "in":
                    # تحديث متوسط التكلفة للوارد الجديد
                    stock.update_average_cost(self.quantity, self.unit_cost)
                else:
                    stock.quantity += self.quantity
                    stock.last_movement_date = timezone.now()
                    stock.save()

            elif self.movement_type in [
                "out",
                "transfer_out",
                "adjustment_out",
                "return_out",
                "damaged",
                "expired",
                "lost",
            ]:
                # حركة صادر - تقليل المخزون
                if stock.quantity >= self.quantity:
                    stock.quantity -= self.quantity
                    stock.last_movement_date = timezone.now()
                    stock.save()
                else:
                    return False  # لا توجد كمية كافية

            # حفظ الحالة بعد التغيير
            stock.refresh_from_db()
            self.quantity_after = stock.quantity
            self.average_cost_after = stock.average_cost

            # اعتماد الحركة
            self.is_approved = True
            self.approved_by = user
            self.approval_date = timezone.now()
            self.save()

            return True

        except Exception as e:
            return False

    def reverse(self, user, reason=None):
        """عكس الحركة"""
        if not self.can_reverse():
            return False

        try:
            # إنشاء حركة عكسية
            reverse_type_map = {
                "in": "out",
                "out": "in",
                "transfer_in": "transfer_out",
                "transfer_out": "transfer_in",
                "adjustment_in": "adjustment_out",
                "adjustment_out": "adjustment_in",
                "return_in": "return_out",
                "return_out": "return_in",
                "found": "lost",
                "lost": "found",
                "damaged": "in",  # عكس التالف = استرداد
                "expired": "in",  # عكس المنتهي الصلاحية = استرداد
            }

            reverse_movement = InventoryMovement.objects.create(
                product=self.product,
                warehouse=self.warehouse,
                movement_type=reverse_type_map.get(self.movement_type, "adjustment_in"),
                document_type="manual",
                document_number=f"REV-{self.movement_number}",
                quantity=self.quantity,
                unit_cost=self.unit_cost,
                reference_movement=self,
                notes=f"عكس الحركة {self.movement_number}"
                + (f" - {reason}" if reason else ""),
                movement_date=timezone.now(),
                created_by=user,
            )

            # اعتماد الحركة العكسية
            if reverse_movement.approve(user):
                # تحديث الحركة الأصلية
                self.is_reversed = True
                self.reversal_movement = reverse_movement
                self.save()
                return True

        except Exception as e:
            pass

        return False


class InventoryAdjustment(models.Model):
    """
    نموذج تسوية المخزون
    لتسوية الفروقات بين المخزون الفعلي والنظري
    """

    ADJUSTMENT_STATUS = (
        ("draft", _("مسودة")),
        ("pending", _("معلق")),
        ("approved", _("معتمد")),
        ("cancelled", _("ملغي")),
    )

    ADJUSTMENT_TYPES = (
        ("physical_count", _("جرد فعلي")),
        ("damage", _("تلف")),
        ("expiry", _("انتهاء صلاحية")),
        ("theft", _("سرقة")),
        ("loss", _("فقدان")),
        ("found", _("عثور")),
        ("correction", _("تصحيح")),
        ("other", _("أخرى")),
    )

    adjustment_number = models.CharField(
        _("رقم التسوية"), max_length=50, unique=True, blank=True
    )
    warehouse = models.ForeignKey(
        "product.Warehouse", on_delete=models.PROTECT, verbose_name=_("المخزن")
    )
    adjustment_type = models.CharField(
        _("نوع التسوية"),
        max_length=20,
        choices=ADJUSTMENT_TYPES,
        default="physical_count",
    )
    adjustment_date = models.DateField(_("تاريخ التسوية"), default=timezone.now)
    status = models.CharField(
        _("الحالة"), max_length=20, choices=ADJUSTMENT_STATUS, default="draft"
    )
    reason = models.TextField(_("سبب التسوية"))
    notes = models.TextField(_("ملاحظات"), blank=True, null=True)
    total_items = models.PositiveIntegerField(_("إجمالي الأصناف"), default=0)
    total_quantity_difference = models.IntegerField(_("إجمالي فرق الكمية"), default=0)
    total_value_difference = models.DecimalField(
        _("إجمالي فرق القيمة"), max_digits=15, decimal_places=2, default=Decimal("0.00")
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="adjustments_created",
        verbose_name=_("أنشئ بواسطة"),
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adjustments_approved",
        verbose_name=_("وافق عليه"),
    )
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    approval_date = models.DateTimeField(_("تاريخ الموافقة"), null=True, blank=True)

    class Meta:
        verbose_name = _("تسوية مخزون")
        verbose_name_plural = _("تسويات المخزون")
        ordering = ["-adjustment_date", "-created_at"]
        indexes = [
            models.Index(fields=["warehouse", "adjustment_date"]),
            models.Index(fields=["status", "adjustment_type"]),
        ]

    def __str__(self):
        return f"{self.adjustment_number} - {self.warehouse.name}"

    def save(self, *args, **kwargs):
        if not self.adjustment_number:
            # توليد رقم التسوية تلقائياً
            from ..models import SerialNumber

            serial = SerialNumber.objects.get_or_create(
                document_type="inventory_adjustment",
                year=timezone.now().year,
                defaults={"prefix": "ADJ"},
            )[0]
            next_number = serial.get_next_number()
            self.adjustment_number = f"{serial.prefix}{next_number:04d}"

        super().save(*args, **kwargs)

    def can_approve(self):
        """هل يمكن اعتماد التسوية؟"""
        return self.status in ["draft", "pending"] and self.adjustment_items.exists()

    def approve(self, user):
        """اعتماد التسوية وتطبيق التغييرات"""
        if not self.can_approve():
            return False

        try:
            # تطبيق جميع بنود التسوية
            for item in self.adjustment_items.all():
                if not item.apply_adjustment():
                    return False

            # تحديث إجماليات التسوية
            self.calculate_totals()

            # اعتماد التسوية
            self.status = "approved"
            self.approved_by = user
            self.approval_date = timezone.now()
            self.save()

            return True

        except Exception as e:
            return False

    def calculate_totals(self):
        """حساب الإجماليات"""
        items = self.adjustment_items.all()
        self.total_items = items.count()
        self.total_quantity_difference = sum(item.quantity_difference for item in items)
        self.total_value_difference = sum(item.value_difference for item in items)
        self.save()


class InventoryAdjustmentItem(models.Model):
    """
    بند تسوية المخزون
    """

    adjustment = models.ForeignKey(
        InventoryAdjustment,
        on_delete=models.CASCADE,
        related_name="adjustment_items",
        verbose_name=_("التسوية"),
    )
    product = models.ForeignKey(
        "product.Product", on_delete=models.PROTECT, verbose_name=_("المنتج")
    )
    system_quantity = models.PositiveIntegerField(
        _("الكمية النظرية"), help_text=_("الكمية حسب النظام")
    )
    actual_quantity = models.PositiveIntegerField(
        _("الكمية الفعلية"), help_text=_("الكمية المعدودة فعلياً")
    )
    quantity_difference = models.IntegerField(
        _("فرق الكمية"), help_text=_("الفرق بين الفعلي والنظري")
    )
    unit_cost = models.DecimalField(_("تكلفة الوحدة"), max_digits=12, decimal_places=2)
    value_difference = models.DecimalField(
        _("فرق القيمة"), max_digits=15, decimal_places=2
    )
    reason = models.CharField(_("السبب"), max_length=100, blank=True, null=True)
    notes = models.TextField(_("ملاحظات"), blank=True, null=True)
    is_applied = models.BooleanField(_("مطبق"), default=False)

    class Meta:
        verbose_name = _("بند تسوية مخزون")
        verbose_name_plural = _("بنود تسوية المخزون")
        unique_together = ("adjustment", "product")

    def __str__(self):
        return f"{self.adjustment.adjustment_number} - {self.product.name}"

    def save(self, *args, **kwargs):
        # حساب الفرق
        self.quantity_difference = self.actual_quantity - self.system_quantity
        self.value_difference = self.quantity_difference * self.unit_cost
        super().save(*args, **kwargs)

    def apply_adjustment(self):
        """تطبيق التسوية على المخزون"""
        if self.is_applied or self.quantity_difference == 0:
            return True

        try:
            # إنشاء حركة مخزون للتسوية
            movement_type = (
                "adjustment_in" if self.quantity_difference > 0 else "adjustment_out"
            )

            movement = InventoryMovement.objects.create(
                product=self.product,
                warehouse=self.adjustment.warehouse,
                movement_type=movement_type,
                document_type="adjustment",
                document_number=self.adjustment.adjustment_number,
                quantity=abs(self.quantity_difference),
                unit_cost=self.unit_cost,
                notes=f"تسوية مخزون - {self.reason or self.adjustment.reason}",
                movement_date=self.adjustment.adjustment_date,
                created_by=self.adjustment.created_by,
            )

            # اعتماد الحركة
            if movement.approve(self.adjustment.created_by):
                self.is_applied = True
                self.save()
                return True

        except Exception as e:
            pass

        return False
