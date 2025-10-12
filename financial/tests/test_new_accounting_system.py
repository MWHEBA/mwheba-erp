"""
اختبارات النظام المحاسبي الجديد
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import date, timedelta

from ..models.chart_of_accounts import AccountType, ChartOfAccounts
from ..models.journal_entry import AccountingPeriod, JournalEntry, JournalEntryLine
from ..services.journal_service import JournalEntryService, AutoJournalService
from ..services.balance_service import BalanceService

User = get_user_model()


class AccountTypeTestCase(TestCase):
    """اختبارات أنواع الحسابات"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
    
    def test_create_account_type(self):
        """اختبار إنشاء نوع حساب"""
        account_type = AccountType.objects.create(
            code='1000',
            name='الأصول',
            category='asset',
            nature='debit',
            created_by=self.user
        )
        
        self.assertEqual(account_type.code, '1000')
        self.assertEqual(account_type.name, 'الأصول')
        self.assertEqual(account_type.category, 'asset')
        self.assertEqual(account_type.nature, 'debit')
        self.assertEqual(account_type.level, 1)
        self.assertTrue(account_type.is_active)
    
    def test_account_type_hierarchy(self):
        """اختبار التسلسل الهرمي لأنواع الحسابات"""
        parent_type = AccountType.objects.create(
            code='1000',
            name='الأصول',
            category='asset',
            nature='debit',
            created_by=self.user
        )
        
        child_type = AccountType.objects.create(
            code='1100',
            name='الأصول المتداولة',
            category='asset',
            nature='debit',
            parent=parent_type,
            created_by=self.user
        )
        
        self.assertEqual(child_type.level, 2)
        self.assertEqual(child_type.parent, parent_type)
        self.assertIn(child_type, parent_type.children.all())


class ChartOfAccountsTestCase(TestCase):
    """اختبارات دليل الحسابات"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        self.asset_type = AccountType.objects.create(
            code='1000',
            name='الأصول',
            category='asset',
            nature='debit',
            created_by=self.user
        )
        
        self.liability_type = AccountType.objects.create(
            code='2000',
            name='الخصوم',
            category='liability',
            nature='credit',
            created_by=self.user
        )
    
    def test_create_account(self):
        """اختبار إنشاء حساب"""
        account = ChartOfAccounts.objects.create(
            code='1001',
            name='الخزينة',
            account_type=self.asset_type,
            is_cash_account=True,
            created_by=self.user
        )
        
        self.assertEqual(account.code, '1001')
        self.assertEqual(account.name, 'الخزينة')
        self.assertEqual(account.account_type, self.asset_type)
        self.assertTrue(account.is_cash_account)
        self.assertTrue(account.is_leaf)
        self.assertTrue(account.can_post_entries())
    
    def test_account_hierarchy(self):
        """اختبار التسلسل الهرمي للحسابات"""
        parent_account = ChartOfAccounts.objects.create(
            code='1000',
            name='الأصول المتداولة',
            account_type=self.asset_type,
            created_by=self.user
        )
        
        child_account = ChartOfAccounts.objects.create(
            code='1001',
            name='الخزينة',
            account_type=self.asset_type,
            parent=parent_account,
            created_by=self.user
        )
        
        self.assertEqual(child_account.level, 2)
        self.assertEqual(child_account.parent, parent_account)
        self.assertFalse(parent_account.is_leaf)  # الأب لم يعد حساباً نهائياً
    
    def test_account_properties(self):
        """اختبار خصائص الحساب"""
        account = ChartOfAccounts.objects.create(
            code='1001',
            name='الخزينة',
            account_type=self.asset_type,
            created_by=self.user
        )
        
        self.assertEqual(account.nature, 'debit')
        self.assertEqual(account.category, 'asset')
        self.assertEqual(account.full_code, '1001')
        self.assertEqual(account.full_name, 'الخزينة')


class AccountingPeriodTestCase(TestCase):
    """اختبارات الفترات المحاسبية"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
    
    def test_create_period(self):
        """اختبار إنشاء فترة محاسبية"""
        period = AccountingPeriod.objects.create(
            name='2024',
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            created_by=self.user
        )
        
        self.assertEqual(period.name, '2024')
        self.assertEqual(period.status, 'open')
        self.assertTrue(period.can_post_entries())
    
    def test_period_validation(self):
        """اختبار التحقق من صحة الفترة"""
        with self.assertRaises(ValidationError):
            period = AccountingPeriod(
                name='Invalid Period',
                start_date=date(2024, 12, 31),
                end_date=date(2024, 1, 1),  # تاريخ النهاية قبل البداية
                created_by=self.user
            )
            period.full_clean()
    
    def test_get_period_for_date(self):
        """اختبار الحصول على الفترة لتاريخ معين"""
        period = AccountingPeriod.objects.create(
            name='2024',
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            created_by=self.user
        )
        
        found_period = AccountingPeriod.get_period_for_date(date(2024, 6, 15))
        self.assertEqual(found_period, period)
        
        not_found = AccountingPeriod.get_period_for_date(date(2025, 1, 1))
        self.assertIsNone(not_found)


