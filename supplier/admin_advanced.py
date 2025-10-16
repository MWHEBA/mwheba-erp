from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import (
    SupplierType,
    SpecializedService,
    ServicePriceTier,
    PaperServiceDetails,
    DigitalPrintingDetails,
    FinishingServiceDetails,
    OffsetPrintingDetails,
    PlateServiceDetails,
    OutdoorPrintingDetails,
    LaserServiceDetails,
    VIPGiftDetails,
)

# ========================================
# Inline Classes
# ========================================


class ServicePriceTierInline(admin.TabularInline):
    model = ServicePriceTier
    extra = 1
    fields = (
        "tier_name",
        "min_quantity",
        "max_quantity",
        "price_per_unit",
        "discount_percentage",
        "is_active",
        "display_order",
    )
    ordering = ("display_order", "min_quantity")


class PaperServiceDetailsInline(admin.StackedInline):
    model = PaperServiceDetails
    extra = 0
    fieldsets = (
        (
            "معلومات الورق",
            {
                "fields": (
                    "paper_type",
                    "gsm",
                    "sheet_size",
                    "custom_width",
                    "custom_height",
                )
            },
        ),
        ("معلومات المورد", {"fields": ("country_of_origin", "brand")}),
        ("السعر الأساسي", {"fields": ("price_per_sheet",)}),
    )


class DigitalPrintingDetailsInline(admin.StackedInline):
    model = DigitalPrintingDetails
    extra = 0
    fieldsets = (
        (
            "معلومات الماكينة",
            {
                "fields": (
                    "machine_type",
                    "machine_model",
                    "paper_handling",
                    "paper_size",
                )
            },
        ),
        (
            "المقاسات والقدرات",
            {
                "fields": (
                    "max_paper_weight_gsm",
                    "supports_heavy_paper",
                )
            },
        ),
        (
            "التسعير",
            {
                "fields": (
                    "price_per_page_bw",
                    "price_per_page_color",
                    "has_price_tiers",
                )
            },
        ),
        (
            "الإمكانيات",
            {
                "fields": (
                    "duplex_printing",
                    "variable_data_printing",
                    "pages_per_minute_bw",
                    "pages_per_minute_color",
                    "setup_time_minutes",
                )
            },
        ),
    )


class FinishingServiceDetailsInline(admin.StackedInline):
    model = FinishingServiceDetails
    extra = 0
    fields = (
        "finishing_type",
        "calculation_method",
        "min_size_cm",
        "max_size_cm",
        "price_per_unit",
        "setup_time_minutes",
        "turnaround_time_hours",
    )


class OffsetPrintingDetailsInline(admin.StackedInline):
    model = OffsetPrintingDetails
    extra = 0
    fieldsets = (
        (
            "معلومات الماكينة",
            {
                "fields": (
                    "machine_type",
                    "sheet_size",
                    "custom_width_cm",
                    "custom_height_cm",
                )
            },
        ),
        ("تكاليف الإعداد", {"fields": ("color_calibration_cost",)}),
        (
            "التسعير بالتراج",
            {"fields": ("impression_cost_per_1000", "special_impression_cost", "break_impression_cost")},
        ),
        (
            "إمكانيات الماكينة",
            {"fields": ("max_colors", "has_uv_coating", "has_aqueous_coating")},
        ),
    )


class PlateServiceDetailsInline(admin.StackedInline):
    model = PlateServiceDetails
    extra = 0
    fieldsets = (
        (
            "معلومات الزنك",
            {
                "fields": (
                    "plate_size",
                    "custom_width_cm",
                    "custom_height_cm",
                )
            },
        ),
        ("التسعير", {"fields": ("price_per_plate", "set_price")}),
    )


class OutdoorPrintingDetailsInline(admin.StackedInline):
    model = OutdoorPrintingDetails
    extra = 0
    fieldsets = (
        (
            "معلومات الطباعة",
            {
                "fields": (
                    "material_type",
                    "printing_type",
                    "max_width_cm",
                    "max_height_cm",
                )
            },
        ),
        ("التسعير", {"fields": ("price_per_sqm", "min_order_sqm")}),
        (
            "خدمات إضافية",
            {
                "fields": (
                    "includes_hemming",
                    "hemming_cost_per_meter",
                    "includes_grommets",
                    "grommet_cost_each",
                )
            },
        ),
        (
            "التسليم والتركيب",
            {
                "fields": (
                    "production_time_days",
                    "includes_installation",
                    "installation_cost_per_sqm",
                )
            },
        ),
    )


