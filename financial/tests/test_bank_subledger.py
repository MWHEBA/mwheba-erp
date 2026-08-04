import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from financial.models import ChartOfAccounts, AccountType, FiscalYear, AccountingPeriod
from financial.services import LedgerCoreService, BankSubledgerService

User = get_user_model()


@pytest.mark.django_db
class TestBankSubledgerService:

    @pytest.fixture
    def setup_bank_subledger(self):
        user = User.objects.create_user(username="bank_sub_user", password="password123")
        today = timezone.now().date()

        fiscal_year = FiscalYear.objects.create(
            year_code=f"FY-{today.year}-BANK",
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

        asset_type, _ = AccountType.objects.get_or_create(code="AST_BANK", defaults={"name": "Asset Bank", "category": "asset"})
        revenue_type, _ = AccountType.objects.get_or_create(code="REV_BANK", defaults={"name": "Revenue Bank", "category": "revenue"})

        bank_acc = ChartOfAccounts.objects.create(code="10201_BANK", name="CIB Bank Account", account_type=asset_type, is_active=True)
        cash_acc = ChartOfAccounts.objects.create(code="10101_CASH", name="Main Cash Box", account_type=asset_type, is_active=True)
        rev_acc = ChartOfAccounts.objects.create(code="40100_BANK", name="Service Revenue", account_type=revenue_type, is_active=True)

        return user, bank_acc, cash_acc, rev_acc

    def test_bank_balance_and_statement(self, setup_bank_subledger):
        user, bank_acc, cash_acc, rev_acc = setup_bank_subledger

        draft = LedgerCoreService.create_draft_entry(
            date=timezone.now().date(),
            description="Bank Deposit",
            reference="DEP-001",
            entry_type="manual",
            created_by=user,
            lines_data=[
                {"account": bank_acc, "debit": Decimal("10000.00"), "credit": Decimal("0.00")},
                {"account": rev_acc, "debit": Decimal("0.00"), "credit": Decimal("10000.00")}
            ]
        )
        LedgerCoreService.post_entry(draft.id, user, posting_source="SALE_PAYMENT")

        bal = BankSubledgerService.get_bank_balance(bank_acc)
        assert bal['balance'] == Decimal("10000.00")

        stmt = BankSubledgerService.get_bank_statement(bank_acc)
        assert stmt['closing_balance'] == Decimal("10000.00")
        assert len(stmt['transactions']) == 1

    def test_cash_and_bank_summary(self, setup_bank_subledger):
        user, bank_acc, cash_acc, rev_acc = setup_bank_subledger

        draft = LedgerCoreService.create_draft_entry(
            date=timezone.now().date(),
            description="Cash Receipt",
            reference="RCPT-001",
            entry_type="manual",
            created_by=user,
            lines_data=[
                {"account": cash_acc, "debit": Decimal("2500.00"), "credit": Decimal("0.00")},
                {"account": rev_acc, "debit": Decimal("0.00"), "credit": Decimal("2500.00")}
            ]
        )
        LedgerCoreService.post_entry(draft.id, user)

        summary = BankSubledgerService.get_cash_and_bank_summary()
        assert summary['grand_total'] >= Decimal("2500.00")
