# دليل اختبار نظام القيود التصحيحية

## 🧪 سيناريوهات الاختبار

### السيناريو 1: تعديل فاتورة مبيعات مرحّلة (زيادة المبلغ)

#### الخطوات:
1. إنشاء فاتورة مبيعات:
   ```
   - العميل: أي عميل
   - المنتج: منتج له cost_price
   - الكمية: 10
   - السعر: 1000 ج.م
   - الإجمالي: 10,000 ج.م
   ```

2. التحقق من إنشاء القيد المحاسبي:
   ```sql
   SELECT * FROM financial_journalentry 
   WHERE reference LIKE '%SALE-%'
   ORDER BY id DESC LIMIT 1;
   ```

3. تعديل الفاتورة:
   ```
   - تغيير الكمية إلى: 15
   - الإجمالي الجديد: 15,000 ج.م
   ```

4. التحقق من القيد التصحيحي:
   ```sql
   SELECT * FROM financial_journalentry 
   WHERE reference LIKE '%تصحيح فاتورة مبيعات%'
   ORDER BY id DESC LIMIT 1;
   ```

#### النتيجة المتوقعة:
```
✅ قيد تصحيحي بمبلغ 5,000 ج.م
✅ مدين: العميل 5,000
✅ دائن: إيرادات المبيعات 5,000
✅ قيد تصحيح التكلفة (حسب cost_price)
```

---

### السيناريو 2: تعديل فاتورة مبيعات مرحّلة (نقص المبلغ)

#### الخطوات:
1. إنشاء فاتورة مبيعات:
   ```
   - الإجمالي: 20,000 ج.م
   ```

2. تعديل الفاتورة:
   ```
   - تقليل الكمية
   - الإجمالي الجديد: 15,000 ج.م
   ```

#### النتيجة المتوقعة:
```
✅ قيد تصحيحي بمبلغ 5,000 ج.م
✅ دائن: العميل 5,000 (تخفيض الذمة)
✅ مدين: إيرادات المبيعات 5,000 (تخفيض الإيرادات)
```

---

### السيناريو 3: تعديل فاتورة مشتريات مرحّلة (زيادة المبلغ)

#### الخطوات:
1. إنشاء فاتورة مشتريات:
   ```
   - المورد: أي مورد
   - الإجمالي: 10,000 ج.م
   ```

2. تعديل الفاتورة:
   ```
   - زيادة الكمية
   - الإجمالي الجديد: 15,000 ج.م
   ```

#### النتيجة المتوقعة:
```
✅ قيد تصحيحي بمبلغ 5,000 ج.م
✅ مدين: المخزون 5,000
✅ دائن: المورد 5,000
```

---

### السيناريو 4: تعديل فاتورة غير مرحّلة

#### الخطوات:
1. إنشاء فاتورة بدون قيد محاسبي
2. تعديل الفاتورة

#### النتيجة المتوقعة:
```
✅ تم التعديل بنجاح
❌ لم يتم إنشاء قيد تصحيحي (لأن الفاتورة غير مرحّلة)
✅ رسالة: "تم تعديل فاتورة المبيعات بنجاح"
```

---

### السيناريو 5: تعديل بدون فروقات

#### الخطوات:
1. إنشاء فاتورة مرحّلة
2. تعديل الفاتورة بنفس المبلغ (مثلاً تغيير الوصف فقط)

#### النتيجة المتوقعة:
```
✅ تم التعديل بنجاح
❌ لم يتم إنشاء قيد تصحيحي (لا توجد فروقات)
✅ رسالة: "لا توجد فروقات تتطلب قيد تصحيحي"
```

---

## 🔍 استعلامات التحقق

### 1. التحقق من القيود التصحيحية:
```sql
SELECT 
    je.number,
    je.date,
    je.entry_type,
    je.reference,
    je.description,
    SUM(jel.debit) as total_debit,
    SUM(jel.credit) as total_credit
FROM financial_journalentry je
LEFT JOIN financial_journalentryline jel ON je.id = jel.journal_entry_id
WHERE je.entry_type = 'adjustment'
GROUP BY je.id
ORDER BY je.date DESC;
```

### 2. التحقق من تطابق القيود:
```sql
-- يجب أن يكون المجموع = 0 (المدين = الدائن)
SELECT 
    journal_entry_id,
    SUM(debit) - SUM(credit) as balance
FROM financial_journalentryline
GROUP BY journal_entry_id
HAVING balance != 0;
```

### 3. التحقق من حركات المخزون:
```sql
SELECT 
    sm.reference_number,
    sm.movement_type,
    sm.quantity,
    sm.document_type,
    sm.document_number,
    sm.notes,
    sm.created_at
FROM product_stockmovement sm
WHERE sm.reference_number LIKE '%EDIT%'
ORDER BY sm.created_at DESC;
```

