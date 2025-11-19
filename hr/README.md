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

MWHEBA ERP Team


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
    first_name_ar='أحمد',
    last_name_ar='محمد',
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
    'reason': 'إجازة سنوية'
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
- **Contract**: العقد هو الاتفاق طويل الأمد الذي يحدد شروط التوظيف والراتب الأساسي
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

## الترخيص

هذا المشروع مملوك لشركة MWHEBA ومحمي بحقوق الملكية الفكرية.
