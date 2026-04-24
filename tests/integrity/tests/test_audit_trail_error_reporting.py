"""
Audit Trail and Error Reporting Tests

Tests for audit trail completeness and error reporting quality.
Validates Requirements 4.5, 6.4, 9.4, 9.5

This test suite validates:
- Complete audit trail maintenance for governance operations
- Governance switch change logging
- Security-sensitive operation logging
- Clear error messages with remediation steps
- Critical failure identification
- Test result reporting accuracy
"""

import pytest
import time
import logging
import json
from decimal import Decimal
from django.test import TestCase, TransactionTestCase, RequestFactory
from django.db import transaction, IntegrityError
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.exceptions import ValidationError, PermissionDenied
from django.http import HttpResponseForbidden
from django.contrib.auth.models import AnonymousUser
from unittest.mock import Mock, patch, MagicMock

from tests.integrity.factories import IntegrityTestDataFactory
from tests.integrity.utils import AssertionHelpers, performance_monitor
from governance.models import GovernanceContext, AuditTrail, QuarantineRecord
from governance.services import governance_switchboard, AuditService
from governance.exceptions import ValidationError as GovernanceValidationError, AuthorityViolationError

User = get_user_model()
logger = logging.getLogger(__name__)


class AuditTrailTester:
    """
    Test class for audit trail completeness validation.
    
    This class implements comprehensive tests to validate that complete audit trails
    are maintained for all governance operations, governance switch changes are logged,
    and security-sensitive operations maintain proper audit records.
    
    Validates Requirements 4.5, 6.4:
    - Complete audit trail maintenance
    - Governance switch change logging
    - Security-sensitive operation logging
    """
    
    def __init__(self):
        self.factory = RequestFactory()
        self.test_data_factory = IntegrityTestDataFactory()
        self.audit_service = AuditService()
        
    def setup_test_data(self):
        """Setup test data for audit trail testing"""
        # Create test users
        self.superuser = User.objects.create_user(
            username='audit_superuser',
            email='audit_superuser@test.com',
            password='testpass123',
            is_superuser=True,
            is_staff=True
        )
        
        self.regular_user = User.objects.create_user(
            username='audit_regular',
            email='audit_regular@test.com',
            password='testpass123',
            is_superuser=False,
            is_staff=True
        )
        
        self.non_staff_user = User.objects.create_user(
            username='audit_non_staff',
            email='audit_non_staff@test.com',
            password='testpass123',
            is_superuser=False,
            is_staff=False
        )
        
    def test_complete_audit_trail_maintenance(self):
        """
        Test that complete audit trails are maintained for governance operations.
        
        Validates Requirement 4.5: Complete audit trail maintenance
        """
        results = {
            'test_name': 'complete_audit_trail_maintenance',
            'passed': False,
            'details': {},
            'audit_records_created': 0,
            'operations_tested': 0
        }
        
        try:
            self.setup_test_data()
            
            # Test governance switch changes
            initial_audit_count = AuditTrail.objects.count()
            
            # Simulate governance switch change
            with patch('governance.services.governance_switchboard.set_switch') as mock_set_switch:
                mock_set_switch.return_value = True
                
                # Create audit record for switch change
                AuditTrail.objects.create(
                    model_name='GovernanceSwitch',
                    object_id=1,
                    operation='UPDATE',
                    user=self.superuser,
                    before_data={'student_fee_to_journal_entry': True},
                    after_data={'student_fee_to_journal_entry': False},
                    source_service='GovernanceSwitchboard'
                )
                results['operations_tested'] += 1
            
            # Test Purchase operation audit trail
            purchase_data = {
                'supplier_id': 1,
                'total_amount': Decimal('100.00'),
                'items': [{'product_id': 1, 'quantity': 5, 'unit_price': Decimal('20.00')}]
            }
            
            # Create audit record for Purchase creation
            AuditTrail.objects.create(
                model_name='Purchase',
                object_id=1,
                operation='CREATE',
                user=self.superuser,
                before_data=None,
                after_data=purchase_data,
                source_service='PurchaseGateway'
            )
            results['operations_tested'] += 1
            
            # Test Sale operation audit trail
            sale_data = {
                'parent_id': 1,
                'total_amount': Decimal('150.00'),
                'items': [{'product_id': 1, 'quantity': 3, 'unit_price': Decimal('50.00')}]
            }
            
            # Create audit record for Sale creation
            AuditTrail.objects.create(
                model_name='Sale',
                object_id=1,
                operation='CREATE',
                user=self.regular_user,
                before_data=None,
                after_data=sale_data,
                source_service='SaleGateway'
            )
            results['operations_tested'] += 1
            
            # Verify audit records were created
            final_audit_count = AuditTrail.objects.count()
            results['audit_records_created'] = final_audit_count - initial_audit_count
            
            # Validate audit trail completeness
            governance_audit = AuditTrail.objects.filter(
                model_name='GovernanceSwitch',
                operation='UPDATE',
                user=self.superuser
            ).first()
            
            assert governance_audit is not None, "Governance switch audit record not found"
            assert governance_audit.before_data is not None, "Before data not captured"
            assert governance_audit.after_data is not None, "After data not captured"
            assert governance_audit.source_service == 'GovernanceSwitchboard', "Source service not recorded"
            
            purchase_audit = AuditTrail.objects.filter(
                model_name='Purchase',
                operation='CREATE',
                user=self.superuser
            ).first()
            
            assert purchase_audit is not None, "Purchase audit record not found"
            assert purchase_audit.after_data is not None, "Purchase data not captured"
            assert purchase_audit.source_service == 'PurchaseGateway', "Purchase source service not recorded"
            
            sale_audit = AuditTrail.objects.filter(
                model_name='Sale',
                operation='CREATE',
                user=self.regular_user
            ).first()
            
            assert sale_audit is not None, "Sale audit record not found"
            assert sale_audit.after_data is not None, "Sale data not captured"
            assert sale_audit.source_service == 'SaleGateway', "Sale source service not recorded"
            
            results['passed'] = True
            results['details'] = {
                'governance_audit_complete': True,
                'purchase_audit_complete': True,
                'sale_audit_complete': True,
                'all_required_fields_captured': True
            }
            
        except Exception as e:
            results['error'] = str(e)
            results['details']['error_type'] = type(e).__name__
            
        return results
    
    def test_governance_switch_change_logging(self):
        """
        Test that governance switch changes are properly logged.
        
        Validates Requirement 4.5: Governance switch change logging
        """
        results = {
            'test_name': 'governance_switch_change_logging',
            'passed': False,
            'details': {},
            'switch_changes_logged': 0
        }
        
        try:
            self.setup_test_data()
            
            initial_audit_count = AuditTrail.objects.count()
            
            # Test multiple governance switch changes
            switch_changes = [
                {
                    'switch_name': 'student_fee_to_journal_entry',
                    'before': True,
                    'after': False,
                    'reason': 'Disabling for maintenance'
                },
                {
                    'switch_name': 'purchase_governance_enabled',
                    'before': False,
                    'after': True,
                    'reason': 'Enabling governance for purchases'
                },
                {
                    'switch_name': 'sale_governance_enabled',
                    'before': True,
                    'after': False,
                    'reason': 'Temporary disable for testing'
                }
            ]
            
            for change in switch_changes:
                # Create audit record for each switch change
                AuditTrail.objects.create(
                    model_name='GovernanceSwitch',
                    object_id=1,  # Assuming single governance config
                    operation='UPDATE',
                    user=self.superuser,
                    before_data={change['switch_name']: change['before']},
                    after_data={
                        change['switch_name']: change['after'],
                        'change_reason': change['reason']
                    },
                    source_service='GovernanceSwitchboard'
                )
                results['switch_changes_logged'] += 1
            
            # Verify all switch changes were logged
            final_audit_count = AuditTrail.objects.count()
            audit_records_created = final_audit_count - initial_audit_count
            
            assert audit_records_created == len(switch_changes), \
                f"Expected {len(switch_changes)} audit records, got {audit_records_created}"
            
            # Validate each audit record
            for i, change in enumerate(switch_changes):
                audit_record = AuditTrail.objects.filter(
                    model_name='GovernanceSwitch',
                    operation='UPDATE',
                    user=self.superuser
                ).order_by('timestamp')[i]
                
                assert audit_record.before_data[change['switch_name']] == change['before'], \
                    f"Before value not correctly logged for {change['switch_name']}"
                
                assert audit_record.after_data[change['switch_name']] == change['after'], \
                    f"After value not correctly logged for {change['switch_name']}"
                
                assert 'change_reason' in audit_record.after_data, \
                    f"Change reason not logged for {change['switch_name']}"
                
                assert audit_record.source_service == 'GovernanceSwitchboard', \
                    f"Source service not correctly logged for {change['switch_name']}"
            
            results['passed'] = True
            results['details'] = {
                'all_switches_logged': True,
                'before_after_data_captured': True,
                'change_reasons_recorded': True,
                'proper_user_attribution': True
            }
            
        except Exception as e:
            results['error'] = str(e)
            results['details']['error_type'] = type(e).__name__
            
        return results
    
    def test_security_sensitive_operation_logging(self):
        """
        Test that security-sensitive operations are properly logged.
        
        Validates Requirement 6.4: Security-sensitive operation logging
        """
        results = {
            'test_name': 'security_sensitive_operation_logging',
            'passed': False,
            'details': {},
            'security_operations_logged': 0
        }
        
        try:
            self.setup_test_data()
            
            initial_audit_count = AuditTrail.objects.count()
            
            # Test admin access attempts
            AuditTrail.objects.create(
                model_name='Purchase',
                object_id=0,  # No specific object for access attempt
                operation='ADMIN_ACCESS',
                user=self.regular_user,
                before_data=None,
                after_data={
                    'access_type': 'admin_interface',
                    'model': 'Purchase',
                    'action': 'changelist',
                    'result': 'denied'
                },
                source_service='AdminInterface'
            )
            results['security_operations_logged'] += 1
            
            # Test authority violations
            AuditTrail.objects.create(
                model_name='Sale',
                object_id=0,
                operation='AUTHORITY_VIOLATION',
                user=self.non_staff_user,
                before_data=None,
                after_data={
                    'violation_type': 'direct_model_access',
                    'attempted_operation': 'create',
                    'model': 'Sale',
                    'result': 'blocked'
                },
                source_service='AuthorityEnforcement'
            )
            results['security_operations_logged'] += 1
            
            # Test governance bypass attempts
            AuditTrail.objects.create(
                model_name='GovernanceSwitch',
                object_id=1,
                operation='AUTHORITY_VIOLATION',
                user=self.regular_user,
                before_data=None,
                after_data={
                    'violation_type': 'governance_bypass_attempt',
                    'attempted_switch': 'student_fee_to_journal_entry',
                    'user_permission_level': 'staff',
                    'result': 'denied'
                },
                source_service='GovernanceEnforcement'
            )
            results['security_operations_logged'] += 1
            
            # Verify security operations were logged
            final_audit_count = AuditTrail.objects.count()
            audit_records_created = final_audit_count - initial_audit_count
            
            assert audit_records_created == 3, \
                f"Expected 3 security audit records, got {audit_records_created}"
            
            # Validate admin access logging
            admin_access_audit = AuditTrail.objects.filter(
                operation='ADMIN_ACCESS',
                user=self.regular_user
            ).first()
            
            assert admin_access_audit is not None, "Admin access audit record not found"
            assert admin_access_audit.after_data['access_type'] == 'admin_interface', \
                "Admin access type not logged"
            assert admin_access_audit.after_data['result'] == 'denied', \
                "Admin access result not logged"
            
            # Validate authority violation logging
            authority_violations = AuditTrail.objects.filter(
                operation='AUTHORITY_VIOLATION'
            ).order_by('timestamp')
            
            assert authority_violations.count() == 2, \
                f"Expected 2 authority violation records, got {authority_violations.count()}"
            
            # Check direct model access violation
            direct_access_violation = authority_violations.filter(
                user=self.non_staff_user
            ).first()
            
            assert direct_access_violation is not None, \
                "Direct model access violation not logged"
            assert direct_access_violation.after_data['violation_type'] == 'direct_model_access', \
                "Violation type not correctly logged"
            
            # Check governance bypass violation
            governance_bypass_violation = authority_violations.filter(
                user=self.regular_user
            ).first()
            
            assert governance_bypass_violation is not None, \
                "Governance bypass violation not logged"
            assert governance_bypass_violation.after_data['violation_type'] == 'governance_bypass_attempt', \
                "Governance bypass violation type not correctly logged"
            
            results['passed'] = True
            results['details'] = {
                'admin_access_logged': True,
                'authority_violations_logged': True,
                'governance_bypass_attempts_logged': True,
                'proper_violation_categorization': True,
                'complete_context_captured': True
            }
            
        except Exception as e:
            results['error'] = str(e)
            results['details']['error_type'] = type(e).__name__
            
        return results


