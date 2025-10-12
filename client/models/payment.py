"""
نماذج دفعات العملاء
"""
from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal


class CustomerPayment(models.Model):
    """
    نموذج دفعات العملاء - مطلوب لنظام تزامن المدفوعات
    """
    PAYMENT_METHOD_CHOICES = [
        ('cash', 'نقدي'),
        ('bank_transfer', 'تحويل بنكي'),
        ('check', 'شيك'),
        ('credit_card', 'بطاقة ائتمان'),
        ('other', 'أخرى'),
    ]
    
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'معلق'),
        ('completed', 'مكتمل'),
        ('cancelled', 'ملغي'),
        ('refunded', 'مسترد'),
    ]
    
    customer = models.ForeignKey(
        'client.Customer', 
        on_delete=models.CASCADE,
        related_name='payments',
        verbose_name='العميل'
    )
    
    amount = models.DecimalField(
        max_digits=15, 
        decimal_places=2,
        verbose_name='المبلغ'
    )
    
    payment_date = models.DateField(
        verbose_name='تاريخ الدفع'
    )
    
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        default='cash',
        verbose_name='طريقة الدفع'
    )
    
    status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default='pending',
        verbose_name='الحالة'
    )
    
    reference_number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='رقم المرجع'
    )
    
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name='الوصف'
    )
    
    # ربط مع نظام المبيعات
    sale = models.ForeignKey(
        'sale.Sale',
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name='customer_payments',
        verbose_name='فاتورة المبيعات'
    )
    
    # ربط مع النظام المالي
    financial_transaction = models.ForeignKey(
        'financial.JournalEntry',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='customer_payments',
        verbose_name='القيد المحاسبي'
    )
    
    # معلومات التتبع
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='تاريخ التحديث')
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='أنشئ بواسطة'
    )
    
    class Meta:
        verbose_name = 'دفعة عميل'
        verbose_name_plural = 'دفعات العملاء'
        ordering = ['-payment_date', '-created_at']
        indexes = [
            models.Index(fields=['customer', 'payment_date']),
            models.Index(fields=['status', 'payment_date']),
            models.Index(fields=['reference_number']),
        ]
    
    def __str__(self):
        return f'دفعة {self.customer.name} - {self.amount} - {self.payment_date}'
    
    def get_payment_method_display_ar(self):
        """عرض طريقة الدفع بالعربية"""
        methods = dict(self.PAYMENT_METHOD_CHOICES)
        return methods.get(self.payment_method, self.payment_method)
    
    def get_status_display_ar(self):
        """عرض الحالة بالعربية"""
        statuses = dict(self.PAYMENT_STATUS_CHOICES)
        return statuses.get(self.status, self.status)
    
    @property
    def is_completed(self):
        """هل الدفعة مكتملة؟"""
        return self.status == 'completed'
    
    @property
    def is_synced_to_financial(self):
        """هل تم ربط الدفعة بالنظام المالي؟"""
        return self.financial_transaction is not None
