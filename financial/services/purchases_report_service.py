"""
خدمة تقرير المشتريات
توفر تحليل شامل للمشتريات والمصروفات
"""

from decimal import Decimal
from datetime import datetime, timedelta
from django.db.models import Sum, Count
from django.utils import timezone
from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.journal_entry import JournalEntryLine


class PurchasesReportService:
    """
    خدمة تقرير المشتريات
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

    def get_purchases_by_account(self):
        """
        الحصول على المشتريات مجمعة حسب الحساب
        
        Returns:
            dict: قائمة المشتريات حسب الحساب
        """
        # جلب حسابات المصروفات
        expense_accounts = ChartOfAccounts.objects.filter(
            account_type__category="expense"
        )

        purchases_data = []
        total_purchases = Decimal("0")

        for account in expense_accounts:
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

            # المصروفات لها رصيد مدين
            balance = total_debit - total_credit

            if balance > 0:  # عرض الحسابات ذات المصروفات فقط
                purchases_data.append({
                    "account": account,
                    "account_code": account.code,
                    "account_name": account.name,
                    "amount": balance,
                    "transactions_count": transactions_count,
                    "percentage": Decimal("0")  # سيتم حسابها لاحقاً
                })
                total_purchases += balance

        # حساب النسب المئوية
        if total_purchases > 0:
            for item in purchases_data:
                try:
                    item["percentage"] = (item["amount"] / total_purchases * 100).quantize(Decimal("0.01"))
                except:
                    item["percentage"] = Decimal("0")

        # ترتيب حسب المبلغ (الأعلى أولاً)
        purchases_data.sort(key=lambda x: x["amount"], reverse=True)

        return {
            "purchases_data": purchases_data,
            "total_purchases": total_purchases
        }

    def get_purchases_statistics(self):
        """
        حساب إحصائيات المشتريات
        
        Returns:
            dict: الإحصائيات
        """
        result = self.get_purchases_by_account()
        total_purchases = result["total_purchases"]
        purchases_data = result["purchases_data"]

        # عدد الأيام
        days_count = (self.date_to - self.date_from).days + 1

        # متوسط المشتريات اليومية
        try:
            avg_daily_purchases = (total_purchases / Decimal(str(days_count))).quantize(Decimal("0.01")) if days_count > 0 else Decimal("0")
        except:
            avg_daily_purchases = Decimal("0")

        # عدد المعاملات
        total_transactions = sum(item["transactions_count"] for item in purchases_data)

        # متوسط قيمة المعاملة
        try:
            avg_transaction_value = (total_purchases / Decimal(str(total_transactions))).quantize(Decimal("0.01")) if total_transactions > 0 else Decimal("0")
        except:
            avg_transaction_value = Decimal("0")

        # أعلى حساب مصروفات
        top_account = purchases_data[0] if purchases_data else None

        return {
            "total_purchases": total_purchases,
            "avg_daily_purchases": avg_daily_purchases,
            "total_transactions": total_transactions,
            "avg_transaction_value": avg_transaction_value,
            "top_account": top_account,
            "days_count": days_count,
            "accounts_count": len(purchases_data)
        }

    def get_monthly_comparison(self, months=6):
        """
        مقارنة المشتريات الشهرية
        
        Args:
            months: عدد الأشهر (افتراضي: 6)
            
        Returns:
            dict: بيانات المقارنة الشهرية
        """
        expense_accounts = ChartOfAccounts.objects.filter(
            account_type__category="expense"
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

            # حساب المشتريات
            result = JournalEntryLine.objects.filter(
                account__in=expense_accounts,
                journal_entry__date__range=[month_start, month_end],
                journal_entry__status='posted'
            ).aggregate(
                total_debit=Sum("debit"),
                total_credit=Sum("credit")
            )
            total_debit = Decimal(str(result["total_debit"])) if result["total_debit"] is not None else Decimal("0")
            total_credit = Decimal(str(result["total_credit"])) if result["total_credit"] is not None else Decimal("0")
            monthly_purchases = total_debit - total_credit
            
            data.append(float(monthly_purchases))

        return {
            "labels": labels,
            "data": data
        }

    def get_purchases_by_category(self):
        """
        تجميع المشتريات حسب فئة الحساب
        
        Returns:
            dict: المشتريات حسب الفئة
        """
        expense_accounts = ChartOfAccounts.objects.filter(
            account_type__category="expense"
        )

        # تجميع حسب نوع الحساب
        categories = {}
        
        for account in expense_accounts:
            category = account.account_type.name
            
            # حساب المشتريات لهذا الحساب
            result = JournalEntryLine.objects.filter(
                account=account,
                journal_entry__date__range=[self.date_from, self.date_to],
                journal_entry__status='posted'
            ).aggregate(
                total_debit=Sum("debit"),
                total_credit=Sum("credit")
            )
            total_debit = Decimal(str(result["total_debit"])) if result["total_debit"] is not None else Decimal("0")
            total_credit = Decimal(str(result["total_credit"])) if result["total_credit"] is not None else Decimal("0")
            purchases = total_debit - total_credit

            if purchases > 0:
                if category not in categories:
                    categories[category] = Decimal("0")
                categories[category] += purchases

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
        purchases_by_account = self.get_purchases_by_account()
        statistics = self.get_purchases_statistics()
        monthly_comparison = self.get_monthly_comparison()
        purchases_by_category = self.get_purchases_by_category()

        return {
            "purchases_data": purchases_by_account["purchases_data"],
            "total_purchases": purchases_by_account["total_purchases"],
            "statistics": statistics,
            "monthly_comparison": monthly_comparison,
            "purchases_by_category": purchases_by_category,
            "date_from": self.date_from,
            "date_to": self.date_to,
        }
