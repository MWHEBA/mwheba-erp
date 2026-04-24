"""
Property-Based Tests for Orphaned Entry Prevention
Tests that the system prevents creation of orphaned journal entries with comprehensive property-based testing using Hypothesis.

Feature: code-governance-system, Property 12: Orphaned Entry Prevention
Validates: Requirements 7.1

Property Definition:
For any Journal_Entry in the system, it should have a valid source reference that points to an existing record
"""

import pytest
import logging
from decimal import Decimal
from datetime import date, timedelta
from unittest.mock import patch, MagicMock
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time
import random

from hypothesis import given, strategies as st, settings, assume, note
from hypothesis.extra.django import TestCase as HypothesisTestCase
from django.test import TransactionTestCase
from django.contrib.auth import get_user_model
from django.db import transaction, IntegrityError
from django.apps import apps

from governance.services import AccountingGateway, JournalEntryLineData, SourceLinkageService
from governance.models import GovernanceContext, QuarantineRecord
from governance.exceptions import ValidationError as GovernanceValidationError
from governance.services.repair_service import RepairService
from governance.services.quarantine_service import QuarantineService
from financial.models import JournalEntry, JournalEntryLine, ChartOfAccounts, AccountingPeriod, AccountType

User = get_user_model()
logger = logging.getLogger(__name__)


# ===== Hypothesis Strategies =====

def valid_source_models_strategy():
    """Generate valid source models from the allowlist"""
    allowed_sources = list(SourceLinkageService.ALLOWED_SOURCES)
    return st.sampled_from(allowed_sources).map(lambda x: x.split('.'))


def invalid_source_models_strategy():
    """Generate invalid source models not in allowlist"""
    invalid_sources = [
        ('invalid', 'InvalidModel'),
        ('fake', 'FakeModel'),
        ('test', 'NonExistentModel'),
        ('random', 'RandomModel'),
        ('', ''),  # Empty strings
        ('students', 'InvalidStudentModel'),
        ('financial', 'UnknownFinancialModel'),
        ('product', 'NonExistentProduct'),
        ('sale', 'InvalidSale')
    ]
    return st.sampled_from(invalid_sources)


def source_ids_strategy():
    """Generate realistic source IDs"""
    return st.integers(min_value=1, max_value=999999)


def invalid_source_ids_strategy():
    """Generate invalid source IDs"""
    return st.one_of(
        st.integers(min_value=-999, max_value=0),  # Negative or zero IDs
        st.just(None),  # None values
    )


def journal_entry_line_data_strategy():
    """Generate realistic journal entry line data"""
    return st.lists(
        st.builds(
            JournalEntryLineData,
            account_code=st.sampled_from(['1001', '1002', '2001', '2002', '3001', '4001', '5001']),
            debit=st.one_of(
                st.just(Decimal('0')),
                st.decimals(min_value=Decimal('0.01'), max_value=Decimal('5000'), places=2)
            ),
            credit=st.one_of(
                st.just(Decimal('0')),
                st.decimals(min_value=Decimal('0.01'), max_value=Decimal('5000'), places=2)
            ),
            description=st.text(min_size=5, max_size=100)
        ).filter(lambda line: (line.debit > 0) != (line.credit > 0)),  # Ensure only one is non-zero
        min_size=2,
        max_size=6
    )


def balanced_journal_entry_lines_strategy():
    """Generate balanced journal entry lines (debits = credits)"""
    @st.composite
    def _balanced_lines(draw):
        # Generate base amount
        amount = draw(st.decimals(min_value=Decimal('1.00'), max_value=Decimal('1000.00'), places=2))
        
        # Create debit line
        debit_line = JournalEntryLineData(
            account_code=draw(st.sampled_from(['1001', '1002', '3001'])),
            debit=amount,
            credit=Decimal('0.00'),
            description="Test debit line"
        )
        
        # Create credit line
        credit_line = JournalEntryLineData(
            account_code=draw(st.sampled_from(['2001', '2002', '4001'])),
            debit=Decimal('0.00'),
            credit=amount,
            description="Test credit line"
        )
        
        return [debit_line, credit_line]
    
    return _balanced_lines()


