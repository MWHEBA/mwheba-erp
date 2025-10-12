from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from sale.models import Sale, SaleItem, SalePayment, SaleReturn, SaleReturnItem


class SaleItemInline(admin.TabularInline):
    """
    عرض بنود الفاتورة ضمن صفحة الفاتورة
    """
    model = SaleItem
    extra = 1
    min_num = 1
    fields = ('product', 'quantity', 'unit_price', 'discount', 'total')
    readonly_fields = ('total',)


class SalePaymentInline(admin.TabularInline):
    """
    عرض مدفوعات الفاتورة ضمن صفحة الفاتورة
    """
    model = SalePayment
    extra = 0
    can_delete = False
    fields = ('payment_date', 'amount', 'payment_method', 'reference_number', 'created_by')
    readonly_fields = ('created_by',)
    
    def has_add_permission(self, request, obj=None):
        # يمكن إضافة مدفوعات فقط للفواتير المحفوظة
        return obj is not None and obj.id is not None


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    """
    إدارة فواتير المبيعات
    """
    list_display = ('number', 'date', 'customer', 'warehouse', 'total', 'payment_method', 
                    'payment_status', 'amount_paid', 'amount_due')
    list_filter = ('date', 'warehouse', 'payment_method', 'payment_status')
    search_fields = ('number', 'customer__name', 'notes')
    readonly_fields = ('subtotal', 'total', 'payment_status', 'created_at', 'updated_at', 'created_by')
    inlines = [SaleItemInline, SalePaymentInline]
    fieldsets = (
        (None, {'fields': ('number', 'date', 'customer', 'warehouse')}),
        (_('المعلومات المالية'), {'fields': ('subtotal', 'discount', 'tax', 'total', 'payment_method', 'payment_status')}),
        (_('معلومات إضافية'), {'fields': ('notes',)}),
        (_('معلومات النظام'), {'fields': ('created_at', 'updated_at', 'created_by')}),
    )
    
    def amount_paid(self, obj):
        return obj.amount_paid
    amount_paid.short_description = _('المبلغ المدفوع')
    
    def amount_due(self, obj):
        return obj.amount_due
    amount_due.short_description = _('المبلغ المتبقي')
    
    def save_model(self, request, obj, form, change):
        if not change:  # إذا كان إنشاء جديد
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
    
    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        
        for instance in instances:
            # تعيين المنشئ للمدفوعات الجديدة
            if isinstance(instance, SalePayment) and not instance.pk:
                instance.created_by = request.user
            instance.save()
        
        # حذف العناصر المحذوفة
        for obj in formset.deleted_objects:
            obj.delete()
        
        formset.save_m2m()
        
        # إعادة حساب إجمالي الفاتورة بعد تحديث العناصر
        if formset.model == SaleItem:
            self.update_sale_totals(form.instance)
    
    def update_sale_totals(self, sale):
        """
        تحديث إجمالي الفاتورة بناءً على بنودها
        """
        from django.db.models import Sum
        
        items_total = sale.items.aggregate(total=Sum('total'))['total'] or 0
        
        sale.subtotal = items_total
        sale.total = sale.subtotal - sale.discount + sale.tax
        sale.save(update_fields=['subtotal', 'total'])


class SaleReturnItemInline(admin.TabularInline):
    """
    عرض بنود مرتجع المبيعات ضمن صفحة المرتجع
    """
    model = SaleReturnItem
    extra = 1
    min_num = 1
    fields = ('sale_item', 'product', 'quantity', 'unit_price', 'discount', 'total', 'reason')
    readonly_fields = ('product', 'total')


@admin.register(SaleReturn)
class SaleReturnAdmin(admin.ModelAdmin):
    """
    إدارة مرتجعات المبيعات
    """
    list_display = ('number', 'date', 'sale', 'warehouse', 'total', 'status')
    list_filter = ('date', 'status', 'warehouse')
    search_fields = ('number', 'sale__number', 'notes')
    readonly_fields = ('created_at', 'updated_at', 'created_by')
    inlines = [SaleReturnItemInline]
    fieldsets = (
        (None, {'fields': ('number', 'date', 'sale', 'warehouse', 'status')}),
        (_('المعلومات المالية'), {'fields': ('subtotal', 'discount', 'tax', 'total')}),
        (_('معلومات إضافية'), {'fields': ('notes',)}),
        (_('معلومات النظام'), {'fields': ('created_at', 'updated_at', 'created_by')}),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:  # إذا كان إنشاء جديد
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(SalePayment)
class SalePaymentAdmin(admin.ModelAdmin):
    """
    إدارة مدفوعات الفواتير
    """
    list_display = ('sale', 'amount', 'payment_date', 'payment_method', 'reference_number')
    list_filter = ('payment_date', 'payment_method')
    search_fields = ('sale__number', 'reference_number')
    readonly_fields = ('created_at', 'created_by')
    
    def save_model(self, request, obj, form, change):
        if not change:  # إذا كان إنشاء جديد
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
