# Corporate ERP — Architecture Reference

> وثيقة مرجعية للبنية التقنية الفعلية للنظام. تعكس الكود الموجود فعلاً.

---

## 1. نظرة عامة

نظام ERP مبني على **Django 4.2** يعمل بقاعدة بيانات **SQLite** (تطوير) أو **MySQL** (إنتاج). الواجهة server-rendered بـ Django Templates + Bootstrap 5، مع REST API بـ JWT للتكامل الخارجي.

```
corporate_erp/          ← Django project root
├── core/               ← النواة: إعدادات، إشعارات، مراقبة
├── users/              ← المستخدمون والصلاحيات
├── governance/         ← الحوكمة: audit، idempotency، أمان
├── client/             ← إدارة العملاء
├── sale/               ← المبيعات والفواتير
├── supplier/           ← الموردون
├── product/            ← المنتجات والمخزون
├── purchase/           ← المشتريات
├── financial/          ← المحاسبة والتقارير المالية
├── hr/                 ← الموارد البشرية والرواتب
├── printing_pricing/   ← تسعير المطبوعات
├── utils/              ← أدوات مساعدة
└── api/                ← REST API
```

---

## 2. التطبيقات (Apps)

### 2.1 core
**الغرض:** النواة المشتركة للنظام.

| النموذج | الوصف |
|---------|-------|
| `SystemSetting` | إعدادات النظام (key/value مع أنواع بيانات) |
| `Notification` | إشعارات المستخدمين |
| `NotificationPreference` | تفضيلات الإشعارات لكل مستخدم |
| `UnifiedLog` | سجل موحد (system, security, performance, audit) |
| `DashboardStat` | إحصائيات لوحة التحكم |

**الخدمات الرئيسية:**
- `NotificationService` — إرسال وإدارة الإشعارات
- `BackupService` — النسخ الاحتياطية
- `DataEncryptionService` — تشفير البيانات (Fernet)
- `DataRetentionService` — دورة حياة البيانات

---

### 2.2 users
**الغرض:** نظام المستخدمين والصلاحيات.

- نموذج `User` مخصص يرث من `AbstractUser`
- نظام أدوار (Roles) مع صلاحيات دقيقة
- JWT tokens: access (15 دقيقة) + refresh (يوم)
- Token blacklist عند تسجيل الخروج

---

### 2.3 governance
**الغرض:** طبقة الحوكمة والأمان.

| النموذج | الوصف |
|---------|-------|
| `IdempotencyRecord` | منع تكرار العمليات |
| `AuditTrail` | سجل تدقيق شامل |
| `ActiveSession` | تتبع الجلسات النشطة |
| `SecurityEvent` | أحداث أمنية |
| `DataClassification` | تصنيف حساسية البيانات |
| `BackupRecord` / `BackupFile` | تتبع النسخ الاحتياطية |
| `DataRetentionPolicy` | سياسات الاحتفاظ بالبيانات |
| `EncryptionKey` | تتبع دورة مفاتيح التشفير |

**الخدمات:**
- `AuditService` — تسجيل العمليات
- `AccountingGateway` — بوابة موحدة لإنشاء القيود المحاسبية مع idempotency
- `AdminSecurityManager` — حماية نماذج الـ admin عالية الخطورة

---

### 2.4 client
**الغرض:** إدارة العملاء.

| النموذج | الوصف |
|---------|-------|
| `Customer` | بيانات العميل مع ربط محاسبي |
| `CustomerPayment` | مدفوعات العملاء |

**العلاقات:**
- `Customer.financial_account` → `financial.ChartOfAccounts` (OneToOne)
- `Customer` ← `sale.Sale` (ForeignKey)

---

### 2.5 sale
**الغرض:** المبيعات والفواتير.

| النموذج | الوصف |
|---------|-------|
| `Sale` | فاتورة البيع |
| `SaleItem` | بنود الفاتورة |
| `SalePayment` | مدفوعات الفاتورة |
| `SaleReturn` | مرتجعات المبيعات |
| `SaleReturnItem` | بنود المرتجع |

**العلاقات:**
- `Sale.customer` → `client.Customer`
- `Sale.items` → `product.Product`
- `SalePayment` → `financial.ChartOfAccounts` (payment_method = account code)

---

### 2.6 supplier
**الغرض:** إدارة الموردين.

