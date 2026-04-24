from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils import timezone
from .models import IdempotencyRecord, AuditTrail, QuarantineRecord, AuthorityDelegation
import json


@admin.register(IdempotencyRecord)
class IdempotencyRecordAdmin(admin.ModelAdmin):
    list_display = [
        'operation_type', 
        'idempotency_key', 
        'created_by', 
        'created_at', 
        'expires_at',
        'is_expired_display'
    ]
    list_filter = [
        'operation_type', 
        'created_at', 
        'expires_at',
        'created_by'
    ]
    search_fields = [
        'operation_type', 
        'idempotency_key',
        'created_by__username'
    ]
    readonly_fields = [
        'created_at', 
        'result_data_display',
        'is_expired_display'
    ]
    ordering = ['-created_at']
    
    def is_expired_display(self, obj):
        if obj.is_expired():
            return format_html('<span style="color: red;">منتهي الصلاحية</span>')
        return format_html('<span style="color: green;">صالح</span>')
    is_expired_display.short_description = 'الحالة'
    
    def result_data_display(self, obj):
        if obj.result_data:
            formatted_json = json.dumps(obj.result_data, indent=2, ensure_ascii=False)
            return format_html('<pre>{}</pre>', formatted_json)
        return 'لا توجد بيانات'
    result_data_display.short_description = 'بيانات النتيجة'
    
    def has_delete_permission(self, request, obj=None):
        # Only allow deletion of expired records
        if obj and not obj.is_expired():
            return False
        return super().has_delete_permission(request, obj)


@admin.register(AuditTrail)
class AuditTrailAdmin(admin.ModelAdmin):
    list_display = [
        'model_name',
        'object_id', 
        'operation',
        'user',
        'source_service',
        'timestamp',
        'has_changes_display'
    ]
    list_filter = [
        'model_name',
        'operation',
        'source_service',
        'timestamp',
        'user'
    ]
    search_fields = [
        'model_name',
        'object_id',
        'user__username',
        'source_service'
    ]
    readonly_fields = [
        'timestamp',
        'before_data_display',
        'after_data_display',
        'additional_context_display',
        'changes_summary'
    ]
    ordering = ['-timestamp']
    date_hierarchy = 'timestamp'
    
    def has_changes_display(self, obj):
        if obj.before_data or obj.after_data:
            return format_html('<span style="color: green;">✓</span>')
        return format_html('<span style="color: gray;">-</span>')
    has_changes_display.short_description = 'تغييرات'
    
    def before_data_display(self, obj):
        if obj.before_data:
            formatted_json = json.dumps(obj.before_data, indent=2, ensure_ascii=False)
            return format_html('<pre>{}</pre>', formatted_json)
        return 'لا توجد بيانات'
    before_data_display.short_description = 'البيانات السابقة'
    
    def after_data_display(self, obj):
        if obj.after_data:
            formatted_json = json.dumps(obj.after_data, indent=2, ensure_ascii=False)
            return format_html('<pre>{}</pre>', formatted_json)
        return 'لا توجد بيانات'
    after_data_display.short_description = 'البيانات الجديدة'
    
    def additional_context_display(self, obj):
        if obj.additional_context:
            formatted_json = json.dumps(obj.additional_context, indent=2, ensure_ascii=False)
            return format_html('<pre>{}</pre>', formatted_json)
        return 'لا توجد بيانات إضافية'
    additional_context_display.short_description = 'السياق الإضافي'
    
    def changes_summary(self, obj):
        if obj.before_data and obj.after_data:
            changes = []
            for key in set(list(obj.before_data.keys()) + list(obj.after_data.keys())):
                old_val = obj.before_data.get(key, 'غير موجود')
                new_val = obj.after_data.get(key, 'محذوف')
                if old_val != new_val:
                    changes.append(f"{key}: {old_val} → {new_val}")
            
            if changes:
                return format_html('<br>'.join(changes))
        return 'لا توجد تغييرات'
    changes_summary.short_description = 'ملخص التغييرات'
    
    def has_add_permission(self, request):
        # Audit trails should only be created programmatically
        return False
    
    def has_delete_permission(self, request, obj=None):
        # Audit trails should be immutable
        return False


