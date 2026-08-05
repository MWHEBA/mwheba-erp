import pytest
from datetime import date
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model

from client.models import Customer
from supplier.models import Supplier
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.services.ledger_core_service import LedgerCoreService
from financial.services.ledger_query_service import LedgerQueryService
from client.services.customer_subledger_service import CustomerSubledgerService
from supplier.services.supplier_subledger_service import SupplierSubledgerService
from financial.services.bank_subledger_service import BankSubledgerService
from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames

User = get_user_model()


class Sprint2SubledgersTestSuite(TestCase):
    """
    مجموعة اختبارات المحركات المحاسبية الفرعية لـ Sprint 2 (AR, AP & Bank Subledgers)
    """

    def setUp(self):
        self.user = User.objects.create_user(username="subledger_admin", password="password123")

        # أنواع الحسابات
        self.asset_type = AccountType.objects.create(code="AST_SUB", name="أصول متداولة", category="asset", nature="debit")
        self.liability_type = AccountType.objects.create(code="LIAB_SUB", name="التزامات متداولة", category="liability", nature="credit")
        self.revenue_type = AccountType.objects.create(code="REV_SUB", name="إيرادات", category="income", nature="credit")

        # حسابات التحكم الإجمالية
        self.ar_control_account = ChartOfAccounts.objects.create(
            code="11000_CTRL", name="حساب تحكم العملاء", account_type=self.asset_type, is_active=True, is_leaf=False
        )
        self.ap_control_account = ChartOfAccounts.objects.create(
            code="21000_CTRL", name="حساب تحكم الموردين", account_type=self.liability_type, is_active=True, is_leaf=False
        )

        # حسابات الفرعية الخاصة بالعملاء والموردين والنقدية
        self.cust_account = ChartOfAccounts.objects.create(
            code="11010_CUST1", name="حساب العميل شركة الأمل", account_type=self.asset_type, is_active=True, is_leaf=True
        )
        self.supp_account = ChartOfAccounts.objects.create(
            code="21010_SUPP1", name="حساب المورد شركة النور", account_type=self.liability_type, is_active=True, is_leaf=True
        )
        self.bank_account = ChartOfAccounts.objects.create(
            code="10201_BANK1", name="بنك مصر - الحساب الجاري", account_type=self.asset_type, is_active=True, is_leaf=True, is_bank_account=True
        )
        self.revenue_account = ChartOfAccounts.objects.create(
            code="41010_REV", name="إيراد المبيعات", account_type=self.revenue_type, is_active=True, is_leaf=True
        )

        # إنشاء فترة محاسبية
        from financial.models.journal_entry import AccountingPeriod
        self.period = AccountingPeriod.objects.create(
            name="فبراير 2026",
            period_number=2,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 28),
            status="open"
        )
        self.customer = Customer.objects.create(
            name="شركة الأمل",
            code="CUST-001",
            financial_account=self.cust_account,
            is_active=True
        )
        self.supplier = Supplier.objects.create(
            name="شركة النور",
            code="SUPP-001",
            financial_account=self.supp_account,
            is_active=True
        )

    def test_01_ledger_query_service_facts_only(self):
        """اختبار خدمة استعلامات حقائق الأستاذ العام LedgerQueryService"""
        # قيد مبيعات آجل
        lines = [
            {"account": self.cust_account, "debit": Decimal("5000.00"), "credit": Decimal("0.00")},
            {"account": self.revenue_account, "debit": Decimal("0.00"), "credit": Decimal("5000.00")},
        ]
        draft = LedgerCoreService.create_draft_entry(
            date=date(2026, 2, 1),
            description="فاتورة مبيعات آفر",
            reference="INV-2026-01",
            entry_type="automatic",
            created_by=self.user,
            lines_data=lines
        )
        LedgerCoreService.post_entry(draft.id, self.user)

        bal_data = LedgerQueryService.get_account_balance(self.cust_account)
        self.assertEqual(bal_data['balance'], Decimal("5000.00"))
        self.assertEqual(bal_data['nature'], 'debit')

        stmt = LedgerQueryService.get_account_statement(self.cust_account)
        self.assertEqual(len(stmt['transactions']), 1)
        self.assertEqual(stmt['closing_balance'], Decimal("5000.00"))

    def test_02_customer_subledger_service(self):
        """اختبار خدمة الدفتر الفرعي للعملاء ومطابقة حساب التحكم"""
        lines = [
            {"account": self.cust_account, "debit": Decimal("3000.00"), "credit": Decimal("0.00")},
            {"account": self.revenue_account, "debit": Decimal("0.00"), "credit": Decimal("3000.00")},
        ]
        draft = LedgerCoreService.create_draft_entry(
            date=date(2026, 2, 5),
            description="فاتورة مبيعات للعميل",
            reference="INV-CUST-1",
            entry_type="automatic",
            created_by=self.user,
            lines_data=lines
        )
        LedgerCoreService.post_entry(draft.id, self.user)

        cust_bal = CustomerSubledgerService.get_customer_balance(self.customer.id)
        self.assertEqual(cust_bal['balance'], Decimal("3000.00"))
        self.assertEqual(cust_bal['customer_name'], "شركة الأمل")

        statement = CustomerSubledgerService.get_customer_statement(self.customer.id)
        self.assertEqual(statement['closing_balance'], Decimal("3000.00"))

    def test_03_supplier_subledger_service(self):
        """اختبار خدمة الدفتر الفرعي للموردين"""
        lines = [
            {"account": self.revenue_account, "debit": Decimal("4000.00"), "credit": Decimal("0.00")},
            {"account": self.supp_account, "debit": Decimal("0.00"), "credit": Decimal("4000.00")},
        ]
        draft = LedgerCoreService.create_draft_entry(
            date=date(2026, 2, 10),
            description="فاتورة مشتريات من المورد",
            reference="BILL-SUPP-1",
            entry_type="automatic",
            created_by=self.user,
            lines_data=lines
        )
        LedgerCoreService.post_entry(draft.id, self.user)

        supp_bal = SupplierSubledgerService.get_supplier_balance(self.supplier.id)
        self.assertEqual(supp_bal['balance'], Decimal("4000.00"))
        self.assertEqual(supp_bal['nature'], 'credit')

    def test_04_bank_subledger_service(self):
        """اختبار خدمة الدفتر الفرعي للبنوك والخزن"""
        lines = [
            {"account": self.bank_account, "debit": Decimal("10000.00"), "credit": Decimal("0.00")},
            {"account": self.revenue_account, "debit": Decimal("0.00"), "credit": Decimal("10000.00")},
        ]
        draft = LedgerCoreService.create_draft_entry(
            date=date(2026, 2, 12),
            description="إيداع بنكي مباشر",
            reference="DEP-BANK-1",
            entry_type="automatic",
            created_by=self.user,
            lines_data=lines
        )
        LedgerCoreService.post_entry(draft.id, self.user)

        bank_bal = BankSubledgerService.get_bank_balance(self.bank_account)
        self.assertEqual(bank_bal['balance'], Decimal("10000.00"))
        self.assertTrue(bank_bal['is_bank'])

        summary = BankSubledgerService.get_cash_and_bank_summary()
        self.assertGreaterEqual(summary['grand_total'], Decimal("10000.00"))
