# وحدة الموارد البشرية - HR Module

**الإصدار:** v2.0.0  
**التاريخ:** 2025-11-03  
**الحالة:** ✅ Production Ready

---

## نظرة عامة

وحدة متكاملة لإدارة الموارد البشرية تشمل إدارة الموظفين، الحضور، الإجازات، والرواتب.

---

## المكونات الأساسية

### 1. النماذج (Models)

| النموذج | الوصف | العلاقات |
|---------|-------|----------|
| **Department** | الأقسام | Parent, Manager |
| **JobTitle** | المسميات الوظيفية | Department |
| **Employee** | الموظفين | Department, JobTitle, User |
| **Shift** | الورديات | - |
| **Attendance** | الحضور | Employee, Shift |
| **LeaveType** | أنواع الإجازات | - |
| **LeaveBalance** | رصيد الإجازات | Employee, LeaveType |
| **Leave** | الإجازات | Employee, LeaveType |
| **Salary** | الرواتب | Employee |
| **Payroll** | كشوف الرواتب | Employee, Salary |
| **Advance** | السلف | Employee |

### 2. الخدمات (Services)

#### EmployeeService
- `create_employee()` - إنشاء موظف
- `update_employee()` - تحديث بيانات
- `terminate_employee()` - إنهاء خدمة
- `get_employee_summary()` - ملخص الموظف
- `calculate_service_duration()` - مدة الخدمة
- `get_active_employees()` - الموظفين النشطين

#### AttendanceService
- `check_in()` - تسجيل حضور
- `check_out()` - تسجيل انصراف
- `calculate_work_hours()` - حساب ساعات العمل
- `calculate_late_minutes()` - حساب التأخير
- `get_monthly_attendance()` - الحضور الشهري

#### LeaveService
- `request_leave()` - طلب إجازة
- `approve_leave()` - اعتماد إجازة
- `reject_leave()` - رفض إجازة
- `calculate_leave_days()` - حساب أيام الإجازة
- `check_leave_balance()` - التحقق من الرصيد

#### PayrollService
- `process_monthly_payroll()` - معالجة رواتب شهرية
- `calculate_salary()` - حساب الراتب
- `calculate_deductions()` - حساب الخصومات
- `generate_payslip()` - إنشاء كشف راتب

### 3. الواجهات (Views)

| المسار | الوصف |
|--------|-------|
| `/hr/` | Dashboard |
| `/hr/employees/` | قائمة الموظفين |
| `/hr/employees/add/` | إضافة موظف |
| `/hr/employees/<id>/` | تفاصيل موظف |
| `/hr/employees/<id>/edit/` | تعديل موظف |
| `/hr/departments/` | الأقسام |
| `/hr/attendance/` | سجل الحضور |
| `/hr/attendance/check-in/` | تسجيل حضور |
| `/hr/attendance/check-out/` | تسجيل انصراف |
| `/hr/leaves/` | الإجازات |
| `/hr/leaves/request/` | طلب إجازة |
| `/hr/leaves/<id>/approve/` | اعتماد إجازة |
| `/hr/payroll/` | كشوف الرواتب |
| `/hr/payroll/process/<month>/` | معالجة رواتب |
| `/hr/reports/` | التقارير |

### 4. التقارير

- **تقرير الحضور** - حضور شهري مع إحصائيات
- **تقرير الإجازات** - إجازات سنوية حسب النوع
- **تقرير الرواتب** - رواتب شهرية مفصلة
- **تقرير الموظفين** - بيانات الموظفين الكاملة

جميع التقارير تدعم:
- فلاتر متقدمة
- تصدير Excel
- طباعة

---

## الصلاحيات

| الصلاحية | الوصف |
|----------|-------|
| `IsHRManager` | مدير الموارد البشرية |
| `IsHRStaff` | موظف HR |
| `IsEmployeeOrHR` | الموظف أو HR |
| `CanApproveLeave` | اعتماد الإجازات |
| `CanProcessPayroll` | معالجة الرواتب |
| `CanViewAttendance` | عرض الحضور |
| `CanManageDepartment` | إدارة الأقسام |
| `IsDirectManager` | المدير المباشر |
| `CanRequestAdvance` | طلب سلفة |

---

## الإحصائيات

| المكون | العدد |
|--------|------|
| Models | 11 |
| Services | 4 (20+ methods) |
| Forms | 6 |
| Views | 16 |
| Templates | 23 |
| Admin Classes | 11 |
| Permissions | 9 |
| API Endpoints | 50+ |
| Reports | 5 |

---

## الملفات الرئيسية

```
hr/
├── models/          # النماذج (4 ملفات)
├── services/        # الخدمات (4 ملفات)
├── forms/           # النماذج (4 ملفات)
├── views.py         # الواجهات
├── urls.py          # المسارات
├── admin.py         # لوحة الإدارة
├── serializers.py   # API Serializers
├── api_views.py     # API ViewSets
├── api_urls.py      # API URLs
├── reports.py       # التقارير
└── permissions.py   # الصلاحيات
```

---

## للمزيد

- **[دليل APIs](HR-API-GUIDE.md)** - جميع الـ endpoints والأمثلة
- **[دليل المستخدم](HR-USER-GUIDE.md)** - كيفية الاستخدام

---

**آخر تحديث:** 2025-11-03
