import logging
from decimal import Decimal
from django.db import transaction, connection
from django.apps import apps
from django.core.files.storage import default_storage
from django.core.cache import cache

logger = logging.getLogger(__name__)


class SystemResetService:
    """
    خدمة تفريغ وتصفير الحركات والمعاملات التجريبية بنسبة 100%
    مع الحفاظ التام على الإعدادات، المستخدمين، شجرة الحسابات، العملات، والمخازن.
    """

    @classmethod
    def reset_test_transactions(cls, user=None, reset_sequences=True, reset_balances=True):
        """
        تفريغ كافة الحركات والمعاملات الحركية بالترتيب المعماري الصارم داخل معاملة ذرية كاملة.
        """
        from core.models import SystemSetting

        summary = {}

        def safe_delete(app_label, model_name):
            """
            حذف السجلات باستخدام _base_manager لضمان شمول السجلات المحذوفة ناعماً (Soft-deleted)
            """
            try:
                model = apps.get_model(app_label, model_name)
                if model:
                    manager = getattr(model, '_base_manager', model.objects)
                    count, _ = manager.all().delete()
                    summary[f"{app_label}.{model_name}"] = count
                    return count
            except Exception as e:
                logger.warning(f"Could not delete {app_label}.{model_name}: {e}")
                summary[f"{app_label}.{model_name}"] = 0
                return 0

        # تفعيل وضع الصيانة المؤقت لتفادي أي تعديلات متزامنة (Race Conditions)
        try:
            SystemSetting.set_setting("maintenance_mode", "true")
        except Exception:
            pass

        try:
            with transaction.atomic():
                # =========================================================================
                # المرحلة 0: فك أقفال الحصانة المحاسبية والارتباطات العكسية (Pre-Reset Unlock)
                # =========================================================================
                try:
                    batch_model = apps.get_model('financial', 'OpeningBalanceBatch')
                    if batch_model:
                        batch_model._base_manager.all().update(
                            status='draft',
                            journal_entry=None,
                            reversal_journal_entry=None
                        )
                except Exception as e:
                    logger.warning(f"Pre-unlock OpeningBalanceBatch: {e}")

                try:
                    je_model = apps.get_model('financial', 'JournalEntry')
                    if je_model:
                        je_model._base_manager.all().update(status='draft')
                except Exception as e:
                    logger.warning(f"Pre-unlock JournalEntry: {e}")

                # =========================================================================
                # المرحلة 1: تنظيف المرفقات والملفات الفيزيائية الآمنة (Attachments & Media)
                # =========================================================================
                try:
                    blob_model = apps.get_model('core', 'FileBlob')
                    if blob_model:
                        for blob in blob_model._base_manager.all():
                            if blob.file and blob.file.name:
                                # حماية شعار وختم الشركة في media/company/
                                if not blob.file.name.startswith('company/'):
                                    try:
                                        default_storage.delete(blob.file.name)
                                    except Exception:
                                        pass
                except Exception as e:
                    logger.warning(f"Physical file cleanup: {e}")

                safe_delete('core', 'Attachment')
                safe_delete('core', 'DraftAttachment')
                safe_delete('core', 'AttachmentAuditLog')
                safe_delete('core', 'AttachmentOrphanReview')
                safe_delete('core', 'FileBlob')
                safe_delete('financial', 'TransactionAttachment')

                # =========================================================================
                # المرحلة 2: أوامر الشغل ومطبعة التسعير (Work Orders & Printing Pricing)
                # =========================================================================
                safe_delete('work_order', 'WorkOrder')
                safe_delete('printing_pricing', 'OrderMaterial')
                safe_delete('printing_pricing', 'PaperSpecification')
                safe_delete('printing_pricing', 'OrderService')
                safe_delete('printing_pricing', 'PrintingSpecification')
                safe_delete('printing_pricing', 'CostCalculation')
                safe_delete('printing_pricing', 'OrderSummary')
                safe_delete('printing_pricing', 'PrintingOrder')

                # =========================================================================
                # المرحلة 3: دورة المبيعات والعملاء (Sales & Customers Transactions - Bottom-Up)
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
                safe_delete('sale', 'SaleReturnItem')
                safe_delete('sale', 'SaleReturn')
                safe_delete('sale', 'ReturnAuthorization')

                # أذون التسليم وأوامر البيع وعروض الأسعار
                safe_delete('sale', 'DeliveryNoteItem')
                safe_delete('sale', 'DeliveryNote')
                safe_delete('sale', 'SalesOrderItem')
                safe_delete('sale', 'SalesOrder')
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
                safe_delete('customer', 'CustomerAllocationAudit')
                safe_delete('customer', 'CustomerTransaction')
                safe_delete('customer', 'CustomerPayment')
                safe_delete('customer', 'CustomerCreditStatusHistory')
                safe_delete('customer', 'CreditAuditLog')

                # =========================================================================
                # المرحلة 4: دورة المشتريات والموردين (Purchases & Suppliers - Bottom-Up)
                # =========================================================================
                safe_delete('purchase', 'BillLineMatching')
                safe_delete('purchase', 'SupplierBillItem')
                safe_delete('purchase', 'SupplierBill')
                safe_delete('purchase', 'GRNAuditLog')
                safe_delete('purchase', 'GRNPostingLog')
                safe_delete('purchase', 'GoodsReceiptItem')
                safe_delete('purchase', 'GoodsReceipt')
                safe_delete('purchase', 'SupplierAdvancePayment')
                safe_delete('supplier', 'SupplierTransaction')
                safe_delete('supplier', 'SupplierPayment')
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
                # المرحلة 5: حركات المخزن وطبقات التكاليف والأصناف (Inventory & Cost Layers)
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
                safe_delete('product', 'ProductLocation')

                # الحركات التشغيلية للأصناف
                safe_delete('product', 'SerialNumber')
                safe_delete('product', 'PriceHistory')
                safe_delete('product', 'ExpiryAlert')
                safe_delete('product', 'ProductBatch')

                # =========================================================================
                # المرحلة 6: المالية والحسابات والقيود والأرصدة الافتتاحية (Financials & GL)
                # =========================================================================
                # الأرصدة الافتتاحية
                safe_delete('financial', 'OpeningBalanceLine')
                safe_delete('financial', 'ControlAccountOverrideRequest')
                safe_delete('financial', 'OpeningBalanceImportBatch')
                safe_delete('financial', 'OpeningBalanceBatch')

                # البنوك والتسويات
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

                # الضرائب وتدقيقها
                safe_delete('financial', 'TaxAdjustment')
                safe_delete('financial', 'TaxReversal')
                safe_delete('financial', 'TaxEvent')
                safe_delete('financial', 'TaxCalculationLine')
                safe_delete('financial', 'TaxTransactionSnapshot')
                safe_delete('financial', 'TaxRuleEvaluationLog')
                safe_delete('financial', 'TaxDeterminationAudit')
                safe_delete('financial', 'TaxExemptionSnapshot')

                # الإيرادات المؤجلة وتقييم العملات
                safe_delete('financial', 'RevenueRecognitionEntry')
                safe_delete('financial', 'RevenueRecognitionScheduleLine')
                safe_delete('financial', 'RevenueRecognitionSchedule')
                safe_delete('financial', 'RevenueRecognitionReversal')

                safe_delete('financial', 'FXRevaluationLine')
                safe_delete('financial', 'FXRevaluationRun')
                safe_delete('financial', 'FXRateSnapshot')
                safe_delete('financial', 'FXApprovalWorkflow')

                # مسارات الاعتماد ومراكز التكلفة والموازنات
                safe_delete('financial', 'EnterpriseApprovalAuditLog')
                safe_delete('financial', 'EnterpriseApprovalStep')
                safe_delete('financial', 'EnterpriseApprovalRequest')
                safe_delete('financial', 'CostCenterBalanceSnapshot')
                safe_delete('financial', 'CostCenterActualSnapshot')
                safe_delete('financial', 'CostCenterAuditLog')
                safe_delete('financial', 'CostAllocationRuleAuditLog')
                safe_delete('financial', 'BudgetOverrideRequest')

                # قيود اليومية والمعاملات المركزية
                safe_delete('financial', 'JournalEntryLineCostAllocation')
                safe_delete('financial', 'FinancialPostingReference')
                safe_delete('financial', 'JournalEntryLine')
                safe_delete('financial', 'JournalEntry')
                safe_delete('financial', 'ExpenseTransaction')
                safe_delete('financial', 'IncomeTransaction')
                safe_delete('financial', 'FinancialTransaction')
                safe_delete('financial', 'FiscalYearClosingRun')

                # سجلات المزامنة واللقطات والكاش
                safe_delete('financial', 'PaymentSyncOperation')
                safe_delete('financial', 'PaymentSyncLog')
                safe_delete('financial', 'PaymentSyncError')
                safe_delete('financial', 'BalanceSnapshot')
                safe_delete('financial', 'AccountBalanceCache')
                safe_delete('financial', 'AccountBalancePeriod')
                safe_delete('financial', 'BalanceAuditLog')
                safe_delete('financial', 'BalanceReconciliation')
                safe_delete('financial', 'FinancialStatementSnapshot')
                safe_delete('financial', 'ValidationAuditLog')
                safe_delete('financial', 'AuditTrail')
                safe_delete('financial', 'InvoiceAuditLog')
                safe_delete('financial', 'PartnerAuditLog')
                safe_delete('financial', 'DataMigrationRun')

                # =========================================================================
                # المرحلة 7: الموارد البشرية والرواتب (HR & Payroll Transactions)
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
                safe_delete('hr', 'LeaveBalance')
                safe_delete('hr', 'LeaveEncashmentLog')
                safe_delete('hr', 'EndOfServiceBenefit')
                safe_delete('hr', 'InsurancePayment')
                safe_delete('hr', 'Attendance')
                safe_delete('hr', 'AttendanceSummary')
                safe_delete('hr', 'LeaveSummary')
                safe_delete('hr', 'BiometricSyncLog')
                safe_delete('hr', 'BiometricLog')

                try:
                    device_model = apps.get_model('hr', 'BiometricDevice')
                    if device_model:
                        device_model._base_manager.all().update(last_sync_time=None)
                except Exception:
                    pass

                # =========================================================================
                # المرحلة 8: الحوكمة والإشعارات ومفاتيح Idempotency (Governance & Core Logs)
                # =========================================================================
                safe_delete('governance', 'IdempotencyRecord')
                safe_delete('governance', 'AuditTrail')
                safe_delete('governance', 'SecurityIncident')
                safe_delete('governance', 'SignalExecution')
                safe_delete('governance', 'SignalPerformanceAlert')
                safe_delete('governance', 'ReportExecution')

                safe_delete('users', 'ActivityLog')
                safe_delete('core', 'Notification')
                safe_delete('core', 'DocumentSequenceAudit')
                safe_delete('core', 'UnifiedLog')
                safe_delete('core', 'Alert')
                safe_delete('core', 'DashboardStat')
                safe_delete('utils', 'SystemLog')

                # =========================================================================
                # المرحلة 9: التصفير الصارم للأرصدة وفتح الفترات وسلاسل الترقيم
                # =========================================================================
                if reset_balances:
                    try:
                        customer_model = apps.get_model('customer', 'Customer')
                        if customer_model:
                            customer_model._base_manager.all().update(balance=Decimal('0.00'))
                    except Exception as e:
                        logger.warning(f"Reset Customer balance: {e}")

                    try:
                        supplier_model = apps.get_model('supplier', 'Supplier')
                        if supplier_model:
                            supplier_model._base_manager.all().update(balance=Decimal('0.00'))
                    except Exception as e:
                        logger.warning(f"Reset Supplier balance: {e}")

                    try:
                        account_model = apps.get_model('financial', 'ChartOfAccounts')
                        if account_model:
                            account_model._base_manager.all().update(
                                opening_balance=Decimal('0.00'),
                                opening_balance_foreign=Decimal('0.00'),
                                opening_balance_rate=Decimal('1.000000'),
                                opening_balance_date=None
                            )
                    except Exception as e:
                        logger.warning(f"Reset ChartOfAccounts opening_balance: {e}")

                    try:
                        stock_model = apps.get_model('product', 'Stock')
                        if stock_model:
                            stock_model._base_manager.all().update(quantity=0, reserved_quantity=0)
                    except Exception as e:
                        logger.warning(f"Reset Stock quantity: {e}")

                    # فتح الفترات المالية والسنوات
                    try:
                        period_model = apps.get_model('financial', 'AccountingPeriod')
                        if period_model:
                            period_model._base_manager.all().update(
                                status='open',
                                closed_at=None,
                                closed_by=None,
                                force_closed_by=None,
                                force_close_reason=''
                            )
                    except Exception as e:
                        logger.warning(f"Reopen AccountingPeriod: {e}")

                    try:
                        fy_model = apps.get_model('financial', 'FiscalYear')
                        if fy_model:
                            fy_model._base_manager.all().update(
                                status='open',
                                closing_journal_entry=None,
                                closed_at=None,
                                closed_by=None,
                                net_profit_loss=Decimal('0.00')
                            )
                    except Exception as e:
                        logger.warning(f"Reopen FiscalYear: {e}")

                    safe_delete('financial', 'PeriodModuleLock')

                if reset_sequences:
                    try:
                        counter_model = apps.get_model('core', 'DocumentSequenceCounter')
                        if counter_model:
                            counter_model._base_manager.all().update(last_number=0)
                    except Exception as e:
                        logger.warning(f"Reset DocumentSequenceCounter: {e}")

                    try:
                        rule_model = apps.get_model('core', 'DocumentSequenceRule')
                        if rule_model:
                            rule_model._base_manager.all().update(is_locked=False)
                    except Exception as e:
                        logger.warning(f"Unlock DocumentSequenceRule: {e}")

            # =========================================================================
            # المرحلة 10: ما بعد المعاملة الذرية (Post-Transaction DDL & Cache Invalidation)
            # DDL statements (ALTER TABLE) must run outside transaction.atomic in MySQL
            # =========================================================================
            if reset_sequences:
                try:
                    db_engine = connection.vendor
                    tables_to_reset = [
                        'sale_sale', 'sale_saleitem', 'sale_salesinvoice', 'sale_quotation',
                        'purchase_purchase', 'purchase_purchaseitem', 'purchase_supplierbill',
                        'financial_journalentry', 'financial_journalentryline',
                        'financial_openingbalancebatch', 'financial_openingbalanceline',
                        'financial_financialtransaction', 'financial_expensetransaction', 'financial_incometransaction',
                        'customer_customertransaction', 'customer_customerpayment',
                        'supplier_suppliertransaction', 'supplier_supplieradvancepayment',
                        'product_stockmovement', 'product_stocktransfer', 'product_stockledgerentry',
                        'work_order_workorder', 'printing_pricing_printingorder'
                    ]
                    with connection.cursor() as cursor:
                        if db_engine == 'sqlite':
                            cursor.execute(
                                f"DELETE FROM sqlite_sequence WHERE name IN ({','.join(['%s']*len(tables_to_reset))})",
                                tables_to_reset
                            )
                        elif db_engine == 'mysql':
                            for table in tables_to_reset:
                                try:
                                    cursor.execute(f"ALTER TABLE `{table}` AUTO_INCREMENT = 1;")
                                except Exception:
                                    pass
                except Exception as e:
                    logger.warning(f"Reset auto_increment counters: {e}")

            # تفريغ كاش الرام والريديس والخدمات المحاسبية
            try:
                cache.clear()
            except Exception:
                pass

            try:
                SystemSetting.invalidate_all_system_caches()
            except Exception:
                pass

            try:
                from financial.services.role_registry import AccountRoleRegistry
                if hasattr(AccountRoleRegistry, 'invalidate_cache'):
                    AccountRoleRegistry.invalidate_cache()
            except Exception:
                pass

            try:
                from financial.services.exchange_rate_service import ExchangeRateService
                if hasattr(ExchangeRateService, 'invalidate_cache'):
                    ExchangeRateService.invalidate_cache()
            except Exception:
                pass

        finally:
            # إلغاء وضع الصيانة في كل الأحوال لضمان عودة عمل النظام
            try:
                SystemSetting.set_setting("maintenance_mode", "false")
            except Exception:
                pass

        total_deleted = sum(summary.values())
        logger.info(f"SystemResetService completed successfully. Total records wiped: {total_deleted}")
        return summary
