"""
Tests for PayrollGateway service - Thread-Safe Payroll Operations

This test suite validates the PayrollGateway service implementation including:
- Thread-safe payroll creation
- Salary component calculation
- Idempotency protection
- Authority validation
- Audit trail creation
- Integration with AccountingGateway
"""

import pytest
from decimal import Decimal
from datetime import date, datetime, timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction

from governance.services import PayrollGateway, PayrollData, SalaryComponentData, IdempotencyService
from governance.models import IdempotencyRecord, AuditTrail, GovernanceContext
from governance.exceptions import (
    AuthorityViolationError, ValidationError as GovValidationError,
    IdempotencyError, ConcurrencyError
)

# Import HR models for testing
from hr.models import Employee, Contract, Payroll, PayrollLine, SalaryComponent, Advance, AdvanceInstallment

User = get_user_model()


class PayrollGatewayTestCase(TestCase):
    """Base test case with common setup for PayrollGateway tests"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='payroll_admin',
            email='payroll@test.com',
            password='testpass123'
        )
        
        # Create test employee
        self.employee = Employee.objects.create(
            employee_number='EMP001',
            name='أحمد محمد',
            national_id='12345678901234',
            phone='01234567890',
            email='ahmed@test.com',
            hire_date=date(2023, 1, 1),
            is_active=True
        )
        
        # Create active contract
        self.contract = Contract.objects.create(
            employee=self.employee,
            contract_type='permanent',
            basic_salary=Decimal('5000.00'),
            start_date=date(2023, 1, 1),
            status='active'
        )
        
        # Create salary components
        self.basic_salary_component = SalaryComponent.objects.create(
            employee=self.employee,
            code='BASIC_SALARY',
            name='الراتب الأساسي',
            component_type='earning',
            calculation_method='fixed',
            amount=Decimal('5000.00'),
            effective_from=date(2023, 1, 1),
            is_active=True,
            order=1
        )
        
        self.allowance_component = SalaryComponent.objects.create(
            employee=self.employee,
            code='ALLOWANCE',
            name='البدلات',
            component_type='earning',
            calculation_method='fixed',
            amount=Decimal('1000.00'),
            effective_from=date(2023, 1, 1),
            is_active=True,
            order=2
        )
        
        self.social_insurance_component = SalaryComponent.objects.create(
            employee=self.employee,
            code='SOCIAL_INSURANCE',
            name='التأمينات الاجتماعية',
            component_type='deduction',
            calculation_method='percentage',
            amount=Decimal('11.00'),  # 11% of basic salary
            effective_from=date(2023, 1, 1),
            is_active=True,
            order=1
        )
        
        self.gateway = PayrollGateway()
        self.test_month = date(2024, 1, 1)


class PayrollGatewayBasicTest(PayrollGatewayTestCase):
    """Test basic PayrollGateway functionality"""
    
    def test_payroll_gateway_initialization(self):
        """Test PayrollGateway initializes correctly"""
        gateway = PayrollGateway()
        
        self.assertIsNotNone(gateway.idempotency_service)
        self.assertIsNotNone(gateway.audit_service)
        self.assertIsNotNone(gateway.authority_service)
        self.assertIsNotNone(gateway.accounting_gateway)
        self.assertEqual(gateway.SUPPORTED_OPERATIONS, {'create', 'calculate', 'approve', 'pay', 'cancel'})
    
    def test_payroll_data_validation(self):
        """Test PayrollData validation"""
        # Valid data
        valid_data = PayrollData(
            employee_id=self.employee.id,
            month=self.test_month,
            payment_method='bank_transfer'
        )
        self.assertEqual(valid_data.employee_id, self.employee.id)
        self.assertEqual(valid_data.month, self.test_month)
        
        # Invalid employee ID
        with self.assertRaises(ValueError):
            PayrollData(employee_id=0, month=self.test_month)
        
        # Invalid month type
        with self.assertRaises(ValueError):
            PayrollData(employee_id=self.employee.id, month="2024-01-01")
        
        # Invalid payment method
        with self.assertRaises(ValueError):
            PayrollData(
                employee_id=self.employee.id,
                month=self.test_month,
                payment_method='invalid_method'
            )
    
    def test_salary_component_data_validation(self):
        """Test SalaryComponentData validation"""
        # Valid data
        valid_component = SalaryComponentData(
            component_code='BASIC_SALARY',
            component_type='earning',
            amount=Decimal('5000.00'),
            description='Basic salary'
        )
        self.assertEqual(valid_component.component_code, 'BASIC_SALARY')
        self.assertEqual(valid_component.amount, Decimal('5000.00'))
        
        # Invalid component code
        with self.assertRaises(ValueError):
            SalaryComponentData(
                component_code='',
                component_type='earning',
                amount=Decimal('5000.00')
            )
        
        # Invalid component type
        with self.assertRaises(ValueError):
            SalaryComponentData(
                component_code='BASIC_SALARY',
                component_type='invalid_type',
                amount=Decimal('5000.00')
            )
        
        # Negative amount
        with self.assertRaises(ValueError):
            SalaryComponentData(
                component_code='BASIC_SALARY',
                component_type='earning',
                amount=Decimal('-1000.00')
            )


class PayrollGatewayCreatePayrollTest(PayrollGatewayTestCase):
    """Test payroll creation through PayrollGateway"""
    
    @patch('governance.services.payroll_gateway.GovernanceContext')
    def test_create_payroll_success(self, mock_context):
        """Test successful payroll creation"""
        idempotency_key = IdempotencyService.generate_payroll_key(
            employee_id=self.employee.id,
            month='2024-01',
            event_type='create'
        )
        
        payroll = self.gateway.create_payroll(
            employee_id=self.employee.id,
            month=self.test_month,
            idempotency_key=idempotency_key,
            user=self.user
        )
        
        # Verify payroll was created
        self.assertIsInstance(payroll, Payroll)
        self.assertEqual(payroll.employee, self.employee)
        self.assertEqual(payroll.month, self.test_month)
        self.assertEqual(payroll.status, 'calculated')
        self.assertEqual(payroll.processed_by, self.user)
        
        # Verify salary calculations
        self.assertEqual(payroll.basic_salary, Decimal('5000.00'))
        self.assertEqual(payroll.allowances, Decimal('1000.00'))
        self.assertEqual(payroll.gross_salary, Decimal('6000.00'))
        
        # Social insurance should be 11% of basic salary = 550
        expected_social_insurance = Decimal('5000.00') * Decimal('11.00') / Decimal('100')
        self.assertEqual(payroll.social_insurance, expected_social_insurance)
        
        # Verify payroll lines were created
        self.assertTrue(payroll.lines.exists())
        
        # Verify idempotency record was created
        idempotency_record = IdempotencyRecord.objects.filter(
            operation_type='payroll_operation',
            idempotency_key=idempotency_key
        ).first()
        self.assertIsNotNone(idempotency_record)
        self.assertEqual(idempotency_record.result_data['payroll_id'], payroll.id)
    
    def test_create_payroll_duplicate_idempotency(self):
        """Test duplicate payroll creation with same idempotency key"""
        idempotency_key = IdempotencyService.generate_payroll_key(
            employee_id=self.employee.id,
            month='2024-01',
            event_type='create'
        )
        
        # Create first payroll
        payroll1 = self.gateway.create_payroll(
            employee_id=self.employee.id,
            month=self.test_month,
            idempotency_key=idempotency_key,
            user=self.user
        )
        
        # Attempt to create duplicate payroll
        payroll2 = self.gateway.create_payroll(
            employee_id=self.employee.id,
            month=self.test_month,
            idempotency_key=idempotency_key,
            user=self.user
        )
        
        # Should return the same payroll
        self.assertEqual(payroll1.id, payroll2.id)
        
        # Should only have one payroll record
        payroll_count = Payroll.objects.filter(
            employee=self.employee,
            month=self.test_month
        ).count()
        self.assertEqual(payroll_count, 1)
    
    def test_create_payroll_invalid_employee(self):
        """Test payroll creation with invalid employee"""
        idempotency_key = IdempotencyService.generate_payroll_key(
            employee_id=99999,
            month='2024-01',
            event_type='create'
        )
        
        with self.assertRaises(GovValidationError) as context:
            self.gateway.create_payroll(
                employee_id=99999,
                month=self.test_month,
                idempotency_key=idempotency_key,
                user=self.user
            )
        
        self.assertIn('Employee not found', str(context.exception))
    
    def test_create_payroll_inactive_employee(self):
        """Test payroll creation with inactive employee"""
        # Make employee inactive
        self.employee.is_active = False
        self.employee.save()
        
        idempotency_key = IdempotencyService.generate_payroll_key(
            employee_id=self.employee.id,
            month='2024-01',
            event_type='create'
        )
        
        with self.assertRaises(GovValidationError) as context:
            self.gateway.create_payroll(
                employee_id=self.employee.id,
                month=self.test_month,
                idempotency_key=idempotency_key,
                user=self.user
            )
        
        self.assertIn('Employee is not active', str(context.exception))
    
    def test_create_payroll_no_active_contract(self):
        """Test payroll creation with no active contract"""
        # Make contract inactive
        self.contract.status = 'terminated'
        self.contract.save()
        
        idempotency_key = IdempotencyService.generate_payroll_key(
            employee_id=self.employee.id,
            month='2024-01',
            event_type='create'
        )
        
        with self.assertRaises(GovValidationError) as context:
            self.gateway.create_payroll(
                employee_id=self.employee.id,
                month=self.test_month,
                idempotency_key=idempotency_key,
                user=self.user
            )
        
        self.assertIn('No active contract found', str(context.exception))
    
    def test_create_payroll_no_salary_components(self):
        """Test payroll creation with no salary components"""
        # Deactivate all salary components
        SalaryComponent.objects.filter(employee=self.employee).update(is_active=False)
        
        idempotency_key = IdempotencyService.generate_payroll_key(
            employee_id=self.employee.id,
            month='2024-01',
            event_type='create'
        )
        
        with self.assertRaises(GovValidationError) as context:
            self.gateway.create_payroll(
                employee_id=self.employee.id,
                month=self.test_month,
                idempotency_key=idempotency_key,
                user=self.user
            )
        
        self.assertIn('No active salary components found', str(context.exception))
    
    def test_create_payroll_existing_payroll(self):
        """Test payroll creation when payroll already exists for month"""
        # Create existing payroll manually
        existing_payroll = Payroll.objects.create(
            employee=self.employee,
            month=self.test_month,
            contract=self.contract,
            basic_salary=Decimal('5000.00'),
            gross_salary=Decimal('5000.00'),
            net_salary=Decimal('5000.00'),
            status='draft',
            processed_by=self.user
        )
        
        idempotency_key = IdempotencyService.generate_payroll_key(
            employee_id=self.employee.id,
            month='2024-01',
            event_type='create'
        )
        
        with self.assertRaises(GovValidationError) as context:
            self.gateway.create_payroll(
                employee_id=self.employee.id,
                month=self.test_month,
                idempotency_key=idempotency_key,
                user=self.user
            )
        
        self.assertIn('Payroll already exists', str(context.exception))


class PayrollGatewayAdvanceDeductionTest(PayrollGatewayTestCase):
    """Test advance deduction functionality in PayrollGateway"""
    
    def setUp(self):
        super().setUp()
        
        # Create advance for testing
        self.advance = Advance.objects.create(
            employee=self.employee,
            amount=Decimal('3000.00'),
            reason='Emergency advance',
            installments_count=3,
            installment_amount=Decimal('1000.00'),
            remaining_amount=Decimal('3000.00'),
            status='paid',
            deduction_start_month=self.test_month,
            payment_date=date(2023, 12, 15),
            approved_by=self.user,
            approved_at=timezone.now()
        )
    
    def test_create_payroll_with_advance_deduction(self):
        """Test payroll creation with advance deduction"""
        idempotency_key = IdempotencyService.generate_payroll_key(
            employee_id=self.employee.id,
            month='2024-01',
            event_type='create'
        )
        
        payroll = self.gateway.create_payroll(
            employee_id=self.employee.id,
            month=self.test_month,
            idempotency_key=idempotency_key,
            user=self.user
        )
        
        # Verify advance deduction was applied
        self.assertEqual(payroll.advance_deduction, Decimal('1000.00'))
        
        # Verify advance installment was created
        installment = AdvanceInstallment.objects.filter(
            advance=self.advance,
            month=self.test_month,
            payroll=payroll
        ).first()
        self.assertIsNotNone(installment)
        self.assertEqual(installment.amount, Decimal('1000.00'))
        self.assertEqual(installment.installment_number, 1)
        
        # Verify advance status was updated
        self.advance.refresh_from_db()
        self.assertEqual(self.advance.status, 'in_progress')
        self.assertEqual(self.advance.paid_installments, 1)
    
    def test_create_payroll_multiple_advances(self):
        """Test payroll creation with multiple advances"""
        # Create second advance
        advance2 = Advance.objects.create(
            employee=self.employee,
            amount=Decimal('2000.00'),
            reason='Second advance',
            installments_count=2,
            installment_amount=Decimal('1000.00'),
            remaining_amount=Decimal('2000.00'),
            status='paid',
            deduction_start_month=self.test_month,
            payment_date=date(2023, 12, 20),
            approved_by=self.user,
            approved_at=timezone.now()
        )
        
        idempotency_key = IdempotencyService.generate_payroll_key(
            employee_id=self.employee.id,
            month='2024-01',
            event_type='create'
        )
        
        payroll = self.gateway.create_payroll(
            employee_id=self.employee.id,
            month=self.test_month,
            idempotency_key=idempotency_key,
            user=self.user
        )
        
        # Verify total advance deduction (1000 + 1000 = 2000)
        self.assertEqual(payroll.advance_deduction, Decimal('2000.00'))
        
        # Verify both installments were created
        installments = AdvanceInstallment.objects.filter(
            month=self.test_month,
            payroll=payroll
        )
        self.assertEqual(installments.count(), 2)
    
    def test_create_payroll_advance_already_deducted(self):
        """Test payroll creation when advance already deducted for month"""
        # Create existing installment
        AdvanceInstallment.objects.create(
            advance=self.advance,
            month=self.test_month,
            amount=Decimal('1000.00'),
            installment_number=1
        )
        
        idempotency_key = IdempotencyService.generate_payroll_key(
            employee_id=self.employee.id,
            month='2024-01',
            event_type='create'
        )
        
        payroll = self.gateway.create_payroll(
            employee_id=self.employee.id,
            month=self.test_month,
            idempotency_key=idempotency_key,
            user=self.user
        )
        
        # Should not deduct advance again
        self.assertEqual(payroll.advance_deduction, Decimal('0.00'))
        
        # Should not create duplicate installment
        installments = AdvanceInstallment.objects.filter(
            advance=self.advance,
            month=self.test_month
        )
        self.assertEqual(installments.count(), 1)


class PayrollGatewayApprovalTest(PayrollGatewayTestCase):
    """Test payroll approval functionality"""
    
    def setUp(self):
        super().setUp()
        
        # Create a calculated payroll for approval testing
        idempotency_key = IdempotencyService.generate_payroll_key(
            employee_id=self.employee.id,
            month='2024-01',
            event_type='create'
        )
        
        self.payroll = self.gateway.create_payroll(
            employee_id=self.employee.id,
            month=self.test_month,
            idempotency_key=idempotency_key,
            user=self.user
        )
    
    def test_approve_payroll_success(self):
        """Test successful payroll approval"""
        approval_key = IdempotencyService.generate_payroll_key(
            employee_id=self.employee.id,
            month='2024-01',
            event_type='approve'
        )
        
        approved_payroll = self.gateway.approve_payroll(
            payroll=self.payroll,
            user=self.user,
            idempotency_key=approval_key,
            notes='Approved for payment'
        )
        
        # Verify approval
        self.assertEqual(approved_payroll.status, 'approved')
        self.assertEqual(approved_payroll.approved_by, self.user)
        self.assertIsNotNone(approved_payroll.approved_at)
        self.assertIn('Approved for payment', approved_payroll.notes)
        
        # Verify idempotency record
        idempotency_record = IdempotencyRecord.objects.filter(
            operation_type='payroll_approval',
            idempotency_key=approval_key
        ).first()
        self.assertIsNotNone(idempotency_record)
    
    def test_approve_payroll_invalid_status(self):
        """Test approval of payroll with invalid status"""
        # Change payroll status to approved
        self.payroll.status = 'approved'
        self.payroll.save()
        
        approval_key = IdempotencyService.generate_payroll_key(
            employee_id=self.employee.id,
            month='2024-01',
            event_type='approve'
        )
        
        with self.assertRaises(GovValidationError) as context:
            self.gateway.approve_payroll(
                payroll=self.payroll,
                user=self.user,
                idempotency_key=approval_key
            )
        
        self.assertIn('Payroll cannot be approved in status', str(context.exception))
    
    def test_approve_payroll_duplicate_idempotency(self):
        """Test duplicate payroll approval with same idempotency key"""
        approval_key = IdempotencyService.generate_payroll_key(
            employee_id=self.employee.id,
            month='2024-01',
            event_type='approve'
        )
        
        # First approval
        approved_payroll1 = self.gateway.approve_payroll(
            payroll=self.payroll,
            user=self.user,
            idempotency_key=approval_key
        )
        
        # Second approval with same key
        approved_payroll2 = self.gateway.approve_payroll(
            payroll=self.payroll,
            user=self.user,
            idempotency_key=approval_key
        )
        
        # Should return the same payroll
        self.assertEqual(approved_payroll1.id, approved_payroll2.id)
        self.assertEqual(approved_payroll2.status, 'approved')


class PayrollGatewayJournalEntryTest(PayrollGatewayTestCase):
    """Test journal entry creation for payroll"""
    
    def setUp(self):
        super().setUp()
        
        # Create a calculated payroll
        idempotency_key = IdempotencyService.generate_payroll_key(
            employee_id=self.employee.id,
            month='2024-01',
            event_type='create'
        )
        
        self.payroll = self.gateway.create_payroll(
            employee_id=self.employee.id,
            month=self.test_month,
            idempotency_key=idempotency_key,
            user=self.user
        )
    
    @patch('governance.services.payroll_gateway.AccountingGateway.create_journal_entry')
    def test_create_payroll_journal_entry(self, mock_create_journal_entry):
        """Test journal entry creation for payroll"""
        # Mock journal entry
        mock_journal_entry = MagicMock()
        mock_journal_entry.id = 123
        mock_journal_entry.number = 'JE-001'
        mock_create_journal_entry.return_value = mock_journal_entry
        
        journal_entry = self.gateway.create_payroll_journal_entry(
            payroll=self.payroll,
            user=self.user
        )
        
        # Verify AccountingGateway was called
        mock_create_journal_entry.assert_called_once()
        call_args = mock_create_journal_entry.call_args
        
        # Verify call arguments
        self.assertEqual(call_args[1]['source_module'], 'hr')
        self.assertEqual(call_args[1]['source_model'], 'Payroll')
        self.assertEqual(call_args[1]['source_id'], self.payroll.id)
        self.assertEqual(call_args[1]['user'], self.user)
        self.assertEqual(call_args[1]['entry_type'], 'payroll')
        
        # Verify journal entry lines were prepared
        lines = call_args[1]['lines']
        self.assertIsInstance(lines, list)
        self.assertTrue(len(lines) > 0)
        
        # Verify payroll was linked to journal entry
        self.payroll.refresh_from_db()
        self.assertEqual(self.payroll.journal_entry, mock_journal_entry)
    
    def test_prepare_payroll_journal_lines(self):
        """Test preparation of journal entry lines for payroll"""
        lines = self.gateway._prepare_payroll_journal_lines(self.payroll)
        
        # Should have lines for salary expense, allowances, social insurance, and net salary
        self.assertIsInstance(lines, list)
        self.assertTrue(len(lines) >= 4)
        
        # Find specific lines
        salary_line = next((line for line in lines if line.account_code == '5100'), None)
        allowance_line = next((line for line in lines if line.account_code == '5110'), None)
        insurance_line = next((line for line in lines if line.account_code == '2200'), None)
        payable_line = next((line for line in lines if line.account_code == '2100'), None)
        
        # Verify salary expense line (debit)
        self.assertIsNotNone(salary_line)
        self.assertEqual(salary_line.debit, self.payroll.basic_salary)
        self.assertEqual(salary_line.credit, Decimal('0'))
        
        # Verify allowance line (debit)
        self.assertIsNotNone(allowance_line)
        self.assertEqual(allowance_line.debit, self.payroll.allowances)
        self.assertEqual(allowance_line.credit, Decimal('0'))
        
        # Verify social insurance line (credit)
        self.assertIsNotNone(insurance_line)
        self.assertEqual(insurance_line.debit, Decimal('0'))
        self.assertEqual(insurance_line.credit, self.payroll.social_insurance)
        
        # Verify net salary payable line (credit)
        self.assertIsNotNone(payable_line)
        self.assertEqual(payable_line.debit, Decimal('0'))
        self.assertEqual(payable_line.credit, self.payroll.net_salary)


class PayrollGatewayStatisticsTest(PayrollGatewayTestCase):
    """Test PayrollGateway statistics and health monitoring"""
    
    def setUp(self):
        super().setUp()
        
        # Create multiple payrolls for statistics testing
        for i in range(3):
            month = date(2024, i + 1, 1)
            idempotency_key = IdempotencyService.generate_payroll_key(
                employee_id=self.employee.id,
                month=month.strftime('%Y-%m'),
                event_type='create'
            )
            
            self.gateway.create_payroll(
                employee_id=self.employee.id,
                month=month,
                idempotency_key=idempotency_key,
                user=self.user
            )
    
    def test_get_payroll_statistics(self):
        """Test payroll statistics generation"""
        stats = self.gateway.get_payroll_statistics()
        
        # Verify basic statistics
        self.assertEqual(stats['total_payrolls'], 3)
        self.assertIn('by_status', stats)
        self.assertIn('total_net_salary', stats)
        self.assertIn('recent_payrolls', stats)
        self.assertIn('average_net_salary', stats)
        
        # Verify status counts
        self.assertEqual(stats['by_status']['calculated'], 3)
        
        # Verify total amounts are strings (for JSON serialization)
        self.assertIsInstance(stats['total_net_salary'], str)
        self.assertIsInstance(stats['average_net_salary'], str)
    
    def test_get_health_status(self):
        """Test PayrollGateway health status"""
        health = self.gateway.get_health_status()
        
        # Verify health structure
        self.assertIn('status', health)
        self.assertIn('issues', health)
        self.assertIn('recommendations', health)
        self.assertIn('metrics', health)
        
        # Should be healthy with recent activity
        self.assertEqual(health['status'], 'healthy')
        self.assertEqual(len(health['issues']), 0)
        
        # Verify metrics
        self.assertEqual(health['metrics']['total_payrolls'], 3)
        self.assertEqual(health['metrics']['recent_activity'], 3)
    
    def test_health_status_with_negative_salaries(self):
        """Test health status detection of negative salaries"""
        # Create payroll with negative salary
        negative_payroll = Payroll.objects.create(
            employee=self.employee,
            month=date(2024, 6, 1),
            contract=self.contract,
            basic_salary=Decimal('1000.00'),
            total_deductions=Decimal('2000.00'),
            net_salary=Decimal('-1000.00'),  # Negative
            status='calculated',
            processed_by=self.user
        )
        
        health = self.gateway.get_health_status()
        
        # Should detect negative salary issue
        self.assertTrue(any('negative net salary' in issue for issue in health['issues']))
        self.assertTrue(any('Review payrolls with negative net salary' in rec for rec in health['recommendations']))


@pytest.mark.django_db
class PayrollGatewayConcurrencyTest(TransactionTestCase):
    """Test PayrollGateway thread safety and concurrency handling"""
    
    def setUp(self):
        """Set up test data for concurrency tests"""
        self.user = User.objects.create_user(
            username='payroll_admin',
            email='payroll@test.com',
            password='testpass123'
        )
        
        self.employee = Employee.objects.create(
            employee_number='EMP001',
            name='أحمد محمد',
            national_id='12345678901234',
            phone='01234567890',
            email='ahmed@test.com',
            hire_date=date(2023, 1, 1),
            is_active=True
        )
        
        self.contract = Contract.objects.create(
            employee=self.employee,
            contract_type='permanent',
            basic_salary=Decimal('5000.00'),
            start_date=date(2023, 1, 1),
            status='active'
        )
        
        SalaryComponent.objects.create(
            employee=self.employee,
            code='BASIC_SALARY',
            name='الراتب الأساسي',
            component_type='earning',
            calculation_method='fixed',
            amount=Decimal('5000.00'),
            effective_from=date(2023, 1, 1),
            is_active=True,
            order=1
        )
        
        self.gateway = PayrollGateway()
        self.test_month = date(2024, 1, 1)
    
    def test_concurrent_payroll_creation_same_idempotency_key(self):
        """Test concurrent payroll creation with same idempotency key"""
        import threading
        import time
        
        idempotency_key = IdempotencyService.generate_payroll_key(
            employee_id=self.employee.id,
            month='2024-01',
            event_type='create'
        )
        
        results = []
        errors = []
        
        def create_payroll():
            try:
                payroll = self.gateway.create_payroll(
                    employee_id=self.employee.id,
                    month=self.test_month,
                    idempotency_key=idempotency_key,
                    user=self.user
                )
                results.append(payroll)
            except Exception as e:
                errors.append(e)
        
        # Create multiple threads
        threads = []
        for i in range(3):
            thread = threading.Thread(target=create_payroll)
            threads.append(thread)
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Should have results from idempotency protection
        self.assertTrue(len(results) > 0)
        
        # All results should be the same payroll
        if len(results) > 1:
            first_payroll_id = results[0].id
            for payroll in results[1:]:
                self.assertEqual(payroll.id, first_payroll_id)
        
        # Should only have one payroll in database
        payroll_count = Payroll.objects.filter(
            employee=self.employee,
            month=self.test_month
        ).count()
        self.assertEqual(payroll_count, 1)
    
    def test_concurrent_advance_deduction(self):
        """Test concurrent advance deduction processing"""
        # Create advance
        advance = Advance.objects.create(
            employee=self.employee,
            amount=Decimal('3000.00'),
            reason='Test advance',
            installments_count=3,
            installment_amount=Decimal('1000.00'),
            remaining_amount=Decimal('3000.00'),
            status='paid',
            deduction_start_month=self.test_month,
            approved_by=self.user,
            approved_at=timezone.now()
        )
        
        import threading
        
        results = []
        errors = []
        
        def create_payroll_with_advance(month_offset):
            try:
                month = date(2024, month_offset, 1)
                idempotency_key = IdempotencyService.generate_payroll_key(
                    employee_id=self.employee.id,
                    month=month.strftime('%Y-%m'),
                    event_type='create'
                )
                
                payroll = self.gateway.create_payroll(
                    employee_id=self.employee.id,
                    month=month,
                    idempotency_key=idempotency_key,
                    user=self.user
                )
                results.append(payroll)
            except Exception as e:
                errors.append(e)
        
        # Create payrolls for different months concurrently
        threads = []
        for i in range(1, 4):  # Months 1, 2, 3
            thread = threading.Thread(target=create_payroll_with_advance, args=(i,))
            threads.append(thread)
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Should have created 3 payrolls
        self.assertEqual(len(results), 3)
        self.assertEqual(len(errors), 0)
        
        # Verify advance installments were created correctly
        installments = AdvanceInstallment.objects.filter(advance=advance)
        self.assertEqual(installments.count(), 3)
        
        # Verify advance status
        advance.refresh_from_db()
        self.assertEqual(advance.status, 'completed')
        self.assertEqual(advance.paid_installments, 3)


if __name__ == '__main__':
    pytest.main([__file__])
