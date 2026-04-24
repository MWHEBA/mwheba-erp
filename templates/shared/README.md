# دليل المكونات المشتركة - Corporate ERP

## 📋 نظرة عامة

هذا الدليل يوثق جميع المكونات المشتركة في نظام Corporate ERP، والتي تم تصميمها لضمان الاتساق والقابلية لإعادة الاستخدام عبر جميع أجزاء التطبيق.

---

## 📁 المكونات المشتركة (Shared Components)

### 1. `page_header.html` - رأس الصفحة الموحد

**الوصف:** مكون رأس الصفحة الرئيسي المستخدم في جميع الصفحات لضمان التصميم الموحد.

**المعاملات الأساسية:**
- `title` / `page_title` (مطلوب): العنوان الرئيسي للصفحة
- `subtitle` / `page_subtitle` (اختياري): العنوان الفرعي
- `icon` / `page_icon` (اختياري): أيقونة Font Awesome
- `description` (اختياري): وصف إضافي طويل

**معاملات التخصيص:**
- `header_class` (اختياري): فئات CSS إضافية للهيدر
- `container_class` (اختياري): فئات CSS للحاوية
- `title_class` (اختياري): فئات CSS للعنوان
- `icon_class` (اختياري): فئات CSS للأيقونة

**معاملات الأزرار والشارات:**
- `header_buttons` / `action_buttons` (اختياري): قائمة أزرار الإجراءات
- `header_badges` (اختياري): قائمة شارات الحالة

**معاملات التنقل:**
- `show_breadcrumb` (اختياري، افتراضي True): إظهار مسار التنقل
- `breadcrumb_items` (اختياري): عناصر مسار التنقل المخصصة

**أمثلة الاستخدام:**

```django
<!-- استخدام بسيط -->
{% include "shared/page_header.html" with title="قائمة العملاء" %}

<!-- استخدام متقدم -->
{% include "shared/page_header.html" with 
    title="قائمة العملاء" 
    subtitle="إدارة بيانات العملاء"
    description="عرض وإدارة جميع بيانات العملاء مع إمكانية البحث والفلترة"
    icon="fa-users" 
    header_buttons=buttons
    header_badges=badges
%}

<!-- مع أزرار مخصصة -->
{% with buttons=[
    {'url': '/clients/add/', 'icon': 'fa-plus', 'text': 'إضافة عميل', 'class': 'btn-primary'},
    {'onclick': 'exportData()', 'icon': 'fa-download', 'text': 'تصدير', 'class': 'btn-success'}
] %}
{% include "shared/page_header.html" with title="العملاء" header_buttons=buttons %}
{% endwith %}
```

---

### 2. `stats_card.html` - كارت الإحصائيات

**الوصف:** كارت لعرض الإحصائيات والأرقام المهمة مع دعم الاتجاهات والألوان.

**المعاملات الأساسية:**
- `title` (مطلوب): عنوان الكارت
- `value` (مطلوب): القيمة الرئيسية
- `unit` (اختياري): وحدة القياس
- `icon` (اختياري): أيقونة Font Awesome

**معاملات التصميم:**
- `color` (اختياري، افتراضي primary): اللون (primary/success/danger/info/warning/dark/light/secondary)
- `size` (اختياري، افتراضي md): الحجم (sm/md/lg)
- `layout` (اختياري، افتراضي vertical): التخطيط (vertical/horizontal)

**معاملات الاتجاه:**
- `trend` (اختياري): الاتجاه (up/down/neutral)
- `trend_value` (اختياري): قيمة الاتجاه (مثل: 12.5)
- `trend_text` (اختياري): نص الاتجاه
- `trend_period` (اختياري): فترة الاتجاه

**معاملات التفاعل:**
- `url` (اختياري): رابط عند النقر على الكارت
- `target` (اختياري): هدف الرابط
- `animate` (اختياري، افتراضي True): تفعيل الحركة

**أمثلة الاستخدام:**

```django
<!-- كارت بسيط -->
{% include "shared/stats_card.html" with 
    title="إجمالي العملاء" 
    value=150 
    unit="عميل" 
    icon="fa-users" 
    color="primary" 
%}

<!-- كارت مع اتجاه صاعد -->
{% include "shared/stats_card.html" with 
    title="المبيعات الشهرية" 
    value=50000 
    unit="جنيه" 
    icon="fa-chart-line" 
    color="success"
    trend="up"
    trend_value=12.5
    trend_period="عن الشهر الماضي"
%}

<!-- كارت قابل للنقر -->
{% include "shared/stats_card.html" with 
    title="الطلبات الجديدة" 
    value=25 
    unit="طلب" 
    icon="fa-shopping-cart" 
    color="info"
    url="/orders/"
%}
```

