"""
Unit tests for QuarantineSystem - Task 16 Implementation

Tests the comprehensive thread-safe quarantine system including:
- Thread-safe storage operations
- Management capabilities
- Reporting tools
- Integration with RepairService
- Batch operations
- Health checks
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db import transaction
import threading
import time

from governance.models import QuarantineRecord, AuditTrail, GovernanceContext
from governance.services.quarantine_system import (
    QuarantineSystem, QuarantineStorage, QuarantineManager, 
    QuarantineReporter, quarantine_system
)
from governance.services.repair_service import CorruptionReport
from governance.exceptions import QuarantineError, ConcurrencyError

User = get_user_model()


class QuarantineSystemTestCase(TestCase):
    """Test cases for QuarantineSystem core functionality"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='test_user',
            email='test@example.com',
            password='testpass123'
        )
        self.quarantine_system = QuarantineSystem()
        
        # Set up governance context
        GovernanceContext.set_context(
            user=self.user,
            service='QuarantineSystem'
        )
    
    def tearDown(self):
        """Clean up after tests"""
        GovernanceContext.clear_context()
    
    def test_quarantine_data_basic(self):
        """Test basic data quarantine functionality"""
        # Test data
        model_name = 'JournalEntry'
        object_id = 123
        corruption_type = 'ORPHANED_ENTRY'
        reason = 'Test quarantine reason'
        original_data = {'entry_id': 123, 'amount': '100.00'}
        
        # Quarantine data
        quarantine_record = self.quarantine_system.quarantine_data(
            model_name=model_name,
            object_id=object_id,
            corruption_type=corruption_type,
            reason=reason,
            original_data=original_data,
            user=self.user
        )
        
        # Verify quarantine record
        self.assertIsInstance(quarantine_record, QuarantineRecord)
        self.assertEqual(quarantine_record.model_name, model_name)
        self.assertEqual(quarantine_record.object_id, object_id)
        self.assertEqual(quarantine_record.corruption_type, corruption_type)
        self.assertEqual(quarantine_record.quarantine_reason, reason)
        self.assertEqual(quarantine_record.original_data, original_data)
        self.assertEqual(quarantine_record.quarantined_by, self.user)
        self.assertEqual(quarantine_record.status, 'QUARANTINED')
        
        # Verify audit trail was created
        audit_records = AuditTrail.objects.filter(
            model_name='QuarantineRecord',
            object_id=quarantine_record.id,
            operation='CREATE'
        )
        self.assertTrue(audit_records.exists())
    
    def test_quarantine_data_duplicate_prevention(self):
        """Test that duplicate quarantine records are prevented"""
        # Test data
        model_name = 'JournalEntry'
        object_id = 123
        corruption_type = 'ORPHANED_ENTRY'
        reason = 'Test quarantine reason'
        original_data = {'entry_id': 123}
        
        # First quarantine
        record1 = self.quarantine_system.quarantine_data(
            model_name=model_name,
            object_id=object_id,
            corruption_type=corruption_type,
            reason=reason,
            original_data=original_data,
            user=self.user
        )
        
        # Second quarantine (should return existing record)
        record2 = self.quarantine_system.quarantine_data(
            model_name=model_name,
            object_id=object_id,
            corruption_type=corruption_type,
            reason=reason,
            original_data=original_data,
            user=self.user
        )
        
        # Should be the same record
        self.assertEqual(record1.id, record2.id)
        
        # Should only have one record in database
        count = QuarantineRecord.objects.filter(
            model_name=model_name,
            object_id=object_id,
            corruption_type=corruption_type
        ).count()
        self.assertEqual(count, 1)
    
    def test_resolve_quarantine(self):
        """Test quarantine resolution functionality"""
        # Create quarantine record
        quarantine_record = QuarantineRecord.objects.create(
            model_name='JournalEntry',
            object_id=123,
            corruption_type='ORPHANED_ENTRY',
            quarantine_reason='Test reason',
            original_data={'test': 'data'},
            quarantined_by=self.user,
            status='QUARANTINED'
        )
        
        resolution_notes = 'Resolved by fixing source linkage'
        
        # Resolve quarantine
        resolved_record = self.quarantine_system.resolve_quarantine(
            quarantine_id=quarantine_record.id,
            resolution_notes=resolution_notes,
            user=self.user
        )
        
        # Verify resolution
        self.assertEqual(resolved_record.status, 'RESOLVED')
        self.assertEqual(resolved_record.resolution_notes, resolution_notes)
        self.assertEqual(resolved_record.resolved_by, self.user)
        self.assertIsNotNone(resolved_record.resolved_at)
        
        # Verify audit trail
        audit_records = AuditTrail.objects.filter(
            model_name='QuarantineRecord',
            object_id=quarantine_record.id,
            operation='UPDATE'
        )
        self.assertTrue(audit_records.exists())
    
    def test_batch_quarantine_data(self):
        """Test batch quarantine operations"""
        # Test data
        quarantine_data_list = [
            {
                'model_name': 'JournalEntry',
                'object_id': 123,
                'corruption_type': 'ORPHANED_ENTRY',
                'reason': 'Test reason 1',
                'original_data': {'entry_id': 123},
                'context': {'batch': True}
            },
            {
                'model_name': 'Stock',
                'object_id': 456,
                'corruption_type': 'NEGATIVE_STOCK',
                'reason': 'Test reason 2',
                'original_data': {'stock_id': 456, 'quantity': -10},
                'context': {'batch': True}
            }
        ]
        
        # Batch quarantine
        result = self.quarantine_system.batch_quarantine_data(
            quarantine_data_list=quarantine_data_list,
            user=self.user
        )
        
        # Verify results
        self.assertTrue(result['success'])
        self.assertEqual(result['created_count'], 2)
        self.assertEqual(result['requested_count'], 2)
        self.assertEqual(len(result['quarantine_ids']), 2)
        
        # Verify records were created
        self.assertEqual(QuarantineRecord.objects.count(), 2)
    
    def test_batch_resolve_quarantine(self):
        """Test batch quarantine resolution"""
        # Create test quarantine records
        records = []
        for i in range(3):
            record = QuarantineRecord.objects.create(
                model_name='JournalEntry',
                object_id=100 + i,
                corruption_type='ORPHANED_ENTRY',
                quarantine_reason=f'Test reason {i}',
                original_data={'entry_id': 100 + i},
                quarantined_by=self.user,
                status='QUARANTINED'
            )
            records.append(record)
        
        quarantine_ids = [r.id for r in records]
        resolution_notes = 'Batch resolution test'
        
        # Batch resolve
        result = self.quarantine_system.batch_resolve_quarantine(
            quarantine_ids=quarantine_ids,
            resolution_notes=resolution_notes,
            user=self.user
        )
        
        # Verify results
        self.assertEqual(len(result['updated']), 3)
        self.assertEqual(len(result['failed']), 0)
        self.assertEqual(result['total_requested'], 3)
        
        # Verify all records are resolved
        resolved_count = QuarantineRecord.objects.filter(
            id__in=quarantine_ids,
            status='RESOLVED'
        ).count()
        self.assertEqual(resolved_count, 3)


