"""
خدمة حساب ملخصات الحضور الشهرية
"""
from decimal import Decimal
from datetime import date, timedelta
from django.db import transaction
from django.utils import timezone
from django.db.models import Sum, Count, Q
from ..models import AttendanceSummary, Attendance, Employee
import logging

logger = logging.getLogger(__name__)


class AttendanceSummaryService:
    """خدمة حساب ملخصات الحضور الشهرية"""
    
    @staticmethod
    @transaction.atomic
    def calculate_monthly_summary(employee, month):
        """
        حساب ملخص الحضور لموظف في شهر معين
        
        Args:
            employee: الموظف
            month: الشهر (datetime.date)
        
        Returns:
            AttendanceSummary: ملخص الحضور
        """
        
        # الحصول على الملخص أو إنشاؤه
        summary, created = AttendanceSummary.objects.get_or_create(
            employee=employee,
            month=month
        )
        
        # حساب الملخص
        summary.calculate()
        
        
        return summary
    
    @staticmethod
    @transaction.atomic
    def calculate_all_summaries_for_month(month, employees=None):
        """
        حساب ملخصات الحضور لجميع الموظفين في شهر معين
        
        Args:
            month: الشهر
            employees: قائمة الموظفين (اختياري)
        
        Returns:
            dict: نتائج الحساب
        """
        if employees is None:
            employees = Employee.objects.filter(status='active')
        
        results = {
            'success': [],
            'failed': [],
            'total': employees.count()
        }
        
        for employee in employees:
            try:
                summary = AttendanceSummaryService.calculate_monthly_summary(employee, month)
                results['success'].append({
                    'employee': employee,
                    'summary': summary
                })
            except Exception as e:
                logger.error(f"فشل حساب ملخص حضور {employee.get_full_name_ar()}: {str(e)}")
                results['failed'].append({
                    'employee': employee,
                    'error': str(e)
                })
        
        
        return results
    
    @staticmethod
    def get_attendance_statistics(employee, start_date, end_date):
        """
        الحصول على إحصائيات الحضور لفترة معينة
        
        Args:
            employee: الموظف
            start_date: تاريخ البداية
            end_date: تاريخ النهاية
        
        Returns:
            dict: الإحصائيات
        """
        from django.db.models import Sum, Count, Avg
        
        attendances = Attendance.objects.filter(
            employee=employee,
            date__gte=start_date,
            date__lte=end_date
        )
        
        stats = attendances.aggregate(
            total_days=Count('id'),
            present_days=Count('id', filter=Q(status='present')),
            absent_days=Count('id', filter=Q(status='absent')),
            late_days=Count('id', filter=Q(status='late')),
            total_work_hours=Sum('work_hours'),
            total_late_minutes=Sum('late_minutes'),
            total_overtime_hours=Sum('overtime_hours'),
            avg_work_hours=Avg('work_hours')
        )
        
        return stats
    
    @staticmethod
    def approve_summary(summary, approved_by):
        """
        اعتماد ملخص الحضور
        
        Args:
            summary: ملخص الحضور
            approved_by: المستخدم المعتمد
        
        Returns:
            AttendanceSummary: الملخص المعتمد
        """
        summary.approve(approved_by)
        
        return summary
    
    @staticmethod
    def recalculate_summary(summary):
        """
        إعادة حساب ملخص الحضور

        Args:
            summary: ملخص الحضور

        Returns:
            AttendanceSummary: الملخص المحدث
        """
        # Guard: cannot recalculate if payroll already processed for this month
        payroll_exists = summary.employee.payrolls.filter(
            month=summary.month,
            status__in=['calculated', 'approved', 'paid']
        ).exists()
        if payroll_exists:
            raise ValueError(
                f'لا يمكن إعادة حساب ملخص الحضور للموظف {summary.employee.get_full_name_ar()} '
                f'لشهر {summary.month.strftime("%Y-%m")} — تم حساب الراتب بالفعل'
            )

        summary.is_calculated = False
        summary.is_approved = False
        summary.approved_by = None
        summary.approved_at = None
        summary.save()

        # تأكد إن أيام الإجازات المعتمدة حالتها on_leave قبل الحساب
        from hr.models import Leave, Attendance
        from hr.utils.payroll_helpers import get_payroll_period
        from datetime import timedelta as _td
        _start, _end, _ = get_payroll_period(summary.month)
        _leave_dates = set()
        for lv in Leave.objects.filter(
            employee=summary.employee, status='approved',
            start_date__lte=_end, end_date__gte=_start
        ):
            _cur = max(lv.start_date, _start)
            while _cur <= min(lv.end_date, _end):
                _leave_dates.add(_cur)
                _cur += _td(days=1)
        if _leave_dates:
            Attendance.objects.filter(
                employee=summary.employee,
                date__in=_leave_dates,
                status='absent'
            ).update(status='on_leave', notes='تم التحديث تلقائياً عند إعادة الحساب')

        summary.calculate()

        return summary

