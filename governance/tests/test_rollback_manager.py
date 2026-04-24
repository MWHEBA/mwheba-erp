"""
Comprehensive tests for RollbackManager.
Tests safe rollback mechanisms, violation monitoring, and emergency responses.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from governance.services.rollback_manager import (
    RollbackManager, 
    GovernanceSnapshot, 
    ViolationThreshold,
    rollback_manager,
    create_governance_snapshot,
    rollback_to_snapshot,
    record_governance_violation,
    get_rollback_statistics,
    rollback_protection
)
from governance.services import governance_switchboard
from governance.exceptions import ValidationError, RollbackError
from governance.models import GovernanceContext

User = get_user_model()


class TestRollbackManager(TestCase):
    """Test RollbackManager functionality"""
    
    def setUp(self):
        """Set up test environment"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Create fresh rollback manager for testing
        self.rollback_manager = RollbackManager(max_snapshots=10)
        
        # Set governance context
        GovernanceContext.set_context(user=self.user, service='TestService')
    
    def tearDown(self):
        """Clean up after tests"""
        GovernanceContext.clear_context()
    
    def test_create_snapshot(self):
        """Test creating governance snapshots"""
        # Mock governance switchboard state
        with patch.object(governance_switchboard, '_component_flags', {'test_component': True}):
            with patch.object(governance_switchboard, '_workflow_flags', {'test_workflow': False}):
                with patch.object(governance_switchboard, '_emergency_flags', {'test_emergency': False}):
                    
                    snapshot = self.rollback_manager.create_snapshot(
                        "Test snapshot creation",
                        self.user
                    )
                    
                    # Verify snapshot properties
                    self.assertIsInstance(snapshot, GovernanceSnapshot)
                    self.assertEqual(snapshot.reason, "Test snapshot creation")
                    self.assertEqual(snapshot.created_by, self.user.username)
                    self.assertIn('test_component', snapshot.component_flags)
                    self.assertIn('test_workflow', snapshot.workflow_flags)
                    self.assertIn('test_emergency', snapshot.emergency_flags)
                    
                    # Verify snapshot is stored
                    snapshots = self.rollback_manager.get_snapshots()
                    self.assertEqual(len(snapshots), 1)
                    self.assertEqual(snapshots[0].snapshot_id, snapshot.snapshot_id)
    
    def test_snapshot_limit_enforcement(self):
        """Test that snapshot limit is enforced"""
        # Create manager with small limit
        manager = RollbackManager(max_snapshots=3)
        
        # Create more snapshots than limit
        for i in range(5):
            with patch.object(governance_switchboard, '_component_flags', {}):
                with patch.object(governance_switchboard, '_workflow_flags', {}):
                    with patch.object(governance_switchboard, '_emergency_flags', {}):
                        manager.create_snapshot(f"Snapshot {i}", self.user)
        
        # Verify only max_snapshots are kept
        snapshots = manager.get_snapshots()
        self.assertEqual(len(snapshots), 3)
        
        # Verify oldest snapshots were removed (should have snapshots 2, 3, 4)
        snapshot_reasons = [s.reason for s in snapshots]
        self.assertIn("Snapshot 2", snapshot_reasons)
        self.assertIn("Snapshot 3", snapshot_reasons)
        self.assertIn("Snapshot 4", snapshot_reasons)
        self.assertNotIn("Snapshot 0", snapshot_reasons)
        self.assertNotIn("Snapshot 1", snapshot_reasons)
    
    @patch('governance.services.rollback_manager.governance_switchboard')
    def test_rollback_to_snapshot(self, mock_switchboard):
        """Test rolling back to a snapshot"""
        # Create initial snapshot
        original_state = {
            'component_flags': {'accounting_gateway_enforcement': True, 'movement_service_enforcement': False},
            'workflow_flags': {'student_fee_to_journal_entry': True, 'stock_movement_to_journal_entry': False},
            'emergency_flags': {'emergency_disable_all_governance': False}
        }
        
        with patch.object(governance_switchboard, '_component_flags', original_state['component_flags']):
            with patch.object(governance_switchboard, '_workflow_flags', original_state['workflow_flags']):
                with patch.object(governance_switchboard, '_emergency_flags', original_state['emergency_flags']):
                    snapshot = self.rollback_manager.create_snapshot("Original state", self.user)
        
        # Mock switchboard methods
        mock_switchboard.is_component_enabled.side_effect = lambda x: False  # Current state different
        mock_switchboard.is_workflow_enabled.side_effect = lambda x: False
        mock_switchboard.is_emergency_flag_active.side_effect = lambda x: False
        mock_switchboard.enable_component.return_value = True
        mock_switchboard.disable_component.return_value = True
        mock_switchboard.enable_workflow.return_value = True
        mock_switchboard.disable_workflow.return_value = True
        mock_switchboard.activate_emergency_flag.return_value = True
        mock_switchboard.deactivate_emergency_flag.return_value = True
        
        # Perform rollback
        result = self.rollback_manager.rollback_to_snapshot(
            snapshot.snapshot_id,
            "Test rollback",
            self.user
        )
        
        # Verify rollback succeeded
        self.assertTrue(result)
        
        # Verify switchboard methods were called correctly
        mock_switchboard.enable_component.assert_any_call(
            'accounting_gateway_enforcement', 'Rollback: Test rollback', self.user
        )
        mock_switchboard.enable_workflow.assert_any_call(
            'student_fee_to_journal_entry', 'Rollback: Test rollback', self.user
        )
    
    def test_rollback_nonexistent_snapshot(self):
        """Test rollback to nonexistent snapshot fails"""
        with self.assertRaises(ValidationError) as context:
            self.rollback_manager.rollback_to_snapshot(
                "nonexistent_snapshot",
                "Test rollback",
                self.user
            )
        
        self.assertIn("Snapshot not found", str(context.exception))
    
    def test_record_violation(self):
        """Test recording governance violations"""
        violation_type = 'authority_violation'
        details = {
            'component': 'accounting_gateway',
            'service': 'UnauthorizedService',
            'model': 'JournalEntry'
        }
        
        # Record violation
        self.rollback_manager.record_violation(violation_type, details, self.user)
        
        # Verify violation was recorded
        stats = self.rollback_manager.get_violation_statistics()
        self.assertEqual(stats['total_violations'], 1)
        self.assertIn(violation_type, stats['violation_types'])
        self.assertEqual(stats['violation_types'][violation_type], 1)
    
    def test_violation_threshold_trigger(self):
        """Test that violation thresholds trigger automated rollback"""
        # Create threshold with low limits for testing
        threshold = ViolationThreshold(
            violation_type='test_violation',
            max_violations=2,
            time_window_minutes=5,
            rollback_action='disable_component',
            target='test_component'
        )
        
        self.rollback_manager.add_violation_threshold(threshold)
        
        with patch.object(governance_switchboard, 'disable_component') as mock_disable:
            mock_disable.return_value = True
            
            # Record violations to exceed threshold
            for i in range(3):
                self.rollback_manager.record_violation(
                    'test_violation',
                    {'component': 'test_component'},
                    self.user
                )
            
            # Verify automated rollback was triggered
            mock_disable.assert_called_once()
            call_args = mock_disable.call_args
            self.assertEqual(call_args[0][0], 'test_component')  # target component
            self.assertIn('Automated rollback', call_args[0][1])  # reason
    
    def test_violation_threshold_emergency_trigger(self):
        """Test that violation thresholds can trigger emergency flags"""
        # Create threshold that triggers emergency flag
        threshold = ViolationThreshold(
            violation_type='critical_violation',
            max_violations=1,
            time_window_minutes=5,
            rollback_action='emergency_disable',
            target='emergency_disable_accounting'
        )
        
        self.rollback_manager.add_violation_threshold(threshold)
        
        with patch.object(governance_switchboard, 'activate_emergency_flag') as mock_emergency:
            mock_emergency.return_value = True
            
            # Record violation to trigger emergency
            self.rollback_manager.record_violation(
                'critical_violation',
                {'component': 'accounting_gateway'},
                self.user
            )
            
            # Verify emergency flag was activated
            mock_emergency.assert_called_once()
            call_args = mock_emergency.call_args
            self.assertEqual(call_args[0][0], 'emergency_disable_accounting')
            self.assertIn('Automated rollback', call_args[0][1])
    
    def test_violation_cleanup(self):
        """Test that old violations are cleaned up"""
        violation_type = 'test_violation'
        
        # Record violation
        self.rollback_manager.record_violation(violation_type, {}, self.user)
        
        # Verify violation exists
        self.assertIn(violation_type, self.rollback_manager._violation_counts)
        self.assertEqual(len(self.rollback_manager._violation_counts[violation_type]), 1)
        
        # Mock old timestamp
        old_time = timezone.now() - timedelta(hours=2)
        self.rollback_manager._violation_counts[violation_type][0] = old_time
        
        # Clean old violations
        current_time = timezone.now()
        self.rollback_manager._clean_old_violations(violation_type, current_time)
        
        # Verify old violation was cleaned
        self.assertEqual(len(self.rollback_manager._violation_counts[violation_type]), 0)
    
    def test_threshold_management(self):
        """Test adding, removing, and managing violation thresholds"""
        threshold = ViolationThreshold(
            violation_type='test_violation',
            max_violations=5,
            time_window_minutes=10,
            rollback_action='disable_component',
            target='test_component'
        )
        
        # Add threshold
        initial_count = len(self.rollback_manager._thresholds)
        self.rollback_manager.add_violation_threshold(threshold)
        self.assertEqual(len(self.rollback_manager._thresholds), initial_count + 1)
        
        # Verify threshold was added
        added_threshold = None
        for t in self.rollback_manager._thresholds:
            if t.violation_type == 'test_violation' and t.target == 'test_component':
                added_threshold = t
                break
        
        self.assertIsNotNone(added_threshold)
        self.assertEqual(added_threshold.max_violations, 5)
        self.assertTrue(added_threshold.enabled)
        
        # Disable threshold
        self.rollback_manager.disable_threshold('test_violation', 'test_component')
        self.assertFalse(added_threshold.enabled)
        
        # Enable threshold
        self.rollback_manager.enable_threshold('test_violation', 'test_component')
        self.assertTrue(added_threshold.enabled)
        
        # Remove threshold
        self.rollback_manager.remove_violation_threshold('test_violation', 'test_component')
        self.assertEqual(len(self.rollback_manager._thresholds), initial_count)
    
    def test_rollback_protection_context_manager(self):
        """Test rollback protection context manager"""
        with patch.object(governance_switchboard, '_component_flags', {}):
            with patch.object(governance_switchboard, '_workflow_flags', {}):
                with patch.object(governance_switchboard, '_emergency_flags', {}):
                    
                    initial_snapshot_count = len(self.rollback_manager.get_snapshots())
                    
                    # Use rollback protection
                    with self.rollback_manager.rollback_protection("Test operation"):
                        # Snapshot should be created
                        snapshots = self.rollback_manager.get_snapshots()
                        self.assertEqual(len(snapshots), initial_snapshot_count + 1)
                        
                        # Verify snapshot reason
                        latest_snapshot = snapshots[-1]
                        self.assertIn("Protection snapshot: Test operation", latest_snapshot.reason)
    
    def test_rollback_protection_with_exception(self):
        """Test rollback protection when exception occurs"""
        with patch.object(governance_switchboard, '_component_flags', {}):
            with patch.object(governance_switchboard, '_workflow_flags', {}):
                with patch.object(governance_switchboard, '_emergency_flags', {}):
                    
                    initial_snapshot_count = len(self.rollback_manager.get_snapshots())
                    
                    # Use rollback protection with exception
                    with self.assertRaises(ValueError):
                        with self.rollback_manager.rollback_protection("Test operation"):
                            # Snapshot should still be created
                            snapshots = self.rollback_manager.get_snapshots()
                            self.assertEqual(len(snapshots), initial_snapshot_count + 1)
                            
                            # Raise exception
                            raise ValueError("Test exception")
                    
                    # Snapshot should still exist after exception
                    final_snapshots = self.rollback_manager.get_snapshots()
                    self.assertEqual(len(final_snapshots), initial_snapshot_count + 1)
    
    def test_get_recent_snapshots(self):
        """Test getting recent snapshots"""
        # Create multiple snapshots
        with patch.object(governance_switchboard, '_component_flags', {}):
            with patch.object(governance_switchboard, '_workflow_flags', {}):
                with patch.object(governance_switchboard, '_emergency_flags', {}):
                    
                    for i in range(5):
                        self.rollback_manager.create_snapshot(f"Snapshot {i}", self.user)
        
        # Get recent snapshots
        recent = self.rollback_manager.get_recent_snapshots(3)
        self.assertEqual(len(recent), 3)
        
        # Verify they are the most recent ones
        snapshot_reasons = [s.reason for s in recent]
        self.assertIn("Snapshot 2", snapshot_reasons)
        self.assertIn("Snapshot 3", snapshot_reasons)
        self.assertIn("Snapshot 4", snapshot_reasons)
    
    def test_violation_statistics(self):
        """Test getting violation statistics"""
        # Record various violations
        violations = [
            ('authority_violation', {'component': 'gateway1'}),
            ('authority_violation', {'component': 'gateway2'}),
            ('stock_violation', {'component': 'movement_service'}),
        ]
        
        for violation_type, details in violations:
            self.rollback_manager.record_violation(violation_type, details, self.user)
        
        # Get statistics
        stats = self.rollback_manager.get_violation_statistics()
        
        # Verify statistics
        self.assertEqual(stats['total_violations'], 3)
        self.assertEqual(stats['violation_types']['authority_violation'], 2)
        self.assertEqual(stats['violation_types']['stock_violation'], 1)
        self.assertIn('recent_violations', stats)
        self.assertIn('active_thresholds', stats)
    
    @patch('governance.services.rollback_manager.send_mail')
    def test_alert_email_sending(self, mock_send_mail):
        """Test that alert emails are sent correctly"""
        # Create rollback manager with alert email
        manager = RollbackManager(alert_email='admin@example.com')
        
        # Create and rollback snapshot to trigger alert
        with patch.object(governance_switchboard, '_component_flags', {'test': True}):
            with patch.object(governance_switchboard, '_workflow_flags', {}):
                with patch.object(governance_switchboard, '_emergency_flags', {}):
                    snapshot = manager.create_snapshot("Test snapshot", self.user)
        
        with patch.object(manager, '_perform_rollback', return_value=True):
            manager.rollback_to_snapshot(snapshot.snapshot_id, "Test rollback", self.user)
        
        # Verify email was sent
        mock_send_mail.assert_called_once()
        call_args = mock_send_mail.call_args
        self.assertIn('Governance Rollback Executed', call_args[1]['subject'])
        self.assertEqual(call_args[1]['recipient_list'], ['admin@example.com'])


