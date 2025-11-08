# financial/views.py
# ملف التجميع الرئيسي - يستورد جميع العروض من الملفات المتخصصة
# هذا الملف مستخدم في urls.py فقط

# تم نقل جميع دوال الحسابات إلى financial/views/account_views.py
from .views.account_views import (
    get_all_active_accounts,
    get_accounts_by_category,
    get_bank_accounts,
    get_next_available_code,
    cash_and_bank_accounts_list,
    chart_of_accounts_list,
    chart_tree_api,
    chart_of_accounts_create,
    chart_of_accounts_detail,
    chart_of_accounts_delete,
    account_types_list,
    account_types_detail,
    account_types_create,
    account_types_edit,
    account_types_delete,
    # account_list,  # لا يوجد - استخدم chart_of_accounts_list
    get_account_transactions,
    # معاملات الشريك
    partner_dashboard,
    partner_transactions_list,
    partner_transaction_detail,
    create_contribution,
    create_withdrawal,
    get_partner_balance,
    get_account_analytics,
    # account_detail,  # تم حذفه - مكرر مع chart_of_accounts_detail
    # account_create,  # لا يوجد - استخدم chart_of_accounts_create
    account_edit,
    # account_transactions,  # تم حذفه - غير مستخدم
    # account_delete,  # تم حذفه - مكرر مع chart_of_accounts_delete
    bank_reconciliation_list,
    bank_reconciliation_create,
)

# تم نقل جميع دوال القيود والمعاملات إلى financial/views/transaction_views.py
from .views.transaction_views import (
    journal_entries_list,
    journal_entries_create,
    journal_entries_detail,
    journal_entries_edit,
    journal_entries_delete,
    journal_entries_post,
    transaction_list,
    transaction_detail,
    # transaction_create,  # تم حذفه - تحت التطوير
    # transaction_edit,  # تم حذفه - تحت التطوير
    # transaction_delete,  # تم حذفه - تحت التطوير
)

# تم نقل دوال الفترات المحاسبية إلى financial/views/period_views.py
from .views.period_views import (
    accounting_periods_list,
    accounting_periods_create,
    accounting_periods_edit,
    accounting_periods_close,
)

# تم نقل دوال المصروفات والإيرادات إلى financial/views/income_views.py
from .views.income_views import (
    expense_list,
    expense_detail,
    expense_create,
    expense_edit,
    expense_mark_paid,
    expense_cancel,
    income_list,
    income_detail,
    income_mark_received,
    income_cancel,
)

# تم نقل APIs والتقارير إلى financial/views/api_views.py
from .views.api_views import (
    api_expense_accounts,
    api_payment_accounts,
    api_income_accounts,
    export_transactions,
    ledger_report,
    balance_sheet,
)