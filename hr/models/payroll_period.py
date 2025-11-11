"""
نماذج فترات الرواتب المحاسبية
"""
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
import calendar


class PayrollPeriod(models.Model):
    """
    نموذج فترة الرواتب - لإدارة دورات الرواتب الشهرية
    """
    
    STATUS_CHOICES = [
        ('draft', 'مسودة'),
        ('calculated', 'محسوبة'),
        ('approved', 'معتمدة'),
        ('paid', 'مدفوعة'),
        ('closed', 'مغلقة')
    ]
    
    year = models.IntegerField(
        verbose_name='السنة',
        help_text='سنة فترة الرواتب'
    )
    
    month = models.IntegerField(
        verbose_name='الشهر',
        help_text='شهر فترة الرواتب (1-12)'
    )
    
    start_date = models.DateField(
        verbose_name='تاريخ البداية',
        help_text='تاريخ بداية فترة الرواتب'
    )
    
    end_date = models.DateField(
        verbose_name='تاريخ النهاية',
        help_text='تاريخ نهاية فترة الرواتب'
    )
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        verbose_name='الحالة',
        help_text='حالة فترة الرواتب'
    )
    
    total_employees = models.IntegerField(
        default=0,
        verbose_name='عدد الموظفين',
        help_text='إجمالي عدد الموظفين في هذه الفترة'
    )
    
    total_gross_salary = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='إجمالي الرواتب الإجمالية',
        help_text='مجموع جميع الرواتب الإجمالية'
    )
    
    total_net_salary = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='إجمالي الرواتب الصافية',
        help_text='مجموع جميع الرواتب الصافية'
    )
    
    total_deductions = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='إجمالي الخصومات',
        help_text='مجموع جميع الخصومات'
    )
    
    # معلومات الإنشاء والاعتماد
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='تاريخ الإنشاء'
    )
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_payroll_periods',
        verbose_name='منشئ الفترة'
    )
    
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='تاريخ الاعتماد'
    )
    
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_payroll_periods',
        verbose_name='معتمد الفترة'
    )
    
    closed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='تاريخ الإغلاق'
    )
    
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='closed_payroll_periods',
        verbose_name='مغلق الفترة'
    )
    
    # ملاحظات
    notes = models.TextField(
        blank=True,
        verbose_name='ملاحظات',
        help_text='ملاحظات إضافية حول فترة الرواتب'
    )
    
    class Meta:
        verbose_name = 'فترة الرواتب'
        verbose_name_plural = 'فترات الرواتب'
        unique_together = ['year', 'month']
        ordering = ['-year', '-month']
        indexes = [
            models.Index(fields=['year', 'month']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"رواتب {self.get_month_name()} {self.year}"
    
    def clean(self):
        """التحقق من صحة البيانات"""
        errors = {}
        
        # التحقق من صحة الشهر
        if not (1 <= self.month <= 12):
            errors['month'] = 'الشهر يجب أن يكون بين 1 و 12'
        
        # التحقق من صحة السنة
        current_year = timezone.now().year
        if self.year < 2020 or self.year > current_year + 1:
            errors['year'] = f'السنة يجب أن تكون بين 2020 و {current_year + 1}'
        
        # التحقق من تواريخ البداية والنهاية
        if self.start_date and self.end_date:
            if self.start_date >= self.end_date:
                errors['end_date'] = 'تاريخ النهاية يجب أن يكون بعد تاريخ البداية'
            
            # التحقق من أن التواريخ في نفس الشهر والسنة
            if (self.start_date.year != self.year or 
                self.start_date.month != self.month or
                self.end_date.year != self.year or 
                self.end_date.month != self.month):
                errors['start_date'] = 'التواريخ يجب أن تكون في نفس الشهر والسنة المحددين'
        
        if errors:
            raise ValidationError(errors)
    
    def save(self, *args, **kwargs):
        """حفظ النموذج مع تعيين التواريخ تلقائياً إذا لم تكن محددة"""
        
        # تعيين تواريخ البداية والنهاية تلقائياً إذا لم تكن محددة
        if not self.start_date or not self.end_date:
            self.start_date = timezone.datetime(self.year, self.month, 1).date()
            last_day = calendar.monthrange(self.year, self.month)[1]
            self.end_date = timezone.datetime(self.year, self.month, last_day).date()
        
        self.full_clean()
        super().save(*args, **kwargs)
    
    def get_month_name(self):
        """الحصول على اسم الشهر بالعربية"""
        month_names = {
            1: 'يناير', 2: 'فبراير', 3: 'مارس', 4: 'أبريل',
            5: 'مايو', 6: 'يونيو', 7: 'يوليو', 8: 'أغسطس',
            9: 'سبتمبر', 10: 'أكتوبر', 11: 'نوفمبر', 12: 'ديسمبر'
        }
        return month_names.get(self.month, str(self.month))
    
    def get_period_display(self):
        """عرض الفترة بصيغة مقروءة"""
        return f"{self.get_month_name()} {self.year}"
    
    def can_calculate(self):
        """التحقق من إمكانية حساب الرواتب"""
        return self.status == 'draft'
    
    def can_approve(self):
        """التحقق من إمكانية اعتماد الرواتب"""
        return self.status == 'calculated'
    
    def can_pay(self):
        """التحقق من إمكانية دفع الرواتب"""
        return self.status == 'approved'
    
    def can_close(self):
        """التحقق من إمكانية إغلاق الفترة"""
        return self.status == 'paid'
    
    def calculate_totals(self):
        """حساب الإجماليات من قسائم الرواتب المرتبطة"""
        from .payroll import Payroll
        
        payrolls = Payroll.objects.filter(
            month__year=self.year,
            month__month=self.month
        )
        
        self.total_employees = payrolls.count()
        self.total_gross_salary = sum(p.gross_salary or Decimal('0') for p in payrolls)
        self.total_net_salary = sum(p.net_salary or Decimal('0') for p in payrolls)
        self.total_deductions = sum(p.total_deductions or Decimal('0') for p in payrolls)
        
        self.save(update_fields=['total_employees', 'total_gross_salary', 
                                'total_net_salary', 'total_deductions'])
    
    def approve(self, approved_by):
        """اعتماد فترة الرواتب"""
        if not self.can_approve():
            raise ValidationError('لا يمكن اعتماد هذه الفترة في الحالة الحالية')
        
        self.status = 'approved'
        self.approved_by = approved_by
        self.approved_at = timezone.now()
        self.save()
    
    def close_period(self, closed_by):
        """إغلاق فترة الرواتب"""
        if not self.can_close():
            raise ValidationError('لا يمكن إغلاق هذه الفترة في الحالة الحالية')
        
        self.status = 'closed'
        self.closed_by = closed_by
        self.closed_at = timezone.now()
        self.save()
    
    @classmethod
    def get_current_period(cls):
        """الحصول على الفترة الحالية"""
        now = timezone.now()
        return cls.objects.filter(
            year=now.year,
            month=now.month
        ).first()
    
    @classmethod
    def create_period(cls, year, month, created_by):
        """إنشاء فترة رواتب جديدة"""
        
        # التحقق من عدم وجود فترة مماثلة
        if cls.objects.filter(year=year, month=month).exists():
            raise ValidationError(f'فترة رواتب {month}/{year} موجودة بالفعل')
        
        period = cls.objects.create(
            year=year,
            month=month,
            created_by=created_by
        )
        
        return period
