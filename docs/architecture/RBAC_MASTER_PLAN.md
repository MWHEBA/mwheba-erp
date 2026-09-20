# وثيقة الخطة الشاملة المتكاملة لنظام الصلاحيات والحوكمة (MWHEBA ERP Master RBAC & Security Plan - النسخة النصية المحكمة v8)

المرجع المعماري والتنفيذي النهائي لإصلاح، توحيد، وإحكام نظام الصلاحيات والحوكمة في **MWHEBA ERP**، متوافقاً مع معايير (NIST Enterprise RBAC Level 2 + Object-Level Security + Permission-Driven Business Logic + Workflow State Guards)، ومصمماً بالكامل بنصوص مهيكلة، تحليلية ومفصلة بدون أي رسوم بيانية أو صور، ومحكماً ضد كافة الثغرات والعيوب الهندسية التي نوقشت بنقد صارم مع الحفاظ التام على 100% من المحتوى والتفاصيل الفنية لمطبعة وهبة، ومدمجاً به نتائج تدقيق قاعدة البيانات الحية، حماية المشتريات، الثبات المحاسبي، وكاش الطبقة الثانية $O(1)$.

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
  6. **استئصال الأدوار الشبحية الخمسة من قاعدة البيانات الحية**:
     - إعدام الأدوار الميتة التابعة لنماذج تم حذفها سابقاً: (`activities_coordinator`, `transportation_coordinator`, `receptionist`, `manager`, `hr_manager`).
     - تثبيت الأدوار المؤسسية العشرة النظيفة والمعتمدة فقط في جدول `users_role`.
  7. **تصحيح تلف ترميز أسماء الأدوار العربية (`display_name`)**:
     - إعادة كتابة أسماء الأدوار بـ UTF-8 الصريح في الداتابيز الحية لمنع ظهور علامات الاستفهام والتشوهات `' '`.
  8. **استئصال ملفات كتم الأخطاء الثلاثة وتطهير الجافاسكريبت**:
     - حذف استدعاءات `error-suppressor.js`, `error-prevention.js`, `suppress-json-errors.js` من `dashboard.html`.
     - إعادة بناء `permissions-dashboard.js` (2116 سطر) والتخلص نهائياً من ترقيعات الـ LocalStorage وكود الـ 42 صلاحية القديم.

---

### الركيزة الثانية: النواة والأداء الفائق وإدارة الهوية (Core Performance, Caching & Identity Pillar)
* **الهدف الجوهري**: توفير استجابة لحظية $O(1)$ لعمليات فحص الصلاحيات داخل الذاكرة بصفر استعلامات SQL متكررة، مع الحفاظ المطلق على المستخدمين القائمين واستمرارية التشغيل، وسد ثغرات تجريد التطبيقات وتناقض البيانات.
* **المكونات والآليات الهندسية للركيزة**:
  1. **محرك `RolePermissionBackend` المطور والمحكم**:
     - القضاء على ثغرة تجريد التطبيقات (`app_label stripping`): إيقاف سطر `codename = perm.split('.')[-1]` واعتماد المطابقة الصارمة على مستوى `(content_type__app_label, codename)` لمنع تسريب الصلاحيات المتشابهة في الأسماء بين التطبيقات (مثل `sale.view_order` و `printing_pricing.view_order`).
     - طبقة توافق عكسي ذكية (Bidirectional Compatibility Map): تضمن ترجمة الصلاحيات الـ 42 العربية القديمة إلى الصلاحيات القياسية الجديدة تلقائياً، لمنع انكسار أي دور من الأدوار الـ 7 القائمة أثناء مرحلة الترقية.
     - استيفاء عقد جانغو الكامل للباك إند: تطبيق دوال `get_all_permissions(user_obj, obj=None)` و `get_group_permissions(user_obj, obj=None)` لترجع `set[str]` بصيغة `'app_label.codename'`.
  2. **توحيد مصدر الحقيقة (Single Source of Truth) وتصحيح عقد `User.get_all_permissions()`**:
     - تعديل دالة `User.get_all_permissions()` في [users/models.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/users/models.py) لتفوض جلب الصلاحيات مباشرة إلى الباك إند الموحد لترجع `set[str]` بصفر تكرار برمجي.
     - إلغاء استنزاف الذاكرة للـ Superuser/Admin: إعادة `True` فورياً $O(1)$ في الفحوصات دون سحب كامل جدول `Permission.objects.all()`.
  3. **معمارية الكاش ثنائية الطبقات الحقيقية (Two-Tier Caching Architecture)**:
     - **الطبقة الأولى (Tier 1 - Request Memory)**: كاش لحظي على مستوى الطلب `request._perm_cache` بصيغة `set[str]`، خيطي آمن، صفر استعلامات، وصفر اعتماديات شبكية أثناء معالجة الطلب الواحد.
     - **الطبقة الثانية (Tier 2 - Process/Distributed Cache)**: ربط الباك إند بـ `django.core.cache` بمفتاح `user_perms_{user.id}` ليعمل بسلاسة عبر كافة صفحات الجلسة دون تكرار أي كويري.
     - تفعيل التطهير الذكي الفوري (Smart Invalidation) عبر إشارات جانغو (`post_save`, `m2m_changed`, `post_delete`) على `Role` و `User`.
  4. **محرك التبعيات المزدوج وسد فجوة المناديب الرقمية (Dual Dependency Engine)**:
     - معالجة فقر صلاحيات مندوب المبيعات (`sales_rep` لديه 23 صلاحية فقط): منح العملات والمخازن والوحدات والضرائب.
     - حقن تلقائي لحظي $O(1)$ في الباك إند: من يملك `sale.add_sale` أو `purchase.add_purchase` يُحقن له تلقائياً `financial.view_currency` و `product.view_warehouse` و `product.view_unit` و `product.view_category` لمنع توقف الفواتير أبداً.
     - بناء محرك حل الاعتماديات للواجهات [users/services/permission_dependency.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/users/services/permission_dependency.py).
  5. **الفصل التام لـ `user_type` عن منطق الصلاحيات وتطهير التناقضات**:
     - إقرار قاعدة صارمة: حقل `user_type` هو مسمى وظيفي وتنظيمي فقط؛ ويُحظر تماماً استخدامه في أي فحص تصريح داخل كود البايثون.
     - مزامنة وتصحيح بيانات حساب `mwheba` القائم ليتطابق نوع حسابه مع دوره الإداري (`admin`) ورفع القيود المتناقضة عنه.
  6. **جسر ترحيل البيانات التلقائي (Data Migration Bridge)**:
     - إنشاء وتشغيل سكريبت ترحيل آمن يضمن ترقية وضمان حقوق الأدوار العشرة النظيفة في الداتابيز ومستخدمي النظام الحاليين دون أي انقطاع للخدمة.
  7. **أداة انتحال الهوية الآمنة والمراقبة (Login As User / Impersonation)**:
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
  4. **تتبع وتوثيق انتحال الهوية في طلبات الـ AJAX**:
     - التقاط `impersonated_by_id` في ترويسات طلبات الـ AJAX وتوثيقها تلقائياً في سجلات `ActivityLog` وبيانات المستندات لضمان المسؤولية القانونية الكاملة وإظهار شريط تحذيري علوي ثابت في [header.html](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/templates/partials/header.html).

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
  5. **الاستلام المخزني الأعمى مالياً (Blind GRN Receiving)**:
     - حجب أسعار الشراء وإجمالي التكلفة عن أمين المخزن في كارتة الاستلام `grn_detail.html`، مع تمكينه من فحص الكميات ومطابقة المواصفات الفنية للخامات والورق، وقصر ظهور الأرقام المالية على مسؤولي المشتريات والإدارة المالية.

---

