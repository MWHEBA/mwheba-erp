"""
أدوات معالجة وربط سجلات البصمة بالحضور والانصراف
"""
import logging
from datetime import timedelta
from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from ..models import BiometricLog, BiometricUserMapping, Employee, Attendance
from ..services.attendance_service import AttendanceService

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
        # المطابقة الثلاثية الذكية
        user_id_str = str(log.user_id).strip()
        emp = Employee.objects.filter(biometric_user_id=user_id_str).first()
        if emp:
            employee = emp
        else:
            mapping = _get_mapping_for_log(log)
            if mapping and mapping.employee:
                employee = mapping.employee
            else:
                emp_num = Employee.objects.filter(employee_number=user_id_str).first()
                if emp_num:
                    employee = emp_num

        if not employee:
            return False, "لم يتم العثور على ربط مناسب لهذا السجل"

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
    mappings = BiometricUserMapping.objects.filter(is_active=True).select_related('employee')

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
        user_id_str = str(log.user_id).strip()
        # 1. Direct match on Employee.biometric_user_id
        emp = Employee.objects.filter(biometric_user_id=user_id_str).first()
        if not emp:
            # 2. BiometricUserMapping
            key = (log.device_id, user_id_str)
            mapping = device_map.get(key) or global_map.get(user_id_str)
            if mapping and mapping.employee:
                emp = mapping.employee
            else:
                # 3. Employee number
                emp = Employee.objects.filter(employee_number=user_id_str).first()

        if not emp:
            stats["skipped_no_mapping"] += 1
            continue

        if not dry_run:
            if log.employee_id == emp.id:
                continue
            log.employee = emp
            log.save(update_fields=["employee"])
        stats["linked"] += 1

    return stats


def _is_valid_checkout(check_in_ts, candidate_ts, shift, log_date):
    """
    تحديد إذا كانت البصمة الأخيرة تُعتبر check_out حقيقي أم لا.
    """
    shift_hours = shift.calculate_work_hours()
    threshold_minutes = max(45, int(shift_hours * 60 * 0.25))
    diff_minutes = (candidate_ts - check_in_ts).total_seconds() / 60
    return diff_minutes >= threshold_minutes


def bulk_process_logs(date=None, employee_id=None, unprocessed_only=True, dry_run=False):
    """
    معالجة سجلات البصمة وتحويلها لسجلات حضور مركزية موحدة:
    - أول بصمة في اليوم = check_in
    - آخر بصمة في اليوم (إذا كانت بعد فترة كافية) = check_out
    - يفوض جميع الحسابات لمحرك AttendanceService المركزي الموحد
    - كل موظف يُعالج في Transaction ذرية مستقلة محصنة
    """
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

    grouped_logs = {}
    for log in logs:
        if not log.employee:
            continue
        key = (log.employee.id, log.timestamp.date())
        if key not in grouped_logs:
            grouped_logs[key] = []
        grouped_logs[key].append(log)

    for (emp_id, log_date), day_logs in grouped_logs.items():
        if dry_run:
            stats["processed"] += len(day_logs)
            continue

        try:
            with transaction.atomic():
                employee = day_logs[0].employee

                # جلب جميع بصمات الموظف لهذا اليوم (سواء معالجة أو جديدة) لضمان الدقة
                all_day_logs = list(
                    BiometricLog.objects.filter(
                        employee=employee,
                        timestamp__date=log_date
                    ).order_by('timestamp')
                )
                day_logs_sorted = all_day_logs if all_day_logs else sorted(day_logs, key=lambda x: x.timestamp)
                check_in_log = day_logs_sorted[0]

                # التعرف الذكي على الوردية الأقرب
                shift = AttendanceService.resolve_effective_shift(employee, check_in_log.timestamp)

                if len(day_logs_sorted) > 1:
                    last_log = day_logs_sorted[-1]
                    check_out_log = last_log if _is_valid_checkout(
                        check_in_log.timestamp, last_log.timestamp, shift, log_date
                    ) else None
                else:
                    check_out_log = None

                # قفل السجل باستخدام select_for_update
                attendance = Attendance.objects.select_for_update().filter(
                    employee=employee,
                    date=log_date
                ).first()

                is_new = False
                if not attendance:
                    attendance = Attendance(
                        employee=employee,
                        date=log_date,
                        shift=shift,
                        source=check_in_log.source or 'device'
                    )
                    is_new = True

                attendance.shift = shift
                attendance.check_in = check_in_log.timestamp
                attendance.check_out = check_out_log.timestamp if check_out_log else None
                if check_in_log.location_name:
                    attendance.location_name = check_in_log.location_name

                # استدعاء المحرك الحسابي الموحد (Single Source of Truth)
                AttendanceService.calculate_daily_attendance(attendance)
                attendance.save()

                if is_new:
                    stats["created"] += 1
                else:
                    stats["updated"] += 1

                # ربط السجلات بالحضور
                for log in day_logs:
                    log.attendance = attendance
                    log.is_processed = True
                    log.processed_at = timezone.now()
                    log.save(update_fields=['attendance', 'is_processed', 'processed_at'])

                stats["processed"] += len(day_logs)

        except Exception as e:
            logger.error(f"Error processing employee {emp_id} on {log_date}: {e}", exc_info=True)
            stats["errors"] += 1

    return stats
