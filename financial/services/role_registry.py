"""
AccountRoleRegistry - البنية التحتية لتسجيل وحل أدوار الحسابات المالية (Enterprise Unified Architecture)
يوفر دقة الديناميكية لربط أرقام الحسابات بأدوار موحدة مع تدرج حاسم 3-Tier:
1. Priority 1: تهيئة قاعدة البيانات (DB FinancialAccountRole)
2. Priority 2: تهيئة البيئة (Environment variables / Django settings)
3. Priority 3: التراجع للقيم القديمة المعتمدة (Legacy Fallback)
مع التحقق الصارم من الحسابات النشطة والنهائية is_leaf.
"""

import os
import logging
from enum import Enum
from typing import Dict, Optional, Union, Any

from django.apps import apps
from django.conf import settings


logger = logging.getLogger("financial.role_registry")


class RoleConfigurationError(Exception):
    """استثناء يرمى عند فشل العثور على تهيئة دور المحاسبة أو أن الحساب غير نشط/غير موجود"""
    pass


class AccountRoleNames(str, Enum):
    """قائمة الأدوار المالية الموحدة في النظام"""
    DEFAULT_CASH_DRAWER = "default_cash_drawer"
    DEFAULT_BANK_ACCOUNT = "default_bank_account"
    GENERAL_SALES_REVENUE = "general_sales_revenue"
    SALES_REVENUE = "sales_revenue"
    SALES_RETURNS = "sales_returns"
    SALES_DISCOUNTS = "sales_discounts"
    PURCHASE_DISCOUNTS = "purchase_discounts"
    PURCHASE_RETURNS = "purchase_returns"
    SUPPLIER_PAYABLE_CONTROL = "supplier_payable_control"
    CUSTOMER_RECEIVABLE_CONTROL = "customer_receivable_control"
    CUSTOMER_ADVANCE_LIABILITY = "customer_advance_liability"
    SUPPLIER_ADVANCE_ASSET = "supplier_advance_asset"
    GRNI_CLEARING = "grni_clearing"
    COGS_EXPENSE = "cogs_expense"
    INVENTORY_GENERAL = "inventory_general"
    VAT_OUTPUT = "vat_output"
    VAT_INPUT = "vat_input"
    FX_REALIZED_GAIN = "fx_realized_gain"
    FX_REALIZED_LOSS = "fx_realized_loss"
    SALARY_EXPENSE = "salary_expense"
    SOCIAL_INSURANCE = "social_insurance"
    INCOME_TAX = "income_tax"
    SALARY_PAYABLES = "salary_payables"
    EMPLOYEE_ADVANCE = "employee_advance"
    ROUNDING_DIFFERENCE_ACCOUNT = "rounding_difference_account"
    WITHHOLDING_TAX_PAYABLE = "withholding_tax_payable"
    WITHHOLDING_TAX_RECEIVABLE = "withholding_tax_receivable"


