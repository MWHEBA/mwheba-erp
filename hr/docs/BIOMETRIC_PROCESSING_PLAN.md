# خطة معالجة البصمات - Biometric Processing Plan

**الإصدار:** 2.0  
**التاريخ:** مارس 2026  
**الحالة:** جاهزة للتنفيذ

---

## 1. القواعد الأساسية (مؤكدة)

| القاعدة | التفاصيل |
|---------|---------|
| أول بصمة في اليوم | check_in دائماً |
| آخر بصمة في اليوم | check_out (لو في أكتر من بصمة) |
| بصمة واحدة فقط | check_in بدون check_out - حضور ناقص |
| البصمات الوسطى | تُحفظ في BiometricLog فقط، لا تؤثر على الحضور |
| الترتيب | بالـ timestamp فقط، log_type من الجهاز يُتجاهل |
| موظف بلا shift | يُسكيب ويفضل `is_processed=False` للمعالجة لاحقاً |
| موظف عنده إجازة وبصم | يتسجل `present` - البصمة تأخذ الأولوية |
| خطأ في معالجة موظف | يُسكيب ويكمل - السجلات تفضل `is_processed=False` |

---

## 2. ما يعمل صح حالياً (لا يُمس)

- ✅ منطق أول/آخر بصمة في `bulk_process_logs`
- ✅ حساب `late_minutes` في `_calculate_late_minutes` (مع دعم رمضان)
- ✅ حساب `early_leave_minutes` في `_calculate_early_leave` (مع دعم رمضان)
- ✅ منطق رمضان في `_get_reference_times` و `_is_ramadan_day`
- ✅ `grace_period_in` و `grace_period_out`
- ✅ `generate_missing_attendances` (الغياب التلقائي)
- ✅ `BridgeAgentAuthentication` والـ HMAC
- ✅ `get_or_create` في `biometric_bridge_sync` لمنع التكرار
- ✅ `bulk_link_logs` لربط الموظفين (بدون N+1)
- ✅ موظف بلا shift → `skipped_no_shift` + `is_processed=False`
- ✅ بصمة واحدة → حضور بدون انصراف
- ✅ هيكل الـ models بالكامل

---

## 3. المشاكل الحقيقية المطلوب إصلاحها

### 🔴 BUG-01: `LeaveRequest` موديل غير موجود في `_calculate_attendance_status`

**الملف:** `hr/services/attendance_service.py`

**الكود الحالي:**
```python
from ..models import LeaveRequest, PermissionRequest  # ❌ LeaveRequest غير موجود
has_leave = LeaveRequest.objects.filter(...)
if has_leave:
    return 'on_leave'
```

**المشكلة:** الموديل الصح اسمه `Leave` مش `LeaveRequest` (موجود في `hr/models/leave.py`).
النتيجة الحالية: كل استدعاء لـ `_calculate_attendance_status` بيطلع `ImportError`، بيتمسك في:
```python
except ImportError:
    pass  # الحالة بتفضل بالمنطق البسيط (late/present) بدون فحص الإجازات
```
يعني فحص الإجازات معطل تماماً من غير ما حد يلاحظ.

**الإصلاح المطلوب:**
```python
# قبل
from ..models import LeaveRequest, PermissionRequest

# بعد
from ..models import Leave, PermissionRequest
```

---

### 🔴 BUG-02: لو الموظف بصم وعنده إجازة، الكود يرجع `on_leave` بدل `present`

**الملف:** `hr/services/attendance_service.py`

**الكود الحالي:**
```python
has_leave = Leave.objects.filter(..., status='approved').exists()
if has_leave:
    return 'on_leave'  # ❌ حتى لو الموظف بصم فعلاً
```

**المطلوب:** البصمة تأخذ الأولوية. لو الموظف بصم، يتسجل `present` بغض النظر عن الإجازة.

**الإصلاح المطلوب:**
```python
def _calculate_attendance_status(check_in, check_out, shift, employee, target_date) -> str:
    from ..models import Leave, PermissionRequest

    # لو في بصمة حضور، البصمة تأخذ الأولوية دائماً
    if check_in:
        return 'present'

    # لو مفيش بصمة - نفحص الإجازات والأذونات
    has_leave = Leave.objects.filter(
        employee=employee,
        start_date__lte=target_date,
        end_date__gte=target_date,
        status='approved'
    ).exists()
    if has_leave:
        return 'on_leave'

    has_permission = PermissionRequest.objects.filter(
        employee=employee,
        date=target_date,
        status='approved'
    ).exists()
    if has_permission:
        return 'permission'

    return 'absent'
```

**ملاحظة:** الـ `late` مش بيتحدد هنا - بيتحدد في `bulk_process_logs` بناءً على `late_minutes > grace_period_in` بعد ما ترجع `present`. ده المنطق الصح.

---

### 🔴 BUG-03: السجلات الفاشلة تُعلَّم `is_processed=True` وتضيع للأبد

**الملف:** `hr/utils/biometric_utils.py`

**الكود الحالي:**
```python
except Exception as e:
    stats["errors"] += 1
    for log in day_logs:
        if not log.is_processed:
            log.is_processed = True      # ❌ البصمة تضيع
            log.processed_at = timezone.now()
            log.save(update_fields=['is_processed', 'processed_at'])
```

**المشكلة:** أي خطأ غير متوقع (database error، timeout، إلخ) بيخلي البصمة تتعلم كـ "معالجة" وما بترجعش للمعالجة.

