# MWHEBA ERP — Architecture Reference

> وثيقة مرجعية للبنية التقنية والمعمارية الفعلية لنظام **MWHEBA ERP**. تعكس الكود وبيئات التشغيل الحقيقية بنسبة 100%.

---

## 1. نظرة عامة

نظام **MWHEBA ERP** هو منصة مؤسسية متكاملة متعددة الأنشطة مبنية على **Django 4.2 LTS**، مصممة لإدارة العمليات الصناعية والتجارية والمالية المتشابكة — من مطابع الأوفست والديجيتال الكبرى، إلى وكالات الدعاية وشركات التوزيع والتجارة.

يعمل النظام بقاعدة بيانات **SQLite** (في بيئة التطوير) و **MySQL 8.0** عبر `PyMySQL` (في بيئة الإنتاج). الواجهة معتمدة على Server-Side Rendering بـ Django Templates مع Bootstrap 5 وقواعد صارمة للتصميم، إلى جانب REST API مؤمن بـ JWT للتكاملات الخارجية.

```
corporate_erp/          ← جذر مشروع جانغو
├── core/               ← النواة: إعدادات النظام، تفعيل الأنشطة (SystemModule)، نظام المستندات (DMS)
├── users/              ← إدارة الهوية: منظومة الـ 10 أدوار القياسية، RolePermissionBackend O(1)
├── governance/         ← الحوكمة: بوابة المحاسبة (AccountingGateway)، سجل التدقيق (AuditTrail)، مانع التكرار (Idempotency)
├── customer/           ← إدارة العملاء والحسابات المدينة وكشوف الحسابات
├── sale/               ← خط أنابيب المبيعات: عروض الأسعار، فواتير المبيعات، إشعارات الخصم، قوائم الأسعار
├── supplier/           ← إدارة الموردين، الخدمات، وشرائح الأسعار
├── product/            ← المخزون الموحد: خامات الورق والمنتجات، حركات المخزن، وتتبع الأصناف
├── printing_pricing/   ← منظومة تسعير المطبوعات: الماكينات، مقاسات الأفرخ، الزنكات، السلوفان، وحساب الهالك
├── work_order/         ← إدارة أوامر الشغل وصالة الإنتاج ومراكز التكلفة التشغيلية
├── purchase/           ← المشتريات: أوامر الشراء، فواتير الموردين، وتوزيع تكاليف الشحن (Landed Cost)
├── financial/          ← المحاسبة المالية المزدوجة ومحرك تقييم العملات الدولية (IAS 21 FX Engine)
├── hr/                 ← إدارة الموارد البشرية، الرواتب، سجلات وأجهزة البصمة، والإجازات
├── presentation/       ← طبقة العرض والـ DTOs والـ Presenters لفصل منطق العرض عن قواعد البيانات
├── utils/              ← الأدوات المساعدة والمكونات المشتركة
└── api/                ← واجهات REST API للتكامل الخارجي
```

---

## 2. التطبيقات وطبقات النظام (Apps & Architecture Layers)

### 2.1 core
**الغرض:** النواة المشتركة للمنصة ونظام إدارة تفعيل الموديولات والمستندات.

| النموذج | الوصف |
|---------|-------|
| `SystemSetting` | إعدادات النظام الموحدة مع التخزين المؤقت (`global_settings_dict_v2`). |
| `SystemModule` | محرك تفعيل وتعطيل الموديولات والأنشطة ديناميكياً مع الاعتماديات (`enabled_modules_dict_v2`). |
| `Notification` | إشعارات المستخدمين والتنبيهات المباشرة. |
| `NotificationPreference` | تفضيلات الإشعارات وقنوات التسليم لكل مستخدم. |
| `UnifiedLog` | سجل أحداث النظام والعمليات الأمنية. |
| `DashboardStat` | الإحصائيات المجمعة للوحة التحكم. |

