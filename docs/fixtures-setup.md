# دليل إعداد Fixtures الاحترافي لنظام ERP

## نظرة عامة

هذا الدليل يوضح كيفية إعداد النظام من الصفر باستخدام fixtures احترافية ومنظمة. يمكنك مسح قاعدة البيانات وإعادة تهيئة النظام بالكامل باستخدام هذه الخطوات.

---

## 📋 قائمة Fixtures المطلوبة (مرتبة حسب الأولوية)

### المرحلة 1: البيانات الأساسية (Core Data)
يجب تحميل هذه البيانات أولاً لأن باقي البيانات تعتمد عليها.

#### 1.1 المستخدمين والصلاحيات
```bash
# ترتيب التحميل مهم جداً
python manage.py loaddata users/fixtures/groups.json
python manage.py loaddata users/fixtures/groups_permissions.json
python manage.py loaddata users/fixtures/initial_data.json
```

**الملفات المطلوبة:**
- ✅ `users/fixtures/groups.json` - مجموعات المستخدمين (المدراء، المحاسبون، إلخ)
- ✅ `users/fixtures/groups_permissions.json` - صلاحيات كل مجموعة
- ✅ `users/fixtures/initial_data.json` - المستخدمين الأساسيين

**البيانات المتضمنة:**
- 4 مجموعات مستخدمين (المدراء، المحاسبون، مدراء المخزون، مندوبي المبيعات)
- مستخدم admin افتراضي مع كلمة مرور آمنة
- صلاحيات محددة لكل مجموعة

#### 1.2 إعدادات النظام الأساسية
```bash
python manage.py loaddata core/fixtures/initial_data.json
```

**الملفات المطلوبة:**
- ✅ `core/fixtures/initial_data.json` - إعدادات الشركة والنظام

**البيانات المتضمنة:**
- اسم الشركة والمعلومات الأساسية
- إعدادات النظام العامة
- إحصائيات لوحة التحكم الافتراضية

---

### المرحلة 2: البيانات المالية (Financial Data)
يجب تحميل هذه البيانات قبل أي عمليات مالية.

#### 2.1 الدليل المحاسبي
```bash
python manage.py loaddata financial/fixtures/chart_of_accounts_final.json
```

**الملفات المطلوبة:**
- ✅ `financial/fixtures/chart_of_accounts_final.json` - شجرة الحسابات المحدثة والمصححة

**البيانات المتضمنة:**
- 18 نوع حساب محدث ومصحح (أصول، خصوم، حقوق ملكية، إيرادات، مصروفات)
- 12 حساب أساسي مع أكواد صحيحة (11011، 11021، 11030، إلخ)
- حسابات النظام الأساسية (is_system_account = true)
- أكواد متطابقة مع دليل الحسابات المعتمد

**⚠️ ملاحظة مهمة:**
- تم إنشاء `chart_of_accounts_final.json` كبديل محدث
- الملفات القديمة (`chart_of_accounts_initial.json`, `chart_of_accounts_restructured.json`) تحتوي على أكواد خاطئة
- **استخدم `chart_of_accounts_final.json` فقط** للتهيئة الجديدة

#### 2.2 قواعد التزامن المالي
```bash
python manage.py loaddata financial/fixtures/payment_sync_rules.json
```

**الملفات المطلوبة:**
- ✅ `financial/fixtures/payment_sync_rules.json` - قواعد تزامن الدفعات

**البيانات المتضمنة:**
- 6 قواعد تزامن (إنشاء، تحديث، حذف للمبيعات والمشتريات)
- ربط تلقائي بين الدفعات والقيود المحاسبية

#### 2.3 بيانات مالية إضافية (اختياري)
```bash
python manage.py loaddata financial/fixtures/initial_data.json
```

**الملفات المطلوبة:**
- ⚠️ `financial/fixtures/initial_data.json` - بيانات مالية تجريبية (غير موجود حالياً)

**البيانات المقترحة:**
- قيود افتتاحية للحسابات
- أرصدة بنكية افتتاحية
- حركات مالية تجريبية

---

### المرحلة 3: بيانات المخزون (Inventory Data)
يجب تحميل هذه البيانات قبل إنشاء فواتير المبيعات والمشتريات.

#### 3.1 المنتجات والمخازن
```bash
python manage.py loaddata product/fixtures/initial_data.json
```

**الملفات المطلوبة:**
- ✅ `product/fixtures/initial_data.json` - المنتجات والتصنيفات والمخازن

