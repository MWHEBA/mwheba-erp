# وثيقة الخطة الشاملة المتكاملة لنظام الصلاحيات والحوكمة (MWHEBA ERP Master RBAC & Security Plan - النسخة النصية المحكمة v7)

المرجع المعماري والتنفيذي النهائي لإصلاح، توحيد، وإحكام نظام الصلاحيات والحوكمة في **MWHEBA ERP**، متوافقاً مع معايير (NIST Enterprise RBAC Level 2 + Object-Level Security + Permission-Driven Business Logic + Workflow State Guards)، ومصمماً بالكامل بنصوص مهيكلة، تحليلية ومفصلة بدون أي رسوم بيانية أو صور، ومحكماً ضد كافة الثغرات والعيوب الهندسية التي نوقشت بنقد صارم مع الحفاظ التام على 100% من المحتوى والتفاصيل الفنية لمطبعة وهبة.

---

## 1. الركائز الهندسية الأساسية للمعمارية الشاملة (The Core Architectural Pillars)

تتأسس المعمارية الأمنية لنظام الصلاحيات في **MWHEBA ERP** على ست ركائز هندسية متكاملة (Pillars)، تم تحويلها بالكامل من المخطط الصوري إلى صياغة نصية تحليلية دقيقة ومحكمة، تضمن تغطية كل مكون ومسؤولياته وآليات عمله:

### الركيزة الأولى: التطهير واستئصال الأكواد الميتة (Purge & Dead Code Elimination Pillar)
* **الهدف الجوهري**: تنظيف قاعدة الكود وقاعدة البيانات من كافة التشوهات والترقيعات القديمة والأكواد الوهمية التي تخلق ثغرات أمنية وتعيق الفحص المعياري.
* **المكونات والآليات الهندسية للركيزة**:
  1. **الاستئصال الجذري لكائن `qrapplication` وتوابعه**:
     - إزالة نموذج وتوابع `QRApplication` بالكامل من نماذج المستخدمين (`Role`), ودوال التحقق (`decorators.py`), ومحرك الصلاحيات (`permission_service.py`), وخدمات الحوكمة المحاسبية (`governance/services/repair_execution_service.py`, `source_linkage_service.py`, `accounting_gateway.py`).
     - تنظيف قاعدة البيانات بحذف أي جداول أو قيود مرتبطة في `auth_permission` و `django_content_type`.
  2. **إنهاء اختطاف الكلاسات (Class Hijacking Elimination)**:
     - إزالة الكود الملتوي في [printing_pricing/views/settings_views.py:25](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/printing_pricing/views/settings_views.py#L25) الذي ورث كلاس `LoginRequiredMixin` من `StaffRequiredMixin` محلياً، واستبداله بصلاحية معيارية صريحة `printing_pricing.manage_pricing_settings`.
  3. **تطهير فحص `is_staff` العشوائي**:
     - إزالة فحص `request.user.is_staff` في [printing_pricing/views/order_views.py:42](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/printing_pricing/views/order_views.py#L42) واستبداله بصلاحية عزل معيارية `printing_pricing.view_all_orders`.
  4. **تنظيف الشروط الدفاعية المكررة عبثياً**:
     - التخلص من سلاسل الشروط المكررة مثل `if not is_admin and not is_superuser and not has_perm` والاعتماد حصراً على سلوك جانغو القياسي حيث يمتلك `superuser` كافة الصلاحيات تلقائياً، وتمرير الفحص عبر الـ Backend الموحد.
  5. **الفصل الاصطلاحي في الموارد البشرية**:
     - الفصل التام في المسميات والواجهات بين أذونات العمل والانصراف الخاصة بالموظفين (`PermissionRequest`) وصلاحيات النظام المؤسسي (`Permission`).

---

### الركيزة الثانية: النواة والأداء الفائق وإدارة الهوية (Core Performance, Caching & Identity Pillar)
* **الهدف الجوهري**: توفير استجابة لحظية $O(1)$ لعمليات فحص الصلاحيات داخل الذاكرة بصفر استعلامات SQL متكررة، مع الحفاظ المطلق على المستخدمين القائمين واستمرارية التشغيل، وسد ثغرات تجريد التطبيقات وتناقض البيانات.
* **المكونات والآليات الهندسية للركيزة**:
  1. **محرك `RolePermissionBackend` المطور والمحكم**:
     - القضاء على ثغرة تجريد التطبيقات (`app_label stripping`): إيقاف سطر `codename = perm.split('.')[-1]` واعتماد المطابقة الصارمة على مستوى `(content_type__app_label, codename)` لمنع تسريب الصلاحيات المتشابهة في الأسماء بين التطبيقات (مثل `sale.view_order` و `printing_pricing.view_order`).
     - طبقة توافق عكسي ذكية (Bidirectional Compatibility Map): تضمن ترجمة الصلاحيات الـ 42 العربية القديمة إلى الصلاحيات القياسية الجديدة تلقائياً، لمنع انكسار أي دور من الأدوار الـ 7 القائمة أثناء مرحلة الترقية.
     - استيفاء عقد جانغو الكامل للباك إند: تطبيق دوال `get_all_permissions(user_obj, obj=None)` و `get_group_permissions(user_obj, obj=None)` لترجع `set[str]` بصيغة `'app_label.codename'`.
  2. **تصحيح عقد نموذج `User.get_all_permissions()`**:
     - تعديل دالة `User.get_all_permissions()` في [users/models.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/users/models.py) لترجع مجموعة نصوص قياسية `set[str]` متوافقة 100% مع جانغو و DRF وقوالب العرض، مع إضافة دالة مساعدة منفصلة `get_all_permission_objects()` لمن يحتاج كائنات الموديل.
  3. **معمارية الكاش متعددة الطبقات (Two-Tier Caching Architecture)**:
     - **الطبقة الأولى (Tier 1)**: كاش الذاكرة اللحظي على مستوى الـ Request (`request._perm_cache`)، فائق السرعة $O(1)$، خيطي آمن (Thread-Safe)، ويضمن صفر استعلامات SQL وصفر اعتماديات شبكية أثناء معالجة الطلب الواحد.
     - **الطبقة الثانية (Tier 2)**: محرك `PermissionCacheService` مع معالجة مرنة للعمل على `LocMemCache` (في بيئة التطوير) و Redis (في بيئة الإنتاج)، مع ربطه بإشارات جانغو للتطهير الفوري (Smart Invalidation) عند تعديل أي دور أو مستخدم.
  4. **الفصل التام لـ `user_type` عن منطق الصلاحيات وتطهير التناقضات**:
     - إقرار قاعدة صارمة: حقل `user_type` هو مسمى وظيفي وتنظيمي فقط؛ ويُحظر تماماً استخدامه في أي فحص تصريح داخل كود البايثون.
     - مزامنة وتصحيح بيانات حساب `mwheba` القائم ليتطابق نوع حسابه مع دوره الإداري (`admin`) ورفع القيود المتناقضة عنه.
  5. **جسر ترحيل البيانات التلقائي (Data Migration Bridge)**:
     - إنشاء وتشغيل سكريبت ترحيل آمن يضمن ترقية وضمان حقوق الأدوار السبعة النشطة حالياً في الداتابيز (`admin`, `sales_rep`, `inventory_manager`, `accountant`, `financial_manager`, `viewer`, `general_coordinator`) ومستخدمي النظام الحاليين دون أي انقطاع للخدمة.
  6. **أداة انتحال الهوية الآمنة والمراقبة (Login As User / Impersonation)**:
     - تمكين الإدارة وفريق الجودة من تسجيل الدخول بهوية أي موظف لمعاينة واختبار تجربة الاستخدام وصلاحيات الشاشات ميدانياً، مع تسجيل كامل لجميع الحركات في سجل التدقيق الأمني (Audit Log).

---

### الركيزة الثالثة: تأمين الـ REST API وعزل الملكية (API Zero-Trust & Object-Level Ownership Pillar)
* **الهدف الجوهري**: سد الأبواب الخلفية عبر واجهات البرمجة وفرض عزل البيانات الصارم بين الموظفين وفق مبدأ الصلاحيات الأدنى (Least Privilege).
* **المكونات والآليات الهندسية للركيزة**:
  1. **كلاس الأذونات المؤسسي الموحد `RoleBasedModelPermissions`**:
     - استبدال كلاسات DRF الهشة وسد ثغرة `SAFE_METHODS` التي كانت تمنح أي مستخدم مسجل إمكانية قراءة القيود المحاسبية وشجرة الحسابات، وفرض فحص الصلاحيات على عمليات القراءة (GET) وعمليات الكتابة (POST/PUT/DELETE) على حد سواء.
  2. **توحيد المسميات القياسية بين الـ Web والـ API**:
     - مطابقة مسميات الصلاحيات بين واجهات الويب وواجهات الـ API (مثل توحيد صلاحية اعتماد الإجازات إلى `hr.approve_leave` بدلاً من الازدواج القديم مع `can_approve_leaves`).
  3. **عزل ملكية البيانات بين المناديب (Object-Level Ownership)**:
     - عزل سجلات فواتير المبيعات، عروض الأسعار، وطلبات التسعير بحيث لا يرى مندوب المبيعات إلا السجلات التي أنشأها بنفسه (`created_by == request.user`)، مع منح المشرفين والإدارة صلاحية الرؤية الشاملة عبر `sale.view_all_sales` و `printing_pricing.view_all_orders`.

---

### الركيزة الرابعة: حوكمة بيزنس المطبعة وصالة الإنتاج (Printing Press & Production Governance Pillar)
* **الهدف الجوهري**: حماية أسرار التسعير وهوامش الأرباح في صناعة الطباعة والتغليف، وفصل مهام صالة التشغيل عن التعاملات التجارية لمنع هدر الخامات وتطهير شاشات الإنتاج من الأرقام المالية.
* **المكونات والآليات الهندسية للركيزة**:
  1. **حماية تكاليف وهوامش التسعير (`printing_pricing`)**:
     - حجب تفاصيل تكاليف خام الورق، أسعار الزنكات، وتكاليف الماكينات، وهوامش الربح الصافية عن شاشات مناديب المبيعات وحصرها على الإدارة والمدير المالي عبر صلاحيتي `printing_pricing.view_profit_margins` و `printing_pricing.view_cost_breakdown`.
  2. **تمكين إدارة مدخلات التسعير بصلاحية صريحة**:
     - إتاحة إدارة جداول الورق ومقاسات الأفرخ وسعة الرزم وحاسبة التحويلات الفنية في صالة الإنتاج (`pricing_sheet_printing.js`) لمسؤولي التسعير بصلاحية معيارية `printing_pricing.manage_pricing_settings` دون اشتراط منحهم صلاحية مدير نظام (`is_staff`).
  3. **استقلالية صالة الإنتاج وتطهير قوالب التشغيل (`work_order`)**:
     - فك الارتباط بين أوامر الشغل وعروض الأسعار، ومنح فنيي المونتاج والطباعة صلاحيات إنتاجية مستقلة `work_order.view_workorder`.
     - تنقية قوالب صالة الإنتاج والطباعة (`work_order_detail.html` و `work_order_print.html`) من أي أرقام مالية، أسعار خامات، أو هوامش أرباح، وقصر إظهار الأرقام المالية على حاملي صلاحيات الإدارة المالية فقط.
  4. **حراسة مسار الإنتاج (Workflow State Guards)**:
     - القفل البرمجي التلقائي لإمكانية التعديل على الفواتير، عروض الأسعار، وأوامر الشغل بمجرد انتقالها لحالة "قيد التشغيل" أو "مكتمل" في الماكينات لمنع هدر الخامات الورقية وتطابق التكاليف المحسوبة مع التشغيل الفعلي.

---

### الركيزة الخامسة: الحوكمة المالية والتداول النقدي (Financial Governance & Cash Authority Pillar)
* **الهدف الجوهري**: حماية الخزائن والحسابات والامتثال لمعايير المحاسبة الدولية (IAS 21) ومنع أي تلاعب نقدي أو محاسبي.
* **المكونات والآليات الهندسية للركيزة**:
  1. **سلطة طبقة الخدمات المؤتمتة (Service-Layer Authority)**:
     - تمكين مندوب المبيعات من تسجيل المقبوضات النقدية والعربون المصاحب للفاتورة مباشرة من شاشة البيع دون منحه صلاحية الاطلاع المباشر على الخزن أو شجرة الحسابات، بحيث تنفذ القيود عبر طبقة الخدمات المصرح لها فقط تلقائياً.
  2. **حوكمة معيار المحاسبة الدولي IAS 21 لإعادة تقييم العملات**:
     - قصر تشغيل وإلغاء عمليات إعادة تقييم العملات الأجنبية (`financial.run_fx_revaluation`) واعتماد أسعار الصرف التاريخية المنتهية على المدير المالي حصراً (`financial.approve_fx_override`).
  3. **تأمين شاشات الخزن وحسابات النقدية**:
     - استبدال الصلاحية اليتيمة في `account_views.py` بصلاحية معيارية تابعة للموديول المالي `financial.view_cash_accounts`.

---

### الركيزة السادسة: الإلزام الرقابي والتحكم الصارم بالواجهات (Strict Enforcement & UI Matrix Pillar)
* **الهدف الجوهري**: إحكام السيطرة التامة على كافة نقاط النهاية في النظام عبر السلسلة التجارية الكاملة وتوفير واجهة إدارة رصينة وخالية من التناقضات.
* **المكونات والآليات الهندسية للركيزة**:
  1. **الحماية السيرفرية الشاملة للأسعار عبر كامل السلسلة التجارية (Pipeline-Wide Price Protection)**:
     - سد ثغرة التعديل عبر المتصفح (Inspect Element أو Raw POST): فرض فحص صلاحية `sale.change_unit_price` في السيرفر عبر الثلاث شاشات متسلسلة:
       *(عروض الأسعار `Quotation` $\leftarrow$ أوامر البيع `SalesOrder` $\leftarrow$ فواتير البيع `Sale`)*.
     - منع تثبيت أي سعر مخالف للسعر الرسمي إلا لمن يحمل الصلاحية الصريحة.
  2. **إحلال الصلاحيات مكان `user_type` بالكامل**:
     - إلغاء فحص `user.user_type == 'sales_rep'` من السيرفر والقوالب نهائياً.
  3. **حماية حقول المندوب والعمولات**:
     - قصر إمكانية تغيير مسؤول المبيعات في الفواتير على المشرفين عبر صلاحية `sale.change_sale_salesman`.
  4. **تأمين إشعارات الـ Context Processors**:
     - حماية استعلامات شارة طلبات الاعتماد `EnterpriseApprovalRequest` بصلاحية معيارية `financial.approve_workflow` لمنع تسريب بيانات الاعتمادات بصفر كويريز إضافية.
  5. **تأمين شامل لجميع الـ Views (Zero-Trust Policy)**:
     - تغطية كافة شاشات وعمليات المبيعات، المشتريات، العملاء، الموردين، المالية، والمخازن بديكوريتورز ومكسنز صارمة.
  6. **واجهة إدارة الصلاحيات المجمعة الذكية (Grouped Matrix UI)**:
     - تجميع الصلاحيات حسب الموديول مع ميزة التحديد التلقائي للاعتماديات المترابطة (Auto-Select Prerequisites) لضمان عدم منح صلاحية فرعية دون صلاحية العرض الأساسية.

---

### مسار التدفق الهيكلي والربط البيني بين الركائز (Inter-Pillar Architectural Dataflow)
يوضح هذا المسار النصي كيفية تتابع العمليات وتبادل البيانات بين الركائز الست لضمان التكامل الأمني المحكم:
1. **نقطة الانطلاق (التطهير والنواة)**:
   - تبدأ المنظومة بتطهير الشوائب والأكواد الميتة عبر **الركيزة الأولى (Purge)**، لتبني فوقها **الركيزة الثانية (Core)** نواة فحص سريعة بكاش الذاكرة اللحظي $O(1)$ مع تثبيت جسر ترقية الأدوار الحالية وتأمين ميزة انتحال الهوية.
2. **بناء الحصانة والملكية (الـ API وعزل السجلات)**:
   - تتسلم **الركيزة الثالثة (API Security)** قواعد التحقق من النواة وتغلق منافذ الـ API الخارجية وتفرض عزل السجلات وفق ملكية كل مندوب (`created_by`).
3. **تطبيق قواعد البيزنس التخصصية (المطبعة والمالية)**:
   - ترتكز عمليات التسعير وصالة التشغيل في **الركيزة الرابعة (Printing Governance)** على عزل التكاليف وتفعيل أقفال مسار الإنتاج لمنع هدر الخامات أثناء دوران الماكينات.
   - وتتكامل معها **الركيزة الخامسة (Financial Governance)** لإتمام العمليات النقدية عبر طبقة الخدمات التلقائية وقصر حوكمة العملات وإعادة التقييم على المدير المالي.
4. **فرض الرقابة وضبط الواجهات (الإلزام التام ومصفوفة التحكم)**:
   - تتوج **الركيزة السادسة (Enforcement & UI)** المعمارية بفرض الرقابة الصارمة على كل زر ومدخل وفورم عبر صلاحيات صريحة، وتقديم واجهة ضبط مجمعة ذكية تدير كافة الركائز السابقة بسلاسة وأمان.

---

## 2. تفاصيل حزم العمل التنفيذية (Detailed Implementation Packages)

---

### الحزمة 1: الاستئصال الجذري لـ `qrapplication` وتطهير الأكواد الميتة

* **إزالة تامة وشاملة لكافة مراجع `qrapplication` و `qr_applications`**:
  1. [users/models.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/users/models.py):
     - حذف التوابع الميتة في نموذج `Role`:
       `can_access_applications` و `can_manage_applications`.
     - تنظيف الـ Docstrings والتعليقات في `has_role_permission`.
  2. [users/decorators.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/users/decorators.py):
     - حذف الديكوريتورز المكسورة: `require_reception_or_admin` و `require_applications_permission`.
  3. [users/services/permission_service.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/users/services/permission_service.py):
     - إزالة الأكواد الميتة: `'add_qrapplication'`, `'change_qrapplication'`, `'view_qrapplication'`, `'can_convert_application'`, `'view_qrcode'`.
  4. [scripts/update_dynamic_roles.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/scripts/update_dynamic_roles.py):
     - إزالة أسطر التحقق من `view_qrapplication`.
  5. [governance/services/](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/governance/services/):
     - تنظيف ملفات `repair_execution_service.py`، `source_linkage_service.py`، و `accounting_gateway.py` من مراجع `qr_applications.QRApplication`.
  6. **تنظيف قاعدة البيانات**: حذف أي سجلات في جدول `auth_permission` أو `django_content_type` تحمل اسم `qrapplication`.

---

### الحزمة 2: تطهير كود اختطاف الكلاسات في إعدادات التسعير وتوحيد الـ Web & API

#### 1. تطهير كود اختطاف الكلاسات في [printing_pricing/views/settings_views.py:25](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/printing_pricing/views/settings_views.py#L25):
* حذف كود:
  ```python
  # حذف الترقيع القديم
  class LoginRequiredMixin(StaffRequiredMixin):
      pass
  ```
* استبداله بنظام الصلاحيات المعياري `PermissionRequiredMixin` مربوطاً بصلاحية:
  `printing_pricing.manage_pricing_settings`
  (لإدارة مقاسات أفرخ الورق، مقاسات الزنكات، خامات السلوفان والبصمة، وتكلفة تشغيل الماكينات بالساعة).
* يتيح هذا لمسؤولي التسعير والمونتاج ضبط أسعار الخامات دون اشتراط إعطائهم `is_staff`، ويمنع موظفي الـ IT من العبث بأسعار الخامات وتكاليف الماكينات.

#### 2. تصحيح تصفية طلبات التسعير في [printing_pricing/views/order_views.py:42](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/printing_pricing/views/order_views.py#L42):
* استبدال:
  ```python
  # القديم المعتمد على is_staff
  if not (self.request.user.is_superuser or self.request.user.is_staff):
      queryset = queryset.filter(created_by=self.request.user)
      
  # الجديد المعياري المعتمد على الصلاحيات
  if not (self.request.user.is_superuser or self.request.user.has_perm('printing_pricing.view_all_orders')):
      queryset = queryset.filter(created_by=self.request.user)
  ```

#### 3. توحيد مسميات الصلاحيات بين الـ Web والـ API:
* توحيد صلاحية اعتماد الإجازات لتكون بصيغة واحدة قياسية: `hr.approve_leave`:
  - في شاشات الويب: [hr/views/leave_bulk_operations.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/hr/views/leave_bulk_operations.py).
  - في الـ API: [hr/permissions.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/hr/permissions.py) (استبدال `can_approve_leaves` بـ `approve_leave`).
* تدقيق ومطابقة كافة صلاحيات الـ HR الأخرى (`view_employee`, `change_employee`, `can_process_payroll`).

#### 4. تطهير الشروط الدفاعية المكررة:
* استبدال السطر المتكرر عبثياً:
  ```python
  # القديم المكرر
  if not request.user.is_admin and not request.user.is_superuser and not request.user.has_perm('...'):
  
  # المعياري النظيف
  if not request.user.has_perm('...'):
  ```
* الاعتماد الكامل على سلوك جانغو المعياري: `has_perm()` يرجع `True` تلقائياً لأي `superuser`، ودور `admin` يمتلك الصلاحيات كاملة في الكاش.

#### 5. الفصل الاصطلاحي في الموارد البشرية:
* توثيق وتمييز صريح في الواجهات بين:
  - **أذونات العمل والانصراف (Work Permits / Attendance Permissions)**: نموذج `PermissionRequest`.
  - **صلاحيات النظام المؤسسي (System RBAC Permissions)**: نموذج `Permission` و `Role`.

---

### الحزمة 3: الأساس التقني، كاش الأداء الفائق، وتأمين انتحال الهوية

#### 1. تعريف صلاحيات البيزنس الحقيقية في `Meta.permissions`:
* [sale/models.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/sale/models.py):
  - `Sale`:
    - `approve_sale`: اعتماد فاتورة المبيعات.
    - `change_unit_price`: تعديل أسعار البيع في الفاتورة.
    - `apply_special_discount`: تطبيق خصم إضافي/استثنائي.
    - `cancel_approved_sale`: إلغاء فاتورة مبيعات معتمدة.
    - `print_sale_invoice`: طباعة فاتورة المبيعات.
    - `view_all_sales`: الاطلاع على فواتير كافة المناديب (خاص بالمشرفين).
  - `Quotation`:
    - `convert_to_order`: تحويل عرض السعر إلى أمر بيع.
    - `change_quotation_price`: تعديل أسعار عروض الأسعار.
    - `view_all_quotations`: الاطلاع على عروض أسعار كافة المناديب.
  - `SalesOrder`:
    - `approve_sales_order`: اعتماد أمر البيع.
    - `change_sales_order_price`: تعديل أسعار أوامر البيع.
    - `view_all_salesorders`: الاطلاع على أوامر بيع كافة المناديب.
* [purchase/models.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/purchase/models.py):
  - `Purchase`:
    - `approve_purchase`: اعتماد فاتورة المشتريات.
    - `change_unit_cost`: تعديل تكلفة الشراء المحددة.
    - `cancel_approved_purchase`: إلغاء فاتورة مشتريات معتمدة.
* [financial/models.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/financial/models.py):
  - `JournalEntry`:
    - `post_journal_entry`: ترحيل/اعتماد القيود المحاسبية.
    - `reverse_journal_entry`: عكس قيد محاسبي معتمد.
  - `AccountingPeriod`:
    - `close_accounting_period`: إغلاق الفترة المحاسبية.
    - `reopen_accounting_period`: إعادة فتح فترة محاسبية مغلقة.
    - `run_fx_revaluation`: تشغيل إعادة تقييم فروق العملات IAS 21 (خاص بالمدير المالي).
* [product/models.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/product/models.py):
  - `InventoryAdjustment`:
    - `approve_inventory_adjustment`: اعتماد تسوية فروق الجرد المخزني.
* [printing_pricing/models.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/printing_pricing/models.py):
  - `PricingOrder`:
    - `view_cost_breakdown`: عرض تفاصيل تكلفة الخامات (الورق، الزنكات، السلوفان، البصمة).
    - `view_profit_margins`: عرض هوامش الربح الصافي للطلبات.
    - `view_all_orders`: عرض طلبات تسعير كافة المناديب للمشرف.
    - `override_pricing_rules`: تجاوز معادلات التسعير التلقائية.
  - نماذج إعدادات التسعير (PaperSpecification, PlateSize, CoatingType, MachineRate):
    - `manage_pricing_settings`: إدارة مقاسات وتكاليف الخامات والماكينات.
* [work_order/models.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/work_order/models.py):
  - `WorkOrder`:
    - `view_workorder`: عرض أمر الشغل ومواصفات الإنتاج الفنية.
    - `change_workorder_status`: تحديث مراحل التشغيل في صالة الإنتاج.
    - `cancel_workorder`: إلغاء أمر شغل صادر.

#### 2. تطوير وتأمين [users/backends.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/users/backends.py) ومحرك الصلاحيات:
* **إلغاء ثغرة تجريد التطبيقات (`app_label stripping`)**:
  - استبدال سطر `codename = perm.split('.')[-1]` بفحص صارم يطابق التطبيق والكود نيم معاً: `content_type__app_label=app_label, codename=codename`.
* **بناء طبقة التوافق العكسي الثنائية (Bidirectional Compatibility Map)**:
  - إضافة قاموس توافق ذكي داخل الـ Backend يترجم أوتوماتيكياً بين الصلاحيات الـ 42 العربية القديمة (مثل `users.ادارة_المبيعات`) والصلاحيات المعيارية الجديدة (`sale.view_sale`, `sale.add_sale`, `sale.change_sale`).
  - يضمن هذا عدم انكسار أي دور من الأدوار الـ 7 القائمة حتى قبل اكتمال تعديل كافة القوالب.
* **استيفاء عقد دوال جانغو القياسية للـ Backend**:
  - إضافة دالة `get_all_permissions(user_obj, obj=None)` ترجع `set[str]` بصيغة `'app_label.codename'`.
  - إضافة دالة `get_group_permissions(user_obj, obj=None)` لترجع صلاحيات الدور والجروبات كنصوص.

#### 3. تصحيح عقد [users/models.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/users/models.py) في `User.get_all_permissions()`:
* تعديل دالة `get_all_permissions(self, obj=None)` لترجع `set[str]` بدلاً من كائنات الموديل `Permission` ليتوافق 100% مع جانغو و DRF وقوالب العرض.
* إضافة دالة مساعدة منفصلة: `get_all_permission_objects(self)` للأماكن التي تحتاج كائنات الموديل الفعلية.
* إقرار الفصل التام لـ `user_type`: يُمنع استخدام `user_type` في أي شروط تصريح أو أمان برمجية، ويظل حقل دلالي وظيفي فقط.

#### 4. معمارية الكاش ثنائية الطبقات وإيقاظ [permission_cache.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/users/services/permission_cache.py):
* **الطبقة الأولى (Tier 1 - Request Memory)**:
  - تخزين الصلاحيات داخل `request._perm_cache` فور أول فحص كـ `set[str]` لضمان زمن استجابة ميكروثانية $O(1)$ وصفر كويريز وصفر اعتماديات شبكية أثناء الـ Request.
* **الطبقة الثانية (Tier 2 - Process & Distributed Cache)**:
  - ربط الـ Backend مع `PermissionCacheService` مع معالجة ذكية للعمل السلس على `LocMemCache` محلياً و Redis على الإنتاج.
  - تفعيل التطهير اللحظي (Smart Cache Invalidation) عبر إشارات جانغو (`post_save`, `m2m_changed`, `post_delete`) على نماذج `Role`, `User`, و `Permission`.

#### 5. جسر ترحيل الأدوار القائمة وتطهير التناقضات (Data Migration Bridge):
* إنشاء وتشغيل الأمر النظامي [users/management/commands/migrate_legacy_roles.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/users/management/commands/migrate_legacy_roles.py):
  - قراءة الأدوار الـ 7 القائمة في قاعدة البيانات (`admin`, `accountant`, `sales_rep`, `inventory_manager`, `financial_manager`, `viewer`, `general_coordinator`).
  - ترقية صلاحياتها تلقائياً إلى صلاحيات الموديلز المعيارية الجديدة.
  - **مزامنة بيانات المستخدمين النشطين**: فحص وتصحيح التناقضات في حساب `mwheba` ليتطابق دوره الإداري (`admin`) مع نوع حسابه ورفع أي قيود سعرية متناقضة عنه.
  - الحفاظ التام على المستخدمين الحاليين وضمان استمرار عملهم فوراً دون انقطاع.

#### 6. تأمين وتوافق ميزة "تسجيل الدخول كمستخدم آخر" (Login As User):
* في [users/views.py:452](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/users/views.py#L452):
  - التأكد من أن تسجيل الدخول كمستخدم آخر يحمّل الصلاحيات الفعلية للدور المستهدف عبر `RolePermissionBackend`.
  - تمكين الـ Superuser من اختبار ومحاكاة صلاحيات أي موظف ميدانياً للتأكد من انضباط الشاشات.

---

### الحزمة 4: تأمين الـ REST API وعزل ملكية البيانات بين المناديب (API & Object-Level Security)

#### 1. إغلاق ثغرة الـ API المفتوحة في [api/permissions.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/api/permissions.py):
* إلغاء الثغرة الحالية في `IsManagerOrReadOnly` التي تتيح لأي مستخدم مسجل قراءة القيود وشجرة الحسابات عبر `SAFE_METHODS`.
* إنشاء كلاس أذونات معيارية: `RoleBasedModelPermissions` يرث من `DjangoModelPermissions` ويدعم:
  - فحص الصلاحيات المعيارية عبر كاش الباك إند (`user.has_perm`).
  - حماية مسارات القراءة (GET) لتتطلب صراحة `view_<model>` (مثلاً `financial.view_journalentry` لقراءة القيود).
  - حماية مسارات التعديل والحذف والإضافة.

#### 2. تحديث [api/viewsets.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/api/viewsets.py):
* تطبيق `RoleBasedModelPermissions` على جميع الـ ViewSets:
  - `JournalEntryViewSet`, `ChartOfAccountsViewSet`: مقفولة تماماً ولا تفتح إلا للمحاسبين والمدير المالي.
  - `ProductViewSet`, `StockViewSet`, `WarehouseViewSet`: تتبع صلاحيات المخازن والمنتجات.
  - `PurchaseViewSet`, `SupplierViewSet`: تتبع صلاحيات المشتريات.

#### 3. عزل ملكية البيانات بين مناديب المبيعات (Object-Level Ownership):
* في شاشات وفلاتر عروض الأسعار وفواتير المبيعات وطلبات التسعير:
  - **المندوب العادي**: الـ QuerySet يُصفى تلقائياً ليظهر فقط: `Q(created_by=request.user) | Q(sales_rep=request.user)`.
  - **مشرف المبيعات / المدير**: إذا كان يملك `sale.view_all_sales` أو `sale.view_all_quotations` أو `printing_pricing.view_all_orders`، يُعرض له كافة فواتير وعروض أسعار جميع المناديب.
  - يمنع هذا تضارب المصالح واطلاع أي مندوب على أسعار وعملاء زميله.

---

### الحزمة 5: حوكمة تسعير المطبوعات وصالة الإنتاج (Printing Press Governance)

#### 1. حماية هوامش الأرباح وأسرار تكاليف الخامات (`printing_pricing`):
* فحص وحماية الشاشات والـ Partial Views:
  - [templates/printing_pricing/orders/partials/summary_sidebar.html](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/templates/printing_pricing/orders/partials/summary_sidebar.html)
  - [templates/printing_pricing/orders/order_detail.html](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/templates/printing_pricing/orders/order_detail.html)
* قصر تفاصيل تكلفة الورق الخام والزنكات وهامش الربح الصافي على من يملك:
  `perms.printing_pricing.view_profit_margins` أو `perms.printing_pricing.view_cost_breakdown`.
* مندوب المبيعات العادي يستطيع استخدام حاسبة التسعير وإصدار عروض الأسعار بالسعر الإجمالي للزبون دون إمكانية كشف أسرار التكلفة وهوامش المطبعة.
* حماية وتغذية حاسبة تحويل الوحدات [pricing_sheet_printing.js](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/static/js/printing_pricing/modules/pricing_sheet_printing.js) بأسعار الخامات السليمة من الموديلز المؤمنة.

#### 2. فك ارتباط أوامر الشغل في صالة الإنتاج (`work_order`) عن المبيعات:
* في [work_order/views.py:27](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/work_order/views.py#L27):
  إلغاء الشرط المعطوب: `if not request.user.has_perm('sale.view_quotation')`.
* استبداله بفحص الصلاحية المستقلة للإنتاج:
  `@permission_required('work_order.view_workorder')`.
* فني المونتاج وتشغيل الماكينات في صالة الإنتاج يفتح أمر الشغل الفني (مقاس الفرخ، عدد الألوان، نوع الورق والسلوفان) دون الحاجة لأي صلاحية بيع أو اطلاع على عروض أسعار المبيعات.

#### 3. تطهير قوالب صالة الإنتاج والطباعة من الأرقام المالية:
* في قوالب أوامر الشغل:
  - [templates/work_order/work_order_detail.html](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/templates/work_order/work_order_detail.html)
  - [templates/work_order/work_order_print.html](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/templates/work_order/work_order_print.html)
* حجب أسعار الورق وتكاليف الزنكات وسعر الساعة للماكينات وهوامش الربح وإجمالي الفاتورة عن عمال الماكينات والفنيين.
* قصر إظهار البيانات المالية في أمر الشغل على من يحمل صلاحية:
  `perms.printing_pricing.view_cost_breakdown` أو الصلاحيات المالية للمدير المالي.

---

### الحزمة 6: حراسة مسار الإنتاج وقواعد الحالة (Workflow State Guards)

* **قفل التعديل لمنع إهدار الخامات**:
  1. في [sale/views.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/sale/views.py):
     - إذا كانت الفاتورة مرتبطة بأمر شغل دخل حيز التشغيل الفعلي في الماكينات (`work_order.status in ['in_production', 'completed']`):
       يُقفل التعديل نهائياً حتى لو كان المستخدم يملك `sale.change_sale`.
     - التعديل في هذه الحالة يتطلب صلاحية استثنائية: `sale.change_approved_sale` وموافقة مدير الإنتاج.
  2. في [purchase/views.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/purchase/views.py):
     - فواتير الشراء التي تم استلام خاماتها في المخزن وتوليد إذن إضافة مخزني لها تُقفل ضد التعديل المباشر لحماية توازن المخزون وتكلفة الخامات.

---

### الحزمة 7: حل أزمة التسعير الشاملة وتأمين السلسلة التجارية والخزن

#### 1. الحماية السيرفرية الشاملة للأسعار عبر كامل السلسلة التجارية (Pipeline-Wide Price Protection):
* **القضاء على ثغرة التعديل بالمتصفح (Inspect Element أو Raw POST)**:
  فرض التحقق السيرفري الصارم لمنع تعديل أسعار البنود عن السعر الرسمي إلا لمن يحمل `sale.change_unit_price` عبر المراحل الثلاث:
  1. **عروض الأسعار (`Quotation`)**: في [sale/quotation_views.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/sale/quotation_views.py) أثناء الإنشاء والتعديل.
  2. **أوامر البيع (`SalesOrder`)**: في [sale/sales_order_views.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/sale/sales_order_views.py) لمنع تثبيت سعر متلاعب به قبل إصدار الفاتورة.
  3. **فواتير المبيعات (`Sale`)**: في [sale/views.py:266](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/sale/views.py#L266) مع استئصال شرط `user_type == "sales_rep"`.
* **تحسين الأداء وتجنب N+1 Queries**:
  استخدام استعلام مجمع `Product.objects.in_bulk(valid_prod_ids)` لمطابقة الأسعار في كويري واحد بدلاً من الـ loop المتكرر:
  ```python
  if not request.user.has_perm("sale.change_unit_price") and not request.user.is_superuser:
      prod_map = Product.objects.in_bulk(clean_prod_ids)
      for i, prod_id in enumerate(clean_prod_ids):
          prod_obj = prod_map.get(prod_id)
          if prod_obj and Decimal(unit_prices[i].replace(',', '')) != Decimal(str(prod_obj.selling_price)):
              raise ValueError(f"غير مسموح لك بتغيير سعر المنتج '{prod_obj.name}'. السعر الرسمي هو {prod_obj.selling_price} ج.م")
  ```

#### 2. تحديث قوالب المبيعات والتسعير:
* استبدال الشروط الصلبة بـ `sale.change_unit_price`:
  - [sale_form.html](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/templates/sale/sale_form.html)
  - [sales_order_form.html](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/templates/sale/sales_order_form.html)
  - [quotation_form.html](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/templates/sale/quotation_form.html)
  ```html
  {% if not perms.sale.change_unit_price %}readonly{% endif %}
  ```

#### 3. حماية وتوحيد صلاحية تغيير مسؤول المبيعات وعمولات المناديب:
* في [sale/forms.py:151](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/sale/forms.py#L151):
  توحيد الفحص حصراً على الصلاحية المعيارية `sale.change_sale_salesman`، لضمان عدم تلاعب أي مندوب عادي في نسبة المبيعات لنفسه أو لزملائه.

#### 4. تصحيح الصلاحية اليتيمة في شاشات الخزن النقدية:
* في [financial/views/account_views.py:492](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/financial/views/account_views.py#L492):
  استبدال `@permission_required('ادارة_الخزن_والحسابات')` بـ:
  ```python
  @permission_required('financial.view_cash_accounts', raise_exception=True)
  ```

---

### الحزمة 8: الحوكمة المالية والتداول النقدي وحوكمة IAS 21

#### 1. البيع النقدي وسلطة الخدمات الخلفية (Service-Layer Authority):
* التفرقة التامة بين:
  - **صلاحية واجهة المستخدم**: المندوب لا يملك صلاحية دخول شجرة الحسابات أو إنشاء قيود يدوية (`financial.add_journalentry`).
  - **سلطة الخدمة الآلية (System Service Authority)**: عند اختيار سداد نقدي أو عربون في الفاتورة، تقوم `SaleService` داخلياً عبر `atomic transaction` بإنشاء حركة الخزينة الآلية دون مطالبة المندوب بصلاحيات محاسبية مباشرة.

#### 2. تأمين Context Processors وأجراس الإشعارات:
* في [core/context_processors.py:106](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/core/context_processors.py#L106):
  استبدال `request.user.has_perm('users.ادارة_المالية')` بصلاحية الاعتمادات المعيارية:
  ```python
  request.user.has_perm('financial.approve_workflow') or request.user.has_perm('governance.approve_workflow')
  ```
  مع استغلال كاش `O(1)` لضمان عدم تنفيذ أي كويري متكرر مع كل صفحة للمستخدم.

#### 3. حوكمة فروق العملات وإعادة التقييم (IAS 21 & FX Governance):
* الالتزام الصارم بتوجيهات المشروع في `.agents/AGENTS.md`:
  - قصر تشغيل `FXRevaluationService` وإعادة تقييم الفترات المحاسبية على صلاحية المدير المالي: `financial.run_fx_revaluation`.
  - في حال تجاوز عمر سعر الصرف 7 أيام، تفعيل إجراء الموافقة الإلزامية للمدير المالي (`RATE_OVERRIDE_APPROVAL`).

---

### الحزمة 9: إصلاح أخطاء الـ Decorators والـ Forms ونماذج المستخدمين

#### 1. إصلاح [users/decorators.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/users/decorators.py):
* إنشاء ديكوريتور موحد: `@require_permission(perm_codename)`:
  - التحقق من صلاحية المستخدم عبر الكاش السريع.
  - إرجاع `JsonResponse` بكود 403 ورسالة عربية واضحة في طلبات الـ AJAX.
  - توجيه طلبات الـ HTTP لصفحة `core/permission_denied.html`.
  - إرسال إشارة تنبيه أمني لنظام الحوكمة `governance.signals.permission_violation`.

#### 2. تصحيح وتطهير [users/forms.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/users/forms.py):
* في [UserRoleForm](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/users/forms.py#L180):
  - استبعاد كافة الصلاحيات التقنية العشوائية (`logentry`, `contenttype`, `session`).
  - حصر خيارات `custom_permissions` على تطبيقات البيزنس الحقيقية فقط.
* في [RoleForm](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/users/forms.py#L95):
  - دعم عرض وحفظ الصلاحيات المعيارية لموديلات النظام.

---

### الحزمة 10: تأمين الـ Endpoints والـ Views موديول تلو الآخر (Zero-Trust Backend)

تطبيق الديكوريتورز الإلزامية تدريجياً عبر 5 خطوات متتالية:

1. **موديول المبيعات (`sale`)**: شاشات الفواتير، عروض الأسعار، وأوامر البيع (مع استثناء الـ Context Lookups الضرورية).
2. **موديول المشتريات (`purchase`)**: فواتير الشراء، أوامر الشراء، ومرتجعات الشراء.
3. **العملاء والموردين (`customer`, `supplier`)**: شاشات السجلات والمدفوعات (مع إبقاء `customer_add_ajax` سريع ومتاح للمبيعات).
4. **المالية والحسابات (`financial`)**: شاشات القيود، الخزن، كشوف الحسابات، والفترات المحاسبية.
5. **أوامر الشغل وتسعير المطبوعات (`work_order`, `printing_pricing`)**: تأمين أوامر الإنتاج وحماية هوامش الربح.

---

### الحزمة 11: محرك حل الاعتماديات والواجهة المجمعة الذكية

#### 1. بناء محرك الاعتماديات [users/services/permission_dependency.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/users/services/permission_dependency.py):
خريطة التبعيات المسبقة (Prerequisites Graph):
* **عمليات المبيعات (`sale.add_sale`, `sale.add_quotation`, `sale.add_salesorder`)**:
  - تتطلب قراءة العملاء: `customer.view_customer`.
  - تتطلب قراءة المنتجات والخامات: `product.view_product`.
  - تتطلب قراءة وحدات القياس: `product.view_unit`.
  - تتطلب قراءة العملات: `financial.view_currency`.
* **عمليات المشتريات (`purchase.add_purchase`, `purchase.change_purchase`)**:
  - تتطلب قراءة الموردين: `supplier.view_supplier`.
  - تتطلب قراءة الخامات والمنتجات: `product.view_product`.
  - تتطلب قراءة المخازن: `product.view_warehouse`.
* **العمليات المالية (`financial.add_journalentry`, `financial.add_paymentvoucher`, `financial.add_receiptvoucher`)**:
  - تتطلب قراءة الحسابات: `financial.view_account`.
  - تتطلب قراءة مراكز التكلفة: `financial.view_costcenter`.
  - تتطلب قراءة الفترات المحاسبية: `financial.view_accountingperiod`.
* **تسعير المطبوعات (`printing_pricing.add_pricingorder`)**:
  - تتطلب قراءة خامات المنتجات: `product.view_product`.
  - تتطلب قراءة الوحدات: `product.view_unit`.
* **أوامر الشغل في صالة الإنتاج (`work_order.add_workorder`)**:
  - تتطلب قراءة مواصفات أمر الشغل: `work_order.view_workorder`.
  - تتطلب قراءة مخازن الخامات: `product.view_warehouse`.

#### 2. واجهة إدارة الأدوار المجمعة الذكية:
* تقسيم الصلاحيات في بطاقات حسب الموديول في لوحة تحكم الأدوار.
* خاصية **Auto-Select Prerequisites**: عند اختيار صلاحية مركبة (مثل إضافة فاتورة)، تفعل الواجهة تلقائياً صلاحيات القراءة التابعة وتوضح ذلك للمسؤول في تلميح فوري، مع حفظها صريحة في قاعدة البيانات لمنع أي بطء في الرن تايم.

---

### الحزمة 12: إنشاء الأدوار المؤسسية القياسية الثمانية (Enterprise System Roles)

أمر نظامي متكامل [users/management/commands/seed_enterprise_roles.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/users/management/commands/seed_enterprise_roles.py) لتهيئة 8 أدوار قياسية جاهزة لمطبعة وهبة:

1. **مدير النظام (System Administrator)**: صلاحيات كاملة لكل شيء.
2. **مدير مالي (Finance Manager)**: شجرة الحسابات، اعتماد القيود، إغلاق الفترات، إعادة تقييم العملات IAS 21، ومراجعة هوامش الربح.
3. **محاسب (Accountant)**: إنشاء وتعديل القيود، أذونات الصرف والقبض، الاطلاع على الحسابات والفواتير والتقارير.
4. **أمين خزانة (Cashier)**: سندات القبض والصرف، حركة الخزينة النقدية اليومية، واستعلام الحسابات المباشرة.
5. **مسؤول مبيعات (Sales Executive)**: عروض الأسعار، أوامر البيع، فواتير المبيعات الخاصة به فقط (حماية السعر وهوامش الربح محجوبة).
6. **مشرف مبيعات (Sales Manager)**: الاطلاع على فواتير وعروض كافة المناديب، اعتماد الخصومات، وصلاحية تعديل الأسعار وتغيير مسؤول المبيعات.
7. **أمين مخزن خامات ومنتجات (Warehouse Officer)**: أذونات استلام وصرف الورق والخامات، التحويلات، تسجيل تسويات الجرد، ومتابعة رصيد المخزن.
8. **فني ومسؤول إنتاج (Production Supervisor / Operator)**: الاطلاع على أوامر الشغل الفنية، تحديث مراحل الطباعة والتشطيب في صالة الماكينات (دون الحاجة لصلاحيات مبيعات).

---

### الحزمة 13: توحيد القوالب والـ Sidebar والـ Header

* تدقيق [templates/partials/sidebar.html](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/templates/partials/sidebar.html) و [templates/partials/header.html](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/templates/partials/header.html).
* استبدال الشروط القديمة مثل `perms.users.عرض_المبيعات` بالشروط المعيارية:
  `perms.sale.view_sale`, `perms.work_order.view_workorder`, `perms.printing_pricing.view_pricingorder`...
* تدقيق صفحة [templates/core/permission_denied.html](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/templates/core/permission_denied.html) لتظهر بتصميم أنيق وهادئ يلتزم بمعايير النظام (CSS variables وبدون تدرجات لونية).

---

## 3. خطة التحقق الشاملة (Automated Test Suite via Pytest)

إنشاء ملف اختبار شامل: [users/tests/test_enterprise_rbac.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/users/tests/test_enterprise_rbac.py):

1. **اختبار خلو النظام من qrapplication (Ghost Code Cleanliness Test)**:
   - التأكد من عدم وجود أي مراجع أو استعلامات لـ `qrapplication` وتطهير الداتابيز منها.
2. **اختبار تطهير اختطاف الكلاسات في إعدادات التسعير (Settings Mixin Decoupling Test)**:
   - التأكد من أن مسؤول التسعير يدير إعدادات الخامات والماكينات بصلاحية `printing_pricing.manage_pricing_settings` دون اشتراط `is_staff`.
3. **اختبار تصفية طلبات التسعير بالصلاحية وليس بـ is_staff (Order View Decoupling Test)**:
   - التأكد من أن مشرف التسعير يرى كافة الطلبات بصلاحية `printing_pricing.view_all_orders`.
4. **اختبار تطابق مسميات الـ Web والـ API (Permission Naming Parity Test)**:
   - التأكد من أن `hr.approve_leave` تعمل بتطابق تام بين شاشات الويب وواجهات الـ REST API.
5. **اختبار كاش الأداء الفائق وتطهير الكاش (Cache Activation & Invalidation Test)**:
   - التأكد من ربط `RolePermissionBackend` مع `PermissionCacheService` وتنفيذ استعلام واحد فقط عند فحص 50 صلاحية.
   - التأكد من تفريغ وتحديث الكاش فور تعديل أي دور.
6. **اختبار محاكاة المستخدم (Login As User / Impersonation Test)**:
   - التأكد من أن تسجيل الدخول بحساب موظف يحاكي بدقة متناهية صلاحيات الدور المخصص له.
7. **اختبار إغلاق ثغرة الـ REST API (DRF Security Test)**:
   - التأكد من أن طلبات GET على `/api/journal-entries/` و `/api/chart-of-accounts/` تُرفض بـ 403 لمندوب المبيعات وموظف الاستقبال.
8. **اختبار عزل فواتير المناديب (Object-Level Ownership Test)**:
   - التأكد من أن المندوب يرى فواتيره فقط، بينما المشرف يرى فواتير جميع المناديب.
9. **اختبار حماية تغيير مسؤول المبيعات (Salesman Assignment Test)**:
   - التأكد من منع المندوب العادي من تعديل حقل مسؤول المبيعات لنفسه أو لزملائه، وسماحه للمشرف فقط.
10. **اختبار انضباط Context Processors (Approval Count Notification Test)**:
    - التحقق من دقة حساب عدد طلبات الاعتماد المعلقة للمدير المالي دون أي كويريز مكررة.
11. **اختبار ترقية الأدوار القائمة ومزامنة المستخدمين (Migration Bridge & Sync Test)**:
    - التأكد من ترقية الأدوار الـ 7 القائمة واحتفاظ حساب `mwheba` وحساب `admin` بكافة إمكانيات التشغيل الإدارية دون تناقض مع `user_type`.
12. **اختبار حماية الأسعار عبر كامل السلسلة التجارية (Pipeline Price Protection Test)**:
    - التحقق من رفض أي محاولة تلاعب بالأسعار في الباك إند لمن لا يملك `sale.change_unit_price` عبر المراحل الثلاث:
      *(عروض الأسعار Quotation $\leftarrow$ أوامر البيع SalesOrder $\leftarrow$ فواتير البيع Sale)*.
13. **اختبار سرية هوامش أرباح المطبعة (Profit Margin Privacy Test)**:
    - التأكد من حجب هوامش الأرباح وتفاصيل تكلفة الورق عن مسؤول المبيعات، وظهورها للمدير المالي.
14. **اختبار فك ارتباط أوامر الشغل وتطهير قوالب الإنتاج (Work Order Decoupling & Privacy Test)**:
    - تمكن مسؤول الإنتاج من فتح أمر الشغل الفني بصلاحية `work_order.view_workorder` فقط دون الحاجة لصلاحية المبيعات.
    - التحقق من حجب كافة أرقام التكلفة والأسعار وهوامش الربح في قوالب `work_order_detail.html` و `work_order_print.html`.
15. **اختبار حظر الدخول غير المصرح (Zero-Trust Views Test)**:
    - التأكد من إرجاع `403` على كافة الـ Views المقفلة عند محاولة الوصول المباشر بالـ URL أو الـ AJAX.
16. **اختبار عزل التطبيقات الصارم في الباك إند (Cross-App Permission Isolation Test)**:
    - التأكد من أن سطر تجريد التطبيقات القديم قد تم القضاء عليه، وأن امتلاك `printing_pricing.view_order` لا يمنح أي وصول إطلاقاً لـ `sale.view_order`.
17. **اختبار التزام دالة User.get_all_permissions بعقد جانغو (Django Contract Compliance Test)**:
    - التأكد من أن إرجاع دالة `request.user.get_all_permissions()` هو مجموعة نصوص قياسية `set[str]` بصيغة `'app_label.codename'`.
18. **اختبار طبقة التوافق العكسي (Bidirectional Compatibility Map Test)**:
    - التأكد من أن أي استعلام قديم بصيغة `has_perm('users.ادارة_المبيعات')` يُترجم بنجاح إلى `sale.view_sale` و `sale.add_sale` لضمان صفر انكسارات.

---

تشغيل الاختبارات:
```powershell
pytest users/tests/test_enterprise_rbac.py -v
```
