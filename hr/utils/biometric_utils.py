import logging
from django.db import transaction
from django.utils import timezone

from ..models import BiometricLog, BiometricUserMapping, Employee

logger = logging.getLogger(__name__)


def _get_mapping_for_log(log):
    mappings = BiometricUserMapping.objects.filter(
        biometric_user_id=str(log.user_id),
        is_active=True,
    )
    if not mappings.exists():
        return None
    if log.device_id:
        device_mapping = mappings.filter(device_id=log.device_id).first()
        if device_mapping is not None:
            return device_mapping
    return mappings.filter(device__isnull=True).first() or mappings.first()


def link_single_log(log, employee_id=None):
    employee = None
    if employee_id:
        try:
            employee = Employee.objects.get(pk=employee_id)
        except Employee.DoesNotExist:
            return False, "لا يوجد موظف بهذا المعرف"
    else:
        mapping = _get_mapping_for_log(log)
        if mapping is None:
            return False, "لم يتم العثور على ربط مناسب لهذا السجل"
        employee = mapping.employee
        if employee is None:
            return False, "الربط لا يحتوي على موظف فعّال"

    if log.employee_id == employee.id:
        return True, "السجل مربوط بالفعل بنفس الموظف"

    log.employee = employee
    log.save(update_fields=["employee"])
    name = employee.get_full_name_ar() if hasattr(employee, "get_full_name_ar") else str(employee)
    return True, f"تم ربط السجل بالموظف: {name}"


def process_single_log(log):
    if log.employee is None:
        success, _ = link_single_log(log)
        if not success:
            return False, "لا يمكن معالجة السجل بدون ربط موظف"

    if log.is_processed:
        return True, "تمت معالجة السجل مسبقاً"

    log.is_processed = True
    log.processed_at = timezone.now()
    log.save(update_fields=["is_processed", "processed_at"])
    return True, "تم تعليم السجل كمُعالج"


def get_mapping_suggestions():
    suggestions = []
    user_ids = (
        BiometricLog.objects.filter(employee__isnull=True)
        .values_list("user_id", flat=True)
        .distinct()
    )
    for user_id in user_ids[:200]:
        try:
            employee = Employee.objects.get(employee_number=str(user_id))
        except Employee.DoesNotExist:
            continue
        suggestions.append(
            {
                "user_id": str(user_id),
                "employee_id": employee.id,
                "employee_number": employee.employee_number,
                "employee_name": employee.get_full_name_ar()
                if hasattr(employee, "get_full_name_ar")
                else str(employee),
            }
        )
    return suggestions


@transaction.atomic
def bulk_link_logs(device_id=None, unlinked_only=True, dry_run=False, limit=None):
    qs = BiometricLog.objects.all()
    if device_id:
        qs = qs.filter(device_id=device_id)
    if unlinked_only:
        qs = qs.filter(employee__isnull=True)

    qs = qs.order_by("timestamp")
    if limit:
        qs = qs[: int(limit)]

    logs = list(qs)
    mappings = BiometricUserMapping.objects.filter(is_active=True)

    device_map = {}
    global_map = {}
    for m in mappings:
        key = (m.device_id, str(m.biometric_user_id))
        device_map[key] = m
        if m.device_id is None:
            global_map[str(m.biometric_user_id)] = m

    stats = {
        "total_logs": len(logs),
        "linked": 0,
        "skipped_no_mapping": 0,
    }

    for log in logs:
        key = (log.device_id, str(log.user_id))
        mapping = device_map.get(key)
        if mapping is None:
            mapping = global_map.get(str(log.user_id))
        if mapping is None or mapping.employee is None:
            stats["skipped_no_mapping"] += 1
            continue

        if not dry_run:
            if log.employee_id == mapping.employee_id:
                continue
            log.employee = mapping.employee
            log.save(update_fields=["employee"])
        stats["linked"] += 1

    return stats


