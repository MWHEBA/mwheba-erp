"""
Tests for simplified payroll signal governance.

This test suite validates activation, status reporting, and health checks
for payroll signal governance.
"""

from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model

from governance.services.payroll_signal_governance import (
    PayrollSignalGovernanceService,
    payroll_signal_governance,
    get_payroll_rollout_status
)

User = get_user_model()


class TestPayrollSignalGovernanceService(TestCase):
    """Test PayrollSignalGovernanceService functionality"""

    def setUp(self):
        """Set up test environment"""
        self.user = User.objects.create_user(
            username='payroll_admin',
            email='payroll@example.com',
            password='testpassword123'
        )
        self.service = PayrollSignalGovernanceService()

    def test_initial_state(self):
        """Test initial state of payroll signal governance"""
        status = self.service.get_rollout_status()
        self.assertFalse(status['governance_enabled'])

    def test_enable_payroll_signal_governance(self):
        """Test enabling payroll signal governance"""
        result = self.service.enable_payroll_signal_governance(self.user, reason="Testing enable")
        self.assertTrue(result)
        status = self.service.get_rollout_status()
        self.assertTrue(status['governance_enabled'])

    def test_disable_payroll_signal_governance(self):
        """Test disabling payroll signal governance"""
        self.service.enable_payroll_signal_governance(self.user)
        result = self.service.disable_payroll_signal_governance(self.user, reason="Testing disable")
        self.assertTrue(result)
        status = self.service.get_rollout_status()
        self.assertFalse(status['governance_enabled'])

    def test_health_status(self):
        """Test health status reporting"""
        health = self.service.get_health_status()
        self.assertIn('status', health)
        self.assertIn('governance_enabled', health)

    def test_convenience_functions(self):
        """Test module-level convenience function"""
        status = get_payroll_rollout_status()
        self.assertIn('governance_enabled', status)