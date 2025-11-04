"""
نموذج قوالب مكونات الراتب الجاهزة
"""
from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal


class SalaryComponentTemplate(models.Model):
    """قوالب مكونات الراتب الجاهزة للاستخدام المتكرر"""
    
    COMPONENT_TYPE_CHOICES = [
        ('earning', 'مستحق'),
        ('deduction', 'مستقطع'),
    ]
    
    name = models.CharField(
        max_length=100,
        verbose_name='اسم البند'
    )
    component_type = models.CharField(
        max_length=20,
        choices=COMPONENT_TYPE_CHOICES,
        verbose_name='نوع المكون'
    )
    formula = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='الصيغة الحسابية',
        help_text='مثال: basic * 0.25 (للنسبة المئوية) أو basic + 500 (لإضافة مبلغ ثابت)'
    )
    default_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name='المبلغ الافتراضي',
        help_text='يُستخدم إذا لم تكن هناك صيغة حسابية'
    )
    description = models.TextField(
        blank=True,
        verbose_name='الوصف'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='نشط'
    )
    order = models.IntegerField(
        default=0,
        verbose_name='الترتيب'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='تاريخ الإنشاء'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='تاريخ التحديث'
    )
    
    class Meta:
        verbose_name = 'قالب مكون راتب'
        verbose_name_plural = 'قوالب مكونات الرواتب'
        ordering = ['component_type', 'order', 'name']
        indexes = [
            models.Index(fields=['component_type', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.get_component_type_display()} - {self.name}"
    
    def get_calculated_amount(self, basic_salary):
        """حساب المبلغ بناءً على الصيغة أو المبلغ الافتراضي"""
        if self.formula:
            try:
                formula = self.formula.replace('basic', str(basic_salary))
                result = eval(formula, {"__builtins__": {}}, {})
                return Decimal(str(result))
            except:
                return self.default_amount
        return self.default_amount