| النموذج | الوصف |
|---------|-------|
| `Supplier` | بيانات المورد مع ربط محاسبي |
| `SupplierType` | أنواع الموردين |
| `SupplierTypeSettings` | إعدادات ديناميكية لأنواع الموردين |
| `SupplierService` | خدمات يقدمها المورد |
| `ServiceType` | أنواع الخدمات (طباعة، لوجستيات، تصنيع) |
| `ServicePriceTier` | شرائح سعرية حسب الكمية |

**العلاقات:**
- `Supplier.financial_account` → `financial.ChartOfAccounts` (OneToOne)
- `Supplier.primary_type` → `SupplierType`

---

### 2.7 product
**الغرض:** كتالوج المنتجات وإدارة المخزون.

| النموذج | الوصف |
|---------|-------|
| `Product` | المنتج (عادي / مجمع / خدمة) |
| `Category` | تصنيفات هرمية |
| `Unit` | وحدات القياس |
| `Warehouse` | المخازن |
| `Stock` | مخزون المنتج في كل مخزن |
| `StockMovement` | حركات المخزون |
| `ProductImage` | صور المنتجات |
| `ProductVariant` | متغيرات المنتج |
| `BundleComponent` | مكونات المنتج المجمع |
| `BundleComponentAlternative` | بدائل مكونات المنتج المجمع |
| `SupplierProductPrice` | أسعار الموردين للمنتج |
| `PriceHistory` | تاريخ تغيير الأسعار |

**أنواع المنتجات:**
- `is_service=False, is_bundle=False` → منتج عادي (له مخزون)
- `is_bundle=True` → منتج مجمع (مخزونه محسوب من مكوناته)
- `is_service=True` → خدمة (لا تحتاج مخزون)

**الخدمات الرئيسية:**
- `StockCalculationEngine` — حساب مخزون المنتجات المجمعة
- `BundleManager` — إنشاء وإدارة المنتجات المجمعة
- `InventoryService` — إدارة المخزون العام
- `ReservationService` — حجز المخزون للطلبات

---

### 2.8 purchase
**الغرض:** المشتريات.

| النموذج | الوصف |
|---------|-------|
| `Purchase` | فاتورة الشراء |
| `PurchaseItem` | بنود الفاتورة |
| `PurchasePayment` | مدفوعات للمورد |
| `PurchaseReturn` | مرتجعات المشتريات |

**العلاقات:**
- `Purchase.supplier` → `supplier.Supplier`
- `Purchase.items` → `product.Product`

---

### 2.9 financial
**الغرض:** المحاسبة المزدوجة والتقارير المالية.

| النموذج | الوصف |
|---------|-------|
| `AccountType` | أنواع الحسابات (أصول، خصوم، إيرادات، مصروفات) |
| `ChartOfAccounts` | دليل الحسابات الهرمي |
| `AccountGroup` | مجموعات الحسابات |
| `JournalEntry` | القيد المحاسبي |
| `JournalEntryLine` | بنود القيد |
| `AccountingPeriod` | الفترات المحاسبية |
| `FinancialCategory` | تصنيفات مالية للإيرادات/المصروفات |
| `FinancialTransaction` | معاملات مالية موحدة |
| `PartnerTransaction` | معاملات الشركاء |
| `Loan` / `LoanPayment` | القروض وأقساطها |

**قاعدة القيود:**
- كل عملية مالية تمر عبر `AccountingGateway` (في governance)
- `AccountingGateway` يضمن idempotency ويمنع التكرار
- القيود تُنشأ بـ `source_module` + `source_model` + `source_id`

**الخدمات الرئيسية (45+):**
- `JournalEntryService` — إنشاء القيود
- `BalanceService` — حساب الأرصدة
- `PaymentIntegrationService` — تكامل المدفوعات
- `AccountingIntegrationService` — تكامل المحاسبة مع باقي الموديولات
- `BankReconciliationService` — التسوية البنكية
- `TrialBalanceService` / `IncomeStatementService` / `BalanceSheetService` — التقارير
- `DataReconciliationService` — مطابقة البيانات اليومية

---

### 2.10 hr
**الغرض:** الموارد البشرية والرواتب.

