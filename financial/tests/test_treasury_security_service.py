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

        acc_type, _ = AccountType.objects.get_or_create(code="CASH", defaults={"name": "نقدي", "category": "asset"})
        if acc_type.category != "asset":
            acc_type.category = "asset"
            acc_type.save()

        bank_type, _ = AccountType.objects.get_or_create(code="BANK", defaults={"name": "بنكي", "category": "asset"})
        if bank_type.category != "asset":
            bank_type.category = "asset"
            bank_type.save()

        cash1, _ = ChartOfAccounts.objects.get_or_create(
            code="10101_TSSERV",
            defaults={
                "name": "خزينة القاهرة",
                "account_type": acc_type,
                "is_cash_account": True,
                "is_leaf": True,
                "is_active": True
            }
        )
        cash2, _ = ChartOfAccounts.objects.get_or_create(
            code="10102_TSSERV",
            defaults={
                "name": "خزينة الإسكندرية",
                "account_type": acc_type,
                "is_cash_account": True,
                "is_leaf": True,
                "is_active": True
            }
        )
        bank1, _ = ChartOfAccounts.objects.get_or_create(
            code="10201_TSSERV",
            defaults={
                "name": "البنك الأهلي",
                "account_type": bank_type,
                "is_bank_account": True,
                "is_leaf": True,
                "is_active": True
            }
        )

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
        assert treasuries.count() >= 3
        assert setup_environment["cash1"] in treasuries
        assert setup_environment["cash2"] in treasuries
        assert setup_environment["bank1"] in treasuries
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

    def test_cash_and_bank_accounts_list_view_assigned_cashier(self, client, setup_environment):
        from django.urls import reverse
        cashier = setup_environment["cashier"]
        client.force_login(cashier)

        response = client.get(reverse("financial:cash_accounts_list"))
        assert response.status_code == 200
        # يجب أن يرى خزنته المسندة إليه فقط (خزينة القاهرة) ولا يرى خزينة الإسكندرية أو البنك
        accounts = list(response.context["accounts"])
        assert len(accounts) == 1
        assert accounts[0].id == setup_environment["cash1"].id

    def test_cash_and_bank_accounts_list_view_unassigned_user_denied(self, client, setup_environment):
        from django.urls import reverse
        restricted = setup_environment["restricted"]
        client.force_login(restricted)

        response = client.get(reverse("financial:cash_accounts_list"))
        assert response.status_code == 403

    def test_cash_account_movements_stealth_security(self, client, setup_environment):
        from django.urls import reverse
        cashier = setup_environment["cashier"]
        client.force_login(cashier)

        # 1. الدخول على خزنته المسندة -> 200 OK
        resp_allowed = client.get(reverse("financial:cash_account_movements", args=[setup_environment["cash1"].id]))
        assert resp_allowed.status_code == 200

        # 2. محاولة الدخول على خزنة غير مسندة -> 404 Not Found (Stealth)
        resp_forbidden = client.get(reverse("financial:cash_account_movements", args=[setup_environment["cash2"].id]))
        assert resp_forbidden.status_code == 404

    def test_assigned_cashier_cannot_perform_treasury_management(self, client, setup_environment):
        from django.urls import reverse
        cashier = setup_environment["cashier"]
        cash1 = setup_environment["cash1"]
        client.force_login(cashier)

        # 1. فحص محاولة فتح صفحة التعديل -> 403
        resp_edit = client.get(reverse("financial:cash_account_edit", args=[cash1.id]))
        assert resp_edit.status_code == 403

        # 2. فحص محاولة التعطيل -> 403
        resp_toggle = client.post(reverse("financial:cash_account_toggle_active", args=[cash1.id]))
        assert resp_toggle.status_code == 403

        # 3. فحص محاولة الحذف -> 403
        resp_delete = client.post(reverse("financial:cash_account_delete", args=[cash1.id]))
        assert resp_delete.status_code == 403

        # 4. فحص محاولة فتح مصفوفة الإسناد -> 403
        resp_assignments = client.get(reverse("financial:treasury_assignments_list"))
        assert resp_assignments.status_code == 403

    def test_cash_account_movements_excel_export(self, client, setup_environment):
        from django.urls import reverse
        cashier = setup_environment["cashier"]
        cash1 = setup_environment["cash1"]
        client.force_login(cashier)

        resp = client.get(reverse("financial:cash_account_movements", args=[cash1.id]), {"export": "excel"})
        assert resp.status_code == 200
        assert resp["Content-Type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        assert "attachment;" in resp["Content-Disposition"]
        assert len(resp.content) > 0

    def test_cash_accounts_list_excel_export(self, client, setup_environment):
        from django.urls import reverse
        cashier = setup_environment["cashier"]
        client.force_login(cashier)

        resp = client.get(reverse("financial:cash_accounts_list"), {"export": "excel"})
        assert resp.status_code == 200
        assert resp["Content-Type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        assert "attachment;" in resp["Content-Disposition"]
        assert len(resp.content) > 0

    def test_assigned_cashier_can_access_exchange_rate_sync_and_lookup(self, client, setup_environment):
        from django.urls import reverse
        cashier = setup_environment["cashier"]
        client.force_login(cashier)

        # 1. فحص endpoint مزامنة أسعار الصرف الرسمية
        resp_sync = client.post(reverse("financial:api_sync_exchange_rates"))
        assert resp_sync.status_code == 200

        # 2. فحص endpoint الاستعلام عن سعر الصرف اللحظي
        resp_lookup = client.get(reverse("financial:api_get_exchange_rate"), {"code": "EGP"})
        assert resp_lookup.status_code == 200




