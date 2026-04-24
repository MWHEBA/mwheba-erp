"""
Admin configuration for Reports Builder models
"""

from django.contrib import admin
from django.utils.html import format_html
from .models import SavedReport, ReportSchedule, ReportExecution


@admin.register(SavedReport)
class SavedReportAdmin(admin.ModelAdmin):
    list_display = ['name', 'report_type', 'data_source', 'created_by', 'status', 'run_count', 'last_run_at', 'created_at']
    list_filter = ['status', 'report_type', 'data_source', 'is_public', 'created_at']
    search_fields = ['name', 'description', 'created_by__username']
    readonly_fields = ['created_at', 'updated_at', 'last_run_at', 'run_count']
    
    fieldsets = (
        ('معلومات أساسية', {
            'fields': ('name', 'description', 'status', 'is_public')
        }),
        ('إعدادات التقرير', {
            'fields': ('report_type', 'data_source', 'selected_fields', 'filters', 'group_by', 'sort_by', 'sort_order')
        }),
        ('معلومات التتبع', {
            'fields': ('created_by', 'created_at', 'updated_at', 'last_run_at', 'run_count'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('created_by')


@admin.register(ReportSchedule)
class ReportScheduleAdmin(admin.ModelAdmin):
    list_display = ['report', 'frequency', 'schedule_time', 'status', 'next_run_at', 'last_run_at', 'created_by']
    list_filter = ['status', 'frequency', 'created_at']
    search_fields = ['report__name', 'email_recipients', 'created_by__username']
    readonly_fields = ['created_at', 'last_run_at', 'next_run_at']
    
    fieldsets = (
        ('التقرير', {
            'fields': ('report', 'status')
        }),
        ('إعدادات الجدولة', {
            'fields': ('frequency', 'schedule_time', 'day_of_week', 'day_of_month')
        }),
        ('المستلمون', {
            'fields': ('email_recipients',)
        }),
        ('معلومات التتبع', {
            'fields': ('created_by', 'created_at', 'last_run_at', 'next_run_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('report', 'created_by')


@admin.register(ReportExecution)
class ReportExecutionAdmin(admin.ModelAdmin):
    list_display = ['report', 'status', 'started_at', 'execution_time_display', 'rows_count', 'triggered_by']
    list_filter = ['status', 'started_at']
    search_fields = ['report__name', 'triggered_by__username']
    readonly_fields = ['report', 'schedule', 'status', 'started_at', 'completed_at', 'execution_time_ms', 
                      'triggered_by', 'rows_count', 'result_data', 'error_message', 'error_traceback']
    
    fieldsets = (
        ('معلومات التنفيذ', {
            'fields': ('report', 'schedule', 'status', 'triggered_by')
        }),
        ('التوقيت', {
            'fields': ('started_at', 'completed_at', 'execution_time_ms')
        }),
        ('النتائج', {
            'fields': ('rows_count', 'result_data'),
            'classes': ('collapse',)
        }),
        ('الأخطاء', {
            'fields': ('error_message', 'error_traceback'),
            'classes': ('collapse',)
        }),
    )
    
    def execution_time_display(self, obj):
        if obj.execution_time_ms:
            if obj.execution_time_ms < 1000:
                return f"{obj.execution_time_ms} ms"
            else:
                return f"{obj.execution_time_ms / 1000:.2f} s"
        return "-"
    execution_time_display.short_description = 'وقت التنفيذ'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('report', 'schedule', 'triggered_by')
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
