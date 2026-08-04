from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional, List, Dict, Any
from enum import Enum


class TaxRoundingPolicy(str, Enum):
    """
    FIN-TAX-001 v3.0: Tax Rounding Policy Options
    """
    ROUND_LINE = "ROUND_LINE"
    ROUND_DOCUMENT = "ROUND_DOCUMENT"
    ROUND_UP = "ROUND_UP"
    ROUND_DOWN = "ROUND_DOWN"
    HALF_UP = "HALF_UP"


@dataclass
class TaxDecision:
    """
    FIN-TAX-001 v3.0: Pure Domain Object carrying Tax Determination Decisions (Business Logic)
    """
    decision_type: str  # TAX_APPLIED, TAX_EXEMPT, ZERO_RATED, TAX_NOT_APPLICABLE, TAX_REQUIRES_REVIEW
    applicable: bool
    selected_rule_code: Optional[str]
    rule_version: int
    tax_code: str
    tax_rate: Decimal
    taxable_amount: Decimal
    tax_amount: Decimal
    withholding_tax_amount: Decimal = Decimal("0.00")
    jurisdiction_code: str = "EGYPT-TAX"
    decision_reason: str = "Tax Rule Applied Successfully"
    effective_date: Optional[str] = None
    requires_manual_review: bool = False
    exemption_certificate_id: Optional[int] = None
    accounting_position: str = "OUTPUT"
    line_decisions: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class TaxCalculationResult:
    """
    FIN-TAX-001 v3.0: Pure Domain Value Object representing final Tax Calculation Output
    """
    document_id: int
    subtotal: Decimal
    taxable_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    currency: str
    exchange_rate: Decimal
    functional_tax_amount: Decimal
    tax_decisions: List[TaxDecision] = field(default_factory=list)
    line_decisions: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class TaxAccountingCommand:
    """
    FIN-TAX-001 v3.0: Pure Domain Command Object for Tax General Ledger Posting
    """
    command_id: str
    correlation_id: str
    document_type: str
    document_number: str
    tax_code: str
    debit_account_code: str
    credit_account_code: str
    taxable_amount: Decimal
    tax_amount: Decimal
    currency_code: str
    exchange_rate: Decimal
    functional_amount: Decimal
    posting_date: Optional[Any] = None
    user: Optional[Any] = None
