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
# try:
#     from .bank_reconciliation import BankReconciliation, BankReconciliationItem
# except Exception:
#     BankReconciliation = BankReconciliationItem = None
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
    FinancialTransaction = None
    ExpenseTransaction = None
    IncomeTransaction = None
    TransactionAttachment = None

from .fiscal_year import FiscalYear
from .currency import Currency, ExchangeRate
from .tax import (
    TaxJurisdiction,
    TaxCode,
    TaxRateHistory,
    TaxRule,
    TaxRuleCondition,
    TaxRuleEvaluationLog,
    TaxAccountMapping,
    TaxRegistration,
    TaxExemptionCertificate,
    TaxCalculationLine,
    TaxEvent,
    TaxDeterminationAudit,
    TaxReversal,
)
from .revenue_recognition import RevenueRecognitionPolicy, RevenueRecognitionSchedule, RevenueRecognitionScheduleLine, RevenueRecognitionEntry, RevenueRecognitionAccountMapping, RevenueRecognitionReversal
from .approval import EnterpriseApprovalRule, EnterpriseApprovalRequest, EnterpriseApprovalStep, EnterpriseApprovalAuditLog

__all__ = [
    # النماذج الأساسية
    "AccountType",
    "ChartOfAccounts",
    "AccountGroup",
    "FiscalYear",
    "AccountingPeriod",
    "JournalEntry",
    "JournalEntryLine",
    "OpeningBalanceBatch",
    "OpeningBalanceLine",
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
