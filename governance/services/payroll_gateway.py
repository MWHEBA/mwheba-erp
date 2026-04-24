"""
PayrollGateway - Thread-Safe Central Gateway for Payroll Operations

This service is the single entry point for creating and managing payroll records in the system.
It provides thread-safe operations, full validation, and integration with the governance
infrastructure to prevent duplicate payrolls and ensure data integrity.

Key Features:
- Thread-safe payroll creation with proper locking
- Salary component calculation with validation
- Idempotency protection using specific key format: PAYROLL:{employee_id}:{year}:{month}:{event_type}
- Integration with AccountingGateway for journal entry creation
- Advance deduction coordination with proper locking
- Support for Payroll → JournalEntry workflow

Usage:
    gateway = PayrollGateway()
    payroll = gateway.create_payroll(
        employee_id=123,
        month=date(2024, 1, 1),
        idempotency_key='PAYROLL:123:2024:01:create',
        user=request.user
    )
"""

import logging
from decimal import Decimal
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from calendar import monthrange

from django.db import transaction, connection
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.apps import apps
from django.db.models import Q, Sum

from ..models import IdempotencyRecord, AuditTrail, GovernanceContext
from ..exceptions import (
    GovernanceError, AuthorityViolationError, ValidationError as GovValidationError,
    ConcurrencyError, IdempotencyError
)
from ..thread_safety import DatabaseLockManager, IdempotencyLock, monitor_operation
from .idempotency_service import IdempotencyService
from .audit_service import AuditService
from .authority_service import AuthorityService
from .accounting_gateway import AccountingGateway, JournalEntryLineData

# Import HR models
from hr.models import Payroll, PayrollLine, Employee, Contract, SalaryComponent, Advance, AdvanceInstallment
# Lazy import to avoid circular dependency
# from hr.services.advance_service import AdvanceService

User = get_user_model()
logger = logging.getLogger(__name__)


@dataclass
class PayrollData:
    """Data structure for payroll creation information"""
    employee_id: int
    month: date
    contract_id: Optional[int] = None
    notes: str = ""
    payment_method: str = 'bank_transfer'
    
    def __post_init__(self):
        """Validate payroll data after initialization"""
        if self.employee_id <= 0:
            raise ValueError("Employee ID must be positive")
        if not isinstance(self.month, date):
            raise ValueError("Month must be a date object")
        if self.payment_method not in ['bank_transfer', 'cash']:
            raise ValueError("Payment method must be 'bank_transfer' or 'cash'")


@dataclass
class SalaryComponentData:
    """Data structure for salary component information"""
    component_code: str
    component_type: str  # 'earning' or 'deduction'
    amount: Decimal
    description: str = ""
    is_taxable: bool = True
    
    def __post_init__(self):
        """Validate component data after initialization"""
        if not self.component_code:
            raise ValueError("Component code is required")
        if self.component_type not in ['earning', 'deduction']:
            raise ValueError("Component type must be 'earning' or 'deduction'")
        if self.amount < 0:
            raise ValueError("Component amount must be non-negative")