---

### 3. `breadcrumb.html` - مسار التنقل

**الوصف:** مكون مسار التنقل مع دعم RTL كامل وتخصيص متقدم.

**المعاملات:**
- `items` (اختياري): قائمة عناصر المسار
- `breadcrumb_items` (اختياري): من السياق
- `show_home` (اختياري، افتراضي True): إظهار رابط الرئيسية
- `home_title` (اختياري، افتراضي "الرئيسية"): عنوان الرئيسية
- `home_url` (اختياري، افتراضي "/"): رابط الرئيسية
- `home_icon` (اختياري، افتراضي "fa-home"): أيقونة الرئيسية

**بنية العنصر:**
```python
{
    'title': 'عنوان العنصر',        # مطلوب
    'url': '/path/to/page/',        # اختياري
    'icon': 'fa-icon-name',         # اختياري
    'active': True/False,           # اختياري
    'target': '_blank',             # اختياري
    'title_attr': 'نص التلميح',     # اختياري
}
```

**أمثلة الاستخدام:**

```django
<!-- استخدام تلقائي -->
{% include "shared/breadcrumb.html" %}

<!-- مع عناصر مخصصة -->
{% with breadcrumb_items=[
    {"title": "الرئيسية", "url": "/", "icon": "fa-home"},
    {"title": "المشتريات", "url": "/purchases/", "icon": "fa-truck"},
    {"title": "قائمة المشتريات", "active": True}
] %}
{% include "shared/breadcrumb.html" with items=breadcrumb_items %}
{% endwith %}
```

---

### 4. `payment_form.html` - نموذج الدفع المشترك

**الوصف:** نموذج موحد لإدخال بيانات الدفعات في المبيعات والمشتريات.

**المعاملات:**
- `invoice` (مطلوب): كائن الفاتورة
- `form` (مطلوب): نموذج Django للدفع
- `is_purchase` (اختياري): هل هي فاتورة مشتريات
- `title` (اختياري): عنوان النموذج
- `currency_symbol` (اختياري): رمز العملة

**الاستخدام:**
```django
{% include "shared/payment_form.html" with 
    invoice=invoice 
    form=payment_form 
    is_purchase=True 
    title="إضافة دفعة للمورد"
%}
```

---

## 📁 المكونات العامة (Components)

### 5. `data_table.html` - جدول البيانات المتقدم

**الوصف:** جدول بيانات شامل مع فلترة وبحث وتصدير وتحكم في الأعمدة.

**المعاملات الأساسية:**
- `table_id` (اختياري، افتراضي "data-table"): معرف الجدول
- `headers` (مطلوب): قائمة رؤوس الأعمدة
- `data` (مطلوب): البيانات المعروضة
- `empty_message` (اختياري): رسالة عدم وجود بيانات

**معاملات التحكم:**
- `show_search` (اختياري، افتراضي True): إظهار البحث
- `show_length_menu` (اختياري، افتراضي True): إظهار قائمة العدد
- `show_filters` (اختياري، افتراضي False): إظهار الفلاتر المتقدمة
- `show_column_toggle` (اختياري، افتراضي False): إظهار/إخفاء الأعمدة
- `show_export` (اختياري، افتراضي False): إظهار أزرار التصدير

**معاملات الجدول:**
- `table_class` (اختياري): فئات CSS إضافية
- `responsive` (اختياري، افتراضي True): جدول متجاوب
- `sortable` (اختياري، افتراضي True): قابل للترتيب
- `hover_effect` (اختياري، افتراضي True): تأثير المرور

**معاملات الصفوف:**
- `clickable_rows` (اختياري، افتراضي False): صفوف قابلة للنقر
- `row_click_url` (اختياري): نمط URL للنقر
- `primary_key` (اختياري، افتراضي "id"): المفتاح الأساسي

