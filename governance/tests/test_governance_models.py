"""
Comprehensive unit tests for governance models with thread-safety considerations.

Tests model validation, constraints, and concurrent access scenarios.
Validates Requirements 13.1 - comprehensive verification tools.

Feature: code-governance-system
"""

import pytest
import threading
import time
from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch, Mock
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError, connection
from django.utils import timezone
from django.db.utils import DatabaseError

from governance.models import (
    IdempotencyRecord,
    AuditTrail,
    QuarantineRecord,
    AuthorityDelegation,
    GovernanceContext
)

User = get_user_model()


class IdempotencyRecordModelTests(TestCase):
    """Unit tests for IdempotencyRecord model validation and constraints"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
    
    def test_model_creation_with_valid_data(self):
        """Test creating IdempotencyRecord with valid data"""
        expires_at = timezone.now() + timedelta(hours=24)
        
        record = IdempotencyRecord.objects.create(
            operation_type='journal_entry',
            idempotency_key='test_key_123',
            result_data={'entry_id': 456, 'amount': '1000.00'},
            expires_at=expires_at,
            created_by=self.user
        )
        
        self.assertEqual(record.operation_type, 'journal_entry')
        self.assertEqual(record.idempotency_key, 'test_key_123')
        self.assertEqual(record.result_data['entry_id'], 456)
        self.assertEqual(record.created_by, self.user)
        self.assertFalse(record.is_expired())
    
    def test_unique_constraint_on_operation_type_and_key(self):
        """Test unique constraint on (operation_type, idempotency_key)"""
        expires_at = timezone.now() + timedelta(hours=24)
        
        # Create first record
        IdempotencyRecord.objects.create(
            operation_type='test_operation',
            idempotency_key='duplicate_key',
            result_data={'test': 'data1'},
            expires_at=expires_at,
            created_by=self.user
        )
        
        # Attempt to create duplicate should fail
        with self.assertRaises(IntegrityError):
            IdempotencyRecord.objects.create(
                operation_type='test_operation',
                idempotency_key='duplicate_key',
                result_data={'test': 'data2'},
                expires_at=expires_at,
                created_by=self.user
            )
    
    def test_different_operation_types_allow_same_key(self):
        """Test that different operation types can use the same idempotency key"""
        expires_at = timezone.now() + timedelta(hours=24)
        
        # Create record with first operation type
        record1 = IdempotencyRecord.objects.create(
            operation_type='journal_entry',
            idempotency_key='shared_key',
            result_data={'entry_id': 123},
            expires_at=expires_at,
            created_by=self.user
        )
        
        # Create record with different operation type - should succeed
        record2 = IdempotencyRecord.objects.create(
            operation_type='stock_movement',
            idempotency_key='shared_key',
            result_data={'movement_id': 456},
            expires_at=expires_at,
            created_by=self.user
        )
        
        self.assertNotEqual(record1.id, record2.id)
        self.assertEqual(record1.idempotency_key, record2.idempotency_key)
    
    def test_clean_method_validation(self):
        """Test model clean method validation"""
        # Test with expiration time in the past
        past_time = timezone.now() - timedelta(hours=1)
        
        record = IdempotencyRecord(
            operation_type='test_operation',
            idempotency_key='test_key',
            result_data={'test': 'data'},
            expires_at=past_time,
            created_by=self.user
        )
        
        with self.assertRaises(ValidationError) as cm:
            record.clean()
        
        self.assertIn('Expiration time must be in the future', str(cm.exception))
    
    def test_is_expired_method(self):
        """Test is_expired method functionality"""
        # Create expired record
        past_time = timezone.now() - timedelta(hours=1)
        expired_record = IdempotencyRecord.objects.create(
            operation_type='test_expired',
            idempotency_key='expired_key',
            result_data={'test': 'data'},
            expires_at=past_time,
            created_by=self.user
        )
        
        # Create active record
        future_time = timezone.now() + timedelta(hours=1)
        active_record = IdempotencyRecord.objects.create(
            operation_type='test_active',
            idempotency_key='active_key',
            result_data={'test': 'data'},
            expires_at=future_time,
            created_by=self.user
        )
        
        self.assertTrue(expired_record.is_expired())
        self.assertFalse(active_record.is_expired())
    
    def test_string_representation(self):
        """Test __str__ method"""
        record = IdempotencyRecord.objects.create(
            operation_type='test_operation',
            idempotency_key='test_key',
            result_data={'test': 'data'},
            expires_at=timezone.now() + timedelta(hours=24),
            created_by=self.user
        )
        
        expected_str = 'test_operation:test_key'
        self.assertEqual(str(record), expected_str)


class IdempotencyRecordConcurrencyTests(TransactionTestCase):
    """Thread-safety tests for IdempotencyRecord model"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='concurrency_user',
            email='concurrency@example.com',
            password='testpass123'
        )
    
    def test_check_and_record_thread_safety(self):
        """Test thread-safe check_and_record method under concurrent access"""
        operation_type = 'concurrent_test'
        idempotency_key = 'concurrent_key'
        result_data = {'test': 'concurrent_data'}
        
        results = []
        errors = []
        
        def concurrent_operation(thread_id):
            """Simulate concurrent operation attempting to use same idempotency key"""
            try:
                is_duplicate, record = IdempotencyRecord.check_and_record(
                    operation_type=operation_type,
                    idempotency_key=idempotency_key,
                    result_data={**result_data, 'thread_id': thread_id},
                    user=self.user,
                    expires_in_hours=1
                )
                
                results.append({
                    'thread_id': thread_id,
                    'is_duplicate': is_duplicate,
                    'record_id': record.id if record else None
                })
                
            except Exception as e:
                errors.append(f"Thread {thread_id}: {str(e)}")
        
        # Start multiple threads simultaneously
        threads = []
        num_threads = 5
        
        for i in range(num_threads):
            thread = threading.Thread(target=concurrent_operation, args=(i,))
            threads.append(thread)
        
        # Start all threads at once
        for thread in threads:
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # Analyze results
        self.assertEqual(len(errors), 0, f"Errors occurred: {errors}")
        self.assertEqual(len(results), num_threads)
        
        # Exactly one thread should succeed (is_duplicate=False)
        successful_operations = [r for r in results if not r['is_duplicate']]
        duplicate_operations = [r for r in results if r['is_duplicate']]
        
        self.assertEqual(len(successful_operations), 1, 
                        f"Expected exactly 1 successful operation, got {len(successful_operations)}")
        self.assertEqual(len(duplicate_operations), num_threads - 1,
                        f"Expected {num_threads - 1} duplicate operations, got {len(duplicate_operations)}")
        
        # All operations should reference the same record
        record_ids = [r['record_id'] for r in results if r['record_id']]
        self.assertTrue(all(rid == record_ids[0] for rid in record_ids),
                       "All operations should reference the same record")
        
        # Verify only one record exists in database
        records = IdempotencyRecord.objects.filter(
            operation_type=operation_type,
            idempotency_key=idempotency_key
        )
        self.assertEqual(records.count(), 1)
    
    def test_expired_record_replacement_thread_safety(self):
        """Test thread-safe replacement of expired records"""
        operation_type = 'expired_replacement_test'
        idempotency_key = 'expired_key'
        
        # Create expired record
        expired_record = IdempotencyRecord.objects.create(
            operation_type=operation_type,
            idempotency_key=idempotency_key,
            result_data={'original': 'data'},
            expires_at=timezone.now() - timedelta(hours=1),
            created_by=self.user
        )
        
        results = []
        errors = []
        
        def replace_expired_record(thread_id):
            """Attempt to replace expired record"""
            try:
                is_duplicate, record = IdempotencyRecord.check_and_record(
                    operation_type=operation_type,
                    idempotency_key=idempotency_key,
                    result_data={'thread_id': thread_id, 'new': 'data'},
                    user=self.user,
                    expires_in_hours=1
                )
                
                results.append({
                    'thread_id': thread_id,
                    'is_duplicate': is_duplicate,
                    'record_id': record.id,
                    'is_new_record': record.id != expired_record.id
                })
                
            except Exception as e:
                errors.append(f"Thread {thread_id}: {str(e)}")
        
        # Start multiple threads
        threads = []
        num_threads = 3
        
        for i in range(num_threads):
            thread = threading.Thread(target=replace_expired_record, args=(i,))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # Analyze results
        self.assertEqual(len(errors), 0, f"Errors occurred: {errors}")
        self.assertEqual(len(results), num_threads)
        
        # One thread should create new record, others should get duplicate
        new_record_operations = [r for r in results if not r['is_duplicate']]
        duplicate_operations = [r for r in results if r['is_duplicate']]
        
        self.assertEqual(len(new_record_operations), 1)
        self.assertEqual(len(duplicate_operations), num_threads - 1)
        
        # Expired record should be deleted
        self.assertFalse(
            IdempotencyRecord.objects.filter(id=expired_record.id).exists()
        )
        
        # New record should exist
        new_records = IdempotencyRecord.objects.filter(
            operation_type=operation_type,
            idempotency_key=idempotency_key
        )
        self.assertEqual(new_records.count(), 1)
        self.assertFalse(new_records.first().is_expired())
    
    def test_high_concurrency_stress_test(self):
        """Stress test with high concurrency to validate unique constraints"""
        operation_type = 'stress_test'
        num_operations = 20
        num_unique_keys = 5
        
        results = []
        errors = []
        
        def stress_operation(operation_id):
            """Perform operation with one of several keys"""
            key_index = operation_id % num_unique_keys
            idempotency_key = f'stress_key_{key_index}'
            
            try:
                is_duplicate, record = IdempotencyRecord.check_and_record(
                    operation_type=operation_type,
                    idempotency_key=idempotency_key,
                    result_data={'operation_id': operation_id},
                    user=self.user,
                    expires_in_hours=1
                )
                
                results.append({
                    'operation_id': operation_id,
                    'key_index': key_index,
                    'is_duplicate': is_duplicate,
                    'record_id': record.id
                })
                
            except Exception as e:
                errors.append(f"Operation {operation_id}: {str(e)}")
        
        # Use ThreadPoolExecutor for better control
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(stress_operation, i) 
                for i in range(num_operations)
            ]
            
            for future in as_completed(futures):
                future.result()  # Wait for completion
        
        # Analyze results
        self.assertEqual(len(errors), 0, f"Errors occurred: {errors}")
        self.assertEqual(len(results), num_operations)
        
        # Group results by key
        results_by_key = {}
        for result in results:
            key_index = result['key_index']
            if key_index not in results_by_key:
                results_by_key[key_index] = []
            results_by_key[key_index].append(result)
        
        # For each key, exactly one operation should succeed
        for key_index, key_results in results_by_key.items():
            successful = [r for r in key_results if not r['is_duplicate']]
            duplicates = [r for r in key_results if r['is_duplicate']]
            
            self.assertEqual(len(successful), 1, 
                           f"Key {key_index}: Expected 1 successful operation, got {len(successful)}")
            self.assertEqual(len(duplicates), len(key_results) - 1,
                           f"Key {key_index}: Expected {len(key_results) - 1} duplicates, got {len(duplicates)}")
        
        # Verify database state
        final_records = IdempotencyRecord.objects.filter(
            operation_type=operation_type
        )
        self.assertEqual(final_records.count(), num_unique_keys)


