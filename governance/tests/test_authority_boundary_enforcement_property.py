"""
Property-Based Tests for Authority Boundary Enforcement
Tests the AuthorityService with comprehensive property-based testing using Hypothesis.

Feature: code-governance-system, Property 10: Authority Boundary Enforcement
Validates: Requirements 12.1, 12.2

Property Definition:
For any High_Risk_Model mutation, all supported write entrypoints MUST route through 
the designated Authoritative_Service; out-of-band mutations MUST be detected, audited, and quarantined
"""

import pytest
import logging
import threading
import time
import random
from decimal import Decimal
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import patch, MagicMock, Mock

from hypothesis import given, strategies as st, settings, assume, note
from hypothesis.extra.django import TestCase as HypothesisTestCase

from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction, IntegrityError

logger = logging.getLogger(__name__)
User = get_user_model()


# ===== Mock Classes for Standalone Testing =====

class MockHighRiskModel:
    """Mock High-Risk Model for standalone testing"""
    
    def __init__(self, model_name, id=None):
        self.model_name = model_name
        self.id = id or random.randint(1000, 9999)
        self.created_at = timezone.now()
        self.updated_at = timezone.now()
        self.created_by_service = None
        self.last_modified_by_service = None
    
    def save(self, service_name=None):
        """Mock save method that tracks which service performed the operation"""
        self.updated_at = timezone.now()
        if service_name:
            self.last_modified_by_service = service_name
        return self
    
    def delete(self, service_name=None):
        """Mock delete method"""
        return True


class MockAuditService:
    """Mock AuditService for standalone testing"""
    
    def __init__(self):
        self.violations = []
        self.operations = []
        self._lock = threading.Lock()
    
    def log_authority_violation(self, service, model, operation, user=None, **context):
        """Mock authority violation logging"""
        with self._lock:
            violation = {
                'service': service,
                'model': model,
                'operation': operation,
                'user': user,
                'timestamp': timezone.now(),
                'context': context
            }
            self.violations.append(violation)
            logger.warning(f"Authority violation logged: {service} attempted {operation} on {model}")
    
    def log_operation(self, model_name, object_id, operation, source_service, user=None, **kwargs):
        """Mock operation logging"""
        with self._lock:
            op = {
                'model_name': model_name,
                'object_id': object_id,
                'operation': operation,
                'source_service': source_service,
                'user': user,
                'timestamp': timezone.now(),
                **kwargs
            }
            self.operations.append(op)
    
    def get_authority_violations(self, hours=24):
        """Mock get authority violations"""
        cutoff = timezone.now() - timedelta(hours=hours)
        return [v for v in self.violations if v['timestamp'] > cutoff]


