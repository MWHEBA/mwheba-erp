from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from decimal import Decimal

from .base import BaseModel, PriceUnit
from .order import PrintingOrder


class OrderService(BaseModel):
    """
    نموذج ربط الخدمات بطلبات التسعير
    """
    order = models.ForeignKey(
        PrintingOrder,
        on_delete=models.CASCADE,
        related_name="services",
        verbose_name=_("الطلب")
    )
    
    # معلومات الخدمة
    service_category = models.CharField(
        max_length=50,
        choices=[
            ('printing', _('طباعة')),
            ('finishing', _('خدمات الطباعة')),  # قص، ريجة، تكسير، تثقيب
            ('packaging', _('خدمات التقفيل')),  # دبوس، بشر، سلك، تجليد
            ('coating', _('تغطية')),
            ('other', _('أخرى'))
        ],
        verbose_name=_("فئة الخدمة")
    )
    
    service_name = models.CharField(
        max_length=200,
        verbose_name=_("اسم الخدمة")
    )
    
    service_description = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("وصف الخدمة")
    )
    
    # معلومات التسعير
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        verbose_name=_("الكمية")
    )
    
    unit = models.CharField(
        max_length=20,
        choices=PriceUnit.choices,
        verbose_name=_("الوحدة")
    )
    
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("سعر الوحدة")
    )
    
    total_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("التكلفة الإجمالية")
    )
    
    # معلومات إضافية
    setup_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("تكلفة الإعداد")
    )
    
    is_optional = models.BooleanField(
        default=False,
        verbose_name=_("خدمة اختيارية")
    )
    
    supplier_info = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("معلومات المورد"),
        help_text=_("snapshot من بيانات المورد والسعر وقت التسعير")
    )

    # ربط مباشر بخدمة المورد — يُملأ عند اختيار المورد في نموذج التسعير
    supplier_service = models.ForeignKey(
        'supplier.SupplierService',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='order_services',
        verbose_name=_("خدمة المورد"),
        help_text=_("الخدمة المحددة من المورد لهذا البند")
    )
    
    finishing_type = models.ForeignKey(
        'printing_pricing.FinishingType',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='order_services',
        verbose_name=_("نوع التشطيب"),
        help_text=_("الربط الصلب بنوع التشطيب (سبوت UV، بصمة، كوفراج)")
    )
    coating_type = models.ForeignKey(
        'printing_pricing.CoatingType',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='order_services',
        verbose_name=_("نوع التغطية/السلوفان"),
        help_text=_("الربط الصلب بنوع التغطية (سلوفان مط، لميع، كوي)")
    )
    packaging_type = models.ForeignKey(
        'printing_pricing.PackagingType',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='order_services',
        verbose_name=_("نوع التقفيل/التجليد"),
        help_text=_("الربط الصلب بنوع التقفيل والتجليد")
    )

    execution_time = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("وقت التنفيذ (ساعات)")
    )

    class Meta:
        verbose_name = _("خدمة الطلب")
        verbose_name_plural = _("خدمات الطلبات")
        ordering = ['service_category', 'service_name']
        indexes = [
            models.Index(fields=['order', 'service_category']),
        ]

    def __str__(self):
        return f"{self.service_name} - {self.order.order_number}"

    def save(self, *args, **kwargs):
        """
        حفظ محسن مع حساب التكلفة الإجمالية
        """
        self.calculate_total_cost()
        super().save(*args, **kwargs)

    def calculate_total_cost(self):
        """
        حساب التكلفة الإجمالية مع الحفاظ على صمامات الحد الأدنى
        """
        calculated = (self.quantity * self.unit_price + self.setup_cost) if (self.quantity and self.unit_price) else self.setup_cost
        if self.total_cost and self.total_cost > calculated:
            return
        self.total_cost = calculated

    def update_pricing(self, new_unit_price=None, new_quantity=None, new_setup_cost=None):
        """
        تحديث التسعير
        """
        if new_unit_price is not None:
            self.unit_price = new_unit_price
        if new_quantity is not None:
            self.quantity = new_quantity
        if new_setup_cost is not None:
            self.setup_cost = new_setup_cost
        
        self.calculate_total_cost()
        self.save()
__all__ = ['OrderService']

