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
            ('finishing', _('تشطيبات')),
            ('binding', _('تجليد')),
            ('cutting', _('تقطيع')),
            ('folding', _('طي')),
            ('lamination', _('تقفيل')),
            ('coating', _('تغطية')),
            ('embossing', _('بصمة')),
            ('perforation', _('ثقب')),
            ('numbering', _('ترقيم')),
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
        help_text=_("معلومات المورد والأسعار")
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
        حساب التكلفة الإجمالية
        """
        if self.quantity and self.unit_price:
            self.total_cost = (self.quantity * self.unit_price) + self.setup_cost
        else:
            self.total_cost = self.setup_cost

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


class PrintingSpecification(BaseModel):
    """
    مواصفات الطباعة للطلب
    """
    order = models.OneToOneField(
        PrintingOrder,
        on_delete=models.CASCADE,
        related_name="printing_spec",
        verbose_name=_("الطلب")
    )
    
    # نوع الطباعة
    printing_type = models.CharField(
        max_length=20,
        choices=[
            ('offset', _('أوفست')),
            ('digital', _('رقمية')),
            ('screen', _('سلك سكرين')),
            ('flexo', _('فلكسو')),
            ('letterpress', _('ليتر برس')),
            ('inkjet', _('نفث حبر')),
            ('laser', _('ليزر'))
        ],
        verbose_name=_("نوع الطباعة")
    )
    
    # معلومات الألوان
    colors_front = models.PositiveIntegerField(
        default=1,
        verbose_name=_("عدد الألوان - الوجه")
    )
    
    colors_back = models.PositiveIntegerField(
        default=0,
        verbose_name=_("عدد الألوان - الظهر")
    )
    
    is_cmyk = models.BooleanField(
        default=True,
        verbose_name=_("طباعة CMYK")
    )
    
    has_spot_colors = models.BooleanField(
        default=False,
        verbose_name=_("يحتوي على ألوان خاصة")
    )
    
    spot_colors_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_("عدد الألوان الخاصة")
    )
    
    # معلومات الجودة
    resolution_dpi = models.PositiveIntegerField(
        default=300,
        verbose_name=_("دقة الطباعة (DPI)")
    )
    
    print_quality = models.CharField(
        max_length=20,
        choices=[
            ('draft', _('مسودة')),
            ('normal', _('عادية')),
            ('high', _('عالية')),
            ('premium', _('ممتازة'))
        ],
        default='normal',
        verbose_name=_("جودة الطباعة")
    )
    
    # معلومات التكلفة
    plates_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("تكلفة الزنكات")
    )
    
    printing_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("تكلفة الطباعة")
    )
    
    # معلومات إضافية
    special_requirements = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("متطلبات خاصة")
    )

    class Meta:
        verbose_name = _("مواصفات الطباعة")
        verbose_name_plural = _("مواصفات الطباعة")

    def __str__(self):
        return f"{self.printing_type} - {self.order.order_number}"

    @property
    def total_colors(self):
        """
        إجمالي عدد الألوان
        """
        return self.colors_front + self.colors_back + self.spot_colors_count

    @property
    def is_double_sided(self):
        """
        هل الطباعة على الوجهين
        """
        return self.colors_back > 0

    def calculate_plates_cost(self, cost_per_plate=None):
        """
        حساب تكلفة الزنكات
        """
        if cost_per_plate is None:
            cost_per_plate = Decimal('50.00')  # سعر افتراضي
        
        total_plates = self.colors_front + self.colors_back + self.spot_colors_count
        self.plates_cost = total_plates * cost_per_plate
        return self.plates_cost


__all__ = ['OrderService', 'PrintingSpecification']