class MockAuthorityService:
    """Mock AuthorityService for standalone property testing"""
    
    # Authority matrix for testing
    AUTHORITY_MATRIX = {
        'JournalEntry': 'AccountingGateway',
        'JournalEntryLine': 'AccountingGateway',
        'Stock': 'MovementService',
        'StockMovement': 'MovementService',
        'StudentFee': 'FinanceService',
        'FeePayment': 'FinanceService',
        'TransportationFee': 'TransportationService',
        'AcademicYear': 'AcademicService',
        'StudentEnrollment': 'StudentService',
        'Student': 'StudentService',
        'User': 'UserService',
        'Group': 'UserService',
    }
    
    CRITICAL_MODELS = [
        'JournalEntry',
        'JournalEntryLine', 
        'Stock',
        'StockMovement'
    ]
    
    def __init__(self):
        self.delegations = {}  # (from_service, to_service, model_name) -> delegation
        self.audit_service = MockAuditService()
        self._lock = threading.Lock()
    
    def validate_authority(self, service_name, model_name, operation, user=None, **context):
        """Mock authority validation"""
        with self._lock:
            # Check if model is governed
            if model_name not in self.AUTHORITY_MATRIX:
                return True  # Allow access to non-governed models
            
            # Get authoritative service
            authoritative_service = self.AUTHORITY_MATRIX[model_name]
            
            # Check direct authority
            if service_name == authoritative_service:
                return True
            
            # Check for active delegation
            if self.check_delegation(authoritative_service, service_name, model_name):
                return True
            
            # Authority violation
            self.audit_service.log_authority_violation(
                service=service_name,
                model=model_name,
                operation=operation,
                user=user,
                **context
            )
            
            from governance.exceptions import AuthorityViolationError
            raise AuthorityViolationError(
                service=service_name,
                model=model_name,
                operation=operation,
                context=context
            )
    
    def get_authoritative_service(self, model_name):
        """Get the authoritative service for a model"""
        return self.AUTHORITY_MATRIX.get(model_name)
    
    def delegate_authority(self, from_service, to_service, model_name, duration, reason, user):
        """Mock authority delegation"""
        with self._lock:
            # Validate delegation
            if model_name not in self.AUTHORITY_MATRIX:
                raise ValueError(f"Model '{model_name}' is not governed")
            
            if from_service != self.AUTHORITY_MATRIX[model_name]:
                raise ValueError(f"Service '{from_service}' is not authoritative for '{model_name}'")
            
            if model_name in self.CRITICAL_MODELS:
                raise ValueError(f"Cannot delegate critical model '{model_name}' authority during runtime")
            
            # Create delegation
            key = (from_service, to_service, model_name)
            delegation = {
                'from_service': from_service,
                'to_service': to_service,
                'model_name': model_name,
                'granted_at': timezone.now(),
                'expires_at': timezone.now() + duration,
                'granted_by': user,
                'reason': reason,
                'is_active': True
            }
            self.delegations[key] = delegation
            return delegation
    
    def check_delegation(self, from_service, to_service, model_name):
        """Check if there's a valid delegation"""
        key = (from_service, to_service, model_name)
        if key not in self.delegations:
            return False
        
        delegation = self.delegations[key]
        return (delegation['is_active'] and 
                delegation['expires_at'] > timezone.now())
    
    def get_authority_statistics(self):
        """Mock authority statistics"""
        return {
            'governed_models': len(self.AUTHORITY_MATRIX),
            'critical_models': len(self.CRITICAL_MODELS),
            'active_delegations': len([d for d in self.delegations.values() 
                                     if d['is_active'] and d['expires_at'] > timezone.now()]),
            'recent_violations': len(self.audit_service.get_authority_violations())
        }


# ===== Hypothesis Strategies =====

# High-risk model names from the authority matrix
high_risk_models = st.sampled_from([
    'JournalEntry', 'JournalEntryLine', 'Stock', 'StockMovement',
    'StudentFee', 'FeePayment', 'TransportationFee', 'AcademicYear',
    'StudentEnrollment', 'Student', 'User', 'Group'
])

# Service names (both authorized and unauthorized)
authorized_services = st.sampled_from([
    'AccountingGateway', 'MovementService', 'FinanceService',
    'TransportationService', 'AcademicService', 'StudentService', 'UserService'
])

unauthorized_services = st.sampled_from([
    'UnauthorizedService', 'HackerService', 'MaliciousService',
    'BypassService', 'DirectDBService', 'AdminPanelService'
])

all_services = st.one_of(authorized_services, unauthorized_services)

# Operations
operations = st.sampled_from(['CREATE', 'UPDATE', 'DELETE', 'BULK_UPDATE', 'BULK_DELETE'])

# Cross-domain authority scenarios
cross_domain_scenarios = st.sampled_from([
    'finance_to_inventory',  # FinanceService trying to modify Stock
    'inventory_to_finance',  # MovementService trying to modify StudentFee
    'admin_to_critical',     # AdminService trying to modify JournalEntry
    'service_to_user',       # Any service trying to modify User/Group
    'direct_db_access',      # Direct database access bypassing services
])

# Authority delegation scenarios
delegation_durations = st.integers(min_value=1, max_value=24).map(lambda h: timedelta(hours=h))
delegation_reasons = st.sampled_from([
    'Emergency maintenance',
    'Data migration',
    'System upgrade',
    'Bug fix deployment',
    'Performance optimization'
])


# ===== Property-Based Tests =====

