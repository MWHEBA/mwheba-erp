import pytest
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.utils import timezone
from django.contrib.auth import get_user_model

from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.treasury_access import UserTreasuryAccess
from financial.services.treasury_security_service import TreasurySecurityService

User = get_user_model()

@pytest.mark.django_db
class TestTreasurySecurityService:

    @pytest.fixture
    def setup_environment(self):
        cache.clear()
        superuser = User.objects.create_superuser(username="admin_cfo", email="admin_cfo@corp.local", password="password123")
        cashier = User.objects.create_user(username="cashier_cairo", email="cashier_cairo@corp.local", password="password123")
        restricted = User.objects.create_user(username="unassigned_user", email="unassigned_user@corp.local", password="password123")

        acc_type, _ = AccountType.objects.get_or_create(code="CASH", name="نقدي", category="asset")
        bank_type, _ = AccountType.objects.get_or_create(code="BANK", name="بنكي", category="asset")

        cash1 = ChartOfAccounts.objects.create(code="10101", name="خزينة القاهرة", account_type=acc_type, is_cash_account=True, is_leaf=True, is_active=True)
        cash2 = ChartOfAccounts.objects.create(code="10102", name="خزينة الإسكندرية", account_type=acc_type, is_cash_account=True, is_leaf=True, is_active=True)
        bank1 = ChartOfAccounts.objects.create(code="10201", name="البنك الأهلي", account_type=bank_type, is_bank_account=True, is_leaf=True, is_active=True)

        # إسناد خزينة القاهرة فقط للكاشير (إيداع + صرف بحد أقصى 5000)
        UserTreasuryAccess.objects.create(
            user=cashier,
            treasury=cash1,
            can_deposit=True,
            can_disburse=True,
            max_single_disbursement_limit=Decimal("5000.00"),
            daily_disbursement_limit=Decimal("15000.00"),
            is_default=True
        )

        return {
            "superuser": superuser,
            "cashier": cashier,
            "restricted": restricted,
            "cash1": cash1,
            "cash2": cash2,
            "bank1": bank1,
        }

    def test_superuser_has_full_access(self, setup_environment):
        su = setup_environment["superuser"]
        treasuries = TreasurySecurityService.get_user_accessible_treasuries(su, action="any")
        assert treasuries.count() == 3
        assert TreasurySecurityService.can_user_deposit(su, setup_environment["cash1"].id) is True
        assert TreasurySecurityService.can_user_deposit(su, setup_environment["cash2"].id) is True

    def test_cashier_granular_access(self, setup_environment):
        cashier = setup_environment["cashier"]
        cash1 = setup_environment["cash1"]
        cash2 = setup_environment["cash2"]

        allowed = TreasurySecurityService.get_user_accessible_treasuries(cashier, action="any")
        assert allowed.count() == 1
        assert allowed.first().id == cash1.id

        assert TreasurySecurityService.can_user_deposit(cashier, cash1.id) is True
        assert TreasurySecurityService.can_user_deposit(cashier, cash2.id) is False

    def test_unassigned_user_has_zero_access(self, setup_environment):
        restricted = setup_environment["restricted"]
        allowed = TreasurySecurityService.get_user_accessible_treasuries(restricted, action="any")
        assert allowed.count() == 0

    def test_single_disbursement_limit_enforcement(self, setup_environment):
        cashier = setup_environment["cashier"]
        cash1 = setup_environment["cash1"]

        # الصرف في حدود 5000 مسموح
        can_disb, msg = TreasurySecurityService.can_user_disburse(cashier, cash1.id, amount=Decimal("4500.00"))
        assert can_disb is True

        # تجاوز 5000 مرفوض
        can_disb, msg = TreasurySecurityService.can_user_disburse(cashier, cash1.id, amount=Decimal("5500.00"))
        assert can_disb is False
        assert "يتجاوز الحد الأقصى المسموح به للحركة الواحدة" in msg

        with pytest.raises(ValidationError):
            TreasurySecurityService.enforce_disbursement(cashier, cash1.id, amount=Decimal("6000.00"))

    def test_time_window_validity(self, setup_environment):
        cashier = setup_environment["cashier"]
        cash2 = setup_environment["cash2"]
        today = timezone.now().date()

        # إسناد مؤقت منتهي الصلاحية
        access = UserTreasuryAccess.objects.create(
            user=cashier,
            treasury=cash2,
            can_deposit=True,
            valid_from=today - timezone.timedelta(days=10),
            valid_until=today - timezone.timedelta(days=1),
        )

        assert TreasurySecurityService.can_user_deposit(cashier, cash2.id) is False
        assert access.is_currently_valid() is False

    def test_cache_invalidation_signal(self, setup_environment):
        cashier = setup_environment["cashier"]
        cache_key = TreasurySecurityService.get_cache_key(cashier.id)
        cache.set(cache_key, {"dummy": "data"}, 600)

        # تعديل الإسناد يجب أن يفرغ الكاش
        access = UserTreasuryAccess.objects.get(user=cashier, treasury=setup_environment["cash1"])
        access.can_disburse = False
        access.save()

        assert cache.get(cache_key) is None