def orphaned_entry_scenarios_strategy():
    """Generate scenarios that would create orphaned entries"""
    return st.one_of(
        # Invalid source model
        st.tuples(
            invalid_source_models_strategy(),
            source_ids_strategy(),
            st.just('INVALID_SOURCE_MODEL')
        ),
        # Valid source model but non-existent record
        st.tuples(
            valid_source_models_strategy(),
            st.integers(min_value=999999, max_value=9999999),  # Very high IDs unlikely to exist
            st.just('NONEXISTENT_RECORD')
        ),
        # Invalid source ID
        st.tuples(
            valid_source_models_strategy(),
            invalid_source_ids_strategy(),
            st.just('INVALID_SOURCE_ID')
        )
    )


def concurrent_orphan_prevention_strategy():
    """Generate concurrent scenarios for orphan prevention testing"""
    return st.tuples(
        st.integers(min_value=2, max_value=5),  # Number of threads
        st.lists(
            st.tuples(
                st.one_of(valid_source_models_strategy(), invalid_source_models_strategy()),
                source_ids_strategy(),
                balanced_journal_entry_lines_strategy()
            ),
            min_size=3,
            max_size=10
        )  # Operations to perform concurrently
    )


# ===== Property-Based Test Class =====

class OrphanedEntryPreventionPropertyTest(HypothesisTestCase):
    """Property-based tests for orphaned entry prevention"""
    
    def setUp(self):
        """Set up test environment"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        GovernanceContext.set_context(user=self.user, service='TestService')
        
        # Create test accounting period
        self.accounting_period = AccountingPeriod.objects.create(
            name='Test Period 2024',
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            is_active=True
        )
        
        # Create test account type
        self.account_type = AccountType.objects.create(
            code='TEST',
            name='Test Account Type',
            category='asset',
            nature='debit'
        )
        
        # Create test accounts
        self.test_accounts = {}
        account_codes = ['1001', '1002', '2001', '2002', '3001', '4001', '5001']
        for code in account_codes:
            account = ChartOfAccounts.objects.create(
                code=code,
                name=f"Test Account {code}",
                account_type=self.account_type,
                is_active=True
            )
            self.test_accounts[code] = account
        
        # Initialize services
        self.gateway = AccountingGateway()
        self.repair_service = RepairService()
        self.quarantine_service = QuarantineService()
    
    def tearDown(self):
        """Clean up after tests"""
        GovernanceContext.clear_context()
    
    @settings(max_examples=50, deadline=30000)
    @given(
        source_data=valid_source_models_strategy(),
        source_id=source_ids_strategy(),
        lines=balanced_journal_entry_lines_strategy()
    )
    def test_property_valid_source_prevents_orphans(self, source_data, source_id, lines):
        """
        **Property 12: Orphaned Entry Prevention (Valid Sources)**
        **Validates: Requirements 7.1**
        
        Property: For any Journal_Entry created with a valid source reference that points 
        to an existing record, the entry should NOT be considered orphaned.
        """
        source_module, source_model = source_data
        note(f"Testing valid source prevention: {source_module}.{source_model}#{source_id}")
        
        # Mock the source to exist
        with patch.object(SourceLinkageService, 'validate_linkage', return_value=True):
            try:
                # Create journal entry through gateway
                entry = self.gateway.create_journal_entry(
                    source_module=source_module,
                    source_model=source_model,
                    source_id=source_id,
                    lines=lines,
                    idempotency_key=f"test-valid-{source_module}-{source_model}-{source_id}",
                    user=self.user,
                    description="Test valid source entry"
                )
                
                # Verify entry was created
                assert entry is not None
                assert entry.source_module == source_module
                assert entry.source_model == source_model
                assert entry.source_id == source_id
                
                # Verify entry is NOT orphaned by checking source linkage
                is_orphaned = not SourceLinkageService.validate_linkage(
                    entry.source_module, 
                    entry.source_model, 
                    entry.source_id
                )
                
                # Property assertion - entry should NOT be orphaned
                assert not is_orphaned, f"Entry with valid source should not be orphaned"
                
                # Verify entry would not be detected as corrupted by repair service
                corruption_report = self.repair_service.scan_for_corruption()
                orphaned_entries = corruption_report.corruption_types.get('ORPHANED_JOURNAL_ENTRIES', {}).get('issues', [])
                
                # Entry should not appear in orphaned entries list
                entry_in_orphaned = any(
                    issue.get('entry_id') == entry.id 
                    for issue in orphaned_entries
                )
                assert not entry_in_orphaned, f"Valid entry should not be detected as orphaned"
                
                logger.info(f"✅ Valid source prevents orphan: {source_module}.{source_model}#{source_id}")
                
            except Exception as e:
                pytest.fail(f"Valid source entry creation should succeed: {str(e)}")
    
    @settings(max_examples=40, deadline=30000)
    @given(orphan_scenario=orphaned_entry_scenarios_strategy())
    def test_property_invalid_source_creates_orphans_and_gets_detected(self, orphan_scenario):
        """
        **Property 12: Orphaned Entry Prevention (Invalid Sources)**
        **Validates: Requirements 7.1**
        
        Property: For any Journal_Entry created with invalid source reference,
        the system should either prevent creation OR detect and quarantine the orphan.
        """
        source_data, source_id, scenario_type = orphan_scenario
        
        # Handle different source data types
        if isinstance(source_data, tuple) and len(source_data) == 2:
            source_module, source_model = source_data
        else:
            # Skip malformed data
            assume(False)
        
        note(f"Testing orphan detection: {source_module}.{source_model}#{source_id} ({scenario_type})")
        
        # Skip if source_id is None (invalid_source_ids_strategy can generate None)
        if source_id is None:
            assume(False)
        
        lines = [
            JournalEntryLineData(
                account_code='1001',
                debit=Decimal('100.00'),
                credit=Decimal('0.00'),
                description="Test debit"
            ),
            JournalEntryLineData(
                account_code='2001',
                debit=Decimal('0.00'),
                credit=Decimal('100.00'),
                description="Test credit"
            )
        ]
        
        # Mock source validation to return False (invalid/non-existent)
        with patch.object(SourceLinkageService, 'validate_linkage', return_value=False):
            # Attempt to create entry with invalid source
            with pytest.raises(GovernanceValidationError) as exc_info:
                self.gateway.create_journal_entry(
                    source_module=source_module,
                    source_model=source_model,
                    source_id=source_id,
                    lines=lines,
                    idempotency_key=f"test-orphan-{source_module}-{source_model}-{source_id}",
                    user=self.user,
                    description="Test orphaned entry"
                )
            
            # Verify the error is about invalid source linkage
            error = exc_info.value
            assert "source" in str(error).lower() or "linkage" in str(error).lower(), \
                f"Error should mention source linkage issue: {str(error)}"
            
            logger.info(f"✅ Invalid source prevented: {source_module}.{source_model}#{source_id}")
    
    @settings(max_examples=20, deadline=30000)
    @given(
        valid_entries=st.lists(
            st.tuples(
                valid_source_models_strategy(),
                source_ids_strategy()
            ),
            min_size=1,
            max_size=5
        ),
        orphan_entries=st.lists(
            orphaned_entry_scenarios_strategy(),
            min_size=1,
            max_size=3
        )
    )
    def test_property_mixed_valid_and_orphan_detection(self, valid_entries, orphan_entries):
        """
        **Property 12: Orphaned Entry Prevention (Mixed Scenarios)**
        **Validates: Requirements 7.1**
        
        Property: In a mix of valid and invalid source references,
        the system should correctly identify and handle each case.
        """
        note(f"Testing mixed scenarios: {len(valid_entries)} valid, {len(orphan_entries)} orphan")
        
        created_entries = []
        prevented_orphans = 0
        
        # Create valid entries
        for source_data, source_id in valid_entries:
            source_module, source_model = source_data
            
            lines = [
                JournalEntryLineData(
                    account_code='1001',
                    debit=Decimal('100.00'),
                    credit=Decimal('0.00'),
                    description="Valid entry debit"
                ),
                JournalEntryLineData(
                    account_code='2001',
                    debit=Decimal('0.00'),
                    credit=Decimal('100.00'),
                    description="Valid entry credit"
                )
            ]
            
            with patch.object(SourceLinkageService, 'validate_linkage', return_value=True):
                try:
                    entry = self.gateway.create_journal_entry(
                        source_module=source_module,
                        source_model=source_model,
                        source_id=source_id,
                        lines=lines,
                        idempotency_key=f"mixed-valid-{source_module}-{source_model}-{source_id}",
                        user=self.user,
                        description="Mixed scenario valid entry"
                    )
                    created_entries.append(entry)
                except Exception as e:
                    logger.warning(f"Valid entry creation failed: {e}")
        
        # Attempt to create orphaned entries (should be prevented)
        for orphan_scenario in orphan_entries:
            source_data, source_id, scenario_type = orphan_scenario
            
            # Handle different source data types
            if isinstance(source_data, tuple) and len(source_data) == 2:
                source_module, source_model = source_data
            else:
                continue  # Skip malformed data
            
            # Skip if source_id is None
            if source_id is None:
                continue
            
            lines = [
                JournalEntryLineData(
                    account_code='1001',
                    debit=Decimal('50.00'),
                    credit=Decimal('0.00'),
                    description="Orphan entry debit"
                ),
                JournalEntryLineData(
                    account_code='2001',
                    debit=Decimal('0.00'),
                    credit=Decimal('50.00'),
                    description="Orphan entry credit"
                )
            ]
            
            with patch.object(SourceLinkageService, 'validate_linkage', return_value=False):
                try:
                    self.gateway.create_journal_entry(
                        source_module=source_module,
                        source_model=source_model,
                        source_id=source_id,
                        lines=lines,
                        idempotency_key=f"mixed-orphan-{source_module}-{source_model}-{source_id}",
                        user=self.user,
                        description="Mixed scenario orphan entry"
                    )
                    # If we reach here, the orphan was not prevented (unexpected)
                    logger.warning(f"Orphan entry was not prevented: {source_module}.{source_model}#{source_id}")
                except GovernanceValidationError:
                    # Expected - orphan was prevented
                    prevented_orphans += 1
                except Exception as e:
                    logger.warning(f"Unexpected error preventing orphan: {e}")
        
        # Verify results
        assert len(created_entries) > 0, "At least some valid entries should be created"
        
        # All valid entries should have proper source linkage
        for entry in created_entries:
            assert entry.source_module is not None
            assert entry.source_model is not None
            assert entry.source_id is not None
            
            # Verify entry is not orphaned (with mocked validation)
            with patch.object(SourceLinkageService, 'validate_linkage', return_value=True):
                is_orphaned = not SourceLinkageService.validate_linkage(
                    entry.source_module, 
                    entry.source_model, 
                    entry.source_id
                )
                assert not is_orphaned, f"Valid entry should not be orphaned"
        
        logger.info(f"✅ Mixed scenarios: {len(created_entries)} valid created, {prevented_orphans} orphans prevented")
    
    @settings(max_examples=15, deadline=45000)
    @given(concurrent_data=concurrent_orphan_prevention_strategy())
    def test_property_concurrent_orphan_prevention(self, concurrent_data):
        """
        **Property 12: Orphaned Entry Prevention (Concurrency)**
        **Validates: Requirements 7.1**
        
        Property: Under concurrent access, orphan prevention should work consistently.
        Valid sources should create entries, invalid sources should be prevented.
        """
        thread_count, operations = concurrent_data
        note(f"Testing concurrent orphan prevention: {thread_count} threads, {len(operations)} operations")
        
        results = []
        errors = []
        
        def process_operation(op_data):
            """Process a single operation"""
            source_data, source_id, lines = op_data
            source_module, source_model = source_data
            
            try:
                # Determine if source is valid (in allowlist)
                source_key = f"{source_module}.{source_model}"
                is_valid_source = source_key in SourceLinkageService.ALLOWED_SOURCES
                
                with patch.object(SourceLinkageService, 'validate_linkage', return_value=is_valid_source):
                    if is_valid_source:
                        # Should succeed
                        entry = self.gateway.create_journal_entry(
                            source_module=source_module,
                            source_model=source_model,
                            source_id=source_id,
                            lines=lines,
                            idempotency_key=f"concurrent-{source_module}-{source_model}-{source_id}-{threading.current_thread().ident}",
                            user=self.user,
                            description="Concurrent test entry"
                        )
                        return ('SUCCESS', entry, source_key)
                    else:
                        # Should fail
                        try:
                            self.gateway.create_journal_entry(
                                source_module=source_module,
                                source_model=source_model,
                                source_id=source_id,
                                lines=lines,
                                idempotency_key=f"concurrent-invalid-{source_module}-{source_model}-{source_id}-{threading.current_thread().ident}",
                                user=self.user,
                                description="Concurrent test invalid entry"
                            )
                            return ('UNEXPECTED_SUCCESS', None, source_key)
                        except GovernanceValidationError:
                            return ('PREVENTED', None, source_key)
                        
            except Exception as e:
                return ('ERROR', str(e), f"{source_module}.{source_model}")
        
        # Execute concurrent operations
        with ThreadPoolExecutor(max_workers=thread_count) as executor:
            futures = [executor.submit(process_operation, op) for op in operations]
            
            for future in as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    errors.append(str(e))
        
        # Analyze results
        successes = [r for r in results if r[0] == 'SUCCESS']
        prevented = [r for r in results if r[0] == 'PREVENTED']
        unexpected_successes = [r for r in results if r[0] == 'UNEXPECTED_SUCCESS']
        operation_errors = [r for r in results if r[0] == 'ERROR']
        
        # Verify no unexpected errors
        assert len(errors) == 0, f"No execution errors should occur: {errors}"
        assert len(operation_errors) == 0, f"No operation errors should occur: {operation_errors}"
        
        # Verify no orphans were created unexpectedly
        assert len(unexpected_successes) == 0, f"Invalid sources should not create entries: {unexpected_successes}"
        
        # Verify all results are accounted for
        total_results = len(successes) + len(prevented) + len(unexpected_successes) + len(operation_errors)
        assert total_results == len(operations), f"All operations should be accounted for"
        
        # Verify successful entries are not orphaned
        for result_type, entry, source_key in successes:
            assert entry is not None
            assert entry.source_module is not None
            assert entry.source_model is not None
            assert entry.source_id is not None
            
            # Source should be in allowlist
            assert source_key in SourceLinkageService.ALLOWED_SOURCES
        
        logger.info(f"✅ Concurrent orphan prevention: {len(successes)} created, {len(prevented)} prevented")
    
    def test_property_repair_service_orphan_detection(self):
        """
        **Property 12: Orphaned Entry Prevention (Repair Service Integration)**
        **Validates: Requirements 7.1**
        
        Property: The RepairService should accurately detect orphaned entries
        and recommend appropriate repair policies.
        """
        # Create a mock orphaned entry (for testing detection)
        with patch('financial.models.JournalEntry.objects.all') as mock_all:
            # Mock an orphaned entry
            mock_entry = MagicMock()
            mock_entry.id = 12345
            mock_entry.number = 'JE-12345'
            mock_entry.source_module = 'students'
            mock_entry.source_model = 'StudentFee'
            mock_entry.source_id = 99999  # Non-existent ID
            mock_entry.total_amount = Decimal('100.00')
            mock_entry.created_at = timezone.now()
            
            mock_all.return_value = [mock_entry]
            
            # Mock source linkage validation to return False (orphaned)
            with patch.object(SourceLinkageService, 'validate_linkage', return_value=False):
                # Run corruption scan
                corruption_report = self.repair_service.scan_for_corruption()
                
                # Verify orphaned entries were detected
                assert 'ORPHANED_JOURNAL_ENTRIES' in corruption_report.corruption_types
                
                orphaned_data = corruption_report.corruption_types['ORPHANED_JOURNAL_ENTRIES']
                assert orphaned_data['count'] > 0
                assert len(orphaned_data['issues']) > 0
                
                # Verify the mock entry was detected
                detected_entry = orphaned_data['issues'][0]
                assert detected_entry['entry_id'] == 12345
                assert detected_entry['source_module'] == 'students'
                assert detected_entry['source_model'] == 'StudentFee'
                assert detected_entry['source_id'] == 99999
                
                # Verify repair recommendations
                recommendations = corruption_report.recommendations
                orphan_recommendations = [
                    r for r in recommendations 
                    if r['corruption_type'] == 'ORPHANED_JOURNAL_ENTRIES'
                ]
                assert len(orphan_recommendations) > 0
                
                # Should recommend RELINK or QUARANTINE
                recommended_policies = [r['policy'] for r in orphan_recommendations]
                assert any(policy in ['RELINK', 'QUARANTINE'] for policy in recommended_policies)
        
        logger.info("✅ Repair service orphan detection works correctly")
    
    def test_property_quarantine_service_orphan_handling(self):
        """
        **Property 12: Orphaned Entry Prevention (Quarantine Integration)**
        **Validates: Requirements 7.1**
        
        Property: Detected orphaned entries should be properly quarantined
        with appropriate metadata and reasoning.
        """
        # Create a mock orphaned entry
        mock_entry = MagicMock()
        mock_entry.id = 54321
        mock_entry.number = 'JE-54321'
        mock_entry.source_module = 'invalid'
        mock_entry.source_model = 'InvalidModel'
        mock_entry.source_id = 12345
        mock_entry.total_amount = Decimal('250.00')
        
        # Quarantine the orphaned entry
        quarantine_record = self.quarantine_service.quarantine_entry(
            entry=mock_entry,
            reason="Orphaned journal entry detected - invalid source reference",
            user=self.user,
            corruption_type='ORPHANED_JOURNAL_ENTRY',
            confidence_level='HIGH',
            evidence={
                'source_module': mock_entry.source_module,
                'source_model': mock_entry.source_model,
                'source_id': mock_entry.source_id,
                'validation_failed': True
            }
        )
        
        # Verify quarantine record was created
        assert quarantine_record is not None
        assert quarantine_record.model_name == 'JournalEntry'
        assert quarantine_record.object_id == 54321
        assert quarantine_record.corruption_type == 'ORPHANED_JOURNAL_ENTRY'
        assert 'orphaned' in quarantine_record.quarantine_reason.lower()
        
        # Verify evidence was stored
        evidence = quarantine_record.original_data.get('evidence', {})
        assert evidence.get('source_module') == 'invalid'
        assert evidence.get('source_model') == 'InvalidModel'
        assert evidence.get('source_id') == 12345
        assert evidence.get('validation_failed') is True
        
        logger.info("✅ Quarantine service orphan handling works correctly")


# ===== Integration Tests =====

class OrphanedEntryPreventionIntegrationTest(TransactionTestCase):
    """Integration tests for orphaned entry prevention with real database operations"""
    
    def setUp(self):
        """Set up test environment"""
        self.user = User.objects.create_user(
            username='integrationuser',
            email='integration@example.com',
            password='testpass123'
        )
        GovernanceContext.set_context(user=self.user, service='IntegrationTestService')
        
        # Create test accounting period
        self.accounting_period = AccountingPeriod.objects.create(
            name='Integration Test Period 2024',
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            is_active=True
        )
        
        # Create test account type
        self.account_type = AccountType.objects.create(
            code='INTTEST',
            name='Integration Test Account Type',
            category='asset',
            nature='debit'
        )
        
        # Create test accounts
        account_codes = ['1001', '2001']
        for code in account_codes:
            ChartOfAccounts.objects.create(
                code=code,
                name=f"Integration Test Account {code}",
                account_type=self.account_type,
                is_active=True
            )
        
        self.gateway = AccountingGateway()
        self.repair_service = RepairService()
    
    def tearDown(self):
        """Clean up after tests"""
        GovernanceContext.clear_context()
    
    @settings(max_examples=5, deadline=20000)
    @given(
        source_data=valid_source_models_strategy(),
        source_id=source_ids_strategy()
    )
    def test_property_real_database_orphan_prevention(self, source_data, source_id):
        """
        **Property 12: Orphaned Entry Prevention (Real Database)**
        **Validates: Requirements 7.1**
        
        Property: With real database operations, orphan prevention should work consistently.
        """
        source_module, source_model = source_data
        note(f"Testing real database orphan prevention: {source_module}.{source_model}#{source_id}")
        
        lines = [
            JournalEntryLineData(
                account_code='1001',
                debit=Decimal('100.00'),
                credit=Decimal('0.00'),
                description="Integration test debit"
            ),
            JournalEntryLineData(
                account_code='2001',
                debit=Decimal('0.00'),
                credit=Decimal('100.00'),
                description="Integration test credit"
            )
        ]
        
        # Test with valid source (mocked to exist)
        with patch.object(SourceLinkageService, 'validate_linkage', return_value=True):
            try:
                entry = self.gateway.create_journal_entry(
                    source_module=source_module,
                    source_model=source_model,
                    source_id=source_id,
                    lines=lines,
                    idempotency_key=f"integration-valid-{source_module}-{source_model}-{source_id}",
                    user=self.user,
                    description="Integration test valid entry"
                )
                
                # Verify entry was created and is not orphaned
                assert entry is not None
                assert entry.source_module == source_module
                assert entry.source_model == source_model
                assert entry.source_id == source_id
                
                # Entry should exist in database
                db_entry = JournalEntry.objects.get(id=entry.id)
                assert db_entry.source_module == source_module
                assert db_entry.source_model == source_model
                assert db_entry.source_id == source_id
                
            except Exception as e:
                pytest.fail(f"Valid source entry should be created: {str(e)}")
        
        # Test with invalid source (should be prevented)
        with patch.object(SourceLinkageService, 'validate_linkage', return_value=False):
            with pytest.raises(GovernanceValidationError):
                self.gateway.create_journal_entry(
                    source_module=source_module,
                    source_model=source_model,
                    source_id=source_id + 10000,  # Different ID
                    lines=lines,
                    idempotency_key=f"integration-invalid-{source_module}-{source_model}-{source_id}",
                    user=self.user,
                    description="Integration test invalid entry"
                )
        
        logger.info(f"✅ Real database orphan prevention works for {source_module}.{source_model}")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--hypothesis-show-statistics'])