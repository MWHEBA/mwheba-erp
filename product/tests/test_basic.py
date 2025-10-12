"""
اختبار أساسي للتأكد من إعداد النظام
"""
import os
import sys
from pathlib import Path

# إضافة مسار المشروع
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# إعداد Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mwheba_erp.settings")

import django

django.setup()


def test_django_setup():
    """اختبار إعداد Django"""
    print("🧪 اختبار إعداد Django...")

    try:
        from django.conf import settings

        print(f"✅ Django version: {django.get_version()}")
        print(f"✅ Settings module: {settings.SETTINGS_MODULE}")
        print(f"✅ Database: {settings.DATABASES['default']['ENGINE']}")
        return True
    except Exception as e:
        print(f"❌ خطأ في إعداد Django: {e}")
        return False


def test_product_models_import():
    """اختبار استيراد نماذج المنتجات"""
    print("\n🧪 اختبار استيراد نماذج المنتجات...")

    try:
        from product.models import Category, Brand, Unit, Warehouse, Product

        print("✅ تم استيراد Category")
        print("✅ تم استيراد Brand")
        print("✅ تم استيراد Unit")
        print("✅ تم استيراد Warehouse")
        print("✅ تم استيراد Product")
        return True
    except Exception as e:
        print(f"❌ خطأ في استيراد النماذج: {e}")
        return False


def test_enhanced_models_import():
    """اختبار استيراد النماذج المحسنة"""
    print("\n🧪 اختبار استيراد النماذج المحسنة...")

    try:
        from product.models import (
            ProductStock,
            InventoryMovement,
            StockReservation,
            ProductBatch,
            LocationZone,
        )

        print("✅ تم استيراد ProductStock")
        print("✅ تم استيراد InventoryMovement")
        print("✅ تم استيراد StockReservation")
        print("✅ تم استيراد ProductBatch")
        print("✅ تم استيراد LocationZone")
        return True
    except Exception as e:
        print(f"❌ خطأ في استيراد النماذج المحسنة: {e}")
        return False


def test_pricing_models_import():
    """اختبار استيراد نماذج التسعير"""
    print("\n🧪 اختبار استيراد نماذج التسعير...")

    try:
        from product.models import SupplierProductPrice, PriceHistory

        print("✅ تم استيراد SupplierProductPrice")
        print("✅ تم استيراد PriceHistory")
        return True
    except Exception as e:
        print(f"❌ خطأ في استيراد نماذج التسعير: {e}")
        return False


def test_user_model():
    """اختبار نموذج المستخدم"""
    print("\n🧪 اختبار نموذج المستخدم...")

    try:
        from django.contrib.auth import get_user_model

        User = get_user_model()
        print(f"✅ نموذج المستخدم: {User}")
        return True
    except Exception as e:
        print(f"❌ خطأ في نموذج المستخدم: {e}")
        return False


def run_all_tests():
    """تشغيل جميع الاختبارات"""
    print("🚀 بدء اختبارات النظام الأساسية")
    print("=" * 50)

    tests = [
        test_django_setup,
        test_product_models_import,
        test_enhanced_models_import,
        test_pricing_models_import,
        test_user_model,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ خطأ في {test.__name__}: {e}")
            failed += 1

    print("\n" + "=" * 50)
    print(f"📊 النتائج النهائية:")
    print(f"✅ نجح: {passed}")
    print(f"❌ فشل: {failed}")

    if failed == 0:
        print("🎉 جميع الاختبارات نجحت!")
        return True
    else:
        print("⚠️ بعض الاختبارات فشلت")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