**البيانات المتضمنة:**
- 6 تصنيفات منتجات (إلكترونيات، ملابس، أجهزة منزلية، أثاث)
- 5 علامات تجارية (سامسونج، آبل، نايكي، إل جي، ايكيا)
- 4 وحدات قياس (قطعة، متر، كيلوجرام، لتر)
- 3 مخازن (المخزن الرئيسي، مخزن الفرع، مخزن الأجهزة)
- 7 منتجات تجريبية مع أرصدة افتتاحية
- 5 أرقام تسلسلية للمستندات

---

### المرحلة 4: بيانات الأطراف (Parties Data)
يجب تحميل هذه البيانات قبل إنشاء الفواتير.

#### 4.1 العملاء
```bash
python manage.py loaddata client/fixtures/initial_data.json
```

**الملفات المطلوبة:**
- ✅ `client/fixtures/initial_data.json` - بيانات العملاء

**البيانات المتضمنة:**
- عميل نقدي افتراضي
- 6 عملاء تجريبيين (أفراد وشركات)
- عميل غير نشط للاختبار

#### 4.2 الموردين
```bash
python manage.py loaddata supplier/fixtures/initial_data.json
```

**الملفات المطلوبة:**
- ✅ `supplier/fixtures/initial_data.json` - بيانات الموردين

**البيانات المتضمنة:**
- مورد نقدي افتراضي
- 5 موردين تجريبيين
- مورد غير نشط للاختبار

---

### المرحلة 5: بيانات المعاملات (Transactions Data)
يتم تحميل هذه البيانات أخيراً لأنها تعتمد على جميع البيانات السابقة.

#### 5.1 فواتير المشتريات
```bash
python manage.py loaddata purchase/fixtures/initial_data.json
python manage.py loaddata purchase/fixtures/initial_data_extra.json
```

**الملفات المطلوبة:**
- ✅ `purchase/fixtures/initial_data.json` - فواتير مشتريات أساسية
- ✅ `purchase/fixtures/initial_data_extra.json` - فواتير مشتريات إضافية

**البيانات المتضمنة:**
- 10 فواتير مشتريات متنوعة
- حالات دفع مختلفة (مدفوع، جزئي، غير مدفوع)
- مرتجعات مشتريات
- طلبات شراء

#### 5.2 فواتير المبيعات
```bash
python manage.py loaddata sale/fixtures/initial_data.json
python manage.py loaddata sale/fixtures/initial_data_extra.json
```

**الملفات المطلوبة:**
- ✅ `sale/fixtures/initial_data.json` - فواتير مبيعات أساسية
- ✅ `sale/fixtures/initial_data_extra.json` - فواتير مبيعات إضافية

**البيانات المتضمنة:**
- 10 فواتير مبيعات متنوعة
- حالات دفع مختلفة
- مرتجعات مبيعات
- خصومات وضرائب

---

## 🚀 سكريبت التهيئة الكامل

### خيار 1: تهيئة كاملة من الصفر (Production-Ready)

```bash
#!/bin/bash
# setup_production.sh - تهيئة النظام للإنتاج

echo "🔄 بدء تهيئة النظام للإنتاج..."

# حذف قاعدة البيانات القديمة
echo "🗑️ حذف قاعدة البيانات القديمة..."
rm -f db.sqlite3

# تطبيق الهجرات
echo "📦 تطبيق الهجرات..."
python manage.py migrate

# تحميل البيانات الأساسية فقط
echo "👥 تحميل المستخدمين والصلاحيات..."
python manage.py loaddata users/fixtures/groups.json
python manage.py loaddata users/fixtures/groups_permissions.json

echo "⚙️ تحميل إعدادات النظام..."
python manage.py loaddata core/fixtures/initial_data.json

echo "💰 تحميل الدليل المحاسبي..."
python manage.py loaddata financial/fixtures/chart_of_accounts_final.json
python manage.py loaddata financial/fixtures/payment_sync_rules.json

echo "📦 تحميل هيكل المخزون..."
python manage.py loaddata product/fixtures/initial_data.json

echo "👤 تحميل العملاء والموردين..."
python manage.py loaddata client/fixtures/initial_data.json
python manage.py loaddata supplier/fixtures/initial_data.json

# إنشاء مستخدم admin
echo "🔐 إنشاء مستخدم المدير..."
python manage.py createsuperuser --username admin --email admin@example.com

echo "✅ تم تهيئة النظام بنجاح للإنتاج!"
```

