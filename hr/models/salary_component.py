"""
نموذج مكونات الراتب
"""
from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal


class SalaryComponent(models.Model):
    """نموذج مكونات الراتب (المستحقات والاستقطاعات)"""
    
    COMPONENT_TYPE_CHOICES = [
        ('earning', 'مستحق'),
        ('deduction', 'مستقطع'),
    ]
    
    # الموظف (أساسي - البنود تتبع الموظف)
    employee = models.ForeignKey(
        'Employee',
        on_delete=models.CASCADE,
        related_name='salary_components',
        verbose_name='الموظف'
    )
    
    # العقد (اختياري - للربط فقط)
    contract = models.ForeignKey(
        'Contract',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='contract_components',
        verbose_name='العقد',
        help_text='العقد الذي تم إضافة البند فيه (اختياري)'
    )
    
    component_type = models.CharField(
        max_length=20,
        choices=COMPONENT_TYPE_CHOICES,
        verbose_name='نوع المكون'
    )
    name = models.CharField(
        max_length=100,
        verbose_name='بند الراتب'
    )
    formula = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='الصيغة الحسابية',
        help_text='مثال: basic * 0.1 أو basic + 500'
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name='المبلغ'
    )
    order = models.IntegerField(
        default=0,
        verbose_name='الترتيب'
    )
    is_basic = models.BooleanField(
        default=False,
        verbose_name='بند أساسي'
    )
    is_taxable = models.BooleanField(
        default=True,
        verbose_name='خاضع للضريبة'
    )
    is_fixed = models.BooleanField(
        default=True,
        verbose_name='ثابت شهرياً'
    )
    notes = models.TextField(
        blank=True,
        verbose_name='ملاحظات'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='تاريخ الإضافة'
    )
    
    class Meta:
        verbose_name = 'مكون راتب'
        verbose_name_plural = 'مكونات الرواتب'
        ordering = ['component_type', 'order', 'id']
        indexes = [
            models.Index(fields=['employee', 'component_type']),
            models.Index(fields=['contract']),
        ]
    
    def __str__(self):
        return f"{self.get_component_type_display()} - {self.name}: {self.amount}"
    
    def calculate_amount(self, basic_salary):
        """حساب المبلغ بناءً على الصيغة الحسابية"""
        if not self.formula:
            return self.amount
        
        try:
            # استبدال basic بالراتب الأساسي
            formula = self.formula.replace('basic', str(basic_salary))
            # تقييم الصيغة بشكل آمن
            result = eval(formula, {"__builtins__": {}}, {})
            return Decimal(str(result))
        except:
            return self.amount
