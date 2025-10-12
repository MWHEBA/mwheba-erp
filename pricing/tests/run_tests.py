#!/usr/bin/env python
"""
سكريبت تشغيل اختبارات نظام التسعير الشامل
Comprehensive Pricing System Test Runner
"""
import os
import sys
import django
import subprocess
import argparse
from pathlib import Path

# إضافة مسار المشروع
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# إعداد Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mwheba_erp.settings")
django.setup()


class PricingTestRunner:
    """مشغل اختبارات نظام التسعير"""

    def __init__(self):
        self.test_categories = {
            "models": "اختبارات النماذج",
            "views": "اختبارات الواجهات",
            "services": "اختبارات الخدمات",
            "apis": "اختبارات APIs",
            "forms": "اختبارات النماذج",
            "javascript": "اختبارات JavaScript",
            "integration": "اختبارات التكامل",
            "performance": "اختبارات الأداء",
            "security": "اختبارات الأمان",
        }

        self.test_files = {
            "models": "test_models.py",
            "views": "test_views.py",
            "services": "test_services.py",
            "apis": "test_apis.py",
            "forms": "test_forms.py",
            "javascript": "test_javascript.py",
        }

    def print_header(self):
        """طباعة رأس البرنامج"""
        print("=" * 80)
        print("مشغل اختبارات نظام التسعير الشامل")
        print("Comprehensive Pricing System Test Runner")
        print("=" * 80)
        print()

    def print_available_categories(self):
        """طباعة الفئات المتاحة"""
        print("فئات الاختبارات المتاحة:")
        print("-" * 40)
        for key, description in self.test_categories.items():
            print(f"  {key:<12} - {description}")
        print()

    def run_basic_tests(self):
        """تشغيل الاختبارات الأساسية"""
        print("تشغيل الاختبارات الأساسية...")
        print("-" * 40)

        try:
            # اختبار استيراد النماذج
            print("اختبار استيراد النماذج...")
            from pricing.models import PricingOrder, PaperType, PaperSize

            print("  تم استيراد النماذج بنجاح")

            # اختبار استيراد الخدمات
            print("اختبار استيراد الخدمات...")
            from pricing.services.calculator import PricingCalculatorService

            print("  تم استيراد الخدمات بنجاح")

            # اختبار استيراد النماذج
            print("اختبار استيراد النماذج...")
            from pricing.forms import PricingOrderForm

            print("  تم استيراد النماذج بنجاح")

            # اختبار الاتصال بقاعدة البيانات
            print("اختبار الاتصال بقاعدة البيانات...")
            count = PricingOrder.objects.count()
            print(f"  عدد طلبات التسعير: {count}")

            print("\nجميع الاختبارات الأساسية نجحت!")
            return True

        except Exception as e:
            print(f"\nفشل في الاختبارات الأساسية: {e}")
            return False

    def run_django_tests(self, test_file=None, verbose=False):
        """تشغيل اختبارات Django"""
        print("تشغيل اختبارات Django...")
        print("-" * 40)

        cmd = ["python", "manage.py", "test"]

        if test_file:
            cmd.append(f'pricing.tests.{test_file.replace(".py", "")}')
        else:
            cmd.append("pricing.tests")

        if verbose:
            cmd.append("--verbosity=2")

        try:
            result = subprocess.run(
                cmd, cwd=project_root, capture_output=True, text=True
            )

            if result.returncode == 0:
                print("اختبارات Django نجحت!")
                if verbose:
                    print(result.stdout)
            else:
                print("فشلت اختبارات Django!")
                print(result.stderr)

            return result.returncode == 0

        except Exception as e:
            print(f"خطأ في تشغيل اختبارات Django: {e}")
            return False

    def run_pytest_tests(self, test_file=None, markers=None, verbose=False):
        """تشغيل اختبارات pytest"""
        print("تشغيل اختبارات pytest...")
        print("-" * 40)

        cmd = ["pytest"]

        if test_file:
            cmd.append(f"pricing/tests/{test_file}")
        else:
            cmd.append("pricing/tests/")

        if markers:
            cmd.extend(["-m", markers])

        if verbose:
            cmd.append("-v")

        # إضافة تقرير التغطية
        cmd.extend(["--cov=pricing", "--cov-report=term-missing"])

        try:
            result = subprocess.run(cmd, cwd=project_root)
            return result.returncode == 0

        except Exception as e:
            print(f"خطأ في تشغيل pytest: {e}")
            return False

    def run_category_tests(self, category, verbose=False):
        """تشغيل اختبارات فئة معينة"""
        if category not in self.test_categories:
            print(f"فئة غير معروفة: {category}")
            return False

        print(f"تشغيل {self.test_categories[category]}...")
        print("-" * 40)

        if category in self.test_files:
            test_file = self.test_files[category]
            return self.run_pytest_tests(test_file, verbose=verbose)
        else:
            # تشغيل اختبارات بناءً على markers
            return self.run_pytest_tests(markers=category, verbose=verbose)

    def run_all_tests(self, verbose=False):
        """تشغيل جميع الاختبارات"""
        print("تشغيل جميع الاختبارات...")
        print("=" * 80)

        results = {}

        # الاختبارات الأساسية
        print("\n1. الاختبارات الأساسية:")
        results["basic"] = self.run_basic_tests()

        # اختبارات Django
        print("\n2. اختبارات Django:")
        results["django"] = self.run_django_tests(verbose=verbose)

        # اختبارات pytest
        print("\n3. اختبارات pytest:")
        results["pytest"] = self.run_pytest_tests(verbose=verbose)

        # تقرير النتائج
        self.print_results_summary(results)

        return all(results.values())

    def run_coverage_report(self):
        """تشغيل تقرير التغطية"""
        print("إنشاء تقرير التغطية...")
        print("-" * 40)

        cmd = [
            "pytest",
            "pricing/tests/",
            "--cov=pricing",
            "--cov-report=html",
            "--cov-report=term-missing",
            "--cov-report=xml",
        ]

        try:
            result = subprocess.run(cmd, cwd=project_root)

            if result.returncode == 0:
                print("تم إنشاء تقرير التغطية!")
                print("تقرير HTML: htmlcov/index.html")
                print("تقرير XML: coverage.xml")
            else:
                print("فشل في إنشاء تقرير التغطية!")

            return result.returncode == 0

        except Exception as e:
            print(f"خطأ في إنشاء تقرير التغطية: {e}")
            return False

    def print_results_summary(self, results):
        """طباعة ملخص النتائج"""
        print("\n" + "=" * 80)
        print("ملخص نتائج الاختبارات")
        print("=" * 80)

        total_tests = len(results)
        passed_tests = sum(1 for result in results.values() if result)

        for test_name, result in results.items():
            status = "نجح" if result else "فشل"
            print(f"  {test_name:<15} - {status}")

        print("-" * 80)
        print(f"الإجمالي: {passed_tests}/{total_tests} اختبار نجح")

        if passed_tests == total_tests:
            print("جميع الاختبارات نجحت!")
        else:
            print("بعض الاختبارات فشلت - يرجى المراجعة")

        print("=" * 80)

    def create_test_data(self):
        """إنشاء بيانات اختبار"""
        print("إنشاء بيانات الاختبار...")
        print("-" * 40)

        try:
            from django.contrib.auth.models import User
            from pricing.models import PaperType, PaperSize
            from decimal import Decimal

            # إنشاء مستخدم (تخطي إذا لم يكن متاحاً)
            try:
                user, created = User.objects.get_or_create(
                    username="testuser", defaults={"email": "test@example.com"}
                )
                if created:
                    user.set_password("testpass123")
                    user.save()
                    print("  تم إنشاء مستخدم الاختبار")
            except Exception as e:
                print(f"  تخطي المستخدم: {str(e)[:50]}...")

            # إنشاء عميل (تخطي إذا لم يكن متاحاً)
            try:
                from client.models import Client

                client, created = Client.objects.get_or_create(
                    name="عميل تجريبي",
                    defaults={"email": "client@test.com", "phone": "01234567890"},
                )
                if created:
                    print("  تم إنشاء عميل الاختبار")
            except ImportError:
                print("  تخطي العميل: النموذج غير متاح")

            # إنشاء أنواع الورق
            paper_types = [
                ("ورق أبيض", "ورق أبيض عادي"),
                ("ورق مقوى", "ورق مقوى للأغلفة"),
                ("ورق ملون", "ورق ملون للتصميم"),
            ]

            for name, description in paper_types:
                paper_type, created = PaperType.objects.get_or_create(
                    name=name, defaults={"description": description}
                )
                if created:
                    print(f"  تم إنشاء نوع ورق: {name}")

            # إنشاء مقاسات الورق
            paper_sizes = [("A4", 21.0, 29.7), ("A3", 29.7, 42.0), ("A5", 14.8, 21.0)]

            for name, width, height in paper_sizes:
                paper_size, created = PaperSize.objects.get_or_create(
                    name=name, defaults={"width": width, "height": height}
                )
                if created:
                    print(f"  تم إنشاء مقاس ورق: {name}")

            print("\nتم إنشاء جميع بيانات الاختبار بنجاح!")
            return True

        except Exception as e:
            print(f"\nفشل في إنشاء بيانات الاختبار: {e}")
            return False


