from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html
from .models import (
    Category,
    Product,
    Warehouse,
    Stock,
    StockMovement,
    Unit,
    ProductImage,
    ProductVariant,
    SupplierProductPrice,
    PriceHistory,
    BundleComponent,
    BundleComponentAlternative,
)

# Import governance security controls
from governance.admin_security import (
    ReadOnlyModelAdmin,
    RestrictedModelAdmin
)


class BundleComponentInline(admin.TabularInline):
    """
    إدارة مكونات المنتج المجمع كـ inline في صفحة المنتج
    """
    model = BundleComponent
    fk_name = 'bundle_product'
    extra = 1
    min_num = 0
    
    fields = ('component_product', 'required_quantity')
    autocomplete_fields = ['component_product']
    
    verbose_name = _("مكون")
    verbose_name_plural = _("مكونات المنتج المجمع")
    
    def get_queryset(self, request):
        """تحسين الاستعلام لتحميل البيانات المرتبطة"""
        return super().get_queryset(request).select_related('component_product')
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """تخصيص حقل المنتج المكون لاستبعاد المنتجات المجمعة"""
        if db_field.name == "component_product":
            # استبعاد المنتجات المجمعة من قائمة المكونات
            kwargs["queryset"] = Product.objects.filter(
                is_bundle=False, 
                is_active=True
            ).select_related('category', 'unit')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class BundleComponentAlternativeInline(admin.TabularInline):
    """
    إدارة البدائل المتاحة لمكون المنتج المجمع
    """
    model = BundleComponentAlternative
    fk_name = 'bundle_component'
    extra = 1
    min_num = 0
    
    fields = (
        'alternative_product',
        'is_default',
        'price_adjustment',
        'display_order',
        'is_active',
        'notes'
    )
    autocomplete_fields = ['alternative_product']
    
    verbose_name = _("بديل")
    verbose_name_plural = _("البدائل المتاحة")
    
    def get_queryset(self, request):
        """تحسين الاستعلام لتحميل البيانات المرتبطة"""
        return super().get_queryset(request).select_related('alternative_product')
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """تخصيص حقل المنتج البديل"""
        if db_field.name == "alternative_product":
            # عرض المنتجات العادية فقط (غير المجمعة)
            kwargs["queryset"] = Product.objects.filter(
                is_bundle=False,
                is_active=True
            ).select_related('category', 'unit')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    """
    إدارة تصنيفات المنتجات
    """

    list_display = ("name", "code", "parent", "is_active")
    list_filter = ("is_active", "parent")
    search_fields = ("name", "code", "description")
    fields = ("name", "code", "parent", "description", "is_active")
    
    def save_model(self, request, obj, form, change):
        # تحويل الكود إلى أحرف كبيرة
        if obj.code:
            obj.code = obj.code.upper().strip()
        super().save_model(request, obj, form, change)





