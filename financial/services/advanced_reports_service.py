"""
خدمة التقارير المالية المتقدمة
"""
from django.db import connection
from django.utils import timezone
from django.core.cache import cache
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any
from datetime import date, datetime, timedelta
import logging
import json

from ..models.chart_of_accounts import ChartOfAccounts, AccountType
from ..models.journal_entry import JournalEntry, JournalEntryLine, AccountingPeriod
from ..services.enhanced_balance_service import EnhancedBalanceService
from ..services.redis_cache_service import financial_cache

logger = logging.getLogger(__name__)


class AdvancedReportsService:
    """
    خدمة التقارير المالية المتقدمة
    """

    CACHE_TIMEOUT = 1800  # 30 دقيقة

    @classmethod
    def generate_comprehensive_trial_balance(
        cls,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        include_zero_balances: bool = False,
        group_by_type: bool = True,
    ) -> Dict:
        """
        ميزان مراجعة شامل ومحسن
        """
        cache_key = f"comprehensive_trial_balance_{date_from}_{date_to}_{include_zero_balances}_{group_by_type}"

        # محاولة الحصول من الكاش
        cached_result = financial_cache.get(
            "trial_balance_comprehensive",
            date_from=date_from,
            date_to=date_to,
            include_zero=include_zero_balances,
        )
        if cached_result:
            return cached_result

        # بناء الاستعلام المحسن
        query = """
        WITH account_balances AS (
            SELECT 
                coa.id,
                coa.code,
                coa.name,
                coa.name_en,
                at.name as account_type_name,
                at.category,
                at.nature,
                COALESCE(SUM(jel.debit), 0) as total_debit,
                COALESCE(SUM(jel.credit), 0) as total_credit,
                CASE 
                    WHEN at.nature = 'debit' THEN COALESCE(SUM(jel.debit), 0) - COALESCE(SUM(jel.credit), 0)
                    ELSE COALESCE(SUM(jel.credit), 0) - COALESCE(SUM(jel.debit), 0)
                END as balance,
                COUNT(jel.id) as transactions_count
            FROM financial_chartofaccounts coa
            INNER JOIN financial_accounttype at ON coa.account_type_id = at.id
            LEFT JOIN financial_journalentryline jel ON coa.id = jel.account_id
            LEFT JOIN financial_journalentry je ON jel.journal_entry_id = je.id AND je.status = 'posted'
            WHERE coa.is_leaf = true AND coa.is_active = true
        """

        params = []

        if date_from:
            query += " AND je.date >= %s"
            params.append(date_from)

        if date_to:
            query += " AND je.date <= %s"
            params.append(date_to)

        query += """
            GROUP BY coa.id, coa.code, coa.name, coa.name_en, at.name, at.category, at.nature
        """

        if not include_zero_balances:
            query += """
            HAVING ABS(CASE 
                WHEN at.nature = 'debit' THEN COALESCE(SUM(jel.debit), 0) - COALESCE(SUM(jel.credit), 0)
                ELSE COALESCE(SUM(jel.credit), 0) - COALESCE(SUM(jel.debit), 0)
            END) > 0.01
            """

        query += """
        )
        SELECT 
            id, code, name, name_en, account_type_name, category, nature,
            total_debit, total_credit, balance, transactions_count,
            CASE WHEN nature = 'debit' AND balance >= 0 THEN balance 
                 WHEN nature = 'credit' AND balance < 0 THEN ABS(balance) ELSE 0 END as debit_balance,
            CASE WHEN nature = 'credit' AND balance >= 0 THEN balance 
                 WHEN nature = 'debit' AND balance < 0 THEN ABS(balance) ELSE 0 END as credit_balance
        FROM account_balances
        ORDER BY category, code
        """

        with connection.cursor() as cursor:
            cursor.execute(query, params)
            columns = [col[0] for col in cursor.description]

            accounts = []
            category_totals = {}
            grand_totals = {
                "total_debit": Decimal("0"),
                "total_credit": Decimal("0"),
                "debit_balance": Decimal("0"),
                "credit_balance": Decimal("0"),
                "accounts_count": 0,
            }

            for row in cursor.fetchall():
                account_data = dict(zip(columns, row))

                # تحويل القيم إلى Decimal
                for key in [
                    "total_debit",
                    "total_credit",
                    "balance",
                    "debit_balance",
                    "credit_balance",
                ]:
                    account_data[key] = Decimal(str(account_data[key] or 0))

                accounts.append(account_data)

                # حساب إجماليات التصنيفات
                category = account_data["category"]
                if category not in category_totals:
                    category_totals[category] = {
                        "total_debit": Decimal("0"),
                        "total_credit": Decimal("0"),
                        "debit_balance": Decimal("0"),
                        "credit_balance": Decimal("0"),
                        "accounts_count": 0,
                    }

                category_totals[category]["total_debit"] += account_data["total_debit"]
                category_totals[category]["total_credit"] += account_data[
                    "total_credit"
                ]
                category_totals[category]["debit_balance"] += account_data[
                    "debit_balance"
                ]
                category_totals[category]["credit_balance"] += account_data[
                    "credit_balance"
                ]
                category_totals[category]["accounts_count"] += 1

                # الإجماليات العامة
                grand_totals["total_debit"] += account_data["total_debit"]
                grand_totals["total_credit"] += account_data["total_credit"]
                grand_totals["debit_balance"] += account_data["debit_balance"]
                grand_totals["credit_balance"] += account_data["credit_balance"]
                grand_totals["accounts_count"] += 1

        # تجميع النتائج
        result = {
            "report_info": {
                "title": "ميزان المراجعة الشامل",
                "date_from": date_from,
                "date_to": date_to,
                "generated_at": timezone.now(),
                "include_zero_balances": include_zero_balances,
                "group_by_type": group_by_type,
            },
            "accounts": accounts,
            "category_totals": category_totals,
            "grand_totals": grand_totals,
            "is_balanced": abs(
                grand_totals["debit_balance"] - grand_totals["credit_balance"]
            )
            < Decimal("0.01"),
            "balance_difference": grand_totals["debit_balance"]
            - grand_totals["credit_balance"],
        }

        # حفظ في الكاش
        financial_cache.set(
            "trial_balance_comprehensive",
            result,
            timeout=cls.CACHE_TIMEOUT,
            date_from=date_from,
            date_to=date_to,
            include_zero=include_zero_balances,
        )

        return result

    @classmethod
    def generate_income_statement(
        cls, date_from: date, date_to: date, comparative_period: bool = False
    ) -> Dict:
        """
        قائمة الدخل المحسنة
        """
        # الفترة الحالية
        current_period = cls._calculate_income_statement_data(date_from, date_to)

        result = {
            "report_info": {
                "title": "قائمة الدخل",
                "period_from": date_from,
                "period_to": date_to,
                "generated_at": timezone.now(),
                "comparative": comparative_period,
            },
            "current_period": current_period,
        }

        # الفترة المقارنة إذا طُلبت
        if comparative_period:
            period_length = (date_to - date_from).days
            comparative_from = date_from - timedelta(days=period_length + 1)
            comparative_to = date_from - timedelta(days=1)

            comparative_data = cls._calculate_income_statement_data(
                comparative_from, comparative_to
            )
            result["comparative_period"] = comparative_data
            result["report_info"]["comparative_from"] = comparative_from
            result["report_info"]["comparative_to"] = comparative_to

            # حساب التغييرات
            result["changes"] = cls._calculate_income_changes(
                current_period, comparative_data
            )

        return result

    @classmethod
    def _calculate_income_statement_data(cls, date_from: date, date_to: date) -> Dict:
        """
        حساب بيانات قائمة الدخل لفترة معينة
        """
        query = """
        SELECT 
            at.category,
            at.name as account_type_name,
            coa.code,
            coa.name,
            CASE 
                WHEN at.nature = 'debit' THEN COALESCE(SUM(jel.debit), 0) - COALESCE(SUM(jel.credit), 0)
                ELSE COALESCE(SUM(jel.credit), 0) - COALESCE(SUM(jel.debit), 0)
            END as balance
        FROM financial_chartofaccounts coa
        INNER JOIN financial_accounttype at ON coa.account_type_id = at.id
        LEFT JOIN financial_journalentryline jel ON coa.id = jel.account_id
        LEFT JOIN financial_journalentry je ON jel.journal_entry_id = je.id
        WHERE coa.is_leaf = true 
            AND coa.is_active = true 
            AND at.category IN ('revenue', 'expense')
            AND je.status = 'posted'
            AND je.date BETWEEN %s AND %s
        GROUP BY at.category, at.name, coa.code, coa.name, at.nature
        HAVING ABS(CASE 
            WHEN at.nature = 'debit' THEN COALESCE(SUM(jel.debit), 0) - COALESCE(SUM(jel.credit), 0)
            ELSE COALESCE(SUM(jel.credit), 0) - COALESCE(SUM(jel.debit), 0)
        END) > 0.01
        ORDER BY at.category, coa.code
        """

        with connection.cursor() as cursor:
            cursor.execute(query, [date_from, date_to])

            revenues = []
            expenses = []
            total_revenue = Decimal("0")
            total_expenses = Decimal("0")

            for row in cursor.fetchall():
                category, account_type_name, code, name, balance = row
                balance = Decimal(str(balance or 0))

                account_data = {
                    "code": code,
                    "name": name,
                    "account_type": account_type_name,
                    "balance": balance,
                }

                if category == "revenue":
                    revenues.append(account_data)
                    total_revenue += balance
                elif category == "expense":
                    expenses.append(account_data)
                    total_expenses += balance

        # حساب صافي الدخل
        net_income = total_revenue - total_expenses

        return {
            "revenues": revenues,
            "expenses": expenses,
            "total_revenue": total_revenue,
            "total_expenses": total_expenses,
            "net_income": net_income,
            "profit_margin": (net_income / total_revenue * 100)
            if total_revenue > 0
            else Decimal("0"),
        }

    @classmethod
    def _calculate_income_changes(cls, current: Dict, comparative: Dict) -> Dict:
        """
        حساب التغييرات بين الفترات
        """
        return {
            "revenue_change": current["total_revenue"] - comparative["total_revenue"],
            "revenue_change_percent": (
                (current["total_revenue"] - comparative["total_revenue"])
                / comparative["total_revenue"]
                * 100
                if comparative["total_revenue"] > 0
                else Decimal("0")
            ),
            "expense_change": current["total_expenses"] - comparative["total_expenses"],
            "expense_change_percent": (
                (current["total_expenses"] - comparative["total_expenses"])
                / comparative["total_expenses"]
                * 100
                if comparative["total_expenses"] > 0
                else Decimal("0")
            ),
            "net_income_change": current["net_income"] - comparative["net_income"],
            "net_income_change_percent": (
                (current["net_income"] - comparative["net_income"])
                / comparative["net_income"]
                * 100
                if comparative["net_income"] != 0
                else Decimal("0")
            ),
        }

    @classmethod
    def generate_balance_sheet(cls, as_of_date: date) -> Dict:
        """
        الميزانية العمومية المحسنة
        """
        query = """
        SELECT 
            at.category,
            at.name as account_type_name,
            coa.code,
            coa.name,
            CASE 
                WHEN at.nature = 'debit' THEN COALESCE(SUM(jel.debit), 0) - COALESCE(SUM(jel.credit), 0)
                ELSE COALESCE(SUM(jel.credit), 0) - COALESCE(SUM(jel.debit), 0)
            END as balance
        FROM financial_chartofaccounts coa
        INNER JOIN financial_accounttype at ON coa.account_type_id = at.id
        LEFT JOIN financial_journalentryline jel ON coa.id = jel.account_id
        LEFT JOIN financial_journalentry je ON jel.journal_entry_id = je.id
        WHERE coa.is_leaf = true 
            AND coa.is_active = true 
            AND at.category IN ('asset', 'liability', 'equity')
            AND je.status = 'posted'
            AND je.date <= %s
        GROUP BY at.category, at.name, coa.code, coa.name, at.nature
        HAVING ABS(CASE 
            WHEN at.nature = 'debit' THEN COALESCE(SUM(jel.debit), 0) - COALESCE(SUM(jel.credit), 0)
            ELSE COALESCE(SUM(jel.credit), 0) - COALESCE(SUM(jel.debit), 0)
        END) > 0.01
        ORDER BY at.category, coa.code
        """

        with connection.cursor() as cursor:
            cursor.execute(query, [as_of_date])

            assets = []
            liabilities = []
            equity = []

            total_assets = Decimal("0")
            total_liabilities = Decimal("0")
            total_equity = Decimal("0")

            for row in cursor.fetchall():
                category, account_type_name, code, name, balance = row
                balance = Decimal(str(balance or 0))

                account_data = {
                    "code": code,
                    "name": name,
                    "account_type": account_type_name,
                    "balance": balance,
                }

                if category == "asset":
                    assets.append(account_data)
                    total_assets += balance
                elif category == "liability":
                    liabilities.append(account_data)
                    total_liabilities += balance
                elif category == "equity":
                    equity.append(account_data)
                    total_equity += balance

        # التحقق من معادلة الميزانية
        balance_equation = total_assets - (total_liabilities + total_equity)
        is_balanced = abs(balance_equation) < Decimal("0.01")

        return {
            "report_info": {
                "title": "الميزانية العمومية",
                "as_of_date": as_of_date,
                "generated_at": timezone.now(),
            },
            "assets": assets,
            "liabilities": liabilities,
            "equity": equity,
            "totals": {
                "total_assets": total_assets,
                "total_liabilities": total_liabilities,
                "total_equity": total_equity,
                "liabilities_and_equity": total_liabilities + total_equity,
            },
            "balance_check": {
                "is_balanced": is_balanced,
                "difference": balance_equation,
            },
        }

    @classmethod
    def generate_cash_flow_statement(cls, date_from: date, date_to: date) -> Dict:
        """
        قائمة التدفقات النقدية
        """
        # الحصول على الحسابات النقدية
        cash_accounts = ChartOfAccounts.objects.filter(
            is_cash_account=True, is_active=True
        )

        if not cash_accounts.exists():
            cash_accounts = ChartOfAccounts.objects.filter(
                code__startswith="1001", is_active=True
            )

        cash_flows = {"operating": [], "investing": [], "financing": []}

        total_cash_flows = {
            "operating": Decimal("0"),
            "investing": Decimal("0"),
            "financing": Decimal("0"),
        }

        # تصنيف التدفقات النقدية حسب نوع المعاملة
        for cash_account in cash_accounts:
            account_flows = cls._analyze_cash_account_flows(
                cash_account, date_from, date_to
            )

            for flow_type, flows in account_flows.items():
                cash_flows[flow_type].extend(flows)
                total_cash_flows[flow_type] += sum(flow["amount"] for flow in flows)

        # حساب صافي التدفق النقدي
        net_cash_flow = sum(total_cash_flows.values())

        # الرصيد النقدي في بداية ونهاية الفترة
        opening_balance = sum(
            EnhancedBalanceService.get_account_balance_optimized(
                acc, date_to=date_from - timedelta(days=1)
            )
            for acc in cash_accounts
        )

        closing_balance = sum(
            EnhancedBalanceService.get_account_balance_optimized(acc, date_to=date_to)
            for acc in cash_accounts
        )

        return {
            "report_info": {
                "title": "قائمة التدفقات النقدية",
                "period_from": date_from,
                "period_to": date_to,
                "generated_at": timezone.now(),
            },
            "cash_flows": cash_flows,
            "totals": total_cash_flows,
            "net_cash_flow": net_cash_flow,
            "opening_balance": opening_balance,
            "closing_balance": closing_balance,
            "calculated_closing": opening_balance + net_cash_flow,
        }

    @classmethod
    def _analyze_cash_account_flows(
        cls, cash_account: ChartOfAccounts, date_from: date, date_to: date
    ) -> Dict:
        """
        تحليل التدفقات النقدية لحساب معين
        """
        # هذا مبسط - في الواقع يحتاج تصنيف أكثر تعقيداً
        query = """
        SELECT 
            je.description,
            je.reference,
            jel.debit,
            jel.credit,
            je.date
        FROM financial_journalentryline jel
        INNER JOIN financial_journalentry je ON jel.journal_entry_id = je.id
        WHERE jel.account_id = %s
            AND je.status = 'posted'
            AND je.date BETWEEN %s AND %s
        ORDER BY je.date
        """

        flows = {"operating": [], "investing": [], "financing": []}

        with connection.cursor() as cursor:
            cursor.execute(query, [cash_account.id, date_from, date_to])

            for row in cursor.fetchall():
                description, reference, debit, credit, trans_date = row
                amount = Decimal(str(debit or 0)) - Decimal(str(credit or 0))

                # تصنيف بسيط حسب الوصف والمرجع
                flow_type = cls._classify_cash_flow(description, reference)

                flows[flow_type].append(
                    {
                        "date": trans_date,
                        "description": description,
                        "reference": reference,
                        "amount": amount,
                    }
                )

        return flows

    @classmethod
    def _classify_cash_flow(cls, description: str, reference: str) -> str:
        """
        تصنيف نوع التدفق النقدي
        """
        description_lower = description.lower() if description else ""
        reference_lower = reference.lower() if reference else ""

        # تصنيف بسيط - يمكن تحسينه
        if any(keyword in description_lower for keyword in ["مبيعات", "عميل", "إيراد"]):
            return "operating"
        elif any(
            keyword in description_lower for keyword in ["مشتريات", "مورد", "مصروف"]
        ):
            return "operating"
        elif any(
            keyword in description_lower for keyword in ["استثمار", "أصل", "معدات"]
        ):
            return "investing"
        elif any(keyword in description_lower for keyword in ["قرض", "رأس مال", "سهم"]):
            return "financing"
        else:
            return "operating"  # افتراضي

    @classmethod
    def generate_accounts_aging_report(
        cls, account_type: str, as_of_date: date  # 'receivables' or 'payables'
    ) -> Dict:
        """
        تقرير أعمار الحسابات (الذمم)
        """
        # تحديد نوع الحساب
        if account_type == "receivables":
            base_account_code = "11030"  # العملاء
            title = "أعمار الذمم المدينة"
        else:
            base_account_code = "21010"  # الموردين
            title = "أعمار الذمم الدائنة"

        # الحصول على الحساب الأساسي
        try:
            base_account = ChartOfAccounts.objects.get(
                code=base_account_code, is_active=True
            )
        except ChartOfAccounts.DoesNotExist:
            return {"error": f"الحساب {base_account_code} غير موجود"}

        # تحليل الأعمار
        aging_periods = [
            ("current", 0, 30, "جاري"),
            ("30_60", 31, 60, "31-60 يوم"),
            ("60_90", 61, 90, "61-90 يوم"),
            ("over_90", 91, 999999, "أكثر من 90 يوم"),
        ]

        aging_data = {}
        total_balance = Decimal("0")

        for period_key, days_from, days_to, period_name in aging_periods:
            # تجنب الأخطاء في التواريخ الكبيرة جداً
            if days_to >= 999999:
                # للفترة الأخيرة، نستخدم تاريخ بعيد جداً (10 سنوات)
                period_from = as_of_date - timedelta(days=3650)
            else:
                period_from = as_of_date - timedelta(days=days_to)
            
            period_to = as_of_date - timedelta(days=days_from)

            balance = EnhancedBalanceService.get_account_balance_optimized(
                base_account, date_from=period_from, date_to=period_to
            )

            aging_data[period_key] = {
                "name": period_name,
                "balance": balance,
                "days_from": days_from,
                "days_to": days_to if days_to < 999999 else None,
            }

            total_balance += balance

        return {
            "report_info": {
                "title": title,
                "as_of_date": as_of_date,
                "generated_at": timezone.now(),
                "account_type": account_type,
            },
            "aging_periods": aging_data,
            "total_balance": total_balance,
            "base_account": {"code": base_account.code, "name": base_account.name},
        }

    @classmethod
    def generate_financial_ratios_report(cls, as_of_date: date) -> Dict:
        """
        تقرير النسب المالية
        """
        # الحصول على بيانات الميزانية وقائمة الدخل
        balance_sheet = cls.generate_balance_sheet(as_of_date)

        # فترة سنة للدخل
        year_start = date(as_of_date.year, 1, 1)
        income_statement = cls.generate_income_statement(year_start, as_of_date)

        # استخراج القيم المطلوبة
        total_assets = balance_sheet["totals"]["total_assets"]
        total_liabilities = balance_sheet["totals"]["total_liabilities"]
        total_equity = balance_sheet["totals"]["total_equity"]

        total_revenue = income_statement["current_period"]["total_revenue"]
        net_income = income_statement["current_period"]["net_income"]

        # حساب النسب المالية
        ratios = {}

        # نسب السيولة
        ratios["liquidity"] = {
            "debt_to_equity": (total_liabilities / total_equity)
            if total_equity > 0
            else Decimal("0"),
            "equity_ratio": (total_equity / total_assets)
            if total_assets > 0
            else Decimal("0"),
            "debt_ratio": (total_liabilities / total_assets)
            if total_assets > 0
            else Decimal("0"),
        }

        # نسب الربحية
        ratios["profitability"] = {
            "profit_margin": (net_income / total_revenue * 100)
            if total_revenue > 0
            else Decimal("0"),
            "return_on_assets": (net_income / total_assets * 100)
            if total_assets > 0
            else Decimal("0"),
            "return_on_equity": (net_income / total_equity * 100)
            if total_equity > 0
            else Decimal("0"),
        }

        # نسب النشاط
        ratios["activity"] = {
            "asset_turnover": (total_revenue / total_assets)
            if total_assets > 0
            else Decimal("0")
        }

        return {
            "report_info": {
                "title": "تقرير النسب المالية",
                "as_of_date": as_of_date,
                "generated_at": timezone.now(),
            },
            "ratios": ratios,
            "base_data": {
                "total_assets": total_assets,
                "total_liabilities": total_liabilities,
                "total_equity": total_equity,
                "total_revenue": total_revenue,
                "net_income": net_income,
            },
        }

    @classmethod
    def clear_reports_cache(cls):
        """
        مسح كاش التقارير
        """
        financial_cache.delete_pattern("trial_balance*")
        financial_cache.delete_pattern("income_statement*")
        financial_cache.delete_pattern("balance_sheet*")
        financial_cache.delete_pattern("cash_flow*")

        logger.info("تم مسح كاش التقارير المالية")