class AuditTrailModelTests(TestCase):
    """Unit tests for AuditTrail model validation and functionality"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='audit_user',
            email='audit@example.com',
            password='testpass123'
        )
    
    def test_model_creation_with_required_fields(self):
        """Test creating AuditTrail with required fields"""
        audit_record = AuditTrail.objects.create(
            model_name='TestModel',
            object_id=123,
            operation='CREATE',
            user=self.user,
            source_service='TestService'
        )
        
        self.assertEqual(audit_record.model_name, 'TestModel')
        self.assertEqual(audit_record.object_id, 123)
        self.assertEqual(audit_record.operation, 'CREATE')
        self.assertEqual(audit_record.user, self.user)
        self.assertEqual(audit_record.source_service, 'TestService')
        self.assertIsNotNone(audit_record.timestamp)
    
    def test_model_creation_with_optional_fields(self):
        """Test creating AuditTrail with optional fields"""
        before_data = {'status': 'draft', 'amount': '100.00'}
        after_data = {'status': 'published', 'amount': '150.00'}
        additional_context = {'reason': 'user_request', 'batch_id': 'B123'}
        
        audit_record = AuditTrail.objects.create(
            model_name='TestModel',
            object_id=456,
            operation='UPDATE',
            user=self.user,
            source_service='TestService',
            before_data=before_data,
            after_data=after_data,
            ip_address='192.168.1.100',
            user_agent='Mozilla/5.0 Test Browser',
            additional_context=additional_context
        )
        
        self.assertEqual(audit_record.before_data, before_data)
        self.assertEqual(audit_record.after_data, after_data)
        self.assertEqual(audit_record.ip_address, '192.168.1.100')
        self.assertEqual(audit_record.user_agent, 'Mozilla/5.0 Test Browser')
        self.assertEqual(audit_record.additional_context, additional_context)
    
    def test_operation_choices_validation(self):
        """Test that operation field validates against allowed choices"""
        valid_operations = ['CREATE', 'UPDATE', 'DELETE', 'VIEW', 'ADMIN_ACCESS', 'AUTHORITY_VIOLATION']
        
        for operation in valid_operations:
            audit_record = AuditTrail.objects.create(
                model_name='TestModel',
                object_id=123,
                operation=operation,
                user=self.user,
                source_service='TestService'
            )
            self.assertEqual(audit_record.operation, operation)
    
    def test_log_operation_class_method(self):
        """Test log_operation class method functionality"""
        before_data = {'field1': 'old_value'}
        after_data = {'field1': 'new_value'}
        
        # Mock request object
        mock_request = Mock()
        mock_request.META = {
            'HTTP_X_FORWARDED_FOR': '10.0.0.1, 192.168.1.1',
            'HTTP_USER_AGENT': 'Test User Agent'
        }
        
        audit_record = AuditTrail.log_operation(
            model_name='TestModel',
            object_id=789,
            operation='UPDATE',
            user=self.user,
            source_service='TestService',
            before_data=before_data,
            after_data=after_data,
            request=mock_request,
            custom_field='custom_value'
        )
        
        self.assertIsNotNone(audit_record)
        self.assertEqual(audit_record.model_name, 'TestModel')
        self.assertEqual(audit_record.object_id, 789)
        self.assertEqual(audit_record.operation, 'UPDATE')
        self.assertEqual(audit_record.before_data, before_data)
        self.assertEqual(audit_record.after_data, after_data)
        self.assertEqual(audit_record.ip_address, '10.0.0.1')  # First IP from X-Forwarded-For
        self.assertEqual(audit_record.user_agent, 'Test User Agent')
        self.assertEqual(audit_record.additional_context['custom_field'], 'custom_value')
    
    def test_get_client_ip_extraction(self):
        """Test IP address extraction from request"""
        # Test X-Forwarded-For header
        mock_request1 = Mock()
        mock_request1.META = {
            'HTTP_X_FORWARDED_FOR': '10.0.0.1, 192.168.1.1',
            'REMOTE_ADDR': '127.0.0.1'
        }
        
        ip1 = AuditTrail._get_client_ip(mock_request1)
        self.assertEqual(ip1, '10.0.0.1')
        
        # Test REMOTE_ADDR fallback
        mock_request2 = Mock()
        mock_request2.META = {
            'REMOTE_ADDR': '192.168.1.100'
        }
        
        ip2 = AuditTrail._get_client_ip(mock_request2)
        self.assertEqual(ip2, '192.168.1.100')
    
    def test_string_representation(self):
        """Test __str__ method"""
        audit_record = AuditTrail.objects.create(
            model_name='TestModel',
            object_id=123,
            operation='CREATE',
            user=self.user,
            source_service='TestService'
        )
        
        expected_str = f'CREATE on TestModel#123 by {self.user.username}'
        self.assertEqual(str(audit_record), expected_str)
    
    def test_log_operation_error_handling(self):
        """Test that log_operation handles errors gracefully"""
        # Test with invalid user (should not raise exception)
        with patch('governance.models.logger') as mock_logger:
            # Force an exception during record creation
            with patch.object(AuditTrail.objects, 'create', side_effect=DatabaseError("Test error")):
                result = AuditTrail.log_operation(
                    model_name='TestModel',
                    object_id=123,
                    operation='CREATE',
                    user=self.user,
                    source_service='TestService'
                )
                
                # Should return None and log error
                self.assertIsNone(result)
                mock_logger.error.assert_called_once()


class QuarantineRecordModelTests(TestCase):
    """Unit tests for QuarantineRecord model validation and functionality"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='quarantine_user',
            email='quarantine@example.com',
            password='testpass123'
        )
        self.resolver_user = User.objects.create_user(
            username='resolver_user',
            email='resolver@example.com',
            password='testpass123'
        )
    
    def test_model_creation_with_required_fields(self):
        """Test creating QuarantineRecord with required fields"""
        original_data = {'id': 123, 'name': 'Test Record', 'status': 'active'}
        
        quarantine_record = QuarantineRecord.objects.create(
            model_name='TestModel',
            object_id=123,
            corruption_type='SUSPICIOUS_PATTERN',
            original_data=original_data,
            quarantine_reason='Detected unusual data pattern',
            quarantined_by=self.user
        )
        
        self.assertEqual(quarantine_record.model_name, 'TestModel')
        self.assertEqual(quarantine_record.object_id, 123)
        self.assertEqual(quarantine_record.corruption_type, 'SUSPICIOUS_PATTERN')
        self.assertEqual(quarantine_record.original_data, original_data)
        self.assertEqual(quarantine_record.quarantine_reason, 'Detected unusual data pattern')
        self.assertEqual(quarantine_record.quarantined_by, self.user)
        self.assertEqual(quarantine_record.status, 'QUARANTINED')  # Default status
        self.assertIsNotNone(quarantine_record.quarantined_at)
    
    def test_corruption_type_choices_validation(self):
        """Test that corruption_type field validates against allowed choices"""
        valid_corruption_types = [
            'ORPHANED_ENTRY',
            'NEGATIVE_STOCK',
            'UNBALANCED_ENTRY',
            'MULTIPLE_ACTIVE_YEAR',
            'INVALID_SOURCE_LINK',
            'AUTHORITY_VIOLATION',
            'SUSPICIOUS_PATTERN'
        ]
        
        for corruption_type in valid_corruption_types:
            quarantine_record = QuarantineRecord.objects.create(
                model_name='TestModel',
                object_id=123,
                corruption_type=corruption_type,
                original_data={'test': 'data'},
                quarantine_reason=f'Test {corruption_type}',
                quarantined_by=self.user
            )
            self.assertEqual(quarantine_record.corruption_type, corruption_type)
    
    def test_status_choices_validation(self):
        """Test that status field validates against allowed choices"""
        valid_statuses = ['QUARANTINED', 'UNDER_REVIEW', 'RESOLVED', 'PERMANENT']
        
        for status in valid_statuses:
            quarantine_record = QuarantineRecord.objects.create(
                model_name='TestModel',
                object_id=123,
                corruption_type='SUSPICIOUS_PATTERN',
                original_data={'test': 'data'},
                quarantine_reason='Test quarantine',
                quarantined_by=self.user,
                status=status
            )
            self.assertEqual(quarantine_record.status, status)
    
    def test_resolve_method(self):
        """Test resolve method functionality"""
        quarantine_record = QuarantineRecord.objects.create(
            model_name='TestModel',
            object_id=456,
            corruption_type='ORPHANED_ENTRY',
            original_data={'id': 456, 'orphaned': True},
            quarantine_reason='Entry has no valid parent',
            quarantined_by=self.user
        )
        
        # Initially should be quarantined
        self.assertEqual(quarantine_record.status, 'QUARANTINED')
        self.assertIsNone(quarantine_record.resolved_at)
        self.assertIsNone(quarantine_record.resolved_by)
        
        # Resolve the quarantine
        resolution_notes = 'Fixed by linking to correct parent record'
        quarantine_record.resolve(self.resolver_user, resolution_notes)
        
        # Refresh from database
        quarantine_record.refresh_from_db()
        
        self.assertEqual(quarantine_record.status, 'RESOLVED')
        self.assertEqual(quarantine_record.resolved_by, self.resolver_user)
        self.assertEqual(quarantine_record.resolution_notes, resolution_notes)
        self.assertIsNotNone(quarantine_record.resolved_at)
        
        # Verify audit trail was created
        audit_records = AuditTrail.objects.filter(
            model_name='QuarantineRecord',
            object_id=quarantine_record.id,
            operation='UPDATE',
            user=self.resolver_user
        )
        self.assertTrue(audit_records.exists())
    
    def test_string_representation(self):
        """Test __str__ method"""
        quarantine_record = QuarantineRecord.objects.create(
            model_name='JournalEntry',
            object_id=789,
            corruption_type='ORPHANED_ENTRY',
            original_data={'test': 'data'},
            quarantine_reason='Test quarantine',
            quarantined_by=self.user
        )
        
        expected_str = 'ORPHANED_ENTRY - JournalEntry#789'
        self.assertEqual(str(quarantine_record), expected_str)