def _is_valid_checkout(check_in_ts, candidate_ts, shift, log_date):
    """
    تحديد إذا كانت البصمة الأخيرة تُعتبر check_out حقيقي أم لا.

    المنطق:
    - لو الفارق بين البصمتين أقل من 30% من مدة الوردية → مش check_out
    - مثال: وردية 6.5 ساعة (390 د) → threshold = 117 دقيقة
    - minimum threshold = 60 دقيقة
    """
    shift_hours = shift.calculate_work_hours()
    # threshold = 30% من مدة الوردية بالدقائق (minimum 60 دقيقة)
    threshold_minutes = max(60, int(shift_hours * 60 * 0.3))

    diff_minutes = (candidate_ts - check_in_ts).total_seconds() / 60
    return diff_minutes >= threshold_minutes


def bulk_process_logs(date=None, employee_id=None, unprocessed_only=True, dry_run=False):
    """
    معالجة سجلات البصمة وتحويلها لسجلات حضور.

    القواعد:
    - أول بصمة في اليوم = check_in
    - آخر بصمة في اليوم = check_out لو الفارق بينها وبين الدخول >= نص مدة الوردية
    - لو الفارق صغير جداً → مفيش check_out (الموظف مابصمش خروج)
    - موظف بلا shift → skipped، is_processed=False للمعالجة لاحقاً
    - خطأ في معالجة موظف → skipped، is_processed=False للـ retry
    - كل موظف في transaction منفصلة - خطأ موظف لا يأثر على الباقين
    """
    from ..models import Attendance

    # ربط السجلات غير المربوطة أولاً - في transaction منفصلة مستقلة
    if not dry_run:
        bulk_link_logs(unlinked_only=True, dry_run=False)

    qs = BiometricLog.objects.all()
    if date is not None:
        qs = qs.filter(timestamp__date=date)
    if employee_id is not None:
        qs = qs.filter(employee_id=employee_id)
    if unprocessed_only:
        qs = qs.filter(is_processed=False)

    logs = list(qs.select_related('employee', 'device').order_by('timestamp'))

    stats = {
        "total_logs": len(logs),
        "processed": 0,
        "created": 0,
        "updated": 0,
        "errors": 0,
        "skipped_no_shift": 0,
    }

    if not logs:
        return stats

    # تجميع السجلات حسب الموظف واليوم
    grouped_logs = {}
    for log in logs:
        if not log.employee:
            continue
        key = (log.employee.id, log.timestamp.date())
        if key not in grouped_logs:
            grouped_logs[key] = []
        grouped_logs[key].append(log)

    from ..services import AttendanceService

    # جلب الإجازات الرسمية مرة واحدة قبل الـ loop
    if grouped_logs:
        all_dates = [log_date for (_, log_date) in grouped_logs.keys()]
        official_holiday_dates = AttendanceService.get_official_holiday_dates(
            min(all_dates), max(all_dates)
        )
    else:
        official_holiday_dates = set()

    for (emp_id, log_date), day_logs in grouped_logs.items():
        # Skip official holidays — تجاهل البصمة في أيام الإجازات الرسمية
        if log_date in official_holiday_dates:
            if not dry_run:
                for log in day_logs:
                    log.is_processed = True
                    log.save(update_fields=['is_processed'])
            stats["processed"] += len(day_logs)
            continue

        if dry_run:
            stats["processed"] += len(day_logs)
            continue

        # كل موظف في transaction مستقلة - فشل موظف لا يأثر على الباقين
        try:
            with transaction.atomic():
                employee = day_logs[0].employee

                # جلب كل بصمات الموظف في هذا اليوم (مش بس الغير معالجة)
                # عشان لو البصمة الأولى اتعالجت قبل كده، نضمها مع الجديدة
                all_day_logs = list(
                    BiometricLog.objects.filter(
                        employee=employee,
                        timestamp__date=log_date
                    ).order_by('timestamp')
                )
                day_logs_sorted = all_day_logs if all_day_logs else sorted(day_logs, key=lambda x: x.timestamp)
                check_in_log = day_logs_sorted[0]

                # موظف بلا shift → skip بدون تعليم is_processed
                shift = employee.shift
                if not shift:
                    stats["skipped_no_shift"] += len(day_logs)
                    continue

                # تحديد check_out: آخر بصمة بس بشرط إن الفارق بينها وبين الدخول >= نص مدة الوردية
                # لو الفارق صغير → الموظف مابصمش خروج (بصمة مكررة أو خروج مؤقت)
                if len(day_logs_sorted) > 1:
                    last_log = day_logs_sorted[-1]
                    check_out_log = last_log if _is_valid_checkout(
                        check_in_log.timestamp, last_log.timestamp, shift, log_date
                    ) else None
                else:
                    check_out_log = None

                # حساب التأخير والانصراف المبكر
                late_minutes = AttendanceService._calculate_late_minutes(
                    check_in_log.timestamp, shift, log_date
                )
                early_leave_minutes = 0
                if check_out_log:
                    early_leave_minutes = AttendanceService._calculate_early_leave(
                        check_out_log.timestamp, shift, log_date
                    )

                # تحديد الحالة - present أو late بناءً على late_minutes
                status = 'late' if late_minutes > shift.grace_period_in else 'present'

                # حساب work_hours و overtime_hours بدون save داخلي
                if check_out_log:
                    delta = check_out_log.timestamp - check_in_log.timestamp
                    work_hours = round(delta.total_seconds() / 3600, 2)
                    shift_hours = shift.calculate_work_hours()
                    overtime_hours = round(max(0.0, work_hours - shift_hours), 2)
                else:
                    work_hours = 0
                    overtime_hours = 0

                attendance = Attendance.objects.filter(
                    employee=employee,
                    date=log_date
                ).first()

                if attendance:
                    # لو السجل موجود، نستخدم الوردية المحفوظة فيه (مش الوردية الحالية للموظف)
                    # عشان لو الوردية اتغيرت، الداتا القديمة تفضل محسوبة بالوردية الصح
                    effective_shift = attendance.shift or shift
                    if effective_shift != shift:
                        # إعادة حساب الدقائق بالوردية المحفوظة
                        late_minutes = AttendanceService._calculate_late_minutes(
                            check_in_log.timestamp, effective_shift, log_date
                        )
                        early_leave_minutes = 0
                        if check_out_log:
                            early_leave_minutes = AttendanceService._calculate_early_leave(
                                check_out_log.timestamp, effective_shift, log_date
                            )
                        status = 'late' if late_minutes > effective_shift.grace_period_in else 'present'
                        if check_out_log:
                            shift_hours = effective_shift.calculate_work_hours()
                            overtime_hours = round(max(0.0, work_hours - shift_hours), 2)

                    attendance.check_in = check_in_log.timestamp
                    attendance.check_out = check_out_log.timestamp if check_out_log else None
                    attendance.late_minutes = late_minutes
                    attendance.early_leave_minutes = early_leave_minutes
                    attendance.work_hours = work_hours
                    attendance.overtime_hours = overtime_hours
                    attendance.status = status
                    attendance.save(update_fields=[
                        'check_in', 'check_out',
                        'late_minutes', 'early_leave_minutes',
                        'work_hours', 'overtime_hours', 'status'
                    ])
                    stats["updated"] += 1
                else:
                    attendance = Attendance.objects.create(
                        employee=employee,
                        date=log_date,
                        shift=shift,
                        check_in=check_in_log.timestamp,
                        check_out=check_out_log.timestamp if check_out_log else None,
                        late_minutes=late_minutes,
                        early_leave_minutes=early_leave_minutes,
                        work_hours=work_hours,
                        overtime_hours=overtime_hours,
                        status=status
                    )
                    stats["created"] += 1

                # ربط السجلات بالحضور وتعليمها كـ "معالجة"
                for log in day_logs:
                    log.attendance = attendance
                    log.is_processed = True
                    log.processed_at = timezone.now()
                    log.save(update_fields=['attendance', 'is_processed', 'processed_at'])

                stats["processed"] += len(day_logs)

        except Exception as e:
            # السجلات تفضل is_processed=False للـ retry - الموظفين التانيين مش متأثرين
            logger.error(
                f"Error processing employee {emp_id} on {log_date}: {e}",
                exc_info=True
            )
            stats["errors"] += 1

    return stats
