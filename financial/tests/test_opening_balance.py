import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from financial.models import (
    ChartOfAccounts,
    AccountType,
    FiscalYear,
    OpeningBalanceBatch,
    OpeningBalanceLine
)
from financial.services.opening_balance_service import OpeningBalanceService, OpeningBalanceValidationService
from financial.exceptions import ImmutableLedgerError, FinancialCoreError

User = get_user_model()


@pytest.mark.django_db
class TestOpeningBalanceService:

    @pytest.fixture
    def setup_opening_balance_data(self):
        user = User.objects.create_user(username="op_balance_user", email="op_balance_user@example.com", password="password123")
        today = timezone.now().date()

        fiscal_year = FiscalYear.objects.create(
            year_code=f"FY-{today.year}-OP",
            name=f"Fiscal Year {today.year}",
            start_date=today.replace(month=1, day=1),
            end_date=today.replace(month=12, day=31),
            status="open"
        )

        asset_type, _ = AccountType.objects.get_or_create(code="AST_OP", defaults={"name": "Asset Op", "category": "asset"})
        equity_type, _ = AccountType.objects.get_or_create(code="EQ_OP", defaults={"name": "Equity Op", "category": "equity"})

        cash_acc = ChartOfAccounts.objects.create(code="10100_OP", name="Cash Op", account_type=asset_type, is_active=True)
        equity_acc = ChartOfAccounts.objects.create(code="30100_OP", name="Equity Op", account_type=equity_type, is_active=True)

        return user, fiscal_year, cash_acc, equity_acc

    def test_opening_balance_posting_and_immutability(self, setup_opening_balance_data):
        user, fiscal_year, cash_acc, equity_acc = setup_opening_balance_data

        batch = OpeningBalanceBatch.objects.create(
            fiscal_year=fiscal_year,
            batch_number="OP-BATCH-TEST-200",
            description="Opening balance batch test",
            status="draft"
        )

        OpeningBalanceLine.objects.create(batch=batch, account=cash_acc, debit=Decimal("25000.00"), credit=Decimal("0.00"))
        OpeningBalanceLine.objects.create(batch=batch, account=equity_acc, debit=Decimal("0.00"), credit=Decimal("25000.00"))

        posted_batch = OpeningBalanceService.post_batch(batch.id, user)
        assert posted_batch.status == "posted"
        assert posted_batch.journal_entry is not None
        assert posted_batch.journal_entry.status == "posted"

        with pytest.raises(ImmutableLedgerError):
            OpeningBalanceService.post_batch(batch.id, user)

        with pytest.raises(ImmutableLedgerError):
            posted_batch.delete()
