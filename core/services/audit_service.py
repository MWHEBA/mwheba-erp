"""
خدمة التدقيق والمراقبة الشاملة للنظام الموحد
Comprehensive Audit and Monitoring Service for the Unified System
"""

import json
import time
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union, Callable
from django.conf import settings
from django.utils import timezone
from django.db import models, transaction
from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
import logging

from utils.models import SystemLog
from core.utils import get_default_currency
from utils.logs import AuditLogHandler, SecurityLogHandler, SystemLogHandler

logger = logging.getLogger(__name__)
User = get_user_model()


class AuditService:
    """
    خدمة التدقيق والمراقبة الشاملة
    Comprehensive Audit and Monitoring Service
    """
    
    # Audit event types
    EVENT_CREATE = "create"
    EVENT_UPDATE = "update"
    EVENT_DELETE = "delete"
    EVENT_LOGIN = "login"
    EVENT_LOGOUT = "logout"
    EVENT_ACCESS = "access"
    EVENT_EXPORT = "export"
    EVENT_IMPORT = "import"
    EVENT_FINANCIAL = "financial"
    EVENT_ACADEMIC = "academic"
    EVENT_SECURITY = "security"
    EVENT_SYSTEM = "system"
    
    # Risk levels
    RISK_LOW = "low"
    RISK_MEDIUM = "medium"
    RISK_HIGH = "high"
    RISK_CRITICAL = "critical"
    
    def __init__(self):
        """Initialize the audit service"""
        self.audit_handler = AuditLogHandler()
        self.security_handler = SecurityLogHandler()
        self.system_handler = SystemLogHandler()
        
        # Performance metrics storage
        self.performance_metrics = {
            'response_times': [],
            'database_queries': [],
            'cache_hits': 0,
            'cache_misses': 0,
            'active_users': set(),
            'error_count': 0
        }
        
        # Thread lock for thread-safe operations
        self._lock = threading.Lock()
        
        # Initialize monitoring
        self._setup_monitoring()
    
    def _setup_monitoring(self):
        """Setup system monitoring"""
        try:
            # Connect to Django signals for automatic auditing
            self._connect_model_signals()
            logger.info("Audit service monitoring initialized")
        except Exception as e:
            logger.error(f"Error setting up audit monitoring: {str(e)}")
    
    def _connect_model_signals(self):
        """Connect to Django model signals for automatic auditing"""
        # This will be called when models are saved/deleted
        # We'll implement specific model monitoring in the actual usage
        pass
    
    def log_user_action(self, user: User, action: str, model_name: str = None, 
                       object_id: str = None, details: Dict = None, 
                       ip_address: str = None, risk_level: str = RISK_LOW) -> Dict:
        """
        Log a user action with comprehensive details
        
        Args:
            user: User performing the action
            action: Action being performed
            model_name: Name of the model being affected
            object_id: ID of the object being affected
            details: Additional details about the action
            ip_address: IP address of the user
            risk_level: Risk level of the action
            
        Returns:
            dict: Audit log entry
        """
        try:
            with self._lock:
                # Ensure we have a valid username
                safe_username = user.username.encode('ascii', 'ignore').decode('ascii') if user else 'system'
                if not safe_username and user:
                    safe_username = f"user_{user.id}"
                elif not safe_username:
                    safe_username = 'system'
                
                audit_entry = {
                    'timestamp': timezone.now().isoformat(),
                    'user_id': user.id if user else None,
                    'username': safe_username,
                    'action': action,
                    'model_name': model_name,
                    'object_id': str(object_id) if object_id else None,
                    'details': details or {},
                    'ip_address': ip_address,
                    'risk_level': risk_level,
                    'session_key': getattr(user, 'session_key', None) if user else None
                }
                
                # Log to audit handler
                self.audit_handler.log_data_change(
                    action=action,
                    user=user,
                    model=model_name,
                    object_id=object_id,
                    old_data=details.get('old_data') if details else None,
                    new_data=details.get('new_data') if details else None
                )
                
                # Store in database
                try:
                    system_log = SystemLog.objects.create(
                        user=user,
                        action=action,
                        model_name=model_name,
                        object_id=str(object_id) if object_id else None,
                        details=json.dumps(details or {}, cls=DjangoJSONEncoder, ensure_ascii=False),
                        ip_address=ip_address
                    )
                    logger.debug(f"Successfully stored audit log in database: {system_log.id}")
                except Exception as db_error:
                    logger.error(f"Error storing audit log in database: {str(db_error)}")
                    logger.error(f"User: {user}, Action: {action}, Model: {model_name}, Object ID: {object_id}")
                    # Don't fail the entire audit process due to database issues
                    pass
                
                # Log high-risk actions to security handler
                if risk_level in [self.RISK_HIGH, self.RISK_CRITICAL]:
                    self.security_handler.log_security_event(
                        event_type=f"high_risk_{action}",
                        user=user,
                        ip_address=ip_address,
                        details=details
                    )
                
                logger.debug(f"Audit log created: {action} by {user.username if user else 'system'}")
                return audit_entry
                
        except Exception as e:
            logger.error(f"Error logging user action: {str(e)}")
            # Return a minimal audit entry instead of empty dict
            safe_username = 'system'
            if user:
                safe_username = user.username.encode('ascii', 'ignore').decode('ascii')
                if not safe_username:
                    safe_username = f"user_{user.id}"
            
            return {
                'timestamp': timezone.now().isoformat(),
                'user_id': user.id if user else None,
                'username': safe_username,
                'action': action,
                'model_name': model_name,
                'object_id': str(object_id) if object_id else None,
                'details': details or {},
                'ip_address': ip_address,
                'risk_level': risk_level,
                'error': str(e)
            }
    
    def log_financial_transaction(self, user: User, transaction_type: str, 
                                amount: float, account_from: str = None, 
                                account_to: str = None, reference: str = None,
                                ip_address: str = None) -> Dict:
        """
        Log financial transactions with enhanced security
        
        Args:
            user: User performing the transaction
            transaction_type: Type of financial transaction
            amount: Transaction amount
            account_from: Source account
            account_to: Destination account
            reference: Transaction reference
            ip_address: User's IP address
            
        Returns:
            dict: Financial audit log entry
        """
        try:
            financial_details = {
                'transaction_type': transaction_type,
                'amount': float(amount),
                'account_from': account_from,
                'account_to': account_to,
                'reference': reference,
                'currency': get_default_currency()
            }
            
            # Determine risk level based on amount
            risk_level = self.RISK_LOW
            if amount > 10000:
                risk_level = self.RISK_CRITICAL
            elif amount > 5000:
                risk_level = self.RISK_HIGH
            elif amount > 1000:
                risk_level = self.RISK_MEDIUM
            
            return self.log_user_action(
                user=user,
                action=self.EVENT_FINANCIAL,
                model_name='FinancialTransaction',
                object_id=reference,
                details=financial_details,
                ip_address=ip_address,
                risk_level=risk_level
            )
            
        except Exception as e:
            logger.error(f"Error logging financial transaction: {str(e)}")
            return {}
    
    def log_customer_action(self, user: User, action: str, customer_id: str = None,
                          details: Dict = None,
                          ip_address: str = None) -> Dict:
        """
        Log customer-related actions
        """
        try:
            customer_details = {
                'action': action,
                'customer_id': customer_id,
                'additional_details': details or {}
            }
            
            return self.log_user_action(
                user=user,
                action=self.EVENT_ACADEMIC,
                model_name='CustomerAction',
                object_id=customer_id,
                details=customer_details,
                ip_address=ip_address,
                risk_level=self.RISK_MEDIUM if action in ['payment', 'refund'] else self.RISK_LOW
            )
            
        except Exception as e:
            logger.error(f"Error logging customer action: {str(e)}")
            return {}
    
    def log_security_event(self, event_type: str, user: User = None, 
                          ip_address: str = None, details: Dict = None,
                          risk_level: str = RISK_HIGH) -> Dict:
        """
        Log security-related events
        
        Args:
            event_type: Type of security event
            user: User involved (if any)
            ip_address: IP address involved
            details: Additional security details
            risk_level: Risk level of the event
            
        Returns:
            dict: Security audit log entry
        """
        try:
            security_details = {
                'security_event_type': event_type,
                'threat_level': risk_level,
                'additional_details': details or {}
            }
            
            # Log to security handler
            self.security_handler.log_security_event(
                event_type=event_type,
                user=user,
                ip_address=ip_address,
                details=security_details
            )
            
            return self.log_user_action(
                user=user,
                action=self.EVENT_SECURITY,
                model_name='SecurityEvent',
                object_id=None,
                details=security_details,
                ip_address=ip_address,
                risk_level=risk_level
            )
            
        except Exception as e:
            logger.error(f"Error logging security event: {str(e)}")
            return {}
    
    def track_performance_metric(self, metric_type: str, value: float, 
                               context: Dict = None) -> bool:
        """
        Track system performance metrics
        
        Args:
            metric_type: Type of performance metric
            value: Metric value
            context: Additional context information
            
        Returns:
            bool: True if successful
        """
        try:
            with self._lock:
                timestamp = timezone.now()
                
                metric_entry = {
                    'timestamp': timestamp.isoformat(),
                    'metric_type': metric_type,
                    'value': float(value),
                    'context': context or {}
                }
                
                # Store different types of metrics
                if metric_type == 'response_time':
                    self.performance_metrics['response_times'].append(metric_entry)
                    # Keep only last 1000 entries
                    if len(self.performance_metrics['response_times']) > 1000:
                        self.performance_metrics['response_times'] = self.performance_metrics['response_times'][-1000:]
                
                elif metric_type == 'database_query':
                    self.performance_metrics['database_queries'].append(metric_entry)
                    # Keep only last 500 entries
                    if len(self.performance_metrics['database_queries']) > 500:
                        self.performance_metrics['database_queries'] = self.performance_metrics['database_queries'][-500:]
                
                elif metric_type == 'cache_hit':
                    self.performance_metrics['cache_hits'] += 1
                
                elif metric_type == 'cache_miss':
                    self.performance_metrics['cache_misses'] += 1
                
                elif metric_type == 'error':
                    self.performance_metrics['error_count'] += 1
                
                # Log performance issues
                if metric_type == 'response_time' and value > 3.0:  # Slow response
                    self.log_security_event(
                        event_type='performance_degradation',
                        details={
                            'metric_type': metric_type,
                            'value': value,
                            'threshold': 3.0,
                            'context': context
                        },
                        risk_level=self.RISK_MEDIUM
                    )
                
                return True
                
        except Exception as e:
            logger.error(f"Error tracking performance metric: {str(e)}")
            return False
    
    def get_audit_trail(self, user_id: int = None, action: str = None,
                       model_name: str = None, start_date: datetime = None,
                       end_date: datetime = None, risk_level: str = None,
                       limit: int = 100) -> List[Dict]:
        """
        Retrieve audit trail with filtering options
        
        Args:
            user_id: Filter by user ID
            action: Filter by action type
            model_name: Filter by model name
            start_date: Start date for filtering
            end_date: End date for filtering
            risk_level: Filter by risk level
            limit: Maximum number of results
            
        Returns:
            list: Filtered audit trail entries
        """
        try:
            # Build query
            query = SystemLog.objects.all()
            
            if user_id:
                query = query.filter(user_id=user_id)
            
            if action:
                query = query.filter(action=action)
            
            if model_name:
                query = query.filter(model_name=model_name)
            
            if start_date:
                query = query.filter(timestamp__gte=start_date)
            
            if end_date:
                query = query.filter(timestamp__lte=end_date)
            
            # Order by timestamp (newest first) and limit
            logs = query.order_by('-timestamp')[:limit]
            
            # Convert to dictionaries
            audit_trail = []
            for log in logs:
                entry = {
                    'id': log.id,
                    'timestamp': log.timestamp.isoformat(),
                    'user_id': log.user_id,
                    'username': log.user.username if log.user else 'system',
                    'action': log.action,
                    'model_name': log.model_name,
                    'object_id': log.object_id,
                    'ip_address': log.ip_address,
                    'details': {}
                }
                
                # Parse details JSON
                if log.details:
                    try:
                        entry['details'] = json.loads(log.details)
                    except:
                        entry['details'] = {'raw': log.details}
                
                # Filter by risk level if specified
                if risk_level:
                    entry_risk = entry['details'].get('risk_level', self.RISK_LOW)
                    if entry_risk != risk_level:
                        continue
                
                audit_trail.append(entry)
            
            return audit_trail
            
        except Exception as e:
            logger.error(f"Error retrieving audit trail: {str(e)}")
            return []
    
    def get_performance_dashboard(self) -> Dict:
        """
        Get performance dashboard data
        
        Returns:
            dict: Performance metrics and statistics
        """
        try:
            with self._lock:
                # Calculate response time statistics
                response_times = [m['value'] for m in self.performance_metrics['response_times']]
                avg_response_time = sum(response_times) / len(response_times) if response_times else 0
                max_response_time = max(response_times) if response_times else 0
                
                # Calculate cache hit rate
                total_cache_requests = self.performance_metrics['cache_hits'] + self.performance_metrics['cache_misses']
                cache_hit_rate = (self.performance_metrics['cache_hits'] / total_cache_requests * 100) if total_cache_requests > 0 else 0
                
                # Get recent database query count
                recent_queries = len([q for q in self.performance_metrics['database_queries'] 
                                    if datetime.fromisoformat(q['timestamp'].replace('Z', '+00:00')) > timezone.now() - timedelta(hours=1)])
                
                dashboard = {
                    'response_time': {
                        'average': round(avg_response_time, 3),
                        'maximum': round(max_response_time, 3),
                        'total_requests': len(response_times)
                    },
                    'cache': {
                        'hit_rate': round(cache_hit_rate, 2),
                        'hits': self.performance_metrics['cache_hits'],
                        'misses': self.performance_metrics['cache_misses']
                    },
                    'database': {
                        'recent_queries': recent_queries,
                        'total_queries': len(self.performance_metrics['database_queries'])
                    },
                    'system': {
                        'active_users': len(self.performance_metrics['active_users']),
                        'error_count': self.performance_metrics['error_count']
                    },
                    'timestamp': timezone.now().isoformat()
                }
                
                return dashboard
                
        except Exception as e:
            logger.error(f"Error generating performance dashboard: {str(e)}")
            return {}
    
    def generate_audit_report(self, start_date: datetime, end_date: datetime,
                            report_type: str = 'comprehensive') -> Dict:
        """
        Generate comprehensive audit report
        
        Args:
            start_date: Report start date
            end_date: Report end date
            report_type: Type of report to generate
            
        Returns:
            dict: Audit report data
        """
        try:
            # Get audit trail for the period
            audit_trail = self.get_audit_trail(
                start_date=start_date,
                end_date=end_date,
                limit=10000  # Large limit for comprehensive report
            )
            
            # Analyze the data
            report = {
                'period': {
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat(),
                    'duration_days': (end_date - start_date).days
                },
                'summary': {
                    'total_actions': len(audit_trail),
                    'unique_users': len(set(entry['user_id'] for entry in audit_trail if entry['user_id'])),
                    'action_types': {},
                    'risk_levels': {},
                    'models_affected': {}
                },
                'details': audit_trail if report_type == 'comprehensive' else audit_trail[:100]
            }
            
            # Count action types
            for entry in audit_trail:
                action = entry['action']
                report['summary']['action_types'][action] = report['summary']['action_types'].get(action, 0) + 1
                
                # Count risk levels
                risk_level = entry['details'].get('risk_level', self.RISK_LOW)
                report['summary']['risk_levels'][risk_level] = report['summary']['risk_levels'].get(risk_level, 0) + 1
                
                # Count affected models
                if entry['model_name']:
                    model = entry['model_name']
                    report['summary']['models_affected'][model] = report['summary']['models_affected'].get(model, 0) + 1
            
            return report
            
        except Exception as e:
            logger.error(f"Error generating audit report: {str(e)}")
            return {}
    
    def cleanup_old_logs(self, days_to_keep: int = 90) -> int:
        """
        Clean up old audit logs to manage storage
        
        Args:
            days_to_keep: Number of days to keep logs
            
        Returns:
            int: Number of logs deleted
        """
        try:
            cutoff_date = timezone.now() - timedelta(days=days_to_keep)
            
            # Delete old system logs
            deleted_count = SystemLog.objects.filter(timestamp__lt=cutoff_date).count()
            SystemLog.objects.filter(timestamp__lt=cutoff_date).delete()
            
            logger.info(f"Cleaned up {deleted_count} old audit logs")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error cleaning up old logs: {str(e)}")
            return 0


