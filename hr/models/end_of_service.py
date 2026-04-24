"""
End of Service Benefit Model

FIX #19: Track end-of-service benefits calculation and payment
"""
from django.db import models
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from decimal import Decimal

User = get_user_model()


class EndOfServiceBenefit(models.Model):
    """
    End of service benefit calculation and tracking
    
    Tracks the calculation, approval, and payment of end-of-service benefits
    for employees when they leave the organization.
    """
    
    STATUS_CHOICES = [
        ('calculated', 'محسوب'),
        ('approved', 'معتمد'),
        ('paid', 'مدفوع'),
        ('cancelled', 'ملغي'),
    ]
    
    CALCULATION_METHOD_CHOICES = [
        ('full_service', 'خدمة كاملة'),
        ('resignation', 'استقالة'),
        ('termination', 'إنهاء خدمة'),
    ]
    
    employee = models.ForeignKey(
        'Employee',
        on_delete=models.PROTECT,
        related_name='end_of_service_benefits',
        verbose_name='الموظف'
    )
    
    # Calculation details
    calculation_date = models.DateField(
        auto_now_add=True,
        verbose_name='تاريخ الحساب'
    )
    termination_date = models.DateField(
        verbose_name='تاريخ انتهاء الخدمة'
    )
    service_years = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name='سنوات الخدمة'
    )
    service_months = models.IntegerField(
        verbose_name='أشهر الخدمة'
    )
    
    # Benefit calculation
    last_salary = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='آخر راتب'
    )
    benefit_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='مبلغ المكافأة'
    )
    calculation_method = models.CharField(
        max_length=50,
        choices=CALCULATION_METHOD_CHOICES,
        verbose_name='طريقة الحساب'
    )
    calculation_details = models.TextField(
        blank=True,
        verbose_name='تفاصيل الحساب',
        help_text='شرح تفصيلي لكيفية حساب المكافأة'
    )
    
    # Status workflow
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='calculated',
        verbose_name='الحالة'
    )
    
    # Approval
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_eos_benefits',
        verbose_name='اعتمد بواسطة'
    )
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='تاريخ الاعتماد'
    )
    
    # Payment
    journal_entry = models.ForeignKey(
        'financial.JournalEntry',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='eos_benefits',
        verbose_name='القيد المحاسبي'
    )
    paid_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='تاريخ الدفع'
    )
    paid_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='paid_eos_benefits',
        verbose_name='دفع بواسطة'
    )
    payment_account = models.ForeignKey(
        'financial.ChartOfAccounts',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='eos_benefit_payments',
        verbose_name='الحساب المدفوع منه'
    )
    
    # Notes
    notes = models.TextField(
        blank=True,
        verbose_name='ملاحظات'
    )
    
    # Audit fields
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='created_eos_benefits',
        verbose_name='أنشئ بواسطة'
    )
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'hr_end_of_service_benefit'
        verbose_name = 'مكافأة نهاية الخدمة'
        verbose_name_plural = 'مكافآت نهاية الخدمة'
        ordering = ['-calculation_date']
        indexes = [
            models.Index(fields=['employee', 'status']),
            models.Index(fields=['status', 'calculation_date']),
        ]
    
    def __str__(self):
        return f'{self.employee.get_full_name_ar()} - {self.benefit_amount} ج.م'
    
    def clean(self):
        """Validate end-of-service benefit data"""
        errors = {}
        
        # Validate termination date
        if self.termination_date and self.employee.hire_date:
            if self.termination_date < self.employee.hire_date:
                errors['termination_date'] = 'تاريخ انتهاء الخدمة لا يمكن أن يكون قبل تاريخ التعيين'
        
        # Validate benefit amount
        if self.benefit_amount and self.benefit_amount < 0:
            errors['benefit_amount'] = 'مبلغ المكافأة لا يمكن أن يكون سالب'
        
        # Validate service years
        if self.service_years and self.service_years < 0:
            errors['service_years'] = 'سنوات الخدمة لا يمكن أن تكون سالبة'
        
        if errors:
            raise ValidationError(errors)
    
    def approve(self, approved_by):
        """Approve the end-of-service benefit"""
        from django.utils import timezone
        
        if self.status != 'calculated':
            raise ValidationError('يمكن اعتماد المكافآت المحسوبة فقط')
        
        self.status = 'approved'
        self.approved_by = approved_by
        self.approved_at = timezone.now()
        self.save()
    
    def mark_as_paid(self, paid_by, journal_entry=None):
        """Mark the benefit as paid"""
        from django.utils import timezone
        
        if self.status != 'approved':
            raise ValidationError('يجب اعتماد المكافأة قبل الدفع')
        
        self.status = 'paid'
        self.paid_by = paid_by
        self.paid_at = timezone.now()
        if journal_entry:
            self.journal_entry = journal_entry
        self.save()
    
    def cancel(self):
        """Cancel the benefit"""
        if self.status == 'paid':
            raise ValidationError('لا يمكن إلغاء مكافأة مدفوعة')
        
        self.status = 'cancelled'
        self.save()