**الخدمات الرئيسية:**
- `NotificationService` — إدارة وإرسال الإشعارات.
- `BackupService` — النسخ الاحتياطي وإدارة الملفات المضغوطة.
- `DataEncryptionService` — تشفير الحقول الحساسة (Fernet).

---

### 2.2 users
**الغرض:** إدارة الهوية وصلاحيات الوصول المؤسسية (NIST Enterprise RBAC Level 2).

- نموذج `User` مخصص يرث من `AbstractUser`، مع استئصال كامل وتام لأي حقول قديمة مثل `user_type`.
- **منظومة الـ 10 أدوار القياسية**:
  `admin`, `financial_manager`, `accountant`, `sales_manager`, `sales_rep`, `procurement_officer`, `inventory_manager`, `production_supervisor`, `hr_officer`, `viewer`.
- **`RolePermissionBackend`**: محرك مصادقة وفحص صلاحيات فائق السرعة $O(1)$ مع كاش لحظي على مستوى الطلب (`_cached_group_permissions`).
- فحص الصلاحيات المعياري بصيغة `'app_label.codename'`.

---

### 2.3 governance
**الغرض:** صمام الأمان والحوكمة والنزاهة المحاسبية والرقابية.

| النموذج | الوصف |
|---------|-------|
| `AccountingGateway` | البوابة الموحدة والوحيدة لإنشاء وترحيل القيود المحاسبية لمنع التجاوز. |
| `IdempotencyRecord` | منع تكرار العمليات المالية عبر مفاتيح فريدة (`idempotency_key`). |
| `AuditTrail` | سجل تدقيق غير قابل للتعديل يسجل بيانات ما قبل وما بعد العملية ومصدرها. |
| `QuarantineRecord` | عزل البيانات المشبوهة أو المتضاربة للفحص الإداري. |
| `ActiveSession` | مراقبة وتتبع الجلسات النشطة وحمايتها من التداخل. |

---

### 2.4 customer
**الغرض:** إدارة العملاء، حدود الائتمان، والحسابات المدينة.

| النموذج | الوصف |
|---------|-------|
| `Customer` | بيانات العميل، نوع المنشأة، حد الائتمان، والربط بحساب دليل الحسابات. |
| `CustomerPayment` | مدفوعات وسندات قبض العملاء المربوطة بالخزائن والبنوك. |

---

### 2.5 sale
**الغرض:** إدارة خط أنابيب المبيعات بالكامل من التسعير إلى التحصيل.

| النموذج | الوصف |
|---------|-------|
| `Quotation` / `QuotationItem` | عروض الأسعار المقدمة للعملاء مع حجز المخزون وربط أوامر الشغل. |
| `Sale` / `SaleItem` | فواتير المبيعات التجارية والضريبية. |
| `SalePayment` | توزيع الدفعات والتحصيلات على الفواتير. |
| `SaleReturn` / `SaleReturnItem` | مرتجعات المبيعات مع تسوية المخزن والقيود العكسية. |
| `CreditNote` | إشعارات الائتمان والتسويات الدائنة للعملاء. |
| `PriceList` / `PriceListItem` | قوائم الأسعار المتعددة (جملة، قطاعي، كبار عملاء) وسياسات الخصم التلقائي. |

---

### 2.6 supplier
**الغرض:** إدارة الموردين والخدمات الصناعية والتجارية.

| النموذج | الوصف |
|---------|-------|
| `Supplier` | بيانات المورد والربط المحاسبي المباشر. |
| `SupplierType` | تصنيفات الموردين (خامات ورق، أحبار، خدمات ما بعد الطباعة، لوجستيات). |
| `SupplierService` / `ServicePriceTier` | خدمات الموردين وشرائح الأسعار حسب الكميات. |

---

### 2.7 product
**الغرض:** كتالوج المنتجات وإدارة المخازن (الالتزام الصارم بمصطلحات المخازن).

