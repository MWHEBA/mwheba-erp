"""
نموذج بنود قسيمة الراتب - لتفصيل المستحقات والخصومات
"""
from django.db import models
from django.contrib.auth import get_user_model
from decimal import Decimal

User = get_user_model()


class PayrollLine(models.Model):
    """بند في قسيمة الراتب - لتفصيل المستحقات والخصومات"""
    
    SOURCE_CHOICES = [
        ('contract', 'من العقد'),
        ('attendance', 'من الحضور'),
        ('leave', 'من الإجازات'),
        ('overtime', 'عمل إضافي'),
        ('advance', 'سلفة'),
        ('bonus', 'مكافأة'),
        ('deduction', 'خصم'),
        ('adjustment', 'تعديل'),
    ]
    
    COMPONENT_TYPE_CHOICES = [
        ('earning', 'مستحق'),
        ('deduction', 'خصم'),
    ]
    
    payroll = models.ForeignKey(
        'Payroll',
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name='قسيمة الراتب'
    )
    
    # البيانات الأساسية
    code = models.CharField(max_length=50, default='', verbose_name='الكود')
    name = models.CharField(max_length=200, default='', verbose_name='اسم البند')
    component_type = models.CharField(
        max_length=20,
        choices=COMPONENT_TYPE_CHOICES,
        default='earning',
        verbose_name='النوع'
    )
    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default='contract',
        verbose_name='المصدر'
    )
    
    # القيم
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=1,
        verbose_name='الكمية',
        help_text='مثال: عدد الأيام، الساعات، إلخ'
    )
    rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='السعر',
        help_text='سعر الوحدة'
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='المبلغ',
        help_text='quantity × rate'
    )
    
    # الربط بالمصادر
    salary_component = models.ForeignKey(
        'SalaryComponent',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='بند الراتب المرتبط'
    )
    attendance_record = models.ForeignKey(
        'Attendance',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='سجل الحضور المرتبط'
    )
    leave_record = models.ForeignKey(
        'Leave',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='الإجازة المرتبطة'
    )
    advance_installment = models.ForeignKey(
        'AdvanceInstallment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='قسط السلفة المرتبط'
    )
    
    # معلومات إضافية
    description = models.TextField(blank=True, verbose_name='الوصف')
    calculation_details = models.JSONField(
        null=True,
        blank=True,
        verbose_name='تفاصيل الحساب',
        help_text='تخزين تفاصيل الحساب بصيغة JSON'
    )
    
    # الترتيب
    order = models.IntegerField(default=0, verbose_name='الترتيب')
    
    # التواريخ
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    
    class Meta:
        verbose_name = 'بند قسيمة راتب'
        verbose_name_plural = 'بنود قسائم الرواتب'
        ordering = ['payroll', 'component_type', 'order']
        indexes = [
            models.Index(fields=['payroll', 'component_type']),
            models.Index(fields=['source']),
            models.Index(fields=['code']),
        ]
    
    def __str__(self):
        return f"{self.payroll.employee.get_full_name_ar()} - {self.name}: {self.amount}"
    
    def save(self, *args, **kwargs):
        """حساب المبلغ تلقائياً"""
        from decimal import Decimal, ROUND_HALF_UP
        
        # حساب المبلغ
        self.amount = (Decimal(str(self.quantity)) * Decimal(str(self.rate))).quantize(
            Decimal('0.01'), 
            rounding=ROUND_HALF_UP
        )
        
        super().save(*args, **kwargs)
    
    def get_source_display_icon(self):
        """الحصول على أيقونة المصدر"""
        icons = {
            'contract': 'fa-file-contract',
            'attendance': 'fa-calendar-check',
            'leave': 'fa-plane-departure',
            'overtime': 'fa-clock',
            'advance': 'fa-hand-holding-usd',
            'bonus': 'fa-gift',
            'deduction': 'fa-minus-circle',
            'adjustment': 'fa-edit',
        }
        return icons.get(self.source, 'fa-circle')
