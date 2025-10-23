# خطة الاختبارات الشاملة المتكاملة لنظام MWHEBA ERP

## نظرة عامة على النظام

### التطبيقات الأساسية
1. **Core** - النواة والإعدادات العامة
2. **Users** - إدارة المستخدمين والصلاحيات
3. **Client** - إدارة العملاء
4. **Supplier** - إدارة الموردين والخدمات المتخصصة
5. **Product** - إدارة المنتجات والمخزون
6. **Purchase** - إدارة المشتريات
7. **Sale** - إدارة المبيعات
8. **Financial** - النظام المحاسبي المتكامل
9. **Printing_Pricing** - نظام التسعير والطباعة
10. **Services** - الخدمات المتخصصة
11. **Utils** - الأدوات المساعدة
12. **API** - واجهات برمجة التطبيقات

---

## المرحلة الأولى: اختبار التطبيقات منفردة

### 1. اختبار تطبيق Core
#### الوظائف الأساسية:
- [ ] إعدادات النظام (SystemSetting)
- [ ] إحصائيات لوحة التحكم (DashboardStat)
- [ ] نظام الإشعارات (Notification)

#### سيناريوهات الاختبار:
```python
# اختبار إعدادات النظام
def test_system_settings():
    # إنشاء إعداد جديد
    # تعديل الإعداد
    # استرجاع الإعداد
    # حذف الإعداد
    pass

# اختبار الإشعارات
def test_notifications():
    # إنشاء إشعار جديد
    # وضع علامة مقروء
    # حذف الإشعار
    pass
```

### 2. اختبار تطبيق Users
#### الوظائف الأساسية:
- [ ] تسجيل المستخدمين
- [ ] تسجيل الدخول والخروج
- [ ] إدارة الصلاحيات
- [ ] تتبع نشاط المستخدمين

#### سيناريوهات الاختبار:
```python
def test_user_management():
    # إنشاء مستخدم جديد
    # تعديل بيانات المستخدم
    # تغيير كلمة المرور
    # تعطيل/تفعيل المستخدم
    # حذف المستخدم
    pass

def test_permissions():
    # إنشاء مجموعة صلاحيات
    # تعيين صلاحيات للمستخدم
    # اختبار الوصول للصفحات
    pass
```

### 3. اختبار تطبيق Product
#### الوظائف الأساسية:
- [ ] إدارة التصنيفات (Category)
- [ ] إدارة العلامات التجارية (Brand)
- [ ] إدارة المنتجات
- [ ] إدارة المخزون
- [ ] تتبع انتهاء الصلاحية

#### سيناريوهات الاختبار:
```python
def test_product_management():
    # إنشاء تصنيف جديد
    # إنشاء منتج جديد
    # تحديث معلومات المنتج
    # إدارة المخزون
    # تتبع حركات المخزون
    pass

def test_inventory_tracking():
    # إضافة كمية للمخزون
    # خصم كمية من المخزون
    # تتبع تاريخ انتهاء الصلاحية
    # تقارير المخزون
    pass
```

### 4. اختبار تطبيق Supplier
#### الوظائف الأساسية:
- [ ] إدارة الموردين
- [ ] إدارة أنواع الموردين
- [ ] الخدمات المتخصصة (ورق، أوفست، ديجيتال، CTP)
- [ ] الشرائح السعرية

#### سيناريوهات الاختبار:
```python
def test_supplier_management():
    # إنشاء مورد جديد
    # تحديث بيانات المورد
    # إضافة خدمات متخصصة
    # إدارة الشرائح السعرية
    pass

def test_specialized_services():
    # خدمات الورق
    # خدمات الأوفست
    # خدمات الديجيتال
    # خدمات CTP
    pass
```

### 5. اختبار تطبيق Client
#### الوظائف الأساسية:
- [ ] إدارة العملاء
- [ ] حسابات العملاء
- [ ] تتبع المعاملات

#### سيناريوهات الاختبار:
```python
def test_client_management():
    # إنشاء عميل جديد
    # تحديث بيانات العميل
    # إدارة حساب العميل
    # تتبع معاملات العميل
    pass
```

