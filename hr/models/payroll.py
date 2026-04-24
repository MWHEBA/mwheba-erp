"""
نماذج قسائم الرواتب والسلف
"""
from django.db import models
from django.db.models import Sum
from django.contrib.auth import get_user_model

User = get_user_model()


class Payroll(models.Model):
    """نموذج قسيمة الراتب الشهري"""
    
    STATUS_CHOICES = [
        ('draft', 'مسودة'),
        ('calculated', 'محسوب'),
        ('approved', 'معتمد'),
        ('paid', 'مدفوع'),
        ('cancelled', 'ملغي'),
    ]
    
    employee = models.ForeignKey(
        'Employee',
        on_delete=models.CASCADE,
        related_name='payrolls',
        verbose_name='الموظف'
    )
    month = models.DateField(verbose_name='الشهر')
    
    # العقد
    contract = models.ForeignKey(
        'Contract',
        on_delete=models.PROTECT,
        verbose_name='العقد',
        help_text='العقد النشط وقت حساب الراتب'
    )
    
    # مكونات الراتب
    basic_salary = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='الأجر الأساسي'
    )
    allowances = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='البدلات'
    )
    
    # الإضافات
    overtime_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name='ساعات العمل الإضافي'
    )
    overtime_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='سعر ساعة العمل الإضافي'
    )
    overtime_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='قيمة العمل الإضافي'
    )
    bonus = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='المكافآت'
    )
    
    # الخصومات
    social_insurance = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='التأمينات الاجتماعية'
    )
    tax = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='الضرائب'
    )
    absence_days = models.IntegerField(
        default=0,
        verbose_name='أيام الغياب'
    )
    absence_deduction = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='خصم الغياب'
    )
    late_deduction = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='خصم التأخير'
    )
    advance_deduction = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='خصم السلف'
    )
    other_deductions = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='خصومات أخرى'
    )
    
    # الإجماليات
    gross_salary = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='إجمالي الراتب'
    )
    total_additions = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='إجمالي الإضافات'
    )
    total_deductions = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='إجمالي الخصومات'
    )
    net_salary = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='صافي الراتب'
    )
    
    # الحالة والدفع
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        verbose_name='الحالة'
    )
    payment_method = models.CharField(
        max_length=50,
        blank=True,
        verbose_name='طريقة الدفع',
        help_text='كود الحساب المالي (خزينة أو بنك)'
    )
    payment_date = models.DateField(
        null=True,
        blank=True,
        verbose_name='تاريخ الدفع'
    )
    payment_reference = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='مرجع الدفع'
    )
    
    # القيد المحاسبي
    journal_entry = models.ForeignKey(
        'financial.JournalEntry',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payrolls',
        verbose_name='القيد المحاسبي'
    )
    
    # التصنيف المالي
    financial_category = models.ForeignKey(
        'financial.FinancialCategory',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payrolls',
        verbose_name='التصنيف المالي',
        help_text='التصنيف المالي للرواتب (يحدد الحساب المحاسبي تلقائياً)'
    )

    financial_subcategory = models.ForeignKey(
        'financial.FinancialSubcategory',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payrolls',
        verbose_name='التصنيف المالي الفرعي',
        help_text='مركز التكلفة (التصنيف الفرعي) المأخوذ من قسم الموظف'
    )

    # الملاحظات
    notes = models.TextField(blank=True, verbose_name='ملاحظات')
    
    # التواريخ
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='تاريخ المعالجة'
    )
    processed_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='processed_payrolls',
        verbose_name='معالج بواسطة'
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_payrolls',
        verbose_name='اعتمد بواسطة'
    )
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='تاريخ الاعتماد'
    )
    
    # ✨ حقول الدفع الجديدة
    paid_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='paid_payrolls',
        verbose_name='دفع بواسطة'
    )
    paid_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='تاريخ الدفع الفعلي'
    )
    payment_account = models.ForeignKey(
        'financial.ChartOfAccounts',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payroll_payments',
        verbose_name='الحساب المدفوع منه',
        help_text='الصندوق أو البنك الذي تم الدفع منه'
    )
    
    @property
    def total_earnings(self):
        """إجمالي المستحقات (بدون الأجر الأساسي)"""
        from decimal import Decimal
        # حساب المستحقات من PayrollLine (بدون الأجر الأساسي)
        earnings_from_lines = self.lines.filter(
            component_type='earning'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        return earnings_from_lines

    @property
    def correct_net_salary(self):
        """
        صافي الراتب الصحيح.
        INSURABLE_SALARY مستبعد بالفعل من الحسابات في calculate_totals_from_lines،
        لذلك نرجع net_salary مباشرة بدون خصم إضافي.
        """
        from decimal import Decimal
        return self.net_salary or Decimal('0')

    @property
    def correct_gross_salary(self):
        """
        إجمالي الراتب الصحيح.
        INSURABLE_SALARY مستبعد بالفعل من الحسابات في calculate_totals_from_lines،
        لذلك نرجع gross_salary مباشرة بدون خصم إضافي.
        """
        from decimal import Decimal
        return self.gross_salary or Decimal('0')

    class Meta:
        verbose_name = 'قسيمة راتب'
        verbose_name_plural = 'قسائم الرواتب'
        unique_together = ['employee', 'month']
        ordering = ['-month', 'employee']
        indexes = [
            models.Index(fields=['month', 'status']),
            models.Index(fields=['employee', 'month']),
        ]
        permissions = [
            ("can_process_payroll", "معالجة الرواتب"),
            ("can_approve_payroll", "اعتماد الرواتب"),
            ("can_pay_payroll", "دفع الرواتب"),
            ("can_view_all_salaries", "عرض جميع الرواتب"),
        ]
    
    def __str__(self):
        return f"{self.employee.get_full_name_ar()} - {self.month.strftime('%Y-%m')}"

    def save(self, *args, **kwargs):
        """
        Override save to enforce net salary validation
        
        FIX #16: Prevent negative net salary
        """
        # Check for force_save flag (for exceptional cases)
        force_save = kwargs.pop('force_save', False)
        
        if not force_save:
            # Validate net salary is not negative
            if hasattr(self, 'net_salary') and self.net_salary is not None:
                if self.net_salary < 0:
                    from django.core.exceptions import ValidationError
                    raise ValidationError(
                        f'صافي الراتب سالب ({self.net_salary}). '
                        f'إجمالي الخصومات ({self.total_deductions}) '
                        f'يتجاوز إجمالي المستحقات ({self.gross_salary + self.total_additions}). '
                        f'يرجى مراجعة الخصومات.'
                    )
        
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Restore advance amounts before deleting payroll"""
        # استعادة المبالغ المخصومة من السلف المرتبطة
        for installment in self.advance_installments.all():
            advance = installment.advance
            advance.paid_installments -= 1
            # إذا عادت السلفة إلى حالة "مدفوعة" من "قيد الخصم"
            if advance.paid_installments == 0 and advance.status == 'in_progress':
                advance.status = 'paid'
            advance.save()
        
        # حذف الأقساط المرتبطة (سيتم تلقائياً بسبب on_delete=CASCADE)
        # لكن يمكننا التأكيد على الحذف اليدوي إذا لزم الأمر
        # self.advance_installments.all().delete()
        
        super().delete(*args, **kwargs)
    
    def calculate_overtime(self):
        """حساب قيمة العمل الإضافي"""
        if self.overtime_hours > 0 and self.overtime_rate > 0:
            self.overtime_amount = self.overtime_hours * self.overtime_rate
        return self.overtime_amount
    
    def calculate_absence_deduction(self):
        """حساب خصم الغياب"""
        if self.absence_days > 0:
            daily_salary = self.basic_salary / 30
            self.absence_deduction = daily_salary * self.absence_days
        return self.absence_deduction
    
    def calculate_totals(self):
        """حساب الإجماليات مع تقريب الكسور لأقرب رقم صحيح"""
        from decimal import Decimal, ROUND_HALF_UP
        
        # إجمالي الراتب
        self.gross_salary = self.basic_salary + self.allowances
        
        # إجمالي الإضافات
        self.calculate_overtime()
        self.total_additions = self.overtime_amount + self.bonus
        
        # إجمالي الخصومات
        self.calculate_absence_deduction()
        self.total_deductions = (
            self.social_insurance +
            self.tax +
            self.absence_deduction +
            self.late_deduction +
            self.advance_deduction +
            self.other_deductions
        )
        
        # تقريب الكسور لأقرب رقم صحيح
        self.gross_salary = self.gross_salary.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        self.total_additions = self.total_additions.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        self.total_deductions = self.total_deductions.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        
        # صافي الراتب مع تجبير الكسور
        net_salary = (
            self.gross_salary +
            self.total_additions -
            self.total_deductions
        )
        self.net_salary = net_salary.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        
        return self.net_salary
    
    def calculate_totals_from_lines(self):
        """
        حساب الإجماليات من PayrollLine (النظام الجديد)
        مع تقريب الكسور لأقرب رقم صحيح
        """
        from django.db.models import Sum
        from decimal import Decimal, ROUND_HALF_UP
        
        # حساب المستحقات من البنود — استبعاد INSURABLE_SALARY لأنه مرجعية فقط
        earnings_from_lines = self.lines.filter(
            component_type='earning'
        ).exclude(code='INSURABLE_SALARY').aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        # في بعض التدفقات الأجر الأساسي مضاف كـ PayrollLine، وفي أخرى مخزن فقط في basic_salary
        has_basic_line = self.lines.filter(code='BASIC_SALARY').exists()
        if has_basic_line:
            total_earnings = earnings_from_lines
        else:
            total_earnings = self.basic_salary + earnings_from_lines
        
        # حساب الاستقطاعات
        deductions = self.lines.filter(
            component_type='deduction'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        # حساب خصم السلف من البنود
        advance_deduction_line = self.lines.filter(
            code='ADVANCE_DEDUCTION'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        # تقريب الكسور لأقرب رقم صحيح للإجماليات الفرعية فقط
        advance_deduction_line = advance_deduction_line.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        
        # تحديث الإجماليات (total_earnings هو property فلا نحدثه)
        self.total_deductions = deductions          # بدون تقريب — الكسور محفوظة
        self.gross_salary = total_earnings          # بدون تقريب — الكسور محفوظة
        self.advance_deduction = advance_deduction_line  # تحديث حقل السلف
        
        # صافي الراتب فقط هو اللي يتقرّب لأقرب جنيه صحيح
        net_salary = total_earnings - deductions
        self.net_salary = net_salary.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        
        return self.net_salary
    
    def clean(self):
        """التحقق من صحة البيانات"""
        from django.core.exceptions import ValidationError
        errors = {}
        
        # التحقق من صافي الراتب
        if hasattr(self, 'net_salary') and self.net_salary is not None and self.net_salary < 0:
            errors['net_salary'] = 'صافي الراتب لا يمكن أن يكون سالب'
        
        # التحقق من ساعات العمل الإضافي
        if self.overtime_hours < 0:
            errors['overtime_hours'] = 'ساعات العمل الإضافي لا يمكن أن تكون سالبة'
        
        if self.overtime_hours > 160:  # حد أقصى معقول
            errors['overtime_hours'] = 'ساعات العمل الإضافي تبدو غير منطقية (أكثر من 160 ساعة)'
        
        # التحقق من أيام الغياب
        if self.absence_days < 0:
            errors['absence_days'] = 'أيام الغياب لا يمكن أن تكون سالبة'
        
        if self.absence_days > 31:
            errors['absence_days'] = 'أيام الغياب لا يمكن أن تتجاوز 31 يوم'
        
        # التحقق من الأجر الأساسي
        if self.basic_salary <= 0:
            errors['basic_salary'] = 'الأجر الأساسي يجب أن يكون أكبر من صفر'
        
        if errors:
            raise ValidationError(errors)


class PayrollAuditLog(models.Model):
    """سجل تدقيق قسائم الرواتب - يتتبع كل تعديل ومن قام به ومتى"""

    ACTION_CHOICES = [
        ('calculated',    'حساب الراتب'),
        ('recalculated',  'إعادة الحساب'),
        ('lines_edited',  'تعديل البنود'),
        ('approved',      'اعتماد'),
        ('unapproved',    'إلغاء الاعتماد'),
        ('paid',          'دفع الراتب'),
        ('cancelled',     'إلغاء'),
        ('note_added',    'إضافة ملاحظة'),
    ]

    payroll = models.ForeignKey(
        'Payroll',
        on_delete=models.CASCADE,
        related_name='audit_logs',
        verbose_name='قسيمة الراتب'
    )
    action = models.CharField(
        max_length=30,
        choices=ACTION_CHOICES,
        verbose_name='الإجراء'
    )
    performed_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='payroll_audit_actions',
        verbose_name='بواسطة'
    )
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name='التوقيت')
    notes = models.TextField(blank=True, verbose_name='ملاحظات')
    # snapshot مختصر للحالة بعد التعديل
    snapshot = models.JSONField(null=True, blank=True, verbose_name='لقطة البيانات')

    class Meta:
        verbose_name = 'سجل تدقيق راتب'
        verbose_name_plural = 'سجلات تدقيق الرواتب'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['payroll', 'timestamp']),
            models.Index(fields=['performed_by', 'timestamp']),
        ]

    def __str__(self):
        return f"{self.get_action_display()} - {self.payroll} - {self.performed_by}"


class Advance(models.Model):
    """نموذج السلف المحسّن - يدعم الأقساط"""
    
    STATUS_CHOICES = [
        ('pending', 'قيد الانتظار'),
        ('approved', 'معتمدة'),
        ('rejected', 'مرفوضة'),
        ('paid', 'مدفوعة'),
        ('in_progress', 'قيد الخصم'),
        ('completed', 'مكتملة'),
        ('cancelled', 'ملغاة'),
    ]
    
    employee = models.ForeignKey(
        'Employee',
        on_delete=models.CASCADE,
        related_name='advances',
        verbose_name='الموظف'
    )
    
    # المبلغ
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='المبلغ الإجمالي'
    )
    reason = models.TextField(verbose_name='السبب')
    
    # نظام الأقساط
    installments_count = models.IntegerField(
        default=1,
        verbose_name='عدد الأقساط',
        help_text='عدد الأشهر التي سيتم خصم السلفة خلالها'
    )
    installment_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='قيمة القسط الشهري',
        help_text='يتم حسابها تلقائياً = المبلغ / عدد الأقساط'
    )
    remaining_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='المبلغ المتبقي'
    )
    paid_installments = models.IntegerField(
        default=0,
        verbose_name='عدد الأقساط المدفوعة'
    )
    
    # تاريخ بدء الخصم
    deduction_start_month = models.DateField(
        null=True,
        blank=True,
        verbose_name='شهر بدء الخصم',
        help_text='الشهر الذي سيبدأ فيه خصم الأقساط'
    )
    
    # الحالة
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='الحالة'
    )
    
    # التصنيف المالي
    financial_category = models.ForeignKey(
        'financial.FinancialCategory',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='advances',
        verbose_name='التصنيف المالي',
        help_text='التصنيف المالي للسلف (يحدد الحساب المحاسبي تلقائياً)'
    )
    
    # التواريخ
    requested_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الطلب')
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_advances',
        verbose_name='اعتمد بواسطة'
    )
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name='تاريخ الاعتماد')
    payment_date = models.DateField(null=True, blank=True, verbose_name='تاريخ الصرف')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='تاريخ الإكمال')
    
    # ملاحظات
    notes = models.TextField(blank=True, verbose_name='ملاحظات')
    
    # القيد المحاسبي
    journal_entry = models.ForeignKey(
        'financial.JournalEntry',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='advances',
        verbose_name='القيد المحاسبي'
    )
    payment_account = models.ForeignKey(
        'financial.ChartOfAccounts',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='advance_payments',
        verbose_name='حساب الصرف (الخزينة/البنك)'
    )
    
    class Meta:
        verbose_name = 'سلفة'
        verbose_name_plural = 'السلف'
        ordering = ['-requested_at']
        indexes = [
            models.Index(fields=['employee', 'status']),
            models.Index(fields=['status', 'deduction_start_month']),
        ]
    
    def __str__(self):
        return f"{self.employee.get_full_name_ar()} - {self.amount} ج.م ({self.installments_count} قسط)"
    
    def clean(self):
        """التحقق من صحة البيانات"""
        from django.core.exceptions import ValidationError
        errors = {}
        
        # التحقق من المبلغ
        if self.amount <= 0:
            errors['amount'] = 'المبلغ يجب أن يكون أكبر من صفر'
        
        # التحقق من عدم تجاوز حد معقول
        if self.amount > 50000:
            errors['amount'] = 'المبلغ يتجاوز الحد الأقصى المسموح (50,000 جنيه)'
        
        # التحقق من عدد الأقساط
        if self.installments_count < 1:
            errors['installments_count'] = 'عدد الأقساط يجب أن يكون على الأقل 1'
        
        if self.installments_count > 24:
            errors['installments_count'] = 'عدد الأقساط لا يمكن أن يتجاوز 24 شهر'
        
        # التحقق من السبب
        if not self.reason or len(self.reason.strip()) < 10:
            errors['reason'] = 'يجب كتابة سبب واضح للسلفة (10 أحرف على الأقل)'
        
        # التحقق من تاريخ بدء الخصم
        if self.status == 'paid' and not self.deduction_start_month:
            errors['deduction_start_month'] = 'يجب تحديد شهر بدء الخصم عند صرف السلفة'

        # التحقق من أن تاريخ بدء الخصم لا يسبق 26 من الشهر السابق
        if self.deduction_start_month and not self.pk:
            from hr.utils import validate_entry_date
            errors.update(validate_entry_date(self.deduction_start_month, 'deduction_start_month'))
        
        if errors:
            raise ValidationError(errors)
    
    def save(self, *args, **kwargs):
        """حساب قيمة القسط والمبلغ المتبقي قبل الحفظ"""
        from decimal import Decimal
        
        # حساب قيمة القسط الشهري
        if self.installments_count > 0:
            self.installment_amount = self.amount / Decimal(str(self.installments_count))
        
        # حساب المبلغ المتبقي
        if self.pk:  # إذا كان السجل موجود
            paid_amount = self.paid_installments * self.installment_amount
            self.remaining_amount = self.amount - paid_amount
            
            # تحديث الحالة تلقائياً
            if self.remaining_amount <= 0 and self.status == 'in_progress':
                self.status = 'completed'
                if not self.completed_at:
                    from django.utils import timezone
                    self.completed_at = timezone.now()
        else:
            self.remaining_amount = self.amount
        
        super().save(*args, **kwargs)
    
    def get_next_installment_amount(self):
        """
        الحصول على قيمة القسط التالي
        
        FIX #17: Handle last installment rounding correctly
        """
        from decimal import Decimal, ROUND_HALF_UP
        
        if self.remaining_amount <= 0:
            return Decimal('0')
        
        # Count paid installments
        paid_count = self.paid_installments
        remaining_installments = self.installments_count - paid_count
        
        # If this is the last installment, return exact remaining amount
        if remaining_installments <= 1:
            return self.remaining_amount
        
        # Otherwise, return regular installment (rounded)
        regular_installment = self.amount / self.installments_count
        regular_installment = regular_installment.quantize(
            Decimal('1'), 
            rounding=ROUND_HALF_UP
        )
        
        # Make sure we don't exceed remaining amount
        if regular_installment > self.remaining_amount:
            return self.remaining_amount
        
        return regular_installment
    
    def record_installment_payment(self, month, amount):
        """تسجيل دفع قسط"""
        from decimal import Decimal
        
        if self.status not in ['paid', 'in_progress']:
            raise ValueError('لا يمكن خصم قسط من سلفة غير مدفوعة')
        
        if self.remaining_amount <= 0:
            raise ValueError('السلفة مكتملة بالفعل')
        
        # إنشاء سجل القسط
        installment = AdvanceInstallment.objects.create(
            advance=self,
            month=month,
            amount=amount,
            installment_number=self.paid_installments + 1
        )
        
        # تحديث السلفة
        self.paid_installments += 1
        if self.status == 'paid':
            self.status = 'in_progress'
        self.save()
        
        return installment
    
    def get_installment_history(self):
        """الحصول على سجل الأقساط المدفوعة"""
        return self.installments.all().order_by('month')
    
    @property
    def is_completed(self):
        """هل تم إكمال خصم السلفة"""
        return self.remaining_amount <= 0 or self.paid_installments >= self.installments_count


class AdvanceInstallment(models.Model):
    """نموذج قسط السلفة - لتتبع الأقساط المدفوعة"""
    
    advance = models.ForeignKey(
        Advance,
        on_delete=models.CASCADE,
        related_name='installments',
        verbose_name='السلفة'
    )
    month = models.DateField(verbose_name='الشهر')
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='المبلغ المخصوم'
    )
    installment_number = models.IntegerField(
        verbose_name='رقم القسط',
        help_text='رقم القسط من إجمالي الأقساط'
    )
    payroll = models.ForeignKey(
        Payroll,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='advance_installments',
        verbose_name='قسيمة الراتب'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الخصم')
    notes = models.TextField(blank=True, verbose_name='ملاحظات')
    
    class Meta:
        verbose_name = 'قسط سلفة'
        verbose_name_plural = 'أقساط السلف'
        unique_together = ['advance', 'month']
        ordering = ['month']
        indexes = [
            models.Index(fields=['advance', 'month']),
            models.Index(fields=['month']),
        ]
    
    def __str__(self):
        return f"قسط {self.installment_number} - {self.advance.employee.get_full_name_ar()} - {self.amount} ج.م"
