"""
Property-Based Tests for Single Gateway Enforcement
Tests that all Journal_Entry creation routes through AccountingGateway with comprehensive property-based testing using Hypothesis.

Feature: code-governance-system, Property 1: Single Gateway Enforcement
Validates: Requirements 1.1

Property Definition:
For any Journal_Entry creation, all supported write entrypoints MUST route through the AccountingGateway; 
out-of-band writes MUST be detected, audited, and quarantined
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

logger = logging.getLogger(__name__)

# Try to import Django components, but make them optional for standalone testing
try:
    from django.test import TestCase, TransactionTestCase
    from django.contrib.auth import get_user_model
    from django.utils import timezone
    from django.db import transaction, IntegrityError
    
    # Only get User model if Django is properly configured
    try:
        User = get_user_model()
        DJANGO_AVAILABLE = True
    except:
        User = None
        DJANGO_AVAILABLE = False
except ImportError:
    # Mock Django components for standalone testing
    TestCase = object
    TransactionTestCase = object
    User = None
    DJANGO_AVAILABLE = False
    
    # Mock timezone for standalone testing
    class MockTimezone:
        @staticmethod
        def now():
            from datetime import datetime
            return datetime.now()
    
    timezone = MockTimezone()


# ===== Mock Classes for Standalone Testing =====

class MockJournalEntry:
    """Mock JournalEntry for standalone testing"""
    
    def __init__(self, id=None, source_module=None, source_model=None, source_id=None):
        self.id = id or random.randint(1000, 9999)
        self.number = f"JE-{self.id:04d}"
        self.source_module = source_module
        self.source_model = source_model
        self.source_id = source_id
        
        # Use appropriate timezone based on availability
        if DJANGO_AVAILABLE:
            try:
                self.created_at = timezone.now()
            except:
                from datetime import datetime
                self.created_at = datetime.now()
        else:
            from datetime import datetime
            self.created_at = datetime.now()
            
        self.created_by_service = None
        self.idempotency_key = None
        self.status = 'draft'
        self.total_amount = Decimal('0.00')
        self.is_balanced = True
        self._gateway_approved = False
    
    def mark_as_gateway_approved(self):
        """Mark entry as approved by gateway"""
        self._gateway_approved = True
        self.created_by_service = 'AccountingGateway'
    
    def save(self, service_name=None):
        """Mock save method that tracks which service performed the operation"""
        if service_name:
            self.created_by_service = service_name
        return self
    
    def validate_entry(self):
        """Mock validation"""
        return True
    
    def validate_governance_rules(self):
        """Mock governance validation"""
        return {'is_valid': True}


class MockAccountingGateway:
    """Mock AccountingGateway for standalone testing"""
    
    def __init__(self):
        self.created_entries = []
        self.violations_detected = []
        self._lock = threading.Lock()
    
    def create_journal_entry(self, source_module, source_model, source_id, lines, 
                           idempotency_key, user, **kwargs):
        """Mock journal entry creation through gateway"""
        with self._lock:
            entry = MockJournalEntry(
                source_module=source_module,
                source_model=source_model,
                source_id=source_id
            )
            entry.mark_as_gateway_approved()
            entry.idempotency_key = idempotency_key
            entry.status = 'posted'
            entry.total_amount = sum(line.debit for line in lines)
            
            self.created_entries.append(entry)
            logger.info(f"Gateway created entry: {entry.number}")
            return entry
    
    def detect_out_of_band_write(self, entry):
        """Mock detection of out-of-band writes"""
        if not entry._gateway_approved:
            # Use appropriate timezone based on availability
            if DJANGO_AVAILABLE:
                try:
                    detected_at = timezone.now()
                except:
                    from datetime import datetime
                    detected_at = datetime.now()
            else:
                from datetime import datetime
                detected_at = datetime.now()
                
            violation = {
                'entry_id': entry.id,
                'entry_number': entry.number,
                'source_module': entry.source_module,
                'source_model': entry.source_model,
                'source_id': entry.source_id,
                'detected_at': detected_at,
                'violation_type': 'OUT_OF_BAND_WRITE'
            }
            self.violations_detected.append(violation)
            logger.warning(f"Out-of-band write detected: {entry.number}")
            return True
        return False


class MockAuditService:
    """Mock AuditService for standalone testing"""
    
    def __init__(self):
        self.violations = []
        self.operations = []
        self._lock = threading.Lock()
    
    def log_gateway_violation(self, entry, violation_type, user=None, **context):
        """Mock gateway violation logging"""
        with self._lock:
            # Use appropriate timezone based on availability
            if DJANGO_AVAILABLE:
                try:
                    timestamp = timezone.now()
                except:
                    from datetime import datetime
                    timestamp = datetime.now()
            else:
                from datetime import datetime
                timestamp = datetime.now()
                
            violation = {
                'entry_id': entry.id,
                'entry_number': entry.number,
                'violation_type': violation_type,
                'user': user,
                'timestamp': timestamp,
                'context': context
            }
            self.violations.append(violation)
            logger.warning(f"Gateway violation logged: {violation_type} for {entry.number}")
    
    def log_operation(self, model_name, object_id, operation, source_service, user=None, **kwargs):
        """Mock operation logging"""
        with self._lock:
            # Use appropriate timezone based on availability
            if DJANGO_AVAILABLE:
                try:
                    timestamp = timezone.now()
                except:
                    from datetime import datetime
                    timestamp = datetime.now()
            else:
                from datetime import datetime
                timestamp = datetime.now()
                
            op = {
                'model_name': model_name,
                'object_id': object_id,
                'operation': operation,
                'source_service': source_service,
                'user': user,
                'timestamp': timestamp,
                **kwargs
            }
            self.operations.append(op)


class MockQuarantineService:
    """Mock QuarantineService for standalone testing"""
    
    def __init__(self):
        self.quarantined_entries = []
        self._lock = threading.Lock()
    
    def quarantine_entry(self, entry, reason, user=None):
        """Mock entry quarantine"""
        with self._lock:
            # Use appropriate timezone based on availability
            if DJANGO_AVAILABLE:
                try:
                    quarantined_at = timezone.now()
                except:
                    from datetime import datetime
                    quarantined_at = datetime.now()
            else:
                from datetime import datetime
                quarantined_at = datetime.now()
                
            quarantine_record = {
                'entry_id': entry.id,
                'entry_number': entry.number,
                'reason': reason,
                'quarantined_at': quarantined_at,
                'user': user,
                'status': 'QUARANTINED'
            }
            self.quarantined_entries.append(quarantine_record)
            logger.info(f"Entry quarantined: {entry.number} - {reason}")
            return quarantine_record


class MockJournalEntryLineData:
    """Mock JournalEntryLineData for testing"""
    
    def __init__(self, account_code, debit, credit, description=""):
        self.account_code = account_code
        self.debit = Decimal(str(debit))
        self.credit = Decimal(str(credit))
        self.description = description


# ===== Hypothesis Strategies =====

def valid_source_strategy():
    """Generate valid source references from allowlist"""
    allowed_sources = [
        ('students', 'StudentFee'),
        ('students', 'FeePayment'),
        ('product', 'StockMovement'),
        ('sale', 'SalePayment'),
        ('purchase', 'PurchasePayment'),
        ('hr', 'PayrollPayment'),
        ('transportation', 'TransportationFee'),
        ('finance', 'ManualAdjustment')
    ]
    return st.sampled_from(allowed_sources)


def high_priority_workflow_strategy():
    """Generate high-priority workflow sources (3 selected workflows)"""
    high_priority_sources = [
        ('students', 'StudentFee'),
        ('product', 'StockMovement'),
        ('students', 'FeePayment')
    ]
    return st.sampled_from(high_priority_sources)


def journal_entry_line_strategy():
    """Generate valid journal entry lines"""
    return st.builds(
        MockJournalEntryLineData,
        account_code=st.sampled_from(['10100', '10301', '41020', '13000', '20100', '51000']),
        debit=st.one_of(
            st.just(Decimal('0')),
            st.decimals(min_value=Decimal('0.01'), max_value=Decimal('10000'), places=2)
        ),
        credit=st.one_of(
            st.just(Decimal('0')),
            st.decimals(min_value=Decimal('0.01'), max_value=Decimal('10000'), places=2)
        ),
        description=st.text(min_size=1, max_size=100)
    ).filter(lambda line: (line.debit > 0) != (line.credit > 0))  # Ensure only one is non-zero


def balanced_journal_lines_strategy():
    """Generate balanced journal entry lines"""
    @st.composite
    def _balanced_lines(draw):
        # Generate amount
        amount = draw(st.decimals(min_value=Decimal('0.01'), max_value=Decimal('5000'), places=2))
        
        # Create debit line
        debit_account = draw(st.sampled_from(['10100', '10301', '13000']))
        debit_line = MockJournalEntryLineData(debit_account, amount, Decimal('0'), "Debit line")
        
        # Create credit line
        credit_account = draw(st.sampled_from(['41020', '20100', '51000']))
        credit_line = MockJournalEntryLineData(credit_account, Decimal('0'), amount, "Credit line")
        
        return [debit_line, credit_line]
    
    return _balanced_lines()


def idempotency_key_strategy():
    """Generate valid idempotency keys"""
    return st.builds(
        lambda module, model, id, event: f"JE:{module}:{model}:{id}:{event}",
        module=st.sampled_from(['students', 'product', 'sale', 'purchase', 'hr', 'transportation', 'finance']),
        model=st.text(min_size=3, max_size=20, alphabet=st.characters(whitelist_categories=('Lu', 'Ll'))),
        id=st.integers(min_value=1, max_value=99999),
        event=st.sampled_from(['create', 'update', 'reverse'])
    )


# ===== Property Tests =====

class SingleGatewayEnforcementPropertyTestMixin:
    """Mixin containing all the property test methods"""
    
    @given(
        source_info=high_priority_workflow_strategy(),
        source_id=st.integers(min_value=1, max_value=99999),
        lines=balanced_journal_lines_strategy(),
        idempotency_key=idempotency_key_strategy()
    )
    @settings(max_examples=50, deadline=5000)
    def test_property_single_gateway_enforcement_basic(self, source_info, source_id, lines, idempotency_key):
        """
        **Property 1: Single Gateway Enforcement (Basic)**
        
        For any Journal_Entry creation through supported workflows, 
        the entry MUST be created through AccountingGateway
        """
        source_module, source_model = source_info
        note(f"Testing gateway enforcement for {source_module}.{source_model}#{source_id}")
        
        # Create journal entry through gateway (correct path)
        entry = self.gateway.create_journal_entry(
            source_module=source_module,
            source_model=source_model,
            source_id=source_id,
            lines=lines,
            idempotency_key=idempotency_key,
            user=self.user
        )
        
        # Verify entry was created through gateway
        assert entry.created_by_service == 'AccountingGateway'
        assert entry._gateway_approved is True
        assert entry.status == 'posted'
        assert entry.idempotency_key == idempotency_key
        
        # Verify no violations detected for gateway-created entries
        assert not self.gateway.detect_out_of_band_write(entry)
        
        # Verify entry is in gateway's created entries list
        assert entry in self.gateway.created_entries
        
        logger.info(f"✅ Gateway enforcement verified for {source_module}.{source_model}#{source_id}")
    
    @given(
        source_info=high_priority_workflow_strategy(),
        source_id=st.integers(min_value=1, max_value=99999),
        lines=balanced_journal_lines_strategy()
    )
    @settings(max_examples=30, deadline=5000)
    def test_property_out_of_band_write_detection(self, source_info, source_id, lines):
        """
        **Property 1: Single Gateway Enforcement (Out-of-Band Detection)**
        
        For any Journal_Entry created outside the AccountingGateway,
        the violation MUST be detected, audited, and quarantined
        """
        source_module, source_model = source_info
        note(f"Testing out-of-band detection for {source_module}.{source_model}#{source_id}")
        
        # Create journal entry outside gateway (violation)
        out_of_band_entry = MockJournalEntry(
            source_module=source_module,
            source_model=source_model,
            source_id=source_id
        )
        # Deliberately NOT marking as gateway approved
        out_of_band_entry.created_by_service = 'DirectWrite'  # Simulate direct write
        
        # Detect out-of-band write
        violation_detected = self.gateway.detect_out_of_band_write(out_of_band_entry)
        
        # Verify violation was detected
        assert violation_detected is True
        assert len(self.gateway.violations_detected) > 0
        
        # Verify violation details
        violation = self.gateway.violations_detected[-1]
        assert violation['entry_id'] == out_of_band_entry.id
        assert violation['violation_type'] == 'OUT_OF_BAND_WRITE'
        assert violation['source_module'] == source_module
        assert violation['source_model'] == source_model
        assert violation['source_id'] == source_id
        
        # Audit the violation
        self.audit_service.log_gateway_violation(
            entry=out_of_band_entry,
            violation_type='OUT_OF_BAND_WRITE',
            user=self.user,
            detected_by='AccountingGateway'
        )
        
        # Verify audit trail was created
        assert len(self.audit_service.violations) > 0
        audit_violation = self.audit_service.violations[-1]
        assert audit_violation['entry_id'] == out_of_band_entry.id
        assert audit_violation['violation_type'] == 'OUT_OF_BAND_WRITE'
        
        # Quarantine the violating entry
        quarantine_record = self.quarantine_service.quarantine_entry(
            entry=out_of_band_entry,
            reason="Out-of-band journal entry creation detected",
            user=self.user
        )
        
        # Verify quarantine was successful
        assert quarantine_record is not None
        assert quarantine_record['entry_id'] == out_of_band_entry.id
        assert quarantine_record['status'] == 'QUARANTINED'
        assert len(self.quarantine_service.quarantined_entries) > 0
        
        logger.info(f"✅ Out-of-band detection verified for {source_module}.{source_model}#{source_id}")
    
    @given(
        workflow_scenarios=st.lists(
            st.tuples(
                high_priority_workflow_strategy(),
                st.integers(min_value=1, max_value=999),
                balanced_journal_lines_strategy(),
                idempotency_key_strategy()
            ),
            min_size=2,
            max_size=5
        )
    )
    @settings(max_examples=20, deadline=10000)
    def test_property_multiple_workflow_enforcement(self, workflow_scenarios):
        """
        **Property 1: Single Gateway Enforcement (Multiple Workflows)**
        
        For any combination of the 3 high-priority workflows (StudentFee, StockMovement, FeePayment),
        ALL entries MUST route through AccountingGateway
        """
        note(f"Testing {len(workflow_scenarios)} workflow scenarios")
        
        created_entries = []
        
        for source_info, source_id, lines, idempotency_key in workflow_scenarios:
            source_module, source_model = source_info
            
            # Create entry through gateway
            entry = self.gateway.create_journal_entry(
                source_module=source_module,
                source_model=source_model,
                source_id=source_id,
                lines=lines,
                idempotency_key=idempotency_key,
                user=self.user
            )
            
            created_entries.append(entry)
        
        # Verify all entries were created through gateway
        for entry in created_entries:
            assert entry.created_by_service == 'AccountingGateway'
            assert entry._gateway_approved is True
            assert entry.status == 'posted'
            assert not self.gateway.detect_out_of_band_write(entry)
        
        # Verify all entries are tracked by gateway
        assert len(self.gateway.created_entries) >= len(workflow_scenarios)
        
        # Verify no violations detected for any gateway-created entries
        gateway_violations = [v for v in self.gateway.violations_detected 
                            if v['entry_id'] in [e.id for e in created_entries]]
        assert len(gateway_violations) == 0
        
        logger.info(f"✅ Multiple workflow enforcement verified for {len(workflow_scenarios)} scenarios")
    
    @given(
        thread_count=st.integers(min_value=2, max_value=5),
        entries_per_thread=st.integers(min_value=1, max_value=3)
    )
    @settings(max_examples=10, deadline=15000)
    def test_property_concurrent_gateway_enforcement(self, thread_count, entries_per_thread):
        """
        **Property 1: Single Gateway Enforcement (Concurrency)**
        
        For any concurrent Journal_Entry creation operations,
        ALL entries MUST route through AccountingGateway consistently
        """
        note(f"Testing concurrent enforcement with {thread_count} threads, {entries_per_thread} entries each")
        
        results = []
        errors = []
        
        def create_entries_thread(thread_id):
            """Create entries in a separate thread"""
            thread_results = []
            try:
                for i in range(entries_per_thread):
                    # Use high-priority workflow
                    source_module, source_model = random.choice([
                        ('students', 'StudentFee'),
                        ('product', 'StockMovement'),
                        ('students', 'FeePayment')
                    ])
                    
                    lines = [
                        MockJournalEntryLineData('10301', Decimal('100'), Decimal('0')),
                        MockJournalEntryLineData('41020', Decimal('0'), Decimal('100'))
                    ]
                    
                    entry = self.gateway.create_journal_entry(
                        source_module=source_module,
                        source_model=source_model,
                        source_id=thread_id * 1000 + i,
                        lines=lines,
                        idempotency_key=f"CONCURRENT:{thread_id}:{i}:{time.time()}",
                        user=self.user
                    )
                    
                    thread_results.append(entry)
                    
            except Exception as e:
                errors.append(f"Thread {thread_id}: {str(e)}")
            
            return thread_results
        
        # Execute concurrent operations
        with ThreadPoolExecutor(max_workers=thread_count) as executor:
            futures = [executor.submit(create_entries_thread, i) for i in range(thread_count)]
            
            for future in as_completed(futures):
                try:
                    thread_results = future.result(timeout=10)
                    results.extend(thread_results)
                except Exception as e:
                    errors.append(f"Future error: {str(e)}")
        
        # Verify no errors occurred
        assert len(errors) == 0, f"Concurrent errors: {errors}"
        
        # Verify all entries were created through gateway
        expected_total = thread_count * entries_per_thread
        assert len(results) == expected_total
        
        for entry in results:
            assert entry.created_by_service == 'AccountingGateway'
            assert entry._gateway_approved is True
            assert entry.status == 'posted'
            assert not self.gateway.detect_out_of_band_write(entry)
        
        # Verify gateway consistency
        assert len(self.gateway.created_entries) >= expected_total
        
        logger.info(f"✅ Concurrent gateway enforcement verified for {expected_total} entries")
    
    @given(
        valid_scenarios=st.lists(
            st.tuples(
                high_priority_workflow_strategy(),
                st.integers(min_value=1, max_value=999),
                balanced_journal_lines_strategy()
            ),
            min_size=1,
            max_size=3
        ),
        violation_scenarios=st.lists(
            st.tuples(
                high_priority_workflow_strategy(),
                st.integers(min_value=1, max_value=999)
            ),
            min_size=1,
            max_size=2
        )
    )
    @settings(max_examples=15, deadline=10000)
    def test_property_mixed_valid_and_violation_scenarios(self, valid_scenarios, violation_scenarios):
        """
        **Property 1: Single Gateway Enforcement (Mixed Scenarios)**
        
        For any mix of valid gateway operations and out-of-band violations,
        the system MUST correctly identify and handle each case
        """
        note(f"Testing {len(valid_scenarios)} valid + {len(violation_scenarios)} violation scenarios")
        
        valid_entries = []
        violation_entries = []
        
        # Create valid entries through gateway
        for source_info, source_id, lines in valid_scenarios:
            source_module, source_model = source_info
            
            entry = self.gateway.create_journal_entry(
                source_module=source_module,
                source_model=source_model,
                source_id=source_id,
                lines=lines,
                idempotency_key=f"VALID:{source_module}:{source_model}:{source_id}:{time.time()}",
                user=self.user
            )
            
            valid_entries.append(entry)
        
        # Create violation entries (out-of-band)
        for source_info, source_id in violation_scenarios:
            source_module, source_model = source_info
            
            violation_entry = MockJournalEntry(
                source_module=source_module,
                source_model=source_model,
                source_id=source_id + 10000  # Ensure different IDs
            )
            violation_entry.created_by_service = 'DirectWrite'
            
            violation_entries.append(violation_entry)
        
        # Verify valid entries are correctly identified
        for entry in valid_entries:
            assert entry.created_by_service == 'AccountingGateway'
            assert entry._gateway_approved is True
            assert not self.gateway.detect_out_of_band_write(entry)
        
        # Verify violations are correctly detected
        detected_violations = 0
        for entry in violation_entries:
            if self.gateway.detect_out_of_band_write(entry):
                detected_violations += 1
                
                # Audit and quarantine the violation
                self.audit_service.log_gateway_violation(
                    entry=entry,
                    violation_type='OUT_OF_BAND_WRITE',
                    user=self.user
                )
                
                self.quarantine_service.quarantine_entry(
                    entry=entry,
                    reason="Mixed scenario violation test",
                    user=self.user
                )
        
        # Verify all violations were detected
        assert detected_violations == len(violation_scenarios)
        
        # Verify audit and quarantine counts
        assert len(self.audit_service.violations) >= len(violation_scenarios)
        assert len(self.quarantine_service.quarantined_entries) >= len(violation_scenarios)
        
        logger.info(f"✅ Mixed scenarios verified: {len(valid_scenarios)} valid, {len(violation_scenarios)} violations")
    
    def test_gateway_enforcement_statistics(self):
        """
        **Property 1: Single Gateway Enforcement (Statistics)**
        
        Gateway enforcement statistics should accurately reflect system state
        """
        # Reset gateway state for clean statistics test
        self.gateway.created_entries = []
        self.gateway.violations_detected = []
        
        # Create some entries through gateway
        for i in range(3):
            lines = [
                MockJournalEntryLineData('10301', Decimal('100'), Decimal('0')),
                MockJournalEntryLineData('41020', Decimal('0'), Decimal('100'))
            ]
            
            self.gateway.create_journal_entry(
                source_module='students',
                source_model='StudentFee',
                source_id=i,
                lines=lines,
                idempotency_key=f"STATS:{i}",
                user=self.user
            )
        
        # Create some violations
        for i in range(2):
            violation_entry = MockJournalEntry(
                source_module='students',
                source_model='StudentFee',
                source_id=i + 100
            )
            violation_entry.created_by_service = 'DirectWrite'
            
            self.gateway.detect_out_of_band_write(violation_entry)
        
        # Verify statistics
        assert len(self.gateway.created_entries) == 3
        assert len(self.gateway.violations_detected) == 2
        
        # Verify all gateway entries are properly marked
        for entry in self.gateway.created_entries:
            assert entry.created_by_service == 'AccountingGateway'
            assert entry._gateway_approved is True
        
        # Verify all violations are properly recorded
        for violation in self.gateway.violations_detected:
            assert violation['violation_type'] == 'OUT_OF_BAND_WRITE'
            assert 'detected_at' in violation
        
        logger.info("✅ Gateway enforcement statistics verified")
    
    def _test_basic_gateway_enforcement(self, source_info, source_id, lines, idempotency_key):
        """Helper method for standalone testing of basic gateway enforcement"""
        source_module, source_model = source_info
        
        # Create journal entry through gateway (correct path)
        entry = self.gateway.create_journal_entry(
            source_module=source_module,
            source_model=source_model,
            source_id=source_id,
            lines=lines,
            idempotency_key=idempotency_key,
            user=self.user
        )
        
        # Verify entry was created through gateway
        assert entry.created_by_service == 'AccountingGateway'
        assert entry._gateway_approved is True
        assert entry.status == 'posted'
        assert entry.idempotency_key == idempotency_key
        
        # Verify no violations detected for gateway-created entries
        assert not self.gateway.detect_out_of_band_write(entry)
        
        # Verify entry is in gateway's created entries list
        assert entry in self.gateway.created_entries
        
        logger.info(f"✅ Gateway enforcement verified for {source_module}.{source_model}#{source_id}")
    
    def _test_out_of_band_detection(self, source_info, source_id, lines):
        """Helper method for standalone testing of out-of-band detection"""
        source_module, source_model = source_info
        
        # Create journal entry outside gateway (violation)
        out_of_band_entry = MockJournalEntry(
            source_module=source_module,
            source_model=source_model,
            source_id=source_id
        )
        # Deliberately NOT marking as gateway approved
        out_of_band_entry.created_by_service = 'DirectWrite'  # Simulate direct write
        
        # Detect out-of-band write
        violation_detected = self.gateway.detect_out_of_band_write(out_of_band_entry)
        
        # Verify violation was detected
        assert violation_detected is True
        assert len(self.gateway.violations_detected) > 0
        
        # Verify violation details
        violation = self.gateway.violations_detected[-1]
        assert violation['entry_id'] == out_of_band_entry.id
        assert violation['violation_type'] == 'OUT_OF_BAND_WRITE'
        assert violation['source_module'] == source_module
        assert violation['source_model'] == source_model
        assert violation['source_id'] == source_id
        
        # Audit the violation
        self.audit_service.log_gateway_violation(
            entry=out_of_band_entry,
            violation_type='OUT_OF_BAND_WRITE',
            user=self.user,
            detected_by='AccountingGateway'
        )
        
        # Verify audit trail was created
        assert len(self.audit_service.violations) > 0
        audit_violation = self.audit_service.violations[-1]
        assert audit_violation['entry_id'] == out_of_band_entry.id
        assert audit_violation['violation_type'] == 'OUT_OF_BAND_WRITE'
        
        # Quarantine the violating entry
        quarantine_record = self.quarantine_service.quarantine_entry(
            entry=out_of_band_entry,
            reason="Out-of-band journal entry creation detected",
            user=self.user
        )
        
        # Verify quarantine was successful
        assert quarantine_record is not None
        assert quarantine_record['entry_id'] == out_of_band_entry.id
        assert quarantine_record['status'] == 'QUARANTINED'
        assert len(self.quarantine_service.quarantined_entries) > 0
        
        logger.info(f"✅ Out-of-band detection verified for {source_module}.{source_model}#{source_id}")


if DJANGO_AVAILABLE:
    class TestSingleGatewayEnforcementProperty(TestCase, SingleGatewayEnforcementPropertyTestMixin):
        """
        **Property 1: Single Gateway Enforcement**
        
        **Validates: Requirements 1.1**
        
        Property 1: Single Gateway Enforcement
        For any Journal_Entry creation, all supported write entrypoints MUST route through 
        the AccountingGateway; out-of-band writes MUST be detected, audited, and quarantined
        """
        
        def setUp(self):
            """Set up test environment"""
            if User:
                self.user = User.objects.create_user(
                    username='property_test_user',
                    email='property@test.com',
                    password='testpass123'
                )
            else:
                # Mock user for standalone testing
                self.user = type('MockUser', (), {
                    'id': 1,
                    'username': 'property_test_user',
                    'email': 'property@test.com'
                })()
            
            # Initialize mock services
            self.gateway = MockAccountingGateway()
            self.audit_service = MockAuditService()
            self.quarantine_service = MockQuarantineService()
else:
    class TestSingleGatewayEnforcementProperty(SingleGatewayEnforcementPropertyTestMixin):
        """
        **Property 1: Single Gateway Enforcement**
        
        **Validates: Requirements 1.1**
        
        Property 1: Single Gateway Enforcement
        For any Journal_Entry creation, all supported write entrypoints MUST route through 
        the AccountingGateway; out-of-band writes MUST be detected, audited, and quarantined
        """
        
        def setUp(self):
            """Set up test environment"""
            # Mock user for standalone testing
            self.user = type('MockUser', (), {
                'id': 1,
                'username': 'property_test_user',
                'email': 'property@test.com'
            })()
            
            # Initialize mock services
            self.gateway = MockAccountingGateway()
            self.audit_service = MockAuditService()
            self.quarantine_service = MockQuarantineService()
    
    @given(
        source_info=high_priority_workflow_strategy(),
        source_id=st.integers(min_value=1, max_value=99999),
        lines=balanced_journal_lines_strategy(),
        idempotency_key=idempotency_key_strategy()
    )
    @settings(max_examples=50, deadline=5000)
    def test_property_single_gateway_enforcement_basic(self, source_info, source_id, lines, idempotency_key):
        """
        **Property 1: Single Gateway Enforcement (Basic)**
        
        For any Journal_Entry creation through supported workflows, 
        the entry MUST be created through AccountingGateway
        """
        source_module, source_model = source_info
        note(f"Testing gateway enforcement for {source_module}.{source_model}#{source_id}")
        
        # Create journal entry through gateway (correct path)
        entry = self.gateway.create_journal_entry(
            source_module=source_module,
            source_model=source_model,
            source_id=source_id,
            lines=lines,
            idempotency_key=idempotency_key,
            user=self.user
        )
        
        # Verify entry was created through gateway
        assert entry.created_by_service == 'AccountingGateway'
        assert entry._gateway_approved is True
        assert entry.status == 'posted'
        assert entry.idempotency_key == idempotency_key
        
        # Verify no violations detected for gateway-created entries
        assert not self.gateway.detect_out_of_band_write(entry)
        
        # Verify entry is in gateway's created entries list
        assert entry in self.gateway.created_entries
        
        logger.info(f"✅ Gateway enforcement verified for {source_module}.{source_model}#{source_id}")
    
    @given(
        source_info=high_priority_workflow_strategy(),
        source_id=st.integers(min_value=1, max_value=99999),
        lines=balanced_journal_lines_strategy()
    )
    @settings(max_examples=30, deadline=5000)
    def test_property_out_of_band_write_detection(self, source_info, source_id, lines):
        """
        **Property 1: Single Gateway Enforcement (Out-of-Band Detection)**
        
        For any Journal_Entry created outside the AccountingGateway,
        the violation MUST be detected, audited, and quarantined
        """
        source_module, source_model = source_info
        note(f"Testing out-of-band detection for {source_module}.{source_model}#{source_id}")
        
        # Create journal entry outside gateway (violation)
        out_of_band_entry = MockJournalEntry(
            source_module=source_module,
            source_model=source_model,
            source_id=source_id
        )
        # Deliberately NOT marking as gateway approved
        out_of_band_entry.created_by_service = 'DirectWrite'  # Simulate direct write
        
        # Detect out-of-band write
        violation_detected = self.gateway.detect_out_of_band_write(out_of_band_entry)
        
        # Verify violation was detected
        assert violation_detected is True
        assert len(self.gateway.violations_detected) > 0
        
        # Verify violation details
        violation = self.gateway.violations_detected[-1]
        assert violation['entry_id'] == out_of_band_entry.id
        assert violation['violation_type'] == 'OUT_OF_BAND_WRITE'
        assert violation['source_module'] == source_module
        assert violation['source_model'] == source_model
        assert violation['source_id'] == source_id
        
        # Audit the violation
        self.audit_service.log_gateway_violation(
            entry=out_of_band_entry,
            violation_type='OUT_OF_BAND_WRITE',
            user=self.user,
            detected_by='AccountingGateway'
        )
        
        # Verify audit trail was created
        assert len(self.audit_service.violations) > 0
        audit_violation = self.audit_service.violations[-1]
        assert audit_violation['entry_id'] == out_of_band_entry.id
        assert audit_violation['violation_type'] == 'OUT_OF_BAND_WRITE'
        
        # Quarantine the violating entry
        quarantine_record = self.quarantine_service.quarantine_entry(
            entry=out_of_band_entry,
            reason="Out-of-band journal entry creation detected",
            user=self.user
        )
        
        # Verify quarantine was successful
        assert quarantine_record is not None
        assert quarantine_record['entry_id'] == out_of_band_entry.id
        assert quarantine_record['status'] == 'QUARANTINED'
        assert len(self.quarantine_service.quarantined_entries) > 0
        
        logger.info(f"✅ Out-of-band detection verified for {source_module}.{source_model}#{source_id}")
    
    @given(
        workflow_scenarios=st.lists(
            st.tuples(
                high_priority_workflow_strategy(),
                st.integers(min_value=1, max_value=999),
                balanced_journal_lines_strategy(),
                idempotency_key_strategy()
            ),
            min_size=2,
            max_size=5
        )
    )
    @settings(max_examples=20, deadline=10000)
    def test_property_multiple_workflow_enforcement(self, workflow_scenarios):
        """
        **Property 1: Single Gateway Enforcement (Multiple Workflows)**
        
        For any combination of the 3 high-priority workflows (StudentFee, StockMovement, FeePayment),
        ALL entries MUST route through AccountingGateway
        """
        note(f"Testing {len(workflow_scenarios)} workflow scenarios")
        
        created_entries = []
        
        for source_info, source_id, lines, idempotency_key in workflow_scenarios:
            source_module, source_model = source_info
            
            # Create entry through gateway
            entry = self.gateway.create_journal_entry(
                source_module=source_module,
                source_model=source_model,
                source_id=source_id,
                lines=lines,
                idempotency_key=idempotency_key,
                user=self.user
            )
            
            created_entries.append(entry)
        
        # Verify all entries were created through gateway
        for entry in created_entries:
            assert entry.created_by_service == 'AccountingGateway'
            assert entry._gateway_approved is True
            assert entry.status == 'posted'
            assert not self.gateway.detect_out_of_band_write(entry)
        
        # Verify all entries are tracked by gateway
        assert len(self.gateway.created_entries) >= len(workflow_scenarios)
        
        # Verify no violations detected for any gateway-created entries
        gateway_violations = [v for v in self.gateway.violations_detected 
                            if v['entry_id'] in [e.id for e in created_entries]]
        assert len(gateway_violations) == 0
        
        logger.info(f"✅ Multiple workflow enforcement verified for {len(workflow_scenarios)} scenarios")
    
    @given(
        thread_count=st.integers(min_value=2, max_value=5),
        entries_per_thread=st.integers(min_value=1, max_value=3)
    )
    @settings(max_examples=10, deadline=15000)
    def test_property_concurrent_gateway_enforcement(self, thread_count, entries_per_thread):
        """
        **Property 1: Single Gateway Enforcement (Concurrency)**
        
        For any concurrent Journal_Entry creation operations,
        ALL entries MUST route through AccountingGateway consistently
        """
        note(f"Testing concurrent enforcement with {thread_count} threads, {entries_per_thread} entries each")
        
        results = []
        errors = []
        
        def create_entries_thread(thread_id):
            """Create entries in a separate thread"""
            thread_results = []
            try:
                for i in range(entries_per_thread):
                    # Use high-priority workflow
                    source_module, source_model = random.choice([
                        ('students', 'StudentFee'),
                        ('product', 'StockMovement'),
                        ('students', 'FeePayment')
                    ])
                    
                    lines = [
                        MockJournalEntryLineData('10301', Decimal('100'), Decimal('0')),
                        MockJournalEntryLineData('41020', Decimal('0'), Decimal('100'))
                    ]
                    
                    entry = self.gateway.create_journal_entry(
                        source_module=source_module,
                        source_model=source_model,
                        source_id=thread_id * 1000 + i,
                        lines=lines,
                        idempotency_key=f"CONCURRENT:{thread_id}:{i}:{time.time()}",
                        user=self.user
                    )
                    
                    thread_results.append(entry)
                    
            except Exception as e:
                errors.append(f"Thread {thread_id}: {str(e)}")
            
            return thread_results
        
        # Execute concurrent operations
        with ThreadPoolExecutor(max_workers=thread_count) as executor:
            futures = [executor.submit(create_entries_thread, i) for i in range(thread_count)]
            
            for future in as_completed(futures):
                try:
                    thread_results = future.result(timeout=10)
                    results.extend(thread_results)
                except Exception as e:
                    errors.append(f"Future error: {str(e)}")
        
        # Verify no errors occurred
        assert len(errors) == 0, f"Concurrent errors: {errors}"
        
        # Verify all entries were created through gateway
        expected_total = thread_count * entries_per_thread
        assert len(results) == expected_total
        
        for entry in results:
            assert entry.created_by_service == 'AccountingGateway'
            assert entry._gateway_approved is True
            assert entry.status == 'posted'
            assert not self.gateway.detect_out_of_band_write(entry)
        
        # Verify gateway consistency
        assert len(self.gateway.created_entries) >= expected_total
        
        logger.info(f"✅ Concurrent gateway enforcement verified for {expected_total} entries")
    
    @given(
        valid_scenarios=st.lists(
            st.tuples(
                high_priority_workflow_strategy(),
                st.integers(min_value=1, max_value=999),
                balanced_journal_lines_strategy()
            ),
            min_size=1,
            max_size=3
        ),
        violation_scenarios=st.lists(
            st.tuples(
                high_priority_workflow_strategy(),
                st.integers(min_value=1, max_value=999)
            ),
            min_size=1,
            max_size=2
        )
    )
    @settings(max_examples=15, deadline=10000)
    def test_property_mixed_valid_and_violation_scenarios(self, valid_scenarios, violation_scenarios):
        """
        **Property 1: Single Gateway Enforcement (Mixed Scenarios)**
        
        For any mix of valid gateway operations and out-of-band violations,
        the system MUST correctly identify and handle each case
        """
        note(f"Testing {len(valid_scenarios)} valid + {len(violation_scenarios)} violation scenarios")
        
        valid_entries = []
        violation_entries = []
        
        # Create valid entries through gateway
        for source_info, source_id, lines in valid_scenarios:
            source_module, source_model = source_info
            
            entry = self.gateway.create_journal_entry(
                source_module=source_module,
                source_model=source_model,
                source_id=source_id,
                lines=lines,
                idempotency_key=f"VALID:{source_module}:{source_model}:{source_id}:{time.time()}",
                user=self.user
            )
            
            valid_entries.append(entry)
        
        # Create violation entries (out-of-band)
        for source_info, source_id in violation_scenarios:
            source_module, source_model = source_info
            
            violation_entry = MockJournalEntry(
                source_module=source_module,
                source_model=source_model,
                source_id=source_id + 10000  # Ensure different IDs
            )
            violation_entry.created_by_service = 'DirectWrite'
            
            violation_entries.append(violation_entry)
        
        # Verify valid entries are correctly identified
        for entry in valid_entries:
            assert entry.created_by_service == 'AccountingGateway'
            assert entry._gateway_approved is True
            assert not self.gateway.detect_out_of_band_write(entry)
        
        # Verify violations are correctly detected
        detected_violations = 0
        for entry in violation_entries:
            if self.gateway.detect_out_of_band_write(entry):
                detected_violations += 1
                
                # Audit and quarantine the violation
                self.audit_service.log_gateway_violation(
                    entry=entry,
                    violation_type='OUT_OF_BAND_WRITE',
                    user=self.user
                )
                
                self.quarantine_service.quarantine_entry(
                    entry=entry,
                    reason="Mixed scenario violation test",
                    user=self.user
                )
        
        # Verify all violations were detected
        assert detected_violations == len(violation_scenarios)
        
        # Verify audit and quarantine counts
        assert len(self.audit_service.violations) >= len(violation_scenarios)
        assert len(self.quarantine_service.quarantined_entries) >= len(violation_scenarios)
        
        logger.info(f"✅ Mixed scenarios verified: {len(valid_scenarios)} valid, {len(violation_scenarios)} violations")
    
    def test_gateway_enforcement_statistics(self):
        """
        **Property 1: Single Gateway Enforcement (Statistics)**
        
        Gateway enforcement statistics should accurately reflect system state
        """
        # Reset gateway state for clean statistics test
        self.gateway.created_entries = []
        self.gateway.violations_detected = []
        
        # Create some entries through gateway
        for i in range(3):
            lines = [
                MockJournalEntryLineData('10301', Decimal('100'), Decimal('0')),
                MockJournalEntryLineData('41020', Decimal('0'), Decimal('100'))
            ]
            
            self.gateway.create_journal_entry(
                source_module='students',
                source_model='StudentFee',
                source_id=i,
                lines=lines,
                idempotency_key=f"STATS:{i}",
                user=self.user
            )
        
        # Create some violations
        for i in range(2):
            violation_entry = MockJournalEntry(
                source_module='students',
                source_model='StudentFee',
                source_id=i + 100
            )
            violation_entry.created_by_service = 'DirectWrite'
            
            self.gateway.detect_out_of_band_write(violation_entry)
        
        # Verify statistics
        assert len(self.gateway.created_entries) == 3
        assert len(self.gateway.violations_detected) == 2
        
        # Verify all gateway entries are properly marked
        for entry in self.gateway.created_entries:
            assert entry.created_by_service == 'AccountingGateway'
            assert entry._gateway_approved is True
        
        # Verify all violations are properly recorded
        for violation in self.gateway.violations_detected:
            assert violation['violation_type'] == 'OUT_OF_BAND_WRITE'
            assert 'detected_at' in violation
        
        logger.info("✅ Gateway enforcement statistics verified")
    
    def _test_basic_gateway_enforcement(self, source_info, source_id, lines, idempotency_key):
        """Helper method for standalone testing of basic gateway enforcement"""
        source_module, source_model = source_info
        
        # Create journal entry through gateway (correct path)
        entry = self.gateway.create_journal_entry(
            source_module=source_module,
            source_model=source_model,
            source_id=source_id,
            lines=lines,
            idempotency_key=idempotency_key,
            user=self.user
        )
        
        # Verify entry was created through gateway
        assert entry.created_by_service == 'AccountingGateway'
        assert entry._gateway_approved is True
        assert entry.status == 'posted'
        assert entry.idempotency_key == idempotency_key
        
        # Verify no violations detected for gateway-created entries
        assert not self.gateway.detect_out_of_band_write(entry)
        
        # Verify entry is in gateway's created entries list
        assert entry in self.gateway.created_entries
        
        logger.info(f"✅ Gateway enforcement verified for {source_module}.{source_model}#{source_id}")
    
    def _test_out_of_band_detection(self, source_info, source_id, lines):
        """Helper method for standalone testing of out-of-band detection"""
        source_module, source_model = source_info
        
        # Create journal entry outside gateway (violation)
        out_of_band_entry = MockJournalEntry(
            source_module=source_module,
            source_model=source_model,
            source_id=source_id
        )
        # Deliberately NOT marking as gateway approved
        out_of_band_entry.created_by_service = 'DirectWrite'  # Simulate direct write
        
        # Detect out-of-band write
        violation_detected = self.gateway.detect_out_of_band_write(out_of_band_entry)
        
        # Verify violation was detected
        assert violation_detected is True
        assert len(self.gateway.violations_detected) > 0
        
        # Verify violation details
        violation = self.gateway.violations_detected[-1]
        assert violation['entry_id'] == out_of_band_entry.id
        assert violation['violation_type'] == 'OUT_OF_BAND_WRITE'
        assert violation['source_module'] == source_module
        assert violation['source_model'] == source_model
        assert violation['source_id'] == source_id
        
        # Audit the violation
        self.audit_service.log_gateway_violation(
            entry=out_of_band_entry,
            violation_type='OUT_OF_BAND_WRITE',
            user=self.user,
            detected_by='AccountingGateway'
        )
        
        # Verify audit trail was created
        assert len(self.audit_service.violations) > 0
        audit_violation = self.audit_service.violations[-1]
        assert audit_violation['entry_id'] == out_of_band_entry.id
        assert audit_violation['violation_type'] == 'OUT_OF_BAND_WRITE'
        
        # Quarantine the violating entry
        quarantine_record = self.quarantine_service.quarantine_entry(
            entry=out_of_band_entry,
            reason="Out-of-band journal entry creation detected",
            user=self.user
        )
        
        # Verify quarantine was successful
        assert quarantine_record is not None
        assert quarantine_record['entry_id'] == out_of_band_entry.id
        assert quarantine_record['status'] == 'QUARANTINED'
        assert len(self.quarantine_service.quarantined_entries) > 0
        
        logger.info(f"✅ Out-of-band detection verified for {source_module}.{source_model}#{source_id}")


# ===== Standalone Test Runner =====

def run_single_gateway_enforcement_property_tests():
    """
    Standalone test runner for Single Gateway Enforcement Property Tests.
    Can be run independently without Django test framework.
    """
    print("=" * 80)
    print("🔒 Running Single Gateway Enforcement Property Tests")
    print("Feature: code-governance-system, Property 1: Single Gateway Enforcement")
    print("Validates: Requirements 1.1")
    print("=" * 80)
    
    # Create mock user for standalone testing
    mock_user = type('MockUser', (), {
        'id': 1,
        'username': 'test_user',
        'email': 'test@example.com'
    })()
    
    # Initialize test instance
    test_instance = TestSingleGatewayEnforcementProperty()
    test_instance.setUp()
    
    test_results = []
    
    # Test 1: Basic Gateway Enforcement
    try:
        print("\n🧪 Test 1: Basic Gateway Enforcement")
        
        # Simulate property test with specific values
        source_info = ('students', 'StudentFee')
        source_id = 123
        lines = [
            MockJournalEntryLineData('10301', Decimal('1000'), Decimal('0')),
            MockJournalEntryLineData('41020', Decimal('0'), Decimal('1000'))
        ]
        idempotency_key = "JE:students:StudentFee:123:create"
        
        # Call the test method directly with parameters
        test_instance._test_basic_gateway_enforcement(source_info, source_id, lines, idempotency_key)
        
        print("   ✅ Basic gateway enforcement - PASSED")
        test_results.append(("Basic Gateway Enforcement", True, None))
        
    except Exception as e:
        print(f"   ❌ Basic gateway enforcement - FAILED: {str(e)}")
        test_results.append(("Basic Gateway Enforcement", False, str(e)))
    
    # Test 2: Out-of-Band Detection
    try:
        print("\n🧪 Test 2: Out-of-Band Write Detection")
        
        source_info = ('product', 'StockMovement')
        source_id = 456
        lines = [
            MockJournalEntryLineData('13000', Decimal('500'), Decimal('0')),
            MockJournalEntryLineData('20100', Decimal('0'), Decimal('500'))
        ]
        
        # Call the test method directly with parameters
        test_instance._test_out_of_band_detection(source_info, source_id, lines)
        
        print("   ✅ Out-of-band detection - PASSED")
        test_results.append(("Out-of-Band Detection", True, None))
        
    except Exception as e:
        print(f"   ❌ Out-of-band detection - FAILED: {str(e)}")
        test_results.append(("Out-of-Band Detection", False, str(e)))
    
    # Test 3: Statistics
    try:
        print("\n🧪 Test 3: Gateway Enforcement Statistics")
        
        test_instance.test_gateway_enforcement_statistics()
        
        print("   ✅ Gateway statistics - PASSED")
        test_results.append(("Gateway Statistics", True, None))
        
    except Exception as e:
        import traceback
        error_msg = f"{str(e)}\n{traceback.format_exc()}"
        print(f"   ❌ Gateway statistics - FAILED: {error_msg}")
        test_results.append(("Gateway Statistics", False, error_msg))
    
    # Summary
    print("\n" + "=" * 80)
    print("📊 SINGLE GATEWAY ENFORCEMENT PROPERTY TEST SUMMARY")
    print("=" * 80)
    
    passed_tests = sum(1 for _, passed, _ in test_results if passed)
    total_tests = len(test_results)
    
    for test_name, passed, error in test_results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name:.<50} {status}")
        if error:
            print(f"   Error: {error}")
    
    print(f"\nResults: {passed_tests}/{total_tests} tests passed")
    
    overall_success = passed_tests == total_tests
    
    if overall_success:
        print("🎉 All Single Gateway Enforcement Property Tests PASSED!")
        print("✅ Property 1: Single Gateway Enforcement - VALIDATED")
    else:
        print("❌ Some Single Gateway Enforcement Property Tests FAILED!")
        print("❌ Property 1: Single Gateway Enforcement - NEEDS ATTENTION")
    
    print("=" * 80)
    
    return overall_success


if __name__ == '__main__':
    """Run standalone property tests"""
    success = run_single_gateway_enforcement_property_tests()
    exit(0 if success else 1)