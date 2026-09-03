# Printing Pricing Master Seed Architecture

تم الاستغناء كلياً عن ملفات الـ JSON Fixtures الثابتة القديمة في هذا المجلد واستبدالها بالمعمارية البرمجية المركزية:
`printing_pricing.services.pricing_lookup_seeder_service.PricingLookupSeederService`

## أسباب الانتقال:
1. تجنب مشاكل الـ Foreign Keys الثابتة (Hardcoded PKs) التي كانت تسبب انهيار العلاقات بين مقاسات الفروخ ومقاسات القص `PieceSize`.
2. تجنب مشاكل `loaddata` وتجاوز دوال `save()` في نماذج الـ Proxy، ورفض MySQL لقيم `updated_at: null`.
3. التشغيل الذاتي الكامل (Self-Bootstrapping): يتم بذر وتحديث كافة الجداول تلقائياً عند تفعيل موديول `printing_pricing` عبر إشارة `SystemModule` وإشارة `post_migrate`.

## كيفية تشغيل البذر يدوياً:
```powershell
python manage.py seed_pricing_data
```
أو عبر بايثون:
```python
from printing_pricing.services.pricing_lookup_seeder_service import PricingLookupSeederService
PricingLookupSeederService.seed_all()
```
