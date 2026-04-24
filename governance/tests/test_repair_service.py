"""
Tests for RepairService - Analysis Only Implementation

Tests the corruption detection scanners and repair policy framework
without executing any repairs (Phase 4A).
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal

from governance.services.repair_service import RepairService, CorruptionReport
from governance.services.repair_policy_framework import (
    RepairPolicyFramework, RepairPolicyType, ConfidenceLevel, DetailedRepairPlan
)
from governance.models import QuarantineRecord, AuditTrail

User = get_user_model()


class TestRepairService(TestCase):
    """Test RepairService corruption detection and policy framework"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='repair_test_user',
            email='repair@test.com',
            password='testpass123'
        )
        self.repair_service = RepairService()
        self.repair_service.set_user(self.user)
    
    def test_repair_service_initialization(self):
        """Test RepairService initializes correctly"""
        service = RepairService()
        
        # Check scanners are initialized
        self.assertIn('ORPHANED_JOURNAL_ENTRIES', service.scanners)
        self.assertIn('NEGATIVE_STOCK', service.scanners)
        self.assertIn('MULTIPLE_ACTIVE_ACADEMIC_YEARS', service.scanners)
        self.assertIn('UNBALANCED_JOURNAL_ENTRIES', service.scanners)
        
        # Check policy framework is initialized
        self.assertIsInstance(service.policy_framework, RepairPolicyFramework)
    
    def test_corruption_report_creation(self):
        """Test CorruptionReport creation and methods"""
        report = CorruptionReport()
        
        # Add corruption findings
        issues = [
            {'entry_id': 1, 'source_module': None},
            {'entry_id': 2, 'source_model': None}
        ]
        
        report.add_corruption(
            corruption_type='ORPHANED_JOURNAL_ENTRIES',
            issues=issues,
            confidence='HIGH',
            evidence={'scan_method': 'ORM_based'}
        )
        
        # Test report data
        self.assertEqual(report.total_issues, 2)
        self.assertIn('ORPHANED_JOURNAL_ENTRIES', report.corruption_types)
        self.assertEqual(report.corruption_types['ORPHANED_JOURNAL_ENTRIES']['count'], 2)
        self.assertEqual(report.corruption_types['ORPHANED_JOURNAL_ENTRIES']['confidence'], 'HIGH')
        
        # Test summary
        summary = report.get_summary()
        self.assertEqual(summary['total_issues'], 2)
        self.assertEqual(summary['high_confidence_issues'], 1)
    
    @patch('governance.services.repair_service.apps.get_model')
    def test_scan_orphaned_journal_entries_no_issues(self, mock_get_model):
        """Test orphaned journal entries scan with no issues found"""
        # Mock JournalEntry model
        mock_entry = Mock()
        mock_entry.id = 1
        mock_entry.source_module = 'students'
        mock_entry.source_model = 'StudentFee'
        mock_entry.source_id = 1
        mock_entry.created_at = timezone.now()
        mock_entry.amount = Decimal('100.00')
        mock_entry.description = 'Test entry'
        
        mock_queryset = Mock()
        mock_queryset.count.return_value = 1
        mock_queryset.__iter__ = Mock(return_value=iter([mock_entry]))
        
        mock_model = Mock()
        mock_model.objects.all.return_value = mock_queryset
        mock_get_model.return_value = mock_model
        
        # Mock source linkage validation to return True (valid)
        with patch.object(self.repair_service, '_validate_journal_entry_linkage', return_value=True):
            issues, confidence, evidence = self.repair_service._scan_orphaned_journal_entries()
        
        # Should find no issues
        self.assertEqual(len(issues), 0)
        self.assertEqual(confidence, 'HIGH')
        self.assertEqual(evidence['total_journal_entries'], 1)
        self.assertEqual(evidence['orphaned_entries'], 0)
    
    @patch('governance.services.repair_service.apps.get_model')
    def test_scan_orphaned_journal_entries_with_issues(self, mock_get_model):
        """Test orphaned journal entries scan with issues found"""
        # Mock orphaned entry
        mock_entry = Mock()
        mock_entry.id = 1
        mock_entry.source_module = None  # Missing source linkage
        mock_entry.source_model = None
        mock_entry.source_id = None
        mock_entry.created_at = timezone.now()
        mock_entry.amount = Decimal('100.00')
        mock_entry.description = 'Orphaned entry'
        
        mock_queryset = Mock()
        mock_queryset.count.return_value = 1
        mock_queryset.__iter__ = Mock(return_value=iter([mock_entry]))
        
        mock_model = Mock()
        mock_model.objects.all.return_value = mock_queryset
        mock_get_model.return_value = mock_model
        
        # Mock source linkage validation to return False (invalid)
        with patch.object(self.repair_service, '_validate_journal_entry_linkage', return_value=False):
            issues, confidence, evidence = self.repair_service._scan_orphaned_journal_entries()
        
        # Should find one issue
        self.assertEqual(len(issues), 1)
        self.assertEqual(confidence, 'HIGH')  # 1 orphan <= 25 threshold
        self.assertEqual(evidence['total_journal_entries'], 1)
        self.assertEqual(evidence['orphaned_entries'], 1)
        
        # Check issue details
        issue = issues[0]
        self.assertEqual(issue['entry_id'], 1)
        self.assertIsNone(issue['source_module'])
    
    @patch('governance.services.repair_service.apps.get_model')
    def test_scan_negative_stock(self, mock_get_model):
        """Test negative stock scan"""
        # Mock negative stock
        mock_stock = Mock()
        mock_stock.id = 1
        mock_stock.product_id = 1
        mock_stock.quantity = Decimal('-5.00')
        mock_stock.product.id = 1
        mock_stock.product.__str__ = Mock(return_value='Test Product')
        mock_stock.updated_at = timezone.now()
        
        mock_negative_queryset = Mock()
        mock_negative_queryset.count.return_value = 1
        mock_negative_queryset.__iter__ = Mock(return_value=iter([mock_stock]))
        
        mock_total_queryset = Mock()
        mock_total_queryset.count.return_value = 10
        
        mock_model = Mock()
        mock_model.objects.filter.return_value = mock_negative_queryset
        mock_model.objects.count.return_value = 10
        mock_get_model.return_value = mock_model
        
        issues, confidence, evidence = self.repair_service._scan_negative_stock()
        
        # Should find one issue
        self.assertEqual(len(issues), 1)
        self.assertEqual(confidence, 'HIGH')
        self.assertEqual(evidence['total_stock_records'], 10)
        self.assertEqual(evidence['negative_stock_count'], 1)
        
        # Check issue details
        issue = issues[0]
        self.assertEqual(issue['stock_id'], 1)
        self.assertEqual(issue['current_quantity'], '-5.00')
    
    @patch('governance.services.repair_service.apps.get_model')
    def test_scan_multiple_active_academic_years(self, mock_get_model):
        """Test multiple active academic years scan"""
        # Mock multiple active years
        mock_year1 = Mock()
        mock_year1.id = 1
        mock_year1.is_active = True
        mock_year1.__str__ = Mock(return_value='2023-2024')
        mock_year1.start_date = timezone.now().date()
        mock_year1.end_date = timezone.now().date()
        
        mock_year2 = Mock()
        mock_year2.id = 2
        mock_year2.is_active = True
        mock_year2.__str__ = Mock(return_value='2024-2025')
        mock_year2.start_date = timezone.now().date()
        mock_year2.end_date = timezone.now().date()
        
        mock_active_queryset = Mock()
        mock_active_queryset.count.return_value = 2  # Multiple active years
        mock_active_queryset.__iter__ = Mock(return_value=iter([mock_year1, mock_year2]))
        
        mock_model = Mock()
        mock_model.objects.filter.return_value = mock_active_queryset
        mock_model.objects.count.return_value = 5
        mock_get_model.return_value = mock_model
        
        issues, confidence, evidence = self.repair_service._scan_multiple_active_academic_years()
        
        # Should find two issues (both active years)
        self.assertEqual(len(issues), 2)
        self.assertEqual(confidence, 'HIGH')
        self.assertEqual(evidence['total_academic_years'], 5)
        self.assertEqual(evidence['active_years_count'], 2)
    
    def test_scan_for_corruption_integration(self):
        """Test full corruption scan integration"""
        # Mock all scanners to return no issues
        with patch.object(self.repair_service, '_scan_orphaned_journal_entries', return_value=([], 'HIGH', {})), \
             patch.object(self.repair_service, '_scan_negative_stock', return_value=([], 'HIGH', {})), \
             patch.object(self.repair_service, '_scan_multiple_active_academic_years', return_value=([], 'HIGH', {})), \
             patch.object(self.repair_service, '_scan_unbalanced_journal_entries', return_value=([], 'HIGH', {})):
            
            report = self.repair_service.scan_for_corruption()
        
        # Should create report with no issues
        self.assertEqual(report.total_issues, 0)
        self.assertEqual(len(report.corruption_types), 0)
        
        # Check audit trail was created
        audit_records = AuditTrail.objects.filter(
            model_name='RepairService',
            operation='CORRUPTION_SCAN',
            user=self.user
        )
        self.assertEqual(audit_records.count(), 1)
    
    def test_repair_policy_framework_integration(self):
        """Test integration with repair policy framework"""
        # Create corruption report with issues
        report = CorruptionReport()
        issues = [{'entry_id': 1, 'source_module': None}]
        report.add_corruption('ORPHANED_JOURNAL_ENTRIES', issues, 'HIGH')
        
        # Generate comprehensive repair plan
        comprehensive_plan = self.repair_service.generate_comprehensive_repair_plan(report)
        
        # Check plan structure
        self.assertIn('detailed_plans', comprehensive_plan)
        self.assertIn('overall_risk_assessment', comprehensive_plan)
        self.assertIn('compliance_validation', comprehensive_plan)
        self.assertTrue(comprehensive_plan['execution_blocked'])
        self.assertEqual(comprehensive_plan['phase'], '4A_ANALYSIS_ONLY')
        
        # Check detailed plan for orphaned entries
        self.assertIn('ORPHANED_JOURNAL_ENTRIES', comprehensive_plan['detailed_plans'])
        orphaned_plan = comprehensive_plan['detailed_plans']['ORPHANED_JOURNAL_ENTRIES']
        self.assertEqual(orphaned_plan['corruption_type'], 'ORPHANED_JOURNAL_ENTRIES')
        self.assertEqual(orphaned_plan['policy_type'], 'RELINK')  # HIGH confidence -> RELINK
        self.assertEqual(orphaned_plan['confidence'], 'HIGH')
    
    def test_create_repair_report_comprehensive(self):
        """Test comprehensive repair report creation"""
        # Create corruption report with multiple issues
        report = CorruptionReport()
        report.add_corruption('ORPHANED_JOURNAL_ENTRIES', [{'entry_id': 1}], 'HIGH')
        report.add_corruption('NEGATIVE_STOCK', [{'stock_id': 1}], 'MEDIUM')
        
        # Create repair report
        repair_report = self.repair_service.create_repair_report(report)
        
        # Check report structure
        self.assertTrue(repair_report['approval_required'])
        self.assertTrue(repair_report['execution_blocked'])
        self.assertEqual(repair_report['phase'], '4A_ANALYSIS_ONLY')
        
        # Check comprehensive plan is included
        self.assertIn('comprehensive_repair_plan', repair_report)
        comprehensive_plan = repair_report['comprehensive_repair_plan']
        self.assertIn('detailed_plans', comprehensive_plan)
        self.assertIn('overall_risk_assessment', comprehensive_plan)
        
        # Check compliance summary
        self.assertIn('compliance_summary', repair_report)
        compliance = repair_report['compliance_summary']
        self.assertIn('all_plans_compliant', compliance)
        self.assertIn('total_violations', compliance)
    
    def test_quarantine_suspicious_data_no_auto_quarantine(self):
        """Test quarantine with auto_quarantine=False"""
        # Create corruption report with HIGH confidence issues
        report = CorruptionReport()
        issues = [{'entry_id': 1, 'source_module': None}]
        report.add_corruption('ORPHANED_JOURNAL_ENTRIES', issues, 'HIGH')
        
        # Should skip quarantine for HIGH confidence without auto_quarantine
        results = self.repair_service.quarantine_suspicious_data(report, auto_quarantine=False)
        
        self.assertEqual(len(results['quarantined_items']), 0)
        self.assertEqual(len(results['skipped_items']), 1)
        self.assertEqual(results['skipped_items'][0]['reason'], 'Confidence HIGH - manual approval required')
    
    def test_quarantine_suspicious_data_low_confidence(self):
        """Test quarantine with LOW confidence issues"""
        # Create corruption report with LOW confidence issues
        report = CorruptionReport()
        issues = [{'entry_id': 1, 'source_module': None}]
        report.add_corruption('ORPHANED_JOURNAL_ENTRIES', issues, 'LOW')
        
        # Mock QuarantineService
        with patch('governance.services.repair_service.QuarantineService.quarantine_orphaned_journal_entry') as mock_quarantine:
            mock_quarantine_record = Mock()
            mock_quarantine_record.id = 1
            mock_quarantine.return_value = mock_quarantine_record
            
            # Should quarantine LOW confidence issues automatically
            results = self.repair_service.quarantine_suspicious_data(report, auto_quarantine=False)
        
        self.assertEqual(len(results['quarantined_items']), 1)
        self.assertEqual(len(results['skipped_items']), 0)
        mock_quarantine.assert_called_once_with(entry_id=1, user=self.user)


