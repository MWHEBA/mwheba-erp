# MWHEBA ERP — Architecture Reference (الدليل المعماري الشامل)

> وثيقة مرجعية للبنية التقنية والمعمارية الفعلية لنظام **MWHEBA ERP**. تعكس الكود وبيئات التشغيل الحقيقية بنسبة 100%.

---

## 📚 الفهرس التوثيقي المتخصص (Specialized Documentation Index)

| المرجع التوثيقي | المسار | الوصف |
|---|---|---|
| 📘 **المحرك المالي والمحاسبي** | [`docs/financial-system.md`](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/docs/financial-system.md) | شجرة الحسابات، محرك تقييم العملات الدولية (FX)، الرقابة على الخزن، وإغلاق الفترات. |
| 🖨️ **تسعير المطبوعات والمونتاج** | [`docs/printing-pricing-system.md`](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/docs/printing-pricing-system.md) | محرك الـ SSOT، حسابات الهالك وتوزيع الأفرخ، أوامر الشغل، وجسر المشتريات. |
| 👥 **الموارد البشرية والرواتب والعهد** | [`docs/hr-system.md`](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/docs/hr-system.md) | الموظفون، العقود، مسيرات الرواتب، عهد الموظفين، وتسجيل الحضور بالبصمة والموبايل. |
| 🔐 **الأدوار والصلاحيات والحوكمة** | [`docs/users-permissions-system.md`](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/docs/users-permissions-system.md) | الـ 10 أدوار القياسية، نطاقات رؤية البيانات، وصلاحيات الخزن والمخازن. |
| 🎨 **نظام الواجهات والتصميم الموحد** | [`docs/frontend-design-system.md`](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/docs/frontend-design-system.md) | معايير التصميم المؤسسي، الـ CSS Tokens، الجداول الموحدة، والـ Modals. |
| 🔌 **واجهات برمجة التطبيقات** | [`docs/api-documentation.md`](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/docs/api-documentation.md) | توثيق الـ REST API و JWT Authentication ونقاط التكامل. |
| ⏱️ **نظام وأجهزة البصمة** | [`docs/biometric-system.md`](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/docs/biometric-system.md) | إدارة أجهزة ZKTeco وعامل المزامنة الخارجي (Bridge Agent). |
| 🚀 **دليل تشغيل الإنتاج والـ DevOps** | [`DEPLOYMENT_GUIDE.md`](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/DEPLOYMENT_GUIDE.md) | خطوات النشر على خوادم cPanel و Passenger وضبط بيئات العمل. |
| 🧪 **خطة الاختبارات والجودة** | [`TESTING_MASTER_PLAN.md`](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/TESTING_MASTER_PLAN.md) | معايير اختبارات pytest ومستويات التغطية المعتمدة. |
| 📖 **قاموس المصطلحات الموحد** | [`docs/glossary.md`](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/docs/glossary.md) | المصطلحات المالية، الطباعية، المخزنية، والأمنية المعتمدة في النظام. |

---

## 1. نظرة عامة (Overview)

نظام **MWHEBA ERP** هو منصة مؤسسية متكاملة متعددة الأنشطة مبنية على **Django 5.2 LTS**، مصممة لإدارة العمليات الصناعية والتجارية والمالية المتشابكة — من مطابع الأوفست والديجيتال الكبرى، إلى وكالات الدعاية وشركات التوزيع والتجارة.

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
├── purchase/           ← المشتريات: أوامر الشراء، فواتير الموردين، وجسر مشتريات أوامر الطباعة
├── financial/          ← المحاسبة المالية المزدوجة ومحرك تقييم العملات الدولية (Multi-Currency FX Engine)
├── hr/                 ← إدارة الموارد البشرية، الرواتب، العهد النقدية، سجلات وأجهزة البصمة، والإجازات
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

---

### 2.2 users
**الغرض:** إدارة الهوية وصلاحيات الوصول المؤسسية (NIST Enterprise RBAC Level 2).