class AuthorityBoundaryEnforcementProperties(HypothesisTestCase):
    """
    Property-based tests for Authority Boundary Enforcement
    
    **Validates: Requirements 12.1, 12.2**
    
    Property 10: Authority Boundary Enforcement
    For any High_Risk_Model mutation, all supported write entrypoints MUST route through 
    the designated Authoritative_Service; out-of-band mutations MUST be detected, audited, and quarantined
    """
    
    def setUp(self):
        """Set up test environment"""
        self.authority_service = MockAuthorityService()
        self.user = Mock()
        self.user.username = 'test_user'
        self.user.is_superuser = True
    
    @settings(max_examples=50, deadline=None)
    @given(
        model_name=high_risk_models,
        operation=operations,
        service_name=all_services
    )
    def test_property_authority_boundary_enforcement_basic(self, model_name, operation, service_name):
        """
        **Property 10: Authority Boundary Enforcement (Basic)**
        
        For any High_Risk_Model mutation, only the designated Authoritative_Service 
        should be allowed to perform the operation.
        """
        note(f"Testing authority for {service_name} performing {operation} on {model_name}")
        
        # Get the authoritative service for this model
        authoritative_service = self.authority_service.get_authoritative_service(model_name)
        assume(authoritative_service is not None)  # Only test governed models
        
        if service_name == authoritative_service:
            # Authorized service should succeed
            try:
                result = self.authority_service.validate_authority(
                    service_name=service_name,
                    model_name=model_name,
                    operation=operation,
                    user=self.user
                )
                assert result is True, f"Authorized service {service_name} should be allowed"
                
                # No violations should be logged for authorized access
                violations = self.authority_service.audit_service.get_authority_violations()
                violation_count_for_this_model = len([
                    v for v in violations 
                    if v['model'] == model_name and v['service'] == service_name
                ])
                assert violation_count_for_this_model == 0, "No violations should be logged for authorized access"
                
            except Exception as e:
                pytest.fail(f"Authorized service {service_name} was rejected: {e}")
        else:
            # Unauthorized service should be rejected
            from governance.exceptions import AuthorityViolationError
            with pytest.raises(AuthorityViolationError):
                self.authority_service.validate_authority(
                    service_name=service_name,
                    model_name=model_name,
                    operation=operation,
                    user=self.user
                )
            
            # Violation should be logged
            violations = self.authority_service.audit_service.get_authority_violations()
            violation_found = any(
                v['model'] == model_name and 
                v['service'] == service_name and 
                v['operation'] == operation
                for v in violations
            )
            assert violation_found, f"Authority violation should be logged for {service_name} on {model_name}"
    
    @settings(max_examples=30, deadline=None)
    @given(
        scenario=cross_domain_scenarios,
        operation=operations
    )
    def test_property_cross_domain_authority_enforcement(self, scenario, operation):
        """
        **Property 10: Authority Boundary Enforcement (Cross-Domain)**
        
        Cross-domain authority violations should be consistently detected and blocked.
        """
        note(f"Testing cross-domain scenario: {scenario} with operation {operation}")
        
        # Define cross-domain violation scenarios
        scenarios = {
            'finance_to_inventory': ('FinanceService', 'Stock'),
            'inventory_to_finance': ('MovementService', 'StudentFee'),
            'admin_to_critical': ('AdminService', 'JournalEntry'),
            'service_to_user': ('FinanceService', 'User'),
            'direct_db_access': ('DirectDBService', 'JournalEntry'),
        }
        
        service_name, model_name = scenarios[scenario]
        
        # This should always be a violation (cross-domain access)
        from governance.exceptions import AuthorityViolationError
        with pytest.raises(AuthorityViolationError):
            self.authority_service.validate_authority(
                service_name=service_name,
                model_name=model_name,
                operation=operation,
                user=self.user
            )
        
        # Verify violation was logged with proper context
        violations = self.authority_service.audit_service.get_authority_violations()
        violation_found = any(
            v['model'] == model_name and 
            v['service'] == service_name and 
            v['operation'] == operation
            for v in violations
        )
        assert violation_found, f"Cross-domain violation should be logged: {scenario}"
    
    @settings(max_examples=20, deadline=None)
    @given(
        model_name=high_risk_models.filter(lambda m: m not in MockAuthorityService.CRITICAL_MODELS),
        duration=delegation_durations,
        reason=delegation_reasons
    )
    def test_property_authority_delegation_enforcement(self, model_name, duration, reason):
        """
        **Property 10: Authority Boundary Enforcement (Delegation)**
        
        Authority delegation should work correctly with proper controls and time bounds.
        """
        note(f"Testing delegation for {model_name} with duration {duration}")
        
        # Get authoritative service
        authoritative_service = self.authority_service.get_authoritative_service(model_name)
        assume(authoritative_service is not None)
        
        # Choose a different service to delegate to
        target_service = 'TestDelegatedService'
        
        # Create delegation
        delegation = self.authority_service.delegate_authority(
            from_service=authoritative_service,
            to_service=target_service,
            model_name=model_name,
            duration=duration,
            reason=reason,
            user=self.user
        )
        
        assert delegation is not None, "Delegation should be created"
        assert delegation['from_service'] == authoritative_service
        assert delegation['to_service'] == target_service
        assert delegation['model_name'] == model_name
        
        # Test that delegated service now has authority
        try:
            result = self.authority_service.validate_authority(
                service_name=target_service,
                model_name=model_name,
                operation='UPDATE',
                user=self.user
            )
            assert result is True, "Delegated service should have authority"
        except Exception as e:
            pytest.fail(f"Delegated service was rejected: {e}")
        
        # Test that delegation expires correctly
        # Mock time passage
        original_now = timezone.now
        future_time = timezone.now() + duration + timedelta(minutes=1)
        
        with patch('django.utils.timezone.now', return_value=future_time):
            # Delegation should now be expired
            from governance.exceptions import AuthorityViolationError
            with pytest.raises(AuthorityViolationError):
                self.authority_service.validate_authority(
                    service_name=target_service,
                    model_name=model_name,
                    operation='UPDATE',
                    user=self.user
                )
    
    @settings(max_examples=20, deadline=None)
    @given(
        model_name=st.sampled_from(MockAuthorityService.CRITICAL_MODELS),
        duration=delegation_durations
    )
    def test_property_critical_model_delegation_restriction(self, model_name, duration):
        """
        **Property 10: Authority Boundary Enforcement (Critical Model Protection)**
        
        Critical models should not allow authority delegation during runtime.
        """
        note(f"Testing critical model delegation restriction for {model_name}")
        
        authoritative_service = self.authority_service.get_authoritative_service(model_name)
        target_service = 'TestService'
        
        # Attempt to delegate critical model authority should fail
        with pytest.raises(ValueError, match="Cannot delegate critical model"):
            self.authority_service.delegate_authority(
                from_service=authoritative_service,
                to_service=target_service,
                model_name=model_name,
                duration=duration,
                reason='Test delegation',
                user=self.user
            )
    
    @settings(max_examples=15, deadline=None)
    @given(
        thread_count=st.integers(min_value=2, max_value=8),
        model_name=high_risk_models,
        operations_per_thread=st.integers(min_value=5, max_value=15)
    )
    def test_property_concurrent_authority_validation(self, thread_count, model_name, operations_per_thread):
        """
        **Property 10: Authority Boundary Enforcement (Concurrency)**
        
        Authority validation should be thread-safe and consistent under concurrent access.
        """
        note(f"Testing concurrent authority validation: {thread_count} threads, {operations_per_thread} ops each")
        
        authoritative_service = self.authority_service.get_authoritative_service(model_name)
        assume(authoritative_service is not None)
        
        results = []
        violations_before = len(self.authority_service.audit_service.violations)
        
        def worker_thread(thread_id):
            """Worker thread that performs authority validations"""
            thread_results = []
            
            for i in range(operations_per_thread):
                # Mix of authorized and unauthorized attempts
                if i % 2 == 0:
                    service = authoritative_service  # Should succeed
                    expected_success = True
                else:
                    service = f'UnauthorizedService{thread_id}'  # Should fail
                    expected_success = False
                
                try:
                    result = self.authority_service.validate_authority(
                        service_name=service,
                        model_name=model_name,
                        operation='UPDATE',
                        user=self.user
                    )
                    thread_results.append((thread_id, i, service, True, expected_success))
                except Exception:
                    thread_results.append((thread_id, i, service, False, expected_success))
            
            return thread_results
        
        # Run concurrent threads
        with ThreadPoolExecutor(max_workers=thread_count) as executor:
            futures = [executor.submit(worker_thread, i) for i in range(thread_count)]
            
            for future in as_completed(futures):
                results.extend(future.result())
        
        # Verify results
        authorized_attempts = [r for r in results if r[2] == authoritative_service]
        unauthorized_attempts = [r for r in results if r[2] != authoritative_service]
        
        # All authorized attempts should succeed
        authorized_successes = [r for r in authorized_attempts if r[3] is True]
        assert len(authorized_successes) == len(authorized_attempts), \
            f"All authorized attempts should succeed: {len(authorized_successes)}/{len(authorized_attempts)}"
        
        # All unauthorized attempts should fail
        unauthorized_failures = [r for r in unauthorized_attempts if r[3] is False]
        assert len(unauthorized_failures) == len(unauthorized_attempts), \
            f"All unauthorized attempts should fail: {len(unauthorized_failures)}/{len(unauthorized_attempts)}"
        
        # Verify violations were logged for unauthorized attempts
        violations_after = len(self.authority_service.audit_service.violations)
        expected_violations = violations_before + len(unauthorized_attempts)
        assert violations_after == expected_violations, \
            f"Expected {expected_violations} violations, got {violations_after}"
    
    @settings(max_examples=10, deadline=None)
    @given(
        model_names=st.lists(high_risk_models, min_size=3, max_size=8, unique=True),
        batch_size=st.integers(min_value=5, max_value=20)
    )
    def test_property_batch_authority_validation(self, model_names, batch_size):
        """
        **Property 10: Authority Boundary Enforcement (Batch Operations)**
        
        Batch operations should maintain authority boundaries consistently.
        """
        note(f"Testing batch authority validation: {len(model_names)} models, batch size {batch_size}")
        
        # Create batch operations mixing authorized and unauthorized
        batch_operations = []
        expected_results = []
        
        for i in range(batch_size):
            model_name = random.choice(model_names)
            authoritative_service = self.authority_service.get_authoritative_service(model_name)
            
            if authoritative_service is None:
                continue  # Skip non-governed models
            
            # Alternate between authorized and unauthorized
            if i % 2 == 0:
                service = authoritative_service
                expected_success = True
            else:
                service = f'UnauthorizedBatchService{i}'
                expected_success = False
            
            batch_operations.append((service, model_name, 'BATCH_UPDATE'))
            expected_results.append(expected_success)
        
        # Execute batch operations
        actual_results = []
        for service, model_name, operation in batch_operations:
            try:
                self.authority_service.validate_authority(
                    service_name=service,
                    model_name=model_name,
                    operation=operation,
                    user=self.user
                )
                actual_results.append(True)
            except Exception:
                actual_results.append(False)
        
        # Verify results match expectations
        assert len(actual_results) == len(expected_results), "Result count mismatch"
        
        for i, (actual, expected) in enumerate(zip(actual_results, expected_results)):
            assert actual == expected, \
                f"Batch operation {i} result mismatch: expected {expected}, got {actual}"
    
    def test_authority_matrix_completeness(self):
        """
        **Property 10: Authority Boundary Enforcement (Matrix Completeness)**
        
        All high-risk models should have designated authoritative services.
        """
        # Verify authority matrix is complete
        assert len(self.authority_service.AUTHORITY_MATRIX) > 0, "Authority matrix should not be empty"
        
        # Verify all critical models are in the matrix
        for critical_model in self.authority_service.CRITICAL_MODELS:
            assert critical_model in self.authority_service.AUTHORITY_MATRIX, \
                f"Critical model {critical_model} should be in authority matrix"
        
        # Verify all services are non-empty strings
        for model_name, service_name in self.authority_service.AUTHORITY_MATRIX.items():
            assert isinstance(model_name, str) and model_name.strip(), \
                f"Model name should be non-empty string: {model_name}"
            assert isinstance(service_name, str) and service_name.strip(), \
                f"Service name should be non-empty string: {service_name}"
    
    def test_authority_statistics_accuracy(self):
        """
        **Property 10: Authority Boundary Enforcement (Statistics)**
        
        Authority statistics should accurately reflect system state.
        """
        stats = self.authority_service.get_authority_statistics()
        
        # Verify basic statistics
        assert stats['governed_models'] == len(self.authority_service.AUTHORITY_MATRIX)
        assert stats['critical_models'] == len(self.authority_service.CRITICAL_MODELS)
        assert stats['active_delegations'] >= 0
        assert stats['recent_violations'] >= 0
        
        # Create a delegation and verify statistics update
        if len([m for m in self.authority_service.AUTHORITY_MATRIX.keys() 
                if m not in self.authority_service.CRITICAL_MODELS]) > 0:
            
            non_critical_model = next(
                m for m in self.authority_service.AUTHORITY_MATRIX.keys() 
                if m not in self.authority_service.CRITICAL_MODELS
            )
            
            authoritative_service = self.authority_service.get_authoritative_service(non_critical_model)
            
            self.authority_service.delegate_authority(
                from_service=authoritative_service,
                to_service='TestStatsService',
                model_name=non_critical_model,
                duration=timedelta(hours=1),
                reason='Statistics test',
                user=self.user
            )
            
            updated_stats = self.authority_service.get_authority_statistics()
            assert updated_stats['active_delegations'] == stats['active_delegations'] + 1