class TestRollbackManagerConvenienceFunctions(TestCase):
    """Test convenience functions for rollback manager"""
    
    def setUp(self):
        """Set up test environment"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        GovernanceContext.set_context(user=self.user, service='TestService')
    
    def tearDown(self):
        """Clean up after tests"""
        GovernanceContext.clear_context()
    
    @patch('governance.services.rollback_manager.rollback_manager')
    def test_create_governance_snapshot(self, mock_manager):
        """Test create_governance_snapshot convenience function"""
        mock_snapshot = Mock()
        mock_manager.create_snapshot.return_value = mock_snapshot
        
        result = create_governance_snapshot("Test snapshot", self.user)
        
        mock_manager.create_snapshot.assert_called_once_with("Test snapshot", self.user)
        self.assertEqual(result, mock_snapshot)
    
    @patch('governance.services.rollback_manager.rollback_manager')
    def test_rollback_to_snapshot_function(self, mock_manager):
        """Test rollback_to_snapshot convenience function"""
        mock_manager.rollback_to_snapshot.return_value = True
        
        result = rollback_to_snapshot("test_snapshot", "Test rollback", self.user)
        
        mock_manager.rollback_to_snapshot.assert_called_once_with(
            "test_snapshot", "Test rollback", self.user
        )
        self.assertTrue(result)
    
    @patch('governance.services.rollback_manager.rollback_manager')
    def test_record_governance_violation_function(self, mock_manager):
        """Test record_governance_violation convenience function"""
        details = {'component': 'test_component'}
        
        record_governance_violation('test_violation', details, self.user)
        
        mock_manager.record_violation.assert_called_once_with(
            'test_violation', details, self.user
        )
    
    @patch('governance.services.rollback_manager.rollback_manager')
    def test_get_rollback_statistics_function(self, mock_manager):
        """Test get_rollback_statistics convenience function"""
        mock_stats = {'total_violations': 5}
        mock_manager.get_violation_statistics.return_value = mock_stats
        
        result = get_rollback_statistics()
        
        mock_manager.get_violation_statistics.assert_called_once()
        self.assertEqual(result, mock_stats)
    
    def test_rollback_protection_function(self):
        """Test rollback_protection convenience function"""
        with patch('governance.services.rollback_manager.rollback_manager') as mock_manager:
            mock_context = Mock()
            mock_manager.rollback_protection.return_value = mock_context
            
            with rollback_protection("Test operation"):
                pass
            
            mock_manager.rollback_protection.assert_called_once_with("Test operation")
            mock_context.__enter__.assert_called_once()
            mock_context.__exit__.assert_called_once()


class TestGovernanceSnapshot(TestCase):
    """Test GovernanceSnapshot data class"""
    
    def test_snapshot_creation(self):
        """Test creating a governance snapshot"""
        timestamp = timezone.now()
        snapshot = GovernanceSnapshot(
            timestamp=timestamp,
            component_flags={'test_component': True},
            workflow_flags={'test_workflow': False},
            emergency_flags={'test_emergency': False},
            reason="Test snapshot",
            created_by="testuser",
            snapshot_id="test_snapshot_123"
        )
        
        self.assertEqual(snapshot.timestamp, timestamp)
        self.assertEqual(snapshot.component_flags, {'test_component': True})
        self.assertEqual(snapshot.workflow_flags, {'test_workflow': False})
        self.assertEqual(snapshot.emergency_flags, {'test_emergency': False})
        self.assertEqual(snapshot.reason, "Test snapshot")
        self.assertEqual(snapshot.created_by, "testuser")
        self.assertEqual(snapshot.snapshot_id, "test_snapshot_123")
    
    def test_snapshot_to_dict(self):
        """Test converting snapshot to dictionary"""
        timestamp = timezone.now()
        snapshot = GovernanceSnapshot(
            timestamp=timestamp,
            component_flags={'test': True},
            workflow_flags={'test': False},
            emergency_flags={'test': False},
            reason="Test",
            created_by="user",
            snapshot_id="test_123"
        )
        
        snapshot_dict = snapshot.to_dict()
        
        self.assertIsInstance(snapshot_dict, dict)
        self.assertEqual(snapshot_dict['timestamp'], timestamp)
        self.assertEqual(snapshot_dict['component_flags'], {'test': True})
        self.assertEqual(snapshot_dict['reason'], "Test")
        self.assertEqual(snapshot_dict['created_by'], "user")
        self.assertEqual(snapshot_dict['snapshot_id'], "test_123")
    
    def test_snapshot_from_dict(self):
        """Test creating snapshot from dictionary"""
        timestamp = timezone.now()
        snapshot_dict = {
            'timestamp': timestamp,
            'component_flags': {'test': True},
            'workflow_flags': {'test': False},
            'emergency_flags': {'test': False},
            'reason': "Test",
            'created_by': "user",
            'snapshot_id': "test_123"
        }
        
        snapshot = GovernanceSnapshot.from_dict(snapshot_dict)
        
        self.assertIsInstance(snapshot, GovernanceSnapshot)
        self.assertEqual(snapshot.timestamp, timestamp)
        self.assertEqual(snapshot.component_flags, {'test': True})
        self.assertEqual(snapshot.reason, "Test")
        self.assertEqual(snapshot.created_by, "user")
        self.assertEqual(snapshot.snapshot_id, "test_123")


class TestViolationThreshold(TestCase):
    """Test ViolationThreshold data class"""
    
    def test_threshold_creation(self):
        """Test creating a violation threshold"""
        threshold = ViolationThreshold(
            violation_type='test_violation',
            max_violations=5,
            time_window_minutes=10,
            rollback_action='disable_component',
            target='test_component',
            enabled=True,
            cooldown_minutes=5
        )
        
        self.assertEqual(threshold.violation_type, 'test_violation')
        self.assertEqual(threshold.max_violations, 5)
        self.assertEqual(threshold.time_window_minutes, 10)
        self.assertEqual(threshold.rollback_action, 'disable_component')
        self.assertEqual(threshold.target, 'test_component')
        self.assertTrue(threshold.enabled)
        self.assertEqual(threshold.cooldown_minutes, 5)
    
    def test_threshold_default_values(self):
        """Test threshold default values"""
        threshold = ViolationThreshold(
            violation_type='test_violation',
            max_violations=5,
            time_window_minutes=10,
            rollback_action='disable_component',
            target='test_component'
        )
        
        # Test default values
        self.assertTrue(threshold.enabled)  # Default should be True
        self.assertEqual(threshold.cooldown_minutes, 5)  # Default should be 5