| النموذج | الوصف |
|---------|-------|
| `Product` | المنتج أو الخامة (خام ورق، أحبار، زنكات، منتج نهائي، خدمة). |
| `Category` / `Unit` | التصنيفات الهرمية ووحدات القياس المتعددة. |
| `Warehouse` | المخازن (ممنوع استخدام لفظ مستودع نهائياً). |
| `Stock` | أرصدة المخزون الموزعة على كل مخزن. |
| `StockMovement` | سجل حركات الإضافة والصرف والتحويل المخزني. |
| `StockTransfer` / `StockSnapshot` | التحويلات بين المخازن واللقطات الدورية للجرد. |

---

### 2.8 printing_pricing
**الغرض:** المنظومة الصناعية الشاملة لتسعير المطبوعات وحساب الهالك والتكاليف.

- **الماكينات والزنكات (`machines.py`)**:
  `PrintingMachine`, `MachineDimension`, `OffsetMachineType`, `DigitalMachineType`, `OffsetSheetSize`, `DigitalSheetSize`, `PlateSize`.
- **الورق والخامات (`paper.py`)**:
  `PaperType`, `PaperSize`, `PaperWeight` (الجراماج), `PaperOrigin`, `PieceSize`.
- **عمليات ما بعد الطباعة (`finishing.py`)**:
  `CoatingType` (السلوفان، الورنيش، UV), `FinishingType` (التكسير، البصمة، الريجة), `PackagingType`.
- **أوامر التسعير ومحرك التكاليف (`order.py` & `breakdown.py`)**:
  `PrintingOrder`, `PaperSpecification`, `OrderMaterial`, `OrderService`, `CostCalculation`, `OrderSummary`.

---

### 2.9 work_order
**الغرض:** أوامر الشغل وصالة الإنتاج ومراكز التكلفة.

| النموذج | الوصف |
|---------|-------|
| `WorkOrder` | أمر الشغل كمركز تكلفة ومشروع تشغيلي مصغر يربط العميل (`Customer`) بفاتورة المبيعات (`Sale.work_order`) وعرض السعر (`Quotation.work_order`). |

- **الحالات التشغيلية**: `draft` (مسودة), `pending` (قيد الانتظار), `in_progress` (قيد التنفيذ), `completed` (مكتمل), `cancelled` (ملغي).
- **الصلاحيات المخصصة**: `change_workorder_status` (تعديل الحالة الإنتاجية), `cancel_workorder` (إلغاء أمر الشغل).

---

### 2.10 purchase
**الغرض:** المشتريات وسلاسل الإمداد.

| النموذج | الوصف |
|---------|-------|
| `Purchase` / `PurchaseItem` | فواتير وأوامر الشراء من الموردين. |
| `PurchasePayment` | سندات الصرف للموردين وجدولة الدفعات. |
| `PurchaseReturn` | مرتجعات المشتريات وتسوية أرصدة الموردين. |

---

### 2.11 financial
**الغرض:** المحاسبة المزدوجة المركزية ومحرك حوكمة العملات الدولية (IAS 21).

#### أ) النماذج الأساسية
`ChartOfAccounts` (دليل الحسابات الهرمي)، `JournalEntry` و `JournalEntryLine` (القيود اليومية المتوازنة)، `AccountingPeriod` (الفترات المحاسبية)، و `FinancialTransaction`.

#### ب) محرك تقييم العملات المتعددة الدولية IAS 21 (`financial/fx/`)
مبني وفق نمط **Domain-Driven Design (DDD)**:
- **النماذج (`financial/fx/models/`)**:
  - `FXApprovalWorkflow`: دورة الموافقات الرقابية من الإدارة المالية.
  - `FXRevaluationRun`: دورة تقييم فروق أسعار الصرف المرتبطة بنهاية الفترة.
  - `FXRevaluationLine`: البنود التفصيلية للفروق المقيمة بين العملة الوظيفية والأجنبية.
  - `FXRateSnapshot`: لقطات أسعار الصرف التاريخية المعتمدة للتقييم.
