"""
Test suite for payroll governance extensions.

Tests the extended governance infrastructure for payroll operations including:
- IdempotencyService payroll key generation
- AuditService payroll audit methods
- AuthorityService payroll authority boundaries
- PayrollGovernanceService functionality
- Payroll feature flags in governance switchboard
"""

import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from unittest.mock import Mock, patch, MagicMock

from governance.services import (
    IdempotencyService, AuditService, AuthorityService, PayrollGovernanceService,
    governance_switchboard
)
from governance.models import IdempotencyRecord, AuditTrail, AuthorityDelegation
from governance.exceptions import AuthorityViolationError, ValidationError

User = get_user_model()


class PayrollIdempotencyServiceTest(TestCase):
    """Test payroll-specific idempotency key generation."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
    
    def test_generate_payroll_key(self):
        """Test payroll idempotency key generation."""
        key = IdempotencyService.generate_payroll_key(
            employee_id=123,
            month='2024-01',
            event_type='create'
        )
        
        expected = 'PAYROLL:123:2024-01:create'
        self.assertEqual(key, expected)
    
    def test_generate_payroll_line_key(self):
        """Test payroll line idempotency key generation."""
        key = IdempotencyService.generate_payroll_line_key(
            payroll_id=456,
            component_code='BASIC_SALARY',
            event_type='create'
        )
        
        expected = 'PAYROLL_LINE:456:BASIC_SALARY:create'
        self.assertEqual(key, expected)
    
    def test_generate_payroll_payment_key(self):
        """Test payroll payment idempotency key generation."""
        key = IdempotencyService.generate_payroll_payment_key(
            payment_reference='PAY-20240115-1234',
            event_type='process'
        )
        
        expected = 'PAYROLL_PAYMENT:PAY-20240115-1234:process'
        self.assertEqual(key, expected)
    
    def test_generate_advance_key(self):
        """Test advance idempotency key generation."""
        key = IdempotencyService.generate_advance_key(
            employee_id=789,
            amount='5000.00',
            request_date='2024-01-15',
            event_type='create'
        )
        
        expected = 'ADVANCE:789:5000.00:2024-01-15:create'
        self.assertEqual(key, expected)
    
    def test_generate_advance_installment_key(self):
        """Test advance installment idempotency key generation."""
        key = IdempotencyService.generate_advance_installment_key(
            advance_id=101,
            month='2024-02',
            event_type='deduct'
        )
        
        expected = 'ADVANCE_INSTALLMENT:101:2024-02:deduct'
        self.assertEqual(key, expected)
    
    def test_generate_payroll_journal_entry_key(self):
        """Test payroll journal entry idempotency key generation."""
        key = IdempotencyService.generate_payroll_journal_entry_key(
            payroll_id=202,
            event_type='create'
        )
        
        expected = 'PAYROLL_JE:202:create'
        self.assertEqual(key, expected)
    
    def test_generate_salary_component_key(self):
        """Test salary component idempotency key generation."""
        key = IdempotencyService.generate_salary_component_key(
            employee_id=303,
            component_code='ALLOWANCE',
            effective_date='2024-01-01',
            event_type='create'
        )
        
        expected = 'SALARY_COMPONENT:303:ALLOWANCE:2024-01-01:create'
        self.assertEqual(key, expected)


class PayrollAuditServiceTest(TestCase):
    """Test payroll-specific audit service methods."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Mock payroll instance
        self.mock_payroll = Mock()
        self.mock_payroll.id = 123
        self.mock_payroll.employee.id = 456
        self.mock_payroll.employee.get_full_name_ar.return_value = 'أحمد محمد'
        self.mock_payroll.month = datetime(2024, 1, 1).date()
        self.mock_payroll.status = 'calculated'
        self.mock_payroll.net_salary = Decimal('5000.00')
        self.mock_payroll.gross_salary = Decimal('6000.00')
    
    @patch('governance.services.audit_service.AuditService.create_audit_record')
    def test_log_payroll_operation(self, mock_create_audit):
        """Test payroll operation audit logging."""
        mock_create_audit.return_value = Mock()
        
        result = AuditService.log_payroll_operation(
            payroll_instance=self.mock_payroll,
            operation='calculate',
            user=self.user,
            source_service='PayrollService',
            additional_context={'calculation_method': 'standard'}
        )
        
        # Verify audit record creation was called
        mock_create_audit.assert_called_once()
        call_args = mock_create_audit.call_args
        
        self.assertEqual(call_args[1]['model_name'], 'hr.Payroll')
        self.assertEqual(call_args[1]['object_id'], 123)
        self.assertEqual(call_args[1]['operation'], 'calculate')
        self.assertEqual(call_args[1]['user'], self.user)
        self.assertEqual(call_args[1]['source_service'], 'PayrollService')
        
        # Check payroll-specific context
        context = call_args[1]['additional_context']
        self.assertEqual(context['employee_id'], 456)
        self.assertEqual(context['employee_name'], 'أحمد محمد')
        self.assertEqual(context['month'], '2024-01')
        self.assertEqual(context['status'], 'calculated')
        self.assertEqual(context['net_salary'], '5000.00')
        self.assertEqual(context['operation_type'], 'payroll_operation')
        self.assertEqual(context['calculation_method'], 'standard')
    
    @patch('governance.services.audit_service.AuditService.create_audit_record')
    def test_log_payroll_payment_operation(self, mock_create_audit):
        """Test payroll payment operation audit logging."""
        mock_create_audit.return_value = Mock()
        
        # Mock payment instance
        mock_payment = Mock()
        mock_payment.id = 789
        mock_payment.payment_reference = 'PAY-20240115-1234'
        mock_payment.payment_type = 'batch'
        mock_payment.payment_method = 'bank_transfer'
        mock_payment.total_amount = Decimal('50000.00')
        mock_payment.net_amount = Decimal('48000.00')
        mock_payment.status = 'processing'
        mock_payment.payment_date = datetime(2024, 1, 15).date()
        
        result = AuditService.log_payroll_payment_operation(
            payment_instance=mock_payment,
            operation='process',
            user=self.user,
            source_service='PayrollPaymentService'
        )
        
        # Verify audit record creation was called
        mock_create_audit.assert_called_once()
        call_args = mock_create_audit.call_args
        
        self.assertEqual(call_args[1]['model_name'], 'hr.PayrollPayment')
        self.assertEqual(call_args[1]['object_id'], 789)
        self.assertEqual(call_args[1]['operation'], 'process')
        
        # Check payment-specific context
        context = call_args[1]['additional_context']
        self.assertEqual(context['payment_reference'], 'PAY-20240115-1234')
        self.assertEqual(context['payment_type'], 'batch')
        self.assertEqual(context['payment_method'], 'bank_transfer')
        self.assertEqual(context['total_amount'], '50000.00')
        self.assertEqual(context['operation_type'], 'payroll_payment_operation')
    
    @patch('governance.services.audit_service.AuditService.create_audit_record')
    def test_log_advance_operation(self, mock_create_audit):
        """Test advance operation audit logging."""
        mock_create_audit.return_value = Mock()
        
        # Mock advance instance
        mock_advance = Mock()
        mock_advance.id = 999
        mock_advance.employee.id = 456
        mock_advance.employee.get_full_name_ar.return_value = 'أحمد محمد'
        mock_advance.amount = Decimal('3000.00')
        mock_advance.installments_count = 6
        mock_advance.remaining_amount = Decimal('2500.00')
        mock_advance.paid_installments = 1
        mock_advance.status = 'in_progress'
        
        result = AuditService.log_advance_operation(
            advance_instance=mock_advance,
            operation='deduct',
            user=self.user,
            source_service='AdvanceService'
        )
        
        # Verify audit record creation was called
        mock_create_audit.assert_called_once()
        call_args = mock_create_audit.call_args
        
        self.assertEqual(call_args[1]['model_name'], 'hr.Advance')
        self.assertEqual(call_args[1]['object_id'], 999)
        self.assertEqual(call_args[1]['operation'], 'deduct')
        
        # Check advance-specific context
        context = call_args[1]['additional_context']
        self.assertEqual(context['employee_id'], 456)
        self.assertEqual(context['amount'], '3000.00')
        self.assertEqual(context['installments_count'], 6)
        self.assertEqual(context['remaining_amount'], '2500.00')
        self.assertEqual(context['paid_installments'], 1)
        self.assertEqual(context['status'], 'in_progress')
        self.assertEqual(context['operation_type'], 'advance_operation')


