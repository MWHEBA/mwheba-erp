from django.shortcuts import render
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.db.models import Count, Q
from django.utils import timezone
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_http_methods
from django.contrib.auth.decorators import login_required
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

class GovernanceBaseView(LoginRequiredMixin, TemplateView):
    """Base view for governance pages"""
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'active_menu': 'governance',
            'breadcrumb_items': [
                {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
                {'title': _('الحوكمة والإدارة'), 'active': True}
            ]
        })
        return context


class AuditManagementView(GovernanceBaseView):
    """Comprehensive Audit and Logs Management"""
    template_name = 'governance/audit_management.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context.update({
            'title': _('إدارة شاملة للتدقيق والسجلات'),
            'subtitle': _('تتبع جميع العمليات والتغييرات في النظام'),
            'icon': 'fas fa-clipboard-list',
            'header_buttons': [
                {
                    'onclick': 'refreshAuditLogs()',
                    'icon': 'fa-sync-alt',
                    'text': 'تحديث',
                    'class': 'btn-primary'
                },
                {
                    'onclick': 'deleteOldAuditLogs()',
                    'icon': 'fa-trash-alt',
                    'text': 'حذف السجلات القديمة',
                    'class': 'btn-danger'
                }
            ],
            'breadcrumb_items': [
                {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
                {'title': _('الحوكمة والإدارة'), 'url': reverse('governance:audit_management'), 'icon': 'fas fa-shield-alt'},
                {'title': _('إدارة التدقيق والسجلات'), 'active': True}
            ]
        })
        
        # Import models
        from governance.models import AuditTrail, QuarantineRecord
        
        # Get real statistics
        today = timezone.now().date()
        today_start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
        
        total_audit_records = AuditTrail.objects.count()
        today_records = AuditTrail.objects.filter(timestamp__gte=today_start).count()
        quarantined_items = QuarantineRecord.objects.filter(
            status__in=['QUARANTINED', 'UNDER_REVIEW']
        ).count()
        
        # Calculate success rate
        total_operations = AuditTrail.objects.count()
        failed_operations = AuditTrail.objects.filter(
            operation__in=['AUTHORITY_VIOLATION', 'EXCEPTION']
        ).count()
        success_rate = ((total_operations - failed_operations) / total_operations * 100) if total_operations > 0 else 100
        
        # Get all audit logs with pagination
        audit_list = AuditTrail.objects.select_related('user').order_by('-timestamp')
        paginator = Paginator(audit_list, 50)  # 50 records per page
        
        page = self.request.GET.get('page', 1)
        try:
            recent_audits = paginator.page(page)
        except PageNotAnInteger:
            recent_audits = paginator.page(1)
        except EmptyPage:
            recent_audits = paginator.page(paginator.num_pages)
        
        # Get quarantined items
        quarantine_records = QuarantineRecord.objects.select_related(
            'quarantined_by', 'resolved_by'
        ).filter(
            status__in=['QUARANTINED', 'UNDER_REVIEW']
        ).order_by('-quarantined_at')[:10]
        
        context.update({
            'total_audit_records': total_audit_records,
            'today_records': today_records,
            'quarantined_items': quarantined_items,
            'success_rate': round(success_rate, 1),
            'recent_audits': recent_audits,
            'quarantine_records': quarantine_records,
        })
        
        return context

