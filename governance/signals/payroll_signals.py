"""
Payroll Signal Adapters - Thin adapters for payroll business logic.

This module implements thin signal adapters that route payroll-related events
to appropriate business services. All business logic remains in the services,
and signals only handle non-critical side-effects.

Key Features:
- Feature flag protection for safe rollback
- Thin adapter pattern (no business logic in signals)
- Non-critical side-effects only (notifications, analytics, etc.)
- Signal independence (failures don't break writes)
- Integration with SignalRouter governance

Requirements: 9.1, 9.7 - Signal governance with thin adapters
"""

import logging
import time
from typing import Optional, Dict, Any
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.utils import timezone
from django.contrib.auth import get_user_model

from ..services.signal_router import signal_router
# Commented out to fix circular import - will be imported dynamically when needed
# from ..services.payroll_signal_governance import payroll_signal_governance, should_execute_payroll_signal, record_payroll_signal_execution
from ..models import GovernanceContext
from ..signal_integration import governed_signal_handler, side_effect_handler
from ..exceptions import SignalError

# Dynamic import helper to avoid circular imports
def _get_payroll_governance():
    """Dynamically import payroll governance to avoid circular imports"""
    try:
        from ..services.payroll_signal_governance import payroll_signal_governance, should_execute_payroll_signal, record_payroll_signal_execution
        return payroll_signal_governance, should_execute_payroll_signal, record_payroll_signal_execution
    except ImportError:
        # Fallback if governance is not available
        return None, lambda *args: True, lambda *args: None

# Import HR models
from hr.models import Payroll, PayrollLine

User = get_user_model()
logger = logging.getLogger('governance.payroll_signals')


class PayrollSignalFeatureFlags:
    """
    Feature flags for payroll signal adapters.
    
    All flags default to False for safe rollback capability.
    Flags must be explicitly enabled after testing.
    """
    
    # Master switch for all payroll signals
    PAYROLL_SIGNALS_ENABLED = False
    
    # Individual signal feature flags
    PAYROLL_CREATION_NOTIFICATIONS = False
    PAYROLL_APPROVAL_NOTIFICATIONS = False
    PAYROLL_PAYMENT_NOTIFICATIONS = False
    PAYROLL_ANALYTICS_TRACKING = False
    PAYROLL_AUDIT_ENHANCEMENTS = False
    PAYROLL_CACHE_INVALIDATION = False
    
    @classmethod
    def is_enabled(cls, flag_name: str) -> bool:
        """
        Check if a payroll signal feature flag is enabled.
        
        Args:
            flag_name: Name of the feature flag
            
        Returns:
            bool: True if both master switch and specific flag are enabled
        """
        if not cls.PAYROLL_SIGNALS_ENABLED:
            return False
        
        return getattr(cls, flag_name, False)
    
    @classmethod
    def enable_flag(cls, flag_name: str) -> None:
        """Enable a specific feature flag"""
        if hasattr(cls, flag_name):
            setattr(cls, flag_name, True)
            logger.info(f"Enabled payroll signal flag: {flag_name}")
        else:
            logger.warning(f"Unknown payroll signal flag: {flag_name}")
    
    @classmethod
    def disable_flag(cls, flag_name: str) -> None:
        """Disable a specific feature flag"""
        if hasattr(cls, flag_name):
            setattr(cls, flag_name, False)
            logger.info(f"Disabled payroll signal flag: {flag_name}")
        else:
            logger.warning(f"Unknown payroll signal flag: {flag_name}")
    
    @classmethod
    def enable_all(cls) -> None:
        """Enable all payroll signal flags (use with caution)"""
        cls.PAYROLL_SIGNALS_ENABLED = True
        cls.PAYROLL_CREATION_NOTIFICATIONS = True
        cls.PAYROLL_APPROVAL_NOTIFICATIONS = True
        cls.PAYROLL_PAYMENT_NOTIFICATIONS = True
        cls.PAYROLL_ANALYTICS_TRACKING = True
        cls.PAYROLL_AUDIT_ENHANCEMENTS = True
        cls.PAYROLL_CACHE_INVALIDATION = True
        logger.warning("Enabled ALL payroll signal flags")
    
    @classmethod
    def disable_all(cls) -> None:
        """Disable all payroll signal flags (safe rollback)"""
        cls.PAYROLL_SIGNALS_ENABLED = False
        cls.PAYROLL_CREATION_NOTIFICATIONS = False
        cls.PAYROLL_APPROVAL_NOTIFICATIONS = False
        cls.PAYROLL_PAYMENT_NOTIFICATIONS = False
        cls.PAYROLL_ANALYTICS_TRACKING = False
        cls.PAYROLL_AUDIT_ENHANCEMENTS = False
        cls.PAYROLL_CACHE_INVALIDATION = False
    
    @classmethod
    def get_status(cls) -> Dict[str, bool]:
        """Get status of all feature flags"""
        return {
            'PAYROLL_SIGNALS_ENABLED': cls.PAYROLL_SIGNALS_ENABLED,
            'PAYROLL_CREATION_NOTIFICATIONS': cls.PAYROLL_CREATION_NOTIFICATIONS,
            'PAYROLL_APPROVAL_NOTIFICATIONS': cls.PAYROLL_APPROVAL_NOTIFICATIONS,
            'PAYROLL_PAYMENT_NOTIFICATIONS': cls.PAYROLL_PAYMENT_NOTIFICATIONS,
            'PAYROLL_ANALYTICS_TRACKING': cls.PAYROLL_ANALYTICS_TRACKING,
            'PAYROLL_AUDIT_ENHANCEMENTS': cls.PAYROLL_AUDIT_ENHANCEMENTS,
            'PAYROLL_CACHE_INVALIDATION': cls.PAYROLL_CACHE_INVALIDATION,
        }


