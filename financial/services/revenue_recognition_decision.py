from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Any
import uuid


@dataclass
class RevenueRecognitionDecision:
    """
    FIN-AR-002: Pure Domain Object representing Revenue Recognition Evaluation Decisions
    """
    accounting_position: str  # RECOGNIZE_REVENUE, CREATE_CONTRACT_LIABILITY, CREATE_CONTRACT_ASSET
    allocated_transaction_price: Decimal
    recognized_amount: Decimal
    deferred_amount: Decimal
    contract_asset_amount: Decimal
    policy_id: int
    policy_version: int
    fx_treatment_type: str = "INVOICE_RATE"


@dataclass
class RevenueAccountingCommand:
    """
    FIN-AR-002: Domain Command Object for General Ledger Revenue Entry Posting
    """
    event_id: str
    correlation_id: str
    invoice_item_id: int
    schedule_id: int
    schedule_line_id: Optional[int]
    accounting_position: str
    foreign_amount: Decimal
    exchange_rate: Decimal
    functional_amount: Decimal
    currency: str
    revenue_account_code: str
    deferred_account_code: str
    asset_account_code: Optional[str] = None
    journal_reference: Optional[str] = None
    user: Optional[Any] = None
