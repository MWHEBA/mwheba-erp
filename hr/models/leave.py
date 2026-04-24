"""
نماذج الإجازات
"""
from decimal import Decimal
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class LeaveType(models.Model):
    """نموذج أنواع الإجازات"""

    CATEGORY_CHOICES = [
        ('annual',      'اعتيادي'),
        ('emergency',   'عارضة'),
        ('sick',        'مرضي'),
        ('exceptional', 'استثنائي (مدفوع)'),
        ('unpaid',      'غير مدفوع'),
    ]

    name_ar = models.CharField(max_length=100, verbose_name='اسم النوع (عربي)')
    name_en = models.CharField(max_length=100, verbose_name='اسم النوع (إنجليزي)', blank=True)
    code = models.CharField(max_length=20, unique=True, verbose_name='الكود')

    # تصنيف الإجازة — يحدد منطق الاستحقاق
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default='annual',
        verbose_name='تصنيف الإجازة',
        help_text='يحدد كيفية حساب الاستحقاق التدريجي لهذا النوع'
    )

    # الإعدادات
    max_days_per_year = models.IntegerField(
        verbose_name='الحد الأقصى في السنة',
        help_text='للإجازات الاستثنائية والغير مدفوعة: هذا هو الرصيد الثابت. للاعتيادي والعارضة: يُستخدم كـ ceiling فقط'
    )
    is_paid = models.BooleanField(default=True, verbose_name='مدفوعة')
    requires_approval = models.BooleanField(default=True, verbose_name='تحتاج موافقة')
    requires_document = models.BooleanField(default=False, verbose_name='تحتاج مستند')

    # معامل الخصم من الراتب — للإجازات غير المدفوعة فقط
    # 1.0 = يوم راتب كامل مقابل كل يوم إجازة، 0.5 = نص يوم
    deduction_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal('1.0'),
        verbose_name='معامل الخصم',
        help_text='كام يوم راتب يُخصم مقابل كل يوم إجازة (للإجازات غير المدفوعة فقط)'
    )

    # هل يدخل في حساب تحويل الرصيد المتبقي لمقابل مالي في نهاية السنة؟
    allow_encashment = models.BooleanField(
        default=False,
        verbose_name='يسمح بتحويله لمقابل مالي',
        help_text='عند تفعيل خيار تحويل الإجازات، هل يدخل هذا النوع في الحساب؟'
    )

    # الحالة
    is_active = models.BooleanField(default=True, verbose_name='نشط')

    # الـ categories التي لا تحتاج رصيداً مسبقاً — single source of truth
    NO_BALANCE_CATEGORIES = ('exceptional', 'sick', 'unpaid')

    class Meta:
        verbose_name = 'نوع إجازة'
        verbose_name_plural = 'أنواع الإجازات'

    def __str__(self):
        return self.name_ar

    def clean(self):
        """التحقق من صحة البيانات"""
        from django.core.exceptions import ValidationError
        errors = {}
        
        # الإجازات الاستثنائية يجب أن تكون دائماً مدفوعة
        if self.category == 'exceptional' and not self.is_paid:
            errors['is_paid'] = 'الإجازات الاستثنائية يجب أن تكون مدفوعة دائماً'
        
        if errors:
            raise ValidationError(errors)
    
    def save(self, *args, **kwargs):
        """حفظ مع التحقق من البيانات"""
        # فرض أن الإجازات الاستثنائية مدفوعة
        if self.category == 'exceptional':
            self.is_paid = True
        self.clean()
        super().save(*args, **kwargs)

    @property
    def requires_balance(self):
        """هل هذا النوع يحتاج رصيداً مسبقاً؟"""
        return self.category not in self.NO_BALANCE_CATEGORIES


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
    accrual_start_date = models.DateField(null=True, blank=True, verbose_name='تاريخ بداية الاستحقاق')
    last_accrual_date = models.DateField(null=True, blank=True, verbose_name='آخر تاريخ استحقاق')

    # مرحلة الاستحقاق — تُستخدم لاكتشاف تغيير المرحلة تلقائياً
    ACCRUAL_PHASE_CHOICES = [
        ('none',    'لم يستحق بعد'),
        ('partial', 'رصيد جزئي'),
        ('full',    'رصيد كامل'),
        ('senior',  'كبير موظفين'),
    ]
    accrual_phase = models.CharField(
        max_length=10,
        choices=ACCRUAL_PHASE_CHOICES,
        default='none',
        verbose_name='مرحلة الاستحقاق',
        help_text='تُحدَّث تلقائياً — تُستخدم لاكتشاف الترقي لمرحلة أعلى'
    )

    # تعديل يدوي
    is_manually_adjusted = models.BooleanField(default=False, verbose_name='معدل يدوياً')
    adjustment_reason = models.TextField(
        blank=True,
        verbose_name='سبب التعديل اليدوي',
        help_text='يُسجَّل تلقائياً عند التعديل اليدوي'
    )
    
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
    
    # معامل الخصم الخاص بهذه الإجازة — يُنسخ من نوع الإجازة عند الإنشاء ويمكن تعديله يدوياً
    deduction_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal('1.0'),
        verbose_name='معامل الخصم',
        help_text='كام يوم راتب يُخصم مقابل كل يوم إجازة (للإجازات غير المدفوعة فقط) — يُنسخ من نوع الإجازة ويمكن تعديله'
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
            
            # التحقق من عدم طلب إجازة قبل 26 من الشهر السابق
            if self.start_date < date.today() and not self.pk:
                from hr.utils import validate_entry_date
                errors.update(validate_entry_date(self.start_date, 'start_date'))
        
        # التحقق من عدد الأيام
        if self.days_count is not None and self.days_count <= 0:
            errors['days_count'] = 'عدد الأيام يجب أن يكون أكبر من صفر'

        if self.days_count is not None and self.days_count > 365:
            errors['days_count'] = 'عدد الأيام لا يمكن أن يتجاوز 365 يوم'

        # ✅ NEW: التحقق من تداخل الإجازات
        if self.employee_id and self.start_date and self.end_date:
            overlapping = Leave.objects.filter(
                employee=self.employee,
                status__in=['pending', 'approved'],
                start_date__lte=self.end_date,
                end_date__gte=self.start_date
            ).exclude(pk=self.pk if self.pk else None)
            
            if overlapping.exists():
                overlap = overlapping.first()
                errors['start_date'] = (
                    f'يوجد إجازة متداخلة من {overlap.start_date} '
                    f'إلى {overlap.end_date} ({overlap.leave_type.name_ar})'
                )

        # التحقق من الرصيد المتاح
        if self.employee_id and self.leave_type_id and not self.pk:
            try:
                balance = LeaveBalance.objects.get(
                    employee=self.employee,
                    leave_type=self.leave_type,
                    year=self.start_date.year if self.start_date else date.today().year
                )
                if self.days_count is not None and self.days_count > (balance.remaining_days or 0):
                    errors['days_count'] = f'الرصيد المتاح فقط {balance.remaining_days or 0} يوم'
            except LeaveBalance.DoesNotExist:
                pass
        
        if errors:
            raise ValidationError(errors)
    
    def save(self, *args, **kwargs):
        """عند الإنشاء: انسخ deduction_multiplier من نوع الإجازة تلقائياً"""
        if not self.pk and self.leave_type_id:
            # إجازة جديدة — انسخ المعامل من النوع كقيمة افتراضية
            try:
                lt = LeaveType.objects.get(pk=self.leave_type_id)
                self.deduction_multiplier = lt.deduction_multiplier
            except LeaveType.DoesNotExist:
                pass
        super().save(*args, **kwargs)

    def calculate_days(self):
        """حساب عدد أيام الإجازة"""
        delta = self.end_date - self.start_date
        self.days_count = delta.days + 1
        self.save()


