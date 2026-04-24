"""
Django Admin interface for QuarantineSystem.

Provides comprehensive admin interface for:
- Viewing quarantine records
- Batch operations
- Statistics and reporting
- Health monitoring
"""

from django.contrib import admin
from django.contrib import messages
from django.shortcuts import render, redirect
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.http import JsonResponse, HttpResponse
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
import json

from .models import QuarantineRecord
from .services.quarantine_system import quarantine_system


class QuarantineRecordAdmin(admin.ModelAdmin):
    """Admin interface for QuarantineRecord model"""
    
    list_display = [
        'id', 'model_name', 'object_id', 'corruption_type_display', 
        'status_display', 'quarantined_at', 'quarantined_by', 
        'resolved_at', 'actions_display'
    ]
    
    list_filter = [
        'status', 'corruption_type', 'model_name', 
        'quarantined_at', 'resolved_at'
    ]
    
    search_fields = [
        'model_name', 'object_id', 'quarantine_reason', 
        'resolution_notes', 'quarantined_by__username'
    ]
    
    readonly_fields = [
        'id', 'quarantined_at', 'quarantined_by', 'original_data_display',
        'resolved_at', 'resolved_by'
    ]
    
    fieldsets = (
        ('Quarantine Information', {
            'fields': (
                'id', 'model_name', 'object_id', 'corruption_type',
                'quarantine_reason', 'quarantined_at', 'quarantined_by'
            )
        }),
        ('Original Data', {
            'fields': ('original_data_display',),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('status',)
        }),
        ('Resolution', {
            'fields': (
                'resolution_notes', 'resolved_at', 'resolved_by'
            ),
            'classes': ('collapse',)
        }),
    )
    
    actions = [
        'mark_under_review', 'resolve_selected', 'export_to_json'
    ]
    
    def get_urls(self):
        """Add custom admin URLs"""
        urls = super().get_urls()
        custom_urls = [
            path('statistics/', self.admin_site.admin_view(self.statistics_view), 
                 name='governance_quarantinerecord_statistics'),
            path('health-check/', self.admin_site.admin_view(self.health_check_view), 
                 name='governance_quarantinerecord_health_check'),
            path('batch-resolve/', self.admin_site.admin_view(self.batch_resolve_view), 
                 name='governance_quarantinerecord_batch_resolve'),
            path('trends/', self.admin_site.admin_view(self.trends_view), 
                 name='governance_quarantinerecord_trends'),
        ]
        return custom_urls + urls
    
    def corruption_type_display(self, obj):
        """Display corruption type with color coding"""
        colors = {
            'ORPHANED_ENTRY': '#ff6b6b',
            'NEGATIVE_STOCK': '#ffa726',
            'UNBALANCED_ENTRY': '#ab47bc',
            'MULTIPLE_ACTIVE_YEAR': '#42a5f5',
            'INVALID_SOURCE_LINK': '#ef5350',
            'AUTHORITY_VIOLATION': '#d32f2f',
            'SUSPICIOUS_PATTERN': '#8d6e63'
        }
        color = colors.get(obj.corruption_type, '#666666')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.corruption_type.replace('_', ' ').title()
        )
    corruption_type_display.short_description = 'Corruption Type'
    
    def status_display(self, obj):
        """Display status with color coding"""
        colors = {
            'QUARANTINED': '#f44336',
            'UNDER_REVIEW': '#ff9800',
            'RESOLVED': '#4caf50',
            'PERMANENT': '#9e9e9e'
        }
        color = colors.get(obj.status, '#666666')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.status
        )
    status_display.short_description = 'Status'
    
    def original_data_display(self, obj):
        """Display original data as formatted JSON"""
        if obj.original_data:
            formatted_json = json.dumps(obj.original_data, indent=2)
            return format_html('<pre>{}</pre>', formatted_json)
        return 'No data'
    original_data_display.short_description = 'Original Data'
    
    def actions_display(self, obj):
        """Display action buttons"""
        actions = []
        
        if obj.status in ['QUARANTINED', 'UNDER_REVIEW']:
            resolve_url = reverse('admin:governance_quarantinerecord_change', args=[obj.id])
            actions.append(f'<a href="{resolve_url}" class="button">Edit</a>')
        
        if obj.status == 'QUARANTINED':
            actions.append('<span style="color: #ff9800;">Under Review</span>')
        
        return format_html(' '.join(actions))
    actions_display.short_description = 'Actions'
    
    def mark_under_review(self, request, queryset):
        """Mark selected records as under review"""
        updated = 0
        for record in queryset.filter(status='QUARANTINED'):
            try:
                quarantine_system.storage.update_quarantine_status(
                    quarantine_id=record.id,
                    new_status='UNDER_REVIEW',
                    user=request.user,
                    notes='Marked for review via admin'
                )
                updated += 1
            except Exception as e:
                messages.error(request, f'Failed to update record {record.id}: {str(e)}')
        
        if updated > 0:
            messages.success(request, f'Marked {updated} records as under review')
    mark_under_review.short_description = 'Mark selected as under review'
    
    def resolve_selected(self, request, queryset):
        """Resolve selected records"""
        if 'apply' in request.POST:
            resolution_notes = request.POST.get('resolution_notes', '')
            if not resolution_notes:
                messages.error(request, 'Resolution notes are required')
                return
            
            updated = 0
            for record in queryset.exclude(status='RESOLVED'):
                try:
                    quarantine_system.resolve_quarantine(
                        quarantine_id=record.id,
                        resolution_notes=resolution_notes,
                        user=request.user
                    )
                    updated += 1
                except Exception as e:
                    messages.error(request, f'Failed to resolve record {record.id}: {str(e)}')
            
            if updated > 0:
                messages.success(request, f'Resolved {updated} records')
            return redirect(request.get_full_path())
        
        # Show confirmation form
        context = {
            'title': 'Resolve Selected Quarantine Records',
            'queryset': queryset.exclude(status='RESOLVED'),
            'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
        }
        return render(request, 'governance/admin/resolve_quarantine_confirmation.html', context)
    resolve_selected.short_description = 'Resolve selected records'
    
    def export_to_json(self, request, queryset):
        """Export selected records to JSON"""
        data = []
        for record in queryset:
            data.append({
                'id': record.id,
                'model_name': record.model_name,
                'object_id': record.object_id,
                'corruption_type': record.corruption_type,
                'status': record.status,
                'quarantine_reason': record.quarantine_reason,
                'original_data': record.original_data,
                'quarantined_at': record.quarantined_at.isoformat(),
                'quarantined_by': record.quarantined_by.username if record.quarantined_by else None,
                'resolved_at': record.resolved_at.isoformat() if record.resolved_at else None,
                'resolved_by': record.resolved_by.username if record.resolved_by else None,
                'resolution_notes': record.resolution_notes
            })
        
        response = HttpResponse(
            json.dumps(data, indent=2),
            content_type='application/json'
        )
        response['Content-Disposition'] = 'attachment; filename="quarantine_records.json"'
        return response
    export_to_json.short_description = 'Export selected to JSON'
    
    def statistics_view(self, request):
        """Display quarantine statistics"""
        # Get date range from request
        days = int(request.GET.get('days', 30))
        date_from = timezone.now() - timedelta(days=days)
        
        # Get statistics
        stats = quarantine_system.get_quarantine_statistics(date_from=date_from)
        
        # Get additional admin-specific stats
        total_records = QuarantineRecord.objects.count()
        recent_24h = QuarantineRecord.objects.filter(
            quarantined_at__gte=timezone.now() - timedelta(hours=24)
        ).count()
        
        # Status distribution
        status_distribution = QuarantineRecord.objects.values('status').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Corruption type distribution
        corruption_distribution = QuarantineRecord.objects.values('corruption_type').annotate(
            count=Count('id')
        ).order_by('-count')
        
        context = {
            'title': 'Quarantine Statistics',
            'stats': stats,
            'total_records': total_records,
            'recent_24h': recent_24h,
            'status_distribution': status_distribution,
            'corruption_distribution': corruption_distribution,
            'days': days,
            'opts': self.model._meta,
        }
        
        return render(request, 'governance/admin/quarantine_statistics.html', context)
    
    def health_check_view(self, request):
        """Display quarantine system health check"""
        health_status = quarantine_system.health_check()
        
        context = {
            'title': 'Quarantine System Health Check',
            'health_status': health_status,
            'opts': self.model._meta,
        }
        
        return render(request, 'governance/admin/quarantine_health_check.html', context)
    
    def batch_resolve_view(self, request):
        """Batch resolve quarantine records"""
        if request.method == 'POST':
            ids_str = request.POST.get('quarantine_ids', '')
            resolution_notes = request.POST.get('resolution_notes', '')
            
            if not ids_str or not resolution_notes:
                messages.error(request, 'Both quarantine IDs and resolution notes are required')
            else:
                try:
                    quarantine_ids = [int(id_str.strip()) for id_str in ids_str.split(',')]
                    result = quarantine_system.batch_resolve_quarantine(
                        quarantine_ids=quarantine_ids,
                        resolution_notes=resolution_notes,
                        user=request.user
                    )
                    
                    updated_count = len(result['updated'])
                    failed_count = len(result['failed'])
                    
                    if updated_count > 0:
                        messages.success(request, f'Successfully resolved {updated_count} records')
                    
                    if failed_count > 0:
                        messages.error(request, f'Failed to resolve {failed_count} records')
                        for failure in result['failed']:
                            messages.error(request, f'ID {failure["id"]}: {failure["error"]}')
                
                except ValueError:
                    messages.error(request, 'Invalid quarantine IDs format. Use comma-separated integers.')
                except Exception as e:
                    messages.error(request, f'Batch resolve failed: {str(e)}')
        
        # Get unresolved records for the form
        unresolved_records = QuarantineRecord.objects.exclude(status='RESOLVED').order_by('-quarantined_at')[:50]
        
        context = {
            'title': 'Batch Resolve Quarantine Records',
            'unresolved_records': unresolved_records,
            'opts': self.model._meta,
        }
        
        return render(request, 'governance/admin/batch_resolve_quarantine.html', context)
    
    def trends_view(self, request):
        """Display quarantine trends"""
        days = int(request.GET.get('days', 30))
        trends = quarantine_system.manager.get_quarantine_trends(days=days)
        
        context = {
            'title': 'Quarantine Trends',
            'trends': trends,
            'days': days,
            'opts': self.model._meta,
        }
        
        return render(request, 'governance/admin/quarantine_trends.html', context)
    
    def changelist_view(self, request, extra_context=None):
        """Add extra context to changelist view"""
        extra_context = extra_context or {}
        
        # Add quick stats to changelist
        extra_context['quick_stats'] = {
            'total': QuarantineRecord.objects.count(),
            'quarantined': QuarantineRecord.objects.filter(status='QUARANTINED').count(),
            'under_review': QuarantineRecord.objects.filter(status='UNDER_REVIEW').count(),
            'resolved': QuarantineRecord.objects.filter(status='RESOLVED').count(),
            'recent_24h': QuarantineRecord.objects.filter(
                quarantined_at__gte=timezone.now() - timedelta(hours=24)
            ).count(),
        }
        
        # Add custom admin URLs
        extra_context['custom_urls'] = {
            'statistics': reverse('admin:governance_quarantinerecord_statistics'),
            'health_check': reverse('admin:governance_quarantinerecord_health_check'),
            'batch_resolve': reverse('admin:governance_quarantinerecord_batch_resolve'),
            'trends': reverse('admin:governance_quarantinerecord_trends'),
        }
        
        return super().changelist_view(request, extra_context=extra_context)


# Register the admin
admin.site.register(QuarantineRecord, QuarantineRecordAdmin)


# Add custom admin site configuration
class QuarantineAdminSite(admin.AdminSite):
    """Custom admin site for quarantine management"""
    site_header = 'Quarantine System Administration'
    site_title = 'Quarantine Admin'
    index_title = 'Quarantine System Management'
    
    def index(self, request, extra_context=None):
        """Custom admin index with quarantine overview"""
        extra_context = extra_context or {}
        
        # Add quarantine system overview
        health_status = quarantine_system.health_check()
        stats = quarantine_system.get_quarantine_statistics()
        
        extra_context['quarantine_overview'] = {
            'health_status': health_status,
            'stats': stats,
            'recent_quarantines': QuarantineRecord.objects.order_by('-quarantined_at')[:5]
        }
        
        return super().index(request, extra_context=extra_context)


# Create custom admin site instance
quarantine_admin_site = QuarantineAdminSite(name='quarantine_admin')