- **الخدمات (`financial/fx/services/`)**:
  - `FXCalculationService`: حساب فروق العملة غير المحققة بدقة.
  - `FXPostingService`: ترحيل قيود الأرباح/الخسائر الناتجة عن التقييم عبر `AccountingGateway`.
  - `FXReversalService`: التوليد والترحيل التلقائي لقيود العكس عند إعادة فتح الفترة لحفظ الـ Audit Trail.
  - `FXValidationService`: صمام أمان حراسة عمر سعر الصرف (Rate Age Guard > 7 أيام يتطلب موافقة CFO).

---

### 2.12 hr
**الغرض:** الموارد البشرية والرواتب والبصمة.
- يضم **25+ نموذجاً موزعة على 21 ملفاً** (العقود، الورديات، الحضور، الإجازات، أذونات العمل، السلف، مسيرات الرواتب، أجهزة وسجلات البصمة).
- يضم **34 خدمة بايثون متخصصة** لإدارة دورة حياة الموظف والرواتب والبصمات.

---

### 2.13 presentation
**الغرض:** طبقة العرض والـ DTOs والـ Presenters لفصل منطق العرض عن الـ Views وقواعد البيانات.

- **كائنات نقل البيانات (`presentation/dto/`)**:
  - `dashboard_dto.py`, `customer_dashboard_dto.py`, `executive_dashboard_dto.py`, `product_dashboard_dto.py`, `audit_dto.py`, `document_dto.py`, و `financial_breakdown_dto.py`.
- **طبقة الـ Presenters (`presentation/services/`)**:
  - `customer_dashboard_presenter.py`, `document_financial_presenter.py`, `financial_dashboard_presenter.py`, و `product_dashboard_presenter.py`.

---

### 2.14 api
**الغرض:** واجهات برمجة التطبيقات REST API للتكاملات الخارجية.
- توثيق JWT مؤمن بـ SimpleJWT ومحدد بمعدلات طلب صارمة (Rate Limiting).
- التحقق الصارم من الصلاحيات عبر `RoleBasedModelPermissions`.

---

## 3. طبقة الميدلوير المنقحة للأداء والأمان (11 ميدلوير نشط)

تم تنقية وتحسين خط أنابيب الميدلوير في `corporate_erp/settings.py` ليقتصر على **11 كلاس نشط فقط** لتحقيق استجابة فائقة ومنع الاستهلاك الزائد للذاكرة:

```python
MIDDLEWARE = [
    # Core Django (8 كلاسات أساسية)
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    
    # Essential Custom (3 كلاسات مخصصة للأمان وتتبع المستخدم)
    "core.middleware.current_user.CurrentUserMiddleware",
    "core.middleware.security_headers.AdvancedSecurityHeadersMiddleware",
    "corsheaders.middleware.CorsMiddleware",
]
```

---

## 4. قاعدة البيانات وإدارة الاتصالات

```
التطوير:  SQLite 3 (db.sqlite3 مع timeout=30)
الإنتاج:   MySQL 8.0 (عبر PyMySQL بترميز utf8mb4)
```

**قواعد ضبط الاتصال بالإنتاج:**
- `ATOMIC_REQUESTS = True`: ضمان سلامة المعاملات المالية بحيث يُنفذ كل ريكويست داخل Database Transaction متكاملة.
- `CONN_MAX_AGE = 0`: معيار صارم لمنع أخطاء `Command Out of Sync` الناتجة عن الاتصالات الدائمة على خوادم الاستضافة المشتركة و cPanel.
- `CONN_HEALTH_CHECKS = True`: فحص سلامة الاتصال قبل استخدامه.

---

## 5. المهام الخلفية والمجدولة (Celery Beat)

جدول المهام المجدولة الفعلي في `corporate_erp/celery.py`:

