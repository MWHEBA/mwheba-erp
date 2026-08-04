import logging
from decimal import Decimal
from typing import Tuple

from product.services.inventory_availability_service import InventoryAvailabilityService

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
    def validate_line_atp(
        cls,
        warehouse_id: int,
        product_id: int,
        requested_quantity: Decimal
    ) -> Tuple[bool, Decimal]:
        """
        التحقق الصارم مما إذا كانت الكمية المطلوبة متوفرة بالكامل في رصيد الوفاء ATP
        Returns: (is_available, available_atp_quantity)
        """
        atp_qty = cls.get_atp_quantity(warehouse_id, product_id)
        is_avail = requested_quantity <= atp_qty
        return is_avail, atp_qty
