"""
خدمات تحسين الأداء باستخدام Window Functions والاستعلامات المحسنة
"""
from django.db import connection, models
from django.utils import timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Union
from datetime import date, datetime
import logging

logger = logging.getLogger(__name__)


class PerformanceOptimizer:
    """
    محسن الأداء للاستعلامات المالية
    """

    @classmethod
    def get_account_running_balances(
        cls,
        account_id: int,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: int = 1000,
    ) -> List[Dict]:
        """
        الحصول على الأرصدة الجارية للحساب باستخدام Window Functions
        """
        query = """
        WITH account_transactions AS (
            SELECT 
                je.id as entry_id,
                je.number as entry_number,
                je.date,
                je.description,
                jel.debit,
                jel.credit,
                jel.description as line_description,
                -- حساب الرصيد الجاري باستخدام Window Function
                SUM(jel.debit - jel.credit) OVER (
                    ORDER BY je.date, je.id 
                    ROWS UNBOUNDED PRECEDING
                ) as running_balance,
                -- ترقيم الصفوف
                ROW_NUMBER() OVER (ORDER BY je.date, je.id) as row_num
            FROM financial_journalentryline jel
            INNER JOIN financial_journalentry je ON jel.journal_entry_id = je.id
            WHERE jel.account_id = %s 
                AND je.status = 'posted'
        """

        params = [account_id]

        if date_from:
            query += " AND je.date >= %s"
            params.append(date_from)

        if date_to:
            query += " AND je.date <= %s"
            params.append(date_to)

        query += """
        )
        SELECT 
            entry_id,
            entry_number,
            date,
            description,
            debit,
            credit,
            line_description,
            running_balance,
            row_num
        FROM account_transactions
        ORDER BY date, entry_id
        """

        if limit:
            query += f" LIMIT {limit}"

        with connection.cursor() as cursor:
            cursor.execute(query, params)
            columns = [col[0] for col in cursor.description]

            results = []
            for row in cursor.fetchall():
                row_dict = dict(zip(columns, row))

                # تحويل القيم المالية إلى Decimal
                for key in ["debit", "credit", "running_balance"]:
                    row_dict[key] = Decimal(str(row_dict[key] or 0))

                results.append(row_dict)

        return results

    @classmethod
    def get_monthly_balances_summary(
        cls, account_ids: List[int] = None, year: int = None
    ) -> List[Dict]:
        """
        ملخص الأرصدة الشهرية باستخدام Window Functions
        """
        if not year:
            year = timezone.now().year

        query = """
        WITH monthly_movements AS (
            SELECT 
                coa.id as account_id,
                coa.code,
                coa.name,
                EXTRACT(MONTH FROM je.date) as month,
                EXTRACT(YEAR FROM je.date) as year,
                SUM(jel.debit) as monthly_debit,
                SUM(jel.credit) as monthly_credit,
                SUM(jel.debit - jel.credit) as monthly_net
            FROM financial_chartofaccounts coa
            LEFT JOIN financial_journalentryline jel ON coa.id = jel.account_id
            LEFT JOIN financial_journalentry je ON jel.journal_entry_id = je.id 
                AND je.status = 'posted'
                AND EXTRACT(YEAR FROM je.date) = %s
            WHERE coa.is_leaf = true AND coa.is_active = true
        """

        params = [year]

        if account_ids:
            placeholders = ",".join(["%s"] * len(account_ids))
            query += f" AND coa.id IN ({placeholders})"
            params.extend(account_ids)

        query += """
            GROUP BY coa.id, coa.code, coa.name, EXTRACT(MONTH FROM je.date), EXTRACT(YEAR FROM je.date)
        ),
        cumulative_balances AS (
            SELECT 
                account_id,
                code,
                name,
                month,
                year,
                monthly_debit,
                monthly_credit,
                monthly_net,
                -- الرصيد التراكمي
                SUM(monthly_net) OVER (
                    PARTITION BY account_id 
                    ORDER BY year, month 
                    ROWS UNBOUNDED PRECEDING
                ) as cumulative_balance,
                -- المقارنة مع الشهر السابق
                LAG(monthly_net) OVER (
                    PARTITION BY account_id 
                    ORDER BY year, month
                ) as previous_month_net,
                -- نسبة التغيير
                CASE 
                    WHEN LAG(monthly_net) OVER (
                        PARTITION BY account_id 
                        ORDER BY year, month
                    ) != 0 THEN
                        (monthly_net - LAG(monthly_net) OVER (
                            PARTITION BY account_id 
                            ORDER BY year, month
                        )) / ABS(LAG(monthly_net) OVER (
                            PARTITION BY account_id 
                            ORDER BY year, month
                        )) * 100
                    ELSE NULL
                END as change_percentage
            FROM monthly_movements
            WHERE year IS NOT NULL AND month IS NOT NULL
        )
        SELECT 
            account_id,
            code,
            name,
            month,
            year,
            COALESCE(monthly_debit, 0) as monthly_debit,
            COALESCE(monthly_credit, 0) as monthly_credit,
            COALESCE(monthly_net, 0) as monthly_net,
            COALESCE(cumulative_balance, 0) as cumulative_balance,
            COALESCE(previous_month_net, 0) as previous_month_net,
            COALESCE(change_percentage, 0) as change_percentage
        FROM cumulative_balances
        ORDER BY code, year, month
        """

        with connection.cursor() as cursor:
            cursor.execute(query, params)
            columns = [col[0] for col in cursor.description]

            results = []
            for row in cursor.fetchall():
                row_dict = dict(zip(columns, row))

                # تحويل القيم المالية إلى Decimal
                for key in [
                    "monthly_debit",
                    "monthly_credit",
                    "monthly_net",
                    "cumulative_balance",
                    "previous_month_net",
                    "change_percentage",
                ]:
                    row_dict[key] = Decimal(str(row_dict[key] or 0))

                results.append(row_dict)

        return results

    @classmethod
    def get_top_accounts_by_activity(
        cls,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: int = 20,
    ) -> List[Dict]:
        """
        أكثر الحسابات نشاطاً باستخدام Window Functions
        """
        query = """
        WITH account_activity AS (
            SELECT 
                coa.id,
                coa.code,
                coa.name,
                COUNT(jel.id) as transactions_count,
                SUM(ABS(jel.debit) + ABS(jel.credit)) as total_activity,
                AVG(ABS(jel.debit) + ABS(jel.credit)) as avg_transaction_size,
                MIN(je.date) as first_transaction,
                MAX(je.date) as last_transaction,
                -- ترتيب حسب النشاط
                ROW_NUMBER() OVER (ORDER BY COUNT(jel.id) DESC) as activity_rank,
                -- ترتيب حسب حجم المعاملات
                ROW_NUMBER() OVER (ORDER BY SUM(ABS(jel.debit) + ABS(jel.credit)) DESC) as volume_rank,
                -- نسبة النشاط من إجمالي النشاط
                COUNT(jel.id) * 100.0 / SUM(COUNT(jel.id)) OVER () as activity_percentage
            FROM financial_chartofaccounts coa
            INNER JOIN financial_journalentryline jel ON coa.id = jel.account_id
            INNER JOIN financial_journalentry je ON jel.journal_entry_id = je.id
            WHERE coa.is_leaf = true 
                AND coa.is_active = true 
                AND je.status = 'posted'
        """

        params = []

        if date_from:
            query += " AND je.date >= %s"
            params.append(date_from)

        if date_to:
            query += " AND je.date <= %s"
            params.append(date_to)

        query += """
            GROUP BY coa.id, coa.code, coa.name
            HAVING COUNT(jel.id) > 0
        )
        SELECT 
            id,
            code,
            name,
            transactions_count,
            total_activity,
            avg_transaction_size,
            first_transaction,
            last_transaction,
            activity_rank,
            volume_rank,
            activity_percentage
        FROM account_activity
        ORDER BY transactions_count DESC
        """

        if limit:
            query += f" LIMIT {limit}"

        with connection.cursor() as cursor:
            cursor.execute(query, params)
            columns = [col[0] for col in cursor.description]

            results = []
            for row in cursor.fetchall():
                row_dict = dict(zip(columns, row))

                # تحويل القيم المالية إلى Decimal
                for key in [
                    "total_activity",
                    "avg_transaction_size",
                    "activity_percentage",
                ]:
                    row_dict[key] = Decimal(str(row_dict[key] or 0))

                results.append(row_dict)

        return results

    @classmethod
    def get_balance_trends_analysis(
        cls, account_ids: List[int], days_back: int = 30
    ) -> Dict:
        """
        تحليل اتجاهات الأرصدة باستخدام Window Functions
        """
        end_date = timezone.now().date()
        start_date = end_date - timezone.timedelta(days=days_back)

        query = """
        WITH daily_balances AS (
            SELECT 
                coa.id as account_id,
                coa.code,
                coa.name,
                je.date,
                SUM(jel.debit - jel.credit) OVER (
                    PARTITION BY coa.id 
                    ORDER BY je.date, je.id 
                    ROWS UNBOUNDED PRECEDING
                ) as running_balance,
                -- المتوسط المتحرك لـ 7 أيام
                AVG(SUM(jel.debit - jel.credit)) OVER (
                    PARTITION BY coa.id 
                    ORDER BY je.date 
                    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
                ) as moving_avg_7d,
                -- الانحراف المعياري
                STDDEV(SUM(jel.debit - jel.credit)) OVER (
                    PARTITION BY coa.id 
                    ORDER BY je.date 
                    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
                ) as volatility_7d
            FROM financial_chartofaccounts coa
            INNER JOIN financial_journalentryline jel ON coa.id = jel.account_id
            INNER JOIN financial_journalentry je ON jel.journal_entry_id = je.id
            WHERE coa.id = ANY(%s)
                AND je.status = 'posted'
                AND je.date BETWEEN %s AND %s
            GROUP BY coa.id, coa.code, coa.name, je.date, je.id
        ),
        trend_analysis AS (
            SELECT 
                account_id,
                code,
                name,
                COUNT(*) as data_points,
                MIN(running_balance) as min_balance,
                MAX(running_balance) as max_balance,
                AVG(running_balance) as avg_balance,
                STDDEV(running_balance) as balance_volatility,
                -- اتجاه الرصيد (موجب = صاعد، سالب = هابط)
                (LAST_VALUE(running_balance) OVER (
                    PARTITION BY account_id 
                    ORDER BY date 
                    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
                ) - FIRST_VALUE(running_balance) OVER (
                    PARTITION BY account_id 
                    ORDER BY date 
                    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
                )) as trend_direction,
                -- معدل التغيير اليومي
                AVG(running_balance - LAG(running_balance) OVER (
                    PARTITION BY account_id ORDER BY date
                )) as daily_change_rate
            FROM daily_balances
            GROUP BY account_id, code, name
        )
        SELECT 
            account_id,
            code,
            name,
            data_points,
            COALESCE(min_balance, 0) as min_balance,
            COALESCE(max_balance, 0) as max_balance,
            COALESCE(avg_balance, 0) as avg_balance,
            COALESCE(balance_volatility, 0) as balance_volatility,
            COALESCE(trend_direction, 0) as trend_direction,
            COALESCE(daily_change_rate, 0) as daily_change_rate,
            CASE 
                WHEN trend_direction > 0 THEN 'صاعد'
                WHEN trend_direction < 0 THEN 'هابط'
                ELSE 'مستقر'
            END as trend_label
        FROM trend_analysis
        ORDER BY ABS(trend_direction) DESC
        """

        with connection.cursor() as cursor:
            cursor.execute(query, [account_ids, start_date, end_date])
            columns = [col[0] for col in cursor.description]

            results = []
            for row in cursor.fetchall():
                row_dict = dict(zip(columns, row))

                # تحويل القيم المالية إلى Decimal
                for key in [
                    "min_balance",
                    "max_balance",
                    "avg_balance",
                    "balance_volatility",
                    "trend_direction",
                    "daily_change_rate",
                ]:
                    row_dict[key] = Decimal(str(row_dict[key] or 0))

                results.append(row_dict)

        return {
            "analysis_period": f"{start_date} إلى {end_date}",
            "accounts_analyzed": len(results),
            "trends": results,
        }

    @classmethod
    def optimize_journal_entry_queries(cls) -> Dict:
        """
        تحسين استعلامات القيود المحاسبية
        """
        optimizations = []

        # إنشاء فهارس محسنة
        indexes_to_create = [
            {
                "table": "financial_journalentry",
                "columns": ["date", "status", "id"],
                "name": "idx_je_date_status_id",
            },
            {
                "table": "financial_journalentryline",
                "columns": ["account_id", "journal_entry_id"],
                "name": "idx_jel_account_entry",
            },
            {
                "table": "financial_journalentryline",
                "columns": ["debit", "credit"],
                "name": "idx_jel_amounts",
            },
        ]

        with connection.cursor() as cursor:
            for index in indexes_to_create:
                try:
                    columns_str = ", ".join(index["columns"])
                    query = f"""
                    CREATE INDEX IF NOT EXISTS {index['name']} 
                    ON {index['table']} ({columns_str})
                    """
                    cursor.execute(query)
                    optimizations.append(f"تم إنشاء الفهرس {index['name']}")
                except Exception as e:
                    optimizations.append(
                        f"خطأ في إنشاء الفهرس {index['name']}: {str(e)}"
                    )

        return {"optimizations_applied": optimizations, "status": "completed"}

    @classmethod
    def analyze_query_performance(cls, query: str, params: List = None) -> Dict:
        """
        تحليل أداء الاستعلام
        """
        with connection.cursor() as cursor:
            # تشغيل EXPLAIN ANALYZE
            explain_query = f"EXPLAIN ANALYZE {query}"

            start_time = timezone.now()
            cursor.execute(explain_query, params or [])
            end_time = timezone.now()

            execution_plan = cursor.fetchall()
            execution_time = (end_time - start_time).total_seconds()

            return {
                "execution_time_seconds": execution_time,
                "execution_plan": execution_plan,
                "query": query,
                "params": params,
            }
