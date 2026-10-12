"""
Django Management Command to inspect Git and GitGuardian issues for MWHEBA ERP.
Usage:
    python manage.py check_git_issues
    python manage.py check_git_issues --all
    python manage.py check_git_issues --json
"""

import sys
from django.core.management.base import BaseCommand
from scripts.check_git_issues import inspect_git_issues, print_formatted_report
import json


class Command(BaseCommand):
    help = "فحص أخطاء ومشاكل وأسرار Git الخاصة بمشروع MWHEBA ERP عبر GitGuardian و Git المحلي"

    def add_arguments(self, parser):
        parser.add_argument(
            "--all",
            action="store_true",
            help="عرض جميع الحوادث بما فيها المتجاهلة والمحلولة",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="إخراج النتيجة بتنسيق JSON",
        )
        parser.add_argument(
            "--no-details",
            action="store_true",
            help="تخطي جلب تفاصيل الملفات لتسريع الفحص",
        )

    def handle(self, *args, **options):
        # Ensure utf-8 output on Windows
        if hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

        show_all = options.get("all", False)
        as_json = options.get("json", False)
        no_details = options.get("no_details", False)

        report = inspect_git_issues(show_all=show_all, fetch_details=not no_details)

        if as_json:
            self.stdout.write(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print_formatted_report(report, show_all=show_all)