### 4. التحقق من أرصدة العملاء:
```sql
SELECT 
    c.name,
    c.balance,
    SUM(CASE WHEN jel.account_id = c.financial_account_id THEN jel.debit - jel.credit ELSE 0 END) as calculated_balance
FROM client_customer c
LEFT JOIN financial_journalentryline jel ON jel.account_id = c.financial_account_id
LEFT JOIN financial_journalentry je ON je.id = jel.journal_entry_id
WHERE je.status = 'posted'
GROUP BY c.id;
```

---

## 📊 التقارير المطلوبة

### 1. تقرير القيود التصحيحية:
```python
from financial.models import JournalEntry

adjustment_entries = JournalEntry.objects.filter(
    entry_type='adjustment'
).order_by('-date')

for entry in adjustment_entries:
    print(f"القيد: {entry.number}")
    print(f"التاريخ: {entry.date}")
    print(f"المرجع: {entry.reference}")
    print(f"الوصف: {entry.description}")
    print("---")
```

### 2. تقرير التطابق:
```python
from financial.models import JournalEntryLine
from django.db.models import Sum

# التحقق من توازن القيود
unbalanced = JournalEntryLine.objects.values('journal_entry').annotate(
    balance=Sum('debit') - Sum('credit')
).exclude(balance=0)

if unbalanced.exists():
    print("⚠️ توجد قيود غير متوازنة!")
    for item in unbalanced:
        print(f"القيد: {item['journal_entry']}, الفرق: {item['balance']}")
else:
    print("✅ جميع القيود متوازنة")
```

---

## ✅ قائمة التحقق

### قبل الاختبار:
- [ ] التأكد من وجود حسابات محاسبية أساسية
- [ ] التأكد من وجود منتجات لها cost_price
- [ ] التأكد من وجود عملاء وموردين
- [ ] التأكد من وجود فترة محاسبية نشطة

### أثناء الاختبار:
- [ ] اختبار زيادة المبلغ
- [ ] اختبار نقص المبلغ
- [ ] اختبار فاتورة غير مرحّلة
- [ ] اختبار بدون فروقات
- [ ] اختبار مع منتجات بدون cost_price

### بعد الاختبار:
- [ ] التحقق من القيود التصحيحية
- [ ] التحقق من توازن القيود
- [ ] التحقق من حركات المخزون
- [ ] التحقق من أرصدة العملاء والموردين
- [ ] التحقق من التقارير المالية

---

## 🐛 الأخطاء المحتملة وحلولها

### خطأ: "لا يمكن العثور على الحسابات المحاسبية المطلوبة"

**الحل:**
```python
# تشغيل setup_default_accounts
from financial.services.accounting_integration_service import AccountingIntegrationService
AccountingIntegrationService.setup_default_accounts()
```

### خطأ: "لم يتم حساب التكلفة الأصلية"

**الحل:**
```python
# التأكد من أن المنتجات لها cost_price
from product.models import Product
products_without_cost = Product.objects.filter(cost_price__isnull=True)
print(f"عدد المنتجات بدون تكلفة: {products_without_cost.count()}")
```

### خطأ: "فشل إنشاء القيد التصحيحي"

**الحل:**
```python
# التحقق من السجلات
import logging
logger = logging.getLogger(__name__)
# راجع السجلات في console
```

---

## 📝 ملاحظات مهمة

1. **القيود التصحيحية تُنشأ فقط للفواتير المرحّلة**
   - إذا لم يكن هناك قيد محاسبي، لن يتم إنشاء قيد تصحيحي

2. **القيود التصحيحية مرحّلة تلقائياً**
   - `status = 'posted'` دائماً

3. **التاريخ**
   - القيد التصحيحي يأخذ تاريخ التعديل (اليوم)
   - وليس تاريخ الفاتورة الأصلية

4. **الفترة المحاسبية**
   - يتم تحديدها تلقائياً بناءً على تاريخ التعديل

5. **المستخدم**
   - يتم تسجيل المستخدم الذي قام بالتعديل في `created_by`

---

## 🎯 معايير النجاح

### ✅ النظام يعمل بشكل صحيح إذا:

1. **القيود متوازنة**
   - مجموع المدين = مجموع الدائن لكل قيد

2. **المخزون متطابق**
   - حركات المخزون تتطابق مع القيود المحاسبية

3. **الأرصدة صحيحة**
   - أرصدة العملاء والموردين تتطابق مع القيود

4. **التقارير دقيقة**
   - الإيرادات والتكاليف تعكس الواقع

5. **الأثر التدقيقي محفوظ**
   - يمكن تتبع جميع التغييرات

---

**تاريخ الإنشاء:** 2025-01-30  
**آخر تحديث:** 2025-01-30  
**الحالة:** ✅ جاهز للاختبار