### 6. اختبار تطبيق Purchase
#### الوظائف الأساسية:
- [ ] إنشاء فواتير الشراء
- [ ] عناصر الفاتورة
- [ ] دفعات الشراء
- [ ] مرتجعات الشراء

#### سيناريوهات الاختبار:
```python
def test_purchase_management():
    # إنشاء فاتورة شراء جديدة
    # إضافة عناصر للفاتورة
    # حفظ الفاتورة
    # تعديل الفاتورة
    # حذف الفاتورة
    pass

def test_purchase_payments():
    # دفعة نقدية
    # دفعة آجلة
    # دفعة جزئية
    # إلغاء دفعة
    pass
```

### 7. اختبار تطبيق Sale
#### الوظائف الأساسية:
- [ ] إنشاء فواتير البيع
- [ ] عناصر الفاتورة
- [ ] دفعات البيع
- [ ] مرتجعات البيع

#### سيناريوهات الاختبار:
```python
def test_sale_management():
    # إنشاء فاتورة بيع جديدة
    # إضافة عناصر للفاتورة
    # حفظ الفاتورة
    # تعديل الفاتورة
    # حذف الفاتورة
    pass

def test_sale_payments():
    # دفعة نقدية
    # دفعة آجلة
    # دفعة جزئية
    # إلغاء دفعة
    pass
```

### 8. اختبار تطبيق Financial
#### الوظائف الأساسية:
- [ ] دليل الحسابات (ChartOfAccounts)
- [ ] القيود المحاسبية (JournalEntry)
- [ ] الفترات المحاسبية (AccountingPeriod)
- [ ] الأرصدة المحسنة (EnhancedBalance)
- [ ] معاملات الشريك (PartnerTransaction)
- [ ] تزامن المدفوعات (PaymentSync)
- [ ] التسوية البنكية (BankReconciliation)
- [ ] سجل التدقيق (AuditTrail)

#### سيناريوهات الاختبار:
```python
def test_chart_of_accounts():
    # إنشاء حساب جديد
    # تعديل الحساب
    # حذف الحساب
    # التحقق من التسلسل الهرمي
    pass

def test_journal_entries():
    # إنشاء قيد محاسبي
    # ترحيل القيد
    # إلغاء ترحيل القيد
    # حذف القيد
    pass

def test_partner_transactions():
    # مساهمة الشريك
    # سحب الشريك
    # تحديث رصيد الشريك
    pass
```

### 9. اختبار تطبيق Printing_Pricing
#### الوظائف الأساسية:
- [ ] إعدادات الورق (PaperType, PaperSize, PaperWeight)
- [ ] إعدادات الماكينات (OffsetMachineType, DigitalMachineType)
- [ ] مقاسات القطع والزنكات
- [ ] حسابات التسعير

#### سيناريوهات الاختبار:
```python
def test_paper_settings():
    # إضافة نوع ورق جديد
    # إضافة مقاس ورق جديد
    # إضافة وزن ورق جديد
    pass

def test_pricing_calculations():
    # حساب تكلفة الطباعة
    # حساب تكلفة الورق
    # حساب التكلفة الإجمالية
    pass
```

---

## المرحلة الثانية: اختبار التكامل بين التطبيقات

### 1. سيناريو شامل: دورة حياة المنتج الكاملة

#### الخطوة 1: تسجيل منتج جديد
```python
def test_product_registration():
    # إنشاء تصنيف منتج
    category = Category.objects.create(name="ورق طباعة")
    
    # إنشاء علامة تجارية
    brand = Brand.objects.create(name="Double A")
    
    # إنشاء منتج
    product = Product.objects.create(
        name="ورق A4 80 جرام",
        category=category,
        brand=brand,
        sku="DA-A4-80",
        cost_price=Decimal('0.50'),
        selling_price=Decimal('0.75')
    )
    
    # التحقق من إنشاء المنتج
    assert product.id is not None
    assert product.current_stock == 0
```

