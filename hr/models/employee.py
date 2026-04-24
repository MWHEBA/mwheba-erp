"""
نموذج الموظف
"""
from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import RegexValidator, MinLengthValidator

User = get_user_model()


class Employee(models.Model):
    """نموذج الموظف الشامل"""
    
    GENDER_CHOICES = [
        ('male', 'ذكر'),
        ('female', 'أنثى'),
    ]
    
    MARITAL_STATUS_CHOICES = [
        ('single', 'أعزب'),
        ('married', 'متزوج'),
        ('divorced', 'مطلق'),
        ('widowed', 'أرمل'),
    ]
    
    MILITARY_STATUS_CHOICES = [
        ('completed', 'أدى الخدمة'),
        ('exempted', 'معفى'),
        ('postponed', 'مؤجل'),
        ('not_applicable', 'لا ينطبق'),
    ]
    
    EMPLOYMENT_TYPE_CHOICES = [
        ('full_time', 'دوام كامل'),
        ('part_time', 'دوام جزئي'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'نشط'),
        ('on_leave', 'في إجازة'),
        ('suspended', 'موقوف'),
        ('terminated', 'منتهي الخدمة'),
    ]
    
    # ربط مع المستخدم
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='employee_profile',
        verbose_name='المستخدم',
        null=True,
        blank=True
    )
    
    # معلومات أساسية
    employee_number = models.CharField(
        max_length=20,
        unique=True,
        verbose_name='رقم الموظف'
    )
    name = models.CharField(
        max_length=200,
        verbose_name='اسم الموظف',
        validators=[
            MinLengthValidator(5, message='الاسم يجب أن يكون 5 أحرف على الأقل'),
        ]
    )
    
    # معلومات شخصية
    national_id = models.CharField(
        max_length=14,
        unique=True,
        verbose_name='الرقم القومي',
        validators=[RegexValidator(regex=r'^\d{14}$', message='الرقم القومي يجب أن يكون 14 رقم')]
    )
    birth_date = models.DateField(verbose_name='تاريخ الميلاد')
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, verbose_name='الجنس')
    marital_status = models.CharField(
        max_length=20,
        choices=MARITAL_STATUS_CHOICES,
        verbose_name='الحالة الاجتماعية'
    )
    military_status = models.CharField(
        max_length=20,
        choices=MILITARY_STATUS_CHOICES,
        blank=True,
        verbose_name='الموقف من التجنيد'
    )
    
    # معلومات الاتصال
    personal_email = models.EmailField(verbose_name='البريد الشخصي', blank=True, null=True)
    work_email = models.EmailField(verbose_name='البريد الوظيفي', blank=True, null=True)
    mobile_phone = models.CharField(max_length=15, verbose_name='الهاتف المحمول', blank=True, null=True)
    home_phone = models.CharField(max_length=15, blank=True, null=True, verbose_name='هاتف المنزل')
    address = models.TextField(verbose_name='العنوان', blank=True, null=True)
    city = models.CharField(max_length=100, verbose_name='المدينة', blank=True, null=True)
    postal_code = models.CharField(max_length=10, blank=True, null=True, verbose_name='الرمز البريدي')
    
    # جهة اتصال الطوارئ
    emergency_contact_name = models.CharField(max_length=200, verbose_name='اسم جهة الاتصال للطوارئ', blank=True)
    emergency_contact_relation = models.CharField(max_length=50, verbose_name='صلة القرابة', blank=True)
    emergency_contact_phone = models.CharField(max_length=15, verbose_name='هاتف الطوارئ', blank=True)
    
    # معلومات وظيفية
    department = models.ForeignKey(
        'Department',
        on_delete=models.PROTECT,
        related_name='employees',
        verbose_name='القسم'
    )
    job_title = models.ForeignKey(
        'JobTitle',
        on_delete=models.PROTECT,
        related_name='employees',
        verbose_name='المسمى الوظيفي'
    )
    direct_manager = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subordinates',
        verbose_name='المدير المباشر'
    )
    shift = models.ForeignKey(
        'Shift',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employees',
        verbose_name='الوردية'
    )
    biometric_user_id = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name='رقم الموظف في جهاز البصمة',
        help_text='رقم تعريف الموظف في نظام البصمة'
    )
    attendance_exempt = models.BooleanField(
        default=False,
        verbose_name='معفى من البصمة',
        help_text='موظفون إداريون أو مديرون لا يخضعون لنظام البصمة — يتم اعتماد حضورهم يدوياً'
    )
    hire_date = models.DateField(verbose_name='تاريخ التعيين')
    employment_type = models.CharField(
        max_length=20,
        choices=EMPLOYMENT_TYPE_CHOICES,
        default='full_time',
        verbose_name='نوع التوظيف'
    )
    
    # الحالة
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active',
        verbose_name='الحالة'
    )
    termination_date = models.DateField(null=True, blank=True, verbose_name='تاريخ إنهاء الخدمة')
    termination_reason = models.TextField(blank=True, verbose_name='سبب إنهاء الخدمة')
    is_insurance_only = models.BooleanField(
        default=False,
        verbose_name='موظف تأمين فقط',
        help_text='لا يدخل في كشف الرواتب — يدفع تأمينه للشركة مباشرة'
    )
    
    # الصورة
    photo = models.ImageField(
        upload_to='hr/employees/photos/',
        blank=True,
        null=True,
        verbose_name='الصورة الشخصية'
    )
    
    # التواريخ
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='تاريخ التحديث')
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='created_employees',
        verbose_name='أنشئ بواسطة'
    )
    
    class Meta:
        verbose_name = 'موظف'
        verbose_name_plural = 'الموظفين'
        ordering = ['employee_number']
        indexes = [
            models.Index(fields=['employee_number']),
            models.Index(fields=['national_id']),
            models.Index(fields=['status']),
            models.Index(fields=['department']),
        ]
        permissions = [
            ("can_manage_employees", "إدارة الموظفين"),
            ("can_view_all_employees", "عرض جميع الموظفين"),
            ("can_terminate_employees", "إنهاء خدمة الموظفين"),
        ]
    
    def __str__(self):
        return f"{self.employee_number} - {self.get_full_name_ar()}"
    
    def get_full_name_ar(self):
        """الحصول على الاسم الكامل بالعربية - Backward compatibility"""
        return self.name
    
    def get_masked_national_id(self):
        """إخفاء الرقم القومي - عرض آخر 3 أرقام فقط"""
        if self.national_id:
            return f"***********{self.national_id[-3:]}"
        return ""
    
    def get_masked_mobile(self):
        """إخفاء رقم الموبايل - عرض آخر 4 أرقام فقط"""
        if self.mobile_phone:
            return f"*******{self.mobile_phone[-4:]}"
        return ""
    
    def get_full_name_en(self):
        """الحصول على الاسم الكامل بالإنجليزية - Deprecated"""
        return self.name
    
    @property
    def age(self):
        """حساب العمر"""
        from datetime import date
        today = date.today()
        return today.year - self.birth_date.year - (
            (today.month, today.day) < (self.birth_date.month, self.birth_date.day)
        )
    
    @property
    def years_of_service(self):
        """حساب سنوات الخدمة الفعلية (بالسنوات الكاملة)"""
        from dateutil.relativedelta import relativedelta
        from datetime import date
        return relativedelta(date.today(), self.hire_date).years
    
    @property
    def is_active(self):
        """هل الموظف نشط"""
        return self.status == 'active'
    
    def get_active_contract(self):
        """
        Get employee's active contract
        Returns the first active contract or None
        """
        from .contract import Contract
        return Contract.objects.filter(
            employee=self,
            status='active'
        ).first()
    
    def clean(self):
        """
        Validate employee data
        Issue #21-25: Missing model validations
        """
        from django.core.exceptions import ValidationError
        from django.utils import timezone
        
        errors = {}
        
        # Validate hire date not in future
        if self.hire_date and self.hire_date > timezone.now().date():
            errors['hire_date'] = 'تاريخ التعيين لا يمكن أن يكون في المستقبل'
        
        # Validate birth date not in future
        if self.birth_date and self.birth_date > timezone.now().date():
            errors['birth_date'] = 'تاريخ الميلاد لا يمكن أن يكون في المستقبل'
        
        # Validate age >= 18
        if self.birth_date:
            age = timezone.now().date().year - self.birth_date.year
            if age < 18:
                errors['birth_date'] = 'يجب أن يكون عمر الموظف 18 سنة على الأقل'
        
        # Validate termination date
        if self.termination_date:
            if self.termination_date < self.hire_date:
                errors['termination_date'] = 'تاريخ إنهاء الخدمة لا يمكن أن يكون قبل تاريخ التعيين'
            
            if self.status != 'terminated':
                errors['status'] = 'يجب تغيير الحالة إلى "منتهي الخدمة" عند تحديد تاريخ إنهاء الخدمة'
        
        # Validate status consistency
        if self.status == 'terminated' and not self.termination_date:
            errors['termination_date'] = 'يجب تحديد تاريخ إنهاء الخدمة للموظفين المنتهية خدمتهم'
        
        if errors:
            raise ValidationError(errors)
    
    def save(self, *args, **kwargs):
        """Override save to call clean()"""
        self.full_clean()
        super().save(*args, **kwargs)
