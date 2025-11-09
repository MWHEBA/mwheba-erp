"""
نماذج الإجازات
"""
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class LeaveType(models.Model):
    """نموذج أنواع الإجازات"""
    
    name_ar = models.CharField(max_length=100, verbose_name='اسم النوع (عربي)')
    name_en = models.CharField(max_length=100, verbose_name='اسم النوع (إنجليزي)', blank=True)
    code = models.CharField(max_length=20, unique=True, verbose_name='الكود')
    
    # الإعدادات
    max_days_per_year = models.IntegerField(verbose_name='الحد الأقصى في السنة')
    is_paid = models.BooleanField(default=True, verbose_name='مدفوعة')
    requires_approval = models.BooleanField(default=True, verbose_name='تحتاج موافقة')
    requires_document = models.BooleanField(default=False, verbose_name='تحتاج مستند')
    
    # الحالة
    is_active = models.BooleanField(default=True, verbose_name='نشط')
    
    class Meta:
        verbose_name = 'نوع إجازة'
        verbose_name_plural = 'أنواع الإجازات'
    
    def __str__(self):
        return self.name_ar


class LeaveBalance(models.Model):
    """نموذج رصيد الإجازات للموظف"""
    
    employee = models.ForeignKey(
        'Employee',
        on_delete=models.CASCADE,
        related_name='leave_balances',
        verbose_name='الموظف'
    )
    leave_type = models.ForeignKey(
        LeaveType,
        on_delete=models.CASCADE,
        verbose_name='نوع الإجازة'
    )
    year = models.IntegerField(verbose_name='السنة')
    
    # الرصيد
    total_days = models.IntegerField(verbose_name='إجمالي الأيام')
    accrued_days = models.IntegerField(default=0, verbose_name='الأيام المستحقة')  # الأيام التي استحقها الموظف فعلياً
    used_days = models.IntegerField(default=0, verbose_name='الأيام المستخدمة')
    remaining_days = models.IntegerField(verbose_name='الأيام المتبقية')
    
    # تتبع الاستحقاق
    accrual_start_date = models.DateField(null=True, blank=True, verbose_name='تاريخ بداية الاستحقاق')  # عادة تاريخ التعيين
    last_accrual_date = models.DateField(null=True, blank=True, verbose_name='آخر تاريخ استحقاق')  # آخر مرة تم تحديث الاستحقاق
    
    class Meta:
        verbose_name = 'رصيد إجازة'
        verbose_name_plural = 'أرصدة الإجازات'
        unique_together = ['employee', 'leave_type', 'year']
    
    def __str__(self):
        return f"{self.employee.get_full_name_ar()} - {self.leave_type.name_ar} - {self.year}"
    
    def update_balance(self):
        """تحديث الرصيد المتبقي"""
        self.remaining_days = self.accrued_days - self.used_days
        self.save()
    
    def calculate_accrued_days(self):
        """
        حساب الأيام المستحقة - مبسط
        استحقاق شهري بسيط بعد انتهاء الفترة التجريبية
        """
        from datetime import date
        from dateutil.relativedelta import relativedelta
        from core.models import SystemSetting
        
        if not self.accrual_start_date:
            return 0
        
        today = date.today()
        delta = relativedelta(today, self.accrual_start_date)
        
        # حساب الأشهر الكاملة فقط
        total_months = delta.years * 12 + delta.months
        
        # جلب فترة التجربة من الإعدادات (افتراضي 3 أشهر)
        probation_months = SystemSetting.get_setting('leave_accrual_probation_months', 3)
        
        if total_months < probation_months:
            # لم ينتهي من الفترة التجريبية
            return 0
        
        # استحقاق شهري بسيط
        monthly_rate = self.total_days / 12.0
        accrued = int((total_months - probation_months) * monthly_rate)
        
        # لا يتجاوز الإجمالي السنوي
        return min(accrued, self.total_days)
    
    def update_accrued_days(self):
        """تحديث الأيام المستحقة وحفظها"""
        from datetime import date
        self.accrued_days = self.calculate_accrued_days()
        self.last_accrual_date = date.today()
        self.update_balance()