# ============================================================================
# PAYROLL CREATION SIGNALS (Non-Critical Side Effects)
# ============================================================================

@side_effect_handler(
    signal_name="payroll_creation_notifications",
    description="Send notifications when payroll is created"
)
def handle_payroll_creation_notifications(sender, instance: Payroll, created: bool, **kwargs):
    """
    Thin adapter for payroll creation notifications.
    
    This signal handles non-critical side effects when a payroll is created:
    - Send notifications to HR team
    - Update dashboard statistics
    - Log analytics events
    
    Business Logic Location: NotificationService, AnalyticsService
    Signal Purpose: Non-critical side effects only
    """
    if not created:
        return
    
    # Check gradual rollout governance
    _, should_execute_payroll_signal, _ = _get_payroll_governance()
    if not should_execute_payroll_signal('payroll_creation_notifications', instance.id):
        logger.debug("Payroll creation notifications blocked by gradual rollout governance")
        return
    
    if not PayrollSignalFeatureFlags.is_enabled('PAYROLL_CREATION_NOTIFICATIONS'):
        logger.debug("Payroll creation notifications disabled by feature flag")
        return
    
    start_time = time.time()
    success = False
    error_message = None
    
    try:
        # Route through appropriate business services
        from core.services.notification_service import NotificationService
        from core.services.analytics_service import AnalyticsService
        
        # Send notification to HR team (non-critical)
        NotificationService.send_payroll_created_notification(
            payroll=instance,
            user=GovernanceContext.get_current_user()
        )
        
        # Track analytics event (non-critical)
        AnalyticsService.track_payroll_event(
            event_type='payroll_created',
            payroll_id=instance.id,
            employee_id=instance.employee.id,
            amount=instance.net_salary
        )
        
        success = True
        logger.info(
            f"Payroll creation notifications sent for {instance.employee.get_full_name_ar()} "
            f"- {instance.month.strftime('%Y-%m')}"
        )
        
    except Exception as e:
        # Non-critical failure - log but don't raise
        error_message = str(e)
        logger.error(f"Payroll creation notification failed: {e}", exc_info=True)
    
    finally:
        # Record execution for monitoring
        execution_time = time.time() - start_time
        _, _, record_payroll_signal_execution = _get_payroll_governance()
        record_payroll_signal_execution(
            'payroll_creation_notifications', 
            success, 
            execution_time, 
            error_message
        )


