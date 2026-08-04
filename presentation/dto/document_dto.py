from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass
class DocumentFinancialBreakdownDTO:
    """
    FIN-EEL: Standard Financial Breakdown DTO for Invoices, Credit Notes, and Returns
    """
    subtotal: Decimal
    discount_amount: Decimal
    taxable_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    currency: str
    exchange_rate: Decimal
    functional_total_egp: Decimal
    payment_terms: Optional[str] = None
    due_date: Optional[str] = None