@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    """
    إدارة وحدات القياس
    """

    list_display = ("name", "symbol", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "symbol")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """
    إدارة المنتجات مع دعم المنتجات المجمعة
    """

    list_display = (
        "name",
        "sku",
        "barcode",
        "category",
        "cost_price",
        "selling_price",
        "get_stock_display",
        "profit_margin",
        "is_bundle",
        "is_service",
        "is_active",
    )
    list_filter = ("category", "is_active", "is_featured", "is_bundle", "is_service", "item_type")
    search_fields = ("name", "sku", "barcode", "description")
    readonly_fields = ("created_at", "updated_at", "created_by", "updated_by")
    
    # إضافة الـ inline للمنتجات المجمعة
    inlines = []
    
    fieldsets = (
        (None, {"fields": ("name", "sku", "barcode", "category", "unit")}),
        (
            _("التسعير"),
            {
                "fields": (
                    "cost_price",
                    "selling_price",
                    "tax_rate",
                    "discount_rate",
                    "default_supplier",
                )
            },
        ),
        (_("المخزون"), {"fields": ("min_stock",)}),
        (
            _("المنتجات المجمعة"), 
            {
                "fields": ("is_bundle",),
                "description": _("المنتجات المجمعة هي منتجات تحتوي على مكونات متعددة")
            }
        ),
        (
            _("الخدمات"),
            {
                "fields": ("is_service",),
                "description": _("الخدمات لا تحتاج مخزون (مثل: كورسات، مواصلات)")
            }
        ),
        (
            _("معلومات المنتج"),
            {
                "fields": (
                    "item_type",
                    "suitable_for_grades", 
                    "uniform_size",
                    "uniform_gender",
                    "educational_subject",
                    "is_child_safe",
                    "quality_certificate"
                ),
                "classes": ("collapse",)
            }
        ),
        (_("معلومات إضافية"), {"fields": ("description", "is_active", "is_featured")}),
        (_("معلومات النظام"), {"fields": ("created_at", "updated_at", "created_by")}),
    )
    
    # إضافة أكشن مخصصة للمنتجات المجمعة
    actions = ['make_bundle', 'make_regular', 'recalculate_bundle_stock', 'export_bundle_info']

    def get_stock_display(self, obj):
        """عرض المخزون مع التمييز بين المنتجات العادية والمجمعة"""
        if obj.is_bundle:
            calculated_stock = obj.calculated_stock
            return f"{calculated_stock} (محسوب)"
        else:
            return obj.current_stock
    
    get_stock_display.short_description = _("المخزون")
    get_stock_display.admin_order_field = "current_stock"

    def current_stock(self, obj):
        """للتوافق مع الكود الموجود"""
        return self.get_stock_display(obj)

    current_stock.short_description = _("المخزون الحالي")

    def profit_margin(self, obj):
        return f"{obj.profit_margin:.2f}%"

    profit_margin.short_description = _("هامش الربح")
    
    def get_inlines(self, request, obj):
        """إضافة الـ inline للمنتجات المجمعة فقط"""
        inlines = []
        if obj and obj.is_bundle:
            inlines.append(BundleComponentInline)
        return inlines
    
    def get_readonly_fields(self, request, obj=None):
        """جعل بعض الحقول للقراءة فقط للمنتجات المجمعة"""
        readonly_fields = list(self.readonly_fields)
        if obj and obj.is_bundle:
            # المنتجات المجمعة لا تحتاج min_stock لأن المخزون محسوب
            readonly_fields.append('min_stock')
        return readonly_fields

    def save_model(self, request, obj, form, change):
        if not change:  # إذا كان إنشاء جديد
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
    
    # أكشن مخصصة للمنتجات المجمعة
    @admin.action(description=_('تحويل إلى منتج مجمع'))
    def make_bundle(self, request, queryset):
        """تحويل المنتجات المحددة إلى منتجات مجمعة"""
        updated = queryset.filter(is_bundle=False).update(is_bundle=True)
        if updated:
            self.message_user(
                request,
                f"تم تحويل {updated} منتج إلى منتجات مجمعة بنجاح.",
                messages.SUCCESS
            )
        else:
            self.message_user(
                request,
                "لم يتم تحديث أي منتج. تأكد من أن المنتجات المحددة ليست مجمعة بالفعل.",
                messages.WARNING
            )
    
    @admin.action(description=_('تحويل إلى منتج عادي'))
    def make_regular(self, request, queryset):
        """تحويل المنتجات المجمعة إلى منتجات عادية"""
        with transaction.atomic():
            updated_count = 0
            for product in queryset.filter(is_bundle=True):
                # حذف المكونات أولاً
                BundleComponent.objects.filter(bundle_product=product).delete()
                # تحويل إلى منتج عادي
                product.is_bundle = False
                product.save()
                updated_count += 1
            
            if updated_count:
                self.message_user(
                    request,
                    f"تم تحويل {updated_count} منتج إلى منتجات عادية وحذف مكوناتها.",
                    messages.SUCCESS
                )
            else:
                self.message_user(
                    request,
                    "لم يتم تحديث أي منتج.",
                    messages.WARNING
                )
    
    @admin.action(description=_('إعادة حساب مخزون المنتجات المجمعة'))
    def recalculate_bundle_stock(self, request, queryset):
        """إعادة حساب مخزون المنتجات المجمعة المحددة"""
        bundle_products = queryset.filter(is_bundle=True)
        if not bundle_products.exists():
            self.message_user(
                request,
                "لا توجد منتجات مجمعة في التحديد.",
                messages.WARNING
            )
            return
        
        try:
            from .services.stock_calculation_engine import StockCalculationEngine
            
            recalculated_count = 0
            for product in bundle_products:
                # إعادة حساب المخزون
                StockCalculationEngine.calculate_bundle_stock(product)
                recalculated_count += 1
            
            self.message_user(
                request,
                f"تم إعادة حساب مخزون {recalculated_count} منتج مجمع بنجاح.",
                messages.SUCCESS
            )
        except Exception as e:
            self.message_user(
                request,
                f"حدث خطأ أثناء إعادة حساب المخزون: {str(e)}",
                messages.ERROR
            )
    
    @admin.action(description=_('تصدير معلومات المنتجات المجمعة'))
    def export_bundle_info(self, request, queryset):
        """تصدير معلومات المنتجات المجمعة ومكوناتها"""
        import csv
        from django.http import HttpResponse
        
        bundle_products = queryset.filter(is_bundle=True)
        if not bundle_products.exists():
            self.message_user(
                request,
                "لا توجد منتجات مجمعة في التحديد.",
                messages.WARNING
            )
            return
        
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="bundle_products.csv"'
        response.write('\ufeff')  # BOM for UTF-8
        
        writer = csv.writer(response)
        writer.writerow([
            'اسم المنتج المجمع', 'كود المنتج', 'السعر', 'المخزون المحسوب',
            'المنتج المكون', 'الكمية المطلوبة', 'مخزون المكون'
        ])
        
        for bundle in bundle_products:
            components = BundleComponent.objects.filter(bundle_product=bundle).select_related('component_product')
            if components.exists():
                for component in components:
                    writer.writerow([
                        bundle.name,
                        bundle.sku,
                        bundle.selling_price,
                        bundle.calculated_stock,
                        component.component_product.name,
                        component.required_quantity,
                        component.component_product.current_stock
                    ])
            else:
                writer.writerow([
                    bundle.name,
                    bundle.sku,
                    bundle.selling_price,
                    bundle.calculated_stock,
                    'لا توجد مكونات',
                    '',
                    ''
                ])
        
        return response


