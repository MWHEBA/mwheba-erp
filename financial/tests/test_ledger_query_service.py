import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from financial.models import (
    ChartOfAccounts,
    AccountType,
    FiscalYear,
    AccountingPeriod,
    JournalEntry,
    JournalEntryLine
)
from financial.services import LedgerCoreService, LedgerQueryService

User = get_user_model()


@pytest.mark.django_db
class TestLedgerQueryService:

    @pytest.fixture
    def setup_query_data(self):
        user = User.objects.create_user(username="query_user", password="password123")
        today = timezone.now().date()

        fiscal_year = FiscalYear.objects.create(
            year_code=f"FY-{today.year}-QUERY",
            name=f"Fiscal Year {today.year}",
            start_date=today.replace(month=1, day=1),
            end_date=today.replace(month=12, day=31),
            status="open"
        )

        period, _ = AccountingPeriod.objects.get_or_create(
            fiscal_year=fiscal_year,
            period_number=today.month,
            defaults={
                "name": f"Period {today.month}",
                "start_date": today.replace(day=1),
                "end_date": today.replace(day=28),
                "status": "open"
            }
        )

        asset_type, _ = AccountType.objects.get_or_create(code="AST_QUERY", defaults={"name": "Asset Query", "category": "asset"})
        revenue_type, _ = AccountType.objects.get_or_create(code="REV_QUERY", defaults={"name": "Revenue Query", "category": "revenue"})

        cash_acc = ChartOfAccounts.objects.create(code="10100_QUERY", name="Cash Query Account", account_type=asset_type, is_active=True)
        rev_acc = ChartOfAccounts.objects.create(code="40100_QUERY", name="Revenue Query Account", account_type=revenue_type, is_active=True)

        return user, fiscal_year, period, cash_acc, rev_acc

    def test_get_account_balance_posted_only(self, setup_query_data):
        user, fiscal_year, period, cash_acc, rev_acc = setup_query_data

        # draft entry should not affect balance
        draft = LedgerCoreService.create_draft_entry(
            date=timezone.now().date(),
            description="Draft Txn",
            reference="REF-DRAFT",
            entry_type="manual",
            created_by=user,
            lines_data=[
                {"account": cash_acc, "debit": Decimal("1000.00"), "credit": Decimal("0.00")},
                {"account": rev_acc, "debit": Decimal("0.00"), "credit": Decimal("1000.00")}
            ]
        )

        bal_draft = LedgerQueryService.get_account_balance(cash_acc)
        assert bal_draft['balance'] == Decimal("0.00")

        # post entry
        posted = LedgerCoreService.post_entry(draft.id, user, posting_source="MANUAL_JOURNAL")
        bal_posted = LedgerQueryService.get_account_balance(cash_acc)
        assert bal_posted['balance'] == Decimal("1000.00")
        assert bal_posted['debit'] == Decimal("1000.00")
        assert bal_posted['credit'] == Decimal("0.00")

    def test_get_account_statement(self, setup_query_data):
        user, fiscal_year, period, cash_acc, rev_acc = setup_query_data
        today = timezone.now().date()

        draft1 = LedgerCoreService.create_draft_entry(
            date=today,
            description="Txn 1",
            reference="REF-1",
            entry_type="manual",
            created_by=user,
            lines_data=[
                {"account": cash_acc, "debit": Decimal("500.00"), "credit": Decimal("0.00")},
                {"account": rev_acc, "debit": Decimal("0.00"), "credit": Decimal("500.00")}
            ]
        )
        LedgerCoreService.post_entry(draft1.id, user)

        stmt = LedgerQueryService.get_account_statement(cash_acc)
        assert stmt['opening_balance'] == Decimal("0.00")
        assert len(stmt['transactions']) == 1
        assert stmt['transactions'][0]['running_balance'] == Decimal("500.00")
        assert stmt['closing_balance'] == Decimal("500.00")

    def test_get_control_account_reconciliation(self, setup_query_data):
        user, fiscal_year, period, cash_acc, rev_acc = setup_query_data

        sub_acc1 = ChartOfAccounts.objects.create(code="10101_SUB", name="Sub 1", account_type=cash_acc.account_type, is_active=True)
        sub_acc2 = ChartOfAccounts.objects.create(code="10102_SUB", name="Sub 2", account_type=cash_acc.account_type, is_active=True)

        # Post 300 to sub1 and 700 to sub2, and 1000 to cash_acc (control)
        draft1 = LedgerCoreService.create_draft_entry(
            date=timezone.now().date(),
            description="Control Reconciliation Setup",
            reference="REF-CTRL",
            entry_type="manual",
            created_by=user,
            lines_data=[
                {"account": cash_acc, "debit": Decimal("1000.00"), "credit": Decimal("0.00")},
                {"account": rev_acc, "debit": Decimal("0.00"), "credit": Decimal("1000.00")}
            ]
        )
        LedgerCoreService.post_entry(draft1.id, user)

        draft2 = LedgerCoreService.create_draft_entry(
            date=timezone.now().date(),
            description="Sub 1 Setup",
            reference="REF-SUB1",
            entry_type="manual",
            created_by=user,
            lines_data=[
                {"account": sub_acc1, "debit": Decimal("300.00"), "credit": Decimal("0.00")},
                {"account": rev_acc, "debit": Decimal("0.00"), "credit": Decimal("300.00")}
            ]
        )
        LedgerCoreService.post_entry(draft2.id, user)

        draft3 = LedgerCoreService.create_draft_entry(
            date=timezone.now().date(),
            description="Sub 2 Setup",
            reference="REF-SUB2",
            entry_type="manual",
            created_by=user,
            lines_data=[
                {"account": sub_acc2, "debit": Decimal("700.00"), "credit": Decimal("0.00")},
                {"account": rev_acc, "debit": Decimal("0.00"), "credit": Decimal("700.00")}
            ]
        )
        LedgerCoreService.post_entry(draft3.id, user)

        rec = LedgerQueryService.get_control_account_reconciliation(cash_acc, [sub_acc1, sub_acc2])
        assert rec['is_reconciled'] is True
        assert rec['control_balance'] == Decimal("1000.00")
        assert rec['sub_accounts_total'] == Decimal("1000.00")
        assert rec['difference'] == Decimal("0.00")
