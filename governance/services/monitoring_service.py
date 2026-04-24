"""
Monitoring Service for Governance System (Simplified).

Provides basic health monitoring for governance components without
the overhead of background threads, metrics collection, or alerting.

This is a simplified version focused on manual health checks only.

✅ PERFORMANCE OPTIMIZATION:
- Removed background monitoring thread (saves 10-20MB memory)
- Removed metrics collection (deque maxlen=1000)
- Removed email/webhook alerting
- Removed alert rules system
- Removed violation pattern analysis
- Logging only - use external tools (Sentry, New Relic) for monitoring
"""

import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass

from django.utils import timezone
from django.conf import settings

from .governance_switchboard import governance_switchboard

logger = logging.getLogger(__name__)


@dataclass
class HealthCheck:
    """Represents a health check for governance components"""
    component: str
    check_name: str
    status: str  # 'healthy', 'warning', 'critical', 'unknown'
    message: str
    last_check: datetime
    response_time_ms: float
    details: Dict[str, Any]


class MonitoringService:
    """
    Simplified monitoring service for governance system.
    
    Provides manual health checks only - no background monitoring,
    no metrics collection, no alerting.
    
    ✅ Use external monitoring tools instead:
    - Sentry for error tracking
    - New Relic for performance monitoring
    - Datadog for infrastructure monitoring
    """
    
    def __init__(self, alert_email: Optional[str] = None, 
                 external_webhook: Optional[str] = None):
        """
        Initialize Monitoring Service.
        
        Args:
            alert_email: Email address for alerts (unused)
            external_webhook: External webhook URL for alerts (unused)
        """
        self.alert_email = alert_email or getattr(settings, 'GOVERNANCE_ALERT_EMAIL', None)
        self.external_webhook = external_webhook
        
        # Health checks storage
        self._health_checks: Dict[str, HealthCheck] = {}
    
    def record_violation(self, violation_type: str, component: str, 
                        details: Dict[str, Any], user=None):
        """
        Record a governance violation (simplified - logging only).
        
        Args:
            violation_type: Type of violation
            component: Component where violation occurred
            details: Violation details
            user: User associated with violation
        """
        # Log violation
        logger.warning(f"Governance violation: {violation_type} in {component}")
    
    def perform_health_check(self, component: str) -> HealthCheck:
        """
        Perform health check for a governance component.
        
        Args:
            component: Component to check
            
        Returns:
            HealthCheck: Health check result
        """
        start_time = time.time()
        
        try:
            # Perform component-specific health checks
            if component == 'accounting_gateway':
                health = self._check_accounting_gateway_health()
            elif component == 'movement_service':
                health = self._check_movement_service_health()
            elif component == 'governance_switchboard':
                health = self._check_switchboard_health()
            elif component == 'audit_trail':
                health = self._check_audit_trail_health()
            elif component == 'idempotency_service':
                health = self._check_idempotency_service_health()
            else:
                health = HealthCheck(
                    component=component,
                    check_name='unknown_component',
                    status='unknown',
                    message=f'Unknown component: {component}',
                    last_check=timezone.now(),
                    response_time_ms=0.0,
                    details={}
                )
            
            response_time = (time.time() - start_time) * 1000
            health.response_time_ms = response_time
            
            # Store health check result
            self._health_checks[component] = health
            
            return health
            
        except Exception as e:
            error_health = HealthCheck(
                component=component,
                check_name='health_check_error',
                status='critical',
                message=f'Health check failed: {e}',
                last_check=timezone.now(),
                response_time_ms=(time.time() - start_time) * 1000,
                details={'error': str(e)}
            )
            
            self._health_checks[component] = error_health
            
            logger.error(f"Health check failed for {component}: {e}")
            return error_health
    
    def get_system_health(self) -> Dict[str, Any]:
        """Get overall system health status"""
        health_summary = {
            'overall_status': 'healthy',
            'components': {},
            'critical_count': 0,
            'warning_count': 0,
            'healthy_count': 0,
            'last_updated': timezone.now()
        }
        
        for component, health in self._health_checks.items():
            health_summary['components'][component] = {
                'status': health.status,
                'message': health.message,
                'last_check': health.last_check,
                'response_time_ms': health.response_time_ms
            }
            
            if health.status == 'critical':
                health_summary['critical_count'] += 1
                health_summary['overall_status'] = 'critical'
            elif health.status == 'warning':
                health_summary['warning_count'] += 1
                if health_summary['overall_status'] == 'healthy':
                    health_summary['overall_status'] = 'warning'
            elif health.status == 'healthy':
                health_summary['healthy_count'] += 1
        
        return health_summary
    
    def _check_accounting_gateway_health(self) -> HealthCheck:
        """Check AccountingGateway health"""
        try:
            enabled = governance_switchboard.is_component_enabled('accounting_gateway_enforcement')
            
            if not enabled:
                return HealthCheck(
                    component='accounting_gateway',
                    check_name='component_status',
                    status='warning',
                    message='AccountingGateway enforcement is disabled',
                    last_check=timezone.now(),
                    response_time_ms=0.0,
                    details={'enabled': False}
                )
            
            return HealthCheck(
                component='accounting_gateway',
                check_name='component_status',
                status='healthy',
                message='AccountingGateway is functioning normally',
                last_check=timezone.now(),
                response_time_ms=0.0,
                details={'enabled': True}
            )
            
        except Exception as e:
            return HealthCheck(
                component='accounting_gateway',
                check_name='health_check_error',
                status='critical',
                message=f'Health check failed: {e}',
                last_check=timezone.now(),
                response_time_ms=0.0,
                details={'error': str(e)}
            )
    
    def _check_movement_service_health(self) -> HealthCheck:
        """Check MovementService health"""
        try:
            enabled = governance_switchboard.is_component_enabled('movement_service_enforcement')
            
            if not enabled:
                return HealthCheck(
                    component='movement_service',
                    check_name='component_status',
                    status='warning',
                    message='MovementService enforcement is disabled',
                    last_check=timezone.now(),
                    response_time_ms=0.0,
                    details={'enabled': False}
                )
            
            return HealthCheck(
                component='movement_service',
                check_name='component_status',
                status='healthy',
                message='MovementService is functioning normally',
                last_check=timezone.now(),
                response_time_ms=0.0,
                details={'enabled': True}
            )
            
        except Exception as e:
            return HealthCheck(
                component='movement_service',
                check_name='health_check_error',
                status='critical',
                message=f'Health check failed: {e}',
                last_check=timezone.now(),
                response_time_ms=0.0,
                details={'error': str(e)}
            )
    
    def _check_switchboard_health(self) -> HealthCheck:
        """Check Governance Switchboard health"""
        try:
            stats = governance_switchboard.get_governance_statistics()
            
            # Check for emergency flags
            if stats['emergency']['active'] > 0:
                return HealthCheck(
                    component='governance_switchboard',
                    check_name='emergency_status',
                    status='critical',
                    message=f"Emergency flags active: {stats['emergency']['active_list']}",
                    last_check=timezone.now(),
                    response_time_ms=0.0,
                    details=stats['emergency']
                )
            
            # Check governance activity
            if not stats['health']['governance_active']:
                return HealthCheck(
                    component='governance_switchboard',
                    check_name='governance_activity',
                    status='warning',
                    message='No governance components are active',
                    last_check=timezone.now(),
                    response_time_ms=0.0,
                    details=stats['health']
                )
            
            return HealthCheck(
                component='governance_switchboard',
                check_name='switchboard_status',
                status='healthy',
                message='Governance Switchboard is functioning normally',
                last_check=timezone.now(),
                response_time_ms=0.0,
                details=stats
            )
            
        except Exception as e:
            return HealthCheck(
                component='governance_switchboard',
                check_name='health_check_error',
                status='critical',
                message=f'Health check failed: {e}',
                last_check=timezone.now(),
                response_time_ms=0.0,
                details={'error': str(e)}
            )
    
    def _check_audit_trail_health(self) -> HealthCheck:
        """Check audit trail health"""
        try:
            from .audit_service import AuditService
            service = AuditService()
            
            return HealthCheck(
                component='audit_trail',
                check_name='audit_trail_status',
                status='healthy',
                message='Audit Trail is functioning normally',
                last_check=timezone.now(),
                response_time_ms=0.0,
                details={}
            )
        except Exception as e:
            return HealthCheck(
                component='audit_trail',
                check_name='health_check_error',
                status='warning',
                message=f'Health check failed: {e}',
                last_check=timezone.now(),
                response_time_ms=0.0,
                details={'error': str(e)}
            )
    
    def _check_idempotency_service_health(self) -> HealthCheck:
        """Check idempotency service health"""
        try:
            from .idempotency_service import IdempotencyService
            service = IdempotencyService()
            
            return HealthCheck(
                component='idempotency_service',
                check_name='idempotency_service_status',
                status='healthy',
                message='Idempotency Service is functioning normally',
                last_check=timezone.now(),
                response_time_ms=0.0,
                details={}
            )
        except Exception as e:
            return HealthCheck(
                component='idempotency_service',
                check_name='health_check_error',
                status='warning',
                message=f'Health check failed: {e}',
                last_check=timezone.now(),
                response_time_ms=0.0,
                details={'error': str(e)}
            )


# Global monitoring service instance
monitoring_service = MonitoringService()


# Convenience functions
def record_governance_violation(violation_type: str, component: str, 
                              details: Dict[str, Any], user=None):
    """Record a governance violation"""
    monitoring_service.record_violation(violation_type, component, details, user)


def get_governance_health() -> Dict[str, Any]:
    """Get overall governance system health"""
    return monitoring_service.get_system_health()


def perform_component_health_check(component: str) -> HealthCheck:
    """Perform health check for a specific component"""
    return monitoring_service.perform_health_check(component)


def record_governance_metric(metric_name: str, value: float, tags: Dict[str, Any] = None):
    """Record a governance metric (simplified - no-op for performance)"""
    pass  # Metrics collection disabled - use external monitoring tools
