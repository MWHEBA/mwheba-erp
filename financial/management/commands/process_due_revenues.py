"""
Command: process_due_revenues
الأمر الإداري المعماري لتوليد وترحيل قيود الاستحقاق الدورية للإيرادات المؤجلة (IFRS 15)
يعمل يومياً أو شهرياً عبر Cron / Celery Beat
"""

import sys
from datetime import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from financial.services.revenue_recognition_service import RevenueRecognitionService


class Command(BaseCommand):
    help = "معالجة وترحيل أقساط الإيرادات المؤجلة المستحقة آلياً وفق معيار IFRS 15"

    def add_arguments(self, parser):
        parser.add_argument(
            "--as-of-date",
            type=str,
            help="تاريخ الاستحقاق المستهدف (YYYY-MM-DD) - الافتراضي اليوم",
        )

    def handle(self, *args, **options):
        date_str = options.get("as_of_date")
        target_date = None
        if date_str:
            try:
                target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                self.stderr.write(self.style.ERROR(f"تنسيق التاريخ غير صحيح: {date_str}. استخدم YYYY-MM-DD"))
                sys.exit(1)

        target_date = target_date or timezone.now().date()
        self.stdout.write(self.style.NOTICE(f"بدء تشغيل معالجة الإيرادات المؤجلة المستحقة حتى تاريخ: {target_date}..."))

        result = RevenueRecognitionService.process_all_due_schedules(as_of_date=target_date)

        self.stdout.write(self.style.SUCCESS(
            f"✅ اكتملت المعالجة بنجاح:\n"
            f"   - الأقساط المعالجة: {result['processed_count']}\n"
            f"   - إجمالي المبلغ المعترف به: {result['total_recognized_amount']} EGP\n"
            f"   - العمليات الفاشلة: {result['failed_count']}"
        ))

        if result.get("errors"):
            self.stdout.write(self.style.WARNING("⚠️ قائمة الأخطاء:"))
            for err in result["errors"]:
                self.stdout.write(self.style.ERROR(f"   * {err}"))
