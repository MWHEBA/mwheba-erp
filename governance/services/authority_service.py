"""
Authority service for managing service authority boundaries.
Ensures only authorized services can modify high-risk models.
"""

import logging
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from ..models import AuthorityDelegation, GovernanceContext
from ..exceptions import AuthorityViolationError, ValidationError
from ..thread_safety import monitor_operation

logger = logging.getLogger(__name__)


class AuthorityService:
    """
    Service for managing authority boundaries and delegations.
    Ensures only authorized services can modify high-risk models.
    """
    
    # Authority matrix defining which service owns which model
    AUTHORITY_MATRIX = {
        'JournalEntry': 'AccountingGateway',
        'JournalEntryLine': 'AccountingGateway',
        'Stock': 'MovementService',
        'StockMovement': 'MovementService',
        'CustomerPayment': 'CustomerService',
        'Sale': 'SaleService',
        'TransportationFee': 'TransportationService',
        'User': 'UserService',
        'Group': 'UserService',
        # ============================================================================
        # PAYROLL AUTHORITY BOUNDARIES
        # ============================================================================
        'Payroll': 'PayrollGateway',
        'PayrollLine': 'PayrollGateway',
        'PayrollPayment': 'PayrollPaymentService',
        'PayrollPaymentLine': 'PayrollPaymentService',
        'Advance': 'AdvanceService',
        'AdvanceInstallment': 'AdvanceService',
        'SalaryComponent': 'SalaryComponentService',
        'PayrollPeriod': 'PayrollPeriodService',
        'Contract': 'ContractService',
        'Employee': 'EmployeeService',
    }
    
    # Critical models that cannot be delegated during runtime
    CRITICAL_MODELS = [
        'JournalEntry',
        'JournalEntryLine', 
        'Stock',
        'StockMovement',
        # ============================================================================
        # PAYROLL CRITICAL MODELS
        # ============================================================================
        'Payroll',
        'PayrollPayment',
        'Advance',
    ]
    
    @classmethod
    def validate_authority(cls, service_name: str, model_name: str, operation: str,
                          user=None, **context):
        """
        Validate if a service has authority to perform an operation on a model.
        
        Args:
            service_name: Name of the service requesting access
            model_name: Name of the model being accessed
            operation: Operation being performed (CREATE, UPDATE, DELETE, etc.)
            user: User performing the operation
            **context: Additional context
            
        Returns:
            bool: True if authorized, raises AuthorityViolationError if not
        """
        with monitor_operation("authority_validation"):
            # Check if model is in authority matrix
            if model_name not in cls.AUTHORITY_MATRIX:
                logger.warning(f"Model not in authority matrix: {model_name}")
                return True  # Allow access to non-governed models
            
            # Get authoritative service
            authoritative_service = cls.AUTHORITY_MATRIX[model_name]
            
            # Check direct authority
            if service_name == authoritative_service:
                logger.debug(f"Direct authority granted: {service_name} → {model_name}")
                return True
            
            # Check for active delegation
            if cls.check_delegation(authoritative_service, service_name, model_name):
                logger.info(f"Delegated authority granted: {service_name} → {model_name}")
                return True
            
            # Authority violation
            logger.error(f"Authority violation: {service_name} attempted {operation} on {model_name}")
            
            # Log the violation
            from .audit_service import AuditService
            AuditService.log_authority_violation(
                model_name=model_name,
                attempted_operation=operation,
                user=user,
                violation_type='unauthorized_service',
                violation_details={
                    'service': service_name,
                    'model': model_name,
                    'operation': operation,
                    **context
                },
                source_service=service_name
            )
            
            raise AuthorityViolationError(
                service=service_name,
                model=model_name,
                operation=operation,
                context=context
            )
    
    @classmethod
    def get_authoritative_service(cls, model_name: str):
        """
        Get the authoritative service for a model.
        
        Args:
            model_name: Name of the model
            
        Returns:
            str: Name of the authoritative service, or None if not governed
        """
        return cls.AUTHORITY_MATRIX.get(model_name)
    
    @classmethod
    def delegate_authority(cls, from_service: str, to_service: str, model_name: str,
                          duration: timedelta, reason: str, user=None):
        """
        Delegate authority from one service to another.
        
        Args:
            from_service: Service delegating authority
            to_service: Service receiving authority
            model_name: Model for which authority is delegated
            duration: How long the delegation lasts
            reason: Reason for delegation
            user: User granting the delegation
            
        Returns:
            AuthorityDelegation: Created delegation record
        """
        # Get user from context if not provided
        if user is None:
            user = GovernanceContext.get_current_user()
            if user is None:
                raise ValidationError(
                    message="No user provided for authority delegation",
                    field="user"
                )
        
        # Validate user permissions
        if not user.is_superuser:
            raise ValidationError(
                message="Authority delegation requires superuser privileges",
                field="user",
                value=user.username
            )
        
        # Check if model is in authority matrix
        if model_name not in cls.AUTHORITY_MATRIX:
            raise ValidationError(
                message=f"Model '{model_name}' is not governed by authority system",
                field="model_name",
                value=model_name
            )
        
        # Verify from_service is authoritative
        authoritative_service = cls.AUTHORITY_MATRIX[model_name]
        if from_service != authoritative_service:
            raise ValidationError(
                message=f"Service '{from_service}' is not authoritative for '{model_name}'. Authoritative service is '{authoritative_service}'",
                field="from_service",
                value=from_service
            )
        
        # Check critical model restrictions
        if model_name in cls.CRITICAL_MODELS and not cls._is_maintenance_window():
            raise ValidationError(
                message=f"Cannot delegate critical model '{model_name}' authority during runtime",
                field="model_name",
                value=model_name
            )
        
        # Validate duration
        max_duration = timedelta(hours=24)
        if duration > max_duration:
            raise ValidationError(
                message=f"Delegation duration cannot exceed {max_duration}",
                field="duration",
                value=str(duration)
            )
        
        with monitor_operation("authority_delegation"):
            try:
                with transaction.atomic():
                    # Check for existing active delegation
                    existing = AuthorityDelegation.objects.filter(
                        from_service=from_service,
                        to_service=to_service,
                        model_name=model_name,
                        is_active=True,
                        expires_at__gt=timezone.now(),
                        revoked_at__isnull=True
                    ).first()
                    
                    if existing:
                        logger.warning(f"Active delegation already exists: {existing}")
                        return existing
                    
                    # Create delegation
                    delegation = AuthorityDelegation.objects.create(
                        from_service=from_service,
                        to_service=to_service,
                        model_name=model_name,
                        expires_at=timezone.now() + duration,
                        granted_by=user,
                        reason=reason,
                        is_active=True
                    )
                    
                    # Log the delegation
                    logger.critical(
                        f"Authority delegated: {from_service} → {to_service} "
                        f"for {model_name} by {user.username} "
                        f"reason: {reason}"
                    )
                    
                    # Audit the delegation
                    from .audit_service import AuditService
                    AuditService.log_operation(
                        model_name='AuthorityDelegation',
                        object_id=delegation.id,
                        operation='CREATE',
                        source_service='AuthorityService',
                        user=user,
                        after_data={
                            'from_service': from_service,
                            'to_service': to_service,
                            'model_name': model_name,
                            'duration': str(duration)
                        }
                    )
                    
                    return delegation
                    
            except Exception as e:
                logger.error(f"Failed to create authority delegation: {e}", exc_info=True)
                raise ValidationError(
                    message=f"Failed to create delegation: {str(e)}",
                    context={'error': str(e)}
                )
    
    @classmethod
    def revoke_delegation(cls, delegation_id: int, reason: str = "", user=None):
        """
        Revoke an authority delegation.
        
        Args:
            delegation_id: ID of the delegation to revoke
            reason: Reason for revocation
            user: User revoking the delegation
            
        Returns:
            AuthorityDelegation: Revoked delegation record
        """
        # Get user from context if not provided
        if user is None:
            user = GovernanceContext.get_current_user()
            if user is None:
                raise ValidationError(
                    message="No user provided for delegation revocation",
                    field="user"
                )
        
        with monitor_operation("authority_revocation"):
            try:
                with transaction.atomic():
                    delegation = AuthorityDelegation.objects.select_for_update().get(
                        id=delegation_id
                    )
                    
                    if not delegation.is_active or delegation.revoked_at:
                        logger.warning(f"Delegation already revoked: {delegation}")
                        return delegation
                    
                    # Revoke the delegation
                    delegation.revoke(user, reason)
                    
                    logger.info(f"Authority delegation revoked: {delegation}")
                    return delegation
                    
            except AuthorityDelegation.DoesNotExist:
                raise ValidationError(
                    message=f"Delegation with ID {delegation_id} not found",
                    field="delegation_id",
                    value=delegation_id
                )
    
    @classmethod
    def check_delegation(cls, from_service: str, to_service: str, model_name: str):
        """
        Check if there's a valid delegation between services for a model.
        
        Args:
            from_service: Authoritative service
            to_service: Service requesting access
            model_name: Model being accessed
            
        Returns:
            bool: True if valid delegation exists
        """
        return AuthorityDelegation.check_delegation(from_service, to_service, model_name)
    
    @classmethod
    def get_active_delegations(cls, service_name: str = None, model_name: str = None):
        """
        Get active delegations with optional filtering.
        
        Args:
            service_name: Filter by service (from or to)
            model_name: Filter by model
            
        Returns:
            QuerySet: Active delegation records
        """
        queryset = AuthorityDelegation.objects.filter(
            is_active=True,
            expires_at__gt=timezone.now(),
            revoked_at__isnull=True
        )
        
        if service_name:
            from django.db.models import Q
            queryset = queryset.filter(
                Q(from_service=service_name) | Q(to_service=service_name)
            )
        
        if model_name:
            queryset = queryset.filter(model_name=model_name)
        
        return queryset.order_by('-granted_at')
    
    @classmethod
    def cleanup_expired_delegations(cls):
        """
        Clean up expired delegations.
        Should be run periodically as a maintenance task.
        
        Returns:
            int: Number of delegations cleaned up
        """
        with monitor_operation("delegation_cleanup"):
            expired_delegations = AuthorityDelegation.objects.filter(
                is_active=True,
                expires_at__lt=timezone.now()
            )
            
            count = expired_delegations.count()
            if count > 0:
                expired_delegations.update(is_active=False)
                logger.info(f"Cleaned up {count} expired authority delegations")
            
            return count
    
    @classmethod
    def get_authority_statistics(cls):
        """
        Get authority system statistics.
        
        Returns:
            dict: Statistics about authority system
        """
        from django.db.models import Count
        
        stats = {}
        
        # Total governed models
        stats['governed_models'] = len(cls.AUTHORITY_MATRIX)
        stats['critical_models'] = len(cls.CRITICAL_MODELS)
        
        # Active delegations
        stats['active_delegations'] = AuthorityDelegation.objects.filter(
            is_active=True,
            expires_at__gt=timezone.now(),
            revoked_at__isnull=True
        ).count()
        
        # Delegations by model
        delegation_counts = AuthorityDelegation.objects.values('model_name').annotate(
            count=Count('id')
        ).order_by('-count')
        
        stats['delegations_by_model'] = {
            item['model_name']: item['count'] 
            for item in delegation_counts
        }
        
        # Recent violations (last 24 hours)
        from .audit_service import AuditService
        recent_violations = AuditService.get_authority_violations(hours=24)
        stats['recent_violations'] = recent_violations.count()
        
        return stats
    
    @classmethod
    def _is_maintenance_window(cls):
        """
        Check if we're currently in a maintenance window.
        During maintenance, critical model delegations are allowed.
        
        Returns:
            bool: True if in maintenance window
        """
        # This could be implemented based on:
        # - Time-based maintenance windows
        # - Feature flags
        # - Environment variables
        # For now, return False (no maintenance window)
        return False
    
    @classmethod
    def validate_startup_authority_matrix(cls):
        """
        Validate authority matrix configuration at startup.
        Ensures all required services are properly configured.
        
        Returns:
            list: List of validation errors, empty if valid
        """
        errors = []
        
        # Check that authority matrix is not empty
        if not cls.AUTHORITY_MATRIX:
            errors.append("Authority matrix is empty")
        
        # Check that all models have valid service names
        for model_name, service_name in cls.AUTHORITY_MATRIX.items():
            if not model_name or not isinstance(model_name, str):
                errors.append(f"Invalid model name: {model_name}")
            if not service_name or not isinstance(service_name, str):
                errors.append(f"Invalid service name for model '{model_name}': {service_name}")
        
        # Check critical models are in matrix
        for model in cls.CRITICAL_MODELS:
            if model not in cls.AUTHORITY_MATRIX:
                errors.append(f"Critical model '{model}' not in authority matrix")
        
        # Check that critical models list is not empty
        if not cls.CRITICAL_MODELS:
            errors.append("Critical models list is empty")
        
        # Validate that all critical models have authoritative services
        for model in cls.CRITICAL_MODELS:
            if model in cls.AUTHORITY_MATRIX:
                service = cls.AUTHORITY_MATRIX[model]
                if not service:
                    errors.append(f"Critical model '{model}' has empty authoritative service")
        
        # Log validation results
        if errors:
            logger.error(f"Authority matrix validation failed: {errors}")
        else:
            logger.info("Authority matrix validation passed")
            logger.debug(f"Governed models: {list(cls.AUTHORITY_MATRIX.keys())}")
            logger.debug(f"Authoritative services: {set(cls.AUTHORITY_MATRIX.values())}")
        
        return errors
    
    # ============================================================================
    # PAYROLL-SPECIFIC AUTHORITY METHODS
    # ============================================================================
    
    @classmethod
    def validate_payroll_authority(cls, service_name: str, operation: str, 
                                 payroll_instance=None, user=None, **context):
        """
        Validate authority for payroll operations with enhanced business rules.
        
        Args:
            service_name: Name of the service requesting access
            operation: Operation being performed
            payroll_instance: Payroll instance (if applicable)
            user: User performing the operation
            **context: Additional context
            
        Returns:
            bool: True if authorized, raises AuthorityViolationError if not
        """
        # Basic authority check
        cls.validate_authority(service_name, 'Payroll', operation, user, **context)
        
        # Additional payroll-specific business rules
        if payroll_instance:
            # Only allow modifications to draft payrolls
            if operation in ['UPDATE', 'DELETE'] and payroll_instance.status != 'draft':
                logger.error(f"Attempt to {operation} non-draft payroll: {payroll_instance.id}")
                raise AuthorityViolationError(
                    service=service_name,
                    model='Payroll',
                    operation=operation,
                    context={
                        'payroll_id': payroll_instance.id,
                        'payroll_status': payroll_instance.status,
                        'reason': 'Cannot modify non-draft payroll'
                    }
                )
            
            # Only PayrollPaymentService can mark payroll as paid
            if operation == 'PAY' and service_name != 'PayrollPaymentService':
                logger.error(f"Unauthorized payment attempt by {service_name}")
                raise AuthorityViolationError(
                    service=service_name,
                    model='Payroll',
                    operation=operation,
                    context={'reason': 'Only PayrollPaymentService can process payments'}
                )
        
        return True
    
    @classmethod
    def validate_payroll_payment_authority(cls, service_name: str, operation: str,
                                         payment_instance=None, user=None, **context):
        """
        Validate authority for payroll payment operations.
        
        Args:
            service_name: Name of the service requesting access
            operation: Operation being performed
            payment_instance: PayrollPayment instance (if applicable)
            user: User performing the operation
            **context: Additional context
            
        Returns:
            bool: True if authorized, raises AuthorityViolationError if not
        """
        # Basic authority check
        cls.validate_authority(service_name, 'PayrollPayment', operation, user, **context)
        
        # Additional payment-specific business rules
        if payment_instance:
            # Only allow modifications to pending payments
            if operation in ['UPDATE', 'DELETE'] and payment_instance.status != 'pending':
                logger.error(f"Attempt to {operation} non-pending payment: {payment_instance.id}")
                raise AuthorityViolationError(
                    service=service_name,
                    model='PayrollPayment',
                    operation=operation,
                    context={
                        'payment_id': payment_instance.id,
                        'payment_status': payment_instance.status,
                        'reason': 'Cannot modify non-pending payment'
                    }
                )
            
            # Only authorized services can complete payments
            if operation == 'COMPLETE' and service_name not in ['PayrollPaymentService', 'BankIntegrationService']:
                logger.error(f"Unauthorized payment completion by {service_name}")
                raise AuthorityViolationError(
                    service=service_name,
                    model='PayrollPayment',
                    operation=operation,
                    context={'reason': 'Unauthorized payment completion service'}
                )
        
        return True
    
    @classmethod
    def validate_advance_authority(cls, service_name: str, operation: str,
                                 advance_instance=None, user=None, **context):
        """
        Validate authority for advance operations.
        
        Args:
            service_name: Name of the service requesting access
            operation: Operation being performed
            advance_instance: Advance instance (if applicable)
            user: User performing the operation
            **context: Additional context
            
        Returns:
            bool: True if authorized, raises AuthorityViolationError if not
        """
        # Basic authority check
        cls.validate_authority(service_name, 'Advance', operation, user, **context)
        
        # Additional advance-specific business rules
        if advance_instance:
            # Only allow modifications to pending advances
            if operation in ['UPDATE', 'DELETE'] and advance_instance.status not in ['pending', 'approved']:
                logger.error(f"Attempt to {operation} processed advance: {advance_instance.id}")
                raise AuthorityViolationError(
                    service=service_name,
                    model='Advance',
                    operation=operation,
                    context={
                        'advance_id': advance_instance.id,
                        'advance_status': advance_instance.status,
                        'reason': 'Cannot modify processed advance'
                    }
                )
            
            # Only PayrollService can deduct installments
            if operation == 'DEDUCT_INSTALLMENT' and service_name != 'PayrollService':
                logger.error(f"Unauthorized installment deduction by {service_name}")
                raise AuthorityViolationError(
                    service=service_name,
                    model='Advance',
                    operation=operation,
                    context={'reason': 'Only PayrollService can deduct installments'}
                )
        
        return True
    
    @classmethod
    def validate_salary_component_authority(cls, service_name: str, operation: str,
                                          component_instance=None, user=None, **context):
        """
        Validate authority for salary component operations.
        
        Args:
            service_name: Name of the service requesting access
            operation: Operation being performed
            component_instance: SalaryComponent instance (if applicable)
            user: User performing the operation
            **context: Additional context
            
        Returns:
            bool: True if authorized, raises AuthorityViolationError if not
        """
        # Basic authority check
        cls.validate_authority(service_name, 'SalaryComponent', operation, user, **context)
        
        # Additional component-specific business rules
        if component_instance:
            # Only allow modifications to active components
            if operation in ['UPDATE', 'TERMINATE'] and not component_instance.is_active:
                logger.error(f"Attempt to {operation} inactive component: {component_instance.id}")
                raise AuthorityViolationError(
                    service=service_name,
                    model='SalaryComponent',
                    operation=operation,
                    context={
                        'component_id': component_instance.id,
                        'is_active': component_instance.is_active,
                        'reason': 'Cannot modify inactive salary component'
                    }
                )
            
            # Only PayrollService can use components in payroll calculation
            if operation == 'CALCULATE' and service_name != 'PayrollService':
                logger.error(f"Unauthorized component calculation by {service_name}")
                raise AuthorityViolationError(
                    service=service_name,
                    model='SalaryComponent',
                    operation=operation,
                    context={'reason': 'Only PayrollService can calculate components'}
                )
        
        return True
    
    @classmethod
    def get_payroll_authority_statistics(cls):
        """
        Get payroll-specific authority system statistics.
        
        Returns:
            dict: Statistics about payroll authority system
        """
        base_stats = cls.get_authority_statistics()
        
        # Add payroll-specific statistics
        payroll_models = [
            'Payroll', 'PayrollLine', 'PayrollPayment', 'PayrollPaymentLine',
            'Advance', 'AdvanceInstallment', 'SalaryComponent', 'PayrollPeriod',
            'Contract', 'Employee'
        ]
        
        payroll_stats = {
            'payroll_models_count': len(payroll_models),
            'payroll_critical_models': [m for m in payroll_models if m in cls.CRITICAL_MODELS],
            'payroll_services': list(set([
                cls.AUTHORITY_MATRIX.get(model) for model in payroll_models
                if cls.AUTHORITY_MATRIX.get(model)
            ]))
        }
        
        # Get payroll-specific delegations
        from django.db.models import Q
        payroll_delegations = AuthorityDelegation.objects.filter(
            Q(model_name__in=payroll_models),
            is_active=True,
            expires_at__gt=timezone.now(),
            revoked_at__isnull=True
        ).count()
        
        payroll_stats['active_payroll_delegations'] = payroll_delegations
        
        # Merge with base stats
        base_stats.update(payroll_stats)
        return base_stats