"""
نظام إدارة المواقع داخل المستودعات
يدير الأرفف والممرات والمواقع التفصيلية للمنتجات
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator
from django.conf import settings
from django.utils import timezone
from decimal import Decimal


class LocationZone(models.Model):
    """
    نموذج المناطق داخل المستودع
    مثل: منطقة التبريد، منطقة الأدوية، منطقة المواد الغذائية
    """
    ZONE_TYPE = (
        ('normal', _('عادي')),
        ('cold', _('تبريد')),
        ('frozen', _('تجميد')),
        ('hazardous', _('مواد خطرة')),
        ('fragile', _('مواد قابلة للكسر')),
        ('high_value', _('عالي القيمة')),
    )
    
    warehouse = models.ForeignKey(
        'product.Warehouse',
        on_delete=models.CASCADE,
        related_name='zones',
        verbose_name=_('المستودع')
    )
    
    name = models.CharField(
        _('اسم المنطقة'),
        max_length=100
    )
    
    code = models.CharField(
        _('كود المنطقة'),
        max_length=20
    )
    
    zone_type = models.CharField(
        _('نوع المنطقة'),
        max_length=20,
        choices=ZONE_TYPE,
        default='normal'
    )
    
    description = models.TextField(
        _('الوصف'),
        blank=True,
        null=True
    )
    
    # خصائص المنطقة
    temperature_min = models.DecimalField(
        _('الحد الأدنى لدرجة الحرارة'),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('بالدرجة المئوية')
    )
    
    temperature_max = models.DecimalField(
        _('الحد الأقصى لدرجة الحرارة'),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('بالدرجة المئوية')
    )
    
    humidity_max = models.PositiveIntegerField(
        _('الحد الأقصى للرطوبة'),
        null=True,
        blank=True,
        validators=[MaxValueValidator(100)],
        help_text=_('بالنسبة المئوية')
    )
    
    # قيود الوصول
    requires_authorization = models.BooleanField(
        _('يتطلب تصريح'),
        default=False
    )
    
    authorized_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        verbose_name=_('المستخدمون المصرح لهم'),
        related_name='authorized_zones'
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
        verbose_name=_('أنشئ بواسطة')
    )
    
    class Meta:
        verbose_name = _('منطقة مستودع')
        verbose_name_plural = _('مناطق المستودعات')
        unique_together = ('warehouse', 'code')
        ordering = ['warehouse', 'name']
    
    def __str__(self):
        return f"{self.warehouse.name} - {self.name}"


class LocationAisle(models.Model):
    """
    نموذج الممرات داخل المنطقة
    """
    zone = models.ForeignKey(
        LocationZone,
        on_delete=models.CASCADE,
        related_name='aisles',
        verbose_name=_('المنطقة')
    )
    
    name = models.CharField(
        _('اسم الممر'),
        max_length=50
    )
    
    code = models.CharField(
        _('كود الممر'),
        max_length=10
    )
    
    description = models.TextField(
        _('الوصف'),
        blank=True,
        null=True
    )
    
    # ترتيب الممر
    sequence = models.PositiveIntegerField(
        _('الترتيب'),
        default=1
    )
    
    is_active = models.BooleanField(
        _('نشط'),
        default=True
    )
    
    class Meta:
        verbose_name = _('ممر')
        verbose_name_plural = _('الممرات')
        unique_together = ('zone', 'code')
        ordering = ['zone', 'sequence', 'name']
    
    def __str__(self):
        return f"{self.zone.name} - ممر {self.name}"


class LocationShelf(models.Model):
    """
    نموذج الأرفف داخل الممر
    """
    aisle = models.ForeignKey(
        LocationAisle,
        on_delete=models.CASCADE,
        related_name='shelves',
        verbose_name=_('الممر')
    )
    
    name = models.CharField(
        _('اسم الرف'),
        max_length=50
    )
    
    code = models.CharField(
        _('كود الرف'),
        max_length=10
    )
    
    # مستويات الرف
    levels = models.PositiveIntegerField(
        _('عدد المستويات'),
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(10)]
    )
    
    # سعة الرف
    max_weight = models.DecimalField(
        _('الحد الأقصى للوزن'),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('بالكيلوجرام')
    )
    
    max_volume = models.DecimalField(
        _('الحد الأقصى للحجم'),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('بالمتر المكعب')
    )
    
    # ترتيب الرف
    sequence = models.PositiveIntegerField(
        _('الترتيب'),
        default=1
    )
    
    is_active = models.BooleanField(
        _('نشط'),
        default=True
    )
    
    class Meta:
        verbose_name = _('رف')
        verbose_name_plural = _('الأرفف')
        unique_together = ('aisle', 'code')
        ordering = ['aisle', 'sequence', 'name']
    
    def __str__(self):
        return f"{self.aisle.name} - رف {self.name}"
    
    @property
    def full_location_code(self):
        """الكود الكامل للموقع"""
        return f"{self.aisle.zone.code}-{self.aisle.code}-{self.code}"


class ProductLocation(models.Model):
    """
    نموذج مواقع المنتجات
    يربط المنتج بموقع محدد في المستودع
    """
    LOCATION_TYPE = (
        ('primary', _('موقع رئيسي')),
        ('secondary', _('موقع ثانوي')),
        ('overflow', _('موقع إضافي')),
        ('picking', _('موقع انتقاء')),
        ('reserve', _('موقع احتياطي')),
    )
    
    product = models.ForeignKey(
        'product.Product',
        on_delete=models.CASCADE,
        related_name='locations',
        verbose_name=_('المنتج')
    )
    
    shelf = models.ForeignKey(
        LocationShelf,
        on_delete=models.CASCADE,
        related_name='product_locations',
        verbose_name=_('الرف')
    )
    
    level = models.PositiveIntegerField(
        _('المستوى'),
        default=1,
        validators=[MinValueValidator(1)]
    )
    
    position = models.CharField(
        _('الموضع'),
        max_length=10,
        blank=True,
        null=True,
        help_text=_('مثل: A1, B2, إلخ')
    )
    
    location_type = models.CharField(
        _('نوع الموقع'),
        max_length=20,
        choices=LOCATION_TYPE,
        default='primary'
    )
    
    # كميات في هذا الموقع
    current_quantity = models.PositiveIntegerField(
        _('الكمية الحالية'),
        default=0
    )
    
    max_quantity = models.PositiveIntegerField(
        _('الحد الأقصى للكمية'),
        null=True,
        blank=True
    )
    
    min_quantity = models.PositiveIntegerField(
        _('الحد الأدنى للكمية'),
        default=0
    )
    
    # معلومات إضافية
    notes = models.TextField(
        _('ملاحظات'),
        blank=True,
        null=True
    )
    
    is_active = models.BooleanField(
        _('نشط'),
        default=True
    )
    
    created_at = models.DateTimeField(
        _('تاريخ الإنشاء'),
        auto_now_add=True
    )
    
    updated_at = models.DateTimeField(
        _('تاريخ آخر تحديث'),
        auto_now=True
    )
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_('أنشئ بواسطة')
    )
    
    class Meta:
        verbose_name = _('موقع منتج')
        verbose_name_plural = _('مواقع المنتجات')
        unique_together = ('product', 'shelf', 'level', 'position')
        ordering = ['product', 'location_type', 'shelf']
    
    def __str__(self):
        position_str = f"-{self.position}" if self.position else ""
        return f"{self.product.name} @ {self.shelf.full_location_code}-L{self.level}{position_str}"
    
    @property
    def full_location_code(self):
        """الكود الكامل للموقع مع المستوى والموضع"""
        position_str = f"-{self.position}" if self.position else ""
        return f"{self.shelf.full_location_code}-L{self.level}{position_str}"
    
    @property
    def warehouse(self):
        """المستودع المرتبط بهذا الموقع"""
        return self.shelf.aisle.zone.warehouse
    
    @property
    def is_full(self):
        """هل الموقع ممتلئ؟"""
        if self.max_quantity:
            return self.current_quantity >= self.max_quantity
        return False
    
    @property
    def is_low(self):
        """هل الكمية منخفضة؟"""
        return self.current_quantity <= self.min_quantity
    
    @property
    def available_space(self):
        """المساحة المتاحة"""
        if self.max_quantity:
            return max(0, self.max_quantity - self.current_quantity)
        return None
    
    def can_accommodate(self, quantity):
        """هل يمكن استيعاب كمية معينة؟"""
        if self.max_quantity:
            return (self.current_quantity + quantity) <= self.max_quantity
        return True


class LocationMovement(models.Model):
    """
    نموذج حركات المواقع
    يتتبع نقل المنتجات بين المواقع
    """
    MOVEMENT_TYPE = (
        ('move', _('نقل')),
        ('restock', _('إعادة تخزين')),
        ('pick', _('انتقاء')),
        ('cycle_count', _('جرد دوري')),
        ('adjustment', _('تسوية')),
    )
    
    product = models.ForeignKey(
        'product.Product',
        on_delete=models.CASCADE,
        related_name='location_movements',
        verbose_name=_('المنتج')
    )
    
    from_location = models.ForeignKey(
        ProductLocation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='movements_from',
        verbose_name=_('من الموقع')
    )
    
    to_location = models.ForeignKey(
        ProductLocation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='movements_to',
        verbose_name=_('إلى الموقع')
    )
    
    movement_type = models.CharField(
        _('نوع الحركة'),
        max_length=20,
        choices=MOVEMENT_TYPE
    )
    
    quantity = models.PositiveIntegerField(
        _('الكمية')
    )
    
    reason = models.TextField(
        _('السبب'),
        blank=True,
        null=True
    )
    
    # ربط بحركة المخزون الأساسية
    inventory_movement = models.ForeignKey(
        'product.InventoryMovement',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('حركة المخزون المرتبطة')
    )
    
    moved_at = models.DateTimeField(
        _('تاريخ النقل'),
        auto_now_add=True
    )
    
    moved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_('نُقل بواسطة')
    )
    
    class Meta:
        verbose_name = _('حركة موقع')
        verbose_name_plural = _('حركات المواقع')
        ordering = ['-moved_at']
    
    def __str__(self):
        from_loc = self.from_location.full_location_code if self.from_location else "خارجي"
        to_loc = self.to_location.full_location_code if self.to_location else "خارجي"
        return f"{self.product.name}: {from_loc} → {to_loc} ({self.quantity})"


class LocationTask(models.Model):
    """
    نموذج مهام المواقع
    مثل: إعادة ترتيب، جرد، نقل، إلخ
    """
    TASK_TYPE = (
        ('restock', _('إعادة تخزين')),
        ('pick', _('انتقاء')),
        ('move', _('نقل')),
        ('count', _('جرد')),
        ('clean', _('تنظيف')),
        ('maintenance', _('صيانة')),
    )
    
    TASK_STATUS = (
        ('pending', _('معلق')),
        ('assigned', _('مُعين')),
        ('in_progress', _('قيد التنفيذ')),
        ('completed', _('مكتمل')),
        ('cancelled', _('ملغي')),
    )
    
    PRIORITY = (
        (1, _('عاجل')),
        (2, _('عالي')),
        (3, _('متوسط')),
        (4, _('منخفض')),
    )
    
    task_type = models.CharField(
        _('نوع المهمة'),
        max_length=20,
        choices=TASK_TYPE
    )
    
    title = models.CharField(
        _('عنوان المهمة'),
        max_length=200
    )
    
    description = models.TextField(
        _('الوصف'),
        blank=True,
        null=True
    )
    
    location = models.ForeignKey(
        ProductLocation,
        on_delete=models.CASCADE,
        related_name='tasks',
        verbose_name=_('الموقع')
    )
    
    product = models.ForeignKey(
        'product.Product',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_('المنتج')
    )
    
    quantity = models.PositiveIntegerField(
        _('الكمية'),
        null=True,
        blank=True
    )
    
    priority = models.PositiveIntegerField(
        _('الأولوية'),
        choices=PRIORITY,
        default=3
    )
    
    status = models.CharField(
        _('الحالة'),
        max_length=20,
        choices=TASK_STATUS,
        default='pending'
    )
    
    # تواريخ مهمة
    due_date = models.DateTimeField(
        _('تاريخ الاستحقاق'),
        null=True,
        blank=True
    )
    
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='location_tasks_assigned',
        verbose_name=_('مُعين إلى')
    )
    
    assigned_at = models.DateTimeField(
        _('تاريخ التعيين'),
        null=True,
        blank=True
    )
    
    started_at = models.DateTimeField(
        _('تاريخ البدء'),
        null=True,
        blank=True
    )
    
    completed_at = models.DateTimeField(
        _('تاريخ الإكمال'),
        null=True,
        blank=True
    )
    
    created_at = models.DateTimeField(
        _('تاريخ الإنشاء'),
        auto_now_add=True
    )
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='location_tasks_created',
        verbose_name=_('أنشئ بواسطة')
    )
    
    class Meta:
        verbose_name = _('مهمة موقع')
        verbose_name_plural = _('مهام المواقع')
        ordering = ['priority', '-created_at']
    
    def __str__(self):
        return f"{self.get_task_type_display()}: {self.title}"
    
    def assign_to(self, user):
        """تعيين المهمة لمستخدم"""
        self.assigned_to = user
        self.assigned_at = timezone.now()
        self.status = 'assigned'
        self.save()
    
    def start_task(self):
        """بدء تنفيذ المهمة"""
        self.started_at = timezone.now()
        self.status = 'in_progress'
        self.save()
    
    def complete_task(self):
        """إكمال المهمة"""
        self.completed_at = timezone.now()
        self.status = 'completed'
        self.save()
