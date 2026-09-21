import pytest
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.utils import timezone

from governance.services.accounting_gateway import AccountingGateway, JournalEntryLineData, SourceInfo
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.treasury_access import UserTreasuryAccess

User = get_user_model()

@pytest.mark.django_db
class TestAccountingGatewayTreasuryGuard:

    @pytest.fixture
    def setup_gateway_data(self):
        superuser, _ = User.objects.get_or_create(username="cfo_user", defaults={"email": "cfo@test.com"})
        if not superuser.is_superuser:
            superuser.is_superuser = True
            superuser.save()
        cashier_deposit_only, _ = User.objects.get_or_create(username="cashier_dep", defaults={"email": "dep@test.com"})
        cashier_disburse, _ = User.objects.get_or_create(username="cashier_disb", defaults={"email": "disb@test.com"})

        cash_type, _ = AccountType.objects.get_or_create(code="CASH", defaults={"name": "نقدي", "category": "asset"})
        rev_type, _ = AccountType.objects.get_or_create(code="REV", defaults={"name": "إيرادات", "category": "revenue"})
        exp_type, _ = AccountType.objects.get_or_create(code="EXP", defaults={"name": "مصروفات", "category": "expense"})

        cash_acc, _ = ChartOfAccounts.objects.get_or_create(code="10101", defaults={"name": "خزينة المقر", "account_type": cash_type, "is_cash_account": True, "is_leaf": True, "is_active": True})
        if not cash_acc.is_cash_account:
            cash_acc.is_cash_account = True
            cash_acc.save()
        rev_acc, _ = ChartOfAccounts.objects.get_or_create(code="41101", defaults={"name": "إيرادات مبيعات", "account_type": rev_type, "is_leaf": True, "is_active": True})
        exp_acc, _ = ChartOfAccounts.objects.get_or_create(code="51101", defaults={"name": "مصروفات عمومية", "account_type": exp_type, "is_leaf": True, "is_active": True})

        # إسناد إيداع فقط للكاشير الأول
        UserTreasuryAccess.objects.filter(user=cashier_deposit_only, treasury=cash_acc).delete()
        UserTreasuryAccess.objects.create(
            user=cashier_deposit_only,
            treasury=cash_acc,
            can_deposit=True,
            can_disburse=False,
        )

        # إسناد صرف للكاشير الثاني بسقف 3000
        UserTreasuryAccess.objects.filter(user=cashier_disburse, treasury=cash_acc).delete()
        UserTreasuryAccess.objects.create(
            user=cashier_disburse,
            treasury=cash_acc,
            can_deposit=False,
            can_disburse=True,
            max_single_disbursement_limit=Decimal("3000.00"),
            daily_disbursement_limit=Decimal("10000.00"),
        )

        return {
            "superuser": superuser,
            "cashier_deposit_only": cashier_deposit_only,
            "cashier_disburse": cashier_disburse,
            "cash_acc": cash_acc,
            "rev_acc": rev_acc,
            "exp_acc": exp_acc,
        }

    def test_deposit_only_user_allowed_to_debit_cash(self, setup_gateway_data):
        user = setup_gateway_data["cashier_deposit_only"]
        cash_acc = setup_gateway_data["cash_acc"]
        rev_acc = setup_gateway_data["rev_acc"]

        gateway = AccountingGateway()
        lines = [
            JournalEntryLineData(account_code=cash_acc.code, debit=Decimal("1000.00"), credit=Decimal("0.00")),
            JournalEntryLineData(account_code=rev_acc.code, debit=Decimal("0.00"), credit=Decimal("1000.00")),
        ]

        entry = gateway.create_journal_entry(
            source_module="financial",
            source_model="ManualJournalEntry",
            source_id=101,
            lines=lines,
            idempotency_key="JE:financial:ManualJournalEntry:101:create",
            user=user,
        )
        assert entry.id is not None
        assert entry.status == "posted"

    def test_deposit_only_user_blocked_from_crediting_cash(self, setup_gateway_data):
        user = setup_gateway_data["cashier_deposit_only"]
        cash_acc = setup_gateway_data["cash_acc"]
        exp_acc = setup_gateway_data["exp_acc"]

        gateway = AccountingGateway()
        lines = [
            JournalEntryLineData(account_code=exp_acc.code, debit=Decimal("500.00"), credit=Decimal("0.00")),
            JournalEntryLineData(account_code=cash_acc.code, debit=Decimal("0.00"), credit=Decimal("500.00")),
        ]

        with pytest.raises(ValidationError) as excinfo:
            gateway.create_journal_entry(
                source_module="financial",
                source_model="ManualJournalEntry",
                source_id=202,
                lines=lines,
                idempotency_key="JE:financial:ManualJournalEntry:202:create",
                user=user,
            )
        assert "صلاحية صرف أو سداد" in str(excinfo.value)

    def test_disbursement_limit_breach_blocked_by_gateway(self, setup_gateway_data):
        user = setup_gateway_data["cashier_disburse"]
        cash_acc = setup_gateway_data["cash_acc"]
        exp_acc = setup_gateway_data["exp_acc"]

        gateway = AccountingGateway()
        lines = [
            JournalEntryLineData(account_code=exp_acc.code, debit=Decimal("4000.00"), credit=Decimal("0.00")),
            JournalEntryLineData(account_code=cash_acc.code, debit=Decimal("0.00"), credit=Decimal("4000.00")),
        ]

        with pytest.raises(ValidationError) as excinfo:
            gateway.create_journal_entry(
                source_module="financial",
                source_model="ManualJournalEntry",
                source_id=303,
                lines=lines,
                idempotency_key="JE:financial:ManualJournalEntry:303:create",
                user=user,
            )
        assert "يتجاوز الحد الأقصى المسموح به للحركة الواحدة" in str(excinfo.value)

    def test_autonomous_system_task_bypass(self, setup_gateway_data):
        user = setup_gateway_data["cashier_deposit_only"]
        cash_acc = setup_gateway_data["cash_acc"]
        exp_acc = setup_gateway_data["exp_acc"]

        gateway = AccountingGateway()
        lines = [
            JournalEntryLineData(account_code=exp_acc.code, debit=Decimal("2000.00"), credit=Decimal("0.00")),
            JournalEntryLineData(account_code=cash_acc.code, debit=Decimal("0.00"), credit=Decimal("2000.00")),
        ]

        entry = gateway.create_journal_entry(
            source_module="financial",
            source_model="ManualJournalEntry",
            source_id=404,
            lines=lines,
            idempotency_key="JE:financial:ManualJournalEntry:404:create",
            user=setup_gateway_data["superuser"],
        )
        assert entry.id is not None
        assert entry.status == "posted"