@admin.register(BundleComponent)
class BundleComponentAdmin(admin.ModelAdmin):
    """
    إدارة مكونات المنتجات المجمعة
    """
    
    inlines = [BundleComponentAlternativeInline]
    
    list_display = (
        'get_bundle_name',
        'get_component_name', 
        'required_quantity',
        'get_component_stock',
        'get_available_bundles',
        'get_alternatives_count',
        'created_at'
    )
    list_filter = (
        'bundle_product__category',
        'component_product__category',
        'created_at'
    )
    search_fields = (
        'bundle_product__name',
        'bundle_product__sku',
        'component_product__name',
        'component_product__sku'
    )
    readonly_fields = ('created_at',)
    
    fieldsets = (
        (None, {
            'fields': ('bundle_product', 'component_product', 'required_quantity')
        }),
        (_('معلومات النظام'), {
            'fields': ('created_at',),
            'classes': ('collapse',)
        })
    )
    
    # تحسين الاستعلامات
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'bundle_product', 
            'component_product',
            'bundle_product__category',
            'component_product__category'
        )
    
    def get_bundle_name(self, obj):
        return f"{obj.bundle_product.name} ({obj.bundle_product.sku})"
    get_bundle_name.short_description = _('المنتج المجمع')
    get_bundle_name.admin_order_field = 'bundle_product__name'
    
    def get_component_name(self, obj):
        return f"{obj.component_product.name} ({obj.component_product.sku})"
    get_component_name.short_description = _('المنتج المكون')
    get_component_name.admin_order_field = 'component_product__name'
    
    def get_component_stock(self, obj):
        return obj.component_product.current_stock
    get_component_stock.short_description = _('مخزون المكون')
    
    def get_available_bundles(self, obj):
        """حساب عدد المنتجات المجمعة المتاحة بناءً على هذا المكون"""
        component_stock = obj.component_product.current_stock
        if obj.required_quantity > 0:
            return component_stock // obj.required_quantity
        return 0
    get_available_bundles.short_description = _('المنتجات المتاحة')
    
    def get_alternatives_count(self, obj):
        """عدد البدائل المتاحة لهذا المكون"""
        count = obj.alternatives.filter(is_active=True).count()
        if count > 0:
            return format_html(
                '<span style="color: green; font-weight: bold;">{} بديل</span>',
                count
            )
        return format_html('<span style="color: gray;">لا يوجد</span>')
    get_alternatives_count.short_description = _('البدائل المتاحة')
    
    # أكشن مخصصة
    actions = ['validate_components', 'update_bundle_stock']
    
    @admin.action(description=_('التحقق من صحة المكونات'))
    def validate_components(self, request, queryset):
        """التحقق من صحة مكونات المنتجات المجمعة"""
        invalid_count = 0
        valid_count = 0
        
        for component in queryset:
            try:
                component.full_clean()
                valid_count += 1
            except Exception as e:
                invalid_count += 1
                self.message_user(
                    request,
                    f"مكون غير صحيح: {component} - {str(e)}",
                    messages.ERROR
                )
        
        if valid_count > 0:
            self.message_user(
                request,
                f"تم التحقق من {valid_count} مكون بنجاح.",
                messages.SUCCESS
            )
    
    @admin.action(description=_('تحديث مخزون المنتجات المجمعة'))
    def update_bundle_stock(self, request, queryset):
        """تحديث مخزون المنتجات المجمعة المتأثرة"""
        try:
            from .services.stock_calculation_engine import StockCalculationEngine
            
            # الحصول على المنتجات المجمعة المتأثرة
            bundle_products = set()
            for component in queryset:
                bundle_products.add(component.bundle_product)
            
            updated_count = 0
            for bundle in bundle_products:
                StockCalculationEngine.calculate_bundle_stock(bundle)
                updated_count += 1
            
            self.message_user(
                request,
                f"تم تحديث مخزون {updated_count} منتج مجمع.",
                messages.SUCCESS
            )
        except Exception as e:
            self.message_user(
                request,
                f"حدث خطأ أثناء تحديث المخزون: {str(e)}",
                messages.ERROR
            )
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """تخصيص حقول الاختيار"""
        if db_field.name == "bundle_product":
            # عرض المنتجات المجمعة فقط
            kwargs["queryset"] = Product.objects.filter(
                is_bundle=True, 
                is_active=True
            ).select_related('category')
        elif db_field.name == "component_product":
            # عرض المنتجات العادية فقط (غير المجمعة)
            kwargs["queryset"] = Product.objects.filter(
                is_bundle=False, 
                is_active=True
            ).select_related('category')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    """
    إدارة صور المنتجات
    """

    list_display = ("product", "image", "is_primary", "alt_text", "created_at")
    list_filter = ("is_primary", "created_at")
    search_fields = ("product__name", "product__sku", "alt_text")


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    """
    إدارة متغيرات المنتجات
    """

    list_display = (
        "product",
        "name",
        "sku",
        "cost_price",
        "selling_price",
        "stock",
        "is_active",
    )
    list_filter = ("is_active", "product")
    search_fields = ("product__name", "name", "sku", "barcode")


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    """
    إدارة المخازن
    """

    list_display = ("name", "code", "location", "manager", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "code", "location")