# Global instance
audit_service = AuditService()


# Utility functions for common audit patterns
def audit_user_login(user: User, ip_address: str = None, success: bool = True) -> Dict:
    """Audit user login attempts"""
    action = audit_service.EVENT_LOGIN if success else 'login_failed'
    risk_level = audit_service.RISK_LOW if success else audit_service.RISK_MEDIUM
    
    return audit_service.log_user_action(
        user=user,
        action=action,
        details={'success': success},
        ip_address=ip_address,
        risk_level=risk_level
    )


def audit_user_logout(user: User, ip_address: str = None) -> Dict:
    """Audit user logout"""
    return audit_service.log_user_action(
        user=user,
        action=audit_service.EVENT_LOGOUT,
        ip_address=ip_address,
        risk_level=audit_service.RISK_LOW
    )


def audit_model_change(user: User, action: str, instance: models.Model, 
                      old_data: Dict = None, new_data: Dict = None,
                      ip_address: str = None) -> Dict:
    """Audit model instance changes"""
    return audit_service.log_user_action(
        user=user,
        action=action,
        model_name=instance.__class__.__name__,
        object_id=instance.pk,
        details={
            'old_data': old_data,
            'new_data': new_data
        },
        ip_address=ip_address,
        risk_level=audit_service.RISK_MEDIUM if action == audit_service.EVENT_DELETE else audit_service.RISK_LOW
    )


def audit_financial_operation(user: User, operation: str, amount: float,
                            reference: str = None, ip_address: str = None) -> Dict:
    """Audit financial operations"""
    return audit_service.log_financial_transaction(
        user=user,
        transaction_type=operation,
        amount=amount,
        reference=reference,
        ip_address=ip_address
    )


def track_response_time(view_name: str, response_time: float, 
                       request_method: str = 'GET') -> bool:
    """Track view response time"""
    return audit_service.track_performance_metric(
        metric_type='response_time',
        value=response_time,
        context={
            'view_name': view_name,
            'method': request_method
        }
    )