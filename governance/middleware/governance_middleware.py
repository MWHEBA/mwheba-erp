"""
Governance middleware for automatic audit trail logging and thread-safe operations.
Provides comprehensive logging for all sensitive operations across all domains.
"""

import logging
import threading
import time
from django.utils.deprecation import MiddlewareMixin
from django.db import transaction
from django.contrib.auth.models import AnonymousUser
from django.core.serializers.json import DjangoJSONEncoder
from django.forms.models import model_to_dict
from django.apps import apps
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from governance.models import AuditTrail, GovernanceContext
from governance.services import AuditService
from governance.thread_safety import monitor_operation
import json

logger = logging.getLogger(__name__)

# High-risk models that require comprehensive audit trails
HIGH_RISK_MODELS = {
    # Financial Models (Critical)
    'financial.JournalEntry': {'level': 'CRITICAL', 'capture_data': True},
    'financial.JournalEntryLine': {'level': 'CRITICAL', 'capture_data': True},
    'financial.FeePayment': {'level': 'CRITICAL', 'capture_data': True},
    'sale.Sale': {'level': 'CRITICAL', 'capture_data': True},
    'purchase.Purchase': {'level': 'CRITICAL', 'capture_data': True},
    
    # Inventory Models (Critical)
    'product.Stock': {'level': 'CRITICAL', 'capture_data': True},
    'product.StockMovement': {'level': 'CRITICAL', 'capture_data': True},
    
    # Financial Models (High)
    'financial.JournalEntry': {'level': 'HIGH', 'capture_data': False},
    'financial.Transaction': {'level': 'HIGH', 'capture_data': False},
    
    # System Models (High)
    'auth.User': {'level': 'HIGH', 'capture_data': False},
    'auth.Group': {'level': 'HIGH', 'capture_data': False},
}

# Thread-local storage for before data capture
_audit_context = threading.local()