class TestRepairPolicyFramework(TestCase):
    """Test RepairPolicyFramework functionality"""
    
    def setUp(self):
        """Set up test data"""
        self.framework = RepairPolicyFramework()
    
    def test_policy_framework_initialization(self):
        """Test policy framework initializes correctly"""
        # Check policies are loaded
        self.assertIn('ORPHANED_JOURNAL_ENTRIES', self.framework.policies)
        self.assertIn('NEGATIVE_STOCK', self.framework.policies)
        self.assertIn('MULTIPLE_ACTIVE_ACADEMIC_YEARS', self.framework.policies)
        
        # Check verification templates
        self.assertIn('ORPHANED_JOURNAL_ENTRIES', self.framework.verification_templates)
        
        # Check rollback templates
        self.assertIn('RELINK_ROLLBACK', self.framework.rollback_templates)
    
    def test_get_policy_high_confidence_orphaned_entries(self):
        """Test policy retrieval for high confidence orphaned entries"""
        policy = self.framework.get_policy('ORPHANED_JOURNAL_ENTRIES', ConfidenceLevel.HIGH)
        
        self.assertEqual(policy['policy'], RepairPolicyType.RELINK)
        self.assertEqual(policy['risk_level'], 'LOW')
        self.assertFalse(policy['approval_required'])
        self.assertEqual(policy['batch_size'], 50)
    
    def test_get_policy_low_confidence_negative_stock(self):
        """Test policy retrieval for low confidence negative stock"""
        policy = self.framework.get_policy('NEGATIVE_STOCK', ConfidenceLevel.LOW)
        
        self.assertEqual(policy['policy'], RepairPolicyType.QUARANTINE)
        self.assertEqual(policy['risk_level'], 'HIGH')
        self.assertTrue(policy['approval_required'])
        self.assertEqual(policy['batch_size'], 5)
    
    def test_create_repair_plan_orphaned_entries(self):
        """Test repair plan creation for orphaned entries"""
        corrupted_objects = [
            {'entry_id': 1, 'source_module': None},
            {'entry_id': 2, 'source_module': None}
        ]
        
        plan = self.framework.create_repair_plan(
            'ORPHANED_JOURNAL_ENTRIES',
            ConfidenceLevel.HIGH,
            corrupted_objects
        )
        
        # Check plan properties
        self.assertEqual(plan.corruption_type, 'ORPHANED_JOURNAL_ENTRIES')
        self.assertEqual(plan.policy_type, RepairPolicyType.RELINK)
        self.assertEqual(plan.confidence, ConfidenceLevel.HIGH)
        self.assertEqual(plan.affected_objects_count, 2)
        
        # Check repair actions
        self.assertGreater(len(plan.repair_actions), 0)
        action = plan.repair_actions[0]
        self.assertEqual(action.action_type, 'RELINK_JOURNAL_ENTRIES')
        self.assertEqual(action.target_model, 'JournalEntry')
        
        # Check verification invariants
        self.assertGreater(len(plan.verification_invariants), 0)
        
        # Check rollback strategy
        self.assertIsNotNone(plan.rollback_strategy)
    
    def test_validate_policy_compliance_compliant_plan(self):
        """Test policy compliance validation for compliant plan"""
        corrupted_objects = [{'entry_id': 1}]
        
        plan = self.framework.create_repair_plan(
            'ORPHANED_JOURNAL_ENTRIES',
            ConfidenceLevel.HIGH,
            corrupted_objects
        )
        
        compliance = self.framework.validate_policy_compliance(plan)
        
        # Should be compliant
        self.assertTrue(compliance['is_compliant'])
        self.assertEqual(len(compliance['violations']), 0)
        
        # Should have recommendations for approval
        self.assertGreater(len(compliance['recommendations']), 0)
    
    def test_repair_plan_serialization(self):
        """Test repair plan serialization to dictionary"""
        corrupted_objects = [{'entry_id': 1}]
        
        plan = self.framework.create_repair_plan(
            'ORPHANED_JOURNAL_ENTRIES',
            ConfidenceLevel.HIGH,
            corrupted_objects
        )
        
        plan_dict = plan.to_dict()
        
        # Check required fields
        self.assertIn('corruption_type', plan_dict)
        self.assertIn('policy_type', plan_dict)
        self.assertIn('confidence', plan_dict)
        self.assertIn('repair_actions', plan_dict)
        self.assertIn('verification_invariants', plan_dict)
        self.assertIn('rollback_strategy', plan_dict)
        self.assertIn('risk_assessment', plan_dict)
        
        # Check values
        self.assertEqual(plan_dict['corruption_type'], 'ORPHANED_JOURNAL_ENTRIES')
        self.assertEqual(plan_dict['policy_type'], 'RELINK')
        self.assertEqual(plan_dict['confidence'], 'HIGH')
        self.assertTrue(plan_dict['approval_required'])