| النموذج | الوصف |
|---------|-------|
| `Employee` | بيانات الموظف الشاملة |
| `Department` | الأقسام |
| `JobTitle` | المسميات الوظيفية |
| `Contract` | عقود العمل مع مكونات الراتب |
| `Shift` | الورديات |
| `Attendance` | سجل الحضور اليومي |
| `AttendanceSummary` | ملخصات الحضور |
| `BiometricDevice` | أجهزة البصمة |
| `BiometricLog` | سجلات البصمة الخام |
| `LeaveType` | أنواع الإجازات |
| `LeaveBalance` | أرصدة الإجازات |
| `LeaveRequest` | طلبات الإجازة |
| `Payroll` | كشف الرواتب |
| `PayrollItem` | بنود الراتب |
| `InsurancePayment` | دفعات التأمين |
| `EndOfServiceBenefit` | مكافأة نهاية الخدمة |
| `OfficialHoliday` | الإجازات الرسمية |

**الخدمات الرئيسية:**
- `PayrollService` — حساب الرواتب
- `AttendanceSummaryService` — معالجة الحضور
- `BiometricService` — تكامل أجهزة البصمة
- `LeaveAccrualService` — استحقاق الإجازات
- `OrganizationService` — إدارة الهيكل التنظيمي

---

### 2.11 printing_pricing
**الغرض:** إدارة طلبات الطباعة والتسعير.

| النموذج | الوصف |
|---------|-------|
| `PrintingOrder` | طلب الطباعة |
| `OrderMaterial` | مواد الطلب |
| `OrderService` | خدمات الطلب |
| `PaperSpecification` | مواصفات الورق |
| `PrintingSpecification` | مواصفات الطباعة |

---

### 2.12 api
**الغرض:** REST API للتكامل الخارجي.

- JWT authentication (SimpleJWT)
- Rate limiting على token endpoints
- Endpoints: `/api/token/`, `/api/token/refresh/`, `/api/token/verify/`, `/api/token/blacklist/`

---

## 3. طبقة الـ Middleware (بالترتيب)

```python
MIDDLEWARE = [
    AdvancedSecurityHeadersMiddleware,   # CSP, HSTS, X-Frame-Options
    SecurityEventLoggerMiddleware,        # تسجيل أحداث أمنية
    SimpleMonitoringMiddleware,           # مراقبة الطلبات
    SecurityMiddleware,                   # Django built-in
    WhiteNoiseMiddleware,                 # Static files
    CorsMiddleware,                       # CORS headers
    SessionMiddleware,                    # Sessions
    CommonMiddleware,                     # Common checks
    CsrfViewMiddleware,                   # CSRF protection
    AuthenticationMiddleware,             # User authentication
    MessageMiddleware,                    # Flash messages
    XFrameOptionsMiddleware,              # Clickjacking protection
    BlockedIPMiddleware,                  # IP blocking
    RateLimitingMiddleware,               # Rate limiting
    SecurityEventMiddleware,              # Security events
    WebhookSecurityMiddleware,            # Webhook validation
    RequestLoggingMiddleware,             # Request logging
    SQLiteOptimizationMiddleware,         # DB optimization
    DatabaseConnectionMiddleware,         # Connection management
    SessionTrackingMiddleware,            # Session monitoring
    ModuleAccessMiddleware,               # Module enable/disable
    CurrentUserMiddleware,                # Current user context
    RealTimePermissionMiddleware,         # Permission checking
    JWTAuthMiddleware,                    # JWT processing
]
```

---

## 4. قاعدة البيانات

```
Development:  SQLite  (db.sqlite3)
Production:   MySQL   (via PyMySQL)
```

**إعدادات مشتركة:**
- `ATOMIC_REQUESTS = True` — كل request في transaction
- `CONN_MAX_AGE = 60` — connection pooling

**Caching:**
- Production: Redis (`redis://localhost:6379/0`)
- Development: LocMem cache

---

## 5. Celery (المهام الخلفية)

**Broker:** Redis (production) / Memory (development)

| المهمة | الجدول |
|--------|--------|
| `hr.tasks.process_biometric_logs_task` | كل 5 دقائق |
| `hr.tasks.cleanup_old_biometric_logs` | أسبوعياً |

> ملاحظة: الـ `celery.py` يحتوي على مهام قديمة مرتبطة بـ `students` app — تحتاج تنظيف.

---

## 6. URL Structure