@admin.register(Stock)
class StockAdmin(ReadOnlyModelAdmin):
    """
    إدارة المخزون - محمي بنظام الحوكمة
    SECURITY: High-risk model - read-only with MovementService authority
    """

    # Security configuration
    authoritative_service = "MovementService"
    business_interface_url = "/product/stock-management/"
    security_warning_message = _(
        "⚠️ تحذير أمني: المخزون محمي ولا يمكن تعديله مباشرة. "
        "استخدم MovementService لتحديث الكميات بأمان."
    )

    list_display = ("product", "warehouse", "quantity", "updated_at", "security_status")
    list_filter = ("warehouse", "updated_at")
    search_fields = ("product__name", "product__sku", "warehouse__name")
    readonly_fields = ("updated_at", "security_info")
    
    fieldsets = (
        (_("معلومات المخزون"), {
            "fields": ("product", "warehouse", "quantity")
        }),
        (_("معلومات النظام"), {
            "fields": ("updated_at",)
        }),
        (_("معلومات الأمان"), {
            "fields": ("security_info",),
            "classes": ("collapse",),
            "description": "معلومات الحماية والحوكمة للمخزون"
        }),
    )
    
    def security_status(self, obj):
        """عرض حالة الأمان للمخزون."""
        return format_html(
            '<span style="color: green; font-weight: bold;">🔒 محمي</span>'
        )
    security_status.short_description = _("حالة الأمان")
    
    def security_info(self, obj):
        """عرض معلومات الأمان والحوكمة."""
        return format_html(
            '<div style="background: #f8f9fa; padding: 10px; border-radius: 5px;">'
            '<strong>نظام الحوكمة:</strong><br>'
            '• الخدمة المخولة: MovementService<br>'
            '• وضع القراءة فقط: نشط<br>'
            '• الكمية الحالية: {}<br>'
            '• آخر تحديث: {}<br>'
            '</div>',
            obj.quantity,
            obj.updated_at.strftime('%Y-%m-%d %H:%M:%S') if obj.updated_at else 'غير محدد'
        )
    security_info.short_description = _("معلومات الأمان")


