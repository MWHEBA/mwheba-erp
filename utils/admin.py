from django.contrib import admin
from .models import SystemLog

@admin.register(SystemLog)
class SystemLogAdmin(admin.ModelAdmin):
    """
    إعدادات عرض سجلات النظام في لوحة الإدارة
    """
    list_display = ('user', 'action', 'model_name', 'object_id', 'timestamp', 'ip_address')
    list_filter = ('action', 'model_name', 'timestamp', 'user')
    search_fields = ('user__username', 'user__email', 'action', 'model_name', 'object_id', 'details')
    readonly_fields = ('user', 'action', 'model_name', 'object_id', 'details', 'ip_address', 'timestamp')
    date_hierarchy = 'timestamp'
    
    def has_add_permission(self, request):
        # منع إضافة سجلات يدويًا، يجب أن تنشأ تلقائيًا من خلال النظام
        return False
    
    def has_change_permission(self, request, obj=None):
        # منع تعديل السجلات للحفاظ على سلامة البيانات
        return False 