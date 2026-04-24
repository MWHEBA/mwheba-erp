# وحدة إدارة الموارد البشرية (HR Module)

## نظرة عامة

وحدة متكاملة لإدارة الموارد البشرية تشمل:
- إدارة بيانات الموظفين
- الحضور والانصراف
- الإجازات
- الرواتب والسلف

## التثبيت

### 1. إضافة التطبيق للـ INSTALLED_APPS

```python
INSTALLED_APPS = [
    ...
    'hr.apps.HrConfig',
]
```

### 2. تطبيق Migrations

```bash
python manage.py migrate hr
```

### 3. تحميل البيانات الأولية

```bash
python manage.py loaddata hr/fixtures/initial_data.json
```

## الهيكل

```
hr/
├── models/              # النماذج (11 نموذج)
├── services/            # الخدمات (4 خدمات)
├── views.py             # Views
├── urls.py              # URLs
├── admin.py             # Admin
└── fixtures/            # البيانات الأولية
```

## النماذج

### الأساسية
- **Employee**: الموظف
- **Department**: القسم
- **JobTitle**: المسمى الوظيفي

### الحضور
- **Shift**: الوردية
- **Attendance**: الحضور

### الإجازات
- **LeaveType**: نوع الإجازة
- **LeaveBalance**: رصيد الإجازات
- **Leave**: الإجازة

### الرواتب
- **Salary**: الراتب
- **Payroll**: قسيمة الراتب
- **Advance**: السلفة

## الخدمات

### EmployeeService
```python
from hr.services import EmployeeService

# إنشاء موظف
employee = EmployeeService.create_employee(data, created_by)

# إنهاء خدمة
EmployeeService.terminate_employee(employee, termination_data, user)
```

### AttendanceService
```python
from hr.services import AttendanceService

# تسجيل حضور
attendance = AttendanceService.record_check_in(employee)

# تسجيل انصراف
AttendanceService.record_check_out(employee)
```

### LeaveService
```python
from hr.services import LeaveService

# طلب إجازة
leave = LeaveService.request_leave(employee, leave_data)

# اعتماد إجازة
LeaveService.approve_leave(leave, approver)
```

### PayrollService
```python
from hr.services import PayrollService

# حساب راتب
payroll = PayrollService.calculate_payroll(employee, month, user)

# معالجة رواتب شهرية
results = PayrollService.process_monthly_payroll(month, user)
```

## URLs

```python
# Dashboard
/hr/

# الموظفين
/hr/employees/
/hr/employees/add/
/hr/employees/<id>/

# الحضور
/hr/attendance/
/hr/attendance/check-in/
/hr/attendance/check-out/

# الإجازات
/hr/leaves/
/hr/leaves/request/

# الرواتب
/hr/payroll/
/hr/payroll/process/<month>/
```

## الصلاحيات

```python
# في settings.py
HR_PERMISSIONS = [
    'can_manage_employees',
    'can_approve_leaves',
    'can_process_payroll',
    'can_view_all_salaries',
]
```

## التكامل المالي

عند اعتماد قسيمة الراتب، يتم إنشاء قيد محاسبي تلقائي:

```
من حـ/ مصروف الرواتب (5101)
    إلى حـ/ البنك (1102)
    إلى حـ/ التأمينات (2103)
    إلى حـ/ الضرائب (2104)
```

## الإصدار

**v1.0.0** - 2025-11-03

## المطورون

Corporate ERP Team


## استكشاف الأخطاء وإصلاحها (Troubleshooting)

### المشاكل الشائعة والحلول

#### 1. خطأ "لا يوجد راتب نشط للموظف"

**المشكلة**: عند محاولة حساب راتب موظف، تظهر رسالة خطأ تفيد بعدم وجود راتب نشط.

