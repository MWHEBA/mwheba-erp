import logging
from django.db import transaction
from django.apps import apps

logger = logging.getLogger(__name__)


class SystemResetService:
    """
    خدمة تفريغ الحركات والمعاملات التجريبية بنسبة 100%
    مع الحفاظ التام على الإعدادات، المستخدمين، شجرة الحسابات، العملات، والمخازن.
    """

    @classmethod
    @transaction.atomic
    def reset_test_transactions(cls, reset_sequences=True, reset_balances=True):
        """
        تفريغ كافة الحركات والمعاملات الحركية فقط بالترتيب المنطقي لاحترام العلاقات الأجنبية.
        """
        summary = {}

        def safe_delete(app_label, model_name):
            try:
                model = apps.get_model(app_label, model_name)
                if model:
                    count, _ = model.objects.all().delete()
                    summary[f"{app_label}.{model_name}"] = count
                    return count
            except Exception as e:
                logger.warning(f"Could not delete {app_label}.{model_name}: {e}")
                summary[f"{app_label}.{model_name}"] = 0
                return 0

        # =========================================================================
        # 1. دورة المبيعات والعملاء (Sales & Clients Transactions)
        # =========================================================================
        # إشعارات الدائن والمرتجعات
        safe_delete('sale', 'CreditNoteAllocation')
        safe_delete('sale', 'CreditNoteReversal')
        safe_delete('sale', 'CreditNoteAudit')
        safe_delete('sale', 'CreditNoteItem')
        safe_delete('sale', 'CreditNote')

        safe_delete('sale', 'SalesReturnInspection')
        safe_delete('sale', 'ReturnCostTrace')
        safe_delete('sale', 'SalesReturnAudit')
        safe_delete('sale', 'SalesReturnItem')
        safe_delete('sale', 'SalesReturnHeader')
        safe_delete('sale', 'SalesReturn')
        safe_delete('sale', 'ReturnAuthorization')

        # أذون التسليم وأوامر البيع
        safe_delete('sale', 'DeliveryNoteItem')
        safe_delete('sale', 'DeliveryNote')
        safe_delete('sale', 'SalesOrderItem')
        safe_delete('sale', 'SalesOrder')

        # عروض الأسعار
        safe_delete('sale', 'QuotationItem')
        safe_delete('sale', 'Quotation')

        # الفواتير والمدفوعات
        safe_delete('sale', 'SalePayment')
        safe_delete('sale', 'SalesInvoiceItem')
        safe_delete('sale', 'SalesInvoice')
        safe_delete('sale', 'SaleItem')
        safe_delete('sale', 'Sale')
        safe_delete('sale', 'PricingAuditLog')

        # مدفوعات وحركات العملاء
        safe_delete('client', 'CustomerAllocationAudit')
        safe_delete('client', 'CustomerTransaction')
        safe_delete('client', 'CustomerPayment')
        safe_delete('client', 'CustomerCreditStatusHistory')
        safe_delete('client', 'CreditAuditLog')

        # =========================================================================
        # 2. دورة المشتريات والموردين (Purchases & Suppliers Transactions)
        # =========================================================================
        safe_delete('purchase', 'BillLineMatching')
        safe_delete('purchase', 'SupplierBillItem')
        safe_delete('purchase', 'SupplierBill')
        safe_delete('purchase', 'GRNAuditLog')
        safe_delete('purchase', 'GRNPostingLog')
        safe_delete('purchase', 'GoodsReceivedNoteItem')
        safe_delete('purchase', 'GoodsReceivedNote')
        safe_delete('purchase', 'PurchaseOrderItem')
        safe_delete('purchase', 'PurchaseOrder')
        safe_delete('purchase', 'PurchaseReturnItem')
        safe_delete('purchase', 'PurchaseReturn')
        safe_delete('purchase', 'PurchasePayment')
        safe_delete('purchase', 'PurchaseItem')
        safe_delete('purchase', 'Purchase')
        safe_delete('purchase', 'ApprovalRequest')

        # مدفوعات وحركات الموردين
        safe_delete('supplier', 'SupplierAllocationAudit')
        safe_delete('supplier', 'SupplierAdvancePayment')
        safe_delete('supplier', 'SupplierTransaction')

        # =========================================================================
        # 3. حركات المخزن والمخزون والتكاليف (Inventory & Stock Movements)
        # =========================================================================
        safe_delete('product', 'StockLedgerEntry')
        safe_delete('product', 'InventoryCostConsumption')
        safe_delete('product', 'InventoryCostLayer')
        safe_delete('product', 'LandedCostAllocation')
        safe_delete('product', 'LandedCostDocument')
        safe_delete('product', 'InventoryValuationAdjustment')
        safe_delete('product', 'InventoryReservationAudit')
        safe_delete('product', 'InventoryReservation')
        safe_delete('product', 'StockReservation')
        safe_delete('product', 'ReservationFulfillment')
        safe_delete('product', 'BatchConsumption')
        safe_delete('product', 'BatchReservation')
        safe_delete('product', 'InventoryAdjustmentItem')
        safe_delete('product', 'InventoryAdjustment')
        safe_delete('product', 'InventoryMovement')
        safe_delete('product', 'StockMovement')
        safe_delete('product', 'StockTransfer')
        safe_delete('product', 'StockSnapshot')
        safe_delete('product', 'BatchVoucherItem')
        safe_delete('product', 'BatchVoucher')
        safe_delete('product', 'LocationMovement')
        safe_delete('product', 'LocationTask')

        # تصفير كميات المخزون
        try:
            stock_model = apps.get_model('product', 'Stock')
            if stock_model:
                stock_model.objects.all().update(quantity=0, reserved_quantity=0)
        except Exception:
            pass

        # =========================================================================
        # 4. الحسابات والقيود والمالية المركزية (Financials & Ledger Entries)
        # =========================================================================
        # البنوك ومطابقات الحسابات
        safe_delete('financial', 'BankMatchAllocation')
        safe_delete('financial', 'BankReconciliationMatch')
        safe_delete('financial', 'BankStatementLine')
        safe_delete('financial', 'BankStatementBatch')

        # التخصيصات والشركاء
        safe_delete('financial', 'PaymentAllocation')
        safe_delete('financial', 'PartnerAdvanceSettlement')
        safe_delete('financial', 'PartnerTransaction')
        safe_delete('financial', 'PartnerBalance')
        safe_delete('financial', 'PartnerCurrencyBalanceSnapshot')
        safe_delete('financial', 'ReconciliationIssue')

        # الضرائب
        safe_delete('financial', 'TaxAdjustment')
        safe_delete('financial', 'TaxReversal')
        safe_delete('financial', 'TaxEvent')
        safe_delete('financial', 'TaxCalculationLine')
        safe_delete('financial', 'TaxTransactionSnapshot')

        # الإيرادات المؤجلة
        safe_delete('financial', 'RevenueRecognitionEntry')
        safe_delete('financial', 'RevenueRecognitionScheduleLine')
        safe_delete('financial', 'RevenueRecognitionSchedule')
        safe_delete('financial', 'RevenueRecognitionReversal')

        # تقييم العملات IAS 21
        safe_delete('financial', 'FXRevaluationLine')
        safe_delete('financial', 'FXRevaluationRun')
        safe_delete('financial', 'FXRateSnapshot')
        safe_delete('financial', 'FXApprovalWorkflow')

        # مسارات الاعتماد
        safe_delete('financial', 'EnterpriseApprovalAuditLog')
        safe_delete('financial', 'EnterpriseApprovalStep')
        safe_delete('financial', 'EnterpriseApprovalRequest')

        # قيود اليومية والمعاملات
        safe_delete('financial', 'JournalEntryLineCostAllocation')
        safe_delete('financial', 'FinancialPostingReference')
        safe_delete('financial', 'JournalEntryLine')
        safe_delete('financial', 'JournalEntry')
        safe_delete('financial', 'ExpenseTransaction')
        safe_delete('financial', 'IncomeTransaction')
        safe_delete('financial', 'FinancialTransaction')
        safe_delete('financial', 'FiscalYearClosingRun')
        safe_delete('financial', 'PaymentSyncOperation')
        safe_delete('financial', 'PaymentSyncLog')
        safe_delete('financial', 'PaymentSyncError')

        # =========================================================================
        # 5. الموارد البشرية والرواتب (HR & Payroll Transactions)
        # =========================================================================
        safe_delete('hr', 'PayrollPaymentLine')
        safe_delete('hr', 'PayrollPayment')
        safe_delete('hr', 'PayrollLine')
        safe_delete('hr', 'PayrollAuditLog')
        safe_delete('hr', 'Payroll')
        safe_delete('hr', 'AdvanceInstallment')
        safe_delete('hr', 'Advance')
        safe_delete('hr', 'PenaltyReward')
        safe_delete('hr', 'PermissionRequest')
        safe_delete('hr', 'Leave')
        safe_delete('hr', 'Attendance')
        safe_delete('hr', 'AttendanceSummary')
        safe_delete('hr', 'LeaveSummary')
        safe_delete('hr', 'BiometricSyncLog')
        safe_delete('hr', 'BiometricLog')

        # =========================================================================
        # 6. تصفير الأرصدة والسلاسل التسلسلية (Balances & Sequences Reset)
        # =========================================================================
        if reset_balances:
            try:
                customer_model = apps.get_model('client', 'Customer')
                if customer_model:
                    customer_model.objects.all().update(current_balance=0)
            except Exception:
                pass

            try:
                supplier_model = apps.get_model('supplier', 'Supplier')
                if supplier_model:
                    supplier_model.objects.all().update(current_balance=0)
            except Exception:
                pass

            try:
                account_model = apps.get_model('financial', 'ChartOfAccounts')
                if account_model:
                    account_model.objects.all().update(current_balance=0)
            except Exception:
                pass

        if reset_sequences:
            try:
                # تصفير تسلسلات الترقيم التلقائي
                seq_model = apps.get_model('core', 'Sequence')
                if seq_model:
                    seq_model.objects.all().update(next_number=1)
            except Exception:
                pass

        total_deleted = sum(summary.values())
        logger.info(f"SystemResetService completed successfully. Total records wiped: {total_deleted}")
        return summary