class PayrollGateway:
    """
    Thread-safe central gateway for all payroll operations.
    
    This class enforces the single entry point pattern for payroll creation,
    ensuring data integrity, proper validation, and audit trail creation.
    """
    
    # Supported payroll operations
    SUPPORTED_OPERATIONS = {
        'create', 'calculate', 'approve', 'pay', 'cancel'
    }
    
    # High-priority payroll workflows that require strict validation
    HIGH_PRIORITY_WORKFLOWS = {
        'monthly_payroll',
        'bonus_payroll',
        'advance_deduction'
    }
    
    def __init__(self):
        """Initialize the PayrollGateway with required services"""
        self.idempotency_service = IdempotencyService
        self.audit_service = AuditService
        self.authority_service = AuthorityService
        self.accounting_gateway = AccountingGateway()
        # Lazy import to avoid circular dependency
        from hr.services.advance_service import AdvanceService
        self.advance_service = AdvanceService()
    
    def create_payroll(
        self,
        employee_id: int,
        month: date,
        idempotency_key: str,
        user: User,
        contract_id: Optional[int] = None,
        notes: str = "",
        payment_method: str = 'bank_transfer',
        workflow_type: str = 'monthly_payroll'
    ) -> Payroll:
        """
        Create a payroll record with full validation and thread-safety.
        
        This is the main entry point for creating payroll records. It enforces
        all governance rules, validates data integrity, and ensures thread-safe
        operation with proper locking.
        
        Args:
            employee_id: ID of the employee
            month: Payroll month as date object
            idempotency_key: Unique key to prevent duplicate operations
            user: User creating the payroll
            contract_id: Optional specific contract ID (auto-determined if not provided)
            notes: Optional notes
            payment_method: Payment method ('bank_transfer' or 'cash')
            workflow_type: Type of payroll workflow
            
        Returns:
            Payroll: The created payroll record with status 'calculated'
            
        Raises:
            AuthorityViolationError: If service lacks authority
            ValidationError: If validation fails
            IdempotencyError: If idempotency check fails
            ConcurrencyError: If concurrency conflict occurs
        """
        operation_start = timezone.now()
        
        try:
            with monitor_operation("payroll_gateway_create_payroll"):
                # Set governance context
                GovernanceContext.set_context(
                    user=user,
                    service='PayrollGateway',
                    operation='create_payroll'
                )
                
                # Validate authority
                self._validate_authority('create')
                
                # Validate payroll data
                payroll_data = PayrollData(
                    employee_id=employee_id,
                    month=month,
                    contract_id=contract_id,
                    notes=notes,
                    payment_method=payment_method
                )
                
                # Check idempotency
                is_duplicate, existing_record, existing_data = self.idempotency_service.check_and_record_operation(
                    operation_type='payroll_operation',
                    idempotency_key=idempotency_key,
                    result_data={},  # Will be updated after creation
                    user=user,
                    expires_in_hours=24
                )
                
                if is_duplicate:
                    logger.info(f"Duplicate payroll creation detected: {idempotency_key}")
                    # Return existing payroll
                    payroll_id = existing_data.get('payroll_id')
                    if payroll_id:
                        return Payroll.objects.get(id=payroll_id)
                    else:
                        raise IdempotencyError(
                            operation_type='payroll_operation',
                            idempotency_key=idempotency_key,
                            context={'error': 'Existing record found but no payroll ID'}
                        )
                
                # Create payroll with thread-safe transaction
                payroll = self._create_payroll_atomic(
                    payroll_data=payroll_data,
                    idempotency_key=idempotency_key,
                    user=user,
                    workflow_type=workflow_type
                )
                
                # Update idempotency record with result
                existing_record.result_data = {
                    'payroll_id': payroll.id,
                    'employee_id': payroll.employee.id,
                    'employee_name': payroll.employee.get_full_name_ar(),
                    'month': payroll.month.isoformat(),
                    'gross_salary': str(payroll.gross_salary),
                    'net_salary': str(payroll.net_salary),
                    'status': payroll.status,
                    'created_at': payroll.created_at.isoformat()
                }
                existing_record.save()
                
                # Create audit trail
                self.audit_service.log_payroll_operation(
                    payroll_instance=payroll,
                    operation='CREATE',
                    user=user,
                    source_service='PayrollGateway',
                    additional_context={
                        'workflow_type': workflow_type,
                        'idempotency_key': idempotency_key,
                        'operation_duration': (timezone.now() - operation_start).total_seconds()
                    }
                )
                
                logger.info(
                    f"Payroll created successfully: {payroll.employee.get_full_name_ar()} "
                    f"for {payroll.month.strftime('%Y-%m')} - Net: {payroll.net_salary}"
                )
                
                return payroll
                
        except Exception as e:
            logger.error(
                f"Failed to create payroll for employee {employee_id} "
                f"month {month.strftime('%Y-%m')}: {str(e)}"
            )
            
            # Create audit trail for failure
            self.audit_service.log_operation(
                model_name='Payroll',
                object_id=0,  # No payroll created
                operation='CREATE_FAILED',
                user=user,
                source_service='PayrollGateway',
                additional_context={
                    'error': str(e),
                    'employee_id': employee_id,
                    'month': month.isoformat(),
                    'idempotency_key': idempotency_key,
                    'workflow_type': workflow_type
                }
            )
            
            raise
        
        finally:
            GovernanceContext.clear_context()
    
    def _create_payroll_atomic(
        self,
        payroll_data: PayrollData,
        idempotency_key: str,
        user: User,
        workflow_type: str
    ) -> Payroll:
        """
        Create payroll within atomic transaction with proper locking.
        
        This method handles the actual database operations with appropriate
        locking mechanisms for thread safety.
        """
        with DatabaseLockManager.atomic_operation():
            # Get and validate employee
            employee = self._get_and_validate_employee(payroll_data.employee_id)
            
            # Get active contract
            contract = self._get_active_contract(employee, payroll_data.month, payroll_data.contract_id)
            
            # Check for existing payroll
            self._check_existing_payroll(employee, payroll_data.month)
            
            # Get salary components
            salary_components = self._get_salary_components(employee, payroll_data.month)
            
            # Calculate salary components with thread-safe operations
            calculated_components = self._calculate_salary_components_atomic(
                employee, payroll_data.month, salary_components, contract
            )
            
            # Create payroll record
            payroll = Payroll(
                employee=employee,
                month=payroll_data.month,
                contract=contract,
                basic_salary=calculated_components['basic_salary'],
                allowances=calculated_components['allowances'],
                overtime_amount=calculated_components['overtime_amount'],
                bonus=calculated_components['bonus'],
                social_insurance=calculated_components['social_insurance'],
                tax=calculated_components['tax'],
                absence_deduction=calculated_components['absence_deduction'],
                late_deduction=calculated_components['late_deduction'],
                advance_deduction=calculated_components['advance_deduction'],
                other_deductions=calculated_components['other_deductions'],
                gross_salary=calculated_components['gross_salary'],
                total_additions=calculated_components['total_additions'],
                total_deductions=calculated_components['total_deductions'],
                net_salary=calculated_components['net_salary'],
                status='calculated',
                payment_method=payroll_data.payment_method,
                notes=payroll_data.notes,
                processed_by=user,
                processed_at=timezone.now()
            )
            
            # Mark as gateway approved to avoid development warnings
            payroll._gateway_approved = True
            payroll.save()
            
            # Create payroll lines for detailed breakdown
            self._create_payroll_lines(payroll, calculated_components['component_details'])
            
            # Process advance deductions with proper locking
            if calculated_components['advance_deduction'] > 0:
                self._process_advance_deductions_atomic(payroll, calculated_components['advance_details'])
            
            # Final validation of complete payroll
            self._validate_complete_payroll(payroll)
            
            return payroll
    
    def _validate_authority(self, operation: str) -> None:
        """
        Validate that PayrollGateway has authority for payroll operations.
        
        Args:
            operation: Operation type ('create', 'approve', 'pay', etc.)
            
        Raises:
            AuthorityViolationError: If authority validation fails
        """
        if operation not in self.SUPPORTED_OPERATIONS:
            raise AuthorityViolationError(
                message=f"Unsupported payroll operation: {operation}",
                error_code="UNSUPPORTED_OPERATION",
                context={'operation': operation, 'supported': list(self.SUPPORTED_OPERATIONS)}
            )
        
        # Check if this service has authority for Payroll operations
        if not self.authority_service.validate_authority(
            service_name='PayrollGateway',
            model_name='Payroll',
            operation=operation.upper()
        ):
            raise AuthorityViolationError(
                message="PayrollGateway lacks authority for Payroll operations",
                error_code="AUTHORITY_VIOLATION",
                context={
                    'service': 'PayrollGateway',
                    'model': 'Payroll',
                    'operation': operation.upper()
                }
            )
    
    def _get_and_validate_employee(self, employee_id: int) -> Employee:
        """
        Get and validate employee with thread-safe operations.
        
        Args:
            employee_id: Employee ID
            
        Returns:
            Employee: Validated employee instance
            
        Raises:
            ValidationError: If employee validation fails
        """
        try:
            # Use select_for_update for thread safety where supported
            if connection.vendor == 'postgresql':
                employee = Employee.objects.select_for_update().get(id=employee_id)
            else:
                employee = Employee.objects.get(id=employee_id)
            
            # Validate employee is active
            if not employee.is_active:
                raise GovValidationError(
                    message=f"Employee is not active: {employee.get_full_name_ar()}",
                    context={'employee_id': employee_id, 'is_active': employee.is_active}
                )
            
            return employee
            
        except Employee.DoesNotExist:
            raise GovValidationError(
                message=f"Employee not found: {employee_id}",
                context={'employee_id': employee_id}
            )
    
    def _get_active_contract(self, employee: Employee, month: date, contract_id: Optional[int] = None) -> Contract:
        """
        Get active contract for employee with validation.
        
        Args:
            employee: Employee instance
            month: Payroll month
            contract_id: Optional specific contract ID
            
        Returns:
            Contract: Active contract
            
        Raises:
            ValidationError: If no active contract found
        """
        if contract_id:
            try:
                contract = Contract.objects.get(id=contract_id, employee=employee)
                if contract.status != 'active':
                    raise GovValidationError(
                        message=f"Specified contract is not active: {contract_id}",
                        context={'contract_id': contract_id, 'status': contract.status}
                    )
                return contract
            except Contract.DoesNotExist:
                raise GovValidationError(
                    message=f"Contract not found: {contract_id}",
                    context={'contract_id': contract_id, 'employee_id': employee.id}
                )
        
        # Get active contract for the month
        contract = employee.contracts.filter(
            status='active',
            start_date__lte=month
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=month)
        ).first()
        
        if not contract:
            raise GovValidationError(
                message=f"No active contract found for employee {employee.get_full_name_ar()} in {month.strftime('%Y-%m')}",
                context={
                    'employee_id': employee.id,
                    'month': month.isoformat(),
                    'active_contracts': employee.contracts.filter(status='active').count()
                }
            )
        
        return contract
    
    def _check_existing_payroll(self, employee: Employee, month: date) -> None:
        """
        Check if payroll already exists for employee and month.
        
        Args:
            employee: Employee instance
            month: Payroll month
            
        Raises:
            ValidationError: If payroll already exists
        """
        existing_payroll = Payroll.objects.filter(
            employee=employee,
            month=month
        ).first()
        
        if existing_payroll:
            raise GovValidationError(
                message=f"Payroll already exists for {employee.get_full_name_ar()} in {month.strftime('%Y-%m')}",
                context={
                    'employee_id': employee.id,
                    'month': month.isoformat(),
                    'existing_payroll_id': existing_payroll.id,
                    'existing_status': existing_payroll.status
                }
            )
    
    def _get_salary_components(self, employee: Employee, month: date) -> List[SalaryComponent]:
        """
        Get active salary components for employee and month.
        
        Args:
            employee: Employee instance
            month: Payroll month
            
        Returns:
            List[SalaryComponent]: Active salary components
            
        Raises:
            ValidationError: If no salary components found
        """
        # Calculate month end date for component validation
        last_day = monthrange(month.year, month.month)[1]
        month_end_date = month.replace(day=last_day)
        
        components = employee.salary_components.filter(
            is_active=True,
            effective_from__lte=month_end_date
        ).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gte=month)
        ).order_by('component_type', 'order')
        
        if not components.exists():
            raise GovValidationError(
                message=f"No active salary components found for {employee.get_full_name_ar()}",
                context={
                    'employee_id': employee.id,
                    'month': month.isoformat(),
                    'total_components': employee.salary_components.count(),
                    'active_components': employee.salary_components.filter(is_active=True).count()
                }
            )
        
        return list(components)
    
    def _calculate_salary_components_atomic(
        self,
        employee: Employee,
        month: date,
        salary_components: List[SalaryComponent],
        contract: Contract
    ) -> Dict[str, Any]:
        """
        Calculate salary components with thread-safe operations.
        
        This method performs all salary calculations with proper locking
        to ensure thread safety and data consistency.
        
        Args:
            employee: Employee instance
            month: Payroll month
            salary_components: List of salary components
            contract: Active contract
            
        Returns:
            Dict: Calculated salary components and totals
        """
        from decimal import Decimal, ROUND_HALF_UP
        
        # Initialize calculation results
        calculations = {
            'basic_salary': Decimal('0'),
            'allowances': Decimal('0'),
            'overtime_amount': Decimal('0'),
            'bonus': Decimal('0'),
            'social_insurance': Decimal('0'),
            'tax': Decimal('0'),
            'absence_deduction': Decimal('0'),
            'late_deduction': Decimal('0'),
            'advance_deduction': Decimal('0'),
            'other_deductions': Decimal('0'),
            'component_details': [],
            'advance_details': []
        }
        
        # Process each salary component
        for component in salary_components:
            component_amount = self._calculate_component_amount(component, employee, month, contract)
            
            # Add to appropriate category
            if component.component_type == 'earning':
                if component.code == 'BASIC_SALARY':
                    calculations['basic_salary'] += component_amount
                elif component.code in ['ALLOWANCE', 'HOUSING_ALLOWANCE', 'TRANSPORT_ALLOWANCE']:
                    calculations['allowances'] += component_amount
                elif component.code == 'OVERTIME':
                    calculations['overtime_amount'] += component_amount
                elif component.code == 'BONUS':
                    calculations['bonus'] += component_amount
            elif component.component_type == 'deduction':
                if component.code == 'SOCIAL_INSURANCE':
                    calculations['social_insurance'] += component_amount
                elif component.code == 'TAX':
                    calculations['tax'] += component_amount
                elif component.code == 'ABSENCE':
                    calculations['absence_deduction'] += component_amount
                elif component.code == 'LATE':
                    calculations['late_deduction'] += component_amount
                else:
                    calculations['other_deductions'] += component_amount
            
            # Store component details for payroll lines
            calculations['component_details'].append({
                'component': component,
                'amount': component_amount,
                'description': f"{component.name} - {month.strftime('%Y-%m')}"
            })
        
        # Calculate advance deductions with thread-safe operations
        advance_deduction, advance_details = self._calculate_advance_deductions_atomic(employee, month)
        calculations['advance_deduction'] = advance_deduction
        calculations['advance_details'] = advance_details
        
        # Calculate totals with proper rounding
        calculations['gross_salary'] = (calculations['basic_salary'] + calculations['allowances']).quantize(
            Decimal('1'), rounding=ROUND_HALF_UP
        )
        calculations['total_additions'] = (calculations['overtime_amount'] + calculations['bonus']).quantize(
            Decimal('1'), rounding=ROUND_HALF_UP
        )
        calculations['total_deductions'] = (
            calculations['social_insurance'] +
            calculations['tax'] +
            calculations['absence_deduction'] +
            calculations['late_deduction'] +
            calculations['advance_deduction'] +
            calculations['other_deductions']
        ).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        
        calculations['net_salary'] = (
            calculations['gross_salary'] +
            calculations['total_additions'] -
            calculations['total_deductions']
        ).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        
        # Validate net salary is not negative
        if calculations['net_salary'] < 0:
            logger.warning(
                f"Negative net salary calculated for {employee.get_full_name_ar()}: {calculations['net_salary']}"
            )
        
        return calculations
    
    def _calculate_component_amount(
        self,
        component: SalaryComponent,
        employee: Employee,
        month: date,
        contract: Contract
    ) -> Decimal:
        """
        Calculate individual component amount with business logic.
        
        Args:
            component: Salary component
            employee: Employee instance
            month: Payroll month
            contract: Active contract
            
        Returns:
            Decimal: Calculated component amount
        """
        from decimal import Decimal
        
        base_amount = component.amount
        
        # Apply calculation logic based on component type
        if component.calculation_method == 'fixed':
            return base_amount
        elif component.calculation_method == 'percentage':
            # Calculate percentage of basic salary
            basic_salary = contract.basic_salary or Decimal('0')
            return (basic_salary * base_amount / 100).quantize(Decimal('0.01'))
        elif component.calculation_method == 'formula':
            # Apply custom formula (simplified implementation)
            return self._apply_component_formula(component, employee, month, contract)
        else:
            return base_amount
    
    def _apply_component_formula(
        self,
        component: SalaryComponent,
        employee: Employee,
        month: date,
        contract: Contract
    ) -> Decimal:
        """
        Apply custom formula for component calculation.
        
        This is a simplified implementation. In a real system, this would
        include more complex business logic for different component types.
        
        Args:
            component: Salary component
            employee: Employee instance
            month: Payroll month
            contract: Active contract
            
        Returns:
            Decimal: Calculated amount
        """
        from decimal import Decimal
        
        # Simplified formula application
        if component.code == 'OVERTIME':
            # Calculate overtime based on hours worked (if available)
            # This would integrate with attendance system
            return Decimal('0')  # Placeholder
        elif component.code == 'ABSENCE':
            # Calculate absence deduction based on days
            # This would integrate with attendance system
            return Decimal('0')  # Placeholder
        else:
            return component.amount
    
    def _calculate_advance_deductions_atomic(self, employee: Employee, month: date) -> Tuple[Decimal, List[Dict]]:
        """
        Calculate advance deductions with thread-safe operations.
        
        Args:
            employee: Employee instance
            month: Payroll month
            
        Returns:
            Tuple[Decimal, List[Dict]]: Total deduction amount and advance details
        """
        from decimal import Decimal
        
        # Get advances that need deduction in this month
        advances_for_deduction = Advance.objects.filter(
            employee=employee,
            status__in=['paid', 'in_progress'],
            deduction_start_month__lte=month,
            remaining_amount__gt=0
        ).order_by('deduction_start_month')
        
        total_deduction = Decimal('0')
        advance_details = []
        
        for advance in advances_for_deduction:
            # Check if installment already exists for this month
            existing_installment = AdvanceInstallment.objects.filter(
                advance=advance,
                month=month
            ).first()
            
            if existing_installment:
                # Already processed this month
                continue
            
            # Calculate installment amount
            installment_amount = advance.get_next_installment_amount()
            if installment_amount > 0:
                total_deduction += installment_amount
                advance_details.append({
                    'advance': advance,
                    'installment_amount': installment_amount,
                    'installment_number': advance.paid_installments + 1
                })
        
        return total_deduction, advance_details
    
    def _create_payroll_lines(self, payroll: Payroll, component_details: List[Dict]) -> None:
        """
        Create detailed payroll lines for salary components.
        
        Args:
            payroll: Payroll instance
            component_details: List of component details
        """
        for detail in component_details:
            component = detail['component']
            amount = detail['amount']
            description = detail['description']
            
            if amount > 0:  # Only create lines for non-zero amounts
                PayrollLine.objects.create(
                    payroll=payroll,
                    code=component.code,
                    name=component.name,
                    component_type=component.component_type,
                    amount=amount,
                    salary_component=component
                )
    
    def _process_advance_deductions_atomic(self, payroll: Payroll, advance_details: List[Dict]) -> None:
        """
        Process advance deductions with thread-safe operations and proper coordination.
        
        This method implements advance deduction coordination by:
        - Creating advance installment records
        - Updating advance status with proper locking
        - Coordinating with advance service for consistency
        
        Args:
            payroll: Payroll instance
            advance_details: List of advance deduction details
        """
        for detail in advance_details:
            advance = detail['advance']
            installment_amount = detail['installment_amount']
            installment_number = detail['installment_number']
            
            # Create advance installment record with proper coordination
            installment = self._create_advance_installment_atomic(
                advance=advance,
                payroll=payroll,
                installment_amount=installment_amount,
                installment_number=installment_number
            )
            
            # Update advance status with thread-safe operations
            self._update_advance_status_atomic(advance, installment_amount)
            
            # Coordinate with advance service for consistency
            self._coordinate_advance_deduction(advance, installment, payroll)
    
    def _create_advance_installment_atomic(
        self,
        advance: Advance,
        payroll: Payroll,
        installment_amount: Decimal,
        installment_number: int
    ) -> AdvanceInstallment:
        """
        Create advance installment record with atomic operations.
        
        Args:
            advance: Advance instance
            payroll: Payroll instance
            installment_amount: Installment amount
            installment_number: Installment number
            
        Returns:
            AdvanceInstallment: Created installment record
        """
        # Check for existing installment to prevent duplicates
        existing_installment = AdvanceInstallment.objects.filter(
            advance=advance,
            month=payroll.month
        ).first()
        
        if existing_installment:
            logger.warning(
                f"Advance installment already exists for advance {advance.id} "
                f"in month {payroll.month.strftime('%Y-%m')}"
            )
            return existing_installment
        
        # Create new installment record
        installment = AdvanceInstallment.objects.create(
            advance=advance,
            month=payroll.month,
            amount=installment_amount,
            installment_number=installment_number,
            payroll=payroll,
            notes=f"Deducted from payroll {payroll.id}",
            created_by=payroll.processed_by,
            processed_at=timezone.now()
        )
        
        logger.info(
            f"Created advance installment {installment.id} for advance {advance.id}: "
            f"amount={installment_amount}, installment={installment_number}"
        )
        
        return installment
    
    def _update_advance_status_atomic(self, advance: Advance, installment_amount: Decimal) -> None:
        """
        Update advance status with thread-safe operations.
        
        Args:
            advance: Advance instance
            installment_amount: Amount being deducted
        """
        # Use select_for_update for thread safety where supported
        if connection.vendor == 'postgresql':
            advance = Advance.objects.select_for_update().get(id=advance.id)
        
        # Update paid installments count
        advance.paid_installments += 1
        
        # Update status based on remaining amount
        if advance.status == 'paid':
            advance.status = 'in_progress'
        
        # Calculate remaining amount
        total_paid = advance.paid_installments * advance.installment_amount
        advance.remaining_amount = advance.amount - total_paid
        
        # Check if advance is completed
        if advance.remaining_amount <= 0:
            advance.status = 'completed'
            advance.completed_at = timezone.now()
            advance.remaining_amount = Decimal('0')  # Ensure it's exactly zero
        
        advance.save()
        
        logger.info(
            f"Updated advance {advance.id}: paid_installments={advance.paid_installments}, "
            f"remaining_amount={advance.remaining_amount}, status={advance.status}"
        )
    
    def _coordinate_advance_deduction(
        self,
        advance: Advance,
        installment: AdvanceInstallment,
        payroll: Payroll
    ) -> None:
        """
        Coordinate advance deduction with advance service for consistency.
        
        This method ensures that the advance deduction is properly coordinated
        with the advance service to maintain data consistency.
        
        Args:
            advance: Advance instance
            installment: Created installment
            payroll: Payroll instance
        """
        try:
            # Notify advance service about the deduction
            self.advance_service.record_payroll_deduction(
                advance_id=advance.id,
                installment_id=installment.id,
                payroll_id=payroll.id,
                amount=installment.amount,
                deduction_date=payroll.month
            )
            
            logger.info(
                f"Coordinated advance deduction with advance service: "
                f"advance={advance.id}, installment={installment.id}, payroll={payroll.id}"
            )
            
        except Exception as e:
            logger.error(
                f"Failed to coordinate advance deduction with advance service: {str(e)}"
            )
            # Don't fail the entire payroll creation for coordination issues
            # The installment record is already created and advance is updated
    
    def _validate_complete_payroll(self, payroll: Payroll) -> None:
        """
        Perform final validation on complete payroll.
        
        Args:
            payroll: Complete payroll to validate
            
        Raises:
            ValidationError: If final validation fails
        """
        try:
            # Use the model's built-in validation
            payroll.full_clean()
            
            # Additional business validation
            if payroll.net_salary < 0:
                logger.warning(
                    f"Negative net salary for {payroll.employee.get_full_name_ar()}: {payroll.net_salary}"
                )
            
            # Validate payroll lines exist
            if not payroll.lines.exists():
                raise GovValidationError(
                    message="Payroll must have at least one payroll line",
                    context={'payroll_id': payroll.id}
                )
            
            # Validate totals match lines
            lines_total_earnings = payroll.lines.filter(
                component_type='earning'
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
            
            lines_total_deductions = payroll.lines.filter(
                component_type='deduction'
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
            
            # Allow small rounding differences
            earnings_diff = abs(lines_total_earnings - (payroll.gross_salary + payroll.total_additions))
            deductions_diff = abs(lines_total_deductions - payroll.total_deductions)
            
            if earnings_diff > Decimal('0.01') or deductions_diff > Decimal('0.01'):
                logger.warning(
                    f"Payroll totals mismatch for {payroll.employee.get_full_name_ar()}: "
                    f"earnings_diff={earnings_diff}, deductions_diff={deductions_diff}"
                )
                
        except ValidationError as e:
            # Convert Django ValidationError to governance ValidationError
            raise GovValidationError(
                message=f"Payroll validation failed: {str(e)}",
                context={'validation_errors': e.messages if hasattr(e, 'messages') else [str(e)]}
            )
    
    def create_payroll_with_journal_entry(
        self,
        employee_id: int,
        month: date,
        idempotency_key: str,
        user: User,
        contract_id: Optional[int] = None,
        notes: str = "",
        payment_method: str = 'bank_transfer',
        workflow_type: str = 'monthly_payroll',
        auto_create_journal: bool = True
    ) -> Tuple[Payroll, Optional['JournalEntry']]:
        """
        Create payroll with automatic journal entry creation (atomic operation).
        
        This method implements the critical workflow pattern similar to MovementService:
        - Creates payroll record
        - Automatically creates corresponding journal entry through AccountingGateway
        - Ensures atomic updates with proper locking (Requirements 2.4, 2.7)
        
        Args:
            employee_id: ID of the employee
            month: Payroll month as date object
            idempotency_key: Unique key to prevent duplicate operations
            user: User creating the payroll
            contract_id: Optional specific contract ID
            notes: Optional notes
            payment_method: Payment method ('bank_transfer' or 'cash')
            workflow_type: Type of payroll workflow
            auto_create_journal: Whether to automatically create journal entry
            
        Returns:
            Tuple[Payroll, Optional[JournalEntry]]: Created payroll and journal entry
            
        Raises:
            AuthorityViolationError: If service lacks authority
            ValidationError: If validation fails
            IdempotencyError: If idempotency check fails
            ConcurrencyError: If concurrency conflict occurs
        """
        operation_start = timezone.now()
        
        try:
            with monitor_operation("payroll_gateway_create_with_journal"):
                # Set governance context
                GovernanceContext.set_context(
                    user=user,
                    service='PayrollGateway',
                    operation='create_payroll_with_journal'
                )
                
                # Validate authority for both payroll and journal creation
                self._validate_authority('create')
                
                # Validate payroll data
                payroll_data = PayrollData(
                    employee_id=employee_id,
                    month=month,
                    contract_id=contract_id,
                    notes=notes,
                    payment_method=payment_method
                )
                
                # Check idempotency for the complete operation
                is_duplicate, existing_record, existing_data = self.idempotency_service.check_and_record_operation(
                    operation_type='payroll_with_journal',
                    idempotency_key=idempotency_key,
                    result_data={},  # Will be updated after creation
                    user=user,
                    expires_in_hours=24
                )
                
                if is_duplicate:
                    logger.info(f"Duplicate payroll+journal creation detected: {idempotency_key}")
                    # Return existing payroll and journal entry
                    payroll_id = existing_data.get('payroll_id')
                    journal_entry_id = existing_data.get('journal_entry_id')
                    
                    if payroll_id:
                        payroll = Payroll.objects.get(id=payroll_id)
                        journal_entry = None
                        if journal_entry_id:
                            from financial.models.journal_entry import JournalEntry
                            journal_entry = JournalEntry.objects.get(id=journal_entry_id)
                        return payroll, journal_entry
                    else:
                        raise IdempotencyError(
                            operation_type='payroll_with_journal',
                            idempotency_key=idempotency_key,
                            context={'error': 'Existing record found but no payroll ID'}
                        )
                
                # Create payroll and journal entry atomically
                payroll, journal_entry = self._create_payroll_with_journal_atomic(
                    payroll_data=payroll_data,
                    idempotency_key=idempotency_key,
                    user=user,
                    workflow_type=workflow_type,
                    auto_create_journal=auto_create_journal
                )
                
                # Update idempotency record with complete result
                existing_record.result_data = {
                    'payroll_id': payroll.id,
                    'employee_id': payroll.employee.id,
                    'employee_name': payroll.employee.get_full_name_ar(),
                    'month': payroll.month.isoformat(),
                    'gross_salary': str(payroll.gross_salary),
                    'net_salary': str(payroll.net_salary),
                    'status': payroll.status,
                    'created_at': payroll.created_at.isoformat(),
                    'journal_entry_id': journal_entry.id if journal_entry else None,
                    'journal_entry_number': journal_entry.number if journal_entry else None
                }
                existing_record.save()
                
                # Create comprehensive audit trail
                self.audit_service.log_payroll_operation(
                    payroll_instance=payroll,
                    operation='CREATE_WITH_JOURNAL',
                    user=user,
                    source_service='PayrollGateway',
                    additional_context={
                        'workflow_type': workflow_type,
                        'idempotency_key': idempotency_key,
                        'journal_entry_id': journal_entry.id if journal_entry else None,
                        'journal_entry_number': journal_entry.number if journal_entry else None,
                        'auto_create_journal': auto_create_journal,
                        'operation_duration': (timezone.now() - operation_start).total_seconds()
                    }
                )
                
                logger.info(
                    f"Payroll with journal entry created successfully: {payroll.employee.get_full_name_ar()} "
                    f"for {payroll.month.strftime('%Y-%m')} - Net: {payroll.net_salary} "
                    f"- Journal: {journal_entry.number if journal_entry else 'None'}"
                )
                
                return payroll, journal_entry
                
        except Exception as e:
            logger.error(
                f"Failed to create payroll with journal entry for employee {employee_id} "
                f"month {month.strftime('%Y-%m')}: {str(e)}"
            )
            
            # Create audit trail for failure
            self.audit_service.log_operation(
                model_name='Payroll',
                object_id=0,  # No payroll created
                operation='CREATE_WITH_JOURNAL_FAILED',
                user=user,
                source_service='PayrollGateway',
                additional_context={
                    'error': str(e),
                    'employee_id': employee_id,
                    'month': month.isoformat(),
                    'idempotency_key': idempotency_key,
                    'workflow_type': workflow_type,
                    'auto_create_journal': auto_create_journal
                }
            )
            
            raise
        
        finally:
            GovernanceContext.clear_context()
    
    def _create_payroll_with_journal_atomic(
        self,
        payroll_data: PayrollData,
        idempotency_key: str,
        user: User,
        workflow_type: str,
        auto_create_journal: bool
    ) -> Tuple[Payroll, Optional['JournalEntry']]:
        """
        Create payroll and journal entry within atomic transaction with proper locking.
        
        This method implements Requirements 2.4 and 2.7:
        - Atomic updates of payroll and journal entries within single transaction boundary
        - Automatic creation of corresponding journal entries through AccountingGateway
        
        Args:
            payroll_data: Validated payroll data
            idempotency_key: Idempotency key for the operation
            user: User creating the records
            workflow_type: Type of payroll workflow
            auto_create_journal: Whether to create journal entry
            
        Returns:
            Tuple[Payroll, Optional[JournalEntry]]: Created payroll and journal entry
        """
        with DatabaseLockManager.atomic_operation():
            # Get and validate employee with locking
            employee = self._get_and_validate_employee(payroll_data.employee_id)
            
            # Get active contract
            contract = self._get_active_contract(employee, payroll_data.month, payroll_data.contract_id)
            
            # Check for existing payroll
            self._check_existing_payroll(employee, payroll_data.month)
            
            # Get salary components
            salary_components = self._get_salary_components(employee, payroll_data.month)
            
            # Calculate salary components with thread-safe operations
            calculated_components = self._calculate_salary_components_atomic(
                employee, payroll_data.month, salary_components, contract
            )
            
            # Create payroll record
            payroll = Payroll(
                employee=employee,
                month=payroll_data.month,
                contract=contract,
                basic_salary=calculated_components['basic_salary'],
                allowances=calculated_components['allowances'],
                overtime_amount=calculated_components['overtime_amount'],
                bonus=calculated_components['bonus'],
                social_insurance=calculated_components['social_insurance'],
                tax=calculated_components['tax'],
                absence_deduction=calculated_components['absence_deduction'],
                late_deduction=calculated_components['late_deduction'],
                advance_deduction=calculated_components['advance_deduction'],
                other_deductions=calculated_components['other_deductions'],
                gross_salary=calculated_components['gross_salary'],
                total_additions=calculated_components['total_additions'],
                total_deductions=calculated_components['total_deductions'],
                net_salary=calculated_components['net_salary'],
                status='calculated',
                payment_method=payroll_data.payment_method,
                notes=payroll_data.notes,
                processed_by=user,
                processed_at=timezone.now()
            )
            
            # Mark as gateway approved to avoid development warnings
            payroll._gateway_approved = True
            payroll.save()
            
            # Create payroll lines for detailed breakdown
            self._create_payroll_lines(payroll, calculated_components['component_details'])
            
            # Process advance deductions with proper locking
            if calculated_components['advance_deduction'] > 0:
                self._process_advance_deductions_atomic(payroll, calculated_components['advance_details'])
            
            # Final validation of complete payroll
            self._validate_complete_payroll(payroll)
            
            # Create journal entry through AccountingGateway if requested
            # Requirements 2.7: Automatically create corresponding journal entries through AccountingGateway
            journal_entry = None
            if auto_create_journal:
                journal_entry = self._create_payroll_journal_entry_atomic(
                    payroll=payroll,
                    user=user,
                    idempotency_key=f"{idempotency_key}_journal"
                )
                
                # Link journal entry to payroll
                payroll.journal_entry = journal_entry
                payroll.save(update_fields=['journal_entry'])
            
            return payroll, journal_entry
    
    def _create_payroll_journal_entry_atomic(
        self,
        payroll: Payroll,
        user: User,
        idempotency_key: str
    ) -> 'JournalEntry':
        """
        Create journal entry for payroll through AccountingGateway (atomic operation).
        
        This method integrates with the AccountingGateway to create proper
        journal entries for payroll transactions within the same transaction boundary.
        
        Args:
            payroll: Payroll instance
            user: User creating the journal entry
            idempotency_key: Idempotency key for journal entry creation
            
        Returns:
            JournalEntry: Created journal entry
            
        Raises:
            ValidationError: If journal entry creation fails
        """
        # Prepare journal entry lines for payroll
        lines = self._prepare_payroll_journal_lines(payroll)
        
        # Get financial category and subcategory from payroll
        financial_category = getattr(payroll, 'financial_category', None)
        financial_subcategory = getattr(payroll, 'financial_subcategory', None)
        
        # Create journal entry through AccountingGateway
        journal_entry = self.accounting_gateway.create_journal_entry(
            source_module='hr',
            source_model='Payroll',
            source_id=payroll.id,
            lines=lines,
            idempotency_key=idempotency_key,
            user=user,
            entry_type='payroll',
            description=f"Payroll for {payroll.employee.get_full_name_ar()} - {payroll.month.strftime('%Y-%m')}",
            reference=f"PAYROLL-{payroll.id}",
            date=payroll.month,
            financial_category=financial_category,
            financial_subcategory=financial_subcategory
        )
        
        logger.info(
            f"Journal entry created for payroll {payroll.id}: {journal_entry.number}"
        )
        
        return journal_entry
    
    def create_payroll_journal_entry(
        self,
        payroll: Payroll,
        user: User,
        idempotency_key: Optional[str] = None
    ) -> 'JournalEntry':
        """
        Create journal entry for existing payroll through AccountingGateway.
        
        This method creates journal entries for payrolls that were created
        without automatic journal entry creation.
        
        Args:
            payroll: Payroll instance
            user: User creating the journal entry
            idempotency_key: Optional idempotency key
            
        Returns:
            JournalEntry: Created journal entry
            
        Raises:
            ValidationError: If journal entry creation fails
        """
        if idempotency_key is None:
            idempotency_key = self.idempotency_service.generate_payroll_journal_entry_key(
                payroll_id=payroll.id,
                event_type='create'
            )
        
        # Check if journal entry already exists
        if hasattr(payroll, 'journal_entry') and payroll.journal_entry:
            logger.warning(f"Payroll {payroll.id} already has journal entry: {payroll.journal_entry.number}")
            return payroll.journal_entry
        
        # Create journal entry through AccountingGateway
        journal_entry = self._create_payroll_journal_entry_atomic(
            payroll=payroll,
            user=user,
            idempotency_key=idempotency_key
        )
        
        # Link journal entry to payroll
        payroll.journal_entry = journal_entry
        payroll.save(update_fields=['journal_entry'])
        
        # Create audit trail for journal entry creation
        self.audit_service.log_payroll_operation(
            payroll_instance=payroll,
            operation='CREATE_JOURNAL_ENTRY',
            user=user,
            source_service='PayrollGateway',
            additional_context={
                'journal_entry_id': journal_entry.id,
                'journal_entry_number': journal_entry.number,
                'idempotency_key': idempotency_key
            }
        )
        
        logger.info(
            f"Journal entry created for existing payroll {payroll.id}: {journal_entry.number}"
        )
        
        return journal_entry
    
    def _prepare_payroll_journal_lines(self, payroll: Payroll) -> List[JournalEntryLineData]:
        """
        Prepare comprehensive journal entry lines for payroll.
        
        This method maps payroll components to appropriate chart of accounts
        and creates balanced journal entry lines for all salary components,
        deductions, and advance deductions.
        
        Args:
            payroll: Payroll instance
            
        Returns:
            List[JournalEntryLineData]: Journal entry lines
        """
        from financial.models.chart_of_accounts import ChartOfAccounts
        
        lines = []
        
        # Basic salary expense (debit)
        if payroll.basic_salary > 0:
            lines.append(JournalEntryLineData(
                account_code='5100',  # Salary Expense
                debit=payroll.basic_salary,
                credit=Decimal('0'),
                description=f"Basic salary - {payroll.employee.get_full_name_ar()}"
            ))
        
        # Allowances expense (debit)
        if payroll.allowances > 0:
            lines.append(JournalEntryLineData(
                account_code='5110',  # Allowances Expense
                debit=payroll.allowances,
                credit=Decimal('0'),
                description=f"Allowances - {payroll.employee.get_full_name_ar()}"
            ))
        
        # Overtime expense (debit)
        if payroll.overtime_amount > 0:
            lines.append(JournalEntryLineData(
                account_code='5120',  # Overtime Expense
                debit=payroll.overtime_amount,
                credit=Decimal('0'),
                description=f"Overtime - {payroll.employee.get_full_name_ar()}"
            ))
        
        # Bonus expense (debit)
        if payroll.bonus > 0:
            lines.append(JournalEntryLineData(
                account_code='5130',  # Bonus Expense
                debit=payroll.bonus,
                credit=Decimal('0'),
                description=f"Bonus - {payroll.employee.get_full_name_ar()}"
            ))
        
        # Social insurance payable (credit)
        if payroll.social_insurance > 0:
            lines.append(JournalEntryLineData(
                account_code='2200',  # Social Insurance Payable
                debit=Decimal('0'),
                credit=payroll.social_insurance,
                description=f"Social insurance - {payroll.employee.get_full_name_ar()}"
            ))
        
        # Tax payable (credit)
        if payroll.tax > 0:
            lines.append(JournalEntryLineData(
                account_code='2210',  # Tax Payable
                debit=Decimal('0'),
                credit=payroll.tax,
                description=f"Tax - {payroll.employee.get_full_name_ar()}"
            ))
        
        # Absence deduction (credit to salary expense reduction)
        if payroll.absence_deduction > 0:
            lines.append(JournalEntryLineData(
                account_code='5100',  # Salary Expense (reduction)
                debit=Decimal('0'),
                credit=payroll.absence_deduction,
                description=f"Absence deduction - {payroll.employee.get_full_name_ar()}"
            ))
        
        # Late deduction (credit to salary expense reduction)
        if payroll.late_deduction > 0:
            lines.append(JournalEntryLineData(
                account_code='5100',  # Salary Expense (reduction)
                debit=Decimal('0'),
                credit=payroll.late_deduction,
                description=f"Late deduction - {payroll.employee.get_full_name_ar()}"
            ))
        
        # Advance deduction coordination (credit to advance receivable)
        if payroll.advance_deduction > 0:
            lines.append(JournalEntryLineData(
                account_code='1300',  # Employee Advances Receivable
                debit=Decimal('0'),
                credit=payroll.advance_deduction,
                description=f"Advance deduction - {payroll.employee.get_full_name_ar()}"
            ))
        
        # Other deductions (credit to appropriate payable account)
        if payroll.other_deductions > 0:
            lines.append(JournalEntryLineData(
                account_code='2220',  # Other Payables
                debit=Decimal('0'),
                credit=payroll.other_deductions,
                description=f"Other deductions - {payroll.employee.get_full_name_ar()}"
            ))
        
        # Net salary payable (credit) - this is what the employee will receive
        if payroll.net_salary > 0:
            lines.append(JournalEntryLineData(
                account_code='2100',  # Salaries Payable
                debit=Decimal('0'),
                credit=payroll.net_salary,
                description=f"Net salary payable - {payroll.employee.get_full_name_ar()}"
            ))
        elif payroll.net_salary < 0:
            # Handle negative net salary (rare case where deductions exceed gross)
            lines.append(JournalEntryLineData(
                account_code='1300',  # Employee Advances Receivable (employee owes company)
                debit=abs(payroll.net_salary),
                credit=Decimal('0'),
                description=f"Employee owes company - {payroll.employee.get_full_name_ar()}"
            ))
        
        # Validate that lines are balanced
        total_debit = sum(line.debit for line in lines)
        total_credit = sum(line.credit for line in lines)
        
        if total_debit != total_credit:
            logger.error(
                f"Unbalanced payroll journal entry for {payroll.employee.get_full_name_ar()}: "
                f"debit={total_debit}, credit={total_credit}, difference={total_debit - total_credit}"
            )
            raise GovValidationError(
                message=f"Payroll journal entry not balanced: debit {total_debit} != credit {total_credit}",
                context={
                    'payroll_id': payroll.id,
                    'employee_name': payroll.employee.get_full_name_ar(),
                    'total_debit': str(total_debit),
                    'total_credit': str(total_credit),
                    'difference': str(total_debit - total_credit)
                }
            )
        
        return lines
    
    def approve_payroll(
        self,
        payroll: Payroll,
        user: User,
        idempotency_key: str,
        notes: str = ""
    ) -> Payroll:
        """
        Approve a calculated payroll with validation and audit trail.
        
        Args:
            payroll: Payroll to approve
            user: User approving the payroll
            idempotency_key: Unique key for this operation
            notes: Optional approval notes
            
        Returns:
            Payroll: Approved payroll
            
        Raises:
            ValidationError: If approval validation fails
        """
        operation_start = timezone.now()
        
        try:
            with monitor_operation("payroll_gateway_approve_payroll"):
                # Set governance context
                GovernanceContext.set_context(
                    user=user,
                    service='PayrollGateway',
                    operation='approve_payroll'
                )
                
                # Validate authority
                self._validate_authority('approve')
                
                # Validate payroll can be approved
                if payroll.status != 'calculated':
                    raise GovValidationError(
                        message=f"Payroll cannot be approved in status: {payroll.status}",
                        context={'payroll_id': payroll.id, 'current_status': payroll.status}
                    )
                
                # Check idempotency
                is_duplicate, existing_record, existing_data = self.idempotency_service.check_and_record_operation(
                    operation_type='payroll_approval',
                    idempotency_key=idempotency_key,
                    result_data={},
                    user=user,
                    expires_in_hours=24
                )
                
                if is_duplicate:
                    logger.info(f"Duplicate payroll approval detected: {idempotency_key}")
                    return payroll  # Already approved
                
                # Approve payroll with thread-safe operations
                with DatabaseLockManager.atomic_operation():
                    if connection.vendor == 'postgresql':
                        payroll = Payroll.objects.select_for_update().get(id=payroll.id)
                    
                    payroll.status = 'approved'
                    payroll.approved_by = user
                    payroll.approved_at = timezone.now()
                    if notes:
                        payroll.notes = f"{payroll.notes}\nApproval notes: {notes}" if payroll.notes else f"Approval notes: {notes}"
                    payroll.save()
                
                # Update idempotency record
                existing_record.result_data = {
                    'payroll_id': payroll.id,
                    'status': payroll.status,
                    'approved_at': payroll.approved_at.isoformat(),
                    'approved_by': user.username
                }
                existing_record.save()
                
                # Create audit trail
                self.audit_service.log_payroll_operation(
                    payroll_instance=payroll,
                    operation='APPROVE',
                    user=user,
                    source_service='PayrollGateway',
                    additional_context={
                        'approval_notes': notes,
                        'idempotency_key': idempotency_key,
                        'operation_duration': (timezone.now() - operation_start).total_seconds()
                    }
                )
                
                logger.info(
                    f"Payroll approved: {payroll.employee.get_full_name_ar()} "
                    f"for {payroll.month.strftime('%Y-%m')} by {user.username}"
                )
                
                return payroll
                
        except Exception as e:
            logger.error(f"Failed to approve payroll {payroll.id}: {str(e)}")
            
            # Create audit trail for failure
            self.audit_service.log_payroll_operation(
                payroll_instance=payroll,
                operation='APPROVE_FAILED',
                user=user,
                source_service='PayrollGateway',
                additional_context={
                    'error': str(e),
                    'idempotency_key': idempotency_key
                }
            )
            
            raise
        
        finally:
            GovernanceContext.clear_context()
    
    def get_payroll_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about payrolls created through the gateway.
        
        Returns:
            Dict: Statistics including counts, amounts, and performance metrics
        """
        from django.db.models import Count, Sum, Avg
        
        stats = {}
        
        # Basic counts
        total_payrolls = Payroll.objects.count()
        stats['total_payrolls'] = total_payrolls
        
        if total_payrolls == 0:
            return stats
        
        # Count by status
        status_counts = Payroll.objects.values('status').annotate(
            count=Count('id')
        ).order_by('-count')
        
        stats['by_status'] = {
            item['status']: item['count']
            for item in status_counts
        }
        
        # Total amounts
        total_net_salary = Payroll.objects.aggregate(
            total=Sum('net_salary')
        )['total'] or Decimal('0')
        
        stats['total_net_salary'] = str(total_net_salary)
        
        # Recent activity (last 30 days)
        recent_cutoff = timezone.now() - timedelta(days=30)
        stats['recent_payrolls'] = Payroll.objects.filter(
            created_at__gte=recent_cutoff
        ).count()
        
        # Average salary
        avg_salary = Payroll.objects.aggregate(
            avg=Avg('net_salary')
        )['avg'] or Decimal('0')
        
        stats['average_net_salary'] = str(avg_salary)
        
        return stats
    
    def process_payroll_payment(
        self,
        payroll: Payroll,
        user: User,
        idempotency_key: str,
        payment_method: str = 'bank_transfer',
        payment_reference: str = "",
        notes: str = ""
    ) -> Tuple[Payroll, 'JournalEntry']:
        """
        Process payroll payment with automatic journal entry creation.
        
        This method handles the payment of approved payrolls by:
        - Updating payroll status to 'paid'
        - Creating payment journal entry through AccountingGateway
        - Ensuring atomic updates with proper locking
        
        Args:
            payroll: Approved payroll to pay
            user: User processing the payment
            idempotency_key: Unique key for this payment operation
            payment_method: Payment method ('bank_transfer' or 'cash')
            payment_reference: Payment reference number
            notes: Optional payment notes
            
        Returns:
            Tuple[Payroll, JournalEntry]: Updated payroll and payment journal entry
            
        Raises:
            ValidationError: If payment validation fails
        """
        operation_start = timezone.now()
        
        try:
            with monitor_operation("payroll_gateway_process_payment"):
                # Set governance context
                GovernanceContext.set_context(
                    user=user,
                    service='PayrollGateway',
                    operation='process_payroll_payment'
                )
                
                # Validate authority
                self._validate_authority('pay')
                
                # Validate payroll can be paid
                if payroll.status != 'approved':
                    raise GovValidationError(
                        message=f"Payroll cannot be paid in status: {payroll.status}",
                        context={'payroll_id': payroll.id, 'current_status': payroll.status}
                    )
                
                # Check idempotency
                is_duplicate, existing_record, existing_data = self.idempotency_service.check_and_record_operation(
                    operation_type='payroll_payment',
                    idempotency_key=idempotency_key,
                    result_data={},
                    user=user,
                    expires_in_hours=24
                )
                
                if is_duplicate:
                    logger.info(f"Duplicate payroll payment detected: {idempotency_key}")
                    # Return existing results
                    payroll_id = existing_data.get('payroll_id')
                    journal_entry_id = existing_data.get('payment_journal_entry_id')
                    
                    if payroll_id and journal_entry_id:
                        from financial.models.journal_entry import JournalEntry
                        updated_payroll = Payroll.objects.get(id=payroll_id)
                        payment_entry = JournalEntry.objects.get(id=journal_entry_id)
                        return updated_payroll, payment_entry
                    else:
                        raise IdempotencyError(
                            operation_type='payroll_payment',
                            idempotency_key=idempotency_key,
                            context={'error': 'Existing record found but incomplete data'}
                        )
                
                # Process payment atomically
                updated_payroll, payment_entry = self._process_payroll_payment_atomic(
                    payroll=payroll,
                    user=user,
                    idempotency_key=idempotency_key,
                    payment_method=payment_method,
                    payment_reference=payment_reference,
                    notes=notes
                )
                
                # Update idempotency record
                existing_record.result_data = {
                    'payroll_id': updated_payroll.id,
                    'status': updated_payroll.status,
                    'paid_at': updated_payroll.paid_at.isoformat() if updated_payroll.paid_at else None,
                    'payment_journal_entry_id': payment_entry.id,
                    'payment_journal_entry_number': payment_entry.number,
                    'payment_method': payment_method,
                    'payment_reference': payment_reference
                }
                existing_record.save()
                
                # Create audit trail
                self.audit_service.log_payroll_operation(
                    payroll_instance=updated_payroll,
                    operation='PROCESS_PAYMENT',
                    user=user,
                    source_service='PayrollGateway',
                    additional_context={
                        'payment_method': payment_method,
                        'payment_reference': payment_reference,
                        'payment_notes': notes,
                        'payment_journal_entry_id': payment_entry.id,
                        'payment_journal_entry_number': payment_entry.number,
                        'idempotency_key': idempotency_key,
                        'operation_duration': (timezone.now() - operation_start).total_seconds()
                    }
                )
                
                logger.info(
                    f"Payroll payment processed: {updated_payroll.employee.get_full_name_ar()} "
                    f"for {updated_payroll.month.strftime('%Y-%m')} - Amount: {updated_payroll.net_salary} "
                    f"- Payment Entry: {payment_entry.number}"
                )
                
                return updated_payroll, payment_entry
                
        except Exception as e:
            logger.error(f"Failed to process payroll payment {payroll.id}: {str(e)}")
            
            # Create audit trail for failure
            self.audit_service.log_payroll_operation(
                payroll_instance=payroll,
                operation='PROCESS_PAYMENT_FAILED',
                user=user,
                source_service='PayrollGateway',
                additional_context={
                    'error': str(e),
                    'idempotency_key': idempotency_key,
                    'payment_method': payment_method
                }
            )
            
            raise
        
        finally:
            GovernanceContext.clear_context()
    
    def _process_payroll_payment_atomic(
        self,
        payroll: Payroll,
        user: User,
        idempotency_key: str,
        payment_method: str,
        payment_reference: str,
        notes: str
    ) -> Tuple[Payroll, 'JournalEntry']:
        """
        Process payroll payment within atomic transaction.
        
        Args:
            payroll: Payroll to pay
            user: User processing payment
            idempotency_key: Idempotency key
            payment_method: Payment method
            payment_reference: Payment reference
            notes: Payment notes
            
        Returns:
            Tuple[Payroll, JournalEntry]: Updated payroll and payment entry
        """
        with DatabaseLockManager.atomic_operation():
            # Lock payroll for update
            if connection.vendor == 'postgresql':
                payroll = Payroll.objects.select_for_update().get(id=payroll.id)
            
            # Update payroll status
            payroll.status = 'paid'
            payroll.paid_at = timezone.now()
            payroll.paid_by = user
            if notes:
                payroll.notes = f"{payroll.notes}\nPayment notes: {notes}" if payroll.notes else f"Payment notes: {notes}"
            payroll.save()
            
            # Create payment journal entry
            payment_entry = self._create_payment_journal_entry_atomic(
                payroll=payroll,
                user=user,
                idempotency_key=f"{idempotency_key}_payment",
                payment_method=payment_method,
                payment_reference=payment_reference
            )
            
            return payroll, payment_entry
    
    def _create_payment_journal_entry_atomic(
        self,
        payroll: Payroll,
        user: User,
        idempotency_key: str,
        payment_method: str,
        payment_reference: str
    ) -> 'JournalEntry':
        """
        Create payment journal entry for payroll through AccountingGateway.
        
        This creates the journal entry that records the actual payment to the employee,
        reducing the Salaries Payable liability and reducing Cash/Bank assets.
        
        Args:
            payroll: Payroll being paid
            user: User creating the entry
            idempotency_key: Idempotency key
            payment_method: Payment method
            payment_reference: Payment reference
            
        Returns:
            JournalEntry: Created payment journal entry
        """
        # Prepare payment journal entry lines
        lines = []
        
        # النظام الجديد: payment_method هو account code مباشرة
        cash_account = payment_method
        
        # التحقق من أن الحساب موجود
        try:
            from financial.models import ChartOfAccounts
            account = ChartOfAccounts.objects.filter(
                code=cash_account,
                is_active=True
            ).first()
            
            if not account:
                raise ValueError(f"الحساب المحاسبي {cash_account} غير موجود أو غير نشط")
        except Exception as e:
            logger.error(f"فشل في التحقق من الحساب {cash_account}: {str(e)}")
            raise
        
        # Debit Salaries Payable (reduce liability)
        lines.append(JournalEntryLineData(
            account_code='2100',  # Salaries Payable
            debit=payroll.net_salary,
            credit=Decimal('0'),
            description=f"Salary payment - {payroll.employee.get_full_name_ar()}"
        ))
        
        # Credit Cash/Bank (reduce asset)
        lines.append(JournalEntryLineData(
            account_code=cash_account,  # Cash or Bank account code
            debit=Decimal('0'),
            credit=payroll.net_salary,
            description=f"Payment via account {cash_account} - {payroll.employee.get_full_name_ar()}"
        ))
        
        # Get financial category and subcategory from payroll
        financial_category = getattr(payroll, 'financial_category', None)
        financial_subcategory = getattr(payroll, 'financial_subcategory', None)
        
        # Create journal entry through AccountingGateway
        payment_entry = self.accounting_gateway.create_journal_entry(
            source_module='hr',
            source_model='Payroll',
            source_id=payroll.id,
            lines=lines,
            idempotency_key=idempotency_key,
            user=user,
            entry_type='payroll_payment',
            description=f"Salary payment for {payroll.employee.get_full_name_ar()} - {payroll.month.strftime('%Y-%m')}",
            reference=payment_reference or f"PAY-{payroll.id}",
            date=timezone.now().date(),
            financial_category=financial_category,
            financial_subcategory=financial_subcategory
        )
        
        logger.info(
            f"Payment journal entry created for payroll {payroll.id}: {payment_entry.number}"
        )
        
        return payment_entry
        """
        Get health status of the PayrollGateway.
        
        Returns:
            Dict: Health status with recommendations
        """
        stats = self.get_payroll_statistics()
        
        health = {
            'status': 'healthy',
            'issues': [],
            'recommendations': [],
            'metrics': {
                'total_payrolls': stats.get('total_payrolls', 0),
                'recent_activity': stats.get('recent_payrolls', 0),
                'average_salary': stats.get('average_net_salary', '0')
            }
        }
        
        # Check for issues
        if stats.get('recent_payrolls', 0) == 0:
            health['issues'].append('No recent payroll activity')
        
        # Check for negative salaries
        negative_salaries = Payroll.objects.filter(net_salary__lt=0).count()
        if negative_salaries > 0:
            health['issues'].append(f'{negative_salaries} payrolls with negative net salary')
            health['recommendations'].append('Review payrolls with negative net salary')
        
        # Check idempotency service health
        try:
            idempotency_health = self.idempotency_service.get_operation_statistics()
            if idempotency_health and idempotency_health.get('expired_count', 0) > 1000:
                health['status'] = 'warning'
                health['issues'].append('High number of expired idempotency records')
                health['recommendations'].append('Run idempotency cleanup')
        except Exception as e:
            health['issues'].append(f'Could not check idempotency service health: {str(e)}')
        
        return health
    def get_payroll_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive statistics about payrolls created through the gateway.
        
        Returns:
            Dict: Statistics including counts, amounts, journal entries, and performance metrics
        """
        from django.db.models import Count, Sum, Avg
        
        stats = {}
        
        # Basic counts
        total_payrolls = Payroll.objects.count()
        stats['total_payrolls'] = total_payrolls
        
        if total_payrolls == 0:
            return stats
        
        # Count by status
        status_counts = Payroll.objects.values('status').annotate(
            count=Count('id')
        ).order_by('-count')
        
        stats['by_status'] = {
            item['status']: item['count']
            for item in status_counts
        }
        
        # Total amounts
        total_net_salary = Payroll.objects.aggregate(
            total=Sum('net_salary')
        )['total'] or Decimal('0')
        
        stats['total_net_salary'] = str(total_net_salary)
        
        # Recent activity (last 30 days)
        recent_cutoff = timezone.now() - timedelta(days=30)
        stats['recent_payrolls'] = Payroll.objects.filter(
            created_at__gte=recent_cutoff
        ).count()
        
        # Average salary
        avg_salary = Payroll.objects.aggregate(
            avg=Avg('net_salary')
        )['avg'] or Decimal('0')
        
        stats['average_net_salary'] = str(avg_salary)
        
        # Journal entry integration statistics
        payrolls_with_journal = Payroll.objects.filter(
            journal_entry__isnull=False
        ).count()
        
        stats['payrolls_with_journal_entries'] = payrolls_with_journal
        stats['journal_entry_integration_ratio'] = (
            payrolls_with_journal / total_payrolls if total_payrolls > 0 else 0
        )
        
        # Advance deduction statistics
        payrolls_with_advances = Payroll.objects.filter(
            advance_deduction__gt=0
        ).count()
        
        stats['payrolls_with_advance_deductions'] = payrolls_with_advances
        stats['advance_deduction_ratio'] = (
            payrolls_with_advances / total_payrolls if total_payrolls > 0 else 0
        )
        
        # Payment processing statistics
        paid_payrolls = Payroll.objects.filter(status='paid').count()
        stats['paid_payrolls'] = paid_payrolls
        stats['payment_completion_ratio'] = (
            paid_payrolls / total_payrolls if total_payrolls > 0 else 0
        )
        
        return stats
    
    def get_health_status(self) -> Dict[str, Any]:
        """
        Get comprehensive health status of the PayrollGateway.
        
        Returns:
            Dict: Health status with recommendations for payroll-accounting integration
        """
        stats = self.get_payroll_statistics()
        
        health = {
            'status': 'healthy',
            'issues': [],
            'recommendations': [],
            'metrics': {
                'total_payrolls': stats.get('total_payrolls', 0),
                'recent_activity': stats.get('recent_payrolls', 0),
                'average_salary': stats.get('average_net_salary', '0'),
                'journal_integration_ratio': stats.get('journal_entry_integration_ratio', 0),
                'advance_deduction_ratio': stats.get('advance_deduction_ratio', 0),
                'payment_completion_ratio': stats.get('payment_completion_ratio', 0)
            }
        }
        
        # Check for issues
        if stats.get('recent_payrolls', 0) == 0:
            health['issues'].append('No recent payroll activity')
        
        # Check for negative salaries
        negative_salaries = Payroll.objects.filter(net_salary__lt=0).count()
        if negative_salaries > 0:
            health['issues'].append(f'{negative_salaries} payrolls with negative net salary')
            health['recommendations'].append('Review payrolls with negative net salary')
        
        # Check journal entry integration
        journal_ratio = stats.get('journal_entry_integration_ratio', 0)
        if journal_ratio < 0.8:
            health['status'] = 'warning'
            health['issues'].append(f'Low journal entry integration ratio: {journal_ratio:.2%}')
            health['recommendations'].append('Ensure payrolls are created with automatic journal entries')
        
        # Check advance deduction coordination
        advance_ratio = stats.get('advance_deduction_ratio', 0)
        if advance_ratio > 0.5:
            health['issues'].append(f'High advance deduction ratio: {advance_ratio:.2%}')
            health['recommendations'].append('Monitor advance deduction patterns for potential issues')
        
        # Check payment completion
        payment_ratio = stats.get('payment_completion_ratio', 0)
        if payment_ratio < 0.9:
            health['issues'].append(f'Low payment completion ratio: {payment_ratio:.2%}')
            health['recommendations'].append('Review unpaid payrolls and payment processing')
        
        # Check idempotency service health
        try:
            idempotency_health = self.idempotency_service.get_operation_statistics()
            if idempotency_health and idempotency_health.get('expired_count', 0) > 1000:
                health['status'] = 'warning'
                health['issues'].append('High number of expired idempotency records')
                health['recommendations'].append('Run idempotency cleanup')
        except Exception as e:
            health['issues'].append(f'Could not check idempotency service health: {str(e)}')
        
        # Check accounting gateway integration
        try:
            accounting_health = self.accounting_gateway.get_health_status()
            if accounting_health and accounting_health.get('status') != 'healthy':
                health['status'] = 'warning'
                health['issues'].append('AccountingGateway health issues detected')
                if 'recommendations' in accounting_health:
                    health['recommendations'].extend(accounting_health['recommendations'])
        except Exception as e:
            health['issues'].append(f'Could not check AccountingGateway health: {str(e)}')
        
        return health