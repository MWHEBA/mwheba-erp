from enum import Enum
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


class CreditDecisionType(str, Enum):
    """
    FIN-AR-001: Strict Credit Decision Type Enum
    """
    APPROVED = "APPROVED"
    BLOCKED = "BLOCKED"
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"


@dataclass
class CreditDecision:
    """
    FIN-AR-001: Pure Python Dataclass Domain Object for Credit Check Results
    """
    decision: CreditDecisionType
    reason: str
    current_exposure: Decimal
    available_credit: Decimal
    credit_limit: Decimal
    requested_amount: Decimal
    requires_approval: bool = False
    approval_type: Optional[str] = None

    @property
    def is_allowed(self) -> bool:
        return self.decision == CreditDecisionType.APPROVED

    @property
    def is_blocked(self) -> bool:
        return self.decision == CreditDecisionType.BLOCKED