**بنية رأس العمود:**
```python
{
    'key': 'field_name',           # مطلوب
    'label': 'عنوان العمود',       # مطلوب
    'sortable': True,              # اختياري
    'searchable': True,            # اختياري
    'width': '20%',                # اختياري
    'class': 'text-center',        # اختياري
    'format': 'currency',          # اختياري (date/datetime/currency/number/boolean/status)
    'template': 'path/to/cell.html' # اختياري
}
```

**أمثلة الاستخدام:**

```django
<!-- جدول بسيط -->
{% include "components/data_table.html" with 
    table_id="customers-table"
    headers=customer_headers
    data=customers
%}

<!-- جدول متقدم مع جميع الميزات -->
{% include "components/data_table.html" with 
    table_id="products-table"
    headers=product_headers
    data=products
    show_export=True
    show_filters=True
    show_column_toggle=True
    clickable_rows=True
    row_click_url="/products/0/"
%}
```

---

### 6. `modal.html` - النافذة المنبثقة

**الوصف:** نافذة منبثقة متعددة الاستخدامات مع دعم النماذج والأحجام المختلفة.

**المعاملات الأساسية:**
- `id` (مطلوب): معرف فريد للنافذة
- `title` (اختياري): عنوان النافذة
- `content` (اختياري): محتوى النافذة

**معاملات التصميم:**
- `size` (اختياري، افتراضي md): الحجم (sm/md/lg/xl/fullscreen)
- `style` (اختياري، افتراضي default): النمط (default/primary/success/danger/warning/info)
- `centered` (اختياري، افتراضي True): محاذاة للوسط
- `scrollable` (اختياري، افتراضي False): قابل للتمرير

**معاملات السلوك:**
- `fade` (اختياري، افتراضي True): تأثير الظهور
- `backdrop` (اختياري، افتراضي true): نوع الخلفية (true/false/static)
- `keyboard` (اختياري، افتراضي True): إغلاق بـ Escape
- `focus` (اختياري، افتراضي True): التركيز التلقائي

**معاملات الرأس:**
- `show_header` (اختياري، افتراضي True): إظهار الرأس
- `title_icon` (اختياري): أيقونة العنوان
- `show_close_button` (اختياري، افتراضي True): زر الإغلاق

**معاملات التذييل:**
- `show_footer` (اختياري، افتراضي False): إظهار التذييل
- `footer` (اختياري): محتوى تذييل مخصص
- `close_text` (اختياري، افتراضي "إغلاق"): نص زر الإغلاق

**معاملات النموذج:**
- `form_modal` (اختياري، افتراضي False): نافذة نموذج
- `form_action` (اختياري): عنوان النموذج
- `form_method` (اختياري، افتراضي POST): طريقة النموذج
- `submit_text` (اختياري، افتراضي "حفظ"): نص زر الإرسال

**أمثلة الاستخدام:**

```django
<!-- نافذة بسيطة -->
{% include "components/modal.html" with 
    id="info-modal" 
    title="معلومات" 
    content="هذه رسالة إعلامية"
%}

<!-- نافذة نموذج -->
{% include "components/modal.html" with 
    id="add-customer-modal"
    title="إضافة عميل جديد"
    size="lg"
    style="primary"
    form_modal=True
    form_action="/customers/add/"
%}

<!-- نافذة تأكيد -->
{% include "components/modal.html" with 
    id="delete-modal"
    title="تأكيد الحذف"
    style="danger"
    action_buttons=delete_buttons
%}
```

---

### 7. `form_field.html` - حقل النموذج الموحد

**الوصف:** مكون موحد لعرض حقول النماذج مع دعم جميع الأنواع والتخطيطات.

**المعاملات الأساسية:**
- `field` (مطلوب): كائن الحقل من نموذج Django
- `field_type` (اختياري): نوع الحقل (يتم تحديده تلقائياً)

**معاملات العرض:**
- `show_label` (اختياري، افتراضي True): عرض العنوان
- `label` (اختياري): نص العنوان المخصص
- `show_required_mark` (اختياري، افتراضي True): علامة الحقل المطلوب

**معاملات الحقل:**
- `placeholder` (اختياري): نص توضيحي
- `readonly` (اختياري، افتراضي False): للقراءة فقط
- `disabled` (اختياري، افتراضي False): معطل
- `autofocus` (اختياري، افتراضي False): التركيز التلقائي