@admin.register(QuarantineRecord)
class QuarantineRecordAdmin(admin.ModelAdmin):
    list_display = [
        'model_name',
        'object_id',
        'corruption_type',
        'status',
        'quarantined_by',
        'quarantined_at',
        'resolved_by',
        'resolved_at'
    ]
    list_filter = [
        'model_name',
        'corruption_type',
        'status',
        'quarantined_at',
        'resolved_at'
    ]
    search_fields = [
        'model_name',
        'object_id',
        'quarantine_reason',
        'quarantined_by__username'
    ]
    readonly_fields = [
        'quarantined_at',
        'original_data_display',
        'quarantine_reason_display'
    ]
    ordering = ['-quarantined_at']
    date_hierarchy = 'quarantined_at'
    
    fieldsets = (
        ('معلومات الحجر الصحي', {
            'fields': (
                'model_name',
                'object_id', 
                'corruption_type',
                'quarantine_reason_display',
                'quarantined_by',
                'quarantined_at'
            )
        }),
        ('البيانات الأصلية', {
            'fields': ('original_data_display',),
            'classes': ('collapse',)
        }),
        ('حالة الحل', {
            'fields': (
                'status',
                'resolution_notes',
                'resolved_by',
                'resolved_at'
            )
        })
    )
    
    def original_data_display(self, obj):
        if obj.original_data:
            formatted_json = json.dumps(obj.original_data, indent=2, ensure_ascii=False)
            return format_html('<pre>{}</pre>', formatted_json)
        return 'لا توجد بيانات'
    original_data_display.short_description = 'البيانات الأصلية'
    
    def quarantine_reason_display(self, obj):
        return format_html('<div style="max-width: 400px; word-wrap: break-word;">{}</div>', obj.quarantine_reason)
    quarantine_reason_display.short_description = 'سبب الحجر الصحي'
    
    def save_model(self, request, obj, form, change):
        if change and obj.status == 'RESOLVED' and not obj.resolved_by:
            obj.resolved_by = request.user
            obj.resolved_at = timezone.now()
        super().save_model(request, obj, form, change)


@admin.register(AuthorityDelegation)
class AuthorityDelegationAdmin(admin.ModelAdmin):
    list_display = [
        'from_service',
        'to_service',
        'model_name',
        'granted_by',
        'granted_at',
        'expires_at',
        'is_active',
        'status_display'
    ]
    list_filter = [
        'from_service',
        'to_service',
        'model_name',
        'is_active',
        'granted_at',
        'expires_at'
    ]
    search_fields = [
        'from_service',
        'to_service',
        'model_name',
        'reason',
        'granted_by__username'
    ]
    readonly_fields = [
        'granted_at',
        'is_expired_display',
        'is_valid_display',
        'time_remaining'
    ]
    ordering = ['-granted_at']
    date_hierarchy = 'granted_at'
    
    fieldsets = (
        ('معلومات التفويض', {
            'fields': (
                'from_service',
                'to_service',
                'model_name',
                'reason'
            )
        }),
        ('التوقيت', {
            'fields': (
                'granted_at',
                'expires_at',
                'time_remaining',
                'is_expired_display'
            )
        }),
        ('الحالة', {
            'fields': (
                'is_active',
                'is_valid_display',
                'granted_by'
            )
        }),
        ('الإلغاء', {
            'fields': (
                'revoked_at',
                'revoked_by'
            ),
            'classes': ('collapse',)
        })
    )
    
    def status_display(self, obj):
        if obj.is_valid():
            return format_html('<span style="color: green;">صالح</span>')
        elif obj.is_expired():
            return format_html('<span style="color: red;">منتهي الصلاحية</span>')
        elif obj.revoked_at:
            return format_html('<span style="color: orange;">ملغي</span>')
        else:
            return format_html('<span style="color: gray;">غير نشط</span>')
    status_display.short_description = 'الحالة'
    
    def is_expired_display(self, obj):
        if obj.is_expired():
            return format_html('<span style="color: red;">منتهي الصلاحية</span>')
        return format_html('<span style="color: green;">صالح</span>')
    is_expired_display.short_description = 'انتهاء الصلاحية'
    
    def is_valid_display(self, obj):
        if obj.is_valid():
            return format_html('<span style="color: green;">✓ صالح</span>')
        return format_html('<span style="color: red;">✗ غير صالح</span>')
    is_valid_display.short_description = 'صالح للاستخدام'
    
    def time_remaining(self, obj):
        from django.utils import timezone
        if obj.is_expired():
            return 'منتهي الصلاحية'
        
        remaining = obj.expires_at - timezone.now()
        hours = remaining.total_seconds() / 3600
        
        if hours < 1:
            minutes = remaining.total_seconds() / 60
            return f'{int(minutes)} دقيقة'
        elif hours < 24:
            return f'{int(hours)} ساعة'
        else:
            days = hours / 24
            return f'{int(days)} يوم'
    time_remaining.short_description = 'الوقت المتبقي'
    
    def save_model(self, request, obj, form, change):
        if not change:  # New delegation
            obj.granted_by = request.user
        super().save_model(request, obj, form, change)
    
    actions = ['revoke_delegations']
    
    def revoke_delegations(self, request, queryset):
        count = 0
        for delegation in queryset.filter(is_active=True, revoked_at__isnull=True):
            delegation.revoke(request.user, "إلغاء من لوحة الإدارة")
            count += 1
        
        self.message_user(request, f'تم إلغاء {count} تفويض بنجاح.')
    revoke_delegations.short_description = 'إلغاء التفويضات المحددة'