class LeaveEncashmentLog(models.Model):
    """سجل عمليات تحويل الإجازات لمقابل مالي"""

    employee = models.ForeignKey(
        'Employee',
        on_delete=models.CASCADE,
        related_name='encashment_logs',
        verbose_name='الموظف'
    )
    payroll = models.ForeignKey(
        'Payroll',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='encashment_logs',
        verbose_name='قسيمة الراتب'
    )
    year = models.IntegerField(verbose_name='سنة الإجازات')
    encashment_month = models.DateField(
        verbose_name='شهر الإضافة للراتب',
        help_text='أول يوم من الشهر الذي أُضيف فيه المقابل المالي للراتب'
    )
    total_days = models.IntegerField(verbose_name='إجمالي الأيام المحوَّلة')
    daily_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='الراتب اليومي'
    )
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name='إجمالي المبلغ'
    )
    processed_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='processed_encashments',
        verbose_name='نفّذ بواسطة'
    )
    processed_at = models.DateTimeField(
        default=timezone.now,
        verbose_name='تاريخ التنفيذ'
    )
    details = models.JSONField(
        default=list,
        verbose_name='تفاصيل التحويل',
        help_text='تفاصيل كل نوع إجازة: الأيام والمبلغ'
    )

    class Meta:
        verbose_name = 'سجل تحويل إجازة'
        verbose_name_plural = 'سجلات تحويل الإجازات'
        ordering = ['-processed_at']
        indexes = [
            models.Index(fields=['employee', 'year']),
            models.Index(fields=['encashment_month']),
        ]

    def __str__(self):
        return (
            f"{self.employee.get_full_name_ar()} — "
            f"{self.year} — {self.total_days} يوم — {self.total_amount} ج.م"
        )
