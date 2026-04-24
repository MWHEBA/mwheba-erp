# استيراد النماذج الجديدة
from .chart_of_accounts import AccountType, ChartOfAccounts, AccountGroup
from .journal_entry import (
    AccountingPeriod,
    JournalEntry,
    JournalEntryLine,
    JournalEntryTemplate,
    JournalEntryTemplateLine,
)
from .validation_audit_log import ValidationAuditLog

from .enhanced_balance import (
    BalanceSnapshot,
    AccountBalanceCache,
    BalanceAuditLog,
    BalanceReconciliation,
)
from .payment_sync import (
    PaymentSyncOperation,
    PaymentSyncLog,
    PaymentSyncRule,
    PaymentSyncError,
)
from .bank_reconciliation import BankReconciliation, BankReconciliationItem
from .categories import FinancialCategory, CategoryBudget, FinancialSubcategory
from .audit_trail import AuditTrail, PaymentAuditMixin
from .invoice_audit_log import InvoiceAuditLog
from .partner_transactions import PartnerTransaction, PartnerBalance
from .partner_settings import PartnerSettings, PartnerPermission, PartnerAuditLog

# استيراد آمن للنماذج الاختيارية
try:
    from .transactions import (
        FinancialTransaction,
        ExpenseTransaction,
        IncomeTransaction,
        TransactionAttachment,
    )
except Exception:
    # النماذج غير متوفرة في قاعدة البيانات بعد
    FinancialTransaction = None
    ExpenseTransaction = None
    IncomeTransaction = None
    TransactionAttachment = None

__all__ = [
    # النماذج الأساسية
    "AccountType",
    "ChartOfAccounts",
    "AccountGroup",
    "AccountingPeriod",
    "JournalEntry",
    "JournalEntryLine",
    "JournalEntryTemplate",
    "JournalEntryTemplateLine",
    # نموذج تدقيق التحقق من المعاملات المالية
    "ValidationAuditLog",
    # نماذج الأرصدة المحسنة
    "BalanceSnapshot",
    "AccountBalanceCache",
    "BalanceAuditLog",
    "BalanceReconciliation",
    # نماذج تزامن المدفوعات
    "PaymentSyncOperation",
    "PaymentSyncLog",
    "PaymentSyncRule",
    "PaymentSyncError",
    # نماذج التسوية البنكية
    "BankReconciliation",
    "BankReconciliationItem",
    # نماذج التصنيفات والميزانيات
    "FinancialCategory",
    "CategoryBudget",
    "FinancialSubcategory",
    # نماذج التدقيق
    "AuditTrail",
    "PaymentAuditMixin",
    "InvoiceAuditLog",
    # نماذج معاملات الشريك
    "PartnerTransaction",
    "PartnerBalance",
    "PartnerSettings",
    "PartnerPermission",
    "PartnerAuditLog",
    # نماذج المعاملات المحسنة
    "FinancialTransaction",
    "ExpenseTransaction",
    "IncomeTransaction",
    "TransactionAttachment",
]