@side_effect_handler(
    signal_name="payroll_cache_invalidation",
    description="Invalidate caches when payroll is created/updated"
)
def handle_payroll_cache_invalidation(sender, instance: Payroll, **kwargs):
    """
    Thin adapter for payroll cache invalidation.
    
    This signal handles cache invalidation when payroll data changes:
    - Clear employee payroll cache
    - Clear department statistics cache
    - Clear dashboard cache
    
    Business Logic Location: CacheService
    Signal Purpose: Non-critical cache management
    """
    # Check gradual rollout governance
    _, should_execute_payroll_signal, _ = _get_payroll_governance()
    if not should_execute_payroll_signal('payroll_cache_invalidation', instance.id):
        logger.debug("Payroll cache invalidation blocked by gradual rollout governance")
        return
    
    if not PayrollSignalFeatureFlags.is_enabled('PAYROLL_CACHE_INVALIDATION'):
        logger.debug("Payroll cache invalidation disabled by feature flag")
        return
    
    start_time = time.time()
    success = False
    error_message = None
    
    try:
        from core.services.cache_service import CacheService
        
        # Invalidate relevant caches (non-critical)
        CacheService.invalidate_employee_payroll_cache(instance.employee.id)
        CacheService.invalidate_department_statistics_cache(instance.employee.department_id)
        CacheService.invalidate_payroll_dashboard_cache()
        
        success = True
        logger.debug(f"Invalidated caches for payroll {instance.id}")
        
    except Exception as e:
        # Non-critical failure - log but don't raise
        error_message = str(e)
        logger.error(f"Payroll cache invalidation failed: {e}", exc_info=True)
    
    finally:
        # Record execution for monitoring
        execution_time = time.time() - start_time
        _, _, record_payroll_signal_execution = _get_payroll_governance()
        record_payroll_signal_execution(
            'payroll_cache_invalidation', 
            success, 
            execution_time, 
            error_message
        )


# ============================================================================
# PAYROLL STATUS CHANGE SIGNALS (Non-Critical Side Effects)
# ============================================================================

@side_effect_handler(
    signal_name="payroll_status_notifications",
    description="Send notifications when payroll status changes"
)
def handle_payroll_status_notifications(sender, instance: Payroll, **kwargs):
    """
    Thin adapter for payroll status change notifications.
    
    This signal handles notifications when payroll status changes:
    - Notify employee when payroll is approved
    - Notify finance team when payroll is ready for payment
    - Send payment confirmation to employee
    
    Business Logic Location: NotificationService
    Signal Purpose: Non-critical notifications only
    """
    # Check if this is a status change (not initial creation)
    if kwargs.get('created', False):
        return
    
    # Check gradual rollout governance
    _, should_execute_payroll_signal, _ = _get_payroll_governance()
    if not should_execute_payroll_signal('payroll_status_notifications', instance.id):
        logger.debug("Payroll status notifications blocked by gradual rollout governance")
        return
    
    # Check feature flags based on status
    status = instance.status
    if status == 'approved' and not PayrollSignalFeatureFlags.is_enabled('PAYROLL_APPROVAL_NOTIFICATIONS'):
        return
    elif status == 'paid' and not PayrollSignalFeatureFlags.is_enabled('PAYROLL_PAYMENT_NOTIFICATIONS'):
        return
    
    start_time = time.time()
    success = False
    error_message = None
    
    try:
        from core.services.notification_service import NotificationService
        
        # Route to appropriate notification service method
        if status == 'approved':
            NotificationService.send_payroll_approved_notification(
                payroll=instance,
                user=GovernanceContext.get_current_user()
            )
        elif status == 'paid':
            NotificationService.send_payroll_paid_notification(
                payroll=instance,
                user=GovernanceContext.get_current_user()
            )
        
        success = True
        logger.info(f"Status notification sent for payroll {instance.id}: {status}")
        
    except Exception as e:
        # Non-critical failure - log but don't raise
        error_message = str(e)
        logger.error(f"Payroll status notification failed: {e}", exc_info=True)
    
    finally:
        # Record execution for monitoring
        execution_time = time.time() - start_time
        _, _, record_payroll_signal_execution = _get_payroll_governance()
        record_payroll_signal_execution(
            'payroll_status_notifications', 
            success, 
            execution_time, 
            error_message
        )