class SystemHealthView(GovernanceBaseView):
    """System Health and Performance Monitoring"""
    template_name = 'governance/system_health.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context['breadcrumb_items'].append({
            'title': _('صحة النظام والأداء'), 'active': True
        })
        
        context.update({
            'title': _('صحة النظام والتنبيهات والأداء'),
            'subtitle': _('مراقبة شاملة لحالة النظام ومؤشرات الأداء'),
            'icon': 'fas fa-heartbeat'
        })
        
        # Get real system health data
        health_data = self._get_system_health_data()
        context.update(health_data)
        
        return context
    
    def _get_system_health_data(self):
        """Get real system health metrics with caching and error handling"""
        from django.db import connection
        from django.contrib.sessions.models import Session
        from django.core.cache import cache
        from governance.models import AuditTrail, QuarantineRecord
        from django.db.models import Count
        import time
        
        # Try to get cached data
        cache_key = 'system_health_metrics'
        cached_data = cache.get(cache_key)
        if cached_data:
            return cached_data
        
        data = {}
        today = timezone.now().date()
        today_start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
        week_ago = timezone.now() - timedelta(days=7)
        month_ago = timezone.now() - timedelta(days=30)
        
        # Health score thresholds
        THRESHOLDS = {
            'db_response': {'excellent': 100, 'good': 500, 'poor': 1000},
            'success_rate': {'excellent': 99, 'good': 95, 'poor': 90},
            'quarantine': {'excellent': 0, 'good': 5, 'poor': 10}
        }
        
        # Database connection test with error handling
        db_connected = True
        db_response_time = 0
        try:
            start_time = time.time()
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            db_response_time = round((time.time() - start_time) * 1000, 2)
        except Exception as e:
            logger.error(f"Database connection error: {e}")
            db_connected = False
            db_response_time = 0
        
        data['db_connected'] = db_connected
        data['db_response_time'] = db_response_time
        
        # Real active users (sessions with actual user activity in last 15 minutes)
        fifteen_minutes_ago = timezone.now() - timedelta(minutes=15)
        try:
            active_user_ids = set()
            recent_sessions = Session.objects.filter(expire_date__gte=timezone.now())
            
            for session in recent_sessions:
                try:
                    session_data = session.get_decoded()
                    user_id = session_data.get('_auth_user_id')
                    if user_id:
                        active_user_ids.add(user_id)
                except Exception:
                    continue
            
            data['active_users'] = len(active_user_ids)
        except Exception as e:
            logger.error(f"Error counting active users: {e}")
            data['active_users'] = 0
        
        # Audit statistics (limited to last month for performance)
        try:
            total_operations = AuditTrail.objects.filter(timestamp__gte=month_ago).count()
            today_operations = AuditTrail.objects.filter(timestamp__gte=today_start).count()
            week_operations = AuditTrail.objects.filter(timestamp__gte=week_ago).count()
            
            # Failed operations (last month only) - ACTIVE only
            failed_operations = AuditTrail.objects.filter(
                timestamp__gte=month_ago,
                operation__in=['AUTHORITY_VIOLATION', 'EXCEPTION'],
                resolution_status='ACTIVE'
            ).count()
            
            # Success rate
            success_rate = 100
            if total_operations > 0:
                success_rate = round(((total_operations - failed_operations) / total_operations) * 100, 1)
            
            data['total_operations'] = total_operations
            data['today_operations'] = today_operations
            data['week_operations'] = week_operations
            data['success_rate'] = success_rate
            data['failed_operations'] = failed_operations
        except Exception as e:
            logger.error(f"Error getting audit statistics: {e}")
            data['total_operations'] = 0
            data['today_operations'] = 0
            data['week_operations'] = 0
            data['success_rate'] = 100
            data['failed_operations'] = 0
        
        # Quarantine records
        try:
            active_quarantine = QuarantineRecord.objects.filter(
                status__in=['QUARANTINED', 'UNDER_REVIEW']
            ).count()
            data['active_quarantine'] = active_quarantine
        except Exception as e:
            logger.error(f"Error getting quarantine count: {e}")
            data['active_quarantine'] = 0
        
        # Database size with better error handling
        db_size_mb = None
        try:
            if connection.vendor == 'sqlite':
                import os
                from django.conf import settings
                db_path = settings.DATABASES['default']['NAME']
                if os.path.exists(db_path):
                    db_size_mb = round(os.path.getsize(db_path) / (1024 * 1024), 2)
            elif connection.vendor == 'mysql':
                try:
                    with connection.cursor() as cursor:
                        cursor.execute("""
                            SELECT ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) 
                            FROM information_schema.tables 
                            WHERE table_schema = DATABASE()
                        """)
                        result = cursor.fetchone()
                        if result and result[0]:
                            db_size_mb = float(result[0])
                except Exception as mysql_error:
                    logger.warning(f"Cannot access information_schema (shared hosting): {mysql_error}")
                    db_size_mb = None
        except Exception as e:
            logger.error(f"Error getting database size: {e}")
            db_size_mb = None
        
        data['db_size_mb'] = db_size_mb if db_size_mb is not None else 'N/A'
        
        # Calculate overall health score with clear thresholds
        health_score = 100
        
        # Database connectivity (30 points)
        if not db_connected:
            health_score -= 30
        elif db_response_time > THRESHOLDS['db_response']['poor']:
            health_score -= 20
        elif db_response_time > THRESHOLDS['db_response']['good']:
            health_score -= 10
        elif db_response_time > THRESHOLDS['db_response']['excellent']:
            health_score -= 5
        
        # Success rate (30 points)
        if data['success_rate'] < THRESHOLDS['success_rate']['poor']:
            health_score -= 30
        elif data['success_rate'] < THRESHOLDS['success_rate']['good']:
            health_score -= 15
        elif data['success_rate'] < THRESHOLDS['success_rate']['excellent']:
            health_score -= 5
        
        # Quarantine status (20 points)
        if data['active_quarantine'] > THRESHOLDS['quarantine']['poor']:
            health_score -= 20
        elif data['active_quarantine'] > THRESHOLDS['quarantine']['good']:
            health_score -= 10
        
        data['system_health_score'] = max(0, min(100, health_score))
        
        # Get recent critical audit logs with error handling - ACTIVE only
        try:
            recent_critical = AuditTrail.objects.filter(
                timestamp__gte=week_ago,
                operation__in=['AUTHORITY_VIOLATION', 'EXCEPTION'],
                resolution_status='ACTIVE'
            ).select_related('user').order_by('-timestamp')[:5]
            data['recent_critical_logs'] = list(recent_critical)
        except Exception as e:
            logger.error(f"Error getting critical logs: {e}")
            data['recent_critical_logs'] = []
        
        # Get active alerts with error handling
        try:
            active_alerts = QuarantineRecord.objects.filter(
                status__in=['QUARANTINED', 'UNDER_REVIEW']
            ).select_related('quarantined_by').order_by('-quarantined_at')[:5]
            data['active_alerts'] = list(active_alerts)
        except Exception as e:
            logger.error(f"Error getting active alerts: {e}")
            data['active_alerts'] = []
        
        # Get exception analysis (grouped by type) - ACTIVE only
        try:
            exception_analysis = AuditTrail.objects.filter(
                timestamp__gte=week_ago,
                operation='EXCEPTION',
                resolution_status='ACTIVE'
            ).values('model_name').annotate(
                count=Count('id')
            ).order_by('-count')[:10]
            data['exception_analysis'] = list(exception_analysis)
        except Exception as e:
            logger.error(f"Error getting exception analysis: {e}")
            data['exception_analysis'] = []
        
        # Get detailed exceptions with context - ACTIVE only
        try:
            detailed_exceptions = []
            recent_exceptions = AuditTrail.objects.filter(
                timestamp__gte=week_ago,
                operation='EXCEPTION',
                resolution_status='ACTIVE'
            ).select_related('user').order_by('-timestamp')[:10]
            
            for exc in recent_exceptions:
                context = exc.additional_context or {}
                detailed_exceptions.append({
                    'id': exc.id,
                    'timestamp': exc.timestamp,
                    'user': exc.user.get_full_name() if exc.user else 'النظام',
                    'exception_type': context.get('exception_type', 'Unknown'),
                    'exception_message': context.get('exception_message', 'No message'),
                    'request_path': context.get('request_path', 'N/A'),
                    'request_method': context.get('request_method', 'N/A'),
                })
            
            data['detailed_exceptions'] = detailed_exceptions
        except Exception as e:
            logger.error(f"Error getting detailed exceptions: {e}")
            data['detailed_exceptions'] = []
        
        # System status indicators
        data['system_status'] = {
            'database': 'success' if db_connected else 'danger',
            'operations': 'success' if data['success_rate'] >= THRESHOLDS['success_rate']['good'] else (
                'warning' if data['success_rate'] >= THRESHOLDS['success_rate']['poor'] else 'danger'
            ),
            'quarantine': 'success' if data['active_quarantine'] <= THRESHOLDS['quarantine']['excellent'] else (
                'warning' if data['active_quarantine'] <= THRESHOLDS['quarantine']['good'] else 'danger'
            ),
        }
        
        # Cache for 1 minute
        cache.set(cache_key, data, 60)
        
        return data

