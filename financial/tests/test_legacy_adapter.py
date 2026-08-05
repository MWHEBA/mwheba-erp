import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.test import override_settings

from financial.models import ChartOfAccounts, AccountType, JournalEntry
from financial.services.legacy_adapter import LegacyAccountingAdapter, LegacyAdapterDisabledError
from financial.services.account_role_registry import AccountRoleRegistry

User = get_user_model()


@pytest.mark.django_db(transaction=True)
class TestLegacyAccountingAdapter:

    @pytest.fixture
    def setup_adapter_data(self):
        import uuid
        uid = uuid.uuid4().hex[:6]
        user = User.objects.create_user(username=f"adapter_user_{uid}", password="password123")
        from financial.models import AccountingPeriod
        today = timezone.now().date()
        AccountingPeriod.objects.get_or_create(
            name=f"Period_{today.year}_{today.month}_{uid}",
            start_date=today.replace(day=1),
            end_date=today.replace(day=28),
            defaults={"status": "open"}
        )

        asset_type, _ = AccountType.objects.get_or_create(code=f"ASSET_{uid}", defaults={"name": "Assets", "category": "ASSET"})
        exp_type, _ = AccountType.objects.get_or_create(code=f"EXP_{uid}", defaults={"name": "Expenses", "category": "EXPENSE"})

        cash_acc = ChartOfAccounts.objects.create(code=f"10100_{uid}", name="Cash Account", account_type=asset_type, is_active=True)
        cogs_acc = ChartOfAccounts.objects.create(code=f"50100_{uid}", name="COGS Account", account_type=exp_type, is_active=True)

        return user, cash_acc, cogs_acc

    def test_post_journal_entry_success(self, setup_adapter_data):
        user, cash_acc, cogs_acc = setup_adapter_data

        lines_data = [
            {"account": cogs_acc, "debit": Decimal("500.00"), "credit": Decimal("0.00"), "description": "COGS Line"},
            {"account": cash_acc, "debit": Decimal("0.00"), "credit": Decimal("500.00"), "description": "Cash Line"},
        ]

        entry = LegacyAccountingAdapter.post_journal_entry(
            date=timezone.now().date(),
            description="Test Bridge Transfer Posting",
            reference="REF-BRIDGE-001",
            entry_type="transfer",
            created_by=user,
            lines_data=lines_data,
            source_module="test_module"
        )

        assert entry is not None
        assert entry.reference == "REF-BRIDGE-001"
        assert entry.lines.count() == 2

    def test_idempotency_duplicate_prevention(self, setup_adapter_data):
        user, cash_acc, cogs_acc = setup_adapter_data

        lines_data = [
            {"account": cogs_acc, "debit": Decimal("100.00"), "credit": Decimal("0.00")},
            {"account": cash_acc, "debit": Decimal("0.00"), "credit": Decimal("100.00")},
        ]

        entry1 = LegacyAccountingAdapter.post_journal_entry(
            date=timezone.now().date(),
            description="Duplicate Reference Test",
            reference="REF-DUP-999",
            entry_type="transfer",
            created_by=user,
            lines_data=lines_data,
            source_module="test_module"
        )

        entry2 = LegacyAccountingAdapter.post_journal_entry(
            date=timezone.now().date(),
            description="Duplicate Reference Test",
            reference="REF-DUP-999",
            entry_type="transfer",
            created_by=user,
            lines_data=lines_data,
            source_module="test_module"
        )

        assert entry1.id == entry2.id

    @override_settings(LEGACY_ACCOUNTING_ADAPTER_ENABLED=False)
    def test_adapter_disabled_raises_error(self, setup_adapter_data):
        user, cash_acc, cogs_acc = setup_adapter_data

        lines_data = [
            {"account": cogs_acc, "debit": Decimal("100.00"), "credit": Decimal("0.00")},
            {"account": cash_acc, "debit": Decimal("0.00"), "credit": Decimal("100.00")},
        ]

        with pytest.raises(LegacyAdapterDisabledError):
            LegacyAccountingAdapter.post_journal_entry(
                date=timezone.now().date(),
                description="Disabled Test",
                reference="REF-DIS-001",
                entry_type="transfer",
                created_by=user,
                lines_data=lines_data,
                source_module="test_module"
            )

    def test_account_role_registry(self, setup_adapter_data):
        user, cash_acc, cogs_acc = setup_adapter_data

        acc = AccountRoleRegistry.get_account_by_role("AP_CONTROL_ACCOUNT")
        # Should return existing account or fallback cleanly
        assert acc is None or isinstance(acc, ChartOfAccounts)
