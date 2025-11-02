# 🏗️ معمارية نظام MWHEBA ERP

**الإصدار:** 1.0.0  
**تاريخ التحديث:** 2025-11-02  
**الحالة:** مكتمل ✅

---

## 📋 نظرة عامة

نظام MWHEBA ERP مبني على معمارية **Django MVT (Model-View-Template)** مع تطبيق أفضل الممارسات في تصميم الأنظمة المؤسسية.

### المبادئ الأساسية

1. **Separation of Concerns** - فصل المسؤوليات
2. **DRY (Don't Repeat Yourself)** - عدم تكرار الكود
3. **SOLID Principles** - مبادئ البرمجة الكائنية
4. **Service Layer Pattern** - طبقة خدمات منفصلة
5. **Repository Pattern** - نمط المستودعات

---

## 🎯 هيكل المشروع

```
mwheba_erp/
├── api/                    # REST API
├── client/                 # إدارة العملاء
├── core/                   # النواة الأساسية
├── financial/              # النظام المالي
├── printing_pricing/       # نظام التسعير
├── product/                # إدارة المنتجات
├── purchase/               # المشتريات
├── sale/                   # المبيعات
├── supplier/               # الموردين
├── users/                  # المستخدمين
├── utils/                  # أدوات مساعدة
├── static/                 # الملفات الثابتة
├── templates/              # القوالب
└── media/                  # ملفات المستخدمين
```

---

## 🔧 المكونات الرئيسية

### 1. Core App - النواة الأساسية

**المسؤوليات:**
- إعدادات النظام والشركة
- Dashboard الرئيسي
- نظام الإشعارات
- الخدمات المشتركة

**النماذج الرئيسية:**
```python
- SystemSetting        # إعدادات النظام
- CompanySetting       # إعدادات الشركة
- Notification         # الإشعارات
- NotificationPreference  # تفضيلات الإشعارات
- Currency             # العملات
- AccountingPeriod     # الفترات المحاسبية
```

**الخدمات:**
```python
- NotificationService  # إدارة الإشعارات
  - create_notification()
  - check_low_stock_alerts()
  - check_due_invoices_alerts()
  - _send_email_notification()
  - _send_sms_notification()
```

### 2. Financial App - النظام المالي

**المسؤوليات:**
- دليل الحسابات
- القيود المحاسبية
- الإيرادات والمصروفات
- معاملات الشريك
- التقارير المالية

**النماذج الرئيسية:**
```python
- ChartOfAccounts      # دليل الحسابات
- JournalEntry         # القيود المحاسبية
- JournalEntryLine     # سطور القيود
- Income               # الإيرادات
- Expense              # المصروفات
- PartnerTransaction   # معاملات الشريك
- PartnerBalance       # رصيد الشريك
```

**الخدمات:**
```python
- PaymentEditService   # تعديل الدفعات
  - can_edit_payment()
  - can_unpost_payment()
  - edit_payment()
  - unpost_payment()
```

**التقارير:**
- دفتر الأستاذ (Ledger)
- ميزان المراجعة (Trial Balance)
- الميزانية العمومية (Balance Sheet)
- قائمة الدخل (Income Statement)
- التدفقات النقدية (Cash Flow)

### 3. Product App - إدارة المنتجات

**المسؤوليات:**
- إدارة المنتجات والتصنيفات
- إدارة المخزون
- حركات المخزون
- تتبع الدفعات والأرقام التسلسلية

**النماذج الرئيسية:**
```python
- Product              # المنتجات
- Category             # التصنيفات
- Stock                # المخزون
- StockMovement        # حركات المخزون
- Warehouse            # المخازن
- BatchTracking        # تتبع الدفعات
- SerialNumber         # الأرقام التسلسلية
```

**الخدمات:**
```python
- InventoryService     # إدارة المخزون
  - adjust_stock()
  - transfer_stock()
  - get_stock_value()
```

### 4. Printing_Pricing App - نظام التسعير

**المسؤوليات:**
- إعدادات الطباعة والتسعير
- حسابات التكلفة المعقدة
- إدارة المقاسات والماكينات

**النماذج الرئيسية:**
```python
# إعدادات الورق
- PaperType            # أنواع الورق
- PaperSize            # مقاسات الورق
- PaperWeight          # أوزان الورق
- PaperOrigin          # منشأ الورق

# إعدادات الطباعة
- OffsetMachineType    # أنواع ماكينات الأوفست
- OffsetSheetSize      # مقاسات ماكينات الأوفست
- DigitalMachineType   # أنواع ماكينات الديجيتال
- DigitalSheetSize     # مقاسات ماكينات الديجيتال

# إعدادات التشطيب
- CoatingType          # أنواع التغطية
- FinishingType        # أنواع التشطيب
- PieceSize            # مقاسات القطع
- PlateSize            # مقاسات الزنكات
```

### 5. Supplier App - إدارة الموردين

**المسؤوليات:**
- إدارة الموردين وأنواعهم
- الخدمات المتخصصة
- نظام موحد للخدمات

**النماذج الرئيسية:**
```python
- Supplier             # الموردين
- SupplierType         # أنواع الموردين
- SupplierTypeSettings # إعدادات الأنواع

# الخدمات المتخصصة
- PaperServiceDetails  # خدمات الورق
- OffsetPrintingDetails  # خدمات الأوفست
- DigitalPrintingDetails # خدمات الديجيتال
- PlateServiceDetails  # خدمات الزنكات
- FinishingServiceDetails # خدمات التشطيب
```

**النظام الموحد:**
```python
- ServiceFormFactory   # مصنع النماذج الموحد
  - get_unified_paper_choices()
  - get_unified_offset_choices()
  - get_unified_ctp_choices()
  - normalize_legacy_data()
```

### 6. Sale & Purchase Apps - المبيعات والمشتريات

**المسؤوليات:**
- إدارة فواتير المبيعات والمشتريات
- إدارة الدفعات
- المرتجعات
- التكامل مع المخزون والمالية

**النماذج الرئيسية:**
```python
# المبيعات
- Sale                 # فواتير المبيعات
- SaleItem             # عناصر الفاتورة
- SalePayment          # دفعات المبيعات
- SaleReturn           # مرتجعات المبيعات

# المشتريات
- Purchase             # فواتير المشتريات
- PurchaseItem         # عناصر الفاتورة
- PurchasePayment      # دفعات المشتريات
- PurchaseReturn       # مرتجعات المشتريات
```

### 7. Users App - إدارة المستخدمين

**المسؤوليات:**
- إدارة المستخدمين والصلاحيات
- الأدوار الوظيفية
- سجل النشاطات

**النماذج الرئيسية:**
```python
- User                 # المستخدمين (Custom User)
- Role                 # الأدوار الوظيفية
- ActivityLog          # سجل النشاطات
```

---

## 🔄 تدفق البيانات (Data Flow)

### 1. دورة المبيعات

```
عميل → فاتورة مبيعات → عناصر الفاتورة
                    ↓
            حركات المخزون (خصم)
                    ↓
            قيد محاسبي تلقائي
                    ↓
        تحديث رصيد العميل
                    ↓
            دفعات المبيعات
                    ↓
        قيد محاسبي للدفعة
```

### 2. دورة المشتريات

```
مورد → فاتورة مشتريات → عناصر الفاتورة
                    ↓
            حركات المخزون (إضافة)
                    ↓
            قيد محاسبي تلقائي
                    ↓
        تحديث رصيد المورد
                    ↓
            دفعات المشتريات
                    ↓
        قيد محاسبي للدفعة
```

### 3. دورة المخزون

```
منتج → مخزن → كمية
        ↓
    حركة مخزون
        ↓
    تحديث الكمية
        ↓
    تنبيه إذا منخفض
```

---

## 🎨 Design Patterns المستخدمة

### 1. Service Layer Pattern

**الهدف:** فصل منطق العمل عن Views

**مثال:**
```python
# financial/services/payment_edit_service.py
class PaymentEditService:
    @classmethod
    def edit_payment(cls, payment, payment_type, new_data, user):
        # منطق معقد لتعديل الدفعة
        pass
```

### 2. Repository Pattern

**الهدف:** تجريد الوصول لقاعدة البيانات

**مثال:**
```python
# product/repositories/product_repository.py
class ProductRepository:
    @staticmethod
    def get_low_stock_products():
        return Product.objects.filter(
            current_stock__lte=F('min_stock')
        )
```

### 3. Factory Pattern

**الهدف:** إنشاء كائنات معقدة

**مثال:**
```python
# supplier/forms/dynamic_forms.py
class ServiceFormFactory:
    @staticmethod
    def get_form_for_category(category):
        # إنشاء النموذج المناسب حسب الفئة
        pass
```

### 4. Strategy Pattern

**الهدف:** اختيار الخوارزمية المناسبة

**مثال:**
```python
# printing_pricing/calculators/
class PricingStrategy:
    def calculate(self, order):
        pass

class OffsetPricingStrategy(PricingStrategy):
    def calculate(self, order):
        # حساب سعر الأوفست
        pass
```

### 5. Observer Pattern

**الهدف:** الإشعار بالتغييرات

**مثال:**
```python
# Django Signals
@receiver(post_save, sender=Sale)
def create_journal_entry(sender, instance, created, **kwargs):
    if created:
        # إنشاء قيد محاسبي تلقائي
        pass
```

---

## 🔐 نظام الصلاحيات

### 1. مستويات الصلاحيات

```python
# المستويات
1. Superuser        # مدير النظام
2. Admin            # مدير
3. Manager          # مدير قسم
4. Accountant       # محاسب
5. Sales            # مندوب مبيعات
6. Warehouse        # أمين مخزن
7. Viewer           # مراجع (قراءة فقط)
```

### 2. نظام الأدوار (Roles)

```python
class Role(models.Model):
    name = models.CharField(max_length=50, unique=True)
    display_name = models.CharField(max_length=100)
    permissions = models.ManyToManyField(Permission)
    is_system_role = models.BooleanField(default=False)
```

### 3. Permissions المخصصة

```python
class Meta:
    permissions = [
        ("can_edit_posted_payments", "يمكنه تعديل الدفعات المرحلة"),
        ("can_unpost_payments", "يمكنه إلغاء ترحيل الدفعات"),
        ("can_delete_journal_entries", "يمكنه حذف القيود المحاسبية"),
    ]
```

---

## 📊 قاعدة البيانات

### 1. استراتيجية التصميم

- **Normalization** - تطبيع البيانات (3NF)
- **Foreign Keys** - مفاتيح أجنبية مع CASCADE
- **Indexes** - فهارس للحقول المستخدمة كثيراً
- **Constraints** - قيود لضمان سلامة البيانات

### 2. العلاقات الرئيسية

```
User ──┬── Sale (created_by)
       ├── Purchase (created_by)
       ├── JournalEntry (created_by)
       └── ActivityLog

Customer ──── Sale ──── SaleItem ──── Product
                 └──── SalePayment

Supplier ──── Purchase ──── PurchaseItem ──── Product
                      └──── PurchasePayment

Product ──── Stock ──── Warehouse
         └── StockMovement

ChartOfAccounts ──── JournalEntryLine ──── JournalEntry
```

### 3. Soft Delete

بعض النماذج تستخدم Soft Delete:
```python
class SoftDeleteModel(models.Model):
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        abstract = True
```

---

## 🔄 نظام الـ Signals

### 1. Post Save Signals

```python
# sale/signals.py
@receiver(post_save, sender=Sale)
def create_sale_journal_entry(sender, instance, created, **kwargs):
    if created and instance.status == 'completed':
        # إنشاء قيد محاسبي للمبيعات
        pass

@receiver(post_save, sender=SalePayment)
def create_payment_journal_entry(sender, instance, created, **kwargs):
    if created:
        # إنشاء قيد محاسبي للدفعة
        pass
```

### 2. Pre Delete Signals

```python
@receiver(pre_delete, sender=Product)
def check_product_usage(sender, instance, **kwargs):
    # التحقق من عدم وجود معاملات مرتبطة
    if instance.sale_items.exists():
        raise ValidationError("لا يمكن حذف منتج له معاملات")
```

---

## 🎯 API Architecture

### 1. REST API Structure

```
/api/
├── token/              # المصادقة
├── users/              # المستخدمين
├── products/           # المنتجات
├── categories/         # التصنيفات
├── suppliers/          # الموردين
├── customers/          # العملاء
├── sales/              # المبيعات
├── purchases/          # المشتريات
├── accounts/           # الحسابات
└── journal-entries/    # القيود
```

### 2. Serializers Hierarchy

```python
# List Serializer (مختصر)
ProductListSerializer
    - id, name, sku, price, stock

# Detail Serializer (كامل)
ProductDetailSerializer
    - جميع الحقول
    - العلاقات
    - الحسابات المشتقة
```

### 3. ViewSets

```python
class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    
    @action(detail=False, methods=['get'])
    def low_stock(self, request):
        # endpoint مخصص
        pass
```

---

## 🎨 Frontend Architecture

### 1. Template Structure

```
templates/
├── base.html           # القالب الأساسي
├── partials/           # مكونات قابلة لإعادة الاستخدام
│   ├── header.html
│   ├── sidebar.html
│   └── footer.html
├── components/         # مكونات UI
│   ├── modals/
│   ├── cells/
│   └── forms/
└── [app_name]/         # قوالب التطبيقات
```

### 2. Static Files Organization

```
static/
├── css/
│   ├── base.css        # الأساسيات
│   ├── auth.css        # المصادقة
│   └── [app].css       # خاص بالتطبيق
├── js/
│   ├── vendor/         # المكتبات الخارجية
│   ├── common.js       # دوال مشتركة
│   └── [app].js        # خاص بالتطبيق
├── fonts/              # الخطوط العربية
└── img/                # الصور
```

### 3. JavaScript Patterns

```javascript
// Module Pattern
const AppModule = (function() {
    // Private
    function privateMethod() {}
    
    // Public
    return {
        publicMethod: function() {}
    };
})();

// Event Delegation
document.addEventListener('click', function(e) {
    if (e.target.matches('.delete-btn')) {
        // معالجة الحذف
    }
});
```

---

## 🔧 Configuration Management

### 1. Settings Structure

```python
mwheba_erp/settings/
├── base.py             # الإعدادات الأساسية
├── development.py      # التطوير
├── production.py       # الإنتاج
└── testing.py          # الاختبار
```

### 2. Environment Variables

```python
# .env
SECRET_KEY=xxx
DEBUG=True
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
EMAIL_HOST=smtp.gmail.com
```

### 3. Feature Flags

```python
# core/models.py
class SystemSetting:
    FEATURE_FLAGS = {
        'enable_sms': False,
        'enable_partner_system': True,
        'enable_batch_tracking': True,
    }
```

---

## 📈 Performance Optimization

### 1. Database Optimization

```python
# استخدام select_related للـ ForeignKey
products = Product.objects.select_related('category')

# استخدام prefetch_related للـ ManyToMany
sales = Sale.objects.prefetch_related('items__product')

# استخدام only/defer
products = Product.objects.only('id', 'name', 'price')
```

### 2. Caching Strategy

```python
# Cache Framework
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
    }
}

# استخدام Cache
from django.core.cache import cache

def get_dashboard_stats():
    stats = cache.get('dashboard_stats')
    if not stats:
        stats = calculate_stats()
        cache.set('dashboard_stats', stats, 300)  # 5 دقائق
    return stats
```

### 3. Query Optimization

```python
# تجنب N+1 Problem
# سيء ❌
for sale in Sale.objects.all():
    print(sale.customer.name)  # استعلام لكل sale

# جيد ✅
for sale in Sale.objects.select_related('customer'):
    print(sale.customer.name)  # استعلام واحد
```

---

## 🧪 Testing Strategy

### 1. Test Types

```python
# Unit Tests
class ProductModelTest(TestCase):
    def test_product_creation(self):
        pass

# Integration Tests
class SaleWorkflowTest(TestCase):
    def test_complete_sale_cycle(self):
        pass

# API Tests
class ProductAPITest(APITestCase):
    def test_list_products(self):
        pass
```

### 2. Test Coverage

```bash
# تشغيل الاختبارات مع التغطية
coverage run --source='.' manage.py test
coverage report
coverage html
```

---

## 🔒 Security Best Practices

### 1. Authentication & Authorization

- استخدام Django's built-in authentication
- JWT للـ API
- Session security
- CSRF protection

### 2. Data Validation

```python
# Form Validation
class ProductForm(forms.ModelForm):
    def clean_price(self):
        price = self.cleaned_data['price']
        if price < 0:
            raise ValidationError("السعر يجب أن يكون موجباً")
        return price
```

### 3. SQL Injection Prevention

- استخدام Django ORM
- تجنب raw SQL
- استخدام parameterized queries

---

## 📝 Logging Strategy

### 1. Logging Configuration

```python
LOGGING = {
    'version': 1,
    'handlers': {
        'file': {
            'class': 'logging.FileHandler',
            'filename': 'logs/django.log',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'level': 'INFO',
        },
    },
}
```

### 2. Usage

```python
import logging
logger = logging.getLogger(__name__)

logger.info("معلومة")
logger.warning("تحذير")
logger.error("خطأ")
```

---

## 🚀 Deployment Architecture

### 1. Production Stack

```
Nginx (Reverse Proxy)
    ↓
Gunicorn (WSGI Server)
    ↓
Django Application
    ↓
PostgreSQL (Database)
    ↓
Redis (Cache & Queue)
```

### 2. Static Files

```python
# settings.py
STATIC_ROOT = '/var/www/static/'
MEDIA_ROOT = '/var/www/media/'

# Nginx
location /static/ {
    alias /var/www/static/;
}
```

---

## 📚 المراجع والموارد

### Documentation
- Django: https://docs.djangoproject.com/
- Django REST Framework: https://www.django-rest-framework.org/
- PostgreSQL: https://www.postgresql.org/docs/

### Best Practices
- Two Scoops of Django
- Django Design Patterns
- Clean Code

---

**آخر تحديث:** 2025-11-02  
**المطور:** فريق MWHEBA ERP  
**الإصدار:** 1.0.0
