"""
✅ PHASE 7: Simplified Monitoring System
Consolidated monitoring functionality for production readiness
"""
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from django.db.models import Count, Avg
from django.db import connection
from django.core.cache import cache
from core.models import Alert, AlertRule, UnifiedLog

logger = logging.getLogger(__name__)


class SimpleMonitoringService:
    """
    ✅ SIMPLIFIED: Basic monitoring service
    Essential monitoring functionality without complex features
    """
    
    def check_system_health(self) -> Dict[str, Any]:
        """Basic system health check"""
        health_status = {
            'status': 'healthy',
            'timestamp': time.time(),
            'checks': {}
        }
        
        # Database check
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            health_status['checks']['database'] = {'status': 'healthy'}
        except Exception as e:
            health_status['checks']['database'] = {'status': 'unhealthy', 'error': str(e)}
            health_status['status'] = 'unhealthy'
            logger.error(f"Database health check failed: {e}")
        
        # Cache check (optional)
        try:
            cache.set('health_check_test', 'ok', 10)
            cached_value = cache.get('health_check_test')
            if cached_value == 'ok':
                health_status['checks']['cache'] = {'status': 'healthy'}
            else:
                health_status['checks']['cache'] = {'status': 'degraded'}
        except Exception as e:
            health_status['checks']['cache'] = {'status': 'degraded', 'error': str(e)}
            logger.warning(f"Cache health check failed: {e}")
        
        return health_status
    
    def log_system_event(self, level: str, message: str, user=None, category='general', **extra_data):
        """Log system event using UnifiedLog"""
        try:
            UnifiedLog.log_system(
                level=level,
                message=message,
                user=user,
                category=category,
                **extra_data
            )
        except Exception as e:
            logger.error(f"Failed to log system event: {e}")
    
    def log_security_event(self, event_type: str, user=None, success=False, severity='medium', **extra_data):
        """Log security event using UnifiedLog"""
        try:
            UnifiedLog.log_security(
                event_type=event_type,
                user=user,
                success=success,
                severity=severity,
                **extra_data
            )
        except Exception as e:
            logger.error(f"Failed to log security event: {e}")
    
    def log_performance_metric(self, metric_name: str, metric_value: float, unit='ms', threshold=None, **extra_data):
        """Log performance metric using UnifiedLog"""
        try:
            UnifiedLog.log_performance(
                metric_name=metric_name,
                metric_value=metric_value,
                unit=unit,
                threshold=threshold,
                **extra_data
            )
        except Exception as e:
            logger.error(f"Failed to log performance metric: {e}")
    
    def log_audit_event(self, user, action: str, resource_type: str, resource_id: str, **extra_data):
        """Log audit event using UnifiedLog"""
        try:
            UnifiedLog.log_audit(
                user=user,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                **extra_data
            )
        except Exception as e:
            logger.error(f"Failed to log audit event: {e}")