#### الخطوة 2: إنشاء فاتورة شراء
```python
def test_purchase_invoice_creation():
    # إنشاء مورد
    supplier = Supplier.objects.create(
        name="مورد الورق المصري",
        supplier_type="paper"
    )
    
    # إنشاء فاتورة شراء
    purchase = Purchase.objects.create(
        supplier=supplier,
        invoice_number="PUR-001",
        invoice_date=timezone.now().date(),
        payment_method="cash"
    )
    
    # إضافة عناصر للفاتورة
    purchase_item = PurchaseItem.objects.create(
        purchase=purchase,
        product=product,
        quantity=1000,
        unit_price=Decimal('0.45'),
        total_price=Decimal('450.00')
    )
    
    # التحقق من تحديث المخزون
    product.refresh_from_db()
    assert product.current_stock == 1000
    
    # التحقق من تحديث سعر التكلفة
    assert product.cost_price == Decimal('0.45')
```

#### الخطوة 3: اختبار القيود المحاسبية للشراء
```python
def test_purchase_accounting_entries():
    # التحقق من إنشاء القيود المحاسبية
    journal_entries = JournalEntry.objects.filter(
        reference_type="purchase",
        reference_id=purchase.id
    )
    
    assert journal_entries.exists()
    
    # التحقق من صحة القيود
    total_debit = sum(entry.debit_amount for entry in journal_entries)
    total_credit = sum(entry.credit_amount for entry in journal_entries)
    assert total_debit == total_credit == Decimal('450.00')
```

#### الخطوة 4: اختبار دفعات الموردين
```python
def test_supplier_payments():
    # دفعة نقدية كاملة
    payment = PurchasePayment.objects.create(
        purchase=purchase,
        amount=Decimal('450.00'),
        payment_method="cash",
        payment_date=timezone.now().date()
    )
    
    # التحقق من تحديث رصيد المورد
    supplier.refresh_from_db()
    assert supplier.balance == Decimal('0.00')
    
    # التحقق من القيود المحاسبية للدفعة
    payment_entries = JournalEntry.objects.filter(
        reference_type="purchase_payment",
        reference_id=payment.id
    )
    assert payment_entries.exists()
```

#### الخطوة 5: إنشاء فاتورة بيع
```python
def test_sale_invoice_creation():
    # إنشاء عميل
    client = Client.objects.create(
        name="عميل تجريبي",
        email="client@test.com"
    )
    
    # إنشاء فاتورة بيع
    sale = Sale.objects.create(
        client=client,
        invoice_number="SAL-001",
        invoice_date=timezone.now().date(),
        payment_method="cash"
    )
    
    # إضافة عناصر للفاتورة
    sale_item = SaleItem.objects.create(
        sale=sale,
        product=product,
        quantity=100,
        unit_price=Decimal('0.75'),
        total_price=Decimal('75.00')
    )
    
    # التحقق من تحديث المخزون
    product.refresh_from_db()
    assert product.current_stock == 900
```

#### الخطوة 6: اختبار القيود المحاسبية للبيع
```python
def test_sale_accounting_entries():
    # التحقق من إنشاء القيود المحاسبية
    journal_entries = JournalEntry.objects.filter(
        reference_type="sale",
        reference_id=sale.id
    )
    
    assert journal_entries.exists()
    
    # التحقق من قيد المبيعات
    sales_entry = journal_entries.filter(account__name="المبيعات").first()
    assert sales_entry.credit_amount == Decimal('75.00')
    
    # التحقق من قيد تكلفة البضاعة المباعة
    cogs_entry = journal_entries.filter(account__name="تكلفة البضاعة المباعة").first()
    assert cogs_entry.debit_amount == Decimal('45.00')  # 100 * 0.45
```

