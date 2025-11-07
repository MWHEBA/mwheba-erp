"""
نموذج الموظف
"""
from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import RegexValidator

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
        ('contract', 'عقد'),
        ('temporary', 'مؤقت'),
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
    first_name_ar = models.CharField(max_length=100, verbose_name='الاسم الأول (عربي)')
    last_name_ar = models.CharField(max_length=100, verbose_name='اسم العائلة (عربي)')
    first_name_en = models.CharField(max_length=100, verbose_name='الاسم الأول (إنجليزي)', blank=True)
    last_name_en = models.CharField(max_length=100, verbose_name='اسم العائلة (إنجليزي)', blank=True)
    
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
    religion = models.CharField(max_length=20, blank=True, verbose_name='الديانة')
    military_status = models.CharField(
        max_length=20,
        choices=MILITARY_STATUS_CHOICES,
        blank=True,
        verbose_name='الموقف من التجنيد'
    )
    
    # معلومات الاتصال
    personal_email = models.EmailField(verbose_name='البريد الشخصي', blank=True)
    work_email = models.EmailField(verbose_name='البريد الوظيفي')
    mobile_phone = models.CharField(max_length=15, verbose_name='الهاتف المحمول')
    home_phone = models.CharField(max_length=15, blank=True, verbose_name='هاتف المنزل')
    address = models.TextField(verbose_name='العنوان')
    city = models.CharField(max_length=100, verbose_name='المدينة')
    postal_code = models.CharField(max_length=10, blank=True, verbose_name='الرمز البريدي')
    
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
    
    # الصورة
    photo = models.ImageField(
        upload_to='hr/employees/photos/',
        blank=True,
        null=True,
        verbose_name='الصورة الشخصية'
    )
    
    # فئة الزيادة
    increase_category = models.ForeignKey(
        'EmployeeIncreaseCategory',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employees',
        verbose_name='فئة الزيادة',
        help_text='فئة الموظف لتحديد سياسة الزيادة'
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
        """الحصول على الاسم الكامل بالعربية"""
        return f"{self.first_name_ar} {self.last_name_ar}"
    
    def get_full_name_en(self):
        """الحصول على الاسم الكامل بالإنجليزية"""
        if self.first_name_en and self.last_name_en:
            return f"{self.first_name_en} {self.last_name_en}"
        return self.get_full_name_ar()
    
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
        """حساب سنوات الخدمة"""
        from datetime import date
        today = date.today()
        return today.year - self.hire_date.year
    
    @property
    def is_active(self):
        """هل الموظف نشط"""
        return self.status == 'active'
