from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import (
    AccountType, ChartOfAccounts,
    AccountingPeriod, JournalEntry, JournalEntryLine,
    PaymentSyncOperation, PaymentSyncLog
)


class JournalEntryLineInline(admin.TabularInline):
    """
    عرض بنود القيد المحاسبي ضمن صفحة القيد
    """
    model = JournalEntryLine
    extra = 1
    min_num = 2
    fields = ('account', 'debit', 'credit', 'description')
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "account":
            from .models import ChartOfAccounts
            kwargs["queryset"] = ChartOfAccounts.objects.filter(is_active=True).order_by('code')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(AccountType)
class AccountTypeAdmin(admin.ModelAdmin):
    """
    إدارة أنواع الحسابات
    """
    list_display = ('name', 'nature', 'is_active')
    list_filter = ('nature', 'is_active')
    search_fields = ('name', 'description')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ChartOfAccounts)
class ChartOfAccountsAdmin(admin.ModelAdmin):
    """
    إدارة دليل الحسابات
    """
    list_display = ('name', 'code', 'account_type', 'parent', 'opening_balance', 'is_active')
    list_filter = ('account_type', 'is_active', 'is_cash_account', 'is_bank_account')
    search_fields = ('name', 'code', 'description')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (None, {'fields': ('name', 'code', 'account_type', 'parent')}),
        (_('الرصيد الافتتاحي'), {'fields': ('opening_balance', 'opening_balance_date')}),
        (_('خصائص الحساب'), {'fields': ('is_cash_account', 'is_bank_account', 'is_active')}),
        (_('معلومات إضافية'), {'fields': ('description',)}),
        (_('معلومات النظام'), {'fields': ('created_at', 'updated_at')}),
    )


@admin.register(AccountingPeriod)
class AccountingPeriodAdmin(admin.ModelAdmin):
    """
    إدارة الفترات المحاسبية
    """
    list_display = ('name', 'start_date', 'end_date', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('name',)
    readonly_fields = ('created_at',)


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    """
    إدارة القيود المحاسبية
    """
    list_display = ('id', 'number', 'date', 'entry_type', 'status', 'reference')
    list_filter = ('entry_type', 'status', 'date', 'accounting_period')
    search_fields = ('number', 'reference', 'description')
    readonly_fields = ('number', 'created_at', 'created_by')
    inlines = [JournalEntryLineInline]
    fieldsets = (
        (None, {'fields': ('number', 'date', 'entry_type', 'accounting_period', 'reference')}),
        (_('معلومات إضافية'), {'fields': ('description', 'status')}),
        (_('معلومات النظام'), {'fields': ('created_at', 'created_by')}),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:  # إذا كان إنشاء جديد
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(JournalEntryLine)
class JournalEntryLineAdmin(admin.ModelAdmin):
    """
    إدارة بنود القيود المحاسبية
    """
    list_display = ('journal_entry', 'account', 'debit', 'credit', 'description')
    list_filter = ('journal_entry__date', 'account__account_type')
    search_fields = ('journal_entry__reference', 'account__name', 'description')
    readonly_fields = ('created_at',)
    fieldsets = (
        (None, {'fields': ('journal_entry', 'account')}),
        (_('المبالغ'), {'fields': ('debit', 'credit')}),
        (_('معلومات إضافية'), {'fields': ('description', 'cost_center', 'project')}),
        (_('معلومات النظام'), {'fields': ('created_at',)}),
    )


@admin.register(PaymentSyncOperation)
class PaymentSyncOperationAdmin(admin.ModelAdmin):
    """
    إدارة عمليات تزامن المدفوعات
    """
    list_display = ('operation_id', 'operation_type', 'status', 'created_at')
    list_filter = ('operation_type', 'status', 'created_at')
    search_fields = ('operation_id', 'source_model', 'target_model')
    readonly_fields = ('operation_id', 'created_at', 'completed_at')


@admin.register(PaymentSyncLog)
class PaymentSyncLogAdmin(admin.ModelAdmin):
    """
    إدارة سجلات تزامن المدفوعات
    """
    list_display = ('sync_operation', 'action', 'target_model', 'success', 'executed_at')
    list_filter = ('action', 'success', 'executed_at')
    search_fields = ('target_model', 'error_message')
    readonly_fields = ('executed_at', 'execution_time')
