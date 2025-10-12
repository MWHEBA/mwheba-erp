from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import (
    SupplierType, SpecializedService, ServicePriceTier,
    PaperServiceDetails, DigitalPrintingDetails, FinishingServiceDetails,
    OffsetPrintingDetails, PlateServiceDetails, OutdoorPrintingDetails,
    LaserServiceDetails, VIPGiftDetails
)

# ========================================
# Inline Classes
# ========================================

class ServicePriceTierInline(admin.TabularInline):
    model = ServicePriceTier
    extra = 1
    fields = ('tier_name', 'min_quantity', 'max_quantity', 'price_per_unit', 'discount_percentage', 'is_active', 'display_order')
    ordering = ('display_order', 'min_quantity')

class PaperServiceDetailsInline(admin.StackedInline):
    model = PaperServiceDetails
    extra = 0
    fieldsets = (
        ('معلومات الورق', {
            'fields': ('paper_type', 'gsm', 'sheet_size', 'custom_width', 'custom_height')
        }),
        ('معلومات المورد', {
            'fields': ('country_of_origin', 'brand')
        }),
        ('التسعير', {
            'fields': ('price_per_sheet', 'price_per_kg')
        }),
    )

class DigitalPrintingDetailsInline(admin.StackedInline):
    model = DigitalPrintingDetails
    extra = 0
    fieldsets = (
        ('معلومات الماكينة', {
            'fields': ('machine_type', 'machine_model', 'paper_handling', 'paper_size')
        }),
        ('المقاسات والقدرات', {
            'fields': ('max_width_cm', 'max_height_cm', 'max_paper_weight_gsm', 'supports_heavy_paper')
        }),
        ('التسعير', {
            'fields': ('price_per_page_bw', 'price_per_page_color', 'has_price_tiers')
        }),
        ('الإمكانيات', {
            'fields': ('duplex_printing', 'variable_data_printing', 'pages_per_minute_bw', 'pages_per_minute_color', 'setup_time_minutes')
        }),
    )

class FinishingServiceDetailsInline(admin.StackedInline):
    model = FinishingServiceDetails
    extra = 0
    fields = ('finishing_type', 'calculation_method', 'min_size_cm', 'max_size_cm', 'price_per_unit', 'setup_time_minutes', 'turnaround_time_hours')

class OffsetPrintingDetailsInline(admin.StackedInline):
    model = OffsetPrintingDetails
    extra = 0
    fieldsets = (
        ('معلومات الماكينة', {
            'fields': ('machine_type', 'machine_model', 'sheet_size', 'custom_width_cm', 'custom_height_cm')
        }),
        ('تكاليف الإعداد', {
            'fields': ('plate_cost', 'color_calibration_cost')
        }),
        ('التسعير بالتراج', {
            'fields': ('impression_cost_per_1000', 'min_impressions')
        }),
        ('إمكانيات الماكينة', {
            'fields': ('max_colors', 'has_uv_coating', 'has_aqueous_coating')
        }),
    )

class PlateServiceDetailsInline(admin.StackedInline):
    model = PlateServiceDetails
    extra = 0
    fieldsets = (
        ('معلومات الزنك', {
            'fields': ('plate_size', 'plate_type', 'custom_width_cm', 'custom_height_cm')
        }),
        ('التسعير', {
            'fields': ('price_per_plate', 'transportation_cost')
        }),
        ('قيود الخدمة', {
            'fields': ('min_plates_count', 'turnaround_time_hours')
        }),
        ('خدمات إضافية', {
            'fields': ('includes_proofing', 'digital_proof_cost')
        }),
    )

class OutdoorPrintingDetailsInline(admin.StackedInline):
    model = OutdoorPrintingDetails
    extra = 0
    fieldsets = (
        ('معلومات الطباعة', {
            'fields': ('material_type', 'printing_type', 'max_width_cm', 'max_height_cm')
        }),
        ('التسعير', {
            'fields': ('price_per_sqm', 'min_order_sqm')
        }),
        ('خدمات إضافية', {
            'fields': ('includes_hemming', 'hemming_cost_per_meter', 'includes_grommets', 'grommet_cost_each')
        }),
        ('التسليم والتركيب', {
            'fields': ('production_time_days', 'includes_installation', 'installation_cost_per_sqm')
        }),
    )

