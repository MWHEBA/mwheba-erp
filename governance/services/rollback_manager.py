"""
Safe Rollback Manager for Governance System.

Provides comprehensive rollback mechanisms for governance components with:
- Feature flag state management with proper locking
- Monitoring and alerting for governance violations
- Emergency disable switches for each component/workflow
- Safe rollback with state preservation and recovery
- Automated rollback triggers based on violation thresholds

Key Features:
- Thread-safe rollback operations
- State snapshots for safe recovery
- Violation threshold monitoring
- Automated emergency responses
- Comprehensive audit logging
"""

import threading
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from django.db import transaction
from django.utils import timezone
from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail

from ..models import GovernanceContext, AuditTrail
from ..exceptions import GovernanceError, ValidationError, RollbackError
from ..thread_safety import monitor_operation, ThreadSafeCounter
from .audit_service import AuditService
from .governance_switchboard import governance_switchboard

logger = logging.getLogger(__name__)


@dataclass
class GovernanceSnapshot:
    """Represents a snapshot of governance state for rollback purposes"""
    timestamp: datetime
    component_flags: Dict[str, bool]
    workflow_flags: Dict[str, bool]
    emergency_flags: Dict[str, bool]
    reason: str
    created_by: str
    snapshot_id: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert snapshot to dictionary"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GovernanceSnapshot':
        """Create snapshot from dictionary"""
        return cls(**data)


@dataclass
class ViolationThreshold:
    """Defines violation thresholds for automated rollback"""
    violation_type: str
    max_violations: int
    time_window_minutes: int
    rollback_action: str  # 'disable_component', 'disable_workflow', 'emergency_disable'
    target: str  # component/workflow/emergency flag name
    enabled: bool = True


