import pytest
from django.test import RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.http import Http404

from core.context_processors import payment_accounts
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.treasury_access import UserTreasuryAccess
from financial.views.account_views import cash_account_movements, chart_of_accounts_detail

User = get_user_model()

@pytest.mark.django_db
class TestTreasuryStealthSecurity:

    @pytest.fixture
    def setup_stealth(self):
        factory = RequestFactory()
        user1 = User.objects.create_user(username="cashier_alex", email="cashier_alex@test.com", password="password123")
        user2 = User.objects.create_user(username="cashier_cairo", email="cashier_cairo@test.com", password="password123")

        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType

        ct = ContentType.objects.get_for_model(ChartOfAccounts)
        perm, _ = Permission.objects.get_or_create(codename="view_chartofaccounts", content_type=ct)
        user1.user_permissions.add(perm)
        user2.user_permissions.add(perm)

        acc_type, _ = AccountType.objects.get_or_create(code="CASH", name="نقدي", category="asset")
        cash_alex = ChartOfAccounts.objects.create(code="10101", name="خزينة الإسكندرية", account_type=acc_type, is_cash_account=True, is_leaf=True, is_active=True)
        cash_cairo = ChartOfAccounts.objects.create(code="10102", name="خزينة القاهرة السرية", account_type=acc_type, is_cash_account=True, is_leaf=True, is_active=True)

        UserTreasuryAccess.objects.create(user=user1, treasury=cash_alex, can_deposit=True, can_disburse=True, is_default=True)
        UserTreasuryAccess.objects.create(user=user2, treasury=cash_cairo, can_deposit=True, can_disburse=True, is_default=True)

        return {
            "factory": factory,
            "user1": user1,
            "user2": user2,
            "cash_alex": cash_alex,
            "cash_cairo": cash_cairo,
        }

    def test_anonymous_user_context_processor(self, setup_stealth):
        request = setup_stealth["factory"].get("/")
        request.user = AnonymousUser()

        ctx = payment_accounts(request)
        assert ctx["payment_accounts"] == []
        assert ctx["cash_payment_accounts"] == []
        assert ctx["default_payment_account"] is None

    def test_context_processor_stealth_isolation(self, setup_stealth):
        user1 = setup_stealth["user1"]
        request = setup_stealth["factory"].get("/")
        request.user = user1

        ctx = payment_accounts(request)
        account_ids = [a["id"] for a in ctx["payment_accounts"]]
        assert setup_stealth["cash_alex"].id in account_ids
        assert setup_stealth["cash_cairo"].id not in account_ids

    def test_stealth_404_on_unauthorized_ledger_detail(self, setup_stealth):
        user1 = setup_stealth["user1"]
        hidden_treasury = setup_stealth["cash_cairo"]

        request = setup_stealth["factory"].get(f"/financial/accounts/{hidden_treasury.id}/")
        request.user = user1

        with pytest.raises(Http404):
            chart_of_accounts_detail(request, pk=hidden_treasury.id)

    def test_stealth_404_on_unauthorized_cash_movements(self, setup_stealth):
        user1 = setup_stealth["user1"]
        hidden_treasury = setup_stealth["cash_cairo"]

        request = setup_stealth["factory"].get(f"/financial/cash-accounts/{hidden_treasury.id}/movements/")
        request.user = user1

        with pytest.raises(Http404):
            cash_account_movements(request, pk=hidden_treasury.id)