class SecurityCenterView(GovernanceBaseView):
    """Security Center for violations and incidents"""
    template_name = 'governance/security_center.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from governance.models import SecurityIncident, BlockedIP, ActiveSession, SecurityPolicy
        from django.db.models import Count, Q
        from datetime import timedelta
        from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
        
        context['breadcrumb_items'].append({
            'title': _('مركز الأمان والحوادث'), 'active': True
        })
        
        context.update({
            'title': _('مركز الأمان والانتهاكات والحوادث'),
            'subtitle': _('مراقبة الانتهاكات الأمنية وإدارة الحوادث'),
            'icon': 'fas fa-shield-alt'
        })
        
        # Security statistics
        total_incidents = SecurityIncident.objects.count()
        active_incidents = SecurityIncident.objects.filter(status='ACTIVE').count()
        critical_incidents = SecurityIncident.objects.filter(severity='CRITICAL', status='ACTIVE').count()
        
        # Calculate security level
        if critical_incidents > 0:
            security_level = 'منخفض'
            security_percentage = 40
        elif active_incidents > 5:
            security_level = 'متوسط'
            security_percentage = 70
        else:
            security_level = 'عالي'
            security_percentage = 95
        
        context.update({
            'security_level': security_level,
            'security_percentage': security_percentage,
            'active_sessions': ActiveSession.objects.filter(is_active=True).count(),
            'suspicious_attempts': SecurityIncident.objects.filter(
                detected_at__gte=timezone.now() - timedelta(days=1),
                severity__in=['HIGH', 'CRITICAL']
            ).count(),
            'blocked_ips': BlockedIP.objects.filter(is_active=True).count(),
        })
        
        # Recent incidents with pagination
        incidents_list = SecurityIncident.objects.select_related('user', 'resolved_by').order_by('-detected_at')
        page = self.request.GET.get('page', 1)
        paginator = Paginator(incidents_list, 10)  # 10 items per page
        
        try:
            recent_incidents = paginator.page(page)
        except PageNotAnInteger:
            recent_incidents = paginator.page(1)
        except EmptyPage:
            recent_incidents = paginator.page(paginator.num_pages)
        
        # Active sessions
        active_sessions = ActiveSession.objects.filter(is_active=True).select_related('user').order_by('-last_activity')[:10]
        
        # Blocked IPs
        blocked_ips = BlockedIP.objects.filter(is_active=True).select_related('blocked_by').order_by('-blocked_at')[:10]
        
        # Security policies
        security_policies = SecurityPolicy.objects.all()
        
        context.update({
            'recent_incidents': recent_incidents,
            'active_sessions_list': active_sessions,
            'blocked_ips_list': blocked_ips,
            'security_policies': security_policies,
        })
        
        return context

