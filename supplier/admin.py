from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import Supplier, SupplierType, SupplierTypeSettings, ServiceType, SupplierService, ServicePriceTier

try:
    admin.site.unregister(Supplier)
    admin.site.unregister(SupplierType)
except admin.sites.NotRegistered:
    pass


@admin.register(Supplier)
class SupplierAdminBasic(admin.ModelAdmin):
    list_display = ("name", "code", "get_primary_type_display", "phone", "is_preferred", "is_active")
    list_filter  = ("is_active", "primary_type", "is_preferred", "created_at")
    search_fields = ("name", "code", "phone", "email", "contact_person", "city")
    readonly_fields = ("balance", "created_at", "updated_at", "created_by")

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(SupplierType)
class SupplierTypeAdmin(admin.ModelAdmin):
    list_display  = ("name", "code", "icon", "color", "display_order", "is_active")
    list_filter   = ("is_active",)
    search_fields = ("name", "code", "description")
    ordering      = ("display_order", "name")


@admin.register(SupplierTypeSettings)
class SupplierTypeSettingsAdmin(admin.ModelAdmin):
    list_display  = ("name", "code", "icon", "color", "display_order", "is_active", "is_system", "suppliers_count", "created_at")
    list_filter   = ("is_active", "is_system", "created_at", "updated_at")
    search_fields = ("name", "code", "description")
    readonly_fields = ("suppliers_count", "created_at", "updated_at", "created_by", "updated_by")
    ordering      = ("display_order", "name")

    fieldsets = (
        (_("المعلومات الأساسية"), {"fields": ("name", "code", "description")}),
        (_("المظهر البصري"),      {"fields": ("icon", "color")}),
        (_("الإعدادات"),          {"fields": ("display_order", "is_active", "is_system")}),
        (_("معلومات التتبع"),     {"fields": ("suppliers_count", "created_at", "updated_at", "created_by", "updated_by"), "classes": ("collapse",)}),
    )

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        else:
            obj.updated_by = request.user
        super().save_model(request, obj, form, change)


class ServicePriceTierInline(admin.TabularInline):
    model  = ServicePriceTier
    extra  = 1
    fields = ('min_quantity', 'max_quantity', 'price_per_unit', 'is_active')


@admin.register(ServiceType)
class ServiceTypeAdmin(admin.ModelAdmin):
    list_display  = ('name', 'code', 'category', 'icon', 'order', 'is_active')
    list_filter   = ('category', 'is_active')
    search_fields = ('name', 'code', 'description')
    ordering      = ('order', 'name')


@admin.register(SupplierService)
class SupplierServiceAdmin(admin.ModelAdmin):
    list_display   = ('supplier', 'service_type', 'name', 'base_price', 'setup_cost', 'is_active', 'created_at')
    list_filter    = ('service_type', 'is_active', 'supplier')
    search_fields  = ('name', 'supplier__name', 'service_type__name')
    readonly_fields = ('created_at', 'updated_at')
    inlines        = [ServicePriceTierInline]

    fieldsets = (
        (_("المعلومات الأساسية"), {"fields": ("supplier", "service_type", "name", "is_active")}),
        (_("التسعير"),            {"fields": ("base_price", "setup_cost")}),
        (_("الخصائص"),            {"fields": ("attributes", "notes")}),
        (_("التتبع"),             {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )


@admin.register(ServicePriceTier)
class ServicePriceTierAdmin(admin.ModelAdmin):
    list_display  = ('service', 'min_quantity', 'max_quantity', 'price_per_unit', 'is_active')
    list_filter   = ('is_active', 'service__service_type')
    search_fields = ('service__name', 'service__supplier__name')
