import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from product.services.inventory_reservation_service import InventoryReservationService

logger = logging.getLogger("sale.management.commands.release_expired_reservations")


class Command(BaseCommand):
    help = "إفراج تلقائي عن حجوزات المخزون المنتهية الصلاحية (Release Expired Stock Reservations)"

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE(f"[{timezone.now()}] بدء فحص الحجوزات المنتهية..."))
        try:
            released = InventoryReservationService.sweep_expired_reservations()
            self.stdout.write(
                self.style.SUCCESS(f"تم بنجاح الإفراج عن {len(released)} حجز منتهي الصلاحية وإعادتها للـ ATP.")
            )
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"خطأ أثناء فك الحجوزات المنتهية: {e}"))
