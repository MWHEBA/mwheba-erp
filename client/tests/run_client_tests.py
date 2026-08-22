#!/usr/bin/env python
"""
سكريبت لتشغيل اختبارات نظام العملاء
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


def run_client_tests():
    """تشغيل اختبارات نظام العملاء"""
    print("🧪 تشغيل اختبارات نظام العملاء")
    print("=" * 50)

    TestRunner = get_runner(settings)
    test_runner = TestRunner(verbosity=2, interactive=False)

    # تشغيل جميع اختبارات العملاء
    test_labels = [
        "client.tests.test_models",
        "client.tests.test_forms",
        "client.tests.test_signals",
        "client.tests.test_views",
        "client.tests.test_apis"
    ]
    
    failures = test_runner.run_tests(test_labels)

    if failures:
        print(f"\n❌ فشل {failures} اختبار")
        return False
    else:
        print("\n✅ جميع الاختبارات نجحت!")
        return True


def create_test_data():
    """إنشاء بيانات اختبار للعملاء"""
    print("📊 إنشاء بيانات اختبار للعملاء...")

    try:
        from django.contrib.auth import get_user_model
        from decimal import Decimal

        User = get_user_model()
        from client.models import Customer

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

        # إنشاء عملاء تجريبيين
        customers_data = [
            {
                "name": "عميل فرد",
                "code": "IND001",
                "email": "individual@test.com",
                "phone": "+201234567890",
                "client_type": "individual",
                "credit_limit": Decimal("10000.00"),
            },
            {
                "name": "شركة اختبار",
                "code": "COMP001",
                "company_name": "شركة اختبار المحدودة",
                "email": "company@test.com",
                "phone": "+201098765432",
                "client_type": "company",
                "credit_limit": Decimal("50000.00"),
            },
            {
                "name": "عميل VIP",
                "code": "VIP001",
                "email": "vip@test.com",
                "phone": "+201111111111",
                "client_type": "individual",
                "is_vip": True,
                "credit_limit": Decimal("100000.00"),
            },
        ]

        for customer_data in customers_data:
            customer, created = Customer.objects.get_or_create(
                code=customer_data["code"], defaults=customer_data
            )
            if created:
                print(f"✅ تم إنشاء عميل: {customer.name}")

        print("\n🎉 تم إنشاء جميع بيانات الاختبار بنجاح!")
        return True

    except Exception as e:
        print(f"❌ خطأ في إنشاء بيانات الاختبار: {e}")
        import traceback

        traceback.print_exc()
        return False


def show_test_statistics():
    """عرض إحصائيات بيانات الاختبار"""
    print("📊 إحصائيات بيانات الاختبار")
    print("=" * 50)

    try:
        from client.models import Customer, CustomerPayment
        from decimal import Decimal
        from django.db.models import Sum

        # عدد العملاء
        total_customers = Customer.objects.count()
        active_customers = Customer.objects.filter(is_active=True).count()
        vip_customers = Customer.objects.filter(is_vip=True).count()
        print(f"📌 إجمالي العملاء: {total_customers}")
        print(f"✅ العملاء النشطين: {active_customers}")
        print(f"⭐ عملاء مميزين (VIP): {vip_customers}")

        # العملاء حسب النوع
        individual_count = Customer.objects.filter(client_type="individual").count()
        company_count = Customer.objects.filter(client_type="company").count()
        government_count = Customer.objects.filter(client_type="government").count()

        print(f"\n📋 توزيع العملاء حسب الكيان القانوني:")
        print(f"   - أفراد: {individual_count}")
        print(f"   - شركات: {company_count}")
        print(f"   - جهات حكومية: {government_count}")

        # المدفوعات
        total_payments = CustomerPayment.objects.count()
        print(f"\n💰 إجمالي المدفوعات: {total_payments}")

        # إجمالي الأرصدة
        total_balance = (
            Customer.objects.aggregate(total=Sum("balance"))["total"] or Decimal("0.00")
        )
        print(f"💵 إجمالي الأرصدة: {total_balance:.2f} جنيه")
        
        # إجمالي حدود الائتمان
        total_credit = (
            Customer.objects.aggregate(total=Sum("credit_limit"))["total"] or Decimal("0.00")
        )
        print(f"💳 إجمالي حدود الائتمان: {total_credit:.2f} جنيه")

        return True

    except Exception as e:
        print(f"❌ خطأ في عرض الإحصائيات: {e}")
        import traceback

        traceback.print_exc()
        return False


def clean_test_data():
    """مسح بيانات الاختبار"""
    print("🧹 مسح بيانات الاختبار...")

    try:
        from client.models import Customer, CustomerPayment

        # مسح المدفوعات
        payments_count = CustomerPayment.objects.count()
        CustomerPayment.objects.all().delete()
        print(f"✅ تم مسح {payments_count} دفعة")

        # مسح العملاء
        customers_count = Customer.objects.count()
        Customer.objects.all().delete()
        print(f"✅ تم مسح {customers_count} عميل")

        print("\n🎉 تم مسح جميع بيانات الاختبار بنجاح!")
        return True

    except Exception as e:
        print(f"❌ خطأ في مسح بيانات الاختبار: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """الدالة الرئيسية"""
    if len(sys.argv) < 2:
        print("الاستخدام:")
        print("  python run_client_tests.py test           - تشغيل الاختبارات")
        print("  python run_client_tests.py create-data    - إنشاء بيانات اختبار")
        print("  python run_client_tests.py stats          - عرض الإحصائيات")
        print("  python run_client_tests.py clean          - مسح بيانات الاختبار")
        return

    command = sys.argv[1]

    if command == "test":
        success = run_client_tests()
    elif command == "create-data":
        success = create_test_data()
    elif command == "stats":
        success = show_test_statistics()
    elif command == "clean":
        success = clean_test_data()
    else:
        print(f"❌ أمر غير معروف: {command}")
        success = False

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
