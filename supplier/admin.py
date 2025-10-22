from django.contrib import admin
from django.utils.translation import gettext_lazy as _

# استيراد النماذج مباشرة من models.py لتجنب مشاكل الاستيراد الدائري
from .models import Supplier, SupplierType, SupplierTypeSettings

# ملاحظة: تم حذف admin_advanced.py لأنه كان معطل وغير مستخدم

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

    list_display = (
        "name",
        "code",
        "get_primary_type_display",
        "phone",
        "is_preferred",
        "is_active",
    )
    list_filter = (
        "is_active",
        "primary_type",
        "supplier_types",
        "is_preferred",
        "created_at",
    )
    search_fields = ("name", "code", "phone", "email", "contact_person", "city")
    readonly_fields = ("balance", "created_at", "updated_at", "created_by")
    filter_horizontal = ("supplier_types",)

    def save_model(self, request, obj, form, change):
        if not change:  # إذا كان إنشاء جديد
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(SupplierTypeSettings)
class SupplierTypeSettingsAdmin(admin.ModelAdmin):
    """
    إعدادات عرض نموذج إعدادات أنواع الموردين في لوحة الإدارة
    """
    
    list_display = (
        "name",
        "code", 
        "icon",
        "color",
        "display_order",
        "is_active",
        "is_system",
        "suppliers_count",
        "created_at"
    )
    
    list_filter = (
        "is_active",
        "is_system", 
        "created_at",
        "updated_at"
    )
    
    search_fields = ("name", "code", "description")
    
    readonly_fields = (
        "suppliers_count",
        "created_at", 
        "updated_at",
        "created_by",
        "updated_by"
    )
    
    ordering = ("display_order", "name")
    
    fieldsets = (
        (_("المعلومات الأساسية"), {
            "fields": ("name", "code", "description")
        }),
        (_("المظهر البصري"), {
            "fields": ("icon", "color")
        }),
        (_("الإعدادات"), {
            "fields": ("display_order", "is_active", "is_system")
        }),
        (_("معلومات التتبع"), {
            "fields": ("suppliers_count", "created_at", "updated_at", "created_by", "updated_by"),
            "classes": ("collapse",)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:  # إذا كان إنشاء جديد
            obj.created_by = request.user
        else:  # إذا كان تحديث
            obj.updated_by = request.user
        super().save_model(request, obj, form, change)