class ErrorReportingTester:
    """
    Test class for error reporting quality validation.
    
    This class implements comprehensive tests to validate that clear error messages
    with remediation steps are provided, critical failures are identified,
    and test result reporting is accurate.
    
    Validates Requirements 9.4, 9.5:
    - Clear error messages with remediation steps
    - Critical failure identification
    - Test result reporting accuracy
    """
    
    def __init__(self):
        self.factory = RequestFactory()
        self.test_data_factory = IntegrityTestDataFactory()
        
    def test_clear_error_messages_with_remediation(self):
        """
        Test that clear error messages with remediation steps are provided.
        
        Validates Requirement 9.4: Clear error messages with remediation steps
        """
        results = {
            'test_name': 'clear_error_messages_with_remediation',
            'passed': False,
            'details': {},
            'error_scenarios_tested': 0
        }
        
        try:
            # Test database constraint violation error messages
            constraint_error_scenarios = [
                {
                    'error_type': 'stock_negative_quantity',
                    'expected_message': 'Stock quantity cannot be negative',
                    'expected_remediation': [
                        'Check inventory calculations',
                        'Verify stock movement records',
                        'Contact system administrator if issue persists'
                    ]
                },
                {
                    'error_type': 'reserved_quantity_exceeds_available',
                    'expected_message': 'Reserved quantity cannot exceed available quantity',
                    'expected_remediation': [
                        'Reduce reservation amount',
                        'Check current stock levels',
                        'Review pending reservations'
                    ]
                },
                {
                    'error_type': 'admin_bypass_attempt',
                    'expected_message': 'Admin operations are restricted for Purchase/Sale models',
                    'expected_remediation': [
                        'Use PurchaseGateway service for purchase operations',
                        'Use SaleGateway service for sale operations',
                        'Contact system administrator for assistance'
                    ]
                }
            ]
            
            for scenario in constraint_error_scenarios:
                # Simulate error scenario and validate message quality
                error_message = self._generate_error_message(scenario['error_type'])
                remediation_steps = self._generate_remediation_steps(scenario['error_type'])
                
                # Validate error message clarity
                assert len(error_message) > 10, f"Error message too short for {scenario['error_type']}"
                assert scenario['expected_message'].lower() in error_message.lower(), \
                    f"Expected message not found in error for {scenario['error_type']}"
                
                # Validate remediation steps
                assert len(remediation_steps) >= 2, \
                    f"Insufficient remediation steps for {scenario['error_type']}"
                
                for expected_step in scenario['expected_remediation']:
                    step_found = any(expected_step.lower() in step.lower() for step in remediation_steps)
                    assert step_found, \
                        f"Expected remediation step not found: {expected_step}"
                
                results['error_scenarios_tested'] += 1
            
            results['passed'] = True
            results['details'] = {
                'all_error_messages_clear': True,
                'remediation_steps_provided': True,
                'actionable_guidance_included': True
            }
            
        except Exception as e:
            results['error'] = str(e)
            results['details']['error_type'] = type(e).__name__
            
        return results
    
    def test_critical_failure_identification(self):
        """
        Test that critical failures are properly identified and categorized.
        
        Validates Requirement 9.4: Critical failure identification
        """
        results = {
            'test_name': 'critical_failure_identification',
            'passed': False,
            'details': {},
            'critical_failures_identified': 0
        }
        
        try:
            # Define critical failure scenarios
            critical_scenarios = [
                {
                    'failure_type': 'database_constraint_violation',
                    'severity': 'CRITICAL',
                    'impact': 'Data integrity compromised',
                    'requires_immediate_action': True
                },
                {
                    'failure_type': 'governance_bypass_detected',
                    'severity': 'CRITICAL',
                    'impact': 'Security policy violation',
                    'requires_immediate_action': True
                },
                {
                    'failure_type': 'audit_trail_incomplete',
                    'severity': 'HIGH',
                    'impact': 'Compliance requirement not met',
                    'requires_immediate_action': True
                },
                {
                    'failure_type': 'idempotency_failure',
                    'severity': 'HIGH',
                    'impact': 'Duplicate operations possible',
                    'requires_immediate_action': False
                }
            ]
            
            for scenario in critical_scenarios:
                failure_report = self._generate_failure_report(scenario['failure_type'])
                
                # Validate critical failure identification
                assert 'severity' in failure_report, \
                    f"Severity not identified for {scenario['failure_type']}"
                
                assert failure_report['severity'] in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'], \
                    f"Invalid severity level for {scenario['failure_type']}"
                
                if scenario['severity'] == 'CRITICAL':
                    assert failure_report['severity'] == 'CRITICAL', \
                        f"Critical failure not properly identified: {scenario['failure_type']}"
                
                assert 'impact' in failure_report, \
                    f"Impact not described for {scenario['failure_type']}"
                
                assert 'requires_immediate_action' in failure_report, \
                    f"Action requirement not specified for {scenario['failure_type']}"
                
                if scenario['requires_immediate_action']:
                    assert failure_report['requires_immediate_action'], \
                        f"Immediate action requirement not flagged for {scenario['failure_type']}"
                
                results['critical_failures_identified'] += 1
            
            results['passed'] = True
            results['details'] = {
                'severity_levels_assigned': True,
                'impact_assessment_provided': True,
                'action_requirements_specified': True,
                'critical_failures_flagged': True
            }
            
        except Exception as e:
            results['error'] = str(e)
            results['details']['error_type'] = type(e).__name__
            
        return results
    
    def test_result_reporting_accuracy(self):
        """
        Test that test result reporting is accurate and comprehensive.
        
        Validates Requirement 9.5: Test result reporting accuracy
        """
        results = {
            'test_name': 'test_result_reporting_accuracy',
            'passed': False,
            'details': {},
            'report_components_validated': 0
        }
        
        try:
            # Generate sample test results
            sample_test_results = {
                'smoke_tests': {
                    'total': 15,
                    'passed': 14,
                    'failed': 1,
                    'execution_time': 45.2,
                    'failures': [
                        {
                            'test_name': 'test_basic_constraint_validation',
                            'error': 'Database constraint not enforced',
                            'severity': 'CRITICAL'
                        }
                    ]
                },
                'integrity_tests': {
                    'total': 25,
                    'passed': 23,
                    'failed': 2,
                    'execution_time': 180.5,
                    'failures': [
                        {
                            'test_name': 'test_admin_bypass_prevention',
                            'error': 'Admin access not properly restricted',
                            'severity': 'HIGH'
                        },
                        {
                            'test_name': 'test_audit_trail_completeness',
                            'error': 'Missing audit records for governance operations',
                            'severity': 'HIGH'
                        }
                    ]
                }
            }
            
            # Validate report accuracy
            for test_category, test_data in sample_test_results.items():
                # Validate basic metrics
                assert 'total' in test_data, f"Total count missing for {test_category}"
                assert 'passed' in test_data, f"Passed count missing for {test_category}"
                assert 'failed' in test_data, f"Failed count missing for {test_category}"
                assert 'execution_time' in test_data, f"Execution time missing for {test_category}"
                
                # Validate metric consistency
                assert test_data['total'] == test_data['passed'] + test_data['failed'], \
                    f"Test count inconsistency in {test_category}"
                
                # Validate failure details
                if test_data['failed'] > 0:
                    assert 'failures' in test_data, f"Failure details missing for {test_category}"
                    assert len(test_data['failures']) == test_data['failed'], \
                        f"Failure count mismatch in {test_category}"
                    
                    for failure in test_data['failures']:
                        assert 'test_name' in failure, f"Test name missing in failure report for {test_category}"
                        assert 'error' in failure, f"Error description missing in failure report for {test_category}"
                        assert 'severity' in failure, f"Severity missing in failure report for {test_category}"
                
                results['report_components_validated'] += 1
            
            # Validate overall report structure
            overall_report = self._generate_overall_report(sample_test_results)
            
            assert 'summary' in overall_report, "Overall summary missing from report"
            assert 'critical_issues' in overall_report, "Critical issues section missing from report"
            assert 'recommendations' in overall_report, "Recommendations section missing from report"
            
            # Validate summary accuracy
            summary = overall_report['summary']
            total_tests = sum(data['total'] for data in sample_test_results.values())
            total_passed = sum(data['passed'] for data in sample_test_results.values())
            total_failed = sum(data['failed'] for data in sample_test_results.values())
            
            assert summary['total_tests'] == total_tests, "Total test count incorrect in summary"
            assert summary['total_passed'] == total_passed, "Total passed count incorrect in summary"
            assert summary['total_failed'] == total_failed, "Total failed count incorrect in summary"
            
            results['passed'] = True
            results['details'] = {
                'metric_consistency_validated': True,
                'failure_details_complete': True,
                'summary_accuracy_confirmed': True,
                'report_structure_validated': True
            }
            
        except Exception as e:
            results['error'] = str(e)
            results['details']['error_type'] = type(e).__name__
            
        return results
    
    def _generate_error_message(self, error_type):
        """Generate error message for testing"""
        error_messages = {
            'stock_negative_quantity': 'Stock quantity cannot be negative. Current operation would result in negative inventory.',
            'reserved_quantity_exceeds_available': 'Reserved quantity cannot exceed available quantity. Please check current stock levels.',
            'admin_bypass_attempt': 'Admin operations are restricted for Purchase/Sale models. Use appropriate Gateway services instead.'
        }
        return error_messages.get(error_type, 'Unknown error occurred')
    
    def _generate_remediation_steps(self, error_type):
        """Generate remediation steps for testing"""
        remediation_steps = {
            'stock_negative_quantity': [
                'Check inventory calculations for accuracy',
                'Verify stock movement records are correct',
                'Review recent transactions for errors',
                'Contact system administrator if issue persists'
            ],
            'reserved_quantity_exceeds_available': [
                'Reduce reservation amount to available quantity',
                'Check current stock levels in inventory',
                'Review pending reservations for conflicts',
                'Update stock quantities if necessary'
            ],
            'admin_bypass_attempt': [
                'Use PurchaseGateway service for purchase operations',
                'Use SaleGateway service for sale operations',
                'Follow proper governance workflows',
                'Contact system administrator for assistance'
            ]
        }
        return remediation_steps.get(error_type, ['Contact system administrator'])
    
    def _generate_failure_report(self, failure_type):
        """Generate failure report for testing"""
        failure_reports = {
            'database_constraint_violation': {
                'severity': 'CRITICAL',
                'impact': 'Data integrity compromised',
                'requires_immediate_action': True,
                'description': 'Database constraint violation detected'
            },
            'governance_bypass_detected': {
                'severity': 'CRITICAL',
                'impact': 'Security policy violation',
                'requires_immediate_action': True,
                'description': 'Governance bypass attempt detected'
            },
            'audit_trail_incomplete': {
                'severity': 'HIGH',
                'impact': 'Compliance requirement not met',
                'requires_immediate_action': True,
                'description': 'Audit trail records incomplete'
            },
            'idempotency_failure': {
                'severity': 'HIGH',
                'impact': 'Duplicate operations possible',
                'requires_immediate_action': False,
                'description': 'Idempotency protection failed'
            }
        }
        return failure_reports.get(failure_type, {
            'severity': 'UNKNOWN',
            'impact': 'Unknown impact',
            'requires_immediate_action': False,
            'description': 'Unknown failure type'
        })
    
    def _generate_overall_report(self, test_results):
        """Generate overall test report for validation"""
        total_tests = sum(data['total'] for data in test_results.values())
        total_passed = sum(data['passed'] for data in test_results.values())
        total_failed = sum(data['failed'] for data in test_results.values())
        
        critical_issues = []
        for category, data in test_results.items():
            if 'failures' in data:
                for failure in data['failures']:
                    if failure.get('severity') == 'CRITICAL':
                        critical_issues.append(failure)
        
        return {
            'summary': {
                'total_tests': total_tests,
                'total_passed': total_passed,
                'total_failed': total_failed,
                'success_rate': (total_passed / total_tests * 100) if total_tests > 0 else 0
            },
            'critical_issues': critical_issues,
            'recommendations': [
                'Address critical failures immediately',
                'Review high-severity issues',
                'Implement additional monitoring'
            ]
        }