@admin.register(StockMovement)
class StockMovementAdmin(ReadOnlyModelAdmin):
    """
    إدارة حركات المخزون - محمية بنظام الحوكمة
    SECURITY: High-risk model - read-only with MovementService authority
    """

    # Security configuration
    authoritative_service = "MovementService"
    business_interface_url = "/product/stock-movements/"
    security_warning_message = _(
        "⚠️ تحذير أمني: حركات المخزون محمية ولا يمكن تعديلها مباشرة. "
        "استخدم MovementService لإنشاء الحركات بأمان."
    )

    list_display = (
        "product",
        "movement_type",
        "warehouse",
        "quantity",
        "timestamp",
        "created_by",
        "security_status"
    )
    list_filter = ("movement_type", "warehouse", "timestamp")
    search_fields = ("product__name", "product__sku", "reference_number", "notes")
    readonly_fields = ("timestamp", "created_by", "security_info")
    
    fieldsets = (
        (None, {"fields": ("product", "warehouse", "movement_type", "quantity")}),
        (
            _("معلومات إضافية"),
            {"fields": ("reference_number", "notes", "destination_warehouse")},
        ),
        (_("معلومات النظام"), {"fields": ("timestamp", "created_by")}),
        (_("معلومات الأمان"), {
            "fields": ("security_info",),
            "classes": ("collapse",),
            "description": "معلومات الحماية والحوكمة لحركة المخزون"
        }),
    )

    def security_status(self, obj):
        """عرض حالة الأمان لحركة المخزون."""
        return format_html(
            '<span style="color: green; font-weight: bold;">🔒 محمي</span>'
        )
    security_status.short_description = _("حالة الأمان")
    
    def security_info(self, obj):
        """عرض معلومات الأمان والحوكمة."""
        return format_html(
            '<div style="background: #f8f9fa; padding: 10px; border-radius: 5px;">'
            '<strong>نظام الحوكمة:</strong><br>'
            '• الخدمة المخولة: MovementService<br>'
            '• وضع القراءة فقط: نشط<br>'
            '• نوع الحركة: {}<br>'
            '• الكمية: {}<br>'
            '• تاريخ الإنشاء: {}<br>'
            '</div>',
            obj.get_movement_type_display() if hasattr(obj, 'get_movement_type_display') else obj.movement_type,
            obj.quantity,
            obj.timestamp.strftime('%Y-%m-%d %H:%M:%S') if obj.timestamp else 'غير محدد'
        )
    security_info.short_description = _("معلومات الأمان")

    def save_model(self, request, obj, form, change):
        """Override to enforce governance controls."""
        # This will be blocked by ReadOnlyModelAdmin
        super().save_model(request, obj, form, change)