```
/                       → core (dashboard)
/login/ /logout/        → authentication
/api/                   → REST API (JWT)
/admin/                 → Django admin
/customers/             → client app
/sales/                 → sale app
/supplier/              → supplier app
/products/              → product app
/purchases/             → purchase app
/financial/             → financial app
/hr/                    → hr app
/governance/            → governance app
/printing-pricing/      → printing_pricing app
/users/                 → users app
/utils/                 → utils app
/health/ /ready/        → health checks
```

---

## 7. Authentication Flow

```
1. POST /api/token/          → {access, refresh}
2. GET  /api/endpoint/       → Authorization: Bearer <access>
3. POST /api/token/refresh/  → {access} (عند انتهاء الـ access)
4. POST /api/token/blacklist/ → logout (يُبطل الـ refresh)
```

**Session-based (للواجهة):**
- Django sessions مع 30 دقيقة timeout
- CSRF protection على جميع POST requests

---

## 8. Frontend Stack

| المكتبة | الاستخدام |
|---------|----------|
| Bootstrap 5 | CSS framework |
| jQuery 3.6 | DOM manipulation |
| DataTables | جداول بيانات مع بحث وترتيب |
| Select2 | قوائم منسدلة محسّنة |
| Chart.js | رسوم بيانية |
| FlatPickr | date/time picker |
| SweetAlert2 | نوافذ تأكيد |
| Toastr | إشعارات toast |
| Font Awesome | أيقونات |
| Tajawal | خط عربي |

**مكونات موحدة (Shared Components):**
- `shared/page_header.html` — هيدر الصفحة مع breadcrumb
- `components/data_table.html` — جدول بيانات موحد
- `components/stats_card.html` — بطاقات إحصائية
- `components/payment_account_select.html` — اختيار حساب الدفع

---

## 9. نمط طبقة الخدمات

كل app يتبع نمط:

```
views.py / views/
    ↓ يستدعي
services/
    ↓ يستدعي
models/
    ↓ يكتب عبر
AccountingGateway (للعمليات المالية)
    ↓ يسجل في
governance.AuditTrail
```

**قاعدة:** لا يكتب أي view مباشرة في `JournalEntry` — كل القيود تمر عبر `AccountingGateway`.

---

## 10. العلاقات الرئيسية بين الـ Apps

```
client.Customer ──────────────────────────────────────────┐
                                                           ↓
sale.Sale ──────────────────────────────────── financial.ChartOfAccounts
    ↓                                                      ↑
sale.SalePayment ──────────────────────────────────────────┘
                                                           ↑
purchase.Purchase ──────────────────────────────────────────┤
    ↓                                                      ↑
purchase.PurchasePayment ──────────────────────────────────┘
                                                           ↑
supplier.Supplier ─────────────────────────────────────────┤
                                                           ↑
hr.Payroll ─────────────────────────────────────────────────┘

product.Product ←── sale.SaleItem
product.Product ←── purchase.PurchaseItem
product.Stock   ←── product.StockMovement (via MovementService)
```

---

## 11. إعدادات الأمان

| الإعداد | القيمة |
|---------|--------|
| `SECURE_SSL_REDIRECT` | True (production) |
| `SESSION_COOKIE_SECURE` | True (production) |
| `CSRF_COOKIE_SECURE` | True (production) |
| `X_FRAME_OPTIONS` | DENY |
| `SECURE_HSTS_SECONDS` | 31536000 |
| JWT Access Token | 15 دقيقة |
| JWT Refresh Token | 1 يوم |
| Session Timeout | 30 دقيقة |
| Rate Limit (token) | 5 req/min |

---

## 12. ملاحظات تقنية مهمة

1. **`db_column='school_item_type'`** في `product.Product.item_type` — اسم العمود في DB قديم، لا تغيره بدون migration.

2. **Celery beat schedule** في `corporate_erp/celery.py` يحتوي على مهام `students.*` قديمة — تحتاج حذف.

3. **`financial/services/data_reconciliation_service.py`** يحتوي على `RECONCILIATION_TYPES = ['student_fees', ...]` — `student_fees` تحتاج حذف.

4. **`financial/services/journal_service.py`** يحتوي على دوال مرتبطة بـ `StudentFee` / `FeePayment` — موثقة في `docs/school-modules-cleanup-inventory.md`.

5. **Bridge Agent** (`bridge_agent/`) — agent خارجي للتكامل مع أجهزة البصمة، يعمل كـ Windows service منفصل.
