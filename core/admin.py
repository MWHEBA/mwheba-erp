from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import (
    SystemSetting, DashboardStat, Notification, NotificationPreference,
    BackupRecord, BackupFile, DataRetentionPolicy, DataRetentionExecution,
    EncryptionKey, DataProtectionAudit, DataClassification,
    SystemModule,
    # ✅ PHASE 7: Simplified monitoring models
    UnifiedLog, AlertRule, Alert
)


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    """
    إدارة إعدادات النظام
    """

    list_display = ("key", "value", "data_type", "group", "is_active")
    list_filter = ("data_type", "group", "is_active")
    search_fields = ("key", "value", "description")
    list_editable = ("value", "is_active")
    fieldsets = (
        (None, {"fields": ("key", "value", "data_type")}),
        (_("الإعدادات الإضافية"), {"fields": ("description", "group", "is_active")}),
    )


@admin.register(DashboardStat)
class DashboardStatAdmin(admin.ModelAdmin):
    """
    إدارة إحصائيات لوحة التحكم
    """

    list_display = ("title", "value", "type", "period", "order", "is_active")
    list_filter = ("type", "period", "is_active")
    search_fields = ("title", "value")
    list_editable = ("order", "is_active")
    fieldsets = (
        (None, {"fields": ("title", "value", "type", "period")}),
        (_("الخيارات المرئية"), {"fields": ("icon", "color", "order", "is_active")}),
        (_("معلومات التغيير"), {"fields": ("change_value", "change_type")}),
    )


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """
    إدارة الإشعارات
    """

    list_display = ("user", "title", "type", "is_read", "created_at")
    list_filter = ("type", "is_read", "created_at")
    search_fields = ("title", "message", "user__username")
    list_editable = ("is_read",)
    readonly_fields = ("created_at",)
    fieldsets = (
        (None, {"fields": ("user", "title", "message", "type")}),
        (_("الحالة"), {"fields": ("is_read", "created_at")}),
    )


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    """
    إدارة تفضيلات الإشعارات
    """

    list_display = ("user", "notify_in_app", "notify_email", "notify_sms", "enable_do_not_disturb", "updated_at")
    list_filter = ("notify_in_app", "notify_email", "notify_sms", "enable_do_not_disturb")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("created_at", "updated_at")
    
    fieldsets = (
        (_("المستخدم"), {"fields": ("user",)}),
        (_("أنواع الإشعارات"), {
            "fields": (
                "enable_inventory_alerts",
                "enable_invoice_notifications",
                "enable_payment_notifications",
                "enable_return_notifications",
                "enable_customer_notifications",
                "enable_product_notifications",
                "enable_user_notifications",
                "enable_system_notifications",
            )
        }),
        (_("طرق الإشعار"), {
            "fields": (
                "notify_in_app",
                "notify_email",
                "email_for_notifications",
                "notify_sms",
                "phone_for_notifications",
            )
        }),
        (_("الجدولة"), {
            "fields": (
                "inventory_check_frequency",
                "invoice_check_frequency",
                "send_daily_summary",
                "daily_summary_time",
            )
        }),
        (_("حدود التنبيهات"), {
            "fields": (
                "alert_on_minimum_stock",
                "alert_on_half_minimum",
                "alert_on_out_of_stock",
                "invoice_due_days_before",
                "alert_on_invoice_due",
                "alert_on_invoice_overdue",
                "invoice_overdue_days_after",
            )
        }),
        (_("عدم الإزعاج"), {
            "fields": (
                "enable_do_not_disturb",
                "do_not_disturb_start",
                "do_not_disturb_end",
            )
        }),
        (_("إدارة الإشعارات القديمة"), {
            "fields": (
                "auto_delete_read_notifications",
                "auto_delete_after_days",
                "auto_archive_old_notifications",
                "auto_archive_after_months",
            )
        }),
        (_("معلومات التحديث"), {"fields": ("created_at", "updated_at")}),
    )

# ============================================================
# PHASE 5: DATA PROTECTION ADMIN CLASSES
# ============================================================