class LaserServiceDetailsInline(admin.StackedInline):
    model = LaserServiceDetails
    extra = 0
    fieldsets = (
        ('معلومات الليزر', {
            'fields': ('laser_type', 'service_type', 'material_type')
        }),
        ('قيود المقاسات', {
            'fields': ('max_width_cm', 'max_height_cm', 'max_thickness_mm')
        }),
        ('التسعير', {
            'fields': ('price_per_minute', 'price_per_cm', 'price_per_piece', 'setup_cost')
        }),
        ('معلومات إضافية', {
            'fields': ('min_order_value', 'turnaround_time_hours', 'includes_design', 'design_cost_per_hour')
        }),
    )

class VIPGiftDetailsInline(admin.StackedInline):
    model = VIPGiftDetails
    extra = 0
    fieldsets = (
        ('معلومات الهدية', {
            'fields': ('gift_category', 'customization_type', 'product_name', 'product_description')
        }),
        ('معلومات المنتج', {
            'fields': ('brand', 'country_of_origin')
        }),
        ('التسعير', {
            'fields': ('base_price', 'customization_cost', 'packaging_cost')
        }),
        ('قيود الطلب', {
            'fields': ('min_order_quantity', 'max_customization_chars')
        }),
        ('التسليم', {
            'fields': ('production_time_days', 'includes_gift_box', 'includes_certificate')
        }),
        ('خدمات إضافية', {
            'fields': ('includes_delivery', 'delivery_cost', 'includes_setup_service', 'setup_service_cost')
        }),
    )

# ========================================
# Admin Classes
# ========================================

@admin.register(SupplierType)
class SupplierTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'icon_display', 'color_display', 'suppliers_count', 'is_active', 'display_order')
    list_filter = ('is_active',)
    search_fields = ('name', 'code', 'description')
    ordering = ('display_order', 'name')
    
    def icon_display(self, obj):
        return format_html('<i class="{}" style="font-size: 18px;"></i>', obj.icon)
    icon_display.short_description = 'أيقونة'
    
    def color_display(self, obj):
        return format_html(
            '<div style="width: 20px; height: 20px; background-color: {}; border-radius: 3px; display: inline-block;"></div>',
            obj.color
        )
    color_display.short_description = 'لون'
    
    def suppliers_count(self, obj):
        count = obj.suppliers.filter(is_active=True).count()
        return format_html('<span class="badge badge-primary">{}</span>', count)
    suppliers_count.short_description = 'عدد الموردين'

# تم حذف SupplierServiceCategoryAdmin لأن النموذج تم حذفه لتجنب التكرار

@admin.register(SpecializedService)
class SpecializedServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'supplier', 'category', 'setup_cost', 'has_tiers', 'is_active')
    list_filter = ('category', 'supplier__primary_type', 'is_active', 'created_at')
    search_fields = ('name', 'description', 'supplier__name')
    ordering = ('-created_at',)
    
    fieldsets = (
        ('معلومات أساسية', {
            'fields': ('supplier', 'category', 'name', 'description')
        }),
        ('معلومات السعر', {
            'fields': ('setup_cost',)
        }),
        ('معلومات إضافية', {
            'fields': ('is_active',)
        }),
    )
    
    inlines = [
        ServicePriceTierInline,
        PaperServiceDetailsInline,
        DigitalPrintingDetailsInline,
        FinishingServiceDetailsInline,
        OffsetPrintingDetailsInline,
        PlateServiceDetailsInline,
        OutdoorPrintingDetailsInline,
        LaserServiceDetailsInline,
        VIPGiftDetailsInline,
    ]
    
    def has_tiers(self, obj):
        has_tiers = obj.price_tiers.filter(is_active=True).exists()
        if has_tiers:
            count = obj.price_tiers.filter(is_active=True).count()
            return format_html('<span class="badge badge-info">{} شريحة</span>', count)
        return format_html('<span class="badge badge-secondary">لا</span>')
    has_tiers.short_description = 'شرائح سعرية'
    
    def get_inline_instances(self, request, obj=None):
        """عرض الـ inline المناسب حسب فئة الخدمة"""
        if not obj:
            return []
        
        inlines = [ServicePriceTierInline]
        
        if obj.category.code == 'paper':
            inlines.append(PaperServiceDetailsInline)
        elif obj.category.code == 'digital_printing':
            inlines.append(DigitalPrintingDetailsInline)
        elif obj.category.code == 'finishing':
            inlines.append(FinishingServiceDetailsInline)
        elif obj.category.code == 'offset_printing':
            inlines.append(OffsetPrintingDetailsInline)
        elif obj.category.code == 'plates':
            inlines.append(PlateServiceDetailsInline)
        elif obj.category.code == 'outdoor':
            inlines.append(OutdoorPrintingDetailsInline)
        elif obj.category.code == 'laser':
            inlines.append(LaserServiceDetailsInline)
        elif obj.category.code == 'vip_gifts':
            inlines.append(VIPGiftDetailsInline)
        
        return [inline(self.model, self.admin_site) for inline in inlines]

