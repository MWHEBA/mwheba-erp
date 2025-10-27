# 🔍 تشخيص مشكلة قيد COGS المفقود

## ❌ المشكلة المكتشفة

### القيد الفعلي المُنشأ:
```
من حـ/ العملاء (11030)                    550 ج.م (مدين)
    إلى حـ/ إيرادات المبيعات (41010)      550 ج.م (دائن)
```

### القيد المفقود:
```
❌ من حـ/ تكلفة البضاعة المباعة (51010)  [التكلفة] (مدين)
❌     إلى حـ/ المخزون (11051)            [التكلفة] (دائن)
```

---

## 🔎 السبب الجذري

### الكود في `accounting_integration_service.py`:

```python
# السطر 85-104
# قيد تكلفة البضاعة المباعة (إذا كانت متاحة)
total_cost = cls._calculate_sale_cost(sale)
if total_cost > 0:  # ⚠️ هنا المشكلة!
    # مدين تكلفة البضاعة المباعة
    JournalEntryLine.objects.create(...)
    # دائن المخزون
    JournalEntryLine.objects.create(...)
```

### دالة حساب التكلفة:

```python
# السطر 436-455
def _calculate_sale_cost(cls, sale) -> Decimal:
    total_cost = Decimal("0.00")
    for item in sale.items.all():
        if hasattr(item.product, "cost_price") and item.product.cost_price:
            total_cost += item.product.cost_price * item.quantity
    
    # تسجيل للتشخيص
    if total_cost == 0:
        logger.warning(f"تكلفة البضاعة المباعة = 0 للفاتورة {sale.number}")
    
    return total_cost
```

---

## 💡 التشخيص

### السيناريو الحالي:

1. **فاتورة SALE0002** تم إنشاؤها بقيمة 550 ج.م
2. المنتجات المباعة **ليس لها سعر تكلفة** (`cost_price = 0` أو `NULL`)
3. دالة `_calculate_sale_cost()` ترجع `0`
4. الشرط `if total_cost > 0` يفشل
5. **لا يُنشأ قيد COGS**

### الدليل:

```python
# السطر 441-442
if hasattr(item.product, "cost_price") and item.product.cost_price:
    # ✅ يُضاف للتكلفة فقط إذا كان cost_price > 0
    total_cost += item.product.cost_price * item.quantity
```

**إذا كان `cost_price = 0` أو `None`:**
- ❌ الشرط `item.product.cost_price` يُقيّم كـ `False`
- ❌ لا يُضاف للتكلفة
- ❌ `total_cost` يظل = 0
- ❌ **لا يُنشأ قيد COGS**

---

## 🎯 الحلول المقترحة

### الحل 1: تحديد سعر التكلفة للمنتجات (موصى به) ✅

**الخطوات:**
1. الذهاب لصفحة المنتجات
2. تحديد سعر التكلفة لكل منتج
3. إعادة إنشاء الفاتورة أو تشغيل script لتحديث القيود

**الفائدة:**
- ✅ قيود COGS دقيقة
- ✅ تقارير مالية صحيحة
- ✅ حساب الأرباح دقيق

---

### الحل 2: إنشاء Script لتحديث القيود القديمة

**الملف:** `financial/management/commands/fix_missing_cogs.py`

