from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe

from .models import (
    PrintingOrder, OrderMaterial, PaperSpecification,
    OrderService, PrintingSpecification, CostCalculation, OrderSummary
)


@admin.register(PrintingOrder)
class PrintingOrderAdmin(admin.ModelAdmin):
    """
    إدارة طلبات التسعير في لوحة الإدارة
    """
    list_display = [
        'order_number', 'customer', 'title', 'order_type', 
        'status', 'quantity', 'estimated_cost_display', 
        'created_at', 'due_date'
    ]
    
    list_filter = [
        'status', 'order_type', 'priority', 'is_rush_order',
        'created_at', 'due_date'
    ]
    
    search_fields = [
        'order_number', 'title', 'customer__name', 
        'customer__company_name', 'description'
    ]
    
    readonly_fields = [
        'order_number', 'created_at', 'updated_at',
        'created_by', 'updated_by'
    ]
    
    fieldsets = (
        (_('معلومات أساسية'), {
            'fields': (
                'order_number', 'customer', 'title', 'description',
                'order_type', 'status', 'priority'
            )
        }),
        (_('المواصفات'), {
            'fields': (
                'quantity', 'pages_count', 'copies_count',
                'width', 'height'
            )
        }),
        (_('التكلفة والتسعير'), {
            'fields': (
                'estimated_cost', 'final_price', 'profit_margin',
                'is_rush_order', 'rush_fee'
            )
        }),
        (_('التواريخ'), {
            'fields': (
                'due_date', 'approved_at'
            )
        }),
        (_('معلومات النظام'), {
            'fields': (
                'created_at', 'updated_at', 'created_by', 'updated_by',
                'is_active', 'notes'
            ),
            'classes': ('collapse',)
        })
    )
    
    inlines = []
    
    def estimated_cost_display(self, obj):
        """عرض التكلفة المقدرة بتنسيق جميل"""
        if obj.estimated_cost:
            return format_html(
                '<span style="color: #28a745; font-weight: bold;">{:,.2f} ج.م</span>',
                obj.estimated_cost
            )
        return '-'
    estimated_cost_display.short_description = _('التكلفة المقدرة')
    
    def get_queryset(self, request):
        """تحسين الاستعلام"""
        return super().get_queryset(request).select_related('customer')
    
    def save_model(self, request, obj, form, change):
        """حفظ محسن مع تسجيل المستخدم"""
        if not change:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


class OrderMaterialInline(admin.TabularInline):
    """إدراج مواد الطلب"""
    model = OrderMaterial
    extra = 1
    fields = [
        'material_type', 'material_name', 'quantity', 
        'unit', 'unit_cost', 'total_cost'
    ]
    readonly_fields = ['total_cost']


class OrderServiceInline(admin.TabularInline):
    """إدراج خدمات الطلب"""
    model = OrderService
    extra = 1
    fields = [
        'service_category', 'service_name', 'quantity',
        'unit', 'unit_price', 'setup_cost', 'total_cost'
    ]
    readonly_fields = ['total_cost']


@admin.register(OrderMaterial)
class OrderMaterialAdmin(admin.ModelAdmin):
    """إدارة مواد الطلبات"""
    list_display = [
        'order', 'material_type', 'material_name',
        'quantity', 'unit', 'unit_cost', 'total_cost'
    ]
    
    list_filter = ['material_type', 'unit']
    search_fields = ['material_name', 'order__order_number']
    
    readonly_fields = ['total_cost', 'created_at', 'updated_at']


@admin.register(PaperSpecification)
class PaperSpecificationAdmin(admin.ModelAdmin):
    """إدارة مواصفات الورق"""
    list_display = [
        'order', 'paper_type_name', 'paper_weight',
        'paper_size_name', 'sheets_needed', 'total_paper_cost'
    ]
    
    search_fields = ['paper_type_name', 'order__order_number']
    readonly_fields = ['total_paper_cost', 'created_at', 'updated_at']


