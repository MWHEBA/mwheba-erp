from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.contrib import messages
from django.utils import timezone
import logging

from .models import User, ActivityLog, Role

logger = logging.getLogger('users.admin')


class SecureAdminMixin:
    """
    Mixin بسيط للأمان في لوحة الإدارة
    """
    
    def has_change_permission(self, request, obj=None):
        """التحقق من صلاحية التعديل مع التسجيل"""
        if hasattr(request.user, 'can_manage_users') and not request.user.can_manage_users():
            return False
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """التحقق من صلاحية الحذف مع التسجيل"""
        if hasattr(request.user, 'can_manage_users') and not request.user.can_manage_users():
            return False
        return super().has_delete_permission(request, obj)
    
    def save_model(self, request, obj, form, change):
        """حفظ مع تسجيل العملية"""
        operation = 'تحديث' if change else 'إنشاء'
        logger.info(f"{operation} {self.model._meta.verbose_name}: {obj} بواسطة {request.user.username}")
        super().save_model(request, obj, form, change)
    
    def delete_model(self, request, obj):
        """حذف مع تسجيل العملية"""
        logger.info(f"حذف {self.model._meta.verbose_name}: {obj} بواسطة {request.user.username}")
        super().delete_model(request, obj)


@admin.register(User)
class CustomUserAdmin(SecureAdminMixin, UserAdmin):
    """
    تخصيص عرض نموذج المستخدم في لوحة الإدارة
    """

    list_display = (
        "username",
        "email", 
        "first_name",
        "last_name",
        "role",
        "is_active",
        "is_staff",
        "security_status"
    )
    list_filter = ("role", "is_staff", "is_active", "date_joined")
    search_fields = ("username", "email", "first_name", "last_name")
    readonly_fields = ("date_joined", "last_login")
    
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
                    "role",
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
    
    def security_status(self, obj):
        """عرض حالة الأمان للمستخدم."""
        if obj.is_superuser:
            return format_html(
                '<span style="color: red; font-weight: bold;">🚨 مدير عام</span>'
            )
        elif obj.is_staff:
            return format_html(
                '<span style="color: orange; font-weight: bold;">⚠️ موظف</span>'
            )
        else:
            return format_html(
                '<span style="color: green; font-weight: bold;">👤 مستخدم</span>'
            )
    security_status.short_description = _("حالة الأمان")
    
    def save_model(self, request, obj, form, change):
        """حفظ مع فحوصات أمان إضافية"""
        # منع غير المديرين من إنشاء مستخدمين خارقين
        if obj.is_superuser and not request.user.is_superuser:
            messages.error(request, "لا يمكن إنشاء مستخدم خارق إلا بواسطة مستخدم خارق آخر")
            return
        
        # تسجيل تغيير الأدوار
        if change and 'role' in form.changed_data:
            old_user = User.objects.get(pk=obj.pk)
            old_role = old_user.role.display_name if old_user.role else 'بدون دور'
            new_role = obj.role.display_name if obj.role else 'بدون دور'
            logger.warning(f"تغيير دور المستخدم {obj.username}: من {old_role} إلى {new_role} بواسطة {request.user.username}")
        
        super().save_model(request, obj, form, change)


@admin.register(Role)
class CustomRoleAdmin(SecureAdminMixin, admin.ModelAdmin):
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
        return obj.users.filter(is_active=True).count()
    users_count.short_description = _("عدد المستخدمين")
    
    def permissions_count(self, obj):
        """عدد الصلاحيات في هذا الدور"""
        return obj.permissions.count()
    permissions_count.short_description = _("عدد الصلاحيات")
    
    def has_delete_permission(self, request, obj=None):
        """منع حذف أدوار النظام"""
        if obj and obj.is_system_role:
            return False
        return super().has_delete_permission(request, obj)
    
    def delete_model(self, request, obj):
        """حذف محسن مع حماية أدوار النظام"""
        if obj.is_system_role:
            messages.error(request, "لا يمكن حذف الأدوار الأساسية للنظام")
            return
        
        users_count = obj.users.filter(is_active=True).count()
        if users_count > 0:
            messages.error(request, f"لا يمكن حذف الدور لأنه مرتبط بـ {users_count} مستخدم نشط")
            return
        
        super().delete_model(request, obj)
    
    def save_model(self, request, obj, form, change):
        """حفظ مع تسجيل تغيير الصلاحيات"""
        if change and 'permissions' in form.changed_data:
            affected_users = obj.users.filter(is_active=True).count()
            logger.warning(f"تغيير صلاحيات الدور {obj.display_name} - يؤثر على {affected_users} مستخدم بواسطة {request.user.username}")
        
        super().save_model(request, obj, form, change)


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





# Secure Group Admin - unregister default and register secure version
admin.site.unregister(Group)

@admin.register(Group)
class SecureGroupAdminCustom(admin.ModelAdmin):
    """
    إدارة مجموعات المستخدمين
    """
    
    list_display = ['name', 'users_count', 'permissions_count']
    search_fields = ['name']
    filter_horizontal = ['permissions']
    
    def users_count(self, obj):
        """عدد المستخدمين في المجموعة."""
        return obj.user_set.count()
    users_count.short_description = _("عدد المستخدمين")
    
    def permissions_count(self, obj):
        """عدد الصلاحيات في المجموعة."""
        return obj.permissions.count()
    permissions_count.short_description = _("عدد الصلاحيات")
