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
        ('formula', 'صيغة حسابية'),
    ]
    
    # تصنيف البنود حسب المصدر والغرض
    COMPONENT_SOURCE_CHOICES = [
        ('contract', 'من العقد'),
        ('temporary', 'مؤقت'),
        ('personal', 'شخصي'),
        ('exceptional', 'استثنائي'),
        ('adjustment', 'تعديل'),
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
    
    # تصنيف البند
    source = models.CharField(
        max_length=20,
        choices=COMPONENT_SOURCE_CHOICES,
        default='contract',
        verbose_name='مصدر البند',
        help_text='تصنيف البند حسب مصدره والغرض منه'
    )
    
    # خصائص البنود المؤقتة والمتكررة
    is_recurring = models.BooleanField(
        default=True,
        verbose_name='متكرر شهرياً',
        help_text='هل يتكرر هذا البند كل شهر؟'
    )
    
    auto_renew = models.BooleanField(
        default=False,
        verbose_name='تجديد تلقائي',
        help_text='هل يتم تجديد البند تلقائياً عند انتهاء صلاحيته؟'
    )
    
    renewal_period_months = models.IntegerField(
        null=True, 
        blank=True,
        verbose_name='فترة التجديد (شهور)',
        help_text='عدد الشهور للتجديد التلقائي (اتركه فارغاً للتجديد اليدوي)'
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
        source_display = self.get_source_display()
        return f"{self.get_component_type_display()} - {self.name} ({source_display}): {self.amount}"
    
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
    
    def is_temporary(self):
        """هل البند مؤقت (له تاريخ انتهاء)"""
        return self.effective_to is not None
    
    def is_expired(self):
        """هل البند منتهي الصلاحية"""
        if not self.effective_to:
            return False
        from django.utils import timezone
        return timezone.now().date() > self.effective_to
    
    def days_until_expiry(self):
        """عدد الأيام المتبقية حتى انتهاء البند"""
        if not self.effective_to:
            return None
        from django.utils import timezone
        delta = self.effective_to - timezone.now().date()
        return delta.days if delta.days > 0 else 0
    
    def needs_renewal(self):
        """هل البند يحتاج تجديد (قارب على الانتهاء)"""
        if not self.is_temporary() or not self.auto_renew:
            return False
        days_left = self.days_until_expiry()
        if days_left is None:
            return False
        # تنبيه قبل 30 يوم من الانتهاء
        return days_left <= 30
    
    def get_renewal_date(self):
        """حساب تاريخ التجديد القادم"""
        if not self.auto_renew or not self.renewal_period_months or not self.effective_to:
            return None
        
        try:
            from dateutil.relativedelta import relativedelta
            return self.effective_to + relativedelta(months=self.renewal_period_months)
        except ImportError:
            # Fallback: استخدام timedelta (أقل دقة)
            from datetime import timedelta
            days = self.renewal_period_months * 30  # تقريبي
            return self.effective_to + timedelta(days=days)
    
    def auto_classify_source(self):
        """تصنيف تلقائي للبند بناءً على خصائصه"""
        if self.is_from_contract:
            return 'contract'
        elif self.is_temporary():
            # فحص نوع البند المؤقت
            name_lower = self.name.lower()
            if any(word in name_lower for word in ['قرض', 'سلفة', 'مقدم']):
                return 'personal'
            elif any(word in name_lower for word in ['مكافأة', 'حافز', 'بونص']):
                return 'exceptional'
            else:
                return 'temporary'
        else:
            return 'adjustment'
