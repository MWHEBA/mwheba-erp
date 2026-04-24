"""
Tests for payroll signal governance with gradual rollout.

This test suite validates the gradual rollout implementation for payroll
signal governance controls, including monitoring and rollback capabilities.
"""

import time
import threading
from unittest.mock import patch, MagicMock
from decimal import Decimal
from datetime import date

from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from governance.services.payroll_signal_governance import (
    PayrollSignalGovernanceService,
    PayrollSignalMetrics,
    RolloutConfiguration,
    payroll_signal_governance,
    should_execute_payroll_signal,
    record_payroll_signal_execution
)
from governance.signals.payroll_signals import PayrollSignalFeatureFlags
from governance.models import GovernanceContext
from hr.models import Payroll, Employee, Contract

User = get_user_model()


class PayrollSignalGovernanceTest(TestCase):
    """Test payroll signal governance with gradual rollout"""
    
    def setUp(self):
        """Set up test environment"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Create test employee and payroll
        self.employee = Employee.objects.create(
            employee_id='EMP001',
            name='أحمد محمد',
            email='ahmed@example.com',
            phone='123456789',
            is_active=True
        )
        
        self.contract = Contract.objects.create(
            employee=self.employee,
            basic_salary=Decimal('5000.00'),
            start_date=date(2024, 1, 1),
            status='active'
        )
        
        self.payroll = Payroll.objects.create(
            employee=self.employee,
            month=date(2024, 1, 1),
            contract=self.contract,
            basic_salary=Decimal('5000.00'),
            net_salary=Decimal('4500.00'),
            status='calculated',
            processed_by=self.user
        )
        
        # Reset governance service state
        self.governance_service = PayrollSignalGovernanceService()
        
        # Disable all flags initially
        PayrollSignalFeatureFlags.disable_all()
    
    def tearDown(self):
        """Clean up after tests"""
        # Disable governance to stop monitoring
        try:
            self.governance_service.disable_payroll_signal_governance(
                self.user, "Test cleanup"
            )
        except:
            pass
        
        # Reset flags
        PayrollSignalFeatureFlags.disable_all()
    
    def test_enable_payroll_signal_governance(self):
        """Test enabling payroll signal governance"""
        # Initially disabled
        self.assertFalse(self.governance_service._governance_enabled)
        
        # Enable governance
        success = self.governance_service.enable_payroll_signal_governance(
            self.user, "Test enable"
        )
        
        self.assertTrue(success)
        self.assertTrue(self.governance_service._governance_enabled)
        self.assertFalse(self.governance_service._master_kill_switch)
        self.assertTrue(PayrollSignalFeatureFlags.PAYROLL_SIGNALS_ENABLED)
        
        # Check that signals are initialized with initial rollout percentages
        status = self.governance_service.get_rollout_status()
        self.assertTrue(status['governance_enabled'])
        self.assertTrue(status['monitoring_active'])
        
        # Check individual signals
        for signal_name in self.governance_service.PAYROLL_SIGNALS:
            signal_status = status['signals'][signal_name]
            self.assertGreater(signal_status['rollout_percentage'], 0)
            self.assertTrue(signal_status['is_enabled'])
    
    def test_disable_payroll_signal_governance(self):
        """Test disabling payroll signal governance (safe rollback)"""
        # Enable first
        self.governance_service.enable_payroll_signal_governance(
            self.user, "Test setup"
        )
        
        # Disable governance
        success = self.governance_service.disable_payroll_signal_governance(
            self.user, "Test disable"
        )
        
        self.assertTrue(success)
        self.assertFalse(self.governance_service._governance_enabled)
        self.assertTrue(self.governance_service._master_kill_switch)
        self.assertFalse(PayrollSignalFeatureFlags.PAYROLL_SIGNALS_ENABLED)
        
        # Check that all signals are disabled
        status = self.governance_service.get_rollout_status()
        self.assertFalse(status['governance_enabled'])
        
        for signal_name in self.governance_service.PAYROLL_SIGNALS:
            signal_status = status['signals'][signal_name]
            self.assertEqual(signal_status['rollout_percentage'], 0)
            self.assertFalse(signal_status['is_enabled'])
    
    def test_gradual_rollout_execution_decision(self):
        """Test gradual rollout execution decision logic"""
        # Enable governance
        self.governance_service.enable_payroll_signal_governance(
            self.user, "Test setup"
        )
        
        # Test with different rollout percentages
        signal_name = 'payroll_creation_notifications'
        
        # Set to 0% - should never execute
        with self.governance_service._metrics_lock:
            self.governance_service._signal_metrics[signal_name].rollout_percentage = 0
        
        should_execute = should_execute_payroll_signal(signal_name, self.payroll.id)
        self.assertFalse(should_execute)
        
        # Set to 100% - should always execute
        with self.governance_service._metrics_lock:
            self.governance_service._signal_metrics[signal_name].rollout_percentage = 100
        
        should_execute = should_execute_payroll_signal(signal_name, self.payroll.id)
        self.assertTrue(should_execute)
        
        # Test consistent routing with same payroll ID
        with self.governance_service._metrics_lock:
            self.governance_service._signal_metrics[signal_name].rollout_percentage = 50
        
        # Should get consistent results for same payroll ID
        result1 = should_execute_payroll_signal(signal_name, self.payroll.id)
        result2 = should_execute_payroll_signal(signal_name, self.payroll.id)
        self.assertEqual(result1, result2)
    
    def test_kill_switch_functionality(self):
        """Test kill switch activation and deactivation"""
        signal_name = 'payroll_creation_notifications'
        
        # Enable governance
        self.governance_service.enable_payroll_signal_governance(
            self.user, "Test setup"
        )
        
        # Initially should execute (assuming rollout > 0)
        initial_should_execute = should_execute_payroll_signal(signal_name, self.payroll.id)
        
        # Activate kill switch
        success = self.governance_service.activate_kill_switch(
            signal_name, self.user, "Test kill switch"
        )
        
        self.assertTrue(success)
        
        # Should not execute when kill switch is active
        should_execute = should_execute_payroll_signal(signal_name, self.payroll.id)
        self.assertFalse(should_execute)
        
        # Check status
        status = self.governance_service.get_rollout_status()
        signal_status = status['signals'][signal_name]
        self.assertTrue(signal_status['kill_switch_active'])
        self.assertEqual(signal_status['rollout_percentage'], 0)
        
        # Deactivate kill switch
        success = self.governance_service.deactivate_kill_switch(
            signal_name, self.user, "Test restore"
        )
        
        self.assertTrue(success)
        
        # Should execute again (back to initial percentage)
        should_execute = should_execute_payroll_signal(signal_name, self.payroll.id)
        # Note: This might be different from initial due to hash-based routing
        
        # Check status
        status = self.governance_service.get_rollout_status()
        signal_status = status['signals'][signal_name]
        self.assertFalse(signal_status['kill_switch_active'])
        self.assertGreater(signal_status['rollout_percentage'], 0)
    
    def test_signal_execution_recording(self):
        """Test recording signal execution metrics"""
        signal_name = 'payroll_creation_notifications'
        
        # Enable governance
        self.governance_service.enable_payroll_signal_governance(
            self.user, "Test setup"
        )
        
        # Record successful execution
        record_payroll_signal_execution(signal_name, True, 0.1)
        
        # Check metrics
        with self.governance_service._metrics_lock:
            metrics = self.governance_service._signal_metrics[signal_name]
            self.assertEqual(metrics.total_executions, 1)
            self.assertEqual(metrics.successful_executions, 1)
            self.assertEqual(metrics.failed_executions, 0)
            self.assertEqual(metrics.error_rate, 0.0)
            self.assertEqual(metrics.consecutive_failures, 0)
        
        # Record failed execution
        record_payroll_signal_execution(signal_name, False, 0.2, "Test error")
        
        # Check updated metrics
        with self.governance_service._metrics_lock:
            metrics = self.governance_service._signal_metrics[signal_name]
            self.assertEqual(metrics.total_executions, 2)
            self.assertEqual(metrics.successful_executions, 1)
            self.assertEqual(metrics.failed_executions, 1)
            self.assertEqual(metrics.error_rate, 50.0)
            self.assertEqual(metrics.consecutive_failures, 1)
            self.assertEqual(metrics.last_error, "Test error")
    
    def test_automatic_rollback_on_high_error_rate(self):
        """Test automatic rollback when error rate exceeds threshold"""
        signal_name = 'payroll_creation_notifications'
        
        # Enable governance
        self.governance_service.enable_payroll_signal_governance(
            self.user, "Test setup"
        )
        
        # Set low error rate threshold for testing
        config = self.governance_service._rollout_configs[signal_name]
        config.max_error_rate = 10.0  # 10% threshold
        config.rollback_on_error = True
        
        # Record multiple failed executions to trigger rollback
        for i in range(10):
            record_payroll_signal_execution(signal_name, False, 0.1, f"Error {i}")
        
        # Check that rollback was triggered
        with self.governance_service._metrics_lock:
            metrics = self.governance_service._signal_metrics[signal_name]
            self.assertEqual(metrics.rollout_percentage, 0)
            self.assertFalse(metrics.is_enabled)
            self.assertGreater(metrics.error_rate, config.max_error_rate)
    
    def test_automatic_rollback_on_consecutive_failures(self):
        """Test automatic rollback on consecutive failures"""
        signal_name = 'payroll_creation_notifications'
        
        # Enable governance
        self.governance_service.enable_payroll_signal_governance(
            self.user, "Test setup"
        )
        
        # Set low consecutive failure threshold for testing
        config = self.governance_service._rollout_configs[signal_name]
        config.max_consecutive_failures = 2
        config.rollback_on_error = True
        
        # Record consecutive failures
        record_payroll_signal_execution(signal_name, False, 0.1, "Error 1")
        record_payroll_signal_execution(signal_name, False, 0.1, "Error 2")
        
        # Check that rollback was triggered
        with self.governance_service._metrics_lock:
            metrics = self.governance_service._signal_metrics[signal_name]
            self.assertEqual(metrics.rollout_percentage, 0)
            self.assertFalse(metrics.is_enabled)
            self.assertEqual(metrics.consecutive_failures, 2)
    
    def test_manual_promotion(self):
        """Test manual promotion of signal rollout"""
        signal_name = 'payroll_creation_notifications'
        
        # Enable governance
        self.governance_service.enable_payroll_signal_governance(
            self.user, "Test setup"
        )
        
        # Record some successful executions to meet promotion conditions
        for i in range(15):
            record_payroll_signal_execution(signal_name, True, 0.1)
        
        # Get initial percentage
        with self.governance_service._metrics_lock:
            initial_percentage = self.governance_service._signal_metrics[signal_name].rollout_percentage
        
        # Promote to 50%
        success = self.governance_service.promote_signal_rollout(
            signal_name, self.user, 50
        )
        
        self.assertTrue(success)
        
        # Check new percentage
        with self.governance_service._metrics_lock:
            new_percentage = self.governance_service._signal_metrics[signal_name].rollout_percentage
            self.assertEqual(new_percentage, 50)
            self.assertGreater(new_percentage, initial_percentage)
    
    def test_promotion_validation(self):
        """Test promotion validation conditions"""
        signal_name = 'payroll_creation_notifications'
        
        # Enable governance
        self.governance_service.enable_payroll_signal_governance(
            self.user, "Test setup"
        )
        
        # Try to promote without meeting conditions (not enough executions)
        success = self.governance_service.promote_signal_rollout(
            signal_name, self.user, 50
        )
        
        self.assertFalse(success)
        
        # Record some executions but with high error rate
        for i in range(10):
            record_payroll_signal_execution(signal_name, False, 0.1, f"Error {i}")
        
        # Try to promote with high error rate
        success = self.governance_service.promote_signal_rollout(
            signal_name, self.user, 50
        )
        
        self.assertFalse(success)
    
    def test_rollout_status_reporting(self):
        """Test comprehensive rollout status reporting"""
        # Enable governance
        self.governance_service.enable_payroll_signal_governance(
            self.user, "Test setup"
        )
        
        # Record some executions
        signal_name = 'payroll_creation_notifications'
        record_payroll_signal_execution(signal_name, True, 0.1)
        record_payroll_signal_execution(signal_name, False, 0.2, "Test error")
        
        # Get status
        status = self.governance_service.get_rollout_status()
        
        # Validate structure
        self.assertIn('governance_enabled', status)
        self.assertIn('monitoring_active', status)
        self.assertIn('signals', status)
        self.assertIn('summary', status)
        self.assertIn('counters', status)
        
        # Validate summary
        summary = status['summary']
        self.assertIn('total_signals', summary)
        self.assertIn('enabled_signals', summary)
        self.assertIn('average_error_rate', summary)
        
        # Validate signal details
        signal_status = status['signals'][signal_name]
        self.assertIn('rollout_percentage', signal_status)
        self.assertIn('metrics', signal_status)
        self.assertIn('config', signal_status)
        
        # Validate metrics
        metrics = signal_status['metrics']
        self.assertEqual(metrics['total_executions'], 2)
        self.assertEqual(metrics['successful_executions'], 1)
        self.assertEqual(metrics['failed_executions'], 1)
        self.assertEqual(metrics['error_rate'], 50.0)
    
    def test_health_status_reporting(self):
        """Test health status reporting"""
        # Get health status when disabled
        health = self.governance_service.get_health_status()
        
        self.assertIn('status', health)
        self.assertIn('issues', health)
        self.assertIn('recommendations', health)
        self.assertIn('metrics', health)
        
        # Should have issues when disabled
        self.assertIn('warning', health['status'].lower())
        self.assertGreater(len(health['issues']), 0)
        
        # Enable governance
        self.governance_service.enable_payroll_signal_governance(
            self.user, "Test setup"
        )
        
        # Get health status when enabled
        health = self.governance_service.get_health_status()
        
        # Should be healthier when enabled
        self.assertIn(health['status'].lower(), ['healthy', 'warning'])
    
    def test_thread_safety(self):
        """Test thread safety of governance operations"""
        # Enable governance
        self.governance_service.enable_payroll_signal_governance(
            self.user, "Test setup"
        )
        
        signal_name = 'payroll_creation_notifications'
        results = []
        
        def worker():
            """Worker function for thread safety test"""
            try:
                # Record executions
                for i in range(10):
                    record_payroll_signal_execution(signal_name, True, 0.1)
                
                # Check execution decision
                should_execute = should_execute_payroll_signal(signal_name, self.payroll.id)
                results.append(should_execute)
                
            except Exception as e:
                results.append(f"Error: {e}")
        
        # Run multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=worker)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads
        for thread in threads:
            thread.join()
        
        # Check that all threads completed successfully
        self.assertEqual(len(results), 5)
        for result in results:
            self.assertIsInstance(result, bool)  # Should be boolean, not error
    
    def test_configuration_validation(self):
        """Test rollout configuration validation"""
        # Test valid configuration
        valid_config = RolloutConfiguration(
            signal_name='test_signal',
            initial_percentage=10,
            increment_percentage=20,
            increment_interval_minutes=30,
            max_error_rate=5.0
        )
        
        # Should not raise exception
        self.assertEqual(valid_config.signal_name, 'test_signal')
        
        # Test invalid configurations
        with self.assertRaises(ValueError):
            RolloutConfiguration(
                signal_name='test_signal',
                initial_percentage=150  # Invalid: > 100
            )
        
        with self.assertRaises(ValueError):
            RolloutConfiguration(
                signal_name='test_signal',
                increment_interval_minutes=0  # Invalid: < 1
            )
        
        with self.assertRaises(ValueError):
            RolloutConfiguration(
                signal_name='test_signal',
                max_error_rate=150.0  # Invalid: > 100
            )
    
    @patch('governance.services.payroll_signal_governance.time.sleep')
    def test_monitoring_loop(self, mock_sleep):
        """Test background monitoring loop"""
        # Enable governance (starts monitoring)
        self.governance_service.enable_payroll_signal_governance(
            self.user, "Test setup"
        )
        
        # Verify monitoring is active
        self.assertTrue(self.governance_service._monitoring_active)
        self.assertIsNotNone(self.governance_service._monitoring_thread)
        
        # Let monitoring run briefly
        time.sleep(0.1)
        
        # Disable governance (stops monitoring)
        self.governance_service.disable_payroll_signal_governance(
            self.user, "Test cleanup"
        )
        
        # Verify monitoring is stopped
        self.assertFalse(self.governance_service._monitoring_active)
    
    def test_unknown_signal_handling(self):
        """Test handling of unknown signals"""
        unknown_signal = 'unknown_payroll_signal'
        
        # Should return True for unknown signals (allow normal execution)
        should_execute = should_execute_payroll_signal(unknown_signal, self.payroll.id)
        self.assertTrue(should_execute)
        
        # Recording execution for unknown signal should not crash
        record_payroll_signal_execution(unknown_signal, True, 0.1)
        
        # Kill switch operations should fail for unknown signals
        with self.assertRaises(Exception):
            self.governance_service.activate_kill_switch(
                unknown_signal, self.user, "Test"
            )


class PayrollSignalIntegrationTest(TestCase):
    """Integration tests for payroll signal governance"""
    
    def setUp(self):
        """Set up test environment"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Reset governance state
        PayrollSignalFeatureFlags.disable_all()
    
    def tearDown(self):
        """Clean up after tests"""
        try:
            payroll_signal_governance.disable_payroll_signal_governance(
                self.user, "Test cleanup"
            )
        except:
            pass
        
        PayrollSignalFeatureFlags.disable_all()
    
    def test_end_to_end_gradual_rollout(self):
        """Test complete end-to-end gradual rollout workflow"""
        # 1. Enable governance
        success = payroll_signal_governance.enable_payroll_signal_governance(
            self.user, "E2E test"
        )
        self.assertTrue(success)
        
        # 2. Check initial state
        status = payroll_signal_governance.get_rollout_status()
        self.assertTrue(status['governance_enabled'])
        self.assertGreater(status['summary']['enabled_signals'], 0)
        
        # 3. Simulate signal executions
        signal_name = 'payroll_creation_notifications'
        for i in range(20):
            success = i % 10 != 0  # 10% failure rate
            record_payroll_signal_execution(
                signal_name, success, 0.1, 
                f"Error {i}" if not success else None
            )
        
        # 4. Promote signal
        promotion_success = payroll_signal_governance.promote_signal_rollout(
            signal_name, self.user, 75
        )
        self.assertTrue(promotion_success)
        
        # 5. Check updated status
        status = payroll_signal_governance.get_rollout_status()
        signal_status = status['signals'][signal_name]
        self.assertEqual(signal_status['rollout_percentage'], 75)
        
        # 6. Activate kill switch
        kill_success = payroll_signal_governance.activate_kill_switch(
            signal_name, self.user, "E2E test kill switch"
        )
        self.assertTrue(kill_success)
        
        # 7. Verify kill switch effect
        should_execute = should_execute_payroll_signal(signal_name, 123)
        self.assertFalse(should_execute)
        
        # 8. Restore kill switch
        restore_success = payroll_signal_governance.deactivate_kill_switch(
            signal_name, self.user, "E2E test restore"
        )
        self.assertTrue(restore_success)
        
        # 9. Disable governance (safe rollback)
        disable_success = payroll_signal_governance.disable_payroll_signal_governance(
            self.user, "E2E test complete"
        )
        self.assertTrue(disable_success)
        
        # 10. Verify final state
        status = payroll_signal_governance.get_rollout_status()
        self.assertFalse(status['governance_enabled'])
        self.assertEqual(status['summary']['enabled_signals'], 0)
    
    def test_governance_switchboard_integration(self):
        """Test integration with governance switchboard"""
        from governance.services.governance_switchboard import governance_switchboard
        
        # Enable payroll governance through switchboard
        success = governance_switchboard.enable_component(
            'payroll_governance', 
            "Integration test", 
            self.user
        )
        self.assertTrue(success)
        
        # Check that component is enabled
        is_enabled = governance_switchboard.is_component_enabled('payroll_governance')
        self.assertTrue(is_enabled)
        
        # Enable payroll signal governance
        signal_success = payroll_signal_governance.enable_payroll_signal_governance(
            self.user, "Integration test"
        )
        self.assertTrue(signal_success)
        
        # Check governance statistics
        stats = governance_switchboard.get_governance_statistics()
        self.assertIn('payroll_governance', stats['components']['enabled_list'])
        
        # Disable through switchboard
        disable_success = governance_switchboard.disable_component(
            'payroll_governance',
            "Integration test cleanup",
            self.user
        )
        self.assertTrue(disable_success)