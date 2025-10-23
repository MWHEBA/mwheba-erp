from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Count, Avg
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.contenttypes.models import ContentType
from datetime import date, datetime, timedelta
from decimal import Decimal
from django.db import models
import json

# استيراد النماذج والخدمات الجديدة
from .forms.expense_forms import ExpenseForm, ExpenseEditForm, ExpenseFilterForm
from .forms.income_forms import IncomeForm, IncomeEditForm, IncomeFilterForm
from .services.expense_income_service import ExpenseIncomeService

# تم نقل جميع الدوال إلى الملفات المتخصصة

# استيراد النماذج الأساسية (موجودة بالتأكيد)
from .models import (
    AccountType,
    ChartOfAccounts,
    AccountingPeriod,
    JournalEntry,
    JournalEntryLine,
)

# استيراد النماذج الاختيارية
try:
    from .models import (
        AccountGroup,
        JournalEntryTemplate,
        JournalEntryTemplateLine,
        BalanceSnapshot,
        AccountBalanceCache,
        BalanceAuditLog,
        PaymentSyncOperation,
        PaymentSyncLog,
    )
except ImportError:
    # في حالة عدم توفر بعض النماذج الاختيارية
    AccountGroup = None
    JournalEntryTemplate = None
    JournalEntryTemplateLine = None
    BalanceSnapshot = None
    AccountBalanceCache = None
    BalanceAuditLog = None
    PaymentSyncOperation = None
    PaymentSyncLog = None


# استيراد النماذج القديمة للتوافق (اختيارية)
try:
    from .models import Transaction, Account, TransactionLine, TransactionForm
except ImportError:
    # في حالة عدم توفر النماذج القديمة، إنشاء نماذج وهمية
    class Transaction:
        objects = type(
            "MockManager",
            (),
            {
                "filter": lambda *args, **kwargs: type(
                    "MockQuerySet",
                    (),
                    {
                        "order_by": lambda *args: [],
                        "aggregate": lambda *args: {"amount__sum": 0, "total": 0},
                        "count": lambda: 0,
                        "exists": lambda: False,
                    },
                )(),
                "create": lambda *args, **kwargs: None,
                "all": lambda: type(
                    "MockQuerySet", (), {"order_by": lambda *args: []}
                )(),
            },
        )()

    Account = ChartOfAccounts  # استخدام النموذج الجديد
    TransactionLine = JournalEntryLine
    TransactionForm = None


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
    account_list,
    get_account_transactions,
    # معاملات الشريك
    partner_dashboard,
    partner_transactions_list,
    partner_transaction_detail,
    create_contribution,
    create_withdrawal,
    get_partner_balance,
    get_account_analytics,
    account_detail,
    account_create,
    account_edit,
    account_transactions,
    account_delete,
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
    transaction_create,
    transaction_edit,
    transaction_delete,
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