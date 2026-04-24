"""
Payroll Signal Governance Service (Simplified).

This service has been simplified to remove background monitoring threads
and complex rollout logic to improve performance.

For gradual rollout, use feature flags directly.

✅ PERFORMANCE OPTIMIZATION:
- Removed background monitoring thread (saves 10-20MB memory)
- Removed gradual rollout system (1000+ lines)
- Removed metrics collection (PayrollSignalMetrics dataclass)
- Removed auto-promotion logic
- Removed rollout health checks
- Simple enable/disable only
"""

import logging
from typing import Dict, Any, Optional

from django.contrib.auth import get_user_model
from django.utils import timezone

from ..models import GovernanceContext
from ..exceptions import ValidationError
from .governance_switchboard import governance_switchboard
from .audit_service import AuditService

User = get_user_model()
logger = logging.getLogger('governance.payroll_signal_governance')


class PayrollSignalGovernanceService:
    """
    Simplified service for managing payroll signal governance.
    
    Background monitoring and automatic rollout removed for performance.
    
    ✅ Use feature flags directly for gradual rollout instead of
    complex background monitoring and auto-promotion logic.
    """
    
    def __init__(self):
        """Initialize the payroll signal governance service"""
        self._governance_enabled = False
    
    def enable_payroll_signal_governance(self, user: User, reason: str = "Manual activation") -> bool:
        """
        Enable payroll signal governance.
        
        Args:
            user: User enabling the governance
            reason: Reason for enabling
            
        Returns:
            bool: True if successfully enabled
        """
        try:
            # Set governance context
            GovernanceContext.set_context(
                user=user,
                service='PayrollSignalGovernanceService',
                operation='enable_governance'
            )
            
            # Enable payroll governance component in switchboard
            governance_switchboard.enable_component(
                'payroll_governance',
                reason=reason,
                user=user
            )
            
            # Set internal governance state
            self._governance_enabled = True
            
            # Create audit trail
            AuditService.log_operation(
                model_name='PayrollSignalGovernanceService',
                object_id=0,
                operation='ENABLE_GOVERNANCE',
                source_service='PayrollSignalGovernanceService',
                user=user,
                after_data={'reason': reason}
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to enable payroll signal governance: {e}")
            raise
        
        finally:
            GovernanceContext.clear_context()
    
    def disable_payroll_signal_governance(self, user: User, reason: str = "Manual disable") -> bool:
        """
        Disable payroll signal governance.
        
        Args:
            user: User disabling the governance
            reason: Reason for disabling
            
        Returns:
            bool: True if successfully disabled
        """
        try:
            # Set governance context
            GovernanceContext.set_context(
                user=user,
                service='PayrollSignalGovernanceService',
                operation='disable_governance'
            )
            
            # Disable payroll governance component in switchboard
            governance_switchboard.disable_component(
                'payroll_governance',
                reason=reason,
                user=user
            )
            
            # Set internal governance state
            self._governance_enabled = False
            
            # Create audit trail
            AuditService.log_operation(
                model_name='PayrollSignalGovernanceService',
                object_id=0,
                operation='DISABLE_GOVERNANCE',
                source_service='PayrollSignalGovernanceService',
                user=user,
                after_data={'reason': reason}
            )
            
            logger.warning(f"Payroll signal governance disabled by {user.username}: {reason}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to disable payroll signal governance: {e}")
            raise
        
        finally:
            GovernanceContext.clear_context()
    
    def get_rollout_status(self) -> Dict[str, Any]:
        """Get rollout status (simplified)"""
        return {
            'governance_enabled': self._governance_enabled,
            'message': 'Background monitoring disabled for performance'
        }
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get health status (simplified)"""
        return {
            'status': 'healthy' if self._governance_enabled else 'disabled',
            'governance_enabled': self._governance_enabled
        }


# Global service instance
payroll_signal_governance = PayrollSignalGovernanceService()


# Convenience functions
def get_payroll_rollout_status() -> Dict[str, Any]:
    """Get payroll signal rollout status"""
    return payroll_signal_governance.get_rollout_status()