class SecurityPoliciesView(GovernanceBaseView):
    """Security Policies and Encryption Center"""
    template_name = 'security/policies_center.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        from governance.services.security_policy_service import SecurityPolicyService
        
        # Initialize service
        service = SecurityPolicyService()
        
        # Initialize default data if needed
        service.initialize_default_policies()
        if self.request.user.is_authenticated:
            service.initialize_default_keys(self.request.user)
        
        context['breadcrumb_items'].append({
            'title': _('مركز السياسات الأمنية'), 'active': True
        })
        
        context.update({
            'title': _('مركز السياسات الأمنية والتشفير'),
            'subtitle': _('إدارة السياسات الأمنية وإعدادات التشفير'),
            'icon': 'fas fa-lock',
            
            # Real data from service
            'security_overview': service.get_security_overview(),
            'auth_policies': service.get_authentication_policies(),
            'network_policies': service.get_network_policies(),
            'encryption_keys': service.get_encryption_keys(),
            'security_stats': service.get_security_statistics(),
            'protection_status': service.get_protection_status()
        })
        
        return context

class SignalsManagementView(GovernanceBaseView):
    """Signals and Permissions Management Center"""
    template_name = 'signals/management_center.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from governance.models import SignalRegistry, SignalExecution, SignalPerformanceAlert
        from django.db.models import Count, Avg, Q
        from datetime import timedelta
        
        context['breadcrumb_items'].append({
            'title': _('مركز إدارة الإشارات والأذونات'), 'active': True
        })
        
        context.update({
            'title': _('مركز إدارة الإشارات والأذونات'),
            'subtitle': _('مراقبة العمليات التلقائية وإدارة الصلاحيات'),
            'icon': 'fas fa-broadcast-tower'
        })
        
        # Get real statistics
        today_start = timezone.make_aware(timezone.datetime.combine(timezone.now().date(), timezone.datetime.min.time()))
        
        # Total signals
        total_signals = SignalRegistry.objects.count()
        active_signals = SignalRegistry.objects.filter(status='ACTIVE').count()
        disabled_signals = SignalRegistry.objects.filter(status='DISABLED').count()
        
        # Today's executions
        today_executions = SignalExecution.objects.filter(executed_at__gte=today_start)
        successful_today = today_executions.filter(status='SUCCESS').count()
        failed_today = today_executions.filter(status='FAILED').count()
        
        context.update({
            'total_signals': total_signals,
            'active_signals': active_signals,
            'disabled_signals': disabled_signals,
            'successful_today': successful_today,
            'failed_today': failed_today,
        })
        
        # Get all signals with their statistics
        signals_data = []
        for signal in SignalRegistry.objects.all().order_by('module_name', 'signal_name'):
            last_execution = signal.get_last_execution()
            
            signals_data.append({
                'id': signal.id,
                'signal_name': signal.signal_name,
                'module_name': signal.module_name,
                'signal_type': signal.get_signal_type_display(),
                'priority': signal.get_priority_display(),
                'priority_class': self._get_priority_class(signal.priority),
                'last_execution': last_execution.executed_at if last_execution else None,
                'success_rate': signal.get_success_rate(),
                'avg_execution_time': signal.get_avg_execution_time(),
                'execution_count': signal.get_execution_count(),
                'status': signal.status,
                'status_display': signal.get_status_display(),
                'status_class': self._get_status_class(signal.status),
                'performance_status': signal.get_performance_status(),
            })
        
        context['signals_data'] = signals_data
        
        # Get performance data for last 24 hours
        performance_data = []
        for signal in SignalRegistry.objects.filter(status='ACTIVE').order_by('-executions__executed_at')[:10]:
            executions_24h = signal.executions.filter(
                executed_at__gte=timezone.now() - timedelta(hours=24)
            )
            
            if executions_24h.exists():
                avg_time = executions_24h.aggregate(avg=Avg('execution_time_ms'))['avg'] or 0
                max_time = executions_24h.aggregate(max=models.Max('execution_time_ms'))['max'] or 0
                count = executions_24h.count()
                
                performance_status = 'excellent'
                if avg_time > signal.max_execution_time_ms:
                    performance_status = 'slow'
                elif avg_time > signal.max_execution_time_ms * 0.7:
                    performance_status = 'warning'
                
                performance_data.append({
                    'signal_name': signal.signal_name,
                    'avg_time': round(avg_time, 2),
                    'max_time': max_time,
                    'count': count,
                    'performance_status': performance_status,
                })
        
        context['performance_data'] = performance_data
        
        # Get active alerts
        active_alerts = SignalPerformanceAlert.objects.filter(
            is_resolved=False
        ).select_related('signal').order_by('-created_at')[:10]
        
        context['active_alerts'] = active_alerts
        
        # Get roles and permissions summary (from existing system)
        from django.contrib.auth.models import Group
        roles_data = []
        for group in Group.objects.all():
            roles_data.append({
                'name': group.name,
                'user_count': group.user_set.count(),
                'permission_count': group.permissions.count(),
            })
        
        context['roles_data'] = roles_data
        
        return context
    
    def _get_priority_class(self, priority):
        """Get Bootstrap class for priority"""
        priority_map = {
            'LOW': 'secondary',
            'MEDIUM': 'info',
            'HIGH': 'warning',
            'CRITICAL': 'danger',
        }
        return priority_map.get(priority, 'secondary')
    
    def _get_status_class(self, status):
        """Get Bootstrap class for status"""
        status_map = {
            'ACTIVE': 'success',
            'DISABLED': 'warning',
            'PAUSED': 'info',
            'ERROR': 'danger',
        }
        return status_map.get(status, 'secondary')