class LaserServiceDetailsInline(admin.StackedInline):
    model = LaserServiceDetails
    extra = 0
    fieldsets = (
        ("معلومات الليزر", {"fields": ("laser_type", "service_type", "material_type")}),
        (
            "قيود المقاسات",
            {"fields": ("max_width_cm", "max_height_cm", "max_thickness_mm")},
        ),
        (
            "التسعير",
            {
                "fields": (
                    "price_per_minute",
                    "price_per_cm",
                    "price_per_piece",
                    "setup_cost",
                )
            },
        ),
        (
            "معلومات إضافية",
            {
                "fields": (
                    "min_order_value",
                    "turnaround_time_hours",
                    "includes_design",
                    "design_cost_per_hour",
                )
            },
        ),
    )


class VIPGiftDetailsInline(admin.StackedInline):
    model = VIPGiftDetails
    extra = 0
    fieldsets = (
        (
            "معلومات الهدية",
            {
                "fields": (
                    "gift_category",
                    "customization_type",
                    "product_name",
                    "product_description",
                )
            },
        ),
        ("معلومات المنتج", {"fields": ("brand", "country_of_origin")}),
        ("التسعير", {"fields": ("base_price", "customization_cost", "packaging_cost")}),
        ("قيود الطلب", {"fields": ("min_order_quantity", "max_customization_chars")}),
        (
            "التسليم",
            {
                "fields": (
                    "production_time_days",
                    "includes_gift_box",
                    "includes_certificate",
                )
            },
        ),
        (
            "خدمات إضافية",
            {
                "fields": (
                    "includes_delivery",
                    "delivery_cost",
                    "includes_setup_service",
                    "setup_service_cost",
                )
            },
        ),
    )


# ========================================
# Admin Classes
# ========================================


@admin.register(SupplierType)
class SupplierTypeAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "icon_display",
        "color_display",
        "suppliers_count",
        "is_active",
        "display_order",
    )
    list_filter = ("is_active",)
    search_fields = ("name", "code", "description")
    ordering = ("display_order", "name")

    def icon_display(self, obj):
        return format_html('<i class="{}" style="font-size: 18px;"></i>', obj.icon)

    icon_display.short_description = "أيقونة"

    def color_display(self, obj):
        return format_html(
            '<div style="width: 20px; height: 20px; background-color: {}; border-radius: 3px; display: inline-block;"></div>',
            obj.color,
        )

    color_display.short_description = "لون"

    def suppliers_count(self, obj):
        count = obj.suppliers.filter(is_active=True).count()
        return format_html('<span class="badge badge-primary">{}</span>', count)

    suppliers_count.short_description = "عدد الموردين"


# تم حذف SupplierServiceCategoryAdmin لأن النموذج تم حذفه لتجنب التكرار


