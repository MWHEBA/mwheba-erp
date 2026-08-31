from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Any


@dataclass
class AllocationResult:
    """
    FIN-AR-004: Pure Domain Value Object for Allocation Outcomes
    كائن قيمة مجرد لنقل نتائج وتفاصيل عمليات التسوية والتوزيع
    """
    customer_id: int
    payment_transaction_id: int
    invoice_transaction_id: int
    allocated_amount: Decimal
    allocation_type: str = "PAYMENT_TO_INVOICE"
    allocation_currency: str = "EGP"
    exchange_rate: Decimal = Decimal("1.000000")
    functional_amount: Optional[Decimal] = None
    realized_fx_difference: Decimal = Decimal("0.00")
    source_document_type: str = "PAYMENT"
    source_document_number: str = ""
    target_document_type: str = "INVOICE"
    target_document_number: str = ""
    allocation_reference: Optional[str] = None
    payment_remaining: Decimal = Decimal("0.00")
    invoice_remaining: Decimal = Decimal("0.00")
    payment_status: str = "CLOSED"
    invoice_status: str = "CLOSED"