class GovernanceAuditMiddleware(MiddlewareMixin):
    """
    Comprehensive audit middleware for governance system.
    Provides automatic audit trail logging with thread-safe operations.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        # Connect to model signals for automatic audit trail creation
        self._connect_signals()
        
    def _connect_signals(self):
        """Connect to Django model signals for automatic audit logging"""
        # Connect pre_save for before data capture
        pre_save.connect(self._capture_before_data, dispatch_uid='governance_pre_save')
        
        # Connect post_save for after data capture
        post_save.connect(self._log_model_save, dispatch_uid='governance_post_save')
        
        # Connect post_delete for deletion logging
        post_delete.connect(self._log_model_delete, dispatch_uid='governance_post_delete')
    
    def process_request(self, request):
        """Set up governance context for the request"""
        user = request.user if hasattr(request, 'user') and request.user.is_authenticated else None
        
        # Set governance context for this thread
        GovernanceContext.set_context(
            user=user,
            service='WebRequest',
            operation='HTTP_REQUEST',
            request=request
        )
        
        # Store request start time for performance monitoring
        request._governance_start_time = time.time()
        
        return None
    
    def process_response(self, request, response):
        """Clean up governance context and log request completion"""
        try:
            # Calculate request duration
            if hasattr(request, '_governance_start_time'):
                duration = time.time() - request._governance_start_time
                
                # Log slow requests (>2 seconds) for monitoring
                if duration > 2.0:
                    logger.warning(f"Slow request detected: {request.path} took {duration:.2f}s")
            
            # Log high-risk admin operations
            if request.path.startswith('/admin/') and request.method in ['POST', 'PUT', 'PATCH', 'DELETE']:
                self._log_admin_operation(request, response)
            
        except Exception as e:
            logger.error(f"Error in governance middleware cleanup: {e}")
        finally:
            # Always clear context to prevent memory leaks
            GovernanceContext.clear_context()
            
        return response
    
    def process_exception(self, request, exception):
        """Log exceptions in governance operations"""
        try:
            user = GovernanceContext.get_current_user()
            if user:
                AuditService.log_operation(
                    model_name='System',
                    object_id=0,
                    operation='EXCEPTION',
                    source_service='GovernanceMiddleware',
                    user=user,
                    request=request,
                    exception_type=type(exception).__name__,
                    exception_message=str(exception),
                    request_path=request.path,
                    request_method=request.method
                )
        except Exception as e:
            logger.error(f"Error logging exception in governance middleware: {e}")
        
        return None
    
    def _log_admin_operation(self, request, response):
        """Log admin panel operations on high-risk models"""
        try:
            # Extract model information from admin URL
            path_parts = request.path.strip('/').split('/')
            if len(path_parts) >= 4 and path_parts[0] == 'admin':
                app_label = path_parts[1]
                model_name = path_parts[2]
                model_key = f"{app_label}.{model_name}"
                
                # Check if this is a high-risk model
                if model_key in HIGH_RISK_MODELS:
                    object_id = path_parts[3] if len(path_parts) > 3 and path_parts[3].isdigit() else 0
                    
                    # Determine admin action
                    admin_action = 'view'
                    if request.method == 'POST':
                        if 'delete' in request.POST:
                            admin_action = 'delete'
                        else:
                            admin_action = 'save'
                    elif request.method in ['PUT', 'PATCH']:
                        admin_action = 'update'
                    elif request.method == 'DELETE':
                        admin_action = 'delete'
                    
                    # Log the admin operation
                    AuditService.log_admin_access(
                        model_name=model_key,
                        object_id=int(object_id) if object_id else 0,
                        admin_action=admin_action,
                        user=request.user,
                        request=request,
                        response_status=response.status_code,
                        high_risk_model=True
                    )
                    
        except Exception as e:
            logger.error(f"Error logging admin operation: {e}")
    
    def _capture_before_data(self, sender, instance, **kwargs):
        """Capture before data for high-risk models (thread-safe)"""
        model_key = f"{sender._meta.app_label}.{sender._meta.model_name}"
        
        # Only capture for high-risk models that require data capture
        if model_key in HIGH_RISK_MODELS and HIGH_RISK_MODELS[model_key].get('capture_data', False):
            try:
                # Use thread-local storage to store before data
                if not hasattr(_audit_context, 'before_data'):
                    _audit_context.before_data = {}
                
                # Create a unique key for this instance
                instance_key = f"{model_key}_{instance.pk if instance.pk else 'new'}"
                
                # Capture current data if instance exists in database
                if instance.pk:
                    try:
                        # Get current data from database (thread-safe)
                        with transaction.atomic():
                            current_instance = sender.objects.select_for_update(nowait=True).get(pk=instance.pk)
                            _audit_context.before_data[instance_key] = self._serialize_model_data(current_instance)
                    except sender.DoesNotExist:
                        _audit_context.before_data[instance_key] = None
                    except Exception as e:
                        logger.warning(f"Could not capture before data for {instance_key}: {e}")
                        _audit_context.before_data[instance_key] = None
                else:
                    # New instance - no before data
                    _audit_context.before_data[instance_key] = None
                    
            except Exception as e:
                logger.error(f"Error capturing before data for {model_key}: {e}")
    
    def _log_model_save(self, sender, instance, created, **kwargs):
        """Log model save operations for high-risk models"""
        model_key = f"{sender._meta.app_label}.{sender._meta.model_name}"
        
        # Only log high-risk models
        if model_key in HIGH_RISK_MODELS:
            try:
                with monitor_operation("audit_model_save"):
                    # Get before data from thread-local storage
                    before_data = None
                    after_data = None
                    
                    if HIGH_RISK_MODELS[model_key].get('capture_data', False):
                        instance_key = f"{model_key}_{instance.pk}"
                        
                        # Get before data
                        if hasattr(_audit_context, 'before_data') and instance_key in _audit_context.before_data:
                            before_data = _audit_context.before_data[instance_key]
                            # Clean up to prevent memory leaks
                            del _audit_context.before_data[instance_key]
                        
                        # Capture after data
                        after_data = self._serialize_model_data(instance)
                    
                    # Determine operation type
                    operation = 'CREATE' if created else 'UPDATE'
                    
                    # Get current user and service from context
                    user = GovernanceContext.get_current_user()
                    service = GovernanceContext.get_current_service() or 'ModelSignal'
                    
                    # Log the operation
                    AuditService.log_operation(
                        model_name=model_key,
                        object_id=instance.pk,
                        operation=operation,
                        source_service=service,
                        user=user,
                        before_data=before_data,
                        after_data=after_data,
                        model_created=created,
                        high_risk_model=True,
                        risk_level=HIGH_RISK_MODELS[model_key]['level']
                    )
                    
            except Exception as e:
                logger.error(f"Error logging model save for {model_key}: {e}")
    
    def _log_model_delete(self, sender, instance, **kwargs):
        """Log model deletion operations for high-risk models"""
        model_key = f"{sender._meta.app_label}.{sender._meta.model_name}"
        
        # Only log high-risk models
        if model_key in HIGH_RISK_MODELS:
            try:
                with monitor_operation("audit_model_delete"):
                    # Capture before data (the data being deleted)
                    before_data = None
                    if HIGH_RISK_MODELS[model_key].get('capture_data', False):
                        before_data = self._serialize_model_data(instance)
                    
                    # Get current user and service from context
                    user = GovernanceContext.get_current_user()
                    service = GovernanceContext.get_current_service() or 'ModelSignal'
                    
                    # Log the deletion
                    AuditService.log_operation(
                        model_name=model_key,
                        object_id=instance.pk,
                        operation='DELETE',
                        source_service=service,
                        user=user,
                        before_data=before_data,
                        after_data=None,
                        high_risk_model=True,
                        risk_level=HIGH_RISK_MODELS[model_key]['level']
                    )
                    
            except Exception as e:
                logger.error(f"Error logging model deletion for {model_key}: {e}")
    
    def _serialize_model_data(self, instance):
        """
        Serialize model instance data for audit trail.
        Thread-safe serialization with proper error handling.
        """
        try:
            # Use model_to_dict for basic serialization
            data = model_to_dict(instance)
            
            # Convert to JSON-serializable format
            serialized_data = {}
            for key, value in data.items():
                try:
                    # Test JSON serialization
                    json.dumps(value, cls=DjangoJSONEncoder)
                    serialized_data[key] = value
                except (TypeError, ValueError):
                    # Convert non-serializable values to string
                    serialized_data[key] = str(value)
            
            # Add metadata
            serialized_data['_model'] = f"{instance._meta.app_label}.{instance._meta.model_name}"
            serialized_data['_pk'] = instance.pk
            serialized_data['_str'] = str(instance)
            
            return serialized_data
            
        except Exception as e:
            logger.error(f"Error serializing model data: {e}")
            return {
                '_model': f"{instance._meta.app_label}.{instance._meta.model_name}",
                '_pk': instance.pk,
                '_str': str(instance),
                '_serialization_error': str(e)
            }


class GovernanceContextMiddleware(MiddlewareMixin):
    """
    Lightweight middleware for setting governance context.
    Can be used independently of the full audit middleware.
    """
    
    def process_request(self, request):
        """Set governance context for the request"""
        user = request.user if hasattr(request, 'user') and request.user.is_authenticated else None
        
        GovernanceContext.set_context(
            user=user,
            service='WebRequest',
            operation='HTTP_REQUEST',
            request=request
        )
        
        return None
    
    def process_response(self, request, response):
        """Clear governance context"""
        GovernanceContext.clear_context()
        return response
    
    def process_exception(self, request, exception):
        """Clear governance context on exception"""
        GovernanceContext.clear_context()
        return None


# Utility functions for manual audit logging

def log_gateway_operation(gateway_name, operation, target_model, target_id, 
                         before_data=None, after_data=None, **context):
    """
    Manually log gateway operations with proper context.
    Thread-safe operation logging.
    """
    try:
        user = GovernanceContext.get_current_user()
        
        AuditService.log_gateway_operation(
            gateway_name=gateway_name,
            operation=operation,
            target_model=target_model,
            target_id=target_id,
            user=user,
            before_data=before_data,
            after_data=after_data,
            **context
        )
    except Exception as e:
        logger.error(f"Error logging gateway operation: {e}")


def log_authority_violation(service, model, operation, object_id=None, **context):
    """
    Log authority boundary violations.
    Thread-safe violation logging.
    """
    try:
        user = GovernanceContext.get_current_user()
        
        AuditService.log_authority_violation(
            service=service,
            model=model,
            operation=operation,
            object_id=object_id,
            user=user,
            **context
        )
    except Exception as e:
        logger.error(f"Error logging authority violation: {e}")


def with_audit_context(user=None, service=None, operation=None):
    """
    Decorator for setting audit context around operations.
    Thread-safe context management.
    
    Usage:
        @with_audit_context(service='AccountingGateway', operation='CREATE_JOURNAL_ENTRY')
        def create_journal_entry(...):
            # Operation code here
            pass
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Set context
            GovernanceContext.set_context(
                user=user,
                service=service,
                operation=operation
            )
            
            try:
                return func(*args, **kwargs)
            finally:
                # Always clear context
                GovernanceContext.clear_context()
        
        return wrapper
    return decorator


# Health check functions

def check_audit_middleware_health():
    """
    Check if audit middleware is working correctly.
    Returns health status and statistics.
    """
    try:
        stats = AuditService.get_audit_statistics()
        
        # Check recent activity
        recent_count = stats.get('recent_operations', 0)
        
        # Check for authority violations
        violations = stats.get('authority_violations', 0)
        
        health_status = {
            'status': 'healthy',
            'total_audit_records': stats.get('total_records', 0),
            'recent_operations_24h': recent_count,
            'authority_violations': violations,
            'high_risk_models_monitored': len(HIGH_RISK_MODELS),
            'middleware_active': True
        }
        
        # Add warnings for concerning patterns
        if violations > 10:
            health_status['warnings'] = health_status.get('warnings', [])
            health_status['warnings'].append(f"High number of authority violations: {violations}")
        
        if recent_count == 0:
            health_status['warnings'] = health_status.get('warnings', [])
            health_status['warnings'].append("No recent audit activity detected")
        
        return health_status
        
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e),
            'middleware_active': False
        }