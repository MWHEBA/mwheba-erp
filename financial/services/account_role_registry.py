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
        "AP_CONTROL_ACCOUNT": getattr(settings, "DEFAULT_AP_ACCOUNT_CODE", "20100"),
        "SUPPLIER_PAYABLE_CONTROL": getattr(settings, "DEFAULT_AP_ACCOUNT_CODE", "20100"),
        "AR_CONTROL_ACCOUNT": getattr(settings, "DEFAULT_AR_ACCOUNT_CODE", "11010"),
        "CASH_CONTROL_ACCOUNT": getattr(settings, "DEFAULT_CASH_ACCOUNT_CODE", "10100"),
        "DEFAULT_CASH_DRAWER": getattr(settings, "DEFAULT_CASH_ACCOUNT_CODE", "10100"),
        "BANK_CONTROL_ACCOUNT": getattr(settings, "DEFAULT_BANK_ACCOUNT_CODE", "10200"),
        "DEFAULT_BANK_ACCOUNT": getattr(settings, "DEFAULT_BANK_ACCOUNT_CODE", "10200"),
        "INVENTORY_CONTROL_ACCOUNT": getattr(settings, "DEFAULT_INVENTORY_ACCOUNT_CODE", "10400"),
        "INVENTORY_ACCOUNT": getattr(settings, "DEFAULT_INVENTORY_ACCOUNT_CODE", "10400"),
        "SALES_REVENUE_ACCOUNT": getattr(settings, "DEFAULT_SALES_ACCOUNT_CODE", "40100"),
        "GENERAL_SALES_REVENUE": getattr(settings, "DEFAULT_SALES_ACCOUNT_CODE", "40100"),
        "COGS_EXPENSE_ACCOUNT": getattr(settings, "DEFAULT_COGS_ACCOUNT_CODE", "50100"),
        "COGS_ACCOUNT": getattr(settings, "DEFAULT_COGS_ACCOUNT_CODE", "50100"),
        "SALARY_EXPENSE_ACCOUNT": getattr(settings, "DEFAULT_SALARY_ACCOUNT_CODE", "50200"),
        "OUTPUT_TAX_ACCOUNT": getattr(settings, "DEFAULT_OUTPUT_TAX_ACCOUNT_CODE", "22010"),
        "INPUT_TAX_ACCOUNT": getattr(settings, "DEFAULT_INPUT_TAX_ACCOUNT_CODE", "11050"),
        "SALES_RETURNS_ACCOUNT": getattr(settings, "DEFAULT_SALES_RETURNS_ACCOUNT_CODE", "41100"),
        "DEFERRED_REVENUE_ACCOUNT": getattr(settings, "DEFAULT_DEFERRED_REVENUE_ACCOUNT_CODE", "21000"),
    }

    @classmethod
    def get_account_code(cls, role_name: str) -> str:
        """
        إرجاع كود الحساب المحاسبي عبر اسم الوظيفة
        """
        return cls.ROLE_MAP.get(role_name, "10100")

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
        code = cls.ROLE_MAP.get(role_name)
        if not code:
            logger.warning(f"Role '{role_name}' is not registered in AccountRoleRegistry.")
            return None

        account = ChartOfAccounts.objects.filter(code=code).first()
        if not account:
            # Fallback by code prefix or first active matching account type
            account = ChartOfAccounts.objects.filter(code__startswith=code[:3], is_active=True).first()

        return account
