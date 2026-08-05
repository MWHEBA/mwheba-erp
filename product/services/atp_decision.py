from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

@dataclass
class ATPDecision:
    """
    FIN-SAL-003: Pure Domain Object for ATP (Available-To-Promise) Validation Outcomes
    """
    available_quantity: Decimal
    requested_quantity: Decimal
    is_available: bool
    shortage_quantity: Decimal
    reason: str
    warehouse_id: int
    product_id: int