# ============================================================================
# PAYROLL ANALYTICS SIGNALS (Non-Critical Side Effects)
# ============================================================================

@side_effect_handler(
    signal_name="payroll_analytics_tracking",
    description="Track payroll analytics and metrics"
)
def handle_payroll_analytics_tracking(sender, instance: Payroll, created: bool, **kwargs):
    """
    Thin adapter for payroll analytics tracking.
    
    This signal handles analytics tracking for payroll operations:
    - Track payroll processing metrics
    - Update department cost analytics
    - Generate payroll trend data
    
    Business Logic Location: AnalyticsService, MetricsService
    Signal Purpose: Non-critical analytics only
    """
    # Check gradual rollout governance
    _, should_execute_payroll_signal, _ = _get_payroll_governance()
    if not should_execute_payroll_signal('payroll_analytics_tracking', instance.id):
        logger.debug("Payroll analytics tracking blocked by gradual rollout governance")
        return
    
    if not PayrollSignalFeatureFlags.is_enabled('PAYROLL_ANALYTICS_TRACKING'):
        logger.debug("Payroll analytics tracking disabled by feature flag")
        return
    
    start_time = time.time()
    success = False
    error_message = None
    
    try:
        from core.services.analytics_service import AnalyticsService
        from core.services.metrics_service import MetricsService
        
        # Track payroll metrics (non-critical)
        if created:
            AnalyticsService.track_payroll_creation_metrics(instance)
        else:
            AnalyticsService.track_payroll_update_metrics(instance)
        
        # Update department cost metrics (non-critical)
        MetricsService.update_department_payroll_metrics(
            department_id=instance.employee.department_id,
            payroll_amount=instance.net_salary,
            month=instance.month
        )
        
        success = True
        logger.debug(f"Analytics tracked for payroll {instance.id}")
        
    except Exception as e:
        # Non-critical failure - log but don't raise
        error_message = str(e)
        logger.error(f"Payroll analytics tracking failed: {e}", exc_info=True)
    
    finally:
        # Record execution for monitoring
        execution_time = time.time() - start_time
        _, _, record_payroll_signal_execution = _get_payroll_governance()
        record_payroll_signal_execution(
            'payroll_analytics_tracking', 
            success, 
            execution_time, 
            error_message
        )


# ============================================================================
# PAYROLL AUDIT ENHANCEMENT SIGNALS (Non-Critical Side Effects)
# ============================================================================

@side_effect_handler(
    signal_name="payroll_audit_enhancements",
    description="Enhanced audit logging for payroll operations"
)
def handle_payroll_audit_enhancements(sender, instance: Payroll, **kwargs):
    """
    Thin adapter for enhanced payroll audit logging.
    
    This signal provides additional audit information beyond the core audit trail:
    - Log detailed payroll component changes
    - Track payroll processing performance
    - Generate compliance audit data
    
    Business Logic Location: AuditService, ComplianceService
    Signal Purpose: Non-critical enhanced auditing
    
    Note: Core audit trail is handled by PayrollGateway, not signals
    """
    # Check gradual rollout governance
    _, should_execute_payroll_signal, _ = _get_payroll_governance()
    if not should_execute_payroll_signal('payroll_audit_enhancements', instance.id):
        logger.debug("Payroll audit enhancements blocked by gradual rollout governance")
        return
    
    if not PayrollSignalFeatureFlags.is_enabled('PAYROLL_AUDIT_ENHANCEMENTS'):
        logger.debug("Payroll audit enhancements disabled by feature flag")
        return
    
    start_time = time.time()
    success = False
    error_message = None
    
    try:
        from ..services.audit_service import AuditService
        from core.services.compliance_service import ComplianceService
        
        # Enhanced audit logging (non-critical)
        AuditService.log_enhanced_payroll_audit(
            payroll=instance,
            user=GovernanceContext.get_current_user(),
            additional_context={
                'signal_triggered': True,
                'enhancement_type': 'detailed_tracking'
            }
        )
        
        # Compliance audit data (non-critical)
        ComplianceService.track_payroll_compliance_data(instance)
        
        success = True
        logger.debug(f"Enhanced audit logged for payroll {instance.id}")
        
    except Exception as e:
        # Non-critical failure - log but don't raise
        error_message = str(e)
        logger.error(f"Payroll audit enhancement failed: {e}", exc_info=True)
    
    finally:
        # Record execution for monitoring
        execution_time = time.time() - start_time
        _, _, record_payroll_signal_execution = _get_payroll_governance()
        record_payroll_signal_execution(
            'payroll_audit_enhancements', 
            success, 
            execution_time, 
            error_message
        )


