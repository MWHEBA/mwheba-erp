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

        if shift is None:
            raise ValueError('الموظف ليس لديه وردية معينة، يرجى تعيين وردية أولاً')

        # حساب التأخير
        late_minutes = AttendanceService._calculate_late_minutes(timestamp, shift, date)
        
        # تحديد الحالة
        status = AttendanceService._calculate_attendance_status(timestamp, None, shift, employee, date)
        # present يرجع دائماً لو في check_in - نحدد late بناءً على late_minutes
        if status == 'present' and late_minutes > shift.grace_period_in:
            status = 'late'
        
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
        early_leave = AttendanceService._calculate_early_leave(timestamp, attendance.shift, date)
        attendance.early_leave_minutes = early_leave

        # تحديد الحالة بعد اكتمال البصمتين
        new_status = AttendanceService._calculate_attendance_status(
            attendance.check_in, attendance.check_out, attendance.shift, employee, date
        )
        # present يرجع دائماً لو في check_in - نحدد late بناءً على late_minutes
        if new_status == 'present' and attendance.late_minutes > attendance.shift.grace_period_in:
            new_status = 'late'
        attendance.status = new_status
        
        attendance.save()
        
        return attendance
    
    @staticmethod
    def _get_employee_shift(employee):
        """الحصول على وردية الموظف - يرجع None لو مفيش وردية معينة"""
        return employee.shift if employee.shift else None

    @staticmethod
    def _is_ramadan_day(date):
        """هل هذا اليوم يقع في رمضان؟"""
        from ..models import RamadanSettings
        return RamadanSettings.objects.filter(
            start_date__lte=date,
            end_date__gte=date
        ).exists()

    @staticmethod
    def _get_reference_times(shift, date):
        """
        إرجاع وقتي البداية والنهاية المرجعيين لهذا اليوم.
        في رمضان: يستخدم ramadan_start_time/end_time لو موجودين.
        في الأيام العادية أو لو الوردية ما عندهاش أوقات رمضان: يستخدم start_time/end_time.
        """
        if AttendanceService._is_ramadan_day(date):
            if shift.ramadan_start_time and shift.ramadan_end_time:
                return shift.ramadan_start_time, shift.ramadan_end_time
        return shift.start_time, shift.end_time

    @staticmethod
    def _calculate_late_minutes(check_in, shift, date=None):
        """حساب دقائق التأخير مع دعم أوقات رمضان"""
        # Handle both aware and naive datetimes
        if timezone.is_aware(check_in):
            check_in_naive = timezone.localtime(check_in)
        else:
            check_in_naive = check_in

        if date is None:
            date = check_in_naive.date()

        # استخدام الوقت المرجعي الصحيح (عادي أو رمضان)
        ref_start, _ = AttendanceService._get_reference_times(shift, date)

        # Create shift start datetime
        shift_start = datetime.combine(date, ref_start)

        # Make it aware if check_in was aware
        if timezone.is_aware(check_in):
            shift_start = timezone.make_aware(shift_start)

        if check_in > shift_start:
            delta = check_in - shift_start
            return int(delta.total_seconds() / 60)
        return 0

    @staticmethod
    def _calculate_early_leave(check_out, shift, date=None):
        """حساب دقائق الانصراف المبكر مع دعم أوقات رمضان"""
        # Handle both aware and naive datetimes
        if timezone.is_aware(check_out):
            check_out_naive = timezone.localtime(check_out)
        else:
            check_out_naive = check_out

        if date is None:
            date = check_out_naive.date()

        # استخدام الوقت المرجعي الصحيح (عادي أو رمضان)
        _, ref_end = AttendanceService._get_reference_times(shift, date)

        # Create shift end datetime
        shift_end = datetime.combine(date, ref_end)

        # Make it aware if check_out was aware
        if timezone.is_aware(check_out):
            shift_end = timezone.make_aware(shift_end)

        if check_out < shift_end:
            delta = shift_end - check_out
            return int(delta.total_seconds() / 60)
        return 0

    @staticmethod
    def _calculate_attendance_status(check_in, check_out, shift, employee, target_date) -> str:
        """
        حساب حالة الحضور.
        - لو في بصمة حضور: present دائماً (البصمة تأخذ الأولوية على الإجازة)
        - لو مفيش بصمة: نفحص الإجازات والأذونات، ثم absent
        - تحديد late/present يتم في bulk_process_logs بناءً على late_minutes
        """
        from ..models import Leave, PermissionRequest

        # البصمة تأخذ الأولوية - لو الموظف بصم يبقى present بغض النظر عن أي حاجة
        if check_in:
            return 'present'

        # مفيش بصمة - نفحص الإجازات
        has_leave = Leave.objects.filter(
            employee=employee,
            start_date__lte=target_date,
            end_date__gte=target_date,
            status='approved'
        ).exists()
        if has_leave:
            return 'on_leave'

        # نفحص الأذونات
        has_permission = PermissionRequest.objects.filter(
            employee=employee,
            date=target_date,
            status='approved'
        ).exists()
        if has_permission:
            return 'permission'

        return 'absent'
    
    @staticmethod
    def calculate_monthly_attendance(employee, month):
        """
        حساب إحصائيات الحضور الشهرية
        
        Args:
            employee: الموظف
            month: الشهر (datetime.date) - أول يوم في الشهر
        
        Returns:
            dict: إحصائيات الحضور
        """
        from hr.utils.payroll_helpers import get_payroll_period
        start_date, end_date, _ = get_payroll_period(month)

        attendances = Attendance.objects.filter(
            employee=employee,
            date__gte=start_date,
            date__lte=end_date,
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

    @staticmethod
    def get_official_holiday_dates(date_from, date_to):
        """
        يرجع set من التواريخ التي تقع في إجازات رسمية نشطة.
        يُستدعى مرة واحدة قبل أي loop للبحث السريع O(1).
        """
        from ..models import OfficialHoliday
        holidays = OfficialHoliday.objects.filter(
            is_active=True,
            start_date__lte=date_to,
            end_date__gte=date_from
        )
        result = set()
        for h in holidays:
            current = max(h.start_date, date_from)
            end = min(h.end_date, date_to)
            while current <= end:
                result.add(current)
                current += timedelta(days=1)
        return result

    @staticmethod
    @transaction.atomic
    def generate_missing_attendances(date_from, date_to):
        """
        إنشاء سجلات غياب للأيام التي لم يتم تسجيل حضور فيها
        وتجاهل أيام الإجازة الأسبوعية
        """
        from ..models import Employee, Attendance
        from core.models import SystemSetting
        import json
        
        # Get weekly off days
        off_days = SystemSetting.get_setting('hr_weekly_off_days', [4])
        if isinstance(off_days, str):
            try:
                off_days = json.loads(off_days)
            except json.JSONDecodeError:
                off_days = [4]

        # Get official holiday dates once before the loop
        official_holiday_dates = AttendanceService.get_official_holiday_dates(date_from, date_to)

        # Get active employees who are not exempt from attendance
        employees = Employee.objects.filter(status='active', attendance_exempt=False)
        
        if not employees.exists():
            return 0
            
        created_count = 0
        current_date = date_from
        
        while current_date <= date_to:
            # Skip weekly off days
            if current_date.weekday() in off_days:
                current_date += timedelta(days=1)
                continue

            # Skip official holidays
            if current_date in official_holiday_dates:
                current_date += timedelta(days=1)
                continue
                
            # For each employee, check if they have an attendance record on this date
            # We can optimize this by doing a bulk check and bulk create
            existing_attendances = set(
                Attendance.objects.filter(
                    date=current_date
                ).values_list('employee_id', flat=True)
            )
            
            # Check approved leaves for this date
            from ..models import Leave
            employees_on_leave = set(
                Leave.objects.filter(
                    status='approved',
                    start_date__lte=current_date,
                    end_date__gte=current_date
                ).values_list('employee_id', flat=True)
            )
            
            # Check approved permissions for this date
            from ..models import PermissionRequest
            employees_on_permission = set(
                PermissionRequest.objects.filter(
                    status='approved',
                    date=current_date
                ).values_list('employee_id', flat=True)
            )
            
            missing_employees = [emp for emp in employees if emp.id not in existing_attendances]
            
            new_records = []
            for emp in missing_employees:
                shift = AttendanceService._get_employee_shift(emp)
                if not shift:
                    continue
                
                # Determine status based on leave or permission
                if emp.id in employees_on_leave:
                    status = 'on_leave'
                    notes = 'تم التسجيل كإجازة تلقائياً'
                elif emp.id in employees_on_permission:
                    status = 'permission'
                    notes = 'تم التسجيل كإذن تلقائياً'
                else:
                    status = 'absent'
                    notes = 'تم التسجيل كغياب تلقائياً (بدون بصمة)'
                    
                new_records.append(
                    Attendance(
                        employee=emp,
                        date=current_date,
                        shift=shift,
                        check_in=None,  # Allowed after migration
                        check_out=None,
                        status=status,
                        work_hours=0,
                        late_minutes=0,
                        early_leave_minutes=0,
                        overtime_hours=0,
                        notes=notes
                    )
                )
            
            if new_records:
                Attendance.objects.bulk_create(new_records)
                created_count += len(new_records)
                
            current_date += timedelta(days=1)
            
        return created_count
