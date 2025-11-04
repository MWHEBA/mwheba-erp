"""
نموذج العقود
"""
from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import FileExtensionValidator
from datetime import date, timedelta

User = get_user_model()


class Contract(models.Model):
    """نموذج عقد الموظف"""
    
    CONTRACT_TYPE_CHOICES = [
        ('permanent', 'دائم'),
        ('temporary', 'مؤقت'),
        ('contract', 'عقد محدد المدة'),
        ('internship', 'تدريب'),
        ('part_time', 'دوام جزئي'),
    ]
    
    STATUS_CHOICES = [
        ('draft', 'مسودة'),
        ('active', 'ساري'),
        ('expired', 'منتهي'),
        ('renewed', 'تم التجديد'),
        ('terminated', 'منهي'),
    ]
    
    # معلومات العقد الأساسية
    contract_number = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='رقم العقد'
    )
    employee = models.ForeignKey(
        'Employee',
        on_delete=models.CASCADE,
        related_name='contracts',
        verbose_name='الموظف'
    )
    contract_type = models.CharField(
        max_length=20,
        choices=CONTRACT_TYPE_CHOICES,
        verbose_name='نوع العقد'
    )
    
    # التواريخ
    start_date = models.DateField(verbose_name='تاريخ البداية')
    end_date = models.DateField(
        null=True,
        blank=True,
        verbose_name='تاريخ النهاية'
    )
    probation_period_months = models.IntegerField(
        default=3,
        verbose_name='فترة التجربة (بالأشهر)'
    )
    probation_end_date = models.DateField(
        null=True,
        blank=True,
        verbose_name='تاريخ انتهاء التجربة'
    )
    
    # الراتب والتعويضات
    basic_salary = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='الراتب الأساسي'
    )
    housing_allowance = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='بدل السكن'
    )
    transportation_allowance = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='بدل المواصلات'
    )
    other_allowances = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='بدلات أخرى'
    )
    total_salary = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='إجمالي الراتب'
    )
    
    # ساعات العمل
    working_hours_per_day = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=8,
        verbose_name='ساعات العمل اليومية'
    )
    working_days_per_week = models.IntegerField(
        default=5,
        verbose_name='أيام العمل الأسبوعية'
    )
    
    # الإجازات
    annual_leave_days = models.IntegerField(
        default=21,
        verbose_name='أيام الإجازة السنوية'
    )
    sick_leave_days = models.IntegerField(
        default=30,
        verbose_name='أيام الإجازة المرضية'
    )
    
    # البنود والشروط
    terms_and_conditions = models.TextField(
        blank=True,
        verbose_name='البنود والشروط'
    )
    special_clauses = models.TextField(
        blank=True,
        verbose_name='بنود خاصة'
    )
    
    # ملف العقد
    contract_file = models.FileField(
        upload_to='contracts/%Y/%m/',
        null=True,
        blank=True,
        validators=[FileExtensionValidator(['pdf', 'doc', 'docx'])],
        verbose_name='ملف العقد'
    )
    
    # التجديد
    auto_renew = models.BooleanField(
        default=False,
        verbose_name='تجديد تلقائي'
    )
    renewal_notice_days = models.IntegerField(
        default=30,
        verbose_name='أيام الإشعار قبل التجديد'
    )
    renewed_to = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='renewed_from',
        verbose_name='تم التجديد إلى'
    )
    
    # الحالة
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        verbose_name='الحالة'
    )
    
    # ملاحظات
    notes = models.TextField(blank=True, verbose_name='ملاحظات')
    
    # التواريخ والمستخدمين
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='تاريخ التحديث')
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='created_contracts',
        verbose_name='أنشئ بواسطة'
    )
    signed_date = models.DateField(
        null=True,
        blank=True,
        verbose_name='تاريخ التوقيع'
    )
    
    class Meta:
        verbose_name = 'عقد'
        verbose_name_plural = 'العقود'
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['contract_number']),
            models.Index(fields=['employee', 'status']),
            models.Index(fields=['start_date', 'end_date']),
        ]
        permissions = [
            ("can_manage_contracts", "إدارة العقود"),
            ("can_sign_contracts", "توقيع العقود"),
            ("can_terminate_contracts", "إنهاء العقود"),
        ]
    
    def __str__(self):
        return f"{self.contract_number} - {self.employee.get_full_name_ar()}"
    
    def save(self, *args, **kwargs):
        # حساب إجمالي الراتب
        self.total_salary = (
            self.basic_salary +
            self.housing_allowance +
            self.transportation_allowance +
            self.other_allowances
        )
        
        # حساب تاريخ انتهاء التجربة
        if self.start_date and self.probation_period_months:
            self.probation_end_date = self.start_date + timedelta(
                days=self.probation_period_months * 30
            )
        
        super().save(*args, **kwargs)
    
    @property
    def is_active(self):
        """هل العقد ساري"""
        return self.status == 'active'
    
    @property
    def is_expired(self):
        """هل العقد منتهي"""
        if self.end_date:
            return date.today() > self.end_date
        return False
    
    @property
    def days_until_expiry(self):
        """عدد الأيام المتبقية حتى انتهاء العقد"""
        if self.end_date:
            delta = self.end_date - date.today()
            return delta.days if delta.days > 0 else 0
        return None
    
    @property
    def needs_renewal_notice(self):
        """هل يحتاج العقد لإشعار تجديد"""
        if self.end_date and self.days_until_expiry is not None:
            return self.days_until_expiry <= self.renewal_notice_days
        return False
    
    @property
    def duration_months(self):
        """مدة العقد بالأشهر"""
        if self.start_date and self.end_date:
            delta = self.end_date - self.start_date
            return delta.days // 30
        return None
    
    def renew(self, new_end_date, created_by):
        """تجديد العقد"""
        new_contract = Contract.objects.create(
            contract_number=f"{self.contract_number}-R",
            employee=self.employee,
            contract_type=self.contract_type,
            start_date=self.end_date + timedelta(days=1),
            end_date=new_end_date,
            basic_salary=self.basic_salary,
            housing_allowance=self.housing_allowance,
            transportation_allowance=self.transportation_allowance,
            other_allowances=self.other_allowances,
            working_hours_per_day=self.working_hours_per_day,
            working_days_per_week=self.working_days_per_week,
            annual_leave_days=self.annual_leave_days,
            sick_leave_days=self.sick_leave_days,
            terms_and_conditions=self.terms_and_conditions,
            auto_renew=self.auto_renew,
            renewal_notice_days=self.renewal_notice_days,
            status='active',
            created_by=created_by
        )
        
        # تحديث العقد الحالي
        self.status = 'renewed'
        self.renewed_to = new_contract
        self.save()
        
        return new_contract
    
    def terminate(self, termination_date=None):
        """إنهاء العقد"""
        self.status = 'terminated'
        if termination_date:
            self.end_date = termination_date
        self.save()