### الركيزة الخامسة: الحوكمة المالية والتداول النقدي (Financial Governance & Cash Authority Pillar)
* **الهدف الجوهري**: حماية الخزائن والحسابات والامتثال لمعايير المحاسبة الدولية (IAS 21) ومنع أي تلاعب نقدي أو محاسبي.
* **المكونات والآليات الهندسية للركيزة**:
  1. **سلطة طبقة الخدمات المؤتمتة (Service-Layer Authority)**:
     - تمكين مندوب المبيعات من تسجيل المقبوضات النقدية والعربون المصاحب للفاتورة مباشرة من شاشة البيع دون منحه صلاحية الاطلاع المباشر على الخزن أو شجرة الحسابات، بحيث تنفذ القيود عبر طبقة الخدمات المصرح لها فقط تلقائياً.
  2. **حوكمة معيار المحاسبة الدولي IAS 21 لإعادة تقييم العملات**:
     - قصر تشغيل وإلغاء عمليات إعادة تقييم العملات الأجنبية (`financial.run_fx_revaluation`) واعتماد أسعار الصرف التاريخية المنتهية على المدير المالي حصراً (`financial.approve_fx_override`).
     - التطابق الحرفي للـ Codenames بالـ Underscores لمنع الـ 403 الصامت (`close_accounting_period`, `reopen_accounting_period`, `run_fx_revaluation`, `post_journal_entry`, `reverse_journal_entry`).
  3. **تأمين شاشات الخزن وحسابات النقدية**:
     - استبدال الصلاحية اليتيمة في `account_views.py` بصلاحية معيارية تابعة للموديول المالي `financial.view_cash_accounts`.
  4. **الحوكمة الصارمة لإغلاق الفترات في طبقة الخدمات**:
     - اشتراط `financial.close_accounting_period` في `PeriodControlService.close_period` وحظر إغلاق الفترة نهائياً في حال وجود فواتير أو قيود بحالة مسودة (Draft/Unposted).
  5. **حوكمة سقف الائتمان بمسار «المسودة المعلقة للاعتماد المالي»**:
     - عند تجاوز العميل لسقفه الائتماني، تُحفظ الفاتورة تلقائياً كـ **«مسودة معلقة للاعتماد المالي (pending_approval)»** مع إشعار للمدير المالي، لمنع كسر أو تعطيل الشغل المستعجل.

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
  4. **حماية تكاليف التوريد في المشتريات (Procurement Cost Guard & Approval)**:
     - إنفاذ صلاحية `purchase.change_unit_cost` في طبقة الخدمات والقوالب `templates/purchase/purchase_form.html` بالتناظر التام مع `change_unit_price` في المبيعات لمنع التلاعب بتكلفة الخامات.
     - اشتراط صلاحية `purchase.approve_purchase` لترحيل فواتير الشراء وتوليد أستاذ المخزن وقيد المورد المحاسبي.
  5. **الثبات المحاسبي وحظر إلغاء المستندات المعتمدة (Accounting Immutability)**:
     - حظر الحذف أو الإلغاء المباشر للفواتير والقيود المرحلة في طبقة الخدمات، وقصر التسوية على المردودات الرسمية (`Purchase Return` / `Sale Return`) والقيود العكسية (`Reverse Journal Entry`).
  6. **هجرة البيانات الصريحة عبر `RunPython` واستكمال `class Meta.permissions`**:
     - إضافة `class Meta.permissions` الناقصة في موديلات `SalesOrder` (`approve_sales_order`, `change_sales_order_price`, `view_all_salesorders`) وموديل `InventoryAdjustment` (`approve_inventory_adjustment`).
     - تنفيذ هجرة بيانات صريحة `RunPython` لضمان وجود كافة الصلاحيات المؤسسية في جدول `auth_permission` في كل بيئات التشغيل والاختبارات.
  7. **تأمين إشعارات الـ Context Processors**:
     - حماية استعلامات شارة طلبات الاعتماد `EnterpriseApprovalRequest` بصلاحية معيارية `financial.approve_workflow` لمنع تسريب بيانات الاعتمادات بصفر كويريز إضافية.
  8. **تأمين شامل لجميع الـ Views (Zero-Trust Policy) مع العزل الجراحي للـ Lookups**:
     - تغطية كافة شاشات وعمليات المبيعات، المشتريات، العملاء، الموردين، المالية، والمخازن بديكوريتورز ومكسنز صارمة، مع تأمين مسارات التغذية والـ AJAX Lookups (`invoice_product_lookup`, `get_stock_by_warehouse`, `customer_add_ajax`).
  9. **واجهة إدارة الصلاحيات المجمعة الذكية (Grouped Matrix UI)**:
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
  - `SalesOrder` (في [sale/models/sales_models.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/sale/models/sales_models.py)):
    - إضافة `class Meta` الغائب تماماً في الموديل وتثبيت الصلاحيات:
      - `approve_sales_order`: اعتماد أمر البيع.
      - `change_sales_order_price`: تعديل أسعار أوامر البيع.
      - `view_all_salesorders`: الاطلاع على أوامر بيع كافة المناديب.
* [purchase/models.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/purchase/models.py):
  - `Purchase`:
    - `approve_purchase`: اعتماد فاتورة المشتريات (إنفاذ الفحص في دوال الترحيل لإنشاء أستاذ المخزن وقيد المورد).
    - `change_unit_cost`: تعديل تكلفة الشراء المحددة (إنفاذ الفحص السيرفري في [purchase_views.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/purchase/views/purchase_views.py) وقفل الحقل `readonly` في الفورم لمن لا يملك الصلاحية).
    - `cancel_approved_purchase`: إلغاء فاتورة مشتريات معتمدة (خاضع لمبدأ الثبات المحاسبي: حظر الحذف المباشر وفرض مسار المردودات والقيد العكسي).
* [financial/models.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/financial/models.py):
  - `JournalEntry`:
    - `post_journal_entry`: ترحيل/اعتماد القيود المحاسبية.
    - `reverse_journal_entry`: عكس قيد محاسبي معتمد.
  - `AccountingPeriod`:
    - `close_accounting_period`: إغلاق الفترة المحاسبية.
    - `reopen_accounting_period`: إعادة فتح فترة محاسبية مغلقة.
    - `run_fx_revaluation`: تشغيل إعادة تقييم فروق العملات IAS 21 (خاص بالمدير المالي).
* [product/models.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/product/models.py):
  - `InventoryAdjustment` (في [product/models/inventory_movement.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/product/models/inventory_movement.py)):
    - إضافة الصلاحية في `Meta.permissions`:
      - `approve_inventory_adjustment`: اعتماد تسوية فروق الجرد المخزني.
* **هجرة البيانات الصريحة (`RunPython` Data Migration)**:
  - إنشاء ملف migration يتضمن دالة `RunPython` صريحة تقوم بالتحقق من وجود هذه الصلاحيات وإنشائها فوراً في جدول `auth_permission` مع ربطها بـ `ContentType` الصحيح لضمان وجودها الحتمي في كافة البيئات وقبل تشغيل الاختبارات.
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
  - يضمن هذا عدم انكسار أي دور من الأدوار القائمة أثناء مرحلة الترقية.
* **استيفاء عقد دوال جانغو القياسية للـ Backend**:
  - إضافة دالة `get_all_permissions(user_obj, obj=None)` ترجع `set[str]` بصيغة `'app_label.codename'`.
  - إضافة دالة `get_group_permissions(user_obj, obj=None)` لترجع صلاحيات الدور والجروبات كنصوص.
* **إنهاء استنزاف الذاكرة للـ Superuser/Admin**:
  - دالة `has_perm()` ترجع `True` فورياً $O(1)$ للـ Superuser والـ Admin بصفر استعلامات SQL، دون سحب كامل جدول `Permission.objects.all()` إلى الذاكرة.
