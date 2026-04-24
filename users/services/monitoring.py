# -*- coding: utf-8 -*-
"""
Simplified Monitoring Service for Permissions System

Basic monitoring and alerting for permission-related operations
without the complexity of full governance monitoring.
"""

from django.utils import timezone
from django.core.cache import cache
from django.db.models import Count, Q
from datetime import timedelta, datetime
from typing import Dict, Any, List, Optional
import logging

from governance.services.audit_service import AuditService
from ..models import User, Role

logger = logging.getLogger('users.monitoring')


class PermissionMonitoringService:
    """
    Simplified monitoring service for permission operations.
    
    Provides basic monitoring without overwhelming complexity.
    """
    
    CACHE_PREFIX = 'perm_monitor'
    CACHE_TIMEOUT = 300  # 5 minutes
    
    @classmethod
    def get_system_health(cls) -> Dict[str, Any]:
        """
        Get basic system health metrics for permissions.
        
        Returns:
            dict: System health status
        """
        try:
            # Basic counts
            total_users = User.objects.filter(is_active=True).count()
            total_roles = Role.objects.filter(is_active=True).count()
            users_with_roles = User.objects.filter(role__isnull=False, is_active=True).count()
            
            # Recent activity (last 24 hours)
            since_yesterday = timezone.now() - timedelta(days=1)
            recent_logins = User.objects.filter(last_login__gte=since_yesterday).count()
            
            # Calculate health score
            role_coverage = (users_with_roles / total_users * 100) if total_users > 0 else 0
            
            health_score = 100
            if role_coverage < 80:
                health_score -= 20
            if recent_logins < (total_users * 0.1):  # Less than 10% daily activity
                health_score -= 10
            
            return {
                'health_score': max(0, health_score),
                'status': 'healthy' if health_score >= 80 else 'warning' if health_score >= 60 else 'critical',
                'metrics': {
                    'total_users': total_users,
                    'total_roles': total_roles,
                    'users_with_roles': users_with_roles,
                    'role_coverage_percentage': round(role_coverage, 2),
                    'recent_logins_24h': recent_logins
                },
                'timestamp': timezone.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting system health: {e}")
            return {
                'health_score': 0,
                'status': 'error',
                'error': str(e),
                'timestamp': timezone.now().isoformat()
            }
    
    @classmethod
    def get_security_alerts(cls, hours: int = 24) -> List[Dict[str, Any]]:
        """
        Get security alerts for the specified time period.
        
        Args:
            hours: Number of hours to look back
            
        Returns:
            list: Security alerts
        """
        try:
            alerts = []
            since_time = timezone.now() - timedelta(hours=hours)
            
            # Check for failed permission checks
            failed_permission_checks = cls._get_failed_permission_checks(since_time)
            if failed_permission_checks > 10:  # Threshold
                alerts.append({
                    'type': 'security',
                    'severity': 'medium',
                    'title': 'كثرة محاولات الوصول المرفوضة',
                    'description': f'{failed_permission_checks} محاولة وصول مرفوضة في آخر {hours} ساعة',
                    'count': failed_permission_checks,
                    'timestamp': timezone.now().isoformat()
                })
            
            # Check for multiple role changes
            role_changes = cls._get_role_changes(since_time)
            if role_changes > 5:  # Threshold
                alerts.append({
                    'type': 'administrative',
                    'severity': 'low',
                    'title': 'نشاط كثيف في تغيير الأدوار',
                    'description': f'{role_changes} تغيير في الأدوار في آخر {hours} ساعة',
                    'count': role_changes,
                    'timestamp': timezone.now().isoformat()
                })
            
            # Check for inactive users with admin roles
            inactive_admins = User.objects.filter(
                role__name__in=['admin', 'superuser'],
                is_active=False
            ).count()
            
            if inactive_admins > 0:
                alerts.append({
                    'type': 'security',
                    'severity': 'high',
                    'title': 'مستخدمين إداريين غير نشطين',
                    'description': f'{inactive_admins} مستخدم إداري غير نشط قد يشكل مخاطر أمنية',
                    'count': inactive_admins,
                    'timestamp': timezone.now().isoformat()
                })
            
            return alerts
            
        except Exception as e:
            logger.error(f"Error getting security alerts: {e}")
            return [{
                'type': 'system',
                'severity': 'high',
                'title': 'خطأ في نظام المراقبة',
                'description': f'فشل في جلب التنبيهات الأمنية: {str(e)}',
                'timestamp': timezone.now().isoformat()
            }]
    
    @classmethod
    def get_usage_statistics(cls, days: int = 7) -> Dict[str, Any]:
        """
        Get usage statistics for the specified period.
        
        Args:
            days: Number of days to analyze
            
        Returns:
            dict: Usage statistics
        """
        try:
            since_date = timezone.now() - timedelta(days=days)
            
            # Active users by day
            daily_active_users = []
            for i in range(days):
                day_start = since_date + timedelta(days=i)
                day_end = day_start + timedelta(days=1)
                
                active_count = User.objects.filter(
                    last_login__gte=day_start,
                    last_login__lt=day_end,
                    is_active=True
                ).count()
                
                daily_active_users.append({
                    'date': day_start.strftime('%Y-%m-%d'),
                    'active_users': active_count
                })
            
            # Role distribution
            role_distribution = Role.objects.filter(is_active=True).annotate(
                user_count=Count('users', filter=Q(users__is_active=True))
            ).values('display_name', 'user_count')
            
            # Most active users (by login frequency)
            active_users = User.objects.filter(
                last_login__gte=since_date,
                is_active=True
            ).order_by('-last_login')[:10]
            
            return {
                'period_days': days,
                'daily_active_users': daily_active_users,
                'role_distribution': list(role_distribution),
                'most_active_users': [
                    {
                        'username': user.username,
                        'full_name': user.get_full_name(),
                        'last_login': user.last_login.isoformat() if user.last_login else None,
                        'role': user.role.display_name if user.role else 'بدون دور'
                    }
                    for user in active_users
                ],
                'generated_at': timezone.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting usage statistics: {e}")
            return {
                'error': str(e),
                'generated_at': timezone.now().isoformat()
            }
    
    @classmethod
    def monitor_operation(cls, operation_name: str, user_id: int, success: bool = True, 
                         details: Optional[Dict] = None):
        """
        Monitor a specific operation for patterns and anomalies.
        
        Args:
            operation_name: Name of the operation
            user_id: User performing the operation
            success: Whether the operation succeeded
            details: Additional operation details
        """
        try:
            # Create monitoring key
            cache_key = f"{cls.CACHE_PREFIX}:op:{operation_name}:{user_id}"
            
            # Get current operation count
            current_count = cache.get(cache_key, 0)
            new_count = current_count + 1
            
            # Store updated count
            cache.set(cache_key, new_count, cls.CACHE_TIMEOUT)
            
            # Check for suspicious patterns
            if new_count > 50:  # Threshold for suspicious activity
                logger.warning(
                    f"High frequency operation detected: {operation_name} "
                    f"by user {user_id} - {new_count} times in {cls.CACHE_TIMEOUT}s"
                )
                
                # Log to audit service
                AuditService.log_operation(
                    model_name='monitoring.suspicious_activity',
                    object_id=user_id,
                    operation='high_frequency_operation',
                    source_service='PermissionMonitoringService',
                    operation_name=operation_name,
                    frequency_count=new_count,
                    time_window=cls.CACHE_TIMEOUT,
                    details=details or {}
                )
            
        except Exception as e:
            logger.error(f"Error monitoring operation {operation_name}: {e}")
    
    @classmethod
    def _get_failed_permission_checks(cls, since_time: datetime) -> int:
        """Get count of failed permission checks from audit log."""
        try:
            # This would query the audit trail for failed permission checks
            # Simplified implementation
            failed_checks = AuditService.get_audit_trail(
                operation='CHECK_PERMISSION',
                start_date=since_time,
                limit=1000
            )
            
            # Count failed checks (where result was False)
            return len([
                entry for entry in failed_checks 
                if entry.additional_context and 
                entry.additional_context.get('result') is False
            ])
            
        except Exception as e:
            logger.error(f"Error getting failed permission checks: {e}")
            return 0
    
    @classmethod
    def _get_role_changes(cls, since_time: datetime) -> int:
        """Get count of role changes from audit log."""
        try:
            role_changes = AuditService.get_audit_trail(
                operation='ASSIGN_ROLE',
                start_date=since_time,
                limit=1000
            )
            return len(role_changes)
            
        except Exception as e:
            logger.error(f"Error getting role changes: {e}")
            return 0
    
    @classmethod
    def get_monitoring_dashboard_data(cls) -> Dict[str, Any]:
        """
        Get comprehensive monitoring data for dashboard display.
        
        Returns:
            dict: Dashboard monitoring data
        """
        try:
            return {
                'system_health': cls.get_system_health(),
                'security_alerts': cls.get_security_alerts(hours=24),
                'usage_statistics': cls.get_usage_statistics(days=7),
                'cache_status': cls._get_cache_status(),
                'generated_at': timezone.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting monitoring dashboard data: {e}")
            return {
                'error': str(e),
                'generated_at': timezone.now().isoformat()
            }
    
    @classmethod
    def _get_cache_status(cls) -> Dict[str, Any]:
        """Get cache system status."""
        try:
            # Test cache functionality
            test_key = f"{cls.CACHE_PREFIX}:test"
            test_value = timezone.now().isoformat()
            
            cache.set(test_key, test_value, 60)
            retrieved_value = cache.get(test_key)
            
            cache_working = retrieved_value == test_value
            
            return {
                'status': 'working' if cache_working else 'failed',
                'backend': cache.__class__.__name__,
                'test_successful': cache_working
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }


# Export main class
__all__ = ['PermissionMonitoringService']