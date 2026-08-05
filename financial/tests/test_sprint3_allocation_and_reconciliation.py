import pytest
from datetime import date
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model

from client.models import Customer, CustomerTransaction
from supplier.models import Supplier, SupplierTransaction
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.journal_entry import AccountingPeriod
from financial.services.ledger_core_service import LedgerCoreService
from financial.services.allocation_service import AllocationService
from financial.services.bank_reconciliation_service import BankReconciliationService
from financial.models.bank_reconciliation import BankStatementBatch, BankStatementLine, BankReconciliationMatch

User = get_user_model()


class Sprint3TestSuite(TestCase):
    """
    حزمة اختبارات المحركات المالية لـ Sprint 3 (Allocation, Aging Credit Balance & Bank Reconciliation)
    """

    def setUp(self):
        self.user = User.objects.create_user(username="sprint3_admin", password="password123")

        # أنواع الحسابات
        self.asset_type = AccountType.objects.create(code="AST_SP3", name="أصول متداولة", category="asset", nature="debit")
        self.liability_type = AccountType.objects.create(code="LIAB_SP3", name="التزامات متداولة", category="liability", nature="credit")
        self.revenue_type = AccountType.objects.create(code="REV_SP3", name="إيرادات", category="income", nature="credit")

        # الحسابات
        self.cust_account = ChartOfAccounts.objects.create(
            code="1103001", name="حساب العميل أفق", account_type=self.asset_type, is_active=True, is_leaf=True
        )
        self.bank_account = ChartOfAccounts.objects.create(
            code="10201", name="بنك CIB", account_type=self.asset_type, is_active=True, is_leaf=True, is_bank_account=True
        )
        self.revenue_account = ChartOfAccounts.objects.create(
            code="41010", name="إيراد خدمات", account_type=self.revenue_type, is_active=True, is_leaf=True
        )

        # الفترة المحاسبية
        self.period = AccountingPeriod.objects.create(
            name="مارس 2026",
            period_number=3,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
            status="open"
        )

        # الكيانات
        self.customer = Customer.objects.create(
            name="شركة أفق للتكنولوجيا",
            code="CUST-OFQ",
            financial_account=self.cust_account,
            is_active=True
        )

        # الترانزاكشنز
        self.inv_txn = CustomerTransaction.objects.create(
            customer=self.customer,
            transaction_type="INVOICE",
            transaction_number="INV-2026-99",
            issue_date=date(2026, 3, 5),
            due_date=date(2026, 3, 20),
            currency="EGP",
            exchange_rate=Decimal("1.000000"),
            functional_amount=Decimal("10000.00"),
            open_amount_functional=Decimal("10000.00"),
            open_amount=Decimal("10000.00"),
            status="OPEN"
        )
        self.pay_txn = CustomerTransaction.objects.create(
            customer=self.customer,
            transaction_type="PAYMENT",
            transaction_number="PAY-2026-99",
            issue_date=date(2026, 3, 10),
            due_date=date(2026, 3, 10),
            currency="EGP",
            exchange_rate=Decimal("1.000000"),
            functional_amount=Decimal("10000.00"),
            open_amount_functional=Decimal("10000.00"),
            open_amount=Decimal("10000.00"),
            status="OPEN"
        )

    def test_01_allocation_service_and_reversal(self):
        """اختبار محرك التسويات وإلغاء التسويات المحصن (Allocation & De-allocation Audit)"""
        res = AllocationService.allocate_payment(
            customer_id=self.customer.id,
            source_doc_type="PAYMENT",
            source_doc_id=self.pay_txn.id,
            target_doc_type="INVOICE",
            target_doc_id=self.inv_txn.id,
            allocated_amount=Decimal("4000.00"),
            allocation_date=date(2026, 3, 15),
            user=self.user
        )
        self.assertEqual(res['allocated_amount'], Decimal("4000.00"))

        self.inv_txn.refresh_from_db()
        self.pay_txn.refresh_from_db()
        self.assertEqual(self.inv_txn.open_amount, Decimal("6000.00"))
        self.assertEqual(self.pay_txn.open_amount, Decimal("6000.00"))

        # إلغاء التسوية وتتبع أثر المراجعة
        rev_res = AllocationService.reverse_allocation(
            allocation_id=res['allocation_id'],
            reason="إلغاء بطلب المحاسب",
            user=self.user
        )
        self.assertEqual(rev_res['status'], "REVERSED")

        self.inv_txn.refresh_from_db()
        self.pay_txn.refresh_from_db()
        self.assertEqual(self.inv_txn.open_amount, Decimal("10000.00"))
        self.assertEqual(self.pay_txn.open_amount, Decimal("10000.00"))

    def test_02_bank_reconciliation_import_and_matching(self):
        """اختبار استيراد كشف البنك والمطابقة التلقائية بـ SHA-256 Guard"""
        csv_data = (
            "date,reference,description,debit,credit\n"
            "2026-03-12,REF-BANK-77,إيداع عميل,5000.00,0.00\n"
        )

        import_res = BankReconciliationService.import_statement_batch(
            bank_account_id=self.bank_account.id,
            batch_number="BATCH-2026-01",
            statement_date=date(2026, 3, 12),
            file_content=csv_data,
            user=self.user
        )
        self.assertEqual(import_res['lines_imported'], 1)

        # اختبار المطابقة التلقائية
        lines = [
            {"account": self.bank_account, "debit": Decimal("5000.00"), "credit": Decimal("0.00")},
            {"account": self.revenue_account, "debit": Decimal("0.00"), "credit": Decimal("5000.00")},
        ]
        draft = LedgerCoreService.create_draft_entry(
            date=date(2026, 3, 12),
            description="إيداع بنكي",
            reference="REF-BANK-77",
            entry_type="automatic",
            created_by=self.user,
            lines_data=lines
        )
        LedgerCoreService.post_entry(draft.id, self.user)

        match_res = BankReconciliationService.auto_reconcile_batch(
            batch_id=import_res['batch_id'],
            user=self.user
        )
        self.assertEqual(match_res['matches_created'], 1)