class Leave(models.Model):
    """نموذج طلبات الإجازات"""
    
    STATUS_CHOICES = [
        ('pending', 'قيد الانتظار'),
        ('approved', 'معتمدة'),
        ('rejected', 'مرفوضة'),
        ('cancelled', 'ملغاة'),
    ]
    
    employee = models.ForeignKey(
        'Employee',
        on_delete=models.CASCADE,
        related_name='leaves',
        verbose_name='الموظف'
    )
    leave_type = models.ForeignKey(
        LeaveType,
        on_delete=models.PROTECT,
        verbose_name='نوع الإجازة'
    )
    
    # التواريخ
    start_date = models.DateField(verbose_name='تاريخ البداية')
    end_date = models.DateField(verbose_name='تاريخ النهاية')
    days_count = models.IntegerField(verbose_name='عدد الأيام')
    
    # السبب
    reason = models.TextField(verbose_name='السبب')
    
    # سير العمل
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='الحالة'
    )
    
    # المراجعة
    requested_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الطلب')
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_leaves',
        verbose_name='راجعه'
    )
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='تاريخ المراجعة'
    )
    review_notes = models.TextField(blank=True, verbose_name='ملاحظات المراجعة')
    
    # الاعتماد
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_leaves',
        verbose_name='اعتمده'
    )
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='تاريخ الاعتماد'
    )
    
    # المرفقات
    attachment = models.FileField(
        upload_to='hr/leaves/attachments/',
        blank=True,
        null=True,
        verbose_name='المرفق'
    )
    
    class Meta:
        verbose_name = 'إجازة'
        verbose_name_plural = 'الإجازات'
        ordering = ['-requested_at']
        indexes = [
            models.Index(fields=['employee', 'status']),
            models.Index(fields=['start_date', 'end_date']),
        ]
        permissions = [
            ("can_approve_leaves", "اعتماد الإجازات"),
            ("can_reject_leaves", "رفض الإجازات"),
            ("can_view_all_leaves", "عرض جميع الإجازات"),
        ]
    
    def __str__(self):
        return f"{self.employee.get_full_name_ar()} - {self.leave_type.name_ar} ({self.start_date})"
    
    def clean(self):
        """التحقق من صحة البيانات"""
        from django.core.exceptions import ValidationError
        from datetime import date
        errors = {}
        
        # التحقق من التواريخ
        if self.start_date and self.end_date:
            if self.start_date > self.end_date:
                errors['end_date'] = 'تاريخ النهاية يجب أن يكون بعد تاريخ البداية'
            
            # التحقق من عدم تجاوز سنة
            days_diff = (self.end_date - self.start_date).days + 1
            if days_diff > 365:
                errors['end_date'] = 'مدة الإجازة لا يمكن أن تتجاوز سنة'
            
            # التحقق من عدم طلب إجازة في الماضي البعيد
            if self.start_date < date.today() and not self.pk:
                # السماح بـ 7 أيام ماضية فقط للطلبات الجديدة
                days_past = (date.today() - self.start_date).days
                if days_past > 7:
                    errors['start_date'] = 'لا يمكن طلب إجازة قبل أكثر من 7 أيام'
        
        # التحقق من عدد الأيام
        if self.days_count <= 0:
            errors['days_count'] = 'عدد الأيام يجب أن يكون أكبر من صفر'
        
        if self.days_count > 365:
            errors['days_count'] = 'عدد الأيام لا يمكن أن يتجاوز 365 يوم'
        
        # التحقق من الرصيد المتاح
        if self.employee_id and self.leave_type_id and not self.pk:
            try:
                balance = LeaveBalance.objects.get(
                    employee=self.employee,
                    leave_type=self.leave_type,
                    year=self.start_date.year if self.start_date else date.today().year
                )
                if self.days_count > balance.remaining_days:
                    errors['days_count'] = f'الرصيد المتاح فقط {balance.remaining_days} يوم'
            except LeaveBalance.DoesNotExist:
                pass  # سيتم إنشاء الرصيد تلقائياً
        
        if errors:
            raise ValidationError(errors)
    
    def calculate_days(self):
        """حساب عدد أيام الإجازة"""
        delta = self.end_date - self.start_date
        self.days_count = delta.days + 1
        self.save()