class RollbackManager:
    """
    Manages safe rollback mechanisms for governance system.
    
    Provides:
    1. State snapshots for safe rollback
    2. Violation monitoring and automated responses
    3. Emergency rollback triggers
    4. State preservation and recovery
    """
    
    # Default violation thresholds
    DEFAULT_THRESHOLDS = [
        ViolationThreshold(
            violation_type='authority_violation',
            max_violations=10,
            time_window_minutes=5,
            rollback_action='disable_component',
            target='authority_boundary_enforcement'
        ),
        ViolationThreshold(
            violation_type='accounting_gateway_bypass',
            max_violations=5,
            time_window_minutes=2,
            rollback_action='emergency_disable',
            target='emergency_disable_accounting'
        ),
        ViolationThreshold(
            violation_type='stock_movement_violation',
            max_violations=3,
            time_window_minutes=1,
            rollback_action='emergency_disable',
            target='emergency_disable_stock'
        ),
        ViolationThreshold(
            violation_type='admin_bypass_attempt',
            max_violations=5,
            time_window_minutes=5,
            rollback_action='disable_component',
            target='admin_lockdown_enforcement'
        ),
        ViolationThreshold(
            violation_type='signal_chain_overflow',
            max_violations=20,
            time_window_minutes=1,
            rollback_action='disable_component',
            target='signal_router_governance'
        ),
        ViolationThreshold(
            violation_type='idempotency_violation',
            max_violations=15,
            time_window_minutes=5,
            rollback_action='disable_component',
            target='idempotency_enforcement'
        )
    ]
    
    def __init__(self, max_snapshots: int = 50, alert_email: Optional[str] = None):
        """
        Initialize Rollback Manager.
        
        Args:
            max_snapshots: Maximum number of snapshots to keep
            alert_email: Email address for critical alerts
        """
        self.max_snapshots = max_snapshots
        self.alert_email = alert_email or getattr(settings, 'GOVERNANCE_ALERT_EMAIL', None)
        
        # Thread-safe locks
        self._snapshot_lock = threading.RLock()
        self._violation_lock = threading.RLock()
        self._rollback_lock = threading.RLock()
        
        # State storage
        self._snapshots: List[GovernanceSnapshot] = []
        self._violation_counts: Dict[str, List[datetime]] = {}
        self._thresholds: List[ViolationThreshold] = self.DEFAULT_THRESHOLDS.copy()
        
        # Monitoring counters
        self._rollback_count = ThreadSafeCounter()
        self._violation_count = ThreadSafeCounter()
        self._emergency_rollback_count = ThreadSafeCounter()
        
        # Load snapshots from cache
        self._load_snapshots_from_cache()
        
        logger.info("RollbackManager initialized")
    
    def create_snapshot(self, reason: str, user=None) -> GovernanceSnapshot:
        """
        Create a snapshot of current governance state.
        
        Args:
            reason: Reason for creating snapshot
            user: User creating the snapshot
            
        Returns:
            GovernanceSnapshot: Created snapshot
        """
        with monitor_operation("create_governance_snapshot"):
            with self._snapshot_lock:
                # Get current state
                current_user = user or GovernanceContext.get_current_user()
                username = current_user.username if current_user else 'system'
                
                snapshot = GovernanceSnapshot(
                    timestamp=timezone.now(),
                    component_flags=dict(governance_switchboard._component_flags),
                    workflow_flags=dict(governance_switchboard._workflow_flags),
                    emergency_flags=dict(governance_switchboard._emergency_flags),
                    reason=reason,
                    created_by=username,
                    snapshot_id=f"snapshot_{timezone.now().strftime('%Y%m%d_%H%M%S')}_{len(self._snapshots)}"
                )
                
                # Add to snapshots list
                self._snapshots.append(snapshot)
                
                # Maintain max snapshots limit
                if len(self._snapshots) > self.max_snapshots:
                    removed_snapshot = self._snapshots.pop(0)
                    logger.info(f"Removed old snapshot: {removed_snapshot.snapshot_id}")
                
                # Save to cache
                self._save_snapshots_to_cache()
                
                # Log snapshot creation
                logger.info(f"Governance snapshot created: {snapshot.snapshot_id} - {reason}")
                
                # Audit the snapshot creation
                AuditService.log_operation(
                    model_name='RollbackManager',
                    object_id=0,
                    operation='SNAPSHOT_CREATED',
                    source_service='RollbackManager',
                    user=current_user,
                    after_data={
                        'snapshot_id': snapshot.snapshot_id,
                        'reason': reason,
                        'component_count': len(snapshot.component_flags),
                        'workflow_count': len(snapshot.workflow_flags),
                        'emergency_count': len(snapshot.emergency_flags)
                    }
                )
                
                return snapshot
    
    def rollback_to_snapshot(self, snapshot_id: str, reason: str, user=None) -> bool:
        """
        Rollback governance state to a specific snapshot.
        
        Args:
            snapshot_id: ID of the snapshot to rollback to
            reason: Reason for rollback
            user: User performing rollback
            
        Returns:
            bool: True if rollback successful
        """
        with monitor_operation("rollback_to_snapshot"):
            with self._rollback_lock:
                # Find the snapshot
                snapshot = None
                for s in self._snapshots:
                    if s.snapshot_id == snapshot_id:
                        snapshot = s
                        break
                
                if not snapshot:
                    raise ValidationError(f"Snapshot not found: {snapshot_id}")
                
                # Create current state snapshot before rollback
                pre_rollback_snapshot = self.create_snapshot(
                    f"Pre-rollback snapshot before {snapshot_id}",
                    user
                )
                
                try:
                    # Perform rollback
                    success = self._perform_rollback(snapshot, reason, user)
                    
                    if success:
                        self._rollback_count.increment()
                        logger.warning(f"Governance rollback completed: {snapshot_id} - {reason}")
                        
                        # Send alert
                        self._send_rollback_alert(snapshot, reason, user)
                        
                        return True
                    else:
                        logger.error(f"Governance rollback failed: {snapshot_id}")
                        return False
                        
                except Exception as e:
                    logger.error(f"Rollback failed with exception: {e}")
                    
                    # Attempt to rollback to pre-rollback state
                    try:
                        self._perform_rollback(pre_rollback_snapshot, "Emergency recovery", user)
                        logger.warning("Emergency recovery to pre-rollback state successful")
                    except Exception as recovery_error:
                        logger.critical(f"Emergency recovery failed: {recovery_error}")
                        self._send_critical_alert("Rollback and recovery both failed", user)
                    
                    raise RollbackError(f"Rollback failed: {e}")
    
    def _perform_rollback(self, snapshot: GovernanceSnapshot, reason: str, user) -> bool:
        """Perform the actual rollback operation"""
        try:
            with transaction.atomic():
                # Rollback component flags
                for flag_name, enabled in snapshot.component_flags.items():
                    current_enabled = governance_switchboard.is_component_enabled(flag_name)
                    if current_enabled != enabled:
                        if enabled:
                            governance_switchboard.enable_component(flag_name, f"Rollback: {reason}", user)
                        else:
                            governance_switchboard.disable_component(flag_name, f"Rollback: {reason}", user)
                
                # Rollback workflow flags
                for flag_name, enabled in snapshot.workflow_flags.items():
                    current_enabled = governance_switchboard.is_workflow_enabled(flag_name)
                    if current_enabled != enabled:
                        if enabled:
                            governance_switchboard.enable_workflow(flag_name, f"Rollback: {reason}", user)
                        else:
                            governance_switchboard.disable_workflow(flag_name, f"Rollback: {reason}", user)
                
                # Rollback emergency flags
                for flag_name, active in snapshot.emergency_flags.items():
                    current_active = governance_switchboard.is_emergency_flag_active(flag_name)
                    if current_active != active:
                        if active:
                            governance_switchboard.activate_emergency_flag(flag_name, f"Rollback: {reason}", user)
                        else:
                            governance_switchboard.deactivate_emergency_flag(flag_name, f"Rollback: {reason}", user)
                
                # Audit the rollback
                AuditService.log_operation(
                    model_name='RollbackManager',
                    object_id=0,
                    operation='ROLLBACK_COMPLETED',
                    source_service='RollbackManager',
                    user=user or GovernanceContext.get_current_user(),
                    after_data={
                        'snapshot_id': snapshot.snapshot_id,
                        'rollback_reason': reason,
                        'original_snapshot_reason': snapshot.reason,
                        'original_created_by': snapshot.created_by,
                        'rollback_timestamp': timezone.now().isoformat()
                    }
                )
                
                return True
                
        except Exception as e:
            logger.error(f"Rollback operation failed: {e}")
            return False
    
    def record_violation(self, violation_type: str, details: Dict[str, Any], user=None):
        """
        Record a governance violation and check thresholds.
        
        Args:
            violation_type: Type of violation
            details: Violation details
            user: User associated with violation
        """
        with monitor_operation("record_governance_violation"):
            with self._violation_lock:
                current_time = timezone.now()
                
                # Record the violation
                if violation_type not in self._violation_counts:
                    self._violation_counts[violation_type] = []
                
                self._violation_counts[violation_type].append(current_time)
                self._violation_count.increment()
                
                # Clean old violations
                self._clean_old_violations(violation_type, current_time)
                
                # Check thresholds
                self._check_violation_thresholds(violation_type, current_time, details, user)
                
                # Log the violation
                logger.warning(f"Governance violation recorded: {violation_type}")
                logger.warning(f"Details: {details}")
                
                # Record in governance switchboard
                governance_switchboard.record_governance_violation(
                    violation_type, 
                    details.get('component', 'unknown'),
                    details,
                    user
                )
    
    def _clean_old_violations(self, violation_type: str, current_time: datetime):
        """Clean violations older than the maximum time window"""
        if violation_type not in self._violation_counts:
            return
        
        # Find maximum time window from thresholds
        max_window = max(
            (t.time_window_minutes for t in self._thresholds if t.violation_type == violation_type),
            default=60
        )
        
        cutoff_time = current_time - timedelta(minutes=max_window)
        
        # Remove old violations
        self._violation_counts[violation_type] = [
            v_time for v_time in self._violation_counts[violation_type]
            if v_time > cutoff_time
        ]
    
    def _check_violation_thresholds(self, violation_type: str, current_time: datetime, 
                                  details: Dict[str, Any], user):
        """Check if violation thresholds are exceeded and trigger rollback if needed"""
        for threshold in self._thresholds:
            if not threshold.enabled or threshold.violation_type != violation_type:
                continue
            
            # Count violations in time window
            window_start = current_time - timedelta(minutes=threshold.time_window_minutes)
            violations_in_window = [
                v_time for v_time in self._violation_counts[violation_type]
                if v_time > window_start
            ]
            
            if len(violations_in_window) >= threshold.max_violations:
                logger.critical(
                    f"Violation threshold exceeded: {violation_type} "
                    f"({len(violations_in_window)}/{threshold.max_violations} "
                    f"in {threshold.time_window_minutes} minutes)"
                )
                
                # Trigger automated rollback
                self._trigger_automated_rollback(threshold, details, user)
    
    def _trigger_automated_rollback(self, threshold: ViolationThreshold, 
                                  details: Dict[str, Any], user):
        """Trigger automated rollback based on threshold"""
        try:
            reason = f"Automated rollback: {threshold.violation_type} threshold exceeded"
            
            if threshold.rollback_action == 'disable_component':
                success = governance_switchboard.disable_component(
                    threshold.target, reason, user
                )
                action_desc = f"Disabled component: {threshold.target}"
                
            elif threshold.rollback_action == 'disable_workflow':
                success = governance_switchboard.disable_workflow(
                    threshold.target, reason, user
                )
                action_desc = f"Disabled workflow: {threshold.target}"
                
            elif threshold.rollback_action == 'emergency_disable':
                success = governance_switchboard.activate_emergency_flag(
                    threshold.target, reason, user
                )
                action_desc = f"Activated emergency flag: {threshold.target}"
                
            else:
                logger.error(f"Unknown rollback action: {threshold.rollback_action}")
                return
            
            if success:
                self._emergency_rollback_count.increment()
                logger.critical(f"Automated rollback executed: {action_desc}")
                
                # Send critical alert
                self._send_critical_alert(
                    f"Automated rollback executed: {action_desc}\n"
                    f"Trigger: {threshold.violation_type} threshold exceeded\n"
                    f"Details: {details}",
                    user
                )
                
                # Audit the automated rollback
                AuditService.log_operation(
                    model_name='RollbackManager',
                    object_id=0,
                    operation='AUTOMATED_ROLLBACK',
                    source_service='RollbackManager',
                    user=user or GovernanceContext.get_current_user(),
                    after_data={
                        'threshold': asdict(threshold),
                        'action_taken': action_desc,
                        'trigger_details': details,
                        'violation_count': len(self._violation_counts.get(threshold.violation_type, []))
                    }
                )
            else:
                logger.error(f"Automated rollback failed: {action_desc}")
                
        except Exception as e:
            logger.critical(f"Automated rollback failed with exception: {e}")
            self._send_critical_alert(f"Automated rollback failed: {e}", user)
    
    def get_snapshots(self) -> List[GovernanceSnapshot]:
        """Get all available snapshots"""
        with self._snapshot_lock:
            return self._snapshots.copy()
    
    def get_recent_snapshots(self, count: int = 10) -> List[GovernanceSnapshot]:
        """Get recent snapshots"""
        with self._snapshot_lock:
            return self._snapshots[-count:] if self._snapshots else []
    
    def get_violation_statistics(self) -> Dict[str, Any]:
        """Get violation statistics"""
        with self._violation_lock:
            current_time = timezone.now()
            
            # Clean old violations first
            for violation_type in list(self._violation_counts.keys()):
                self._clean_old_violations(violation_type, current_time)
            
            stats = {
                'total_violations': self._violation_count.get_value(),
                'total_rollbacks': self._rollback_count.get_value(),
                'emergency_rollbacks': self._emergency_rollback_count.get_value(),
                'violation_types': {},
                'active_thresholds': len([t for t in self._thresholds if t.enabled]),
                'recent_violations': {}
            }
            
            # Calculate violation type statistics
            for violation_type, violations in self._violation_counts.items():
                stats['violation_types'][violation_type] = len(violations)
                
                # Recent violations (last hour)
                recent_cutoff = current_time - timedelta(hours=1)
                recent_violations = [v for v in violations if v > recent_cutoff]
                stats['recent_violations'][violation_type] = len(recent_violations)
            
            return stats
    
    def _send_rollback_alert(self, snapshot: GovernanceSnapshot, reason: str, user):
        """Send rollback alert email"""
        if not self.alert_email:
            return
        
        try:
            subject = f"Governance Rollback Executed - {snapshot.snapshot_id}"
            message = f"""
Governance system rollback has been executed.

Snapshot ID: {snapshot.snapshot_id}
Rollback Reason: {reason}
Original Snapshot Reason: {snapshot.reason}
Original Created By: {snapshot.created_by}
Rollback Executed By: {user.username if user else 'system'}
Rollback Time: {timezone.now()}

Snapshot Details:
- Component Flags: {len(snapshot.component_flags)}
- Workflow Flags: {len(snapshot.workflow_flags)}
- Emergency Flags: {len(snapshot.emergency_flags)}

Please review the system status and take appropriate action if needed.
            """
            
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[self.alert_email],
                fail_silently=True
            )
            
        except Exception as e:
            logger.error(f"Failed to send rollback alert: {e}")
    
    def _send_critical_alert(self, message: str, user):
        """Send critical alert email"""
        if not self.alert_email:
            return
        
        try:
            subject = "CRITICAL: Governance System Alert"
            full_message = f"""
CRITICAL GOVERNANCE SYSTEM ALERT

{message}

Time: {timezone.now()}
User: {user.username if user else 'system'}

Please investigate immediately and take corrective action.
            """
            
            send_mail(
                subject=subject,
                message=full_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[self.alert_email],
                fail_silently=True
            )
            
        except Exception as e:
            logger.error(f"Failed to send critical alert: {e}")
    
    def _save_snapshots_to_cache(self):
        """Save snapshots to cache for persistence"""
        try:
            snapshot_data = [s.to_dict() for s in self._snapshots]
            cache.set('governance_snapshots', snapshot_data, timeout=86400)  # 24 hours
        except Exception as e:
            logger.error(f"Failed to save snapshots to cache: {e}")
    
    def _load_snapshots_from_cache(self):
        """Load snapshots from cache"""
        try:
            snapshot_data = cache.get('governance_snapshots', [])
            self._snapshots = [
                GovernanceSnapshot.from_dict(data) for data in snapshot_data
            ]
            logger.info(f"Loaded {len(self._snapshots)} snapshots from cache")
        except Exception as e:
            logger.error(f"Failed to load snapshots from cache: {e}")
            self._snapshots = []
    
    def add_violation_threshold(self, threshold: ViolationThreshold):
        """Add a custom violation threshold"""
        with self._violation_lock:
            self._thresholds.append(threshold)
            logger.info(f"Added violation threshold: {threshold.violation_type}")
    
    def remove_violation_threshold(self, violation_type: str, target: str):
        """Remove a violation threshold"""
        with self._violation_lock:
            self._thresholds = [
                t for t in self._thresholds
                if not (t.violation_type == violation_type and t.target == target)
            ]
            logger.info(f"Removed violation threshold: {violation_type} -> {target}")
    
    def enable_threshold(self, violation_type: str, target: str):
        """Enable a violation threshold"""
        with self._violation_lock:
            for threshold in self._thresholds:
                if threshold.violation_type == violation_type and threshold.target == target:
                    threshold.enabled = True
                    logger.info(f"Enabled threshold: {violation_type} -> {target}")
                    break
    
    def disable_threshold(self, violation_type: str, target: str):
        """Disable a violation threshold"""
        with self._violation_lock:
            for threshold in self._thresholds:
                if threshold.violation_type == violation_type and threshold.target == target:
                    threshold.enabled = False
                    logger.info(f"Disabled threshold: {violation_type} -> {target}")
                    break
    
    @contextmanager
    def rollback_protection(self, reason: str):
        """Context manager that creates snapshot and provides rollback protection"""
        snapshot = self.create_snapshot(f"Protection snapshot: {reason}")
        try:
            yield snapshot
        except Exception as e:
            logger.error(f"Operation failed, rollback protection available: {e}")
            logger.info(f"Use snapshot {snapshot.snapshot_id} for rollback if needed")
            raise


# Global rollback manager instance
rollback_manager = RollbackManager()


# Convenience functions
def create_governance_snapshot(reason: str, user=None) -> GovernanceSnapshot:
    """Create a governance state snapshot"""
    return rollback_manager.create_snapshot(reason, user)


def rollback_to_snapshot(snapshot_id: str, reason: str, user=None) -> bool:
    """Rollback to a specific snapshot"""
    return rollback_manager.rollback_to_snapshot(snapshot_id, reason, user)


def record_governance_violation(violation_type: str, details: Dict[str, Any], user=None):
    """Record a governance violation"""
    rollback_manager.record_violation(violation_type, details, user)


def get_rollback_statistics() -> Dict[str, Any]:
    """Get rollback and violation statistics"""
    return rollback_manager.get_violation_statistics()


@contextmanager
def rollback_protection(reason: str):
    """Context manager for rollback protection"""
    with rollback_manager.rollback_protection(reason):
        yield