**معاملات الأيقونات:**
- `prepend_icon` (اختياري): أيقونة قبل الحقل
- `append_icon` (اختياري): أيقونة بعد الحقل
- `icon_color` (اختياري، افتراضي secondary): لون الأيقونة

**معاملات المساعدة:**
- `help_text` (اختياري): نص مساعد
- `show_help_text` (اختياري، افتراضي True): إظهار المساعدة
- `show_validation` (اختياري، افتراضي True): إظهار رسائل التحقق

**معاملات التخطيط:**
- `layout` (اختياري، افتراضي vertical): التخطيط (vertical/horizontal/inline)
- `wrapper_class` (اختياري): فئات الحاوية
- `field_class` (اختياري): فئات الحقل

**أمثلة الاستخدام:**

```django
<!-- حقل بسيط -->
{% include "components/form_field.html" with field=form.name %}

<!-- حقل بريد إلكتروني مع أيقونة -->
{% include "components/form_field.html" with 
    field=form.email 
    prepend_icon="fa-envelope"
    help_text="أدخل بريدك الإلكتروني الصحيح"
%}

<!-- حقل كلمة مرور -->
{% include "components/form_field.html" with 
    field=form.password 
    prepend_icon="fa-lock"
    help_text="يجب أن تحتوي على 8 أحرف على الأقل"
%}

<!-- حقل أفقي -->
{% include "components/form_field.html" with 
    field=form.birth_date 
    layout="horizontal"
    prepend_icon="fa-calendar"
%}
```

---

### 8. `status_badge.html` - شارة الحالة

**الوصف:** شارة لعرض حالة العناصر مع ألوان وأنماط مختلفة.

**المعاملات:**
- `status` (مطلوب): حالة العنصر
- `label` (اختياري): نص مخصص للعرض
- `size` (اختياري): حجم الشارة (sm/lg)
- `pill` (اختياري، افتراضي True): نمط الكبسولة
- `badge_class` (اختياري): فئات CSS إضافية

**الحالات المدعومة:**
- `active` → نشط (أخضر)
- `inactive` → غير نشط (رمادي)
- `pending` → معلق (أصفر)
- `completed` → مكتمل (أخضر)
- `cancelled` → ملغي (أحمر)
- `paid` → مدفوع (أخضر)
- `unpaid` → غير مدفوع (أصفر)

**أمثلة الاستخدام:**

```django
<!-- شارة بسيطة -->
{% include "components/status_badge.html" with status="active" %}

<!-- شارة مخصصة -->
{% include "components/status_badge.html" with 
    status="processing" 
    label="قيد المعالجة" 
    size="lg"
%}
```

---

### 9. `alert.html` - التنبيهات

**الوصف:** مكون التنبيهات والرسائل مع أنواع وأيقونات مختلفة.

**المعاملات:**
- `type` (اختياري، افتراضي info): نوع التنبيه (success/info/warning/danger/primary/secondary)
- `message` (مطلوب): نص الرسالة
- `dismissible` (اختياري، افتراضي False): قابل للإغلاق
- `icon` (اختياري): أيقونة مخصصة
- `alert_class` (اختياري): فئات CSS إضافية

**أمثلة الاستخدام:**

```django
<!-- تنبيه نجاح -->
{% include "components/alert.html" with 
    type="success" 
    message="تمت العملية بنجاح" 
    dismissible=True 
%}

<!-- تنبيه خطأ -->
{% include "components/alert.html" with 
    type="danger" 
    message="حدث خطأ في العملية" 
    icon="fa-exclamation-triangle"
%}
```

---

## 🎨 الميزات العامة

### إمكانية الوصول (Accessibility)
- تسميات ARIA مناسبة لجميع العناصر التفاعلية
- دعم كامل لقارئات الشاشة
- تنقل سهل بلوحة المفاتيح
- تباين ألوان يتوافق مع معايير WCAG 2.1
- دعم وضع الحركة المقللة

### دعم اللغة العربية (RTL)
- اتجاه صحيح للنصوص من اليمين لليسار
- أيقونات في المواضع المناسبة للعربية
- أسهم التنقل بالاتجاه الصحيح
- محاذاة صحيحة للعناصر

### التصميم المتجاوب
- تخطيطات تتكيف مع جميع أحجام الشاشات
- أحجام مناسبة للأجهزة المحمولة
- تفاعل لمسي محسن للشاشات اللمسية
- نصوص قابلة للقراءة على جميع الأجهزة

