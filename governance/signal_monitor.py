"""
Signal Monitoring Decorator
ديكوريتور لمراقبة أداء الإشارات تلقائياً
"""
import time
import traceback
import logging
from functools import wraps
from django.utils import timezone

logger = logging.getLogger(__name__)


def monitor_signal(signal_name=None, module_name=None, model_name=None, 
                  signal_type='custom', priority='MEDIUM', is_critical=False,
                  description='', max_execution_time_ms=1000):
    """
    ديكوريتور لمراقبة تنفيذ الإشارات
    
    Usage:
        @monitor_signal(
            signal_name='customer_account_creation',
            module_name='client',
            model_name='Customer',
            signal_type='post_save',
            priority='CRITICAL',
            is_critical=True
        )
        @receiver(post_save, sender=Customer)
        def create_customer_account(sender, instance, created, **kwargs):
            ...
    """
    def decorator(func):
        # Get signal name from function if not provided
        _signal_name = signal_name or func.__name__
        _module_name = module_name or func.__module__.split('.')[0]
        _model_name = model_name or 'Unknown'
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            status = 'SUCCESS'
            error_message = ''
            error_trace = ''
            instance_id = None
            user = None
            
            try:
                # Try to extract instance and user from kwargs
                instance = kwargs.get('instance')
                if instance and hasattr(instance, 'pk'):
                    instance_id = instance.pk
                
                # Try to get user from instance or kwargs
                if instance and hasattr(instance, 'created_by'):
                    user = instance.created_by
                elif instance and hasattr(instance, 'user'):
                    user = instance.user
                
                # Execute the signal handler
                result = func(*args, **kwargs)
                
                return result
                
            except Exception as e:
                status = 'FAILED'
                error_message = str(e)
                error_trace = traceback.format_exc()
                logger.error(f"Signal {_signal_name} failed: {e}\n{error_trace}")
                
                # Re-raise the exception to maintain signal behavior
                raise
                
            finally:
                # Calculate execution time
                execution_time_ms = int((time.time() - start_time) * 1000)
                
                # Log execution asynchronously to avoid blocking
                try:
                    from governance.models import SignalRegistry, SignalExecution
                    
                    # Register signal if not exists
                    signal_registry, created = SignalRegistry.objects.get_or_create(
                        signal_name=_signal_name,
                        defaults={
                            'signal_type': signal_type,
                            'module_name': _module_name,
                            'model_name': _model_name,
                            'priority': priority,
                            'is_critical': is_critical,
                            'description': description,
                            'handler_function': f"{func.__module__}.{func.__name__}",
                            'max_execution_time_ms': max_execution_time_ms,
                        }
                    )
                    
                    # Log execution
                    SignalExecution.log_execution(
                        signal_name=_signal_name,
                        status=status,
                        execution_time_ms=execution_time_ms,
                        instance_id=instance_id,
                        user=user,
                        error_message=error_message,
                        error_traceback=error_trace,
                    )
                    
                    # Check for performance issues
                    if status == 'SUCCESS' and execution_time_ms > max_execution_time_ms:
                        from governance.models import SignalPerformanceAlert
                        SignalPerformanceAlert.create_alert(
                            signal=signal_registry,
                            alert_type='SLOW_EXECUTION',
                            severity='WARNING',
                            message=f'الإشارة {_signal_name} استغرقت {execution_time_ms}ms (الحد الأقصى: {max_execution_time_ms}ms)',
                            execution_time_ms=execution_time_ms,
                            threshold_ms=max_execution_time_ms
                        )
                    
                    # Check for critical failures
                    if status == 'FAILED' and is_critical:
                        from governance.models import SignalPerformanceAlert
                        SignalPerformanceAlert.create_alert(
                            signal=signal_registry,
                            alert_type='CRITICAL_FAILURE',
                            severity='CRITICAL',
                            message=f'فشل حرج في الإشارة {_signal_name}: {error_message}',
                            error_message=error_message,
                            error_traceback=error_trace
                        )
                    
                except Exception as log_error:
                    # Don't let logging errors break the signal
                    logger.error(f"Failed to log signal execution: {log_error}")
        
        return wrapper
    return decorator


def get_signal_statistics(signal_name=None, days=1):
    """
    الحصول على إحصائيات الإشارة
    """
    try:
        from governance.models import SignalRegistry, SignalExecution
        from datetime import timedelta
        
        if signal_name:
            signal = SignalRegistry.objects.get(signal_name=signal_name)
            return {
                'signal_name': signal.signal_name,
                'success_rate': signal.get_success_rate(days=days),
                'avg_execution_time': signal.get_avg_execution_time(days=days),
                'execution_count': signal.get_execution_count(days=days),
                'last_execution': signal.get_last_execution(),
                'status': signal.status,
                'performance_status': signal.get_performance_status(),
            }
        else:
            # Get overall statistics
            start_time = timezone.now() - timedelta(days=days)
            return SignalExecution.get_statistics(days=days)
            
    except Exception as e:
        logger.error(f"Failed to get signal statistics: {e}")
        return None
