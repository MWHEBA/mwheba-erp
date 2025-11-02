# منع إضافة فواتير بتاريخ مستقبلي

## نظرة عامة
تم إضافة التحقق من التاريخ المستقبلي لجميع نماذج الفواتير والدفعات والمرتجعات في النظام لمنع إدخال تواريخ مستقبلية.

## التاريخ
**تاريخ التطبيق:** 2025-11-01

## الملفات المعدلة

### 1. فواتير المبيعات (`sale/forms.py`)

#### ✅ `SaleForm` - نموذج الفاتورة
```python
def clean_date(self):
    """التحقق من أن تاريخ الفاتورة ليس في المستقبل"""
    date = self.cleaned_data.get("date")
    if date and date > timezone.now().date():
        raise ValidationError("تاريخ الفاتورة لا يمكن أن يكون في المستقبل")
    return date
```

#### ✅ `SalePaymentForm` - نموذج الدفعة
```python
def clean_payment_date(self):
    """التحقق من أن تاريخ الدفعة ليس في المستقبل"""
    payment_date = self.cleaned_data.get("payment_date")
    if payment_date and payment_date > timezone.now().date():
        raise ValidationError("تاريخ الدفعة لا يمكن أن يكون في المستقبل")
    return payment_date
```

#### ✅ `SalePaymentEditForm` - نموذج تعديل الدفعة
```python
def clean_payment_date(self):
    """التحقق من أن تاريخ الدفعة ليس في المستقبل"""
    payment_date = self.cleaned_data.get("payment_date")
    if payment_date and payment_date > timezone.now().date():
        raise ValidationError("تاريخ الدفعة لا يمكن أن يكون في المستقبل")
    return payment_date
```

#### ✅ `SaleReturnForm` - نموذج المرتجع
```python
def clean_date(self):
    """التحقق من أن تاريخ المرتجع ليس في المستقبل"""
    date = self.cleaned_data.get("date")
    if date and date > timezone.now().date():
        raise ValidationError("تاريخ المرتجع لا يمكن أن يكون في المستقبل")
    return date
```

---

### 2. فواتير المشتريات (`purchase/forms.py`)

#### ✅ `PurchaseForm` - نموذج الفاتورة
```python
def clean_date(self):
    """التحقق من أن تاريخ الفاتورة ليس في المستقبل"""
    date = self.cleaned_data.get("date")
    if date and date > timezone.now().date():
        raise ValidationError("تاريخ الفاتورة لا يمكن أن يكون في المستقبل")
    return date
```

#### ✅ `PurchasePaymentForm` - نموذج الدفعة
```python
def clean_payment_date(self):
    """التحقق من أن تاريخ الدفعة ليس في المستقبل"""
    payment_date = self.cleaned_data.get("payment_date")
    if payment_date and payment_date > timezone.now().date():
        raise ValidationError("تاريخ الدفعة لا يمكن أن يكون في المستقبل")
    return payment_date
```

#### ✅ `PurchasePaymentEditForm` - نموذج تعديل الدفعة
```python
def clean_payment_date(self):
    """التحقق من أن تاريخ الدفعة ليس في المستقبل"""
    payment_date = self.cleaned_data.get("payment_date")
    if payment_date and payment_date > timezone.now().date():
        raise ValidationError("تاريخ الدفعة لا يمكن أن يكون في المستقبل")
    return payment_date
```

#### ✅ `PurchaseReturnForm` - نموذج المرتجع
```python
def clean_date(self):
    """التحقق من أن تاريخ المرتجع ليس في المستقبل"""
    date = self.cleaned_data.get("date")
    if date and date > timezone.now().date():
        raise ValidationError("تاريخ المرتجع لا يمكن أن يكون في المستقبل")
    return date
```

---

## النماذج التي كانت تطبق التحقق مسبقاً

### 1. النماذج المالية (`financial/forms/`)

#### ✅ `ExpenseForm` - نموذج المصروفات
```python
def clean_expense_date(self):
    expense_date = self.cleaned_data.get("expense_date")
    if expense_date and expense_date > timezone.now().date():
        raise ValidationError("تاريخ المصروف لا يمكن أن يكون في المستقبل")
    return expense_date
```

#### ✅ `IncomeForm` - نموذج الإيرادات
```python
def clean_income_date(self):
    income_date = self.cleaned_data.get("income_date")
    if income_date and income_date > timezone.now().date():
        raise ValidationError("تاريخ الإيراد لا يمكن أن يكون في المستقبل")
    return income_date
```

### 2. نموذج نطاق التاريخ (`core/forms.py`)

#### ✅ `DateRangeForm` - مع خاصية `allows_future_dates`
```python
# التحقق من عدم وجود تواريخ مستقبلية إذا كان غير مسموح بها
if not self.allows_future_dates:
    today = timezone.now().date()
    if start_date and start_date > today:
        self.add_error("start_date", _("لا يمكن تحديد تاريخ في المستقبل"))
    if end_date and end_date > today:
        self.add_error("end_date", _("لا يمكن تحديد تاريخ في المستقبل"))
```

---

## ملخص التغييرات