**الحل**:
```python
# تحقق من وجود عقد نشط للموظف
contract = employee.contracts.filter(status='active').first()
if not contract:
    # أنشئ عقد جديد أو فعّل عقد موجود
    contract = Contract.objects.create(
        employee=employee,
        contract_type='permanent',
        start_date=date.today(),
        basic_salary=Decimal('5000.00'),
        status='active',
        created_by=user
    )
```

#### 2. خطأ في حساب خصم السلف

**المشكلة**: السلف لا يتم خصمها من الراتب بشكل صحيح.

**الحل**:
```python
# تأكد من أن السلفة في الحالة الصحيحة
advance = Advance.objects.get(id=advance_id)
if advance.status not in ['paid', 'in_progress']:
    advance.status = 'paid'
    advance.payment_date = date.today()
    advance.deduction_start_month = date.today().replace(day=1)
    advance.save()
```

#### 3. مشكلة في تسجيل الحضور من جهاز البصمة

**المشكلة**: البيانات لا تُسحب من جهاز البصمة.

**الحل**:
```python
from hr.services.biometric_service import ZKTecoService

# تحقق من اتصال الجهاز
device = BiometricDevice.objects.get(id=device_id)
connection = ZKTecoService.connect(device.ip_address, device.port)
if connection:
    # اسحب السجلات
    result = ZKTecoService.get_attendance_records(connection)
    ZKTecoService.disconnect(connection)
```

#### 4. خطأ في حساب رصيد الإجازات

**المشكلة**: رصيد الإجازات غير صحيح بعد الموافقة على إجازة.

**الحل**:
```python
# تحديث رصيد الإجازات يدوياً
leave_balance = LeaveBalance.objects.get(
    employee=employee,
    leave_type=leave.leave_type,
    year=leave.start_date.year
)
leave_balance.used_days += leave.days_count
leave_balance.remaining_days -= leave.days_count
leave_balance.save()
```

#### 5. مشكلة في القيود المحاسبية للرواتب

**المشكلة**: القيود المحاسبية لا تُنشأ تلقائياً عند اعتماد الراتب.

**الحل**:
```python
from hr.services.payroll_service import PayrollService

# أنشئ القيد يدوياً
payroll = Payroll.objects.get(id=payroll_id)
if payroll.status == 'approved':
    journal_entry = PayrollService.create_journal_entry(payroll, user)
```

## أمثلة عملية (Real-World Examples)

### مثال 1: إضافة موظف جديد مع عقد وراتب

```python
from django.contrib.auth import get_user_model
from hr.models import Employee, Department, JobTitle, Contract
from decimal import Decimal
from datetime import date

User = get_user_model()

# 1. إنشاء حساب مستخدم
user = User.objects.create_user(
    username='ahmed.mohamed',
    email='ahmed@company.com',
    password='secure_password'
)

# 2. إنشاء سجل الموظف
department = Department.objects.get(code='IT')
job_title = JobTitle.objects.get(code='DEV')

employee = Employee.objects.create(
    user=user,
    employee_number='EMP001',
    name='أحمد محمد',
    national_id='12345678901234',
    birth_date=date(1990, 1, 1),
    gender='male',
    marital_status='single',
    work_email='ahmed@company.com',
    mobile_phone='01234567890',
    address='القاهرة',
    city='القاهرة',
    department=department,
    job_title=job_title,
    hire_date=date.today(),
    created_by=request.user
)

# 3. إنشاء عقد العمل
contract = Contract.objects.create(
    employee=employee,
    contract_number='C001',
    contract_type='permanent',
    job_title=job_title,
    department=department,
    start_date=date.today(),
    basic_salary=Decimal('10000.00'),
    housing_allowance=Decimal('2000.00'),
    transport_allowance=Decimal('1000.00'),
    status='active',
    created_by=request.user
)
```

### مثال 2: معالجة رواتب شهر كامل

