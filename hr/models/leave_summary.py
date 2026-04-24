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
    annual_leave_days = models.IntegerField(default=0, verbose_name='إجازات اعتيادية')
    sick_leave_days = models.IntegerField(default=0, verbose_name='إجازات مرضية')
    emergency_leave_days = models.IntegerField(default=0, verbose_name='إجازات طارئة')
    exceptional_leave_days = models.IntegerField(default=0, verbose_name='إجازات استثنائية')
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
        from hr.utils.payroll_helpers import get_payroll_period
        
        # تحديد بداية ونهاية الدورة (تدعم الدورة المرنة)
        start_date, end_date, _ = get_payroll_period(self.month)
        
        # إعادة تعيين القيم
        self.annual_leave_days = 0
        self.sick_leave_days = 0
        self.emergency_leave_days = 0
        self.exceptional_leave_days = 0
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
            
            # ✅ تصنيف ديناميكي حسب category
            if leave.leave_type.category == 'annual':
                self.annual_leave_days += days_in_month
            elif leave.leave_type.category == 'sick':
                self.sick_leave_days += days_in_month
            elif leave.leave_type.category == 'emergency':
                self.emergency_leave_days += days_in_month
            elif leave.leave_type.category == 'exceptional':
                # الإجازات الاستثنائية دائماً مدفوعة ومستقلة
                self.exceptional_leave_days += days_in_month
            elif leave.leave_type.category == 'unpaid':
                # unpaid category — يُحسب في unpaid_leave_days عبر is_paid أدناه
                pass
            
            # حساب المدفوع وغير المدفوع
            # unpaid_leave_days يُحسب مرة واحدة فقط بناءً على is_paid
            if leave.leave_type.is_paid:
                self.total_paid_days += days_in_month
            else:
                self.total_unpaid_days += days_in_month
                self.unpaid_leave_days += days_in_month
            
            # حفظ التفاصيل — المعامل يُؤخذ من الإجازة نفسها (مش من النوع)
            details_list.append({
                'leave_id': leave.id,
                'leave_type': leave.leave_type.name_ar,
                'start_date': str(leave.start_date),
                'end_date': str(leave.end_date),
                'days_in_month': days_in_month,
                'is_paid': leave.leave_type.is_paid,
                'deduction_multiplier': str(leave.deduction_multiplier),
            })
        
        self.details = details_list
        
        # حساب مبلغ الخصم للإجازات غير المدفوعة (مع مراعاة deduction_multiplier لكل نوع)
        # مع دعم الدورة المرنة
        from hr.utils.payroll_helpers import get_payroll_period
        from django.db.models import Q
        _, period_end, _ = get_payroll_period(self.month)
        contract = self.employee.contracts.filter(
            status='active',
            start_date__lte=period_end
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=self.month)
        ).order_by('-start_date').first()
        if contract and self.total_unpaid_days > 0:
            daily_salary = (Decimal(str(contract.basic_salary)) / Decimal('30')).quantize(
                Decimal('0.01'),
                rounding=ROUND_HALF_UP
            )
            total_deduction = Decimal('0')
            for detail in details_list:
                if not detail['is_paid']:
                    multiplier = Decimal(detail.get('deduction_multiplier', '1.0'))
                    total_deduction += (
                        Decimal(str(detail['days_in_month'])) * daily_salary * multiplier
                    ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            self.deduction_amount = total_deduction.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        self.is_calculated = True
        self.save()
        
    
    @property
    def total_leave_days(self):
        """إجمالي أيام الإجازات"""
        return self.total_paid_days + self.total_unpaid_days

