"""
✅ PHASE 7: Simplified Monitoring Admin
Basic admin interface for simplified monitoring system
"""
from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from django.db.models import Count
from core.models import UnifiedLog, AlertRule, Alert


@admin.register(UnifiedLog)
class UnifiedLogAdmin(admin.ModelAdmin):
    """Simplified admin for unified logs"""
    list_display = ['timestamp', 'log_type', 'level', 'category', 'message_preview', 'user']
    list_filter = ['log_type', 'level', 'category', 'timestamp']
    search_fields = ['message', 'user__username', 'ip_address']
    readonly_fields = ['timestamp', 'log_type', 'level', 'category', 'message', 'user', 'request_id', 'ip_address', 'user_agent', 'data']
    date_hierarchy = 'timestamp'
    ordering = ['-timestamp']
    list_per_page = 50
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('timestamp', 'log_type', 'level', 'category', 'message')
        }),
        ('User Information', {
            'fields': ('user', 'ip_address', 'user_agent', 'request_id')
        }),
        ('Additional Data', {
            'fields': ('data',),
            'classes': ('collapse',)
        })
    )
    
    def message_preview(self, obj):
        """Show truncated message"""
        return obj.message[:100] + '...' if len(obj.message) > 100 else obj.message
    message_preview.short_description = 'Message Preview'
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(AlertRule)
class AlertRuleAdmin(admin.ModelAdmin):
    """Simplified admin for alert rules"""
    list_display = ['name', 'metric_type', 'severity', 'threshold_display', 'time_window_minutes', 'is_active']
    list_filter = ['metric_type', 'severity', 'is_active']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'is_active')
        }),
        ('Alert Conditions', {
            'fields': ('metric_type', 'operator', 'threshold_value', 'time_window_minutes', 'severity')
        }),
        ('Notifications', {
            'fields': ('email_recipients',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def threshold_display(self, obj):
        """Display threshold condition"""
        return f"{obj.get_operator_display()} {obj.threshold_value}"
    threshold_display.short_description = 'Threshold'


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    """Simplified admin for alerts"""
    list_display = ['created_at', 'rule', 'status', 'severity_display', 'metric_value', 'acknowledged_by']
    list_filter = ['status', 'rule__severity', 'created_at']
    search_fields = ['rule__name', 'message']
    readonly_fields = ['created_at', 'updated_at', 'rule', 'message', 'metric_value', 'threshold_value']
    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    
    fieldsets = (
        ('Alert Information', {
            'fields': ('rule', 'status', 'message', 'metric_value', 'threshold_value')
        }),
        ('Management', {
            'fields': ('acknowledged_by', 'acknowledged_at', 'resolved_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def severity_display(self, obj):
        """Display alert severity with color"""
        colors = {
            'critical': 'red',
            'error': 'orange',
            'warning': 'yellow',
            'info': 'blue'
        }
        color = colors.get(obj.rule.severity, 'black')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.rule.get_severity_display()
        )
    severity_display.short_description = 'Severity'
    
    actions = ['acknowledge_alerts', 'resolve_alerts']
    
    def acknowledge_alerts(self, request, queryset):
        """Acknowledge selected alerts"""
        updated = 0
        for alert in queryset.filter(status='active'):
            alert.acknowledge(request.user)
            updated += 1
        
        self.message_user(request, f'{updated} alerts acknowledged successfully.')
    acknowledge_alerts.short_description = 'Acknowledge selected alerts'
    
    def resolve_alerts(self, request, queryset):
        """Resolve selected alerts"""
        updated = 0
        for alert in queryset.filter(status__in=['active', 'acknowledged']):
            alert.resolve()
            updated += 1
        
        self.message_user(request, f'{updated} alerts resolved successfully.')
    resolve_alerts.short_description = 'Resolve selected alerts'