@admin.register(SupplierProductPrice)
class SupplierProductPriceAdmin(admin.ModelAdmin):
    """
    إدارة أسعار المنتجات للموردين
    """

    list_display = (
        "product",
        "supplier",
        "cost_price",
        "is_default",
        "last_purchase_date",
        "last_purchase_quantity",
        "is_active",
        "created_at",
    )
    list_filter = ("is_default", "is_active", "supplier", "last_purchase_date")
    search_fields = (
        "product__name",
        "product__sku",
        "supplier__name",
        "supplier__code",
    )
    readonly_fields = ("created_at", "updated_at", "created_by")

    fieldsets = (
        (None, {"fields": ("product", "supplier", "cost_price")}),
        (_("الحالة"), {"fields": ("is_active", "is_default")}),
        (
            _("معلومات آخر شراء"),
            {"fields": ("last_purchase_date", "last_purchase_quantity")},
        ),
        (_("ملاحظات"), {"fields": ("notes",)}),
        (
            _("معلومات النظام"),
            {
                "fields": ("created_at", "updated_at", "created_by"),
                "classes": ("collapse",),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        if not change:  # إذا كان إنشاء جديد
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(PriceHistory)
class PriceHistoryAdmin(admin.ModelAdmin):
    """
    إدارة تاريخ تغيير الأسعار
    """

    list_display = (
        "get_product_name",
        "get_supplier_name",
        "old_price",
        "new_price",
        "change_amount",
        "change_percentage",
        "change_reason",
        "change_date",
        "changed_by",
    )
    list_filter = ("change_reason", "change_date", "supplier_product_price__supplier")
    search_fields = (
        "supplier_product_price__product__name",
        "supplier_product_price__supplier__name",
        "purchase_reference",
        "notes",
    )
    readonly_fields = (
        "change_date",
        "changed_by",
        "change_amount",
        "change_percentage",
    )
    date_hierarchy = "change_date"

    fieldsets = (
        (None, {"fields": ("supplier_product_price", "old_price", "new_price")}),
        (
            _("التغيير"),
            {"fields": ("change_amount", "change_percentage", "change_reason")},
        ),
        (_("المرجع"), {"fields": ("purchase_reference", "notes")}),
        (
            _("معلومات النظام"),
            {"fields": ("change_date", "changed_by"), "classes": ("collapse",)},
        ),
    )

    def get_product_name(self, obj):
        return obj.supplier_product_price.product.name

    get_product_name.short_description = _("المنتج")
    get_product_name.admin_order_field = "supplier_product_price__product__name"

    def get_supplier_name(self, obj):
        return obj.supplier_product_price.supplier.name

    get_supplier_name.short_description = _("المورد")
    get_supplier_name.admin_order_field = "supplier_product_price__supplier__name"

    def has_add_permission(self, request):
        # منع الإضافة اليدوية - يتم التسجيل تلقائياً
        return False

    def has_delete_permission(self, request, obj=None):
        # منع الحذف للحفاظ على سجل التاريخ
        return False



@admin.register(BundleComponentAlternative)
class BundleComponentAlternativeAdmin(admin.ModelAdmin):
    """
    إدارة بدائل مكونات المنتجات المجمعة
    """
    
    list_display = (
        'get_bundle_name',
        'get_component_name',
        'alternative_product',
        'is_default',
        'price_adjustment',
        'display_order',
        'is_active',
        'created_at'
    )
    list_filter = (
        'is_default',
        'is_active',
        'bundle_component__bundle_product__category',
        'created_at'
    )
    search_fields = (
        'bundle_component__bundle_product__name',
        'bundle_component__component_product__name',
        'alternative_product__name',
        'alternative_product__sku'
    )
    readonly_fields = ('created_at', 'updated_at')
    autocomplete_fields = ['alternative_product']
    
    fieldsets = (
        (None, {
            'fields': ('bundle_component', 'alternative_product')
        }),
        (_('إعدادات البديل'), {
            'fields': ('is_default', 'price_adjustment', 'display_order', 'is_active')
        }),
        (_('ملاحظات'), {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
        (_('معلومات النظام'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_queryset(self, request):
        """تحسين الاستعلام"""
        return super().get_queryset(request).select_related(
            'bundle_component__bundle_product',
            'bundle_component__component_product',
            'alternative_product'
        )
    
    def get_bundle_name(self, obj):
        return obj.bundle_component.bundle_product.name
    get_bundle_name.short_description = _('المنتج المجمع')
    get_bundle_name.admin_order_field = 'bundle_component__bundle_product__name'
    
    def get_component_name(self, obj):
        return obj.bundle_component.component_product.name
    get_component_name.short_description = _('المكون الأساسي')
    get_component_name.admin_order_field = 'bundle_component__component_product__name'