@admin.register(BackupRecord)
class BackupRecordAdmin(admin.ModelAdmin):
    """
    إدارة سجلات النسخ الاحتياطية
    """
    list_display = ('backup_id', 'backup_type', 'status', 'size_mb', 'started_at', 'duration_seconds')
    list_filter = ('backup_type', 'status', 'storage_type', 'started_at')
    search_fields = ('backup_id', 'remote_path')
    readonly_fields = ('backup_id', 'started_at', 'completed_at', 'duration_seconds', 'size_mb')
    
    fieldsets = (
        (_('معلومات النسخة الاحتياطية'), {
            'fields': ('backup_id', 'backup_type', 'status', 'storage_type')
        }),
        (_('تفاصيل الحجم والملفات'), {
            'fields': ('total_size_bytes', 'file_count', 'compression_ratio')
        }),
        (_('معلومات التوقيت'), {
            'fields': ('started_at', 'completed_at', 'duration_seconds')
        }),
        (_('التحقق من السلامة'), {
            'fields': ('verification_status', 'verified_files', 'failed_files', 'verification_errors')
        }),
        (_('التخزين البعيد'), {
            'fields': ('remote_path', 'remote_upload_status')
        }),
        (_('معلومات إضافية'), {
            'fields': ('created_by', 'metadata')
        }),
    )
    
    def size_mb(self, obj):
        return f"{obj.size_mb:.2f} MB"
    size_mb.short_description = _('الحجم (MB)')


@admin.register(BackupFile)
class BackupFileAdmin(admin.ModelAdmin):
    """
    إدارة ملفات النسخ الاحتياطية
    """
    list_display = ('filename', 'file_type', 'size_mb', 'is_verified', 'backup_record')
    list_filter = ('file_type', 'is_verified', 'is_encrypted', 'is_compressed')
    search_fields = ('filename', 'file_path', 'checksum')
    readonly_fields = ('size_mb', 'checksum', 'created_at')
    
    fieldsets = (
        (_('معلومات الملف'), {
            'fields': ('backup_record', 'file_type', 'filename', 'file_path')
        }),
        (_('خصائص الملف'), {
            'fields': ('size_bytes', 'checksum', 'is_encrypted', 'is_compressed')
        }),
        (_('التحقق'), {
            'fields': ('is_verified', 'verification_date')
        }),
        (_('معلومات الإنشاء'), {
            'fields': ('created_at',)
        }),
    )
    
    def size_mb(self, obj):
        return f"{obj.size_mb:.2f} MB"
    size_mb.short_description = _('الحجم (MB)')


@admin.register(DataRetentionPolicy)
class DataRetentionPolicyAdmin(admin.ModelAdmin):
    """
    إدارة سياسات الاحتفاظ بالبيانات
    """
    list_display = ('name', 'model_name', 'retention_days', 'status', 'created_at')
    list_filter = ('status', 'archive_before_delete', 'anonymize_before_delete', 'cascade_delete')
    search_fields = ('name', 'model_name', 'description')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        (_('معلومات السياسة'), {
            'fields': ('name', 'description', 'model_name', 'status')
        }),
        (_('إعدادات الاحتفاظ'), {
            'fields': ('retention_days', 'archive_before_delete', 'anonymize_before_delete', 'cascade_delete')
        }),
        (_('إعدادات الإشعارات'), {
            'fields': ('notification_days',)
        }),
        (_('شروط التطبيق'), {
            'fields': ('conditions', 'exclude_conditions')
        }),
        (_('معلومات الإنشاء'), {
            'fields': ('created_at', 'updated_at', 'created_by')
        }),
    )


@admin.register(DataRetentionExecution)
class DataRetentionExecutionAdmin(admin.ModelAdmin):
    """
    إدارة تنفيذ سياسات الاحتفاظ بالبيانات
    """
    list_display = ('execution_id', 'policy', 'status', 'records_deleted', 'started_at', 'duration_seconds')
    list_filter = ('status', 'dry_run', 'started_at')
    search_fields = ('execution_id', 'policy__name')
    readonly_fields = ('execution_id', 'started_at', 'completed_at', 'duration_seconds')
    
    fieldsets = (
        (_('معلومات التنفيذ'), {
            'fields': ('execution_id', 'policy', 'status', 'dry_run')
        }),
        (_('النتائج'), {
            'fields': ('records_found', 'records_deleted', 'records_archived', 'records_anonymized')
        }),
        (_('معلومات التوقيت'), {
            'fields': ('started_at', 'completed_at', 'duration_seconds')
        }),
        (_('الأخطاء'), {
            'fields': ('errors',)
        }),
    )


