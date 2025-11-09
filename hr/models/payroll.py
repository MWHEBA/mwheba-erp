"""
نماذج كشوف الرواتب والسلف
"""
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class Payroll(models.Model):
    """نموذج كشف الراتب الشهري"""
    
    STATUS_CHOICES = [
        ('draft', 'مسودة'),
        ('calculated', 'محسوب'),
        ('approved', 'معتمد'),
        ('paid', 'مدفوع'),
        ('cancelled', 'ملغي'),
    ]
    
    PAYMENT_METHOD_CHOICES = [
        ('bank_transfer', 'تحويل بنكي'),
        ('cash', 'نقدي'),
        ('cheque', 'شيك'),
    ]
    
    employee = models.ForeignKey(
        'Employee',
        on_delete=models.CASCADE,
        related_name='payrolls',
        verbose_name='الموظف'
    )
    month = models.DateField(verbose_name='الشهر')
    salary = models.ForeignKey(
        'Salary',
        on_delete=models.PROTECT,
        verbose_name='الراتب'
    )
    
    # مكونات الراتب
    basic_salary = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='الراتب الأساسي'
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
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        default='bank_transfer',
        verbose_name='طريقة الدفع'
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
    
    class Meta:
        verbose_name = 'كشف راتب'
        verbose_name_plural = 'كشوف الرواتب'
        unique_together = ['employee', 'month']
        ordering = ['-month', 'employee']
        indexes = [
            models.Index(fields=['month', 'status']),
            models.Index(fields=['employee', 'month']),
        ]
        permissions = [
            ("can_process_payroll", "معالجة الرواتب"),
            ("can_approve_payroll", "اعتماد الرواتب"),
            ("can_view_all_salaries", "عرض جميع الرواتب"),
        ]
    
    def __str__(self):
        return f"{self.employee.get_full_name_ar()} - {self.month.strftime('%Y-%m')}"
    
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
        """حساب الإجماليات"""
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
        
        # صافي الراتب
        self.net_salary = (
            self.gross_salary +
            self.total_additions -
            self.total_deductions
        )
        
        return self.net_salary
    
    def clean(self):
        """التحقق من صحة البيانات"""
        from django.core.exceptions import ValidationError
        errors = {}
        
        # التحقق من صافي الراتب
        if hasattr(self, 'net_salary') and self.net_salary < 0:
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
        
        # التحقق من الراتب الأساسي
        if self.basic_salary <= 0:
            errors['basic_salary'] = 'الراتب الأساسي يجب أن يكون أكبر من صفر'
        
        if errors:
            raise ValidationError(errors)


class Advance(models.Model):
    """نموذج السلف (مبسط - خصم مرة واحدة)"""
    
    STATUS_CHOICES = [
        ('pending', 'قيد الانتظار'),
        ('approved', 'معتمدة'),
        ('rejected', 'مرفوضة'),
        ('paid', 'مدفوعة'),
        ('deducted', 'تم الخصم'),
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
        verbose_name='المبلغ'
    )
    reason = models.TextField(verbose_name='السبب')
    
    # الخصم (مرة واحدة)
    deducted = models.BooleanField(
        default=False,
        verbose_name='تم الخصم'
    )
    deduction_month = models.DateField(
        null=True,
        blank=True,
        verbose_name='شهر الخصم'
    )
    
    # الحالة
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='الحالة'
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
    
    class Meta:
        verbose_name = 'سلفة'
        verbose_name_plural = 'السلف'
        ordering = ['-requested_at']
    
    def __str__(self):
        return f"{self.employee.get_full_name_ar()} - {self.amount}"
    
    def clean(self):
        """التحقق من صحة البيانات"""
        from django.core.exceptions import ValidationError
        errors = {}
        
        # التحقق من المبلغ
        if self.amount <= 0:
            errors['amount'] = 'المبلغ يجب أن يكون أكبر من صفر'
        
        # التحقق من عدم تجاوز حد معقول
        if self.amount > 50000:  # حد أقصى 50,000 جنيه
            errors['amount'] = 'المبلغ يتجاوز الحد الأقصى المسموح (50,000 جنيه)'
        
        # التحقق من السبب
        if not self.reason or len(self.reason.strip()) < 10:
            errors['reason'] = 'يجب كتابة سبب واضح للسلفة (10 أحرف على الأقل)'
        
        if errors:
            raise ValidationError(errors)
    
    def mark_as_deducted(self, month):
        """تحديد السلفة كمخصومة"""
        self.deducted = True
        self.deduction_month = month
        self.status = 'deducted'
        self.save()
