import pytest
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth import get_user_model
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.treasury_access import UserTreasuryAccess, TreasuryAccessAuditLog

User = get_user_model()

@pytest.mark.django_db
class TestUserTreasuryAccessModel:

    @pytest.fixture
    def setup_data(self):
        user1 = User.objects.create_user(username="cashier1", email="cashier1@test.com", password="password123")
        user2 = User.objects.create_user(username="cashier2", email="cashier2@test.com", password="password123")
        
        acc_type, _ = AccountType.objects.get_or_create(code="CASH", name="نقدي", category="asset")
        treasury1 = ChartOfAccounts.objects.create(
            code="10101",
            name="خزينة الفرع الرئيسي",
            account_type=acc_type,
            is_cash_account=True,
            is_leaf=True,
            is_active=True
        )
        treasury2 = ChartOfAccounts.objects.create(
            code="10102",
            name="خزينة فرع المعادي",
            account_type=acc_type,
            is_cash_account=True,
            is_leaf=True,
            is_active=True
        )
        return {
            "user1": user1,
            "user2": user2,
            "treasury1": treasury1,
            "treasury2": treasury2,
        }

    def test_create_valid_access(self, setup_data):
        user = setup_data["user1"]
        trsy = setup_data["treasury1"]
        
        access = UserTreasuryAccess.objects.create(
            user=user,
            treasury=trsy,
            can_deposit=True,
            can_disburse=True,
            max_single_disbursement_limit=Decimal("5000.00"),
            daily_disbursement_limit=Decimal("20000.00"),
        )
        access.clean()
        assert access.id is not None
        assert access.can_deposit is True
        assert access.can_disburse is True
        assert access.is_currently_valid() is True
        assert access.has_deposit_permission() is True
        assert access.has_disburse_permission() is True

    def test_validation_error_on_no_permissions(self, setup_data):
        user = setup_data["user1"]
        trsy = setup_data["treasury1"]
        
        access = UserTreasuryAccess(
            user=user,
            treasury=trsy,
            can_deposit=False,
            can_disburse=False,
        )
        with pytest.raises(ValidationError):
            access.clean()

    def test_validation_error_on_invalid_dates(self, setup_data):
        user = setup_data["user1"]
        trsy = setup_data["treasury1"]
        today = timezone.now().date()
        
        access = UserTreasuryAccess(
            user=user,
            treasury=trsy,
            can_deposit=True,
            valid_from=today + timezone.timedelta(days=10),
            valid_until=today,
        )
        with pytest.raises(ValidationError):
            access.clean()

    def test_validation_error_on_single_limit_greater_than_daily(self, setup_data):
        user = setup_data["user1"]
        trsy = setup_data["treasury1"]
        
        access = UserTreasuryAccess(
            user=user,
            treasury=trsy,
            can_disburse=True,
            max_single_disbursement_limit=Decimal("15000.00"),
            daily_disbursement_limit=Decimal("10000.00"),
        )
        with pytest.raises(ValidationError):
            access.clean()

    def test_unique_user_treasury_constraint(self, setup_data):
        user = setup_data["user1"]
        trsy = setup_data["treasury1"]
        
        UserTreasuryAccess.objects.create(
            user=user,
            treasury=trsy,
            can_deposit=True,
        )
        with pytest.raises(Exception):
            UserTreasuryAccess.objects.create(
                user=user,
                treasury=trsy,
                can_disburse=True,
            )

    def test_treasury_access_audit_log(self, setup_data):
        user = setup_data["user1"]
        trsy = setup_data["treasury1"]
        
        log = TreasuryAccessAuditLog.objects.create(
            user=user,
            treasury=trsy,
            action="ASSIGNED",
            new_permissions={"can_deposit": True, "can_disburse": False},
            book_balance_at_change=Decimal("10000.00"),
        )
        assert log.id is not None
        assert log.action == "ASSIGNED"
        assert log.book_balance_at_change == Decimal("10000.00")
