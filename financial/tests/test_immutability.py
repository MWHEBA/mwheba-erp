import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db import connection, transaction

from financial.models import (
    ChartOfAccounts,
    AccountType,
    AccountingPeriod,
    FiscalYear,
    JournalEntry,
    JournalEntryLine,
    OpeningBalanceBatch,
    OpeningBalanceLine
)
from financial.services import LedgerCoreService, OpeningBalanceService
from financial.exceptions import ImmutableLedgerError, FinancialCoreError

User = get_user_model()


@pytest.mark.django_db
class TestFinancialCoreImmutability:

    @pytest.fixture
    def setup_ledger_data(self):
        user = User.objects.create_user(username="immutability_user", password="password123")
        today = timezone.now().date()

        fiscal_year = FiscalYear.objects.create(
            year_code=f"FY-{today.year}-TEST",
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

        asset_type, _ = AccountType.objects.get_or_create(code="AST_IMM", defaults={"name": "Asset Imm", "category": "asset"})
        revenue_type, _ = AccountType.objects.get_or_create(code="REV_IMM", defaults={"name": "Revenue Imm", "category": "revenue"})

        cash_acc = ChartOfAccounts.objects.create(code="10100_IMM", name="Cash Imm", account_type=asset_type, is_active=True)
        rev_acc = ChartOfAccounts.objects.create(code="40100_IMM", name="Revenue Imm", account_type=revenue_type, is_active=True)

        return user, fiscal_year, period, cash_acc, rev_acc

    def test_orm_save_whitelist_for_reversal(self, setup_ledger_data):
        user, fiscal_year, period, cash_acc, rev_acc = setup_ledger_data

        draft = LedgerCoreService.create_draft_entry(
            date=timezone.now().date(),
            description="Test Immutability Entry",
            reference="REF-IMM-001",
            entry_type="manual",
            created_by=user,
            lines_data=[
                {"account": cash_acc, "debit": Decimal("1000.00"), "credit": Decimal("0.00")},
                {"account": rev_acc, "debit": Decimal("0.00"), "credit": Decimal("1000.00")}
            ]
        )

        posted_entry = LedgerCoreService.post_entry(draft.id, user)
        assert posted_entry.status == "posted"

        # 1. Modifying description on posted entry raises ImmutableLedgerError
        posted_entry.description = "Modified Description"
        with pytest.raises(ImmutableLedgerError):
            posted_entry.save()

        # 2. Updating reversed_by_entry via update_fields=['reversed_by_entry'] succeeds
        reversal_draft = LedgerCoreService.create_draft_entry(
            date=timezone.now().date(),
            description="Reversal Entry",
            reference="REF-REV-001",
            entry_type="manual",
            created_by=user,
            lines_data=[
                {"account": cash_acc, "debit": Decimal("0.00"), "credit": Decimal("1000.00")},
                {"account": rev_acc, "debit": Decimal("1000.00"), "credit": Decimal("0.00")}
            ]
        )
        reversal_posted = LedgerCoreService.post_entry(reversal_draft.id, user)

        posted_entry.reversed_by_entry = reversal_posted
        posted_entry.save(update_fields=["reversed_by_entry"])
        posted_entry.refresh_from_db()
        assert posted_entry.reversed_by_entry_id == reversal_posted.id

    def test_journal_entry_header_vs_line_immutability(self, setup_ledger_data):
        user, fiscal_year, period, cash_acc, rev_acc = setup_ledger_data

        draft = LedgerCoreService.create_draft_entry(
            date=timezone.now().date(),
            description="Line Immutability Entry",
            reference="REF-LINE-IMM",
            entry_type="manual",
            created_by=user,
            lines_data=[
                {"account": cash_acc, "debit": Decimal("500.00"), "credit": Decimal("0.00")},
                {"account": rev_acc, "debit": Decimal("0.00"), "credit": Decimal("500.00")}
            ]
        )
        posted_entry = LedgerCoreService.post_entry(draft.id, user)

        # Inserting line to posted entry fails
        line = JournalEntryLine(journal_entry=posted_entry, account=cash_acc, debit=Decimal("100.00"), credit=Decimal("0.00"))
        with pytest.raises(ImmutableLedgerError):
            line.save()

        # Deleting posted entry fails
        with pytest.raises(ImmutableLedgerError):
            posted_entry.delete()

        # Deleting existing line of posted entry fails
        existing_line = posted_entry.lines.first()
        with pytest.raises(ImmutableLedgerError):
            existing_line.delete()

    def test_opening_balance_batch_immutability(self, setup_ledger_data):
        user, fiscal_year, period, cash_acc, rev_acc = setup_ledger_data

        batch = OpeningBalanceBatch.objects.create(
            fiscal_year=fiscal_year,
            batch_number="OP-BATCH-TEST-100",
            description="Test Opening Balance Batch",
            status="draft"
        )
        line = OpeningBalanceLine.objects.create(
            batch=batch,
            account=cash_acc,
            debit=Decimal("5000.00"),
            credit=Decimal("0.00")
        )
        line2 = OpeningBalanceLine.objects.create(
            batch=batch,
            account=rev_acc,
            debit=Decimal("0.00"),
            credit=Decimal("5000.00")
        )

        posted_batch = OpeningBalanceService.post_batch(batch.id, user)
        assert posted_batch.status == "posted"

        with pytest.raises(ImmutableLedgerError):
            posted_batch.description = "Updated description"
            posted_batch.save()

        with pytest.raises(ImmutableLedgerError):
            posted_batch.delete()

        with pytest.raises(ImmutableLedgerError):
            line.debit = Decimal("6000.00")
            line.save()

        with pytest.raises(ImmutableLedgerError):
            line.delete()

    def test_direct_sql_posted_entry_update_blocked(self, setup_ledger_data):
        user, fiscal_year, period, cash_acc, rev_acc = setup_ledger_data

        draft = LedgerCoreService.create_draft_entry(
            date=timezone.now().date(),
            description="SQL Bypass Test",
            reference="REF-SQL-001",
            entry_type="manual",
            created_by=user,
            lines_data=[
                {"account": cash_acc, "debit": Decimal("300.00"), "credit": Decimal("0.00")},
                {"account": rev_acc, "debit": Decimal("0.00"), "credit": Decimal("300.00")}
            ]
        )
        posted_entry = LedgerCoreService.post_entry(draft.id, user)

        if connection.vendor == 'postgresql':
            with pytest.raises(Exception) as exc_info:
                with connection.cursor() as cursor:
                    cursor.execute("UPDATE financial_journalentry SET description = %s WHERE id = %s", ["Hacked Description", posted_entry.id])
            assert "IMMUTABLE_LEDGER_ERROR" in str(exc_info.value)
        else:
            with pytest.raises(ImmutableLedgerError):
                posted_entry.description = "Hacked via ORM"
                posted_entry.save()

    def test_direct_sql_posted_line_insert_blocked(self, setup_ledger_data):
        user, fiscal_year, period, cash_acc, rev_acc = setup_ledger_data

        draft = LedgerCoreService.create_draft_entry(
            date=timezone.now().date(),
            description="SQL Line Insert Test",
            reference="REF-SQL-LINE-001",
            entry_type="manual",
            created_by=user,
            lines_data=[
                {"account": cash_acc, "debit": Decimal("400.00"), "credit": Decimal("0.00")},
                {"account": rev_acc, "debit": Decimal("0.00"), "credit": Decimal("400.00")}
            ]
        )
        posted_entry = LedgerCoreService.post_entry(draft.id, user)

        if connection.vendor == 'postgresql':
            with pytest.raises(Exception) as exc_info:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO financial_journalentryline (journal_entry_id, account_id, debit, credit, created_at) VALUES (%s, %s, %s, %s, NOW())",
                        [posted_entry.id, cash_acc.id, Decimal("100.00"), Decimal("0.00")]
                    )
            assert "IMMUTABLE_LEDGER_ERROR" in str(exc_info.value)
        else:
            line = JournalEntryLine(journal_entry=posted_entry, account=cash_acc, debit=Decimal("100.00"), credit=Decimal("0.00"))
            with pytest.raises(ImmutableLedgerError):
                line.save()
