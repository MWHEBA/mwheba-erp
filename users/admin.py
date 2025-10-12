from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User, ActivityLog


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    """
    تخصيص عرض نموذج المستخدم في لوحة الإدارة
    """
    list_display = ('username', 'email', 'first_name', 'last_name', 'user_type', 'status', 'is_staff')
    list_filter = ('user_type', 'status', 'is_staff', 'is_active')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'phone')
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (_('المعلومات الشخصية'), {'fields': ('first_name', 'last_name', 'email', 'phone', 'profile_image', 'address')}),
        (_('الصلاحيات'), {'fields': ('user_type', 'status', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        (_('تواريخ مهمة'), {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'password1', 'password2', 'user_type', 'status'),
        }),
    )


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    """
    إدارة سجلات نشاطات المستخدمين
    """
    list_display = ('user', 'action', 'model_name', 'object_id', 'timestamp', 'ip_address')
    list_filter = ('action', 'model_name', 'timestamp')
    search_fields = ('user__username', 'action', 'model_name', 'ip_address')
    readonly_fields = ('user', 'action', 'model_name', 'object_id', 'timestamp', 'ip_address', 'user_agent', 'extra_data')
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
