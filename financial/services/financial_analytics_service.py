"""
خدمة التحليلات المالية
توفر مؤشرات مالية متقدمة وتحليلات شاملة
"""

from decimal import Decimal
from datetime import datetime, timedelta
from django.db.models import Sum, Count, Q, Avg, F
from django.utils import timezone
from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.journal_entry import JournalEntry, JournalEntryLine
from client.models import Customer


class FinancialAnalyticsService:
    """
    خدمة التحليلات المالية
    """

    def __init__(self, date_from=None, date_to=None):
        """
        تهيئة الخدمة
        
        Args:
            date_from: تاريخ البداية (افتراضي: أول الشهر الحالي)
            date_to: تاريخ النهاية (افتراضي: اليوم)
        """
        self.date_to = date_to or timezone.now().date()
        self.date_from = date_from or self.date_to.replace(day=1)

    def get_basic_metrics(self):
        """
        حساب المؤشرات المالية الأساسية
        
        Returns:
            dict: المؤشرات الأساسية
        """
        # حساب الإيرادات
        income_accounts = ChartOfAccounts.objects.filter(
            account_type__category="income"
        )
        
        monthly_income = JournalEntryLine.objects.filter(
            account__in=income_accounts,
            journal_entry__date__range=[self.date_from, self.date_to],
            journal_entry__status='posted'
        ).aggregate(total=Sum("credit"))["total"] or Decimal("0")

        # حساب المصروفات
        expense_accounts = ChartOfAccounts.objects.filter(
            account_type__category="expense"
        )
        
        monthly_expenses = JournalEntryLine.objects.filter(
            account__in=expense_accounts,
            journal_entry__date__range=[self.date_from, self.date_to],
            journal_entry__status='posted'
        ).aggregate(total=Sum("debit"))["total"] or Decimal("0")

        # حساب صافي الربح
        net_profit = monthly_income - monthly_expenses

        # حساب هامش الربح
        profit_margin = Decimal("0")
        if monthly_income > 0:
            profit_margin = (net_profit / monthly_income) * 100

        # حساب متوسط قيمة القيد
        entries = JournalEntry.objects.filter(
            date__range=[self.date_from, self.date_to],
            status='posted'
        )
        
        avg_entry_value = Decimal("0")
        if entries.exists():
            total_debit = entries.aggregate(
                total=Sum("lines__debit")
            )["total"] or Decimal("0")
            avg_entry_value = total_debit / entries.count() if entries.count() > 0 else Decimal("0")

        # عدد المعاملات اليومية
        today = timezone.now().date()
        daily_transactions = JournalEntry.objects.filter(
            date=today,
            status='posted'
        ).count()

        return {
            "monthly_income": monthly_income,
            "monthly_expenses": monthly_expenses,
            "net_profit": net_profit,
            "profit_margin": profit_margin.quantize(Decimal("0.01")),
            "avg_entry_value": avg_entry_value,
            "daily_transactions": daily_transactions,
        }

    def get_advanced_metrics(self):
        """
        حساب مؤشرات الأداء المتقدمة
        
        Returns:
            dict: المؤشرات المتقدمة
        """
        # معدل التحصيل (نسبة المدفوعات من إجمالي الفواتير)
        receivable_accounts = ChartOfAccounts.objects.filter(
            account_type__category="asset",
            name__icontains="عملاء"
        )
        
        total_receivables = Decimal("0")
        for account in receivable_accounts:
            balance = self._get_account_balance(account)
            if balance > 0:  # مدين (ذمم مدينة)
                total_receivables += balance

        # إجمالي المبيعات
        income_accounts = ChartOfAccounts.objects.filter(
            account_type__category="income"
        )
        total_sales = JournalEntryLine.objects.filter(
            account__in=income_accounts,
            journal_entry__date__range=[self.date_from, self.date_to],
            journal_entry__status='posted'
        ).aggregate(total=Sum("credit"))["total"] or Decimal("0")

        # معدل التحصيل
        collection_rate = Decimal("0")
        if total_sales > 0:
            collected = total_sales - total_receivables
            collection_rate = (collected / total_sales) * 100 if collected >= 0 else Decimal("0")

        # عدد العملاء الجدد
        new_customers = Customer.objects.filter(
            created_at__date__range=[self.date_from, self.date_to]
        ).count()

        # متوسط دورة المبيعات (من تاريخ القيد إلى التحصيل)
        # نحسبها من متوسط عمر أرصدة العملاء
        avg_sales_cycle = self._calculate_avg_sales_cycle()

        # الديون المستحقة (أرصدة العملاء المتأخرة)
        due_debt = self._calculate_due_debt()

        return {
            "collection_rate": collection_rate.quantize(Decimal("0.01")),
            "new_customers": new_customers,
            "sales_cycle": avg_sales_cycle,
            "due_debt": due_debt,
            "total_receivables": total_receivables,
        }

    def get_monthly_trends(self, months=6):
        """
        حساب اتجاهات الإيرادات والمصروفات لعدة أشهر
        
        Args:
            months: عدد الأشهر (افتراضي: 6)
            
        Returns:
            dict: بيانات الاتجاهات
        """
        trends = {
            "labels": [],
            "revenue": [],
            "expenses": [],
        }

        # حساب بيانات كل شهر
        for i in range(months - 1, -1, -1):
            # حساب تاريخ بداية ونهاية الشهر
            month_end = self.date_to - timedelta(days=30 * i)
            month_start = month_end.replace(day=1)
            
            # اسم الشهر
            month_name = month_end.strftime("%B")
            month_name_ar = self._get_arabic_month_name(month_end.month)
            trends["labels"].append(month_name_ar)

            # حساب الإيرادات
            income_accounts = ChartOfAccounts.objects.filter(
                account_type__category="income"
            )
            monthly_revenue = JournalEntryLine.objects.filter(
                account__in=income_accounts,
                journal_entry__date__range=[month_start, month_end],
                journal_entry__status='posted'
            ).aggregate(total=Sum("credit"))["total"] or Decimal("0")
            trends["revenue"].append(float(monthly_revenue))

            # حساب المصروفات
            expense_accounts = ChartOfAccounts.objects.filter(
                account_type__category="expense"
            )
            monthly_expenses = JournalEntryLine.objects.filter(
                account__in=expense_accounts,
                journal_entry__date__range=[month_start, month_end],
                journal_entry__status='posted'
            ).aggregate(total=Sum("debit"))["total"] or Decimal("0")
            trends["expenses"].append(float(monthly_expenses))

        return trends

    def get_expense_distribution(self):
        """
        حساب توزيع المصروفات حسب التصنيف
        
        Returns:
            dict: توزيع المصروفات
        """
        expense_accounts = ChartOfAccounts.objects.filter(
            account_type__category="expense"
        )

        distribution = {
            "labels": [],
            "data": [],
        }

        # تجميع المصروفات حسب نوع الحساب
        for account in expense_accounts:
            total = JournalEntryLine.objects.filter(
                account=account,
                journal_entry__date__range=[self.date_from, self.date_to],
                journal_entry__status='posted'
            ).aggregate(total=Sum("debit"))["total"] or Decimal("0")

            if total > 0:
                distribution["labels"].append(account.name)
                distribution["data"].append(float(total))

        return distribution

    def _get_account_balance(self, account):
        """
        حساب رصيد حساب معين
        
        Args:
            account: الحساب
            
        Returns:
            Decimal: الرصيد
        """
        # حساب المدين
        debit = JournalEntryLine.objects.filter(
            account=account,
            journal_entry__status='posted',
            journal_entry__date__lte=self.date_to
        ).aggregate(total=Sum("debit"))["total"] or Decimal("0")

        # حساب الدائن
        credit = JournalEntryLine.objects.filter(
            account=account,
            journal_entry__status='posted',
            journal_entry__date__lte=self.date_to
        ).aggregate(total=Sum("credit"))["total"] or Decimal("0")

        # الرصيد حسب نوع الحساب
        if account.account_type.category in ["asset", "expense"]:
            return debit - credit
        else:
            return credit - debit

    def _calculate_avg_sales_cycle(self):
        """
        حساب متوسط دورة المبيعات (بالأيام)
        
        Returns:
            Decimal: متوسط الأيام
        """
        # نحسب متوسط عمر أرصدة العملاء
        receivable_accounts = ChartOfAccounts.objects.filter(
            account_type__category="asset",
            name__icontains="عملاء"
        )

        if not receivable_accounts.exists():
            return Decimal("0")

        # جلب آخر قيود لأرصدة العملاء
        recent_entries = JournalEntryLine.objects.filter(
            account__in=receivable_accounts,
            journal_entry__status='posted',
            journal_entry__date__range=[self.date_from, self.date_to]
        ).order_by("-journal_entry__date")[:100]

        if not recent_entries.exists():
            return Decimal("0")

        # حساب متوسط الفترة
        total_days = 0
        count = 0
        today = timezone.now().date()

        for entry in recent_entries:
            days = (today - entry.journal_entry.date).days
            total_days += days
            count += 1

        return Decimal(total_days / count if count > 0 else 0).quantize(Decimal("0.1"))

    def _calculate_due_debt(self):
        """
        حساب الديون المستحقة (المتأخرة أكثر من 30 يوم)
        
        Returns:
            Decimal: إجمالي الديون المستحقة
        """
        receivable_accounts = ChartOfAccounts.objects.filter(
            account_type__category="asset",
            name__icontains="عملاء"
        )

        due_date = self.date_to - timedelta(days=30)
        
        due_debt = JournalEntryLine.objects.filter(
            account__in=receivable_accounts,
            journal_entry__status='posted',
            journal_entry__date__lte=due_date
        ).aggregate(
            debit=Sum("debit"),
            credit=Sum("credit")
        )

        total_debit = due_debt["debit"] or Decimal("0")
        total_credit = due_debt["credit"] or Decimal("0")
        
        return total_debit - total_credit if total_debit > total_credit else Decimal("0")

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

    def get_complete_analytics(self):
        """
        الحصول على جميع التحليلات المالية
        
        Returns:
            dict: جميع التحليلات
        """
        basic_metrics = self.get_basic_metrics()
        advanced_metrics = self.get_advanced_metrics()
        monthly_trends = self.get_monthly_trends()
        expense_distribution = self.get_expense_distribution()

        return {
            "basic_metrics": basic_metrics,
            "advanced_metrics": advanced_metrics,
            "monthly_trends": monthly_trends,
            "expense_distribution": expense_distribution,
            "date_from": self.date_from,
            "date_to": self.date_to,
        }
