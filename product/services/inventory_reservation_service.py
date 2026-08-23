import logging
from decimal import Decimal
from typing import List, Dict, Any
from django.db import transaction, models
from django.utils import timezone

from product.models import Product, Warehouse, Stock
from product.models.inventory_reservation import InventoryReservation, InventoryReservationAudit
from product.services.atp_service import ATPService
from sale.models.sales_models import SalesOrder, SalesOrderItem
from financial.exceptions import FinancialCoreError

logger = logging.getLogger("product.services.inventory_reservation_service")


class InventoryReservationService:
    """
    FIN-SAL-003: Inventory Reservation Engine Service (v2.0 Locked Master Final)
    محرك حجز المخزون غير المباشر بأسطر أمر البيع مع تأمين القفل المتزامن select_for_update ودعم التسليم الجزئي
    """

    @classmethod
    def reserve_sales_order_lines(cls, sales_order_id: int, user=None) -> List[InventoryReservation]:
        """
        حجز المخزون غير المباشر لكل سطر في أمر البيع مع القفل المتزامن لصفوف المنتج والمخزن
        """
        with transaction.atomic():
            so = SalesOrder.objects.select_for_update().get(pk=sales_order_id)
            reservations = []

            for line in so.items.all():
                if getattr(line.product, "is_service", False):
                    continue

                # Concurrency Lock on Product and Stock position
                _ = Product.objects.select_for_update().get(pk=line.product_id)
                try:
                    _ = Stock.objects.select_for_update().get(warehouse_id=so.warehouse_id, product_id=line.product_id)
                except Stock.DoesNotExist:
                    pass

                # ATP Validation per line
                is_avail, atp_qty = ATPService.validate_line_atp(
                    warehouse_id=so.warehouse_id,
                    product_id=line.product_id,
                    requested_quantity=line.ordered_qty
                )

                if not is_avail:
                    atp_disp = str(int(atp_qty)) if atp_qty == int(atp_qty) else f"{atp_qty:.4f}".rstrip("0").rstrip(".")
                    req_disp = str(int(line.ordered_qty)) if line.ordered_qty == int(line.ordered_qty) else f"{line.ordered_qty:.4f}".rstrip("0").rstrip(".")
                    shortage = line.ordered_qty - atp_qty
                    shortage_disp = str(int(shortage)) if shortage == int(shortage) else f"{shortage:.4f}".rstrip("0").rstrip(".")
                    raise FinancialCoreError(
                        f"Overselling Error: لا يتوفر رصيد كافٍ بالمخزن ({so.warehouse.name}) للصنف «{line.product.name}». الرصيد المتاح: {atp_disp} | المطلوب: {req_disp} | العجز: {shortage_disp}"
                    )

                res = InventoryReservation.objects.create(
                    sales_order=so,
                    sales_order_line=line,
                    product=line.product,
                    warehouse=so.warehouse,
                    quantity=line.ordered_qty,
                    fulfilled_quantity=Decimal("0.0000"),
                    reservation_status="ACTIVE",
                    created_by=user
                )

                InventoryReservationAudit.objects.create(
                    reservation=res,
                    action="CREATED",
                    previous_quantity=Decimal("0.0000"),
                    new_quantity=line.ordered_qty,
                    reason=f"Soft inventory reservation created for SO #{so.order_number} line #{line.id}",
                    user=user
                )

                reservations.append(res)

            logger.info(f"Reserved {len(reservations)} lines for Sales Order #{so.order_number}.")
            return reservations

    @classmethod
    def consume_reservation_for_delivery_note(
        cls,
        sales_order_id: int,
        delivery_items_data: List[Dict[str, Any]],
        user=None
    ) -> List[InventoryReservation]:
        """
        استهلاك الحجز وتحديث حالة التسليم الجزئي PARTIALLY_FULFILLED أو الاستيفاء الكامل FULFILLED
        """
        with transaction.atomic():
            so = SalesOrder.objects.get(pk=sales_order_id)
            updated_res = []

            for item in delivery_items_data:
                so_item_id = item["so_item_id"]
                deliv_qty = Decimal(str(item["delivered_qty"]))

                try:
                    res = InventoryReservation.objects.select_for_update().get(
                        sales_order_id=sales_order_id,
                        sales_order_line_id=so_item_id,
                        reservation_status__in=["ACTIVE", "PARTIALLY_FULFILLED"]
                    )
                except InventoryReservation.DoesNotExist:
                    continue

                prev_qty = res.fulfilled_quantity
                new_fulfilled = prev_qty + deliv_qty

                if new_fulfilled >= res.quantity:
                    res.reservation_status = "FULFILLED"
                    action_type = "FULFILLED"
                else:
                    res.reservation_status = "PARTIALLY_FULFILLED"
                    action_type = "PARTIALLY_FULFILLED"

                res.fulfilled_quantity = new_fulfilled
                res.save()

                InventoryReservationAudit.objects.create(
                    reservation=res,
                    action=action_type,
                    previous_quantity=prev_qty,
                    new_quantity=new_fulfilled,
                    reason=f"Consumed {deliv_qty} for delivery note on SO #{so.order_number}",
                    user=user
                )

                updated_res.append(res)

            logger.info(f"Consumed reservations for {len(updated_res)} lines on Sales Order #{so.order_number}.")
            return updated_res

    @classmethod
    def release_reservation_for_sales_order(
        cls,
        sales_order_id: int,
        reason: str = "SO Cancelled",
        user=None
    ) -> List[InventoryReservation]:
        """
        إلغاء وإفراج عن حجوزات المخزون لأمر البيع
        """
        with transaction.atomic():
            reservations = InventoryReservation.objects.filter(
                sales_order_id=sales_order_id,
                reservation_status__in=["ACTIVE", "PARTIALLY_FULFILLED"]
            )
            released = []

            for res in reservations:
                prev_stat = res.reservation_status
                res.reservation_status = "CANCELLED"
                res.released_at = timezone.now()
                res.save()

                InventoryReservationAudit.objects.create(
                    reservation=res,
                    action="CANCELLED",
                    previous_quantity=res.quantity,
                    new_quantity=Decimal("0.0000"),
                    reason=f"Reservation released ({prev_stat} -> CANCELLED): {reason}",
                    user=user
                )

                released.append(res)

            logger.info(f"Released {len(released)} reservations for Sales Order ID {sales_order_id} (Reason: {reason}).")
            return released

    @classmethod
    def sweep_expired_reservations(cls, user=None) -> List[InventoryReservation]:
        """
        FIN-SAL-008: تنظيف وإفراج تلقائي عن الحجوزات المنتهية (Sweep Expired Stock Reservations)
        """
        now = timezone.now()
        with transaction.atomic():
            expired_res = InventoryReservation.objects.filter(
                reservation_status__in=["EXPIRED", "CANCELLED"]
            )
            swept = []
            for res in expired_res:
                res.reservation_status = "EXPIRED"
                res.released_at = now
                res.save()

                InventoryReservationAudit.objects.create(
                    reservation=res,
                    action="EXPIRED",
                    previous_quantity=res.quantity,
                    new_quantity=Decimal("0.0000"),
                    reason="Automatic Sweep: Reservation TTL Expired",
                    user=user
                )
                swept.append(res)

            if swept:
                logger.info(f"Auto-swept {len(swept)} expired stock reservations.")
            return swept
