from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import (
    AccountType,
    ChartOfAccounts,
    AccountingPeriod,
    JournalEntry,
    JournalEntryLine,
    PaymentSyncOperation,
    PaymentSyncLog,
    PartnerTransaction,
    PartnerBalance,
    InvoiceAuditLog,
)
from core.models import SystemSetting


class JournalEntryLineInline(admin.TabularInline):
    """
    عرض بنود القيد المحاسبي ضمن صفحة القيد
    """

    model = JournalEntryLine
    extra = 1
    min_num = 2
    fields = ("account", "debit", "credit", "description")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "account":
            from .models import ChartOfAccounts

            kwargs["queryset"] = ChartOfAccounts.objects.filter(
                is_active=True
            ).order_by("code")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(AccountType)
class AccountTypeAdmin(admin.ModelAdmin):
    """
    إدارة أنواع الحسابات
    """

    list_display = ("name", "nature", "is_active")
    list_filter = ("nature", "is_active")
    search_fields = ("name", "description")
    readonly_fields = ("created_at", "updated_at")


@admin.register(ChartOfAccounts)
class ChartOfAccountsAdmin(admin.ModelAdmin):
    """
    إدارة دليل الحسابات
    """

    list_display = (
        "name",
        "code",
        "account_type",
        "parent",
        "opening_balance",
        "is_active",
    )
    list_filter = ("account_type", "is_active", "is_cash_account", "is_bank_account")
    search_fields = ("name", "code", "description")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("name", "code", "account_type", "parent")}),
        (
            _("الرصيد الافتتاحي"),
            {"fields": ("opening_balance", "opening_balance_date")},
        ),
        (
            _("خصائص الحساب"),
            {"fields": ("is_cash_account", "is_bank_account", "is_active")},
        ),
        (_("معلومات إضافية"), {"fields": ("description",)}),
        (_("معلومات النظام"), {"fields": ("created_at", "updated_at")}),
    )


@admin.register(AccountingPeriod)
class AccountingPeriodAdmin(admin.ModelAdmin):
    """
    إدارة الفترات المحاسبية
    """

    list_display = ("name", "start_date", "end_date", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("name",)
    readonly_fields = ("created_at",)


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    """
    إدارة القيود المحاسبية
    """

    list_display = ("id", "number", "date", "entry_type", "status", "reference")
    list_filter = ("entry_type", "status", "date", "accounting_period")
    search_fields = ("number", "reference", "description")
    readonly_fields = ("number", "created_at", "created_by")
    inlines = [JournalEntryLineInline]
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "number",
                    "date",
                    "entry_type",
                    "accounting_period",
                    "reference",
                )
            },
        ),
        (_("معلومات إضافية"), {"fields": ("description", "status")}),
        (_("معلومات النظام"), {"fields": ("created_at", "created_by")}),
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

    list_display = ("journal_entry", "account", "debit", "credit", "description")
    list_filter = ("journal_entry__date", "account__account_type")
    search_fields = ("journal_entry__reference", "account__name", "description")
    readonly_fields = ("created_at",)
    fieldsets = (
        (None, {"fields": ("journal_entry", "account")}),
        (_("المبالغ"), {"fields": ("debit", "credit")}),
        (_("معلومات إضافية"), {"fields": ("description", "cost_center", "project")}),
        (_("معلومات النظام"), {"fields": ("created_at",)}),
    )


@admin.register(PaymentSyncOperation)
class PaymentSyncOperationAdmin(admin.ModelAdmin):
    """
    إدارة عمليات تزامن المدفوعات
    """

    list_display = ("operation_id", "operation_type", "status", "created_at")
    list_filter = ("operation_type", "status", "created_at")
    search_fields = ("operation_id", "source_model", "target_model")
    readonly_fields = ("operation_id", "created_at", "completed_at")


@admin.register(PaymentSyncLog)
class PaymentSyncLogAdmin(admin.ModelAdmin):
    """
    إدارة سجلات تزامن المدفوعات
    """

    list_display = (
        "sync_operation",
        "action",
        "target_model",
        "success",
        "executed_at",
    )
    list_filter = ("action", "success", "executed_at")
    search_fields = ("target_model", "error_message")
    readonly_fields = ("executed_at", "execution_time")


