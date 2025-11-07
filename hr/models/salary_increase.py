"""
نماذج نظام زيادات المرتبات من الإعدادات
"""
from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

User = get_user_model()


class SalaryIncreaseTemplate(models.Model):
    """قالب زيادة المرتب - سياسة عامة قابلة لإعادة الاستخدام"""
    
    INCREASE_TYPE_CHOICES = [
        ('percentage', 'نسبة مئوية'),
        ('fixed', 'مبلغ ثابت'),
        ('performance', 'حسب الأداء'),
        ('inflation', 'حسب التضخم'),
        ('seniority', 'حسب الأقدمية'),
    ]
    
    FREQUENCY_CHOICES = [
        ('annual', 'سنوي'),
        ('semi_annual', 'نصف سنوي'),
        ('quarterly', 'ربع سنوي'),
        ('monthly', 'شهري'),
    ]
    
    # معلومات أساسية
    name = models.CharField(
        max_length=200,
        verbose_name='اسم القالب',
        help_text='مثال: زيادة سنوية 10%'
    )
    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='الكود',
        help_text='كود فريد للقالب'
    )
    description = models.TextField(
        blank=True,
        verbose_name='الوصف'
    )
    
    # نوع الزيادة
    increase_type = models.CharField(
        max_length=20,
        choices=INCREASE_TYPE_CHOICES,
        verbose_name='نوع الزيادة'
    )
    
    # القيم الافتراضية
    default_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name='النسبة الافتراضية (%)',
        help_text='مثال: 10 للزيادة 10%'
    )
    default_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        verbose_name='المبلغ الافتراضي'
    )
    
    # التكرار
    frequency = models.CharField(
        max_length=20,
        choices=FREQUENCY_CHOICES,
        default='annual',
        verbose_name='التكرار'
    )
    
    # الشروط
    min_service_months = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name='الحد الأدنى لأشهر الخدمة',
        help_text='مثال: 12 لتطبيق الزيادة بعد سنة'
    )
    min_performance_rating = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
        verbose_name='الحد الأدنى لتقييم الأداء',
        help_text='مثال: 3.5 من 5'
    )
    
    # القيود
    max_increase_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name='الحد الأقصى لنسبة الزيادة (%)'
    )
    max_increase_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        verbose_name='الحد الأقصى لمبلغ الزيادة'
    )
    
    # الحالة
    is_active = models.BooleanField(
        default=True,
        verbose_name='نشط'
    )
    is_default = models.BooleanField(
        default=False,
        verbose_name='افتراضي',
        help_text='القالب الافتراضي للخطط الجديدة'
    )
    
    # التواريخ
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='تاريخ التحديث')
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='created_increase_templates',
        verbose_name='أنشئ بواسطة'
    )
    
    class Meta:
        verbose_name = 'قالب زيادة المرتب'
        verbose_name_plural = 'قوالب زيادات المرتبات'
        ordering = ['-is_default', 'name']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['is_active', 'is_default']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.get_increase_type_display()})"
    
    def clean(self):
        """التحقق من صحة البيانات"""
        from django.core.exceptions import ValidationError
        
        # التحقق من وجود قيمة افتراضية حسب النوع
        if self.increase_type == 'percentage' and not self.default_percentage:
            raise ValidationError({
                'default_percentage': 'يجب تحديد النسبة الافتراضية لنوع النسبة المئوية'
            })
        
        if self.increase_type == 'fixed' and not self.default_amount:
            raise ValidationError({
                'default_amount': 'يجب تحديد المبلغ الافتراضي لنوع المبلغ الثابت'
            })