@admin.register(SpecializedService)
class SpecializedServiceAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "supplier",
        "category",
        "get_main_price",
        "setup_cost",
        "has_tiers",
        "is_active",
    )
    list_filter = ("category", "supplier__primary_type", "is_active", "created_at")
    search_fields = ("name", "description", "supplier__name")
    ordering = ("-created_at",)

    fieldsets = (
        ("معلومات أساسية", {"fields": ("supplier", "category", "name", "description")}),
        ("إعدادات الخدمة", {"fields": ("setup_cost", "is_active")}),
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

    has_tiers.short_description = "شرائح سعرية"

    def get_service_type(self, obj):
        """عرض نوع الخدمة التفصيلي للتغطية والتقفيل"""
        if obj.category.code == "coating" and hasattr(obj, "finishing_details"):
            try:
                from pricing.models import CoatingType
                coating_type = CoatingType.objects.get(id=obj.finishing_details.finishing_type)
                return format_html('<span class="badge badge-success">{}</span>', coating_type.name)
            except:
                return format_html('<span class="text-muted">نوع غير معروف</span>')
        elif obj.category.code == "packaging" and hasattr(obj, "finishing_details"):
            type_display = {
                'lamination': 'تقفيل',
                'cellophane': 'سيلوفان',
                'thermal_packaging': 'تغليف حراري',
                'box_packaging': 'تعبئة في صناديق',
                'custom_packaging': 'تعبئة مخصصة'
            }.get(obj.finishing_details.finishing_type, obj.finishing_details.finishing_type)
            return format_html('<span class="badge badge-info">{}</span>', type_display)
        return "-"

    get_service_type.short_description = "نوع الخدمة"

    def get_main_price(self, obj):
        """عرض السعر الأساسي حسب نوع الخدمة"""
        if obj.category.code == "paper" and hasattr(obj, "paper_details"):
            price = obj.paper_details.price_per_sheet
            return format_html('<span class="badge badge-success">{} ج.م/فرخ</span>', price)
        elif obj.category.code == "digital_printing" and hasattr(obj, "digital_details"):
            if obj.digital_details.price_per_page_color:
                return format_html('<span class="badge badge-info">{} ج.م/صفحة ملونة</span>', 
                                 obj.digital_details.price_per_page_color)
        elif obj.category.code == "offset_printing" and hasattr(obj, "offset_details"):
            if obj.offset_details.impression_cost_per_1000:
                return format_html('<span class="badge badge-warning">{} ج.م/1000 تراج</span>', 
                                 obj.offset_details.impression_cost_per_1000)
        elif obj.category.code == "finishing" and hasattr(obj, "finishing_details"):
            price = obj.finishing_details.price_per_unit
            return format_html('<span class="badge badge-primary">{} ج.م/وحدة</span>', price)
        elif obj.category.code == "coating" and hasattr(obj, "finishing_details"):
            price = obj.finishing_details.price_per_unit
            method = obj.finishing_details.calculation_method
            method_display = {
                'per_piece': 'قطعة',
                'per_thousand': '1000',
                'per_square_meter': 'م²',
                'per_sheet': 'فرخ',
                'per_hour': 'ساعة'
            }.get(method, 'وحدة')
            return format_html('<span class="badge badge-success">{} ج.م/{}</span>', price, method_display)
        elif obj.category.code == "packaging" and hasattr(obj, "finishing_details"):
            price = obj.finishing_details.price_per_unit
            method = obj.finishing_details.calculation_method
            method_display = {
                'per_piece': 'قطعة',
                'per_thousand': '1000',
                'per_square_meter': 'م²',
                'per_sheet': 'فرخ',
                'per_hour': 'ساعة'
            }.get(method, 'وحدة')
            return format_html('<span class="badge badge-info">{} ج.م/{}</span>', price, method_display)
        elif obj.category.code == "laser" and hasattr(obj, "laser_details"):
            if obj.laser_details.price_per_minute:
                return format_html('<span class="badge badge-dark">{} ج.م/دقيقة</span>', 
                                 obj.laser_details.price_per_minute)
        
        return format_html('<span class="text-muted">غير محدد</span>')

    get_main_price.short_description = "السعر الأساسي"

    def get_inline_instances(self, request, obj=None):
        """عرض الـ inline المناسب حسب فئة الخدمة"""
        if not obj:
            return []

        inlines = [ServicePriceTierInline]

        if obj.category.code == "paper":
            inlines.append(PaperServiceDetailsInline)
        elif obj.category.code == "digital_printing":
            inlines.append(DigitalPrintingDetailsInline)
        elif obj.category.code == "finishing":
            inlines.append(FinishingServiceDetailsInline)
        elif obj.category.code == "coating":
            inlines.append(FinishingServiceDetailsInline)
        elif obj.category.code == "packaging":
            inlines.append(FinishingServiceDetailsInline)
        elif obj.category.code == "offset_printing":
            inlines.append(OffsetPrintingDetailsInline)
        elif obj.category.code == "plates":
            inlines.append(PlateServiceDetailsInline)
        elif obj.category.code == "outdoor":
            inlines.append(OutdoorPrintingDetailsInline)
        elif obj.category.code == "laser":
            inlines.append(LaserServiceDetailsInline)
        elif obj.category.code == "vip_gifts":
            inlines.append(VIPGiftDetailsInline)

        return [inline(self.model, self.admin_site) for inline in inlines]


@admin.register(ServicePriceTier)
class ServicePriceTierAdmin(admin.ModelAdmin):
    list_display = (
        "service",
        "tier_name",
        "quantity_range",
        "price_per_unit",
        "discount_percentage",
        "is_active",
        "display_order",
    )
    list_filter = ("service__category", "is_active")
    search_fields = ("service__name", "tier_name")
    ordering = ("service", "display_order", "min_quantity")

    def quantity_range(self, obj):
        if obj.max_quantity:
            return f"{obj.min_quantity} - {obj.max_quantity}"
        else:
            return f"{obj.min_quantity}+"

    quantity_range.short_description = "نطاق الكمية"


# ========================================
# تسجيل النماذج التفصيلية
# ========================================


# تم حذف PaperServiceDetails من Admin لتجنب التكرار
# البيانات متاحة من خلال SpecializedService مع inline

# تم حذف جميع النماذج التفصيلية من Admin لتجنب التكرار
# جميع البيانات متاحة من خلال SpecializedService مع inlines

# @admin.register(DigitalPrintingDetails) - محذوف
# @admin.register(OffsetPrintingDetails) - محذوف
# جميع النماذج التفصيلية محذوفة من Admin لتجنب التكرار
# البيانات متاحة من خلال SpecializedService مع inlines المناسبة

# الفوائد:
# 1. تجنب التكرار في واجهة الإدارة
# 2. إدارة موحدة للخدمات من مكان واحد
# 3. عرض أفضل للعلاقات بين البيانات
# 4. تقليل التعقيد للمستخدمين


# تخصيص العنوان
admin.site.site_header = "إدارة الخدمات المتخصصة - MWHEBA ERP"
admin.site.site_title = "الخدمات المتخصصة"
admin.site.index_title = "لوحة تحكم الخدمات المتخصصة"