# Security Models Admin
from .models import SecurityIncident, BlockedIP, ActiveSession, SecurityPolicy


@admin.register(SecurityIncident)
class SecurityIncidentAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'incident_type',
        'severity',
        'status',
        'ip_address',
        'user',
        'detected_at',
        'resolved_at'
    ]
    list_filter = [
        'incident_type',
        'severity',
        'status',
        'detected_at',
        'resolved_at'
    ]
    search_fields = [
        'ip_address',
        'username_attempted',
        'user__username',
        'description'
    ]
    readonly_fields = [
        'detected_at',
        'additional_data_display'
    ]
    ordering = ['-detected_at']
    date_hierarchy = 'detected_at'
    
    fieldsets = (
        ('معلومات الحادث', {
            'fields': (
                'incident_type',
                'severity',
                'status',
                'description'
            )
        }),
        ('معلومات المستخدم والشبكة', {
            'fields': (
                'ip_address',
                'user',
                'username_attempted',
                'user_agent',
                'request_path',
                'request_method'
            )
        }),
        ('التوقيت', {
            'fields': (
                'detected_at',
                'resolved_at',
                'resolved_by',
                'resolution_notes'
            )
        }),
        ('بيانات إضافية', {
            'fields': ('additional_data_display',),
            'classes': ('collapse',)
        })
    )
    
    def additional_data_display(self, obj):
        if obj.additional_data:
            formatted_json = json.dumps(obj.additional_data, indent=2, ensure_ascii=False)
            return format_html('<pre>{}</pre>', formatted_json)
        return 'لا توجد بيانات إضافية'
    additional_data_display.short_description = 'البيانات الإضافية'
    
    def save_model(self, request, obj, form, change):
        if change and obj.status == 'RESOLVED' and not obj.resolved_by:
            obj.resolved_by = request.user
            obj.resolved_at = timezone.now()
        super().save_model(request, obj, form, change)
    
    actions = ['mark_as_resolved', 'mark_as_false_positive']
    
    def mark_as_resolved(self, request, queryset):
        count = queryset.filter(status='ACTIVE').update(
            status='RESOLVED',
            resolved_at=timezone.now(),
            resolved_by=request.user
        )
        self.message_user(request, f'تم حل {count} حادث بنجاح.')
    mark_as_resolved.short_description = 'تسجيل كمحلول'
    
    def mark_as_false_positive(self, request, queryset):
        count = queryset.update(
            status='FALSE_POSITIVE',
            resolved_at=timezone.now(),
            resolved_by=request.user
        )
        self.message_user(request, f'تم تسجيل {count} حادث كإنذار خاطئ.')
    mark_as_false_positive.short_description = 'تسجيل كإنذار خاطئ'


@admin.register(BlockedIP)
class BlockedIPAdmin(admin.ModelAdmin):
    list_display = [
        'ip_address',
        'reason',
        'is_active',
        'attempts_count',
        'blocked_at',
        'blocked_by',
        'unblocked_at'
    ]
    list_filter = [
        'reason',
        'is_active',
        'blocked_at',
        'unblocked_at'
    ]
    search_fields = [
        'ip_address',
        'description',
        'blocked_by__username'
    ]
    readonly_fields = [
        'blocked_at',
        'attempts_count',
        'last_attempt_at'
    ]
    ordering = ['-blocked_at']
    date_hierarchy = 'blocked_at'
    
    fieldsets = (
        ('معلومات الحجب', {
            'fields': (
                'ip_address',
                'reason',
                'description',
                'is_active'
            )
        }),
        ('الإحصائيات', {
            'fields': (
                'attempts_count',
                'last_attempt_at'
            )
        }),
        ('التوقيت', {
            'fields': (
                'blocked_at',
                'blocked_by',
                'unblocked_at',
                'unblocked_by'
            )
        })
    )
    
    actions = ['unblock_ips', 'block_ips']
    
    def unblock_ips(self, request, queryset):
        count = 0
        for blocked_ip in queryset.filter(is_active=True):
            blocked_ip.unblock(request.user)
            count += 1
        self.message_user(request, f'تم إلغاء حجب {count} عنوان IP.')
    unblock_ips.short_description = 'إلغاء حجب العناوين المحددة'
    
    def block_ips(self, request, queryset):
        count = queryset.filter(is_active=False).update(
            is_active=True,
            blocked_at=timezone.now(),
            blocked_by=request.user
        )
        self.message_user(request, f'تم حجب {count} عنوان IP.')
    block_ips.short_description = 'حجب العناوين المحددة'