```python
from hr.services import PayrollService
from datetime import date

# معالجة رواتب شهر يناير 2025
month = date(2025, 1, 1)
results = PayrollService.process_monthly_payroll(month, request.user)

# عرض النتائج
for result in results:
    if result['success']:
        print(f"✓ تم حساب راتب {result['employee'].get_full_name_ar()}")
        print(f"  الراتب الصافي: {result['payroll'].net_salary}")
    else:
        print(f"✗ فشل حساب راتب {result['employee'].get_full_name_ar()}")
        print(f"  الخطأ: {result['error']}")
```

### مثال 3: إدارة السلف بالأقساط

```python
from hr.models import Advance
from decimal import Decimal
from datetime import date

# 1. إنشاء طلب سلفة
advance = Advance.objects.create(
    employee=employee,
    amount=Decimal('6000.00'),
    installments_count=6,
    reason='سلفة شخصية',
    status='pending',
    requested_by=employee.user
)

# 2. اعتماد السلفة
advance.status = 'approved'
advance.approved_by = manager_user
advance.approved_at = timezone.now()
advance.save()

# 3. صرف السلفة
advance.status = 'paid'
advance.payment_date = date.today()
advance.deduction_start_month = date(2025, 2, 1)  # البدء في فبراير
advance.save()

# 4. عند حساب الراتب، سيتم خصم القسط تلقائياً
payroll = PayrollService.calculate_payroll(employee, date(2025, 2, 1), request.user)
print(f"خصم السلفة: {payroll.advance_deduction}")  # سيكون 1000.00
```

### مثال 4: إدارة الإجازات

```python
from hr.services import LeaveService
from hr.models import LeaveType
from datetime import date, timedelta

# 1. طلب إجازة
leave_type = LeaveType.objects.get(code='ANNUAL')
leave_data = {
    'leave_type': leave_type,
    'start_date': date(2025, 3, 1),
    'end_date': date(2025, 3, 5),
    'reason': 'إجازة اعتيادية'
}

leave = LeaveService.request_leave(employee, leave_data)

# 2. اعتماد الإجازة
LeaveService.approve_leave(leave, manager_user)

# 3. التحقق من الرصيد المتبقي
balance = employee.leave_balances.get(
    leave_type=leave_type,
    year=2025
)
print(f"الرصيد المتبقي: {balance.remaining_days} يوم")
```

### مثال 5: تكامل الحضور مع البصمة

```python
from hr.services.biometric_service import ZKTecoService
from hr.models import BiometricDevice, Attendance
from datetime import date

# 1. الاتصال بجهاز البصمة
device = BiometricDevice.objects.get(name='Main Office')
connection = ZKTecoService.connect(device.ip_address, device.port)

if connection:
    # 2. سحب سجلات الحضور
    result = ZKTecoService.get_attendance_records(connection)
    
    if result['success']:
        # 3. معالجة السجلات
        for record in result['records']:
            # البحث عن الموظف
            mapping = BiometricUserMapping.objects.filter(
                device=device,
                biometric_user_id=record.user_id
            ).first()
            
            if mapping:
                # إنشاء سجل حضور
                Attendance.objects.create(
                    employee=mapping.employee,
                    date=record.timestamp.date(),
                    check_in=record.timestamp,
                    status='present'
                )
    
    # 4. قطع الاتصال
    ZKTecoService.disconnect(connection)
```

## الأسئلة الشائعة (FAQ)

### س1: كيف أحسب راتب موظف لشهر معين؟

**ج**: استخدم `PayrollService.calculate_payroll()`:

```python
from hr.services import PayrollService
from datetime import date

payroll = PayrollService.calculate_payroll(
    employee=employee,
    month=date(2025, 1, 1),
    processed_by=request.user
)
```

### س2: ما الفرق بين Contract و Payroll؟

**ج**: 
- **Contract**: العقد هو الاتفاق طويل الأمد الذي يحدد شروط التوظيف والأجر الأساسي
- **Payroll**: قسيمة الراتب هي الحساب الشهري الفعلي الذي يشمل الحضور والخصومات والإضافات

### س3: كيف أضيف بدل جديد لموظف؟

**ج**: استخدم نموذج `SalaryComponent`:

