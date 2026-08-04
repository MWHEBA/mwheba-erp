from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Any


@dataclass
class ReturnInspectionDecision:
    """
    FIN-SAL-002 v2.0: Pure Domain Object carrying Sales Return Inspection Decisions
    """
    inspection_result: str  # GOOD, DAMAGED, SCRAP_REJECTED
    approved_quantity: Decimal
    rejected_quantity: Decimal
    restorable_quantity: Decimal
    quarantine_quantity: Decimal
    scrap_quantity: Decimal
    restoration_cost: Decimal
    reason: str = "Return Quality Inspection Completed"
    requires_approval: bool = False


@dataclass
class InventoryMovementCommand:
    """
    FIN-SAL-002 v2.0: Pure Domain Command Object for Physical Inventory Stock Movement
    """
    movement_type: str  # IN_RETURN, QUARANTINE_TRANSFER
    warehouse_from: Optional[Any]
    warehouse_to: Any
    product_id: int
    quantity: Decimal
    unit_cost: Decimal
    reference_type: str
    reference_id: str
    correlation_id: str


@dataclass
class ReturnAccountingCommand:
    """
    FIN-SAL-002 v2.0: Pure Domain Command Object for Sales Return COGS Reversal Accounting
    """
    correlation_id: str
    document_number: str
    inventory_account: str
    cogs_account: str
    amount: Decimal
    currency: str
    exchange_rate: Decimal
    posting_date: Optional[Any] = None
    user: Optional[Any] = None