* **محرك التبعيات المزدوج المدمج (Dual Dependency Engine)**:
  - حقن تلقائي لحظي $O(1)$ في الباك إند: من يملك `sale.add_sale` أو `purchase.add_purchase` يُحقن له في كاش الصلاحيات تلقائياً `financial.view_currency` و `product.view_warehouse` و `product.view_unit` و `product.view_category` لمنع تعطل شاشات الفواتير الميدانية وسد فجوة المناديب الرقمية (23 صلاحية).

#### 3. توحيد مصدر الحقيقة (Single Source of Truth) وتصحيح عقد [users/models.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/users/models.py):
* تعديل دالة `get_all_permissions(self, obj=None)` في نموذج `User` لتفوض جلب الصلاحيات مباشرة إلى `RolePermissionBackend` الموحد لترجع `set[str]` بدلاً من كائنات الموديل، مما يقضي على ازدواجية الكود واختلاف نتائج الفحص بين الموديل والباك إند.
* إضافة دالة مساعدة منفصلة: `get_all_permission_objects(self)` للأماكن الإدارية التي تحتاج كائنات الموديل الفعلية.
* إقرار الفصل التام لـ `user_type`: يُمنع استخدام `user_type` في أي شروط تصريح أو أمان برمجية، ويظل حقل دلالي وظيفي فقط.

#### 4. معمارية الكاش ثنائية الطبقات الحقيقية وإيقاظ [permission_cache.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/users/services/permission_cache.py):
* **الطبقة الأولى (Tier 1 - Request Memory)**:
  - تخزين الصلاحيات داخل `request._perm_cache` فور أول فحص كـ `set[str]` لضمان زمن استجابة ميكروثانية $O(1)$ وصفر كويريز وصفر اعتماديات شبكية أثناء الـ Request الواحد.
* **الطبقة الثانية (Tier 2 - Process & Distributed Cache)**:
  - ربط الباك إند بـ `django.core.cache` بمفتاح `user_perms_{user.id}` مع تصحيح عقد `_get_cached_user_permissions` في [permission_service.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/users/services/permission_service.py) لترجع نصوص الصلاحيات بدقة.
  - تفعيل التطهير اللحظي الشامل (Bulk Role-Based Cache Invalidation) عبر إشارة `m2m_changed` على جدول الوسيط `Role.permissions.through` وجدول `User.roles.through`؛ بحيث عند تعديل صلاحيات أي دور يتم جلب معرّفات جميع المستخدمين المرتبطين بهذا الدور دفعة واحدة ومسح مفاتيح الكاش الخاصة بهم عبر `cache.delete_many([f"user_perms_{uid}" for uid in user_ids])` لتنعكس التعديلات لحظياً على كافة الموظفين بدون أي تأخير أو بقاء صلاحيات قديمة.

#### 5. تطهير قاعدة البيانات الحية وترحيل الأدوار وتصحيح الترميز العربي:
* تشغيل سكريبت تنظيف وترحيل شامل يغطي:
  - **استئصال الأدوار الشبحية الخمسة**: حذف `activities_coordinator`, `transportation_coordinator`, `receptionist`, `manager`, `hr_manager` التابعة لموديلات محذوفة.
  - **تصحيح تلف ترميز الأسماء العربية (`display_name`)**: إعادة كتابة الأسماء بـ UTF-8 الصريح في جدول `users_role` (مثل: "مدير النظام", "مدير مالي", "محاسب", "مسؤول مشتريات وموردين", "أمين مخازن ومنتجات", "مشرف مبيعات", "مندوب مبيعات", "مسؤول تشغيل وإنتاج", "مسؤول موارد بشرية", "مستخدم استعلام").
  - **تثبيت الأدوار المؤسسية العشرة النظيفة** وترقية صلاحياتها لصلاحيات الموديلز المعيارية.
  - **مزامنة بيانات المستخدمين النشطين**: فحص وتصحيح التناقضات في حساب `mwheba` ليتطابق دوره الإداري (`admin`) مع نوع حسابه ورفع أي قيود سعرية متناقضة عنه.
  - الحفاظ التام على المستخدمين الحاليين وضمان استمرار عملهم فوراً دون انقطاع.

