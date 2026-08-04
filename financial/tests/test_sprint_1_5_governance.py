import pytest
import inspect
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db import transaction

from financial.models import (
    ChartOfAccounts,
    AccountType,
    FiscalYear,
    AccountingPeriod,
    JournalEntry,
    JournalEntryLine,
    FinancialPostingReference
)
from financial.services import LedgerCoreService
from financial.exceptions import ImmutableLedgerError, FinancialCoreError
from governance.services.accounting_gateway import AccountingGateway, JournalEntryLineData

User = get_user_model()


@pytest.mark.django_db
class TestSprint15Governance:

    @pytest.fixture
    def setup_governance_data(self):
        user = User.objects.create_user(username="gov_user_15", password="password123")
        today = timezone.now().date()

        fiscal_year = FiscalYear.objects.create(
            year_code=f"FY-{today.year}-GOV",
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

        asset_type, _ = AccountType.objects.get_or_create(code="AST_GOV", defaults={"name": "Asset Gov", "category": "asset"})
        revenue_type, _ = AccountType.objects.get_or_create(code="REV_GOV", defaults={"name": "Revenue Gov", "category": "revenue"})

        cash_acc = ChartOfAccounts.objects.create(code="10100_GOV", name="Cash Gov", account_type=asset_type, is_active=True)
        rev_acc = ChartOfAccounts.objects.create(code="40100_GOV", name="Revenue Gov", account_type=revenue_type, is_active=True)

        return user, fiscal_year, period, cash_acc, rev_acc

    def test_gateway_has_no_direct_journal_writes(self):
        """CI Protection Test: Ensures AccountingGateway has 0 direct JournalEntry.objects.create calls"""
        gateway_source = inspect.getsource(AccountingGateway._create_journal_entry_atomic)
        assert "JournalEntry.objects.create(" not in gateway_source, "AccountingGateway must delegate creation to LedgerCoreService"
        assert "JournalEntry(" not in gateway_source, "AccountingGateway must not instantiate JournalEntry directly"

    def test_gateway_facade_delegation(self, setup_governance_data):
        """Verify AccountingGateway delegates entry creation and posting 100% to LedgerCoreService"""
        user, fiscal_year, period, cash_acc, rev_acc = setup_governance_data
        gateway = AccountingGateway()

        from financial.models import FinancialTransaction
        txn = FinancialTransaction.objects.create(
            transaction_type="income",
            account=cash_acc,
            amount=Decimal("2000.00"),
            date=timezone.now().date(),
            title="Facade Transaction",
            status="approved",
            created_by=user
        )

        lines = [
            JournalEntryLineData(account_code=cash_acc.code, debit=Decimal("2000.00"), credit=Decimal("0.00"), description="Sale Cash"),
            JournalEntryLineData(account_code=rev_acc.code, debit=Decimal("0.00"), credit=Decimal("2000.00"), description="Sale Revenue")
        ]

        posted_entry = gateway.create_journal_entry(
            source_module="financial",
            source_model="FinancialTransaction",
            source_id=txn.id,
            lines=lines,
            idempotency_key=f"JE:financial:FinancialTransaction:{txn.id}:create",
            user=user,
            entry_type="automatic",
            description="Facade Delegation Test",
            reference="FACADE-999"
        )

        assert posted_entry is not None
        assert posted_entry.status == "posted"
        assert posted_entry.posting_source == "FINANCIAL_FINANCIALTRANSACTION"
        assert posted_entry.lines.count() == 2

    def test_posting_reference_idempotency_concurrency(self, setup_governance_data):
        """Verify duplicate posting attempt with same (source_type, source_id, posting_type) is rejected via atomic DB constraint"""
        user, fiscal_year, period, cash_acc, rev_acc = setup_governance_data

        draft1 = LedgerCoreService.create_draft_entry(
            date=timezone.now().date(),
            description="First Posting Attempt",
            reference="REF-IDEMP-001",
            entry_type="manual",
            created_by=user,
            lines_data=[
                {"account": cash_acc, "debit": Decimal("1000.00"), "credit": Decimal("0.00")},
                {"account": rev_acc, "debit": Decimal("0.00"), "credit": Decimal("1000.00")}
            ]
        )

        posted1 = LedgerCoreService.post_entry(
            entry_id=draft1.id,
            user=user,
            posting_source="SALE_INVOICE",
            source_type="SALE_INVOICE",
            source_id="INV-2025-100",
            posting_type="MAIN"
        )
        assert posted1.status == "posted"
        assert FinancialPostingReference.objects.filter(source_type="SALE_INVOICE", source_id="INV-2025-100", posting_type="MAIN").exists()

        draft2 = LedgerCoreService.create_draft_entry(
            date=timezone.now().date(),
            description="Duplicate Posting Attempt",
            reference="REF-IDEMP-002",
            entry_type="manual",
            created_by=user,
            lines_data=[
                {"account": cash_acc, "debit": Decimal("1000.00"), "credit": Decimal("0.00")},
                {"account": rev_acc, "debit": Decimal("0.00"), "credit": Decimal("1000.00")}
            ]
        )

        with pytest.raises(FinancialCoreError) as exc_info:
            LedgerCoreService.post_entry(
                entry_id=draft2.id,
                user=user,
                posting_source="SALE_INVOICE",
                source_type="SALE_INVOICE",
                source_id="INV-2025-100",
                posting_type="MAIN"
            )
        assert "DUPLICATE_POSTING_BLOCKED" in str(exc_info.value)

    def test_original_entry_source_of_truth(self, setup_governance_data):
        """Verify original_entry is primary Source of Truth for reversal entries"""
        user, fiscal_year, period, cash_acc, rev_acc = setup_governance_data

        draft = LedgerCoreService.create_draft_entry(
            date=timezone.now().date(),
            description="Original Sales Transaction",
            reference="REF-TRUTH-001",
            entry_type="sale",
            created_by=user,
            lines_data=[
                {"account": cash_acc, "debit": Decimal("3000.00"), "credit": Decimal("0.00")},
                {"account": rev_acc, "debit": Decimal("0.00"), "credit": Decimal("3000.00")}
            ]
        )
        original_entry = LedgerCoreService.post_entry(draft.id, user, posting_source="SALE_INVOICE", posting_reference="INV-3000")

        reversal_entry = LedgerCoreService.reverse_entry(
            entry_id=original_entry.id,
            user=user,
            reversal_reason="Customer return order"
        )

        assert reversal_entry.is_reversal is True
        assert reversal_entry.original_entry_id == original_entry.id
        assert reversal_entry.posting_source == "REVERSAL"

        original_entry.refresh_from_db()
        assert original_entry.reversed_by_entry_id == reversal_entry.id

    def test_posted_status_change_strictly_blocked(self, setup_governance_data):
        """Verify ORM attempt to change posted entry status to draft or cancelled raises ImmutableLedgerError"""
        user, fiscal_year, period, cash_acc, rev_acc = setup_governance_data

        draft = LedgerCoreService.create_draft_entry(
            date=timezone.now().date(),
            description="Strict Status Lock Test",
            reference="REF-LOCK-001",
            entry_type="manual",
            created_by=user,
            lines_data=[
                {"account": cash_acc, "debit": Decimal("500.00"), "credit": Decimal("0.00")},
                {"account": rev_acc, "debit": Decimal("0.00"), "credit": Decimal("500.00")}
            ]
        )
        posted_entry = LedgerCoreService.post_entry(draft.id, user)

        posted_entry.status = "draft"
        with pytest.raises(ImmutableLedgerError):
            posted_entry.save(update_fields=["status"])

        posted_entry.status = "cancelled"
        with pytest.raises(ImmutableLedgerError):
            posted_entry.save(update_fields=["status"])