| المهمة | التكرار | الغرض |
|--------|---------|-------|
| `financial.tasks.retry_failed_settlements` | كل 5 دقائق | إعادة محاولة التسويات المالية العالقة |
| `financial.tasks.cleanup_old_audit_logs` | يومياً | تنظيف وتدوير سجلات التدقيق المؤرشفة |
| `financial.tasks.generate_daily_settlement_report` | كل ساعة | توليد ملخص التسويات اليومية |
| `hr.tasks.process_biometric_logs_task` | كل 5 دقائق | سحب ومعالجة حركات البصمات وتحويلها لحضور وانصراف |
| `hr.tasks.cleanup_old_biometric_logs` | أسبوعياً | أرشفة سجلات البصمة القديمة |

---

## 6. مسارات النظام (URL Structure)

```
/                       → core (لوحة التحكم الرئيسية)
/login/ /logout/        → نظام تسجيل الدخول وإدارة الجلسات
/api/                   → REST API الموثق بـ JWT
/admin/                 → لوحة إدارة جانغو
/customers/             → موديول العملاء والحسابات
/sales/                 → موديول المبيعات وعروض الأسعار
/work-orders/           → موديول أوامر الشغل ومراكز التكلفة
/suppliers/             → موديول الموردين والخدمات
/products/              → موديول المخازن والمنتجات والخامات
/printing-pricing/      → موديول تسعير المطبوعات وحساب الهالك
/purchases/             → موديول المشتريات
/financial/             → موديول المالية والحسابات ومحرك IAS 21
/hr/                    → موديول الموارد البشرية والرواتب والبصمة
/governance/            → موديول الحوكمة وسجلات التدقيق
/utils/                 → الأدوات والمكونات المساعدة
```

---

## 7. واجهة المستخدم والتصميم الصارم (UI/UX Standards)

يلتزم النظام بدستور واجهات صارم وفقاً لـ `.agents/AGENTS.md`:
- **ألوان نقية وثابتة**: استخدام متغيرات الـ CSS (`var(--...)`) المعتمدة في `:root` فقط، وحظر التدرجات اللونية (Flat Colors Only - No Gradients).
- **المكونات المشتركة الموحدة**:
  - `shared/page_header.html`: هيدر الصفحة مع مسار التنقل (Breadcrumbs).
  - `components/data_table.html`: جدول البيانات الموحد.
  - `partials/pagination.html`: ترقيم الصفحات الخادمي السريع (SSR Pagination).
  - التنبيهات الموحدة بـ Toastr مع تأخير 3.1 ثانية لإتاحة اكتمال الأنيميشن قبل إعادة التحميل.

---

## 8. العلاقات المعمارية وتدفق العمليات

```
العميل (Customer)
  │
  ├─► عرض السعر (Quotation) ──► طلب التسعير (PrintingOrder)
  │                                    │
  ▼                                    ▼
فاتورة البيع (Sale) ◄────────── أمر الشغل (WorkOrder)
  │                                    │
  ├─► صرف الخامات (StockMovement) ◄───┘
  │
  ▼
بوابة المحاسبة (AccountingGateway)
  │
  ├─► القيد المحاسبي المتوازن (JournalEntry)
  │
  ▼
سجل التدقيق غير القابل للتلاعب (AuditTrail)
```

---

## 9. ملاحظات تقنية وتبرئة الكود

1. **براءة الكود 100% من مخلفات نظام المدارس القديم**:
   تم التحقق الشامل من قاعدة الكود بالكامل، وأُثبت خلو الكود تماماً من أي جداول أو أعمدة أو دوال قديمة تخص المدارس أو الطلاب (`school_item_type`, `students.*`, `student_fees`, `StudentFee`).
2. **عامل الربط للبصمة (Bridge Agent)**:
   خدمة خارجية (`bridge_agent/agent.py`) تعمل كـ Windows Service على شبكة أجهزة البصمة لمزامنة السجلات الحية مع خادم الـ ERP بأمان وسرعة.
3. **بيئة الإنتاج القياسية**:
   النظام مهيأ للتشغيل السلس على خوادم **cPanel / CloudLinux** بواسطة **Phusion Passenger** (`passenger_wsgi.py`)، بالإضافة إلى إمكانية التشغيل على سيرفرات VPS مخصصة بنظام Ubuntu و Nginx و Gunicorn.
