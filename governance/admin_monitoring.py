# -*- coding: utf-8 -*-
"""
Admin Monitoring Dashboard for Code Governance System

This module provides real-time monitoring and alerting capabilities
for admin panel activities with focus on security and compliance.

Key Features:
- Real-time admin activity monitoring
- Security alert dashboard
- Compliance reporting
- Automated threat detection
- Performance metrics for admin operations
"""

from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.db.models import Count, Q
from django.contrib.auth import get_user_model
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import json
import logging

from .models import AuditTrail
from .admin_audit import AdminAuditTrail
from .admin_security import AdminSecurityManager

User = get_user_model()
logger = logging.getLogger('governance.admin_monitoring')


class AdminMonitoringDashboard:
    """
    Comprehensive admin monitoring dashboard for security and compliance.
    
    This class provides various monitoring and reporting capabilities
    for admin panel activities with real-time alerting.
    """
    
    @staticmethod
    def get_dashboard_data(hours: int = 24) -> Dict[str, Any]:
        """
        Get comprehensive dashboard data for admin monitoring.
        
        Args:
            hours: Number of hours to look back for data
            
        Returns:
            Dict containing all dashboard metrics and data
        """
        try:
            start_time = timezone.now() - timedelta(hours=hours)
            
            # Get basic audit summary
            audit_summary = AdminAuditTrail.get_admin_audit_summary(
                start_date=start_time
            )
            
            # Get security alerts
            security_alerts = AdminAuditTrail.get_security_alerts(
                hours=hours,
                min_severity='WARNING'
            )
            
            # Get high-risk model activity
            high_risk_activity = AdminMonitoringDashboard._get_high_risk_activity(start_time)
            
            # Get user activity summary
            user_activity = AdminMonitoringDashboard._get_user_activity_summary(start_time)
            
            # Get compliance status
            compliance_status = AdminMonitoringDashboard._get_compliance_status()
            
            # Get performance metrics
            performance_metrics = AdminMonitoringDashboard._get_performance_metrics(start_time)
            
            dashboard_data = {
                'timestamp': timezone.now().isoformat(),
                'time_range_hours': hours,
                'audit_summary': audit_summary,
                'security_alerts': security_alerts,
                'high_risk_activity': high_risk_activity,
                'user_activity': user_activity,
                'compliance_status': compliance_status,
                'performance_metrics': performance_metrics,
                'system_health': {
                    'total_alerts': len(security_alerts),
                    'critical_alerts': len([a for a in security_alerts if a['security_level'] == 'CRITICAL']),
                    'blocked_operations': audit_summary.get('blocked_operations', 0),
                    'compliance_score': compliance_status.get('compliance_percentage', 0)
                }
            }
            
            return dashboard_data
            
        except Exception as e:
            logger.error(f"Failed to get dashboard data: {e}")
            return {
                'error': str(e),
                'timestamp': timezone.now().isoformat()
            }
    
    @staticmethod
    def _get_high_risk_activity(start_time: datetime) -> Dict[str, Any]:
        """Get activity summary for high-risk models."""
        try:
            high_risk_models = AdminSecurityManager.HIGH_RISK_MODELS
            
            activity_data = {
                'total_operations': 0,
                'blocked_operations': 0,
                'models_accessed': 0,
                'model_breakdown': {}
            }
            
            for model_label in high_risk_models:
                model_records = AuditTrail.objects.filter(
                    timestamp__gte=start_time,
                    source_service='AdminPanel',
                    model_name=model_label
                )
                
                if model_records.exists():
                    activity_data['models_accessed'] += 1
                    
                    model_stats = {
                        'total_operations': model_records.count(),
                        'blocked_operations': 0,
                        'security_events': 0,
                        'unique_users': model_records.values('user').distinct().count()
                    }
                    
                    # Count blocked operations and security events
                    for record in model_records:
                        context = record.additional_context or {}
                        if context.get('result') == 'blocked':
                            model_stats['blocked_operations'] += 1
                            activity_data['blocked_operations'] += 1
                        if context.get('security_event'):
                            model_stats['security_events'] += 1
                    
                    activity_data['model_breakdown'][model_label] = model_stats
                    activity_data['total_operations'] += model_stats['total_operations']
            
            return activity_data
            
        except Exception as e:
            logger.error(f"Failed to get high-risk activity: {e}")
            return {'error': str(e)}
    
    @staticmethod
    def _get_user_activity_summary(start_time: datetime) -> Dict[str, Any]:
        """Get user activity summary for admin operations."""
        try:
            user_records = AuditTrail.objects.filter(
                timestamp__gte=start_time,
                source_service='AdminPanel'
            ).values('user__username').annotate(
                operation_count=Count('id'),
                blocked_count=Count('id', filter=Q(additional_context__result='blocked')),
                security_events=Count('id', filter=Q(additional_context__security_event=True))
            ).order_by('-operation_count')
            
            user_activity = {
                'total_active_users': user_records.count(),
                'top_users': list(user_records[:10]),
                'suspicious_users': []
            }
            
            # Identify suspicious users (high blocked operations or security events)
            for user_data in user_records:
                if (user_data['blocked_count'] > 5 or 
                    user_data['security_events'] > 3 or
                    (user_data['blocked_count'] / max(user_data['operation_count'], 1)) > 0.3):
                    user_activity['suspicious_users'].append(user_data)
            
            return user_activity
            
        except Exception as e:
            logger.error(f"Failed to get user activity summary: {e}")
            return {'error': str(e)}
    
    @staticmethod
    def _get_compliance_status() -> Dict[str, Any]:
        """Get compliance status for admin security controls."""
        try:
            compliance_report = AdminSecurityManager.check_security_compliance()
            
            total_models = len(AdminSecurityManager.HIGH_RISK_MODELS)
            compliant_models = len(compliance_report['compliant_models'])
            
            compliance_status = {
                'total_high_risk_models': total_models,
                'compliant_models': compliant_models,
                'non_compliant_models': len(compliance_report['non_compliant_models']),
                'compliance_percentage': (compliant_models / total_models * 100) if total_models > 0 else 0,
                'errors': compliance_report['errors'],
                'last_check': timezone.now().isoformat()
            }
            
            return compliance_status
            
        except Exception as e:
            logger.error(f"Failed to get compliance status: {e}")
            return {'error': str(e)}
    
    @staticmethod
    def _get_performance_metrics(start_time: datetime) -> Dict[str, Any]:
        """Get performance metrics for admin operations."""
        try:
            # Get operation counts by hour
            hourly_operations = []
            current_time = start_time
            
            while current_time < timezone.now():
                next_hour = current_time + timedelta(hours=1)
                hour_count = AuditTrail.objects.filter(
                    timestamp__gte=current_time,
                    timestamp__lt=next_hour,
                    source_service='AdminPanel'
                ).count()
                
                hourly_operations.append({
                    'hour': current_time.strftime('%H:00'),
                    'operations': hour_count
                })
                
                current_time = next_hour
            
            # Calculate average operations per hour
            total_operations = sum(h['operations'] for h in hourly_operations)
            avg_operations_per_hour = total_operations / len(hourly_operations) if hourly_operations else 0
            
            performance_metrics = {
                'hourly_operations': hourly_operations,
                'total_operations': total_operations,
                'avg_operations_per_hour': round(avg_operations_per_hour, 2),
                'peak_hour': max(hourly_operations, key=lambda x: x['operations']) if hourly_operations else None
            }
            
            return performance_metrics
            
        except Exception as e:
            logger.error(f"Failed to get performance metrics: {e}")
            return {'error': str(e)}
    
    @staticmethod
    def generate_security_report(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        format_type: str = 'json'
    ) -> Dict[str, Any]:
        """
        Generate comprehensive security report for admin activities.
        
        Args:
            start_date: Start date for the report
            end_date: End date for the report
            format_type: Format of the report (json, csv, pdf)
            
        Returns:
            Dict containing the security report
        """
        try:
            # Default to last 7 days if no dates provided
            if not start_date:
                start_date = timezone.now() - timedelta(days=7)
            if not end_date:
                end_date = timezone.now()
            
            # Get comprehensive audit data
            audit_records = AuditTrail.objects.filter(
                timestamp__gte=start_date,
                timestamp__lte=end_date,
                source_service='AdminPanel'
            ).order_by('-timestamp')
            
            # Analyze security events
            security_events = []
            blocked_operations = []
            bypass_attempts = []
            
            for record in audit_records:
                context = record.additional_context or {}
                
                if context.get('security_event'):
                    security_events.append({
                        'timestamp': record.timestamp.isoformat(),
                        'user': record.user.username if record.user else 'Unknown',
                        'model': record.model_name,
                        'operation': record.operation,
                        'security_level': context.get('security_level'),
                        'violation_type': context.get('violation_type'),
                        'ip_address': context.get('ip_address')
                    })
                
                if context.get('result') == 'blocked':
                    blocked_operations.append({
                        'timestamp': record.timestamp.isoformat(),
                        'user': record.user.username if record.user else 'Unknown',
                        'model': record.model_name,
                        'operation': record.operation,
                        'reason': context.get('violation_type', 'Security policy')
                    })
                
                if 'bypass' in record.operation:
                    bypass_attempts.append({
                        'timestamp': record.timestamp.isoformat(),
                        'user': record.user.username if record.user else 'Unknown',
                        'model': record.model_name,
                        'method': context.get('method_name'),
                        'bypass_type': context.get('bypass_type')
                    })
            
            # Generate report
            security_report = {
                'report_metadata': {
                    'generated_at': timezone.now().isoformat(),
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat(),
                    'format': format_type,
                    'total_records': audit_records.count()
                },
                'summary': {
                    'total_operations': audit_records.count(),
                    'security_events': len(security_events),
                    'blocked_operations': len(blocked_operations),
                    'bypass_attempts': len(bypass_attempts),
                    'unique_users': audit_records.values('user').distinct().count(),
                    'high_risk_models_accessed': audit_records.filter(
                        model_name__in=AdminSecurityManager.HIGH_RISK_MODELS
                    ).values('model_name').distinct().count()
                },
                'security_events': security_events,
                'blocked_operations': blocked_operations,
                'bypass_attempts': bypass_attempts,
                'recommendations': AdminMonitoringDashboard._generate_security_recommendations(
                    security_events, blocked_operations, bypass_attempts
                )
            }
            
            return security_report
            
        except Exception as e:
            logger.error(f"Failed to generate security report: {e}")
            return {
                'error': str(e),
                'report_metadata': {
                    'generated_at': timezone.now().isoformat(),
                    'status': 'failed'
                }
            }
    
    @staticmethod
    def _generate_security_recommendations(
        security_events: List[Dict],
        blocked_operations: List[Dict],
        bypass_attempts: List[Dict]
    ) -> List[str]:
        """Generate security recommendations based on audit data."""
        recommendations = []
        
        # Check for high number of security events
        if len(security_events) > 50:
            recommendations.append(
                "High number of security events detected. Review user permissions and access patterns."
            )
        
        # Check for bypass attempts
        if bypass_attempts:
            recommendations.append(
                f"{len(bypass_attempts)} bypass attempts detected. "
                "Investigate users and strengthen admin security controls."
            )
        
        # Check for blocked operations
        if len(blocked_operations) > 20:
            recommendations.append(
                "High number of blocked operations. Review user training and access policies."
            )
        
        # Check for repeated violations by same users
        user_violations = {}
        for event in security_events:
            user = event['user']
            user_violations[user] = user_violations.get(user, 0) + 1
        
        repeat_violators = [user for user, count in user_violations.items() if count > 5]
        if repeat_violators:
            recommendations.append(
                f"Users with repeated violations: {', '.join(repeat_violators)}. "
                "Consider additional training or access restrictions."
            )
        
        if not recommendations:
            recommendations.append("No immediate security concerns identified.")
        
        return recommendations