---

## 🔧 التخصيص المتقدم

### متغيرات CSS المتاحة

```css
:root {
    /* الألوان الأساسية */
    --bs-primary: #0d6efd;
    --bs-success: #198754;
    --bs-danger: #dc3545;
    --bs-warning: #ffc107;
    --bs-info: #0dcaf0;
    
    /* ألوان المكونات */
    --card-color: var(--primary-color);
    --modal-bg: #ffffff;
    --table-hover-bg: #f8f9fa;
    
    /* المسافات */
    --spacing-1: 0.25rem;
    --spacing-2: 0.5rem;
    --spacing-3: 1rem;
    --spacing-4: 1.5rem;
    --spacing-5: 3rem;
    
    /* الحدود */
    --border-radius: 0.375rem;
    --border-radius-lg: 0.5rem;
    --border-color: #dee2e6;
    
    /* الظلال */
    --shadow-sm: 0 0.125rem 0.25rem rgba(0, 0, 0, 0.075);
    --shadow-md: 0 0.5rem 1rem rgba(0, 0, 0, 0.15);
}
```

### تخصيص الألوان

```css
/* تخصيص ألوان كروت الإحصائيات */
.stats-card-custom {
    --card-color: #6f42c1;
}

/* تخصيص ألوان الجداول */
.table-custom {
    --table-hover-bg: #e3f2fd;
}
```

### إضافة فئات مخصصة

```django
<!-- كارت إحصائيات مخصص -->
{% include "shared/stats_card.html" with 
    title="إحصائية مخصصة"
    value=100
    card_class="stats-card-custom shadow-lg"
%}

<!-- جدول مخصص -->
{% include "components/data_table.html" with 
    table_id="custom-table"
    headers=headers
    data=data
    table_class="table-custom"
%}
```

---

## 📚 أفضل الممارسات

### استخدام المكونات
1. **استخدم المكونات المشتركة دائماً** بدلاً من إنشاء HTML مخصص
2. **مرر المعاملات المطلوبة فقط** واترك الباقي للقيم الافتراضية
3. **استخدم أسماء معاملات واضحة** لتحسين قابلية القراءة
4. **اختبر المكونات على أحجام شاشات مختلفة**

### الأداء
1. **تجنب تمرير بيانات كبيرة** كمعاملات للمكونات
2. **استخدم التخزين المؤقت** للبيانات المتكررة
3. **قم بتحسين الصور** المستخدمة في المكونات
4. **استخدم الـ lazy loading** للمحتوى الثقيل

### إمكانية الوصول
1. **أضف نصوص بديلة** لجميع الصور والأيقونات
2. **استخدم تسميات ARIA** المناسبة
3. **تأكد من تباين الألوان** الكافي
4. **اختبر التنقل بلوحة المفاتيح**

---

## 🧪 الاختبار والتحقق

### اختبار المكونات
```python
# مثال لاختبار مكون page_header
def test_page_header_rendering():
    context = {
        'title': 'اختبار العنوان',
        'subtitle': 'اختبار العنوان الفرعي',
        'icon': 'fa-test'
    }
    html = render_to_string('shared/page_header.html', context)
    assert 'اختبار العنوان' in html
    assert 'fa-test' in html
```

### التحقق من إمكانية الوصول
```javascript
// استخدام axe-core للتحقق من إمكانية الوصول
axe.run(document, function (err, results) {
    if (err) throw err;
    console.log(results.violations);
});
```

---

## 📞 الدعم والمساعدة

### الأخطاء الشائعة
1. **عدم تمرير المعاملات المطلوبة**: تأكد من تمرير جميع المعاملات المطلوبة
2. **أخطاء في أسماء المعاملات**: راجع التوثيق للتأكد من الأسماء الصحيحة
3. **مشاكل في التنسيق**: تأكد من تضمين ملفات CSS المطلوبة

### نصائح للتطوير
1. **استخدم أدوات المطور** في المتصفح لفحص المكونات
2. **اقرأ التعليقات** في ملفات المكونات للحصول على تفاصيل إضافية
3. **اختبر على متصفحات مختلفة** للتأكد من التوافق
4. **استخدم أدوات التحقق من إمكانية الوصول**

---

## 📝 سجل التغييرات

