# كتيب المطور السريع للأدوار والصلاحيات (RBAC Developer Reference & Cheatsheet) 🔐

> **مرجع تنفيذي سريع للمطورين في MWHEBA ERP**  
> ⚠️ **تنبيه معماري**: المرجع المعماري والأمني النهائي والشامل المعتمد للمنصة هو:  
> 📘 **[وثيقة الخطة الشاملة المتكاملة لنظام الصلاحيات والحوكمة (RBAC Master Plan v7)](file:///c:/Users/UTD/Desktop/MWHEBA%20ERP/docs/architecture/RBAC_MASTER_PLAN.md)**.

---

## 1. الركائز الأساسية لنظام الصلاحيات

1. **الامتثال الكامل لعقد جانغو القياسي**: يتم فحص الصلاحيات حصراً عبر الصيغة المعيارية لجانغو: `'app_label.codename'`.
2. **استئصال تام لـ `user_type`**: لا يوجد أي حقل اسمه `user_type` في نموذج `User` أو أي فحص برمجي له في الكود؛ الاعتماد بنسبة 100% على الصلاحيات والأدوار الموحدة.
3. **أداء فائق واستجابة لحظية $O(1)$**: يعتمد النظام على `RolePermissionBackend` الذي يقوم بعمل كاش لحظي لكافة صلاحيات المستخدم على مستوى الطلب الواحد (`request.user._cached_group_permissions`) بصفر استعلامات SQL متكررة داخل الريكويست.

---

## 2. جدول الأدوار المؤسسية القياسية الـ 10 (Standard Enterprise Roles)

يحتوي النظام على **10 أدوار قياسية** موحدة تترجم إلى خصائص مساعدة مباشرة على كائن المستخدم `User`:

| الدور البرمجي (`role.name`) | الاسم المعروض | الخاصية في كود الموديل (`User`) | النطاق الوظيفي الأساسي |
|---|---|---|---|
| `admin` | مدير النظام | `user.is_admin` | صلاحيات إدارية وتشغيلية شاملة |
| `financial_manager` | المدير المالي | `user.is_financial_manager` | إدارة الحسابات، قفل الفترات، واعتماد فروق العملة IAS 21 |
| `accountant` | محاسب | `user.is_accountant` | تسجيل القيود اليومية، مراجعة المدفوعات، وسندات القبض والصرف |
| `sales_manager` | مدير المبيعات | `user.is_sales_manager` | اعتماد عروض الأسعار، متابعة المناديب، وإدارة قوائم الأسعار |
| `sales_rep` | مندوب مبيعات | `user.is_sales_rep` | إنشاء عروض الأسعار وفواتير المبيعات (مع عزل سجلاته فقط) |
| `procurement_officer` | مسؤول المشتريات | `user.is_procurement_officer` | أوامر الشراء، متابعة الموردين، وإدخال فواتير المشتريات |
| `inventory_manager` | أمين المخزن | `user.is_inventory_manager` | حركات المخزن، أذون الصرف والإضافة، والجرد المخزني |
| `production_supervisor` | مشرف الإنتاج | `user.is_production_supervisor` | متابعة أوامر الشغل (`work_order`) ومراحل الماكينات بصالة الإنتاج |
| `hr_officer` | مسؤول الموارد البشرية | `user.is_hr_officer` | الموظفين، عقود العمل، الحضور والبصمة، ومسيرات الرواتب |
| `viewer` | مستعرض فقط | `user.is_viewer` | صلاحيات استعلام وقراءة فقط دون أي صلاحية تعديل أو إضافة |

---

## 3. دليل فحص الصلاحيات للمطورين (Developer Code Cheatsheet)

### أ) في دوال وعروض بايثون (Views)

#### 1. استخدام الديكوريتور القياسي `@permission_required`:
```python
from django.contrib.auth.decorators import permission_required

@permission_required('sale.add_sale', raise_exception=True)
def create_sale_view(request):
    # منطق إنشاء الفاتورة
    ...
```

#### 2. الفحص اليدوي المباشر داخل الـ View:
```python
def print_work_order(request, pk):
    # الفحص الصارم للصلاحية المعيارية
    if not request.user.has_perm('work_order.view_workorder'):
        raise PermissionDenied("ليس لديك صلاحية استعراض أمر الشغل")
    ...
```

#### 3. في Class-Based Views باستخدام `PermissionRequiredMixin`:
```python
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.views.generic import ListView
from work_order.models import WorkOrder

class WorkOrderListView(PermissionRequiredMixin, ListView):
    model = WorkOrder
    permission_required = 'work_order.view_workorder'
    template_name = 'work_order/work_order_list.html'
```

---

### ب) في قوالب العرض (Django Templates)

استخدم كائن `perms` القياسي الذي يوفره جانغو تلقائياً:

```django
<!-- إظهار زر إضافة فاتورة فقط لمن يملك الصلاحية -->
{% if perms.sale.add_sale %}
    <a href="{% url 'sale:sale_create' %}" class="btn btn-primary">
        <i class="fas fa-plus me-1"></i> إنشاء فاتورة جديدة
    </a>
{% endif %}

<!-- إخفاء هوامش الأرباح وتكاليف الخامات عن مناديب المبيعات -->
{% if perms.printing_pricing.view_profit_margins %}
    <div class="cost-breakdown-card">
        <h6>صافي هامش الربح: {{ order.profit_margin }}%</h6>
    </div>
{% endif %}
```

---

### ج) في واجهات الـ REST API (Django REST Framework)

استخدم كلاس الصلاحيات المؤسسي `RoleBasedModelPermissions`:

```python
from rest_framework.viewsets import ModelViewSet
from core.api_permissions import RoleBasedModelPermissions
from sale.models import Sale
from sale.serializers import SaleSerializer

class SaleViewSet(ModelViewSet):
    queryset = Sale.objects.all()
    serializer_class = SaleSerializer
    permission_classes = [RoleBasedModelPermissions]
    # يفرض فحص الصلاحية على عمليات القراءة والكتابة معاً
```

---

## 4. محرك الباك إند المعياري (`RolePermissionBackend`)

* **الموقع**: `users/backends.py`
* **آلية العمل**:
  1. عند طلب فحص صلاحية `request.user.has_perm('sale.add_sale')`، يستدعي جانغو `RolePermissionBackend.has_perm()`.
  2. إذا كان المستخدم `is_superuser`، يرجع `True` فوراً.
  3. يفحص الكاش اللحظي للريكويست: إذا تم تحميل الصلاحيات مسبقاً، يسترجعها من الذاكرة في زمن $O(1)$.
  4. إذا لم تكن بالكاش، يجلب صلاحيات دور المستخدم الأساسي `user.role.permissions` مع الصلاحيات الإضافية المخصصة `user.custom_permissions` في استعلام SQL وحيد باستخدام `select_related('content_type')`.
  5. يخزن الصلاحيات في `_cached_group_permissions` كـ `set[str]` بصيغة `'app_label.codename'`.

---

## 5. قواعد ذهبية لحماية النظام (Security Checklist)

1. **لا تختبر المسميات إطلاقاً**: ممنوع كتابة `if user.role.name == 'sales_rep'` لتحديد مسار الأعمال، استخدم دائماً الصلاحية المعيارية `if user.has_perm('sale.view_all_sales')`.
2. **عزل ملكية السجلات (Object Ownership)**: مندوب المبيعات لا يرى إلا فواتيره التي أنشأها بنفسه (`created_by == request.user`)، بينما مدير المبيعات يملك صلاحية `sale.view_all_sales` لرؤية فواتير الفريق بالكامل.
3. **حماية أسرار التسعير في المطبعة**: شاشات الإنتاج والماكينات (`work_order`) يجب أن تخلو تماماً من أي أسعار بيع، تكاليف ورق، أو هوامش ربح؛ الرؤية المالية حصرية لحاملي صلاحيات الإدارة المالية.