@admin.register(OrderService)
class OrderServiceAdmin(admin.ModelAdmin):
    """إدارة خدمات الطلبات"""
    list_display = [
        'order', 'service_category', 'service_name',
        'quantity', 'unit_price', 'total_cost'
    ]
    
    list_filter = ['service_category', 'is_optional']
    search_fields = ['service_name', 'order__order_number']
    
    readonly_fields = ['total_cost', 'created_at', 'updated_at']


@admin.register(PrintingSpecification)
class PrintingSpecificationAdmin(admin.ModelAdmin):
    """إدارة مواصفات الطباعة"""
    list_display = [
        'order', 'printing_type', 'colors_front', 'colors_back',
        'total_colors_display', 'plates_cost', 'printing_cost'
    ]
    
    list_filter = ['printing_type', 'is_cmyk', 'has_spot_colors']
    search_fields = ['order__order_number']
    
    readonly_fields = ['created_at', 'updated_at']
    
    def total_colors_display(self, obj):
        """عرض إجمالي الألوان"""
        return f"{obj.total_colors} لون"
    total_colors_display.short_description = _('إجمالي الألوان')


@admin.register(CostCalculation)
class CostCalculationAdmin(admin.ModelAdmin):
    """إدارة حسابات التكلفة"""
    list_display = [
        'order', 'calculation_type', 'total_cost',
        'calculation_date', 'is_current'
    ]
    
    list_filter = [
        'calculation_type', 'is_current', 'calculation_date'
    ]
    
    search_fields = ['order__order_number']
    
    readonly_fields = [
        'total_cost', 'calculation_date', 'created_at', 'updated_at'
    ]
    
    fieldsets = (
        (_('معلومات الحساب'), {
            'fields': (
                'order', 'calculation_type', 'is_current'
            )
        }),
        (_('نتائج الحساب'), {
            'fields': (
                'base_cost', 'additional_costs', 'total_cost'
            )
        }),
        (_('تفاصيل إضافية'), {
            'fields': (
                'calculation_details', 'parameters_used'
            ),
            'classes': ('collapse',)
        }),
        (_('معلومات النظام'), {
            'fields': (
                'calculation_date', 'created_at', 'updated_at',
                'created_by', 'updated_by', 'notes'
            ),
            'classes': ('collapse',)
        })
    )


@admin.register(OrderSummary)
class OrderSummaryAdmin(admin.ModelAdmin):
    """إدارة ملخصات الطلبات"""
    list_display = [
        'order', 'material_cost', 'printing_cost',
        'finishing_cost', 'total_cost', 'final_price'
    ]
    
    search_fields = ['order__order_number']
    
    readonly_fields = [
        'subtotal', 'total_cost', 'profit_amount', 'final_price',
        'last_calculated', 'created_at', 'updated_at'
    ]
    
    fieldsets = (
        (_('ملخص التكاليف'), {
            'fields': (
                'order', 'material_cost', 'printing_cost',
                'finishing_cost', 'design_cost', 'other_costs'
            )
        }),
        (_('الحسابات'), {
            'fields': (
                'subtotal', 'discount_amount', 'tax_amount',
                'rush_fee', 'total_cost'
            )
        }),
        (_('الربح والسعر النهائي'), {
            'fields': (
                'profit_margin_percentage', 'profit_amount', 'final_price'
            )
        }),
        (_('معلومات إضافية'), {
            'fields': (
                'calculation_notes', 'last_calculated'
            ),
            'classes': ('collapse',)
        })
    )
    
    def get_queryset(self, request):
        """تحسين الاستعلام"""
        return super().get_queryset(request).select_related('order')


# إضافة الإدراجات للطلب الرئيسي
PrintingOrderAdmin.inlines = [OrderMaterialInline, OrderServiceInline]

# تخصيص عنوان لوحة الإدارة
admin.site.site_header = _('إدارة نظام التسعير المحسن')
admin.site.site_title = _('التسعير المحسن')
admin.site.index_title = _('لوحة التحكم')
