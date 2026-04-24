#!/usr/bin/env python
"""
التحقق من تحديث فكستشرز الوحدات
Verify Units Fixtures Update Script
"""

import os
import sys
import django
import json

# إعداد Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'corporate_erp.settings')
django.setup()

from product.models import Unit


def verify_units_fixtures():
    """التحقق من تحديث فكستشرز الوحدات"""
    
    print("🔍 التحقق من تحديث فكستشرز الوحدات...")
    
    # قراءة ملف الفكستشرز
    fixtures_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'product', 'fixtures', 'units.json')
    
    if not os.path.exists(fixtures_path):
        print(f"❌ ملف الفكستشرز غير موجود: {fixtures_path}")
        return False
    
    try:
        with open(fixtures_path, 'r', encoding='utf-8') as f:
            fixtures_data = json.load(f)
    except Exception as e:
        print(f"❌ خطأ في قراءة ملف الفكستشرز: {e}")
        return False
    
    print(f"📄 تم قراءة ملف الفكستشرز: {len(fixtures_data)} عنصر")
    
    # التحقق من الوحدات في الفكستشرز
    print(f"\n📋 الوحدات في الفكستشرز:")
    
    expected_units = ['قطعة', 'كرتونة', 'طقم']
    found_units = []
    
    for item in fixtures_data:
        if item.get('model') == 'product.unit':
            fields = item.get('fields', {})
            name = fields.get('name', 'غير محدد')
            symbol = fields.get('symbol', 'غير محدد')
            is_active = fields.get('is_active', False)
            pk = item.get('pk', 'غير محدد')
            
            print(f"   • {name} (ID: {pk}, Symbol: {symbol})")
            print(f"     - نشطة: {'نعم' if is_active else 'لا'}")
            
            found_units.append(name)
    
    # التحقق من وجود جميع الوحدات المطلوبة
    print(f"\n🎯 نتائج التحقق:")
    
    all_found = True
    for unit_name in expected_units:
        if unit_name in found_units:
            print(f"   ✅ {unit_name} موجودة في الفكستشرز")
        else:
            print(f"   ❌ {unit_name} غير موجودة في الفكستشرز")
            all_found = False
    
    # التحقق من الوحدات في قاعدة البيانات
    print(f"\n💾 الوحدات في قاعدة البيانات:")
    db_units = Unit.objects.all().order_by('id')
    
    for unit in db_units:
        status = "✅ نشطة" if unit.is_active else "❌ غير نشطة"
        print(f"   • {unit.name} (ID: {unit.id}) - {status}")
    
    # التحقق من صحة JSON
    try:
        json.dumps(fixtures_data, ensure_ascii=False, indent=2)
        print(f"\n   ✅ ملف JSON صحيح ومنسق بشكل سليم")
    except Exception as e:
        print(f"   ❌ خطأ في تنسيق JSON: {e}")
        return False
    
    if all_found:
        print(f"\n🎉 تم تحديث فكستشرز الوحدات بنجاح!")
        print(f"📝 يمكن الآن استخدام الأمر: python manage.py loaddata product/fixtures/units.json")
    else:
        print(f"\n❌ فشل في تحديث فكستشرز الوحدات!")
    
    return all_found


if __name__ == '__main__':
    try:
        success = verify_units_fixtures()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"❌ خطأ في تنفيذ التحقق: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)