def main():
    """الدالة الرئيسية"""
    parser = argparse.ArgumentParser(
        description="مشغل اختبارات نظام التسعير الشامل",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "command",
        choices=[
            "all",
            "basic",
            "django",
            "pytest",
            "category",
            "coverage",
            "create-data",
        ],
        help="نوع الاختبار المطلوب تشغيله",
    )

    parser.add_argument(
        "--category",
        choices=["models", "views", "services", "apis", "forms", "javascript"],
        help="فئة الاختبارات (مطلوب مع command=category)",
    )

    parser.add_argument("--verbose", "-v", action="store_true", help="عرض تفاصيل أكثر")

    args = parser.parse_args()

    runner = PricingTestRunner()
    runner.print_header()

    success = False

    if args.command == "all":
        success = runner.run_all_tests(verbose=args.verbose)

    elif args.command == "basic":
        success = runner.run_basic_tests()

    elif args.command == "django":
        success = runner.run_django_tests(verbose=args.verbose)

    elif args.command == "pytest":
        success = runner.run_pytest_tests(verbose=args.verbose)

    elif args.command == "category":
        if not args.category:
            print("يجب تحديد الفئة مع --category")
            runner.print_available_categories()
            sys.exit(1)
        success = runner.run_category_tests(args.category, verbose=args.verbose)

    elif args.command == "coverage":
        success = runner.run_coverage_report()

    elif args.command == "create-data":
        success = runner.create_test_data()

    # إنهاء البرنامج
    if success:
        print("\nتم تنفيذ الأمر بنجاح!")
        sys.exit(0)
    else:
        print("\nفشل في تنفيذ الأمر!")
        sys.exit(1)


if __name__ == "__main__":
    main()