### 2. سيناريو معاملات الشريك
```python
def test_partner_transactions():
    # مساهمة الشريك
    contribution = PartnerTransaction.objects.create(
        transaction_type="PARTNER_CONTRIBUTION",
        amount=Decimal('10000.00'),
        description="مساهمة رأس مال"
    )
    
    # التحقق من القيود المحاسبية
    partner_account = ChartOfAccounts.objects.get(name__contains="جاري الشريك")
    cash_account = ChartOfAccounts.objects.get(name__contains="الصندوق")
    
    # التحقق من تحديث الأرصدة
    assert partner_account.current_balance == Decimal('10000.00')
    assert cash_account.current_balance == Decimal('10000.00')
    
    # سحب الشريك
    withdrawal = PartnerTransaction.objects.create(
        transaction_type="PARTNER_WITHDRAWAL",
        amount=Decimal('2000.00'),
        description="سحب شخصي"
    )
    
    # التحقق من تحديث الأرصدة
    partner_account.refresh_from_db()
    cash_account.refresh_from_db()
    assert partner_account.current_balance == Decimal('8000.00')
```

### 3. سيناريو التقارير المالية
```python
def test_financial_reports():
    # ميزان المراجعة
    trial_balance = generate_trial_balance()
    assert trial_balance['total_debits'] == trial_balance['total_credits']
    
    # قائمة الدخل
    income_statement = generate_income_statement()
    assert 'revenue' in income_statement
    assert 'expenses' in income_statement
    assert 'net_income' in income_statement
    
    # الميزانية العمومية
    balance_sheet = generate_balance_sheet()
    assert balance_sheet['total_assets'] == balance_sheet['total_liabilities_equity']
```

### 4. سيناريو تقارير المخزون
```python
def test_inventory_reports():
    # تقرير المخزون الحالي
    inventory_report = generate_inventory_report()
    assert len(inventory_report) > 0
    
    # تقرير حركات المخزون
    stock_movements = generate_stock_movement_report()
    assert len(stock_movements) > 0
    
    # تقرير تقادم المخزون
    aging_report = generate_inventory_aging_report()
    assert 'aged_items' in aging_report
```

---

## المرحلة الثالثة: اختبار الأداء والحمولة

### 1. اختبار الأداء
```python
def test_performance():
    # اختبار سرعة إنشاء الفواتير
    start_time = time.time()
    for i in range(100):
        create_sample_invoice()
    end_time = time.time()
    
    assert (end_time - start_time) < 30  # يجب أن يكتمل في أقل من 30 ثانية
    
    # اختبار سرعة التقارير
    start_time = time.time()
    generate_trial_balance()
    end_time = time.time()
    
    assert (end_time - start_time) < 5  # يجب أن يكتمل في أقل من 5 ثواني
```

### 2. اختبار الحمولة
```python
def test_concurrent_users():
    # محاكاة 10 مستخدمين متزامنين
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        for i in range(10):
            future = executor.submit(simulate_user_activity)
            futures.append(future)
        
        # انتظار اكتمال جميع المهام
        for future in futures:
            future.result()
```

---

## المرحلة الرابعة: اختبار الأمان

### 1. اختبار الصلاحيات
```python
def test_permissions():
    # إنشاء مستخدم بصلاحيات محدودة
    limited_user = User.objects.create_user(
        username="limited_user",
        password="test123"
    )
    
    # اختبار منع الوصول للصفحات المحظورة
    client = Client()
    client.login(username="limited_user", password="test123")
    
    response = client.get('/financial/journal-entries/')
    assert response.status_code == 403  # Forbidden
```

### 2. اختبار حماية البيانات
```python
def test_data_protection():
    # اختبار تشفير كلمات المرور
    user = User.objects.create_user(
        username="test_user",
        password="test123"
    )
    assert user.password != "test123"  # يجب أن تكون مشفرة
    
    # اختبار حماية CSRF
    client = Client()
    response = client.post('/purchase/create/', {})
    assert response.status_code == 403  # CSRF protection
```

---

## المرحلة الخامسة: اختبار واجهة المستخدم

### 1. اختبار المودالز والنماذج
```python
def test_modals():
    # اختبار مودال إضافة منتج
    response = client.get('/product/create/')
    assert response.status_code == 200
    assert 'modal' in response.content.decode()
    
    # اختبار إرسال النموذج عبر AJAX
    response = client.post('/product/create/', {
        'name': 'منتج تجريبي',
        'sku': 'TEST-001'
    }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    
    assert response.status_code == 200
    data = json.loads(response.content)
    assert data['success'] == True
```

