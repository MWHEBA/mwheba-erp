"""
واجهة إدارة سجلات تدقيق الفواتير
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from financial.models import InvoiceAuditLog


@admin.register(InvoiceAuditLog)
class InvoiceAuditLogAdmin(admin.ModelAdmin):
    """
    واجهة إدارة سجلات تدقيق الفواتير
    """

    list_display = [
        "id",
        "invoice_display",
        "action_type_display",
        "difference_display",
        "adjustment_entry_link",
        "created_by",
        "created_at",
    ]

    list_filter = [
        "invoice_type",
        "action_type",
        "created_at",
    ]

    search_fields = [
        "invoice_number",
        "reason",
        "notes",
    ]

    readonly_fields = [
        "invoice_type",
        "invoice_id",
        "invoice_number",
        "action_type",
        "old_total",
        "old_cost",
        "new_total",
        "new_cost",
        "total_difference",
        "cost_difference",
        "adjustment_entry",
        "created_at",
        "created_by",
    ]

    fieldsets = (
        (
            _("معلومات الفاتورة"),
            {
                "fields": (
                    "invoice_type",
                    "invoice_id",
                    "invoice_number",
                    "action_type",
                )
            },
        ),
        (
            _("القيم القديمة"),
            {
                "fields": (
                    "old_total",
                    "old_cost",
                )
            },
        ),
        (
            _("القيم الجديدة"),
            {
                "fields": (
                    "new_total",
                    "new_cost",
                )
            },
        ),
        (
            _("الفروقات"),
            {
                "fields": (
                    "total_difference",
                    "cost_difference",
                )
            },
        ),
        (
            _("القيد التصحيحي"),
            {
                "fields": ("adjustment_entry",)
            },
        ),
        (
            _("التفاصيل"),
            {
                "fields": (
                    "reason",
                    "notes",
                )
            },
        ),
        (
            _("معلومات التتبع"),
            {
                "fields": (
                    "created_at",
                    "created_by",
                )
            },
        ),
    )

    def invoice_display(self, obj):
        """عرض معلومات الفاتورة"""
        return f"{obj.get_invoice_type_display()} - {obj.invoice_number}"

    invoice_display.short_description = _("الفاتورة")

    def action_type_display(self, obj):
        """عرض نوع الإجراء مع أيقونة"""
        if obj.action_type == "adjustment":
            return format_html(
                '<span style="color: #ff9800;">⚙️ {}</span>',
                obj.get_action_type_display(),
            )
        return obj.get_action_type_display()

    action_type_display.short_description = _("نوع الإجراء")

    def difference_display(self, obj):
        """عرض الفرق مع لون حسب الاتجاه"""
        if obj.total_difference > 0:
            color = "#4caf50"  # أخضر للزيادة
            icon = "↑"
        elif obj.total_difference < 0:
            color = "#f44336"  # أحمر للنقص
            icon = "↓"
        else:
            color = "#9e9e9e"  # رمادي لعدم التغيير
            icon = "="

        return format_html(
            '<span style="color: {}; font-weight: bold;">{} {} ج.م</span>',
            color,
            icon,
            abs(obj.total_difference),
        )

    difference_display.short_description = _("الفرق")

    def adjustment_entry_link(self, obj):
        """رابط للقيد التصحيحي"""
        if obj.adjustment_entry:
            url = reverse(
                "admin:financial_journalentry_change",
                args=[obj.adjustment_entry.id],
            )
            return format_html(
                '<a href="{}" target="_blank">{}</a>',
                url,
                obj.adjustment_entry.number,
            )
        return "-"

    adjustment_entry_link.short_description = _("القيد التصحيحي")

    def has_add_permission(self, request):
        """منع الإضافة اليدوية - يتم الإنشاء تلقائياً"""
        return False

    def has_delete_permission(self, request, obj=None):
        """منع الحذف - للحفاظ على الأثر التدقيقي"""
        return False