class AuthorityDelegationModelTests(TestCase):
    """Unit tests for AuthorityDelegation model validation and functionality"""
    
    def setUp(self):
        self.granter_user = User.objects.create_user(
            username='granter_user',
            email='granter@example.com',
            password='testpass123',
            is_superuser=True
        )
        self.revoker_user = User.objects.create_user(
            username='revoker_user',
            email='revoker@example.com',
            password='testpass123',
            is_superuser=True
        )
    
    def test_model_creation_with_valid_data(self):
        """Test creating AuthorityDelegation with valid data"""
        expires_at = timezone.now() + timedelta(hours=12)
        
        delegation = AuthorityDelegation.objects.create(
            from_service='AccountingGateway',
            to_service='RepairService',
            model_name='JournalEntry',
            expires_at=expires_at,
            granted_by=self.granter_user,
            reason='Emergency repair of corrupted entries'
        )
        
        self.assertEqual(delegation.from_service, 'AccountingGateway')
        self.assertEqual(delegation.to_service, 'RepairService')
        self.assertEqual(delegation.model_name, 'JournalEntry')
        self.assertEqual(delegation.expires_at, expires_at)
        self.assertEqual(delegation.granted_by, self.granter_user)
        self.assertEqual(delegation.reason, 'Emergency repair of corrupted entries')
        self.assertTrue(delegation.is_active)
        self.assertIsNone(delegation.revoked_at)
        self.assertIsNone(delegation.revoked_by)
    
    def test_clean_method_validation(self):
        """Test model clean method validation"""
        now = timezone.now()
        
        # Test expiration time before grant time
        delegation = AuthorityDelegation(
            from_service='TestService1',
            to_service='TestService2',
            model_name='TestModel',
            granted_at=now,
            expires_at=now - timedelta(hours=1),  # Past time
            granted_by=self.granter_user,
            reason='Test delegation'
        )
        
        with self.assertRaises(ValidationError) as cm:
            delegation.clean()
        
        self.assertIn('Expiration time must be after grant time', str(cm.exception))
        
        # Test delegation duration exceeding maximum (24 hours)
        delegation2 = AuthorityDelegation(
            from_service='TestService1',
            to_service='TestService2',
            model_name='TestModel',
            granted_at=now,
            expires_at=now + timedelta(hours=25),  # Exceeds 24 hour limit
            granted_by=self.granter_user,
            reason='Test delegation'
        )
        
        with self.assertRaises(ValidationError) as cm:
            delegation2.clean()
        
        self.assertIn('Delegation duration cannot exceed', str(cm.exception))
    
    def test_is_expired_method(self):
        """Test is_expired method functionality"""
        # Create expired delegation
        past_time = timezone.now() - timedelta(hours=1)
        expired_delegation = AuthorityDelegation.objects.create(
            from_service='TestService1',
            to_service='TestService2',
            model_name='TestModel',
            expires_at=past_time,
            granted_by=self.granter_user,
            reason='Test expired delegation'
        )
        
        # Create active delegation
        future_time = timezone.now() + timedelta(hours=1)
        active_delegation = AuthorityDelegation.objects.create(
            from_service='TestService3',
            to_service='TestService4',
            model_name='TestModel',
            expires_at=future_time,
            granted_by=self.granter_user,
            reason='Test active delegation'
        )
        
        self.assertTrue(expired_delegation.is_expired())
        self.assertFalse(active_delegation.is_expired())
    
    def test_is_valid_method(self):
        """Test is_valid method functionality"""
        future_time = timezone.now() + timedelta(hours=1)
        
        # Create valid delegation
        valid_delegation = AuthorityDelegation.objects.create(
            from_service='TestService1',
            to_service='TestService2',
            model_name='TestModel',
            expires_at=future_time,
            granted_by=self.granter_user,
            reason='Test valid delegation'
        )
        
        self.assertTrue(valid_delegation.is_valid())
        
        # Test invalid delegation (revoked)
        valid_delegation.revoke(self.revoker_user, 'Test revocation')
        self.assertFalse(valid_delegation.is_valid())
        
        # Test invalid delegation (expired)
        past_time = timezone.now() - timedelta(hours=1)
        expired_delegation = AuthorityDelegation.objects.create(
            from_service='TestService3',
            to_service='TestService4',
            model_name='TestModel',
            expires_at=past_time,
            granted_by=self.granter_user,
            reason='Test expired delegation'
        )
        
        self.assertFalse(expired_delegation.is_valid())
    
    def test_revoke_method(self):
        """Test revoke method functionality"""
        delegation = AuthorityDelegation.objects.create(
            from_service='TestService1',
            to_service='TestService2',
            model_name='TestModel',
            expires_at=timezone.now() + timedelta(hours=12),
            granted_by=self.granter_user,
            reason='Test delegation for revocation'
        )
        
        # Initially should be active
        self.assertTrue(delegation.is_active)
        self.assertIsNone(delegation.revoked_at)
        self.assertIsNone(delegation.revoked_by)
        
        # Revoke the delegation
        revocation_reason = 'Emergency revocation due to security concern'
        delegation.revoke(self.revoker_user, revocation_reason)
        
        # Refresh from database
        delegation.refresh_from_db()
        
        self.assertFalse(delegation.is_active)
        self.assertEqual(delegation.revoked_by, self.revoker_user)
        self.assertIsNotNone(delegation.revoked_at)
        
        # Verify audit trail was created
        audit_records = AuditTrail.objects.filter(
            model_name='AuthorityDelegation',
            object_id=delegation.id,
            operation='UPDATE',
            user=self.revoker_user
        )
        self.assertTrue(audit_records.exists())
    
    def test_check_delegation_class_method(self):
        """Test check_delegation class method functionality"""
        # Create valid delegation
        delegation = AuthorityDelegation.objects.create(
            from_service='AccountingGateway',
            to_service='RepairService',
            model_name='JournalEntry',
            expires_at=timezone.now() + timedelta(hours=12),
            granted_by=self.granter_user,
            reason='Test delegation check'
        )
        
        # Should find valid delegation
        is_valid = AuthorityDelegation.check_delegation(
            from_service='AccountingGateway',
            to_service='RepairService',
            model_name='JournalEntry'
        )
        self.assertTrue(is_valid)
        
        # Should not find delegation for different parameters
        is_valid_different = AuthorityDelegation.check_delegation(
            from_service='MovementService',
            to_service='RepairService',
            model_name='Stock'
        )
        self.assertFalse(is_valid_different)
        
        # Should not find delegation after revocation
        delegation.revoke(self.revoker_user, 'Test revocation')
        is_valid_after_revoke = AuthorityDelegation.check_delegation(
            from_service='AccountingGateway',
            to_service='RepairService',
            model_name='JournalEntry'
        )
        self.assertFalse(is_valid_after_revoke)
    
    def test_string_representation(self):
        """Test __str__ method"""
        delegation = AuthorityDelegation.objects.create(
            from_service='AccountingGateway',
            to_service='RepairService',
            model_name='JournalEntry',
            expires_at=timezone.now() + timedelta(hours=12),
            granted_by=self.granter_user,
            reason='Test delegation'
        )
        
        expected_str = 'AccountingGateway → RepairService for JournalEntry'
        self.assertEqual(str(delegation), expected_str)