#### 6. تأمين وتوافق ميزة "تسجيل الدخول كمستخدم آخر" (Login As User) وتتبع الـ AJAX:
* في [users/views.py:452](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/users/views.py#L452):
  - التأكد من أن تسجيل الدخول كمستخدم آخر يحمّل الصلاحيات الفعلية للدور المستهدف عبر `RolePermissionBackend`.
  - التقاط `impersonated_by_id` في ترويسات طلبات الـ AJAX وتوثيقها تلقائياً في سجلات `ActivityLog` وبيانات المستندات لضمان المسؤولية القانونية الكاملة.
  - إظهار شريط تحذيري علوي ثابت في [header.html](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/templates/partials/header.html) ينبه المدير بوضعه الحالي مع زر سريع للعودة لحسابه الأصلي.

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

#### 5. حماية تكاليف التوريد في المشتريات والاستلام المخزني الأعمى وتأمين مسارات الحذف (Procurement Security & Immutability):
* **القضاء على كارثة حذف القيود في `purchase_delete` (خط 1187-1277 في [purchase_views.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/purchase/views/purchase_views.py))**:
  - **حظر الحذف المطلق للفواتير المرحلة**: إذا كانت الفاتورة مرحلة (`status == 'posted'`) أو صدر لها قيد محاسبي أو أذونات مخزنية، يُمنع الحذف نهائياً برمجياً ومحاسبياً ويُرفض الطلب برسالة خطأ صريحة. يُحظر تماماً كود `journal_entry.delete()` و `journal_entry.status = 'draft'` لمنع تمزيق الدفاتر والتسلسل المحاسبي.
  - قصر الحذف على الفواتير المسودة فقط (`status == 'draft'`) لمن يملك صراحة `purchase.delete_purchase`.
  - معالجة التسويات للفواتير المعتمدة عبر إنشاء إشعار مدين رسمي ومردودات مشتريات (`Purchase Return`) وقيد محاسبي عكسي.
* **إنفاذ صلاحية تعديل تكلفة الشراء الحقيقية (`purchase.change_unit_cost`)**:
  - إنهاء "الصلاحية الوهمية"؛ فحص الصلاحية برمجياً بالسيرفر في `purchase_create` و `purchase_update` داخل [purchase/views/purchase_views.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/purchase/views/purchase_views.py) قبل تمرير الأسعار لـ `MovementService.process_movement`. إذا لم يكن المستخدم يملك الصلاحية، يُرفض تعديل السعر عن السعر المسجل بقائمة المورد أو أمر الشراء المعتمد.
  - قفل الحقل `readonly` في قوالب الشراء [purchase_form.html](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/templates/purchase/purchase_form.html):
    `{% if not perms.purchase.change_unit_cost %}readonly{% endif %}`.
* **تأمين واجهات المشتريات بالصلاحيات المعيارية لجانغو**:
  - حماية كافة دوال الـ Views في [purchase/views/purchase_views.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/purchase/views/purchase_views.py) بديكوريتورز الصلاحيات المعيارية بدلاً من الاكتفاء بـ `@login_required`:
    - `purchase_list`: `@permission_required('purchase.view_purchase')`
    - `purchase_create`: `@permission_required('purchase.add_purchase')`
    - `purchase_detail`: `@permission_required('purchase.view_purchase')`
    - `purchase_update`: `@permission_required('purchase.change_purchase')`
    - `purchase_delete`: `@permission_required('purchase.delete_purchase')`
* **تأمين اعتماد أوامر الشراء في طبقة الخدمات (`ProcurementService.approve_purchase_order`)**:
  - في [purchase/services/procurement_service.py:194](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/purchase/services/procurement_service.py#L194): اشتراط امتلاك المستخدم المستدعى صلاحية `purchase.approve_purchaseorder` أو `purchase.approve_purchase` برمجياً في السيرفر قبل تحويل حالة الأمر إلى `APPROVED`.
* **إصلاح المسار المكسور لحذف المبيعات (`sale_delete`) في [sale/urls.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/sale/urls.py)**:
  - معالجة الراوت المكسور `path("<int:pk>/delete/", views.sale_delete, name="sale_delete")` الذي لا يملك دالة مقابلة في [sale/views.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/sale/views.py)؛ إما بربطه بدالة مؤمنة ومحصورة على فواتير المسودة (`draft`) مع فحص `sale.delete_sale`، أو إزالة الراوت نهائياً بما يتوافق مع سياسة حظر حذف المبيعات.
* **إنفاذ صلاحية اعتماد المشتريات (`purchase.approve_purchase`)**:
  - اشتراط الصلاحية لترحيل الفاتورة وتوليد إذن الإضافة المخزني وقيد استحقاق المورد المحاسبي.
* **الثبات المحاسبي وحظر إلغاء المستندات المعتمدة (`purchase.cancel_approved_purchase`)**:
  - حظر الإلغاء أو الحذف المباشر للفاتورة بعد اعتمادها وترحيلها، وتوجيه التسوية حصراً لإنشاء مردودات مشتريات رسمية (`Purchase Return`) وقيد محاسبي عكسي.
* **الاستلام المخزني الأعمى مالياً (Blind GRN Receiving & Print Guard)**:
  - في [templates/purchase/grn_detail.html](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/templates/purchase/grn_detail.html) وقالب الطباعة [templates/purchase/purchase_print.html](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/templates/purchase/purchase_print.html): حجب كافة الأسعار وقيم التكلفة وإجمالي الفاتورة عن أمين المخزن أو من لا يحمل صلاحية الاطلاع المالي، ليقتصر دوره على تدقيق الكميات والمواصفات الفنية للورق والخامات المستلمة دون أي تسريب لأسرار التوريد.

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

#### 4. التطابق الحرفي للـ Codenames بالـ Underscores:
* الالتزام الصارم بأسماء الصلاحيات المالية كما هي مسجلة في الموديلز:
  - `financial.close_accounting_period`
  - `financial.reopen_accounting_period`
  - `financial.run_fx_revaluation`
  - `financial.post_journal_entry`
  - `financial.reverse_journal_entry`
  لمنع أخطاء الـ 403 الصامتة الناجمة عن فحص الأسماء بدون شرطات سفلية.

#### 5. الحوكمة الصارمة لإغلاق الفترات في طبقة الخدمات:
* اشتراط `financial.close_accounting_period` في `PeriodControlService.close_period` وحظر إغلاق الفترة نهائياً في حال وجود فواتير مبيعات أو مشتريات أو قيود يومية بحالة مسودة (Draft/Unposted).

#### 6. حوكمة سقف الائتمان بمسار «المسودة المعلقة للاعتماد المالي» وحماية الإضافة السريعة:
* عند تجاوز العميل لسقفه الائتماني، تُحفظ الفاتورة تلقائياً في `SaleService` كـ **«مسودة معلقة للاعتماد المالي (pending_approval)»** مع إشعار للمدير المالي؛ بحيث لا تولد الفاتورة أي قيد يومية في الحسابات ولا تخصم رصيد المخزن الفعلي حتى يصدر الاعتماد المالي الصريح، منعاً لكسر أو تعطيل الشغل المستعجل.
* **حماية سقف الائتمان في `customer_add_ajax`**: تجاهل أي قيمة مرسلة لحقل `credit_limit` في طلب الإضافة السريع من المبيعات، وتثبيته دائماً بـ `0.00` تلقائياً، مع قصر تعديل سقف الائتمان على الشاشة الرئيسية للعميل وبصلاحية `customer.change_credit_limit` للمدير المالي حصراً.

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

#### 3. تطهير واجهة الصلاحيات واستئصال ملفات كتم الأخطاء:
* حذف ملفات كتم الأخطاء الثلاثة (`error-suppressor.js`, `error-prevention.js`, `suppress-json-errors.js`) من [dashboard.html](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/templates/users/dashboard.html).
* إعادة بناء واختزال [permissions-dashboard.js](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/static/js/permissions-dashboard.js) والتخلص نهائياً من ترقيعات الـ LocalStorage وكود الـ 42 صلاحية القديم.

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

### الحزمة 12: تثبيت الأدوار المؤسسية القياسية العشرة (Ten Enterprise Canonical Roles)

تثبيت وبذر الأدوار المؤسسية النظيفة العشرة عبر [users/management/commands/seed_clean_roles.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/users/management/commands/seed_clean_roles.py) بعد تطهير الأدوار الشبحية:

1. **مدير النظام (System Administrator - `admin`)**: صلاحيات كاملة وشاملة لكافة وظائف النظام.
2. **مدير مالي (Finance Manager - `financial_manager`)**: شجرة الحسابات، اعتماد القيود، إغلاق الفترات، إعادة تقييم العملات IAS 21، ومراجعة هوامش الربح.
3. **محاسب (Accountant - `accountant`)**: إنشاء وتعديل القيود، أذونات الصرف والقبض، الاطلاع على الحسابات والفواتير والتقارير المالية.
4. **مسؤول مشتريات وموردين (Procurement Officer - `procurement_officer`)**: أوامر الشراء، فواتير الشراء، اعتماد المشتريات، وإدارة بيانات الموردين.
5. **أمين مخازن ومنتجات (Inventory Manager - `inventory_manager`)**: أذونات استلام وصرف الورق والخامات، التحويلات بين المخازن، تسويات الجرد، وأذونات الاستلام المخزني (GRN الأعمى مالياً).
6. **مشرف مبيعات (Sales Manager - `sales_manager`)**: الاطلاع على فواتير وعروض كافة المناديب، اعتماد الخصومات وسقف الائتمان، وصلاحية تعديل الأسعار وتغيير مسؤول المبيعات.
7. **مندوب مبيعات (Sales Representative - `sales_rep`)**: عروض الأسعار، أوامر البيع، فواتير المبيعات الخاصة به فقط (حماية السعر، وهوامش الربح وتكاليف الخامات محجوبة عنه).
8. **مسؤول تشغيل وإنتاج (Production Supervisor - `production_supervisor`)**: الاطلاع على أوامر الشغل الفنية، تحديث مراحل المونتاج والطباعة والتشطيب في صالة الماكينات (دون الحاجة لصلاحيات مبيعات أو أسعار).
9. **مسؤول موارد بشرية (HR Officer - `hr_officer`)**: شؤون الموظفين، الحضور والانصراف، الإجازات، ومسيرات الرواتب.
10. **مستخدم استعلام (Viewer - `viewer`)**: صلاحيات القراءة والاستعلام فقط دون أي حق في الإضافة أو التعديل أو الحذف.

---

### الحزمة 13: توحيد القوالب والـ Sidebar والـ Header

* تدقيق [templates/partials/sidebar.html](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/templates/partials/sidebar.html) و [templates/partials/header.html](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/templates/partials/header.html).
* استبدال الشروط القديمة مثل `perms.users.عرض_المبيعات` بالشروط المعيارية:
  `perms.sale.view_sale`, `perms.work_order.view_workorder`, `perms.printing_pricing.view_pricingorder`...
* تدقيق صفحة [templates/core/permission_denied.html](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/templates/core/permission_denied.html) لتظهر بتصميم أنيق وهادئ يلتزم بمعايير النظام (CSS variables وبدون تدرجات لونية).

---

### الحزمة 14: المرحلة العاشرة - ترقية تخصيص المستخدمين، الأدوار المتعددة، حماية التخصيصات، ونطاق البيانات

#### 1. إنهاء العمى البصري ودعم الحرمان الصريح في واجهة الصلاحيات (`edit_user_permissions_modal.html`):
* تطوير نقطة النهاية `users/permissions/users/<id>/permissions/` لترجع الصلاحيات مقسمة بوضوح:
  - `role_permissions`: الصلاحيات الممنوحة له تلقائياً بحكم دوره المؤسسي وأدواره الثانوية.
  - `custom_permissions`: الصلاحيات الفردية الممنوحة له بصفة شخصية استثنائية.
  - `revoked_permissions`: الصلاحيات المستثناة أو المحجوبة عنه من أدواره.
* في واجهة المودال:
  - عرض الصلاحيات الموروثة من الدور كصناديق مغلقة (Disabled) محاطة بشارة توضيحية خفيفة `موروثة من الدور الأساسي` مع منع ازدواجية البيانات.
  - إمكانية تحديد استثناءات صريحة لحجب صلاحية موروثة عبر إضافة `revoked_permissions = models.ManyToManyField(Permission, blank=True, related_name='revoked_from_users')` في [users/models.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/users/models.py).
  - تحديث معادلة الباك إند في [users/backends.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/users/backends.py):
    $$\text{Effective Permissions} = (\text{Role} \cup \text{Secondary Roles} \cup \text{Custom}) \setminus \text{Revoked}$$

#### 2. معمارية الأدوار المتعددة للموظفين متعددي المهام (Multi-Role Support):
* كسر قيد الدور الفردي: إضافة `secondary_roles = models.ManyToManyField(Role, blank=True, related_name='secondary_users')` في [users/models.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/users/models.py).
* تحديث [users/backends.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/users/backends.py) في `get_group_permissions` لتجميع الصلاحيات من الدور الأساسي `primary_role` والأدوار الثانوية `secondary_roles` بتوافق تام مع كاش الأداء الفائق $O(1)$.
* إتاحة اختيار الأدوار الثانوية في واجهة المودال وتعيين الأدوار.

#### 3. الحماية المؤسسية للتخصيصات من المسح عند إعادة البذر (`Enterprise Seed Protection`):
* تعديل [seed_clean_roles.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/users/management/commands/seed_clean_roles.py) ليدعم علم `--force-reset`:
  - عند تشغيل الأمر العادي أثناء التحديثات أو النشر، لا يتم مسح أو تصفير أي صلاحيات قام المشرف بتخصيصها للأدوار القائمة في لوحة التحكم.
  - مسح التخصيصات وإعادة الضبط الصارم يتطلب تمرير الراية صراحة: `python manage.py seed_clean_roles --force-reset`.

#### 4. تأطير أمان البيانات على مستوى النطاق والمخزن والفرع (Row-Level & Data Scoping):
* حوكمة نطاق الصلاحيات التشغيلية:
  - حصر حركة أمين المخزن على المخازن المصرح له بها (`assigned_warehouses`).
  - حصر الحركات المالية وأذونات الصرف للمحاسب على الخزن النقدية والحسابات المعتمدة له.
  - حصر مناديب المبيعات على عملاء قطاعهم البيعي المعتمد.

#### 5. تطهير واجهة إدارة الصلاحيات (`dashboard.html`) والامتثال لقواعد التصميم (Rule #2 & Rule #6):
* استئصال الـ 320 سطر CSS المدمجة داخل [dashboard.html](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/templates/users/permissions/dashboard.html) ونقل التنسيقات النظيفة إلى ملف الأنماط المعياري [unified-components.css](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/static/css/unified-components.css) مع استبدال كافة الألوان الثابتة بمتغيرات الـ `:root`.
* حذف أي أنيميشن أو تأثيرات غير مصرح بها (`pulse`, `spin` الزائد).
* تفعيل [page_header.html](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/templates/shared/page_header.html) بالمسار الكامل المعياري `breadcrumb_items` وفق Rule #6.

#### 6. تأمين بيئة الإنتاج المتعددة المعالجات (Production Multi-Worker Cache Guard):
* إضافة فحص نظامي `check_production_cache_backend` في [users/apps.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/users/apps.py) يطلق تحذيراً عند تشغيل بيئة الإنتاج (`DEBUG=False`) مع خادم كاش محلي `LocMemCache` بدلاً من خادم مركزي مثل Redis، لضمان اتساق الكاش الفوري عبر كافة الـ Workers.

#### 7. تقييد الـ Global Selectors في الجافاسكريبت:
* في [static/js/permissions-dashboard.js](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/static/js/permissions-dashboard.js):
  - تقييد دوال `selectAllPermissions` و `clearAllPermissions` وتحديد الفئات بحاوية المودال النشط حصراً لمنع التأثير على أي شاشات أو مودالات خلفية.

#### 8. القضاء على ازدواجية جداول الصلاحيات المخصصة (`Dual-Permission Redundancy Elimination`):
* توحيد الصلاحيات الفردية للمستخدم حصراً على حقل جانغو القياسي `user.user_permissions`.
* إنهاء الازدواجية في الحقل المكرر `user.custom_permissions` وتطهير التزامن المزدوج في الـ Views والباك إند والـ Prefetch في الخدمات لتوفير استعلامات قاعدة البيانات وجداول الـ M2M الزائدة.

#### 9. استئصال كوارث الـ N+1 Queries في تبويبات لوحة الصلاحيات (`users_tab.html` و `roles_tab.html`):
* في [users_tab.html](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/templates/users/permissions/tabs/users_tab.html): استبدال `user.role.permissions.count` و `user.user_permissions.count` بحقول محملة مسبقاً أو تجميعية `.annotate()` في استعلام المستخدمين.
* في [roles_tab.html](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/templates/users/permissions/tabs/roles_tab.html): استبدال `{{ role.permissions.count }}` بـ `.annotate(permissions_count=Count('permissions'))` لمنع ضرب الداتابيز لكل كارت دور.

#### 10. التحميل الذكي للتبويبات حسب الطلب (`Tab Lazy / On-Demand Loading`):
* تعديل دالة `permissions_dashboard` في [users/permissions_views.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/users/permissions_views.py):
  - تحميل بيانات التبويب النشط فقط (وفق باراميتر `tab`) بدلاً من السحب المتزامن الثقيل لكافة الأدوار، والمستخدمين، وسجلات المراقبة `ActivityLog` لـ 30 يوماً في كل طلب GET.

#### 11. تفكيك قيد أسماء الأدوار المشفرة في منطق الأعمال (`De-hardcoding Role Names`):
* استبدال الاعتماد الحصري على `role.name == 'sales_rep'` أو `is_sales_rep` في النماذج والـ Views بفحص الصلاحيات الوظيفية الصريحة (`has_perm('sale.add_sale')` و `has_perm('sale.view_own_sales')`) لتمكين إنشاء أدوار مبيعات أو مشتريات مخصصة جديدة والعمل بكفاءة دون الحاجة لتعديل الكود المصدري.

#### 12. شريط البحث اللحظي وتيسير واجهة المودالات (Permission Live Search Filter):
* إضافة حقل بحث فوري لحظي سريع في رأس [edit_user_permissions_modal.html](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/templates/users/permissions/modals/edit_user_permissions_modal.html)، [role_create_modal.html](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/templates/users/permissions/modals/role_create_modal.html)، و [role_edit_modal.html](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/templates/users/permissions/modals/role_edit_modal.html).
* تصفية الـ 350+ صلاحية أثناء الكتابة فورياً وفق الاسم المعروض أو الكود التقني دون الحاجة للتمرير العشوائي المرهق.

#### 13. سجل التدقيق الجنائي وتتبع الفروقات (Forensic Audit Trail & Diff Tracking):
* توحيد تسجيل كافة عمليات تعديل الصلاحيات المخصصة عبر [AuditService](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/governance/services/audit_service.py) و `ActivityLog`.
* توثيق الفارق الدقيق بالأسماء القياسية (`app_label.codename`) قبل وبعد:
  - `added_permissions`: قائمة الصلاحيات التي تم منحها للموظف.
  - `removed_permissions`: قائمة الصلاحيات التي سُحبت منه.
  بدلاً من مجرد أرقام IDs مجردة أو عدادات رقمية عمياء، لتحقيق الامتثال الجنائي والمحاسبي الصارم.

#### 14. تأمين واجهات الـ REST API واستئصال تسريب المستخدمين وبقايا `is_staff`:
* تصحيح Endpoint المناديب `salesmen` في [api/viewsets.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/api/viewsets.py) ليقتصر حصراً على من يملك أدوار أو صلاحيات مبيعات حقيقية بدلاً من كشف جميع مستخدمي الشركة لأي حساب مسجل.
* استئصال آخر بقايا لشرط `is_staff` في [api/permissions.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/api/permissions.py) داخل `IsOwnerOrReadOnly` لضمان التطهير الأمني الكامل.

#### 15. دعم الهرمية والوراثة في الأدوار المؤسسية (Role Hierarchy & Inheritance):
* إضافة حقل الدور الأب `parent_role = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='child_roles')` في [users/models.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/users/models.py).
* دعم تجميع الصلاحيات الهرمي في [users/backends.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/users/backends.py) بحيث يرث دور مثل مدير المبيعات `sales_manager` صلاحيات المندوب `sales_rep` تلقائياً دون الحاجة لتكرار إدخالها عند كل تعديل.

---

## 3. خطة التحقق الشاملة (Automated Test Suites via Pytest)

### 3.1. حزمة اختبارات المعمارية العامة (General Architecture Test Suite)
ملف الاختبار: [users/tests/test_enterprise_rbac.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/users/tests/test_enterprise_rbac.py):
1. **اختبار خلو النظام من qrapplication**: التأكد من عدم وجود أي مراجع أو استعلامات لـ `qrapplication` وتطهير الداتابيز منها.
2. **اختبار تطهير اختطاف الكلاسات في إعدادات التسعير**: التأكد من أن مسؤول التسعير يدير إعدادات الخامات والماكينات بصلاحية `printing_pricing.manage_pricing_settings` دون اشتراط `is_staff`.
3. **اختبار تصفية طلبات التسعير بالصلاحية وليس بـ is_staff**: التأكد من أن مشرف التسعير يرى كافة الطلبات بصلاحية `printing_pricing.view_all_orders`.
4. **اختبار تطابق مسميات الـ Web والـ API**: التأكد من أن `hr.approve_leave` تعمل بتطابق تام بين شاشات الويب وواجهات الـ REST API.
5. **اختبار كاش الأداء الفائق وتطهير الكاش**: التأكد من ربط `RolePermissionBackend` مع `PermissionCacheService` وتنفيذ استعلام واحد فقط عند فحص 50 صلاحية وتفريغه الفوري عند التعديل.
6. **اختبار محاكاة المستخدم (Login As User)**: التأكد من أن تسجيل الدخول بحساب موظف يحاكي بدقة متناهية صلاحيات الدور المخصص له.
7. **اختبار إغلاق ثغرة الـ REST API**: التأكد من أن طلبات GET على `/api/journal-entries/` و `/api/chart-of-accounts/` تُرفض بـ 403 لمن لا يملك الصلاحية.
8. **اختبار عزل فواتير المناديب**: التأكد من أن المندوب يرى فواتيره فقط، بينما المشرف يرى فواتير جميع المناديب.
9. **اختبار حماية تغيير مسؤول المبيعات**: التأكد من منع المندوب العادي من تعديل حقل مسؤول المبيعات لنفسه أو لزملائه، وسماحه للمشرف فقط.
10. **اختبار انضباط Context Processors**: التحقق من دقة حساب عدد طلبات الاعتماد المعلقة للمدير المالي دون أي كويريز مكررة.
11. **اختبار ترقية الأدوار القائمة ومزامنة المستخدمين**: التأكد من ترقية الأدوار واحتفاظ حساب `mwheba` وحساب `admin` بكافة إمكانيات التشغيل الإدارية دون تناقض مع `user_type`.
12. **اختبار حماية الأسعار عبر كامل السلسلة التجارية**: التحقق من رفض أي محاولة تلاعب بالأسعار في الباك إند لمن لا يملك `sale.change_unit_price` عبر المراحل الثلاث (عروض الأسعار $\leftarrow$ أوامر البيع $\leftarrow$ فواتير البيع).
13. **اختبار سرية هوامش أرباح المطبعة**: التأكد من حجب هوامش الأرباح وتفاصيل تكلفة الورق عن مسؤول المبيعات، وظهورها للمدير المالي.
14. **اختبار فك ارتباط أوامر الشغل وتطهير قوالب الإنتاج**: تمكن مسؤول الإنتاج من فتح أمر الشغل الفني بصلاحية `work_order.view_workorder` فقط دون الحاجة لصلاحية المبيعات، مع حجب الأسعار والتكاليف في قوالب الشغل.
15. **اختبار حظر الدخول غير المصرح**: التأكد من إرجاع `403` على كافة الـ Views المقفلة عند محاولة الوصول المباشر بالـ URL أو الـ AJAX.
16. **اختبار عزل التطبيقات الصارم في الباك إند**: التأكد من أن سطر تجريد التطبيقات القديم قد تم القضاء عليه، وأن امتلاك `printing_pricing.view_order` لا يمنح أي وصول إطلاقاً لـ `sale.view_order`.
17. **اختبار التزام دالة User.get_all_permissions بعقد جانغو**: التأكد من أن إرجاع دالة `request.user.get_all_permissions()` هو مجموعة نصوص قياسية `set[str]` بصيغة `'app_label.codename'`.
18. **اختبار طبقة التوافق العكسي**: التأكد من أن أي استعلام قديم بصيغة `has_perm('users.ادارة_المبيعات')` يُترجم بنجاح إلى `sale.view_sale` و `sale.add_sale` لضمان صفر انكسارات.

### 3.2. حزمة اختبارات التدقيق الشاملة والإنفاذ الحازم (Phase 3 Comprehensive Enforcement Suite)
ملف الاختبار: [users/tests/test_rbac_phase3_enforcement.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/users/tests/test_rbac_phase3_enforcement.py) (18 سيناريو اختبار صارم):
1. `test_ghost_roles_purged_and_display_names_utf8_clean`: التحقق من استئصال الأدوار الميتة الخمسة وتصحيح ترميز أسماء الأدوار العربية بـ UTF-8 في جدول `users_role`.
2. `test_sales_rep_has_currency_and_warehouse_read_permissions`: التحقق من سد فجوة المناديب الرقمية وامتلاكهم لقراءة العملات والمخازن والوحدات والضرائب.
3. `test_purchase_change_unit_cost_permission_enforced`: التحقق من حظر التلاعب في تكلفة شراء الأصناف والخامات بدون `purchase.change_unit_cost`.
4. `test_purchase_approve_permission_enforced`: التحقق من حظر ترحيل واعتماد فواتير الشراء بدون `purchase.approve_purchase`.
5. `test_accounting_immutability_blocks_direct_posted_cancellation`: التحقق من حظر الإلغاء المباشر للمستندات المرحلة وفرض مسار القيود العكسية والمردودات.
6. `test_permission_codenames_exact_match_with_underscores`: التحقق من تطابق أسماء الصلاحيات مع الـ underscores (`close_accounting_period`, `post_journal_entry`).
7. `test_explicit_data_migration_creates_permissions`: التحقق من نجاح هجرة البيانات الصريحة عبر `RunPython` وإنشاء الصلاحيات في `auth_permission`.
8. `test_currency_dependency_implicitly_injected_for_sales_and_procurement`: التحقق من حقن `financial.view_currency` تلقائياً لمن يملك صلاحيات مبيعات أو مشتريات.
9. `test_superuser_permission_check_executes_zero_permission_queries`: التحقق من أن فحص صلاحيات السوبر يوزر والمدير يعمل بـ 0 استعلامات زائدة $O(1)$ دون سحب جدول الصلاحيات.
10. `test_tier2_cache_integration_avoids_duplicate_db_queries`: التحقق من ربط كاش الطبقة الثانية بـ `django.core.cache` وتفريغه عند تعديل الدور.
11. `test_user_model_delegates_permissions_to_backend`: التحقق من توحيد مصدر الصلاحيات وتفويض الموديل للباك إند.
12. `test_period_close_blocked_at_service_layer_without_permission`: التحقق من حظر إغلاق الفترة في طبقة الخدمات لمن لا يملك الصلاحية.
13. `test_period_close_blocked_if_unposted_drafts_exist`: التحقق من رفض إغلاق الفترة في حال وجود مسودات غير معتمدة.
14. `test_fx_revaluation_and_manual_rate_lock`: التحقق من قصر إعادة التقييم IAS 21 وقفل سعر الصرف اليدوي على الصلاحيات المخصصة.
15. `test_purchase_endpoints_require_permissions`: التحقق من حماية فواتير وأوامر الشراء بالصلاحيات المعيارية.
16. `test_grn_blind_receiving_masks_prices_for_warehouse_officer`: التحقق من حجب أسعار الشراء عن أمين المخزن في الـ GRN.
17. `test_credit_limit_exceeded_creates_pending_approval_sale`: التحقق من مسار حفظ الفاتورة كـ "مسودة معلقة للاعتماد" عند تجاوز الائتمان.
18. `test_impersonation_logs_activity_and_tracks_ajax_delegation`: التحقق من توثيق الانتحال في طلبات الـ AJAX وفي `ActivityLog`.

### 3.3. حزمة اختبارات المرحلة التاسعة: الانتحال القانوني وإنفاذ القوالب ومصفوفة الشخصيات (Phase 9 Suite)
ملف الاختبار: [users/tests/test_rbac_phase9_personas_and_ui.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/users/tests/test_rbac_phase9_personas_and_ui.py) (28 سيناريو اختبار صارم بنسبة نجاح 100%):
1. `TestImpersonationSecurity`:
   - توثيق النشاط وسجل التدقيق القانوني (`ActivityLog: IMPERSONATION_START / IMPERSONATION_STOP`).
   - حقن وترويسة الأمان `X-Impersonated-By` وتتبع الـ Thread-Local عبر `core/middleware/current_user.py`.
   - استرجاع حساب المشرف وتنظيف الجلسة والكاش بنظافة عند إنهاء الانتحال.
   - حظر أمني لانتحال السوبر يوزر الآخر وحظر الانتحال المتداخل (Nested Impersonation Block).
   - حظر المستخدمين العاديين من استدعاء ميزة الانتحال.
2. `TestDetailViewsDomGating`:
   - حجب أزرار التعديل والحذف وروابط الـ DOM في فواتير المبيعات، فواتير الشراء، العملاء، والموردين عن مستخدم الاستعلام (`viewer`).
   - إخفاء خيارات الحذف للمستندات المقفلة محاسبياً (مثل الفواتير المدفوعة) حتى للمشرف التزاماً بدورة حياة المستند وثبات الدفاتر.
3. `TestSidebarGating`:
   - خلو القائمة الجانبية من تسريب السياسات السعرية لمناديب المبيعات.
   - خلو القائمة الجانبية من تسريب إعدادات الموارد البشرية لمستخدمي الاستعلام.
4. `TestRolesIntegrity`:
   - التحقق من وجود الأدوار العشرة القياسية وتعيينها كأدوار نظام محمية (`is_system_role=True`).
5. `TestAdditionalDetailViewsGating`:
   - تطهير عروض الأسعار (`Quotation`) وأوامر الشغل (`WorkOrder`) من أزرار التعديل والتحويل والحذف لغير المصرح لهم.
   - قفل تعديل أوامر الشغل المنتهية (`completed`).
6. `TestPermissionsDashboardAndPersonas`:
   - حظر غير المشرفين من لوحة إدارة الصلاحيات وتوفر زر الانتحال في جدول المستخدمين.
   - التحقق من تكامل صلاحيات المحاسب، مندوب المبيعات، أمين المخازن، مسؤول الموارد البشرية، والمدير المالي.
   - التحقق من دورة حياة وتفريغ كاش الصلاحيات `PermissionCacheService`.

### 3.4. حزمة اختبارات المرحلة العاشرة: تعدد الأدوار والوراثة الهرمية وحظر الصلاحيات المباشر (Phase 10 Suite)
ملف الاختبار: [users/tests/test_rbac_phase10_multi_role_and_ui.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/users/tests/test_rbac_phase10_multi_role_and_ui.py) (16 سيناريو اختبار صارم بنسبة نجاح 100%):
1. `TestPhase10MultiRoleAndHierarchy`:
   - التحقق من تجميع صلاحيات الأدوار الثانوية المتعددة (`secondary_roles`) مع الدور الأساسي.
   - التحقق من توريث صلاحيات الدور الأب بشكل تكراري شجري عالي الكفاءة (`parent_role`).
   - التحقق من تفريغ كاش الصلاحيات اللحظي عند تعديل علاقات الأدوار الثانوية.
2. `TestPhase10ExplicitRevocations`:
   - التحقق من الإنفاذ الفوري لحظر الصلاحيات الصريح (`revoked_permissions`) وتجاوزه لصلاحيات الأدوار الممنوحة.
   - عزل واستثناء المشرفين المطلقين (`is_superuser`) من الحظر البرمجي العرضي.
3. `TestPhase10ApiSecurity`:
   - قفل وتأمين مسارات الـ API الإدارية (`/users/api/user-roles/`, `/users/api/user-permissions/`) وحصرها على المشرفين.
   - توثيق كافة التعديلات في سجل التدقيق المؤسسي `ActivityLog` مع بصمة الـ IP ومسؤول التعديل.

### 3.5. حزمة اختبارات المرحلة الحادية عشرة: عزل نطاق البيانات، تعزيز الأمان، وشجرة التبعيات المحوكمة (Phase 11 Suite)
ملف الاختبار: [users/tests/test_rbac_phase11_data_scoping_and_dependencies.py](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/users/tests/test_rbac_phase11_data_scoping_and_dependencies.py) (9 سيناريوهات اختبار دقيقة بنسبة نجاح 100%):
1. `test_sales_scoping_for_salesman`:
   - عزل فواتير المبيعات للمندوب العادي وحصرها على فواتيره الخاصة فقط.
2. `test_sales_scoping_for_accountant`:
   - إعفاء المحاسبين والمديرين الماليين من العزل لضمان انسيابية القيود وسندات القبض.
3. `test_quotation_and_sales_order_scoping`:
   - عزل عروض الأسعار وأوامر البيع بنطاق المستخدم المندوب أو منشئ المستند مع دعم المشرفين.
4. `test_managed_warehouses_scoping`:
   - قصر أذون الصرف والتحويل المخزني على المخازن التابعة للمستخدم فقط مع الالتزام التام بمصطلح «مخزن / مخازن».
5. `test_transfer_voucher_form_warehouse_scoping`:
   - تقييد حقول نماذج التحويل المخزني برمجياً في الباك إند (`TransferVoucherForm`).
6. `test_credit_note_scoping`:
   - عزل إشعارات الخصم والإضافة (`CreditNote`) ومردودات المبيعات وحمايتها بصلاحيات تفصيلية.
7. `test_transition_dependencies`:
   - سحب وحل التبعيات التلقائية للعمليات الانتقالية المركبة (مثل تحويل عروض الأسعار لأوامر بيع وفواتير).
8. `test_role_comparison_structure`:
   - التحقق من سلامة هيكل مقارنة الأدوار المجمعة حسب التطبيق (`app_label`) لدعم نافذة المقارنة التفاعلية.
9. `test_role_export_payload`:
   - التحقق من سلامة حزم التصدير كملف JSON آمن ومطابق للمواصفات القياسية.

---

### المرحلة الثانية عشرة (Phase 12: Production Orders, Business Partners & Financial Governance Hardening)
تتويج المنظومة بإغلاق كافة الثغرات البرمجية في صالة الإنتاج، تسعير الطباعة، شركاء الأعمال (العملاء والموردين)، وإحكام الحوكمة المالية لشجرة الحسابات وإلغاء ترحيل القيود عبر 4 حزم معمارية متكاملة:

#### 1. حزمة صالة الإنتاج وتسعير الطباعة (Package 1: Production & Printing Order Governance)
* **حوكمة مركز تكلفة أوامر الشغل (`work_order_detail`)**:
  - فحص الصلاحيات المالية للمستخدم (`can_view_financials`) وحجب تنفيذ استعلامات قواعد البيانات الخمسة الثقيلة (`sales`, `purchases`, `financial_transactions`, `incomes_direct`, `expenses_direct`) وضبط مجاميع التكاليف والأرباح بـ `None` لغير المصرح لهم لحماية الأداء والسرية المحاسبية.
  - تأمين تسجيل الدفعات المقدمة (`work_order_record_deposit`) واستئصال الاعتماد على `is_admin` والتحقق الصارم من صلاحيات الدفعات.
  - قفل تعديل أوامر الشغل المنتهية أو الملغاة (`completed`, `cancelled`) ومنع تجاوزها برمجياً لغير السوبر يوزر.
* **حوكمة عروض أسعار الطباعة (`printing_pricing/views/order_views.py`)**:
  - منع الاعتماد الذاتي (`approve_order`): حظر قيام المندوب أو منشئ الطلب باعتماد طلبه بنفسه (`order.created_by == request.user and not is_manager`).
  - حجب التكاليف وهوامش الأرباح في حساب التكلفة (`calculate_order_cost`): إعادة `0.0` لحقول التكلفة والهوامش مع الحفاظ على كائن الـ JSON وعدم كسر الـ Frontend.
  - تأمين نسخ طلبات التسعير (`duplicate_order`): اشتراط صلاحية `printing_pricing.add_pricingorder`.

#### 2. حزمة مدير الأسعار وحركات المخازن الموجهة (Package 2: Unified Price Manager & Movement Scoping)
* **حوكمة مدير الأسعار الموحد (`price_manager_views.py`)**:
  - حماية شاشة العرض بصلاحية `product.view_product`.
  - حماية التحديث الفردي والجماعي للأسعار بصلاحية `product.change_product` مع المعاملات الذرية `transaction.atomic()`.
  - التوثيق الصارم في سجل تاريخ الأسعار الموحد `PricingService.log_price_change` عند كل تعديل لسعر البيع أو التكلفة.
  - تعطيل حقول الإدخال في القالب (`disabled readonly`) للمستخدمين غير المصرح لهم.
* **حوكمة أذون الاستلام والصرف والتسوية المخزنية**:
  - عزل المخازن المصرح بها للمستخدم عبر `DataScopingService.get_managed_warehouses` في كافة شاشات أذون الصرف والاستلام المفردة والمجمعة لمنع التلاعب (BOLA).
  - حماية شاشة التسوية المخزنية `stock_adjust` بصلاحية `product.approve_inventory_adjustment` أو `product.change_stock` وقصر المخازن على المعتمدة.

#### 3. حزمة شركاء الأعمال: العملاء والموردين (Package 3: Business Partners Governance)
* **حوكمة إدارة العملاء والحد الائتماني**:
  - حماية `customer_edit` بصلاحية `customer.change_customer`.
  - تأمين `customer_add_ajax` بصلاحية `customer.add_customer` وضبط `return_json=True` لردود الـ AJAX.
  - تأمين حقول سقف الائتمان وحالة الائتمان وفئة المخاطر في `CustomerForm` في الباك إند ومنع التلاعب بها عبر أدوات المطورين أو الطلبات المباشرة، مع إعادة القيمة للقيمة الأصلية إن لم يكن المستخدم مديراً مالياً.
  - حماية Endpoint أعمار الديون `customer_aging_api` بصلاحية `customer.view_customer`.
* **حوكمة خدمات وأسعار الموردين (`supplier/views.py`)**:
  - تأمين 10 نهايات طرفية (Endpoints) لخدمات الموردين وشرائح الأسعار وأعمار ديون الموردين بصلاحيات `supplier.change_supplier` و `supplier.view_supplier`.

#### 4. حزمة الحوكمة المالية والخزائن (Package 4: Financial & Treasury Governance)
* **حوكمة دليل وشجرة الحسابات (`financial/views/account_views.py`)**:
  - تأمين عمليات الإضافة والتعديل والحذف بصلاحيات `add_chartofaccounts`, `change_chartofaccounts`, `delete_chartofaccounts`.
  - تأمين التحويل المالي بين الخزائن والحسابات البنكية (`transfer_between_accounts`) بصلاحية `financial.add_journalentry` المحاسبية.
  - حظر حذف أي حساب يمتلك حسابات فرعية أو قيود يومية لحماية شجرة الحسابات والثبات المحاسبي.
* **حوكمة إلغاء ترحيل القيود اليومية (`financial/views/transaction_views.py`)**:
  - حصر إلغاء ترحيل القيود اليومية `journal_entries_unpost` حصرياً بالمدير المالي أو السوبر يوزر أو من يحمل صلاحية `financial.unpost_journal_entry`.
  - ربط أزرار الإجراءات في القوالب بالصلاحيات بدقة.

#### 5. تغطية الاختبارات الآلية للمرحلة 12 (100% Pass):
ملف الاختبار: [users/tests/test_rbac_phase12_production_partners_and_financial.py](file:///c:/Users/UTD/Desktop/MWHEBA ERP/users/tests/test_rbac_phase12_production_partners_and_financial.py) (10 سيناريوهات متقدمة بنسبة نجاح 100%):
1. `test_work_order_detail_masks_financial_metrics_from_operator`: حجب المؤشرات واستعلامات التكاليف عن المشغل.
2. `test_printing_order_blocks_self_approval`: منع الاعتماد الذاتي للمندوب.
3. `test_printing_order_calculate_cost_masks_margins_for_unauthorized`: حجب نسب وهوامش الأرباح بدون كسر الـ Schema.
4. `test_price_manager_view_and_update_rbac`: اشتراط الصلاحيات لمدير الأسعار والتحديث الذري.
5. `test_receipt_voucher_warehouse_scoping`: عزل أذون الاستلام المخزنية حسب المخازن المصرح بها.
6. `test_supplier_aging_api_requires_view_permission`: حماية كشف أعمار ديون الموردين.
7. `test_price_tier_add_requires_change_supplier_permission`: حماية إضافة شرائح أسعار الموردين.
8. `test_customer_form_credit_limit_backend_tamper_protection`: حماية سقف الائتمان من التلاعب البرمجي في النموذج لمستخدم غير مصرح.
9. `test_batch_voucher_approve_warehouse_scoping`: عزل اعتماد الإذن الجماعي وحظر الاعتماد لمخزن غير مسند مع الرد بـ 403 AJAX.
10. `test_transfer_between_accounts_requires_permission`: اشتراط الصلاحية المحاسبية للتحويل بين الخزائن.
11. `test_journal_entry_unpost_restricted_to_financial_manager`: قصر إلغاء الترحيل على المدير المالي.

---

## 4. أوامر التحقق والتشغيل الإلزامية
```powershell
# 1. تشغيل اختبارات المرحلة الثانية عشرة بمفردها (11 اختباراً)
pytest users/tests/test_rbac_phase12_production_partners_and_financial.py -v

# 2. تشغيل كافة اختبارات الأمان والصلاحيات مجمعة (221 اختباراً عبر كافة المراحل)
pytest users/tests/test_rbac_*.py -q

# 3. فحص سلامة النظام الشاملة لجانغو
python manage.py check
```

