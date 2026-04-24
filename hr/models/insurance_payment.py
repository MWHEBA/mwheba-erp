"""
نموذج دفعات تأمين الموظفين الخارجيين
"""
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class InsurancePayment(models.Model):
    """دفعة تأمين شهرية لموظف تأمين فقط"""

    STATUS_CHOICES = [
        ('pending', 'لم يُدفع'),
        ('paid', 'مدفوع'),
    ]

    employee = models.ForeignKey(
        'Employee',
        on_delete=models.PROTECT,
        related_name='insurance_payments',
        verbose_name='الموظف'
    )
    month = models.DateField(verbose_name='الشهر')
    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='إجمالي التأمين',
        help_text='نصيب الموظف + نصيب الشركة'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='الحالة'
    )
    payment_date = models.DateField(null=True, blank=True, verbose_name='تاريخ الدفع')
    payment_account = models.ForeignKey(
        'financial.ChartOfAccounts',
        on_delete=models.PROTECT,
        null=True, blank=True,
        verbose_name='حساب الاستلام'
    )
    journal_entry = models.ForeignKey(
        'financial.JournalEntry',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name='القيد المحاسبي'
    )
    received_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True, blank=True,
        verbose_name='استلم بواسطة'
    )
    notes = models.TextField(blank=True, verbose_name='ملاحظات')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['employee', 'month']
        verbose_name = 'دفعة تأمين'
        verbose_name_plural = 'دفعات التأمين'
        ordering = ['-month', 'employee']
        indexes = [
            models.Index(fields=['month', 'status']),
            models.Index(fields=['employee', 'month']),
        ]

    def __str__(self):
        return f"{self.employee.get_full_name_ar()} - {self.month.strftime('%Y-%m')} - {self.get_status_display()}"
