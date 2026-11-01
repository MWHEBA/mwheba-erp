# -*- coding: utf-8 -*-
import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from real_estate.services.booking_sweep_service import UnitBookingSweepService


class Command(BaseCommand):
    help = "كنس حجوزات الوحدات العقارية المنتهية وتحرير الوحدات المحجوزة تلقائياً"

    def add_arguments(self, parser):
        parser.add_argument(
            '--as-of-date',
            type=str,
            help='تاريخ المقارنة بالصيغة YYYY-MM-DD (افتراضياً: اليوم الحالي)',
        )

    def handle(self, *args, **options):
        date_str = options.get('as_of_date')
        if date_str:
            try:
                as_of_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                self.stderr.write(self.style.ERROR(f"تنسيق تاريخ غير صالح: {date_str}. استخدم YYYY-MM-DD."))
                return
        else:
            as_of_date = timezone.localdate()

        self.stdout.write(self.style.NOTICE(f"بدء فحص الحجوزات المنتهية حتى تاريخ {as_of_date}..."))
        released_count = UnitBookingSweepService.sweep_expired_bookings(as_of_date=as_of_date)
        self.stdout.write(self.style.SUCCESS(f"اكتمل الفحص: تم تحرير {released_count} وحدة بنجاح."))
