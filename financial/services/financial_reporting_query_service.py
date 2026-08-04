"""
FinancialReportingQueryService - بوابة الاستعلامات المالية الموحدة للتقارير والقوائم المالية (FIN-REP-001)
تعمل كبوابة محكومة لتجريد استعلامات التقارير وحظر الاستعلام المباشر لموديلات قاعدة البيانات
"""

import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional
from django.db.models import Sum

from financial.models.chart_of_accounts import ChartOfAccounts
from financial.services.ledger_query_service import LedgerQueryService
from client.services.customer_aging_service import CustomerAgingService
from supplier.services.supplier_aging_service import SupplierAgingService
from product.services.valuation_service import InventoryValuationService

logger = logging.getLogger("financial.reporting_query_service")


class FinancialReportingQueryService:
    """
    البوابة المركزية لاستعلامات التقارير المالية (Single Controlled Reporting Query Gateway)
    """

    @classmethod
    def get_account_balance_fact(
        cls,
        account_code: str,
        as_of_date: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        استعلام رصيد حساب معتمد عبر LedgerQueryService
        """
        return LedgerQueryService.get_account_balance(account_code, as_of_date=as_of_date)

    @classmethod
    def get_account_group_totals(
        cls,
        code_prefix: str,
        as_of_date: Optional[Any] = None
    ) -> Decimal:
        """
        حساب إجمالي الأرصدة لمجموعة حسابات تبدأ بـ code_prefix (مثال: '1' للأصول، '4' للإيرادات)
        """
        accounts = ChartOfAccounts.objects.filter(code__startswith=code_prefix, is_active=True)
        total_balance = Decimal("0.00")

        for acc in accounts:
            bal_fact = cls.get_account_balance_fact(account_code=acc.code, as_of_date=as_of_date)
            total_balance += Decimal(str(bal_fact.get("balance", "0.00")))

        return total_balance.quantize(Decimal("0.01"))

    @classmethod
    def get_subledger_summary_facts(
        cls,
        as_of_date: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        جمع حقائق دفاتر الأستاذ الفرعية للمطبقة (AR / AP / Stock Valuation)
        """
        cust_aging = CustomerAgingService.get_portfolio_aging_summary(as_of_date=as_of_date)
        supp_aging = SupplierAgingService.get_portfolio_aging_summary(as_of_date=as_of_date)
        inv_val = InventoryValuationService.get_valuation_control_report()

        return {
            "ar_total_receivables": Decimal(str(cust_aging.get("total_outstanding", "0.00"))).quantize(Decimal("0.01")),
            "ap_total_payables": Decimal(str(supp_aging.get("total_outstanding", "0.00"))).quantize(Decimal("0.01")),
            "inventory_valuation": Decimal(str(inv_val.get("total_active_layer_valuation", "0.00"))).quantize(Decimal("0.01"))
        }