- نموذج `User` مخصص يرث من `AbstractUser`، مع استئصال كامل وتام لأي حقول قديمة مثل `user_type`.
- **منظومة الـ 10 أدوار القياسية**: `admin`, `financial_manager`, `accountant`, `sales_manager`, `sales_rep`, `procurement_officer`, `inventory_manager`, `production_supervisor`, `hr_officer`, `viewer`.
- **`RolePermissionBackend`**: محرك مصادقة وفحص صلاحيات فائق السرعة $O(1)$ مع كاش لحظي على مستوى الطلب (`_cached_group_permissions`).
- **نطاقات رؤية البيانات (Data Visibility Scopes):** الشامل، الفرع والمخزن، أو السجلات الخاصة فقط.

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

### 2.4 customer & sale
**الغرض:** إدارة العملاء، عروض الأسعار، خط أنابيب المبيعات، والتحصيلات.
- دورة المبيعات: `Quotation` ──► `Sale` ──► `SalePayment` ──► `SaleReturn`.
- دعم قوائم الأسعار المتعددة وسياسات الخصم الآلي (`PriceList`).
- عزل سجلات مناديب المبيعات حسب الصلاحيات.

---

### 2.5 printing_pricing & work_order
**الغرض:** محرك تسعير المطبوعات SSOT وحسابات المونتاج وأوامر الشغل.
- خوارزميات المونتاج وحساب الهالك ومقاسات الأفرخ (`PricingCalculationEngine`).
- تحويل عروض الأسعار إلى أوامر شغل ومراكز تكلفة (`WorkOrder`).
- جسر المشتريات الآلي (`ProcurementBridgeService`) لتوليد طلبات شراء الخامات والخدمات الصناعية.

---

### 2.6 financial
**الغرض:** المحاسبة المزدوجة ومحرك تقييم العملات الدولية وإغلاق الفترات.
- شجرة الحسابات الهرمية (5 مستويات) وقيود اليومية المتزنة.
- محرك تقييم العملات الأجنبية المعتمد على DDD (`financial/fx/`) مع حراسة عمر سعر الصرف (Rate Age Guard).
- منظومة رقابة وصلاحيات الخزن النقدية (`TreasurySecurityService`).
- منظومة إدارة وتسوية عهد الموظفين النقدية (`CustodyService`).
- معالجة فروق السنتات والتقريب ($\le 0.05$) آلياً.

---

### 2.7 hr
**الغرض:** الموارد البشرية، الرواتب الذكية، أجهزة البصمة، وتسجيل الحضور.
- مسيرات الرواتب المتكاملة مع الحسابات (`IntegratedPayrollService`).
- المزامنة الحية مع أجهزة البصمة (ZKTeco) وتطبيق الحضور بالموبايل والموقع الجغرافي (`GeofencingService`).
- إدارة السلف والبدلات والجزاءات والإجازات السنوية.

---

## 3. طبقة الميدلوير المنقحة (11 ميدلوير نشط)

تم تنقية وتحسين خط أنابيب الميدلوير في `corporate_erp/settings.py` ليقتصر على **11 كلاس نشط فقط**:

```python
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.current_user.CurrentUserMiddleware",
    "core.middleware.security_headers.AdvancedSecurityHeadersMiddleware",
    "corsheaders.middleware.CorsMiddleware",
]
```

---

## 4. العلاقات المعمارية وتدفق العمليات

```
العميل (Customer)
  │
  ├─► عرض السعر (Quotation) ──► طلب التسعير (PrintingOrder)
  │                                    │
  ▼                                    ▼
فاتورة البيع (Sale) ◄────────── أمر الشغل (WorkOrder)
  │                                    │
  ├─► صرف الخامات (StockMovement) ◄───┤
  │                                    ▼
  │                             جسر المشتريات (ProcurementBridge)
  │                                    │
  ▼                                    ▼
بوابة المحاسبة (AccountingGateway) ◄── أوامر شراء الخامات (PurchaseOrder)
  │
  ├─► القيد المحاسبي المتوازن (JournalEntry)
  │
  ▼
سجل التدقيق غير القابل للتلاعب (AuditTrail)
```