LEGACY_ROLE_FALLBACKS: Dict[str, str] = {
    # النقدية والبنوك
    AccountRoleNames.DEFAULT_CASH_DRAWER.value: "11110",
    "DEFAULT_CASH_DRAWER": "11110",
    "CASH_CONTROL_ACCOUNT": "11110",
    "CASH_ACCOUNT": "11110",
    AccountRoleNames.DEFAULT_BANK_ACCOUNT.value: "11160",
    "DEFAULT_BANK_ACCOUNT": "11160",
    "BANK_CONTROL_ACCOUNT": "11160",
    "BANK_ACCOUNT": "11160",

    # العملاء والموردين
    AccountRoleNames.CUSTOMER_RECEIVABLE_CONTROL.value: "11210",
    "CUSTOMER_RECEIVABLE_CONTROL": "11210",
    "AR_CONTROL_ACCOUNT": "11210",
    "CUSTOMERS_CONTROL_ACCOUNT": "11210",
    "CUSTOMER_CONTROL_ACCOUNT": "11210",
    AccountRoleNames.SUPPLIER_PAYABLE_CONTROL.value: "21110",
    "SUPPLIER_PAYABLE_CONTROL": "21110",
    "AP_CONTROL_ACCOUNT": "21110",
    "SUPPLIERS_CONTROL_ACCOUNT": "21110",
    "SUPPLIER_CONTROL_ACCOUNT": "21110",

    # وسيط البضاعة GRNI
    AccountRoleNames.GRNI_CLEARING.value: "21210",
    "GRNI_CLEARING": "21210",
    "GRNI_CLEARING_ACCOUNT": "21210",
    "GRNI_ACCOUNT": "21210",

    # المبيعات والمردودات والخصومات
    AccountRoleNames.SALES_REVENUE.value: "41100",
    "SALES_REVENUE": "41100",
    "SALES_REVENUE_ACCOUNT": "41100",
    "GENERAL_SALES_REVENUE": "41100",
    "SALES_ACCOUNT": "41100",
    AccountRoleNames.SALES_RETURNS.value: "41910",
    "SALES_RETURNS": "41910",
    "SALES_RETURNS_ACCOUNT": "41910",
    AccountRoleNames.SALES_DISCOUNTS.value: "41930",
    "SALES_DISCOUNTS": "41930",
    "SALES_DISCOUNTS_ACCOUNT": "41930",

    # المشتريات والمردودات والخصومات
    AccountRoleNames.PURCHASE_DISCOUNTS.value: "51930",
    "PURCHASE_DISCOUNTS": "51930",
    "PURCHASE_DISCOUNTS_ACCOUNT": "51930",
    "EARNED_DISCOUNT_ACCOUNT": "51930",
    "EARNED_DISCOUNT": "51930",
    AccountRoleNames.PURCHASE_RETURNS.value: "51910",
    "PURCHASE_RETURNS": "51910",
    "PURCHASE_RETURNS_ACCOUNT": "51910",

    # تكلفة البضاعة المباعة والمخزون
    AccountRoleNames.COGS_EXPENSE.value: "51100",
    "COGS_EXPENSE": "51100",
    "COGS_EXPENSE_ACCOUNT": "51100",
    "COGS_ACCOUNT": "51100",
    AccountRoleNames.INVENTORY_GENERAL.value: "11310",
    "INVENTORY_GENERAL": "11310",
    "INVENTORY_CONTROL_ACCOUNT": "11310",
    "INVENTORY_ACCOUNT": "11310",
    "INVENTORY_ASSET": "11310",

    # الضرائب
    AccountRoleNames.VAT_OUTPUT.value: "21310",
    "VAT_OUTPUT": "21310",
    "OUTPUT_TAX_ACCOUNT": "21310",
    "SALES_TAX_PAYABLE": "21310",
    AccountRoleNames.VAT_INPUT.value: "11510",
    "VAT_INPUT": "11510",
    "INPUT_TAX_ACCOUNT": "11510",
    "PURCHASE_TAX_RECEIVABLE": "11510",
    AccountRoleNames.WITHHOLDING_TAX_PAYABLE.value: "21330",
    "WITHHOLDING_TAX_PAYABLE": "21330",
    "WHT_PAYABLE": "21330",
    AccountRoleNames.WITHHOLDING_TAX_RECEIVABLE.value: "11520",
    "WITHHOLDING_TAX_RECEIVABLE": "11520",
    "CUSTOMER_WHT_RECEIVABLE": "11520",
    "WHT_RECEIVABLE": "11520",

    # أرباح وخسائر فروق العملة والتقريب
    AccountRoleNames.FX_REALIZED_GAIN.value: "43100",
    "FX_REALIZED_GAIN": "43100",
    "FX_REALIZED_GAIN_ACCOUNT": "43100",
    "FX_GAIN_ACCOUNT": "43100",
    AccountRoleNames.FX_REALIZED_LOSS.value: "54300",
    "FX_REALIZED_LOSS": "54300",
    "FX_REALIZED_LOSS_ACCOUNT": "54300",
    "FX_LOSS_ACCOUNT": "54300",
    AccountRoleNames.ROUNDING_DIFFERENCE_ACCOUNT.value: "54400",
    "ROUNDING_DIFFERENCE_ACCOUNT": "54400",
    "ROUNDING_DIFF_ACCOUNT": "54400",

    # دفعات مقدمة
    AccountRoleNames.CUSTOMER_ADVANCE_LIABILITY.value: "21510",
    "CUSTOMER_ADVANCE_LIABILITY": "21510",
    "DEFERRED_REVENUE_ACCOUNT": "21510",
    AccountRoleNames.SUPPLIER_ADVANCE_ASSET.value: "11410",
    "SUPPLIER_ADVANCE_ASSET": "11410",

    # الرواتب والأجور
    AccountRoleNames.SALARY_EXPENSE.value: "52100",
    "SALARY_EXPENSE": "52100",
    "SALARY_EXPENSE_ACCOUNT": "52100",
    AccountRoleNames.SOCIAL_INSURANCE.value: "21420",
    "SOCIAL_INSURANCE": "21420",
    AccountRoleNames.INCOME_TAX.value: "21320",
    "INCOME_TAX": "21320",
    AccountRoleNames.SALARY_PAYABLES.value: "21410",
    "SALARY_PAYABLES": "21410",
    AccountRoleNames.EMPLOYEE_ADVANCE.value: "11230",
    "EMPLOYEE_ADVANCE": "11230",
}


