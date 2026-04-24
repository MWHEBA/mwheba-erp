# -*- coding: utf-8 -*-
"""
Signal Governance Decorator

Provides unified governance decorator for Django signal handlers.
Handles audit logging, error handling, performance monitoring, and quarantine.
"""

import logging
import time
import functools
from typing import Callable
from django.db import transaction
from django.utils import timezone

from .audit_service import AuditService
from .quarantine_service import QuarantineService
from ..models import GovernanceContext
from ..exceptions import SignalError

logger = logging.getLogger('governance.signals')


def governed_signal_handler(
    signal_name: str,
    critical: bool = False,
    description: str = "",
    max_execution_time: float = 5.0,
    retry_count: int = 0
):
    """
    Unified governance decorator for Django signal handlers.
    
    Features:
    - Automatic audit logging
    - Error handling and quarantine
    - Performance monitoring
    - Prevents signal failures from breaking main operations
    
    Args:
        signal_name: Unique name for this signal handler
        critical: Whether this is a critical signal (affects error handling)
        description: Human-readable description of the signal
        max_execution_time: Maximum allowed execution time in seconds
        retry_count: Number of retries for transient failures
    
    Usage:
        @governed_signal_handler(
            signal_name="customer_payment_creation",
            critical=True,
            description="Create automatic payment record for new customer"
        )
        @receiver(post_save, sender=Customer)
        def create_payment_for_customer(sender, instance, created, **kwargs):
            if not created:
                return
            # Signal logic here
    
    Important Notes:
    - Always use transaction.on_commit() for heavy operations
    - Signal failures won't break the main operation (unless critical=True)
    - All signals are automatically audited
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(sender, instance, **kwargs):
            # Get user from context
            user = GovernanceContext.get_current_user()
            
            # Performance tracking
            start_time = time.time()
            
            # Extract signal context
            created = kwargs.get('created', False)
            signal_type = 'post_save' if 'created' in kwargs else 'unknown'
            model_name = f"{sender._meta.app_label}.{sender._meta.model_name}"
            object_id = getattr(instance, 'pk', None)
            
            try:
                # Execute signal handler
                result = func(sender, instance, **kwargs)
                
                # Check execution time
                execution_time = time.time() - start_time
                if execution_time > max_execution_time:
                    logger.warning(
                        f"Signal handler exceeded max execution time: "
                        f"{signal_name} took {execution_time:.2f}s "
                        f"(max: {max_execution_time}s)"
                    )
                
                # Audit logging
                AuditService.log_signal_operation(
                    signal_name=signal_name,
                    sender_model=model_name,
                    sender_id=object_id,
                    operation=f"{signal_type}_{func.__name__}",
                    user=user,
                    success=True,
                    execution_time=execution_time,
                    description=description,
                    created=created
                )
                
                logger.debug(
                    f"Signal handler completed: {signal_name} "
                    f"for {model_name}:{object_id} in {execution_time:.2f}s"
                )
                
                return result
                
            except Exception as e:
                execution_time = time.time() - start_time
                
                # Log error
                logger.error(
                    f"Signal handler failed: {signal_name} - {str(e)}",
                    exc_info=True,
                    extra={
                        'signal_name': signal_name,
                        'model': model_name,
                        'object_id': object_id,
                        'execution_time': execution_time
                    }
                )
                
                # Audit logging for failure
                AuditService.log_signal_operation(
                    signal_name=signal_name,
                    sender_model=model_name,
                    sender_id=object_id,
                    operation=f"{signal_type}_{func.__name__}_failed",
                    user=user,
                    success=False,
                    error=str(e),
                    execution_time=execution_time,
                    description=description,
                    created=created
                )
                
                # Quarantine if critical
                if critical:
                    try:
                        QuarantineService.quarantine_data(
                            model_name=model_name,
                            object_id=object_id,
                            corruption_type='signal_failure',
                            details={
                                'signal_name': signal_name,
                                'signal_type': signal_type,
                                'error': str(e),
                                'execution_time': execution_time,
                                'description': description
                            },
                            user=user
                        )
                    except Exception as quarantine_error:
                        logger.error(
                            f"Failed to quarantine failed signal: {quarantine_error}"
                        )
                
                # Re-raise if critical, otherwise log and continue
                if critical:
                    raise SignalError(
                        signal_name=signal_name,
                        context={
                            'model': model_name,
                            'object_id': object_id,
                            'error': str(e)
                        }
                    )
                else:
                    # Non-critical signals don't break the main operation
                    logger.info(
                        f"Non-critical signal failed but operation continues: {signal_name}"
                    )
                    return None
        
        return wrapper
    return decorator


class SignalErrorHandler:
    """
    Unified error handler for signal operations.
    Provides consistent error handling and reporting across all signals.
    """
    
    @staticmethod
    def handle_signal_error(signal_name: str, instance, error: Exception, critical: bool = True):
        """
        Handle signal error with proper logging and quarantine.
        
        Args:
            signal_name: Name of the signal
            instance: Model instance that triggered the signal
            error: Exception that occurred
            critical: Whether this is a critical error
        """
        model_name = f"{instance._meta.app_label}.{instance._meta.model_name}"
        object_id = getattr(instance, 'pk', None)
        user = GovernanceContext.get_current_user()
        
        error_data = {
            'signal_name': signal_name,
            'model': model_name,
            'instance_id': object_id,
            'error': str(error),
            'error_type': type(error).__name__
        }
        
        # Log error
        logger.error(
            f"Signal error: {signal_name} - {error}",
            extra=error_data
        )
        
        # Audit log
        AuditService.log_signal_operation(
            signal_name=signal_name,
            sender_model=model_name,
            sender_id=object_id,
            operation='signal_error',
            user=user,
            success=False,
            error=str(error)
        )
        
        # Quarantine if critical
        if critical:
            try:
                QuarantineService.quarantine_data(
                    model_name=model_name,
                    object_id=object_id,
                    corruption_type='signal_error',
                    details=error_data,
                    user=user
                )
            except Exception as quarantine_error:
                logger.error(f"Failed to quarantine signal error: {quarantine_error}")


class SignalPerformanceMonitor:
    """
    Monitor signal performance and detect slow signals.
    """
    
    @staticmethod
    def monitor_signal_performance(signal_name: str):
        """
        Decorator to monitor signal performance.
        
        Usage:
            @SignalPerformanceMonitor.monitor_signal_performance('my_signal')
            @governed_signal_handler('my_signal', critical=True)
            @receiver(post_save, sender=MyModel)
            def my_signal_handler(sender, instance, **kwargs):
                pass
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()
                
                try:
                    result = func(*args, **kwargs)
                    execution_time = time.time() - start_time
                    
                    # Record performance metric
                    SignalPerformanceMonitor._record_performance(
                        signal_name, execution_time, success=True
                    )
                    
                    # Warn if slow
                    if execution_time > 2.0:
                        logger.warning(
                            f"Slow signal detected: {signal_name} "
                            f"took {execution_time:.2f}s"
                        )
                    
                    return result
                    
                except Exception as e:
                    execution_time = time.time() - start_time
                    SignalPerformanceMonitor._record_performance(
                        signal_name, execution_time, success=False
                    )
                    raise
            
            return wrapper
        return decorator
    
    @staticmethod
    def _record_performance(signal_name: str, execution_time: float, success: bool):
        """
        Record signal performance metrics.
        
        Args:
            signal_name: Name of the signal
            execution_time: Execution time in seconds
            success: Whether the signal succeeded
        """
        from django.core.cache import cache
        
        cache_key = f'signal_performance_{signal_name}'
        stats = cache.get(cache_key, {
            'count': 0,
            'total_time': 0,
            'failures': 0,
            'max_time': 0,
            'min_time': float('inf')
        })
        
        stats['count'] += 1
        stats['total_time'] += execution_time
        stats['max_time'] = max(stats['max_time'], execution_time)
        stats['min_time'] = min(stats['min_time'], execution_time)
        
        if not success:
            stats['failures'] += 1
        
        cache.set(cache_key, stats, 3600)  # 1 hour
    
    @staticmethod
    def get_signal_statistics(signal_name: str) -> dict:
        """
        Get performance statistics for a signal.
        
        Args:
            signal_name: Name of the signal
        
        Returns:
            dict: Performance statistics
        """
        from django.core.cache import cache
        
        cache_key = f'signal_performance_{signal_name}'
        stats = cache.get(cache_key)
        
        if not stats:
            return {'error': 'No statistics available'}
        
        avg_time = stats['total_time'] / stats['count'] if stats['count'] > 0 else 0
        failure_rate = (stats['failures'] / stats['count'] * 100) if stats['count'] > 0 else 0
        
        return {
            'signal_name': signal_name,
            'total_executions': stats['count'],
            'total_failures': stats['failures'],
            'failure_rate': f"{failure_rate:.1f}%",
            'avg_execution_time': f"{avg_time:.3f}s",
            'max_execution_time': f"{stats['max_time']:.3f}s",
            'min_execution_time': f"{stats['min_time']:.3f}s"
        }