# ===== Integration Tests with Real Django Models =====

@pytest.mark.django_db
class AuthorityBoundaryEnforcementIntegrationTests(TransactionTestCase):
    """
    Integration tests for Authority Boundary Enforcement with real Django models
    """
    
    def setUp(self):
        """Set up test environment with real Django models"""
        from governance.services import AuthorityService
        from governance.models import GovernanceContext
        
        self.authority_service = AuthorityService
        self.user = User.objects.create_user(
            username='test_authority_user',
            email='test@example.com',
            password='testpass123'
        )
        self.user.is_superuser = True
        self.user.save()
        
        # Set governance context
        GovernanceContext.set_current_user(self.user)
        GovernanceContext.set_current_service('TestService')
    
    def tearDown(self):
        """Clean up after tests"""
        from governance.models import GovernanceContext
        GovernanceContext.clear_context()
    
    @settings(max_examples=10, deadline=None)
    @given(
        model_name=st.sampled_from(['JournalEntry', 'Stock', 'StudentFee']),
        operation=operations
    )
    def test_real_authority_validation(self, model_name, operation):
        """Test authority validation with real AuthorityService"""
        note(f"Testing real authority validation: {model_name} {operation}")
        
        authoritative_service = self.authority_service.get_authoritative_service(model_name)
        assume(authoritative_service is not None)
        
        # Test authorized access
        try:
            result = self.authority_service.validate_authority(
                service_name=authoritative_service,
                model_name=model_name,
                operation=operation,
                user=self.user
            )
            assert result is True, f"Authorized service should succeed"
        except Exception as e:
            pytest.fail(f"Authorized service failed: {e}")
        
        # Test unauthorized access
        from governance.exceptions import AuthorityViolationError
        with pytest.raises(AuthorityViolationError):
            self.authority_service.validate_authority(
                service_name='UnauthorizedTestService',
                model_name=model_name,
                operation=operation,
                user=self.user
            )
    
    def test_startup_authority_matrix_validation(self):
        """Test authority matrix validation during system startup"""
        errors = self.authority_service.validate_startup_authority_matrix()
        
        # Should have no validation errors
        assert len(errors) == 0, f"Authority matrix validation errors: {errors}"
        
        # Verify matrix completeness
        assert len(self.authority_service.AUTHORITY_MATRIX) > 0
        assert len(self.authority_service.CRITICAL_MODELS) > 0
        
        # Verify all critical models are governed
        for critical_model in self.authority_service.CRITICAL_MODELS:
            assert critical_model in self.authority_service.AUTHORITY_MATRIX


