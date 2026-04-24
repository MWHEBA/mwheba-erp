# خطة تنفيذ مراكز تكلفة الأقسام

## الهدف
ربط كل قسم بتصنيف مالي فرعي (FinancialSubcategory) تحت التصنيف الرئيسي "رواتب وأجور" (salaries, pk=8)،
بحيث كل قيد راتب يُصنَّف تلقائياً بمركز تكلفة القسم — دون أي تغيير في الحسابات المحاسبية.

## القاعدة المحاسبية
- الحساب المحاسبي ثابت للكل: `50200` مصروف الرواتب
- التصنيف الرئيسي ثابت: `salaries` (pk=8, default_expense_account=11)
- التصنيف الفرعي = مركز التكلفة = القسم

---

## المرحلة 0 — تحليل الفكستشرز الموجودة (قبل أي تنفيذ)

### الأقسام الموجودة في hr/fixtures/departments.json
| pk | code    | name_ar               |
|----|---------|-----------------------|
| 1  | DEPT001 | الإدارة العامة        |
| 2  | DEPT002 | الشؤون الأكاديمية     |
| 3  | DEPT003 | الشؤون المالية        |
| 4  | DEPT004 | الخدمات المساندة      |
| 6  | DEPT006 | الإشراف التربوي       |
| 7  | DEPT007 | خدمات تعليمية         |

**ملاحظة:** pk=5 غير موجود في الفيكستشر (محذوف أو لم يُنشأ).

### التصنيف الرئيسي المستهدف في financial/fixtures/financial_categories.json
```
pk=8, code="salaries", name="رواتب وأجور", default_expense_account=11
```

### التصنيفات الفرعية الموجودة تحت salaries (pk=8) في financial/fixtures/financial_subcategories.json
```
pk=22, code="basic_salary",  name="رواتب أساسية"   → parent_category=8
pk=23, code="auto_salary",   name="مرتبات أوتو"    → parent_category=8
```
**يعني:** فيه subcategories موجودة تحت salaries لكنها مش مراكز تكلفة أقسام.
آخر pk مستخدم في الفيكستشر = **40** → الـ pks الجديدة تبدأ من **41**.

### نتيجة التحليل
- نضيف 3 subcategories فقط (مراكز تكلفة) تحت parent_category=8
- الـ pks: 41 → 43
- مفيش تعارض مع أي subcategory موجودة
- أنت تربط كل قسم بالتصنيف المناسب يدوياً من الـ UI

---

## المرحلة 1 — إضافة الـ Fixture

**الملف:** `financial/fixtures/financial_subcategories.json`
إضافة 3 records في نهاية الملف:

| pk | code             | name                    | parent_category |
|----|------------------|-------------------------|-----------------|
| 41 | dept_admin       | رواتب أقسام إدارية      | 8               |
| 42 | dept_operations  | رواتب أقسام تشغيلية     | 8               |
| 43 | dept_auto        | رواتب أوتو              | 8               |

---

## المرحلة 2 — Migration على Department Model

إضافة حقل `financial_subcategory` على `Department`:
```python
financial_subcategory = models.ForeignKey(
    'financial.FinancialSubcategory',
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name='departments',
    verbose_name='مركز التكلفة (التصنيف الفرعي)'
)
```

---

## المرحلة 3 — تحديث DepartmentForm

في `hr/forms/employee_forms.py`:
- إضافة `financial_subcategory` لـ `fields` في `DepartmentForm`
- فلترة الـ queryset على `parent_category__code='salaries'` و `is_active=True`

---

## المرحلة 4 — تحديث Template

في `templates/hr/department/form.html`:
- إضافة حقل select للتصنيف الفرعي بجانب حقل المدير

---

## المرحلة 5 — تحديث payroll_accounting_service.py

منطق الـ fallback:
```python
# 1. جيب subcategory من القسم
financial_subcategory = None
financial_category = None

dept = getattr(payroll.employee, 'department', None)
if dept and dept.financial_subcategory:
    financial_subcategory = dept.financial_subcategory
    financial_category = financial_subcategory.parent_category
else:
    # fallback: payroll.financial_category أو salaries من الـ DB
    financial_category = getattr(payroll, 'financial_category', None)
    if not financial_category:
        from financial.models import FinancialCategory
        financial_category = FinancialCategory.objects.filter(
            code='salaries', is_active=True
        ).first()
```

---

## ما لا يتغير
- حسابات المحاسبة (50200, 20210, 20220, 10350) — ثابتة
- منطق السلف والتأمينات والضرائب — كما هو
- InsurancePayment — كما هو
- باقي التصنيفات المالية في النظام — لا علاقة لها

## ترتيب التنفيذ
1. إضافة الـ fixture (المرحلة 1)
2. Migration (المرحلة 2)
3. DepartmentForm (المرحلة 3)
4. Template (المرحلة 4)
5. payroll_accounting_service.py (المرحلة 5)
6. أنت تدخل وتربط كل قسم بالـ subcategory المناسبة يدوياً من الـ UI
