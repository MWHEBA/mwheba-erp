from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import SystemSetting, DashboardStat, Notification


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    """
    إدارة إعدادات النظام
    """
    list_display = ('key', 'value', 'data_type', 'group', 'is_active')
    list_filter = ('data_type', 'group', 'is_active')
    search_fields = ('key', 'value', 'description')
    list_editable = ('value', 'is_active')
    fieldsets = (
        (None, {
            'fields': ('key', 'value', 'data_type')
        }),
        (_('الإعدادات الإضافية'), {
            'fields': ('description', 'group', 'is_active')
        }),
    )


@admin.register(DashboardStat)
class DashboardStatAdmin(admin.ModelAdmin):
    """
    إدارة إحصائيات لوحة التحكم
    """
    list_display = ('title', 'value', 'type', 'period', 'order', 'is_active')
    list_filter = ('type', 'period', 'is_active')
    search_fields = ('title', 'value')
    list_editable = ('order', 'is_active')
    fieldsets = (
        (None, {
            'fields': ('title', 'value', 'type', 'period')
        }),
        (_('الخيارات المرئية'), {
            'fields': ('icon', 'color', 'order', 'is_active')
        }),
        (_('معلومات التغيير'), {
            'fields': ('change_value', 'change_type')
        }),
    )


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """
    إدارة الإشعارات
    """
    list_display = ('user', 'title', 'type', 'is_read', 'created_at')
    list_filter = ('type', 'is_read', 'created_at')
    search_fields = ('title', 'message', 'user__username')
    list_editable = ('is_read',)
    readonly_fields = ('created_at',)
    fieldsets = (
        (None, {
            'fields': ('user', 'title', 'message', 'type')
        }),
        (_('الحالة'), {
            'fields': ('is_read', 'created_at')
        }),
    ) 