```python
from hr.models import SalaryComponent
from decimal import Decimal

component = SalaryComponent.objects.create(
    employee=employee,
    component_type='earning',
    name='بدل مواصلات',
    amount=Decimal('500.00'),
    is_fixed=True,
    is_active=True
)
```

### س4: كيف أتعامل مع الموظفين الذين يعملون بنظام الورديات؟

**ج**: أنشئ ورديات وخصصها للموظفين:

```python
from hr.models import Shift
from datetime import time

# إنشاء وردية
shift = Shift.objects.create(
    name='الوردية الصباحية',
    shift_type='morning',
    start_time=time(8, 0),
    end_time=time(16, 0),
    work_hours=8.0
)

# تخصيص الوردية للموظف
employee.shift = shift
employee.save()
```

### س5: كيف أحسب العمل الإضافي؟

**ج**: العمل الإضافي يُحسب تلقائياً عند معالجة الراتب بناءً على سجلات الحضور:

```python
# سيتم حساب ساعات العمل الإضافي تلقائياً
payroll = PayrollService.calculate_payroll(employee, month, user)
print(f"ساعات العمل الإضافي: {payroll.overtime_hours}")
print(f"قيمة العمل الإضافي: {payroll.overtime_amount}")
```

### س6: كيف أتعامل مع الموظفين المستقيلين؟

**ج**: استخدم `EmployeeService.terminate_employee()`:

```python
from hr.services import EmployeeService
from datetime import date

termination_data = {
    'termination_date': date.today(),
    'termination_reason': 'استقالة',
    'final_settlement': Decimal('5000.00')
}

EmployeeService.terminate_employee(
    employee=employee,
    termination_data=termination_data,
    user=request.user
)
```

### س7: كيف أعرف إذا كان الموظف لديه رصيد إجازات كافٍ؟

**ج**: تحقق من `LeaveBalance`:

```python
from hr.models import LeaveBalance

balance = LeaveBalance.objects.get(
    employee=employee,
    leave_type=leave_type,
    year=2025
)

if balance.remaining_days >= requested_days:
    print("الرصيد كافٍ")
else:
    print(f"الرصيد غير كافٍ. المتبقي: {balance.remaining_days} يوم")
```

### س8: كيف أصدر تقرير رواتب شهري؟

**ج**: استعلم عن قسائم الرواتب للشهر المطلوب:

```python
from hr.models import Payroll
from datetime import date

month = date(2025, 1, 1)
payrolls = Payroll.objects.filter(
    month=month,
    status='paid'
).select_related('employee', 'contract')

total_paid = sum(p.net_salary for p in payrolls)
print(f"إجمالي الرواتب المدفوعة: {total_paid}")
```

### س9: كيف أتعامل مع التأمينات والضرائب؟

**ج**: يتم حسابها تلقائياً في `PayrollService`:

```python
payroll = PayrollService.calculate_payroll(employee, month, user)
print(f"التأمينات: {payroll.social_insurance}")
print(f"الضرائب: {payroll.tax}")
print(f"الراتب الصافي: {payroll.net_salary}")
```

### س10: كيف أربط نظام HR بالنظام المالي؟

**ج**: عند اعتماد الراتب، يتم إنشاء قيد محاسبي تلقائياً:

```python
# عند اعتماد الراتب
payroll.status = 'approved'
payroll.approved_by = manager_user
payroll.save()

# سيتم إنشاء قيد محاسبي تلقائياً في financial.JournalEntry
# يمكنك الوصول إليه عبر:
journal_entry = payroll.journal_entries.first()
```

## الدعم والمساعدة

للحصول على المساعدة:
- راجع الوثائق الكاملة في `/docs/hr-system.md`
- تواصل مع فريق التطوير: dev@mwheba.com
- افتح issue على GitHub

## تحليل شامل: نظام الحضور والبصمة وعلاقته بالمرتب

### نظرة عامة على التدفق

