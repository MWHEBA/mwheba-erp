from django.urls import path
from . import views

app_name = "financial"

urlpatterns = [
    # ============== النظام المحاسبي الموحد ==============
    # قائمة الخزن    # الحسابات النقدية والبنكية
    path(
        "cash-accounts/",
        views.cash_and_bank_accounts_list,
        name="cash_and_bank_accounts_list",
    ),
    # alias للاسم القديم المستخدم في بعض القوالب/المناظر
    path(
        "cash-accounts-list/",
        views.cash_and_bank_accounts_list,
        name="cash_accounts_list",
    ),
    # صفحة حركات الحساب النقدي
    path(
        "cash-accounts/<int:pk>/movements/",
        views.cash_account_movements,
        name="cash_account_movements",
    ),
    # نظام تتبع حركات الخزن
    # دليل الحسابات (النظام الجديد) - شجرة الحسابات الكاملة
    path("accounts/", views.chart_of_accounts_list, name="chart_of_accounts_list"),
    # alias للاسم القديم المستخدم في بعض القوالب/المناظر
    path("accounts-list/", views.chart_of_accounts_list, name="account_list"),
    path("accounts/tree-api/", views.chart_tree_api, name="chart_tree_api"),
    path(
        "accounts/create/",
        views.chart_of_accounts_create,
        name="chart_of_accounts_create",
    ),
    # alias للاسم القديم المستخدم في بعض القوالب
    path(
        "accounts/create-account/",
        views.chart_of_accounts_create,
        name="account_create",
    ),
    path("accounts/<int:pk>/", views.chart_of_accounts_detail, name="account_detail"),
    # path('accounts/<int:account_id>/approve-all-pending/', views.approve_all_pending_entries, name='approve_all_pending_entries'),
    path("accounts/<int:pk>/edit/", views.account_edit, name="account_edit"),
    path(
        "accounts/<int:pk>/delete/",
        views.chart_of_accounts_delete,
        name="account_delete",
    ),
    path("account-types/", views.account_types_list, name="account_types_list"),
    path(
        "account-types/create/", views.account_types_create, name="account_types_create"
    ),
    path(
        "account-types/<int:pk>/",
        views.account_types_detail,
        name="account_type_detail",
    ),
    path(
        "account-types/<int:pk>/edit/",
        views.account_types_edit,
        name="account_types_edit",
    ),
    path(
        "account-types/<int:pk>/delete/",
        views.account_types_delete,
        name="account_types_delete",
    ),
    # APIs للقيود المحاسبية (تم حذفها لتبسيط النظام)
    # APIs لإدارة تزامن المدفوعات (معطلة مؤقتاً)
    # path(
    #     "api/payment-sync/retry-failed/",
    #     views.payment_sync_retry_failed_api,
    #     name="payment_sync_retry_failed_api",
    # ),
    # path(
    #     "api/payment-sync/resolve-errors/",
    #     views.payment_sync_resolve_errors_api,
    #     name="payment_sync_resolve_errors_api",
    # ),
    # path(
    #     "api/payment-sync/process-all/",
    #     views.payment_sync_process_all_api,
    #     name="payment_sync_process_all_api",
    # ),
    # path(
    #     "api/payment-sync/reset-all/",
    #     views.payment_sync_reset_all_api,
    #     name="payment_sync_reset_all_api",
    # ),
    # القيود المحاسبية
    path("journal-entries/", views.journal_entries_list, name="journal_entries_list"),
    path(
        "journal-entries/create/",
        views.journal_entries_create,
        name="journal_entries_create",
    ),
    path(
        "journal-entries/<int:pk>/",
        views.journal_entries_detail,
        name="journal_entries_detail",
    ),
    path(
        "journal-entries/<int:pk>/edit/",
        views.journal_entries_edit,
        name="journal_entries_edit",
    ),
    path(
        "journal-entries/<int:pk>/delete/",
        views.journal_entry_delete,
        name="journal_entry_delete",
    ),
    path(
        "journal-entries/<int:pk>/post/",
        views.journal_entries_post,
        name="journal_entries_post",
    ),
    # الفترات المحاسبية
    path(
        "accounting-periods/",
        views.accounting_periods_list,
        name="accounting_periods_list",
    ),
    path(
        "accounting-periods/create/",
        views.accounting_periods_create,
        name="accounting_periods_create",
    ),
    path(
        "accounting-periods/<int:pk>/edit/",
        views.accounting_periods_edit,
        name="accounting_periods_edit",
    ),
    path(
        "accounting-periods/<int:pk>/close/",
        views.accounting_periods_close,
        name="accounting_periods_close",
    ),
    # المصروفات والإيرادات
    path("expenses/", views.expense_list, name="expense_list"),
    path("expenses/create/", views.expense_create, name="expense_create"),  # AJAX only
    path("expenses/<int:pk>/", views.expense_detail, name="expense_detail"),
    path("expenses/<int:pk>/edit/", views.expense_edit, name="expense_edit"),
    path("expenses/<int:pk>/cancel/", views.expense_cancel, name="expense_cancel"),  # بدلاً من delete
    path("expenses/<int:pk>/mark-paid/", views.expense_mark_paid, name="expense_mark_paid"),  # بدلاً من post
    path("incomes/", views.income_list, name="income_list"),
    path("incomes/create/", views.expense_create_enhanced, name="income_create"),  # استخدام دالة إنشاء محسنة
    path("incomes/<int:pk>/", views.income_detail, name="income_detail"),
    path("incomes/<int:pk>/cancel/", views.income_cancel, name="income_cancel"),  # بدلاً من delete
    path("incomes/<int:pk>/mark-received/", views.income_mark_received, name="income_mark_received"),  # بدلاً من post
    # المعاملات العامة
    path("transactions/", views.transaction_list, name="transaction_list"),
    path("transactions/<int:pk>/", views.transaction_detail, name="transaction_detail"),
    # API للمودالز السريعة
    path("api/expense-accounts/", views.api_expense_accounts, name="api_expense_accounts"),
    path("api/payment-accounts/", views.api_payment_accounts, name="api_payment_accounts"),
    path("api/income-accounts/", views.api_income_accounts, name="api_income_accounts"),
    # الأرصدة المحسنة
    path(
        "enhanced-balances/",
        views.enhanced_balances_list,
        name="enhanced_balances_list",
    ),
    path(
        "enhanced-balances/refresh/",
        views.enhanced_balances_refresh,
        name="enhanced_balances_refresh",
    ),
    path(
        "enhanced-balances/audit/",
        views.enhanced_balances_audit,
        name="enhanced_balances_audit",
    ),
    # تزامن المدفوعات - تم حذف dashboard (مجرد عرض بدون وظائف فعلية)
    path(
        "payment-sync/operations/",
        views.payment_sync_operations,
        name="payment_sync_operations",
    ),
    path("payment-sync/logs/", views.payment_sync_logs, name="payment_sync_logs"),
    # التقارير المحاسبية المتقدمة
    path("reports/ledger/", views.ledger_report, name="ledger_report"),
    path(
        "reports/trial-balance/",
        views.trial_balance_report,
        name="trial_balance_report",
    ),
    # تقارير العمليات
    path("reports/sales/", views.sales_report, name="sales_report"),
    path("reports/purchases/", views.purchases_report, name="purchases_report"),
    path("reports/inventory/", views.inventory_report, name="inventory_report"),
    # النسخ الاحتياطي والصيانة
    path("backup/general/", views.general_backup, name="general_backup"),
    path(
        "backup/financial/",
        views.financial_backup_advanced,
        name="financial_backup_advanced",
    ),
    path("backup/restore/", views.restore_data, name="restore_data"),
    path(
        "maintenance/integrity-check/",
        views.data_integrity_check,
        name="data_integrity_check",
    ),
    # التقارير المالية الأساسية
    path("reports/balance-sheet/", views.balance_sheet, name="balance_sheet"),
    path("reports/income-statement/", views.income_statement, name="income_statement"),
    path("reports/analytics/", views.financial_analytics, name="financial_analytics"),
    # إدارة الدفعات المحسنة
    path("payments/list/", views.payment_list, name="payment_list"),
    path(
        "payments/<str:payment_type>/<int:payment_id>/",
        views.payment_detail,
        name="payment_detail",
    ),
    path(
        "payments/<str:payment_type>/<int:payment_id>/edit/",
        views.payment_edit,
        name="payment_edit",
    ),
    path(
        "payments/<str:payment_type>/<int:payment_id>/unpost/",
        views.payment_unpost,
        name="payment_unpost",
    ),
    path(
        "payments/<str:payment_type>/<int:payment_id>/delete/",
        views.payment_delete,
        name="payment_delete",
    ),
    path(
        "payments/<str:payment_type>/<int:payment_id>/history/",
        views.payment_history,
        name="payment_history",
    ),
    # سجل التدقيق
    path("audit-trail/", views.audit_trail_list, name="audit_trail_list"),
    path("audit-trail/cleanup/", views.audit_trail_cleanup, name="audit_trail_cleanup"),
    # معاملات الشريك
    path("partner/", views.partner_dashboard, name="partner_dashboard"),
    path("partner/transactions/", views.partner_transactions_list, name="partner_transactions_list"),
    path("partner/transactions/<int:pk>/", views.partner_transaction_detail, name="partner_transaction_detail"),
    path("partner/contribute/", views.create_contribution, name="create_contribution"),
    path("partner/withdraw/", views.create_withdrawal, name="create_withdrawal"),
    # API endpoints للشراكة
    path("api/partner/balance/", views.get_partner_balance, name="get_partner_balance"),
    # API endpoints
    path(
        "api/journal-entry/<int:journal_entry_id>/summary/",
        views.journal_entry_summary_api,
        name="journal_entry_summary_api",
    ),
]
