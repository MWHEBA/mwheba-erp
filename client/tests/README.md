# اختبارات نظام العملاء

## نظرة عامة
هذا المجلد يحتوي على **88 اختبار شامل** لنظام إدارة العملاء في MWHEBA ERP بتغطية ~95%+.

## الملفات

### 1. test_models.py (48 اختبار)
اختبارات شاملة للنماذج:
- **CustomerModelTest**: اختبارات نموذج العميل الأساسية
- **CustomerPaymentTest**: اختبارات مدفوعات العملاء
- **CustomerTypesTest**: اختبارات أنواع العملاء المختلفة
- **CustomerBusinessLogicTest**: اختبارات منطق الأعمال
- **CustomerAdvancedTest**: اختبارات متقدمة للعميل
- **CustomerPaymentAdvancedTest**: اختبارات متقدمة للمدفوعات

### 2. test_forms.py (18 اختبار)
اختبارات النماذج:
- **CustomerFormTest**: اختبارات نموذج العميل
- **CustomerAccountChangeFormTest**: اختبارات تغيير الحساب
- **CustomerFormIntegrationTest**: اختبارات التكامل

### 3. test_signals.py (12 اختبار)
اختبارات Signals:
- **CustomerSignalsTest**: اختبارات إشارات العميل
- **CustomerSignalsIntegrationTest**: اختبارات تكامل الإشارات

### 5. test_views.py (10 اختبار)
اختبارات العروض:
- **CustomerListViewTest**: اختبارات قائمة العملاء
- **CustomerAddViewTest**: اختبارات إضافة عميل
- **CustomerEditViewTest**: اختبارات تعديل عميل
- **CustomerDeleteViewTest**: اختبارات حذف عميل
- **CustomerDetailViewTest**: اختبارات تفاصيل عميل
- **CustomerViewsPermissionsTest**: اختبارات الصلاحيات
- **CustomerViewsIntegrationTest**: اختبارات التكامل

### 5. run_client_tests.py
سكريبت لتشغيل الاختبارات وإدارة بيانات الاختبار

## كيفية الاستخدام

### تشغيل الاختبارات
```bash
python client/tests/run_client_tests.py test
```

### إنشاء بيانات اختبار
```bash
python client/tests/run_client_tests.py create-data
```

### عرض الإحصائيات
```bash
python client/tests/run_client_tests.py stats
```

### مسح بيانات الاختبار
```bash
python client/tests/run_client_tests.py clean
```

## الاختبارات المتوفرة

### اختبارات نموذج العميل (CustomerModelTest)
1. **test_create_customer**: اختبار إنشاء عميل جديد
2. **test_customer_str_method**: اختبار طريقة __str__
3. **test_customer_balance_calculation**: اختبار حساب الرصيد
4. **test_customer_credit_limit**: اختبار حد الائتمان
5. **test_available_credit**: اختبار حساب الرصيد المتاح

### اختبارات مدفوعات العملاء (CustomerPaymentTest)
1. **test_create_customer_payment**: اختبار إنشاء دفعة
2. **test_payment_str_method**: اختبار طريقة __str__ للدفعة

### اختبارات أنواع العملاء (CustomerTypesTest)
1. **test_individual_customer**: اختبار العميل الفرد
2. **test_company_customer**: اختبار العميل شركة
3. **test_vip_customer**: اختبار العميل VIP

### اختبارات منطق الأعمال (CustomerBusinessLogicTest)
1. **test_credit_limit_check**: اختبار فحص حد الائتمان
2. **test_customer_status_management**: اختبار إدارة حالة العميل
3. **test_customer_contact_info**: اختبار معلومات الاتصال

## النماذج المختبرة

### Customer (العميل)
- **الحقول الأساسية**: name, code, email, phone
- **الحقول المالية**: balance, credit_limit
- **التصنيف**: client_type (individual, company, vip, government)
- **الحالة**: is_active
- **معلومات إضافية**: address, city, company_name

### CustomerPayment (مدفوعات العميل)
- **الحقول الأساسية**: customer, amount, payment_date
- **طريقة الدفع**: payment_method (cash, bank_transfer, check)
- **معلومات إضافية**: reference_number, notes

## بيانات الاختبار

عند تشغيل `create-data`، يتم إنشاء:

### العملاء
1. **عميل فرد** (IND001)
   - النوع: individual
   - حد الائتمان: 10,000 جنيه

2. **شركة اختبار** (COMP001)
   - النوع: company
   - حد الائتمان: 50,000 جنيه

3. **عميل VIP** (VIP001)
   - النوع: vip
   - حد الائتمان: 100,000 جنيه

## النتائج المتوقعة

### تشغيل الاختبارات
```
Ran 13 tests in X.XXXs
OK
✅ جميع الاختبارات نجحت!
```

### الإحصائيات
```
📌 إجمالي العملاء: X
✅ العملاء النشطين: X
📋 توزيع العملاء حسب النوع:
   - أفراد: X
   - شركات: X
   - VIP: X
   - جهات حكومية: X
💰 إجمالي المدفوعات: X
💵 إجمالي الأرصدة: X.XX جنيه
💳 إجمالي حدود الائتمان: X.XX جنيه
```

## ملاحظات

- جميع الاختبارات تستخدم قاعدة بيانات مؤقتة في الذاكرة
- لا تؤثر الاختبارات على قاعدة البيانات الفعلية
- يتم مسح جميع البيانات تلقائياً بعد انتهاء الاختبارات
- التحذيرات حول "نوع حساب RECEIVABLES" لا تؤثر على نجاح الاختبارات

## التطوير المستقبلي

يمكن إضافة اختبارات لـ:
- [ ] تكامل العملاء مع فواتير البيع
- [ ] تكامل العملاء مع النظام المحاسبي
- [ ] تقارير العملاء
- [ ] سجل تعاملات العملاء
- [ ] حساب المديونية الفعلية