### 2. اختبار الفلاتر والبحث
```python
def test_filters():
    # اختبار فلتر المنتجات حسب التصنيف
    response = client.get('/product/list/?category=1')
    assert response.status_code == 200
    
    # اختبار البحث في المنتجات
    response = client.get('/product/list/?search=ورق')
    assert response.status_code == 200
```

---

## خطة التنفيذ

### الأسبوع الأول: إعداد بيئة الاختبار
- [ ] إعداد قاعدة بيانات اختبار
- [ ] إنشاء بيانات تجريبية
- [ ] إعداد أدوات الاختبار

### الأسبوع الثاني: اختبار التطبيقات منفردة
- [ ] اختبار Core و Users
- [ ] اختبار Product و Supplier
- [ ] اختبار Purchase و Sale

### الأسبوع الثالث: اختبار التكامل
- [ ] سيناريوهات دورة حياة المنتج
- [ ] سيناريوهات المعاملات المالية
- [ ] اختبار التقارير

### الأسبوع الرابع: اختبار الأداء والأمان
- [ ] اختبار الحمولة
- [ ] اختبار الأمان
- [ ] اختبار واجهة المستخدم

### الأسبوع الخامس: التوثيق والتحسين
- [ ] توثيق النتائج
- [ ] إصلاح الأخطاء المكتشفة
- [ ] تحسين الأداء

---

## أدوات الاختبار المطلوبة

### 1. أدوات اختبار Django
```python
# requirements-test.txt
pytest==7.4.0
pytest-django==4.5.2
pytest-cov==4.1.0
factory-boy==3.3.0
faker==19.3.0
selenium==4.11.2
```

### 2. إعداد pytest
```python
# pytest.ini
[tool:pytest]
DJANGO_SETTINGS_MODULE = mwheba_erp.settings
python_files = tests.py test_*.py *_tests.py
addopts = --cov=. --cov-report=html --cov-report=term-missing
```

### 3. Factory للبيانات التجريبية
```python
# factories.py
import factory
from django.contrib.auth import get_user_model
from product.models import Product, Category

User = get_user_model()

class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
    
    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@test.com")
    first_name = factory.Faker('first_name')
    last_name = factory.Faker('last_name')

class CategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Category
    
    name = factory.Faker('word')
    is_active = True

class ProductFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Product
    
    name = factory.Faker('word')
    category = factory.SubFactory(CategoryFactory)
    sku = factory.Sequence(lambda n: f"SKU{n:04d}")
    cost_price = factory.Faker('pydecimal', left_digits=3, right_digits=2, positive=True)
    selling_price = factory.LazyAttribute(lambda obj: obj.cost_price * Decimal('1.3'))
```

---

## معايير النجاح

### 1. التغطية (Coverage)
- [ ] تغطية كود لا تقل عن 90%
- [ ] تغطية جميع النماذج الأساسية
- [ ] تغطية جميع Views الرئيسية

### 2. الأداء
- [ ] زمن استجابة أقل من 2 ثانية للصفحات العادية
- [ ] زمن استجابة أقل من 5 ثواني للتقارير
- [ ] دعم 50 مستخدم متزامن بدون مشاكل

### 3. الأمان
- [ ] لا توجد ثغرات أمنية معروفة
- [ ] حماية كاملة من CSRF و XSS
- [ ] تشفير صحيح للبيانات الحساسة

### 4. الوظائف
- [ ] جميع الوظائف الأساسية تعمل بشكل صحيح
- [ ] التكامل بين التطبيقات يعمل بسلاسة
- [ ] التقارير تُظهر بيانات صحيحة

---

## الخلاصة

هذه الخطة الشاملة تغطي جميع جوانب النظام من الاختبار الفردي للتطبيقات إلى الاختبار المتكامل والأداء والأمان. تنفيذ هذه الخطة سيضمن جودة عالية للنظام وثقة في استقراره وأدائه.
