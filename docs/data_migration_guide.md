# دليل نقل البيانات من النظام القديم إلى الجديد

## نظرة عامة
يوفر هذا الدليل تعليمات شاملة لنقل البيانات من نظام التسعير القديم إلى النظام الجديد المطور.

## الأوامر المتاحة

### 1. تصدير البيانات الحالية (نسخة احتياطية)
```bash
# تصدير جميع البيانات بتنسيق JSON
python manage.py export_pricing_data --output-file backup_2025.json

# تصدير البيانات بتنسيق CSV
python manage.py export_pricing_data --output-file backup_2025.csv --format csv
```

### 2. نقل البيانات من النظام القديم
```bash
# نقل البيانات من قاعدة بيانات SQLite القديمة
python manage.py migrate_old_pricing_data --old-db-path /path/to/old/database.db

# تشغيل تجريبي لمعاينة البيانات بدون حفظ
python manage.py migrate_old_pricing_data --old-db-path /path/to/old/database.db --dry-run

# مسح البيانات الموجودة قبل النقل
python manage.py migrate_old_pricing_data --old-db-path /path/to/old/database.db --clear-existing
```

### 3. استيراد البيانات من ملف JSON
```bash
# استيراد البيانات من ملف نسخة احتياطية
python manage.py import_pricing_data --input-file backup_2025.json

# تشغيل تجريبي
python manage.py import_pricing_data --input-file backup_2025.json --dry-run

# مسح البيانات الموجودة قبل الاستيراد
python manage.py import_pricing_data --input-file backup_2025.json --clear-existing
```

## خطوات النقل الموصى بها

### الخطوة 1: عمل نسخة احتياطية من البيانات الحالية
```bash
python manage.py export_pricing_data --output-file backup_before_migration.json
```

### الخطوة 2: التحقق من البيانات القديمة (تشغيل تجريبي)
```bash
python manage.py migrate_old_pricing_data --old-db-path /path/to/old/database.db --dry-run
```

### الخطوة 3: تنفيذ النقل الفعلي
```bash
python manage.py migrate_old_pricing_data --old-db-path /path/to/old/database.db --clear-existing
```

### الخطوة 4: التحقق من البيانات المنقولة
- تصفح واجهات الإدارة للتأكد من نقل البيانات بشكل صحيح
- التحقق من العلاقات بين الجداول
- اختبار وظائف النظام الأساسية

## البيانات المدعومة للنقل

### إعدادات الورق
- ✅ أنواع الورق (PaperType)
- ✅ مقاسات الورق (PaperSize) 
- ✅ أوزان الورق (PaperWeight)
- ✅ مناشئ الورق (PaperOrigin)

### إعدادات الطباعة
- ✅ اتجاهات الطباعة (PrintDirection)
- ✅ جوانب الطباعة (PrintSide)

### إعدادات التشطيب
- ✅ أنواع التغطية (CoatingType)
- ✅ أنواع التشطيب (FinishingType)

### إعدادات المنتجات
- ✅ أنواع المنتجات (ProductType)
- ✅ مقاسات المنتجات (ProductSize)
- ✅ مقاسات القطع (PieceSize)

### إعدادات الماكينات
- ✅ أنواع ماكينات الأوفست (OffsetMachineType)
- ✅ مقاسات ماكينات الأوفست (OffsetSheetSize)
- ✅ أنواع ماكينات الديجيتال (DigitalMachineType)
- ✅ مقاسات ماكينات الديجيتال (DigitalSheetSize)

### إعدادات أخرى
- ✅ مقاسات الزنكات (PlateSize)
- ✅ إعدادات النظام (SystemSetting)

## هيكل قاعدة البيانات القديمة المتوقع

يتوقع السكريبت وجود الجداول التالية في قاعدة البيانات القديمة:

```sql
-- أمثلة على هيكل الجداول المتوقعة
CREATE TABLE paper_types (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT 1,
    is_default BOOLEAN DEFAULT 0
);

CREATE TABLE paper_sizes (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    width REAL,
    height REAL,
    is_active BOOLEAN DEFAULT 1,
    is_default BOOLEAN DEFAULT 0
);

-- ... باقي الجداول
```

## معالجة الأخطاء الشائعة

### خطأ: الجدول غير موجود
```
الجدول paper_types غير موجود في قاعدة البيانات القديمة
```
**الحل**: تأكد من أن قاعدة البيانات القديمة تحتوي على الجداول المطلوبة أو قم بتخطي الجداول المفقودة.

### خطأ: تضارب في البيانات الفريدة
```
UNIQUE constraint failed: printing_pricing_paperorigin.code
```
**الحل**: تحقق من وجود بيانات مكررة في النظام القديم أو استخدم خيار `--clear-existing`.

### خطأ: حقل مفقود
```
no such column: description
```
**الحل**: تأكد من أن هيكل قاعدة البيانات القديمة يتطابق مع المتوقع أو قم بتعديل السكريبت.

## نصائح مهمة

### 1. اختبار البيانات
- استخدم دائماً `--dry-run` أولاً للتحقق من البيانات
- اختبر على نسخة تطوير قبل الإنتاج

### 2. النسخ الاحتياطية
- احتفظ بنسخة احتياطية من البيانات الحالية
- احتفظ بنسخة من قاعدة البيانات القديمة

### 3. التحقق من البيانات
- تحقق من صحة البيانات المنقولة
- اختبر الوظائف الأساسية بعد النقل

### 4. الأداء
- قد يستغرق نقل البيانات الكبيرة وقتاً طويلاً
- فكر في تقسيم العملية إلى دفعات صغيرة للبيانات الضخمة

## استكشاف الأخطاء

### تشغيل السكريبت في وضع التصحيح
```bash
python manage.py migrate_old_pricing_data --old-db-path /path/to/old/database.db --dry-run --verbosity=2
```

### فحص سجلات Django
تأكد من تفعيل سجلات Django للحصول على معلومات تفصيلية عن الأخطاء.

### التحقق من البيانات يدوياً
```python
# في Django shell
python manage.py shell

from printing_pricing.models.settings_models import PaperType
print(f"عدد أنواع الورق: {PaperType.objects.count()}")
```

## الدعم والمساعدة

في حالة مواجهة مشاكل:
1. تحقق من سجلات الأخطاء
2. استخدم وضع التشغيل التجريبي للتشخيص
3. راجع هيكل قاعدة البيانات القديمة
4. تواصل مع فريق التطوير مع تفاصيل الخطأ
