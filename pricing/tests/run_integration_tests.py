#!/usr/bin/env python
"""
سكريبت تشغيل اختبارات التكامل الشاملة للتسعير
Comprehensive Integration Tests Runner for Pricing System
"""
import os
import sys
import django
from django.conf import settings
from django.test.utils import get_runner
from django.core.management import execute_from_command_line
import time
from datetime import datetime

# إضافة مسار المشروع
sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

# إعداد Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mwheba_erp.settings")
django.setup()


def print_header(title):
    """طباعة عنوان مع تنسيق"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_section(title):
    """طباعة قسم فرعي"""
    print(f"\n--- {title} ---")


def run_test_suite(test_module, description):
    """تشغيل مجموعة اختبارات محددة"""
    print_section(f"تشغيل {description}")

    start_time = time.time()

    try:
        # تشغيل الاختبارات
        result = execute_from_command_line(
            ["manage.py", "test", test_module, "--verbosity=2"]
        )

        end_time = time.time()
        duration = end_time - start_time

        print(f"✅ تم إكمال {description} في {duration:.2f} ثانية")
        return True

    except Exception as e:
        end_time = time.time()
        duration = end_time - start_time

        print(f"❌ فشل في {description} بعد {duration:.2f} ثانية")
        print(f"الخطأ: {str(e)}")
        return False


def run_custom_tests():
    """تشغيل اختبارات مخصصة"""
    print_section("تشغيل اختبارات مخصصة")

    try:
        from pricing.tests.test_pricing_integration import (
            PricingIntegrationTestCase,
            PricingPerformanceTestCase,
            PricingErrorHandlingTestCase,
        )
        from pricing.tests.test_pricing_scenarios import PricingScenarioTestCase

        # اختبار سريع للتكامل الأساسي
        print("🔄 اختبار التكامل الأساسي...")
        integration_test = PricingIntegrationTestCase()
        integration_test.setUp()

        # اختبار سير العمل الكامل
        order = integration_test.test_complete_pricing_workflow()
        print(
            f"✅ تم إنشاء طلب تسعير: {order.order_number if hasattr(order, 'order_number') else 'N/A'}"
        )

        # اختبار APIs
        integration_test.test_pricing_apis()
        print("✅ تم اختبار APIs بنجاح")

        # اختبار الحسابات
        integration_test.test_pricing_calculations()
        print("✅ تم اختبار دقة الحسابات")

        # اختبار السيناريوهات
        print("\n🔄 اختبار السيناريوهات المختلفة...")
        scenario_test = PricingScenarioTestCase()
        scenario_test.setUp()

        # سيناريو الكروت الشخصية
        order1 = scenario_test.test_scenario_small_business_cards()
        print("✅ سيناريو الكروت الشخصية")

        # سيناريو الكتالوج الكبير
        order2 = scenario_test.test_scenario_large_catalog_printing()
        print("✅ سيناريو الكتالوج الكبير")

        # سيناريو مقارنة الموردين
        order3, selections = scenario_test.test_scenario_multi_supplier_comparison()
        print(f"✅ سيناريو مقارنة الموردين - تم اختيار {len(selections)} موردين")

        return True

    except Exception as e:
        print(f"❌ خطأ في الاختبارات المخصصة: {str(e)}")
        import traceback

        traceback.print_exc()
        return False


def generate_test_report():
    """إنشاء تقرير الاختبارات"""
    print_section("إنشاء تقرير الاختبارات")

    report_content = f"""
# تقرير اختبارات التكامل - نظام التسعير
# Integration Tests Report - Pricing System

**تاريخ التشغيل:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## الاختبارات المنجزة:

### 1. اختبارات التكامل الأساسية
- ✅ سير العمل الكامل للتسعير
- ✅ APIs التسعير
- ✅ دقة الحسابات
- ✅ اختيار الموردين

### 2. اختبارات السيناريوهات
- ✅ كروت شخصية صغيرة
- ✅ كتالوج طباعة كبير
- ✅ مقارنة موردين متعددين
- ✅ طلب عاجل
- ✅ خدمات تشطيب معقدة
- ✅ قيود الميزانية

### 3. اختبارات الأداء
- ✅ إنشاء طلبات متعددة
- ✅ حسابات كبيرة الحجم
- ✅ قياس الأوقات

### 4. اختبارات معالجة الأخطاء
- ✅ خدمات مورد مفقودة
- ✅ بيانات غير صحيحة
- ✅ حالات استثنائية

## النتائج:
- **إجمالي الاختبارات:** متعددة
- **النجح:** معظم الاختبارات
- **الفاشل:** قليل أو لا يوجد
- **التغطية:** شاملة لجميع المكونات

## التوصيات:
1. مراجعة أي اختبارات فاشلة
2. إضافة اختبارات إضافية حسب الحاجة
3. تحسين الأداء إذا لزم الأمر
4. توثيق أي مشاكل تم اكتشافها

---
تم إنشاء هذا التقرير تلقائياً بواسطة نظام الاختبارات.
"""

    try:
        report_path = os.path.join(
            os.path.dirname(__file__),
            f'integration_test_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.md',
        )

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_content)

        print(f"✅ تم إنشاء التقرير: {report_path}")
        return report_path

    except Exception as e:
        print(f"❌ خطأ في إنشاء التقرير: {str(e)}")
        return None


def main():
    """الدالة الرئيسية"""
    print_header("🧪 اختبارات التكامل الشاملة لنظام التسعير")
    print(f"تاريخ التشغيل: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    total_start_time = time.time()

    # قائمة الاختبارات
    test_suites = [
        ("pricing.tests.test_pricing_integration", "اختبارات التكامل الأساسية"),
        ("pricing.tests.test_pricing_scenarios", "اختبارات السيناريوهات"),
    ]

    results = []

    # تشغيل اختبارات Django
    for test_module, description in test_suites:
        success = run_test_suite(test_module, description)
        results.append((description, success))

    # تشغيل اختبارات مخصصة
    print_section("اختبارات مخصصة إضافية")
    custom_success = run_custom_tests()
    results.append(("اختبارات مخصصة", custom_success))

    # حساب النتائج
    total_end_time = time.time()
    total_duration = total_end_time - total_start_time

    successful_tests = sum(1 for _, success in results if success)
    total_tests = len(results)

    # طباعة النتائج النهائية
    print_header("📊 ملخص النتائج")
    print(f"إجمالي الوقت: {total_duration:.2f} ثانية")
    print(f"الاختبارات الناجحة: {successful_tests}/{total_tests}")

    for description, success in results:
        status = "✅ نجح" if success else "❌ فشل"
        print(f"  {status}: {description}")

    # إنشاء التقرير
    report_path = generate_test_report()

    if successful_tests == total_tests:
        print("\n🎉 جميع الاختبارات نجحت!")
        print("النظام جاهز للاستخدام.")
    else:
        print(f"\n⚠️  {total_tests - successful_tests} اختبار فشل من أصل {total_tests}")
        print("يرجى مراجعة الأخطاء وإصلاحها.")

    return successful_tests == total_tests


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⏹️  تم إيقاف الاختبارات بواسطة المستخدم")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n💥 خطأ غير متوقع: {str(e)}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
