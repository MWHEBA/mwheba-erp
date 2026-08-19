import logging
from typing import Optional, Dict, Any
from django.conf import settings
from financial.models import ChartOfAccounts

logger = logging.getLogger("financial.services.account_role_registry")


class AccountRoleRegistry:
    """
    FIN-EEL / Sprint 0.5: Dynamic Account Role Configuration Registry
    يوفر خريطة ديناميكية لربط الأكواد المحاسبية بالوظائف الإدارية والتشغيلية (Roles) بدون أكواد نصية محفورة.
    """

    ROLE_MAP: Dict[str, str] = {
        "AP_CONTROL_ACCOUNT": getattr(settings, "DEFAULT_AP_ACCOUNT_CODE", "21110"),
        "SUPPLIER_PAYABLE_CONTROL": getattr(settings, "DEFAULT_AP_ACCOUNT_CODE", "21110"),
        "AR_CONTROL_ACCOUNT": getattr(settings, "DEFAULT_AR_ACCOUNT_CODE", "11210"),
        "CUSTOMER_RECEIVABLE_CONTROL": getattr(settings, "DEFAULT_AR_ACCOUNT_CODE", "11210"),
        "CASH_CONTROL_ACCOUNT": getattr(settings, "DEFAULT_CASH_ACCOUNT_CODE", "11110"),
        "DEFAULT_CASH_DRAWER": getattr(settings, "DEFAULT_CASH_ACCOUNT_CODE", "11110"),
        "BANK_CONTROL_ACCOUNT": getattr(settings, "DEFAULT_BANK_ACCOUNT_CODE", "11160"),
        "DEFAULT_BANK_ACCOUNT": getattr(settings, "DEFAULT_BANK_ACCOUNT_CODE", "11160"),
        "INVENTORY_CONTROL_ACCOUNT": getattr(settings, "DEFAULT_INVENTORY_ACCOUNT_CODE", "11310"),
        "INVENTORY_ACCOUNT": getattr(settings, "DEFAULT_INVENTORY_ACCOUNT_CODE", "11310"),
        "SALES_REVENUE_ACCOUNT": getattr(settings, "DEFAULT_SALES_ACCOUNT_CODE", "41100"),
        "GENERAL_SALES_REVENUE": getattr(settings, "DEFAULT_SALES_ACCOUNT_CODE", "41100"),
        "COGS_EXPENSE_ACCOUNT": getattr(settings, "DEFAULT_COGS_ACCOUNT_CODE", "51100"),
        "COGS_ACCOUNT": getattr(settings, "DEFAULT_COGS_ACCOUNT_CODE", "51100"),
        "SALARY_EXPENSE_ACCOUNT": getattr(settings, "DEFAULT_SALARY_ACCOUNT_CODE", "52110"),
        "OUTPUT_TAX_ACCOUNT": getattr(settings, "DEFAULT_OUTPUT_TAX_ACCOUNT_CODE", "21310"),
        "INPUT_TAX_ACCOUNT": getattr(settings, "DEFAULT_INPUT_TAX_ACCOUNT_CODE", "11510"),
        "SALES_RETURNS_ACCOUNT": getattr(settings, "DEFAULT_SALES_RETURNS_ACCOUNT_CODE", "41910"),
        "SALES_DISCOUNTS_ACCOUNT": getattr(settings, "DEFAULT_SALES_DISCOUNTS_ACCOUNT_CODE", "41920"),
        "DEFERRED_REVENUE_ACCOUNT": getattr(settings, "DEFAULT_DEFERRED_REVENUE_ACCOUNT_CODE", "21510"),
        "GRNI_CLEARING_ACCOUNT": getattr(settings, "DEFAULT_GRNI_ACCOUNT_CODE", "21210"),
        "FX_GAIN_ACCOUNT": getattr(settings, "DEFAULT_FX_GAIN_ACCOUNT_CODE", "43100"),
        "FX_LOSS_ACCOUNT": getattr(settings, "DEFAULT_FX_LOSS_ACCOUNT_CODE", "54300"),
        "ROUNDING_DIFFERENCE_ACCOUNT": getattr(settings, "DEFAULT_ROUNDING_DIFFERENCE_ACCOUNT_CODE", "54400"),
    }

    @classmethod
    def get_account_code(cls, role_name: str) -> str:
        """
        إرجاع كود الحساب المحاسبي عبر اسم الوظيفة
        """
        from financial.services.role_registry import AccountRoleRegistry as CoreRegistry
        try:
            return CoreRegistry.resolve_role_code(role_name)
        except Exception:
            return cls.ROLE_MAP.get(role_name, "11110")

    @classmethod
    def get_account(cls, role_name: str) -> Optional[ChartOfAccounts]:
        """
        Alias for get_account_by_role
        """
        return cls.get_account_by_role(role_name)

    @classmethod
    def get_account_by_role(cls, role_name: str) -> Optional[ChartOfAccounts]:
        """
        البحث عن الحساب المحاسبي عبر اسم الوظيفة (Role Name)
        """
        from financial.services.role_registry import AccountRoleRegistry as CoreRegistry
        try:
            return CoreRegistry.get_account(role_name)
        except Exception:
            code = cls.ROLE_MAP.get(role_name)
            if not code:
                return None
            return ChartOfAccounts.objects.filter(code=code, is_active=True).first()
