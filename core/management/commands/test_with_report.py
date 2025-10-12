import os
import sys
import subprocess
import datetime
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.test.runner import DiscoverRunner
from django.test.utils import get_runner
import unittest
import json
import html
import colorama


class HTMLTestResultWithTime(unittest.TextTestResult):
    """نتيجة اختبار تقوم بتخزين وقت كل اختبار وحالة الاكتمال"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.test_timings = {}
        self.results = {"passed": [], "failed": [], "skipped": [], "errors": []}
        colorama.init()

    def startTest(self, test):
        self.start_time = datetime.datetime.now()
        super().startTest(test)

    def _record_test(self, test, category, err=None):
        test_id = test.id()
        test_name = test.shortDescription() or str(test)
        duration = datetime.datetime.now() - self.start_time
        self.test_timings[test_id] = duration.total_seconds()

        error_info = None
        if err:
            error_type, error_value, _ = err
            error_info = f"{error_type.__name__}: {error_value}"

        self.results[category].append(
            {
                "id": test_id,
                "name": test_name,
                "time": self.test_timings[test_id],
                "error": error_info,
            }
        )

    def addSuccess(self, test):
        super().addSuccess(test)
        self._record_test(test, "passed")
        print(f"{colorama.Fore.GREEN}• {test.id()} - نجح{colorama.Style.RESET_ALL}")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._record_test(test, "failed", err)
        print(f"{colorama.Fore.RED}✗ {test.id()} - فشل{colorama.Style.RESET_ALL}")
        print(f"  {colorama.Fore.RED}{err[1]}{colorama.Style.RESET_ALL}")

    def addError(self, test, err):
        super().addError(test, err)
        self._record_test(test, "errors", err)
        print(f"{colorama.Fore.YELLOW}! {test.id()} - خطأ{colorama.Style.RESET_ALL}")
        print(f"  {colorama.Fore.YELLOW}{err[1]}{colorama.Style.RESET_ALL}")

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._record_test(test, "skipped")
        print(f"{colorama.Fore.BLUE}- {test.id()} - تم تخطيه{colorama.Style.RESET_ALL}")


class HTMLTestRunner(unittest.TextTestRunner):
    """مشغل اختبار يستخدم HTMLTestResultWithTime ويصدر تقرير HTML"""

    def __init__(self, output_file="test_report.html", **kwargs):
        kwargs["resultclass"] = HTMLTestResultWithTime
        super().__init__(**kwargs)
        self.output_file = output_file

    def run(self, test):
        "تشغيل الاختبار وتوليد تقرير HTML"
        result = super().run(test)
        self._generate_html_report(result)
        return result

    def _generate_html_report(self, result):
        """توليد تقرير HTML من نتائج الاختبار"""
        now = datetime.datetime.now()

        # جمع إحصائيات النتائج
        stats = {
            "total": result.testsRun,
            "passed": len(result.results["passed"]),
            "failed": len(result.results["failed"]),
            "errors": len(result.results["errors"]),
            "skipped": len(result.results["skipped"]),
        }
        stats["success_percent"] = (
            int((stats["passed"] / stats["total"]) * 100) if stats["total"] > 0 else 0
        )

        # بناء تقرير HTML
        html_content = f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>تقرير الاختبارات</title>
  <style>
    body {{
      font-family: Arial, sans-serif;
      margin: 0;
      padding: 20px;
      line-height: 1.6;
      color: #333;
      direction: rtl;
    }}
    h1, h2, h3 {{
      color: #2c3e50;
    }}
    .summary {{
      background-color: #f8f9fa;
      border-radius: 4px;
      padding: 15px;
      margin-bottom: 20px;
    }}
    .stats {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin: 15px 0;
    }}
    .stat {{
      flex: 1;
      min-width: 150px;
      background: white;
      padding: 10px;
      border-radius: 4px;
      box-shadow: 0 2px 4px rgba(0,0,0,0.1);
      text-align: center;
    }}
    .progress {{
      height: 10px;
      background-color: #e9ecef;
      border-radius: 5px;
      margin-top: 5px;
    }}
    .progress-bar {{
      height: 100%;
      border-radius: 5px;
      background-color: #28a745;
    }}
    .section {{
      margin-bottom: 30px;
    }}
    .test-case {{
      background-color: white;
      border-left: 5px solid #ddd;
      padding: 10px 15px;
      margin-bottom: 10px;
      border-radius: 0 4px 4px 0;
    }}
    .test-case.passed {{
      border-color: #28a745;
    }}
    .test-case.failed {{
      border-color: #dc3545;
    }}
    .test-case.error {{
      border-color: #fd7e14;
    }}
    .test-case.skipped {{
      border-color: #6c757d;
    }}
    .test-name {{
      font-weight: bold;
    }}
    .test-id {{
      font-size: 0.9em;
      color: #6c757d;
    }}
    .test-time {{
      font-size: 0.9em;
      color: #6c757d;
    }}
    .test-error {{
      background-color: #f8f9fa;
      padding: 10px;
      margin-top: 10px;
      overflow-x: auto;
      white-space: pre-wrap;
      color: #dc3545;
    }}
    .timestamp {{
      font-size: 0.9em;
      color: #6c757d;
      text-align: left;
    }}
  </style>
</head>
<body>
  <h1>تقرير الاختبارات</h1>
  
  <div class="summary">
    <h2>ملخص</h2>
    <div class="stats">
      <div class="stat">
        <div>إجمالي الاختبارات</div>
        <div><strong>{stats['total']}</strong></div>
      </div>
      <div class="stat" style="color: #28a745;">
        <div>ناجح</div>
        <div><strong>{stats['passed']}</strong></div>
      </div>
      <div class="stat" style="color: #dc3545;">
        <div>فاشل</div>
        <div><strong>{stats['failed']}</strong></div>
      </div>
      <div class="stat" style="color: #fd7e14;">
        <div>أخطاء</div>
        <div><strong>{stats['errors']}</strong></div>
      </div>
      <div class="stat" style="color: #6c757d;">
        <div>تم تخطيه</div>
        <div><strong>{stats['skipped']}</strong></div>
      </div>
    </div>
    
    <div>
      نسبة النجاح: <strong>{stats['success_percent']}%</strong>
      <div class="progress">
        <div class="progress-bar" style="width: {stats['success_percent']}%"></div>
      </div>
    </div>
  </div>
  
"""

        # إضافة قسم الاختبارات الناجحة
        if result.results["passed"]:
            html_content += """
  <div class="section">
    <h2>الاختبارات الناجحة</h2>
"""
            for test in sorted(result.results["passed"], key=lambda x: x["time"]):
                html_content += f"""
    <div class="test-case passed">
      <div class="test-name">{html.escape(test['name'])}</div>
      <div class="test-id">{html.escape(test['id'])}</div>
      <div class="test-time">الوقت: {test['time']:.3f} ثانية</div>
    </div>
"""
            html_content += "  </div>\n"

        # إضافة قسم الاختبارات الفاشلة
        if result.results["failed"]:
            html_content += """
  <div class="section">
    <h2>الاختبارات الفاشلة</h2>
"""
            for test in result.results["failed"]:
                html_content += f"""
    <div class="test-case failed">
      <div class="test-name">{html.escape(test['name'])}</div>
      <div class="test-id">{html.escape(test['id'])}</div>
      <div class="test-time">الوقت: {test['time']:.3f} ثانية</div>
      <div class="test-error">{html.escape(test['error'] or '')}</div>
    </div>
"""
            html_content += "  </div>\n"

        # إضافة قسم أخطاء الاختبارات
        if result.results["errors"]:
            html_content += """
  <div class="section">
    <h2>أخطاء الاختبارات</h2>
"""
            for test in result.results["errors"]:
                html_content += f"""
    <div class="test-case error">
      <div class="test-name">{html.escape(test['name'])}</div>
      <div class="test-id">{html.escape(test['id'])}</div>
      <div class="test-time">الوقت: {test['time']:.3f} ثانية</div>
      <div class="test-error">{html.escape(test['error'] or '')}</div>
    </div>
"""
            html_content += "  </div>\n"

        # إضافة قسم الاختبارات المتخطاة
        if result.results["skipped"]:
            html_content += """
  <div class="section">
    <h2>الاختبارات المتخطاة</h2>
"""
            for test in result.results["skipped"]:
                html_content += f"""
    <div class="test-case skipped">
      <div class="test-name">{html.escape(test['name'])}</div>
      <div class="test-id">{html.escape(test['id'])}</div>
      <div class="test-time">الوقت: {test['time']:.3f} ثانية</div>
    </div>
"""
            html_content += "  </div>\n"

        # إكمال التقرير
        html_content += f"""
  <div class="timestamp">
    تم إنشاء هذا التقرير في: {now.strftime('%Y-%m-%d %H:%M:%S')}
  </div>
</body>
</html>
"""

        # كتابة التقرير إلى ملف
        with open(self.output_file, "w", encoding="utf-8") as f:
            f.write(html_content)

        print(
            f"\n\n{colorama.Fore.GREEN}تم إنشاء تقرير الاختبار في: {self.output_file}{colorama.Style.RESET_ALL}"
        )


