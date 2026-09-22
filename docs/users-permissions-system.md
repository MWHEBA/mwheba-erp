# كتيب المطور للأدوار والصلاحيات والرقابة الأمنية (RBAC & Security Reference) 🔐

> **مرجع تنفيذي شامل للمطورين في MWHEBA ERP** يوثق نظام الـ 10 أدوار القياسية، نطاقات رؤية البيانات (Data Visibility Scopes)، وصلاحيات الخزن والمخازن.
> ⚠️ **تنبيه معماري**: المرجع المعماري والأمني الشامل هو: 📘 **[وثيقة الخطة الشاملة المتكاملة لنظام الصلاحيات والحوكمة (RBAC Master Plan v7)](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/docs/architecture/RBAC_MASTER_PLAN.md)**.

---

## 1. الركائز الأساسية لنظام الصلاحيات

1. **الامتثال الكامل لعقد جانغو القياسي**: يتم فحص الصلاحيات حصراً عبر الصيغة المعيارية لجانغو: `'app_label.codename'`.
2. **استئصال تام لـ `user_type`**: لا يوجد أي حقل اسمه `user_type` في نموذج `User`؛ الاعتماد بنسبة 100% على الصلاحيات والأدوار الموحدة.
3. **أداء فائق واستجابة لحظية $O(1)$**: يعتمد النظام على `RolePermissionBackend` الذي يقوم بعمل كاش لحظي لكافة صلاحيات المستخدم على مستوى الطلب الواحد (`request.user._cached_group_permissions`) بدون استعلامات SQL متكررة.

---

## 2. جدول الأدوار المؤسسية الـ 10 (Standard Enterprise Roles)

| الدور البرمجي (`role.name`) | الاسم المعروض | الخاصية في الموديل (`User`) | النطاق الوظيفي الأساسي |
|---|---|---|---|
| `admin` | مدير النظام | `user.is_admin` | صلاحيات إدارية وتشغيلية شاملة |
| `financial_manager` | المدير المالي | `user.is_financial_manager` | إدارة الحسابات، قفل الفترات، واعتماد فروق العملة |
| `accountant` | محاسب | `user.is_accountant` | تسجيل القيود اليومية، مراجعة المدفوعات، وسندات القبض والصرف |
| `sales_manager` | مدير المبيعات | `user.is_sales_manager` | اعتماد عروض الأسعار، متابعة المناديب، وإدارة قوائم الأسعار |
| `sales_rep` | مندوب مبيعات | `user.is_sales_rep` | إنشاء عروض الأسعار وفواتير المبيعات (ضمن نطاق سجلاته فقط) |
| `procurement_officer` | مسؤول المشتريات | `user.is_procurement_officer` | أوامر الشراء، متابعة الموردين، وإدخال فواتير المشتريات |
| `inventory_manager` | أمين المخزن | `user.is_inventory_manager` | حركات المخزن، أذون الصرف والإضافة، والجرد المخزني |
| `production_supervisor` | مشرف الإنتاج | `user.is_production_supervisor` | متابعة أوامر الشغل (`work_order`) ومراحل الماكينات بصالة الإنتاج |
| `hr_officer` | مسؤول الموارد البشرية | `user.is_hr_officer` | الموظفين، عقود العمل، الحضور والبصمة، ومسيرات الرواتب |
| `viewer` | مستعرض فقط | `user.is_viewer` | صلاحيات استعلام وقراءة فقط دون أي صلاحية تعديل أو إضافة |

---

## 3. نطاقات رؤية البيانات (Data Visibility Scopes)

يحدد النظام مدى رؤية المستخدم للبيانات في صفحات القوائم والتقارير:

1. **النطاق الشامل (Global Scope):** للمديرين والمدير المالي لرؤية كافة الفروع والمخازن والمناديب.
2. **نطاق المخزن / الفرع (Warehouse / Branch Scope):** لأمناء المخازن ومشرفي الإنتاج لعرض السجلات المرتبطة بمخزنهم المعين فقط.
3. **نطاق السجلات الخاصة (Own Records Scope):** لمناديب المبيعات حيث تقتصر رؤيتهم على عروض الأسعار والفواتير التي قاموا بإنشائها فقط.

---

## 4. صلاحيات وأمان الخزن النقدية والمخازن (Treasury & Warehouse Security)

* **صلاحيات الخزن النقدية (`TreasurySecurityService`):**
  * لا يمكن لأي مستخدم الصرف أو التحصيل من خزينة إلا إذا كان معيناً عليها كمسؤول خزينة أو يمتلك صلاحية `financial.manage_all_treasuries`.
  * حماية حركات الخزينة من التداخل وقفل الأرصدة لحظياً.
* **صلاحيات المخازن الموحدة:**
  * تقييد أذون الإضافة والصرف المخزني بأمين المخزن المعتمد.
  * **التزام التسمية الموحدة:** يُمنع تماماً استخدام كلمة «مستودع» ويتم الالتزام حصراً بـ «مخزن / مخازن / أمين المخزن».

---

## 5. دليل فحص الصلاحيات للمطورين (Developer Cheatsheet)

### أ) في دوال وعروض بايثون (Views):
```python
from django.contrib.auth.decorators import permission_required

@permission_required('sale.add_sale', raise_exception=True)
def create_sale_view(request):
    ...
```

### ب) في القوالب (Templates):
```django
{% if perms.sale.add_sale %}
    <a href="{% url 'sale:sale_create' %}" class="btn btn-primary">
        <i class="fas fa-plus me-1"></i> إنشاء فاتورة جديدة
    </a>
{% endif %}
```

### ج) في واجهات الـ REST API (DRF):
```python
from rest_framework.viewsets import ModelViewSet
from api.permissions import RoleBasedModelPermissions

class SaleViewSet(ModelViewSet):
    permission_classes = [RoleBasedModelPermissions]
    ...
```