@admin.register(ServicePriceTier)
class ServicePriceTierAdmin(admin.ModelAdmin):
    list_display = ('service', 'tier_name', 'quantity_range', 'price_per_unit', 'discount_percentage', 'is_active', 'display_order')
    list_filter = ('service__category', 'is_active')
    search_fields = ('service__name', 'tier_name')
    ordering = ('service', 'display_order', 'min_quantity')
    
    def quantity_range(self, obj):
        if obj.max_quantity:
            return f"{obj.min_quantity} - {obj.max_quantity}"
        else:
            return f"{obj.min_quantity}+"
    quantity_range.short_description = 'نطاق الكمية'

# ========================================
# تسجيل النماذج التفصيلية
# ========================================

@admin.register(PaperServiceDetails)
class PaperServiceDetailsAdmin(admin.ModelAdmin):
    list_display = ('service', 'paper_type', 'gsm', 'sheet_size', 'brand', 'price_per_sheet')
    list_filter = ('paper_type', 'sheet_size', 'country_of_origin')
    search_fields = ('service__name', 'brand', 'country_of_origin')

@admin.register(DigitalPrintingDetails)
class DigitalPrintingDetailsAdmin(admin.ModelAdmin):
    list_display = ('service', 'machine_type', 'paper_size', 'price_per_page_color', 'has_price_tiers', 'duplex_printing')
    list_filter = ('machine_type', 'paper_size', 'has_price_tiers', 'duplex_printing')
    search_fields = ('service__name', 'machine_model')

@admin.register(OffsetPrintingDetails)
class OffsetPrintingDetailsAdmin(admin.ModelAdmin):
    list_display = ('service', 'machine_type', 'sheet_size', 'max_colors', 'impression_cost_per_1000', 'has_uv_coating')
    list_filter = ('machine_type', 'sheet_size', 'max_colors', 'has_uv_coating')
    search_fields = ('service__name', 'machine_model')

@admin.register(LaserServiceDetails)
class LaserServiceDetailsAdmin(admin.ModelAdmin):
    list_display = ('service', 'laser_type', 'service_type', 'material_type', 'price_per_minute', 'includes_design')
    list_filter = ('laser_type', 'service_type', 'material_type', 'includes_design')
    search_fields = ('service__name',)

@admin.register(VIPGiftDetails)
class VIPGiftDetailsAdmin(admin.ModelAdmin):
    list_display = ('service', 'gift_category', 'product_name', 'brand', 'base_price', 'includes_gift_box')
    list_filter = ('gift_category', 'customization_type', 'includes_gift_box', 'includes_delivery')
    search_fields = ('service__name', 'product_name', 'brand')

# تخصيص العنوان
admin.site.site_header = "إدارة الخدمات المتخصصة - MWHEBA ERP"
admin.site.site_title = "الخدمات المتخصصة"
admin.site.index_title = "لوحة تحكم الخدمات المتخصصة"