class AuthorityDelegationConcurrencyTests(TransactionTestCase):
    """Thread-safety tests for AuthorityDelegation model"""
    
    def setUp(self):
        self.granter_user = User.objects.create_user(
            username='concurrent_granter',
            email='granter@example.com',
            password='testpass123',
            is_superuser=True
        )
    
    def test_concurrent_delegation_checks(self):
        """Test concurrent delegation checks are thread-safe"""
        # Create delegation
        delegation = AuthorityDelegation.objects.create(
            from_service='TestService1',
            to_service='TestService2',
            model_name='TestModel',
            expires_at=timezone.now() + timedelta(hours=12),
            granted_by=self.granter_user,
            reason='Concurrent test delegation'
        )
        
        results = []
        errors = []
        
        def check_delegation_concurrent(thread_id):
            """Perform concurrent delegation checks"""
            try:
                for i in range(10):
                    is_valid = AuthorityDelegation.check_delegation(
                        from_service='TestService1',
                        to_service='TestService2',
                        model_name='TestModel'
                    )
                    results.append({
                        'thread_id': thread_id,
                        'check_id': i,
                        'is_valid': is_valid
                    })
                    
            except Exception as e:
                errors.append(f"Thread {thread_id}: {str(e)}")
        
        # Start multiple threads
        threads = []
        num_threads = 5
        
        for i in range(num_threads):
            thread = threading.Thread(target=check_delegation_concurrent, args=(i,))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # Analyze results
        self.assertEqual(len(errors), 0, f"Errors occurred: {errors}")
        self.assertEqual(len(results), num_threads * 10)
        
        # All checks should return True (delegation is valid)
        all_valid = all(result['is_valid'] for result in results)
        self.assertTrue(all_valid, "All delegation checks should return True")


