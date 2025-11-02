# financial/tests/test_ledger_report.py
"""
اختبارات شاملة لتقرير دفتر الأستاذ
"""

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from decimal import Decimal
from datetime import date, timedelta

from ..models import (
    ChartOfAccounts,
    AccountType,
    JournalEntry,
    JournalEntryLine,
)
from ..services.ledger_service import LedgerService

User = get_user_model()


class LedgerServiceTestCase(TestCase):
    """
    اختبارات خدمة دفتر الأستاذ
    """

    def setUp(self):
        """
        إعداد بيانات الاختبار
        """
        # إنشاء مستخدم
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )

        # إنشاء أنواع حسابات
        self.asset_type = AccountType.objects.create(
            name='أصول متداولة',
            category='asset',
            nature='debit',
            code='1'
        )

        self.revenue_type = AccountType.objects.create(
            name='إيرادات',
            category='revenue',
            nature='credit',
            code='4'
        )

        # إنشاء حسابات
        self.cash_account = ChartOfAccounts.objects.create(
            code='1001',
            name='النقدية',
            account_type=self.asset_type,
            is_leaf=True,
            is_active=True
        )

        self.revenue_account = ChartOfAccounts.objects.create(
            code='4001',
            name='إيرادات المبيعات',
            account_type=self.revenue_type,
            is_leaf=True,
            is_active=True
        )

        # إنشاء قيود محاسبية
        self.create_test_entries()

    def create_test_entries(self):
        """
        إنشاء قيود اختبارية
        """
        # قيد 1: إيراد نقدي 1000
        entry1 = JournalEntry.objects.create(
            number='JE001',
            date=date.today() - timedelta(days=10),
            description='إيراد نقدي',
            status='posted',
            created_by=self.user
        )
        JournalEntryLine.objects.create(
            journal_entry=entry1,
            account=self.cash_account,
            debit=Decimal('1000.00'),
            credit=Decimal('0.00'),
            description='قبض نقدي'
        )
        JournalEntryLine.objects.create(
            journal_entry=entry1,
            account=self.revenue_account,
            debit=Decimal('0.00'),
            credit=Decimal('1000.00'),
            description='إيراد مبيعات'
        )

        # قيد 2: إيراد نقدي 500
        entry2 = JournalEntry.objects.create(
            number='JE002',
            date=date.today() - timedelta(days=5),
            description='إيراد نقدي آخر',
            status='posted',
            created_by=self.user
        )
        JournalEntryLine.objects.create(
            journal_entry=entry2,
            account=self.cash_account,
            debit=Decimal('500.00'),
            credit=Decimal('0.00'),
            description='قبض نقدي'
        )
        JournalEntryLine.objects.create(
            journal_entry=entry2,
            account=self.revenue_account,
            debit=Decimal('0.00'),
            credit=Decimal('500.00'),
            description='إيراد مبيعات'
        )

        # قيد 3: مسودة (لا يجب أن يظهر)
        entry3 = JournalEntry.objects.create(
            number='JE003',
            date=date.today(),
            description='قيد مسودة',
            status='draft',
            created_by=self.user
        )
        JournalEntryLine.objects.create(
            journal_entry=entry3,
            account=self.cash_account,
            debit=Decimal('200.00'),
            credit=Decimal('0.00'),
            description='مسودة'
        )

    def test_get_opening_balance(self):
        """
        اختبار حساب الرصيد الافتتاحي
        """
        # الرصيد الافتتاحي قبل 7 أيام (بعد القيد الأول)
        opening = LedgerService.get_opening_balance(
            self.cash_account,
            date.today() - timedelta(days=7)
        )
        self.assertEqual(opening, Decimal('1000.00'))

        # الرصيد الافتتاحي قبل 15 يوم (قبل كل القيود)
        opening_before = LedgerService.get_opening_balance(
            self.cash_account,
            date.today() - timedelta(days=15)
        )
        self.assertEqual(opening_before, Decimal('0.00'))

    def test_get_account_summary(self):
        """
        اختبار حساب ملخص الحساب
        """
        summary = LedgerService.get_account_summary(self.cash_account)

        # التحقق من المجاميع
        self.assertEqual(summary['total_debit'], Decimal('1500.00'))
        self.assertEqual(summary['total_credit'], Decimal('0.00'))
        self.assertEqual(summary['closing_balance'], Decimal('1500.00'))
        self.assertEqual(summary['transaction_count'], 2)  # فقط المرحلة

    def test_get_account_transactions(self):
        """
        اختبار جلب معاملات الحساب
        """
        transactions = LedgerService.get_account_transactions(self.cash_account)

        # يجب أن يكون هناك 2 معاملة فقط (المرحلة)
        self.assertEqual(len(transactions), 2)

        # التحقق من الرصيد التراكمي
        self.assertEqual(transactions[0]['balance'], Decimal('1000.00'))
        self.assertEqual(transactions[1]['balance'], Decimal('1500.00'))

    def test_get_account_transactions_with_date_filter(self):
        """
        اختبار فلترة المعاملات بالتاريخ
        """
        # فقط آخر 7 أيام
        transactions = LedgerService.get_account_transactions(
            self.cash_account,
            date_from=date.today() - timedelta(days=7)
        )

        # يجب أن يكون هناك معاملة واحدة فقط
        self.assertEqual(len(transactions), 1)
        self.assertEqual(transactions[0]['debit'], Decimal('500.00'))

    def test_get_all_accounts_summary(self):
        """
        اختبار ملخص جميع الحسابات
        """
        summaries = LedgerService.get_all_accounts_summary()

        # يجب أن يكون هناك حسابين نشطين
        self.assertEqual(len(summaries), 2)

        # التحقق من حساب النقدية
        cash_summary = next(s for s in summaries if s['account'].code == '1001')
        self.assertEqual(cash_summary['closing_balance'], Decimal('1500.00'))

        # التحقق من حساب الإيرادات
        revenue_summary = next(s for s in summaries if s['account'].code == '4001')
        self.assertEqual(revenue_summary['closing_balance'], Decimal('1500.00'))

    def test_revenue_account_balance_calculation(self):
        """
        اختبار حساب رصيد حساب دائن (إيرادات)
        """
        summary = LedgerService.get_account_summary(self.revenue_account)

        # الإيرادات حساب دائن - الرصيد = دائن - مدين
        self.assertEqual(summary['total_credit'], Decimal('1500.00'))
        self.assertEqual(summary['total_debit'], Decimal('0.00'))
        self.assertEqual(summary['closing_balance'], Decimal('1500.00'))


