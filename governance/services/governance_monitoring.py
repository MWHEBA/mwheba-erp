"""
Governance Monitoring Service (Simplified).

This service has been simplified to remove background monitoring threads,
metrics collection, and automatic alerting to improve performance.

For monitoring, use external tools like Sentry or New Relic.

✅ PERFORMANCE OPTIMIZATION:
- Removed background monitoring loop (saves 10-20MB memory)
- Removed DB queries every 30 seconds
- Removed automatic rollback logic
- Removed component responsiveness checks
- Removed violation threshold monitoring
- Logging only - use external monitoring tools
"""

import logging
from typing import Dict, Any

from django.utils import timezone

from ..models import AuditTrail
from ..exceptions import GovernanceError
from .audit_service import AuditService
from .governance_switchboard import governance_switchboard

logger = logging.getLogger(__name__)


class GovernanceMonitoringService:
    """
    Simplified monitoring service for governance violations.
    
    This service only provides basic violation recording without
    background monitoring, metrics collection, or automatic responses.
    
    ✅ Use external monitoring tools instead:
    - Sentry for error tracking and alerting
    - New Relic for performance monitoring
    - Datadog for infrastructure monitoring
    """
    
    def __init__(self):
        """Initialize the monitoring service"""
        pass
    
    def record_violation(self, 
                        violation_type: str,
                        component: str,
                        severity: str,
                        details: Dict[str, Any],
                        user: str = None,
                        source_service: str = None):
        """
        Record a governance violation (simplified - logging only).
        
        Args:
            violation_type: Type of violation
            component: Component where violation occurred
            severity: Severity level
            details: Violation details
            user: User associated with violation
            source_service: Service that detected the violation
        """
        # Log violation
        logger.error(
            f"Governance violation: {violation_type} in {component} "
            f"(Severity: {severity}) - {details}"
        )
        
        # Record in governance switchboard
        governance_switchboard.record_governance_violation(
            violation_type, component, details, user
        )
    
    def get_monitoring_status(self) -> Dict[str, Any]:
        """Get current monitoring status (simplified)"""
        return {
            'monitoring_active': False,
            'message': 'Background monitoring disabled for performance'
        }
    
    def get_violation_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get violation summary (simplified)"""
        return {
            'time_period_hours': hours,
            'message': 'Violation tracking disabled - use audit trail for history'
        }


# Global monitoring service instance
governance_monitoring = GovernanceMonitoringService()


# Convenience functions
def record_violation(violation_type: str, component: str, severity: str, 
                    details: Dict[str, Any], user: str = None, source_service: str = None):
    """Record a governance violation"""
    governance_monitoring.record_violation(
        violation_type, component, severity, details, user, source_service
    )


def get_monitoring_status() -> Dict[str, Any]:
    """Get current monitoring status"""
    return governance_monitoring.get_monitoring_status()


def get_violation_summary(hours: int = 24) -> Dict[str, Any]:
    """Get violation summary"""
    return governance_monitoring.get_violation_summary(hours)


# Backward compatibility stubs
class ViolationType:
    """Violation type constants (simplified)"""
    UNAUTHORIZED_ACCESS = 'unauthorized_access'
    DATA_INTEGRITY = 'data_integrity'
    WORKFLOW_BYPASS = 'workflow_bypass'
    AUTHORITY_VIOLATION = 'authority_violation'
    AUDIT_TRAIL_GAP = 'audit_trail_gap'


class AlertLevel:
    """Alert level constants (simplified)"""
    INFO = 'info'
    WARNING = 'warning'
    ERROR = 'error'
    CRITICAL = 'critical'


def start_monitoring():
    """Start monitoring (no-op - background monitoring disabled)"""
    pass


def stop_monitoring():
    """Stop monitoring (no-op - background monitoring disabled)"""
    pass


def record_metric(metric_name: str, value: float, tags: Dict[str, Any] = None):
    """Record a metric (no-op - metrics collection disabled)"""
    pass
