"""
نموذج أسطر قسيمة الراتب
"""
from django.db import models
from decimal import Decimal


class PayrollLine(models.Model):
    """
    سطر في قسيمة الراتب - يحتوي على تفاصيل كل بند
    هذا يسمح بـ:
    - تتبع دقيق لكل بند
    - سهولة المراجعة
    - إمكانية التعديل قبل الاعتماد
    """
    
    payroll = models.ForeignKey(
        'Payroll',
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name='قسيمة الراتب'
    )
    
    salary_component = models.ForeignKey(
        'SalaryComponent',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name='مكون الراتب',
        help_text='البند الأصلي (للمرجعية فقط)'
    )
    
    # البيانات (نسخة من SalaryComponent وقت الحساب - snapshot)
    code = models.CharField(
        max_length=50,
        verbose_name='الكود'
    )
    name = models.CharField(
        max_length=100,
        verbose_name='اسم البند'
    )
    component_type = models.CharField(
        max_length=20,
        verbose_name='نوع المكون'
    )
    
    # المبلغ المحسوب
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='المبلغ'
    )
    
    # التفاصيل (للشفافية)
    calculation_details = models.JSONField(
        null=True,
        blank=True,
        verbose_name='تفاصيل الحساب',
        help_text='مثل: الصيغة المستخدمة، القيم المدخلة، إلخ'
    )
    
    # الترتيب
    order = models.IntegerField(
        default=0,
        verbose_name='الترتيب'
    )
    
    # ملاحظات
    notes = models.TextField(
        blank=True,
        verbose_name='ملاحظات'
    )
    
    class Meta:
        verbose_name = 'سطر قسيمة راتب'
        verbose_name_plural = 'أسطر قسائم الرواتب'
        ordering = ['payroll', 'order']
        indexes = [
            models.Index(fields=['payroll', 'component_type']),
            models.Index(fields=['salary_component']),
        ]
    
    def __str__(self):
        return f"{self.name}: {self.amount}"
