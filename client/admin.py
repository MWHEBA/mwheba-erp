from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import Customer, CustomerPayment


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    """
    إعدادات عرض نموذج العميل في لوحة الإدارة
    """
    list_display = ('name', 'code', 'phone', 'email', 'credit_limit', 'balance', 'available_credit', 'is_active')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'code', 'phone', 'email', 'tax_number')
    readonly_fields = ('balance', 'created_at', 'updated_at', 'created_by')
    fieldsets = (
        (None, {'fields': ('name', 'code', 'phone', 'email', 'address')}),
        (_('المعلومات المالية'), {'fields': ('credit_limit', 'balance')}),
        (_('معلومات إضافية'), {'fields': ('tax_number', 'is_active', 'notes')}),
        (_('معلومات النظام'), {'fields': ('created_at', 'updated_at', 'created_by')}),
    )
    
    def available_credit(self, obj):
        return obj.available_credit
    available_credit.short_description = _('الرصيد المتاح')
    
    def save_model(self, request, obj, form, change):
        if not change:  # إذا كان إنشاء جديد
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(CustomerPayment)
class CustomerPaymentAdmin(admin.ModelAdmin):
    """
    إعدادات عرض نموذج مدفوعات العميل في لوحة الإدارة
    """
    list_display = ('customer', 'amount', 'payment_date', 'payment_method', 'reference_number')
    list_filter = ('payment_date', 'payment_method')
    search_fields = ('customer__name', 'reference_number', 'notes')
    raw_id_fields = ('customer',)
    readonly_fields = ('created_at', 'created_by')
    fieldsets = (
        (None, {'fields': ('customer', 'amount', 'payment_date', 'payment_method')}),
        (_('معلومات إضافية'), {'fields': ('reference_number', 'notes')}),
        (_('معلومات النظام'), {'fields': ('created_at', 'created_by')}),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:  # إذا كان إنشاء جديد
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
