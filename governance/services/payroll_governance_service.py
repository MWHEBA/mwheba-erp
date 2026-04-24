"""
Payroll Governance Service - Specialized governance for payroll operations.

This service provides payroll-specific governance functionality including:
- Payroll operation validation
- Payroll-specific feature flags
- Payroll audit trail management
- Payroll authority enforcement
- Payroll idempotency protection
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Dict, Any, List
from django.utils import timezone
from django.db import transaction
from django.contrib.auth import get_user_model

from .idempotency_service import IdempotencyService
from .audit_service import AuditService
from .authority_service import AuthorityService
from .governance_switchboard import governance_switchboard
from ..models import GovernanceContext
from ..exceptions import GovernanceError, AuthorityViolationError, ValidationError

User = get_user_model()
logger = logging.getLogger('governance.payroll_service')


class PayrollGovernanceService:
    """
    Specialized governance service for payroll operations.
    
    Provides comprehensive governance controls for all payroll-related operations
    including validation, authorization, audit trails, and idempotency protection.
    """
    
    # Payroll-specific feature flags
    PAYROLL_FEATURE_FLAGS = {
        'payroll_idempotency_enforcement': True,
        'payroll_authority_enforcement': True,
        'payroll_audit_trail_enforcement': True,
        'payroll_calculation_validation': True,
        'payroll_payment_validation': True,
        'advance_deduction_validation': True,
        'salary_component_validation': True,
        'payroll_batch_processing': True,
        'payroll_journal_entry_creation': True,
        'payroll_period_lock_enforcement': True,
    }
    
    @classmethod
    def is_payroll_feature_enabled(cls, feature_name: str) -> bool:
        """
        Check if a payroll-specific feature is enabled.
        
        Args:
            feature_name: Name of the feature to check
            
        Returns:
            bool: True if feature is enabled
        """
        # Check global governance switchboard first
        if not governance_switchboard.is_component_enabled('payroll_governance'):
            return False
        
        # Check payroll-specific feature flag
        return cls.PAYROLL_FEATURE_FLAGS.get(feature_name, False)
    
    @classmethod
    def validate_payroll_operation(
        cls,
        operation_type: str,
        payroll_data: Dict,
        user: User,
        source_service: str = "PayrollService"
    ) -> Dict[str, Any]:
        """
        Validate payroll operation with comprehensive governance checks.
        
        Args:
            operation_type: Type of operation (create, calculate, approve, pay)
            payroll_data: Payroll data to validate
            user: User performing the operation
            source_service: Service performing the operation
            
        Returns:
            dict: Validation result with status and details
        """
        validation_result = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'governance_checks': {}
        }
        
        try:
            # Authority validation
            if cls.is_payroll_feature_enabled('payroll_authority_enforcement'):
                try:
                    AuthorityService.validate_payroll_authority(
                        service_name=source_service,
                        operation=operation_type.upper(),
                        user=user
                    )
                    validation_result['governance_checks']['authority'] = 'passed'
                except AuthorityViolationError as e:
                    validation_result['valid'] = False
                    validation_result['errors'].append(f"Authority violation: {str(e)}")
                    validation_result['governance_checks']['authority'] = 'failed'
            
            # Business rule validation
            if cls.is_payroll_feature_enabled('payroll_calculation_validation'):
                business_validation = cls._validate_payroll_business_rules(
                    operation_type, payroll_data
                )
                validation_result['governance_checks']['business_rules'] = business_validation
                
                if not business_validation['valid']:
                    validation_result['valid'] = False
                    validation_result['errors'].extend(business_validation['errors'])
            
            # Idempotency check
            if cls.is_payroll_feature_enabled('payroll_idempotency_enforcement'):
                idempotency_key = cls._generate_payroll_idempotency_key(
                    operation_type, payroll_data
                )
                
                exists, record, result_data = IdempotencyService.check_operation_exists(
                    'payroll_operation', idempotency_key
                )
                
                if exists:
                    validation_result['warnings'].append(
                        f"Duplicate operation detected: {idempotency_key}"
                    )
                    validation_result['governance_checks']['idempotency'] = 'duplicate'
                    validation_result['existing_result'] = result_data
                else:
                    validation_result['governance_checks']['idempotency'] = 'new'
                    validation_result['idempotency_key'] = idempotency_key
            
            # Audit trail preparation
            if cls.is_payroll_feature_enabled('payroll_audit_trail_enforcement'):
                validation_result['governance_checks']['audit_trail'] = 'prepared'
                validation_result['audit_context'] = {
                    'operation_type': operation_type,
                    'user_id': user.id,
                    'source_service': source_service,
                    'timestamp': timezone.now().isoformat()
                }
            
        except Exception as e:
            logger.error(f"Payroll validation error: {e}", exc_info=True)
            validation_result['valid'] = False
            validation_result['errors'].append(f"Validation error: {str(e)}")
        
        return validation_result
    
    @classmethod
    def validate_payroll_payment_operation(
        cls,
        operation_type: str,
        payment_data: Dict,
        user: User,
        source_service: str = "PayrollPaymentService"
    ) -> Dict[str, Any]:
        """
        Validate payroll payment operation with governance checks.
        
        Args:
            operation_type: Type of operation (create, process, complete, cancel)
            payment_data: Payment data to validate
            user: User performing the operation
            source_service: Service performing the operation
            
        Returns:
            dict: Validation result with status and details
        """
        validation_result = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'governance_checks': {}
        }
        
        try:
            # Authority validation
            if cls.is_payroll_feature_enabled('payroll_authority_enforcement'):
                try:
                    AuthorityService.validate_payroll_payment_authority(
                        service_name=source_service,
                        operation=operation_type.upper(),
                        user=user
                    )
                    validation_result['governance_checks']['authority'] = 'passed'
                except AuthorityViolationError as e:
                    validation_result['valid'] = False
                    validation_result['errors'].append(f"Authority violation: {str(e)}")
                    validation_result['governance_checks']['authority'] = 'failed'
            
            # Payment validation
            if cls.is_payroll_feature_enabled('payroll_payment_validation'):
                payment_validation = cls._validate_payment_business_rules(
                    operation_type, payment_data
                )
                validation_result['governance_checks']['payment_rules'] = payment_validation
                
                if not payment_validation['valid']:
                    validation_result['valid'] = False
                    validation_result['errors'].extend(payment_validation['errors'])
            
            # Idempotency check
            if cls.is_payroll_feature_enabled('payroll_idempotency_enforcement'):
                idempotency_key = cls._generate_payment_idempotency_key(
                    operation_type, payment_data
                )
                
                exists, record, result_data = IdempotencyService.check_operation_exists(
                    'payroll_payment_operation', idempotency_key
                )
                
                if exists:
                    validation_result['warnings'].append(
                        f"Duplicate payment operation: {idempotency_key}"
                    )
                    validation_result['governance_checks']['idempotency'] = 'duplicate'
                    validation_result['existing_result'] = result_data
                else:
                    validation_result['governance_checks']['idempotency'] = 'new'
                    validation_result['idempotency_key'] = idempotency_key
        
        except Exception as e:
            logger.error(f"Payment validation error: {e}", exc_info=True)
            validation_result['valid'] = False
            validation_result['errors'].append(f"Payment validation error: {str(e)}")
        
        return validation_result
    
    @classmethod
    def validate_advance_operation(
        cls,
        operation_type: str,
        advance_data: Dict,
        user: User,
        source_service: str = "AdvanceService"
    ) -> Dict[str, Any]:
        """
        Validate advance operation with governance checks.
        
        Args:
            operation_type: Type of operation (create, approve, pay, deduct)
            advance_data: Advance data to validate
            user: User performing the operation
            source_service: Service performing the operation
            
        Returns:
            dict: Validation result with status and details
        """
        validation_result = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'governance_checks': {}
        }
        
        try:
            # Authority validation
            if cls.is_payroll_feature_enabled('payroll_authority_enforcement'):
                try:
                    AuthorityService.validate_advance_authority(
                        service_name=source_service,
                        operation=operation_type.upper(),
                        user=user
                    )
                    validation_result['governance_checks']['authority'] = 'passed'
                except AuthorityViolationError as e:
                    validation_result['valid'] = False
                    validation_result['errors'].append(f"Authority violation: {str(e)}")
                    validation_result['governance_checks']['authority'] = 'failed'
            
            # Advance validation
            if cls.is_payroll_feature_enabled('advance_deduction_validation'):
                advance_validation = cls._validate_advance_business_rules(
                    operation_type, advance_data
                )
                validation_result['governance_checks']['advance_rules'] = advance_validation
                
                if not advance_validation['valid']:
                    validation_result['valid'] = False
                    validation_result['errors'].extend(advance_validation['errors'])
        
        except Exception as e:
            logger.error(f"Advance validation error: {e}", exc_info=True)
            validation_result['valid'] = False
            validation_result['errors'].append(f"Advance validation error: {str(e)}")
        
        return validation_result
    
    @classmethod
    def create_payroll_audit_record(
        cls,
        payroll_instance,
        operation: str,
        user: User,
        before_data: Optional[Dict] = None,
        after_data: Optional[Dict] = None,
        source_service: str = "PayrollService"
    ) -> Optional[Any]:
        """
        Create comprehensive audit record for payroll operations.
        
        Args:
            payroll_instance: Payroll model instance
            operation: Operation performed
            user: User who performed the operation
            before_data: Data before operation
            after_data: Data after operation
            source_service: Service that performed the operation
            
        Returns:
            AuditTrail record or None if audit is disabled
        """
        if not cls.is_payroll_feature_enabled('payroll_audit_trail_enforcement'):
            return None
        
        return AuditService.log_payroll_operation(
            payroll_instance=payroll_instance,
            operation=operation,
            user=user,
            source_service=source_service,
            before_data=before_data,
            after_data=after_data
        )
    
    @classmethod
    def record_payroll_operation(
        cls,
        operation_type: str,
        idempotency_key: str,
        result_data: Dict,
        user: User
    ) -> bool:
        """
        Record successful payroll operation for idempotency protection.
        
        Args:
            operation_type: Type of operation
            idempotency_key: Unique operation key
            result_data: Operation result data
            user: User who performed the operation
            
        Returns:
            bool: True if recorded successfully
        """
        if not cls.is_payroll_feature_enabled('payroll_idempotency_enforcement'):
            return True
        
        try:
            is_duplicate, record = IdempotencyService.check_and_record_operation(
                operation_type='payroll_operation',
                idempotency_key=idempotency_key,
                result_data=result_data,
                user=user
            )
            return True
        except Exception as e:
            logger.error(f"Failed to record payroll operation: {e}")
            return False
    
    @classmethod
    def get_payroll_governance_status(cls) -> Dict[str, Any]:
        """
        Get comprehensive status of payroll governance system.
        
        Returns:
            dict: Detailed status information
        """
        status = {
            'enabled': governance_switchboard.is_component_enabled('payroll_governance'),
            'features': {},
            'statistics': {},
            'health': 'healthy'
        }
        
        # Feature status
        for feature, default_enabled in cls.PAYROLL_FEATURE_FLAGS.items():
            status['features'][feature] = cls.is_payroll_feature_enabled(feature)
        
        # Statistics
        try:
            status['statistics'] = AuthorityService.get_payroll_authority_statistics()
        except Exception as e:
            logger.error(f"Failed to get payroll statistics: {e}")
            status['statistics'] = {'error': str(e)}
            status['health'] = 'degraded'
        
        # Health checks
        disabled_features = [
            feature for feature, enabled in status['features'].items()
            if not enabled
        ]
        
        if disabled_features:
            status['health'] = 'warning'
            status['disabled_features'] = disabled_features
        
        return status
    
    # ============================================================================
    # PRIVATE HELPER METHODS
    # ============================================================================
    
    @classmethod
    def _validate_payroll_business_rules(
        cls,
        operation_type: str,
        payroll_data: Dict
    ) -> Dict[str, Any]:
        """Validate payroll-specific business rules."""
        validation = {'valid': True, 'errors': []}
        
        try:
            # Basic salary validation
            if 'basic_salary' in payroll_data:
                basic_salary = Decimal(str(payroll_data['basic_salary']))
                if basic_salary <= 0:
                    validation['valid'] = False
                    validation['errors'].append('Basic salary must be greater than zero')
            
            # Net salary validation
            if 'net_salary' in payroll_data:
                net_salary = Decimal(str(payroll_data['net_salary']))
                if net_salary < 0:
                    validation['valid'] = False
                    validation['errors'].append('Net salary cannot be negative')
            
            # Status transition validation
            if operation_type == 'approve' and payroll_data.get('status') != 'calculated':
                validation['valid'] = False
                validation['errors'].append('Can only approve calculated payrolls')
            
            if operation_type == 'pay' and payroll_data.get('status') != 'approved':
                validation['valid'] = False
                validation['errors'].append('Can only pay approved payrolls')
        
        except Exception as e:
            validation['valid'] = False
            validation['errors'].append(f'Business rule validation error: {str(e)}')
        
        return validation
    
    @classmethod
    def _validate_payment_business_rules(
        cls,
        operation_type: str,
        payment_data: Dict
    ) -> Dict[str, Any]:
        """Validate payment-specific business rules."""
        validation = {'valid': True, 'errors': []}
        
        try:
            # Amount validation
            if 'total_amount' in payment_data:
                total_amount = Decimal(str(payment_data['total_amount']))
                if total_amount <= 0:
                    validation['valid'] = False
                    validation['errors'].append('Payment amount must be greater than zero')
            
            # Payment method validation - النظام الجديد
            payment_method = payment_data.get('payment_method')
            if payment_method and not payment_data.get('bank_reference'):
                # التحقق من أن الحساب بنكي
                try:
                    from financial.models import ChartOfAccounts
                    account = ChartOfAccounts.objects.filter(code=payment_method).first()
                    if account and account.is_bank_account:
                        validation['valid'] = False
                        validation['errors'].append('Bank reference required for bank accounts')
                except Exception:
                    pass
            
            # Status validation
            if operation_type == 'complete' and payment_data.get('status') != 'processing':
                validation['valid'] = False
                validation['errors'].append('Can only complete processing payments')
        
        except Exception as e:
            validation['valid'] = False
            validation['errors'].append(f'Payment validation error: {str(e)}')
        
        return validation
    
    @classmethod
    def _validate_advance_business_rules(
        cls,
        operation_type: str,
        advance_data: Dict
    ) -> Dict[str, Any]:
        """Validate advance-specific business rules."""
        validation = {'valid': True, 'errors': []}
        
        try:
            # Amount validation
            if 'amount' in advance_data:
                amount = Decimal(str(advance_data['amount']))
                if amount <= 0:
                    validation['valid'] = False
                    validation['errors'].append('Advance amount must be greater than zero')
                
                if amount > Decimal('50000'):  # Maximum advance limit
                    validation['valid'] = False
                    validation['errors'].append('Advance amount exceeds maximum limit')
            
            # Installments validation
            if 'installments_count' in advance_data:
                installments = int(advance_data['installments_count'])
                if installments < 1 or installments > 24:
                    validation['valid'] = False
                    validation['errors'].append('Installments must be between 1 and 24')
        
        except Exception as e:
            validation['valid'] = False
            validation['errors'].append(f'Advance validation error: {str(e)}')
        
        return validation
    
    @classmethod
    def _generate_payroll_idempotency_key(
        cls,
        operation_type: str,
        payroll_data: Dict
    ) -> str:
        """Generate idempotency key for payroll operations."""
        employee_id = payroll_data.get('employee_id')
        month = payroll_data.get('month', timezone.now().strftime('%Y-%m'))
        
        return IdempotencyService.generate_payroll_key(
            employee_id=employee_id,
            month=month,
            event_type=operation_type
        )
    
    @classmethod
    def _generate_payment_idempotency_key(
        cls,
        operation_type: str,
        payment_data: Dict
    ) -> str:
        """Generate idempotency key for payment operations."""
        payment_reference = payment_data.get('payment_reference', 'unknown')
        
        return IdempotencyService.generate_payroll_payment_key(
            payment_reference=payment_reference,
            event_type=operation_type
        )


# Export main class
__all__ = ['PayrollGovernanceService']