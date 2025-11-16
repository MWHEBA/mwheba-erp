from django.db import transaction
from django.utils import timezone

from ..models import BiometricLog, BiometricUserMapping, Employee


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


@transaction.atomic
def bulk_process_logs(date=None, employee_id=None, unprocessed_only=True, dry_run=False):
    qs = BiometricLog.objects.all()
    if date is not None:
        qs = qs.filter(timestamp__date=date)
    if employee_id is not None:
        qs = qs.filter(employee_id=employee_id)
    if unprocessed_only:
        qs = qs.filter(is_processed=False)

    logs = list(qs)
    stats = {
        "total_logs": len(logs),
        "processed": 0,
        "errors": 0,
    }

    for log in logs:
        if dry_run:
            stats["processed"] += 1
            continue
        try:
            success, _ = process_single_log(log)
            if success:
                stats["processed"] += 1
            else:
                stats["errors"] += 1
        except Exception:
            stats["errors"] += 1

    return stats