### خيار 2: تهيئة كاملة مع بيانات تجريبية (Development/Testing)

```bash
#!/bin/bash
# setup_development.sh - تهيئة النظام للتطوير والاختبار

echo "🔄 بدء تهيئة النظام للتطوير..."

# حذف قاعدة البيانات القديمة
echo "🗑️ حذف قاعدة البيانات القديمة..."
rm -f db.sqlite3

# تطبيق الهجرات
echo "📦 تطبيق الهجرات..."
python manage.py migrate

# المرحلة 1: البيانات الأساسية
echo "👥 المرحلة 1: تحميل المستخدمين والصلاحيات..."
python manage.py loaddata users/fixtures/groups.json
python manage.py loaddata users/fixtures/groups_permissions.json
python manage.py loaddata users/fixtures/initial_data.json

echo "⚙️ تحميل إعدادات النظام..."
python manage.py loaddata core/fixtures/initial_data.json

# المرحلة 2: البيانات المالية
echo "💰 المرحلة 2: تحميل الدليل المحاسبي..."
python manage.py loaddata financial/fixtures/chart_of_accounts_final.json
python manage.py loaddata financial/fixtures/payment_sync_rules.json

# المرحلة 3: بيانات المخزون
echo "📦 المرحلة 3: تحميل المنتجات والمخازن..."
python manage.py loaddata product/fixtures/initial_data.json

# المرحلة 4: بيانات الأطراف
echo "👤 المرحلة 4: تحميل العملاء والموردين..."
python manage.py loaddata client/fixtures/initial_data.json
python manage.py loaddata supplier/fixtures/initial_data.json

# المرحلة 5: بيانات المعاملات
echo "📄 المرحلة 5: تحميل الفواتير..."
python manage.py loaddata purchase/fixtures/initial_data.json
python manage.py loaddata purchase/fixtures/initial_data_extra.json
python manage.py loaddata sale/fixtures/initial_data.json
python manage.py loaddata sale/fixtures/initial_data_extra.json

echo "✅ تم تهيئة النظام بنجاح مع البيانات التجريبية!"
echo "📊 يمكنك الآن تسجيل الدخول باستخدام:"
echo "   Username: admin"
echo "   Password: admin123"
```

### خيار 3: سكريبت PowerShell للويندوز

```powershell
# setup_system.ps1 - تهيئة النظام على Windows

Write-Host "🔄 بدء تهيئة النظام..." -ForegroundColor Cyan

# حذف قاعدة البيانات القديمة
Write-Host "🗑️ حذف قاعدة البيانات القديمة..." -ForegroundColor Yellow
if (Test-Path "db.sqlite3") {
    Remove-Item "db.sqlite3" -Force
}

# تطبيق الهجرات
Write-Host "📦 تطبيق الهجرات..." -ForegroundColor Yellow
python manage.py migrate

# المرحلة 1: البيانات الأساسية
Write-Host "👥 المرحلة 1: تحميل المستخدمين والصلاحيات..." -ForegroundColor Green
python manage.py loaddata users/fixtures/groups.json
python manage.py loaddata users/fixtures/groups_permissions.json
python manage.py loaddata users/fixtures/initial_data.json

Write-Host "⚙️ تحميل إعدادات النظام..." -ForegroundColor Green
python manage.py loaddata core/fixtures/initial_data.json

# المرحلة 2: البيانات المالية
Write-Host "💰 المرحلة 2: تحميل الدليل المحاسبي..." -ForegroundColor Green
python manage.py loaddata financial/fixtures/chart_of_accounts_final.json
python manage.py loaddata financial/fixtures/payment_sync_rules.json

# المرحلة 3: بيانات المخزون
Write-Host "📦 المرحلة 3: تحميل المنتجات والمخازن..." -ForegroundColor Green
python manage.py loaddata product/fixtures/initial_data.json

# المرحلة 4: بيانات الأطراف
Write-Host "👤 المرحلة 4: تحميل العملاء والموردين..." -ForegroundColor Green
python manage.py loaddata client/fixtures/initial_data.json
python manage.py loaddata supplier/fixtures/initial_data.json

# المرحلة 5: بيانات المعاملات (اختياري)
$loadTransactions = Read-Host "هل تريد تحميل البيانات التجريبية للفواتير؟ (Y/N)"
if ($loadTransactions -eq "Y" -or $loadTransactions -eq "y") {
    Write-Host "📄 المرحلة 5: تحميل الفواتير..." -ForegroundColor Green
    python manage.py loaddata purchase/fixtures/initial_data.json
    python manage.py loaddata purchase/fixtures/initial_data_extra.json
    python manage.py loaddata sale/fixtures/initial_data.json
    python manage.py loaddata sale/fixtures/initial_data_extra.json
}

Write-Host "✅ تم تهيئة النظام بنجاح!" -ForegroundColor Green
```