class GovernanceContextTests(TestCase):
    """Unit tests for GovernanceContext thread-local storage"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='context_user',
            email='context@example.com',
            password='testpass123'
        )
    
    def test_context_set_and_get(self):
        """Test setting and getting governance context"""
        mock_request = Mock()
        
        GovernanceContext.set_context(
            user=self.user,
            service='TestService',
            operation='TEST_OPERATION',
            request=mock_request
        )
        
        context = GovernanceContext.get_context()
        
        self.assertEqual(context['user'], self.user)
        self.assertEqual(context['service'], 'TestService')
        self.assertEqual(context['operation'], 'TEST_OPERATION')
        self.assertEqual(context['request'], mock_request)
    
    def test_context_clear(self):
        """Test clearing governance context"""
        GovernanceContext.set_context(
            user=self.user,
            service='TestService',
            operation='TEST_OPERATION'
        )
        
        # Verify context is set
        context = GovernanceContext.get_context()
        self.assertEqual(context['user'], self.user)
        
        # Clear context
        GovernanceContext.clear_context()
        
        # Verify context is cleared
        context = GovernanceContext.get_context()
        self.assertIsNone(context['user'])
        self.assertIsNone(context['service'])
        self.assertIsNone(context['operation'])
        self.assertIsNone(context['request'])
    
    def test_context_convenience_methods(self):
        """Test convenience methods for getting current user and service"""
        GovernanceContext.set_context(
            user=self.user,
            service='ConvenienceTestService'
        )
        
        current_user = GovernanceContext.get_current_user()
        current_service = GovernanceContext.get_current_service()
        
        self.assertEqual(current_user, self.user)
        self.assertEqual(current_service, 'ConvenienceTestService')
        
        # Test when context is not set
        GovernanceContext.clear_context()
        
        current_user = GovernanceContext.get_current_user()
        current_service = GovernanceContext.get_current_service()
        
        self.assertIsNone(current_user)
        self.assertIsNone(current_service)


class GovernanceContextConcurrencyTests(TransactionTestCase):
    """Thread-safety tests for GovernanceContext"""
    
    def setUp(self):
        self.users = []
        for i in range(5):
            user = User.objects.create_user(
                username=f'thread_user_{i}',
                email=f'thread{i}@example.com',
                password='testpass123'
            )
            self.users.append(user)
    
    def test_context_thread_isolation(self):
        """Test that governance context is properly isolated between threads"""
        results = []
        errors = []
        
        def thread_context_test(thread_id):
            """Test context isolation in individual thread"""
            try:
                user = self.users[thread_id]
                service = f'ThreadService_{thread_id}'
                operation = f'THREAD_OP_{thread_id}'
                
                # Set context for this thread
                GovernanceContext.set_context(
                    user=user,
                    service=service,
                    operation=operation
                )
                
                # Small delay to allow potential context mixing
                time.sleep(0.01)
                
                # Get context and verify it's correct for this thread
                context = GovernanceContext.get_context()
                current_user = GovernanceContext.get_current_user()
                current_service = GovernanceContext.get_current_service()
                
                results.append({
                    'thread_id': thread_id,
                    'context_user_id': context['user'].id if context['user'] else None,
                    'context_service': context['service'],
                    'context_operation': context['operation'],
                    'current_user_id': current_user.id if current_user else None,
                    'current_service': current_service,
                    'expected_user_id': user.id,
                    'expected_service': service,
                    'expected_operation': operation
                })
                
                # Clear context
                GovernanceContext.clear_context()
                
            except Exception as e:
                errors.append(f"Thread {thread_id}: {str(e)}")
        
        # Start multiple threads
        threads = []
        num_threads = 5
        
        for i in range(num_threads):
            thread = threading.Thread(target=thread_context_test, args=(i,))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # Analyze results
        self.assertEqual(len(errors), 0, f"Errors occurred: {errors}")
        self.assertEqual(len(results), num_threads)
        
        # Verify each thread had its own isolated context
        for result in results:
            thread_id = result['thread_id']
            
            # Context should match expected values for this thread
            self.assertEqual(result['context_user_id'], result['expected_user_id'],
                           f"Thread {thread_id}: Context user mismatch")
            self.assertEqual(result['context_service'], result['expected_service'],
                           f"Thread {thread_id}: Context service mismatch")
            self.assertEqual(result['context_operation'], result['expected_operation'],
                           f"Thread {thread_id}: Context operation mismatch")
            
            # Convenience methods should also match
            self.assertEqual(result['current_user_id'], result['expected_user_id'],
                           f"Thread {thread_id}: Current user mismatch")
            self.assertEqual(result['current_service'], result['expected_service'],
                           f"Thread {thread_id}: Current service mismatch")


@pytest.mark.django_db
class GovernanceModelsIntegrationTests:
    """Integration tests for governance models working together"""
    
    def test_complete_governance_workflow(self):
        """Test complete workflow involving all governance models"""
        # Create test user
        user = User.objects.create_user(
            username='integration_user',
            email='integration@example.com',
            password='testpass123'
        )
        
        # Set governance context
        GovernanceContext.set_context(
            user=user,
            service='IntegrationTestService',
            operation='COMPLETE_WORKFLOW'
        )
        
        try:
            # 1. Create idempotency record
            is_duplicate, idempotency_record = IdempotencyRecord.check_and_record(
                operation_type='integration_test',
                idempotency_key='workflow_key_123',
                result_data={'workflow_id': 123, 'status': 'started'},
                user=user,
                expires_in_hours=1
            )
            
            assert not is_duplicate
            assert idempotency_record is not None
            
            # 2. Create audit trail
            audit_record = AuditTrail.log_operation(
                model_name='WorkflowModel',
                object_id=123,
                operation='CREATE',
                user=user,
                source_service='IntegrationTestService',
                before_data=None,
                after_data={'status': 'created', 'workflow_id': 123}
            )
            
            assert audit_record is not None
            
            # 3. Create authority delegation
            delegation = AuthorityDelegation.objects.create(
                from_service='IntegrationTestService',
                to_service='WorkflowService',
                model_name='WorkflowModel',
                expires_at=timezone.now() + timedelta(hours=2),
                granted_by=user,
                reason='Integration test delegation'
            )
            
            assert delegation.is_valid()
            
            # 4. Check delegation
            is_delegated = AuthorityDelegation.check_delegation(
                from_service='IntegrationTestService',
                to_service='WorkflowService',
                model_name='WorkflowModel'
            )
            
            assert is_delegated
            
            # 5. Create quarantine record (simulating corruption detection)
            quarantine_record = QuarantineRecord.objects.create(
                model_name='WorkflowModel',
                object_id=123,
                corruption_type='SUSPICIOUS_PATTERN',
                original_data={'workflow_id': 123, 'suspicious_field': 'unusual_value'},
                quarantine_reason='Detected unusual pattern in workflow data',
                quarantined_by=user
            )
            
            assert quarantine_record.status == 'QUARANTINED'
            
            # 6. Resolve quarantine
            quarantine_record.resolve(user, 'Pattern verified as legitimate')
            
            assert quarantine_record.status == 'RESOLVED'
            
            # 7. Verify all records exist and are properly linked
            assert IdempotencyRecord.objects.filter(
                operation_type='integration_test',
                idempotency_key='workflow_key_123'
            ).exists()
            
            assert AuditTrail.objects.filter(
                model_name='WorkflowModel',
                object_id=123,
                user=user
            ).count() >= 2  # At least workflow creation + quarantine resolution
            
            assert AuthorityDelegation.objects.filter(
                from_service='IntegrationTestService',
                to_service='WorkflowService',
                model_name='WorkflowModel',
                is_active=True
            ).exists()
            
            assert QuarantineRecord.objects.filter(
                model_name='WorkflowModel',
                object_id=123,
                status='RESOLVED'
            ).exists()
            
        finally:
            GovernanceContext.clear_context()