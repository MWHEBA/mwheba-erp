"""
Test workflow-level feature flags implementation.
Tests for task 7.2: Create workflow-level feature flags (Critical for Phase 2 & 5)
"""

import pytest
from django.test import TestCase
from django.contrib.auth import get_user_model
from unittest.mock import patch, MagicMock

from governance.services import (
    governance_switchboard,
    is_workflow_enabled,
    enable_workflow,
    disable_workflow
)
from governance.exceptions import ValidationError

User = get_user_model()


class WorkflowFlagsTest(TestCase):
    """Test workflow-level feature flags for critical Phase 2 & 5 workflows"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='test_admin',
            email='admin@test.com',
            password='testpass123',
            is_superuser=True
        )
        
        # Reset switchboard to defaults
        governance_switchboard._initialize_flags()
    
    def test_critical_workflow_flags_exist(self):
        """Test that all required workflow flags are defined"""
        required_workflows = [
            'student_fee_to_journal_entry',
            'stock_movement_to_journal_entry', 
            'fee_payment_to_journal_entry'
        ]
        
        for workflow in required_workflows:
            self.assertIn(workflow, governance_switchboard.WORKFLOW_FLAGS)
            
            # Check workflow configuration
            config = governance_switchboard.WORKFLOW_FLAGS[workflow]
            self.assertIn('name', config)
            self.assertIn('description', config)
            self.assertIn('critical', config)
            self.assertIn('risk_level', config)
            self.assertIn('corruption_prevention', config)
            
            # All these workflows should be critical and high risk
            self.assertTrue(config['critical'])
            self.assertEqual(config['risk_level'], 'HIGH')
    
    def test_student_fee_workflow_flag(self):
        """Test StudentFee → JournalEntry workflow flag"""
        workflow_name = 'student_fee_to_journal_entry'
        
        # Should be disabled by default
        self.assertFalse(is_workflow_enabled(workflow_name))
        
        # Enable workflow
        result = enable_workflow(workflow_name, "Test enable", self.user)
        self.assertTrue(result)
        self.assertTrue(is_workflow_enabled(workflow_name))
        
        # Disable workflow
        result = disable_workflow(workflow_name, "Test disable", self.user)
        self.assertTrue(result)
        self.assertFalse(is_workflow_enabled(workflow_name))
    
    def test_stock_movement_workflow_flag(self):
        """Test StockMovement → JournalEntry workflow flag"""
        workflow_name = 'stock_movement_to_journal_entry'
        
        # Should be disabled by default
        self.assertFalse(is_workflow_enabled(workflow_name))
        
        # Enable workflow
        result = enable_workflow(workflow_name, "Test enable", self.user)
        self.assertTrue(result)
        self.assertTrue(is_workflow_enabled(workflow_name))
        
        # Disable workflow
        result = disable_workflow(workflow_name, "Test disable", self.user)
        self.assertTrue(result)
        self.assertFalse(is_workflow_enabled(workflow_name))
    
    def test_fee_payment_workflow_flag(self):
        """Test FeePayment → JournalEntry workflow flag"""
        workflow_name = 'fee_payment_to_journal_entry'
        
        # Should be disabled by default
        self.assertFalse(is_workflow_enabled(workflow_name))
        
        # Enable workflow
        result = enable_workflow(workflow_name, "Test enable", self.user)
        self.assertTrue(result)
        self.assertTrue(is_workflow_enabled(workflow_name))
        
        # Disable workflow
        result = disable_workflow(workflow_name, "Test disable", self.user)
        self.assertTrue(result)
        self.assertFalse(is_workflow_enabled(workflow_name))
    
    def test_workflow_component_dependencies(self):
        """Test that workflows have proper component dependencies"""
        # StudentFee workflow should depend on accounting_gateway_enforcement
        config = governance_switchboard.WORKFLOW_FLAGS['student_fee_to_journal_entry']
        self.assertIn('accounting_gateway_enforcement', config['component_dependencies'])
        
        # StockMovement workflow should depend on both movement and accounting services
        config = governance_switchboard.WORKFLOW_FLAGS['stock_movement_to_journal_entry']
        self.assertIn('movement_service_enforcement', config['component_dependencies'])
        self.assertIn('accounting_gateway_enforcement', config['component_dependencies'])
        
        # FeePayment workflow should depend on accounting_gateway_enforcement
        config = governance_switchboard.WORKFLOW_FLAGS['fee_payment_to_journal_entry']
        self.assertIn('accounting_gateway_enforcement', config['component_dependencies'])
    
    def test_workflow_dependency_validation(self):
        """Test that workflow dependencies are validated"""
        # Try to enable workflow without enabling its component dependencies
        workflow_name = 'student_fee_to_journal_entry'
        
        # Should fail because accounting_gateway_enforcement is not enabled
        result = enable_workflow(workflow_name, "Test without deps", self.user)
        self.assertFalse(result)
        self.assertFalse(is_workflow_enabled(workflow_name))
        
        # Enable the component dependency first
        from governance.services import enable_component
        enable_component('accounting_gateway_enforcement', "Enable for test", self.user)
        
        # Now workflow should enable successfully
        result = enable_workflow(workflow_name, "Test with deps", self.user)
        self.assertTrue(result)
        self.assertTrue(is_workflow_enabled(workflow_name))
    
    def test_individual_workflow_monitoring(self):
        """Test individual workflow monitoring capability"""
        # Enable a workflow
        workflow_name = 'student_fee_to_journal_entry'
        enable_workflow(workflow_name, "Test monitoring", self.user)
        
        # Get governance statistics
        stats = governance_switchboard.get_governance_statistics()
        
        # Check workflow statistics
        self.assertIn('workflows', stats)
        self.assertIn('enabled_list', stats['workflows'])
        self.assertIn(workflow_name, stats['workflows']['enabled_list'])
        
        # Check high-risk workflow monitoring
        self.assertIn('high_risk_enabled', stats['workflows'])
        self.assertIn('high_risk_enabled_list', stats['workflows'])
        self.assertIn(workflow_name, stats['workflows']['high_risk_enabled_list'])
    
    def test_workflow_rollback_capability(self):
        """Test workflow rollback capability"""
        workflow_name = 'fee_payment_to_journal_entry'
        
        # Enable workflow
        enable_workflow(workflow_name, "Test rollback", self.user)
        self.assertTrue(is_workflow_enabled(workflow_name))
        
        # Use temporary override to disable (rollback simulation)
        with governance_switchboard.temporary_flag_override(
            'workflow', workflow_name, False, "Temporary rollback test"
        ):
            self.assertFalse(is_workflow_enabled(workflow_name))
        
        # Should be back to enabled after context manager
        self.assertTrue(is_workflow_enabled(workflow_name))
    
    def test_emergency_workflow_disable(self):
        """Test emergency disable of workflows"""
        # Enable all critical workflows
        critical_workflows = [
            'student_fee_to_journal_entry',
            'stock_movement_to_journal_entry',
            'fee_payment_to_journal_entry'
        ]
        
        # Enable component dependencies first
        from governance.services import enable_component
        enable_component('accounting_gateway_enforcement', "Test emergency", self.user)
        enable_component('movement_service_enforcement', "Test emergency", self.user)
        
        # Enable workflows
        for workflow in critical_workflows:
            enable_workflow(workflow, "Test emergency", self.user)
            self.assertTrue(is_workflow_enabled(workflow))
        
        # Activate emergency disable for accounting
        from governance.services import activate_emergency
        activate_emergency(
            'emergency_disable_accounting', 
            "Test emergency disable", 
            self.user
        )
        
        # All accounting-related workflows should be disabled
        accounting_workflows = [
            'student_fee_to_journal_entry',
            'stock_movement_to_journal_entry',
            'fee_payment_to_journal_entry'
        ]
        
        for workflow in accounting_workflows:
            self.assertFalse(is_workflow_enabled(workflow))
    
    def test_workflow_corruption_prevention_mapping(self):
        """Test that workflows have proper corruption prevention mapping"""
        # StudentFee workflow should prevent orphaned entries and unbalanced entries
        config = governance_switchboard.WORKFLOW_FLAGS['student_fee_to_journal_entry']
        corruption_prevention = config['corruption_prevention']
        self.assertIn('orphaned_journal_entries', corruption_prevention)
        self.assertIn('unbalanced_entries', corruption_prevention)
        
        # StockMovement workflow should prevent negative stock and orphaned entries
        config = governance_switchboard.WORKFLOW_FLAGS['stock_movement_to_journal_entry']
        corruption_prevention = config['corruption_prevention']
        self.assertIn('negative_stock', corruption_prevention)
        self.assertIn('orphaned_journal_entries', corruption_prevention)
        
        # FeePayment workflow should prevent payment sync corruption and orphaned entries
        config = governance_switchboard.WORKFLOW_FLAGS['fee_payment_to_journal_entry']
        corruption_prevention = config['corruption_prevention']
        self.assertIn('payment_sync_corruption', corruption_prevention)
        self.assertIn('orphaned_journal_entries', corruption_prevention)
    
    def test_invalid_workflow_name(self):
        """Test handling of invalid workflow names"""
        with self.assertRaises(ValidationError):
            enable_workflow('invalid_workflow_name', "Test invalid", self.user)
        
        # is_workflow_enabled should return False for invalid names (not raise exception)
        self.assertFalse(is_workflow_enabled('invalid_workflow_name'))
    
    def test_workflow_flag_persistence(self):
        """Test that workflow flags persist across switchboard instances"""
        workflow_name = 'student_fee_to_journal_entry'
        
        # Enable workflow
        enable_workflow(workflow_name, "Test persistence", self.user)
        self.assertTrue(is_workflow_enabled(workflow_name))
        
        # Create new switchboard instance (simulates restart)
        from governance.services.governance_switchboard import GovernanceSwitchboard
        new_switchboard = GovernanceSwitchboard()
        
        # Flag should still be enabled (cached)
        self.assertTrue(new_switchboard.is_workflow_enabled(workflow_name))


class WorkflowIntegrationTest(TestCase):
    """Integration tests for workflow flags with other governance components"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='test_admin',
            email='admin@test.com', 
            password='testpass123',
            is_superuser=True
        )
        
        # Reset switchboard to defaults
        governance_switchboard._initialize_flags()
    
    def test_workflow_audit_logging(self):
        """Test that workflow flag changes are properly audited"""
        workflow_name = 'student_fee_to_journal_entry'
        
        # Enable audit logging
        governance_switchboard.enable_audit = True
        
        with patch('governance.services.audit_service.AuditService.log_operation') as mock_audit:
            # Enable workflow
            enable_workflow(workflow_name, "Test audit", self.user)
            
            # Verify audit was called
            mock_audit.assert_called()
            call_args = mock_audit.call_args
            
            # Check audit parameters
            self.assertEqual(call_args[1]['operation'], 'WORKFLOW_ENABLED')
            self.assertEqual(call_args[1]['source_service'], 'GovernanceSwitchboard')
            self.assertEqual(call_args[1]['user'], self.user)
            
            # Check audit data
            after_data = call_args[1]['after_data']
            self.assertEqual(after_data['workflow'], workflow_name)
            self.assertTrue(after_data['enabled'])
            self.assertEqual(after_data['reason'], "Test audit")
    
    def test_workflow_statistics_integration(self):
        """Test workflow statistics integration"""
        # Enable some workflows
        from governance.services import enable_component
        enable_component('accounting_gateway_enforcement', "Test stats", self.user)
        
        enable_workflow('student_fee_to_journal_entry', "Test stats", self.user)
        enable_workflow('fee_payment_to_journal_entry', "Test stats", self.user)
        
        # Get statistics
        stats = governance_switchboard.get_governance_statistics()
        
        # Verify workflow statistics
        self.assertEqual(stats['workflows']['enabled'], 2)
        self.assertEqual(stats['workflows']['high_risk_enabled'], 2)
        self.assertIn('student_fee_to_journal_entry', stats['workflows']['enabled_list'])
        self.assertIn('fee_payment_to_journal_entry', stats['workflows']['enabled_list'])
        
        # Verify health status
        self.assertTrue(stats['health']['governance_active'])
        self.assertTrue(stats['health']['critical_workflows_protected'])
    
    def test_workflow_configuration_validation(self):
        """Test workflow configuration validation"""
        errors = governance_switchboard.validate_configuration()
        
        # Should have no configuration errors
        self.assertEqual(len(errors), 0)
        
        # All required workflow flags should be properly configured
        required_workflows = [
            'student_fee_to_journal_entry',
            'stock_movement_to_journal_entry',
            'fee_payment_to_journal_entry'
        ]
        
        for workflow in required_workflows:
            config = governance_switchboard.WORKFLOW_FLAGS[workflow]
            
            # Required fields should be present
            self.assertIsNotNone(config.get('name'))
            self.assertIsNotNone(config.get('description'))
            self.assertIsInstance(config.get('default'), bool)
            self.assertIsInstance(config.get('critical'), bool)
            self.assertIn('component_dependencies', config)
            self.assertIn('risk_level', config)
            self.assertIn('corruption_prevention', config)