---

## 📝 Fixtures المفقودة والمقترحة

### 1. Financial Initial Data
**الملف:** `financial/fixtures/initial_data.json`

**البيانات المقترحة:**
```json
[
  {
    "model": "financial.journalentry",
    "pk": 1,
    "fields": {
      "number": "JE0001",
      "date": "2025-01-01",
      "description": "قيد افتتاحي - رأس المال",
      "entry_type": "opening",
      "is_posted": true,
      "created_by": 1,
      "created_at": "2025-01-01T00:00:00Z"
    }
  },
  {
    "model": "financial.journalentryline",
    "pk": 1,
    "fields": {
      "journal_entry": 1,
      "account": 1,
      "debit": "100000.00",
      "credit": "0.00",
      "description": "رصيد افتتاحي - الخزينة"
    }
  },
  {
    "model": "financial.journalentryline",
    "pk": 2,
    "fields": {
      "journal_entry": 1,
      "account": 5,
      "debit": "0.00",
      "credit": "100000.00",
      "description": "رصيد افتتاحي - رأس المال"
    }
  }
]
```

### 2. Users Initial Data (محسّن)
**الملف:** `users/fixtures/initial_data.json`

**التحسينات المقترحة:**
- إضافة مستخدمين بأدوار مختلفة
- كلمات مرور آمنة ومشفرة
- بيانات تواصل كاملة

### 3. Core Settings (موسّع)
**الملف:** `core/fixtures/system_settings.json`

**الإعدادات المقترحة:**
```json
[
  {
    "model": "core.systemsetting",
    "fields": {
      "key": "company_name",
      "value": "شركة وحيبة للتجارة",
      "data_type": "string",
      "group": "general"
    }
  },
  {
    "model": "core.systemsetting",
    "fields": {
      "key": "company_tax_number",
      "value": "123456789",
      "data_type": "string",
      "group": "general"
    }
  },
  {
    "model": "core.systemsetting",
    "fields": {
      "key": "default_currency",
      "value": "EGP",
      "data_type": "string",
      "group": "financial"
    }
  },
  {
    "model": "core.systemsetting",
    "fields": {
      "key": "default_tax_rate",
      "value": "14.00",
      "data_type": "decimal",
      "group": "financial"
    }
  },
  {
    "model": "core.systemsetting",
    "fields": {
      "key": "low_stock_threshold",
      "value": "10",
      "data_type": "integer",
      "group": "inventory"
    }
  }
]
```

### 4. Financial Accounts (موسّع)
**الملف:** `financial/fixtures/extended_accounts.json`

**حسابات إضافية مقترحة:**
- حسابات ضرائب (ضريبة القيمة المضافة، ضريبة الدخل)
- حسابات مصروفات تفصيلية (رواتب، إيجار، كهرباء، صيانة)
- حسابات إيرادات تفصيلية
- حسابات بنكية متعددة

---

## 🔍 التحقق من صحة البيانات

### سكريبت التحقق
```python
# verify_fixtures.py
from django.core.management import call_command
from django.db import connection

def verify_data():
    """التحقق من صحة البيانات المحملة"""
    
    checks = {
        'users.User': 'المستخدمين',
        'auth.Group': 'المجموعات',
        'client.Customer': 'العملاء',
        'supplier.Supplier': 'الموردين',
        'product.Product': 'المنتجات',
        'product.Warehouse': 'المخازن',
        'financial.ChartOfAccounts': 'الحسابات',
        'financial.AccountType': 'أنواع الحسابات',
    }
    
    print("🔍 التحقق من البيانات المحملة...")
    print("-" * 50)
    
    for model, name in checks.items():
        app, model_name = model.split('.')
        with connection.cursor() as cursor:
            table = f"{app}_{model_name.lower()}"
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            status = "✅" if count > 0 else "❌"
            print(f"{status} {name}: {count} سجل")
    
    print("-" * 50)
    print("✅ انتهى التحقق")

if __name__ == '__main__':
    verify_data()
```

