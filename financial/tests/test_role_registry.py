import os
import pytest
from decimal import Decimal
from django.test import RequestFactory, override_settings
from django.core.cache import cache

from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models import AccountType
from financial.services.role_registry import (
    AccountRoleRegistry,
    AccountRoleNames,
    RoleConfigurationError,
    LEGACY_ROLE_FALLBACKS
)
from core.context_processors import payment_accounts as cp_payment_accounts
from core.context_processors_optimized import payment_accounts as cp_opt_payment_accounts
from supplier.forms import SupplierAccountChangeForm
from supplier.models import Supplier
from supplier.services.supplier_service import SupplierService


@pytest.mark.django_db
class TestAccountRoleRegistryAndContextProcessors:

    @pytest.fixture
    def setup_asset_and_liability_types(self):
        asset_type, _ = AccountType.objects.get_or_create(
            code="AST_ROLE",
            defaults={"name": "Asset Role Test", "category": "asset"}
        )
        liability_type, _ = AccountType.objects.get_or_create(
            code="LIAB_ROLE",
            defaults={"name": "Liability Role Test", "category": "liability"}
        )
        return asset_type, liability_type

    def test_supplier_service_account_creation_and_subaccount_generation(self, setup_asset_and_liability_types, monkeypatch):
        asset_type, liability_type = setup_asset_and_liability_types
        from supplier.models import SupplierType

        supp_type, _ = SupplierType.objects.get_or_create(code="COMP_TEST", defaults={"name": "Company Test"})

        control_account = ChartOfAccounts.objects.create(
            code="20199",
            name="Supplier Control Dynamic Test",
            account_type=liability_type,
            is_active=True
        )

        monkeypatch.setenv("ACCOUNT_ROLE_SUPPLIER_PAYABLE_CONTROL", "20199")

        supplier = Supplier.objects.create(
            name="مورد جديد للتجربة",
            code="SUPP_TEST_100",
            primary_type=supp_type
        )

        acc = SupplierService.create_financial_account_for_supplier(supplier)

        assert acc is not None
        assert acc.parent == control_account
        assert acc.code.startswith("2019")
        assert len(acc.code) == 8

    def test_supplier_service_missing_control_account_raises_error(self, monkeypatch):
        from supplier.models import SupplierType
        supp_type, _ = SupplierType.objects.get_or_create(code="COMP_TEST", defaults={"name": "Company Test"})
        monkeypatch.setenv("ACCOUNT_ROLE_SUPPLIER_PAYABLE_CONTROL", "NON_EXISTENT_999")

        supplier = Supplier.objects.create(
            name="مورد مفقود الحساب",
            code="SUPP_MISSING_101",
            primary_type=supp_type
        )

        with pytest.raises(RoleConfigurationError):
            SupplierService.create_financial_account_for_supplier(supplier)

    def test_supplier_form_account_resolution_and_rendering(self, setup_asset_and_liability_types, monkeypatch):
        asset_type, liability_type = setup_asset_and_liability_types

        supplier_control = ChartOfAccounts.objects.create(
            code="20199_SUPP",
            name="Supplier Control Test Account",
            account_type=liability_type,
            is_active=True
        )
        sub_supplier_account = ChartOfAccounts.objects.create(
            code="20199_SUB1",
            name="Sub Supplier Account 1",
            account_type=liability_type,
            parent=supplier_control,
            is_active=True,
            is_leaf=True
        )

        monkeypatch.setenv("ACCOUNT_ROLE_SUPPLIER_PAYABLE_CONTROL", "20199_SUPP")

        form = SupplierAccountChangeForm()
        assert "financial_account" in form.fields
        queryset_codes = set(form.fields["financial_account"].queryset.values_list("code", flat=True))
        assert "20199_SUB1" in queryset_codes

    def test_resolved_account_exists_and_is_active(self, setup_asset_and_liability_types):
        asset_type, _ = setup_asset_and_liability_types
        created_account = ChartOfAccounts.objects.create(
            code="10100",
            name="Default Cash Drawer Active Account",
            account_type=asset_type,
            is_active=True
        )

        account = AccountRoleRegistry.get_account(AccountRoleNames.DEFAULT_CASH_DRAWER)

        assert account is not None
        assert account.pk == created_account.pk
        assert account.code == "10100"
        assert account.is_active is True
        assert account.account_type is not None
        assert account.account_type.code == "AST_ROLE"

    def test_legacy_fallback_resolution_priority_3(self, setup_asset_and_liability_types):
        asset_type, _ = setup_asset_and_liability_types
        ChartOfAccounts.objects.create(
            code="10100",
            name="Default Cash Drawer Account",
            account_type=asset_type,
            is_active=True
        )

        resolved_code = AccountRoleRegistry.resolve_role_code(AccountRoleNames.DEFAULT_CASH_DRAWER)
        assert resolved_code == "10100"

        account = AccountRoleRegistry.get_account(AccountRoleNames.DEFAULT_CASH_DRAWER)
        assert isinstance(account, ChartOfAccounts)
        assert account.code == "10100"

    def test_env_resolution_priority_2(self, monkeypatch, setup_asset_and_liability_types):
        asset_type, _ = setup_asset_and_liability_types
        ChartOfAccounts.objects.create(
            code="10199_ENV",
            name="ENV Cash Account",
            account_type=asset_type,
            is_active=True
        )

        monkeypatch.setenv("ACCOUNT_ROLE_DEFAULT_CASH_DRAWER", "10199_ENV")

        resolved_code = AccountRoleRegistry.resolve_role_code(AccountRoleNames.DEFAULT_CASH_DRAWER)
        assert resolved_code == "10199_ENV"

        account = AccountRoleRegistry.get_account(AccountRoleNames.DEFAULT_CASH_DRAWER)
        assert account.code == "10199_ENV"

    def test_role_naming_consistency_validation(self):
        validated = AccountRoleRegistry.validate_role_name(AccountRoleNames.DEFAULT_CASH_DRAWER)
        assert validated == "default_cash_drawer"

        validated_custom = AccountRoleRegistry.validate_role_name("custom_role_name")
        assert validated_custom == "custom_role_name"

    def test_unmapped_role_raises_configuration_error(self):
        with pytest.raises(RoleConfigurationError) as exc_info:
            AccountRoleRegistry.resolve_role_code("UNKNOWN_ROLE_CODE_xyz")

        assert "Missing account role configuration" in str(exc_info.value)

    def test_empty_role_raises_configuration_error(self):
        with pytest.raises(RoleConfigurationError):
            AccountRoleRegistry.resolve_role_code("")

    def test_inactive_account_raises_configuration_error(self, setup_asset_and_liability_types):
        asset_type, _ = setup_asset_and_liability_types
        ChartOfAccounts.objects.create(
            code="10200",
            name="Inactive Bank Account",
            account_type=asset_type,
            is_active=False
        )

        with pytest.raises(RoleConfigurationError) as exc_info:
            AccountRoleRegistry.get_account(AccountRoleNames.DEFAULT_BANK_ACCOUNT)

        assert "is inactive" in str(exc_info.value)

    def test_context_processors_account_resolution_and_caching(self, monkeypatch, setup_asset_and_liability_types):
        asset_type, _ = setup_asset_and_liability_types
        cache.clear()
        
        cash_acc = ChartOfAccounts.objects.create(
            code="10199_CP",
            name="CP Cash Account",
            account_type=asset_type,
            is_active=True,
            is_cash_account=True
        )
        bank_acc = ChartOfAccounts.objects.create(
            code="10299_CP",
            name="CP Bank Account",
            account_type=asset_type,
            is_active=True,
            is_bank_account=True
        )

        monkeypatch.setenv("ACCOUNT_ROLE_DEFAULT_CASH_DRAWER", "10199_CP")
        monkeypatch.setenv("ACCOUNT_ROLE_DEFAULT_BANK_ACCOUNT", "10299_CP")

        rf = RequestFactory()
        request = rf.get("/")

        context_normal = cp_payment_accounts(request)
        assert context_normal["default_payment_account"] is not None
        assert context_normal["default_payment_account"].code == "10199_CP"
        assert context_normal["default_bank_account"] is not None
        assert context_normal["default_bank_account"].code == "10299_CP"

        context_opt = cp_opt_payment_accounts(request)
        assert context_opt["default_payment_account"] is not None
        assert context_opt["default_payment_account"]["code"] == "10199_CP"
        assert context_opt["default_bank_account"] is not None
        assert context_opt["default_bank_account"]["code"] == "10299_CP"