@admin.register(ActiveSession)
class ActiveSessionAdmin(admin.ModelAdmin):
    list_display = [
        'user',
        'ip_address',
        'login_at',
        'last_activity',
        'is_active',
        'terminated_at'
    ]
    list_filter = [
        'is_active',
        'login_at',
        'last_activity',
        'terminated_at'
    ]
    search_fields = [
        'user__username',
        'ip_address',
        'session_key'
    ]
    readonly_fields = [
        'session_key',
        'login_at',
        'last_activity',
        'user_agent_display'
    ]
    ordering = ['-last_activity']
    date_hierarchy = 'login_at'
    
    fieldsets = (
        ('معلومات الجلسة', {
            'fields': (
                'user',
                'session_key',
                'is_active'
            )
        }),
        ('معلومات الشبكة', {
            'fields': (
                'ip_address',
                'user_agent_display'
            )
        }),
        ('التوقيت', {
            'fields': (
                'login_at',
                'last_activity',
                'terminated_at',
                'terminated_by'
            )
        })
    )
    
    def user_agent_display(self, obj):
        if obj.user_agent:
            return format_html('<div style="max-width: 600px; word-wrap: break-word;">{}</div>', obj.user_agent)
        return 'غير متاح'
    user_agent_display.short_description = 'User Agent'
    
    def has_add_permission(self, request):
        return False
    
    actions = ['terminate_sessions']
    
    def terminate_sessions(self, request, queryset):
        count = 0
        for session in queryset.filter(is_active=True):
            session.terminate(terminated_by=request.user)
            count += 1
        self.message_user(request, f'تم إنهاء {count} جلسة.')
    terminate_sessions.short_description = 'إنهاء الجلسات المحددة'


@admin.register(SecurityPolicy)
class SecurityPolicyAdmin(admin.ModelAdmin):
    list_display = [
        'policy_type',
        'is_enabled',
        'updated_at',
        'updated_by'
    ]
    list_filter = [
        'policy_type',
        'is_enabled',
        'updated_at'
    ]
    search_fields = [
        'policy_type',
        'description'
    ]
    readonly_fields = [
        'created_at',
        'updated_at',
        'configuration_display'
    ]
    ordering = ['policy_type']
    
    fieldsets = (
        ('معلومات السياسة', {
            'fields': (
                'policy_type',
                'is_enabled',
                'description'
            )
        }),
        ('الإعدادات', {
            'fields': (
                'configuration',
                'configuration_display'
            )
        }),
        ('التوقيت', {
            'fields': (
                'created_at',
                'updated_at',
                'updated_by'
            )
        })
    )
    
    def configuration_display(self, obj):
        if obj.configuration:
            formatted_json = json.dumps(obj.configuration, indent=2, ensure_ascii=False)
            return format_html('<pre>{}</pre>', formatted_json)
        return 'لا توجد إعدادات'
    configuration_display.short_description = 'الإعدادات (للعرض فقط)'
    
    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
    
    actions = ['enable_policies', 'disable_policies']
    
    def enable_policies(self, request, queryset):
        count = queryset.update(is_enabled=True, updated_by=request.user, updated_at=timezone.now())
        self.message_user(request, f'تم تفعيل {count} سياسة.')
    enable_policies.short_description = 'تفعيل السياسات المحددة'
    
    def disable_policies(self, request, queryset):
        count = queryset.update(is_enabled=False, updated_by=request.user, updated_at=timezone.now())
        self.message_user(request, f'تم تعطيل {count} سياسة.')
    disable_policies.short_description = 'تعطيل السياسات المحددة'


# Import Reports admin
from .admin_reports import SavedReportAdmin, ReportScheduleAdmin, ReportExecutionAdmin
