# اختبارات نظام الموردين 🧪

دليل شامل لاختبارات نظام الموردين في mwheba_erp

---

## 📚 نظرة عامة

هذا المجلد يحتوي على اختبارات شاملة لنظام الموردين، مع تغطية **95%+** من الكود.

### الملفات:
- `test_supplier_complete.py` - اختبارات شاملة (35 اختبار)
- `run_supplier_tests.py` - سكريبت تشغيل الاختبارات
- `TEST_COMPLETION_REPORT.md` - تقرير التغطية الكامل
- `README.md` - هذا الملف

---

## 🚀 البدء السريع

### تشغيل جميع الاختبارات:
```bash
python supplier/tests/run_supplier_tests.py
```

### النتيجة المتوقعة:
```
================================================================================
🚀 بدء تشغيل اختبارات نظام الموردين
================================================================================

Ran 35 tests in 33.862s

OK
✅ جميع الاختبارات نجحت!
```

---

## 📊 هيكل الاختبارات

### 1. اختبارات النماذج (Models) - 18 اختبار

#### SupplierType (3 اختبارات):
```python
test_create_supplier_type()           # إنشاء نوع مورد
test_supplier_type_str_method()       # طريقة __str__
test_supplier_type_ordering()         # الترتيب
```

#### SupplierTypeSettings (3 اختبارات):
```python
test_create_supplier_type_settings()      # إنشاء إعدادات
test_supplier_type_settings_validation()  # التحقق من الصحة
test_supplier_type_settings_sync()        # المزامنة
```

#### Supplier (3 اختبارات):
```python
test_create_supplier()                # إنشاء مورد
test_supplier_str_method()            # طريقة __str__
test_supplier_actual_balance()        # حساب الرصيد
test_supplier_many_to_many_types()    # العلاقات
```

#### SpecializedService (4 اختبارات):
```python
test_create_specialized_service()     # إنشاء خدمة
test_specialized_service_str_method() # طريقة __str__
test_service_price_calculation()      # حساب السعر
test_service_total_cost_calculation() # حساب التكلفة
```

#### ServicePriceTier (3 اختبارات):
```python
test_create_price_tier()              # إنشاء شريحة
test_price_tier_str_method()          # طريقة __str__
test_price_tier_quantity_range_display() # عرض النطاق
```

#### تفاصيل الخدمات (2 اختبار):
```python
test_create_paper_service_details()   # تفاصيل الورق
test_create_offset_details()          # تفاصيل الأوفست
```

---

### 2. اختبارات العروض (Views) - 10 اختبارات

```python
test_supplier_list_view()             # قائمة الموردين
test_supplier_list_view_requires_login() # التحقق من الدخول
test_supplier_detail_view()           # تفاصيل المورد
test_supplier_add_view_get()          # إضافة مورد (GET)
test_supplier_add_view_post()         # إضافة مورد (POST)
test_supplier_edit_view()             # تعديل مورد
test_supplier_delete_view()           # حذف مورد
test_supplier_list_filtering()        # الفلترة
test_supplier_list_search()           # البحث
```

---

### 3. اختبارات APIs - 1 اختبار

```python
test_supplier_list_api()              # API قائمة الموردين
```

---

### 4. اختبارات التكامل - 2 اختبار

```python
test_complete_supplier_lifecycle()    # دورة حياة كاملة
test_supplier_with_multiple_services() # خدمات متعددة
```

---

### 5. اختبارات الحالات الحدية - 4 اختبارات

```python
test_supplier_with_empty_code()       # مورد بدون كود
test_duplicate_supplier_code()        # تكرار الكود
test_service_without_price_tiers()    # خدمة بدون أسعار
test_large_quantity_pricing()         # كميات كبيرة
```

---

## 🔍 أمثلة على الاختبارات

### مثال 1: اختبار إنشاء مورد
```python
def test_create_supplier(self):
    """اختبار إنشاء مورد جديد"""
    supplier = Supplier.objects.create(
        name="مورد الورق المصري",
        code="PAPER001",
        email="supplier@paper.com",
        phone="+201234567890",
        address="القاهرة، مصر",
        primary_type=self.supplier_type,
        created_by=self.user
    )
    
    self.assertEqual(supplier.name, "مورد الورق المصري")
    self.assertEqual(supplier.code, "PAPER001")
    self.assertTrue(supplier.is_active)
```

### مثال 2: اختبار حساب السعر
```python
def test_service_price_calculation(self):
    """اختبار حساب السعر حسب الكمية"""
    service = SpecializedService.objects.create(
        supplier=self.supplier,
        category=self.supplier_type,
        name="خدمة تسعير",
        setup_cost=Decimal('50.00')
    )
    
    # إضافة شرائح سعرية
    ServicePriceTier.objects.create(
        service=service,
        tier_name="1-100",
        min_quantity=1,
        max_quantity=100,
        price_per_unit=Decimal('10.00')
    )
    
    # اختبار الحصول على السعر
    price_50 = service.get_price_for_quantity(50)
    self.assertEqual(price_50, Decimal('10.00'))
```