```
البصمة → الحضور اليومي → الملخص الشهري → حساب الراتب → القيد المحاسبي
```

### 1. دورة الحضور اليومية

#### 1.1 تسجيل الحضور (Check-in)
```python
# الموظف يسجل حضوره عبر البصمة أو يدوياً
attendance = AttendanceService.record_check_in(
    employee=employee,
    timestamp=datetime.now(),
    shift=shift
)
```

**ما يحدث:**
- يتم إنشاء سجل `Attendance` جديد
- يتم حساب دقائق التأخير مقارنة بوقت بداية الوردية
- يتم تحديد الحالة: `present` (حاضر) أو `late` (متأخر)
- فترة السماح (`grace_period_in`) تُطبق تلقائياً

**مثال:**
- وقت بداية الوردية: 8:00 صباحاً
- فترة السماح: 15 دقيقة
- الموظف سجل حضوره: 8:10 صباحاً → حالة: `present`
- الموظف سجل حضوره: 8:20 صباحاً → حالة: `late` (10 دقائق تأخير)

#### 1.2 تسجيل الانصراف (Check-out)
```python
# الموظف يسجل انصرافه
attendance = AttendanceService.record_check_out(
    employee=employee,
    timestamp=datetime.now()
)
```

**ما يحدث:**
- يتم تحديث سجل الحضور بوقت الانصراف
- يتم حساب ساعات العمل الفعلية
- يتم حساب دقائق الانصراف المبكر
- يتم حساب ساعات العمل الإضافي (إن وجدت)

**مثال:**
- وقت نهاية الوردية: 4:00 مساءً
- الموظف سجل انصرافه: 6:00 مساءً → 2 ساعة عمل إضافي
- الموظف سجل انصرافه: 3:30 مساءً → 30 دقيقة انصراف مبكر

### 2. نظام الأذونات (Permissions)

#### 2.1 أنواع الأذونات
- **تأخير في الحضور** (`LATE_ARRIVAL`)
- **انصراف مبكر** (`EARLY_LEAVE`)
- **إذن خروج أثناء العمل** (`WORK_LEAVE`)
- **إذن طارئ** (`EMERGENCY`)

#### 2.2 الحصة الشهرية (On-the-fly Calculation)
```python
# لا يوجد model منفصل للحصة - يتم الحساب مباشرة
usage = PermissionRequest.get_monthly_usage(employee, month_date)
# Returns: {'total_count': 2, 'total_hours': 5.5}
```

**القواعد:**
- الحد الأقصى: 4 أذونات شهرياً
- الحد الأقصى: 12 ساعة شهرياً
- يتم التحقق تلقائياً عند طلب إذن جديد

#### 2.3 تأثير الأذونات على الحضور
```python
# عند اعتماد الإذن
PermissionService.approve_permission(permission, approver)
```

**ما يحدث:**
- إذا كان نوع الإذن `LATE_ARRIVAL`: يتم إلغاء خصم التأخير من سجل الحضور
- إذا كان نوع الإذن `EARLY_LEAVE`: يتم إلغاء خصم الانصراف المبكر
- يتم ربط الإذن بسجل الحضور (`attendance` field)
- يتم إضافة ملاحظة في سجل الحضور

**مثال:**
```
قبل الاعتماد:
- الحضور: 8:30 صباحاً (30 دقيقة تأخير)
- الحالة: late
- خصم التأخير: سيتم حسابه في الراتب

بعد اعتماد إذن التأخير:
- الحضور: 8:30 صباحاً
- الحالة: present
- خصم التأخير: 0 (تم الإلغاء)
- ملاحظة: "إذن معتمد: تأخير في الحضور"
```

### 3. نظام الإجازات (Leaves)

#### 3.1 أنواع الإجازات
- **إجازة اعتيادية** (`ANNUAL`) - مدفوعة
- **إجازة مرضية** (`SICK`) - مدفوعة (حسب السياسة)
- **إجازة طارئة** (`EMERGENCY`) - مدفوعة/غير مدفوعة
- **إجازة بدون راتب** (`UNPAID`) - غير مدفوعة

