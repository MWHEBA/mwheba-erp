from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from decimal import Decimal

from .base import BaseModel, PricingStatus, OrderType
from client.models import Customer


class PrintingOrder(BaseModel):
    """
    نموذج طلب التسعير المحسن
    """
    # معلومات أساسية
    order_number = models.CharField(
        max_length=50,
        unique=True,
        verbose_name=_("رقم الطلب"),
        help_text=_("رقم فريد للطلب")
    )
    
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="printing_orders",
        verbose_name=_("العميل")
    )
    
    title = models.CharField(
        max_length=200,
        verbose_name=_("عنوان الطلب")
    )
    
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("وصف الطلب")
    )
    
    order_type = models.CharField(
        max_length=20,
        choices=OrderType.choices,
        verbose_name=_("نوع الطلب")
    )
    
    status = models.CharField(
        max_length=20,
        choices=PricingStatus.choices,
        default=PricingStatus.DRAFT,
        verbose_name=_("حالة الطلب")
    )
    
    # معلومات الكمية والمواصفات
    quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        verbose_name=_("الكمية")
    )
    
    pages_count = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        verbose_name=_("عدد الصفحات")
    )
    
    copies_count = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        verbose_name=_("عدد النسخ")
    )
    
    # معلومات الأبعاد
    width = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name=_("العرض (سم)")
    )
    
    height = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name=_("الارتفاع (سم)")
    )
    
    # معلومات التكلفة
    estimated_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("التكلفة المقدرة")
    )
    
    final_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("السعر النهائي")
    )
    
    profit_margin = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('20.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("هامش الربح (%)")
    )
    
    # تواريخ مهمة
    due_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("تاريخ التسليم المطلوب")
    )
    
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("تاريخ الاعتماد")
    )
    
    # معلومات إضافية
    priority = models.CharField(
        max_length=10,
        choices=[
            ('low', _('منخفضة')),
            ('medium', _('متوسطة')),
            ('high', _('عالية')),
            ('urgent', _('عاجلة'))
        ],
        default='medium',
        verbose_name=_("الأولوية")
    )
    
    is_rush_order = models.BooleanField(
        default=False,
        verbose_name=_("طلب عاجل")
    )
    
    rush_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("رسوم الاستعجال")
    )

    class Meta:
        verbose_name = _("طلب تسعير")
        verbose_name_plural = _("طلبات التسعير")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['order_number']),
            models.Index(fields=['customer', 'status']),
            models.Index(fields=['created_at']),
            models.Index(fields=['due_date']),
        ]

    def __str__(self):
        return f"{self.order_number} - {self.title}"

    def save(self, *args, **kwargs):
        """
        حفظ محسن مع توليد رقم الطلب تلقائياً
        """
        if not self.order_number:
            self.order_number = self.generate_order_number()
        super().save(*args, **kwargs)

    def generate_order_number(self):
        """
        توليد رقم طلب فريد
        """
        from django.utils import timezone
        import random
        
        now = timezone.now()
        date_part = now.strftime("%Y%m%d")
        
        # البحث عن آخر رقم في نفس اليوم
        last_order = PrintingOrder.objects.filter(
            order_number__startswith=f"PO{date_part}"
        ).order_by('-order_number').first()
        
        if last_order:
            last_seq = int(last_order.order_number[-3:])
            new_seq = last_seq + 1
        else:
            new_seq = 1
            
        return f"PO{date_part}{new_seq:03d}"

    @property
    def total_pages(self):
        """
        إجمالي عدد الصفحات (الصفحات × النسخ)
        """
        return self.pages_count * self.copies_count

    @property
    def total_items(self):
        """
        إجمالي عدد القطع
        """
        return self.quantity * self.copies_count

    def calculate_final_price(self):
        """
        حساب السعر النهائي مع هامش الربح
        """
        if self.estimated_cost:
            margin_amount = self.estimated_cost * (self.profit_margin / 100)
            return self.estimated_cost + margin_amount + self.rush_fee
        return Decimal('0.00')

    def update_status(self, new_status, user=None):
        """
        تحديث حالة الطلب مع تسجيل المستخدم
        """
        old_status = self.status
        self.status = new_status
        
        if new_status == PricingStatus.APPROVED:
            from django.utils import timezone
            self.approved_at = timezone.now()
            
        if user:
            self.updated_by = user
            
        self.save()
        
        # يمكن إضافة signal هنا لتسجيل تغيير الحالة
        return old_status, new_status


__all__ = ['PrintingOrder']