class QuarantineManagerTestCase(TestCase):
    """Test cases for QuarantineManager functionality"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='test_user',
            email='test@example.com',
            password='testpass123'
        )
        self.manager = QuarantineManager()
        
        # Create test quarantine records
        self.test_records = []
        corruption_types = ['ORPHANED_ENTRY', 'NEGATIVE_STOCK', 'UNBALANCED_ENTRY']
        statuses = ['QUARANTINED', 'UNDER_REVIEW', 'RESOLVED']
        
        for i in range(9):
            record = QuarantineRecord.objects.create(
                model_name='JournalEntry',
                object_id=100 + i,
                corruption_type=corruption_types[i % 3],
                quarantine_reason=f'Test reason {i}',
                original_data={'entry_id': 100 + i},
                quarantined_by=self.user,
                status=statuses[i % 3],
                quarantined_at=timezone.now() - timedelta(days=i)
            )
            self.test_records.append(record)
    
    def test_search_quarantine_records_no_filters(self):
        """Test searching quarantine records without filters"""
        result = self.manager.search_quarantine_records()
        
        # Should return all records
        self.assertEqual(len(result['records']), 9)
        self.assertEqual(result['pagination']['total_records'], 9)
        self.assertEqual(result['pagination']['current_page'], 1)
        self.assertTrue(result['pagination']['total_pages'] >= 1)
    
    def test_search_quarantine_records_with_filters(self):
        """Test searching quarantine records with filters"""
        # Filter by corruption type
        result = self.manager.search_quarantine_records(
            filters={'corruption_type': 'ORPHANED_ENTRY'}
        )
        
        # Should return 3 records (every 3rd record)
        self.assertEqual(len(result['records']), 3)
        for record in result['records']:
            self.assertEqual(record.corruption_type, 'ORPHANED_ENTRY')
        
        # Filter by status
        result = self.manager.search_quarantine_records(
            filters={'status': 'RESOLVED'}
        )
        
        # Should return 3 records
        self.assertEqual(len(result['records']), 3)
        for record in result['records']:
            self.assertEqual(record.status, 'RESOLVED')
        
        # Filter by multiple statuses
        result = self.manager.search_quarantine_records(
            filters={'status': ['QUARANTINED', 'UNDER_REVIEW']}
        )
        
        # Should return 6 records
        self.assertEqual(len(result['records']), 6)
    
    def test_search_quarantine_records_pagination(self):
        """Test pagination in search results"""
        # Test with small page size
        result = self.manager.search_quarantine_records(
            page=1,
            page_size=3
        )
        
        self.assertEqual(len(result['records']), 3)
        self.assertEqual(result['pagination']['current_page'], 1)
        self.assertEqual(result['pagination']['page_size'], 3)
        self.assertTrue(result['pagination']['has_next'])
        self.assertFalse(result['pagination']['has_previous'])
        
        # Test second page
        result = self.manager.search_quarantine_records(
            page=2,
            page_size=3
        )
        
        self.assertEqual(len(result['records']), 3)
        self.assertEqual(result['pagination']['current_page'], 2)
        self.assertTrue(result['pagination']['has_previous'])
    
    def test_get_quarantine_statistics(self):
        """Test quarantine statistics generation"""
        stats = self.manager.get_quarantine_statistics()
        
        # Verify summary statistics
        self.assertEqual(stats['summary']['total_quarantined'], 9)
        self.assertIn('recent_24h', stats['summary'])
        self.assertIn('recent_7d', stats['summary'])
        self.assertIn('resolved_count', stats['summary'])
        self.assertIn('resolution_rate', stats['summary'])
        
        # Verify breakdowns
        self.assertIn('by_status', stats)
        self.assertIn('by_corruption_type', stats)
        self.assertIn('by_model', stats)
        
        # Verify status breakdown
        self.assertEqual(stats['by_status']['QUARANTINED'], 3)
        self.assertEqual(stats['by_status']['UNDER_REVIEW'], 3)
        self.assertEqual(stats['by_status']['RESOLVED'], 3)
        
        # Verify corruption type breakdown
        self.assertEqual(stats['by_corruption_type']['ORPHANED_ENTRY'], 3)
        self.assertEqual(stats['by_corruption_type']['NEGATIVE_STOCK'], 3)
        self.assertEqual(stats['by_corruption_type']['UNBALANCED_ENTRY'], 3)
    
    def test_get_quarantine_trends(self):
        """Test quarantine trends analysis"""
        trends = self.manager.get_quarantine_trends(days=30)
        
        # Verify structure
        self.assertIn('period', trends)
        self.assertIn('daily_counts', trends)
        self.assertIn('corruption_type_trends', trends)
        
        # Verify period info
        self.assertEqual(trends['period']['days'], 30)
        self.assertIn('start_date', trends['period'])
        self.assertIn('end_date', trends['period'])
        
        # Verify trends data
        self.assertIsInstance(trends['daily_counts'], list)
        self.assertIsInstance(trends['corruption_type_trends'], dict)


class QuarantineReporterTestCase(TestCase):
    """Test cases for QuarantineReporter functionality"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='test_user',
            email='test@example.com',
            password='testpass123'
        )
        self.reporter = QuarantineReporter()
        
        # Create test data
        QuarantineRecord.objects.create(
            model_name='JournalEntry',
            object_id=123,
            corruption_type='ORPHANED_ENTRY',
            quarantine_reason='Test reason',
            original_data={'entry_id': 123},
            quarantined_by=self.user,
            status='QUARANTINED'
        )
        
        # Create resolved record for resolution analysis
        resolved_record = QuarantineRecord.objects.create(
            model_name='Stock',
            object_id=456,
            corruption_type='NEGATIVE_STOCK',
            quarantine_reason='Negative stock test',
            original_data={'stock_id': 456},
            quarantined_by=self.user,
            status='RESOLVED',
            resolved_by=self.user,
            resolved_at=timezone.now(),
            resolution_notes='Fixed manually'
        )
        # Set quarantined_at to earlier time for resolution time calculation
        resolved_record.quarantined_at = timezone.now() - timedelta(hours=2)
        resolved_record.save()
    
    def test_generate_summary_report(self):
        """Test summary report generation"""
        report = self.reporter.generate_comprehensive_report(report_type='summary')
        
        # Verify report structure
        self.assertEqual(report['report_type'], 'summary')
        self.assertIn('generated_at', report)
        self.assertIn('data', report)
        
        # Verify data sections
        self.assertIn('statistics', report['data'])
        self.assertIn('recent_quarantines', report['data'])
        
        # Verify statistics
        stats = report['data']['statistics']
        self.assertIn('summary', stats)
        self.assertIn('by_status', stats)
        self.assertIn('by_corruption_type', stats)
    
    def test_generate_trends_report(self):
        """Test trends report generation"""
        report = self.reporter.generate_comprehensive_report(report_type='trends')
        
        # Verify report structure
        self.assertEqual(report['report_type'], 'trends')
        self.assertIn('data', report)
        
        # Verify trends data
        self.assertIn('trends', report['data'])
        trends = report['data']['trends']
        self.assertIn('period', trends)
        self.assertIn('daily_counts', trends)
        self.assertIn('corruption_type_trends', trends)
    
    def test_generate_full_report(self):
        """Test full comprehensive report generation"""
        report = self.reporter.generate_comprehensive_report(report_type='full')
        
        # Verify report structure
        self.assertEqual(report['report_type'], 'full')
        self.assertIn('data', report)
        
        # Verify all data sections are present
        data = report['data']
        self.assertIn('statistics', data)
        self.assertIn('recent_quarantines', data)
        self.assertIn('trends', data)
        self.assertIn('corruption_type_details', data)
        self.assertIn('resolution_analysis', data)
        
        # Verify corruption type details
        corruption_details = data['corruption_type_details']
        self.assertIsInstance(corruption_details, dict)
        
        # Verify resolution analysis
        resolution_analysis = data['resolution_analysis']
        self.assertIn('resolution_by_corruption_type', resolution_analysis)


