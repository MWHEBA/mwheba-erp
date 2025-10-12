"""
نظام تتبع تواريخ انتهاء الصلاحية للمنتجات
يدير الدفعات وتواريخ انتهاء الصلاحية مع التنبيهات
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from django.conf import settings
from django.utils import timezone
from decimal import Decimal
from datetime import datetime, timedelta


class ProductBatch(models.Model):
    """
    نموذج دفعات المنتجات
    يتتبع كل دفعة من المنتج مع تاريخ انتهاء الصلاحية
    """
    BATCH_STATUS = (
        ('active', _('نشط')),
        ('expired', _('منتهي الصلاحية')),
        ('recalled', _('مسحوب')),
        ('damaged', _('تالف')),
        ('sold_out', _('نفد')),
    )
    
    # معلومات الدفعة
    batch_number = models.CharField(
        _('رقم الدفعة'),
        max_length=100,
        unique=True
    )
    
    product = models.ForeignKey(
        'product.Product',
        on_delete=models.CASCADE,
        related_name='batches',
        verbose_name=_('المنتج')
    )
    
    warehouse = models.ForeignKey(
        'product.Warehouse',
        on_delete=models.CASCADE,
        related_name='product_batches',
        verbose_name=_('المستودع')
    )
    
    # كميات الدفعة
    initial_quantity = models.PositiveIntegerField(
        _('الكمية الأولية'),
        validators=[MinValueValidator(1)]
    )
    
    current_quantity = models.PositiveIntegerField(
        _('الكمية الحالية'),
        default=0
    )
    
    reserved_quantity = models.PositiveIntegerField(
        _('الكمية المحجوزة'),
        default=0
    )
    
    # تواريخ مهمة
    production_date = models.DateField(
        _('تاريخ الإنتاج'),
        null=True,
        blank=True
    )
    
    expiry_date = models.DateField(
        _('تاريخ انتهاء الصلاحية'),
        null=True,
        blank=True
    )
    
    received_date = models.DateField(
        _('تاريخ الاستلام'),
        default=timezone.now
    )
    
    # معلومات التكلفة
    unit_cost = models.DecimalField(
        _('تكلفة الوحدة'),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    
    total_cost = models.DecimalField(
        _('التكلفة الإجمالية'),
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    
    # حالة الدفعة
    status = models.CharField(
        _('حالة الدفعة'),
        max_length=20,
        choices=BATCH_STATUS,
        default='active'
    )
    
    # معلومات المورد
    supplier = models.ForeignKey(
        'supplier.Supplier',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('المورد')
    )
    
    supplier_batch_number = models.CharField(
        _('رقم دفعة المورد'),
        max_length=100,
        blank=True,
        null=True
    )
    
    # معلومات إضافية
    notes = models.TextField(
        _('ملاحظات'),
        blank=True,
        null=True
    )
    
    location_code = models.CharField(
        _('كود الموقع'),
        max_length=50,
        blank=True,
        null=True,
        help_text=_('موقع الدفعة داخل المستودع')
    )
    
    # تتبع المستخدمين
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='product_batches_created',
        verbose_name=_('أنشئ بواسطة')
    )
    
    created_at = models.DateTimeField(
        _('تاريخ الإنشاء'),
        auto_now_add=True
    )
    
    updated_at = models.DateTimeField(
        _('تاريخ آخر تحديث'),
        auto_now=True
    )
    
    class Meta:
        verbose_name = _('دفعة منتج')
        verbose_name_plural = _('دفعات المنتجات')
        ordering = ['expiry_date', 'batch_number']
        indexes = [
            models.Index(fields=['product', 'warehouse', 'status']),
            models.Index(fields=['expiry_date', 'status']),
            models.Index(fields=['batch_number']),
        ]
        unique_together = ('batch_number', 'product')
    
    def __str__(self):
        return f"{self.product.name} - دفعة {self.batch_number}"
    
    @property
    def available_quantity(self):
        """الكمية المتاحة (الحالية - المحجوزة)"""
        return max(0, self.current_quantity - self.reserved_quantity)
    
    @property
    def days_to_expiry(self):
        """عدد الأيام حتى انتهاء الصلاحية"""
        if not self.expiry_date:
            return None
        
        today = timezone.now().date()
        delta = self.expiry_date - today
        return delta.days
    
    @property
    def is_expired(self):
        """هل انتهت صلاحية الدفعة؟"""
        if not self.expiry_date:
            return False
        
        return timezone.now().date() > self.expiry_date
    
    @property
    def is_near_expiry(self, warning_days=30):
        """هل الدفعة قريبة من انتهاء الصلاحية؟"""
        days_to_expiry = self.days_to_expiry
        if days_to_expiry is None:
            return False
        
        return 0 <= days_to_expiry <= warning_days
    
    @property
    def expiry_status(self):
        """حالة انتهاء الصلاحية"""
        if self.is_expired:
            return 'expired'
        elif self.is_near_expiry(7):
            return 'critical'
        elif self.is_near_expiry(30):
            return 'warning'
        else:
            return 'good'
    
    @property
    def expiry_status_display(self):
        """عرض حالة انتهاء الصلاحية"""
        status_map = {
            'expired': 'منتهي الصلاحية',
            'critical': 'حرج (أقل من أسبوع)',
            'warning': 'تحذير (أقل من شهر)',
            'good': 'جيد'
        }
        return status_map.get(self.expiry_status, 'غير محدد')
    
    def consume_quantity(self, quantity, user=None):
        """
        استهلاك كمية من الدفعة
        """
        if quantity <= 0:
            raise ValueError("الكمية يجب أن تكون أكبر من صفر")
        
        if quantity > self.available_quantity:
            raise ValueError(f"الكمية المطلوبة ({quantity}) أكبر من المتاحة ({self.available_quantity})")
        
        self.current_quantity -= quantity
        
        # تحديث الحالة إذا نفدت الدفعة
        if self.current_quantity <= 0:
            self.status = 'sold_out'
        
        self.save()
        
        # إنشاء سجل الاستهلاك
        BatchConsumption.objects.create(
            batch=self,
            quantity_consumed=quantity,
            consumed_by=user,
            notes=f"استهلاك {quantity} من الدفعة"
        )
    
    def reserve_quantity(self, quantity, reservation_reference=None):
        """
        حجز كمية من الدفعة
        """
        if quantity <= 0:
            raise ValueError("الكمية يجب أن تكون أكبر من صفر")
        
        if quantity > self.available_quantity:
            raise ValueError(f"الكمية المطلوبة ({quantity}) أكبر من المتاحة ({self.available_quantity})")
        
        self.reserved_quantity += quantity
        self.save()
        
        # إنشاء سجل الحجز
        BatchReservation.objects.create(
            batch=self,
            quantity_reserved=quantity,
            reservation_reference=reservation_reference,
            notes=f"حجز {quantity} من الدفعة"
        )
    
    def release_reservation(self, quantity, reservation_reference=None):
        """
        إلغاء حجز كمية من الدفعة
        """
        if quantity <= 0:
            raise ValueError("الكمية يجب أن تكون أكبر من صفر")
        
        if quantity > self.reserved_quantity:
            raise ValueError(f"الكمية المطلوبة ({quantity}) أكبر من المحجوزة ({self.reserved_quantity})")
        
        self.reserved_quantity -= quantity
        self.save()
        
        # إنشاء سجل إلغاء الحجز
        BatchReservation.objects.create(
            batch=self,
            quantity_reserved=-quantity,  # كمية سالبة للإلغاء
            reservation_reference=reservation_reference,
            notes=f"إلغاء حجز {quantity} من الدفعة"
        )


class BatchConsumption(models.Model):
    """
    سجل استهلاك الدفعات
    يتتبع جميع عمليات الاستهلاك من كل دفعة
    """
    batch = models.ForeignKey(
        ProductBatch,
        on_delete=models.CASCADE,
        related_name='consumptions',
        verbose_name=_('الدفعة')
    )
    
    quantity_consumed = models.PositiveIntegerField(
        _('الكمية المستهلكة')
    )
    
    consumed_at = models.DateTimeField(
        _('تاريخ الاستهلاك'),
        auto_now_add=True
    )
    
    consumed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('استُهلك بواسطة')
    )
    
    # ربط بحركة المخزون
    inventory_movement = models.ForeignKey(
        'product.InventoryMovement',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('حركة المخزون المرتبطة')
    )
    
    notes = models.TextField(
        _('ملاحظات'),
        blank=True,
        null=True
    )
    
    class Meta:
        verbose_name = _('سجل استهلاك الدفعة')
        verbose_name_plural = _('سجلات استهلاك الدفعات')
        ordering = ['-consumed_at']
    
    def __str__(self):
        return f"استهلاك {self.quantity_consumed} من {self.batch.batch_number}"


class BatchReservation(models.Model):
    """
    سجل حجوزات الدفعات
    يتتبع جميع عمليات الحجز وإلغاء الحجز
    """
    batch = models.ForeignKey(
        ProductBatch,
        on_delete=models.CASCADE,
        related_name='reservations',
        verbose_name=_('الدفعة')
    )
    
    quantity_reserved = models.IntegerField(
        _('الكمية المحجوزة'),
        help_text=_('كمية موجبة للحجز، سالبة لإلغاء الحجز')
    )
    
    reservation_reference = models.CharField(
        _('مرجع الحجز'),
        max_length=100,
        blank=True,
        null=True
    )
    
    reserved_at = models.DateTimeField(
        _('تاريخ الحجز'),
        auto_now_add=True
    )
    
    notes = models.TextField(
        _('ملاحظات'),
        blank=True,
        null=True
    )
    
    class Meta:
        verbose_name = _('سجل حجز الدفعة')
        verbose_name_plural = _('سجلات حجز الدفعات')
        ordering = ['-reserved_at']
    
    def __str__(self):
        action = "حجز" if self.quantity_reserved > 0 else "إلغاء حجز"
        return f"{action} {abs(self.quantity_reserved)} من {self.batch.batch_number}"


class ExpiryAlert(models.Model):
    """
    تنبيهات انتهاء الصلاحية
    يدير التنبيهات للدفعات القريبة من انتهاء الصلاحية
    """
    ALERT_TYPE = (
        ('near_expiry', _('قريب من انتهاء الصلاحية')),
        ('expired', _('منتهي الصلاحية')),
        ('critical', _('حرج')),
    )
    
    batch = models.ForeignKey(
        ProductBatch,
        on_delete=models.CASCADE,
        related_name='expiry_alerts',
        verbose_name=_('الدفعة')
    )
    
    alert_type = models.CharField(
        _('نوع التنبيه'),
        max_length=20,
        choices=ALERT_TYPE
    )
    
    alert_date = models.DateField(
        _('تاريخ التنبيه'),
        default=timezone.now
    )
    
    days_to_expiry = models.IntegerField(
        _('أيام حتى انتهاء الصلاحية')
    )
    
    is_acknowledged = models.BooleanField(
        _('تم الاطلاع'),
        default=False
    )
    
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('اطلع عليه')
    )
    
    acknowledged_at = models.DateTimeField(
        _('تاريخ الاطلاع'),
        null=True,
        blank=True
    )
    
    action_taken = models.TextField(
        _('الإجراء المتخذ'),
        blank=True,
        null=True
    )
    
    created_at = models.DateTimeField(
        _('تاريخ الإنشاء'),
        auto_now_add=True
    )
    
    class Meta:
        verbose_name = _('تنبيه انتهاء الصلاحية')
        verbose_name_plural = _('تنبيهات انتهاء الصلاحية')
        ordering = ['-created_at']
        unique_together = ('batch', 'alert_type', 'alert_date')
    
    def __str__(self):
        return f"تنبيه {self.get_alert_type_display()} - {self.batch.batch_number}"
    
    def acknowledge(self, user, action_taken=None):
        """
        الاطلاع على التنبيه
        """
        self.is_acknowledged = True
        self.acknowledged_by = user
        self.acknowledged_at = timezone.now()
        
        if action_taken:
            self.action_taken = action_taken
        
        self.save()


class ExpiryRule(models.Model):
    """
    قواعد تنبيهات انتهاء الصلاحية
    تحدد متى يتم إنشاء التنبيهات
    """
    name = models.CharField(
        _('اسم القاعدة'),
        max_length=100
    )
    
    # فلاتر القاعدة
    product_category = models.ForeignKey(
        'product.Category',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_('فئة المنتج')
    )
    
    warehouse = models.ForeignKey(
        'product.Warehouse',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_('المستودع')
    )
    
    # إعدادات التنبيهات
    warning_days = models.PositiveIntegerField(
        _('أيام التحذير'),
        default=30,
        help_text=_('عدد الأيام قبل انتهاء الصلاحية لإرسال تحذير')
    )
    
    critical_days = models.PositiveIntegerField(
        _('أيام الحالة الحرجة'),
        default=7,
        help_text=_('عدد الأيام قبل انتهاء الصلاحية لإرسال تنبيه حرج')
    )
    
    auto_block_expired = models.BooleanField(
        _('حظر المنتجات المنتهية الصلاحية تلقائياً'),
        default=True
    )
    
    notify_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        verbose_name=_('المستخدمون المُنبهون'),
        help_text=_('المستخدمون الذين سيتلقون التنبيهات')
    )
    
    is_active = models.BooleanField(
        _('نشط'),
        default=True
    )
    
    created_at = models.DateTimeField(
        _('تاريخ الإنشاء'),
        auto_now_add=True
    )
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='expiry_rules_created',
        verbose_name=_('أنشئ بواسطة')
    )
    
    class Meta:
        verbose_name = _('قاعدة تنبيه انتهاء الصلاحية')
        verbose_name_plural = _('قواعد تنبيهات انتهاء الصلاحية')
        ordering = ['name']
    
    def __str__(self):
        return self.name