class ReportsBuilderView(GovernanceBaseView):
    """Advanced Reports Builder and Scheduler"""
    template_name = 'reports/builder_center.html'
    
    def get_context_data(self, **kwargs):
        from governance.services.reports_builder_service import ReportsBuilderService
        from governance.models import SavedReport, ReportSchedule
        
        context = super().get_context_data(**kwargs)
        
        context['breadcrumb_items'].append({
            'title': _('مركز بناء التقارير'), 'active': True
        })
        
        context.update({
            'title': _('مركز بناء التقارير المخصصة والجدولة'),
            'subtitle': _('إنشاء تقارير مخصصة وجدولة التقارير التلقائية'),
            'icon': 'fas fa-chart-line'
        })
        
        # Get statistics
        stats = ReportsBuilderService.get_report_statistics()
        context['stats'] = stats
        
        # Get saved reports
        saved_reports = ReportsBuilderService.get_saved_reports(user=self.request.user)
        context['saved_reports'] = saved_reports
        
        # Get scheduled reports
        scheduled_reports = ReportsBuilderService.get_scheduled_reports(user=self.request.user)
        context['scheduled_reports'] = scheduled_reports
        
        return context



@login_required
@require_POST
def delete_old_audit_logs(request):
    """Delete audit logs older than 1 month"""
    try:
        from governance.models import AuditTrail
        
        # Calculate date 1 month ago
        one_month_ago = timezone.now() - timedelta(days=30)
        
        # Delete old records
        deleted_count, _ = AuditTrail.objects.filter(timestamp__lt=one_month_ago).delete()
        
        return JsonResponse({
            'success': True,
            'message': f'تم حذف {deleted_count} سجل قديم بنجاح',
            'deleted_count': deleted_count
        })
    except Exception as e:
        logger.error(f"Error deleting old audit logs: {e}")
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ أثناء حذف السجلات: {str(e)}'
        }, status=500)


