import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from financial.models import ChartOfAccounts, AccountType, AccountingPeriod, FiscalYear, FinancialStatementSnapshot
from financial.services.financial_reporting_query_service import FinancialReportingQueryService
from financial.services.financial_statement_engine import FinancialStatementEngine
from financial.services.financial_snapshot_service import FinancialSnapshotService
from financial.services.ledger_core_service import LedgerCoreService

User = get_user_model()


@pytest.mark.django_db(transaction=True)
class TestFinancialReportingEngine:

    @pytest.fixture
    def setup_reporting_data(self):
        user = User.objects.create_user(username="rep_user5", password="password123")

        asset_type, _ = AccountType.objects.get_or_create(code="ASSET", defaults={"name": "Asset", "category": "ASSET"})
        liability_type, _ = AccountType.objects.get_or_create(code="LIABILITY", defaults={"name": "Liability", "category": "LIABILITY"})
        equity_type, _ = AccountType.objects.get_or_create(code="EQUITY", defaults={"name": "Equity", "category": "EQUITY"})
        revenue_type, _ = AccountType.objects.get_or_create(code="REVENUE", defaults={"name": "Revenue", "category": "REVENUE"})
        expense_type, _ = AccountType.objects.get_or_create(code="EXPENSE", defaults={"name": "Expense", "category": "EXPENSE"})

        cash_acc = ChartOfAccounts.objects.create(code="10100_CASH", name="Cash Box", account_type=asset_type, is_active=True)
        ar_acc = ChartOfAccounts.objects.create(code="11010_AR", name="Accounts Receivable", account_type=asset_type, is_active=True)
        inv_acc = ChartOfAccounts.objects.create(code="11040_INV", name="Inventory Control", account_type=asset_type, is_active=True)

        ap_acc = ChartOfAccounts.objects.create(code="20100_AP", name="Accounts Payable", account_type=liability_type, is_active=True)
        equity_acc = ChartOfAccounts.objects.create(code="30100_EQ", name="Capital", account_type=equity_type, is_active=True)

        rev_acc = ChartOfAccounts.objects.create(code="40100_REV", name="Sales Revenue", account_type=revenue_type, is_active=True)
        cogs_acc = ChartOfAccounts.objects.create(code="50100_COGS", name="Cost of Goods Sold", account_type=expense_type, is_active=True)
        exp_acc = ChartOfAccounts.objects.create(code="60100_EXP", name="Office Expense", account_type=expense_type, is_active=True)

        fiscal_year = FiscalYear.objects.create(name="FY2026", start_date="2026-01-01", end_date="2026-12-31")
        period = AccountingPeriod.objects.create(fiscal_year=fiscal_year, name="AUG2026", period_number=8, start_date="2026-08-01", end_date="2026-08-31", status="OPEN")

        today = timezone.now().date()
        # Create balanced postings: Revenue 1000 EGP (Cash +1000, Rev +1000)
        lines1 = [
            {"account": cash_acc, "debit": Decimal("1000.00"), "credit": Decimal("0.00"), "description": "Cash debit"},
            {"account": rev_acc, "debit": Decimal("0.00"), "credit": Decimal("1000.00"), "description": "Rev credit"}
        ]
        entry1 = LedgerCoreService.create_draft_entry(
            date=today,
            description="Sales Revenue Entry",
            reference="INV-REP-100",
            entry_type="GENERAL",
            created_by=user,
            lines_data=lines1
        )
        LedgerCoreService.post_entry(entry1.id, user=user)

        # COGS Entry 400 EGP (COGS +400, Inv +400)
        lines2 = [
            {"account": cogs_acc, "debit": Decimal("400.00"), "credit": Decimal("0.00"), "description": "COGS debit"},
            {"account": inv_acc, "debit": Decimal("0.00"), "credit": Decimal("400.00"), "description": "Inv credit"}
        ]
        entry2 = LedgerCoreService.create_draft_entry(
            date=today,
            description="COGS Entry",
            reference="INV-REP-100-COGS",
            entry_type="GENERAL",
            created_by=user,
            lines_data=lines2
        )
        LedgerCoreService.post_entry(entry2.id, user=user)

        return user, period, cash_acc, rev_acc, cogs_acc

    def test_fin_rep_001_reporting_query_gateway(self, setup_reporting_data):
        user, period, cash_acc, rev_acc, cogs_acc = setup_reporting_data

        fact = FinancialReportingQueryService.get_account_balance_fact("10100_CASH")
        assert abs(Decimal(str(fact["balance"]))) == Decimal("1000.00")

        total_assets = FinancialReportingQueryService.get_account_group_totals("1")
        # Cash (+1000) + Inv (-400) = 600
        assert total_assets == Decimal("600.00")

    def test_fin_rep_002_trial_balance_and_financial_statements(self, setup_reporting_data):
        user, period, cash_acc, rev_acc, cogs_acc = setup_reporting_data

        # 1. Trial Balance
        tb = FinancialStatementEngine.generate_trial_balance()
        assert tb["is_balanced"] is True
        assert tb["total_debit"] == Decimal("1400.00")
        assert tb["total_credit"] == Decimal("1400.00")

        # 2. Income Statement
        pnl = FinancialStatementEngine.generate_income_statement()
        assert pnl["total_revenue"] == Decimal("1000.00")
        assert pnl["total_cogs"] == Decimal("400.00")
        assert pnl["net_income"] == Decimal("600.00")

        # 3. Balance Sheet
        bs = FinancialStatementEngine.generate_balance_sheet()
        assert bs["is_balanced"] is True
        assert bs["total_assets"] == Decimal("600.00")
        assert bs["net_income"] == Decimal("600.00")

    def test_fin_rep_003_historical_reporting_snapshot(self, setup_reporting_data):
        user, period, cash_acc, rev_acc, cogs_acc = setup_reporting_data

        snap = FinancialSnapshotService.create_statement_snapshot(
            period=period,
            statement_type="TRIAL_BALANCE",
            user=user
        )

        assert snap is not None
        assert snap.statement_type == "TRIAL_BALANCE"
        assert "lines" in snap.statement_data
        assert Decimal(snap.statement_data["total_debit"]) == Decimal("1400.00")
