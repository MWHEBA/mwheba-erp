# تحليل شامل: قيد تكلفة البضاعة المباعة (COGS)

## 📋 النظام الحالي

### آلية العمل التلقائية

```python
# ملف: sale/signals.py
@receiver(post_save, sender=Sale)
def create_financial_transaction_for_sale(sender, instance, created, **kwargs):
    """إنشاء قيد محاسبي تلقائي عند تأكيد فاتورة المبيعات"""
    if created and instance.status == "confirmed":
        journal_entry = AccountingIntegrationService.create_sale_journal_entry(
            sale=instance, user=instance.created_by
        )
```

**الشروط:**
- ✅ فاتورة جديدة (`created=True`)
- ✅ حالة مؤكدة (`status="confirmed"`)
- ✅ تلقائي بالكامل

---

## 🔄 القيود المحاسبية

### مثال: فاتورة بقيمة 10,000 ج.م وتكلفة 6,000 ج.م

```
من حـ/ العملاء (11030)                    10,000 ج.م (مدين)
    إلى حـ/ إيرادات المبيعات (41010)      10,000 ج.م (دائن)

من حـ/ تكلفة البضاعة المباعة (51010)      6,000 ج.م (مدين)
    إلى حـ/ المخزون (11051)                6,000 ج.م (دائن)
```

---

## 💰 حساب التكلفة

```python
# ملف: financial/services/accounting_integration_service.py
def _calculate_sale_cost(cls, sale) -> Decimal:
    total_cost = Decimal("0.00")
    for item in sale.items.all():
        if hasattr(item.product, "cost_price") and item.product.cost_price:
            total_cost += item.product.cost_price * item.quantity
    return total_cost
```

**المعادلة:**
```
COGS = Σ (سعر تكلفة المنتج × الكمية المباعة)
```

---

## 📊 الحسابات المستخدمة

| الكود | الاسم | النوع | الطبيعة |
|-------|-------|-------|---------|
| 51010 | تكلفة البضاعة المباعة | مصروفات | مدين |
| 11051 | المخزون | أصول | مدين |
| 41010 | إيرادات المبيعات | إيرادات | دائن |
| 11030 | العملاء | أصول | مدين |

---

## ⚠️ المشاكل المحتملة

### 1. منتج بدون سعر تكلفة

**المشكلة:**
```python
product.cost_price = 0  # أو None
# النتيجة: total_cost = 0
# لا يُنشأ قيد COGS
```

**التأثير:**
- ✅ قيد الإيراد يُنشأ
- ❌ قيد التكلفة لا يُنشأ
- ⚠️ المخزون لا يتأثر محاسبياً

**الحل:**
```python
# يسجل تحذير في logs
logger.warning(f"تكلفة البضاعة المباعة = 0 للفاتورة {sale.number}")
```

**التوصية:**
- إضافة validation في نموذج البيع
- تنبيه المستخدم قبل البيع
- تقرير دوري بالمنتجات بدون تكلفة

---

### 2. تعديل الفاتورة بعد الإنشاء

**المشكلة:**
```python
sale.items.add(new_item)  # إضافة منتج جديد
sale.save()
# Signal لا يعمل (created=False)
```

**التأثير:**
- ❌ القيد المحاسبي لا يتحدث
- ⚠️ عدم تطابق بين الفاتورة والقيد

**التوصيات:**
1. منع التعديل بعد التأكيد
2. إضافة signal للتحديث
3. إلغاء القيد القديم وإنشاء جديد

---

### 3. مرتجعات المبيعات

**الوضع الحالي:**
```python
@receiver(post_save, sender=SaleReturn)
def create_financial_transaction_for_return(sender, instance, **kwargs):
    pass  # معطل حالياً
```

**المشكلة:**
- ❌ لا يُنشأ قيد للمرتجعات
- ⚠️ عدم انعكاس المرتجعات في الحسابات

**القيد المطلوب:**
```
من حـ/ إيرادات المبيعات (41010)          2,000 ج.م (مدين)
    إلى حـ/ العملاء (11030)               2,000 ج.م (دائن)

من حـ/ المخزون (11051)                   1,200 ج.م (مدين)
    إلى حـ/ تكلفة البضاعة المباعة (51010) 1,200 ج.م (دائن)
```

---

## 📈 التأثير على القوائم المالية

### قائمة الدخل
```
إيرادات المبيعات                    100,000 ج.م
(-) تكلفة البضاعة المباعة           (60,000 ج.م)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
= مجمل الربح                         40,000 ج.م

نسبة مجمل الربح = 40%
```

### الميزانية
```
المخزون:
  الرصيد الافتتاحي     80,000 ج.م
  (-) تكلفة المباع     (60,000 ج.م)
  (+) المشتريات          50,000 ج.م
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  = الرصيد الختامي       70,000 ج.م
```

---

## 🎯 التوصيات

### 1. التحقق من سعر التكلفة
```python
def clean(self):
    for item in self.items:
        if not item.product.cost_price:
            raise ValidationError(
                f"المنتج '{item.product.name}' ليس له سعر تكلفة"
            )
```

### 2. معالجة المرتجعات
```python
@receiver(post_save, sender=SaleReturn)
def create_financial_transaction_for_return(sender, instance, **kwargs):
    if instance.status == "confirmed":
        AccountingIntegrationService.create_return_journal_entry(instance)
```

### 3. تقرير مطابقة COGS
```python
def cogs_reconciliation_report(date_from, date_to):
    # مقارنة بين:
    # 1. القيود المحاسبية
    # 2. فواتير المبيعات
    # 3. حركات المخزون
```

---

## ✅ الخلاصة

### يعمل بشكل صحيح:
1. ✅ إنشاء قيد تلقائي عند البيع
2. ✅ حساب التكلفة من المنتجات
3. ✅ قيد مزدوج كامل (إيراد + تكلفة)
4. ✅ تأثير على المخزون والإيرادات

### يحتاج تحسين:
1. ⚠️ معالجة المنتجات بدون تكلفة
2. ⚠️ تعديل الفواتير بعد الإنشاء
3. ⚠️ قيود المرتجعات
4. ⚠️ تقارير المطابقة

---

## 📚 الملفات الأساسية

1. `sale/signals.py` - Signal البيع
2. `financial/services/accounting_integration_service.py` - خدمة التكامل
3. `product/models/base_models.py` - نموذج المنتج
4. `financial/models/journal_entry.py` - القيود المحاسبية
5. `financial/fixtures/chart_of_accounts_final.json` - دليل الحسابات