class JournalEntryTestCase(TestCase):
    """اختبارات القيود اليومية"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # إنشاء أنواع الحسابات
        self.asset_type = AccountType.objects.create(
            code='1000',
            name='الأصول',
            category='asset',
            nature='debit',
            created_by=self.user
        )
        
        self.equity_type = AccountType.objects.create(
            code='3000',
            name='حقوق الملكية',
            category='equity',
            nature='credit',
            created_by=self.user
        )
        
        # إنشاء الحسابات
        self.cash_account = ChartOfAccounts.objects.create(
            code='1001',
            name='الخزينة',
            account_type=self.asset_type,
            is_cash_account=True,
            created_by=self.user
        )
        
        self.capital_account = ChartOfAccounts.objects.create(
            code='3001',
            name='رأس المال',
            account_type=self.equity_type,
            created_by=self.user
        )
        
        # إنشاء فترة محاسبية
        self.period = AccountingPeriod.objects.create(
            name='2024',
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            created_by=self.user
        )
    
    def test_create_journal_entry(self):
        """اختبار إنشاء قيد يومي"""
        entry = JournalEntry.objects.create(
            date=date.today(),
            description='قيد افتتاحي',
            accounting_period=self.period,
            created_by=self.user
        )
        
        self.assertIsNotNone(entry.number)
        self.assertEqual(entry.status, 'draft')
        self.assertEqual(entry.entry_type, 'manual')
    
    def test_journal_entry_with_lines(self):
        """اختبار قيد مع بنود"""
        entry = JournalEntry.objects.create(
            date=date.today(),
            description='قيد افتتاحي',
            accounting_period=self.period,
            created_by=self.user
        )
        
        # إضافة بنود القيد
        JournalEntryLine.objects.create(
            journal_entry=entry,
            account=self.cash_account,
            debit=Decimal('1000'),
            credit=Decimal('0'),
            description='نقدية'
        )
        
        JournalEntryLine.objects.create(
            journal_entry=entry,
            account=self.capital_account,
            debit=Decimal('0'),
            credit=Decimal('1000'),
            description='رأس المال'
        )
        
        self.assertEqual(entry.total_debit, Decimal('1000'))
        self.assertEqual(entry.total_credit, Decimal('1000'))
        self.assertTrue(entry.is_balanced)
        self.assertEqual(entry.difference, Decimal('0'))
    
    def test_post_journal_entry(self):
        """اختبار ترحيل قيد"""
        entry = JournalEntry.objects.create(
            date=date.today(),
            description='قيد افتتاحي',
            accounting_period=self.period,
            created_by=self.user
        )
        
        # إضافة بنود متوازنة
        JournalEntryLine.objects.create(
            journal_entry=entry,
            account=self.cash_account,
            debit=Decimal('1000'),
            credit=Decimal('0')
        )
        
        JournalEntryLine.objects.create(
            journal_entry=entry,
            account=self.capital_account,
            debit=Decimal('0'),
            credit=Decimal('1000')
        )
        
        # ترحيل القيد
        entry.post(self.user)
        
        self.assertEqual(entry.status, 'posted')
        self.assertIsNotNone(entry.posted_at)
        self.assertEqual(entry.posted_by, self.user)
    
    def test_unbalanced_entry_validation(self):
        """اختبار التحقق من القيود غير المتوازنة"""
        entry = JournalEntry.objects.create(
            date=date.today(),
            description='قيد غير متوازن',
            accounting_period=self.period,
            created_by=self.user
        )
        
        # إضافة بنود غير متوازنة
        JournalEntryLine.objects.create(
            journal_entry=entry,
            account=self.cash_account,
            debit=Decimal('1000'),
            credit=Decimal('0')
        )
        
        JournalEntryLine.objects.create(
            journal_entry=entry,
            account=self.capital_account,
            debit=Decimal('0'),
            credit=Decimal('500')  # مبلغ مختلف
        )
        
        with self.assertRaises(ValidationError):
            entry.validate_entry()


class JournalEntryServiceTestCase(TestCase):
    """اختبارات خدمة القيود المحاسبية"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # إنشاء أنواع الحسابات والحسابات
        asset_type = AccountType.objects.create(
            code='1000',
            name='الأصول',
            category='asset',
            nature='debit',
            created_by=self.user
        )
        
        equity_type = AccountType.objects.create(
            code='3000',
            name='حقوق الملكية',
            category='equity',
            nature='credit',
            created_by=self.user
        )
        
        self.cash_account = ChartOfAccounts.objects.create(
            code='1001',
            name='الخزينة',
            account_type=asset_type,
            created_by=self.user
        )
        
        self.capital_account = ChartOfAccounts.objects.create(
            code='3001',
            name='رأس المال',
            account_type=equity_type,
            created_by=self.user
        )
        
        # إنشاء فترة محاسبية
        AccountingPeriod.objects.create(
            name='2024',
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            created_by=self.user
        )
    
    def test_create_simple_entry(self):
        """اختبار إنشاء قيد بسيط"""
        entry = JournalEntryService.create_simple_entry(
            debit_account='1001',
            credit_account='3001',
            amount=Decimal('1000'),
            description='قيد افتتاحي',
            date=date(2024, 6, 15),  # تاريخ ضمن الفترة المحاسبية
            user=self.user
        )
        
        self.assertEqual(entry.status, 'posted')
        self.assertEqual(entry.total_debit, Decimal('1000'))
        self.assertEqual(entry.total_credit, Decimal('1000'))
        self.assertTrue(entry.is_balanced)
    
    def test_create_entry_with_lines_data(self):
        """اختبار إنشاء قيد مع بيانات البنود"""
        lines_data = [
            {
                'account_code': '1001',
                'debit': 1000,
                'credit': 0,
                'description': 'نقدية'
            },
            {
                'account_code': '3001',
                'debit': 0,
                'credit': 1000,
                'description': 'رأس المال'
            }
        ]
        
        entry = JournalEntryService.create_entry(
            description='قيد افتتاحي',
            date=date(2024, 6, 15),  # تاريخ ضمن الفترة المحاسبية
            lines_data=lines_data,
            user=self.user,
            auto_post=True
        )
        
        self.assertEqual(entry.lines.count(), 2)
        self.assertEqual(entry.status, 'posted')