class PayrollAuthorityServiceTest(TestCase):
    """Test payroll-specific authority service methods."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
    
    def test_payroll_authority_matrix(self):
        """Test that payroll models are in authority matrix."""
        payroll_models = [
            'Payroll', 'PayrollLine', 'PayrollPayment', 'PayrollPaymentLine',
            'Advance', 'AdvanceInstallment', 'SalaryComponent', 'PayrollPeriod',
            'Contract', 'Employee'
        ]
        
        for model in payroll_models:
            self.assertIn(model, AuthorityService.AUTHORITY_MATRIX)
            authoritative_service = AuthorityService.get_authoritative_service(model)
            self.assertIsNotNone(authoritative_service)
    
    def test_payroll_critical_models(self):
        """Test that critical payroll models are marked as critical."""
        critical_payroll_models = ['Payroll', 'PayrollPayment', 'Advance']
        
        for model in critical_payroll_models:
            self.assertIn(model, AuthorityService.CRITICAL_MODELS)
    
    def test_validate_payroll_authority_success(self):
        """Test successful payroll authority validation."""
        # Should not raise exception for authorized service
        result = AuthorityService.validate_payroll_authority(
            service_name='PayrollService',
            operation='CREATE',
            user=self.user
        )
        self.assertTrue(result)
    
    def test_validate_payroll_authority_violation(self):
        """Test payroll authority violation."""
        with self.assertRaises(AuthorityViolationError):
            AuthorityService.validate_payroll_authority(
                service_name='UnauthorizedService',
                operation='CREATE',
                user=self.user
            )
    
    def test_validate_payroll_payment_authority_success(self):
        """Test successful payroll payment authority validation."""
        result = AuthorityService.validate_payroll_payment_authority(
            service_name='PayrollPaymentService',
            operation='CREATE',
            user=self.user
        )
        self.assertTrue(result)
    
    def test_validate_advance_authority_success(self):
        """Test successful advance authority validation."""
        result = AuthorityService.validate_advance_authority(
            service_name='AdvanceService',
            operation='CREATE',
            user=self.user
        )
        self.assertTrue(result)
    
    def test_validate_salary_component_authority_success(self):
        """Test successful salary component authority validation."""
        result = AuthorityService.validate_salary_component_authority(
            service_name='SalaryComponentService',
            operation='CREATE',
            user=self.user
        )
        self.assertTrue(result)


class PayrollGovernanceServiceTest(TestCase):
    """Test PayrollGovernanceService functionality."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
    
    def test_payroll_feature_flags(self):
        """Test payroll feature flag definitions."""
        expected_flags = [
            'payroll_idempotency_enforcement',
            'payroll_authority_enforcement',
            'payroll_audit_trail_enforcement',
            'payroll_calculation_validation',
            'payroll_payment_validation',
            'advance_deduction_validation',
            'salary_component_validation',
            'payroll_batch_processing',
            'payroll_journal_entry_creation',
            'payroll_period_lock_enforcement',
        ]
        
        for flag in expected_flags:
            self.assertIn(flag, PayrollGovernanceService.PAYROLL_FEATURE_FLAGS)
    
    @patch('governance.services.payroll_governance_service.governance_switchboard')
    def test_is_payroll_feature_enabled(self, mock_switchboard):
        """Test payroll feature flag checking."""
        mock_switchboard.is_component_enabled.return_value = True
        
        # Test enabled feature
        result = PayrollGovernanceService.is_payroll_feature_enabled('payroll_idempotency_enforcement')
        self.assertTrue(result)
        
        # Test disabled governance
        mock_switchboard.is_component_enabled.return_value = False
        result = PayrollGovernanceService.is_payroll_feature_enabled('payroll_idempotency_enforcement')
        self.assertFalse(result)
    
    @patch('governance.services.payroll_governance_service.AuthorityService')
    @patch('governance.services.payroll_governance_service.IdempotencyService')
    def test_validate_payroll_operation(self, mock_idempotency, mock_authority):
        """Test payroll operation validation."""
        # Mock successful validation
        mock_authority.validate_payroll_authority.return_value = True
        mock_idempotency.check_operation_exists.return_value = (False, None, None)
        
        payroll_data = {
            'employee_id': 123,
            'month': '2024-01',
            'basic_salary': '5000.00',
            'net_salary': '4500.00',
            'status': 'draft'
        }
        
        with patch.object(PayrollGovernanceService, 'is_payroll_feature_enabled', return_value=True):
            result = PayrollGovernanceService.validate_payroll_operation(
                operation_type='create',
                payroll_data=payroll_data,
                user=self.user,
                source_service='PayrollService'
            )
        
        self.assertTrue(result['valid'])
        self.assertEqual(len(result['errors']), 0)
        self.assertIn('governance_checks', result)
    
    def test_validate_payroll_business_rules(self):
        """Test payroll business rules validation."""
        # Test valid payroll data
        payroll_data = {
            'basic_salary': '5000.00',
            'net_salary': '4500.00',
            'status': 'calculated'
        }
        
        result = PayrollGovernanceService._validate_payroll_business_rules(
            'approve', payroll_data
        )
        
        self.assertTrue(result['valid'])
        self.assertEqual(len(result['errors']), 0)
        
        # Test invalid payroll data
        invalid_data = {
            'basic_salary': '0',  # Invalid
            'net_salary': '-100',  # Invalid
            'status': 'draft'  # Invalid for approve operation
        }
        
        result = PayrollGovernanceService._validate_payroll_business_rules(
            'approve', invalid_data
        )
        
        self.assertFalse(result['valid'])
        self.assertGreater(len(result['errors']), 0)
    
    def test_get_payroll_governance_status(self):
        """Test payroll governance status retrieval."""
        with patch.object(governance_switchboard, 'is_component_enabled', return_value=True):
            status = PayrollGovernanceService.get_payroll_governance_status()
        
        self.assertIn('enabled', status)
        self.assertIn('features', status)
        self.assertIn('statistics', status)
        self.assertIn('health', status)


