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
        logger.info(f"بدء حساب ملخص حضور {employee.get_full_name_ar()} لشهر {month.strftime('%Y-%m')}")
        
        # الحصول على الملخص أو إنشاؤه
        summary, created = AttendanceSummary.objects.get_or_create(
            employee=employee,
            month=month
        )
        
        # حساب الملخص
        summary.calculate()
        
        logger.info(f"تم حساب ملخص الحضور: {summary.present_days} يوم حضور، {summary.absent_days} يوم غياب")
        
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
        
        logger.info(f"تم حساب {len(results['success'])} ملخص، فشل {len(results['failed'])}")
        
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
        summary.is_calculated = False
        summary.is_approved = False
        summary.approved_by = None
        summary.approved_at = None
        summary.save()
        
        summary.calculate()
        
        logger.info(f"تم إعادة حساب ملخص حضور {summary.employee.get_full_name_ar()} لشهر {summary.month.strftime('%Y-%m')}")
        
        return summary