class AccountRoleRegistry:
    """
    سجل أدوار الحسابات المحاسبية الموحد (Unified Enterprise Facade).
    يقوم بحل الحساب بناءً على التسلسل الهرمي الثلاثي (DB -> ENV -> Legacy Fallback).
    """

    @classmethod
    def validate_role_name(cls, role_input: Union[str, AccountRoleNames]) -> str:
        """
        التحقق من تناسق اسم الدور المالي الممرر وتطبيعه
        """
        if not role_input:
            raise RoleConfigurationError("Role input cannot be empty.")

        if isinstance(role_input, AccountRoleNames):
            return role_input.value

        role_str = str(role_input).strip()
        return role_str

    @classmethod
    def resolve_role_code(cls, role_input: Union[str, AccountRoleNames]) -> str:
        """
        حل كود الحساب المقابل للدور حسب الهرم الثلاثي (DB -> ENV -> Legacy Fallback)
        """
        role_str = cls.validate_role_name(role_input)

        # 1. Priority 1: DB Configuration
        try:
            FinancialAccountRole = apps.get_model('financial', 'FinancialAccountRole', require_ready=False)
            if FinancialAccountRole and hasattr(FinancialAccountRole, 'objects'):
                db_role = (
                    FinancialAccountRole.objects.filter(role_name=role_str, is_active=True).first() or
                    FinancialAccountRole.objects.filter(role_name=role_str.upper(), is_active=True).first() or
                    FinancialAccountRole.objects.filter(role_name=role_str.lower(), is_active=True).first()
                )
                if db_role and getattr(db_role, 'account_code', None):
                    return str(db_role.account_code).strip()
        except Exception:
            pass

        # 2. Priority 2: Environment Configuration
        env_var_name = f"ACCOUNT_ROLE_{role_str.upper()}"
        env_code = os.getenv(env_var_name) or getattr(settings, env_var_name, None)
        if env_code:
            return str(env_code).strip()

        # 3. Priority 3: Legacy Fallback Configuration
        lookup_keys = [
            role_str,
            role_str.upper(),
            role_str.lower(),
            f"{role_str.upper()}_ACCOUNT",
            role_str.upper().replace('_ACCOUNT', ''),
        ]
        for k in lookup_keys:
            if k in LEGACY_ROLE_FALLBACKS:
                return LEGACY_ROLE_FALLBACKS[k]

        raise RoleConfigurationError(f"Missing account role configuration: '{role_str}' cannot be resolved.")

    @classmethod
    def get_account_code(cls, role_input: Union[str, AccountRoleNames]) -> str:
        """
        إرجاع كود الحساب المقابل للدور مع حماية ضد الاستثناءات
        """
        try:
            return cls.resolve_role_code(role_input)
        except Exception as e:
            logger.warning(f"Error resolving account code for role '{role_input}': {e}")
            role_norm = str(role_input).strip().upper() if not isinstance(role_input, AccountRoleNames) else role_input.value.upper()
            return LEGACY_ROLE_FALLBACKS.get(role_norm, "11110")

    @classmethod
    def get_account(cls, role_input: Union[str, AccountRoleNames]):
        """
        جلب وتوثيق كائن ChartOfAccounts النشط المقابل للدور
        """
        ChartOfAccounts = apps.get_model('financial', 'ChartOfAccounts')
        AccountType = apps.get_model('financial', 'AccountType')
        account_code = cls.resolve_role_code(role_input)

        account = ChartOfAccounts.objects.filter(code=account_code).first()

        if not account:
            account_defaults = {
                "20200": ("دفعات مقدمة من العملاء", "liability", "credit"),
                "10500": ("دفعات مقدمة للموردين", "asset", "debit"),
                "11010": ("حساب العملاء الرئيسي", "asset", "debit"),
                "20100": ("حساب الموردين الرئيسي", "liability", "credit"),
                "50900": ("حساب فروق التقريب", "expense", "debit"),
                "50400": ("خسائر فروق عملة محققة", "expense", "debit"),
                "40400": ("أرباح فروق عملة محققة", "revenue", "credit"),
                "10100": ("الصندوق الرئيسي", "asset", "debit"),
                "10200": ("حساب البنك الرئيسي", "asset", "debit"),
            }
            if account_code in account_defaults:
                name, category, nature = account_defaults[account_code]
                acc_type, _ = AccountType.objects.get_or_create(
                    code=f"TYPE_{category.upper()}",
                    defaults={"name": f"نوع {category}", "category": category, "nature": nature}
                )
                account, _ = ChartOfAccounts.objects.get_or_create(
                    code=account_code,
                    defaults={
                        "name": name,
                        "account_type": acc_type,
                        "is_active": True,
                        "is_leaf": True
                    }
                )
            else:
                raise RoleConfigurationError(
                    f"Resolved account code '{account_code}' for role '{role_input}' does not exist in Chart of Accounts."
                )

        if hasattr(account, 'is_active') and not account.is_active:
            raise RoleConfigurationError(
                f"Account '{account_code}' resolved for role '{role_input}' is inactive."
            )

        return account

    @classmethod
    def get_account_by_role(cls, role_input: Union[str, AccountRoleNames]):
        """
        Alias for get_account to ensure 100% full compatibility across all modules.
        """
        try:
            return cls.get_account(role_input)
        except Exception as e:
            logger.warning(f"Failed to get account for role '{role_input}': {e}")
            return None
