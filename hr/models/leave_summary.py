"""
نموذج ملخص الإجازات الشهري
"""
from django.db import models
from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


class LeaveSummary(models.Model):
    """ملخص الإجازات الشهري للموظف"""
    
    employee = models.ForeignKey(
        'Employee',
        on_delete=models.CASCADE,
        related_name='leave_summaries',
        verbose_name='الموظف'
    )
    month = models.DateField(verbose_name='الشهر')
    
    # الإجازات حسب النوع
    annual_leave_days = models.IntegerField(default=0, verbose_name='إجازات سنوية')
    sick_leave_days = models.IntegerField(default=0, verbose_name='إجازات مرضية')
    emergency_leave_days = models.IntegerField(default=0, verbose_name='إجازات طارئة')
    unpaid_leave_days = models.IntegerField(default=0, verbose_name='إجازات بدون راتب')
    
    # الإجماليات
    total_paid_days = models.IntegerField(default=0, verbose_name='إجمالي الأيام المدفوعة')
    total_unpaid_days = models.IntegerField(default=0, verbose_name='إجمالي الأيام غير المدفوعة')
    
    # التأثير المالي
    deduction_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='مبلغ الخصم'
    )
    
    # الحالة
    is_calculated = models.BooleanField(default=False, verbose_name='تم الحساب')
    
    # التفاصيل
    details = models.JSONField(
        null=True,
        blank=True,
        verbose_name='التفاصيل',
        help_text='تفاصيل كل إجازة'
    )
    
    # ملاحظات
    notes = models.TextField(blank=True, verbose_name='ملاحظات')
    
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)
    
    class Meta:
        verbose_name = 'ملخص إجازات شهري'
        verbose_name_plural = 'ملخصات الإجازات الشهرية'
        unique_together = ['employee', 'month']
        ordering = ['-month', 'employee']
        indexes = [
            models.Index(fields=['employee', 'month']),
            models.Index(fields=['month', 'is_calculated']),
        ]
    
    def __str__(self):
        return f"{self.employee.get_full_name_ar()} - {self.month.strftime('%Y-%m')}"
    
    def calculate(self):
        """حساب ملخص الإجازات للشهر"""
        from .leave import Leave
        
        logger.info(f"بدء حساب ملخص إجازات {self.employee.get_full_name_ar()} لشهر {self.month.strftime('%Y-%m')}")
        
        # تحديد بداية ونهاية الشهر
        start_date = self.month.replace(day=1)
        if self.month.month == 12:
            end_date = self.month.replace(year=self.month.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end_date = self.month.replace(month=self.month.month + 1, day=1) - timedelta(days=1)
        
        # إعادة تعيين القيم
        self.annual_leave_days = 0
        self.sick_leave_days = 0
        self.emergency_leave_days = 0
        self.unpaid_leave_days = 0
        self.total_paid_days = 0
        self.total_unpaid_days = 0
        self.deduction_amount = Decimal('0')
        
        # جلب الإجازات المعتمدة
        leaves = Leave.objects.filter(
            employee=self.employee,
            status='approved',
            start_date__lte=end_date,
            end_date__gte=start_date
        )
        
        details_list = []
        
        for leave in leaves:
            # حساب الأيام المتداخلة مع الشهر
            leave_start = max(leave.start_date, start_date)
            leave_end = min(leave.end_date, end_date)
            days_in_month = (leave_end - leave_start).days + 1
            
            # تصنيف حسب النوع
            leave_type_name = leave.leave_type.name_ar.lower()
            
            if 'سنوية' in leave_type_name or 'annual' in leave_type_name:
                self.annual_leave_days += days_in_month
            elif 'مرضية' in leave_type_name or 'sick' in leave_type_name:
                self.sick_leave_days += days_in_month
            elif 'طارئة' in leave_type_name or 'emergency' in leave_type_name:
                self.emergency_leave_days += days_in_month
            
            # حساب المدفوع وغير المدفوع
            if leave.leave_type.is_paid:
                self.total_paid_days += days_in_month
            else:
                self.total_unpaid_days += days_in_month
                self.unpaid_leave_days += days_in_month
            
            # حفظ التفاصيل
            details_list.append({
                'leave_id': leave.id,
                'leave_type': leave.leave_type.name_ar,
                'start_date': str(leave.start_date),
                'end_date': str(leave.end_date),
                'days_in_month': days_in_month,
                'is_paid': leave.leave_type.is_paid
            })
        
        self.details = details_list
        
        # حساب مبلغ الخصم للإجازات غير المدفوعة
        contract = self.employee.contracts.filter(status='active').first()
        if contract and self.total_unpaid_days > 0:
            daily_salary = (Decimal(str(contract.basic_salary)) / Decimal('30')).quantize(
                Decimal('0.01'), 
                rounding=ROUND_HALF_UP
            )
            self.deduction_amount = (Decimal(str(self.total_unpaid_days)) * daily_salary).quantize(
                Decimal('0.01'), 
                rounding=ROUND_HALF_UP
            )
        
        self.is_calculated = True
        self.save()
        
        logger.info(f"تم حساب الملخص: {self.total_paid_days} يوم مدفوع، {self.total_unpaid_days} يوم غير مدفوع")
    
    @property
    def total_leave_days(self):
        """إجمالي أيام الإجازات"""
        return self.total_paid_days + self.total_unpaid_days

