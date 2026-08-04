import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from financial.models import (
    ChartOfAccounts,
    AccountType,
    FiscalYear,
    AccountingPeriod,
    BankStatementBatch,
    BankStatementLine,
    BankReconciliationMatch
)
from financial.services import LedgerCoreService, BankReconciliationService

User = get_user_model()


@pytest.mark.django_db
class TestBankReconciliationEngine:

    @pytest.fixture
    def setup_bank_rec_data(self):
        user = User.objects.create_user(username="bank_rec_user", password="password123")
        today = timezone.now().date()

        fiscal_year = FiscalYear.objects.create(
            year_code=f"FY-{today.year}-REC",
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

        asset_type, _ = AccountType.objects.get_or_create(code="AST_REC", defaults={"name": "Asset Rec", "category": "asset"})
        revenue_type, _ = AccountType.objects.get_or_create(code="REV_REC", defaults={"name": "Revenue Rec", "category": "revenue"})

        bank_acc = ChartOfAccounts.objects.create(code="10201_REC", name="CIB Rec Bank Account", account_type=asset_type, is_active=True)
        rev_acc = ChartOfAccounts.objects.create(code="40100_REC", name="Service Rev Rec Account", account_type=revenue_type, is_active=True)

        return user, bank_acc, rev_acc

    def test_import_and_auto_match_exact(self, setup_bank_rec_data):
        user, bank_acc, rev_acc = setup_bank_rec_data
        today = timezone.now().date()

        # Post GL entry
        draft = LedgerCoreService.create_draft_entry(
            date=today,
            description="Client Wire Deposit",
            reference="WIRE-7788",
            entry_type="manual",
            created_by=user,
            lines_data=[
                {"account": bank_acc, "debit": Decimal("5000.00"), "credit": Decimal("0.00")},
                {"account": rev_acc, "debit": Decimal("0.00"), "credit": Decimal("5000.00")}
            ]
        )
        posted_entry = LedgerCoreService.post_entry(draft.id, user, posting_reference="WIRE-7788")
        gl_line = posted_entry.lines.get(account=bank_acc)

        # Import statement batch
        batch = BankReconciliationService.import_statement_batch(
            bank_account_id=bank_acc.id,
            statement_date=today,
            opening_balance=Decimal("0.00"),
            closing_balance=Decimal("5000.00"),
            lines_data=[
                {
                    "transaction_date": today,
                    "reference_number": "WIRE-7788",
                    "description": "Incoming Wire 7788",
                    "debit": Decimal("5000.00"),
                    "credit": Decimal("0.00")
                }
            ],
            user=user
        )

        assert batch.lines.count() == 1
        stmt_line = batch.lines.first()
        assert stmt_line.is_matched is False

        # Run auto-match
        match_result = BankReconciliationService.auto_match_batch(batch.id, user)
        assert match_result['exact_matches'] == 1

        stmt_line.refresh_from_db()
        assert stmt_line.is_matched is True

        match_rec = BankReconciliationMatch.objects.get(statement_line=stmt_line)
        assert match_rec.journal_line_id == gl_line.id
        assert match_rec.match_type == "EXACT"

    def test_probable_match_requires_user_confirmation(self, setup_bank_rec_data):
        user, bank_acc, rev_acc = setup_bank_rec_data
        today = timezone.now().date()
        date_gl = today - timezone.timedelta(days=2)

        # Post GL entry 2 days earlier
        draft = LedgerCoreService.create_draft_entry(
            date=date_gl,
            description="Client Wire Probable",
            reference="DIFF-REF-99",
            entry_type="manual",
            created_by=user,
            lines_data=[
                {"account": bank_acc, "debit": Decimal("3500.00"), "credit": Decimal("0.00")},
                {"account": rev_acc, "debit": Decimal("0.00"), "credit": Decimal("3500.00")}
            ]
        )
        posted_entry = LedgerCoreService.post_entry(draft.id, user)
        gl_line = posted_entry.lines.get(account=bank_acc)

        # Import statement batch on today date
        batch = BankReconciliationService.import_statement_batch(
            bank_account_id=bank_acc.id,
            statement_date=today,
            opening_balance=Decimal("0.00"),
            closing_balance=Decimal("3500.00"),
            lines_data=[
                {
                    "transaction_date": today,
                    "reference_number": "STMT-REF-100",
                    "description": "Incoming Probable Wire",
                    "debit": Decimal("3500.00"),
                    "credit": Decimal("0.00")
                }
            ],
            user=user
        )

        stmt_line = batch.lines.first()

        # Run auto-match
        match_result = BankReconciliationService.auto_match_batch(batch.id, user)
        assert match_result['probable_matches_pending'] == 1
        assert match_result['exact_matches'] == 0

        # FIN-BANK-002 Verification: statement_line.is_matched MUST remain False until user confirms
        stmt_line.refresh_from_db()
        assert stmt_line.is_matched is False

        match_rec = BankReconciliationMatch.objects.get(statement_line=stmt_line)
        assert match_rec.match_type == "PROBABLE"

        # Confirm match by user
        BankReconciliationService.confirm_match(match_rec.id, user)
        stmt_line.refresh_from_db()
        assert stmt_line.is_matched is True

