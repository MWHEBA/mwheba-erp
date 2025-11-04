"""
نموذج الراتب
"""
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class Salary(models.Model):
    """نموذج راتب الموظف"""
    
    employee = models.ForeignKey(
        'Employee',
        on_delete=models.CASCADE,
        related_name='salaries',
        verbose_name='الموظف'
    )
    effective_date = models.DateField(verbose_name='تاريخ السريان')
    
    # مكونات الراتب
    basic_salary = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='الراتب الأساسي'
    )
    housing_allowance = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='بدل السكن'
    )
    transport_allowance = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='بدل المواصلات'
    )
    food_allowance = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='بدل الطعام'
    )
    phone_allowance = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='بدل الهاتف'
    )
    other_allowances = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='بدلات أخرى'
    )
    
    # الاستقطاعات الثابتة
    social_insurance_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=11,
        verbose_name='نسبة التأمينات (%)'
    )
    tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name='نسبة الضريبة (%)'
    )
    
    # الحسابات
    gross_salary = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='إجمالي الراتب'
    )
    total_deductions = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='إجمالي الاستقطاعات'
    )
    net_salary = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='صافي الراتب'
    )
    
    # الحالة
    is_active = models.BooleanField(default=True, verbose_name='نشط')
    notes = models.TextField(blank=True, verbose_name='ملاحظات')
    
    # التواريخ
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='created_salaries',
        verbose_name='أنشئ بواسطة'
    )
    
    class Meta:
        verbose_name = 'راتب'
        verbose_name_plural = 'الرواتب'
        ordering = ['-effective_date']
        indexes = [
            models.Index(fields=['employee', 'effective_date']),
        ]
    
    def __str__(self):
        return f"{self.employee.get_full_name_ar()} - {self.effective_date}"
    
    def calculate_gross_salary(self):
        """حساب إجمالي الراتب"""
        self.gross_salary = (
            self.basic_salary +
            self.housing_allowance +
            self.transport_allowance +
            self.food_allowance +
            self.phone_allowance +
            self.other_allowances
        )
        return self.gross_salary
    
    def calculate_deductions(self):
        """حساب الاستقطاعات"""
        social_insurance = self.basic_salary * (self.social_insurance_rate / 100)
        tax = self.gross_salary * (self.tax_rate / 100)
        self.total_deductions = social_insurance + tax
        return self.total_deductions
    
    def calculate_net_salary(self):
        """حساب صافي الراتب"""
        self.calculate_gross_salary()
        self.calculate_deductions()
        self.net_salary = self.gross_salary - self.total_deductions
        return self.net_salary
    
    def save(self, *args, **kwargs):
        self.calculate_net_salary()
        super().save(*args, **kwargs)
