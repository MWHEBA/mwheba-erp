"""
HR-specific wrapper for PayrollGateway.
Handles HR business logic while using governance infrastructure.

NOTE: This service provides TWO approaches:
1. Use PayrollGateway directly (simple payrolls)
2. Use IntegratedPayrollService with governance wrapper (complex payrolls with attendance/leave)
"""
from governance.services.payroll_gateway import PayrollGateway
from governance.exceptions import GovernanceError, IdempotencyError
from governance.services.idempotency_service import IdempotencyService
from governance.services.audit_service import AuditService
from django.db import transaction
from django.db.models import Prefetch
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


class HRPayrollGatewayService:
    """
    HR-specific payroll service using PayrollGateway.
    
    This service wraps PayrollGateway and adds HR-specific logic:
    - Advance deduction handling
    - Leave balance integration
    - Attendance integration
    - HR-specific validations
    
    Two modes of operation:
    1. Simple mode: Uses PayrollGateway.create_payroll() directly
    2. Integrated mode: Uses IntegratedPayrollService with governance features
    """
    
    def __init__(self):
        self.gateway = PayrollGateway()
        self.idempotency_service = IdempotencyService()
        self.audit_service = AuditService()
    
    @transaction.atomic
    def calculate_employee_payroll_simple(self, employee, month, processed_by):
        """
        Calculate payroll for employee using PayrollGateway (simple mode).
        
        This uses PayrollGateway's built-in calculation logic.
        Use this for basic payrolls without attendance/leave integration.
        
        Args:
            employee: Employee instance
            month: Payroll month (date object)
            processed_by: User processing the payroll
            
        Returns:
            Payroll: Created payroll instance
            
        Raises:
            ValidationError: If validation fails
            IdempotencyError: If payroll already exists
        """
        # Generate idempotency key
        idempotency_key = self._generate_idempotency_key(employee, month)
        
        try:
            # Create payroll through gateway
            payroll = self.gateway.create_payroll(
                employee_id=employee.id,
                month=month,
                idempotency_key=idempotency_key,
                user=processed_by,
                workflow_type='monthly_payroll'
            )
            
            
            return payroll
            
        except IdempotencyError as e:
            # Payroll already exists - return existing
            logger.warning(f"Payroll already exists: {e}")
            existing_payroll = self._get_existing_payroll(employee, month)
            return existing_payroll
            
        except GovernanceError as e:
            logger.error(f"Governance error: {e}")
            raise
            
        except Exception as e:
            logger.exception(f"Unexpected error creating payroll: {e}")
            raise
    
    @transaction.atomic
    def calculate_employee_payroll_integrated(self, employee, month, processed_by):
        """
        Calculate payroll using IntegratedPayrollService with governance features.
        
        This uses HR's IntegratedPayrollService for complex calculations
        (attendance, leave, advances) but adds governance features:
        - Idempotency protection
        - Audit trail
        - Thread safety
        
        Args:
            employee: Employee instance
            month: Payroll month (date object)
            processed_by: User processing the payroll
            
        Returns:
            Payroll: Created payroll instance
            
        Raises:
            ValidationError: If validation fails
            IdempotencyError: If payroll already exists
        """
        from hr.services.integrated_payroll_service import IntegratedPayrollService
        
        # Generate idempotency key
        idempotency_key = self._generate_idempotency_key(employee, month)
        
        operation_start = timezone.now()
        
        try:
            # Check idempotency
            is_duplicate, existing_record, existing_data = self.idempotency_service.check_and_record_operation(
                operation_type='hr_integrated_payroll',
                idempotency_key=idempotency_key,
                result_data={},
                user=processed_by,
                expires_in_hours=24
            )
            
            if is_duplicate:
                payroll_id = existing_data.get('payroll_id')
                if payroll_id:
                    # Try to get the payroll by ID; if deleted, fall through to recreate
                    try:
                        return self._get_payroll_by_id(payroll_id)
                    except Exception:
                        logger.warning(
                            f"Idempotency record references payroll {payroll_id} "
                            f"but it no longer exists. Recreating for {employee.get_full_name_ar()}."
                        )
                
                # Check if payroll actually exists in DB (previous attempt may have failed mid-way)
                from hr.models import Payroll
                existing_payroll = Payroll.objects.filter(employee=employee, month=month).first()
                if existing_payroll:
                    return existing_payroll
                
                # Idempotency record exists but payroll was never created (previous attempt failed).
                # Reset the idempotency record so we can retry.
                logger.warning(
                    f"Stale idempotency record found for {employee.get_full_name_ar()} "
                    f"month={month}. Resetting and retrying payroll creation."
                )
                existing_record.result_data = {}
                existing_record.expires_at = timezone.now() + timezone.timedelta(hours=24)
                existing_record.save()
                # Fall through to create the payroll below
            
            # Create payroll using IntegratedPayrollService
            payroll = IntegratedPayrollService.calculate_integrated_payroll(
                employee=employee,
                month=month,
                processed_by=processed_by
            )
            
            # Update idempotency record
            existing_record.result_data = {
                'payroll_id': payroll.id,
                'employee_id': payroll.employee.id,
                'employee_name': payroll.employee.get_full_name_ar(),
                'month': payroll.month.isoformat(),
                'gross_salary': str(payroll.correct_gross_salary),
                'net_salary': str(payroll.correct_net_salary),
                'status': payroll.status,
                'created_at': payroll.created_at.isoformat()
            }
            existing_record.save()
            
            # Create audit trail
            self.audit_service.log_operation(
                model_name='Payroll',
                object_id=payroll.id,
                operation='CREATE',
                user=processed_by,
                source_service='HRPayrollGatewayService',
                additional_context={
                    'workflow_type': 'integrated_payroll',
                    'idempotency_key': idempotency_key,
                    'operation_duration': (timezone.now() - operation_start).total_seconds(),
                    'employee_name': employee.get_full_name_ar(),
                    'month': month.strftime('%Y-%m')
                }
            )
            
            
            return payroll
            
        except Exception as e:
            logger.error(f"Failed to create integrated payroll: {e}")
            
            # Create audit trail for failure
            self.audit_service.log_operation(
                model_name='Payroll',
                object_id=0,
                operation='CREATE_FAILED',
                user=processed_by,
                source_service='HRPayrollGatewayService',
                additional_context={
                    'error': str(e),
                    'employee_id': employee.id,
                    'month': month.isoformat(),
                    'idempotency_key': idempotency_key,
                    'workflow_type': 'integrated_payroll'
                }
            )
            
            raise
    
    def calculate_employee_payroll(self, employee, month, processed_by, use_integrated=True):
        """
        Calculate payroll for employee (auto-selects mode).
        
        Args:
            employee: Employee instance
            month: Payroll month (date object)
            processed_by: User processing the payroll
            use_integrated: If True, uses IntegratedPayrollService (default)
            
        Returns:
            Payroll: Created payroll instance
        """
        if use_integrated:
            return self.calculate_employee_payroll_integrated(employee, month, processed_by)
        else:
            return self.calculate_employee_payroll_simple(employee, month, processed_by)
    
    def _generate_idempotency_key(self, employee, month):
        """Generate unique idempotency key for payroll."""
        return f'PAYROLL:{employee.id}:{month.year}:{month.month:02d}:create'
    
    def _get_existing_payroll(self, employee, month):
        """Get existing payroll for employee and month."""
        from hr.models import Payroll
        return Payroll.objects.get(employee=employee, month=month)
    
    def _get_payroll_by_id(self, payroll_id):
        """Get payroll by ID."""
        from hr.models import Payroll
        return Payroll.objects.get(id=payroll_id)
    
    def process_monthly_payrolls(self, month, department=None, processed_by=None, use_integrated=True):
        """
        Process payrolls for all employees in a month with Query Optimization.
        Issue #12: N+1 queries in payroll processing
        
        Args:
            month: Payroll month
            department: Optional department filter
            processed_by: User processing payrolls
            use_integrated: If True, uses IntegratedPayrollService (default)
            
        Returns:
            dict: Results with success and failed lists
        """
        from hr.models import Employee, SalaryComponent, Advance, Contract
        
        # Get active employees with ALL related data in ONE optimized query
        employees = Employee.objects.select_related(
            'user',
            'department',
            'job_title',
            'shift'
        ).prefetch_related(
            Prefetch(
                'salary_components',
                queryset=SalaryComponent.objects.filter(
                    is_active=True
                ).select_related('contract'),
                to_attr='active_salary_components'
            ),
            Prefetch(
                'advances',
                queryset=Advance.objects.filter(
                    status__in=['paid', 'in_progress']
                ).select_related('employee'),
                to_attr='active_advances'
            ),
            Prefetch(
                'contracts',
                queryset=Contract.objects.filter(
                    status='active'
                ).select_related('employee'),
                to_attr='active_contracts'
            )
        ).filter(status='active', is_insurance_only=False)
        
        if department:
            employees = employees.filter(department=department)
        
        results = {
            'success': [],
            'failed': [],
            'skipped': []
        }
        
        
        for employee in employees:
            try:
                # All data already loaded - no additional queries!
                payroll = self.calculate_employee_payroll(
                    employee, month, processed_by, use_integrated=use_integrated
                )
                results['success'].append({
                    'employee': employee,
                    'payroll': payroll
                })
                
            except IdempotencyError:
                # Already processed - skip
                results['skipped'].append({
                    'employee': employee,
                    'reason': 'Already processed'
                })
                
            except Exception as e:
                logger.error(
                    f"Failed to process payroll for {employee.get_full_name_ar()}: {e}"
                )
                results['failed'].append({
                    'employee': employee,
                    'error': str(e)
                })
        
        
        return results

