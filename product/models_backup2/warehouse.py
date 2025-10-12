"""
نماذج المستودعات وإدارة المخزون
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from django.utils import timezone
from decimal import Decimal

User = get_user_model()


class Warehouse(models.Model):
    """
    نموذج المستودعات
    """
    name = models.CharField(
        _('اسم المستودع'),
        max_length=255
    )
    
    code = models.CharField(
        _('كود المستودع'),
        max_length=50,
        unique=True
    )
    
    description = models.TextField(
        _('الوصف'),
        blank=True,
        null=True
    )
    
    address = models.TextField(
        _('العنوان'),
        blank=True,
        null=True
    )
    
    phone = models.CharField(
        _('الهاتف'),
        max_length=20,
        blank=True,
        null=True
    )
    
    manager = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_warehouses',
        verbose_name=_('مدير المستودع')
    )
    
    is_active = models.BooleanField(
        _('نشط'),
        default=True
    )
    
    is_main = models.BooleanField(
        _('مستودع رئيسي'),
        default=False,
        help_text=_('المستودع الرئيسي للشركة')
    )
    
    created_at = models.DateTimeField(
        _('تاريخ الإنشاء'),
        auto_now_add=True
    )
    
    updated_at = models.DateTimeField(
        _('تاريخ التحديث'),
        auto_now=True
    )
    
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='created_warehouses',
        verbose_name=_('أنشئ بواسطة')
    )
    
    class Meta:
        app_label = 'product'
        verbose_name = _('مستودع')
        verbose_name_plural = _('المستودعات')
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.code})"
    
    def save(self, *args, **kwargs):
        # التأكد من وجود مستودع رئيسي واحد فقط
        if self.is_main:
            Warehouse.objects.filter(is_main=True).exclude(pk=self.pk).update(is_main=False)
        
        super().save(*args, **kwargs)
    
    @classmethod
    def get_main_warehouse(cls):
        """
        الحصول على المستودع الرئيسي
        """
        try:
            return cls.objects.get(is_main=True, is_active=True)
        except cls.DoesNotExist:
            # إذا لم يوجد مستودع رئيسي، إرجاع أول مستودع نشط
            return cls.objects.filter(is_active=True).first()
    
    def get_total_products(self):
        """
        الحصول على إجمالي عدد المنتجات في المستودع
        """
        return self.stocks.filter(quantity__gt=0).count()
    
    def get_total_value(self):
        """
        الحصول على إجمالي قيمة المخزون في المستودع
        """
        from django.db.models import Sum, F
        total = self.stocks.aggregate(
            total_value=Sum(F('quantity') * F('product__cost_price'))
        )
        return total['total_value'] or Decimal('0')


class ProductStock(models.Model):
    """
    نموذج مخزون المنتجات في المستودعات
    """
    product = models.ForeignKey(
        'product.Product',
        on_delete=models.CASCADE,
        related_name='stocks',
        verbose_name=_('المنتج')
    )
    
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name='stocks',
        verbose_name=_('المستودع')
    )
    
    quantity = models.DecimalField(
        _('الكمية'),
        max_digits=12,
        decimal_places=3,
        default=0,
        validators=[MinValueValidator(0)]
    )
    
    reserved_quantity = models.DecimalField(
        _('الكمية المحجوزة'),
        max_digits=12,
        decimal_places=3,
        default=0,
        validators=[MinValueValidator(0)],
        help_text=_('الكمية المحجوزة للطلبات المعلقة')
    )
    
    average_cost = models.DecimalField(
        _('متوسط التكلفة'),
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)]
    )
    
    last_purchase_date = models.DateTimeField(
        _('تاريخ آخر شراء'),
        null=True,
        blank=True
    )
    
    last_sale_date = models.DateTimeField(
        _('تاريخ آخر بيع'),
        null=True,
        blank=True
    )
    
    last_movement_date = models.DateTimeField(
        _('تاريخ آخر حركة'),
        null=True,
        blank=True
    )
    
    reorder_point = models.DecimalField(
        _('نقطة إعادة الطلب'),
        max_digits=12,
        decimal_places=3,
        default=0,
        validators=[MinValueValidator(0)],
        help_text=_('الكمية التي عندها يجب إعادة طلب المنتج')
    )
    
    max_stock = models.DecimalField(
        _('الحد الأقصى للمخزون'),
        max_digits=12,
        decimal_places=3,
        default=0,
        validators=[MinValueValidator(0)],
        help_text=_('الحد الأقصى للكمية في المستودع')
    )
    
    location = models.CharField(
        _('الموقع في المستودع'),
        max_length=100,
        blank=True,
        null=True,
        help_text=_('مثل: رف A، صف 1، عمود 3')
    )
    
    updated_at = models.DateTimeField(
        _('تاريخ التحديث'),
        auto_now=True
    )
    
    class Meta:
        app_label = 'product'
        verbose_name = _('مخزون منتج')
        verbose_name_plural = _('مخزون المنتجات')
        unique_together = ['product', 'warehouse']
        ordering = ['product__name', 'warehouse__name']
        indexes = [
            models.Index(fields=['product', 'warehouse']),
            models.Index(fields=['warehouse', 'quantity']),
            models.Index(fields=['product', 'quantity']),
        ]
    
    def __str__(self):
        return f"{self.product.name} - {self.warehouse.name} ({self.quantity})"
    
    @property
    def available_quantity(self):
        """
        الكمية المتاحة (الكمية الكلية - المحجوزة)
        """
        return self.quantity - self.reserved_quantity
    
    def update_last_movement(self):
        """
        تحديث تاريخ آخر حركة
        """
        from django.utils import timezone
        self.last_movement_date = timezone.now()
        self.save(update_fields=['last_movement_date'])


class StockTransfer(models.Model):
    """
    نموذج نقل المخزون بين المستودعات
    """
    TRANSFER_STATUS_CHOICES = [
        ('draft', _('مسودة')),
        ('pending', _('معلق')),
        ('approved', _('موافق عليه')),
        ('in_transit', _('في الطريق')),
        ('completed', _('مكتمل')),
        ('cancelled', _('ملغي')),
    ]
    
    transfer_number = models.CharField(
        _('رقم التحويل'),
        max_length=50,
        unique=True,
        blank=True
    )
    
    product = models.ForeignKey(
        'product.Product',
        on_delete=models.CASCADE,
        related_name='transfers',
        verbose_name=_('المنتج')
    )
    
    from_warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name='outgoing_transfers',
        verbose_name=_('من المستودع')
    )
    
    to_warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name='incoming_transfers',
        verbose_name=_('إلى المستودع')
    )
    
    quantity = models.DecimalField(
        _('الكمية'),
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(0.001)]
    )
    
    status = models.CharField(
        _('الحالة'),
        max_length=20,
        choices=TRANSFER_STATUS_CHOICES,
        default='draft'
    )
    
    transfer_date = models.DateTimeField(
        _('تاريخ التحويل'),
        default=timezone.now
    )
    
    notes = models.TextField(
        _('ملاحظات'),
        blank=True,
        null=True
    )
    
    created_at = models.DateTimeField(
        _('تاريخ الإنشاء'),
        auto_now_add=True
    )
    
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='created_transfers',
        verbose_name=_('أنشئ بواسطة')
    )
    
    class Meta:
        app_label = 'product'
        verbose_name = _('نقل مخزون')
        verbose_name_plural = _('عمليات نقل المخزون')
        ordering = ['-transfer_date', '-created_at']
        indexes = [
            models.Index(fields=['from_warehouse', 'transfer_date']),
            models.Index(fields=['to_warehouse', 'transfer_date']),
            models.Index(fields=['product', 'transfer_date']),
            models.Index(fields=['status', 'transfer_date']),
        ]
    
    def __str__(self):
        return f"تحويل {self.transfer_number} - {self.product.name} ({self.quantity})"
    
    def save(self, *args, **kwargs):
        if not self.transfer_number:
            # إنشاء رقم تحويل تلقائي
            now = timezone.now()
            prefix = f"TRF{now.strftime('%Y%m%d')}"
            
            last_transfer = StockTransfer.objects.filter(
                transfer_number__startswith=prefix
            ).order_by('-transfer_number').first()
            
            if last_transfer:
                last_number = int(last_transfer.transfer_number[-4:])
                new_number = last_number + 1
            else:
                new_number = 1
            
            self.transfer_number = f"{prefix}{new_number:04d}"
        
        super().save(*args, **kwargs)