@admin.register(EncryptionKey)
class EncryptionKeyAdmin(admin.ModelAdmin):
    """
    إدارة مفاتيح التشفير
    """
    list_display = ('key_id', 'algorithm', 'status', 'created_at', 'encryption_count', 'last_used_at')
    list_filter = ('status', 'algorithm', 'created_at')
    search_fields = ('key_id', 'key_hash')
    readonly_fields = ('key_hash', 'created_at', 'activated_at', 'rotated_at', 'encryption_count', 'decryption_count', 'last_used_at')
    
    fieldsets = (
        (_('معلومات المفتاح'), {
            'fields': ('key_id', 'key_hash', 'algorithm', 'status')
        }),
        (_('دورة حياة المفتاح'), {
            'fields': ('created_at', 'activated_at', 'rotated_at', 'rotation_reason')
        }),
        (_('إحصائيات الاستخدام'), {
            'fields': ('encryption_count', 'decryption_count', 'last_used_at')
        }),
        (_('معلومات الإنشاء'), {
            'fields': ('created_by',)
        }),
    )


@admin.register(DataProtectionAudit)
class DataProtectionAuditAdmin(admin.ModelAdmin):
    """
    إدارة سجل تدقيق حماية البيانات
    """
    list_display = ('operation_type', 'object_type', 'object_id', 'success', 'user', 'timestamp')
    list_filter = ('operation_type', 'success', 'timestamp')
    search_fields = ('object_type', 'object_id', 'description', 'user__username')
    readonly_fields = ('timestamp',)
    
    fieldsets = (
        (_('معلومات العملية'), {
            'fields': ('operation_type', 'object_type', 'object_id', 'description')
        }),
        (_('النتيجة'), {
            'fields': ('success', 'error_message')
        }),
        (_('معلومات السياق'), {
            'fields': ('user', 'ip_address', 'user_agent')
        }),
        (_('بيانات إضافية'), {
            'fields': ('metadata', 'timestamp')
        }),
    )


@admin.register(DataClassification)
class DataClassificationAdmin(admin.ModelAdmin):
    """
    إدارة تصنيف البيانات
    """
    list_display = ('model_name', 'field_name', 'classification_level', 'requires_encryption', 'requires_anonymization')
    list_filter = ('classification_level', 'requires_encryption', 'requires_anonymization')
    search_fields = ('model_name', 'field_name', 'description')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        (_('معلومات التصنيف'), {
            'fields': ('model_name', 'field_name', 'classification_level', 'description')
        }),
        (_('متطلبات الحماية'), {
            'fields': ('requires_encryption', 'requires_anonymization', 'retention_days')
        }),
        (_('معلومات التحديث'), {
            'fields': ('created_at', 'updated_at')
        }),
    )

# ============================================================
# ✅ PHASE 7: Simplified Monitoring Admin Classes
# ============================================================

