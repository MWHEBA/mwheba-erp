"""
نماذج دفعات الرواتب المحاسبية
"""
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal


class PayrollPayment(models.Model):
    """
    نموذج دفعة الراتب - لتتبع دفعات الرواتب والقيود المحاسبية
    """
    
    PAYMENT_TYPE_CHOICES = [
        ('individual', 'دفعة فردية'),
        ('batch', 'دفعة جماعية'),
        ('advance', 'سلفة على الراتب'),
        ('bonus', 'مكافأة إضافية')
    ]
    
    PAYMENT_METHOD_CHOICES = [
        ('cash', 'نقداً'),
        ('bank_transfer', 'تحويل بنكي'),
        ('check', 'شيك'),
        ('online', 'دفع إلكتروني')
    ]
    
    STATUS_CHOICES = [
        ('pending', 'في الانتظار'),
        ('processing', 'قيد المعالجة'),
        ('completed', 'مكتمل'),
        ('failed', 'فشل'),
        ('cancelled', 'ملغي')
    ]
    
    # معلومات الدفعة الأساسية
    payment_reference = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='مرجع الدفعة',
        help_text='رقم مرجعي فريد للدفعة'
    )
    
    payment_type = models.CharField(
        max_length=20,
        choices=PAYMENT_TYPE_CHOICES,
        default='individual',
        verbose_name='نوع الدفعة'
    )
    
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        default='cash',
        verbose_name='طريقة الدفع'
    )
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='حالة الدفعة'
    )
    
    # المبالغ المالية
    total_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name='إجمالي المبلغ',
        help_text='إجمالي مبلغ الدفعة'
    )
    
    net_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name='المبلغ الصافي',
        help_text='المبلغ الصافي بعد الخصومات'
    )
    
    fees_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='رسوم التحويل',
        help_text='رسوم التحويل أو المعالجة'
    )
    
    # الحساب المحاسبي
    payment_account = models.ForeignKey(
        'financial.ChartOfAccounts',
        on_delete=models.PROTECT,
        verbose_name='حساب الدفع',
        help_text='الحساب المحاسبي المدفوع منه (صندوق/بنك)'
    )
    
    # القيد المحاسبي
    journal_entry = models.ForeignKey(
        'financial.JournalEntry',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='القيد المحاسبي',
        help_text='القيد المحاسبي المرتبط بالدفعة'
    )
    
    # معلومات التوقيت
    payment_date = models.DateField(
        verbose_name='تاريخ الدفع',
        help_text='تاريخ تنفيذ الدفعة'
    )
    
    due_date = models.DateField(
        null=True,
        blank=True,
        verbose_name='تاريخ الاستحقاق',
        help_text='تاريخ استحقاق الدفعة'
    )
    
    processed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='وقت المعالجة',
        help_text='وقت معالجة الدفعة'
    )
    
    # معلومات المستخدمين
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_payroll_payments',
        verbose_name='منشئ الدفعة'
    )
    
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='processed_payroll_payments',
        verbose_name='معالج الدفعة'
    )
    
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_payroll_payments',
        verbose_name='معتمد الدفعة'
    )
    
    # معلومات إضافية
    description = models.TextField(
        blank=True,
        verbose_name='الوصف',
        help_text='وصف تفصيلي للدفعة'
    )
    
    bank_reference = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='مرجع البنك',
        help_text='رقم المرجع من البنك (للتحويلات البنكية)'
    )
    
    check_number = models.CharField(
        max_length=50,
        blank=True,
        verbose_name='رقم الشيك',
        help_text='رقم الشيك (للدفع بالشيك)'
    )
    
    notes = models.TextField(
        blank=True,
        verbose_name='ملاحظات',
        help_text='ملاحظات إضافية'
    )
    
    # معلومات التتبع
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='تاريخ الإنشاء'
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='تاريخ التحديث'
    )
    
    class Meta:
        verbose_name = 'دفعة الراتب'
        verbose_name_plural = 'دفعات الرواتب'
        ordering = ['-payment_date', '-created_at']
        indexes = [
            models.Index(fields=['payment_reference']),
            models.Index(fields=['payment_date']),
            models.Index(fields=['status']),
            models.Index(fields=['payment_type']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"دفعة {self.payment_reference} - {self.total_amount} ج.م"
    
    def clean(self):
        """التحقق من صحة البيانات"""
        errors = {}
        
        # التحقق من المبالغ
        if self.total_amount <= 0:
            errors['total_amount'] = 'إجمالي المبلغ يجب أن يكون أكبر من صفر'
        
        if self.net_amount <= 0:
            errors['net_amount'] = 'المبلغ الصافي يجب أن يكون أكبر من صفر'
        
        if self.fees_amount < 0:
            errors['fees_amount'] = 'رسوم التحويل لا يمكن أن تكون سالبة'
        
        # التحقق من تاريخ الاستحقاق
        if self.due_date and self.payment_date and self.due_date < self.payment_date:
            errors['due_date'] = 'تاريخ الاستحقاق لا يمكن أن يكون قبل تاريخ الدفع'
        
        # التحقق من معلومات الدفع حسب الطريقة
        if self.payment_method == 'bank_transfer' and not self.bank_reference:
            errors['bank_reference'] = 'مرجع البنك مطلوب للتحويلات البنكية'
        
        if self.payment_method == 'check' and not self.check_number:
            errors['check_number'] = 'رقم الشيك مطلوب للدفع بالشيك'
        
        if errors:
            raise ValidationError(errors)
    
    def save(self, *args, **kwargs):
        """حفظ النموذج مع إنشاء مرجع تلقائي إذا لم يكن موجوداً"""
        
        # إنشاء مرجع تلقائي إذا لم يكن موجوداً
        if not self.payment_reference:
            self.payment_reference = self.generate_payment_reference()
        
        self.full_clean()
        super().save(*args, **kwargs)
    
    def generate_payment_reference(self):
        """إنشاء مرجع دفعة فريد"""
        from django.utils.crypto import get_random_string
        
        # تنسيق: PAY-YYYYMMDD-XXXX
        date_part = timezone.now().strftime('%Y%m%d')
        random_part = get_random_string(4, '0123456789')
        
        reference = f"PAY-{date_part}-{random_part}"
        
        # التأكد من عدم وجود مرجع مماثل
        while PayrollPayment.objects.filter(payment_reference=reference).exists():
            random_part = get_random_string(4, '0123456789')
            reference = f"PAY-{date_part}-{random_part}"
        
        return reference
    
    def can_process(self):
        """التحقق من إمكانية معالجة الدفعة"""
        return self.status == 'pending'
    
    def can_complete(self):
        """التحقق من إمكانية إكمال الدفعة"""
        return self.status == 'processing'
    
    def can_cancel(self):
        """التحقق من إمكانية إلغاء الدفعة"""
        return self.status in ['pending', 'processing']
    
    def process_payment(self, processed_by):
        """معالجة الدفعة"""
        if not self.can_process():
            raise ValidationError('لا يمكن معالجة هذه الدفعة في الحالة الحالية')
        
        self.status = 'processing'
        self.processed_by = processed_by
        self.processed_at = timezone.now()
        self.save()
    
    def complete_payment(self):
        """إكمال الدفعة"""
        if not self.can_complete():
            raise ValidationError('لا يمكن إكمال هذه الدفعة في الحالة الحالية')
        
        self.status = 'completed'
        self.save()
    
    def fail_payment(self, reason=None):
        """فشل الدفعة"""
        if not self.can_complete():
            raise ValidationError('لا يمكن تعيين هذه الدفعة كفاشلة في الحالة الحالية')
        
        self.status = 'failed'
        if reason:
            self.notes = f"{self.notes}\nسبب الفشل: {reason}" if self.notes else f"سبب الفشل: {reason}"
        self.save()
    
    def cancel_payment(self, cancelled_by, reason=None):
        """إلغاء الدفعة"""
        if not self.can_cancel():
            raise ValidationError('لا يمكن إلغاء هذه الدفعة في الحالة الحالية')
        
        self.status = 'cancelled'
        if reason:
            self.notes = f"{self.notes}\nسبب الإلغاء: {reason}" if self.notes else f"سبب الإلغاء: {reason}"
        self.save()
    
    def get_payrolls(self):
        """الحصول على قسائم الرواتب المرتبطة بهذه الدفعة"""
        from .payroll import Payroll
        return Payroll.objects.filter(payment=self)
    
    def calculate_totals_from_payrolls(self):
        """حساب الإجماليات من قسائم الرواتب المرتبطة"""
        payrolls = self.get_payrolls()
        
        self.total_amount = sum(p.gross_salary or Decimal('0') for p in payrolls)
        self.net_amount = sum(p.net_salary or Decimal('0') for p in payrolls)
        
        self.save(update_fields=['total_amount', 'net_amount'])
    
    @classmethod
    def create_batch_payment(cls, payrolls, payment_account, payment_method, created_by, description=None):
        """إنشاء دفعة جماعية من قسائم رواتب متعددة"""
        
        if not payrolls:
            raise ValidationError('لا توجد قسائم رواتب للدفع')
        
        # حساب الإجماليات
        total_amount = sum(p.gross_salary or Decimal('0') for p in payrolls)
        net_amount = sum(p.net_salary or Decimal('0') for p in payrolls)
        
        # إنشاء الدفعة
        payment = cls.objects.create(
            payment_type='batch',
            payment_method=payment_method,
            total_amount=total_amount,
            net_amount=net_amount,
            payment_account=payment_account,
            payment_date=timezone.now().date(),
            created_by=created_by,
            description=description or f'دفعة جماعية لـ {len(payrolls)} موظف'
        )
        
        # ربط قسائم الرواتب بالدفعة
        for payroll in payrolls:
            payroll.payment = payment
            payroll.save()
        
        return payment


class PayrollPaymentLine(models.Model):
    """
    نموذج سطر دفعة الراتب - لتفصيل مكونات الدفعة
    """
    
    payment = models.ForeignKey(
        PayrollPayment,
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name='الدفعة'
    )
    
    payroll = models.ForeignKey(
        'hr.Payroll',
        on_delete=models.CASCADE,
        verbose_name='قسيمة الراتب'
    )
    
    employee_name = models.CharField(
        max_length=200,
        verbose_name='اسم الموظف',
        help_text='اسم الموظف (للمرجعية السريعة)'
    )
    
    gross_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='المبلغ الإجمالي'
    )
    
    net_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='المبلغ الصافي'
    )
    
    deductions_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='مبلغ الخصومات'
    )
    
    notes = models.TextField(
        blank=True,
        verbose_name='ملاحظات'
    )
    
    class Meta:
        verbose_name = 'سطر دفعة الراتب'
        verbose_name_plural = 'أسطر دفعات الرواتب'
        unique_together = ['payment', 'payroll']
    
    def __str__(self):
        return f"{self.employee_name} - {self.net_amount} ج.م"
    
    def save(self, *args, **kwargs):
        """حفظ النموذج مع تعيين اسم الموظف تلقائياً"""
        if self.payroll and not self.employee_name:
            self.employee_name = self.payroll.employee.get_full_name_ar()
        
        super().save(*args, **kwargs)
