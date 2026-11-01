# -*- coding: utf-8 -*-
"""
UnitBookingSweepService - خدمة كنس الحجوزات المنتهية وتحرير الوحدات المحتكرة
تطبق بروتوكول القفل المزدوج الذري لمنع تحرير وحدات تم التعاقد عليها بالتزامن.
"""
import logging
from datetime import date
from django.db import transaction
from django.utils import timezone
from real_estate.models.unit import PropertyUnit
from real_estate.models.booking import UnitBooking

logger = logging.getLogger(__name__)


class UnitBookingSweepService:
    """
    خدمة كنس الحجوزات منتهية الصلاحية
    """

    @classmethod
    def sweep_expired_bookings(cls, as_of_date: date = None) -> int:
        """
        فحص وتحرير كافة الحجوزات المنتهية مع الحراسة التزامنية الصارمة:
        - يمر على الحجوزات النشطة التي تجاوزت تاريخ الانتهاء.
        - يقفل الحجز والوحدة ذرياً داخل transaction.atomic.
        - لا يحرر الوحدة إلا إذا كانت لا تزال RESERVED ومربوطة بذات الحجز، منعاً لتحرير وحدات تم التعاقد عليها بالتزامن.
        """
        target_date = as_of_date or timezone.localdate()
        expired_booking_ids = list(
            UnitBooking.objects.filter(
                status=UnitBooking.BookingStatus.ACTIVE,
                expiry_date__lt=target_date
            ).values_list('id', flat=True)
        )

        released_count = 0
        skipped_count = 0

        for b_id in expired_booking_ids:
            with transaction.atomic():
                try:
                    locked_booking = UnitBooking.objects.select_for_update().get(pk=b_id)
                except UnitBooking.DoesNotExist:
                    continue

                locked_unit = PropertyUnit.objects.select_for_update().get(pk=locked_booking.unit_id)

                # Strict Guard: Only release if booking is STILL ACTIVE and EXPIRED,
                # AND unit is STILL RESERVED for THIS specific booking
                if (
                    locked_booking.status == UnitBooking.BookingStatus.ACTIVE
                    and locked_booking.expiry_date < target_date
                    and locked_unit.status == PropertyUnit.UnitStatus.RESERVED
                    and locked_unit.current_booking_id == locked_booking.id
                ):
                    locked_booking.status = UnitBooking.BookingStatus.EXPIRED_RELEASED
                    locked_booking.save(update_fields=['status', 'updated_at'])

                    locked_unit.status = PropertyUnit.UnitStatus.AVAILABLE
                    locked_unit.current_booking = None
                    locked_unit.status_version += 1
                    locked_unit.save(update_fields=['status', 'current_booking', 'status_version'])

                    released_count += 1
                    logger.info(
                        f"🧹 [Sweeper] تم إنهاء الحجز {locked_booking.booking_number} "
                        f"وتحرير الوحدة {locked_unit.unit_code} للبيع مجدداً."
                    )
                else:
                    skipped_count += 1
                    logger.warning(
                        f"🛡️ [Sweeper] تم تفادي تحرير الوحدة {locked_unit.unit_code} "
                        f"بسبب تغيير متزامن: booking_status={locked_booking.status}, unit_status={locked_unit.status}"
                    )

        logger.info(f"Sweep complete: {released_count} bookings expired/released, {skipped_count} skipped.")
        return released_count