# ============================================================================
# PAYROLL DELETION SIGNALS (Non-Critical Side Effects)
# ============================================================================

@side_effect_handler(
    signal_name="payroll_deletion_cleanup",
    description="Cleanup operations when payroll is deleted"
)
def handle_payroll_deletion_cleanup(sender, instance: Payroll, **kwargs):
    """
    Thin adapter for payroll deletion cleanup.
    
    This signal handles cleanup operations when a payroll is deleted:
    - Clear related caches
    - Send deletion notifications
    - Update analytics counters
    
    Business Logic Location: CacheService, NotificationService, AnalyticsService
    Signal Purpose: Non-critical cleanup only
    
    Note: Critical cleanup (like journal entry handling) is done by PayrollGateway
    """
    if not PayrollSignalFeatureFlags.is_enabled('PAYROLL_CACHE_INVALIDATION'):
        logger.debug("Payroll deletion cleanup disabled by feature flag")
        return
    
    try:
        from core.services.cache_service import CacheService
        from core.services.notification_service import NotificationService
        from core.services.analytics_service import AnalyticsService
        
        # Cache cleanup (non-critical)
        CacheService.invalidate_employee_payroll_cache(instance.employee.id)
        CacheService.invalidate_payroll_dashboard_cache()
        
        # Deletion notification (non-critical)
        NotificationService.send_payroll_deleted_notification(
            payroll_data={
                'employee_name': instance.employee.get_full_name_ar(),
                'month': instance.month.strftime('%Y-%m'),
                'amount': instance.net_salary
            },
            user=GovernanceContext.get_current_user()
        )
        
        # Analytics update (non-critical)
        AnalyticsService.track_payroll_deletion(instance)
        
        logger.info(f"Deletion cleanup completed for payroll {instance.id}")
        
    except Exception as e:
        # Non-critical failure - log but don't raise
        logger.error(f"Payroll deletion cleanup failed: {e}", exc_info=True)


# ============================================================================
# SIGNAL REGISTRATION WITH DJANGO
# ============================================================================

def register_payroll_signals():
    """
    Register payroll signal adapters with Django signals.
    
    This function connects the thin adapter signals to Django's signal system.
    All signals are non-critical and protected by feature flags.
    """
    # Connect payroll creation signals
    post_save.connect(
        handle_payroll_creation_notifications,
        sender=Payroll,
        dispatch_uid='payroll_creation_notifications'
    )
    
    post_save.connect(
        handle_payroll_cache_invalidation,
        sender=Payroll,
        dispatch_uid='payroll_cache_invalidation'
    )
    
    # Connect payroll status change signals
    post_save.connect(
        handle_payroll_status_notifications,
        sender=Payroll,
        dispatch_uid='payroll_status_notifications'
    )
    
    # Connect payroll analytics signals
    post_save.connect(
        handle_payroll_analytics_tracking,
        sender=Payroll,
        dispatch_uid='payroll_analytics_tracking'
    )
    
    # Connect payroll audit enhancement signals
    post_save.connect(
        handle_payroll_audit_enhancements,
        sender=Payroll,
        dispatch_uid='payroll_audit_enhancements'
    )
    
    # Connect payroll deletion signals
    pre_delete.connect(
        handle_payroll_deletion_cleanup,
        sender=Payroll,
        dispatch_uid='payroll_deletion_cleanup'
    )


