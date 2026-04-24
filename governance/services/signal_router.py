"""
SignalRouter with governance controls for systemic signal management.
Provides thread-safe signal routing with kill switches and depth limiting.
"""

import threading
import logging
from contextlib import contextmanager
from typing import Dict, List, Optional, Callable, Any
from django.db import transaction
from django.utils import timezone
from django.conf import settings

from ..models import GovernanceContext, AuditTrail
from ..exceptions import SignalError, ConfigurationError
from ..thread_safety import monitor_operation, ThreadSafeCounter
from .audit_service import AuditService

logger = logging.getLogger(__name__)


class SignalRouter:
    """
    Thread-safe signal router with governance controls.
    
    Key Features:
    - Global and per-signal kill switches
    - Signal depth limiting to prevent infinite recursion
    - Thread-safe call stack management
    - Comprehensive audit logging
    - Feature flags for maintenance mode
    - Signal independence (failures don't break writes)
    """
    
    # Default configuration
    DEFAULT_DEPTH_LIMIT = 5
    DEFAULT_TIMEOUT = 30  # seconds
    
    def __init__(self, depth_limit: int = None, enable_audit: bool = True):
        """
        Initialize SignalRouter with governance controls.
        
        Args:
            depth_limit: Maximum signal chain depth (default: 5)
            enable_audit: Whether to enable audit logging (default: True)
        """
        self.depth_limit = depth_limit or self.DEFAULT_DEPTH_LIMIT
        self.enable_audit = enable_audit
        
        # Global kill switch
        self._global_enabled = True
        self._global_lock = threading.RLock()
        
        # Per-signal kill switches
        self._signal_switches: Dict[str, bool] = {}
        self._switches_lock = threading.RLock()
        
        # Thread-local storage for call stacks
        self._local = threading.local()
        
        # Signal handlers registry
        self._handlers: Dict[str, List[Callable]] = {}
        self._handlers_lock = threading.RLock()
        
        # Monitoring counters
        self._signal_counter = ThreadSafeCounter()
        self._blocked_counter = ThreadSafeCounter()
        self._error_counter = ThreadSafeCounter()
        
        # Feature flags
        self._maintenance_mode = False
        self._maintenance_lock = threading.RLock()
    
    @property
    def call_stack(self) -> List[str]:
        """Thread-safe access to current call stack"""
        if not hasattr(self._local, 'call_stack'):
            self._local.call_stack = []
        return self._local.call_stack
    
    @property
    def global_enabled(self) -> bool:
        """Check if global kill switch is enabled"""
        with self._global_lock:
            return self._global_enabled
    
    @property
    def maintenance_mode(self) -> bool:
        """Check if maintenance mode is active"""
        with self._maintenance_lock:
            return self._maintenance_mode
    
    def enable_global_signals(self) -> None:
        """Enable global signal processing"""
        with self._global_lock:
            self._global_enabled = True
            logger.info("Global signal processing enabled")
            
            if self.enable_audit:
                AuditService.log_operation(
                    model_name='SignalRouter',
                    object_id=0,
                    operation='ENABLE_GLOBAL',
                    source_service='SignalRouter',
                    user=GovernanceContext.get_current_user()
                )
    
    def disable_global_signals(self, reason: str = "Manual disable") -> None:
        """
        Disable all signal processing globally.
        This is a kill switch that prevents all signals from executing.
        """
        with self._global_lock:
            self._global_enabled = False
            logger.warning(f"Global signal processing disabled: {reason}")
            
            if self.enable_audit:
                AuditService.log_operation(
                    model_name='SignalRouter',
                    object_id=0,
                    operation='DISABLE_GLOBAL',
                    source_service='SignalRouter',
                    user=GovernanceContext.get_current_user(),
                    disable_reason=reason
                )
    
    def enable_signal(self, signal_name: str) -> None:
        """Enable specific signal"""
        with self._switches_lock:
            self._signal_switches[signal_name] = True
            logger.info(f"Signal '{signal_name}' enabled")
            
            if self.enable_audit:
                AuditService.log_operation(
                    model_name='SignalRouter',
                    object_id=0,
                    operation='ENABLE_SIGNAL',
                    source_service='SignalRouter',
                    user=GovernanceContext.get_current_user(),
                    signal_name=signal_name
                )
    
    def disable_signal(self, signal_name: str, reason: str = "Manual disable") -> None:
        """Disable specific signal"""
        with self._switches_lock:
            self._signal_switches[signal_name] = False
            logger.warning(f"Signal '{signal_name}' disabled: {reason}")
            
            if self.enable_audit:
                AuditService.log_operation(
                    model_name='SignalRouter',
                    object_id=0,
                    operation='DISABLE_SIGNAL',
                    source_service='SignalRouter',
                    user=GovernanceContext.get_current_user(),
                    signal_name=signal_name,
                    disable_reason=reason
                )
    
    def is_signal_enabled(self, signal_name: str) -> bool:
        """Check if specific signal is enabled"""
        with self._switches_lock:
            return self._signal_switches.get(signal_name, True)
    
    def enter_maintenance_mode(self, reason: str = "Maintenance") -> None:
        """
        Enter maintenance mode - disables all non-critical signals.
        Critical signals (those marked as required) may still execute.
        """
        with self._maintenance_lock:
            self._maintenance_mode = True
            logger.warning(f"Entered maintenance mode: {reason}")
            
            if self.enable_audit:
                AuditService.log_operation(
                    model_name='SignalRouter',
                    object_id=0,
                    operation='ENTER_MAINTENANCE',
                    source_service='SignalRouter',
                    user=GovernanceContext.get_current_user(),
                    maintenance_reason=reason
                )
    
    def exit_maintenance_mode(self) -> None:
        """Exit maintenance mode"""
        with self._maintenance_lock:
            self._maintenance_mode = False
            logger.info("Exited maintenance mode")
            
            if self.enable_audit:
                AuditService.log_operation(
                    model_name='SignalRouter',
                    object_id=0,
                    operation='EXIT_MAINTENANCE',
                    source_service='SignalRouter',
                    user=GovernanceContext.get_current_user()
                )
    
    def register_handler(self, signal_name: str, handler: Callable, 
                        critical: bool = False, description: str = "") -> None:
        """
        Register a signal handler.
        
        Args:
            signal_name: Name of the signal
            handler: Handler function
            critical: Whether this handler is critical (executes even in maintenance mode)
            description: Description of what the handler does
        """
        with self._handlers_lock:
            if signal_name not in self._handlers:
                self._handlers[signal_name] = []
            
            handler_info = {
                'handler': handler,
                'critical': critical,
                'description': description,
                'registered_at': timezone.now()
            }
            
            self._handlers[signal_name].append(handler_info)
    
    def unregister_handler(self, signal_name: str, handler: Callable) -> bool:
        """
        Unregister a signal handler.
        
        Returns:
            bool: True if handler was found and removed
        """
        with self._handlers_lock:
            if signal_name in self._handlers:
                original_count = len(self._handlers[signal_name])
                self._handlers[signal_name] = [
                    h for h in self._handlers[signal_name] 
                    if h['handler'] != handler
                ]
                removed = len(self._handlers[signal_name]) < original_count
                if removed:
                    logger.info(f"Unregistered handler for '{signal_name}'")
                return removed
            return False
    
    def route_signal(self, signal_name: str, sender, instance=None, 
                    critical: bool = False, **kwargs) -> Dict[str, Any]:
        """
        Route signal through governance controls.
        
        Args:
            signal_name: Name of the signal being routed
            sender: Signal sender (model class)
            instance: Model instance if applicable
            critical: Whether this signal is critical (required for data integrity)
            **kwargs: Additional signal arguments
            
        Returns:
            dict: Routing result with success status and details
        """
        routing_result = {
            'signal_name': signal_name,
            'success': False,
            'blocked': False,
            'error': None,
            'handlers_executed': 0,
            'handlers_failed': 0,
            'call_stack_depth': len(self.call_stack)
        }
        
        # Increment signal counter
        self._signal_counter.increment()
        
        try:
            with monitor_operation(f"signal_routing_{signal_name}"):
                # Check governance controls
                block_reason = self._check_governance_controls(signal_name, critical)
                if block_reason:
                    routing_result['blocked'] = True
                    routing_result['block_reason'] = block_reason
                    self._blocked_counter.increment()
                    
                    logger.info(f"Signal '{signal_name}' blocked: {block_reason}")
                    
                    if self.enable_audit:
                        AuditService.log_signal_operation(
                            signal_name=signal_name,
                            sender_model=sender.__name__ if hasattr(sender, '__name__') else str(sender),
                            sender_id=getattr(instance, 'id', 0) if instance else 0,
                            operation='BLOCKED',
                            user=GovernanceContext.get_current_user(),
                            block_reason=block_reason,
                            critical=critical
                        )
                    
                    # For non-critical signals, blocking is success (fail-safe)
                    routing_result['success'] = not critical
                    return routing_result
                
                # Execute signal with monitoring
                routing_result.update(
                    self._execute_signal_handlers(signal_name, sender, instance, **kwargs)
                )
                
                if self.enable_audit and routing_result['handlers_executed'] > 0:
                    AuditService.log_signal_operation(
                        signal_name=signal_name,
                        sender_model=sender.__name__ if hasattr(sender, '__name__') else str(sender),
                        sender_id=getattr(instance, 'id', 0) if instance else 0,
                        operation='EXECUTED',
                        user=GovernanceContext.get_current_user(),
                        handlers_executed=routing_result['handlers_executed'],
                        handlers_failed=routing_result['handlers_failed'],
                        critical=critical
                    )
                
                routing_result['success'] = True
                return routing_result
                
        except Exception as e:
            self._error_counter.increment()
            routing_result['error'] = str(e)
            
            logger.error(f"Signal routing failed for '{signal_name}': {e}", exc_info=True)
            
            if self.enable_audit:
                AuditService.log_signal_operation(
                    signal_name=signal_name,
                    sender_model=sender.__name__ if hasattr(sender, '__name__') else str(sender),
                    sender_id=getattr(instance, 'id', 0) if instance else 0,
                    operation='ERROR',
                    user=GovernanceContext.get_current_user(),
                    error=str(e),
                    critical=critical
                )
            
            # For critical signals, propagate the error
            if critical:
                raise SignalError(signal_name, f"Critical signal failed: {e}")
            
            # For non-critical signals, log and continue (fail-safe)
            routing_result['success'] = True  # Success means "didn't break the main operation"
            return routing_result
    
    def _check_governance_controls(self, signal_name: str, critical: bool) -> Optional[str]:
        """
        Check all governance controls to determine if signal should be blocked.
        
        Returns:
            str: Block reason if signal should be blocked, None if allowed
        """
        # Check global kill switch
        if not self.global_enabled:
            return "global_kill_switch_active"
        
        # Check per-signal kill switch
        if not self.is_signal_enabled(signal_name):
            return "signal_disabled"
        
        # Check maintenance mode (only blocks non-critical signals)
        if self.maintenance_mode and not critical:
            return "maintenance_mode_active"
        
        # Check call stack depth
        if len(self.call_stack) >= self.depth_limit:
            return f"depth_limit_exceeded_{len(self.call_stack)}_of_{self.depth_limit}"
        
        # Check for circular signal chains
        if signal_name in self.call_stack:
            return f"circular_signal_chain_detected"
        
        return None
    
    def _execute_signal_handlers(self, signal_name: str, sender, instance, **kwargs) -> Dict[str, Any]:
        """
        Execute registered handlers for the signal.
        
        Returns:
            dict: Execution results
        """
        result = {
            'handlers_executed': 0,
            'handlers_failed': 0,
            'handler_results': []
        }
        
        # Add signal to call stack
        self.call_stack.append(signal_name)
        
        try:
            with self._handlers_lock:
                handlers = self._handlers.get(signal_name, [])
            
            for handler_info in handlers:
                handler = handler_info['handler']
                critical = handler_info['critical']
                description = handler_info['description']
                
                try:
                    # Check if handler should run in maintenance mode
                    if self.maintenance_mode and not critical:
                        logger.debug(f"Skipping non-critical handler in maintenance mode: {description}")
                        continue
                    
                    # Execute handler
                    logger.debug(f"Executing signal handler: {description}")
                    handler_result = handler(sender=sender, instance=instance, **kwargs)
                    
                    result['handlers_executed'] += 1
                    result['handler_results'].append({
                        'handler': description,
                        'success': True,
                        'result': handler_result
                    })
                    
                except Exception as e:
                    result['handlers_failed'] += 1
                    result['handler_results'].append({
                        'handler': description,
                        'success': False,
                        'error': str(e)
                    })
                    
                    logger.error(f"Signal handler failed ({description}): {e}", exc_info=True)
                    
                    # For critical handlers, we might want to propagate the error
                    if critical:
                        logger.error(f"Critical signal handler failed: {description}")
                        # Note: We don't raise here to allow other handlers to run
                        # The calling code can check handler_results for critical failures
            
            return result
            
        finally:
            # Always remove signal from call stack
            if self.call_stack and self.call_stack[-1] == signal_name:
                self.call_stack.pop()
    
    @contextmanager
    def signal_context(self, signal_name: str, critical: bool = False):
        """
        Context manager for signal execution with proper cleanup.
        
        Args:
            signal_name: Name of the signal
            critical: Whether the signal is critical
        """
        # Check governance controls before entering context
        block_reason = self._check_governance_controls(signal_name, critical)
        if block_reason:
            if critical:
                raise SignalError(signal_name, f"Critical signal blocked: {block_reason}")
            else:
                logger.info(f"Non-critical signal '{signal_name}' blocked: {block_reason}")
                yield False  # Indicate signal was blocked
                return
        
        # Add to call stack
        self.call_stack.append(signal_name)
        
        try:
            yield True  # Indicate signal can proceed
        finally:
            # Always clean up call stack
            if self.call_stack and self.call_stack[-1] == signal_name:
                self.call_stack.pop()
    
    def get_signal_statistics(self) -> Dict[str, Any]:
        """Get comprehensive signal routing statistics"""
        with self._switches_lock:
            disabled_signals = [
                name for name, enabled in self._signal_switches.items() 
                if not enabled
            ]
        
        with self._handlers_lock:
            handler_counts = {
                signal: len(handlers) 
                for signal, handlers in self._handlers.items()
            }
        
        return {
            'global_enabled': self.global_enabled,
            'maintenance_mode': self.maintenance_mode,
            'depth_limit': self.depth_limit,
            'current_call_stack_depth': len(self.call_stack),
            'current_call_stack': self.call_stack.copy(),
            'disabled_signals': disabled_signals,
            'registered_handlers': handler_counts,
            'counters': {
                'signals_processed': self._signal_counter.get_value(),
                'signals_blocked': self._blocked_counter.get_value(),
                'signal_errors': self._error_counter.get_value()
            }
        }
    
    def reset_statistics(self) -> None:
        """Reset all monitoring counters"""
        self._signal_counter.reset()
        self._blocked_counter.reset()
        self._error_counter.reset()
        logger.info("Signal router statistics reset")
    
    def validate_configuration(self) -> List[str]:
        """
        Validate signal router configuration.
        
        Returns:
            List[str]: List of configuration errors (empty if valid)
        """
        errors = []
        
        if self.depth_limit < 1:
            errors.append(f"Invalid depth_limit: {self.depth_limit} (must be >= 1)")
        
        if self.depth_limit > 20:
            errors.append(f"Excessive depth_limit: {self.depth_limit} (recommended <= 20)")
        
        # Check for potential configuration issues
        with self._handlers_lock:
            for signal_name, handlers in self._handlers.items():
                if len(handlers) > 10:
                    errors.append(f"Signal '{signal_name}' has {len(handlers)} handlers (consider reducing)")
                
                critical_count = sum(1 for h in handlers if h['critical'])
                if critical_count > 3:
                    errors.append(f"Signal '{signal_name}' has {critical_count} critical handlers (consider reducing)")
        
        return errors


