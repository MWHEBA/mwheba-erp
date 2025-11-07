# ✅ قائمة المهام: نظام زيادات المرتبات

---

## 🔴 المرحلة 0: تنظيف الأكواد القديمة (30% متبقي)

### 1. تنظيف Views ⏳
**الملف:** `hr/views.py`

#### الخطوات:
- [ ] حذف `contract_increase_apply()` (السطر 2954)
- [ ] حذف `contract_increase_cancel()` (السطر 2971)
- [ ] إضافة `contract_increase_action()` الموحدة
- [ ] اختبار الدالة الجديدة

#### الكود المطلوب:
```python
@login_required
@require_http_methods(["POST"])
def contract_increase_action(request, increase_id, action):
    """دالة موحدة لإجراءات الزيادات (تطبيق/إلغاء)"""
    from .models import ContractIncrease
    from django.http import JsonResponse
    
    increase = get_object_or_404(ContractIncrease, pk=increase_id)
    
    if action == 'apply':
        success, message = increase.apply_increase(applied_by=request.user)
    elif action == 'cancel':
        success, message = increase.cancel_increase()
    else:
        return JsonResponse({
            'success': False,
            'message': 'إجراء غير صحيح'
        }, status=400)
    
    return JsonResponse({
        'success': success,
        'message': message
    })
```

---

### 2. تنظيف URLs ⏳
**الملف:** `hr/urls.py`

#### الخطوات:
- [ ] حذف المسارين القديمين (السطور 136-137)
- [ ] إضافة المسار الموحد
- [ ] تحديث المراجع في القوالب (إن وجدت)

#### الكود المطلوب:
```python
# حذف:
# path('contracts/increases/<int:increase_id>/apply/', views.contract_increase_apply, name='contract_increase_apply'),
# path('contracts/increases/<int:increase_id>/cancel/', views.contract_increase_cancel, name='contract_increase_cancel'),

# إضافة:
path('contracts/increases/<int:increase_id>/<str:action>/', 
     views.contract_increase_action, 
     name='contract_increase_action'),
```

---

### 3. تحسين Admin ⏳
**الملف:** `hr/admin.py`

#### الخطوات:
- [ ] إضافة imports للنماذج الجديدة
- [ ] تسجيل `SalaryIncreaseTemplate`
- [ ] تسجيل `AnnualIncreasePlan`
- [ ] تسجيل `PlannedIncrease`
- [ ] تسجيل `EmployeeIncreaseCategory`

#### الكود المطلوب:
```python
from .models import (
    SalaryIncreaseTemplate, 
    AnnualIncreasePlan,
    PlannedIncrease, 
    EmployeeIncreaseCategory
)

@admin.register(SalaryIncreaseTemplate)
class SalaryIncreaseTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'increase_type', 'is_active', 'is_default']
    list_filter = ['increase_type', 'is_active', 'is_default']
    search_fields = ['name', 'code']
    ordering = ['-is_default', 'name']
    fieldsets = (
        ('معلومات أساسية', {
            'fields': ('name', 'code', 'description')
        }),
        ('نوع الزيادة', {
            'fields': ('increase_type', 'default_percentage', 'default_amount', 'frequency')
        }),
        ('الشروط والقيود', {
            'fields': ('min_service_months', 'min_performance_rating', 
                      'max_increase_percentage', 'max_increase_amount')
        }),
        ('الحالة', {
            'fields': ('is_active', 'is_default')
        }),
    )

@admin.register(AnnualIncreasePlan)
class AnnualIncreasePlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'year', 'template', 'status', 'effective_date', 'total_budget']
    list_filter = ['year', 'status', 'template']
    search_fields = ['name']
    ordering = ['-year', '-created_at']
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'approved_by']

@admin.register(PlannedIncrease)
class PlannedIncreaseAdmin(admin.ModelAdmin):
    list_display = ['employee', 'plan', 'current_salary', 'new_salary', 'status', 'applied_date']
    list_filter = ['status', 'plan', 'applied_date']
    search_fields = ['employee__first_name_ar', 'employee__last_name_ar', 'employee__employee_number']
    ordering = ['plan', 'employee']
    readonly_fields = ['created_at', 'updated_at', 'approved_by']

@admin.register(EmployeeIncreaseCategory)
class EmployeeIncreaseCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'default_template', 'is_active']
    list_filter = ['is_active', 'default_template']
    search_fields = ['name', 'code']
    ordering = ['name']
```

---

## 🔴 المرحلة 3: القوالب (0% - 12 ملف)

### 1. الصفحة الرئيسية ⏳
**الملف:** `templates/hr/salary_increase/settings_home.html`

#### المحتوى المطلوب:
- [ ] كارت: إجمالي القوالب النشطة
- [ ] كارت: إجمالي الخطط
- [ ] كارت: الخطط النشطة
- [ ] كارت: الزيادات المعلقة
- [ ] روابط سريعة للأقسام
- [ ] جدول الخطط الأخيرة

---

### 2. قوالب الزيادات ⏳