class QuarantineStorageTestCase(TransactionTestCase):
    """Test cases for QuarantineStorage thread-safety"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='test_user',
            email='test@example.com',
            password='testpass123'
        )
    
    def test_concurrent_quarantine_storage(self):
        """Test thread-safe concurrent quarantine storage"""
        results = []
        errors = []
        
        def quarantine_worker(worker_id):
            """Worker function for concurrent quarantine"""
            try:
                record = QuarantineStorage.store_quarantine_record(
                    model_name='JournalEntry',
                    object_id=123,  # Same object ID to test duplicate prevention
                    corruption_type='ORPHANED_ENTRY',
                    reason=f'Worker {worker_id} test',
                    original_data={'worker_id': worker_id},
                    user=self.user
                )
                results.append(record.id)
            except Exception as e:
                errors.append(str(e))
        
        # Create multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=quarantine_worker, args=(i,))
            threads.append(thread)
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Verify results
        self.assertEqual(len(errors), 0, f"Errors occurred: {errors}")
        
        # Should only have one unique record ID (duplicate prevention)
        unique_ids = set(results)
        self.assertEqual(len(unique_ids), 1)
        
        # Verify only one record was created in database
        count = QuarantineRecord.objects.filter(
            model_name='JournalEntry',
            object_id=123,
            corruption_type='ORPHANED_ENTRY'
        ).count()
        self.assertEqual(count, 1)
    
    def test_concurrent_status_updates(self):
        """Test thread-safe concurrent status updates"""
        # Create quarantine record
        record = QuarantineRecord.objects.create(
            model_name='JournalEntry',
            object_id=123,
            corruption_type='ORPHANED_ENTRY',
            quarantine_reason='Test reason',
            original_data={'test': 'data'},
            quarantined_by=self.user,
            status='QUARANTINED'
        )
        
        results = []
        errors = []
        
        def update_worker(worker_id):
            """Worker function for concurrent updates"""
            try:
                updated_record = QuarantineStorage.update_quarantine_status(
                    quarantine_id=record.id,
                    new_status='UNDER_REVIEW',
                    user=self.user,
                    notes=f'Updated by worker {worker_id}'
                )
                results.append(updated_record.status)
            except Exception as e:
                errors.append(str(e))
        
        # Create multiple threads
        threads = []
        for i in range(3):
            thread = threading.Thread(target=update_worker, args=(i,))
            threads.append(thread)
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Verify results
        self.assertEqual(len(errors), 0, f"Errors occurred: {errors}")
        
        # All updates should succeed with same status
        for status in results:
            self.assertEqual(status, 'UNDER_REVIEW')
        
        # Verify final status in database
        record.refresh_from_db()
        self.assertEqual(record.status, 'UNDER_REVIEW')


class QuarantineSystemIntegrationTestCase(TestCase):
    """Integration tests for QuarantineSystem with RepairService"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='test_user',
            email='test@example.com',
            password='testpass123'
        )
        self.quarantine_system = QuarantineSystem()
    
    def test_quarantine_from_corruption_report(self):
        """Test quarantine integration with RepairService corruption report"""
        # Create mock corruption report
        corruption_report = CorruptionReport()
        
        # Add high confidence issues (should not be quarantined automatically)
        corruption_report.add_corruption(
            corruption_type='ORPHANED_JOURNAL_ENTRIES',
            issues=[
                {'entry_id': 123, 'source_module': None},
                {'entry_id': 124, 'source_module': None}
            ],
            confidence='HIGH'
        )
        
        # Add low confidence issues (should be quarantined automatically)
        corruption_report.add_corruption(
            corruption_type='NEGATIVE_STOCK',
            issues=[
                {'stock_id': 456, 'quantity': -10},
                {'stock_id': 457, 'quantity': -5}
            ],
            confidence='LOW'
        )
        
        # Quarantine from corruption report
        result = self.quarantine_system.quarantine_from_corruption_report(
            corruption_report=corruption_report,
            user=self.user
        )
        
        # Verify results
        self.assertTrue(result['success'])
        self.assertEqual(result['created_count'], 2)  # Only low confidence issues
        
        # Verify quarantine records were created
        quarantine_count = QuarantineRecord.objects.filter(
            corruption_type='NEGATIVE_STOCK'
        ).count()
        self.assertEqual(quarantine_count, 2)
        
        # Verify high confidence issues were not quarantined
        high_confidence_count = QuarantineRecord.objects.filter(
            corruption_type='ORPHANED_JOURNAL_ENTRIES'
        ).count()
        self.assertEqual(high_confidence_count, 0)
    
    def test_health_check(self):
        """Test quarantine system health check"""
        # Create some test data
        QuarantineRecord.objects.create(
            model_name='JournalEntry',
            object_id=123,
            corruption_type='ORPHANED_ENTRY',
            quarantine_reason='Test reason',
            original_data={'test': 'data'},
            quarantined_by=self.user,
            status='QUARANTINED'
        )
        
        # Create stuck quarantine (over 30 days old)
        stuck_record = QuarantineRecord.objects.create(
            model_name='Stock',
            object_id=456,
            corruption_type='NEGATIVE_STOCK',
            quarantine_reason='Stuck test',
            original_data={'test': 'data'},
            quarantined_by=self.user,
            status='QUARANTINED'
        )
        # Manually set old date
        stuck_record.quarantined_at = timezone.now() - timedelta(days=35)
        stuck_record.save()
        
        # Run health check
        health_status = self.quarantine_system.health_check()
        
        # Verify health check structure
        self.assertIn('status', health_status)
        self.assertIn('checks', health_status)
        self.assertIn('timestamp', health_status)
        
        # Verify individual checks
        checks = health_status['checks']
        self.assertIn('database_connectivity', checks)
        self.assertIn('stuck_quarantines', checks)
        self.assertIn('recent_activity', checks)
        
        # Verify database connectivity check
        db_check = checks['database_connectivity']
        self.assertEqual(db_check['status'], 'ok')
        self.assertEqual(db_check['total_records'], 2)
        
        # Verify stuck quarantines check
        stuck_check = checks['stuck_quarantines']
        self.assertEqual(stuck_check['status'], 'warning')
        self.assertEqual(stuck_check['stuck_count'], 1)
        
        # Verify recent activity check
        activity_check = checks['recent_activity']
        self.assertEqual(activity_check['status'], 'ok')
        self.assertIn('recent_24h_count', activity_check)


