from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import PlateSize


@admin.register(PlateSize)
class PlateSizeAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "width",
        "height", 
        "area_display",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active",)
    search_fields = ("name",)
    ordering = ("width", "height")
    readonly_fields = ("created_at",)

    fieldsets = (
        (_("معلومات أساسية"), {"fields": ("name",)}),
        (_("الأبعاد"), {"fields": ("width", "height")}),
        (_("الإعدادات"), {"fields": ("is_active",)}),
        (
            _("معلومات النظام"),
            {"fields": ("created_at",), "classes": ("collapse",)},
        ),
    )

    def area_display(self, obj):
        """عرض المساحة بشكل مقروء"""
        area = obj.width * obj.height
        return f"{area:.2f} سم²"
    area_display.short_description = _("المساحة")
