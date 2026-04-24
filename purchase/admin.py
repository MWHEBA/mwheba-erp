from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from purchase.models import (
    Purchase,
    PurchaseItem,
    PurchasePayment,
    PurchaseReturn,
    PurchaseReturnItem,
)


class PurchaseItemInline(admin.TabularInline):
    """
    عرض بنود فاتورة المشتريات ضمن صفحة الفاتورة
    """

    model = PurchaseItem
    extra = 1
    min_num = 1
    fields = ("product", "quantity", "unit_price", "discount", "total")
    readonly_fields = ("total",)


class PurchasePaymentInline(admin.TabularInline):
    """
    عرض مدفوعات فاتورة المشتريات ضمن صفحة الفاتورة
    """

    model = PurchasePayment
    extra = 0
    can_delete = False
    fields = (
        "payment_date",
        "amount",
        "payment_method",
        "reference_number",
        "created_by",
    )
    readonly_fields = ("created_by",)

    def has_add_permission(self, request, obj=None):
        # يمكن إضافة مدفوعات فقط للفواتير المحفوظة
        return obj is not None and obj.id is not None


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    """
    إدارة فواتير المشتريات
    """

    list_display = (
        "number",
        "date",
        "supplier",
        "warehouse",
        "service_badge",
        "total",
        "payment_method",
        "payment_status",
        "amount_paid",
        "amount_due",
    )
    list_filter = (
        "date",
        "warehouse",
        "payment_method",
        "payment_status",
        "is_service",
        "service_type",
    )
    search_fields = ("number", "supplier__name", "notes")
    readonly_fields = (
        "subtotal",
        "total",
        "payment_status",
        "journal_entry",
        "created_at",
        "updated_at",
        "created_by",
    )
    inlines = [PurchaseItemInline, PurchasePaymentInline]
    fieldsets = (
        (None, {"fields": ("number", "date", "supplier", "warehouse")}),
        (
            _("معلومات الخدمة"),
            {
                "fields": ("is_service", "service_type", "service_metadata"),
                "classes": ("collapse",),
                "description": "معلومات إضافية إذا كانت فاتورة خدمة",
            },
        ),
        (
            _("المعلومات المالية"),
            {
                "fields": (
                    "subtotal",
                    "discount",
                    "tax",
                    "total",
                    "payment_method",
                    "payment_status",
                    "financial_category",
                    "journal_entry",
                )
            },
        ),
        (_("معلومات إضافية"), {"fields": ("notes",)}),
        (_("معلومات النظام"), {"fields": ("created_at", "updated_at", "created_by")}),
    )

    def service_badge(self, obj):
        """عرض badge للخدمات"""
        if obj.is_service:
            service_type_display = (
                obj.get_service_type_display() if obj.service_type else "خدمة"
            )
            return format_html(
                '<span style="background-color: #28a745; color: white; padding: 3px 10px; '
                'border-radius: 3px; font-size: 11px;">{}</span>',
                service_type_display,
            )
        return format_html(
            '<span style="background-color: #6c757d; color: white; padding: 3px 10px; '
            'border-radius: 3px; font-size: 11px;">منتج</span>'
        )

    service_badge.short_description = _("النوع")

    def get_queryset(self, request):
        """تحسين الاستعلام"""
        qs = super().get_queryset(request)
        return qs.select_related(
            "supplier", "warehouse", "financial_category", "journal_entry"
        )

    def amount_paid(self, obj):
        return obj.amount_paid

    amount_paid.short_description = _("المبلغ المدفوع")

    def amount_due(self, obj):
        return obj.amount_due

    amount_due.short_description = _("المبلغ المتبقي")

    def save_model(self, request, obj, form, change):
        if not change:  # إذا كان إنشاء جديد
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)

        for instance in instances:
            # تعيين المنشئ للمدفوعات الجديدة
            if isinstance(instance, PurchasePayment) and not instance.pk:
                instance.created_by = request.user
            instance.save()

        # حذف العناصر المحذوفة
        for obj in formset.deleted_objects:
            obj.delete()

        formset.save_m2m()

        # إعادة حساب إجمالي الفاتورة بعد تحديث العناصر
        if formset.model == PurchaseItem:
            self.update_purchase_totals(form.instance)

    def update_purchase_totals(self, purchase):
        """
        تحديث إجمالي الفاتورة بناءً على بنودها
        """
        from django.db.models import Sum

        items_total = purchase.items.aggregate(total=Sum("total"))["total"] or 0

        purchase.subtotal = items_total
        purchase.total = purchase.subtotal - purchase.discount + purchase.tax
        purchase.save(update_fields=["subtotal", "total"])


class PurchaseReturnItemInline(admin.TabularInline):
    """
    عرض بنود مرتجع المشتريات ضمن صفحة المرتجع
    """

    model = PurchaseReturnItem
    extra = 1
    min_num = 1
    fields = (
        "purchase_item",
        "product",
        "quantity",
        "unit_price",
        "discount",
        "total",
        "reason",
    )
    readonly_fields = ("product", "total")


@admin.register(PurchaseReturn)
class PurchaseReturnAdmin(admin.ModelAdmin):
    """
    إدارة مرتجعات المشتريات
    """

    list_display = ("number", "date", "purchase", "warehouse", "total", "status")
    list_filter = ("date", "status", "warehouse")
    search_fields = ("number", "purchase__number", "notes")
    readonly_fields = ("created_at", "updated_at", "created_by")
    inlines = [PurchaseReturnItemInline]
    fieldsets = (
        (None, {"fields": ("number", "date", "purchase", "warehouse", "status")}),
        (_("المعلومات المالية"), {"fields": ("subtotal", "discount", "tax", "total")}),
        (_("معلومات إضافية"), {"fields": ("notes",)}),
        (_("معلومات النظام"), {"fields": ("created_at", "updated_at", "created_by")}),
    )

    def save_model(self, request, obj, form, change):
        if not change:  # إذا كان إنشاء جديد
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(PurchasePayment)
class PurchasePaymentAdmin(admin.ModelAdmin):
    """
    إدارة مدفوعات فواتير المشتريات
    """

    list_display = (
        "purchase",
        "amount",
        "payment_date",
        "payment_method",
        "reference_number",
    )
    list_filter = ("payment_date", "payment_method")
    search_fields = ("purchase__number", "reference_number")
    readonly_fields = ("created_at", "created_by")

    def save_model(self, request, obj, form, change):
        if not change:  # إذا كان إنشاء جديد
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
