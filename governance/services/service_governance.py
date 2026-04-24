# -*- coding: utf-8 -*-
"""
Service Governance Decorator

Provides unified governance decorator for all service operations.
Handles idempotency, audit logging, error handling, and performance monitoring.
"""

import logging
import time
import functools
from typing import Optional, Callable, Any
from django.db import transaction
from django.utils import timezone

from .idempotency_service import IdempotencyService
from .audit_service import AuditService
from .quarantine_service import QuarantineService
from ..models import GovernanceContext
from ..exceptions import GovernanceError, IdempotencyError

logger = logging.getLogger('governance.service')


def governed_service(
    critical: bool = False,
    description: str = "",
    enable_idempotency: bool = True,
    enable_audit: bool = True,
    max_execution_time: float = 30.0,
    retry_count: int = 0
):
    """
    Unified governance decorator for service methods.
    
    Features:
    - Automatic idempotency checking (optional)
    - Automatic audit logging (optional)
    - Error handling and quarantine
    - Performance monitoring
    - Retry logic for transient failures
    
    Args:
        critical: Whether this is a critical operation (affects error handling)
        description: Human-readable description of the operation
        enable_idempotency: Enable automatic idempotency checking
        enable_audit: Enable automatic audit logging
        max_execution_time: Maximum allowed execution time in seconds
        retry_count: Number of retries for transient failures
    
    Usage:
        @governed_service(critical=True, description="Create customer payments")
        def create_customer_payments(self, customer, payment_data):
            # Service logic here
            return result
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Extract service instance and operation context
            service_instance = args[0] if args else None
            service_name = service_instance.__class__.__name__ if service_instance else func.__name__
            
            # Get user from context
            user = GovernanceContext.get_current_user()
            
            # Performance tracking
            start_time = time.time()
            operation_id = f"{service_name}.{func.__name__}"
            
            # Idempotency key generation (if enabled)
            idempotency_key = None
            if enable_idempotency:
                idempotency_key = _generate_idempotency_key(
                    service_name, func.__name__, args, kwargs
                )
            
            try:
                # Check idempotency (if enabled)
                if enable_idempotency and idempotency_key:
                    is_duplicate, record, cached_result = IdempotencyService.check_and_record_operation(
                        operation_type=f"service_{service_name}",
                        idempotency_key=idempotency_key,
                        result_data={},
                        user=user
                    )
                    
                    if is_duplicate:
                        logger.info(
                            f"Duplicate operation detected: {operation_id} - "
                            f"Returning cached result"
                        )
                        return cached_result.get('result')
                
                # Execute the actual service method
                result = _execute_with_retry(
                    func, args, kwargs, retry_count, operation_id
                )
                
                # Check execution time
                execution_time = time.time() - start_time
                if execution_time > max_execution_time:
                    logger.warning(
                        f"Service operation exceeded max execution time: "
                        f"{operation_id} took {execution_time:.2f}s "
                        f"(max: {max_execution_time}s)"
                    )
                
                # Update idempotency record with result (if enabled)
                if enable_idempotency and idempotency_key:
                    IdempotencyService.check_and_record_operation(
                        operation_type=f"service_{service_name}",
                        idempotency_key=idempotency_key,
                        result_data={'result': result, 'success': True},
                        user=user
                    )
                
                # Audit logging (if enabled)
                if enable_audit:
                    AuditService.log_operation(
                        model_name=service_name,
                        object_id=idempotency_key or operation_id,
                        operation=func.__name__,
                        source_service=service_name,
                        user=user,
                        success=True,
                        execution_time=execution_time,
                        description=description
                    )
                
                logger.info(
                    f"Service operation completed: {operation_id} "
                    f"in {execution_time:.2f}s"
                )
                
                return result
                
            except Exception as e:
                execution_time = time.time() - start_time
                
                # Log error
                logger.error(
                    f"Service operation failed: {operation_id} - {str(e)}",
                    exc_info=True
                )
                
                # Audit logging for failure (if enabled)
                if enable_audit:
                    AuditService.log_operation(
                        model_name=service_name,
                        object_id=idempotency_key or operation_id,
                        operation=f"{func.__name__}_failed",
                        source_service=service_name,
                        user=user,
                        success=False,
                        error=str(e),
                        execution_time=execution_time,
                        description=description
                    )
                
                # Quarantine data if critical operation
                if critical:
                    try:
                        QuarantineService.quarantine_data(
                            model_name=service_name,
                            object_id=idempotency_key or operation_id,
                            corruption_type='service_failure',
                            details={
                                'operation': func.__name__,
                                'error': str(e),
                                'args': str(args)[:500],
                                'kwargs': str(kwargs)[:500],
                                'execution_time': execution_time
                            },
                            user=user
                        )
                    except Exception as quarantine_error:
                        logger.error(
                            f"Failed to quarantine failed operation: {quarantine_error}"
                        )
                
                # Re-raise the exception
                raise
        
        return wrapper
    return decorator


def _generate_idempotency_key(service_name: str, method_name: str, args: tuple, kwargs: dict) -> str:
    """
    Generate idempotency key from service call parameters.
    
    Args:
        service_name: Name of the service class
        method_name: Name of the method being called
        args: Positional arguments
        kwargs: Keyword arguments
    
    Returns:
        str: Idempotency key
    """
    # Skip first argument (self)
    relevant_args = args[1:] if len(args) > 1 else []
    
    # Extract IDs from arguments
    key_components = [service_name, method_name]
    
    for arg in relevant_args:
        if hasattr(arg, 'id'):
            key_components.append(str(arg.id))
        elif hasattr(arg, 'pk'):
            key_components.append(str(arg.pk))
        elif isinstance(arg, (int, str)):
            key_components.append(str(arg))
    
    # Add relevant kwargs
    for key, value in sorted(kwargs.items()):
        if key not in ['user', 'request']:  # Skip context objects
            if hasattr(value, 'id'):
                key_components.append(f"{key}:{value.id}")
            elif isinstance(value, (int, str, bool)):
                key_components.append(f"{key}:{value}")
    
    return ':'.join(key_components)


def _execute_with_retry(func: Callable, args: tuple, kwargs: dict, retry_count: int, operation_id: str) -> Any:
    """
    Execute function with retry logic for transient failures.
    
    Args:
        func: Function to execute
        args: Positional arguments
        kwargs: Keyword arguments
        retry_count: Number of retries
        operation_id: Operation identifier for logging
    
    Returns:
        Any: Function result
    
    Raises:
        Exception: If all retries fail
    """
    last_exception = None
    
    for attempt in range(retry_count + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            
            if attempt < retry_count:
                # Exponential backoff
                wait_time = 2 ** attempt
                logger.warning(
                    f"Service operation failed (attempt {attempt + 1}/{retry_count + 1}): "
                    f"{operation_id} - Retrying in {wait_time}s"
                )
                time.sleep(wait_time)
            else:
                # Final attempt failed
                logger.error(
                    f"Service operation failed after {retry_count + 1} attempts: "
                    f"{operation_id}"
                )
    
    # All retries exhausted
    raise last_exception