class AnnualIncreasePlan(models.Model):
    """خطة الزيادات السنوية"""
    
    STATUS_CHOICES = [
        ('draft', 'مسودة'),
        ('approved', 'معتمدة'),
        ('in_progress', 'قيد التنفيذ'),
        ('completed', 'مكتملة'),
        ('cancelled', 'ملغية'),
    ]
    
    # معلومات أساسية
    name = models.CharField(
        max_length=200,
        verbose_name='اسم الخطة',
        help_text='مثال: خطة الزيادات 2025'
    )
    year = models.IntegerField(
        verbose_name='السنة',
        validators=[MinValueValidator(2020), MaxValueValidator(2100)]
    )
    template = models.ForeignKey(
        SalaryIncreaseTemplate,
        on_delete=models.PROTECT,
        related_name='annual_plans',
        verbose_name='القالب'
    )
    
    # التواريخ
    effective_date = models.DateField(
        verbose_name='تاريخ السريان',
        help_text='التاريخ المخطط لتطبيق الزيادات'
    )
    approval_date = models.DateField(
        null=True,
        blank=True,
        verbose_name='تاريخ الاعتماد'
    )
    
    # الميزانية
    total_budget = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        verbose_name='إجمالي الميزانية',
        help_text='الميزانية المخصصة للزيادات'
    )
    allocated_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='المبلغ المخصص',
        help_text='المبلغ المخصص فعلياً للموظفين'
    )
    
    # الحالة
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        verbose_name='الحالة'
    )
    
    # ملاحظات
    notes = models.TextField(
        blank=True,
        verbose_name='ملاحظات'
    )
    
    # التواريخ
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='تاريخ التحديث')
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='created_increase_plans',
        verbose_name='أنشئ بواسطة'
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='approved_increase_plans',
        verbose_name='اعتمد بواسطة'
    )
    
    class Meta:
        verbose_name = 'خطة الزيادات السنوية'
        verbose_name_plural = 'خطط الزيادات السنوية'
        ordering = ['-year', '-created_at']
        unique_together = ['name', 'year']
        indexes = [
            models.Index(fields=['year', 'status']),
            models.Index(fields=['effective_date']),
        ]
    
    def __str__(self):
        return f"{self.name} - {self.year}"
    
    def calculate_total_cost(self):
        """حساب التكلفة الإجمالية للخطة"""
        increases = self.planned_increases.filter(status='approved')
        return sum(inc.calculated_amount or Decimal('0') for inc in increases)
    
    def get_eligible_employees(self):
        """الحصول على الموظفين المؤهلين للزيادة"""
        from .employee import Employee
        
        # الموظفين النشطين
        employees = Employee.objects.filter(status='active')
        
        # تطبيق شروط القالب
        if self.template.min_service_months > 0:
            min_hire_date = timezone.now().date() - timedelta(
                days=self.template.min_service_months * 30
            )
            employees = employees.filter(hire_date__lte=min_hire_date)
        
        return employees
    
    def approve(self, approved_by):
        """اعتماد الخطة"""
        self.status = 'approved'
        self.approval_date = timezone.now().date()
        self.approved_by = approved_by
        self.save()
    
    def start_execution(self):
        """بدء تنفيذ الخطة"""
        if self.status != 'approved':
            return False, "يجب اعتماد الخطة أولاً"
        
        self.status = 'in_progress'
        self.save()
        return True, "تم بدء تنفيذ الخطة"
    
    def complete(self):
        """إكمال الخطة"""
        self.status = 'completed'
        self.save()