#### 3.2 نظام الاستحقاق (Accrual System)
```python
# الاستحقاق الشهري البسيط
balance.calculate_accrued_days()
```

**كيف يعمل:**
- الموظف يستحق إجازات بشكل شهري بعد انتهاء فترة التجربة
- مثال: 21 يوم سنوياً = 1.75 يوم شهرياً
- فترة التجربة الافتراضية: 3 أشهر (لا استحقاق خلالها)
- يتم تحديث الاستحقاق تلقائياً عند طلب إجازة

**مثال:**
```
تاريخ التعيين: 1 يناير 2024
فترة التجربة: 3 أشهر
الإجازات الاعتيادية: 21 يوم

الشهر 1-3: لا استحقاق (فترة تجربة)
الشهر 4: 1.75 يوم
الشهر 5: 3.5 يوم
الشهر 6: 5.25 يوم
...
الشهر 12: 15.75 يوم (تقريباً)
```

#### 3.3 تأثير الإجازات على الراتب
```python
# عند اعتماد الإجازة
LeaveService.approve_leave(leave, approver)
```

**ما يحدث:**
- يتم خصم الأيام من رصيد الإجازات
- إذا كانت الإجازة **مدفوعة**: لا يوجد خصم من الراتب
- إذا كانت الإجازة **غير مدفوعة**: يتم حساب خصم في الراتب

**حساب الخصم:**
```python
daily_salary = basic_salary / 30
deduction = unpaid_leave_days * daily_salary
```

### 4. الملخص الشهري (Monthly Summary)

#### 4.1 ملخص الحضور (AttendanceSummary)
```python
# يتم حسابه تلقائياً في نهاية الشهر أو عند حساب الراتب
summary = AttendanceSummaryService.calculate_monthly_summary(employee, month)
```

**ما يتم حسابه:**
- عدد أيام الحضور (`present_days`)
- عدد أيام الغياب (`absent_days`)
- عدد أيام التأخير (`late_days`)
- إجمالي ساعات العمل (`total_work_hours`)
- إجمالي دقائق التأخير (`total_late_minutes`)
- إجمالي ساعات العمل الإضافي (`total_overtime_hours`)
- **مبلغ خصم الغياب** (`absence_deduction_amount`)
- **مبلغ خصم التأخير** (`late_deduction_amount`)
- **مبلغ العمل الإضافي** (`overtime_amount`)

**صيغ الحساب:**
```python
# خصم الغياب
daily_salary = basic_salary / 30
absence_deduction = absent_days * daily_salary

# خصم التأخير (كل 60 دقيقة = ساعة من اليوم)
late_hours = total_late_minutes / 60
hourly_salary = daily_salary / 8  # assuming 8 hours workday
late_deduction = late_hours * hourly_salary

# العمل الإضافي (150% من الساعة العادية)
overtime_rate = hourly_salary * 1.5
overtime_amount = total_overtime_hours * overtime_rate
```

#### 4.2 ملخص الإجازات (LeaveSummary)
```python
# يتم حسابه تلقائياً
summary = LeaveSummary.objects.get(employee=employee, month=month)
summary.calculate()
```

**ما يتم حسابه:**
- عدد أيام الإجازات المدفوعة (`total_paid_days`)
- عدد أيام الإجازات غير المدفوعة (`total_unpaid_days`)
- **مبلغ خصم الإجازات غير المدفوعة** (`deduction_amount`)

### 5. حساب الراتب المتكامل (Integrated Payroll)

#### 5.1 التدفق الكامل
```python
# استخدام الخدمة المتكاملة (عبر Gateway)
service = HRPayrollGatewayService()
payroll = service.calculate_employee_payroll(
    employee=employee,
    month=month,
    processed_by=user,
    use_integrated=True  # مهم جداً!
)
```