#### 2.1 قائمة القوالب
**الملف:** `templates/hr/salary_increase/template_list.html`

- [ ] جدول بالقوالب
- [ ] أعمدة: الاسم، الكود، النوع، النسبة/المبلغ، الحالة
- [ ] فلترة حسب النوع
- [ ] فلترة حسب الحالة
- [ ] زر إنشاء قالب جديد
- [ ] أزرار تعديل/حذف

#### 2.2 نموذج القالب
**الملف:** `templates/hr/salary_increase/template_form.html`

- [ ] حقل الاسم
- [ ] حقل الكود
- [ ] حقل الوصف
- [ ] اختيار نوع الزيادة
- [ ] حقل النسبة (يظهر للنسبة المئوية)
- [ ] حقل المبلغ (يظهر للمبلغ الثابت)
- [ ] اختيار التكرار
- [ ] حقل الحد الأدنى للخدمة
- [ ] checkbox نشط
- [ ] checkbox افتراضي
- [ ] أزرار حفظ/إلغاء

#### 2.3 حذف القالب
**الملف:** `templates/hr/salary_increase/template_delete.html`

- [ ] رسالة تأكيد
- [ ] عرض معلومات القالب
- [ ] تحذير من التأثيرات
- [ ] أزرار تأكيد/إلغاء

---

### 3. الخطط السنوية ⏳

#### 3.1 قائمة الخطط
**الملف:** `templates/hr/salary_increase/plan_list.html`

- [ ] جدول بالخطط
- [ ] أعمدة: الاسم، السنة، القالب، الحالة، التاريخ، الميزانية
- [ ] فلترة حسب السنة
- [ ] فلترة حسب الحالة
- [ ] زر إنشاء خطة جديدة
- [ ] أزرار عرض/تعديل

#### 3.2 نموذج الخطة
**الملف:** `templates/hr/salary_increase/plan_form.html`

- [ ] حقل الاسم
- [ ] حقل السنة
- [ ] اختيار القالب
- [ ] حقل تاريخ السريان
- [ ] حقل الميزانية الإجمالية
- [ ] حقل الملاحظات
- [ ] اختيار الحالة (للتعديل)
- [ ] أزرار حفظ/إلغاء

#### 3.3 تفاصيل الخطة
**الملف:** `templates/hr/salary_increase/plan_detail.html`

- [ ] معلومات الخطة
- [ ] كروت الإحصائيات (معلق/معتمد/مرفوض/مطبق)
- [ ] جدول الزيادات المخططة
- [ ] أعمدة: الموظف، الراتب الحالي، الزيادة، الراتب الجديد، الحالة
- [ ] أزرار اعتماد/رفض لكل زيادة
- [ ] زر توليد زيادات
- [ ] زر تطبيق جماعي

#### 3.4 توليد الزيادات
**الملف:** `templates/hr/salary_increase/generate_increases.html`

- [ ] معلومات الخطة
- [ ] عدد الموظفين المؤهلين
- [ ] معاينة الموظفين
- [ ] التكلفة المتوقعة
- [ ] أزرار توليد/إلغاء

---

### 4. الزيادات المخططة ⏳

#### 4.1 تأكيد التطبيق الجماعي
**الملف:** `templates/hr/salary_increase/bulk_apply_confirm.html`

- [ ] معلومات الخطة
- [ ] عدد الزيادات المعتمدة
- [ ] جدول الزيادات
- [ ] التكلفة الإجمالية
- [ ] تحذير من عدم الرجوع
- [ ] أزرار تأكيد/إلغاء

---

### 5. فئات الموظفين ⏳

#### 5.1 قائمة الفئات
**الملف:** `templates/hr/salary_increase/category_list.html`

- [ ] جدول بالفئات
- [ ] أعمدة: الاسم، الكود، القالب الافتراضي، الحالة
- [ ] زر إنشاء فئة جديدة
- [ ] أزرار تعديل/حذف

#### 5.2 نموذج الفئة
**الملف:** `templates/hr/salary_increase/category_form.html`

- [ ] حقل الاسم
- [ ] حقل الكود
- [ ] حقل الوصف
- [ ] اختيار القالب الافتراضي
- [ ] checkbox نشط
- [ ] أزرار حفظ/إلغاء

#### 5.3 حذف الفئة
**الملف:** `templates/hr/salary_increase/category_delete.html`

- [ ] رسالة تأكيد
- [ ] عرض معلومات الفئة
- [ ] عدد الموظفين المرتبطين
- [ ] أزرار تأكيد/إلغاء

---

## 🔴 المرحلة 4: التكامل (0%)

### 1. تفعيل URLs ⏳
**الملف:** `hr/urls.py`

#### الخطوات:
- [ ] حذف التعليق من السطور 172-174
- [ ] إضافة المسارات الكاملة
- [ ] اختبار جميع المسارات