class BalanceServiceTestCase(TestCase):
    """اختبارات خدمة الأرصدة"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # إنشاء الحسابات والفترة
        asset_type = AccountType.objects.create(
            code='1000',
            name='الأصول',
            category='asset',
            nature='debit',
            created_by=self.user
        )
        
        self.cash_account = ChartOfAccounts.objects.create(
            code='1001',
            name='الخزينة',
            account_type=asset_type,
            created_by=self.user
        )
        
        period = AccountingPeriod.objects.create(
            name='2024',
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            created_by=self.user
        )
        
        # إنشاء قيد وترحيله
        entry = JournalEntry.objects.create(
            date=date.today(),
            description='قيد اختبار',
            accounting_period=period,
            status='posted',
            created_by=self.user
        )
        
        JournalEntryLine.objects.create(
            journal_entry=entry,
            account=self.cash_account,
            debit=Decimal('1000'),
            credit=Decimal('0')
        )
    
    def test_get_account_balance(self):
        """اختبار حساب رصيد الحساب"""
        balance = BalanceService.get_account_balance(self.cash_account)
        self.assertEqual(balance, Decimal('1000'))
        
        # اختبار بالكود
        balance_by_code = BalanceService.get_account_balance('1001')
        self.assertEqual(balance_by_code, Decimal('1000'))
    
    def test_trial_balance(self):
        """اختبار ميزان المراجعة"""
        trial_balance = BalanceService.get_trial_balance()
        
        # يجب أن يحتوي على حساب واحد على الأقل
        self.assertGreater(len(trial_balance), 0)
        
        # التحقق من الإجماليات
        totals = trial_balance[-1]
        self.assertEqual(totals['account_name'], 'الإجمالي')


if __name__ == '__main__':
    import django
    django.setup()
    
    from django.test.utils import get_runner
    from django.conf import settings
    
    TestRunner = get_runner(settings)
    test_runner = TestRunner()
    failures = test_runner.run_tests(["financial.tests.test_new_accounting_system"])
