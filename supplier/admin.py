from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import Supplier, SupplierType

# استيراد الواجهات المتقدمة
from .admin_advanced import *

# إلغاء تسجيل النماذج المكررة إذا كانت مسجلة
try:
    admin.site.unregister(Supplier)
    admin.site.unregister(SupplierType)
except admin.sites.NotRegistered:
    pass

@admin.register(Supplier)
class SupplierAdminBasic(admin.ModelAdmin):
    """
    إعدادات عرض نموذج المورد في لوحة الإدارة - النسخة الأساسية
    """
    list_display = ('name', 'code', 'get_primary_type_display', 'phone', 'is_preferred', 'is_active')
    list_filter = ('is_active', 'primary_type', 'supplier_types', 'is_preferred', 'created_at')
    search_fields = ('name', 'code', 'phone', 'email', 'contact_person', 'city')
    readonly_fields = ('balance', 'created_at', 'updated_at', 'created_by')
    filter_horizontal = ('supplier_types',)
    
    def save_model(self, request, obj, form, change):
        if not change:  # إذا كان إنشاء جديد
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