# إدارة معاملات الشريك
@admin.register(PartnerTransaction)
class PartnerTransactionAdmin(admin.ModelAdmin):
    """
    إدارة معاملات الشريك في Django Admin
    """
    
    list_display = [
        'id', 'transaction_type_display', 'partner_name', 
        'amount_display', 'transaction_date', 'status_display', 
        'created_by', 'created_at'
    ]
    
    list_filter = [
        'transaction_type', 'status', 'transaction_date', 
        'contribution_type', 'withdrawal_type', 'created_at'
    ]
    
    search_fields = [
        'description', 'partner_account__name', 'cash_account__name',
        'created_by__username', 'created_by__first_name', 'created_by__last_name'
    ]
    
    readonly_fields = [
        'created_at', 'updated_at', 'approved_at', 'journal_entry_link'
    ]
    
    fieldsets = (
        (_('معلومات المعاملة'), {
            'fields': (
                'transaction_type', 'partner_account', 'cash_account', 
                'amount', 'transaction_date'
            )
        }),
        (_('تفاصيل المعاملة'), {
            'fields': (
                'contribution_type', 'withdrawal_type', 
                'description', 'notes'
            )
        }),
        (_('الحالة والموافقات'), {
            'fields': (
                'status', 'created_by', 'approved_by', 
                'approved_at'
            )
        }),
        (_('القيد المحاسبي'), {
            'fields': ('journal_entry_link',),
            'classes': ('collapse',)
        }),
        (_('معلومات التدقيق'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    date_hierarchy = 'transaction_date'
    ordering = ['-transaction_date', '-created_at']
    
    def transaction_type_display(self, obj):
        """عرض نوع المعاملة مع أيقونة"""
        if obj.transaction_type == 'contribution':
            return format_html(
                '<span style="color: green;"><i class="fas fa-plus-circle"></i> {}</span>',
                obj.get_transaction_type_display()
            )
        else:
            return format_html(
                '<span style="color: orange;"><i class="fas fa-minus-circle"></i> {}</span>',
                obj.get_transaction_type_display()
            )
    transaction_type_display.short_description = _('نوع المعاملة')
    transaction_type_display.admin_order_field = 'transaction_type'
    
    def partner_name(self, obj):
        """اسم الشريك"""
        return obj.partner_account.name if obj.partner_account else '-'
    partner_name.short_description = _('الشريك')
    partner_name.admin_order_field = 'partner_account__name'
    
    def amount_display(self, obj):
        """عرض المبلغ مع تنسيق"""
        color = 'green' if obj.transaction_type == 'contribution' else 'orange'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{} {}</span>',
            color, obj.amount, SystemSetting.get_currency_symbol()
        )
    amount_display.short_description = _('المبلغ')
    amount_display.admin_order_field = 'amount'
    
    def status_display(self, obj):
        """عرض الحالة مع ألوان"""
        colors = {
            'pending': '#ffc107',
            'approved': '#17a2b8',
            'completed': '#28a745',
            'cancelled': '#dc3545'
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 10px; font-size: 0.8em;">{}</span>',
            color, obj.get_status_display()
        )
    status_display.short_description = _('الحالة')
    status_display.admin_order_field = 'status'
    
    def journal_entry_link(self, obj):
        """رابط للقيد المحاسبي"""
        if obj.journal_entry:
            url = reverse('admin:financial_journalentry_change', args=[obj.journal_entry.id])
            return format_html(
                '<a href="{}" target="_blank">القيد رقم {} <i class="fas fa-external-link-alt"></i></a>',
                url, obj.journal_entry.number
            )
        return '-'
    journal_entry_link.short_description = _('القيد المحاسبي')
    
    def get_queryset(self, request):
        """تحسين الاستعلام"""
        return super().get_queryset(request).select_related(
            'partner_account', 'cash_account', 'created_by', 
            'approved_by', 'journal_entry'
        )
    
    def save_model(self, request, obj, form, change):
        """حفظ النموذج مع تحديث المنشئ"""
        if not change:  # إنشاء جديد
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(PartnerBalance)
class PartnerBalanceAdmin(admin.ModelAdmin):
    """
    إدارة أرصدة الشركاء في Django Admin
    """
    
    list_display = [
        'partner_name', 'total_contributions_display', 
        'total_withdrawals_display', 'current_balance_display',
        'last_transaction_date', 'updated_at'
    ]
    
    readonly_fields = [
        'total_contributions', 'total_withdrawals', 'current_balance',
        'last_transaction_date', 'updated_at'
    ]
    
    search_fields = ['partner_account__name']
    
    def partner_name(self, obj):
        """اسم الشريك"""
        return obj.partner_account.name if obj.partner_account else '-'
    partner_name.short_description = _('الشريك')
    partner_name.admin_order_field = 'partner_account__name'
    
    def total_contributions_display(self, obj):
        """عرض إجمالي المساهمات"""
        return format_html(
            '<span style="color: green; font-weight: bold;">{} {}</span>',
            obj.total_contributions, SystemSetting.get_currency_symbol()
        )
    total_contributions_display.short_description = _('إجمالي المساهمات')
    total_contributions_display.admin_order_field = 'total_contributions'
    
    def total_withdrawals_display(self, obj):
        """عرض إجمالي السحوبات"""
        return format_html(
            '<span style="color: orange; font-weight: bold;">{} {}</span>',
            obj.total_withdrawals, SystemSetting.get_currency_symbol()
        )
    total_withdrawals_display.short_description = _('إجمالي السحوبات')
    total_withdrawals_display.admin_order_field = 'total_withdrawals'
    
    def current_balance_display(self, obj):
        """عرض الرصيد الحالي"""
        color = 'green' if obj.current_balance >= 0 else 'red'
        return format_html(
            '<span style="color: {}; font-weight: bold; font-size: 1.1em;">{} {}</span>',
            color, obj.current_balance, SystemSetting.get_currency_symbol()
        )
    current_balance_display.short_description = _('الرصيد الحالي')
    current_balance_display.admin_order_field = 'current_balance'
    
    def get_queryset(self, request):
        """تحسين الاستعلام"""
        return super().get_queryset(request).select_related('partner_account')
    
    def has_add_permission(self, request):
        """منع الإضافة اليدوية - يتم الإنشاء تلقائياً"""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """منع الحذف"""
        return False
    
    actions = ['update_balances']
    
    def update_balances(self, request, queryset):
        """إجراء لتحديث الأرصدة"""
        updated_count = 0
        for balance in queryset:
            balance.update_balance()
            updated_count += 1
        
        self.message_user(
            request,
            f'تم تحديث {updated_count} رصيد بنجاح.'
        )
    update_balances.short_description = _('تحديث الأرصدة المحددة')


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
            icon = "="
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
