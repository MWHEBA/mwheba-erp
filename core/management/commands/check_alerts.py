"""
أمر Django لفحص جميع التنبيهات
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from core.services.notification_service import NotificationService
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "فحص جميع التنبيهات (المخزون المنخفض والفواتير المستحقة)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--type",
            choices=["stock", "invoices", "all"],
            default="all",
            help="نوع التنبيهات المراد فحصها",
        )
        parser.add_argument("--verbose", action="store_true", help="عرض تفاصيل أكثر")

    def handle(self, *args, **options):
        alert_type = options["type"]
        verbose = options["verbose"]

        self.stdout.write(
            self.style.SUCCESS(f"بدء فحص التنبيهات - النوع: {alert_type}")
        )

        notifications_created = []

        try:
            if alert_type in ["stock", "all"]:
                if verbose:
                    self.stdout.write("فحص تنبيهات المخزون المنخفض...")

                stock_alerts = NotificationService.check_low_stock_alerts()
                notifications_created.extend(stock_alerts)

                self.stdout.write(
                    self.style.SUCCESS(
                        f"تم إنشاء {len(stock_alerts)} تنبيه مخزون منخفض"
                    )
                )

            if alert_type in ["invoices", "all"]:
                if verbose:
                    self.stdout.write("فحص تنبيهات الفواتير المستحقة...")

                invoice_alerts = NotificationService.check_due_invoices_alerts()
                notifications_created.extend(invoice_alerts)

                self.stdout.write(
                    self.style.SUCCESS(
                        f"تم إنشاء {len(invoice_alerts)} تنبيه فواتير مستحقة"
                    )
                )

            # عرض الملخص النهائي
            total_alerts = len(notifications_created)

            if total_alerts > 0:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"\n✅ تم الانتهاء من فحص التنبيهات"
                        f"\n📊 إجمالي التنبيهات الجديدة: {total_alerts}"
                        f'\n⏰ وقت الفحص: {timezone.now().strftime("%Y-%m-%d %H:%M:%S")}'
                    )
                )

                if verbose:
                    self.stdout.write("\nتفاصيل التنبيهات المُنشأة:")
                    for notification in notifications_created:
                        self.stdout.write(
                            f"- {notification.type}: {notification.title} "
                            f"(المستخدم: {notification.user.username})"
                        )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"✅ لا توجد تنبيهات جديدة"
                        f'\n⏰ وقت الفحص: {timezone.now().strftime("%Y-%m-%d %H:%M:%S")}'
                    )
                )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ خطأ في فحص التنبيهات: {e}"))
            logger.error(f"خطأ في أمر فحص التنبيهات: {e}")
            return

        self.stdout.write(self.style.SUCCESS("🎉 تم الانتهاء من فحص التنبيهات بنجاح"))