class PayrollGovernanceSwitchboardTest(TestCase):
    """Test payroll feature flags in governance switchboard."""
    
    def test_payroll_component_flags(self):
        """Test that payroll component flags are defined."""
        payroll_components = [
            'payroll_governance',
            'payroll_authority_enforcement',
            'payroll_idempotency_enforcement',
            'payroll_audit_enforcement',
            'payroll_journal_entry_enforcement'
        ]
        
        for component in payroll_components:
            self.assertIn(component, governance_switchboard.COMPONENT_FLAGS)
            flag_config = governance_switchboard.COMPONENT_FLAGS[component]
            self.assertIn('name', flag_config)
            self.assertIn('description', flag_config)
            self.assertIn('default', flag_config)
            self.assertIn('critical', flag_config)
    
    def test_payroll_workflow_flags(self):
        """Test that payroll workflow flags are defined."""
        payroll_workflows = [
            'payroll_calculation_workflow',
            'payroll_payment_workflow',
            'payroll_to_journal_entry_workflow',
            'advance_management_workflow',
            'salary_component_workflow'
        ]
        
        for workflow in payroll_workflows:
            self.assertIn(workflow, governance_switchboard.WORKFLOW_FLAGS)
            flag_config = governance_switchboard.WORKFLOW_FLAGS[workflow]
            self.assertIn('name', flag_config)
            self.assertIn('description', flag_config)
            self.assertIn('default', flag_config)
            self.assertIn('critical', flag_config)
            self.assertIn('component_dependencies', flag_config)
            self.assertIn('risk_level', flag_config)
            self.assertIn('corruption_prevention', flag_config)
    
    def test_payroll_flag_dependencies(self):
        """Test that payroll flags have correct dependencies."""
        # Test component dependencies
        payroll_authority = governance_switchboard.COMPONENT_FLAGS['payroll_authority_enforcement']
        self.assertIn('authority_boundary_enforcement', payroll_authority['dependencies'])
        
        payroll_idempotency = governance_switchboard.COMPONENT_FLAGS['payroll_idempotency_enforcement']
        self.assertIn('idempotency_enforcement', payroll_idempotency['dependencies'])
        
        # Test workflow dependencies
        payroll_calculation = governance_switchboard.WORKFLOW_FLAGS['payroll_calculation_workflow']
        self.assertIn('payroll_governance', payroll_calculation['component_dependencies'])
        self.assertIn('payroll_authority_enforcement', payroll_calculation['component_dependencies'])


