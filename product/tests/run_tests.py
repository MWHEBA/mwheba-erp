#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
سكريبت تشغيل اختبارات نظام المخزن المحسن
"""
import os
import sys
import subprocess
from pathlib import Path

# إضافة مسار المشروع إلى sys.path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# إعداد Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mwheba_erp.settings")

import django

django.setup()

from django.conf import settings
from django.test.utils import get_runner


def run_all_tests():
    """تشغيل جميع اختبارات المخزن"""
    print("🚀 بدء تشغيل اختبارات نظام المخزن المحسن...")
    print("=" * 60)

    TestRunner = get_runner(settings)
    test_runner = TestRunner(verbosity=2, interactive=True)

    # قائمة الاختبارات
    test_modules = [
        "product.tests.test_enhanced_inventory",
        "product.tests.test_advanced_services",
        "product.tests.test_views_and_apis",
    ]

    failures = test_runner.run_tests(test_modules)

    print("=" * 60)
    if failures:
        print(f"[ERROR] فشل {failures} اختبار")
        return False
    else:
        print("[OK] نجحت جميع الاختبارات!")
        return True


def run_specific_test(test_name):
    """تشغيل اختبار محدد"""
    print(f"🎯 تشغيل الاختبار: {test_name}")
    print("=" * 60)

    TestRunner = get_runner(settings)
    test_runner = TestRunner(verbosity=2, interactive=True)

    failures = test_runner.run_tests([test_name])

    print("=" * 60)
    if failures:
        print(f"[ERROR] فشل الاختبار {test_name}")
        return False
    else:
        print(f"[OK] نجح الاختبار {test_name}!")
        return True


def run_test_category(category):
    """تشغيل فئة معينة من الاختبارات"""
    categories = {
        "models": "product.tests.test_enhanced_inventory",
        "services": "product.tests.test_advanced_services",
        "views": "product.tests.test_views_and_apis",
        "inventory": [
            "product.tests.test_enhanced_inventory.ProductStockTestCase",
            "product.tests.test_enhanced_inventory.InventoryMovementTestCase",
            "product.tests.test_enhanced_inventory.InventoryServiceTestCase",
        ],
        "reservations": [
            "product.tests.test_enhanced_inventory.StockReservationTestCase",
            "product.tests.test_enhanced_inventory.ReservationServiceTestCase",
            "product.tests.test_views_and_apis.ReservationSystemTestCase",
        ],
        "expiry": [
            "product.tests.test_enhanced_inventory.ProductBatchTestCase",
            "product.tests.test_enhanced_inventory.ExpiryServiceTestCase",
            "product.tests.test_views_and_apis.ExpirySystemTestCase",
        ],
        "pricing": [
            "product.tests.test_advanced_services.PricingServiceTestCase",
            "product.tests.test_views_and_apis.SupplierPricingAPITestCase",
        ],
        "performance": "product.tests.test_advanced_services.PerformanceTestCase",
        "security": "product.tests.test_advanced_services.SecurityTestCase",
    }

    if category not in categories:
        print(f"[ERROR] فئة الاختبار '{category}' غير موجودة")
        print("التصنيفات المتاحة:", list(categories.keys()))
        return False

    test_modules = categories[category]
    if isinstance(test_modules, str):
        test_modules = [test_modules]

    print(f"🎯 تشغيل اختبارات فئة: {category}")
    print("=" * 60)

    TestRunner = get_runner(settings)
    test_runner = TestRunner(verbosity=2, interactive=True)

    failures = test_runner.run_tests(test_modules)

    print("=" * 60)
    if failures:
        print(f"[ERROR] فشل {failures} اختبار في فئة {category}")
        return False
    else:
        print(f"[OK] نجحت جميع اختبارات فئة {category}!")
        return True


def show_test_coverage():
    """عرض تغطية الاختبارات"""
    try:
        import coverage

        print("[STATS] تشغيل تحليل تغطية الاختبارات...")
        print("=" * 60)

        # إنشاء كائن التغطية
        cov = coverage.Coverage()
        cov.start()

        # تشغيل الاختبارات
        success = run_all_tests()

        # إيقاف التغطية وحفظ النتائج
        cov.stop()
        cov.save()

        print("\n📈 تقرير التغطية:")
        print("-" * 40)
        cov.report(show_missing=True)

        # إنشاء تقرير HTML
        cov.html_report(directory="htmlcov")
        print("\n📄 تم إنشاء تقرير HTML في مجلد htmlcov/")

        return success

    except ImportError:
        print("[WARNING]  مكتبة coverage غير مثبتة")
        print("لتثبيتها: pip install coverage")
        return run_all_tests()


def create_test_data():
    """إنشاء بيانات اختبار"""
    from product.tests.test_utils import TestDataFactory, TestScenarios

    print("[BUILD]  إنشاء بيانات اختبار...")
    print("=" * 60)

    try:
        # إنشاء سيناريو مخزون أساسي
        inventory_data = TestScenarios.setup_basic_inventory_scenario()
        print(f"[OK] تم إنشاء سيناريو المخزون الأساسي")
        print(f"   - المستخدم: {inventory_data['user'].username}")
        print(f"   - المخزن: {inventory_data['warehouse'].name}")
        print(f"   - المنتجات: {len(inventory_data['products'])}")

        # إنشاء سيناريو تسعير الموردين
        pricing_data = TestScenarios.setup_supplier_pricing_scenario()
        print(f"[OK] تم إنشاء سيناريو تسعير الموردين")
        print(f"   - المنتج: {pricing_data['product'].name}")
        print(f"   - الموردين: {len(pricing_data['suppliers'])}")

        # إنشاء سيناريو انتهاء الصلاحية
        expiry_data = TestScenarios.setup_expiry_tracking_scenario()
        print(f"[OK] تم إنشاء سيناريو انتهاء الصلاحية")
        print(f"   - المنتج: {expiry_data['product'].name}")
        print(f"   - الدفعات: {len(expiry_data['batches'])}")

        # إنشاء سيناريو الحجوزات
        reservation_data = TestScenarios.setup_reservation_scenario()
        print(f"[OK] تم إنشاء سيناريو الحجوزات")
        print(f"   - المنتج: {reservation_data['product'].name}")
        print(f"   - الحجوزات: {len(reservation_data['reservations'])}")

        print("\n[DONE] تم إنشاء جميع بيانات الاختبار بنجاح!")
        return True

    except Exception as e:
        print(f"[ERROR] خطأ في إنشاء بيانات الاختبار: {e}")
        return False


def clean_test_data():
    """تنظيف بيانات الاختبار"""
    print("🧹 تنظيف بيانات الاختبار...")
    print("=" * 60)

    try:
        from django.contrib.auth import get_user_model
        from product.models import Product, Category, Brand, Unit, Warehouse
        from supplier.models import Supplier

        User = get_user_model()

        # حذف البيانات بالترتيب الصحيح
        models_to_clean = [
            (Product, "المنتجات"),
            (Warehouse, "المخازن"),
            (Supplier, "الموردين"),
            (Category, "التصنيفات"),
            (Brand, "الأنواع"),
            (Unit, "وحدات القياس"),
        ]

        for model, name in models_to_clean:
            # حذف البيانات التي تحتوي على "اختبار" في الاسم
            count = model.objects.filter(name__icontains="اختبار").count()
            if count > 0:
                model.objects.filter(name__icontains="اختبار").delete()
                print(f"[OK] تم حذف {count} من {name}")

        # حذف المستخدمين الاختباريين
        test_users = User.objects.filter(username__startswith="test")
        user_count = test_users.count()
        if user_count > 0:
            test_users.delete()
            print(f"[OK] تم حذف {user_count} مستخدم اختباري")

        print("\n[DONE] تم تنظيف جميع بيانات الاختبار!")
        return True

    except Exception as e:
        print(f"[ERROR] خطأ في تنظيف بيانات الاختبار: {e}")
        return False


def print_help():
    """طباعة رسالة المساعدة"""
    print("🧪 نظام اختبارات المخزن المحسن")
    print("=" * 40)
    print()
    print("الاستخدام:")
    print("  python run_tests.py [command] [options]")
    print()
    print("الأوامر المتاحة:")
    print("  all                    - تشغيل جميع الاختبارات")
    print("  category <name>        - تشغيل فئة محددة من الاختبارات")
    print("  test <name>            - تشغيل اختبار محدد")
    print("  coverage               - تشغيل الاختبارات مع تحليل التغطية")
    print("  create-data            - إنشاء بيانات اختبار")
    print("  clean-data             - تنظيف بيانات الاختبار")
    print("  help, --help, -h       - عرض هذه الرسالة")
    print()
    print("فئات الاختبارات المتاحة:")
    print("  models                 - اختبارات النماذج")
    print("  services               - اختبارات الخدمات")
    print("  views                  - اختبارات الواجهات")
    print("  inventory              - اختبارات المخزون")
    print("  reservations           - اختبارات الحجوزات")
    print("  expiry                 - اختبارات انتهاء الصلاحية")
    print("  pricing                - اختبارات التسعير")
    print("  performance            - اختبارات الأداء")
    print("  security               - اختبارات الأمان")
    print()
    print("أمثلة:")
    print("  python run_tests.py all")
    print("  python run_tests.py category inventory")
    print("  python run_tests.py test ProductStockTestCase")
    print("  python run_tests.py coverage")


def main():
    """دالة رئيسية لتشغيل الاختبارات"""
    if len(sys.argv) < 2:
        print("[ERROR] يرجى تحديد نوع الاختبار")
        print(
            "الاستخدام: python run_tests.py [all|category|test|coverage|create-data|clean-data|help]"
        )
        print("- models, services, views")
        print("- inventory, reservations, expiry, pricing")
        print("- performance, security")
        return

    command = sys.argv[1]

    if command in ["--help", "-h", "help"]:
        print_help()
        return

    if command == "all":
        success = run_all_tests()
    elif command == "category" and len(sys.argv) > 2:
        success = run_test_category(sys.argv[2])
    elif command == "test" and len(sys.argv) > 2:
        success = run_specific_test(sys.argv[2])
    elif command == "coverage":
        success = show_test_coverage()
    elif command == "create-data":
        success = create_test_data()
    elif command == "clean-data":
        success = clean_test_data()
    else:
        print(f"[ERROR] أمر غير معروف: {command}")
        success = False

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
