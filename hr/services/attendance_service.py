"""
خدمة إدارة الحضور والانصراف
"""
from datetime import datetime, timedelta
from django.db import transaction
from django.utils import timezone
from ..models import Attendance, Shift


class AttendanceService:
    """خدمة إدارة الحضور والانصراف"""
    
    @staticmethod
    @transaction.atomic
    def record_check_in(employee, timestamp=None, shift=None):
        """
        تسجيل حضور الموظف
        
        Args:
            employee: الموظف
            timestamp: وقت الحضور (اختياري)
            shift: الوردية (اختياري)
        
        Returns:
            Attendance: سجل الحضور
        """
        if timestamp is None:
            timestamp = timezone.now()
        
        date = timestamp.date()
        
        # التحقق من عدم وجود سجل حضور لنفس اليوم
        if Attendance.objects.filter(employee=employee, date=date).exists():
            raise ValueError('تم تسجيل الحضور مسبقاً لهذا اليوم')
        
        # الحصول على الوردية
        if shift is None:
            shift = AttendanceService._get_employee_shift(employee)
        
        # حساب التأخير
        late_minutes = AttendanceService._calculate_late_minutes(timestamp, shift)
        
        # تحديد الحالة
        status = 'late' if late_minutes > shift.grace_period_in else 'present'
        
        # إنشاء سجل الحضور
        attendance = Attendance.objects.create(
            employee=employee,
            date=date,
            shift=shift,
            check_in=timestamp,
            late_minutes=late_minutes,
            status=status
        )
        
        return attendance
    
    @staticmethod
    @transaction.atomic
    def record_check_out(employee, timestamp=None):
        """
        تسجيل انصراف الموظف
        
        Args:
            employee: الموظف
            timestamp: وقت الانصراف (اختياري)
        
        Returns:
            Attendance: سجل الحضور المحدث
        """
        if timestamp is None:
            timestamp = timezone.now()
        
        date = timestamp.date()
        
        # الحصول على سجل الحضور
        try:
            attendance = Attendance.objects.get(employee=employee, date=date)
        except Attendance.DoesNotExist:
            raise ValueError('لم يتم تسجيل الحضور لهذا اليوم')
        
        # التحقق من عدم تسجيل الانصراف مسبقاً
        if attendance.check_out:
            raise ValueError('تم تسجيل الانصراف مسبقاً')
        
        # تسجيل الانصراف
        attendance.check_out = timestamp
        
        # حساب ساعات العمل
        attendance.calculate_work_hours()
        
        # حساب الانصراف المبكر
        early_leave = AttendanceService._calculate_early_leave(timestamp, attendance.shift)
        attendance.early_leave_minutes = early_leave
        
        attendance.save()
        
        return attendance
    
    @staticmethod
    def _get_employee_shift(employee):
        """الحصول على وردية الموظف"""
        # يمكن تطوير هذا لدعم جدول ورديات متغير
        return Shift.objects.filter(is_active=True).first()
    
    @staticmethod
    def _calculate_late_minutes(check_in, shift):
        """حساب دقائق التأخير"""
        shift_start = timezone.make_aware(datetime.combine(check_in.date(), shift.start_time))
        if check_in > shift_start:
            delta = check_in - shift_start
            return int(delta.total_seconds() / 60)
        return 0
    
    @staticmethod
    def _calculate_early_leave(check_out, shift):
        """حساب دقائق الانصراف المبكر"""
        shift_end = timezone.make_aware(datetime.combine(check_out.date(), shift.end_time))
        if check_out < shift_end:
            delta = shift_end - check_out
            return int(delta.total_seconds() / 60)
        return 0
    
    @staticmethod
    def calculate_monthly_attendance(employee, month):
        """
        حساب إحصائيات الحضور الشهرية
        
        Args:
            employee: الموظف
            month: الشهر (datetime.date)
        
        Returns:
            dict: إحصائيات الحضور
        """
        attendances = Attendance.objects.filter(
            employee=employee,
            date__year=month.year,
            date__month=month.month
        )
        
        return {
            'total_days': attendances.count(),
            'present_days': attendances.filter(status='present').count(),
            'late_days': attendances.filter(status='late').count(),
            'absent_days': attendances.filter(status='absent').count(),
            'total_work_hours': sum(float(a.work_hours) for a in attendances),
            'total_overtime_hours': sum(float(a.overtime_hours) for a in attendances),
            'total_late_minutes': sum(a.late_minutes for a in attendances),
        }