# Admin views for monitoring dashboard
@method_decorator(staff_member_required, name='dispatch')
class AdminMonitoringView:
    """Django admin view for monitoring dashboard."""
    
    def dashboard_view(self, request):
        """Main dashboard view."""
        hours = int(request.GET.get('hours', 24))
        dashboard_data = AdminMonitoringDashboard.get_dashboard_data(hours)
        
        if request.headers.get('Accept') == 'application/json':
            return JsonResponse(dashboard_data)
        
        context = {
            'title': 'Admin Security Monitoring Dashboard',
            'dashboard_data': dashboard_data,
            'hours': hours
        }
        
        return render(request, 'governance/admin/monitoring_dashboard.html', context)
    
    def security_alerts_view(self, request):
        """Security alerts view."""
        hours = int(request.GET.get('hours', 24))
        min_severity = request.GET.get('severity', 'WARNING')
        
        alerts = AdminAuditTrail.get_security_alerts(hours, min_severity)
        
        if request.headers.get('Accept') == 'application/json':
            return JsonResponse({'alerts': alerts})
        
        context = {
            'title': 'Security Alerts',
            'alerts': alerts,
            'hours': hours,
            'min_severity': min_severity
        }
        
        return render(request, 'governance/admin/security_alerts.html', context)
    
    def security_report_view(self, request):
        """Security report generation view."""
        days = int(request.GET.get('days', 7))
        format_type = request.GET.get('format', 'json')
        
        start_date = timezone.now() - timedelta(days=days)
        end_date = timezone.now()
        
        report = AdminMonitoringDashboard.generate_security_report(
            start_date, end_date, format_type
        )
        
        if format_type == 'json':
            return JsonResponse(report)
        elif format_type == 'csv':
            # TODO: Implement CSV export
            return JsonResponse({'error': 'CSV format not yet implemented'})
        else:
            return JsonResponse(report)


# Export main classes
__all__ = [
    'AdminMonitoringDashboard',
    'AdminMonitoringView'
]