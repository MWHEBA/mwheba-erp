import logging
from decimal import Decimal
from typing import Tuple

from product.services.inventory_availability_service import InventoryAvailabilityService
from product.services.atp_decision import ATPDecision

logger = logging.getLogger("product.services.atp_service")


class ATPService:
    """
    FIN-SAL-003: Available-To-Promise (ATP) Engine Service
    محرك فحص الكميات المتاحة للوفاء بالوعود التجارية والبيع
    """

    @classmethod
    def get_atp_quantity(cls, warehouse_id: int, product_id: int) -> Decimal:
        """
        احتساب رصيد الوفاء التجاري المتاح (ATP Quantity)
        """
        return InventoryAvailabilityService.get_available_quantity(warehouse_id, product_id)

    @classmethod
    def evaluate_atp_decision(
        cls,
        warehouse_id: int,
        product_id: int,
        requested_quantity: Decimal
    ) -> ATPDecision:
        """
        تقييم قرار الوفاء التجاري ATP وتوليد كائن Domain Object محوكم
        """
        atp_qty = cls.get_atp_quantity(warehouse_id, product_id)
        is_avail = requested_quantity <= atp_qty
        shortage = Decimal("0.0000") if is_avail else (requested_quantity - atp_qty)
        reason = "Quantity fully available for promise." if is_avail else f"Shortage of {shortage} units."

        return ATPDecision(
            available_quantity=atp_qty,
            requested_quantity=requested_quantity,
            is_available=is_avail,
            shortage_quantity=shortage,
            reason=reason,
            warehouse_id=warehouse_id,
            product_id=product_id
        )

    @classmethod
    def validate_line_atp(
        cls,
        warehouse_id: int,
        product_id: int,
        requested_quantity: Decimal
    ) -> Tuple[bool, Decimal]:
        """
        Legacy tuple adapter wrapping evaluate_atp_decision for backward compatibility
        """
        decision = cls.evaluate_atp_decision(warehouse_id, product_id, requested_quantity)
        return decision.is_available, decision.available_quantity
