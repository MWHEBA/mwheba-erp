import logging
from decimal import Decimal
from django.db.models import Sum, F, ExpressionWrapper, DecimalField
from product.models import Stock, InventoryReservation
from presentation.dto.dashboard_dto import InventoryMetricsDTO

logger = logging.getLogger("financial.services.dashboard.inventory_metrics_service")


class InventoryMetricsService:
    """
    FIN-EEL: Inventory & Reservation Metrics Aggregation Sub-Service
    """

    @classmethod
    def get_inventory_metrics(cls) -> InventoryMetricsDTO:
        stocks = Stock.objects.select_related("product")
        val_total = Decimal("0.00")

        for stk in stocks:
            cost = stk.product.cost_price or Decimal("0.00")
            val_total += (stk.quantity * cost)

        active_res = InventoryReservation.objects.filter(reservation_status="ACTIVE")
        res_count = active_res.count()
        res_qty_total = active_res.aggregate(total=Sum("quantity"))["total"] or Decimal("0.00")

        low_stock_count = Stock.objects.filter(quantity__lt=Decimal("10.0000")).count()

        return InventoryMetricsDTO(
            total_valuation=val_total.quantize(Decimal("0.01")),
            active_reservations_count=res_count,
            reserved_quantity_total=res_qty_total,
            low_stock_items_count=low_stock_count,
            currency="EGP"
        )
