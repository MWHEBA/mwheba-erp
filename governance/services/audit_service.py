# -*- coding: utf-8 -*-
"""
Audit Service for Code Governance System

This service provides comprehensive audit trail functionality for tracking
all operations on high-risk models, especially admin panel access attempts.

Key Features:
- Thread-safe audit record creation
- Comprehensive context capture
- Admin access attempt logging
- Authority violation tracking
- Performance optimized for high-volume logging
"""

from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.conf import settings
from typing import Optional, Dict, Any, Union
import logging
import json
from datetime import datetime

from ..models import AuditTrail
from ..thread_safety import ThreadSafeOperationMixin

User = get_user_model()
logger = logging.getLogger('governance.audit_service')


class AuditService(ThreadSafeOperationMixin):
    """
    Thread-safe audit service for comprehensive operation tracking.
    
    This service ensures all sensitive operations are properly logged
    with complete context information for security and compliance.
    """
    
    @classmethod
    @transaction.atomic
    def create_audit_record(
        cls,
        model_name: str,
        object_id: Optional[Union[int, str]],
        operation: str,
        user: Optional[User],
        source_service: str = "Unknown",
        before_data: Optional[Dict] = None,
        after_data: Optional[Dict] = None,
        additional_context: Optional[Dict] = None
    ) -> AuditTrail:
        """
        Create a comprehensive audit trail record.
        
        Args:
            model_name: Name of the model being operated on
            object_id: ID of the specific object (if applicable)
            operation: Type of operation (create, update, delete, view, etc.)
            user: User performing the operation
            source_service: Service/component initiating the operation
            before_data: Data before the operation
            after_data: Data after the operation
            additional_context: Any additional context information
            
        Returns:
            AuditTrail: The created audit record
        """
        try:
            # ✅ Skip audit if object_id is None (e.g., pre_save signals before object creation)
            if object_id is None:
                logger.debug(
                    f"Skipping audit record for {operation} on {model_name}: object_id is None (likely pre_save signal)"
                )
                return None
            
            # Ensure thread-safe operation
            with cls._get_thread_lock():
                # Prepare audit data
                audit_data = {
                    'model_name': model_name,
                    'object_id': str(object_id),
                    'operation': operation,
                    'source_service': source_service,
                    'timestamp': timezone.now(),
                    'before_data': cls._sanitize_data(before_data),
                    'after_data': cls._sanitize_data(after_data),
                    'additional_context': cls._sanitize_data(additional_context)
                }
                
                # Add user if provided
                if user:
                    audit_data['user'] = user
                
                # Create audit record
                audit_record = AuditTrail.objects.create(**audit_data)
                
                # Log to application logger as well
                logger.info(
                    f"Audit record created: {operation} on {model_name} "
                    f"by {user.username if user else 'system'} via {source_service}",
                    extra={
                        'audit_id': audit_record.id,
                        'model_name': model_name,
                        'object_id': object_id,
                        'operation': operation,
                        'user_id': user.id if user else None,
                        'source_service': source_service
                    }
                )
                
                return audit_record
                
        except Exception as e:
            # Log the error but don't let audit failures break the application
            logger.error(
                f"Failed to create audit record for {operation} on {model_name}: {e}",
                extra={
                    'model_name': model_name,
                    'object_id': object_id,
                    'operation': operation,
                    'user_id': user.id if user else None,
                    'error': str(e)
                }
            )
            # Re-raise in development, log and continue in production
            if hasattr(settings, 'DEBUG') and settings.DEBUG:
                raise
            return None
    
    @classmethod
    def log_admin_access(
        cls,
        model_name: str,
        action_type: str,
        result: str,
        user: User,
        request_data: Optional[Dict] = None,
        object_id: Optional[Union[int, str]] = None,
        additional_context: Optional[Dict] = None
    ) -> Optional[AuditTrail]:
        """
        Specialized method for logging admin panel access attempts.
        
        Args:
            model_name: Name of the model being accessed
            action_type: Type of admin action (view, add, change, delete, etc.)
            result: Result of the action (allowed, blocked, error, etc.)
            user: User attempting the action
            request_data: HTTP request data
            object_id: ID of specific object being accessed
            additional_context: Additional context information
            
        Returns:
            AuditTrail: The created audit record or None if failed
        """
        # Prepare admin-specific context
        admin_context = {
            'action_type': action_type,
            'result': result,
            'access_method': 'admin_panel',
            'timestamp': timezone.now().isoformat()
        }
        
        # Add request data if provided
        if request_data:
            admin_context.update({
                'ip_address': request_data.get('ip_address'),
                'user_agent': request_data.get('user_agent'),
                'session_key': request_data.get('session_key'),
                'path': request_data.get('path'),
                'method': request_data.get('method')
            })
        
        # Merge with additional context
        if additional_context:
            admin_context.update(additional_context)
        
        # Create audit record
        return cls.create_audit_record(
            model_name=model_name,
            object_id=object_id,
            operation=f"admin_{action_type}",
            user=user,
            source_service="AdminPanel",
            additional_context=admin_context
        )
    
    @classmethod
    def log_authority_violation(
        cls,
        model_name: str,
        attempted_operation: str,
        user: User,
        violation_type: str,
        violation_details: Dict,
        source_service: str = "Unknown"
    ) -> Optional[AuditTrail]:
        """
        Log authority boundary violations for security monitoring.
        
        Args:
            model_name: Name of the model involved
            attempted_operation: Operation that was attempted
            user: User who attempted the operation
            violation_type: Type of violation (unauthorized_service, missing_permission, etc.)
            violation_details: Detailed information about the violation
            source_service: Service where violation occurred
            
        Returns:
            AuditTrail: The created audit record or None if failed
        """
        violation_context = {
            'violation_type': violation_type,
            'attempted_operation': attempted_operation,
            'violation_details': violation_details,
            'security_event': True,
            'requires_investigation': True,
            'timestamp': timezone.now().isoformat()
        }
        
        return cls.create_audit_record(
            model_name=model_name,
            object_id=0,  # Use 0 for authority violations where no object exists yet
            operation="authority_violation",
            user=user,
            source_service=source_service,
            additional_context=violation_context
        )
    
    @classmethod
    def log_governance_event(
        cls,
        event_type: str,
        event_details: Dict,
        user: Optional[User] = None,
        model_name: Optional[str] = None,
        object_id: Optional[Union[int, str]] = None
    ) -> Optional[AuditTrail]:
        """
        Log general governance system events.
        
        Args:
            event_type: Type of governance event
            event_details: Detailed information about the event
            user: User associated with the event (if applicable)
            model_name: Model associated with the event (if applicable)
            object_id: Object ID associated with the event (if applicable)
            
        Returns:
            AuditTrail: The created audit record or None if failed
        """
        governance_context = {
            'event_type': event_type,
            'event_details': event_details,
            'governance_system': True,
            'timestamp': timezone.now().isoformat()
        }
        
        return cls.create_audit_record(
            model_name=model_name or "governance.system",
            object_id=object_id,
            operation=f"governance_{event_type}",
            user=user,
            source_service="GovernanceSystem",
            additional_context=governance_context
        )
    
    @classmethod
    def get_audit_trail(
        cls,
        model_name: Optional[str] = None,
        object_id: Optional[Union[int, str]] = None,
        user: Optional[User] = None,
        operation: Optional[str] = None,
        source_service: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> list:
        """
        Retrieve audit trail records with filtering options.
        
        Args:
            model_name: Filter by model name
            object_id: Filter by object ID
            user: Filter by user
            operation: Filter by operation type
            source_service: Filter by source service
            start_date: Filter by start date
            end_date: Filter by end date
            limit: Maximum number of records to return
            
        Returns:
            list: List of AuditTrail records matching the criteria
        """
        try:
            queryset = AuditTrail.objects.all()
            
            # Apply filters
            if model_name:
                queryset = queryset.filter(model_name=model_name)
            if object_id:
                queryset = queryset.filter(object_id=str(object_id))
            if user:
                queryset = queryset.filter(user=user)
            if operation:
                queryset = queryset.filter(operation=operation)
            if source_service:
                queryset = queryset.filter(source_service=source_service)
            if start_date:
                queryset = queryset.filter(timestamp__gte=start_date)
            if end_date:
                queryset = queryset.filter(timestamp__lte=end_date)
            
            # Order by timestamp (most recent first) and limit
            return list(queryset.order_by('-timestamp')[:limit])
            
        except Exception as e:
            logger.error(f"Failed to retrieve audit trail: {e}")
            return []
    
    @classmethod
    def get_security_events(
        cls,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 50
    ) -> list:
        """
        Retrieve security-related audit events.
        
        Args:
            start_date: Filter by start date
            end_date: Filter by end date
            limit: Maximum number of records to return
            
        Returns:
            list: List of security-related audit records
        """
        try:
            queryset = AuditTrail.objects.filter(
                additional_context__security_event=True
            )
            
            if start_date:
                queryset = queryset.filter(timestamp__gte=start_date)
            if end_date:
                queryset = queryset.filter(timestamp__lte=end_date)
            
            return list(queryset.order_by('-timestamp')[:limit])
            
        except Exception as e:
            logger.error(f"Failed to retrieve security events: {e}")
            return []
    
    @classmethod
    def _sanitize_data(cls, data: Any) -> Any:
        """
        Sanitize data for safe storage in audit records.
        
        This method ensures that sensitive information is not stored
        in audit records and that the data is JSON-serializable.
        """
        if data is None:
            return None
        
        if isinstance(data, dict):
            sanitized = {}
            for key, value in data.items():
                # Skip sensitive fields
                if key.lower() in ['password', 'token', 'secret', 'key', 'credential']:
                    sanitized[key] = '[REDACTED]'
                else:
                    sanitized[key] = cls._sanitize_data(value)
            return sanitized
        
        elif isinstance(data, (list, tuple)):
            return [cls._sanitize_data(item) for item in data]
        
        elif isinstance(data, (str, int, float, bool)):
            return data
        
        elif isinstance(data, datetime):
            return data.isoformat()
        
        else:
            # Convert other types to string representation
            return str(data)
    
    @classmethod
    def log_operation(
        cls,
        model_name: str,
        object_id: Optional[Union[int, str]],
        operation: str,
        source_service: str,
        user: Optional[User] = None,
        **kwargs
    ) -> Optional[AuditTrail]:
        """
        Log a general operation (alias for create_audit_record with additional context).
        
        Args:
            model_name: Name of the model
            object_id: ID of the object
            operation: Type of operation
            source_service: Service performing the operation
            user: User performing the operation
            **kwargs: Additional context data
            
        Returns:
            AuditTrail: The created audit record or None if failed
        """
        return cls.create_audit_record(
            model_name=model_name,
            object_id=object_id,
            operation=operation,
            user=user,
            source_service=source_service,
            additional_context=kwargs
        )
    
    @classmethod
    def log_signal_operation(
        cls,
        signal_name: str,
        sender_model: str,
        sender_id: Optional[Union[int, str]],
        operation: str,
        user: Optional[User] = None,
        **kwargs
    ) -> Optional[AuditTrail]:
        """
        Log a signal operation.
        
        Args:
            signal_name: Name of the signal
            sender_model: Model that sent the signal
            sender_id: ID of the sender object
            operation: Type of operation
            user: User associated with the operation
            **kwargs: Additional context data
            
        Returns:
            AuditTrail: The created audit record or None if failed
        """
        context = {
            'signal_name': signal_name,
            'sender_model': sender_model,
            'sender_id': sender_id,
            **kwargs
        }
        
        return cls.create_audit_record(
            model_name=f"signal.{signal_name}",
            object_id=sender_id,
            operation=operation,
            user=user,
            source_service="SignalRouter",
            additional_context=context
        )
    
    @classmethod
    def create_model_audit_record(
        cls,
        instance,
        operation: str,
        user: User,
        before_data: Optional[Dict] = None,
        after_data: Optional[Dict] = None,
        source_service: str = "Unknown"
    ) -> Optional[AuditTrail]:
        """
        Create audit record for a specific model instance.
        
        Args:
            instance: The model instance being audited
            operation: Type of operation
            user: User performing the operation
            before_data: Data before the operation
            after_data: Data after the operation
            source_service: Service initiating the operation
            
        Returns:
            AuditTrail: The created audit record or None if failed
        """
        model_name = f"{instance._meta.app_label}.{instance._meta.model_name}"
        object_id = getattr(instance, 'pk', None)
        
        return cls.create_audit_record(
            model_name=model_name,
            object_id=object_id,
            operation=operation,
            user=user,
            source_service=source_service,
            before_data=before_data,
            after_data=after_data
        )
    
    # ============================================================================
    # PAYROLL-SPECIFIC AUDIT METHODS
    # ============================================================================
    
    @classmethod
    def log_payroll_operation(
        cls,
        payroll_instance,
        operation: str,
        user: User,
        source_service: str = "PayrollService",
        before_data: Optional[Dict] = None,
        after_data: Optional[Dict] = None,
        additional_context: Optional[Dict] = None
    ) -> Optional[AuditTrail]:
        """
        Log payroll-specific operations with enhanced context.
        
        Args:
            payroll_instance: Payroll model instance
            operation: Operation type (create, calculate, approve, pay, cancel)
            user: User performing the operation
            source_service: Service performing the operation
            before_data: Data before operation
            after_data: Data after operation
            additional_context: Additional payroll-specific context
            
        Returns:
            AuditTrail: The created audit record or None if failed
        """
        # Prepare payroll-specific context
        payroll_context = {
            'employee_id': payroll_instance.employee.id,
            'employee_name': payroll_instance.employee.get_full_name_ar(),
            'month': payroll_instance.month.strftime('%Y-%m'),
            'status': payroll_instance.status,
            'net_salary': str(payroll_instance.net_salary),
            'gross_salary': str(payroll_instance.gross_salary),
            'operation_type': 'payroll_operation'
        }
        
        # Add additional context if provided
        if additional_context:
            payroll_context.update(additional_context)
        
        return cls.create_audit_record(
            model_name='hr.Payroll',
            object_id=payroll_instance.id,
            operation=operation,
            user=user,
            source_service=source_service,
            before_data=before_data,
            after_data=after_data,
            additional_context=payroll_context
        )
    
    @classmethod
    def log_payroll_payment_operation(
        cls,
        payment_instance,
        operation: str,
        user: User,
        source_service: str = "PayrollPaymentService",
        before_data: Optional[Dict] = None,
        after_data: Optional[Dict] = None,
        additional_context: Optional[Dict] = None
    ) -> Optional[AuditTrail]:
        """
        Log payroll payment operations with enhanced context.
        
        Args:
            payment_instance: PayrollPayment model instance
            operation: Operation type (create, process, complete, cancel)
            user: User performing the operation
            source_service: Service performing the operation
            before_data: Data before operation
            after_data: Data after operation
            additional_context: Additional payment-specific context
            
        Returns:
            AuditTrail: The created audit record or None if failed
        """
        # Prepare payment-specific context
        payment_context = {
            'payment_reference': payment_instance.payment_reference,
            'payment_type': payment_instance.payment_type,
            'payment_method': payment_instance.payment_method,
            'total_amount': str(payment_instance.total_amount),
            'net_amount': str(payment_instance.net_amount),
            'status': payment_instance.status,
            'payment_date': payment_instance.payment_date.strftime('%Y-%m-%d'),
            'operation_type': 'payroll_payment_operation'
        }
        
        # Add additional context if provided
        if additional_context:
            payment_context.update(additional_context)
        
        return cls.create_audit_record(
            model_name='hr.PayrollPayment',
            object_id=payment_instance.id,
            operation=operation,
            user=user,
            source_service=source_service,
            before_data=before_data,
            after_data=after_data,
            additional_context=payment_context
        )
    
    @classmethod
    def log_advance_operation(
        cls,
        advance_instance,
        operation: str,
        user: User,
        source_service: str = "AdvanceService",
        before_data: Optional[Dict] = None,
        after_data: Optional[Dict] = None,
        additional_context: Optional[Dict] = None
    ) -> Optional[AuditTrail]:
        """
        Log advance operations with enhanced context.
        
        Args:
            advance_instance: Advance model instance
            operation: Operation type (create, approve, pay, deduct, complete)
            user: User performing the operation
            source_service: Service performing the operation
            before_data: Data before operation
            after_data: Data after operation
            additional_context: Additional advance-specific context
            
        Returns:
            AuditTrail: The created audit record or None if failed
        """
        # Prepare advance-specific context
        advance_context = {
            'employee_id': advance_instance.employee.id,
            'employee_name': advance_instance.employee.get_full_name_ar(),
            'amount': str(advance_instance.amount),
            'installments_count': advance_instance.installments_count,
            'remaining_amount': str(advance_instance.remaining_amount),
            'paid_installments': advance_instance.paid_installments,
            'status': advance_instance.status,
            'operation_type': 'advance_operation'
        }
        
        # Add additional context if provided
        if additional_context:
            advance_context.update(additional_context)
        
        return cls.create_audit_record(
            model_name='hr.Advance',
            object_id=advance_instance.id,
            operation=operation,
            user=user,
            source_service=source_service,
            before_data=before_data,
            after_data=after_data,
            additional_context=advance_context
        )
    
    @classmethod
    def log_salary_component_operation(
        cls,
        component_instance,
        operation: str,
        user: User,
        source_service: str = "SalaryComponentService",
        before_data: Optional[Dict] = None,
        after_data: Optional[Dict] = None,
        additional_context: Optional[Dict] = None
    ) -> Optional[AuditTrail]:
        """
        Log salary component operations with enhanced context.
        
        Args:
            component_instance: SalaryComponent model instance
            operation: Operation type (create, update, terminate, renew)
            user: User performing the operation
            source_service: Service performing the operation
            before_data: Data before operation
            after_data: Data after operation
            additional_context: Additional component-specific context
            
        Returns:
            AuditTrail: The created audit record or None if failed
        """
        # Prepare component-specific context
        component_context = {
            'employee_id': component_instance.employee.id,
            'employee_name': component_instance.employee.get_full_name_ar(),
            'component_type': component_instance.component_type,
            'amount': str(component_instance.amount),
            'effective_date': component_instance.effective_date.strftime('%Y-%m-%d') if component_instance.effective_date else None,
            'end_date': component_instance.end_date.strftime('%Y-%m-%d') if component_instance.end_date else None,
            'is_active': component_instance.is_active,
            'operation_type': 'salary_component_operation'
        }
        
        # Add additional context if provided
        if additional_context:
            component_context.update(additional_context)
        
        return cls.create_audit_record(
            model_name='hr.SalaryComponent',
            object_id=component_instance.id,
            operation=operation,
            user=user,
            source_service=source_service,
            before_data=before_data,
            after_data=after_data,
            additional_context=component_context
        )
    
    @classmethod
    def log_payroll_batch_operation(
        cls,
        batch_id: str,
        operation: str,
        user: User,
        employee_count: int = 0,
        total_amount: Optional[str] = None,
        source_service: str = "PayrollBatchService",
        additional_context: Optional[Dict] = None
    ) -> Optional[AuditTrail]:
        """
        Log batch payroll operations.
        
        Args:
            batch_id: Unique batch identifier
            operation: Operation type (process, approve, pay, cancel)
            user: User performing the operation
            employee_count: Number of employees in batch
            total_amount: Total amount for batch
            source_service: Service performing the operation
            additional_context: Additional batch-specific context
            
        Returns:
            AuditTrail: The created audit record or None if failed
        """
        # Prepare batch-specific context
        batch_context = {
            'batch_id': batch_id,
            'employee_count': employee_count,
            'total_amount': total_amount,
            'operation_type': 'payroll_batch_operation'
        }
        
        # Add additional context if provided
        if additional_context:
            batch_context.update(additional_context)
        
        return cls.create_audit_record(
            model_name='hr.PayrollBatch',
            object_id=batch_id,
            operation=operation,
            user=user,
            source_service=source_service,
            additional_context=batch_context
        )


# Audit decorators for easy integration
def audit_operation(operation: str, source_service: str = "Unknown"):
    """
    Decorator to automatically audit function calls.
    
    Usage:
        @audit_operation("create_journal_entry", "AccountingGateway")
        def create_entry(user, data):
            # Function implementation
            pass
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Extract user from arguments (assuming it's the first argument)
            user = args[0] if args and hasattr(args[0], 'username') else None
            
            try:
                result = func(*args, **kwargs)
                
                # Create audit record for successful operation
                if user:
                    AuditService.create_audit_record(
                        model_name="function_call",
                        object_id=None,
                        operation=operation,
                        user=user,
                        source_service=source_service,
                        additional_context={
                            'function_name': func.__name__,
                            'success': True
                        }
                    )
                
                return result
                
            except Exception as e:
                # Create audit record for failed operation
                if user:
                    AuditService.create_audit_record(
                        model_name="function_call",
                        object_id=None,
                        operation=f"{operation}_failed",
                        user=user,
                        source_service=source_service,
                        additional_context={
                            'function_name': func.__name__,
                            'success': False,
                            'error': str(e)
                        }
                    )
                
                raise
        
        return wrapper
    return decorator


# Export main classes and functions
__all__ = [
    'AuditService',
    'audit_operation'
]