```python
from django.core.management.base import BaseCommand
from sale.models import Sale
from financial.services.accounting_integration_service import AccountingIntegrationService

class Command(BaseCommand):
    help = 'إصلاح القيود المحاسبية المفقودة لتكلفة البضاعة المباعة'

    def handle(self, *args, **options):
        # البحث عن الفواتير بدون قيد COGS
        sales = Sale.objects.filter(
            status='confirmed',
            journal_entry__isnull=False
        )
        
        fixed_count = 0
        skipped_count = 0
        
        for sale in sales:
            # التحقق من وجود قيد COGS
            cogs_lines = sale.journal_entry.lines.filter(
                account__code='51010'
            )
            
            if not cogs_lines.exists():
                # حساب التكلفة
                total_cost = AccountingIntegrationService._calculate_sale_cost(sale)
                
                if total_cost > 0:
                    # إضافة قيد COGS للقيد الموجود
                    accounts = AccountingIntegrationService._get_required_accounts_for_sale()
                    
                    # مدين تكلفة البضاعة المباعة
                    JournalEntryLine.objects.create(
                        journal_entry=sale.journal_entry,
                        account=accounts["cost_of_goods_sold"],
                        debit=total_cost,
                        credit=Decimal("0.00"),
                        description=f"تكلفة البضاعة المباعة - فاتورة {sale.number} (محدث)",
                    )
                    
                    # دائن المخزون
                    JournalEntryLine.objects.create(
                        journal_entry=sale.journal_entry,
                        account=accounts["inventory"],
                        debit=Decimal("0.00"),
                        credit=total_cost,
                        description=f"تخفيض المخزون - فاتورة {sale.number} (محدث)",
                    )
                    
                    fixed_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f'✅ تم إصلاح قيد COGS للفاتورة {sale.number}')
                    )
                else:
                    skipped_count += 1
                    self.stdout.write(
                        self.style.WARNING(f'⚠️ تم تخطي الفاتورة {sale.number} (تكلفة = 0)')
                    )
        
        self.stdout.write(
            self.style.SUCCESS(f'\n✅ تم إصلاح {fixed_count} فاتورة')
        )
        self.stdout.write(
            self.style.WARNING(f'⚠️ تم تخطي {skipped_count} فاتورة (بدون تكلفة)')
        )
```

**الاستخدام:**
```bash
python manage.py fix_missing_cogs
```

---

### الحل 3: تقرير المنتجات بدون تكلفة

**الملف:** `product/management/commands/products_without_cost.py`

```python
from django.core.management.base import BaseCommand
from product.models import Product
from django.db.models import Q

class Command(BaseCommand):
    help = 'عرض المنتجات التي ليس لها سعر تكلفة'

    def handle(self, *args, **options):
        products = Product.objects.filter(
            Q(cost_price__isnull=True) | Q(cost_price=0),
            is_active=True
        )
        
        self.stdout.write(
            self.style.WARNING(f'\n⚠️ وُجد {products.count()} منتج بدون سعر تكلفة:\n')
        )
        
        for product in products:
            self.stdout.write(
                f'  - {product.name} (ID: {product.id})'
            )
        
        self.stdout.write(
            self.style.SUCCESS('\n✅ يرجى تحديد سعر التكلفة لهذه المنتجات')
        )
```

**الاستخدام:**
```bash
python manage.py products_without_cost
```

---

## 📊 التأثير

### الوضع الحالي:
```
فاتورة SALE0002:
  الإيرادات: 550 ج.م ✅
  التكلفة: 0 ج.م ❌
  مجمل الربح: 550 ج.م ❌ (خطأ!)
```

### بعد الإصلاح (مثال):
```
فاتورة SALE0002:
  الإيرادات: 550 ج.م ✅
  التكلفة: 350 ج.م ✅
  مجمل الربح: 200 ج.م ✅ (صحيح!)
```

---

## ✅ خطة العمل

### الخطوة 1: تحديد المنتجات بدون تكلفة
```bash
python manage.py products_without_cost
```

### الخطوة 2: تحديد سعر التكلفة
- الذهاب لصفحة كل منتج
- إدخال سعر التكلفة المناسب
- حفظ التغييرات

### الخطوة 3: إصلاح القيود القديمة
```bash
python manage.py fix_missing_cogs
```

### الخطوة 4: التحقق
- فتح صفحة القيود المحاسبية
- البحث عن فاتورة SALE0002
- التأكد من وجود 4 بنود (بدلاً من 2)

---

## 🎯 الخلاصة

**المشكلة:** المنتجات بدون سعر تكلفة → قيد COGS لا يُنشأ

**الحل:** تحديد سعر التكلفة لجميع المنتجات

**النتيجة:** قيود محاسبية كاملة ودقيقة ✅
