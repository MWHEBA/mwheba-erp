import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.test import override_settings

from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.journal_entry import JournalEntry, JournalEntryLine
from financial.services.legacy_adapter import LegacyAccountingAdapter, LegacyAdapterDisabledError

User = get_user_model()


@pytest.mark.django_db
class TestLegacyAccountingAdapterHardening:

    @pytest.fixture
    def setup_accounts_and_user(self):
        from financial.models import AccountType, AccountingPeriod
        user = User.objects.create_user(username="test_adapter_user", password="password123")
        
        today = timezone.now().date()
        start = today.replace(day=1)
        end = today.replace(day=28)
        AccountingPeriod.objects.get_or_create(
            name=f"Period Test {today.year}-{today.month}",
            defaults={
                "start_date": start,
                "end_date": end,
                "status": "open"
            }
        )
        asset_type, _ = AccountType.objects.get_or_create(
            code="AST",
            defaults={"name": "Asset Test", "category": "asset"}
        )
        expense_type, _ = AccountType.objects.get_or_create(
            code="EXT",
            defaults={"name": "Expense Test", "category": "expense"}
        )
        cash_account = ChartOfAccounts.objects.create(
            code="10101T",
            name="Cash Account Test",
            account_type=asset_type
        )
        expense_account = ChartOfAccounts.objects.create(
            code="50101T",
            name="Expense Account Test",
            account_type=expense_type
        )
        return user, cash_account, expense_account

    def test_post_journal_entry_success(self, setup_accounts_and_user):
        user, cash_account, expense_account = setup_accounts_and_user

        lines_data = [
            {"account": expense_account, "debit": Decimal("500.00"), "credit": Decimal("0.00"), "description": "Expense Line"},
            {"account": cash_account, "debit": Decimal("0.00"), "credit": Decimal("500.00"), "description": "Cash Line"}
        ]

        entry = LegacyAccountingAdapter.post_journal_entry(
            date=timezone.now().date(),
            description="Test Adapter Entry",
            reference="REF-ADAPTER-SUCCESS",
            entry_type="manual",
            created_by=user,
            lines_data=lines_data,
            source_module="test_module"
        )

        assert isinstance(entry, JournalEntry)
        assert entry.reference == "REF-ADAPTER-SUCCESS"
        assert entry.lines.count() == 2
        assert sum(line.debit for line in entry.lines.all()) == Decimal("500.00")

    def test_transaction_rollback_on_exception(self, setup_accounts_and_user):
        user, cash_account, expense_account = setup_accounts_and_user

        initial_entries_count = JournalEntry.objects.count()
        initial_lines_count = JournalEntryLine.objects.count()

        invalid_lines_data = [
            {"account": expense_account, "debit": Decimal("100.00"), "credit": Decimal("0.00"), "description": "Valid Line"},
            {"account": "NON_EXISTENT_ACCOUNT_OBJECT", "debit": Decimal("0.00"), "credit": Decimal("100.00"), "description": "Invalid Line"}
        ]

        with pytest.raises(Exception):
            LegacyAccountingAdapter.post_journal_entry(
                date=timezone.now().date(),
                description="Test Rollback Entry",
                reference="REF-ROLLBACK-1",
                entry_type="manual",
                created_by=user,
                lines_data=invalid_lines_data,
                source_module="test_rollback"
            )

        assert JournalEntry.objects.count() == initial_entries_count
        assert JournalEntryLine.objects.count() == initial_lines_count

    def test_duplicate_posting_protection(self, setup_accounts_and_user):
        user, cash_account, expense_account = setup_accounts_and_user

        lines_data = [
            {"account": expense_account, "debit": Decimal("250.00"), "credit": Decimal("0.00"), "description": "Line 1"},
            {"account": cash_account, "debit": Decimal("0.00"), "credit": Decimal("250.00"), "description": "Line 2"}
        ]

        entry1 = LegacyAccountingAdapter.post_journal_entry(
            date=timezone.now().date(),
            description="First Posting",
            reference="REF-DUP-PROTECT-100",
            entry_type="transfer",
            created_by=user,
            lines_data=lines_data,
            source_module="test_dup"
        )

        entry2 = LegacyAccountingAdapter.post_journal_entry(
            date=timezone.now().date(),
            description="Duplicate Posting Attempt",
            reference="REF-DUP-PROTECT-100",
            entry_type="transfer",
            created_by=user,
            lines_data=lines_data,
            source_module="test_dup"
        )

        assert entry1.id == entry2.id
        assert JournalEntry.objects.filter(reference="REF-DUP-PROTECT-100").count() == 1

    @override_settings(LEGACY_ACCOUNTING_ADAPTER_ENABLED=False)
    def test_adapter_disabled_feature_flag_raises_error(self, setup_accounts_and_user):
        user, cash_account, expense_account = setup_accounts_and_user
        assert LegacyAccountingAdapter.is_enabled() is False

        lines_data = [
            {"account": expense_account, "debit": Decimal("50.00"), "credit": Decimal("0.00"), "description": "Flag Disabled Line"}
        ]

        with pytest.raises(LegacyAdapterDisabledError) as exc_info:
            LegacyAccountingAdapter.post_journal_entry(
                date=timezone.now().date(),
                description="Test Disabled Flag",
                reference="REF-FLAG-ERR",
                entry_type="manual",
                created_by=user,
                lines_data=lines_data,
                source_module="test_flag"
            )

        assert "LEGACY_ACCOUNTING_ADAPTER_ENABLED is False" in str(exc_info.value)
