"""
نموذج ملخص الحضور الشهري
"""
from django.db import models
from django.contrib.auth import get_user_model
from django.db.models import Sum, Count, Q
from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta
import logging

User = get_user_model()
logger = logging.getLogger(__name__)


class AttendanceSummary(models.Model):
    """ملخص الحضور الشهري للموظف"""
    
    employee = models.ForeignKey(
        'Employee',
        on_delete=models.CASCADE,
        related_name='attendance_summaries',
        verbose_name='الموظف'
    )
    month = models.DateField(verbose_name='الشهر')
    
    # إحصائيات الحضور
    total_working_days = models.IntegerField(
        default=0,
        verbose_name='إجمالي أيام العمل',
        help_text='عدد أيام العمل في الشهر (بدون الجمع والعطلات)'
    )
    present_days = models.IntegerField(
        default=0,
        verbose_name='أيام الحضور'
    )
    absent_days = models.IntegerField(
        default=0,
        verbose_name='أيام الغياب'
    )
    late_days = models.IntegerField(
        default=0,
        verbose_name='أيام التأخير'
    )
    half_days = models.IntegerField(
        default=0,
        verbose_name='أيام نصف يوم'
    )
    
    # الإجازات
    paid_leave_days = models.IntegerField(
        default=0,
        verbose_name='أيام الإجازات المدفوعة'
    )
    unpaid_leave_days = models.IntegerField(
        default=0,
        verbose_name='أيام الإجازات غير المدفوعة'
    )
    
    # الساعات
    total_work_hours = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='إجمالي ساعات العمل'
    )
    total_late_minutes = models.IntegerField(
        default=0,
        verbose_name='إجمالي دقائق التأخير'
    )
    total_early_leave_minutes = models.IntegerField(
        default=0,
        verbose_name='إجمالي دقائق الانصراف المبكر'
    )
    total_overtime_hours = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='إجمالي ساعات العمل الإضافي'
    )
    
    # الحسابات المالية
    absence_deduction_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='مبلغ خصم الغياب'
    )
    late_deduction_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='مبلغ خصم التأخير'
    )
    overtime_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='مبلغ العمل الإضافي'
    )
    
    # الحالة
    is_calculated = models.BooleanField(
        default=False,
        verbose_name='تم الحساب'
    )
    is_approved = models.BooleanField(
        default=False,
        verbose_name='معتمد'
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_attendance_summaries',
        verbose_name='اعتمد بواسطة'
    )
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='تاريخ الاعتماد'
    )
    
    # ملاحظات
    notes = models.TextField(blank=True, verbose_name='ملاحظات')
    calculation_details = models.JSONField(
        null=True,
        blank=True,
        verbose_name='تفاصيل الحساب'
    )
    
    # التواريخ
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)
    
    class Meta:
        verbose_name = 'ملخص حضور شهري'
        verbose_name_plural = 'ملخصات الحضور الشهرية'
        unique_together = ['employee', 'month']
        ordering = ['-month', 'employee']
        indexes = [
            models.Index(fields=['employee', 'month']),
            models.Index(fields=['month', 'is_calculated']),
            models.Index(fields=['is_approved']),
        ]
    
    def __str__(self):
        return f"{self.employee.get_full_name_ar()} - {self.month.strftime('%Y-%m')}"
    
    def calculate(self):
        """حساب ملخص الحضور للشهر"""
        from .attendance import Attendance
        from .leave import Leave
        
        logger.info(f"بدء حساب ملخص حضور {self.employee.get_full_name_ar()} لشهر {self.month.strftime('%Y-%m')}")
        
        # تحديد بداية ونهاية الشهر
        start_date = self.month.replace(day=1)
        if self.month.month == 12:
            end_date = self.month.replace(year=self.month.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end_date = self.month.replace(month=self.month.month + 1, day=1) - timedelta(days=1)
        
        # جلب سجلات الحضور
        attendance_records = Attendance.objects.filter(
            employee=self.employee,
            date__gte=start_date,
            date__lte=end_date
        )
        
        # حساب الإحصائيات
        self.present_days = attendance_records.filter(status='present').count()
        self.absent_days = attendance_records.filter(status='absent').count()
        self.late_days = attendance_records.filter(status='late').count()
        self.half_days = attendance_records.filter(status='half_day').count()
        
        # حساب الساعات
        totals = attendance_records.aggregate(
            total_hours=Sum('work_hours'),
            total_late=Sum('late_minutes'),
            total_early=Sum('early_leave_minutes'),
            total_overtime=Sum('overtime_hours')
        )
        
        self.total_work_hours = totals['total_hours'] or Decimal('0')
        self.total_late_minutes = totals['total_late'] or 0
        self.total_early_leave_minutes = totals['total_early'] or 0
        self.total_overtime_hours = totals['total_overtime'] or Decimal('0')
        
        # حساب الإجازات
        leaves = Leave.objects.filter(
            employee=self.employee,
            status='approved',
            start_date__lte=end_date,
            end_date__gte=start_date
        )
        
        self.paid_leave_days = 0
        self.unpaid_leave_days = 0
        
        for leave in leaves:
            # حساب الأيام المتداخلة مع الشهر
            leave_start = max(leave.start_date, start_date)
            leave_end = min(leave.end_date, end_date)
            days_in_month = (leave_end - leave_start).days + 1
            
            if leave.leave_type.is_paid:
                self.paid_leave_days += days_in_month
            else:
                self.unpaid_leave_days += days_in_month
        
        # حساب أيام العمل الفعلية (بدون الجمع)
        self.total_working_days = self._calculate_working_days(start_date, end_date)
        
        # حساب المبالغ المالية
        self._calculate_financial_amounts()
        
        self.is_calculated = True
        self.save()
        
        logger.info(f"تم حساب الملخص: {self.present_days} حضور، {self.absent_days} غياب، {self.total_overtime_hours} ساعة إضافي")
    
    def _calculate_working_days(self, start_date, end_date):
        """حساب أيام العمل (بدون الجمع والعطلات)"""
        working_days = 0
        current_date = start_date
        
        while current_date <= end_date:
            # تخطي الجمعة (4 = Friday في Python)
            if current_date.weekday() != 4:
                working_days += 1
            current_date += timedelta(days=1)
        
        return working_days
    
    def _calculate_financial_amounts(self):
        """حساب المبالغ المالية"""
        # الحصول على العقد النشط
        contract = self.employee.contracts.filter(status='active').first()
        if not contract:
            logger.warning(f"لا يوجد عقد نشط للموظف {self.employee.get_full_name_ar()}")
            return
        
        # حساب الراتب اليومي
        daily_salary = (Decimal(str(contract.basic_salary)) / Decimal('30')).quantize(
            Decimal('0.01'), 
            rounding=ROUND_HALF_UP
        )
        
        # حساب خصم الغياب
        self.absence_deduction_amount = (Decimal(str(self.absent_days)) * daily_salary).quantize(
            Decimal('0.01'), 
            rounding=ROUND_HALF_UP
        )
        
        # حساب خصم الإجازات غير المدفوعة
        self.absence_deduction_amount += (Decimal(str(self.unpaid_leave_days)) * daily_salary).quantize(
            Decimal('0.01'), 
            rounding=ROUND_HALF_UP
        )
        
        # حساب خصم التأخير (كل 60 دقيقة = ساعة من اليوم)
        if self.total_late_minutes > 0:
            late_hours = Decimal(str(self.total_late_minutes)) / Decimal('60')
            hourly_salary = daily_salary / Decimal('8')  # assuming 8 hours workday
            self.late_deduction_amount = (late_hours * hourly_salary).quantize(
                Decimal('0.01'), 
                rounding=ROUND_HALF_UP
            )
        
        # حساب العمل الإضافي
        if self.total_overtime_hours > 0:
            hourly_salary = daily_salary / Decimal('8')
            overtime_rate = hourly_salary * Decimal('1.5')  # 150% للعمل الإضافي
            self.overtime_amount = (Decimal(str(self.total_overtime_hours)) * overtime_rate).quantize(
                Decimal('0.01'), 
                rounding=ROUND_HALF_UP
            )
    
    def approve(self, approved_by):
        """اعتماد ملخص الحضور"""
        from django.utils import timezone
        
        self.is_approved = True
        self.approved_by = approved_by
        self.approved_at = timezone.now()
        self.save()
        
        logger.info(f"تم اعتماد ملخص حضور {self.employee.get_full_name_ar()} لشهر {self.month.strftime('%Y-%m')}")
    
    @property
    def attendance_rate(self):
        """نسبة الحضور"""
        if self.total_working_days > 0:
            return (self.present_days / self.total_working_days) * 100
        return 0
    
    @property
    def total_deductions(self):
        """إجمالي الخصومات"""
        return self.absence_deduction_amount + self.late_deduction_amount