class PlannedIncrease(models.Model):
    """زيادة مخططة ضمن خطة سنوية"""
    
    STATUS_CHOICES = [
        ('pending', 'قيد الانتظار'),
        ('approved', 'معتمدة'),
        ('rejected', 'مرفوضة'),
        ('applied', 'مطبقة'),
    ]
    
    # الربط
    plan = models.ForeignKey(
        AnnualIncreasePlan,
        on_delete=models.CASCADE,
        related_name='planned_increases',
        verbose_name='الخطة'
    )
    employee = models.ForeignKey(
        'Employee',
        on_delete=models.CASCADE,
        related_name='planned_increases',
        verbose_name='الموظف'
    )
    contract = models.ForeignKey(
        'Contract',
        on_delete=models.CASCADE,
        related_name='planned_increases',
        verbose_name='العقد'
    )
    
    # القيم
    current_salary = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='الراتب الحالي'
    )
    increase_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='نسبة الزيادة (%)'
    )
    increase_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='مبلغ الزيادة'
    )
    calculated_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='المبلغ المحسوب'
    )
    new_salary = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='الراتب الجديد'
    )
    
    # معلومات إضافية
    performance_rating = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
        verbose_name='تقييم الأداء'
    )
    justification = models.TextField(
        blank=True,
        verbose_name='المبرر'
    )
    
    # الحالة
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='الحالة'
    )
    
    # التطبيق
    applied_date = models.DateField(
        null=True,
        blank=True,
        verbose_name='تاريخ التطبيق'
    )
    contract_increase = models.OneToOneField(
        'ContractIncrease',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='planned_increase',
        verbose_name='الزيادة المطبقة'
    )
    
    # التواريخ
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='تاريخ التحديث')
    approved_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='approved_increases',
        verbose_name='اعتمد بواسطة'
    )
    
    class Meta:
        verbose_name = 'زيادة مخططة'
        verbose_name_plural = 'الزيادات المخططة'
        ordering = ['plan', 'employee']
        unique_together = ['plan', 'employee']
        indexes = [
            models.Index(fields=['plan', 'status']),
            models.Index(fields=['employee', 'status']),
        ]
    
    def __str__(self):
        return f"{self.employee.get_full_name_ar()} - {self.plan.name}"
    
    def calculate_increase(self):
        """حساب مبلغ الزيادة"""
        if self.plan.template.increase_type == 'percentage' and self.increase_percentage:
            self.calculated_amount = (
                self.current_salary * self.increase_percentage / Decimal('100')
            )
        else:
            self.calculated_amount = self.increase_amount or Decimal('0')
        
        self.new_salary = self.current_salary + self.calculated_amount
        return self.calculated_amount
    
    def apply_to_contract(self, applied_by):
        """تطبيق الزيادة على العقد"""
        from .contract import ContractIncrease
        
        if self.status != 'approved':
            return False, "الزيادة غير معتمدة"
        
        if self.contract_increase:
            return False, "الزيادة مطبقة بالفعل"
        
        # إنشاء ContractIncrease
        contract_increase = ContractIncrease.objects.create(
            contract=self.contract,
            increase_number=self.contract.scheduled_increases.count() + 1,
            increase_type='percentage' if self.increase_percentage else 'fixed',
            increase_percentage=self.increase_percentage,
            increase_amount=self.calculated_amount,
            months_from_start=0,  # تطبيق فوري
            scheduled_date=self.plan.effective_date,
            status='pending',
            created_by=applied_by,
            notes=f'زيادة من خطة: {self.plan.name}'
        )
        
        # تطبيق الزيادة
        success, message = contract_increase.apply_increase(applied_by)
        
        if success:
            self.status = 'applied'
            self.applied_date = timezone.now().date()
            self.contract_increase = contract_increase
            self.save()
        
        return success, message
    
    def approve(self, approved_by):
        """اعتماد الزيادة"""
        self.status = 'approved'
        self.approved_by = approved_by
        self.save()
    
    def reject(self):
        """رفض الزيادة"""
        self.status = 'rejected'
        self.save()


class EmployeeIncreaseCategory(models.Model):
    """فئة الموظف لتحديد سياسة الزيادة"""
    
    # معلومات أساسية
    name = models.CharField(
        max_length=100,
        verbose_name='اسم الفئة',
        help_text='مثال: موظفين إداريين، مديرين، فنيين'
    )
    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='الكود'
    )
    description = models.TextField(
        blank=True,
        verbose_name='الوصف'
    )
    
    # القالب الافتراضي
    default_template = models.ForeignKey(
        SalaryIncreaseTemplate,
        on_delete=models.PROTECT,
        related_name='employee_categories',
        verbose_name='القالب الافتراضي'
    )
    
    # الحالة
    is_active = models.BooleanField(
        default=True,
        verbose_name='نشط'
    )
    
    # التواريخ
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='تاريخ التحديث')
    
    class Meta:
        verbose_name = 'فئة موظف للزيادات'
        verbose_name_plural = 'فئات الموظفين للزيادات'
        ordering = ['name']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return self.name
