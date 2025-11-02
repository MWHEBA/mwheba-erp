from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import SystemSetting, DashboardStat, Notification, NotificationPreference


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
