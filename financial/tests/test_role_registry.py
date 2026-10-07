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
        import uuid
        from supplier.models import SupplierType
        supp_type, _ = SupplierType.objects.get_or_create(code="COMP_TEST", defaults={"name": "Company Test"})
        monkeypatch.setenv("ACCOUNT_ROLE_SUPPLIER_PAYABLE_CONTROL", "NON_EXISTENT_999")

        import random
        unique_code = f"SUPP_NO_CTRL_{uuid.uuid4().hex[:6]}"
        supplier = Supplier(
            id=random.randint(500000, 999999),
            name="مورد مفقود الحساب",
            code=unique_code,
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
        created_account, _ = ChartOfAccounts.objects.get_or_create(
            code="11110",
            defaults={
                "name": "Default Cash Drawer Active Account",
                "account_type": asset_type,
                "is_active": True
            }
        )
        created_account.is_active = True
        created_account.save()

        account = AccountRoleRegistry.get_account(AccountRoleNames.DEFAULT_CASH_DRAWER)

        assert account is not None
        assert account.pk == created_account.pk
        assert account.code == "11110"
        assert account.is_active is True
        assert account.account_type is not None

    def test_legacy_fallback_resolution_priority_3(self, setup_asset_and_liability_types):
        asset_type, _ = setup_asset_and_liability_types
        ChartOfAccounts.objects.get_or_create(
            code="11110",
            defaults={
                "name": "Default Cash Drawer Account",
                "account_type": asset_type,
                "is_active": True
            }
        )

        resolved_code = AccountRoleRegistry.resolve_role_code(AccountRoleNames.DEFAULT_CASH_DRAWER)
        assert resolved_code == "11110"

        account = AccountRoleRegistry.get_account(AccountRoleNames.DEFAULT_CASH_DRAWER)
        assert isinstance(account, ChartOfAccounts)
        assert account.code == "11110"

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
        acc, _ = ChartOfAccounts.objects.get_or_create(
            code="11160001",
            defaults={"name": "Inactive Bank Account", "account_type": asset_type}
        )
        acc.is_active = False
        acc.save()

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
        assert context_normal["default_payment_account"]["code"] == "10199_CP"
        assert context_normal["default_bank_account"] is not None
        assert context_normal["default_bank_account"]["code"] == "10299_CP"

    def test_bank_charges_and_vat_input_default_resolutions(self):
        """التحقق من حل أدوار المصاريف البنكية وضريبة المدخلات بالأكواد المعيارية الصحيحة 54100 و 11510"""
        bank_charges_code = AccountRoleRegistry.resolve_role_code(AccountRoleNames.BANK_CHARGES_EXPENSE)
        assert bank_charges_code == "54100"

        vat_input_code = AccountRoleRegistry.resolve_role_code(AccountRoleNames.VAT_INPUT)
        assert vat_input_code == "11510"

        fx_gain_code = AccountRoleRegistry.resolve_role_code(AccountRoleNames.FX_REALIZED_GAIN)
        assert fx_gain_code == "43100"

        fx_loss_code = AccountRoleRegistry.resolve_role_code(AccountRoleNames.FX_REALIZED_LOSS)
        assert fx_loss_code == "54300"

    def test_semantic_type_guard_rejects_invalid_account_category(self):
        """التحقق من أن صمام الأمان الدلالي (Semantic Type Guard) يرفض ربط دور مصاريف بحساب أصول"""
        asset_type, _ = AccountType.objects.get_or_create(
            code="AST_TEST_GUARD",
            defaults={"name": "Asset Test Guard", "category": "asset"}
        )
        # إنشاء حساب خاطئ (أصول) مع كود المصاريف البنكية
        acc, _ = ChartOfAccounts.objects.get_or_create(
            code="54100_TEST",
            defaults={"name": "Bank Charges Bad Asset", "account_type": asset_type, "is_active": True}
        )
        acc.account_type = asset_type
        acc.is_active = True
        acc.save()

        import os
        os.environ["ACCOUNT_ROLE_BANK_CHARGES_EXPENSE"] = "54100_TEST"
        try:
            with pytest.raises(RoleConfigurationError) as exc_info:
                AccountRoleRegistry.get_account(AccountRoleNames.BANK_CHARGES_EXPENSE)
            assert "does not match expected category 'expense'" in str(exc_info.value)
        finally:
            os.environ.pop("ACCOUNT_ROLE_BANK_CHARGES_EXPENSE", None)


@pytest.mark.django_db
class TestAllRolesAuditAndCompliance:
    """
    اختبارات الحوكمة الرقابية الذاتية والتدقيق الشامل لكافة الأدوار المالية (Phase 6 Governance Audit)
    """

    @pytest.fixture(autouse=True)
    def setup_system_coa_and_roles(self):
        from django.core.management import call_command
        call_command("setup_accounting_system", force=True)

    def test_all_roles_audit_against_chart_of_accounts_and_seeding(self):
        """
        تدقيق شامل لجميع الأدوار الـ 28 المسجلة في AccountRoleNames:
        1. التأكد من وجود سجل FinancialAccountRole في قاعدة البيانات (Priority 1)
        2. التأكد من وجود الحساب الفعلي في شجرة الحسابات ونشاطه (is_active=True)
        3. التحقق من مطابقة نوع الحساب للمصفوفة الدلالية المعيارية ROLE_EXPECTED_CATEGORIES
        """
        from financial.models.account_role import FinancialAccountRole
        from financial.services.role_registry import ROLE_EXPECTED_CATEGORIES

        # استثناء الأدوار المرادفة العامة إن وجدت
        all_roles = list(AccountRoleNames)
        assert len(all_roles) >= 28

        for role in all_roles:
            role_name = role.value
            expected_category = ROLE_EXPECTED_CATEGORIES.get(role_name)
            assert expected_category is not None, f"Role '{role_name}' must be defined in ROLE_EXPECTED_CATEGORIES"

            # 1. حل كود الحساب
            resolved_code = AccountRoleRegistry.resolve_role_code(role)
            assert resolved_code, f"Role '{role_name}' must resolve to a valid account code"

            # 2. جلب الحساب وتطبيق الحماية الدلالية
            account = AccountRoleRegistry.get_account(role)
            assert account is not None, f"Account for role '{role_name}' ({resolved_code}) must exist in COA"
            assert account.is_active is True, f"Account '{account.code}' for role '{role_name}' must be active"
            assert account.account_type is not None, f"Account '{account.code}' must have an account_type"
            assert account.account_type.category == expected_category, (
                f"Role '{role_name}' expected category '{expected_category}' "
                f"but got '{account.account_type.category}' for account '{account.code}'"
            )

            # 3. التحقق من وجود السجل في قاعدة البيانات (Priority 1)
            db_role = FinancialAccountRole.objects.filter(role_name=role_name, is_active=True).first()
            assert db_role is not None, f"DB FinancialAccountRole record must exist for role '{role_name}'"
            assert db_role.account.code == resolved_code, (
                f"DB role '{role_name}' account '{db_role.account.code}' does not match resolved '{resolved_code}'"
            )

    def test_three_tier_hierarchy_precedence(self, monkeypatch):
        """
        التحقق من التدرج الهرمي الحاسم الثلاثي (Priority 1: DB -> Priority 2: ENV -> Priority 3: Legacy Fallback)
        """
        from financial.models.account_role import FinancialAccountRole

        expense_type, _ = AccountType.objects.get_or_create(
            code="EXPENSE",
            defaults={"name": "مصروفات", "category": "expense", "nature": "debit"}
        )

        # إنشاء 3 حسابات تجريبية
        acc_db = ChartOfAccounts.objects.create(
            code="54101",
            name="Bank Charges DB Role Test",
            account_type=expense_type,
            is_active=True,
            is_leaf=True
        )
        acc_env = ChartOfAccounts.objects.create(
            code="54102",
            name="Bank Charges ENV Role Test",
            account_type=expense_type,
            is_active=True,
            is_leaf=True
        )

        role_name = AccountRoleNames.BANK_CHARGES_EXPENSE.value

        # ضبط قاعدة البيانات على acc_db
        db_role, _ = FinancialAccountRole.objects.update_or_create(
            role_name=role_name,
            defaults={"account": acc_db, "is_active": True}
        )

        # ضبط متغير البيئة على acc_env
        monkeypatch.setenv("ACCOUNT_ROLE_BANK_CHARGES_EXPENSE", "54102")

        # 1. اختبار الأولوية 1: قاعدة البيانات تغلب متغير البيئة والـ Legacy
        assert AccountRoleRegistry.resolve_role_code(role_name) == "54101"
        account = AccountRoleRegistry.get_account(role_name)
        assert account.code == "54101"

        # 2. اختبار الأولوية 2: عند تعطيل سجل قاعدة البيانات، يغلب متغير البيئة الـ Legacy
        db_role.is_active = False
        db_role.save()
        assert AccountRoleRegistry.resolve_role_code(role_name) == "54102"
        account = AccountRoleRegistry.get_account(role_name)
        assert account.code == "54102"

        # 3. اختبار الأولوية 3: عند إزالة متغير البيئة، يتم التراجع للـ Legacy Fallback (54100)
        monkeypatch.delenv("ACCOUNT_ROLE_BANK_CHARGES_EXPENSE", raising=False)
        assert AccountRoleRegistry.resolve_role_code(role_name) == "54100"
        account = AccountRoleRegistry.get_account(role_name)
        assert account.code == "54100"

    def test_semantic_type_guard_rejects_category_mismatches_for_core_roles(self):
        """
        التحقق من أن صمام الأمان الدلالي يمنع أي محاولة لربط الحسابات بتصنيفات غير متوافقة
        سواء كانت أصولاً مرتبطة بإيرادات، أو خصوماً مرتبطة بأصول، أو مصروفات مرتبطة بخصوم
        """
        from financial.models.account_role import FinancialAccountRole

        asset_type = AccountType.objects.get(code="ASSET")
        liability_type = AccountType.objects.get(code="LIABILITY")
        revenue_type = AccountType.objects.get(code="REVENUE")
        expense_type = AccountType.objects.get(code="EXPENSE")

        # حساب أصول
        bad_asset = ChartOfAccounts.objects.create(
            code="99001",
            name="Bad Asset Account",
            account_type=asset_type,
            is_active=True,
            is_leaf=True
        )
        # حساب خصوم
        bad_liability = ChartOfAccounts.objects.create(
            code="99002",
            name="Bad Liability Account",
            account_type=liability_type,
            is_active=True,
            is_leaf=True
        )

        # 1. محاولة ربط دور إيرادات المبيعات (revenue) بحساب أصول (asset)
        FinancialAccountRole.objects.update_or_create(
            role_name=AccountRoleNames.SALES_REVENUE.value,
            defaults={"account": bad_asset, "is_active": True}
        )
        with pytest.raises(RoleConfigurationError) as exc:
            AccountRoleRegistry.get_account(AccountRoleNames.SALES_REVENUE)
        assert "does not match expected category 'revenue'" in str(exc.value)

        # 2. محاولة ربط دور ضريبة المدخلات (asset) بحساب خصوم (liability)
        FinancialAccountRole.objects.update_or_create(
            role_name=AccountRoleNames.VAT_INPUT.value,
            defaults={"account": bad_liability, "is_active": True}
        )
        with pytest.raises(RoleConfigurationError) as exc:
            AccountRoleRegistry.get_account(AccountRoleNames.VAT_INPUT)
        assert "does not match expected category 'asset'" in str(exc.value)

        # 3. محاولة ربط دور خسائر فروق العملة (expense) بحساب أصول (asset)
        FinancialAccountRole.objects.update_or_create(
            role_name=AccountRoleNames.FX_REALIZED_LOSS.value,
            defaults={"account": bad_asset, "is_active": True}
        )
        with pytest.raises(RoleConfigurationError) as exc:
            AccountRoleRegistry.get_account(AccountRoleNames.FX_REALIZED_LOSS)
        assert "does not match expected category 'expense'" in str(exc.value)

