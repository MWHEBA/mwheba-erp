from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from decimal import Decimal

from .base import BaseModel, CalculationType
from .order import PrintingOrder


class CostCalculation(BaseModel):
    """
    نموذج حفظ نتائج حسابات التكلفة
    """
    order = models.ForeignKey(
        PrintingOrder,
        on_delete=models.CASCADE,
        related_name="calculations",
        verbose_name=_("الطلب")
    )
    
    calculation_type = models.CharField(
        max_length=20,
        choices=CalculationType.choices,
        verbose_name=_("نوع الحساب")
    )
    
    # نتائج الحساب
    base_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("التكلفة الأساسية")
    )
    
    additional_costs = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("التكاليف الإضافية")
    )
    
    total_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("إجمالي التكلفة")
    )
    
    # معلومات الحساب
    calculation_details = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("تفاصيل الحساب"),
        help_text=_("تفاصيل مفصلة عن كيفية الحساب")
    )
    
    calculation_date = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("تاريخ الحساب")
    )
    
    is_current = models.BooleanField(
        default=True,
        verbose_name=_("الحساب الحالي"),
        help_text=_("هل هذا هو الحساب الأحدث لهذا النوع")
    )
    
    # معلومات المعايير المستخدمة
    parameters_used = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("المعايير المستخدمة"),
        help_text=_("المعايير والقيم المستخدمة في الحساب")
    )

    class Meta:
        verbose_name = _("حساب التكلفة")
        verbose_name_plural = _("حسابات التكلفة")
        ordering = ['-calculation_date']
        indexes = [
            models.Index(fields=['order', 'calculation_type']),
            models.Index(fields=['calculation_date']),
            models.Index(fields=['is_current']),
        ]
        unique_together = [
            ['order', 'calculation_type', 'is_current']
        ]

    def __str__(self):
        return f"{self.get_calculation_type_display()} - {self.order.order_number}"

    def save(self, *args, **kwargs):
        """
        حفظ محسن مع تحديث الحسابات السابقة
        """
        if self.is_current:
            # إلغاء تفعيل الحسابات السابقة من نفس النوع
            CostCalculation.objects.filter(
                order=self.order,
                calculation_type=self.calculation_type,
                is_current=True
            ).exclude(pk=self.pk).update(is_current=False)
        
        # حساب إجمالي التكلفة
        self.calculate_total()
        super().save(*args, **kwargs)

    def calculate_total(self):
        """
        حساب إجمالي التكلفة
        """
        self.total_cost = self.base_cost + self.additional_costs

    def add_detail(self, key, value, description=None):
        """
        إضافة تفصيل للحساب
        """
        if not self.calculation_details:
            self.calculation_details = {}
        
        self.calculation_details[key] = {
            'value': str(value),
            'description': description or key,
            'timestamp': str(self.calculation_date or self.created_at)
        }

    def get_detail(self, key, default=None):
        """
        الحصول على تفصيل من الحساب
        """
        if self.calculation_details and key in self.calculation_details:
            return self.calculation_details[key].get('value', default)
        return default


class OrderSummary(BaseModel):
    """
    ملخص شامل لطلب التسعير
    """
    order = models.OneToOneField(
        PrintingOrder,
        on_delete=models.CASCADE,
        related_name="summary",
        verbose_name=_("الطلب")
    )
    
    # ملخص التكاليف
    material_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("تكلفة المواد")
    )
    
    printing_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("تكلفة الطباعة")
    )
    
    finishing_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("تكلفة التشطيبات")
    )
    
    design_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("تكلفة التصميم")
    )
    
    other_costs = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("تكاليف أخرى")
    )
    
    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("المجموع الفرعي")
    )
    
    # الخصومات والإضافات
    discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("قيمة الخصم")
    )
    
    tax_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("قيمة الضريبة")
    )
    
    rush_fee = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("رسوم الاستعجال")
    )
    
    total_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("إجمالي التكلفة")
    )
    
    # معلومات الربح
    profit_margin_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('20.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("هامش الربح (%)")
    )
    
    profit_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("قيمة الربح")
    )
    
    final_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("السعر النهائي")
    )
    
    # معلومات إضافية
    last_calculated = models.DateTimeField(
        auto_now=True,
        verbose_name=_("آخر حساب")
    )
    
    calculation_notes = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("ملاحظات الحساب")
    )

    class Meta:
        verbose_name = _("ملخص الطلب")
        verbose_name_plural = _("ملخصات الطلبات")

    def __str__(self):
        return f"ملخص - {self.order.order_number}"

    def calculate_all(self):
        """
        حساب جميع القيم
        """
        # حساب المجموع الفرعي
        self.subtotal = (
            self.material_cost + 
            self.printing_cost + 
            self.finishing_cost + 
            self.design_cost + 
            self.other_costs
        )
        
        # حساب إجمالي التكلفة
        self.total_cost = (
            self.subtotal - 
            self.discount_amount + 
            self.tax_amount + 
            self.rush_fee
        )
        
        # حساب الربح
        self.profit_amount = self.total_cost * (self.profit_margin_percentage / 100)
        
        # حساب السعر النهائي
        self.final_price = self.total_cost + self.profit_amount

    def update_from_calculations(self):
        """
        تحديث الملخص من حسابات التكلفة الحالية
        """
        calculations = self.order.calculations.filter(is_current=True)
        
        for calc in calculations:
            if calc.calculation_type == CalculationType.MATERIAL:
                self.material_cost = calc.total_cost
            elif calc.calculation_type == CalculationType.PRINTING:
                self.printing_cost = calc.total_cost
            elif calc.calculation_type == CalculationType.FINISHING:
                self.finishing_cost = calc.total_cost
            elif calc.calculation_type == CalculationType.DESIGN:
                self.design_cost = calc.total_cost
        
        self.calculate_all()
        self.save()

    @property
    def cost_breakdown(self):
        """
        تفصيل التكاليف كنسبة مئوية
        """
        if self.subtotal > 0:
            return {
                'material_percentage': float((self.material_cost / self.subtotal) * 100),
                'printing_percentage': float((self.printing_cost / self.subtotal) * 100),
                'finishing_percentage': float((self.finishing_cost / self.subtotal) * 100),
                'design_percentage': float((self.design_cost / self.subtotal) * 100),
                'other_percentage': float((self.other_costs / self.subtotal) * 100),
            }
        return {}


__all__ = ['CostCalculation', 'OrderSummary']
