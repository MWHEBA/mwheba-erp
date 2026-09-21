"""
خدمة إدارة الحضور والانصراف والمحرك الحسابي الموحد (Unified Attendance & Overtime Engine)
Single Source of Truth لجميع حسابات الحضور والانصراف في MWHEBA ERP.
"""
from datetime import datetime, timedelta, date, time
from decimal import Decimal
from typing import Optional, Tuple, Set
import logging
from django.db import transaction
from django.utils import timezone
from django.db.models import Q

from ..models import Shift, Attendance, Employee, OfficialHoliday, RamadanSettings, Leave, PermissionRequest
from ..utils.payroll_helpers import (
    get_weekly_off_days,
    get_overtime_settings,
    get_grace_period_mode,
    get_missing_checkout_policy,
    get_payroll_period,
)

logger = logging.getLogger(__name__)


class AttendanceService:
    """خدمة إدارة الحضور والانصراف والمحرك الحسابي الموحد"""

    @staticmethod
    def _is_ramadan_day(target_date: date) -> bool:
        """هل هذا اليوم يقع في شهر رمضان؟"""
        return RamadanSettings.objects.filter(
            start_date__lte=target_date,
            end_date__gte=target_date
        ).exists()

    @staticmethod
    def _get_reference_times(shift: Shift, target_date: date) -> Tuple[time, time]:
        """
        إرجاع وقتي البداية والنهاية المرجعيين لهذا اليوم.
        في رمضان: يستخدم ramadan_start_time/end_time إن وجدا.
        """
        if AttendanceService._is_ramadan_day(target_date):
            if shift.ramadan_start_time and shift.ramadan_end_time:
                return shift.ramadan_start_time, shift.ramadan_end_time
        return shift.start_time, shift.end_time

    @staticmethod
    def resolve_effective_shift(employee: Employee, check_in_dt: Optional[datetime] = None) -> Shift:
        """
        التعرف الذكي على الوردية المناسبة:
        1. إذا كان الموظف لديه وردية أساسية وبصم في وقت يقترب من وردية أخرى نشطة (Rotational Shift Proximity)، يتعرف عليها تلقائياً.
        2. الوردية المخصصة للموظف (employee.shift).
        3. الوردية الافتراضية للشركة (Fallback Default Shift).
        """
        active_shifts = list(Shift.objects.filter(is_active=True))
        if not active_shifts:
            raise ValueError('لا توجد أي وردية نشطة في النظام، يرجى إنشاء وردية أولاً')

        assigned_shift = employee.shift

        if check_in_dt and active_shifts:
            check_in_local = timezone.localtime(check_in_dt) if timezone.is_aware(check_in_dt) else check_in_dt
            check_in_time = check_in_local.time()
            check_in_minutes = check_in_time.hour * 60 + check_in_time.minute

            best_shift = None
            min_diff = 999999

            for s in active_shifts:
                ref_start, _ = AttendanceService._get_reference_times(s, check_in_local.date())
                shift_minutes = ref_start.hour * 60 + ref_start.minute
                diff = abs(check_in_minutes - shift_minutes)
                # إذا كانت المسافة أقل من 90 دقيقة، نعتبرها مطابقة قرب الوردية
                if diff < min_diff:
                    min_diff = diff
                    best_shift = s

            # إذا وجدنا وردية قريبة جداً (في حدود 120 دقيقة) والموظف ورديته الأساسية بعيدة جداً
            if best_shift and min_diff <= 120:
                if assigned_shift:
                    assigned_ref, _ = AttendanceService._get_reference_times(assigned_shift, check_in_local.date())
                    assigned_diff = abs(check_in_minutes - (assigned_ref.hour * 60 + assigned_ref.minute))
                    # لو الوردية التانية أقرب بكتير (فارق ساعتين أو أكتر) → نختار الأقرب
                    if assigned_diff - min_diff >= 120:
                        return best_shift
                else:
                    return best_shift

        if assigned_shift:
            return assigned_shift

        # Fallback to default / regular shift
        from core.models import SystemSetting
        default_shift_id = SystemSetting.get_setting('hr_default_shift_id', None)
        if default_shift_id:
            try:
                return Shift.objects.get(id=int(default_shift_id), is_active=True)
            except Exception:
                pass

        regular_shift = Shift.objects.filter(is_active=True, shift_type='regular').first()
        return regular_shift or active_shifts[0]

    @staticmethod
    def _calculate_late_minutes(check_in: Optional[datetime], shift: Shift, target_date: Optional[date] = None, employee: Optional[Employee] = None) -> int:
        """
        حساب دقائق التأخير مع مراعاة رمضان وفلسفة فترة السماح والتسوية مع الأذونات المعتمدة.
        """
        if not check_in:
            return 0

        check_in_local = timezone.localtime(check_in) if timezone.is_aware(check_in) else check_in
        if target_date is None:
            target_date = check_in_local.date()

        ref_start, _ = AttendanceService._get_reference_times(shift, target_date)
        shift_start = datetime.combine(target_date, ref_start)
        if timezone.is_aware(check_in):
            shift_start = timezone.make_aware(shift_start)

        if check_in_local <= shift_start:
            return 0

        raw_delay_minutes = int((check_in_local - shift_start).total_seconds() / 60)
        grace_in = shift.grace_period_in or 0
        grace_mode = get_grace_period_mode()

        if raw_delay_minutes <= grace_in:
            late_minutes = 0
        else:
            if grace_mode == 'deduct_grace':
                late_minutes = raw_delay_minutes - grace_in
            else:
                # hard_threshold: عند تجاوز فترة السماح يُحسب كامل التأخير من أول دقيقة
                late_minutes = raw_delay_minutes

        # التسوية التلقائية مع أذونات العمل الصباحية المعتمدة
        if employee and late_minutes > 0:
            permissions = PermissionRequest.objects.filter(
                employee=employee,
                date=target_date,
                status='approved'
            )
            for perm in permissions:
                # لو الإذن صباحي أو يغطي وقت التأخير
                hours_val = getattr(perm, 'duration_hours', None) or getattr(perm, 'hours', 0)
                perm_minutes = int(float(hours_val) * 60)
                late_minutes = max(0, late_minutes - perm_minutes)

        return late_minutes

    @staticmethod
    def _calculate_early_leave(check_out: Optional[datetime], shift: Shift, target_date: Optional[date] = None, employee: Optional[Employee] = None) -> int:
        """
        حساب دقائق الانصراف المبكر مع مراعاة رمضان والتسوية مع الأذونات المعتمدة.
        """
        if not check_out:
            return 0

        check_out_local = timezone.localtime(check_out) if timezone.is_aware(check_out) else check_out
        if target_date is None:
            target_date = check_out_local.date()

        _, ref_end = AttendanceService._get_reference_times(shift, target_date)
        ref_start, _ = AttendanceService._get_reference_times(shift, target_date)

        shift_end = datetime.combine(target_date, ref_end)
        # إذا كانت الوردية ليلية وتمتد لليوم التالي
        if ref_end < ref_start:
            shift_end += timedelta(days=1)

        if timezone.is_aware(check_out):
            shift_end = timezone.make_aware(shift_end)

        if check_out_local >= shift_end:
            return 0

        raw_early_minutes = int((shift_end - check_out_local).total_seconds() / 60)
        grace_out = shift.grace_period_out or 0
        grace_mode = get_grace_period_mode()

        if raw_early_minutes <= grace_out:
            early_minutes = 0
        else:
            if grace_mode == 'deduct_grace':
                early_minutes = raw_early_minutes - grace_out
            else:
                early_minutes = raw_early_minutes

        # التسوية التلقائية مع أذونات العمل المسائية المعتمدة
        if employee and early_minutes > 0:
            permissions = PermissionRequest.objects.filter(
                employee=employee,
                date=target_date,
                status='approved'
            )
            for perm in permissions:
                hours_val = getattr(perm, 'duration_hours', None) or getattr(perm, 'hours', 0)
                perm_minutes = int(float(hours_val) * 60)
                early_minutes = max(0, early_minutes - perm_minutes)

        return early_minutes

    @staticmethod
    def get_official_holiday_dates(date_from: date, date_to: date) -> Set[date]:
        """استرجاع مجموعة تواريخ العطلات الرسمية النشطة للبحث السريع O(1)"""
        holidays = OfficialHoliday.objects.filter(
            is_active=True,
            start_date__lte=date_to,
            end_date__gte=date_from
        )
        result = set()
        for h in holidays:
            cur = max(h.start_date, date_from)
            end = min(h.end_date, date_to)
            while cur <= end:
                result.add(cur)
                cur += timedelta(days=1)
        return result

    @staticmethod
    def calculate_daily_attendance(attendance: Attendance) -> None:
        """
        المحرك المركزي الموحد لحساب اليومية لسجل الحضور:
        - يحسب ساعات العمل بدقة مع تطبيق حدود الوردية الرسمية (Shift Start Boundary).
        - يمنع احتساب إضافي صباحي قبل موعد الوردية.
        - يطبق سياسة تسوية التأخير الصباحي مقابل الإضافي المسائي (فصل تام / 1:1 / نسبة).
        - يطبق حظر الخصم المزدوج لنصف اليوم.
        - يدعم ساعات الإضافي في العطلات والإجازات الرسمية.
        - يعالج نسيان بصمة الانصراف وفق السياسة المعتمدة.
        """
        emp = attendance.employee
        target_date = attendance.date
        shift = attendance.shift or AttendanceService.resolve_effective_shift(emp, attendance.check_in)
        attendance.shift = shift

        # 1. التحقق من العطلات والإجازات الأسبوعية
        is_holiday = OfficialHoliday.objects.filter(
            is_active=True,
            start_date__lte=target_date,
            end_date__gte=target_date
        ).exists()
        weekly_off_days = get_weekly_off_days(shift=shift)
        is_weekly_off = target_date.weekday() in weekly_off_days

        ot_settings = get_overtime_settings()
        shift_req_hours = shift.calculate_ramadan_work_hours() if AttendanceService._is_ramadan_day(target_date) else shift.calculate_work_hours()

        # لو مفيش بصمة دخول
        if not attendance.check_in:
            attendance.work_hours = Decimal('0.00')
            attendance.overtime_hours = Decimal('0.00')
            attendance.late_minutes = 0
            attendance.early_leave_minutes = 0

            # تحديد الحالة في غياب البصمة
            if Leave.objects.filter(employee=emp, start_date__lte=target_date, end_date__gte=target_date, status='approved').exists():
                attendance.status = 'on_leave'
            elif PermissionRequest.objects.filter(employee=emp, date=target_date, status='approved').exists():
                attendance.status = 'permission'
            elif is_holiday or is_weekly_off:
                attendance.status = 'present'  # عطلة رسمية / أسبوعية
            else:
                attendance.status = 'absent'
            return

        # 2. حساب دقائق التأخير
        late_min = AttendanceService._calculate_late_minutes(attendance.check_in, shift, target_date, employee=emp)
        attendance.late_minutes = late_min

        # 3. معالجة الانصراف وساعات العمل
        if attendance.check_out:
            attendance.is_missing_checkout = False
            early_min = AttendanceService._calculate_early_leave(attendance.check_out, shift, target_date, employee=emp)
            attendance.early_leave_minutes = early_min

            check_in_ts = timezone.localtime(attendance.check_in) if timezone.is_aware(attendance.check_in) else attendance.check_in
            check_out_ts = timezone.localtime(attendance.check_out) if timezone.is_aware(attendance.check_out) else attendance.check_out

            # تطبيق حدود بداية الوردية (Shift Start Boundary):
            # الحضور المبكر قبل بداية الوردية لا يحتسب كساعات عمل عادية ولا يولد إضافي (إلا في العطلات)
            ref_start, ref_end = AttendanceService._get_reference_times(shift, target_date)
            shift_start_dt = datetime.combine(target_date, ref_start)
            if timezone.is_aware(attendance.check_in):
                shift_start_dt = timezone.make_aware(shift_start_dt)

            if not (is_holiday or is_weekly_off):
                effective_start = max(check_in_ts, shift_start_dt)
            else:
                effective_start = check_in_ts

            if check_out_ts > effective_start:
                delta = check_out_ts - effective_start
                raw_work_hours = Decimal(str(round(delta.total_seconds() / 3600, 2)))
            else:
                raw_work_hours = Decimal('0.00')

            attendance.work_hours = raw_work_hours

            # 4. حساب ساعات العمل الإضافي (Overtime Engine)
            if is_holiday or is_weekly_off:
                # يوم عطلة/إجازة أسبوعية: كل ساعات العمل الفعلية تُحتسب كإضافي
                attendance.overtime_hours = raw_work_hours
                attendance.status = 'present'
            else:
                # يوم عمل عادي:
                raw_ot_minutes = max(0, int((raw_work_hours - Decimal(str(shift_req_hours))) * 60))
                min_ot_minutes = ot_settings['min_minutes']
                offset_policy = ot_settings['late_offset_policy']
                offset_ratio = ot_settings['late_offset_ratio']

                # تطبيق سياسة تسوية التأخير الصباحي مقابل الإضافي
                if offset_policy == 'offset_full':
                    net_ot_minutes = max(0, raw_ot_minutes - late_min)
                elif offset_policy == 'offset_ratio':
                    net_ot_minutes = max(0, raw_ot_minutes - int(late_min * offset_ratio))
                else:
                    # independent: فصل تام
                    net_ot_minutes = raw_ot_minutes

                if net_ot_minutes >= min_ot_minutes:
                    calculated_ot_hours = Decimal(str(round(net_ot_minutes / 60, 2)))
                    # تطبيق الحد الأقصى لساعات الإضافي يومياً
                    max_ot = ot_settings['max_daily_hours']
                    attendance.overtime_hours = min(calculated_ot_hours, max_ot)
                else:
                    attendance.overtime_hours = Decimal('0.00')

                # تحديد الحالة (present / late / half_day)
                half_day_threshold = Decimal(str(shift_req_hours)) / Decimal('2.0')
                if raw_work_hours <= half_day_threshold and raw_work_hours < Decimal(str(shift_req_hours)):
                    attendance.status = 'half_day'
                    # حظر الخصم المزدوج: تصفير دقائق الانصراف المبكر حتى لا يدفع الموظف جزاء نصف يوم + دقائق مبكرة
                    attendance.early_leave_minutes = 0
                elif late_min > 0:
                    attendance.status = 'late'
                else:
                    attendance.status = 'present'

        else:
            # بصمة حضور بدون انصراف (Missing Check-out)
            missing_policy = get_missing_checkout_policy()
            attendance.is_missing_checkout = True

            if missing_policy == 'count_regular_shift':
                attendance.work_hours = Decimal(str(shift_req_hours))
                attendance.early_leave_minutes = 0
            else:
                attendance.work_hours = Decimal('0.00')
                attendance.early_leave_minutes = 0

            attendance.overtime_hours = Decimal('0.00')
            attendance.status = 'late' if late_min > 0 else 'present'

    @staticmethod
    @transaction.atomic
    def record_check_in(employee: Employee, timestamp: Optional[datetime] = None, shift: Optional[Shift] = None, source: str = 'device', location_name: str = '', is_field_visit: bool = False, customer=None, work_order=None) -> Attendance:
        """
        تسجيل حضور الموظف بطريقة ذرية آمنة (Atomic Transaction with Row Lock)
        """
        if timestamp is None:
            timestamp = timezone.now()

        target_date = (timezone.localtime(timestamp) if timezone.is_aware(timestamp) else timestamp).date()

        if shift is None:
            shift = AttendanceService.resolve_effective_shift(employee, timestamp)

        # قفل السجل باستخدام select_for_update لمنع سباق التزامن عند ذروة 9:00 ص
        attendance = Attendance.objects.select_for_update().filter(employee=employee, date=target_date).first()

        if attendance:
            # لو كان مسجل غياب تلقائي أو مسودة، نقوم بتحديثه بالحضور الفعلي
            attendance.shift = shift
            attendance.check_in = timestamp
            attendance.source = source
            attendance.location_name = location_name
            attendance.is_field_visit = is_field_visit
            if customer:
                attendance.customer = customer
            if work_order:
                attendance.work_order = work_order
        else:
            attendance = Attendance(
                employee=employee,
                date=target_date,
                shift=shift,
                check_in=timestamp,
                source=source,
                location_name=location_name,
                is_field_visit=is_field_visit,
                customer=customer,
                work_order=work_order
            )

        AttendanceService.calculate_daily_attendance(attendance)
        attendance.save()
        AttendanceService._invalidate_draft_payroll(employee, target_date)
        return attendance

    @staticmethod
    @transaction.atomic
    def record_check_out(employee: Employee, timestamp: Optional[datetime] = None) -> Attendance:
        """
        تسجيل انصراف الموظف مع تحديث الحسابات المركزية وإعادة حساب الأوفر تايم
        """
        if timestamp is None:
            timestamp = timezone.now()

        target_date = (timezone.localtime(timestamp) if timezone.is_aware(timestamp) else timestamp).date()

        # فحص الورديات الليلية: إذا لم يوجد سجل لنفس اليوم وكان الوقت صباحاً، نبحث عن سجل الأمس المفتوح
        attendance = Attendance.objects.select_for_update().filter(employee=employee, date=target_date).first()
        if not attendance:
            yesterday = target_date - timedelta(days=1)
            attendance_yesterday = Attendance.objects.select_for_update().filter(
                employee=employee,
                date=yesterday,
                check_in__isnull=False,
                check_out__isnull=True
            ).first()
            if attendance_yesterday:
                attendance = attendance_yesterday

        if not attendance or not attendance.check_in:
            raise ValueError('لم يتم العثور على حركة حضور مفتوحة لتسجيل الانصراف')

        attendance.check_out = timestamp
        AttendanceService.calculate_daily_attendance(attendance)
        attendance.save()
        AttendanceService._invalidate_draft_payroll(employee, attendance.date)
        return attendance

    @staticmethod
    def _invalidate_draft_payroll(employee: Employee, target_date: date) -> None:
        """وسم مسودات الرواتب المفتوحة بأنها بحاجة لإعادة الحساب عند تعديل الحضور"""
        from ..models import Payroll
        from ..utils.payroll_helpers import get_payroll_month_for_date
        month = get_payroll_month_for_date(target_date)
        month_first = month.replace(day=1)
        Payroll.objects.filter(
            employee=employee,
            month__in=[month, month_first, target_date],
            status__in=['draft', 'calculated']
        ).update(is_stale=True)

    @staticmethod
    @transaction.atomic
    def generate_missing_attendances(date_from: date, date_to: date) -> int:
        """
        توليد سجلات الغياب التلقائي مع حصر التعيينات والاستقالات Pro-Rata
        وتجنب الإجازات الرسمية والعطلات الأسبوعية للوردية.
        """
        official_holiday_dates = AttendanceService.get_official_holiday_dates(date_from, date_to)

        # استبعاد المعفيين من البصمة
        employees = Employee.objects.filter(status='active', attendance_exempt=False)
        if not employees.exists():
            return 0

        created_count = 0
        current_date = date_from

        while current_date <= date_to:
            if current_date in official_holiday_dates:
                current_date += timedelta(days=1)
                continue

            existing_attendances = set(
                Attendance.objects.filter(date=current_date).values_list('employee_id', flat=True)
            )

            # فحص الإجازات والأذونات
            employees_on_leave = set(
                Leave.objects.filter(
                    status='approved',
                    start_date__lte=current_date,
                    end_date__gte=current_date
                ).values_list('employee_id', flat=True)
            )

            employees_on_permission = set(
                PermissionRequest.objects.filter(
                    status='approved',
                    date=current_date
                ).values_list('employee_id', flat=True)
            )

            new_records = []
            for emp in employees:
                if emp.id in existing_attendances:
                    continue

                # حصر التعيين وإنهاء الخدمة في منتصف الشهر (Mid-Month Pro-Rata Guard)
                if emp.hire_date and current_date < emp.hire_date:
                    continue
                if emp.termination_date and current_date > emp.termination_date:
                    continue

                shift = AttendanceService.resolve_effective_shift(emp)
                weekly_off_days = get_weekly_off_days(shift=shift)
                if current_date.weekday() in weekly_off_days:
                    continue

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
                        check_in=None,
                        check_out=None,
                        status=status,
                        work_hours=Decimal('0.00'),
                        late_minutes=0,
                        early_leave_minutes=0,
                        overtime_hours=Decimal('0.00'),
                        notes=notes
                    )
                )

            if new_records:
                Attendance.objects.bulk_create(new_records)
                created_count += len(new_records)

            current_date += timedelta(days=1)

        return created_count
