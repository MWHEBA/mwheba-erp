from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import (
    PricingOrder, InternalContent, OrderFinishing,
    ExtraExpense, OrderComment, OffsetMachineType, OffsetSheetSize,
    DigitalMachineType, DigitalSheetSize
)


class InternalContentInline(admin.StackedInline):
    model = InternalContent
    can_delete = True
    verbose_name = _('محتوى داخلي')
    verbose_name_plural = _('محتوى داخلي')


class OrderFinishingInline(admin.TabularInline):
    model = OrderFinishing
    extra = 1
    verbose_name = _('تشطيب')
    verbose_name_plural = _('تشطيبات')


class ExtraExpenseInline(admin.TabularInline):
    model = ExtraExpense
    extra = 1
    verbose_name = _('مصروف إضافي')
    verbose_name_plural = _('مصاريف إضافية')


class OrderCommentInline(admin.TabularInline):
    model = OrderComment
    extra = 1
    verbose_name = _('تعليق')
    verbose_name_plural = _('تعليقات')
    readonly_fields = ('user', 'created_at')


@admin.register(PricingOrder)
class PricingOrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'client', 'title', 'order_type', 'status', 'created_by', 'created_at')
    list_filter = ('status', 'order_type', 'is_approved', 'is_executed', 'created_at')
    search_fields = ('order_number', 'title', 'client__name', 'description')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    
    fieldsets = (
        (_('معلومات الطلب الأساسية'), {
            'fields': ('order_number', 'client', 'order_type', 'title', 'description', 'quantity')
        }),
        (_('المحتوى'), {
            'fields': ('has_internal_content',)
        }),
        (_('معلومات الطباعة'), {
            'fields': ('paper_type', 'paper_size', 'print_direction', 'print_sides', 'colors_front', 'colors_back', 'coating_type')
        }),
        (_('المورد'), {
            'fields': ('supplier', 'press')
        }),
        (_('التكاليف والأسعار'), {
            'fields': ('material_cost', 'printing_cost', 'finishing_cost', 'extra_cost', 'total_cost', 'profit_margin', 'sale_price')
        }),
        (_('الحالة'), {
            'fields': ('status', 'is_approved', 'is_executed', 'approved_by', 'approved_at', 'executed_at')
        }),
        (_('معلومات النظام'), {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('order_number', 'total_cost', 'created_at', 'updated_at', 'approved_at', 'executed_at')
    inlines = [InternalContentInline, OrderFinishingInline, ExtraExpenseInline, OrderCommentInline]
    
    def save_model(self, request, obj, form, change):
        if not change:  # If creating a new object
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
    
    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            if isinstance(instance, OrderComment) and not instance.pk:
                instance.user = request.user
            instance.save()
        formset.save_m2m()


@admin.register(InternalContent)
class InternalContentAdmin(admin.ModelAdmin):
    list_display = ('order', 'paper_type', 'page_count', 'material_cost', 'printing_cost')
    list_filter = ('paper_type',)
    search_fields = ('order__order_number', 'order__title')
    ordering = ('-order__created_at',)


@admin.register(OrderFinishing)
class OrderFinishingAdmin(admin.ModelAdmin):
    list_display = ('order', 'finishing_type', 'quantity', 'unit_price', 'total_price')
    list_filter = ('finishing_type',)
    search_fields = ('order__order_number', 'order__title', 'finishing_type__name')
    ordering = ('-order__created_at',)


@admin.register(ExtraExpense)
class ExtraExpenseAdmin(admin.ModelAdmin):
    list_display = ('order', 'name', 'amount')
    search_fields = ('order__order_number', 'order__title', 'name', 'description')
    ordering = ('-order__created_at',)


@admin.register(OrderComment)
class OrderCommentAdmin(admin.ModelAdmin):
    list_display = ('order', 'user', 'comment', 'created_at')
    list_filter = ('user',)
    search_fields = ('order__order_number', 'order__title', 'user__email', 'comment')
    ordering = ('-created_at',)
    readonly_fields = ('created_at',)


@admin.register(OffsetMachineType)
class OffsetMachineTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'manufacturer', 'is_active', 'is_default', 'created_at')
    list_filter = ('manufacturer', 'is_active', 'is_default')
    search_fields = ('name', 'code', 'manufacturer', 'description')
    ordering = ('manufacturer', 'name')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        (_('معلومات أساسية'), {
            'fields': ('name', 'code', 'manufacturer')
        }),
        (_('الوصف'), {
            'fields': ('description',)
        }),
        (_('الإعدادات'), {
            'fields': ('is_active', 'is_default')
        }),
        (_('معلومات النظام'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(OffsetSheetSize)
class OffsetSheetSizeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'width_cm', 'height_cm', 'area_m2', 'is_active', 'is_default', 'is_custom_size')
    list_filter = ('is_active', 'is_default', 'is_custom_size')
    search_fields = ('name', 'code', 'description')
    ordering = ('width_cm', 'height_cm')
    readonly_fields = ('created_at', 'updated_at', 'area_cm2', 'area_m2')
    
    fieldsets = (
        (_('معلومات أساسية'), {
            'fields': ('name', 'code')
        }),
        (_('الأبعاد'), {
            'fields': ('width_cm', 'height_cm', 'area_cm2', 'area_m2')
        }),
        (_('الوصف'), {
            'fields': ('description',)
        }),
        (_('الإعدادات'), {
            'fields': ('is_active', 'is_default', 'is_custom_size')
        }),
        (_('معلومات النظام'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


# ==================== إدارة ماكينات الديجيتال ====================

@admin.register(DigitalMachineType)
class DigitalMachineTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'manufacturer', 'is_active', 'is_default', 'created_at')
    list_filter = ('manufacturer', 'is_active', 'is_default')
    search_fields = ('name', 'code', 'manufacturer', 'description')
    ordering = ('manufacturer', 'name')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        (_('معلومات أساسية'), {
            'fields': ('name', 'code', 'manufacturer')
        }),
        (_('الوصف'), {
            'fields': ('description',)
        }),
        (_('الإعدادات'), {
            'fields': ('is_active', 'is_default')
        }),
        (_('معلومات النظام'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(DigitalSheetSize)
class DigitalSheetSizeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'width_cm', 'height_cm', 'area_m2', 'is_active', 'is_default', 'is_custom_size')
    list_filter = ('is_active', 'is_default', 'is_custom_size')
    search_fields = ('name', 'code', 'description')
    ordering = ('width_cm', 'height_cm')
    readonly_fields = ('created_at', 'updated_at', 'area_cm2', 'area_m2')
    
    fieldsets = (
        (_('معلومات أساسية'), {
            'fields': ('name', 'code')
        }),
        (_('الأبعاد'), {
            'fields': ('width_cm', 'height_cm', 'area_cm2', 'area_m2')
        }),
        (_('الوصف'), {
            'fields': ('description',)
        }),
        (_('الإعدادات'), {
            'fields': ('is_active', 'is_default', 'is_custom_size')
        }),
        (_('معلومات النظام'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
