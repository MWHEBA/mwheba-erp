"""
Comprehensive tests for MonitoringService.
Tests monitoring, alerting, health checks, and performance metrics.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from governance.services.monitoring_service import (
    MonitoringService,
    AlertRule,
    HealthCheck,
    PerformanceMetric,
    monitoring_service,
    record_governance_metric,
    record_governance_violation,
    get_governance_health,
    perform_component_health_check
)
from governance.services import governance_switchboard
from governance.exceptions import ValidationError, MonitoringError
from governance.models import GovernanceContext

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
        
        # Create fresh monitoring service for testing
        self.monitoring_service = MonitoringService(alert_email='admin@example.com')
        
        # Set governance context
        GovernanceContext.set_context(user=self.user, service='TestService')
    
    def tearDown(self):
        """Clean up after tests"""
        GovernanceContext.clear_context()
        # Stop monitoring to clean up background thread
        self.monitoring_service.stop_monitoring()
    
    def test_record_metric(self):
        """Test recording performance metrics"""
        metric_name = 'test_metric'
        metric_value = 42.5
        metric_unit = 'ms'
        metric_tags = {'component': 'test_component'}
        
        # Record metric
        self.monitoring_service.record_metric(
            metric_name, metric_value, metric_unit, metric_tags
        )
        
        # Verify metric was recorded
        self.assertIn(metric_name, self.monitoring_service._metrics)
        metrics = list(self.monitoring_service._metrics[metric_name])
        self.assertEqual(len(metrics), 1)
        
        recorded_metric = metrics[0]
        self.assertEqual(recorded_metric.name, metric_name)
        self.assertEqual(recorded_metric.value, metric_value)
        self.assertEqual(recorded_metric.unit, metric_unit)
        self.assertEqual(recorded_metric.tags, metric_tags)
        self.assertIsInstance(recorded_metric.timestamp, datetime)
    
    def test_record_violation(self):
        """Test recording governance violations"""
        violation_type = 'authority_violation'
        component = 'accounting_gateway'
        details = {
            'service': 'UnauthorizedService',
            'model': 'JournalEntry',
            'operation': 'CREATE'
        }
        
        # Record violation
        self.monitoring_service.record_violation(
            violation_type, component, details, self.user
        )
        
        # Verify violation counter was incremented
        self.assertEqual(self.monitoring_service._violation_counter.get_value(), 1)
        
        # Verify violation metric was recorded
        self.assertIn('governance_violations', self.monitoring_service._metrics)
        violation_metrics = list(self.monitoring_service._metrics['governance_violations'])
        self.assertEqual(len(violation_metrics), 1)
        
        violation_metric = violation_metrics[0]
        self.assertEqual(violation_metric.value, 1.0)
        self.assertEqual(violation_metric.tags['violation_type'], violation_type)
        self.assertEqual(violation_metric.tags['component'], component)
    
    @patch('governance.services.monitoring_service.governance_switchboard')
    def test_accounting_gateway_health_check(self, mock_switchboard):
        """Test AccountingGateway health check"""
        # Mock enabled component with no violations
        mock_switchboard.is_component_enabled.return_value = True
        
        # Perform health check
        health = self.monitoring_service.perform_health_check('accounting_gateway')
        
        # Verify health check result
        self.assertIsInstance(health, HealthCheck)
        self.assertEqual(health.component, 'accounting_gateway')
        self.assertEqual(health.status, 'healthy')
        self.assertIn('functioning normally', health.message)
        self.assertIsInstance(health.response_time_ms, float)
        self.assertGreater(health.response_time_ms, 0)
    
    @patch('governance.services.monitoring_service.governance_switchboard')
    def test_accounting_gateway_health_check_disabled(self, mock_switchboard):
        """Test AccountingGateway health check when disabled"""
        # Mock disabled component
        mock_switchboard.is_component_enabled.return_value = False
        
        # Perform health check
        health = self.monitoring_service.perform_health_check('accounting_gateway')
        
        # Verify health check result
        self.assertEqual(health.status, 'warning')
        self.assertIn('enforcement is disabled', health.message)
        self.assertFalse(health.details['enabled'])
    
    @patch('governance.services.monitoring_service.governance_switchboard')
    def test_accounting_gateway_health_check_with_violations(self, mock_switchboard):
        """Test AccountingGateway health check with violations"""
        # Mock enabled component
        mock_switchboard.is_component_enabled.return_value = True
        
        # Record violations to trigger warning/critical status
        for i in range(3):
            self.monitoring_service.record_metric(
                'governance_violations',
                1.0,
                'count',
                {
                    'violation_type': 'accounting_gateway_bypass',
                    'component': 'accounting_gateway'
                }
            )
        
        # Perform health check
        health = self.monitoring_service.perform_health_check('accounting_gateway')
        
        # Should be warning due to violations
        self.assertEqual(health.status, 'warning')
        self.assertIn('violations detected', health.message)
    
    @patch('governance.services.monitoring_service.governance_switchboard')
    def test_movement_service_health_check(self, mock_switchboard):
        """Test MovementService health check"""
        # Mock enabled component with no violations
        mock_switchboard.is_component_enabled.return_value = True
        
        # Perform health check
        health = self.monitoring_service.perform_health_check('movement_service')
        
        # Verify health check result
        self.assertEqual(health.component, 'movement_service')
        self.assertEqual(health.status, 'healthy')
        self.assertIn('functioning normally', health.message)
    
    @patch('governance.services.monitoring_service.governance_switchboard')
    def test_switchboard_health_check(self, mock_switchboard):
        """Test Governance Switchboard health check"""
        # Mock healthy switchboard state
        mock_stats = {
            'emergency': {
                'active': 0,
                'active_list': []
            },
            'health': {
                'governance_active': True
            }
        }
        mock_switchboard.get_governance_statistics.return_value = mock_stats
        
        # Perform health check
        health = self.monitoring_service.perform_health_check('governance_switchboard')
        
        # Verify health check result
        self.assertEqual(health.component, 'governance_switchboard')
        self.assertEqual(health.status, 'healthy')
        self.assertIn('functioning normally', health.message)
    
    @patch('governance.services.monitoring_service.governance_switchboard')
    def test_switchboard_health_check_emergency_active(self, mock_switchboard):
        """Test Switchboard health check with active emergency flags"""
        # Mock emergency active state
        mock_stats = {
            'emergency': {
                'active': 1,
                'active_list': ['emergency_disable_all_governance']
            },
            'health': {
                'governance_active': True
            }
        }
        mock_switchboard.get_governance_statistics.return_value = mock_stats
        
        # Perform health check
        health = self.monitoring_service.perform_health_check('governance_switchboard')
        
        # Should be critical due to emergency flags
        self.assertEqual(health.status, 'critical')
        self.assertIn('Emergency flags active', health.message)
    
    def test_unknown_component_health_check(self):
        """Test health check for unknown component"""
        health = self.monitoring_service.perform_health_check('unknown_component')
        
        self.assertEqual(health.component, 'unknown_component')
        self.assertEqual(health.status, 'unknown')
        self.assertIn('Unknown component', health.message)
    
    def test_health_check_exception_handling(self):
        """Test health check exception handling"""
        # Mock an exception during health check
        with patch.object(self.monitoring_service, '_check_accounting_gateway_health') as mock_check:
            mock_check.side_effect = Exception("Test exception")
            
            health = self.monitoring_service.perform_health_check('accounting_gateway')
            
            self.assertEqual(health.status, 'critical')
            self.assertIn('Health check failed', health.message)
            self.assertIn('Test exception', health.message)
    
    def test_get_system_health(self):
        """Test getting overall system health"""
        # Perform some health checks to populate data
        with patch('governance.services.monitoring_service.governance_switchboard'):
            self.monitoring_service.perform_health_check('accounting_gateway')
            self.monitoring_service.perform_health_check('movement_service')
        
        # Get system health
        health_summary = self.monitoring_service.get_system_health()
        
        # Verify health summary structure
        self.assertIn('overall_status', health_summary)
        self.assertIn('components', health_summary)
        self.assertIn('critical_count', health_summary)
        self.assertIn('warning_count', health_summary)
        self.assertIn('healthy_count', health_summary)
        self.assertIn('last_updated', health_summary)
        
        # Verify components are included
        self.assertIn('accounting_gateway', health_summary['components'])
        self.assertIn('movement_service', health_summary['components'])
    
    def test_get_metrics_summary(self):
        """Test getting metrics summary"""
        # Record some metrics
        self.monitoring_service.record_metric('test_metric_1', 10.0, 'ms')
        self.monitoring_service.record_metric('test_metric_1', 20.0, 'ms')
        self.monitoring_service.record_metric('test_metric_2', 5.0, 'count')
        
        # Get metrics summary
        summary = self.monitoring_service.get_metrics_summary(hours=1)
        
        # Verify summary structure
        self.assertIn('time_period_hours', summary)
        self.assertIn('metrics', summary)
        self.assertIn('total_violations', summary)
        self.assertIn('total_alerts', summary)
        self.assertIn('total_health_checks', summary)
        
        # Verify metrics data
        self.assertIn('test_metric_1', summary['metrics'])
        self.assertIn('test_metric_2', summary['metrics'])
        
        metric_1_data = summary['metrics']['test_metric_1']
        self.assertEqual(metric_1_data['count'], 2)
        self.assertEqual(metric_1_data['min'], 10.0)
        self.assertEqual(metric_1_data['max'], 20.0)
        self.assertEqual(metric_1_data['avg'], 15.0)
        self.assertEqual(metric_1_data['latest'], 20.0)
        self.assertEqual(metric_1_data['unit'], 'ms')
    
    def test_alert_rule_threshold_trigger(self):
        """Test that alert rules trigger correctly"""
        # Create alert rule with low threshold
        alert_rule = AlertRule(
            name='test_alert',
            condition='threshold',
            metric='test_metric',
            threshold=15.0,
            time_window_minutes=5,
            severity='warning',
            channels=['log']
        )
        
        self.monitoring_service._alert_rules = [alert_rule]
        
        with patch.object(self.monitoring_service, '_trigger_alert') as mock_trigger:
            # Record metric that exceeds threshold
            self.monitoring_service.record_metric('test_metric', 20.0)
            
            # Verify alert was triggered
            mock_trigger.assert_called_once()
            call_args = mock_trigger.call_args[0]
            self.assertEqual(call_args[0], alert_rule)
            self.assertEqual(call_args[1], 'test_metric')
            self.assertEqual(call_args[2], 20.0)
    
    def test_alert_rule_rate_trigger(self):
        """Test that rate-based alert rules trigger correctly"""
        # Create rate-based alert rule
        alert_rule = AlertRule(
            name='test_rate_alert',
            condition='rate',
            metric='test_metric',
            threshold=2.0,  # 2 per minute
            time_window_minutes=1,
            severity='error',
            channels=['log']
        )
        
        self.monitoring_service._alert_rules = [alert_rule]
        
        with patch.object(self.monitoring_service, '_trigger_alert') as mock_trigger:
            # Record metrics that exceed rate threshold
            self.monitoring_service.record_metric('test_metric', 1.0)
            self.monitoring_service.record_metric('test_metric', 1.0)
            self.monitoring_service.record_metric('test_metric', 1.0)  # This should trigger
            
            # Verify alert was triggered
            mock_trigger.assert_called()
    
    def test_alert_cooldown(self):
        """Test alert cooldown mechanism"""
        # Create alert rule with short cooldown
        alert_rule = AlertRule(
            name='test_cooldown_alert',
            condition='threshold',
            metric='test_metric',
            threshold=10.0,
            time_window_minutes=5,
            severity='warning',
            channels=['log'],
            cooldown_minutes=1
        )
        
        self.monitoring_service._alert_rules = [alert_rule]
        
        with patch.object(self.monitoring_service, '_trigger_alert') as mock_trigger:
            # First metric should trigger alert
            self.monitoring_service.record_metric('test_metric', 15.0)
            self.assertEqual(mock_trigger.call_count, 1)
            
            # Second metric immediately after should not trigger (cooldown)
            self.monitoring_service.record_metric('test_metric', 20.0)
            self.assertEqual(mock_trigger.call_count, 1)  # Still 1, not 2
    
    @patch('governance.services.monitoring_service.logger')
    def test_alert_logging(self, mock_logger):
        """Test that alerts are logged correctly"""
        alert_rule = AlertRule(
            name='test_log_alert',
            condition='threshold',
            metric='test_metric',
            threshold=10.0,
            time_window_minutes=5,
            severity='critical',
            channels=['log']
        )
        
        # Trigger alert
        self.monitoring_service._trigger_alert(alert_rule, 'test_metric', 15.0)
        
        # Verify critical log was called
        mock_logger.critical.assert_called_once()
        log_message = mock_logger.critical.call_args[0][0]
        self.assertIn('test_log_alert', log_message)
        self.assertIn('test_metric', log_message)
        self.assertIn('15.0', log_message)
    
    @patch('governance.services.monitoring_service.send_mail')
    def test_alert_email_sending(self, mock_send_mail):
        """Test that alert emails are sent correctly"""
        alert_rule = AlertRule(
            name='test_email_alert',
            condition='threshold',
            metric='test_metric',
            threshold=10.0,
            time_window_minutes=5,
            severity='error',
            channels=['email']
        )
        
        # Trigger alert
        self.monitoring_service._trigger_alert(alert_rule, 'test_metric', 15.0)
        
        # Verify email was sent
        mock_send_mail.assert_called_once()
        call_kwargs = mock_send_mail.call_args[1]
        self.assertIn('Governance Alert', call_kwargs['subject'])
        self.assertIn('ERROR', call_kwargs['subject'])
        self.assertEqual(call_kwargs['recipient_list'], ['admin@example.com'])
    
    def test_monitoring_service_initialization(self):
        """Test MonitoringService initialization"""
        service = MonitoringService(
            alert_email='test@example.com',
            external_webhook='https://example.com/webhook'
        )
        
        self.assertEqual(service.alert_email, 'test@example.com')
        self.assertEqual(service.external_webhook, 'https://example.com/webhook')
        self.assertTrue(service._monitoring_active)
        self.assertIsNotNone(service._monitoring_thread)
        
        # Clean up
        service.stop_monitoring()
    
    def test_stop_monitoring(self):
        """Test stopping monitoring service"""
        service = MonitoringService()
        
        # Verify monitoring is active
        self.assertTrue(service._monitoring_active)
        
        # Stop monitoring
        service.stop_monitoring()
        
        # Verify monitoring is stopped
        self.assertFalse(service._monitoring_active)


class TestMonitoringServiceConvenienceFunctions(TestCase):
    """Test convenience functions for monitoring service"""
    
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
    
    @patch('governance.services.monitoring_service.monitoring_service')
    def test_record_governance_metric(self, mock_service):
        """Test record_governance_metric convenience function"""
        record_governance_metric('test_metric', 42.0, 'ms', {'tag': 'value'})
        
        mock_service.record_metric.assert_called_once_with(
            'test_metric', 42.0, 'ms', {'tag': 'value'}
        )
    
    @patch('governance.services.monitoring_service.monitoring_service')
    def test_record_governance_violation_function(self, mock_service):
        """Test record_governance_violation convenience function"""
        details = {'component': 'test_component'}
        
        record_governance_violation('test_violation', 'test_component', details, self.user)
        
        mock_service.record_violation.assert_called_once_with(
            'test_violation', 'test_component', details, self.user
        )
    
    @patch('governance.services.monitoring_service.monitoring_service')
    def test_get_governance_health_function(self, mock_service):
        """Test get_governance_health convenience function"""
        mock_health = {'overall_status': 'healthy'}
        mock_service.get_system_health.return_value = mock_health
        
        result = get_governance_health()
        
        mock_service.get_system_health.assert_called_once()
        self.assertEqual(result, mock_health)
    
    @patch('governance.services.monitoring_service.monitoring_service')
    def test_perform_component_health_check_function(self, mock_service):
        """Test perform_component_health_check convenience function"""
        mock_health = HealthCheck(
            component='test_component',
            check_name='test_check',
            status='healthy',
            message='Test message',
            last_check=timezone.now(),
            response_time_ms=10.0,
            details={}
        )
        mock_service.perform_health_check.return_value = mock_health
        
        result = perform_component_health_check('test_component')
        
        mock_service.perform_health_check.assert_called_once_with('test_component')
        self.assertEqual(result, mock_health)


class TestAlertRule(TestCase):
    """Test AlertRule data class"""
    
    def test_alert_rule_creation(self):
        """Test creating an alert rule"""
        rule = AlertRule(
            name='test_alert',
            condition='threshold',
            metric='test_metric',
            threshold=10.0,
            time_window_minutes=5,
            severity='warning',
            channels=['email', 'log'],
            enabled=True,
            cooldown_minutes=2
        )
        
        self.assertEqual(rule.name, 'test_alert')
        self.assertEqual(rule.condition, 'threshold')
        self.assertEqual(rule.metric, 'test_metric')
        self.assertEqual(rule.threshold, 10.0)
        self.assertEqual(rule.time_window_minutes, 5)
        self.assertEqual(rule.severity, 'warning')
        self.assertEqual(rule.channels, ['email', 'log'])
        self.assertTrue(rule.enabled)
        self.assertEqual(rule.cooldown_minutes, 2)
    
    def test_alert_rule_defaults(self):
        """Test alert rule default values"""
        rule = AlertRule(
            name='test_alert',
            condition='threshold',
            metric='test_metric',
            threshold=10.0,
            time_window_minutes=5,
            severity='warning',
            channels=['log']
        )
        
        # Test default values
        self.assertTrue(rule.enabled)
        self.assertEqual(rule.cooldown_minutes, 5)


class TestHealthCheck(TestCase):
    """Test HealthCheck data class"""
    
    def test_health_check_creation(self):
        """Test creating a health check"""
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
        self.assertEqual(health.check_name, 'test_check')
        self.assertEqual(health.status, 'healthy')
        self.assertEqual(health.message, 'All systems operational')
        self.assertEqual(health.last_check, timestamp)
        self.assertEqual(health.response_time_ms, 15.5)
        self.assertEqual(health.details, {'key': 'value'})


class TestPerformanceMetric(TestCase):
    """Test PerformanceMetric data class"""
    
    def test_performance_metric_creation(self):
        """Test creating a performance metric"""
        timestamp = timezone.now()
        metric = PerformanceMetric(
            name='test_metric',
            value=42.5,
            unit='ms',
            timestamp=timestamp,
            tags={'component': 'test', 'environment': 'test'}
        )
        
        self.assertEqual(metric.name, 'test_metric')
        self.assertEqual(metric.value, 42.5)
        self.assertEqual(metric.unit, 'ms')
        self.assertEqual(metric.timestamp, timestamp)
        self.assertEqual(metric.tags, {'component': 'test', 'environment': 'test'})