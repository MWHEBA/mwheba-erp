"""
Comprehensive tests for MonitoringService (Simplified).
Tests health checks, violation logging, and system health status.
"""

from datetime import datetime
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from governance.services.monitoring_service import (
    MonitoringService,
    HealthCheck,
    monitoring_service,
    record_governance_metric,
    record_governance_violation,
    get_governance_health,
    perform_component_health_check
)
from governance.services import governance_switchboard

User = get_user_model()


class TestMonitoringService(TestCase):
    """Test MonitoringService functionality"""
    
    def setUp(self):
        """Set up test environment"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.monitoring_service = MonitoringService()

    def test_service_initialization(self):
        """Test monitoring service initialization"""
        service = MonitoringService(alert_email='admin@example.com')
        self.assertEqual(service.alert_email, 'admin@example.com')

    def test_record_violation(self):
        """Test recording a governance violation"""
        with patch('governance.services.monitoring_service.logger') as mock_logger:
            self.monitoring_service.record_violation(
                violation_type='UNAUTHORIZED_ACCESS',
                component='accounting_gateway',
                details={'ip': '127.0.0.1'},
                user=self.user
            )
            mock_logger.warning.assert_called_once()

    def test_perform_health_check_known_component(self):
        """Test performing health check for a known component"""
        health = self.monitoring_service.perform_health_check('accounting_gateway')
        self.assertIsInstance(health, HealthCheck)
        self.assertEqual(health.component, 'accounting_gateway')
        self.assertIn(health.status, ['healthy', 'warning', 'critical'])

    def test_perform_health_check_unknown_component(self):
        """Test performing health check for an unknown component"""
        health = self.monitoring_service.perform_health_check('unknown_comp')
        self.assertIsInstance(health, HealthCheck)
        self.assertEqual(health.component, 'unknown_comp')
        self.assertEqual(health.status, 'unknown')

    def test_get_system_health(self):
        """Test getting overall system health status"""
        self.monitoring_service.perform_health_check('accounting_gateway')
        summary = self.monitoring_service.get_system_health()
        self.assertIn('overall_status', summary)
        self.assertIn('components', summary)
        self.assertIn('accounting_gateway', summary['components'])


class TestMonitoringServiceConvenienceFunctions(TestCase):
    """Test module-level convenience functions"""

    def test_record_governance_violation(self):
        """Test record_governance_violation function"""
        with patch.object(monitoring_service, 'record_violation') as mock_record:
            record_governance_violation('TEST_VIOLATION', 'test_comp', {'data': 1})
            mock_record.assert_called_once_with('TEST_VIOLATION', 'test_comp', {'data': 1}, None)

    def test_get_governance_health(self):
        """Test get_governance_health function"""
        with patch.object(monitoring_service, 'get_system_health', return_value={'overall_status': 'healthy'}) as mock_health:
            result = get_governance_health()
            mock_health.assert_called_once()
            self.assertEqual(result, {'overall_status': 'healthy'})

    def test_perform_component_health_check(self):
        """Test perform_component_health_check function"""
        with patch.object(monitoring_service, 'perform_health_check') as mock_check:
            perform_component_health_check('audit_trail')
            mock_check.assert_called_once_with('audit_trail')

    def test_record_governance_metric(self):
        """Test record_governance_metric (no-op for performance)"""
        # Should execute without error
        record_governance_metric('test_metric', 10.0)


class TestHealthCheckDataClass(TestCase):
    """Test HealthCheck data class"""
    
    def test_health_check_creation(self):
        """Test creating a health check data class"""
        timestamp = timezone.now()
        health = HealthCheck(
            component='test_component',
            check_name='test_check',
            status='healthy',
            message='All systems operational',
            last_check=timestamp,
            response_time_ms=15.5,
            details={'key': 'value'}
        )
        self.assertEqual(health.component, 'test_component')
        self.assertEqual(health.status, 'healthy')