#### الكود المطلوب:
```python
# إعدادات زيادات المرتبات
path('salary-increase-settings/', include([
    # الصفحة الرئيسية
    path('', salary_increase_views.salary_increase_settings_home, 
         name='salary_increase_settings'),
    
    # قوالب الزيادات
    path('templates/', salary_increase_views.IncreaseTemplateListView.as_view(), 
         name='increase_template_list'),
    path('templates/create/', salary_increase_views.IncreaseTemplateCreateView.as_view(), 
         name='increase_template_create'),
    path('templates/<int:pk>/edit/', salary_increase_views.IncreaseTemplateUpdateView.as_view(), 
         name='increase_template_edit'),
    path('templates/<int:pk>/delete/', salary_increase_views.IncreaseTemplateDeleteView.as_view(), 
         name='increase_template_delete'),
    
    # الخطط السنوية
    path('plans/', salary_increase_views.AnnualPlanListView.as_view(), 
         name='annual_plan_list'),
    path('plans/create/', salary_increase_views.AnnualPlanCreateView.as_view(), 
         name='annual_plan_create'),
    path('plans/<int:pk>/', salary_increase_views.AnnualPlanDetailView.as_view(), 
         name='annual_plan_detail'),
    path('plans/<int:pk>/edit/', salary_increase_views.AnnualPlanUpdateView.as_view(), 
         name='annual_plan_edit'),
    path('plans/<int:pk>/generate/', salary_increase_views.generate_planned_increases, 
         name='generate_planned_increases'),
    path('plans/<int:pk>/apply/', salary_increase_views.bulk_apply_increases, 
         name='bulk_apply_increases'),
    
    # الزيادات المخططة
    path('increases/<int:increase_id>/approve/', salary_increase_views.approve_planned_increase, 
         name='approve_planned_increase'),
    path('increases/<int:increase_id>/reject/', salary_increase_views.reject_planned_increase, 
         name='reject_planned_increase'),
    path('increases/<int:increase_id>/apply/', salary_increase_views.apply_planned_increase, 
         name='apply_planned_increase'),
    
    # فئات الموظفين
    path('categories/', salary_increase_views.EmployeeCategoryListView.as_view(), 
         name='employee_category_list'),
    path('categories/create/', salary_increase_views.EmployeeCategoryCreateView.as_view(), 
         name='employee_category_create'),
    path('categories/<int:pk>/edit/', salary_increase_views.EmployeeCategoryUpdateView.as_view(), 
         name='employee_category_edit'),
    path('categories/<int:pk>/delete/', salary_increase_views.EmployeeCategoryDeleteView.as_view(), 
         name='employee_category_delete'),
])),
```

---

### 2. إضافة رابط القائمة الجانبية ⏳
**الملف:** `templates/base.html` أو `templates/partials/sidebar.html`

#### الخطوات:
- [ ] البحث عن قسم الموارد البشرية في القائمة
- [ ] إضافة رابط إعدادات الزيادات
- [ ] اختبار الرابط

#### الكود المطلوب:
```html
<!-- في قسم الموارد البشرية -->
<li class="nav-item">
    <a href="{% url 'hr:salary_increase_settings' %}" class="nav-link">
        <i class="fas fa-chart-line"></i>
        <span>إعدادات زيادات المرتبات</span>
    </a>
</li>
```

---

### 3. اختبار التكامل ⏳

#### الخطوات:
- [ ] اختبار توليد الزيادات
- [ ] اختبار اعتماد الزيادات
- [ ] اختبار التطبيق الفردي
- [ ] اختبار التطبيق الجماعي
- [ ] اختبار الربط مع ContractIncrease
- [ ] اختبار تحديث الراتب في العقد

---

## 🔴 المرحلة 5: التوثيق (0%)

### 1. دليل المستخدم ⏳
- [ ] شرح القوالب
- [ ] شرح الخطط
- [ ] شرح الزيادات المخططة
- [ ] شرح الفئات
- [ ] أمثلة عملية

### 2. البيانات الأولية ⏳
**الملف:** `fixtures/initial_salary_increase_data.json`

- [ ] قالب: زيادة سنوية 10%
- [ ] قالب: زيادة نصف سنوية 5%
- [ ] فئة: موظفين إداريين
- [ ] فئة: مديرين

---

## 📊 ملخص المهام

### التنظيف (3 مهام)
- [ ] دمج Views
- [ ] تبسيط URLs
- [ ] تحسين Admin

### القوالب (12 ملف)
- [ ] settings_home.html
- [ ] template_list.html
- [ ] template_form.html
- [ ] template_delete.html
- [ ] plan_list.html
- [ ] plan_form.html
- [ ] plan_detail.html
- [ ] generate_increases.html
- [ ] bulk_apply_confirm.html
- [ ] category_list.html
- [ ] category_form.html
- [ ] category_delete.html

### التكامل (3 مهام)
- [ ] تفعيل URLs
- [ ] إضافة رابط القائمة
- [ ] اختبار شامل

### التوثيق (2 مهام)
- [ ] دليل المستخدم
- [ ] البيانات الأولية

---

**إجمالي المهام:** 20 مهمة  
**المكتمل:** 0  
**المتبقي:** 20  
**التقدم:** 0% ⏳