class Command(BaseCommand):
    help = "تشغيل الاختبارات وإنشاء تقرير مفصل بالنتائج"

    def add_arguments(self, parser):
        parser.add_argument(
            "test_labels", nargs="*", help="وسوم الاختبارات المطلوب تشغيلها"
        )
        parser.add_argument(
            "--output",
            "-o",
            default="test_report.html",
            help="مسار ملف التقرير المخرج (الافتراضي: test_report.html)",
        )

    def handle(self, *args, **options):
        # طباعة عنوان التقرير
        colorama.init()
        self.stdout.write(
            colorama.Fore.CYAN
            + "\n==== تشغيل الاختبارات وإنشاء تقرير ====\n"
            + colorama.Style.RESET_ALL
        )

        # الحصول على مشغل الاختبارات
        TestRunner = get_runner(settings)

        # إنشاء مشغل اختبارات مخصص
        test_runner = HTMLTestRunner(
            output_file=options["output"],
            verbosity=options["verbosity"],
        )

        # الحصول على مجموعة الاختبارات
        discover_runner = DiscoverRunner(verbosity=options["verbosity"])
        test_suite = discover_runner.build_suite(options["test_labels"])

        # تشغيل الاختبارات
        self.stdout.write(
            colorama.Fore.YELLOW
            + f"جارٍ تشغيل {test_suite.countTestCases()} اختبار..."
            + colorama.Style.RESET_ALL
        )
        result = test_runner.run(test_suite)

        # عرض ملخص النتائج
        self.stdout.write("\n===== ملخص نتائج الاختبارات =====")
        self.stdout.write(f"الإجمالي: {result.testsRun}")
        self.stdout.write(
            colorama.Fore.GREEN
            + f"نجاح: {len(result.results['passed'])}"
            + colorama.Style.RESET_ALL
        )

        if result.failures:
            self.stdout.write(
                colorama.Fore.RED
                + f"فشل: {len(result.failures)}"
                + colorama.Style.RESET_ALL
            )

        if result.errors:
            self.stdout.write(
                colorama.Fore.YELLOW
                + f"أخطاء: {len(result.errors)}"
                + colorama.Style.RESET_ALL
            )

        self.stdout.write(f"تم التخطي: {len(result.results['skipped'])}")
        self.stdout.write("============================\n")

        if result.failures or result.errors:
            return sys.exit(1)
