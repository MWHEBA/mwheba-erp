"""
نماذج الأذون الجماعية (Batch Vouchers)
يسمح بإنشاء إذن واحد يحتوي على عدة منتجات
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.core.validators import MinValueValidator
from django.utils import timezone
from decimal import Decimal


class BatchVoucher(models.Model):
    """
    نموذج الإذن الجماعي - يحتوي على عدة منتجات
    """
    VOUCHER_TYPES = (
        ('receipt', _('إذن استلام جماعي')),
        ('issue', _('إذن صرف جماعي')),
        ('transfer', _('إذن تحويل جماعي')),
    )
    
    STATUS_CHOICES = (
        ('draft', _('مسودة')),
        ('pending', _('معلق')),
        ('approved', _('معتمد')),
    )
    
    voucher_number = models.CharField(
        _('رقم الإذن'),
        max_length=50,
        unique=True,
        blank=True
    )
    voucher_type = models.CharField(
        _('نوع الإذن'),
        max_length=20,
        choices=VOUCHER_TYPES
    )
    voucher_date = models.DateTimeField(
        _('تاريخ الإذن'),
        default=timezone.now
    )
    status = models.CharField(
        _('الحالة'),
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft'
    )
    
    # المخزن الأساسي (للاستلام/الصرف) أو المخزن المصدر (للتحويل)
    warehouse = models.ForeignKey(
        'Warehouse',
        on_delete=models.PROTECT,
        verbose_name=_('المخزن'),
        related_name='batch_vouchers'
    )
    
    # المخزن الهدف (للتحويل فقط)
    target_warehouse = models.ForeignKey(
        'Warehouse',
        on_delete=models.PROTECT,
        verbose_name=_('المخزن الهدف'),
        related_name='batch_vouchers_target',
        null=True,
        blank=True
    )
    
    # للاستلام والصرف
    purpose_type = models.CharField(
        _('الغرض'),
        max_length=30,
        choices=[
            ('donation', _('تبرع/هدية واردة')),
            ('inventory_gain', _('زيادة جرد')),
            ('samples', _('عينات مجانية')),
            ('marketing', _('تسويق وإعلان')),
            ('gifts', _('هدايا')),
            ('damage', _('تلف')),
            ('expired', _('منتهي الصلاحية')),
            ('theft', _('سرقة/فقدان')),
            ('other', _('أخرى')),
        ],
        null=True,
        blank=True
    )
    party_name = models.CharField(
        _('اسم الجهة'),
        max_length=200,
        blank=True
    )
    reference_document = models.CharField(
        _('المستند المرجعي'),
        max_length=100,
        blank=True
    )
    
    # معلومات إضافية
    notes = models.TextField(_('ملاحظات'), blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='batch_vouchers_created',
        verbose_name=_('أنشأه')
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='batch_vouchers_updated',
        verbose_name=_('عدله')
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='batch_vouchers_approved',
        verbose_name=_('اعتمده')
    )
    
    # التواريخ
    approval_date = models.DateTimeField(_('تاريخ الاعتماد'), null=True, blank=True)
    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True)
    updated_at = models.DateTimeField(_('تاريخ التحديث'), auto_now=True)
    
    # الإجماليات
    total_items = models.PositiveIntegerField(_('عدد الأصناف'), default=0)
    total_quantity = models.PositiveIntegerField(_('إجمالي الكمية'), default=0)
    total_value = models.DecimalField(
        _('إجمالي القيمة'),
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )
    
    # القيد المحاسبي الموحد
    journal_entry = models.ForeignKey(
        'financial.JournalEntry',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='batch_vouchers',
        verbose_name=_('القيد المحاسبي')
    )
    
    class Meta:
        verbose_name = _('إذن جماعي')
        verbose_name_plural = _('أذون جماعية')
        ordering = ['-voucher_date', '-created_at']
        indexes = [
            models.Index(fields=['voucher_type', 'status']),
            models.Index(fields=['warehouse', 'voucher_date']),
            models.Index(fields=['status', 'created_at']),
        ]
        permissions = [
            ('approve_batchvoucher', 'Can approve batch vouchers'),
        ]
    
    def __str__(self):
        return f"{self.voucher_number} - {self.get_voucher_type_display()}"
    
    def save(self, *args, **kwargs):
        if not self.voucher_number:
            from .system_utils import SerialNumber
            
            # تحديد البادئة حسب نوع الإذن
            prefix_map = {
                'receipt': 'BRV',  # Batch Receipt Voucher
                'issue': 'BIV',    # Batch Issue Voucher
                'transfer': 'BTV', # Batch Transfer Voucher
            }
            prefix = prefix_map.get(self.voucher_type, 'BV')
            
            # استخدام اسم أقصر للـ document_type
            doc_type_map = {
                'receipt': 'batch_rcpt',
                'issue': 'batch_issue',
                'transfer': 'batch_xfer',
            }
            doc_type = doc_type_map.get(self.voucher_type, 'batch')
            
            serial = SerialNumber.objects.get_or_create(
                document_type=doc_type,
                year=timezone.now().year,
                defaults={'prefix': prefix}
            )[0]
            next_number = serial.get_next_number()
            self.voucher_number = f"{serial.prefix}{next_number:04d}"
        
        super().save(*args, **kwargs)
    
    def can_edit(self):
        """هل يمكن تعديل الإذن؟"""
        return self.status in ['draft', 'pending']
    
    def can_approve(self):
        """هل يمكن اعتماد الإذن؟"""
        return self.status != 'approved' and self.items.exists()
    
    def can_delete(self):
        """هل يمكن حذف الإذن؟"""
        return self.status == 'draft'
    
    def calculate_totals(self):
        """حساب الإجماليات"""
        items = self.items.all()
        self.total_items = items.count()
        self.total_quantity = sum(item.quantity for item in items)
        self.total_value = sum(item.total_cost for item in items)
        self.save(update_fields=['total_items', 'total_quantity', 'total_value'])


class BatchVoucherItem(models.Model):
    """
    بند في الإذن الجماعي - منتج واحد
    """
    batch_voucher = models.ForeignKey(
        BatchVoucher,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name=_('الإذن الجماعي')
    )
    product = models.ForeignKey(
        'Product',
        on_delete=models.PROTECT,
        verbose_name=_('المنتج')
    )
    quantity = models.PositiveIntegerField(
        _('الكمية'),
        validators=[MinValueValidator(1)]
    )
    unit_cost = models.DecimalField(
        _('تكلفة الوحدة'),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    total_cost = models.DecimalField(
        _('التكلفة الإجمالية'),
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    
    # ربط بحركة المخزون المنشأة
    inventory_movement = models.OneToOneField(
        'InventoryMovement',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='batch_item',
        verbose_name=_('حركة المخزون')
    )
    
    notes = models.TextField(_('ملاحظات'), blank=True)
    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True)
    
    class Meta:
        verbose_name = _('بند إذن جماعي')
        verbose_name_plural = _('بنود الأذون الجماعية')
        unique_together = ('batch_voucher', 'product')
        ordering = ['batch_voucher', 'product']
    
    def __str__(self):
        return f"{self.batch_voucher.voucher_number} - {self.product.name}"
    
    def save(self, *args, **kwargs):
        # حساب التكلفة الإجمالية
        self.total_cost = self.quantity * self.unit_cost
        super().save(*args, **kwargs)
        
        # تحديث إجماليات الإذن
        self.batch_voucher.calculate_totals()
