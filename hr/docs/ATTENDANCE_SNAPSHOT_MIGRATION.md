# Attendance Snapshot Migration Guide

## المشكلة
بعد تطبيق نظام الـ Snapshot للحضور، الملخصات المعتمدة القديمة (قبل التحديث) مش عندها snapshot محفوظ.

## الحل
تم إنشاء management command لعمل backfill للـ snapshots للملخصات المعتمدة القديمة.

## الاستخدام

### 1. التجربة أولاً (Dry Run)
```bash
python manage.py backfill_attendance_snapshots --dry-run
```
هيعرضلك إيه اللي هيتعمل بدون ما يحفظ أي حاجة.

### 2. تطبيق الـ Backfill
```bash
python manage.py backfill_attendance_snapshots
```
هيعمل backfill لكل الملخصات المعتمدة اللي مش عندها snapshot.

### 3. شهر محدد
```bash
python manage.py backfill_attendance_snapshots --month 2024-01
```
هيعمل backfill بس للملخصات في شهر معين.

### 4. إعادة التوليد (Force)
```bash
python manage.py backfill_attendance_snapshots --force
```
هيعيد توليد الـ snapshots حتى لو موجودة (استخدمه بحذر).

## ملاحظات مهمة

### ✅ آمن للاستخدام
- الـ command بيستخدم transactions عشان لو حصل خطأ، مش هيحفظ بيانات ناقصة
- بيعمل validation قبل الحفظ
- بيعرض تقرير مفصل بعد الانتهاء

### ⚠️ متى تستخدمه
- بعد تطبيق التحديث مباشرة (مرة واحدة فقط)
- لو اكتشفت ملخصات معتمدة بدون snapshot

### 🔍 كيف تتأكد إنه اشتغل صح
```python
from hr.models import AttendanceSummary

# Check approved summaries without snapshots
summaries = AttendanceSummary.objects.filter(is_approved=True)
missing = []
for s in summaries:
    if not s.calculation_details or \
       'absence_snapshot' not in s.calculation_details or \
       'late_deduction_snapshot' not in s.calculation_details:
        missing.append(s)

print(f"Summaries missing snapshots: {len(missing)}")
```

## البيانات المحفوظة

### Absence Snapshot
```json
{
  "absence_snapshot": {
    "absent_days": 3,
    "daily_salary": "100",
    "total_deduction": "350",
    "details": [
      {"date": "2024-01-05", "multiplier": "1.0", "deduction": "100"}
    ],
    "backfilled": true
  }
}
```

### Late Deduction Snapshot
```json
{
  "late_deduction_snapshot": {
    "net_penalizable_minutes": 120,
    "penalty_id": 5,
    "penalty_name": "جزاء تأخير متوسط",
    "penalty_days": "0.5",
    "daily_salary": "100",
    "total_deduction": "50",
    "backfilled": true
  }
}
```

الـ `backfilled: true` بيميز الـ snapshots اللي اتعملت بالـ backfill عن اللي اتعملت تلقائياً.
