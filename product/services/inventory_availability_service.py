import logging
from decimal import Decimal
from typing import Dict, Any
from django.db import models

from product.models import Product, Warehouse, Stock
from product.models.inventory_reservation import InventoryReservation

logger = logging.getLogger("product.services.inventory_availability_service")


class InventoryAvailabilityService:
    """
    FIN-SAL-003: Inventory Availability Engine Service
    محرك استعلام الموقف المخزني الفلي والحجوزات الحالية والصافي المتاح
    """

    @classmethod
    def get_on_hand_quantity(cls, warehouse_id: int, product_id: int) -> Decimal:
        """
        استعلام الكمية الفيزيائية الفعلية المتاحة في المخزن (On-Hand Physical Stock)
        """
        try:
            stock = Stock.objects.get(warehouse_id=warehouse_id, product_id=product_id)
            return Decimal(str(stock.quantity))
        except Stock.DoesNotExist:
            return Decimal("0.0000")

    @classmethod
    def get_active_reservations_quantity(cls, warehouse_id: int, product_id: int) -> Decimal:
        """
        استعلام إجمالي الكميات المحجوزة غير المستوفاة (Active & Partially Fulfilled Soft Commitments)
        Formula: Sum(quantity - fulfilled_quantity) for ACTIVE & PARTIALLY_FULFILLED
        """
        active_res = InventoryReservation.objects.filter(
            warehouse_id=warehouse_id,
            product_id=product_id,
            reservation_status__in=["ACTIVE", "PARTIALLY_FULFILLED"]
        )
        total = Decimal("0.0000")
        for res in active_res:
            total += res.remaining_reserved_quantity
        return total

    @classmethod
    def get_available_quantity(cls, warehouse_id: int, product_id: int) -> Decimal:
        """
        حساب الكمية الصافية القابلة للبيع والحجز (Net Available Quantity = On-Hand - Active Reservations)
        """
        on_hand = cls.get_on_hand_quantity(warehouse_id, product_id)
        active_reservations = cls.get_active_reservations_quantity(warehouse_id, product_id)
        available = on_hand - active_reservations
        return max(Decimal("0.0000"), available)