---

## 📊 هيكل Fixtures الموصى به

```
fixtures/
├── 01_core/
│   ├── groups.json                    # المجموعات والصلاحيات
│   ├── permissions.json               # الصلاحيات التفصيلية
│   └── system_settings.json           # إعدادات النظام
│
├── 02_financial/
│   ├── account_types.json             # أنواع الحسابات
│   ├── chart_of_accounts.json         # شجرة الحسابات
│   ├── opening_balances.json          # الأرصدة الافتتاحية
│   └── payment_sync_rules.json        # قواعد التزامن
│
├── 03_inventory/
│   ├── categories.json                # تصنيفات المنتجات
│   ├── brands.json                    # الأنواع
│   ├── units.json                     # وحدات القياس
│   ├── warehouses.json                # المخازن
│   └── products.json                  # المنتجات
│
├── 04_parties/
│   ├── customers.json                 # العملاء
│   └── suppliers.json                 # الموردين
│
└── 05_demo_data/ (اختياري)
    ├── purchases.json                 # فواتير مشتريات تجريبية
    ├── sales.json                     # فواتير مبيعات تجريبية
    └── transactions.json              # معاملات مالية تجريبية
```

---

## ⚠️ ملاحظات مهمة

### 1. ترتيب التحميل
- **مهم جداً:** يجب اتباع الترتيب المذكور أعلاه
- عدم اتباع الترتيب قد يسبب أخطاء Foreign Key

### 2. كلمات المرور
- كلمات المرور في fixtures التطوير مشفرة بـ PBKDF2
- **يجب تغيير كلمات المرور في الإنتاج**
- استخدم `python manage.py changepassword` لتغيير كلمات المرور

### 3. البيانات التجريبية
- البيانات في `initial_data_extra.json` هي بيانات تجريبية فقط
- **لا تستخدمها في بيئة الإنتاج**

### 4. الأرقام التسلسلية
- fixtures المنتجات تحتوي على أرقام تسلسلية
- تأكد من تحديثها إذا كنت تضيف بيانات يدوياً

### 5. النسخ الاحتياطي
```bash
# عمل نسخة احتياطية قبل إعادة التهيئة
python manage.py dumpdata > backup_$(date +%Y%m%d_%H%M%S).json

# استعادة من نسخة احتياطية
python manage.py loaddata backup_20250101_120000.json
```

---

## 🎯 حالات الاستخدام

### 1. تهيئة نظام جديد للإنتاج
```bash
# استخدم setup_production.sh
# يحمل البيانات الأساسية فقط بدون بيانات تجريبية
```

### 2. إعداد بيئة تطوير
```bash
# استخدم setup_development.sh
# يحمل جميع البيانات بما فيها التجريبية
```

### 3. إعادة تعيين النظام للاختبار
```bash
# احذف قاعدة البيانات وأعد التهيئة
rm db.sqlite3
python manage.py migrate
# ثم حمل fixtures المطلوبة
```

### 4. تحديث البيانات الأساسية فقط
```bash
# حمل fixtures محددة دون حذف قاعدة البيانات
python manage.py loaddata --ignorenonexistent financial/fixtures/chart_of_accounts_final.json
```

---

## 📚 مراجع إضافية

- [Django Fixtures Documentation](https://docs.djangoproject.com/en/stable/howto/initial-data/)
- [Best Practices for Django Fixtures](https://docs.djangoproject.com/en/stable/topics/db/fixtures/)
- دليل النظام المالي: `docs/financial_system_documentation.md`
- دليل نظام البطاقات: `docs/cards_system.md`

---

## ✅ قائمة التحقق النهائية

قبل نشر النظام للإنتاج، تأكد من:

- [ ] تم تحميل جميع fixtures الأساسية
- [ ] تم إنشاء مستخدم admin بكلمة مرور قوية
- [ ] تم التحقق من الدليل المحاسبي
- [ ] تم إعداد المخازن والمنتجات الأساسية
- [ ] تم تكوين إعدادات النظام (اسم الشركة، الضرائب، إلخ)
- [ ] تم اختبار العمليات الأساسية (مبيعات، مشتريات، قيود)
- [ ] تم عمل نسخة احتياطية من قاعدة البيانات
- [ ] تم توثيق أي تخصيصات إضافية

---

**تم إعداده بواسطة:** فريق تطوير نظام ERP  
**آخر تحديث:** 2025-01-01  
**الإصدار:** 1.0