| النموذج | الملف | حقل التاريخ | الحالة |
|---------|------|------------|--------|
| **SaleForm** | `sale/forms.py` | `date` | ✅ تم الإضافة |
| **SalePaymentForm** | `sale/forms.py` | `payment_date` | ✅ تم الإضافة |
| **SalePaymentEditForm** | `sale/forms.py` | `payment_date` | ✅ تم الإضافة |
| **SaleReturnForm** | `sale/forms.py` | `date` | ✅ تم الإضافة |
| **PurchaseForm** | `purchase/forms.py` | `date` | ✅ تم الإضافة |
| **PurchasePaymentForm** | `purchase/forms.py` | `payment_date` | ✅ تم الإضافة |
| **PurchasePaymentEditForm** | `purchase/forms.py` | `payment_date` | ✅ تم الإضافة |
| **PurchaseReturnForm** | `purchase/forms.py` | `date` | ✅ تم الإضافة |
| **ExpenseForm** | `financial/forms/expense_forms.py` | `expense_date` | ✅ موجود مسبقاً |
| **IncomeForm** | `financial/forms/income_forms.py` | `income_date` | ✅ موجود مسبقاً |
| **DateRangeForm** | `core/forms.py` | `start_date`, `end_date` | ✅ موجود مسبقاً |

---

## رسائل الخطأ

جميع رسائل الخطأ موحدة وواضحة باللغة العربية:

- **للفواتير:** "تاريخ الفاتورة لا يمكن أن يكون في المستقبل"
- **للدفعات:** "تاريخ الدفعة لا يمكن أن يكون في المستقبل"
- **للمرتجعات:** "تاريخ المرتجع لا يمكن أن يكون في المستقبل"
- **للمصروفات:** "تاريخ المصروف لا يمكن أن يكون في المستقبل"
- **للإيرادات:** "تاريخ الإيراد لا يمكن أن يكون في المستقبل"

---

## آلية العمل

1. **التحقق على مستوى النموذج (Form Level):**
   - يتم التحقق في دالة `clean_<field_name>()` لكل حقل تاريخ
   - يتم مقارنة التاريخ المدخل مع `timezone.now().date()`
   - إذا كان التاريخ أكبر من اليوم، يتم رفع `ValidationError`

2. **التوقيت المستخدم:**
   - يتم استخدام `timezone.now().date()` للحصول على التاريخ الحالي
   - يأخذ في الاعتبار المنطقة الزمنية المحددة في إعدادات Django

3. **التعامل مع القيم الفارغة:**
   - التحقق يتم فقط إذا كان التاريخ موجوداً (`if date and ...`)
   - لا يتم رفع خطأ إذا كان الحقل فارغاً (للحقول الاختيارية)

---

## الاختبار

### اختبار يدوي:
1. محاولة إنشاء فاتورة مبيعات بتاريخ غد
2. محاولة إضافة دفعة بتاريخ مستقبلي
3. محاولة إنشاء مرتجع بتاريخ مستقبلي
4. التأكد من ظهور رسالة الخطأ المناسبة

### اختبار تلقائي (مقترح):
```python
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from sale.forms import SaleForm, SalePaymentForm, SaleReturnForm
from purchase.forms import PurchaseForm, PurchasePaymentForm, PurchaseReturnForm

class FutureDateValidationTest(TestCase):
    def test_sale_form_rejects_future_date(self):
        """اختبار رفض تاريخ مستقبلي في فاتورة المبيعات"""
        future_date = timezone.now().date() + timedelta(days=1)
        form = SaleForm(data={'date': future_date, ...})
        self.assertFalse(form.is_valid())
        self.assertIn('date', form.errors)
    
    def test_sale_payment_form_rejects_future_date(self):
        """اختبار رفض تاريخ مستقبلي في دفعة المبيعات"""
        future_date = timezone.now().date() + timedelta(days=1)
        form = SalePaymentForm(data={'payment_date': future_date, ...})
        self.assertFalse(form.is_valid())
        self.assertIn('payment_date', form.errors)
    
    # ... المزيد من الاختبارات
```

---

## الفوائد

1. **منع الأخطاء المحاسبية:**
   - تجنب تسجيل معاملات بتواريخ مستقبلية
   - ضمان دقة التقارير المالية

2. **توحيد السلوك:**
   - جميع النماذج تتبع نفس القاعدة
   - رسائل خطأ موحدة وواضحة

3. **سهولة الصيانة:**
   - كود بسيط وواضح
   - سهل الفهم والتعديل

4. **تجربة مستخدم أفضل:**
   - رسائل خطأ واضحة باللغة العربية
   - منع الأخطاء قبل الحفظ

---

## ملاحظات

- التحقق يتم على مستوى النموذج (Form Validation)
- لا يؤثر على البيانات الموجودة مسبقاً
- يمكن تعديل السلوك بسهولة إذا لزم الأمر
- يعمل مع جميع المناطق الزمنية المدعومة في Django

---

## المراجع

- `core/validators.py` - يحتوي على `validate_future_date()` للاستخدام العام
- `core/forms.py` - يحتوي على `DateRangeForm` مع خاصية `allows_future_dates`
- Django Documentation: [Form Validation](https://docs.djangoproject.com/en/stable/ref/forms/validation/)