# Global signal router instance
signal_router = SignalRouter()


# Convenience functions for common operations

def route_signal(signal_name: str, sender, instance=None, critical: bool = False, **kwargs):
    """
    Route a signal through the global signal router.
    
    This is the main entry point for signal routing in the application.
    """
    return signal_router.route_signal(signal_name, sender, instance, critical, **kwargs)


def disable_all_signals(reason: str = "Emergency disable"):
    """Emergency function to disable all signals"""
    signal_router.disable_global_signals(reason)


def enable_all_signals():
    """Re-enable all signals after emergency disable"""
    signal_router.enable_global_signals()


@contextmanager
def signals_disabled(reason: str = "Temporary disable"):
    """Context manager to temporarily disable all signals"""
    was_enabled = signal_router.global_enabled
    
    if was_enabled:
        signal_router.disable_global_signals(reason)
    
    try:
        yield
    finally:
        if was_enabled:
            signal_router.enable_global_signals()


@contextmanager
def maintenance_mode(reason: str = "Maintenance"):
    """Context manager for maintenance mode"""
    was_maintenance = signal_router.maintenance_mode
    
    if not was_maintenance:
        signal_router.enter_maintenance_mode(reason)
    
    try:
        yield
    finally:
        if not was_maintenance:
            signal_router.exit_maintenance_mode()


def register_signal_handler(signal_name: str, handler: Callable, 
                          critical: bool = False, description: str = ""):
    """Register a signal handler with the global router"""
    signal_router.register_handler(signal_name, handler, critical, description)


def get_signal_statistics():
    """Get signal routing statistics"""
    return signal_router.get_signal_statistics()