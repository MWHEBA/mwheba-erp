"""
Governance system exceptions and error handling.
Provides structured error handling for all governance operations.
"""

class GovernanceError(Exception):
    """
    Base class for all governance-related errors.
    Provides structured error information with context.
    """
    def __init__(self, message: str, error_code: str = None, context: dict = None):
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.context = context or {}
        super().__init__(message)
    
    def __str__(self):
        return f"[{self.error_code}] {self.message}"
    
    def to_dict(self):
        """Convert error to dictionary for API responses"""
        return {
            'error_code': self.error_code,
            'message': self.message,
            'context': self.context
        }


class AuthorityViolationError(GovernanceError):
    """
    Raised when authority boundaries are violated.
    Indicates unauthorized access to protected resources.
    """
    def __init__(self, service: str, model: str, operation: str, context: dict = None):
        message = f"Service '{service}' is not authorized to perform '{operation}' on '{model}'"
        super().__init__(
            message=message,
            error_code="AUTHORITY_VIOLATION",
            context={
                'service': service,
                'model': model,
                'operation': operation,
                **(context or {})
            }
        )


class ValidationError(GovernanceError):
    """
    Raised when business rule validation fails.
    Indicates data or operation does not meet business requirements.
    """
    def __init__(self, message: str, field: str = None, value=None, context: dict = None):
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            context={
                'field': field,
                'value': value,
                **(context or {})
            }
        )


class ConcurrencyError(GovernanceError):
    """
    Raised when concurrency conflicts occur.
    Indicates race conditions or locking failures.
    """
    def __init__(self, message: str, resource: str = None, context: dict = None):
        super().__init__(
            message=message,
            error_code="CONCURRENCY_ERROR",
            context={
                'resource': resource,
                **(context or {})
            }
        )


class IdempotencyError(GovernanceError):
    """
    Raised when idempotency key conflicts occur.
    Indicates duplicate operation attempts.
    """
    def __init__(self, operation_type: str, idempotency_key: str, context: dict = None):
        message = f"Operation '{operation_type}' with key '{idempotency_key}' already exists"
        super().__init__(
            message=message,
            error_code="IDEMPOTENCY_ERROR",
            context={
                'operation_type': operation_type,
                'idempotency_key': idempotency_key,
                **(context or {})
            }
        )


class QuarantineError(GovernanceError):
    """
    Raised when data is quarantined due to corruption.
    Indicates data integrity issues requiring manual intervention.
    """
    def __init__(self, model: str, object_id: int, corruption_type: str, context: dict = None):
        message = f"Data quarantined: {model}#{object_id} - {corruption_type}"
        super().__init__(
            message=message,
            error_code="QUARANTINE_ERROR",
            context={
                'model': model,
                'object_id': object_id,
                'corruption_type': corruption_type,
                **(context or {})
            }
        )


class RepairError(GovernanceError):
    """
    Raised when data repair operations fail.
    Indicates issues during corruption repair attempts.
    """
    def __init__(self, repair_type: str, message: str, context: dict = None):
        super().__init__(
            message=f"Repair failed ({repair_type}): {message}",
            error_code="REPAIR_ERROR",
            context={
                'repair_type': repair_type,
                **(context or {})
            }
        )


class SignalError(GovernanceError):
    """
    Raised when signal processing fails.
    Indicates issues with signal chain management.
    """
    def __init__(self, signal_name: str, message: str, context: dict = None):
        super().__init__(
            message=f"Signal error ({signal_name}): {message}",
            error_code="SIGNAL_ERROR",
            context={
                'signal_name': signal_name,
                **(context or {})
            }
        )


class GatewayError(GovernanceError):
    """
    Raised when gateway operations fail.
    Indicates issues with centralized service gateways.
    """
    def __init__(self, gateway: str, operation: str, message: str, context: dict = None):
        super().__init__(
            message=f"Gateway error ({gateway}.{operation}): {message}",
            error_code="GATEWAY_ERROR",
            context={
                'gateway': gateway,
                'operation': operation,
                **(context or {})
            }
        )


class ConfigurationError(GovernanceError):
    """
    Raised when governance configuration is invalid.
    Indicates system setup or configuration issues.
    """
    def __init__(self, component: str, message: str, context: dict = None):
        super().__init__(
            message=f"Configuration error ({component}): {message}",
            error_code="CONFIGURATION_ERROR",
            context={
                'component': component,
                **(context or {})
            }
        )


class RollbackError(GovernanceError):
    """
    Raised when rollback operations fail.
    Indicates issues during governance state rollback.
    """
    def __init__(self, snapshot_id: str, message: str, context: dict = None):
        super().__init__(
            message=f"Rollback failed ({snapshot_id}): {message}",
            error_code="ROLLBACK_ERROR",
            context={
                'snapshot_id': snapshot_id,
                **(context or {})
            }
        )


class MonitoringError(GovernanceError):
    """
    Raised when monitoring operations fail.
    Indicates issues with governance monitoring and health checks.
    """
    def __init__(self, component: str, check_type: str, message: str, context: dict = None):
        super().__init__(
            message=f"Monitoring error ({component}.{check_type}): {message}",
            error_code="MONITORING_ERROR",
            context={
                'component': component,
                'check_type': check_type,
                **(context or {})
            }
        )


# Exception handling utilities

def handle_governance_error(error: GovernanceError, logger=None):
    """
    Standard error handling for governance exceptions.
    Logs error and returns structured response.
    """
    if logger:
        logger.error(f"Governance error: {error}", extra=error.context)
    
    return {
        'success': False,
        'error': error.to_dict()
    }


def safe_governance_operation(operation_func, logger=None, default_return=None):
    """
    Decorator/wrapper for safe governance operations.
    Catches and handles governance exceptions gracefully.
    """
    def wrapper(*args, **kwargs):
        try:
            return operation_func(*args, **kwargs)
        except GovernanceError as e:
            if logger:
                logger.error(f"Governance operation failed: {e}", extra=e.context)
            return default_return
        except Exception as e:
            # Convert unexpected exceptions to governance errors
            governance_error = GovernanceError(
                message=f"Unexpected error: {str(e)}",
                error_code="UNEXPECTED_ERROR",
                context={'original_exception': type(e).__name__}
            )
            if logger:
                logger.error(f"Unexpected governance error: {governance_error}", exc_info=True)
            return default_return
    
    return wrapper