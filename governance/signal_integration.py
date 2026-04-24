"""
Django signal integration for SignalRouter governance controls.
Provides decorators and utilities to integrate SignalRouter with Django signals.
"""

import functools
import logging
from typing import Callable, Any
from django.dispatch import Signal
from django.db.models.signals import post_save, pre_save, post_delete, pre_delete

from .services.signal_router import signal_router
from .models import GovernanceContext
from .exceptions import SignalError

logger = logging.getLogger(__name__)


def governed_signal_handler(signal_name: str = None, critical: bool = False, 
                          description: str = "", auto_register: bool = True):
    """
    Decorator to create a governed signal handler.
    
    Args:
        signal_name: Name of the signal (defaults to function name)
        critical: Whether this handler is critical for data integrity
        description: Description of what the handler does
        auto_register: Whether to automatically register with SignalRouter
        
    Usage:
        @governed_signal_handler("user_created", critical=False, description="Send welcome email")
        def send_welcome_email(sender, instance, created, **kwargs):
            if created:
                # Send email logic here
                pass
    """
    def decorator(handler_func: Callable) -> Callable:
        nonlocal signal_name, description
        
        # Default signal name to function name
        if signal_name is None:
            signal_name = handler_func.__name__
        
        # Default description
        if not description:
            description = f"Signal handler: {handler_func.__name__}"
        
        @functools.wraps(handler_func)
        def wrapper(sender, instance=None, **kwargs):
            """Wrapped handler that routes through SignalRouter"""
            try:
                # Route through SignalRouter with governance controls
                result = signal_router.route_signal(
                    signal_name=signal_name,
                    sender=sender,
                    instance=instance,
                    critical=critical,
                    handler_func=handler_func,
                    **kwargs
                )
                
                # If signal was blocked, return early
                if result['blocked']:
                    logger.debug(f"Signal '{signal_name}' blocked: {result['block_reason']}")
                    return None
                
                # If routing failed and signal is critical, raise error
                if not result['success'] and critical:
                    raise SignalError(signal_name, f"Critical signal routing failed: {result.get('error', 'Unknown error')}")
                
                # Execute the actual handler if not blocked
                if result['success'] and not result['blocked']:
                    return handler_func(sender, instance=instance, **kwargs)
                
                return None
                
            except Exception as e:
                logger.error(f"Governed signal handler failed ({signal_name}): {e}", exc_info=True)
                
                # For critical handlers, re-raise the exception
                if critical:
                    raise
                
                # For non-critical handlers, log and continue (fail-safe)
                return None
        
        # Store metadata on the wrapper function
        wrapper._signal_name = signal_name
        wrapper._critical = critical
        wrapper._description = description
        wrapper._original_handler = handler_func
        
        # Auto-register with SignalRouter if requested
        if auto_register:
            signal_router.register_handler(
                signal_name=signal_name,
                handler=handler_func,  # Register original function, not wrapper
                critical=critical,
                description=description
            )
        
        return wrapper
    
    return decorator


def connect_governed_signal(signal: Signal, handler: Callable, sender=None, 
                          signal_name: str = None, critical: bool = False,
                          description: str = ""):
    """
    Connect a Django signal with SignalRouter governance.
    
    Args:
        signal: Django signal to connect to
        handler: Handler function
        sender: Sender class (optional)
        signal_name: Name for SignalRouter (defaults to handler name)
        critical: Whether handler is critical
        description: Handler description
        
    Usage:
        def my_handler(sender, instance, **kwargs):
            # Handler logic
            pass
        
        connect_governed_signal(
            post_save, 
            my_handler, 
            sender=MyModel,
            signal_name="my_model_saved",
            critical=False,
            description="Handle MyModel save"
        )
    """
    if signal_name is None:
        signal_name = handler.__name__
    
    if not description:
        description = f"Django signal handler: {handler.__name__}"
    
    # Create governed wrapper
    governed_handler = governed_signal_handler(
        signal_name=signal_name,
        critical=critical,
        description=description,
        auto_register=True
    )(handler)
    
    # Connect to Django signal
    signal.connect(governed_handler, sender=sender)
    
    logger.info(f"Connected governed signal handler '{signal_name}' to {signal}")
    
    return governed_handler


class GovernedSignalMixin:
    """
    Mixin for Django models to provide governed signal handling.
    
    Usage:
        class MyModel(models.Model, GovernedSignalMixin):
            name = models.CharField(max_length=100)
            
            def on_post_save(self, created, **kwargs):
                if created:
                    # Handle creation
                    pass
            
            def on_pre_delete(self, **kwargs):
                # Handle deletion
                pass
    """
    
    @classmethod
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        
        # Auto-connect governed signal handlers
        cls._connect_governed_signals()
    
    @classmethod
    def _connect_governed_signals(cls):
        """Auto-connect governed signal handlers based on method names"""
        signal_mappings = {
            'on_pre_save': (pre_save, False),
            'on_post_save': (post_save, False),
            'on_pre_delete': (pre_delete, True),  # Deletion is often critical
            'on_post_delete': (post_delete, False),
        }
        
        for method_name, (django_signal, default_critical) in signal_mappings.items():
            if hasattr(cls, method_name):
                handler = getattr(cls, method_name)
                
                # Check if handler has governance metadata
                critical = getattr(handler, '_critical', default_critical)
                description = getattr(handler, '_description', f"{cls.__name__}.{method_name}")
                
                # Connect with governance
                connect_governed_signal(
                    signal=django_signal,
                    handler=cls._create_instance_handler(handler),
                    sender=cls,
                    signal_name=f"{cls.__name__.lower()}_{method_name}",
                    critical=critical,
                    description=description
                )
    
    @classmethod
    def _create_instance_handler(cls, method):
        """Create a handler that calls the instance method"""
        def instance_handler(sender, instance, **kwargs):
            if isinstance(instance, cls):
                return method(instance, **kwargs)
        
        return instance_handler