class ContractAmendment(models.Model):
    """نموذج تعديلات العقد"""
    
    AMENDMENT_TYPE_CHOICES = [
        ('salary_increase', 'زيادة راتب'),
        ('position_change', 'تغيير منصب'),
        ('extension', 'تمديد'),
        ('other', 'أخرى'),
    ]
    
    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name='amendments',
        verbose_name='العقد'
    )
    amendment_number = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='رقم التعديل'
    )
    amendment_type = models.CharField(
        max_length=20,
        choices=AMENDMENT_TYPE_CHOICES,
        verbose_name='نوع التعديل'
    )
    effective_date = models.DateField(verbose_name='تاريخ السريان')
    description = models.TextField(verbose_name='الوصف')
    
    # التغييرات
    old_value = models.TextField(blank=True, verbose_name='القيمة القديمة')
    new_value = models.TextField(blank=True, verbose_name='القيمة الجديدة')
    
    # ملف التعديل
    amendment_file = models.FileField(
        upload_to='contract_amendments/%Y/%m/',
        null=True,
        blank=True,
        validators=[FileExtensionValidator(['pdf', 'doc', 'docx'])],
        verbose_name='ملف التعديل'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        verbose_name='أنشئ بواسطة'
    )
    
    class Meta:
        verbose_name = 'تعديل عقد'
        verbose_name_plural = 'تعديلات العقود'
        ordering = ['-effective_date']
    
    def __str__(self):
        return f"{self.amendment_number} - {self.contract.contract_number}"
