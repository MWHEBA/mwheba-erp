"""
خدمة تقرير المبيعات
توفر تحليل شامل للمبيعات والإيرادات
"""

from decimal import Decimal
from datetime import datetime, timedelta
from django.db.models import Sum, Count, Q, Avg
from django.utils import timezone
from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.journal_entry import JournalEntry, JournalEntryLine


class SalesReportService:
    """
    خدمة تقرير المبيعات
    """

    def __init__(self, date_from=None, date_to=None):
        """
        تهيئة الخدمة
        
        Args:
            date_from: تاريخ البداية (افتراضي: أول الشهر الحالي)
            date_to: تاريخ النهاية (افتراضي: اليوم)
        """
        today = timezone.now().date()
        self.date_to = date_to or today
        self.date_from = date_from or datetime(today.year, today.month, 1).date()

    def get_sales_by_account(self):
        """
        الحصول على المبيعات مجمعة حسب الحساب
        
        Returns:
            list: قائمة المبيعات حسب الحساب
        """
        # جلب حسابات الإيرادات
        revenue_accounts = ChartOfAccounts.objects.filter(
            account_type__category="revenue"
        )

        sales_data = []
        total_sales = Decimal("0")

        for account in revenue_accounts:
            # جلب القيود المرحلة فقط
            journal_lines = JournalEntryLine.objects.filter(
                account=account,
                journal_entry__date__range=[self.date_from, self.date_to],
                journal_entry__status='posted'
            )

            # حساب المجاميع
            totals = journal_lines.aggregate(
                total_debit=Sum("debit"),
                total_credit=Sum("credit"),
                count=Count("id")
            )

            total_debit = Decimal(str(totals["total_debit"])) if totals["total_debit"] is not None else Decimal("0")
            total_credit = Decimal(str(totals["total_credit"])) if totals["total_credit"] is not None else Decimal("0")
            transactions_count = totals["count"] or 0

            # الإيرادات لها رصيد دائن
            balance = total_credit - total_debit

            if balance > 0:  # عرض الحسابات ذات الإيرادات فقط
                sales_data.append({
                    "account": account,
                    "account_code": account.code,
                    "account_name": account.name,
                    "total_amount": balance,  # تغيير من amount إلى total_amount
                    "transaction_count": transactions_count,  # تغيير من transactions_count إلى transaction_count
                    "percentage": Decimal("0")  # سيتم حسابها لاحقاً
                })
                total_sales += balance

        # حساب النسب المئوية
        if total_sales > 0:
            for item in sales_data:
                try:
                    item["percentage"] = (item["total_amount"] / total_sales * 100).quantize(Decimal("0.01"))
                except:
                    item["percentage"] = Decimal("0")

        # ترتيب حسب المبلغ (الأعلى أولاً)
        sales_data.sort(key=lambda x: x["total_amount"], reverse=True)

        return {
            "sales_data": sales_data,
            "total_sales": total_sales
        }

    def get_sales_statistics(self):
        """
        حساب إحصائيات المبيعات
        
        Returns:
            dict: الإحصائيات
        """
        result = self.get_sales_by_account()
        total_sales = result["total_sales"]
        sales_data = result["sales_data"]

        # عدد الأيام
        days_count = (self.date_to - self.date_from).days + 1

        # متوسط المبيعات اليومية
        avg_daily_sales = total_sales / days_count if days_count > 0 else Decimal("0")

        # عدد المعاملات
        total_transactions = sum(item["transaction_count"] for item in sales_data)

        # متوسط قيمة المعاملة
        avg_transaction_value = total_sales / total_transactions if total_transactions > 0 else Decimal("0")

        # أعلى حساب مبيعات
        top_account = sales_data[0] if sales_data else None

        return {
            "total_sales": total_sales,
            "avg_daily_sales": avg_daily_sales,
            "total_transactions": total_transactions,
            "avg_transaction_value": avg_transaction_value,
            "top_account": top_account,
            "days_count": days_count,
            "accounts_count": len(sales_data)
        }

    def get_daily_sales_trend(self):
        """
        الحصول على اتجاه المبيعات اليومي
        
        Returns:
            dict: بيانات الاتجاه اليومي
        """
        revenue_accounts = ChartOfAccounts.objects.filter(
            account_type__category="revenue"
        )

        # جلب المبيعات اليومية
        # جلب المبيعات اليومية (بدون عمليات حسابية في aggregate)
        from collections import defaultdict
        daily_totals = defaultdict(lambda: {'debit': Decimal('0'), 'credit': Decimal('0')})
        
        lines = JournalEntryLine.objects.filter(
            account__in=revenue_accounts,
            journal_entry__date__range=[self.date_from, self.date_to],
            journal_entry__status='posted'
        ).select_related('journal_entry')
        
        for line in lines:
            date = line.journal_entry.date
            daily_totals[date]['debit'] += line.debit
            daily_totals[date]['credit'] += line.credit
        
        daily_sales = sorted(
            [{'journal_entry__date': date, 'daily_total': totals['credit'] - totals['debit']} 
             for date, totals in daily_totals.items()],
            key=lambda x: x['journal_entry__date']
        )

        labels = []
        data = []

        for item in daily_sales:
            date = item["journal_entry__date"]
            amount = item["daily_total"] or Decimal("0")
            
            if amount > 0:
                labels.append(date.strftime("%Y-%m-%d"))
                data.append(float(amount))

        return {
            "labels": labels,
            "data": data
        }

    def get_monthly_comparison(self, months=6):
        """
        مقارنة المبيعات الشهرية
        
        Args:
            months: عدد الأشهر (افتراضي: 6)
            
        Returns:
            dict: بيانات المقارنة الشهرية
        """
        revenue_accounts = ChartOfAccounts.objects.filter(
            account_type__category="revenue"
        )

        labels = []
        data = []

        # حساب بيانات كل شهر
        for i in range(months - 1, -1, -1):
            # حساب تاريخ بداية ونهاية الشهر
            month_end = self.date_to - timedelta(days=30 * i)
            month_start = month_end.replace(day=1)
            
            # اسم الشهر
            month_name = self._get_arabic_month_name(month_end.month)
            labels.append(month_name)

            # حساب المبيعات
            result = JournalEntryLine.objects.filter(
                account__in=revenue_accounts,
                journal_entry__date__range=[month_start, month_end],
                journal_entry__status='posted'
            ).aggregate(
                total_credit=Sum("credit"),
                total_debit=Sum("debit")
            )
            total_credit = Decimal(str(result["total_credit"])) if result["total_credit"] is not None else Decimal("0")
            total_debit = Decimal(str(result["total_debit"])) if result["total_debit"] is not None else Decimal("0")
            monthly_sales = total_credit - total_debit
            
            data.append(float(monthly_sales))

        return {
            "labels": labels,
            "data": data
        }

    def get_sales_by_category(self):
        """
        تجميع المبيعات حسب فئة الحساب
        
        Returns:
            dict: المبيعات حسب الفئة
        """
        revenue_accounts = ChartOfAccounts.objects.filter(
            account_type__category="revenue"
        )

        # تجميع حسب نوع الحساب
        categories = {}
        
        for account in revenue_accounts:
            category = account.account_type.name
            
            # حساب المبيعات لهذا الحساب
            result = JournalEntryLine.objects.filter(
                account=account,
                journal_entry__date__range=[self.date_from, self.date_to],
                journal_entry__status='posted'
            ).aggregate(
                total_credit=Sum("credit"),
                total_debit=Sum("debit")
            )
            total_credit = Decimal(str(result["total_credit"])) if result["total_credit"] is not None else Decimal("0")
            total_debit = Decimal(str(result["total_debit"])) if result["total_debit"] is not None else Decimal("0")
            sales = total_credit - total_debit

            if sales > 0:
                if category not in categories:
                    categories[category] = Decimal("0")
                categories[category] += sales

        # تحويل إلى قوائم
        labels = list(categories.keys())
        data = [float(categories[key]) for key in labels]

        return {
            "labels": labels,
            "data": data
        }

    def _get_arabic_month_name(self, month_number):
        """
        الحصول على اسم الشهر بالعربية
        
        Args:
            month_number: رقم الشهر (1-12)
            
        Returns:
            str: اسم الشهر بالعربية
        """
        months = {
            1: "يناير",
            2: "فبراير",
            3: "مارس",
            4: "إبريل",
            5: "مايو",
            6: "يونيو",
            7: "يوليو",
            8: "أغسطس",
            9: "سبتمبر",
            10: "أكتوبر",
            11: "نوفمبر",
            12: "ديسمبر",
        }
        return months.get(month_number, "")

    def get_complete_report(self):
        """
        الحصول على التقرير الكامل
        
        Returns:
            dict: التقرير الكامل
        """
        sales_by_account = self.get_sales_by_account()
        statistics = self.get_sales_statistics()
        daily_trend = self.get_daily_sales_trend()
        monthly_comparison = self.get_monthly_comparison()
        sales_by_category = self.get_sales_by_category()

        return {
            "sales_data": sales_by_account["sales_data"],
            "total_sales": sales_by_account["total_sales"],
            "statistics": statistics,
            "daily_trend": daily_trend,
            "monthly_comparison": monthly_comparison,
            "sales_by_category": sales_by_category,
            "date_from": self.date_from,
            "date_to": self.date_to,
        }
