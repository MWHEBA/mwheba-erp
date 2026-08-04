"""
FinancialStatementEngine - محرك إنشاء واحتساب القوائم المالية الموحدة (FIN-REP-002)
يتولى احتساب ميزان المراجعة وقائمة الدخل والميزانية العمومية والتحقق من المعادلات المحاسبية
"""

import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional

from financial.models.chart_of_accounts import ChartOfAccounts
from financial.services.financial_reporting_query_service import FinancialReportingQueryService
from financial.exceptions import FinancialValidationError

logger = logging.getLogger("financial.statement_engine")


class FinancialStatementEngine:
    """
    محرك القوائم المالية القياسية (Standard Financial Statement Engine)
    """

    @classmethod
    def generate_trial_balance(
        cls,
        as_of_date: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        توليد ميزان المراجعة (Trial Balance) مع التحقق المحاسبي من التوازن Sum(Debit) == Sum(Credit)
        """
        accounts = ChartOfAccounts.objects.filter(is_active=True).order_by("code")
        lines = []

        total_debit = Decimal("0.00")
        total_credit = Decimal("0.00")

        for acc in accounts:
            bal_fact = FinancialReportingQueryService.get_account_balance_fact(
                account_code=acc.code,
                as_of_date=as_of_date
            )

            debit = Decimal(str(bal_fact.get("debit", "0.00"))).quantize(Decimal("0.01"))
            credit = Decimal(str(bal_fact.get("credit", "0.00"))).quantize(Decimal("0.01"))
            net_balance = Decimal(str(bal_fact.get("balance", "0.00"))).quantize(Decimal("0.01"))

            if debit > 0 or credit > 0 or abs(net_balance) > 0:
                lines.append({
                    "account_id": acc.id,
                    "account_code": acc.code,
                    "account_name": acc.name,
                    "account_type": acc.account_type.name if acc.account_type else "",
                    "debit": debit,
                    "credit": credit,
                    "net_balance": net_balance
                })

                total_debit += debit
                total_credit += credit

        discrepancy = (total_debit - total_credit).quantize(Decimal("0.01"))
        is_balanced = abs(discrepancy) == Decimal("0.00")

        logger.info(f"Trial Balance Generated: Total Debit={total_debit}, Total Credit={total_credit}, Balanced={is_balanced}")

        return {
            "as_of_date": as_of_date,
            "lines": lines,
            "total_debit": total_debit,
            "total_credit": total_credit,
            "discrepancy": discrepancy,
            "is_balanced": is_balanced
        }

    @classmethod
    def generate_income_statement(
        cls,
        as_of_date: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        توليد قائمة الدخل / الأرباح والخسائر (Income Statement / P&L)
        Formula: Net Income = Total Revenue (4xxxx) - COGS (5xxxx) - Operating Expenses (6xxxx)
        """
        total_revenue = FinancialReportingQueryService.get_account_group_totals("4", as_of_date=as_of_date)
        total_cogs = FinancialReportingQueryService.get_account_group_totals("5", as_of_date=as_of_date)
        total_expenses = FinancialReportingQueryService.get_account_group_totals("6", as_of_date=as_of_date)

        # Revenue balances are credit-based
        gross_profit = (abs(total_revenue) - total_cogs).quantize(Decimal("0.01"))
        net_income = (gross_profit - total_expenses).quantize(Decimal("0.01"))

        logger.info(f"Income Statement Generated: Revenue={total_revenue}, COGS={total_cogs}, Expenses={total_expenses}, Net Income={net_income}")

        return {
            "as_of_date": as_of_date,
            "total_revenue": abs(total_revenue),
            "total_cogs": total_cogs,
            "gross_profit": gross_profit,
            "total_expenses": total_expenses,
            "net_income": net_income
        }

    @classmethod
    def generate_balance_sheet(
        cls,
        as_of_date: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        توليد الميزانية العمومية والمركز المالي (Balance Sheet)
        Formula: Total Assets (1xxxx) == Total Liabilities (2xxxx) + Total Equity (3xxxx) + Net Income
        """
        total_assets = FinancialReportingQueryService.get_account_group_totals("1", as_of_date=as_of_date)
        total_liabilities = FinancialReportingQueryService.get_account_group_totals("2", as_of_date=as_of_date)
        total_equity = FinancialReportingQueryService.get_account_group_totals("3", as_of_date=as_of_date)

        income_stmt = cls.generate_income_statement(as_of_date=as_of_date)
        net_income = income_stmt["net_income"]

        total_liabilities_and_equity = (abs(total_liabilities) + abs(total_equity) + net_income).quantize(Decimal("0.01"))
        accounting_equation_diff = (total_assets - total_liabilities_and_equity).quantize(Decimal("0.01"))
        is_balanced = abs(accounting_equation_diff) == Decimal("0.00")

        logger.info(
            f"Balance Sheet Generated: Assets={total_assets}, Liabilities+Equity+NetIncome={total_liabilities_and_equity}, Balanced={is_balanced}"
        )

        return {
            "as_of_date": as_of_date,
            "total_assets": total_assets,
            "total_liabilities": abs(total_liabilities),
            "total_equity": abs(total_equity),
            "net_income": net_income,
            "total_liabilities_and_equity": total_liabilities_and_equity,
            "accounting_equation_diff": accounting_equation_diff,
            "is_balanced": is_balanced
        }