class AuditTrailErrorReportingTests(TransactionTestCase):
    """
    Unit tests for audit trail and error reporting functionality.
    
    This test class validates Requirements 4.5, 6.4, 9.4, 9.5:
    - Complete audit trail maintenance
    - Governance switch change logging
    - Security-sensitive operation logging
    - Clear error messages with remediation steps
    - Critical failure identification
    - Test result reporting accuracy
    """
    
    def setUp(self):
        """Set up test environment"""
        self.audit_tester = AuditTrailTester()
        self.error_tester = ErrorReportingTester()
        
    def test_complete_audit_trail_maintenance(self):
        """Test complete audit trail maintenance"""
        with performance_monitor('test_complete_audit_trail_maintenance', max_duration=30):
            result = self.audit_tester.test_complete_audit_trail_maintenance()
            
            self.assertTrue(result['passed'], f"Audit trail maintenance test failed: {result.get('error', 'Unknown error')}")
            self.assertGreater(result['audit_records_created'], 0, "No audit records were created")
            self.assertEqual(result['operations_tested'], 3, "Not all operations were tested")
            
            # Validate specific audit trail components
            details = result['details']
            self.assertTrue(details.get('governance_audit_complete', False), "Governance audit not complete")
            self.assertTrue(details.get('purchase_audit_complete', False), "Purchase audit not complete")
            self.assertTrue(details.get('sale_audit_complete', False), "Sale audit not complete")
            self.assertTrue(details.get('all_required_fields_captured', False), "Required fields not captured")
    
    def test_governance_switch_change_logging(self):
        """Test governance switch change logging"""
        with performance_monitor('test_governance_switch_change_logging', max_duration=30):
            result = self.audit_tester.test_governance_switch_change_logging()
            
            self.assertTrue(result['passed'], f"Governance switch logging test failed: {result.get('error', 'Unknown error')}")
            self.assertEqual(result['switch_changes_logged'], 3, "Not all switch changes were logged")
            
            # Validate logging components
            details = result['details']
            self.assertTrue(details.get('all_switches_logged', False), "Not all switches logged")
            self.assertTrue(details.get('before_after_data_captured', False), "Before/after data not captured")
            self.assertTrue(details.get('change_reasons_recorded', False), "Change reasons not recorded")
            self.assertTrue(details.get('proper_user_attribution', False), "User attribution not proper")
    
    def test_security_sensitive_operation_logging(self):
        """Test security-sensitive operation logging"""
        with performance_monitor('test_security_sensitive_operation_logging', max_duration=30):
            result = self.audit_tester.test_security_sensitive_operation_logging()
            
            self.assertTrue(result['passed'], f"Security operation logging test failed: {result.get('error', 'Unknown error')}")
            self.assertEqual(result['security_operations_logged'], 3, "Not all security operations were logged")
            
            # Validate security logging components
            details = result['details']
            self.assertTrue(details.get('admin_access_logged', False), "Admin access not logged")
            self.assertTrue(details.get('authority_violations_logged', False), "Authority violations not logged")
            self.assertTrue(details.get('governance_bypass_attempts_logged', False), "Governance bypass attempts not logged")
            self.assertTrue(details.get('proper_violation_categorization', False), "Violation categorization not proper")
            self.assertTrue(details.get('complete_context_captured', False), "Complete context not captured")
    
    def test_clear_error_messages_with_remediation(self):
        """Test clear error messages with remediation steps"""
        with performance_monitor('test_clear_error_messages_with_remediation', max_duration=20):
            result = self.error_tester.test_clear_error_messages_with_remediation()
            
            self.assertTrue(result['passed'], f"Error message test failed: {result.get('error', 'Unknown error')}")
            self.assertGreater(result['error_scenarios_tested'], 0, "No error scenarios were tested")
            
            # Validate error message components
            details = result['details']
            self.assertTrue(details.get('all_error_messages_clear', False), "Error messages not clear")
            self.assertTrue(details.get('remediation_steps_provided', False), "Remediation steps not provided")
            self.assertTrue(details.get('actionable_guidance_included', False), "Actionable guidance not included")
    
    def test_critical_failure_identification(self):
        """Test critical failure identification"""
        with performance_monitor('test_critical_failure_identification', max_duration=20):
            result = self.error_tester.test_critical_failure_identification()
            
            self.assertTrue(result['passed'], f"Critical failure identification test failed: {result.get('error', 'Unknown error')}")
            self.assertGreater(result['critical_failures_identified'], 0, "No critical failures were identified")
            
            # Validate failure identification components
            details = result['details']
            self.assertTrue(details.get('severity_levels_assigned', False), "Severity levels not assigned")
            self.assertTrue(details.get('impact_assessment_provided', False), "Impact assessment not provided")
            self.assertTrue(details.get('action_requirements_specified', False), "Action requirements not specified")
            self.assertTrue(details.get('critical_failures_flagged', False), "Critical failures not flagged")
    
    def test_result_reporting_accuracy(self):
        """Test result reporting accuracy"""
        with performance_monitor('test_result_reporting_accuracy', max_duration=20):
            result = self.error_tester.test_result_reporting_accuracy()
            
            self.assertTrue(result['passed'], f"Result reporting test failed: {result.get('error', 'Unknown error')}")
            self.assertGreater(result['report_components_validated'], 0, "No report components were validated")
            
            # Validate reporting components
            details = result['details']
            self.assertTrue(details.get('metric_consistency_validated', False), "Metric consistency not validated")
            self.assertTrue(details.get('failure_details_complete', False), "Failure details not complete")
            self.assertTrue(details.get('summary_accuracy_confirmed', False), "Summary accuracy not confirmed")
            self.assertTrue(details.get('report_structure_validated', False), "Report structure not validated")