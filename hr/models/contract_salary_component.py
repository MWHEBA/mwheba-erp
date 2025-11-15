"""
نموذج بنود الراتب الثابتة المرتبطة بالعقد
"""
from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal


class ContractSalaryComponent(models.Model):
    """بنود الراتب الثابتة التي تُضاف مع العقد"""
    
    COMPONENT_TYPE_CHOICES = [
        ('earning', 'مستحق'),
        ('deduction', 'مستقطع'),
    ]
    
    CALCULATION_METHOD_CHOICES = [
        ('fixed', 'ثابت'),
        ('formula', 'صيغة حسابية'),
    ]
    
    # الربط بالعقد
    contract = models.ForeignKey(
        'Contract',
        on_delete=models.CASCADE,
        related_name='salary_components',
        verbose_name='العقد'
    )
    
    # القالب (اختياري)
    template = models.ForeignKey(
        'SalaryComponentTemplate',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='contract_instances',
        verbose_name='القالب',
        help_text='القالب المستخدم (اختياري)'
    )
    
    # البيانات الأساسية
    code = models.CharField(
        max_length=50,
        verbose_name='الكود',
        help_text='مثل: BASIC, HOUSING, TRANSPORT'
    )
    name = models.CharField(
        max_length=100,
        verbose_name='اسم البند'
    )
    component_type = models.CharField(
        max_length=20,
        choices=COMPONENT_TYPE_CHOICES,
        verbose_name='نوع البند'
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
        verbose_name = 'بند راتب العقد'
        verbose_name_plural = 'بنود رواتب العقود'
        ordering = ['component_type', 'order', 'id']
        indexes = [
            models.Index(fields=['contract', 'component_type']),
            models.Index(fields=['code']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['contract', 'code'],
                name='unique_contract_component_code'
            ),
        ]
    
    def __str__(self):
        return f"{self.contract.contract_number} - {self.name}"
    
    def get_display_amount(self):
        """عرض المبلغ بشكل مناسب حسب طريقة الحساب"""
        if self.calculation_method == 'fixed':
            return f"{self.amount} ج.م"
        elif self.calculation_method == 'percentage':
            return f"{self.percentage}%"
        elif self.calculation_method == 'formula':
            return self.formula
        return str(self.amount)
    
    def copy_to_employee_component(self, employee):
        """
        نسخ هذا البند إلى SalaryComponent للموظف
        يُستخدم عند تفعيل العقد
        
        المنطق:
        1. البحث عن بند بنفس الكود (مهما كان مصدره)
        2. إذا وُجد، تحديثه وتحويله لبند عقد
        3. إذا لم يوجد، إنشاء بند جديد
        """
        from hr.models import SalaryComponent
        from django.utils import timezone
        
        # البحث عن أي بند بنفس الكود للموظف (مهما كان مصدره)
        existing = SalaryComponent.objects.filter(
            employee=employee,
            code=self.code
        ).first()
        
        if existing:
            # تحديث البند الموجود وتحويله لبند عقد
            existing.contract = self.contract
            existing.source_contract_component = self
            existing.is_from_contract = True
            existing.source = 'contract'  # تغيير المصدر لعقد
            existing.name = self.name
            existing.component_type = self.component_type
            existing.calculation_method = self.calculation_method
            existing.amount = self.amount
            existing.percentage = self.percentage
            existing.formula = self.formula
            existing.is_basic = self.is_basic
            existing.is_taxable = self.is_taxable
            existing.is_fixed = self.is_fixed
            existing.affects_overtime = self.affects_overtime
            existing.order = self.order
            existing.show_in_payslip = self.show_in_payslip
            existing.notes = self.notes
            existing.effective_from = self.contract.start_date
            existing.effective_to = self.contract.end_date
            existing.is_active = True
            existing.save()
            return existing
        else:
            code = self.code
            
            # إنشاء البند الجديد
            component = SalaryComponent.objects.create(
                employee=employee,
                contract=self.contract,
                source_contract_component=self,
                is_from_contract=True,
                source='contract',  # تحديد المصدر كعقد
                template=self.template,
                code=code,
                name=self.name,
                component_type=self.component_type,
                calculation_method=self.calculation_method,
                amount=self.amount,
                percentage=self.percentage,
                formula=self.formula,
                is_basic=self.is_basic,
                is_taxable=self.is_taxable,
                is_fixed=self.is_fixed,
                affects_overtime=self.affects_overtime,
                order=self.order,
                show_in_payslip=self.show_in_payslip,
                notes=self.notes,
                effective_from=self.contract.start_date,
                effective_to=self.contract.end_date,
                is_active=True
            )
            
            return component
