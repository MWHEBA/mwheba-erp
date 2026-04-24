# -*- coding: utf-8 -*-
"""
نماذج إدارة المخزون
يحتوي على: Warehouse, Stock, StockMovement
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from django.conf import settings
from django.utils import timezone
from decimal import Decimal


class Warehouse(models.Model):
    """
    نموذج المخازن
    """

    name = models.CharField(_("اسم المخزن"), max_length=255)
    code = models.CharField(_("كود المخزن"), max_length=20, unique=True, blank=True)
    location = models.CharField(_("الموقع"), max_length=255, blank=True, null=True)
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        verbose_name=_("المدير"),
        null=True,
        blank=True,
        related_name="managed_warehouses",
    )
    description = models.TextField(_("الوصف"), blank=True, null=True)
    is_active = models.BooleanField(_("نشط"), default=True)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        verbose_name = _("مخزن")
        verbose_name_plural = _("المخازن")
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """Generate automatic warehouse code if not provided"""
        if not self.code:
            # Get the last warehouse
            last_warehouse = Warehouse.objects.order_by('-code').first()

            if last_warehouse and last_warehouse.code:
                try:
                    # Extract number from last code (assuming format WH0001)
                    if last_warehouse.code.startswith('WH'):
                        last_number = int(last_warehouse.code.replace('WH', ''))
                        new_number = last_number + 1
                    else:
                        new_number = 1
                except (ValueError, AttributeError):
                    new_number = 1
            else:
                new_number = 1

            # Generate new code
            self.code = f"WH{new_number:04d}"

        super().save(*args, **kwargs)



class Stock(models.Model):
    """
    نموذج المخزون الموحد - يجمع مزايا النموذجين القديم والجديد
    """
    
    # الحقول الأساسية (من النموذج القديم)
    product = models.ForeignKey(
        "Product",
        on_delete=models.CASCADE,
        related_name="stocks",  # نحتفظ بالاسم القديم للتوافق
        verbose_name=_("المنتج"),
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name="stocks",
        verbose_name=_("المخزن"),
    )
    quantity = models.PositiveIntegerField(_("الكمية المتاحة"), default=0)
    
    # الحقول المحسنة (من ProductStock)
    reserved_quantity = models.PositiveIntegerField(
        _("الكمية المحجوزة"), 
        default=0,
        help_text=_("الكمية المحجوزة للطلبات المعلقة")
    )
    average_cost = models.DecimalField(
        _("متوسط التكلفة"), 
        max_digits=12, 
        decimal_places=2, 
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))]
    )
    last_movement_date = models.DateTimeField(
        _("تاريخ آخر حركة"), 
        null=True, 
        blank=True
    )
    min_stock_level = models.PositiveIntegerField(
        _("الحد الأدنى للمخزون"), 
        default=0,
        help_text=_("الحد الأدنى المطلوب في هذا المخزن")
    )
    max_stock_level = models.PositiveIntegerField(
        _("الحد الأقصى للمخزون"), 
        default=0,
        help_text=_("الحد الأقصى المسموح في هذا المخزن")
    )
    location_code = models.CharField(
        _("كود الموقع"), 
        max_length=50, 
        blank=True, 
        null=True,
        help_text=_("كود موقع المنتج داخل المخزن (مثل: A1-B2)")
    )
    
    # حقول الحوكمة والحماية من التكرار
    last_movement_service = models.CharField(
        _("آخر خدمة حركة"),
        max_length=100,
        default='MovementService',
        help_text=_("آخر خدمة قامت بتحديث هذا المخزون")
    )
    
    # حقول النظام
    is_active = models.BooleanField(_("نشط"), default=True)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        verbose_name=_("أنشئ بواسطة"),
        related_name="stocks_created"
    )
    
    class Meta:
        verbose_name = _("مخزون")
        verbose_name_plural = _("المخزون")
        unique_together = ("product", "warehouse")
        ordering = ["warehouse", "product"]
        indexes = [
            models.Index(fields=["product", "warehouse"]),
            models.Index(fields=["warehouse", "quantity"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return f"{self.product} - {self.warehouse} ({self.available_quantity})"
    
    # الخصائص المحسوبة (من ProductStock)
    @property
    def available_quantity(self):
        """الكمية المتاحة للبيع (الكمية الكلية - المحجوزة)"""
        return max(0, self.quantity - self.reserved_quantity)
    
    @property
    def is_low_stock(self):
        """هل المخزون منخفض؟"""
        return self.quantity <= self.min_stock_level
    
    @property
    def is_out_of_stock(self):
        """هل المخزون نفذ؟"""
        return self.quantity == 0
    
    @property
    def is_overstocked(self):
        """هل المخزون زائد عن الحد الأقصى؟"""
        return self.max_stock_level > 0 and self.quantity > self.max_stock_level
    
    @property
    def stock_status(self):
        """حالة المخزون"""
        if self.is_out_of_stock:
            return "out_of_stock"
        elif self.is_low_stock:
            return "low_stock"
        elif self.is_overstocked:
            return "overstocked"
        else:
            return "normal"
    
    @property
    def stock_value(self):
        """قيمة المخزون (الكمية × متوسط التكلفة)"""
        return self.quantity * self.average_cost
    
    def reserve_quantity(self, quantity):
        """حجز كمية من المخزون"""
        if quantity <= self.available_quantity:
            self.reserved_quantity += quantity
            self.save()
            return True
        return False
    
    def release_quantity(self, quantity):
        """إلغاء حجز كمية من المخزون"""
        if quantity <= self.reserved_quantity:
            self.reserved_quantity -= quantity
            self.save()
            return True
        return False
    
    def update_average_cost(self, new_quantity, new_cost):
        """تحديث متوسط التكلفة عند إضافة مخزون جديد"""
        if new_quantity > 0:
            total_value = (self.quantity * self.average_cost) + (new_quantity * new_cost)
            total_quantity = self.quantity + new_quantity
            self.average_cost = total_value / total_quantity if total_quantity > 0 else new_cost
            self.quantity = total_quantity
            self.last_movement_date = timezone.now()
            self.save()
    
    def save(self, *args, **kwargs):
        """حفظ المخزون مع تحذير الحوكمة"""
        # تحذير تطوير إذا لم يتم تحديث المخزون عبر الخدمة المخولة
        if not getattr(self, '_service_approved', False):
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Stock {self.product} updated outside MovementService - audit will flag this")
        
        super().save(*args, **kwargs)
    
    def mark_as_service_approved(self):
        """
        تمييز المخزون كمعتمد من الخدمة المخولة
        يستخدم لتجنب تحذيرات التطوير
        """
        self._service_approved = True
    
    def validate_governance_rules(self):
        """
        التحقق من قواعد الحوكمة للمخزون
        
        العائد:
            dict: نتائج التحقق
        """
        result = {
            'is_valid': True,
            'warnings': [],
            'errors': []
        }
        
        # التحقق من عدم وجود مخزون سالب
        if self.quantity < 0:
            result['errors'].append(f"مخزون سالب: {self.quantity}")
            result['is_valid'] = False
        
        # التحقق من الخدمة المحدثة
        if not self.last_movement_service:
            result['warnings'].append("الخدمة المحدثة غير محددة")
        
        # التحقق من الكمية المحجوزة
        if self.reserved_quantity > self.quantity:
            result['errors'].append("الكمية المحجوزة أكبر من الكمية المتاحة")
            result['is_valid'] = False
        
        return result


class StockMovement(models.Model):
    """
    نموذج حركة المخزون
    """

    MOVEMENT_TYPES = (
        ("in", _("وارد")),
        ("out", _("صادر")),
        ("transfer", _("تحويل")),
        ("adjustment", _("تسوية")),
        ("return_in", _("مرتجع وارد")),
        ("return_out", _("مرتجع صادر")),
    )

    # أنواع مستندات الحركة
    DOCUMENT_TYPES = (
        ("purchase", _("شراء")),
        ("purchase_return", _("مرتجع مشتريات")),
        ("sale", _("بيع")),
        ("sale_return", _("مرتجع مبيعات")),
        ("transfer", _("تحويل")),
        ("adjustment", _("جرد")),
        ("opening", _("رصيد")),
        ("other", _("أخرى")),
    )

    product = models.ForeignKey(
        "Product",
        on_delete=models.PROTECT,
        related_name="movements",
        verbose_name=_("المنتج"),
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="movements",
        verbose_name=_("المخزن"),
    )
    movement_type = models.CharField(
        _("نوع الحركة"), max_length=20, choices=MOVEMENT_TYPES
    )
    quantity = models.PositiveIntegerField(_("الكمية"))
    unit_cost = models.DecimalField(
        _("تكلفة الوحدة"),
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text=_("تكلفة الوحدة الواحدة للحركة")
    )
    reference_number = models.CharField(
        _("رقم المرجع"), max_length=50, blank=True, null=True
    )
    document_type = models.CharField(
        _("نوع المستند"), max_length=20, choices=DOCUMENT_TYPES, default="other"
    )
    document_number = models.CharField(
        _("رقم المستند"), max_length=50, blank=True, null=True
    )
    notes = models.TextField(_("ملاحظات"), blank=True, null=True)
    timestamp = models.DateTimeField(_("تاريخ الحركة"), auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_("أنشئ بواسطة"),
        related_name="stock_movements_created",
    )
    # للتحويلات
    destination_warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        verbose_name=_("المخزن المستلم"),
        related_name="incoming_movements",
        blank=True,
        null=True,
    )

    # حقول لتتبع كمية المخزون قبل وبعد الحركة
    quantity_before = models.PositiveIntegerField(_("الكمية قبل"), default=0)
    quantity_after = models.PositiveIntegerField(_("الكمية بعد"), default=0)

    # خاصية لتخطي تحديث المخزون (للاستخدام الداخلي)
    _skip_update = False

    number = models.CharField(
        _("رقم الحركة"), max_length=50, unique=True, blank=True, null=True
    )

    # ربط بالقيد المحاسبي
    journal_entry = models.ForeignKey(
        "financial.JournalEntry",
        on_delete=models.SET_NULL,
        verbose_name=_("القيد المحاسبي"),
        related_name="stock_movements",
        blank=True,
        null=True,
    )
    
    # حقول الحوكمة والحماية من التكرار
    idempotency_key = models.CharField(
        _("مفتاح منع التكرار"),
        max_length=255,
        unique=True,
        null=True,
        blank=True,
        help_text=_("مفتاح فريد لضمان عدم تكرار العملية")
    )
    created_by_service = models.CharField(
        _("الخدمة المنشئة"),
        max_length=100,
        default='MovementService',
        help_text=_("الخدمة التي أنشأت هذه الحركة")
    )

    class Meta:
        verbose_name = _("حركة المخزون")
        verbose_name_plural = _("حركات المخزون")
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["product", "warehouse"]),
            models.Index(fields=["movement_type", "timestamp"]),
            models.Index(fields=["document_type", "document_number"]),
            models.Index(fields=["idempotency_key"]),
            models.Index(fields=["created_by_service"]),
        ]

    def __str__(self):
        return f"{self.product} - {self.movement_type} - {self.quantity} - {self.timestamp}"

    @property
    def total_cost(self):
        """حساب التكلفة الإجمالية للحركة"""
        from decimal import Decimal
        return Decimal(str(self.quantity)) * self.unit_cost

    def _create_journal_entry(self):
        """إنشاء قيد محاسبي لحركة المخزون عبر Service"""
        from product.services.stock_accounting_service import StockAccountingService
        
        entry = StockAccountingService.create_stock_movement_entry(
            stock_movement=self,
            user=self.created_by
        )
        
        if entry:
            # ربط القيد بالحركة
            self.journal_entry = entry
            StockMovement.objects.filter(pk=self.pk).update(journal_entry=entry)

    def save(self, *args, **kwargs):
        """
        حفظ حركة المخزون

        ملاحظة: تحديث المخزون يتم عبر Signal في product/signals.py
        هذا يضمن تحديث المخزون فقط بعد حفظ الحركة بنجاح (Django Best Practice)
        """
        # توليد رقم الحركة إذا لم يكن موجوداً
        if not self.number:
            from .system_utils import SerialNumber
            serial = SerialNumber.objects.get_or_create(
                document_type="stock_movement",
                year=timezone.now().year,
                defaults={"prefix": "MOV"},
            )[0]
            next_number = serial.get_next_number()
            self.number = f"{serial.prefix}{next_number:04d}"

        # حفظ الحركة
        is_new = self.pk is None
        
        # تحذير تطوير إذا لم يتم إنشاء الحركة عبر الخدمة المخولة
        if not getattr(self, '_service_approved', False):
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"StockMovement for {self.product} created outside MovementService - audit will flag this")
        
        super().save(*args, **kwargs)

        # إنشاء قيد محاسبي تلقائياً (فقط للحركات الجديدة وبدون قيد)
        # ملاحظة: لا نُنشئ قيود لحركات الشراء والبيع لأن القيود تُنشأ من الفواتير
        excluded_types = ["purchase", "sale", "purchase_return", "sale_return"]
        if (
            is_new
            and not self.journal_entry
            and not getattr(self, "_skip_update", False)
            and self.document_type not in excluded_types
        ):
            self._create_journal_entry()
    
    def set_idempotency_key(self, key):
        """
        تعيين مفتاح منع التكرار
        
        الوسائط:
            key: مفتاح منع التكرار
        """
        self.idempotency_key = key
        self.save(update_fields=['idempotency_key'])
    
    def mark_as_service_approved(self):
        """
        تمييز الحركة كمعتمدة من الخدمة المخولة
        يستخدم لتجنب تحذيرات التطوير
        """
        self._service_approved = True
    
    def validate_governance_rules(self):
        """
        التحقق من قواعد الحوكمة لحركة المخزون
        
        العائد:
            dict: نتائج التحقق
        """
        result = {
            'is_valid': True,
            'warnings': [],
            'errors': []
        }
        
        # التحقق من وجود مفتاح منع التكرار للحركات الحساسة
        if self.movement_type in ['out', 'transfer'] and self.quantity > 100:
            if not self.idempotency_key:
                result['warnings'].append("حركة حساسة بدون مفتاح منع التكرار")
        
        # التحقق من الخدمة المنشئة
        if not self.created_by_service:
            result['warnings'].append("الخدمة المنشئة غير محددة")
        
        # التحقق من صحة الكمية
        if self.quantity <= 0:
            result['errors'].append("كمية الحركة يجب أن تكون موجبة")
            result['is_valid'] = False
        
        return result