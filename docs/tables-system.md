# نظام الجداول الموحد

## مقدمة

هذا النظام يوفر طريقة موحدة لعرض جداول البيانات في التطبيق، ويستخدم تنسيقات موحدة تناسب كافة أنواع البيانات مثل المعاملات المالية، المنتجات، العملاء، وغيرها. 

يتكون النظام من:

1. **قالب Django**: `templates/components/data_table.html`
2. **ملف CSS**: `static/css/tables.css`
3. **ملف JavaScript**: `static/js/global-table.js`

## التثبيت والإعداد

### الخطوة 1: ربط الملفات في القالب الأساسي (`base.html`)

```html
{% load static %}

{% block styles %}
<!-- ملف CSS الأساسي للجداول -->
<link rel="stylesheet" href="{% static 'css/tables.css' %}">
<!-- مكتبة DataTables لتحسين وظائف الجدول -->
<link rel="stylesheet" href="{% static 'vendor/datatables/dataTables.bootstrap5.min.css' %}">
{% endblock %}

{% block scripts %}
<!-- مكتبة jQuery (مطلوبة) -->
<script src="{% static 'vendor/jquery/jquery.min.js' %}"></script>
<!-- مكتبة DataTables -->
<script src="{% static 'vendor/datatables/jquery.dataTables.min.js' %}"></script>
<script src="{% static 'vendor/datatables/dataTables.bootstrap5.min.js' %}"></script>
<!-- ملف JavaScript الخاص بالجداول -->
<script src="{% static 'js/global-table.js' %}"></script>
{% endblock %}
```

### الخطوة 2: إضافة المكتبات المطلوبة

تأكد من تثبيت المكتبات التالية:

- jQuery
- DataTables (يمكن تحميلها من [الموقع الرسمي](https://datatables.net/download/))

## الاستخدام الأساسي

### في ملف View (Python)

```python
def transaction_list(request):
    transactions = Transaction.objects.all()
    
    # تعريف عناوين الأعمدة
    headers = [
        {'key': 'type', 'label': 'النوع', 'sortable': False, 'format': 'icon_text', 
         'icon_callback': 'get_type_class', 'icon_class_callback': 'get_type_icon'},
        {'key': 'date', 'label': 'التاريخ', 'sortable': True, 'format': 'date'},
        {'key': 'account', 'label': 'الحساب', 'sortable': True},
        {'key': 'description', 'label': 'الوصف', 'sortable': True, 'ellipsis': True},
        {'key': 'amount', 'label': 'المبلغ', 'sortable': True, 'format': 'currency', 'variant': 'income', 'class': 'text-end'},
        {'key': 'balance', 'label': 'الرصيد', 'sortable': True, 'format': 'currency', 'class': 'text-end'},
        {'key': 'reference', 'label': 'المرجع', 'sortable': True, 'format': 'reference'},
    ]
    
    # تعريف أزرار الإجراءات
    action_buttons = [
        {'url': 'financial:transaction_detail', 'icon': 'fa-eye', 'label': 'عرض', 'class': 'action-view'},
        {'url': 'financial:transaction_update', 'icon': 'fa-edit', 'label': 'تعديل', 'class': 'action-edit'},
        {'url': 'financial:transaction_delete', 'icon': 'fa-trash', 'label': 'حذف', 'class': 'action-delete'},
    ]
    
    context = {
        'transactions': transactions,
        'headers': headers,
        'action_buttons': action_buttons,
    }
    
    return render(request, 'financial/transaction_list.html', context)
```

### في ملف Template (HTML)

```html
{% extends "base.html" %}
{% load static %}
{% load i18n %}

{% block content %}
<!-- جدول المعاملات -->
<div class="card">
    <div class="card-header">
        <h5 class="card-title">{% trans "قائمة المعاملات" %}</h5>
    </div>
    <div class="card-body">
        <!-- استخدام قالب الجدول الموحد -->
        {% with 
            table_id="transactions-table"
            headers=headers
            data=transactions
            empty_message="لا توجد معاملات مالية للعرض"
            table_class="hover"
            action_buttons=action_buttons
            primary_key="id"
        %}
        {% include "components/data_table.html" %}
        {% endwith %}
    </div>
</div>
{% endblock %}

{% block scripts %}
{{ block.super }}
<script>
    $(document).ready(function() {
        // تهيئة جدول المعاملات
        initGlobalTable('transactions-table', {
            pageLength: 15,
            order: [1, 'desc'],  // ترتيب حسب التاريخ تنازلياً
            columnDefs: [
                { targets: 'col-actions', orderable: false },  // عمود الإجراءات غير قابل للترتيب
                { targets: 'col-type', orderable: false }      // عمود النوع غير قابل للترتيب
            ]
        });
    });
</script>
{% endblock %}
```

## خيارات وإعدادات متقدمة

### معلمات قالب الجدول (`data_table.html`)

| المعلمة | الوصف | القيمة الافتراضية |
|---------|-------|-------------------|
| `table_id` | معرف الجدول | "data-table" |
| `headers` | قائمة برؤوس الأعمدة | مطلوب |
| `data` | قائمة العناصر المعروضة | مطلوب |
| `empty_message` | رسالة عندما لا توجد بيانات | "لا توجد بيانات للعرض" |
| `table_class` | تصنيفات CSS إضافية للجدول | "" |
| `primary_key` | اسم الحقل المستخدم كمفتاح أساسي | "id" |
| `action_buttons` | قائمة بأزرار الإجراءات | [] |
| `responsive` | هل الجدول مستجيب | True |
| `sortable` | هل الجدول قابل للترتيب | True |
| `current_order_by` | الحقل الحالي للترتيب | "" |
| `current_order_dir` | اتجاه الترتيب الحالي | "" |
| `row_class_callback` | دالة لتحديد فئة الصفوف | None |
| `show_currency` | هل تظهر رمز العملة | False |
| `currency_symbol` | رمز العملة | "ج.م" |
| `hover_effect` | هل تظهر تأثير عند المرور | True |

### تنسيق رؤوس الأعمدة

```python
headers = [
    {
        'key': 'name',              # اسم الحقل
        'label': 'الاسم',           # العنوان المعروض
        'sortable': True,           # هل العمود قابل للترتيب
        'format': 'text',           # نوع التنسيق
        'width': '20%',             # عرض العمود
        'class': 'text-center',     # فئة CSS للعمود
        'ellipsis': True,           # إذا كان النص طويلاً يتم قصه
        'variant': 'income',        # متغير لتنسيق العمود (للألوان)
        'template': 'custom.html',  # قالب مخصص للعرض
        'icon_callback': 'get_icon', # دالة لاسترجاع أيقونة
    }
]
```

### أنواع تنسيق البيانات المدعومة

| النوع | الوصف | مثال |
|-------|-------|-------|
| `text` | نص عادي (افتراضي) | "اسم المنتج" |
| `date` | تاريخ | "2023-08-15" |
| `datetime` | تاريخ ووقت | "2023-08-15 13:45" |
| `currency` | قيمة مالية | "1,234.56 ج.م" |
| `boolean` | قيمة منطقية | "نعم" / "لا" |
| `image` | صورة | عرض صورة مصغرة |
| `status` | حالة | "نشط" / "غير نشط" |
| `reference` | رقم مرجعي | "REF-12345" |
| `icon_text` | أيقونة مع نص | أيقونة وبجانبها نص |

### وظائف JavaScript المتاحة

| الوظيفة | الوصف |
|---------|-------|
| `initGlobalTable(tableId, options)` | تهيئة الجدول |
| `updateTableData(tableId, data)` | تحديث بيانات الجدول |
| `loadTableData(tableId, url, data)` | استرجاع بيانات الجدول عبر AJAX |
| `withTableOptimization(tableId, callback)` | تنفيذ عمليات متعددة بكفاءة |
| `exportTableToExcel(tableId, filename)` | تصدير الجدول إلى Excel |
| `exportTableToPDF(tableId, filename)` | تصدير الجدول إلى PDF |
| `addExportButtons(tableId, containerSelector)` | إضافة أزرار التصدير |

## تفعيل خاصية التصدير

لتفعيل خاصية تصدير الجدول إلى Excel أو PDF، يجب إضافة مكتبات DataTables Buttons:

```html
<!-- ملفات CSS الإضافية -->
<link rel="stylesheet" href="{% static 'vendor/datatables/buttons.bootstrap5.min.css' %}">

<!-- ملفات JavaScript الإضافية -->
<script src="{% static 'vendor/datatables/dataTables.buttons.min.js' %}"></script>
<script src="{% static 'vendor/datatables/buttons.bootstrap5.min.js' %}"></script>
<script src="{% static 'vendor/datatables/buttons.html5.min.js' %}"></script>
<script src="{% static 'vendor/datatables/buttons.print.min.js' %}"></script>
<script src="{% static 'vendor/datatables/jszip.min.js' %}"></script>
<script src="{% static 'vendor/datatables/pdfmake.min.js' %}"></script>
<script src="{% static 'vendor/datatables/vfs_fonts.js' %}"></script>
```

ثم إضافة أزرار التصدير:

```javascript
// إضافة أزرار التصدير
addExportButtons('transactions-table', '.actions-container');
```

## تخصيص المظهر

لتخصيص مظهر الجدول، يمكن إضافة الأنماط المخصصة في ملف CSS:

```css
/* تخصيص لون الصفوف الفردية */
.transaction-table tbody tr:nth-child(odd) {
    background-color: rgba(0, 0, 0, 0.02);
}

/* تخصيص لون رأس الجدول */
.transaction-table th {
    background-color: #007bff;
    color: white;
}

/* تخصيص تأثير المرور فوق الصفوف */
.transaction-table tbody tr:hover {
    background-color: rgba(0, 123, 255, 0.1);
}
```

## ربط خيارات AJAX للتحميل المؤجل

لتحميل البيانات عبر AJAX بدلاً من تضمينها مباشرة في الصفحة:

```javascript
initGlobalTable('transactions-table', {
    processing: true,
    serverSide: true,
    ajax: {
        url: "{% url 'financial:transaction_data' %}",
        data: function(data) {
            data.account = $('#account').val();
            data.type = $('#type').val();
            return data;
        }
    },
    // باقي الإعدادات...
});
```

## الملاحظات والتوصيات

1. استخدم القالب الموحد في جميع صفحات القوائم للحفاظ على اتساق التصميم.
2. استخدم تصنيفات CSS المعرفة مسبقاً قدر الإمكان مثل `.transaction-amount.income`.
3. تجنب تكرار التنسيقات CSS الخاصة بالجداول، استخدم ملف `tables.css` الموحد.
4. استخدم `row_class_callback` لتطبيق تنسيقات مختلفة على الصفوف حسب البيانات.
5. للجداول التي تحتوي على بيانات كثيرة، فعّل خيار التحميل المؤجل (AJAX) لتحسين الأداء.

## أمثلة إضافية

### مثال 1: جدول المنتجات

```python
# في ملف الـ view
headers = [
    {'key': 'image', 'label': 'الصورة', 'sortable': False, 'format': 'image', 'width': '5%'},
    {'key': 'code', 'label': 'الكود', 'sortable': True, 'width': '10%'},
    {'key': 'name', 'label': 'اسم المنتج', 'sortable': True, 'width': '25%'},
    {'key': 'category', 'label': 'التصنيف', 'sortable': True, 'width': '15%'},
    {'key': 'price', 'label': 'السعر', 'sortable': True, 'format': 'currency', 'class': 'text-end', 'width': '10%'},
    {'key': 'stock', 'label': 'المخزون', 'sortable': True, 'class': 'text-center', 'width': '10%'},
    {'key': 'status', 'label': 'الحالة', 'sortable': True, 'format': 'status', 'width': '10%'},
]
```

### مثال 2: جدول العملاء

```python
# في ملف الـ view
headers = [
    {'key': 'name', 'label': 'اسم العميل', 'sortable': True, 'width': '25%'},
    {'key': 'phone', 'label': 'رقم الجوال', 'sortable': True, 'width': '15%'},
    {'key': 'email', 'label': 'البريد الإلكتروني', 'sortable': True, 'width': '20%'},
    {'key': 'orders_count', 'label': 'عدد الطلبات', 'sortable': True, 'class': 'text-center', 'width': '10%'},
    {'key': 'total_spent', 'label': 'إجمالي المشتريات', 'sortable': True, 'format': 'currency', 'class': 'text-end', 'width': '15%'},
    {'key': 'created_at', 'label': 'تاريخ التسجيل', 'sortable': True, 'format': 'date', 'width': '15%'},
]
``` 