@pytest.mark.django_db
class PayrollGovernanceIntegrationTest(TransactionTestCase):
    """Integration tests for payroll governance system."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
    
    def test_payroll_idempotency_integration(self):
        """Test end-to-end payroll idempotency protection."""
        # Generate idempotency key
        key = IdempotencyService.generate_payroll_key(
            employee_id=123,
            month='2024-01',
            event_type='create'
        )
        
        # First operation should succeed
        result_data = {'payroll_id': 456, 'status': 'created'}
        is_duplicate, record = IdempotencyService.check_and_record_operation(
            operation_type='payroll_operation',
            idempotency_key=key,
            result_data=result_data,
            user=self.user
        )
        
        self.assertFalse(is_duplicate)
        self.assertIsNotNone(record)
        
        # Second operation should be detected as duplicate
        is_duplicate, record = IdempotencyService.check_and_record_operation(
            operation_type='payroll_operation',
            idempotency_key=key,
            result_data=result_data,
            user=self.user
        )
        
        self.assertTrue(is_duplicate)
        self.assertEqual(record.result_data, result_data)
    
    def test_payroll_authority_integration(self):
        """Test end-to-end payroll authority enforcement."""
        # Test authorized access
        try:
            AuthorityService.validate_payroll_authority(
                service_name='PayrollService',
                operation='CREATE',
                user=self.user
            )
        except AuthorityViolationError:
            self.fail("Authorized service should not raise violation")
        
        # Test unauthorized access
        with self.assertRaises(AuthorityViolationError):
            AuthorityService.validate_payroll_authority(
                service_name='UnauthorizedService',
                operation='CREATE',
                user=self.user
            )
    
    @patch('governance.services.audit_service.AuditService.create_audit_record')
    def test_payroll_audit_integration(self, mock_create_audit):
        """Test end-to-end payroll audit trail creation."""
        mock_create_audit.return_value = Mock()
        
        # Mock payroll instance
        mock_payroll = Mock()
        mock_payroll.id = 123
        mock_payroll.employee.id = 456
        mock_payroll.employee.get_full_name_ar.return_value = 'أحمد محمد'
        mock_payroll.month = datetime(2024, 1, 1).date()
        mock_payroll.status = 'calculated'
        mock_payroll.net_salary = Decimal('5000.00')
        mock_payroll.gross_salary = Decimal('6000.00')
        
        # Create audit record
        audit_record = PayrollGovernanceService.create_payroll_audit_record(
            payroll_instance=mock_payroll,
            operation='calculate',
            user=self.user,
            source_service='PayrollService'
        )
        
        # Verify audit record was created
        mock_create_audit.assert_called_once()


if __name__ == '__main__':
    pytest.main([__file__])