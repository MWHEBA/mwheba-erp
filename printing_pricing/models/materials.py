from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from decimal import Decimal

from .base import BaseModel, PriceUnit
from .order import PrintingOrder


class OrderMaterial(BaseModel):
    """
    نموذج ربط المواد بطلبات التسعير
    """
    order = models.ForeignKey(
        PrintingOrder,
        on_delete=models.CASCADE,
        related_name="materials",
        verbose_name=_("الطلب")
    )
    
    # معلومات المادة (سنربطها بالنماذج الموجودة لاحقاً)
    material_type = models.CharField(
        max_length=50,
        verbose_name=_("نوع المادة"),
        help_text=_("ورق، حبر، زنكات، إلخ")
    )
    
    material_name = models.CharField(
        max_length=200,
        verbose_name=_("اسم المادة")
    )
    
    # معلومات الكمية والتكلفة
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        verbose_name=_("الكمية المطلوبة")
    )
    
    unit = models.CharField(
        max_length=20,
        choices=PriceUnit.choices,
        verbose_name=_("الوحدة")
    )
    
    unit_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("تكلفة الوحدة")
    )
    
    total_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("التكلفة الإجمالية")
    )
    
    # معلومات إضافية
    waste_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('5.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("نسبة الهالك (%)")
    )
    
    supplier_info = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("معلومات المورد"),
        help_text=_("معلومات المورد والأسعار")
    )

    class Meta:
        verbose_name = _("مادة الطلب")
        verbose_name_plural = _("مواد الطلبات")
        ordering = ['material_type', 'material_name']
        indexes = [
            models.Index(fields=['order', 'material_type']),
        ]

    def __str__(self):
        return f"{self.material_name} - {self.order.order_number}"

    def save(self, *args, **kwargs):
        """
        حفظ محسن مع حساب التكلفة الإجمالية
        """
        self.calculate_total_cost()
        super().save(*args, **kwargs)

    def calculate_total_cost(self):
        """
        حساب التكلفة الإجمالية مع الهالك
        """
        if self.quantity and self.unit_cost:
            base_cost = self.quantity * self.unit_cost
            waste_amount = base_cost * (self.waste_percentage / 100)
            self.total_cost = base_cost + waste_amount
        else:
            self.total_cost = Decimal('0.00')

    def update_cost(self, new_unit_cost=None, new_quantity=None):
        """
        تحديث التكلفة
        """
        if new_unit_cost is not None:
            self.unit_cost = new_unit_cost
        if new_quantity is not None:
            self.quantity = new_quantity
        
        self.calculate_total_cost()
        self.save()


class PaperSpecification(BaseModel):
    """
    مواصفات الورق للطلب
    """
    order = models.OneToOneField(
        PrintingOrder,
        on_delete=models.CASCADE,
        related_name="paper_spec",
        verbose_name=_("الطلب")
    )
    
    # نوع الورق (سنربطه بالنماذج الموجودة لاحقاً)
    paper_type_name = models.CharField(
        max_length=100,
        verbose_name=_("نوع الورق")
    )
    
    paper_weight = models.PositiveIntegerField(
        verbose_name=_("وزن الورق (جرام)")
    )
    
    paper_size_name = models.CharField(
        max_length=50,
        verbose_name=_("مقاس الورق")
    )
    
    # معلومات الأبعاد
    sheet_width = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name=_("عرض الفرخ (سم)")
    )
    
    sheet_height = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name=_("طول الفرخ (سم)")
    )
    
    # معلومات الكمية
    sheets_needed = models.PositiveIntegerField(
        verbose_name=_("عدد الفروخ المطلوبة")
    )
    
    montage_count = models.PositiveIntegerField(
        default=1,
        verbose_name=_("عدد القطع في الفرخ")
    )
    
    # مقاس القطع
    PIECE_SIZE_CHOICES = [
        ('', '-- اختر مقاس القطع --'),
        ('A4', 'A4 (21×29.7 سم)'),
        ('A5', 'A5 (14.8×21 سم)'),
        ('A6', 'A6 (10.5×14.8 سم)'),
        ('10x15', '10×15 سم'),
        ('15x20', '15×20 سم'),
        ('20x30', '20×30 سم'),
        ('custom', 'مقاس مخصص'),
    ]
    
    piece_size = models.CharField(
        max_length=50,
        choices=PIECE_SIZE_CHOICES,
        blank=True,
        null=True,
        verbose_name=_("مقاس القطع")
    )
    
    # معلومات التكلفة
    sheet_cost = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("تكلفة الفرخ")
    )
    
    total_paper_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("إجمالي تكلفة الورق")
    )

    class Meta:
        verbose_name = _("مواصفات الورق")
        verbose_name_plural = _("مواصفات الأوراق")

    def __str__(self):
        return f"{self.paper_type_name} - {self.order.order_number}"

    def save(self, *args, **kwargs):
        """
        حفظ محسن مع حساب التكلفة
        """
        self.calculate_total_cost()
        super().save(*args, **kwargs)

    def calculate_total_cost(self):
        """
        حساب إجمالي تكلفة الورق
        """
        if self.sheets_needed and self.sheet_cost:
            self.total_paper_cost = self.sheets_needed * self.sheet_cost
        else:
            self.total_paper_cost = Decimal('0.00')

    @property
    def sheet_area(self):
        """
        مساحة الفرخ بالسنتيمتر المربع
        """
        if self.sheet_width and self.sheet_height:
            return self.sheet_width * self.sheet_height
        return Decimal('0.00')

    def calculate_sheets_needed(self, total_pieces, montage_count=None):
        """
        حساب عدد الفروخ المطلوبة
        """
        if montage_count:
            self.montage_count = montage_count
        
        if self.montage_count > 0:
            import math
            self.sheets_needed = math.ceil(total_pieces / self.montage_count)
        else:
            self.sheets_needed = total_pieces


__all__ = ['OrderMaterial', 'PaperSpecification']
