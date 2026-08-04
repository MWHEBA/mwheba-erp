from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, List, Dict, Any


@dataclass
class AuditEvidenceDTO:
    """
    FIN-EEL: Immutable Digital Audit Evidence DTO
    """
    correlation_id: str
    processed_event_id: str
    audit_hash: str
    is_hash_valid: bool
    event_type: str
    journal_reference: Optional[str]
    timestamp: str
    user_name: Optional[str] = None


@dataclass
class LifecycleTimelineStepDTO:
    """
    FIN-EEL: Document Lifecycle Timeline Step DTO
    """
    step_name: str
    status: str  # COMPLETED, CURRENT, PENDING, REJECTED
    timestamp: Optional[str]
    user_name: Optional[str]
    details: Optional[str] = None


@dataclass
class LifecycleTimelineDTO:
    """
    FIN-EEL: Full Document Lifecycle Timeline DTO
    """
    document_type: str
    document_number: str
    current_status: str
    steps: List[LifecycleTimelineStepDTO]