@admin.register(UnifiedLog)
class UnifiedLogAdmin(admin.ModelAdmin):
    """إدارة السجلات الموحدة"""
    list_display = ['timestamp', 'log_type', 'level', 'category', 'message_preview', 'user']
    list_filter = ['log_type', 'level', 'category', 'timestamp']
    search_fields = ['message', 'user__username', 'ip_address']
    readonly_fields = ['timestamp', 'log_type', 'level', 'category', 'message', 'user', 'request_id', 'ip_address', 'user_agent', 'data']
    date_hierarchy = 'timestamp'
    ordering = ['-timestamp']
    list_per_page = 50
    
    fieldsets = (
        (_('المعلومات الأساسية'), {
            'fields': ('timestamp', 'log_type', 'level', 'category', 'message')
        }),
        (_('معلومات المستخدم'), {
            'fields': ('user', 'ip_address', 'user_agent', 'request_id')
        }),
        (_('البيانات الإضافية'), {
            'fields': ('data',),
            'classes': ('collapse',)
        })
    )
    
    def message_preview(self, obj):
        return obj.message[:100] + '...' if len(obj.message) > 100 else obj.message
    message_preview.short_description = _('معاينة الرسالة')
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AlertRule)
class AlertRuleAdmin(admin.ModelAdmin):
    """إدارة قواعد التنبيهات"""
    list_display = ['name', 'metric_type', 'severity', 'threshold_display', 'time_window_minutes', 'is_active']
    list_filter = ['metric_type', 'severity', 'is_active']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        (_('المعلومات الأساسية'), {
            'fields': ('name', 'description', 'is_active')
        }),
        (_('شروط التنبيه'), {
            'fields': ('metric_type', 'operator', 'threshold_value', 'time_window_minutes', 'severity')
        }),
        (_('الإشعارات'), {
            'fields': ('email_recipients',)
        }),
        (_('معلومات التحديث'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def threshold_display(self, obj):
        return f"{obj.get_operator_display()} {obj.threshold_value}"
    threshold_display.short_description = _('العتبة')


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    """إدارة التنبيهات"""
    list_display = ['created_at', 'rule', 'status', 'severity_display', 'metric_value', 'acknowledged_by']
    list_filter = ['status', 'rule__severity', 'created_at']
    search_fields = ['rule__name', 'message']
    readonly_fields = ['created_at', 'updated_at', 'rule', 'message', 'metric_value', 'threshold_value']
    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    
    fieldsets = (
        (_('معلومات التنبيه'), {
            'fields': ('rule', 'status', 'message', 'metric_value', 'threshold_value')
        }),
        (_('الإدارة'), {
            'fields': ('acknowledged_by', 'acknowledged_at', 'resolved_at')
        }),
        (_('معلومات التحديث'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def severity_display(self, obj):
        return obj.rule.get_severity_display()
    severity_display.short_description = _('الخطورة')
    
    actions = ['acknowledge_alerts', 'resolve_alerts']
    
    def acknowledge_alerts(self, request, queryset):
        updated = 0
        for alert in queryset.filter(status='active'):
            alert.acknowledge(request.user)
            updated += 1
        self.message_user(request, f'{updated} تنبيه تم الإقرار به بنجاح.')
    acknowledge_alerts.short_description = _('إقرار التنبيهات المحددة')
    
    def resolve_alerts(self, request, queryset):
        updated = 0
        for alert in queryset.filter(status__in=['active', 'acknowledged']):
            alert.resolve()
            updated += 1
        self.message_user(request, f'{updated} تنبيه تم حله بنجاح.')
    resolve_alerts.short_description = _('حل التنبيهات المحددة')



# ============================================================
# SYSTEM MODULES MANAGEMENT
# ============================================================

@admin.register(SystemModule)
class SystemModuleAdmin(admin.ModelAdmin):
    """
    إدارة تطبيقات النظام
    """
    list_display = ('name_ar', 'code', 'module_type', 'is_enabled', 'order')
    list_filter = ('module_type', 'is_enabled')
    search_fields = ('name_ar', 'name_en', 'code', 'description')
    list_editable = ('is_enabled', 'order')
    readonly_fields = ('created_at', 'updated_at')
    filter_horizontal = ('required_modules',)
    
    fieldsets = (
        (_('المعلومات الأساسية'), {
            'fields': ('code', 'name_ar', 'name_en', 'description', 'icon')
        }),
        (_('الإعدادات'), {
            'fields': ('module_type', 'is_enabled', 'order')
        }),
        (_('التبعيات'), {
            'fields': ('required_modules',)
        }),
        (_('معلومات إضافية'), {
            'fields': ('url_namespace', 'menu_id')
        }),
        (_('معلومات التحديث'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # مسح الكاش عند التعديل
        from django.core.cache import cache
        cache.delete('enabled_modules_dict')
        cache.delete('enabled_modules_set')
        try:
            cache.delete_pattern('module_enabled_*')
        except AttributeError:
            pass