# ===== Test Runner =====

def run_authority_boundary_enforcement_property_tests():
    """Run all authority boundary enforcement property tests"""
    import subprocess
    import sys
    
    print("=" * 80)
    print("🔒 Running Authority Boundary Enforcement Property Tests")
    print("Feature: code-governance-system, Property 10: Authority Boundary Enforcement")
    print("Validates: Requirements 12.1, 12.2")
    print("=" * 80)
    
    # Run standalone property tests
    print("\n📋 Running Standalone Property Tests...")
    try:
        result = subprocess.run([
            sys.executable, '-m', 'pytest', 
            'governance/tests/test_authority_boundary_enforcement_property.py::AuthorityBoundaryEnforcementProperties',
            '-v', '--tb=short'
        ], capture_output=True, text=True, cwd='.')
        
        print("STDOUT:", result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        standalone_success = result.returncode == 0
        print(f"✅ Standalone tests: {'PASSED' if standalone_success else 'FAILED'}")
        
    except Exception as e:
        print(f"❌ Error running standalone tests: {e}")
        standalone_success = False
    
    # Run integration tests
    print("\n🔗 Running Integration Tests...")
    try:
        result = subprocess.run([
            sys.executable, '-m', 'pytest', 
            'governance/tests/test_authority_boundary_enforcement_property.py::AuthorityBoundaryEnforcementIntegrationTests',
            '-v', '--tb=short'
        ], capture_output=True, text=True, cwd='.')
        
        print("STDOUT:", result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        integration_success = result.returncode == 0
        print(f"✅ Integration tests: {'PASSED' if integration_success else 'FAILED'}")
        
    except Exception as e:
        print(f"❌ Error running integration tests: {e}")
        integration_success = False
    
    overall_success = standalone_success and integration_success
    
    print("\n" + "=" * 80)
    if overall_success:
        print("🎉 All Authority Boundary Enforcement Property Tests PASSED!")
        print("✅ Property 10: Authority Boundary Enforcement - VALIDATED")
    else:
        print("❌ Some Authority Boundary Enforcement Property Tests FAILED!")
        print("🔍 Check the test output above for details")
    print("=" * 80)
    
    return overall_success


if __name__ == '__main__':
    success = run_authority_boundary_enforcement_property_tests()
    sys.exit(0 if success else 1)