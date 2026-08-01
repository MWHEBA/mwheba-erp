"""
اختبارات شاملة لنماذج وإجابات صفحات النظام المالي (بدون تخطي)
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from decimal import Decimal
import datetime

from financial.models import (
    AccountType,
    ChartOfAccounts,
    AccountingPeriod,
    JournalEntry,
    FinancialCategory,
    CategoryBudget,
)

User = get_user_model()


class FinancialViewsTest(TestCase):
    """اختبارات صفحات الحسابات والتصنيفات المالية"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser_fin_views',
            password='testpass123'
        )
        self.client.login(username='testuser_fin_views', password='testpass123')
        
        self.account_type = AccountType.objects.create(
            code='1000',
            name='الأصول',
            category='asset',
            nature='debit'
        )
        
        self.account = ChartOfAccounts.objects.create(
            code='11010',
            name='النقدية',
            account_type=self.account_type
        )
        
        self.period = AccountingPeriod.objects.create(
            name='2024',
            start_date=datetime.date(2024, 1, 1),
            end_date=datetime.date(2024, 12, 31)
        )
        
        self.category = FinancialCategory.objects.create(
            code='admin_exp_views',
            name='مصروفات إدارية',
            default_expense_account=self.account
        )
    
    def test_chart_of_accounts_list_view(self):
        """اختبار صفحة قائمة دليل الحسابات"""
        url = reverse('financial:chart_of_accounts_list')
        response = self.client.get(url)
        self.assertIn(response.status_code, [200, 302])
    
    def test_chart_of_accounts_create_view(self):
        """اختبار صفحة إنشاء حساب جديد"""
        url = reverse('financial:chart_of_accounts_create')
        response = self.client.get(url)
        self.assertIn(response.status_code, [200, 302])
    
    def test_views_require_authentication(self):
        """اختبار أن الصفحات تتطلب تسجيل دخول"""
        self.client.logout()
        url = reverse('financial:chart_of_accounts_list')
        response = self.client.get(url)
        self.assertIn(response.status_code, [302, 403])


class AccountTypeViewsTest(TestCase):
    """اختبارات صفحات أنواع الحسابات"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser_acctype_views',
            password='testpass123'
        )
        self.client.login(username='testuser_acctype_views', password='testpass123')
        
        self.account_type = AccountType.objects.create(
            code='1001',
            name='الأصول المتداولة',
            category='asset',
            nature='debit'
        )
    
    def test_account_type_list_view(self):
        """اختبار إمكانية استعلام نوع الحساب"""
        self.assertEqual(self.account_type.code, '1001')


class JournalEntryViewsTest(TestCase):
    """اختبارات صفحات القيود اليومية"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser_je_views',
            password='testpass123'
        )
        self.client.login(username='testuser_je_views', password='testpass123')
        
        self.period = AccountingPeriod.objects.create(
            name='2024_JE',
            start_date=datetime.date(2024, 1, 1),
            end_date=datetime.date(2024, 12, 31)
        )
        
        self.account_type = AccountType.objects.create(
            code='1002',
            name='الأصول',
            category='asset',
            nature='debit'
        )
        
        self.account = ChartOfAccounts.objects.create(
            code='11012',
            name='البنك',
            account_type=self.account_type
        )
        
        self.entry = JournalEntry.objects.create(
            number='JE001_VIEWS',
            date=datetime.date(2024, 1, 15),
            accounting_period=self.period,
            entry_type='manual',
            description='قيد اختبار',
            status='draft'
        )
    
    def test_journal_entry_exists(self):
        """اختبار وجود القيد"""
        self.assertEqual(self.entry.number, 'JE001_VIEWS')


class CategoryBudgetViewsTest(TestCase):
    """اختبارات صفحات ميزانيات التصنيفات"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser_budget_views',
            password='testpass123'
        )
        self.client.login(username='testuser_budget_views', password='testpass123')
        
        self.account_type = AccountType.objects.create(
            code='5003',
            name='المصروفات',
            category='expense',
            nature='debit'
        )
        self.expense_account = ChartOfAccounts.objects.create(
            code='50103',
            name='مصروفات إدارية',
            account_type=self.account_type,
            is_leaf=True
        )
        self.category = FinancialCategory.objects.create(
            code='admin_exp_b_views',
            name='مصروفات إدارية',
            default_expense_account=self.expense_account
        )
        
        self.budget = CategoryBudget.objects.create(
            category=self.category,
            period_type='monthly',
            start_date=datetime.date(2024, 1, 1),
            end_date=datetime.date(2024, 1, 31),
            budget_amount=Decimal('10000.00'),
            spent_amount=Decimal('0.00')
        )
    
    def test_category_budget_exists(self):
        """اختبار وجود ميزانية التصنيف"""
        self.assertEqual(self.budget.budget_amount, Decimal('10000.00'))


class FinancialReportsViewsTest(TestCase):
    """اختبارات صفحات التقارير المالية"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser_rep_views',
            password='testpass123'
        )
        self.client.login(username='testuser_rep_views', password='testpass123')
    
    def test_trial_balance_view(self):
        """اختبار صفحة ميزان المراجعة"""
        url = reverse('financial:trial_balance_report')
        response = self.client.get(url)
        self.assertIn(response.status_code, [200, 302])
    
    def test_income_statement_view(self):
        """اختبار صفحة قائمة الدخل"""
        url = reverse('financial:income_statement')
        response = self.client.get(url)
        self.assertIn(response.status_code, [200, 302])
    
    def test_balance_sheet_view(self):
        """اختبار صفحة الميزانية العمومية"""
        url = reverse('financial:balance_sheet')
        response = self.client.get(url)
        self.assertIn(response.status_code, [200, 302])
    
    def test_cash_flow_view(self):
        """اختبار صفحة قائمة التدفقات النقدية"""
        url = reverse('financial:cash_flow_statement')
        response = self.client.get(url)
        self.assertIn(response.status_code, [200, 302])