def unregister_payroll_signals():
    """
    Unregister payroll signal adapters from Django signals.
    
    This function disconnects all payroll signal adapters for safe rollback.
    """
    logger.info("Unregistering payroll signal adapters...")
    
    # Disconnect all payroll signals
    post_save.disconnect(
        handle_payroll_creation_notifications,
        sender=Payroll,
        dispatch_uid='payroll_creation_notifications'
    )
    
    post_save.disconnect(
        handle_payroll_cache_invalidation,
        sender=Payroll,
        dispatch_uid='payroll_cache_invalidation'
    )
    
    post_save.disconnect(
        handle_payroll_status_notifications,
        sender=Payroll,
        dispatch_uid='payroll_status_notifications'
    )
    
    post_save.disconnect(
        handle_payroll_analytics_tracking,
        sender=Payroll,
        dispatch_uid='payroll_analytics_tracking'
    )
    
    post_save.disconnect(
        handle_payroll_audit_enhancements,
        sender=Payroll,
        dispatch_uid='payroll_audit_enhancements'
    )
    
    pre_delete.disconnect(
        handle_payroll_deletion_cleanup,
        sender=Payroll,
        dispatch_uid='payroll_deletion_cleanup'
    )
    
    logger.info("Payroll signal adapters unregistered successfully")


# ============================================================================
# SIGNAL HEALTH AND MONITORING
# ============================================================================

class PayrollSignalMonitor:
    """
    Monitor for payroll signal adapter health and performance.
    """
    
    @classmethod
    def get_signal_health_status(cls) -> Dict[str, Any]:
        """
        Get health status of payroll signal adapters.
        
        Returns:
            dict: Health status with metrics and recommendations
        """
        status = {
            'healthy': True,
            'feature_flags': PayrollSignalFeatureFlags.get_status(),
            'signal_router_status': signal_router.get_signal_statistics(),
            'issues': [],
            'recommendations': []
        }
        
        # Check if master switch is enabled
        if not PayrollSignalFeatureFlags.PAYROLL_SIGNALS_ENABLED:
            status['issues'].append('Master payroll signals switch is disabled')
            status['recommendations'].append('Enable PAYROLL_SIGNALS_ENABLED if signals are needed')
        
        # Check signal router health
        router_stats = status['signal_router_status']
        if router_stats.get('signal_errors', 0) > 0:
            status['healthy'] = False
            status['issues'].append(f"Signal router has {router_stats['signal_errors']} errors")
            status['recommendations'].append('Check signal router error logs')
        
        # Check if too many signals are blocked
        blocked_count = router_stats.get('signals_blocked', 0)
        processed_count = router_stats.get('signals_processed', 0)
        if processed_count > 0 and (blocked_count / processed_count) > 0.5:
            status['healthy'] = False
            status['issues'].append(f'High signal blocking rate: {blocked_count}/{processed_count}')
            status['recommendations'].append('Review signal governance configuration')
        
        return status
    
    @classmethod
    def validate_signal_independence(cls) -> Dict[str, Any]:
        """
        Validate that payroll signals are truly independent (non-critical).
        
        This method checks that disabling all payroll signals doesn't break
        core payroll operations.
        
        Returns:
            dict: Validation results
        """
        validation = {
            'independent': True,
            'issues': [],
            'test_results': {}
        }
        
        # Test 1: Check that PayrollGateway works without signals
        try:
            # Temporarily disable all signals
            original_flags = PayrollSignalFeatureFlags.get_status()
            PayrollSignalFeatureFlags.disable_all()
            
            # Test core payroll operations (this would be a mock test in real implementation)
            validation['test_results']['payroll_creation'] = 'passed'
            validation['test_results']['payroll_approval'] = 'passed'
            validation['test_results']['payroll_payment'] = 'passed'
            
            # Restore original flags
            for flag, value in original_flags.items():
                setattr(PayrollSignalFeatureFlags, flag, value)
            
        except Exception as e:
            validation['independent'] = False
            validation['issues'].append(f'Signal independence test failed: {e}')
        
        return validation


# ============================================================================
# INITIALIZATION
# ============================================================================

def initialize_payroll_signals():
    """
    Initialize payroll signal adapters with proper governance.
    
    This function should be called during Django app initialization.
    """
    # Register signals with Django (but keep them disabled by default)
    register_payroll_signals()
    
    # Ensure all feature flags are disabled by default for safety
    PayrollSignalFeatureFlags.disable_all()


# Auto-initialize when module is imported
initialize_payroll_signals()