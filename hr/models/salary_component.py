"""
نموذج مكونات الراتب
"""
from django.db import models
from django.core.validators import MinValueValidator
from django.db.models import Q
from decimal import Decimal


class SalaryComponent(models.Model):
    """نموذج مكونات الراتب (المستحقات والاستقطاعات)"""
    
    COMPONENT_TYPE_CHOICES = [
        ('earning', 'مستحق'),
        ('deduction', 'مستقطع'),
    ]
    
    CALCULATION_METHOD_CHOICES = [
        ('fixed', 'ثابت'),
        ('percentage', 'نسبة مئوية'),
        ('formula', 'صيغة حسابية'),
    ]
    
    # الربط (واحد منهم فقط)
    template = models.ForeignKey(
        'SalaryComponentTemplate',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='instances',
        verbose_name='القالب',
        help_text='القالب المستخدم لإنشاء هذا البند (اختياري)'
    )
    
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
        related_name='employee_salary_components',
        verbose_name='العقد',
        help_text='العقد الذي تم إضافة البند فيه (اختياري)'
    )
    
    # المصدر (إذا كان منسوخ من العقد)
    source_contract_component = models.ForeignKey(
        'ContractSalaryComponent',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='copied_components',
        verbose_name='بند العقد المصدر',
        help_text='البند الأصلي في العقد (إن كان منسوخاً)'
    )
    
    # هل منسوخ من العقد؟
    is_from_contract = models.BooleanField(
        default=False,
        verbose_name='منسوخ من العقد',
        help_text='هل هذا البند منسوخ من بنود العقد الثابتة؟'
    )
    
    # البيانات الأساسية
    code = models.CharField(
        max_length=50,
        verbose_name='الكود',
        help_text='مثل: BASIC, HOUSING, TRANSPORT'
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
    
    # طريقة الحساب
    calculation_method = models.CharField(
        max_length=20,
        choices=CALCULATION_METHOD_CHOICES,
        default='fixed',
        verbose_name='طريقة الحساب'
    )
    
    # القيم
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name='المبلغ الثابت'
    )
    percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='النسبة المئوية',
        help_text='من الراتب الأساسي'
    )
    formula = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='الصيغة الحسابية',
        help_text='مثال: BASIC * 0.1 + 500'
    )
    
    # الخصائص
    is_basic = models.BooleanField(
        default=False,
        verbose_name='راتب أساسي',
        help_text='هل هذا هو الراتب الأساسي؟'
    )
    is_taxable = models.BooleanField(
        default=True,
        verbose_name='خاضع للضريبة'
    )
    is_fixed = models.BooleanField(
        default=True,
        verbose_name='ثابت شهرياً'
    )
    affects_overtime = models.BooleanField(
        default=False,
        verbose_name='يؤثر على حساب الإضافي'
    )
    
    # الترتيب والعرض
    order = models.IntegerField(
        default=0,
        verbose_name='الترتيب'
    )
    show_in_payslip = models.BooleanField(
        default=True,
        verbose_name='يظهر في قسيمة الراتب'
    )
    
    # الفترة الزمنية
    effective_from = models.DateField(
        null=True,
        blank=True,
        verbose_name='ساري من'
    )
    effective_to = models.DateField(
        null=True,
        blank=True,
        verbose_name='ساري حتى'
    )
    
    # الحالة
    is_active = models.BooleanField(
        default=True,
        verbose_name='نشط'
    )
    
    # الحساب المحاسبي (للخصومات والمستحقات)
    account_code = models.CharField(
        max_length=20,
        blank=True,
        verbose_name='رمز الحساب المحاسبي',
        help_text='رمز الحساب المحاسبي المرتبط بهذا البند (اختياري)'
    )
    
    # ملاحظات
    notes = models.TextField(
        blank=True,
        verbose_name='ملاحظات'
    )
    
    # التواريخ
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='تاريخ الإضافة'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='تاريخ التحديث'
    )
    
    class Meta:
        verbose_name = 'مكون راتب'
        verbose_name_plural = 'مكونات الرواتب'
        ordering = ['component_type', 'order', 'id']
        indexes = [
            models.Index(fields=['employee', 'component_type', 'is_active']),
            models.Index(fields=['contract']),
            models.Index(fields=['code']),
            models.Index(fields=['effective_from', 'effective_to']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['employee', 'code'],
                name='unique_employee_component_code'
            ),
        ]
    
    def __str__(self):
        return f"{self.get_component_type_display()} - {self.name}: {self.amount}"
    
    def get_formula_display(self):
        """عرض الصيغة بالعربي"""
        if not self.formula:
            return ''
        
        # استبدال المتغيرات الإنجليزية بالعربية
        formula_ar = self.formula
        formula_ar = formula_ar.replace('basic', 'الأساسي')
        formula_ar = formula_ar.replace('BASIC', 'الأساسي')
        formula_ar = formula_ar.replace('gross', 'الإجمالي')
        formula_ar = formula_ar.replace('GROSS', 'الإجمالي')
        formula_ar = formula_ar.replace('days', 'الأيام')
        formula_ar = formula_ar.replace('DAYS', 'الأيام')
        
        return formula_ar
    
    def calculate_amount(self, context):
        """
        حساب المبلغ بناءً على طريقة الحساب
        
        Args:
            context: dict يحتوي على:
                - basic_salary: الراتب الأساسي
                - gross_salary: إجمالي الراتب
                - worked_days: أيام العمل
                - etc.
        
        Returns:
            Decimal: المبلغ المحسوب
        """
        if self.calculation_method == 'fixed':
            return self.amount
        
        elif self.calculation_method == 'percentage':
            basic = context.get('basic_salary', Decimal('0'))
            if self.percentage:
                return basic * (self.percentage / Decimal('100'))
            return Decimal('0')
        
        elif self.calculation_method == 'formula':
            return self._evaluate_formula(context)
        
        return self.amount
    
    def _evaluate_formula(self, context):
        """تقييم الصيغة الحسابية بشكل آمن"""
        if not self.formula:
            return self.amount
        
        try:
            formula = self.formula.upper()
            
            # استبدال المتغيرات
            replacements = {
                'BASIC': str(context.get('basic_salary', 0)),
                'GROSS': str(context.get('gross_salary', 0)),
                'DAYS': str(context.get('worked_days', 30)),
            }
            
            for var, value in replacements.items():
                formula = formula.replace(var, value)
            
            # تقييم آمن (فقط عمليات حسابية)
            allowed_chars = set('0123456789.+-*/() ')
            if not all(c in allowed_chars for c in formula):
                return self.amount
            
            result = eval(formula, {"__builtins__": {}}, {})
            return Decimal(str(result))
        except:
            return self.amount
