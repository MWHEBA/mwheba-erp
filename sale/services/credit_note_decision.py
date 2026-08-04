from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Any


@dataclass
class CreditNoteDecision:
    """
    FIN-SAL-005 v2.0: Pure Domain Object carrying Financial Credit Note Decisions
    """
    decision_type: str  # SALES_RETURN, INVOICE_CANCELLATION, PRICE_ADJUSTMENT, MANUAL_ADJUSTMENT
    reason: str
    source_document: str
    return_reference: Optional[str]
    approved_amount: Decimal
    tax_amount: Decimal
    currency: str = "EGP"
    exchange_rate: Decimal = Decimal("1.000000")
    requires_approval: bool = False


@dataclass
class CreditNoteAccountingCommand:
    """
    FIN-SAL-005 v2.0: Pure Domain Command Object for Credit Note Financial Posting via AccountingGateway
    """
    command_id: str
    correlation_id: str
    document_number: str
    revenue_account: str
    vat_account: str
    customer_account: str
    amount: Decimal
    tax_amount: Decimal
    currency: str
    exchange_rate: Decimal
    posting_date: Optional[Any] = None
    user: Optional[Any] = None
