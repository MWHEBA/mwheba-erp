# هيكل قوالب نظام الموردين

## التنظيم الجديد المحسن

### 📁 `core/` - الملفات الأساسية (6 ملفات)
- `supplier_list.html` - قائمة الموردين
- `supplier_form.html` - إضافة/تعديل مورد  
- `supplier_detail.html` - تفاصيل المورد (الأكبر - 52KB)
- `supplier_delete.html` - حذف مورد
- `supplier_change_account.html` - تغيير حساب المورد
- `suppliers_by_type.html` - الموردين حسب النوع

### 📁 `services/` - إدارة الخدمات (5 ملفات)
- `add_specialized_service.html` - إضافة خدمة متخصصة (الأعقد - 39KB)
- `edit_specialized_service.html` - تعديل خدمة متخصصة
- `delete_specialized_service.html` - حذف خدمة متخصصة
- `dynamic_service_form.html` - النموذج الديناميكي للخدمات
- `delete_service_confirm.html` - تأكيد حذف خدمة

### 📁 `analysis/` - التفاصيل والتحليلات (1 ملف)
- `supplier_services_detail.html` - تفاصيل خدمات المورد

### 📁 `forms/` - نماذج الخدمات المتخصصة (8 ملفات)
- `coating_form.html` - نموذج خدمات التغطية
- `digital_form.html` - نموذج الطباعة الديجيتال
- `finishing_form.html` - نموذج خدمات التشطيب
- `generic_form.html` - نموذج عام
- `offset_form.html` - نموذج طباعة الأوفست
- `packaging_form.html` - نموذج خدمات التعبئة
- `paper_form.html` - نموذج خدمات الورق
- `plates_form.html` - نموذج خدمات الزنكات

## الملفات المحذوفة

### ✅ تم حذف الملفات القديمة والمكررة:
- `add_service.html` - نظام الخدمات القديم
- `edit_service.html` - تعديل خدمة (نظام قديم)
- `delete_service.html` - حذف خدمة (نظام قديم)
- `add_specialized_service_old.html` - نسخة احتياطية قديمة
- `edit_specialized_service_old.html` - نسخة احتياطية قديمة
- `supplier_form_old.html` - نسخة احتياطية قديمة
- `price_comparison.html` - مقارنة الأسعار (غير مستخدم)
- `service_comparison.html` - مقارنة الخدمات (غير مستخدم)
- `service_calculator.html` - حاسبة الخدمات (غير مستخدم)
- `specialized_services_list.html` - قائمة الخدمات (غير مستخدم في URLs)

## الإحصائيات

### قبل التنظيف:
- **30 ملف** إجمالي
- **12 ملف مكرر/قديم** تم حذفها

### بعد التنظيف:
- **20 ملف** مستخدم فعلياً
- **4 مجلدات** منظمة حسب الوظيفة
- **توفير 40%** من الملفات
- **تحسين كبير** في سهولة الصيانة

## ملاحظات مهمة

1. **جميع الملفات المتبقية مستخدمة فعلياً** في URLs والـ Views
2. **النظام الديناميكي للخدمات** هو الأساس الآن
3. **مجلد forms/** يحتوي على جميع نماذج الخدمات المتخصصة
4. **التنظيم يسهل** إضافة ملفات جديدة مستقبلاً

## تحديث المسارات

✅ **تم تحديث جميع المسارات في Views:**

### الملفات الأساسية:
```python
# تم التحديث
'supplier/core/supplier_list.html'
'supplier/core/supplier_form.html'  
'supplier/core/supplier_detail.html'
'supplier/core/supplier_delete.html'
'supplier/core/supplier_change_account.html'
'supplier/core/suppliers_by_type.html'
```

### ملفات الخدمات:
```python
# تم التحديث
'supplier/services/add_specialized_service.html'
'supplier/services/edit_specialized_service.html'
'supplier/services/delete_specialized_service.html'
'supplier/services/dynamic_service_form.html'
'supplier/services/delete_service_confirm.html'
```

### ملفات التحليل:
```python
# تم التحديث
'supplier/analysis/supplier_services_detail.html'
'supplier/analysis/service_comparison.html'
```

### ملفات النماذج (لم تتغير):
```python
# المسارات كما هي
'supplier/forms/paper_form.html'
'supplier/forms/offset_form.html'
# ... باقي النماذج
```

## الملفات المحدثة:
- ✅ `supplier/views.py` - جميع المسارات
- ✅ `supplier/views_pricing.py` - مسارات الخدمات
- ✅ `supplier/api_views.py` - مسارات النماذج

## الاختبار:
جميع الصفحات يجب أن تعمل بشكل طبيعي مع المسارات الجديدة.