**المطلوب:** لو حصل خطأ، السجلات تفضل `is_processed=False` عشان لما تضغط الزرار تاني تتعالج.

**الإصلاح المطلوب:**
```python
except Exception as e:
    logger.error(f"Error processing employee {employee_id} on {date}: {e}", exc_info=True)
    stats["errors"] += 1
    # السجلات تفضل is_processed=False للمعالجة في المرة الجاية
    # لا نعمل أي save هنا
```

---

### 🟡 PERF-01: N+1 Query في ربط الموظفين داخل `bulk_process_logs`

**الملف:** `hr/utils/biometric_utils.py`

**الكود الحالي:**
```python
for log in logs:
    if not log.employee:
        mapping = BiometricUserMapping.objects.filter(...).first()  # query لكل log
        mapping = BiometricUserMapping.objects.filter(...).first()  # query تانية
```

**المشكلة:** لو في 500 بصمة غير مربوطة = 1000+ query.

**الإصلاح المطلوب:** استدعاء `bulk_link_logs()` الموجودة بالفعل قبل بدء المعالجة، بدل إعادة كتابة المنطق:

```python
def bulk_process_logs(date=None, employee_id=None, unprocessed_only=True, dry_run=False):
    # ربط السجلات غير المربوطة أولاً (بدون N+1)
    bulk_link_logs(
        device_id=None,
        unlinked_only=True,
        dry_run=dry_run
    )
    
    # ... باقي الكود
    
    # وحذف الـ loop الداخلي للربط من grouped_logs
```

---

### 🟡 PERF-02: ثلاث `save()` لنفس الـ Attendance record

**الملف:** `hr/utils/biometric_utils.py`

**الكود الحالي:**
```python
attendance.save(update_fields=[...])          # save أول
attendance.calculate_work_hours()             # save تاني جوا الـ method
attendance.save(update_fields=['status'])     # save تالت
```

**المشكلة:** `calculate_work_hours()` بتعمل `self.save()` داخلها، يعني 3 saves لنفس الـ record.

**الإصلاح المطلوب:** حساب `work_hours` و `overtime_hours` يدوياً قبل الـ save الأخير بدل استدعاء الـ method:

```python
# حساب work_hours بدون save داخلي
if check_out_log:
    delta = check_out_log.timestamp - check_in_log.timestamp
    work_hours = round(delta.total_seconds() / 3600, 2)
    shift_hours = shift.calculate_work_hours()
    overtime_hours = max(0, work_hours - shift_hours)
else:
    work_hours = 0
    overtime_hours = 0

# save واحدة بكل الحقول
attendance.save(update_fields=[
    'shift', 'check_in', 'check_out',
    'late_minutes', 'early_leave_minutes',
    'work_hours', 'overtime_hours', 'status'
])
```

---

## 4. ترتيب التنفيذ

| # | الكود | الملف | الوقت المقدر | الأثر |
|---|-------|-------|-------------|-------|
| 1 | BUG-01: تصحيح `LeaveRequest` → `Leave` | `attendance_service.py` | 5 دقائق | فحص الإجازات يشتغل |
| 2 | BUG-02: البصمة تأخذ الأولوية على الإجازة | `attendance_service.py` | 15 دقيقة | منطق الحالة صح |
| 3 | BUG-03: السجلات الفاشلة لا تُعلَّم | `biometric_utils.py` | 10 دقائق | retry يشتغل |
| 4 | PERF-01: استدعاء `bulk_link_logs` | `biometric_utils.py` | 15 دقيقة | أداء أفضل |
| 5 | PERF-02: save واحدة بدل 3 | `biometric_utils.py` | 20 دقيقة | أداء أفضل |

---

## 5. سيناريوهات الاختبار

### سيناريو 1: موظف بصم مرتين
```
Input:  [08:05, 16:10]
Output: check_in=08:05, check_out=16:10
Status: present أو late (حسب grace_period)
```

### سيناريو 2: موظف بصم مرة واحدة
```
Input:  [08:05]
Output: check_in=08:05, check_out=None
Status: present
```

### سيناريو 3: موظف بصم أكثر من مرتين
```
Input:  [08:05, 12:00, 13:00, 16:10]
Output: check_in=08:05, check_out=16:10
        البصمتين الوسطانيين في BiometricLog فقط
```

### سيناريو 4: موظف مالوش shift
```
Input:  [08:05]
Output: is_processed=False، skipped_no_shift++
        يُعالج لما يتضاف له shift
```

### سيناريو 5: موظف عنده إجازة معتمدة وبصم
```
Input:  [08:05] + إجازة معتمدة
Output: check_in=08:05، status='present'
        الإجازة تفضل موجودة في النظام بدون تأثير
```

### سيناريو 6: خطأ في المعالجة
```
Input:  [08:05] + خطأ غير متوقع
Output: is_processed=False، errors++
        يُعالج في المرة الجاية
```

### سيناريو 7: موظف مش مربوط بـ mapping
```
Input:  بصمة بـ user_id غير مربوط
Output: is_processed=False، يُتجاهل في grouped_logs
        يُعالج بعد إضافة الـ mapping
```

---

## 6. ما لن يتغير

- منطق أول/آخر بصمة
- حسابات رمضان
- `generate_missing_attendances`
- `BridgeAgentAuthentication`
- `bulk_link_logs`
- هيكل الـ models
- `_calculate_late_minutes` و `_calculate_early_leave`
- `grace_period_in` و `grace_period_out`
- `_get_employee_shift` → **يتغير**: يرجع `None` لو مفيش shift بدل الـ fallback
