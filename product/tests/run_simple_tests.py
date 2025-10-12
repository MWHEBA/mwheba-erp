#!/usr/bin/env python
"""
سكريبت بسيط لتشغيل اختبارات Django
"""
import os
import sys
from pathlib import Path

# إضافة مسار المشروع إلى sys.path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# إعداد Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mwheba_erp.settings")

import django

django.setup()

from django.test.utils import get_runner
from django.conf import settings


def run_simple_tests():
    """تشغيل الاختبارات البسيطة"""
    print("🧪 تشغيل اختبارات نظام المخزون البسيطة")
    print("=" * 50)

    TestRunner = get_runner(settings)
    test_runner = TestRunner(verbosity=2, interactive=False)

    # تشغيل الاختبار البسيط
    failures = test_runner.run_tests(["product.tests.test_simple"])

    if failures:
        print(f"\n❌ فشل {failures} اختبار")
        return False
    else:
        print("\n✅ جميع الاختبارات نجحت!")
        return True


def create_test_data():
    """إنشاء بيانات اختبار بسيطة"""
    print("📊 إنشاء بيانات اختبار...")

    try:
        from django.contrib.auth import get_user_model

        User = get_user_model()
        from product.models import Category, Brand, Unit, Warehouse

        # إنشاء مستخدم اختبار
        user, created = User.objects.get_or_create(
            username="testuser",
            defaults={
                "email": "test@example.com",
                "first_name": "مستخدم",
                "last_name": "اختبار",
            },
        )
        if created:
            user.set_password("testpass123")
            user.save()
            print("✅ تم إنشاء مستخدم اختبار")

        # إنشاء تصنيفات
        categories_data = [
            "إلكترونيات",
            "ملابس",
            "أطعمة",
        ]

        for cat_name in categories_data:
            category, created = Category.objects.get_or_create(name=cat_name)
            if created:
                print(f"✅ تم إنشاء تصنيف: {category.name}")

        # إنشاء ماركات
        brands_data = [
            "سامسونج",
            "آبل",
            "هواوي",
        ]

        for brand_name in brands_data:
            brand, created = Brand.objects.get_or_create(name=brand_name)
            if created:
                print(f"✅ تم إنشاء ماركة: {brand.name}")

        # إنشاء وحدات قياس
        units_data = [
            {"name": "قطعة", "symbol": "قطعة"},
            {"name": "كيلو", "symbol": "كجم"},
            {"name": "متر", "symbol": "م"},
        ]

        for unit_data in units_data:
            unit, created = Unit.objects.get_or_create(
                name=unit_data["name"], defaults={"symbol": unit_data["symbol"]}
            )
            if created:
                print(f"✅ تم إنشاء وحدة: {unit.name}")

        # إنشاء مخازن
        warehouses_data = [
            {"name": "المخزن الرئيسي", "location": "الرياض"},
            {"name": "مخزن فرعي", "location": "جدة"},
        ]

        for warehouse_data in warehouses_data:
            warehouse, created = Warehouse.objects.get_or_create(
                name=warehouse_data["name"],
                defaults={"location": warehouse_data["location"]},
            )
            if created:
                print(f"✅ تم إنشاء مخزن: {warehouse.name}")

        print("\n🎉 تم إنشاء جميع بيانات الاختبار بنجاح!")
        return True

    except Exception as e:
        print(f"❌ خطأ في إنشاء بيانات الاختبار: {e}")
        return False


def main():
    """الدالة الرئيسية"""
    if len(sys.argv) < 2:
        print("الاستخدام: python run_simple_tests.py [test|create-data]")
        return

    command = sys.argv[1]

    if command == "test":
        success = run_simple_tests()
    elif command == "create-data":
        success = create_test_data()
    else:
        print(f"❌ أمر غير معروف: {command}")
        success = False

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
