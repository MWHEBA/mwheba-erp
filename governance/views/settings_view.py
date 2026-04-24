from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from governance.models import (
    AuditTrail, SecurityIncident, SignalRegistry, 
    SavedReport, SecurityPolicy, QuarantineRecord
)
from django.utils import timezone
from datetime import timedelta


class GovernanceSettingsView(LoginRequiredMixin, TemplateView):
    """Governance Settings Hub - Central page for all governance links"""
    template_name = 'governance/settings.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Page header configuration
        context.update({
            'active_menu': 'settings',
            'title': 'إعدادات الحوكمة والإدارة',
            'subtitle': 'مركز إدارة الحوكمة والأمان والتقارير',
            'icon': 'fas fa-shield-alt',
            'breadcrumb_items': [
                {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
                {'title': 'الإعدادات', 'url': '#', 'icon': 'fas fa-cog'},
                {'title': 'إعدادات الحوكمة', 'active': True}
            ]
        })
        
        # Get statistics for each section
        today_start = timezone.make_aware(
            timezone.datetime.combine(timezone.now().date(), timezone.datetime.min.time())
        )
        week_ago = timezone.now() - timedelta(days=7)
        
        # Audit statistics
        total_audit_records = AuditTrail.objects.count()
        today_audit_records = AuditTrail.objects.filter(timestamp__gte=today_start).count()
        
        # System health statistics
        active_quarantine = QuarantineRecord.objects.filter(
            status__in=['QUARANTINED', 'UNDER_REVIEW']
        ).count()
        critical_exceptions = AuditTrail.objects.filter(
            timestamp__gte=week_ago,
            operation='EXCEPTION',
            resolution_status='ACTIVE'
        ).count()
        
        # Security statistics
        active_incidents = SecurityIncident.objects.filter(status='ACTIVE').count()
        total_incidents = SecurityIncident.objects.count()
        
        # Security policies statistics
        total_policies = SecurityPolicy.objects.count()
        active_policies = SecurityPolicy.objects.filter(is_enabled=True).count()
        
        # Signals statistics
        total_signals = SignalRegistry.objects.count()
        active_signals = SignalRegistry.objects.filter(status='ACTIVE').count()
        
        # Reports statistics
        total_reports = SavedReport.objects.count()
        user_reports = SavedReport.objects.filter(created_by=self.request.user).count()
        
        context.update({
            # Audit stats
            'total_audit_records': total_audit_records,
            'today_audit_records': today_audit_records,
            
            # Health stats
            'active_quarantine': active_quarantine,
            'critical_exceptions': critical_exceptions,
            
            # Security stats
            'active_incidents': active_incidents,
            'total_incidents': total_incidents,
            
            # Policies stats
            'total_policies': total_policies,
            'active_policies': active_policies,
            
            # Signals stats
            'total_signals': total_signals,
            'active_signals': active_signals,
            
            # Reports stats
            'total_reports': total_reports,
            'user_reports': user_reports,
        })
        
        return context