def critical_signal_handler(signal_name: str = None, description: str = ""):
    """Decorator for critical signal handlers"""
    return governed_signal_handler(
        signal_name=signal_name,
        critical=True,
        description=description
    )


def side_effect_handler(signal_name: str = None, description: str = ""):
    """Decorator for non-critical side-effect handlers"""
    return governed_signal_handler(
        signal_name=signal_name,
        critical=False,
        description=description
    )


class SignalGovernanceMiddleware:
    """
    Middleware to set up governance context for signal handling.
    Should be added to MIDDLEWARE setting.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Set governance context for the request
        user = getattr(request, 'user', None)
        if user and user.is_authenticated:
            GovernanceContext.set_context(
                user=user,
                service='WebRequest',
                operation='http_request',
                request=request
            )
        
        try:
            response = self.get_response(request)
            return response
        finally:
            # Clean up governance context
            GovernanceContext.clear_context()


# Utility functions for common signal patterns

def disable_signals_for_operation(operation_func: Callable, reason: str = "Bulk operation"):
    """
    Decorator to disable signals during bulk operations.
    
    Usage:
        @disable_signals_for_operation
        def bulk_create_users(user_data_list):
            # Bulk create without triggering signals
            User.objects.bulk_create([User(**data) for data in user_data_list])
    """
    @functools.wraps(operation_func)
    def wrapper(*args, **kwargs):
        from .services.signal_router import signals_disabled
        
        with signals_disabled(reason):
            return operation_func(*args, **kwargs)
    
    return wrapper


def maintenance_mode_operation(operation_func: Callable, reason: str = "Maintenance operation"):
    """
    Decorator to run operation in maintenance mode (only critical signals).
    
    Usage:
        @maintenance_mode_operation
        def system_maintenance():
            # Perform maintenance with only critical signals
            pass
    """
    @functools.wraps(operation_func)
    def wrapper(*args, **kwargs):
        from .services.signal_router import maintenance_mode
        
        with maintenance_mode(reason):
            return operation_func(*args, **kwargs)
    
    return wrapper


def with_signal_context(signal_name: str, critical: bool = False):
    """
    Decorator to run function within a signal context.
    
    Usage:
        @with_signal_context("data_processing", critical=True)
        def process_data():
            # Function runs within signal context
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with signal_router.signal_context(signal_name, critical) as can_proceed:
                if can_proceed:
                    return func(*args, **kwargs)
                else:
                    logger.info(f"Function '{func.__name__}' skipped due to signal governance")
                    return None
        
        return wrapper
    
    return decorator


# Example usage and integration patterns

class ExampleIntegration:
    """
    Example of how to integrate SignalRouter with existing Django signals.
    This class demonstrates best practices for signal governance.
    """
    
    @staticmethod
    def setup_user_signals():
        """Example: Set up governed signals for User model"""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        @side_effect_handler("user_welcome_email", "Send welcome email to new users")
        def send_welcome_email(sender, instance, created, **kwargs):
            if created:
                # Send welcome email (non-critical side effect)
                logger.info(f"Sending welcome email to {instance.email}")
        
        @critical_signal_handler("user_audit_log", "Log user creation for audit")
        def log_user_creation(sender, instance, created, **kwargs):
            if created:
                # Critical audit logging
                from .services.audit_service import AuditService
                AuditService.log_operation(
                    model_name='User',
                    object_id=instance.id,
                    operation='CREATE',
                    source_service='UserSignals',
                    user=instance
                )
        
        # Connect to Django signals
        connect_governed_signal(post_save, send_welcome_email, sender=User)
        connect_governed_signal(post_save, log_user_creation, sender=User)
    
    @staticmethod
    def setup_financial_signals():
        """Example: Set up governed signals for financial operations"""
        
        @critical_signal_handler("journal_entry_validation", "Validate journal entry integrity")
        def validate_journal_entry(sender, instance, **kwargs):
            # Critical validation for financial data
            if hasattr(instance, 'validate_balance'):
                instance.validate_balance()
        
        @side_effect_handler("financial_notification", "Send financial notifications")
        def send_financial_notification(sender, instance, **kwargs):
            # Non-critical notification
            logger.info(f"Financial event: {instance}")
        
        # These would be connected to appropriate financial model signals
        # connect_governed_signal(pre_save, validate_journal_entry, sender=JournalEntry)
        # connect_governed_signal(post_save, send_financial_notification, sender=JournalEntry)


# Signal governance configuration
class SignalGovernanceConfig:
    """Configuration for signal governance system"""
    
    # Default settings
    DEFAULT_DEPTH_LIMIT = 5
    DEFAULT_ENABLE_AUDIT = True
    
    # Critical signal patterns (these should never be disabled)
    CRITICAL_SIGNAL_PATTERNS = [
        'audit_',
        'validation_',
        'integrity_',
        'security_'
    ]
    
    # Non-critical signal patterns (safe to disable during maintenance)
    NON_CRITICAL_SIGNAL_PATTERNS = [
        'notification_',
        'email_',
        'cache_',
        'analytics_'
    ]
    
    @classmethod
    def is_critical_signal(cls, signal_name: str) -> bool:
        """Determine if a signal is critical based on naming patterns"""
        return any(
            pattern in signal_name.lower() 
            for pattern in cls.CRITICAL_SIGNAL_PATTERNS
        )
    
    @classmethod
    def is_non_critical_signal(cls, signal_name: str) -> bool:
        """Determine if a signal is non-critical based on naming patterns"""
        return any(
            pattern in signal_name.lower() 
            for pattern in cls.NON_CRITICAL_SIGNAL_PATTERNS
        )