### الإصدار الحالي
- ✅ توحيد جميع المكونات المشتركة
- ✅ دعم كامل للغة العربية وRTL
- ✅ تحسينات إمكانية الوصول
- ✅ تصميم متجاوب محسن
- ✅ توثيق شامل مع أمثلة

### التحسينات المستقبلية
- 🔄 إضافة المزيد من أنواع الحقول
- 🔄 تحسين أداء الجداول الكبيرة
- 🔄 إضافة المزيد من خيارات التخصيص
- 🔄 دعم الوضع المظلم

---

## 🔄 التوحيد الأخير (ديسمبر 2024)

### ما تم توحيده:

#### 1. صفحة قائمة العناصر (`templates/students/students/list.html`)
**قبل التوحيد:**
- هيدر مكتوب يدوياً مع breadcrumb منفصل
- كروت إحصائيات Bootstrap عادية
- تنسيق مختلف عن باقي الصفحات

**بعد التوحيد:**
- استخدام `shared/page_header.html` الموحد
- استخدام `shared/stats_card.html` للإحصائيات
- تنسيق موحد مع صفحة الموردين
- إضافة `section-container` للتنسيق المتسق

#### 2. تحديث StudentListView (`students/views.py`)
**الإضافات:**
```python
# بيانات الهيدر الموحد
context['page_title'] = 'قائمة العناصر'
context['page_subtitle'] = 'إدارة العناصر وعرض بياناتهم'
context['page_icon'] = 'fas fa-graduation-cap'

# أزرار الهيدر
context['header_buttons'] = [
    {
        'url': reverse('students:student_create'),
        'icon': 'fa-plus',
        'text': 'إضافة عنصر جديد',
        'class': 'btn-primary'
    }
]

# عناصر البريدكرمب
context['breadcrumb_items'] = [
    {
        'title': 'الرئيسية',
        'url': reverse('core:dashboard'),
        'icon': 'fas fa-home'
    },
    {
        'title': 'العناصر',
        'active': True,
        'icon': 'fas fa-graduation-cap'
    }
]
```

#### 3. العناصر الموحدة الآن:

**الهيدر:**
- ✅ عنوان موحد مع أيقونة
- ✅ وصف فرعي
- ✅ أزرار إجراءات في نفس المكان
- ✅ breadcrumb موحد

**كروت الإحصائيات:**
- ✅ تصميم موحد مع ألوان متسقة
- ✅ أيقونات في نفس المواضع
- ✅ تأثيرات hover متطابقة
- ✅ responsive design

**السكاشن (الأقسام):**
- ✅ `section-container` موحد
- ✅ `section-title` متسق
- ✅ `filter-section` للبحث والفلترة
- ✅ تباعد وحدود موحدة

**الجداول:**
- ✅ تنسيق موحد للأزرار
- ✅ صفوف قابلة للنقر
- ✅ أعمدة إجراءات متسقة
- ✅ empty state موحد

#### 4. الفوائد المحققة:

**للمطورين:**
- 🔧 صيانة أسهل - تعديل واحد يؤثر على جميع الصفحات
- 🔧 كود أقل تكراراً
- 🔧 معايير موحدة للتطوير

**للمستخدمين:**
- 👤 تجربة متسقة عبر النظام
- 👤 تعلم أسرع للواجهة
- 👤 تنقل أكثر سهولة

**للتصميم:**
- 🎨 مظهر احترافي موحد
- 🎨 ألوان وخطوط متسقة
- 🎨 تجاوب أفضل مع الشاشات المختلفة

#### 5. الصفحات المتوافقة الآن:
- ✅ صفحة الموردين (`supplier/core/supplier_list.html`)
- ✅ صفحة العناصر (`students/students/list.html`)
- 🔄 باقي الصفحات (قيد التوحيد التدريجي)

#### 6. المكونات المستخدمة:
```django
<!-- الهيدر الموحد -->
{% include "shared/page_header.html" with 
    title="قائمة العناصر" 
    subtitle="إدارة العناصر وعرض بياناتهم" 
    icon="fas fa-graduation-cap" 
    header_buttons=header_buttons 
%}

<!-- كروت الإحصائيات الموحدة -->
{% include "shared/stats_card.html" with 
    title="إجمالي العناصر" 
    value=stats.total_students 
    unit="عنصر" 
    icon="fa-users" 
    color="primary" 
%}
```

---

*آخر تحديث: ديسمبر 2024*