class LedgerReportViewTestCase(TestCase):
    """
    اختبارات view تقرير دفتر الأستاذ
    """

    def setUp(self):
        """
        إعداد بيانات الاختبار
        """
        # إنشاء مستخدم
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')

        # إنشاء نوع حساب
        self.asset_type = AccountType.objects.create(
            name='أصول',
            category='asset',
            nature='debit',
            code='1'
        )

        # إنشاء حساب
        self.account = ChartOfAccounts.objects.create(
            code='1001',
            name='النقدية',
            account_type=self.asset_type,
            is_leaf=True,
            is_active=True
        )

    def test_ledger_report_view_accessible(self):
        """
        اختبار إمكانية الوصول للتقرير
        """
        response = self.client.get(reverse('financial:ledger_report'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'financial/reports/ledger_report.html')

    def test_ledger_report_with_account_filter(self):
        """
        اختبار التقرير مع فلتر الحساب
        """
        response = self.client.get(
            reverse('financial:ledger_report'),
            {'account': self.account.id}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('summary', response.context)
        self.assertEqual(response.context['account'], self.account)

    def test_ledger_report_with_date_filter(self):
        """
        اختبار التقرير مع فلتر التاريخ
        """
        response = self.client.get(
            reverse('financial:ledger_report'),
            {
                'date_from': '2025-01-01',
                'date_to': '2025-12-31'
            }
        )
        self.assertEqual(response.status_code, 200)

    def test_ledger_report_excel_export(self):
        """
        اختبار تصدير Excel
        """
        response = self.client.get(
            reverse('financial:ledger_report'),
            {
                'account': self.account.id,
                'export': 'excel'
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    def test_ledger_report_invalid_account(self):
        """
        اختبار التقرير مع حساب غير موجود
        """
        response = self.client.get(
            reverse('financial:ledger_report'),
            {'account': 99999}
        )
        # يجب أن يعيد توجيه أو يعرض رسالة خطأ
        self.assertIn(response.status_code, [302, 404])

    def test_ledger_report_pagination(self):
        """
        اختبار الـ pagination
        """
        # إنشاء 60 قيد لاختبار الـ pagination
        for i in range(60):
            entry = JournalEntry.objects.create(
                number=f'JE{i:03d}',
                date=date.today(),
                description=f'قيد {i}',
                status='posted',
                created_by=self.user
            )
            JournalEntryLine.objects.create(
                journal_entry=entry,
                account=self.account,
                debit=Decimal('100.00'),
                credit=Decimal('0.00')
            )

        response = self.client.get(
            reverse('financial:ledger_report'),
            {'account': self.account.id}
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('page_obj', response.context)
        # يجب أن تكون الصفحة الأولى تحتوي على 50 معاملة
        self.assertEqual(len(response.context['page_obj']), 50)


class LedgerReportIntegrationTestCase(TestCase):
    """
    اختبارات التكامل الشاملة
    """

    def setUp(self):
        """
        إعداد سيناريو واقعي
        """
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )

        # إنشاء دليل حسابات كامل
        self.setup_chart_of_accounts()
        self.create_realistic_transactions()

    def setup_chart_of_accounts(self):
        """
        إنشاء دليل حسابات واقعي
        """
        # أنواع الحسابات
        self.asset_type = AccountType.objects.create(
            name='أصول متداولة',
            category='asset',
            nature='debit',
            code='1'
        )

        self.liability_type = AccountType.objects.create(
            name='خصوم متداولة',
            category='liability',
            nature='credit',
            code='2'
        )

        self.revenue_type = AccountType.objects.create(
            name='إيرادات',
            category='revenue',
            nature='credit',
            code='4'
        )

        self.expense_type = AccountType.objects.create(
            name='مصروفات',
            category='expense',
            nature='debit',
            code='5'
        )

        # الحسابات
        self.cash = ChartOfAccounts.objects.create(
            code='1001',
            name='النقدية',
            account_type=self.asset_type,
            is_leaf=True,
            is_active=True
        )

        self.accounts_receivable = ChartOfAccounts.objects.create(
            code='1101',
            name='العملاء',
            account_type=self.asset_type,
            is_leaf=True,
            is_active=True
        )

        self.accounts_payable = ChartOfAccounts.objects.create(
            code='2101',
            name='الموردين',
            account_type=self.liability_type,
            is_leaf=True,
            is_active=True
        )

        self.sales_revenue = ChartOfAccounts.objects.create(
            code='4001',
            name='إيرادات المبيعات',
            account_type=self.revenue_type,
            is_leaf=True,
            is_active=True
        )

        self.salaries_expense = ChartOfAccounts.objects.create(
            code='5001',
            name='مصروف الرواتب',
            account_type=self.expense_type,
            is_leaf=True,
            is_active=True
        )

    def create_realistic_transactions(self):
        """
        إنشاء معاملات واقعية
        """
        # مبيعات نقدية
        entry1 = JournalEntry.objects.create(
            number='JE001',
            date=date(2025, 1, 15),
            description='مبيعات نقدية',
            status='posted',
            created_by=self.user
        )
        JournalEntryLine.objects.create(
            journal_entry=entry1,
            account=self.cash,
            debit=Decimal('10000.00'),
            credit=Decimal('0.00')
        )
        JournalEntryLine.objects.create(
            journal_entry=entry1,
            account=self.sales_revenue,
            debit=Decimal('0.00'),
            credit=Decimal('10000.00')
        )

        # مبيعات آجلة
        entry2 = JournalEntry.objects.create(
            number='JE002',
            date=date(2025, 1, 20),
            description='مبيعات آجلة',
            status='posted',
            created_by=self.user
        )
        JournalEntryLine.objects.create(
            journal_entry=entry2,
            account=self.accounts_receivable,
            debit=Decimal('5000.00'),
            credit=Decimal('0.00')
        )
        JournalEntryLine.objects.create(
            journal_entry=entry2,
            account=self.sales_revenue,
            debit=Decimal('0.00'),
            credit=Decimal('5000.00')
        )

        # دفع رواتب
        entry3 = JournalEntry.objects.create(
            number='JE003',
            date=date(2025, 1, 25),
            description='دفع رواتب',
            status='posted',
            created_by=self.user
        )
        JournalEntryLine.objects.create(
            journal_entry=entry3,
            account=self.salaries_expense,
            debit=Decimal('3000.00'),
            credit=Decimal('0.00')
        )
        JournalEntryLine.objects.create(
            journal_entry=entry3,
            account=self.cash,
            debit=Decimal('0.00'),
            credit=Decimal('3000.00')
        )

    def test_complete_ledger_flow(self):
        """
        اختبار تدفق كامل لدفتر الأستاذ
        """
        # 1. اختبار ملخص النقدية
        cash_summary = LedgerService.get_account_summary(self.cash)
        self.assertEqual(cash_summary['total_debit'], Decimal('10000.00'))
        self.assertEqual(cash_summary['total_credit'], Decimal('3000.00'))
        self.assertEqual(cash_summary['closing_balance'], Decimal('7000.00'))

        # 2. اختبار ملخص الإيرادات
        revenue_summary = LedgerService.get_account_summary(self.sales_revenue)
        self.assertEqual(revenue_summary['closing_balance'], Decimal('15000.00'))

        # 3. اختبار جميع الحسابات
        all_summaries = LedgerService.get_all_accounts_summary()
        self.assertEqual(len(all_summaries), 5)

        # 4. التحقق من توازن القيود
        total_debits = sum(s['total_debit'] for s in all_summaries)
        total_credits = sum(s['total_credit'] for s in all_summaries)
        self.assertEqual(total_debits, total_credits)