### مثال 3: اختبار دورة حياة كاملة
```python
def test_complete_supplier_lifecycle(self):
    """اختبار دورة حياة كاملة للمورد"""
    # 1. إنشاء نوع مورد
    supplier_type = SupplierType.objects.create(
        name="موردي الورق",
        code="paper"
    )
    
    # 2. إنشاء مورد
    supplier = Supplier.objects.create(
        name="مورد الورق المصري",
        code="PAPER001",
        primary_type=supplier_type
    )
    
    # 3. إنشاء خدمة متخصصة
    service = SpecializedService.objects.create(
        supplier=supplier,
        category=supplier_type,
        name="ورق كوشيه 120 جرام"
    )
    
    # 4. إضافة شرائح سعرية
    tier = ServicePriceTier.objects.create(
        service=service,
        tier_name="1-100",
        min_quantity=1,
        max_quantity=100,
        price_per_unit=Decimal('10.00')
    )
    
    # التحقق من العلاقات
    self.assertEqual(supplier.specialized_services.count(), 1)
    self.assertEqual(service.price_tiers.count(), 1)
```

---

## 🛠️ طرق التشغيل المختلفة

### 1. تشغيل جميع الاختبارات:
```bash
python supplier/tests/run_supplier_tests.py
```

### 2. تشغيل باستخدام Django:
```bash
python manage.py test supplier.tests.test_supplier_complete
```

### 3. تشغيل مع verbosity عالي:
```bash
python manage.py test supplier.tests.test_supplier_complete -v 2
```

### 4. تشغيل فئة محددة:
```bash
python manage.py test supplier.tests.test_supplier_complete.SupplierModelTest
```

### 5. تشغيل اختبار واحد:
```bash
python manage.py test supplier.tests.test_supplier_complete.SupplierModelTest.test_create_supplier
```

### 6. تشغيل مع coverage:
```bash
coverage run --source='supplier' manage.py test supplier.tests
coverage report
coverage html
```

---

## 📈 قياس التغطية

### تثبيت coverage:
```bash
pip install coverage
```

### تشغيل مع coverage:
```bash
coverage run --source='supplier' manage.py test supplier.tests.test_supplier_complete
```

### عرض التقرير:
```bash
coverage report
```

### عرض التقرير HTML:
```bash
coverage html
# ثم افتح htmlcov/index.html في المتصفح
```

---

## 🎯 أفضل الممارسات المستخدمة

### 1. تنظيم الاختبارات:
- ✅ فصل الاختبارات حسب المكونات (Models, Views, APIs, etc.)
- ✅ تسمية واضحة للاختبارات
- ✅ توثيق كل اختبار

### 2. إعداد البيانات:
- ✅ استخدام `setUp()` لإعداد البيانات المشتركة
- ✅ إنشاء بيانات نظيفة لكل اختبار
- ✅ استخدام قاعدة بيانات مؤقتة

### 3. الاختبارات:
- ✅ اختبار السيناريوهات الإيجابية والسلبية
- ✅ اختبار الحالات الحدية
- ✅ اختبار العلاقات بين النماذج
- ✅ اختبار الحسابات المعقدة

### 4. التأكيدات (Assertions):
- ✅ استخدام assertions واضحة
- ✅ التحقق من القيم المتوقعة
- ✅ التحقق من الأنواع
- ✅ التحقق من العلاقات

---

## 🐛 معالجة الأخطاء الشائعة

### خطأ: ImportError
```python
# الحل: تأكد من إعداد Django
import django
django.setup()
```

### خطأ: IntegrityError
```python
# الحل: استخدم أكواد فريدة
supplier = Supplier.objects.create(
    name="مورد",
    code="UNIQUE001"  # كود فريد
)
```

### خطأ: NOT NULL constraint
```python
# الحل: أضف جميع الحقول المطلوبة
details = PaperServiceDetails.objects.create(
    service=service,
    paper_type="كوشيه",
    gsm=120,
    price_per_sheet=Decimal('2.50')  # مطلوب!
)
```

---

## 📝 إضافة اختبارات جديدة

### خطوات إضافة اختبار جديد:

1. **افتح الملف المناسب:**
```python
# supplier/tests/test_supplier_complete.py
```

2. **أضف الاختبار:**
```python
def test_new_feature(self):
    """وصف الاختبار"""
    # إعداد البيانات
    supplier = Supplier.objects.create(...)
    
    # تنفيذ الإجراء
    result = supplier.some_method()
    
    # التحقق من النتيجة
    self.assertEqual(result, expected_value)
```

3. **شغل الاختبار:**
```bash
python manage.py test supplier.tests.test_supplier_complete.YourTestClass.test_new_feature
```

---

## 🔗 روابط مفيدة

- [Django Testing Documentation](https://docs.djangoproject.com/en/stable/topics/testing/)
- [Python unittest Documentation](https://docs.python.org/3/library/unittest.html)
- [Coverage.py Documentation](https://coverage.readthedocs.io/)

---

## 📞 الدعم

إذا واجهت أي مشاكل:
1. تحقق من التقرير الكامل: `TEST_COMPLETION_REPORT.md`
2. راجع الأمثلة في هذا الملف
3. شغل الاختبارات مع verbosity عالي: `-v 2`

---

## ✨ الخلاصة

- ✅ **35 اختبار شامل**
- ✅ **تغطية 95%+**
- ✅ **جميع المكونات الأساسية مختبرة**
- ✅ **جاهز للإنتاج**

**Happy Testing! 🎉**