**ما يحدث خطوة بخطوة:**

1. **التحقق من العقد النشط**
   ```python
   contract = employee.contracts.filter(status='active').first()
   if not contract:
       raise ValueError('لا يوجد عقد نشط')
   ```

2. **حساب/جلب ملخص الحضور**
   ```python
   attendance_summary = AttendanceSummaryService.calculate_monthly_summary(employee, month)
   ```

3. **حساب/جلب ملخص الإجازات**
   ```python
   leave_summary = LeaveSummary.objects.get_or_create(employee=employee, month=month)
   leave_summary.calculate()
   ```

4. **إنشاء قسيمة الراتب**
   ```python
   payroll = Payroll.objects.create(
       employee=employee,
       month=month,
       contract=contract,
       basic_salary=contract.basic_salary,
       status='calculated'
   )
   ```

5. **إضافة بنود الراتب من العقد**
   ```python
   # الأجر الأساسي
   PayrollLine.objects.create(
       payroll=payroll,
       code='BASIC_SALARY',
       name='الأجر الأساسي',
       component_type='earning',
       amount=contract.basic_salary
   )
   
   # البدلات النشطة
   for component in employee.salary_components.filter(is_active=True):
       PayrollLine.objects.create(
           payroll=payroll,
           code=component.code,
           name=component.name,
           component_type=component.component_type,
           amount=component.amount
       )
   ```

6. **إضافة بنود الحضور**
   ```python
   # خصم الغياب
   if attendance_summary.absence_deduction_amount > 0:
       PayrollLine.objects.create(
           code='ABSENCE_DEDUCTION',
           name=f'خصم غياب ({attendance_summary.absent_days} يوم)',
           component_type='deduction',
           amount=attendance_summary.absence_deduction_amount
       )
   
   # خصم التأخير
   if attendance_summary.late_deduction_amount > 0:
       PayrollLine.objects.create(
           code='LATE_DEDUCTION',
           name=f'خصم تأخير ({attendance_summary.total_late_minutes} دقيقة)',
           component_type='deduction',
           amount=attendance_summary.late_deduction_amount
       )
   
   # العمل الإضافي
   if attendance_summary.overtime_amount > 0:
       PayrollLine.objects.create(
           code='OVERTIME',
           name=f'عمل إضافي ({attendance_summary.total_overtime_hours} ساعة)',
           component_type='earning',
           amount=attendance_summary.overtime_amount
       )
   ```

7. **إضافة بنود الإجازات**
   ```python
   # خصم الإجازات غير المدفوعة
   if leave_summary.deduction_amount > 0:
       PayrollLine.objects.create(
           code='UNPAID_LEAVE_DEDUCTION',
           name=f'خصم إجازات بدون راتب ({leave_summary.total_unpaid_days} يوم)',
           component_type='deduction',
           amount=leave_summary.deduction_amount
       )
   ```

8. **إضافة خصم السلف**
   ```python
   # حساب أقساط السلف المستحقة
   total_deduction, advances_list = AdvanceService.calculate_advance_deduction(
       employee=employee,
       payroll_month=month
   )
   
   for advance_data in advances_list:
       PayrollLine.objects.create(
           code=f'ADVANCE_{advance.id}',
           name=f'قسط سلفة ({advance.paid_installments}/{advance.installments_count})',
           component_type='deduction',
           amount=installment_amount
       )
   ```

9. **حساب الإجماليات**
   ```python
   payroll.calculate_totals_from_lines()
   # gross_salary = basic_salary + allowances
   # total_additions = overtime + bonuses
   # total_deductions = absence + late + unpaid_leave + advance + insurance + tax
   # net_salary = gross_salary + total_additions - total_deductions
   ```

#### 5.2 مثال عملي كامل