class SimpleAlertingService:
    """
    ✅ SIMPLIFIED: Basic alerting service
    Essential alerting functionality without complex escalation
    """
    
    def check_alert_rules(self) -> List[Dict[str, Any]]:
        """Check active alert rules and trigger alerts if needed"""
        triggered_alerts = []
        active_rules = AlertRule.objects.filter(is_active=True)
        
        for rule in active_rules:
            try:
                if self._should_trigger_alert(rule):
                    alert = self._create_alert(rule)
                    if alert:
                        triggered_alerts.append({
                            'rule': rule.name,
                            'alert_id': alert.id,
                            'severity': rule.severity,
                            'message': alert.message
                        })
                        
                        # Send notification
                        self._send_alert_notification(alert)
                        
            except Exception as e:
                logger.error(f"Error evaluating alert rule {rule.name}: {e}")
        
        return triggered_alerts
    
    def _should_trigger_alert(self, rule: AlertRule) -> bool:
        """Simple alert rule evaluation"""
        time_window_start = timezone.now() - timedelta(minutes=rule.time_window_minutes)
        
        # Get metric value based on rule type
        metric_value = self._get_metric_value(rule.metric_type, time_window_start)
        
        if metric_value is None:
            return False
        
        # Simple condition evaluation
        if rule.operator == 'gt':
            return metric_value > rule.threshold_value
        elif rule.operator == 'lt':
            return metric_value < rule.threshold_value
        elif rule.operator == 'eq':
            return metric_value == rule.threshold_value
        
        return False
    
    def _get_metric_value(self, metric_type: str, since: datetime) -> Optional[float]:
        """Get current metric value for evaluation"""
        try:
            if metric_type == 'error_rate':
                total_logs = UnifiedLog.objects.filter(timestamp__gte=since).count()
                error_logs = UnifiedLog.objects.filter(
                    timestamp__gte=since,
                    level__in=['ERROR', 'CRITICAL']
                ).count()
                return (error_logs / total_logs * 100) if total_logs > 0 else 0
            
            elif metric_type == 'failed_logins':
                return UnifiedLog.objects.filter(
                    timestamp__gte=since,
                    log_type='security',
                    data__event_type='authentication',
                    data__success=False
                ).count()
            
            elif metric_type == 'concurrent_users':
                return UnifiedLog.objects.filter(
                    timestamp__gte=since,
                    user__isnull=False
                ).values('user').distinct().count()
            
            return None
                
        except Exception as e:
            logger.error(f"Error getting metric value for {metric_type}: {e}")
            return None
    
    def _create_alert(self, rule: AlertRule) -> Optional[Alert]:
        """Create a new alert instance"""
        try:
            # Check if there's already an active alert for this rule
            existing_alert = Alert.objects.filter(
                rule=rule,
                status='active',
                created_at__gte=timezone.now() - timedelta(minutes=rule.time_window_minutes)
            ).first()
            
            if existing_alert:
                return None  # Don't create duplicate alerts
            
            # Get current metric value
            time_window_start = timezone.now() - timedelta(minutes=rule.time_window_minutes)
            metric_value = self._get_metric_value(rule.metric_type, time_window_start)
            
            alert = Alert.objects.create(
                rule=rule,
                message=f"{rule.name}: {rule.metric_type} is {metric_value} (threshold: {rule.threshold_value})",
                metric_value=metric_value or 0,
                threshold_value=rule.threshold_value
            )
            
            logger.warning(f"Alert triggered: {rule.name}")
            return alert
            
        except Exception as e:
            logger.error(f"Error creating alert for rule {rule.name}: {e}")
            return None
    
    def _send_alert_notification(self, alert: Alert) -> bool:
        """Send basic alert notification via email"""
        try:
            if not alert.rule.email_recipients:
                return False
                
            recipients = [email.strip() for email in alert.rule.email_recipients.split(',') if email.strip()]
            
            if not recipients:
                return False
            
            subject = f"[{alert.rule.severity.upper()}] System Alert: {alert.rule.name}"
            message = f"""
System Alert Triggered

Rule: {alert.rule.name}
Severity: {alert.rule.severity.upper()}
Message: {alert.message}
Time: {alert.created_at}

Please check the system dashboard for more details.
            """
            
            # Send simple email
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=recipients,
                fail_silently=True
            )
            
            logger.info(f"Alert notification sent for {alert.rule.name}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending alert notification: {e}")
            return False


# Global service instances
monitoring_service = SimpleMonitoringService()
alerting_service = SimpleAlertingService()


def check_system_health() -> Dict[str, Any]:
    """Convenience function to check system health"""
    return monitoring_service.check_system_health()


def trigger_alert_check() -> List[Dict[str, Any]]:
    """Convenience function to trigger alert checks"""
    return alerting_service.check_alert_rules()


def log_system_event(level: str, message: str, user=None, category='general', **extra_data):
    """Convenience function to log system events"""
    return monitoring_service.log_system_event(level, message, user, category, **extra_data)


def log_security_event(event_type: str, user=None, success=False, severity='medium', **extra_data):
    """Convenience function to log security events"""
    return monitoring_service.log_security_event(event_type, user, success, severity, **extra_data)


def log_performance_metric(metric_name: str, metric_value: float, unit='ms', threshold=None, **extra_data):
    """Convenience function to log performance metrics"""
    return monitoring_service.log_performance_metric(metric_name, metric_value, unit, threshold, **extra_data)


def log_audit_event(user, action: str, resource_type: str, resource_id: str, **extra_data):
    """Convenience function to log audit events"""
    return monitoring_service.log_audit_event(user, action, resource_type, resource_id, **extra_data)