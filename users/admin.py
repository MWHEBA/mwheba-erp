from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User, ActivityLog, Role


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    """
    تخصيص عرض نموذج المستخدم في لوحة الإدارة
    """

    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "user_type",
        "status",
        "is_staff",
    )
    list_filter = ("user_type", "status", "is_staff", "is_active")
    search_fields = ("username", "email", "first_name", "last_name", "phone")
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (
            _("المعلومات الشخصية"),
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "email",
                    "phone",
                    "profile_image",
                    "address",
                )
            },
        ),
        (
            _("الصلاحيات"),
            {
                "fields": (
                    "user_type",
                    "status",
                    "role",
                    "custom_permissions",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (_("تواريخ مهمة"), {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "email",
                    "password1",
                    "password2",
                    "user_type",
                    "status",
                ),
            },
        ),
    )


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    """
    إدارة سجلات نشاطات المستخدمين
    """

    list_display = (
        "user",
        "action",
        "model_name",
        "object_id",
        "timestamp",
        "ip_address",
    )
    list_filter = ("action", "model_name", "timestamp")
    search_fields = ("user__username", "action", "model_name", "ip_address")
    readonly_fields = (
        "user",
        "action",
        "model_name",
        "object_id",
        "timestamp",
        "ip_address",
        "user_agent",
        "extra_data",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    """
    إدارة الأدوار في لوحة الإدارة
    """
    list_display = (
        "display_name",
        "name",
        "is_system_role",
        "is_active",
        "users_count",
        "permissions_count",
        "created_at",
    )
    list_filter = ("is_system_role", "is_active", "created_at")
    search_fields = ("name", "display_name", "description")
    filter_horizontal = ("permissions",)
    readonly_fields = ("created_at", "updated_at")
    
    fieldsets = (
        (
            _("معلومات الدور"),
            {
                "fields": (
                    "name",
                    "display_name",
                    "description",
                    "is_system_role",
                    "is_active",
                )
            },
        ),
        (
            _("الصلاحيات"),
            {
                "fields": ("permissions",),
                "classes": ("collapse",),
            },
        ),
        (
            _("معلومات إضافية"),
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )
    
    def users_count(self, obj):
        """عدد المستخدمين في هذا الدور"""
        return obj.users_count
    users_count.short_description = _("عدد المستخدمين")
    
    def permissions_count(self, obj):
        """عدد الصلاحيات في هذا الدور"""
        return obj.permissions_count
    permissions_count.short_description = _("عدد الصلاحيات")
    
    def has_delete_permission(self, request, obj=None):
        """منع حذف أدوار النظام"""
        if obj and obj.is_system_role:
            return False
        return super().has_delete_permission(request, obj)