@login_required
@require_POST
def mark_exception_resolved(request, audit_id):
    """Mark an exception as resolved"""
    try:
        from governance.models import AuditTrail
        from django.core.cache import cache
        
        audit = AuditTrail.objects.get(id=audit_id, operation='EXCEPTION')
        notes = request.POST.get('notes', '')
        
        audit.mark_as_resolved(request.user, notes)
        
        # Clear health metrics cache
        cache.delete('system_health_metrics')
        
        return JsonResponse({
            'success': True,
            'message': 'تم تعليم المشكلة كمحلولة بنجاح'
        })
    except AuditTrail.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'السجل غير موجود'
        }, status=404)
    except Exception as e:
        logger.error(f"Error marking exception as resolved: {e}")
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ: {str(e)}'
        }, status=500)


@login_required
@require_POST
def mark_exception_ignored(request, audit_id):
    """Mark an exception as ignored"""
    try:
        from governance.models import AuditTrail
        from django.core.cache import cache
        
        audit = AuditTrail.objects.get(id=audit_id, operation='EXCEPTION')
        notes = request.POST.get('notes', '')
        
        audit.mark_as_ignored(request.user, notes)
        
        # Clear health metrics cache
        cache.delete('system_health_metrics')
        
        return JsonResponse({
            'success': True,
            'message': 'تم تجاهل المشكلة بنجاح'
        })
    except AuditTrail.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'السجل غير موجود'
        }, status=404)
    except Exception as e:
        logger.error(f"Error marking exception as ignored: {e}")
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ: {str(e)}'
        }, status=500)


@login_required
@require_POST
def recheck_exception(request, audit_id):
    """Re-check if an exception still exists"""
    try:
        from governance.models import AuditTrail
        from django.conf import settings
        from django.core.cache import cache
        
        audit = AuditTrail.objects.get(id=audit_id, operation='EXCEPTION')
        context = audit.additional_context or {}
        request_path = context.get('request_path')
        exception_type = context.get('exception_type', '')
        
        if not request_path:
            return JsonResponse({
                'success': False,
                'message': 'لا يمكن إعادة الفحص - المسار غير متوفر'
            }, status=400)
        
        # Try to access the URL using requests library
        try:
            import requests
            
            # Determine the correct base URL
            # If DEBUG is True, use current request host (localhost)
            # If DEBUG is False, use SITE_URL from settings (production)
            if settings.DEBUG:
                # Development: use current request host
                scheme = 'https' if request.is_secure() else 'http'
                host = request.get_host()
                base_url = f"{scheme}://{host}"
            else:
                # Production: use SITE_URL from .env
                base_url = settings.SITE_URL.rstrip('/')
            
            full_url = f"{base_url}{request_path}"
            
            # Make request with timeout
            # Disable SSL verification for localhost
            verify_ssl = not ('localhost' in full_url or '127.0.0.1' in full_url)
            
            response = requests.get(
                full_url, 
                timeout=5, 
                allow_redirects=True,
                verify=verify_ssl,
                headers={'User-Agent': 'SystemHealthCheck/1.0'}
            )
            status_code = response.status_code
            
            # Consider 2xx and 3xx as success
            if 200 <= status_code < 400:
                # Mark as auto-resolved
                audit.resolution_status = 'AUTO_RESOLVED'
                audit.resolved_at = timezone.now()
                audit.resolution_notes = f'تم الفحص تلقائياً - الصفحة تعمل الآن (Status: {status_code})'
                audit.save(update_fields=['resolution_status', 'resolved_at', 'resolution_notes'])
                
                # Clear health metrics cache
                cache.delete('system_health_metrics')
                
                return JsonResponse({
                    'success': True,
                    'resolved': True,
                    'message': f'المشكلة تم حلها! الصفحة تعمل الآن (Status: {status_code})'
                })
            else:
                return JsonResponse({
                    'success': True,
                    'resolved': False,
                    'message': f'المشكلة لا تزال موجودة: HTTP {status_code}'
                })
                
        except ImportError:
            # requests library not available
            return JsonResponse({
                'success': False,
                'message': 'لا يمكن إعادة الفحص تلقائياً - استخدم زر "تم الحل" يدوياً'
            }, status=400)
            
        except requests.exceptions.Timeout:
            return JsonResponse({
                'success': True,
                'resolved': False,
                'message': 'المشكلة لا تزال موجودة: انتهت مهلة الاتصال (الصفحة بطيئة جداً)'
            })
            
        except requests.exceptions.ConnectionError:
            return JsonResponse({
                'success': True,
                'resolved': False,
                'message': 'المشكلة لا تزال موجودة: فشل الاتصال بالخادم'
            })
            
        except requests.exceptions.RequestException as req_error:
            error_msg = str(req_error)
            # Simplify error message
            if 'Max retries exceeded' in error_msg:
                return JsonResponse({
                    'success': True,
                    'resolved': False,
                    'message': 'المشكلة لا تزال موجودة: فشل الاتصال بالصفحة'
                })
            return JsonResponse({
                'success': True,
                'resolved': False,
                'message': f'المشكلة لا تزال موجودة: {error_msg[:80]}'
            })
            
    except AuditTrail.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'السجل غير موجود'
        }, status=404)
    except Exception as e:
        logger.error(f"Error rechecking exception: {e}")
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ أثناء الفحص: {str(e)}'
        }, status=500)



