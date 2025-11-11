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