@pytest.mark.django_db
class TestQuarantineSystemPytest:
    """Pytest-based tests for QuarantineSystem"""
    
    def test_quarantine_system_singleton(self):
        """Test that quarantine_system is properly initialized"""
        from governance.services.quarantine_system import quarantine_system
        
        assert quarantine_system is not None
        assert isinstance(quarantine_system, QuarantineSystem)
        assert hasattr(quarantine_system, 'storage')
        assert hasattr(quarantine_system, 'manager')
        assert hasattr(quarantine_system, 'reporter')
    
    def test_quarantine_system_thread_safety_mixin(self):
        """Test that QuarantineSystem uses ThreadSafeOperationMixin"""
        from governance.services.quarantine_system import QuarantineSystem
        from governance.thread_safety import ThreadSafeOperationMixin
        
        assert issubclass(QuarantineSystem, ThreadSafeOperationMixin)
        
        # Test that thread-safe operation context manager works
        qs = QuarantineSystem()
        with qs.thread_safe_operation("test_operation"):
            # Should not raise any exceptions
            pass
    
    @patch('governance.services.quarantine_system.monitor_operation')
    def test_monitoring_decorators(self, mock_monitor):
        """Test that monitoring decorators are applied"""
        from governance.services.quarantine_system import QuarantineSystem
        
        qs = QuarantineSystem()
        
        # Mock user
        user = Mock()
        user.username = 'test_user'
        
        # Test that monitor_operation is called
        with patch.object(qs.storage, 'store_quarantine_record') as mock_store:
            mock_store.return_value = Mock(id=1)
            
            qs.quarantine_data(
                model_name='TestModel',
                object_id=123,
                corruption_type='TEST_TYPE',
                reason='Test reason',
                original_data={'test': 'data'},
                user=user
            )
            
            # Verify monitoring was called
            mock_monitor.assert_called_with("quarantine_data")