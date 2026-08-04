import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from financial.models import (
    ChartOfAccounts,
    AccountType,
    AccountingPeriod,
    FiscalYear,
    JournalEntry
)
from financial.services.ledger_core_service import LedgerCoreService
from financial.exceptions import FinancialCoreError, ImmutableLedgerError

User = get_user_model()


@pytest.mark.django_db
class TestLedgerCoreService:

    @pytest.fixture
    def setup_ledger_data(self):
        user = User.objects.create_user(username="ledger_core_user", password="password123")
        today = timezone.now().date()

        fiscal_year = FiscalYear.objects.create(
            year_code=f"FY-{today.year}-CORE",
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

        asset_type, _ = AccountType.objects.get_or_create(code="AST_CORE", defaults={"name": "Asset Core", "category": "asset"})
        revenue_type, _ = AccountType.objects.get_or_create(code="REV_CORE", defaults={"name": "Revenue Core", "category": "revenue"})

        cash_acc = ChartOfAccounts.objects.create(code="10100_CORE", name="Cash Core", account_type=asset_type, is_active=True)
        rev_acc = ChartOfAccounts.objects.create(code="40100_CORE", name="Revenue Core", account_type=revenue_type, is_active=True)

        return user, fiscal_year, period, cash_acc, rev_acc

    def test_controlled_reversal_sequence(self, setup_ledger_data):
        user, fiscal_year, period, cash_acc, rev_acc = setup_ledger_data

        draft = LedgerCoreService.create_draft_entry(
            date=timezone.now().date(),
            description="Original Sales Transaction",
            reference="REF-SALES-100",
            entry_type="sale",
            created_by=user,
            lines_data=[
                {"account": cash_acc, "debit": Decimal("1500.00"), "credit": Decimal("0.00")},
                {"account": rev_acc, "debit": Decimal("0.00"), "credit": Decimal("1500.00")}
            ]
        )

        original_posted = LedgerCoreService.post_entry(draft.id, user, posting_source="SALES_ENGINE", posting_reference="INV-1001")
        assert original_posted.status == "posted"

        reversal_posted = LedgerCoreService.reverse_entry(
            entry_id=original_posted.id,
            user=user,
            reversal_reason="Customer return order"
        )

        assert reversal_posted.status == "posted"
        assert reversal_posted.is_reversal is True
        assert reversal_posted.original_entry_id == original_posted.id

        original_posted.refresh_from_db()
        assert original_posted.reversed_by_entry_id == reversal_posted.id

        rev_lines = list(reversal_posted.lines.order_by("id"))
        assert len(rev_lines) == 2
        assert rev_lines[0].credit == Decimal("1500.00")
        assert rev_lines[1].debit == Decimal("1500.00")

    def test_unbalanced_entry_rejection(self, setup_ledger_data):
        user, fiscal_year, period, cash_acc, rev_acc = setup_ledger_data

        with pytest.raises(FinancialCoreError) as exc_info:
            LedgerCoreService.create_draft_entry(
                date=timezone.now().date(),
                description="Unbalanced Entry Attempt",
                reference="REF-UNBAL-001",
                entry_type="manual",
                created_by=user,
                lines_data=[
                    {"account": cash_acc, "debit": Decimal("1000.00"), "credit": Decimal("0.00")},
                    {"account": rev_acc, "debit": Decimal("0.00"), "credit": Decimal("900.00")}
                ]
            )

        assert "Unbalanced entry" in str(exc_info.value)
