"""
Django Command: sync_daily_exchange_rates
أمر الجدولة التلقائية لمزامنة وتحديث أسعار الصرف الحية للعملات النشطة مع البنك المركزي
يُشغل يومياً عبر Cron / Task Scheduler كل صباح.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from financial.services.exchange_rate_sync_service import ExchangeRateSyncService


class Command(BaseCommand):
    help = "مزامنة وتحديث أسعار صرف العملات الأجنبية النشطة مع البنك المركزي والسوق المالي تلقائياً"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="إجبار المزامنة حتى لو كانت الأسعار محدثة لليوم الحالي",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE(f"[START] Syncing daily exchange rates... [{timezone.now().strftime('%Y-%m-%d %H:%M:%S')}]"))
        
        try:
            result = ExchangeRateSyncService.sync_official_cbe_rates()
            if result.get("status") == "SUCCESS":
                synced_list = result.get("synced_rates", [])
                self.stdout.write(
                    self.style.SUCCESS(
                        f"[SUCCESS] {result.get('message')} (Base: {result.get('base_currency')})"
                    )
                )
                for item in synced_list:
                    self.stdout.write(f"  - {item['code']}: {item['rate']}")
            else:
                self.stdout.write(
                    self.style.WARNING(f"[WARNING] {result.get('message')}")
                )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"[ERROR] Sync failed: {str(e)}")
            )
