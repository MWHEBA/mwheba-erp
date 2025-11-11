# اختبارات نظام الموارد البشرية (HR Tests)

## 📁 هيكل الاختبارات

تم تنظيم جميع الاختبارات في مجلد `tests/` مع تجميع منطقي حسب الوظيفة:

```
hr/tests/
├── __init__.py                 # ملف التهيئة
├── README.md                   # هذا الملف
├── test_models.py              # اختبارات النماذج (Models)
├── test_services.py            # اختبارات الخدمات (Services)
├── test_views.py               # اختبارات الواجهات (Views)
├── test_api.py                 # اختبارات API
├── test_forms.py               # اختبارات النماذج (Forms)
├── test_permissions.py         # اختبارات الصلاحيات
├── test_reports.py             # اختبارات التقارير
├── test_signals.py             # اختبارات الإشارات
├── test_serializers.py         # اختبارات المسلسلات
├── test_salary_system.py       # اختبارات نظام الرواتب الجديد
├── test_advance_system.py      # اختبارات نظام السلف بالأقساط
└── test_integration.py         # اختبارات التكامل الشاملة
```

## 🎯 تفاصيل الملفات

### 1. test_models.py
**النماذج المختبرة:**
- Department, JobTitle, Employee, Shift
- Attendance
- Salary, Advance, AdvanceInstallment
- Contract, SalaryComponent, BiometricDevice

**التغطية:**
- إنشاء النماذج
- التحقق من الحقول
- العلاقات بين النماذج
- الدوال المخصصة (`__str__`, `get_full_name_ar`, etc.)

### 2. test_services.py
**الخدمات المختبرة:**
- EmployeeService
- AttendanceService
- LeaveService
- PayrollService

**التغطية:**
- إنشاء وإدارة الموظفين
- تسجيل الحضور والانصراف
- طلب واعتماد الإجازات
- حساب الرواتب مع السلف

### 3. test_views.py
**الواجهات المختبرة:**
- Dashboard
- Employee CRUD
- Department CRUD
- Advance Management

**التغطية:**
- الوصول للصفحات
- التحقق من الصلاحيات
- عرض البيانات

### 4. test_api.py
**API Endpoints المختبرة:**
- /hr/api/departments/
- /hr/api/job-titles/
- /hr/api/employees/

**التغطية:**
- List, Retrieve, Create, Update, Delete
- البحث والتصفية
- Authentication

### 5. test_salary_system.py
**نظام الرواتب الجديد:**
- SalaryComponent
- SalaryComponentService
- حساب الراتب الإجمالي
- إضافة وتعديل البنود

### 6. test_advance_system.py
**نظام السلف بالأقساط:**
- إنشاء سلفة بأقساط
- تفعيل وصرف السلفة
- خصم الأقساط الشهرية
- تسجيل الأقساط
- إكمال السلفة

### 7. test_integration.py
**اختبارات التكامل:**
- دورة حياة السلفة الكاملة
- التكامل بين الرواتب والسلف
- سيناريوهات معقدة

## 🚀 تشغيل الاختبارات

### تشغيل جميع الاختبارات:
```bash
python manage.py test hr.tests
```

### تشغيل ملف محدد:
```bash
python manage.py test hr.tests.test_models
python manage.py test hr.tests.test_services
python manage.py test hr.tests.test_advance_system
```

### تشغيل اختبار محدد:
```bash
python manage.py test hr.tests.test_models.DepartmentModelTest
python manage.py test hr.tests.test_models.DepartmentModelTest.test_department_creation
```

### تشغيل مع تقرير التغطية:
```bash
coverage run --source='hr' manage.py test hr.tests
coverage report
coverage html
```

## 📊 إحصائيات الاختبارات

| الملف | عدد الاختبارات | التغطية |
|------|----------------|---------|
| test_models.py | 15+ | النماذج الأساسية |
| test_services.py | 12+ | الخدمات الرئيسية |
| test_views.py | 8+ | الواجهات |
| test_api.py | 6+ | API Endpoints |
| test_forms.py | 4+ | النماذج |
| test_permissions.py | 3+ | الصلاحيات |
| test_reports.py | 2+ | التقارير |
| test_signals.py | 2+ | الإشارات |
| test_serializers.py | 3+ | المسلسلات |
| test_salary_system.py | 4+ | نظام الرواتب |
| test_advance_system.py | 6+ | نظام السلف |
| test_integration.py | 2+ | التكامل |
| **المجموع** | **67+** | **شامل** |

## ✅ ما تم دمجه

تم دمج الملفات التالية في الهيكل الجديد:

### الملفات القديمة المدموجة:
1. ✅ `tests.py` → `test_models.py` + `test_services.py` + `test_views.py`
2. ✅ `tests_comprehensive.py` → `test_models.py` + `test_integration.py`
3. ✅ `tests_models_extended.py` → `test_models.py`
4. ✅ `tests_services.py` → `test_services.py`
5. ✅ `tests_services_advanced.py` → `test_services.py`
6. ✅ `tests_views.py` → `test_views.py`
7. ✅ `tests_advanced_views.py` → `test_views.py`
8. ✅ `tests_api.py` → `test_api.py`
9. ✅ `tests_forms_advanced.py` → `test_forms.py`
10. ✅ `tests_permissions.py` → `test_permissions.py`
11. ✅ `tests_reports.py` → `test_reports.py`
12. ✅ `tests_signals.py` → `test_signals.py`
13. ✅ `tests_serializers.py` → `test_serializers.py`
14. ✅ `tests_model_methods.py` → `test_models.py`
15. ✅ `tests_edge_cases.py` → `test_integration.py`
16. ✅ `test_new_salary_system.py` → `test_salary_system.py`
17. ✅ `test_advance_system.py` → `test_advance_system.py`

## 🎨 مبادئ التنظيم

1. **فصل المسؤوليات**: كل ملف يختبر جانب واحد من النظام
2. **تسمية واضحة**: أسماء الملفات تعكس محتواها
3. **تجميع منطقي**: الاختبارات المتشابهة في ملف واحد
4. **سهولة الصيانة**: كود نظيف ومنظم
5. **توثيق شامل**: تعليقات بالعربية لكل اختبار

## 📝 ملاحظات

- جميع الاختبارات تستخدم timestamps لتجنب تضارب البيانات
- الاختبارات مستقلة ولا تعتمد على بعضها
- استخدام `TransactionTestCase` للاختبارات التي تحتاج transactions
- معالجة الأخطاء بـ `try/except` للاختبارات الاختيارية

## 🔄 التحديثات المستقبلية

- [ ] إضافة اختبارات للعقود
- [ ] إضافة اختبارات للبصمة
- [ ] زيادة تغطية الاختبارات لـ 100%
- [ ] إضافة اختبارات الأداء
- [ ] إضافة اختبارات الأمان