# Security Center API Views
@login_required
@require_http_methods(["GET"])
def get_incident_details(request, incident_id):
    """Get incident details for modal"""
    from governance.models import SecurityIncident
    from django.http import JsonResponse
    
    try:
        incident = SecurityIncident.objects.select_related('user', 'resolved_by').get(id=incident_id)
        
        data = {
            'id': incident.id,
            'incident_type': incident.get_incident_type_display(),
            'severity': incident.get_severity_display(),
            'status': incident.get_status_display(),
            'ip_address': incident.ip_address,
            'user': incident.user.username if incident.user else incident.username_attempted or 'unknown',
            'description': incident.description,
            'user_agent': incident.user_agent,
            'request_path': incident.request_path,
            'request_method': incident.request_method,
            'detected_at': incident.detected_at.strftime('%Y-%m-%d %H:%M:%S'),
            'resolved_at': incident.resolved_at.strftime('%Y-%m-%d %H:%M:%S') if incident.resolved_at else None,
            'resolved_by': incident.resolved_by.username if incident.resolved_by else None,
            'resolution_notes': incident.resolution_notes,
        }
        
        return JsonResponse({'success': True, 'data': data})
    except SecurityIncident.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'الحادث غير موجود'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def resolve_incident(request, incident_id):
    """Resolve a security incident"""
    from governance.models import SecurityIncident
    from django.http import JsonResponse
    
    try:
        incident = SecurityIncident.objects.get(id=incident_id)
        notes = request.POST.get('notes', '')
        
        incident.resolve(user=request.user, notes=notes)
        
        return JsonResponse({
            'success': True,
            'message': 'تم حل الحادث بنجاح'
        })
    except SecurityIncident.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'الحادث غير موجود'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def block_ip_address(request, ip_address):
    """Block an IP address"""
    from governance.models import BlockedIP
    from django.http import JsonResponse
    
    try:
        description = request.POST.get('description', 'حجب يدوي من مركز الأمان')
        
        blocked = BlockedIP.block_ip(
            ip_address=ip_address,
            description=description,
            reason='MANUAL_BLOCK',
            user=request.user
        )
        
        if blocked:
            return JsonResponse({
                'success': True,
                'message': f'تم حجب عنوان IP: {ip_address}'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'فشل حجب عنوان IP'
            }, status=500)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def unblock_ip_address(request, blocked_ip_id):
    """Unblock an IP address"""
    from governance.models import BlockedIP
    from django.http import JsonResponse
    
    try:
        blocked_ip = BlockedIP.objects.get(id=blocked_ip_id)
        ip_address = blocked_ip.ip_address
        
        blocked_ip.unblock(user=request.user)
        
        return JsonResponse({
            'success': True,
            'message': f'تم إلغاء حجب عنوان IP: {ip_address}'
        })
    except BlockedIP.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'عنوان IP غير موجود'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def terminate_session(request, session_id):
    """Terminate a user session"""
    from governance.models import ActiveSession
    from django.http import JsonResponse
    from django.contrib.sessions.models import Session
    
    try:
        session = ActiveSession.objects.get(id=session_id)
        username = session.user.username
        session_key = session.session_key
        
        # Terminate in our tracking system
        session.terminate(terminated_by=request.user)
        
        # Delete the actual Django session
        try:
            django_session = Session.objects.get(session_key=session_key)
            django_session.delete()
            logger.info(f"Django session {session_key} deleted for user {username}")
        except Session.DoesNotExist:
            logger.warning(f"Django session {session_key} not found")
        
        return JsonResponse({
            'success': True,
            'message': f'تم إنهاء جلسة المستخدم: {username}'
        })
    except ActiveSession.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'الجلسة غير موجودة'}, status=404)
    except Exception as e:
        logger.error(f"Error terminating session: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# Security Policies API Views
@login_required
@require_http_methods(["POST"])
def rotate_encryption_key(request, key_id):
    """Rotate an encryption key"""
    from governance.services.security_policy_service import SecurityPolicyService
    
    try:
        service = SecurityPolicyService()
        new_key = service.rotate_encryption_key(key_id, request.user)
        
        return JsonResponse({
            'success': True,
            'message': f'تم تدوير المفتاح بنجاح',
            'new_key': {
                'id': new_key.id,
                'key_name': new_key.key_name,
                'expires_at': new_key.expires_at.isoformat()
            }
        })
    except Exception as e:
        logger.error(f"Error rotating encryption key: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def create_encryption_key(request):
    """Create a new encryption key"""
    from governance.services.security_policy_service import SecurityPolicyService
    import json
    
    try:
        data = json.loads(request.body)
        
        key_name = data.get('key_name')
        key_type = data.get('key_type')
        duration_months = int(data.get('duration_months', 12))
        notes = data.get('notes', '')
        
        if not key_name or not key_type:
            return JsonResponse({
                'success': False,
                'error': 'يرجى إدخال اسم المفتاح ونوع التشفير'
            }, status=400)
        
        service = SecurityPolicyService()
        key = service.create_encryption_key(
            key_name=key_name,
            key_type=key_type,
            duration_months=duration_months,
            user=request.user,
            notes=notes
        )
        
        return JsonResponse({
            'success': True,
            'message': f'تم إنشاء المفتاح {key_name} بنجاح',
            'key': {
                'id': key.id,
                'key_name': key.key_name,
                'key_type': key.key_type,
                'expires_at': key.expires_at.isoformat()
            }
        })
    except Exception as e:
        logger.error(f"Error creating encryption key: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def run_security_scan(request):
    """Run a comprehensive security scan"""
    from governance.services.security_policy_service import SecurityPolicyService
    
    try:
        service = SecurityPolicyService()
        results = service.run_security_scan(request.user)
        
        return JsonResponse({
            'success': True,
            'message': 'تم إكمال الفحص الأمني',
            'results': {
                'issues_found': results['issues_found'],
                'warnings': results['warnings'],
                'recommendations': results['recommendations'],
                'timestamp': results['timestamp'].isoformat()
            }
        })
    except Exception as e:
        logger.error(f"Error running security scan: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def rotate_all_keys(request):
    """Rotate all active encryption keys"""
    from governance.services.security_policy_service import SecurityPolicyService
    from governance.models import EncryptionKey
    
    try:
        service = SecurityPolicyService()
        active_keys = EncryptionKey.objects.filter(status='ACTIVE')
        
        rotated_count = 0
        errors = []
        
        for key in active_keys:
            try:
                service.rotate_encryption_key(key.id, request.user)
                rotated_count += 1
            except Exception as e:
                errors.append(f"{key.key_name}: {str(e)}")
        
        return JsonResponse({
            'success': True,
            'message': f'تم تدوير {rotated_count} مفتاح بنجاح',
            'rotated_count': rotated_count,
            'errors': errors
        })
    except Exception as e:
        logger.error(f"Error rotating all keys: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def export_security_report(request):
    """Export security report"""
    from django.http import HttpResponse
    from governance.services.security_policy_service import SecurityPolicyService
    import json
    from datetime import datetime
    
    try:
        service = SecurityPolicyService()
        
        report = {
            'generated_at': datetime.now().isoformat(),
            'generated_by': request.user.username,
            'overview': service.get_security_overview(),
            'statistics': service.get_security_statistics(),
            'auth_policies': service.get_authentication_policies(),
            'network_policies': service.get_network_policies(),
            'encryption_keys': service.get_encryption_keys(),
            'protection_status': service.get_protection_status()
        }
        
        # Create JSON response
        response = HttpResponse(
            json.dumps(report, indent=2, ensure_ascii=False),
            content_type='application/json; charset=utf-8'
        )
        response['Content-Disposition'] = f'attachment; filename="security_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json"'
        
        return response
    except Exception as e:
        logger.error(f"Error exporting security report: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