**البيانات:**
- الأجر الأساسي: 10,000 جنيه
- بدل مواصلات: 1,000 جنيه
- أيام العمل في الشهر: 26 يوم
- أيام الحضور: 24 يوم
- أيام الغياب: 2 يوم
- دقائق التأخير: 120 دقيقة (ساعتين)
- ساعات العمل الإضافي: 10 ساعات
- إجازات غير مدفوعة: 0 يوم
- سلفة: 6,000 جنيه على 6 أقساط (1,000 جنيه شهرياً)

**الحساب:**
```
1. المستحقات:
   - الأجر الأساسي: 10,000
   - بدل مواصلات: 1,000
   - عمل إضافي: (10,000 / 30 / 8) * 1.5 * 10 = 625
   ────────────────────────────────────────
   إجمالي المستحقات: 11,625

2. الخصومات:
   - خصم غياب: (10,000 / 30) * 2 = 667
   - خصم تأخير: (10,000 / 30 / 8) * 2 = 83
   - قسط سلفة: 1,000
   - تأمينات: 1,000 (مثال)
   - ضرائب: 500 (مثال)
   ────────────────────────────────────────
   إجمالي الخصومات: 3,250

3. صافي الراتب:
   11,625 - 3,250 = 8,375 جنيه
```

### 6. الاستثناءات والإعفاءات

#### 6.1 الأذونات المعتمدة
- **تلغي** خصم التأخير أو الانصراف المبكر
- **لا تؤثر** على عدد أيام الحضور
- **تُسجل** في ملاحظات سجل الحضور

#### 6.2 الإجازات المدفوعة
- **لا تُخصم** من الراتب
- **تُخصم** من رصيد الإجازات
- **تُحسب** ضمن أيام العمل

#### 6.3 الإجازات غير المدفوعة
- **تُخصم** من الراتب
- **لا تُخصم** من رصيد الإجازات
- **لا تُحسب** ضمن أيام العمل

#### 6.4 فترة التجربة
- **لا استحقاق** للإجازات الاعتيادية
- **تُطبق** جميع قواعد الحضور والخصومات
- **يمكن** منح إجازات استثنائية

### 7. التكامل مع النظام المالي

#### 7.1 القيد المحاسبي التلقائي
```python
# عند اعتماد الراتب
service = PayrollAccountingService()
journal_entry = service.create_payroll_journal_entry(
    payroll=payroll,
    created_by=user
)
```

**القيد الناتج:**
```
من حـ/ مصروف الرواتب (50200)        11,625
    إلى حـ/ الصندوق/البنك (10100)      8,375
    إلى حـ/ التأمينات المستحقة (21030)  1,000
    إلى حـ/ الضرائب المستحقة (21040)     500
    إلى حـ/ سلف الموظفين (13010)       1,000
    إلى حـ/ خصومات أخرى (21050)         750
```

### 8. نقاط مهمة

#### ✅ الأذونات
- تُلغي الخصومات فقط إذا تم اعتمادها
- لها حصة شهرية محددة (4 أذونات، 12 ساعة)
- يتم التحقق من الحصة تلقائياً

#### ✅ الإجازات
- الاستحقاق يتم حسابه شهرياً بعد فترة التجربة
- الإجازات المدفوعة لا تؤثر على الراتب
- الإجازات غير المدفوعة تُخصم من الراتب

#### ✅ الحضور
- يتم حساب التأخير والانصراف المبكر تلقائياً
- فترات السماح تُطبق على كل وردية
- العمل الإضافي يُحسب بمعدل 150%

#### ✅ السلف
- تُخصم على أقساط شهرية
- يتم حساب القسط تلقائياً عند حساب الراتب
- القسط الأخير يُعدل ليطابق المبلغ المتبقي بالضبط

#### ✅ الراتب المتكامل
- يجمع كل البنود تلقائياً
- يُنشئ قيد محاسبي تلقائياً
- محمي بنظام Idempotency (لا تكرار)
- يحتفظ بسجل تدقيق كامل (Audit Trail)

## الترخيص

هذا المشروع مملوك لشركة MWHEBA ومحمي بحقوق الملكية الفكرية.
