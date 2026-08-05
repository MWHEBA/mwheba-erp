"""
AccountRoleRegistry - البنية التحتية لتسجيل وحل أدوار الحسابات المالية (Batch 2 Phase 1 & 2)
يوفر دقة الدقة والديناميكية لربط أرقام الحسابات بأدوار موحدة مع تدرج حاسم 3-Tier:
1. Priority 1: تهيئة قاعدة البيانات (DB FinancialAccountRole)
2. Priority 2: تهيئة البيئة (Environment variables / Django settings)
3. Priority 3: التراجع للقيم القديمة المعتمدة (Legacy Fallback)
"""

import os
import logging
from enum import Enum
from typing import Dict, Optional, Union

from django.apps import apps
from django.conf import settings


logger = logging.getLogger("financial.role_registry")


class RoleConfigurationError(Exception):
    """استثناء يرمى عند فشل العثور على تهيئة دور المحاسبة أو أن الحساب غير نائم/غير موجود"""
    pass


class AccountRoleNames(str, Enum):
    """قائمة الأدوار المالية الموحدة في النظام"""
    DEFAULT_CASH_DRAWER = "default_cash_drawer"
    DEFAULT_BANK_ACCOUNT = "default_bank_account"
    GENERAL_SALES_REVENUE = "general_sales_revenue"
    SUPPLIER_PAYABLE_CONTROL = "supplier_payable_control"
    SALARY_EXPENSE = "salary_expense"
    SOCIAL_INSURANCE = "social_insurance"
    INCOME_TAX = "income_tax"
    SALARY_PAYABLES = "salary_payables"
    EMPLOYEE_ADVANCE = "employee_advance"
    INVENTORY_GENERAL = "inventory_general"


LEGACY_ROLE_FALLBACKS: Dict[str, str] = {
    AccountRoleNames.DEFAULT_CASH_DRAWER.value: "10100",
    AccountRoleNames.DEFAULT_BANK_ACCOUNT.value: "10200",
    AccountRoleNames.GENERAL_SALES_REVENUE.value: "40100",
    AccountRoleNames.SUPPLIER_PAYABLE_CONTROL.value: "20100",
    "AP_CONTROL_ACCOUNT": "20100",
    "AR_CONTROL_ACCOUNT": "11010",
    AccountRoleNames.SALARY_EXPENSE.value: "50200",
    "SALARY_EXPENSE": "50200",
    AccountRoleNames.SOCIAL_INSURANCE.value: "2103",
    AccountRoleNames.INCOME_TAX.value: "2104",
    AccountRoleNames.SALARY_PAYABLES.value: "20200",
    "SALARY_PAYABLES": "20200",
    AccountRoleNames.EMPLOYEE_ADVANCE.value: "10350",
    AccountRoleNames.INVENTORY_GENERAL.value: "10400",
}


class AccountRoleRegistry:
    """
    سجل أدوار الحسابات المحاسبية الموحد.
    يقوم بحل الحساب بناءً على التسلسل الهرمي الثلاثي (DB -> ENV -> Legacy Fallback).
    """

    @classmethod
    def validate_role_name(cls, role_input: Union[str, AccountRoleNames]) -> str:
        """
        التحقق من تناسق اسم الدور المالي الممرر مقارنة بـ AccountRoleNames
        """
        if not role_input:
            raise RoleConfigurationError("Role input cannot be empty.")

        role_str = role_input.value if isinstance(role_input, AccountRoleNames) else str(role_input)
        valid_roles = {r.value for r in AccountRoleNames}
        
        if role_str not in valid_roles:
            logger.info(f"Role '{role_str}' passed as custom role string outside standard AccountRoleNames Enum.")

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
                db_role = FinancialAccountRole.objects.filter(role_name=role_str, is_active=True).first()
                if db_role and getattr(db_role, 'account_code', None):
                    return db_role.account_code
        except Exception:
            pass

        # 2. Priority 2: Environment Configuration
        env_var_name = f"ACCOUNT_ROLE_{role_str.upper()}"
        env_code = os.getenv(env_var_name) or getattr(settings, env_var_name, None)
        if env_code:
            return str(env_code).strip()

        # 3. Priority 3: Legacy Fallback Configuration
        if role_str in LEGACY_ROLE_FALLBACKS:
            return LEGACY_ROLE_FALLBACKS[role_str]

        raise RoleConfigurationError(f"Missing account role configuration: '{role_str}' cannot be resolved.")

    @classmethod
    def get_account(cls, role_input: Union[str, AccountRoleNames]):
        """
        جلب وتوثيق كائن ChartOfAccounts النشط المقابل للدور
        """
        ChartOfAccounts = apps.get_model('financial', 'ChartOfAccounts')
        account_code = cls.resolve_role_code(role_input)

        account = ChartOfAccounts.objects.filter(code=account_code).first()

        if not account:
            raise RoleConfigurationError(
                f"Resolved account code '{account_code}' for role '{role_input}' does not exist in Chart of Accounts."
            )

        if hasattr(account, 'is_active') and not account.is_active:
            raise RoleConfigurationError(
                f"Account '{account_code}' resolved for role '{role_input}' is inactive."
            )

        return account
