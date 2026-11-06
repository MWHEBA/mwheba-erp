# -*- coding: utf-8 -*-
import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from real_estate.services.legal_escalation_service import LegalEscalationPipeline


class Command(BaseCommand):
    help = "تشغيل رادار التنبيهات المسبقة للأقساط العقارية واحتساب غرامات التأخير والتصعيد القانوني تلقائياً"

    def add_arguments(self, parser):
        parser.add_argument(
            '--as-of-date',
            type=str,
            help='تاريخ الفحص بالصيغة YYYY-MM-DD (افتراضياً: اليوم الحالي)',
        )
        parser.add_argument(
            '--stage',
            type=str,
            help='تصفية مرحلة محددة فقط (مثل: STAGE_1_PRE_DUE)',
        )

    def handle(self, *args, **options):
        date_str = options.get('as_of_date')
        stage = options.get('stage')

        if date_str:
            try:
                as_of_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                self.stderr.write(self.style.ERROR(f"تنسيق تاريخ غير صالح: {date_str}. استخدم YYYY-MM-DD."))
                return
        else:
            as_of_date = timezone.localdate()

        stages_filter = [stage] if stage else None
        self.stdout.write(self.style.NOTICE(f"بدء فحص رادار الأقساط العقارية حتى تاريخ {as_of_date}..."))
        result = LegalEscalationPipeline.run_daily_escalation_sweep(
            as_of_date=as_of_date,
            stages_filter=stages_filter
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"اكتمل الفحص: تم إصدار {result['processed_count']} إشعار، "
                f"تحديث غرامات {result['penalties_updated_count']} قسط، "
                f"وتخطي {result['skipped_duplicate_count']} إشعار مكرر."
            )
        )
