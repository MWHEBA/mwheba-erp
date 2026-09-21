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
    work_location = models.ForeignKey(
        'WorkLocation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employees',
        verbose_name='مقر العمل المعتمد'
    )
    allow_mobile_attendance = models.BooleanField(
        default=False,
        verbose_name='السماح ببصمة الموبايل GPS',
        help_text='تمكين الموظف من تسجيل الحضور عبر تطبيق الموبايل PWA'
    )
    allowed_all_locations = models.BooleanField(
        default=False,
        verbose_name='السماح بالبصمة في كافة المقرات (موظف متنقل)',
        help_text='تمكين الموظف من البصمة في أي فرع أو مقر نشط للشركة'
    )
    allow_field_visits = models.BooleanField(
        default=False,
        verbose_name='السماح بالزيارات الميدانية والمأموريات',
        help_text='تمكين تسجيل البصمة الميدانية خارج مقرات الشركة بدون التقيد بنطاق جغرافي محدد'
    )
    registered_device_uuid = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='معرف الجهاز المعتمد',
        help_text='بصمة عتاد الهاتف المرتبط بحساب الموظف لمنع تبادل الهواتف'
    )
    device_bound_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='تاريخ ربط الجهاز'
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
            ("can_manual_attendance", "إمكانية إضافة وتعديل الحضور اليدوي"),
            ("can_import_attendance", "إمكانية استيراد الحضور من Excel"),
            ("can_reset_device_binding", "إمكانية إعادة تعيين ربط جهاز الموظف"),
        ]
    
    def __str__(self):
        return f"{self.employee_number} - {self.get_full_name_ar()}"
    
    def get_full_name_ar(self):
        """الحصول على الاسم الكامل بالعربية"""
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
    
    def get_first_name(self):
        """الحصول على الاسم الأول"""
        if self.name:
            return self.name.split()[0]
        return ""
    
    def get_last_name(self):
        """الحصول على الاسم الأخير"""
        if self.name:
            parts = self.name.split()
            return parts[-1] if len(parts) > 1 else parts[0]
    @property
    def is_active(self):
        """التحقق مما إذا كان الموظف نشطاً في الخدمة"""
        return self.status == 'active'

    @property
    def age(self):
        """العمر بالسنوات"""
        return self.get_age()

    def get_age(self):
        """حساب العمر بالسنوات"""
        if self.birth_date:
            from datetime import date
            today = date.today()
            return today.year - self.birth_date.year - (
                (today.month, today.day) < (self.birth_date.month, self.birth_date.day)
            )
        return None
    
    @property
    def years_of_service(self):
        """سنوات الخدمة للموظف"""
        return self.get_service_years() or 0

    def get_service_years(self):
        """حساب سنوات الخدمة"""
        if self.hire_date:
            from datetime import date
            end_date = self.termination_date if self.termination_date else date.today()
            return end_date.year - self.hire_date.year - (
                (end_date.month, end_date.day) < (self.hire_date.month, self.hire_date.day)
            )
        return None
    
    def get_active_contract(self):
        """الحصول على العقد النشط الحالي للموظف"""
        return self.contracts.filter(status='active').first()
    
    def get_gender_display_ar(self):
        """عرض الجنس بالعربية"""
        return dict(self.GENDER_CHOICES).get(self.gender, self.gender)
    
    def get_marital_status_display_ar(self):
        """عرض الحالة الاجتماعية بالعربية"""
        return dict(self.MARITAL_STATUS_CHOICES).get(self.marital_status, self.marital_status)
    
    def get_status_display_ar(self):
        """عرض الحالة بالعربية"""
        return dict(self.STATUS_CHOICES).get(self.status, self.status)
    
    def clean(self):
        from django.core.exceptions import ValidationError
        if self.hire_date and self.birth_date:
            age_at_hire = (self.hire_date - self.birth_date).days / 365.25
            if age_at_hire < 18:
                raise ValidationError({'hire_date': 'عمر الموظف عند التعيين يجب أن يكون 18 سنة على الأقل'})
        
        if self.termination_date and self.hire_date:
            if self.termination_date < self.hire_date:
                raise ValidationError({'termination_date': 'تاريخ إنهاء الخدمة لا يمكن أن يكون قبل تاريخ التعيين'})
    
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
