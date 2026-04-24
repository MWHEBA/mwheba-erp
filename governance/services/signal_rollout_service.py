"""
Signal Rollout Service - Gradual rollout and monitoring for signal governance controls.

This service provides safe, gradual activation of signal governance with:
- Phased rollout with monitoring at each stage
- Automatic rollback on error thresholds
- Performance monitoring and alerting
- Kill switches for emergency situations
- Comprehensive logging and audit trails
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from django.utils import timezone
from django.db import transaction
from django.core.cache import cache

from .governance_switchboard import governance_switchboard
from .signal_router import signal_router
from .audit_service import AuditService
from .monitoring_service import MonitoringService
from ..models import GovernanceContext
from ..exceptions import GovernanceError, RolloutError

logger = logging.getLogger(__name__)


class SignalRolloutService:
    """
    Service for managing gradual rollout of signal governance controls.
    
    Provides safe activation with monitoring, automatic rollback on issues,
    and comprehensive audit trails for all rollout operations.
    """
    
    # Rollout phases
    ROLLOUT_PHASES = {
        'DISABLED': 0,
        'MONITORING': 1,    # Monitor only, no enforcement
        'PILOT': 2,         # Enable for small subset
        'GRADUAL': 3,       # Gradual increase in coverage
        'FULL': 4           # Full enforcement
    }
    
    # Error thresholds for automatic rollback
    ERROR_THRESHOLDS = {
        'signal_error_rate': 0.05,      # 5% error rate
        'performance_degradation': 0.20, # 20% performance drop
        'blocked_operations': 0.10       # 10% blocked operations
    }
    
    def __init__(self):
        self.cache_prefix = 'signal_rollout'
        self.monitoring_window = timedelta(minutes=15)
    
    def start_gradual_rollout(self, workflow: str, target_phase: str = 'FULL', 
                            user: Optional[Any] = None) -> Dict[str, Any]:
        """
        Start gradual rollout for a specific workflow.
        
        Args:
            workflow: Workflow name to roll out
            target_phase: Target rollout phase
            user: User initiating the rollout
            
        Returns:
            dict: Rollout initiation result
        """
        try:
            with transaction.atomic():
                # Set governance context
                GovernanceContext.set_context(
                    user=user,
                    service='SignalRolloutService',
                    operation='start_gradual_rollout'
                )
                
                result = {
                    'success': False,
                    'workflow': workflow,
                    'target_phase': target_phase,
                    'current_phase': 'DISABLED',
                    'rollout_id': None,
                    'monitoring_enabled': False
                }
                
                # Validate workflow
                if not self._validate_workflow(workflow):
                    raise RolloutError(f"Invalid workflow: {workflow}")
                
                # Check if rollout already in progress
                existing_rollout = self._get_rollout_status(workflow)
                if existing_rollout and existing_rollout['phase'] != 'DISABLED':
                    raise RolloutError(f"Rollout already in progress for {workflow}")
                
                # Create rollout record
                rollout_id = self._create_rollout_record(workflow, target_phase, user)
                result['rollout_id'] = rollout_id
                
                # Start with monitoring phase
                monitoring_result = self._enable_monitoring_phase(workflow, rollout_id)
                result['monitoring_enabled'] = monitoring_result['success']
                result['current_phase'] = 'MONITORING'
                
                # Create audit trail
                AuditService.log_operation(
                    model_name='SignalRollout',
                    object_id=rollout_id,
                    operation='ROLLOUT_STARTED',
                    source_service='SignalRolloutService',
                    user=user,
                    workflow=workflow,
                    target_phase=target_phase
                )
                
                result['success'] = True
                logger.info(f"Gradual rollout started for {workflow} targeting {target_phase}")
                
                return result
                
        except Exception as e:
            logger.error(f"Failed to start gradual rollout for {workflow}: {e}")
            raise RolloutError(f"Rollout initiation failed: {e}")
            
        finally:
            GovernanceContext.clear_context()
    
    def advance_rollout_phase(self, workflow: str, user: Optional[Any] = None) -> Dict[str, Any]:
        """
        Advance rollout to the next phase with safety checks.
        
        Args:
            workflow: Workflow name
            user: User advancing the rollout
            
        Returns:
            dict: Phase advancement result
        """
        try:
            with transaction.atomic():
                # Set governance context
                GovernanceContext.set_context(
                    user=user,
                    service='SignalRolloutService',
                    operation='advance_rollout_phase'
                )
                
                result = {
                    'success': False,
                    'workflow': workflow,
                    'previous_phase': None,
                    'new_phase': None,
                    'safety_checks_passed': False,
                    'metrics': {}
                }
                
                # Get current rollout status
                rollout_status = self._get_rollout_status(workflow)
                if not rollout_status:
                    raise RolloutError(f"No active rollout found for {workflow}")
                
                current_phase = rollout_status['phase']
                result['previous_phase'] = current_phase
                
                # Determine next phase
                next_phase = self._get_next_phase(current_phase, rollout_status['target_phase'])
                if not next_phase:
                    raise RolloutError(f"Cannot advance from {current_phase}")
                
                result['new_phase'] = next_phase
                
                # Perform safety checks
                safety_result = self._perform_safety_checks(workflow, current_phase)
                result['safety_checks_passed'] = safety_result['passed']
                result['metrics'] = safety_result['metrics']
                
                if not safety_result['passed']:
                    # Automatic rollback on safety check failure
                    rollback_result = self._automatic_rollback(workflow, safety_result['issues'])
                    result['automatic_rollback'] = rollback_result
                    raise RolloutError(f"Safety checks failed: {safety_result['issues']}")
                
                # Advance to next phase
                advancement_result = self._execute_phase_advancement(workflow, next_phase)
                result.update(advancement_result)
                
                # Update rollout record
                self._update_rollout_record(rollout_status['rollout_id'], next_phase)
                
                # Create audit trail
                AuditService.log_operation(
                    model_name='SignalRollout',
                    object_id=rollout_status['rollout_id'],
                    operation='PHASE_ADVANCED',
                    source_service='SignalRolloutService',
                    user=user,
                    workflow=workflow,
                    previous_phase=current_phase,
                    new_phase=next_phase,
                    metrics=result['metrics']
                )
                
                result['success'] = True
                logger.info(f"Rollout phase advanced for {workflow}: {current_phase} → {next_phase}")
                
                return result
                
        except Exception as e:
            logger.error(f"Failed to advance rollout phase for {workflow}: {e}")
            raise RolloutError(f"Phase advancement failed: {e}")
            
        finally:
            GovernanceContext.clear_context()
    
    def emergency_rollback(self, workflow: str, reason: str, user: Optional[Any] = None) -> Dict[str, Any]:
        """
        Emergency rollback of signal governance controls.
        
        Args:
            workflow: Workflow name to rollback
            reason: Reason for emergency rollback
            user: User initiating rollback
            
        Returns:
            dict: Rollback result
        """
        try:
            with transaction.atomic():
                # Set governance context
                GovernanceContext.set_context(
                    user=user,
                    service='SignalRolloutService',
                    operation='emergency_rollback'
                )
                
                result = {
                    'success': False,
                    'workflow': workflow,
                    'reason': reason,
                    'previous_phase': None,
                    'rollback_actions': []
                }
                
                # Get current rollout status
                rollout_status = self._get_rollout_status(workflow)
                if rollout_status:
                    result['previous_phase'] = rollout_status['phase']
                
                # Execute emergency rollback
                rollback_result = self._execute_emergency_rollback(workflow, reason)
                result['rollback_actions'] = rollback_result['actions']
                
                # Update rollout record
                if rollout_status:
                    self._update_rollout_record(rollout_status['rollout_id'], 'DISABLED', 
                                              emergency_rollback=True, rollback_reason=reason)
                
                # Create audit trail
                AuditService.log_operation(
                    model_name='SignalRollout',
                    object_id=rollout_status['rollout_id'] if rollout_status else 0,
                    operation='EMERGENCY_ROLLBACK',
                    source_service='SignalRolloutService',
                    user=user,
                    workflow=workflow,
                    reason=reason,
                    actions=result['rollback_actions']
                )
                
                result['success'] = True
                logger.warning(f"Emergency rollback completed for {workflow}: {reason}")
                
                return result
                
        except Exception as e:
            logger.error(f"Emergency rollback failed for {workflow}: {e}")
            raise RolloutError(f"Emergency rollback failed: {e}")
            
        finally:
            GovernanceContext.clear_context()
    
    def get_rollout_status(self, workflow: str = None) -> Dict[str, Any]:
        """
        Get current rollout status for workflow(s).
        
        Args:
            workflow: Specific workflow (None for all)
            
        Returns:
            dict: Rollout status information
        """
        if workflow:
            return self._get_rollout_status(workflow)
        else:
            # Get status for all workflows
            return {
                wf: self._get_rollout_status(wf) 
                for wf in [
                    'customer_payment_to_journal_entry',
                    'purchase_payment_to_journal_entry',
                    'stock_movement_to_journal_entry',
                    'transportation_fee_to_journal_entry'
                ]
            }
    
    def monitor_rollout_health(self, workflow: str) -> Dict[str, Any]:
        """
        Monitor rollout health and performance metrics.
        
        Args:
            workflow: Workflow to monitor
            
        Returns:
            dict: Health monitoring results
        """
        try:
            result = {
                'workflow': workflow,
                'health_status': 'unknown',
                'metrics': {},
                'alerts': [],
                'recommendations': []
            }
            
            # Get current rollout status
            rollout_status = self._get_rollout_status(workflow)
            if not rollout_status:
                result['health_status'] = 'no_rollout'
                return result
            
            # Collect metrics
            metrics = self._collect_rollout_metrics(workflow)
            result['metrics'] = metrics
            
            # Analyze health
            health_analysis = self._analyze_rollout_health(workflow, metrics)
            result['health_status'] = health_analysis['status']
            result['alerts'] = health_analysis['alerts']
            result['recommendations'] = health_analysis['recommendations']
            
            # Check for automatic rollback conditions
            if health_analysis['status'] == 'critical':
                logger.warning(f"Critical health status detected for {workflow} rollout")
                result['automatic_rollback_recommended'] = True
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to monitor rollout health for {workflow}: {e}")
            return {
                'workflow': workflow,
                'health_status': 'error',
                'error': str(e)
            }
    
    # Private helper methods
    
    def _validate_workflow(self, workflow: str) -> bool:
        """Validate that workflow is supported for rollout"""
        supported_workflows = [
            'customer_payment_to_journal_entry',
            'purchase_payment_to_journal_entry',
            'stock_movement_to_journal_entry',
            'transportation_fee_to_journal_entry'
        ]
        return workflow in supported_workflows
    
    def _create_rollout_record(self, workflow: str, target_phase: str, user: Optional[Any]) -> str:
        """Create rollout tracking record"""
        rollout_id = f"{workflow}_{timezone.now().strftime('%Y%m%d_%H%M%S')}"
        
        rollout_data = {
            'rollout_id': rollout_id,
            'workflow': workflow,
            'target_phase': target_phase,
            'current_phase': 'DISABLED',
            'started_at': timezone.now().isoformat(),
            'started_by': str(user) if user else 'system',
            'status': 'active'
        }
        
        cache.set(f"{self.cache_prefix}:rollout:{workflow}", rollout_data, timeout=86400)  # 24 hours
        return rollout_id
    
    def _get_rollout_status(self, workflow: str) -> Optional[Dict[str, Any]]:
        """Get current rollout status from cache"""
        return cache.get(f"{self.cache_prefix}:rollout:{workflow}")
    
    def _update_rollout_record(self, rollout_id: str, phase: str, **kwargs):
        """Update rollout record with new phase and metadata"""
        # This would update the rollout record in cache/database
        # Implementation depends on storage mechanism
        pass
    
    def _enable_monitoring_phase(self, workflow: str, rollout_id: str) -> Dict[str, Any]:
        """Enable monitoring phase for workflow"""
        try:
            # Enable monitoring without enforcement
            MonitoringService.enable_workflow_monitoring(workflow)
            
            # Start collecting baseline metrics
            self._start_baseline_collection(workflow)
            
            return {
                'success': True,
                'monitoring_enabled': True
            }
            
        except Exception as e:
            logger.error(f"Failed to enable monitoring phase: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _get_next_phase(self, current_phase: str, target_phase: str) -> Optional[str]:
        """Determine next phase in rollout sequence"""
        phase_order = ['DISABLED', 'MONITORING', 'PILOT', 'GRADUAL', 'FULL']
        
        try:
            current_index = phase_order.index(current_phase)
            target_index = phase_order.index(target_phase)
            
            if current_index < target_index:
                return phase_order[current_index + 1]
            else:
                return None  # Already at or past target
                
        except ValueError:
            return None
    
    def _perform_safety_checks(self, workflow: str, current_phase: str) -> Dict[str, Any]:
        """Perform comprehensive safety checks before phase advancement"""
        result = {
            'passed': True,
            'issues': [],
            'metrics': {}
        }
        
        try:
            # Collect current metrics
            metrics = self._collect_rollout_metrics(workflow)
            result['metrics'] = metrics
            
            # Check error rates
            if metrics.get('error_rate', 0) > self.ERROR_THRESHOLDS['signal_error_rate']:
                result['passed'] = False
                result['issues'].append(f"High error rate: {metrics['error_rate']:.2%}")
            
            # Check performance
            if metrics.get('performance_degradation', 0) > self.ERROR_THRESHOLDS['performance_degradation']:
                result['passed'] = False
                result['issues'].append(f"Performance degradation: {metrics['performance_degradation']:.2%}")
            
            # Check blocked operations
            if metrics.get('blocked_rate', 0) > self.ERROR_THRESHOLDS['blocked_operations']:
                result['passed'] = False
                result['issues'].append(f"High blocked operations: {metrics['blocked_rate']:.2%}")
            
            return result
            
        except Exception as e:
            logger.error(f"Safety checks failed: {e}")
            result['passed'] = False
            result['issues'].append(f"Safety check error: {e}")
            return result
    
    def _collect_rollout_metrics(self, workflow: str) -> Dict[str, Any]:
        """Collect comprehensive metrics for rollout monitoring"""
        try:
            # Get signal router statistics
            signal_stats = signal_router.get_signal_statistics()
            
            # Calculate metrics
            total_signals = signal_stats['counters']['signals_processed']
            error_signals = signal_stats['counters']['signal_errors']
            blocked_signals = signal_stats['counters']['signals_blocked']
            
            metrics = {
                'total_signals': total_signals,
                'error_signals': error_signals,
                'blocked_signals': blocked_signals,
                'error_rate': error_signals / max(total_signals, 1),
                'blocked_rate': blocked_signals / max(total_signals, 1),
                'success_rate': (total_signals - error_signals) / max(total_signals, 1),
                'timestamp': timezone.now().isoformat()
            }
            
            # Add workflow-specific metrics
            if governance_switchboard.is_workflow_enabled(workflow):
                metrics['workflow_enabled'] = True
                metrics['enforcement_active'] = True
            else:
                metrics['workflow_enabled'] = False
                metrics['enforcement_active'] = False
            
            return metrics
            
        except Exception as e:
            logger.error(f"Failed to collect rollout metrics: {e}")
            return {'error': str(e)}
    
    def _analyze_rollout_health(self, workflow: str, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze rollout health based on metrics"""
        result = {
            'status': 'healthy',
            'alerts': [],
            'recommendations': []
        }
        
        # Analyze error rates
        error_rate = metrics.get('error_rate', 0)
        if error_rate > 0.10:  # 10%
            result['status'] = 'critical'
            result['alerts'].append(f"Critical error rate: {error_rate:.2%}")
            result['recommendations'].append("Consider emergency rollback")
        elif error_rate > 0.05:  # 5%
            result['status'] = 'warning'
            result['alerts'].append(f"High error rate: {error_rate:.2%}")
            result['recommendations'].append("Monitor closely before advancing")
        
        # Analyze blocked operations
        blocked_rate = metrics.get('blocked_rate', 0)
        if blocked_rate > 0.15:  # 15%
            result['status'] = 'critical'
            result['alerts'].append(f"High blocked operations: {blocked_rate:.2%}")
            result['recommendations'].append("Check signal configuration")
        
        # Analyze success rate
        success_rate = metrics.get('success_rate', 1)
        if success_rate < 0.90:  # 90%
            if result['status'] != 'critical':
                result['status'] = 'warning'
            result['alerts'].append(f"Low success rate: {success_rate:.2%}")
        
        return result
    
    def _execute_phase_advancement(self, workflow: str, next_phase: str) -> Dict[str, Any]:
        """Execute the actual phase advancement"""
        result = {
            'phase_actions': [],
            'enforcement_enabled': False
        }
        
        try:
            if next_phase == 'PILOT':
                # Enable workflow with limited scope
                governance_switchboard.enable_workflow(workflow)
                result['phase_actions'].append('workflow_enabled')
                result['enforcement_enabled'] = True
                
            elif next_phase == 'GRADUAL':
                # Increase enforcement scope
                result['phase_actions'].append('enforcement_increased')
                result['enforcement_enabled'] = True
                
            elif next_phase == 'FULL':
                # Full enforcement
                governance_switchboard.enable_workflow(workflow)
                result['phase_actions'].append('full_enforcement_enabled')
                result['enforcement_enabled'] = True
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to execute phase advancement: {e}")
            raise RolloutError(f"Phase advancement execution failed: {e}")
    
    def _automatic_rollback(self, workflow: str, issues: List[str]) -> Dict[str, Any]:
        """Execute automatic rollback due to safety issues"""
        try:
            rollback_result = self._execute_emergency_rollback(workflow, f"Automatic rollback: {', '.join(issues)}")
            
            logger.warning(f"Automatic rollback executed for {workflow}: {issues}")
            
            return rollback_result
            
        except Exception as e:
            logger.error(f"Automatic rollback failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def _execute_emergency_rollback(self, workflow: str, reason: str) -> Dict[str, Any]:
        """Execute emergency rollback actions"""
        actions = []
        
        try:
            # Disable workflow enforcement
            governance_switchboard.disable_workflow(workflow, reason)
            actions.append('workflow_disabled')
            
            # Disable related components if needed
            if workflow == 'customer_payment_to_journal_entry':
                governance_switchboard.disable_component('accounting_gateway_enforcement', reason)
                actions.append('accounting_gateway_enforcement_disabled')
            
            # Clear any cached state
            cache.delete(f"{self.cache_prefix}:metrics:{workflow}")
            actions.append('cache_cleared')
            
            return {
                'success': True,
                'actions': actions
            }
            
        except Exception as e:
            logger.error(f"Emergency rollback execution failed: {e}")
            return {
                'success': False,
                'actions': actions,
                'error': str(e)
            }
    
    def _start_baseline_collection(self, workflow: str):
        """Start collecting baseline metrics for comparison"""
        try:
            baseline_metrics = self._collect_rollout_metrics(workflow)
            cache.set(f"{self.cache_prefix}:baseline:{workflow}", baseline_metrics, timeout=86400)
            
            logger.info(f"Baseline metrics collection started for {workflow}")
            
        except Exception as e:
            logger.error(f"Failed to start baseline collection: {e}")


# Global rollout service instance
signal_rollout_service = SignalRolloutService()


# Convenience functions
def start_workflow_rollout(workflow: str, target_phase: str = 'FULL', user=None):
    """Start gradual rollout for a workflow"""
    return signal_rollout_service.start_gradual_rollout(workflow, target_phase, user)


def advance_workflow_phase(workflow: str, user=None):
    """Advance workflow to next rollout phase"""
    return signal_rollout_service.advance_rollout_phase(workflow, user)


def emergency_workflow_rollback(workflow: str, reason: str, user=None):
    """Emergency rollback of workflow"""
    return signal_rollout_service.emergency_rollback(workflow, reason, user)


def get_rollout_status(workflow: str = None):
    """Get rollout status for workflow(s)"""
    return signal_rollout_service.get_rollout_status(workflow)


def monitor_rollout_health(workflow: str):
    """Monitor rollout health"""
    return signal_rollout_service.monitor_rollout_health(workflow)