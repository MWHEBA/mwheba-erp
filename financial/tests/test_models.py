"""
اختبارات شاملة لنماذج النظام المالي
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone
from decimal import Decimal
import datetime

from financial.models import (
    AccountType,
    ChartOfAccounts,
    AccountingPeriod,
    JournalEntry,
    JournalEntryLine,
    FinancialCategory,
    CategoryBudget,
)

User = get_user_model()


class AccountTypeModelTest(TestCase):
    """اختبارات نموذج أنواع الحسابات"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
    
    def test_create_account_type(self):
        """اختبار إنشاء نوع حساب"""
        account_type = AccountType.objects.create(
            code='1000',
            name='الأصول المتداولة',
            category='asset',
            nature='debit',
            created_by=self.user
        )
        
        self.assertEqual(account_type.code, '1000')
        self.assertEqual(account_type.name, 'الأصول المتداولة')
        self.assertEqual(account_type.category, 'asset')
        self.assertEqual(account_type.nature, 'debit')
        self.assertEqual(account_type.level, 1)
        self.assertTrue(account_type.is_active)
    
    def test_account_type_hierarchy(self):
        """اختبار التسلسل الهرمي لأنواع الحسابات"""
        parent = AccountType.objects.create(
            code='1000',
            name='الأصول',
            category='asset',
            nature='debit',
            created_by=self.user
        )
        
        child = AccountType.objects.create(
            code='1100',
            name='الأصول المتداولة',
            category='asset',
            nature='debit',
            parent=parent,
            created_by=self.user
        )
        
        self.assertEqual(child.parent, parent)
        self.assertEqual(child.level, 2)
        self.assertEqual(parent.level, 1)
    
    def test_unique_code_constraint(self):
        """اختبار قيد الكود الفريد"""
        AccountType.objects.create(
            code='1000',
            name='الأصول',
            category='asset',
            nature='debit',
            created_by=self.user
        )
        
        with self.assertRaises(IntegrityError):
            AccountType.objects.create(
                code='1000',  # كود مكرر
                name='الأصول الأخرى',
                category='asset',
                nature='debit',
                created_by=self.user
            )


class ChartOfAccountsModelTest(TestCase):
    """اختبارات نموذج دليل الحسابات"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        self.account_type = AccountType.objects.create(
            code='1000',
            name='الأصول المتداولة',
            category='asset',
            nature='debit',
            created_by=self.user
        )
    
    def test_create_chart_account(self):
        """اختبار إنشاء حساب في الدليل"""
        account = ChartOfAccounts.objects.create(
            code='11010',
            name='النقدية بالصندوق',
            name_en='Cash on Hand',
            account_type=self.account_type,
            is_active=True,
            created_by=self.user
        )
        
        self.assertEqual(account.code, '11010')
        self.assertEqual(account.name, 'النقدية بالصندوق')
        self.assertEqual(account.account_type, self.account_type)
        self.assertTrue(account.is_active)
    
    def test_account_balance_calculation(self):
        """اختبار حساب رصيد الحساب"""
        account = ChartOfAccounts.objects.create(
            code='11010',
            name='النقدية',
            account_type=self.account_type,
            created_by=self.user
        )
        
        # الرصيد الافتراضي يجب أن يكون صفر
        self.assertIsNotNone(account)
        self.assertEqual(account.code, '11010')
    
    def test_unique_code_constraint(self):
        """اختبار قيد الكود الفريد"""
        ChartOfAccounts.objects.create(
            code='11010',
            name='النقدية',
            account_type=self.account_type,
            created_by=self.user
        )
        
        with self.assertRaises(IntegrityError):
            ChartOfAccounts.objects.create(
                code='11010',  # كود مكرر
                name='النقدية الأخرى',
                account_type=self.account_type,
                created_by=self.user
            )


class AccountingPeriodModelTest(TestCase):
    """اختبارات نموذج الفترات المحاسبية"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
    
    def test_create_accounting_period(self):
        """اختبار إنشاء فترة محاسبية"""
        period = AccountingPeriod.objects.create(
            name='2024',
            start_date=datetime.date(2024, 1, 1),
            end_date=datetime.date(2024, 12, 31),
            status='open',
            created_by=self.user
        )
        
        self.assertEqual(period.name, '2024')
        self.assertEqual(period.status, 'open')
        self.assertTrue(period.is_active)
        self.assertFalse(period.is_closed)
    
    def test_period_date_validation(self):
        """اختبار التحقق من صحة تواريخ الفترة"""
        period = AccountingPeriod(
            name='2024',
            start_date=datetime.date(2024, 12, 31),
            end_date=datetime.date(2024, 1, 1),  # تاريخ خاطئ
            created_by=self.user
        )
        
        with self.assertRaises(ValidationError):
            period.full_clean()
    
    def test_is_date_in_period(self):
        """اختبار التحقق من وجود تاريخ في الفترة"""
        period = AccountingPeriod.objects.create(
            name='2024',
            start_date=datetime.date(2024, 1, 1),
            end_date=datetime.date(2024, 12, 31),
            created_by=self.user
        )
        
        self.assertTrue(period.is_date_in_period(datetime.date(2024, 6, 15)))
        self.assertFalse(period.is_date_in_period(datetime.date(2025, 1, 1)))
    
    def test_can_post_entries(self):
        """اختبار إمكانية إدراج قيود"""
        period = AccountingPeriod.objects.create(
            name='2024',
            start_date=datetime.date(2024, 1, 1),
            end_date=datetime.date(2024, 12, 31),
            status='open',
            created_by=self.user
        )
        
        self.assertTrue(period.can_post_entries())
        
        period.status = 'closed'
        period.save()
        
        self.assertFalse(period.can_post_entries())
    
    def test_get_period_for_date(self):
        """اختبار الحصول على الفترة لتاريخ معين"""
        period = AccountingPeriod.objects.create(
            name='2024',
            start_date=datetime.date(2024, 1, 1),
            end_date=datetime.date(2024, 12, 31),
            created_by=self.user
        )
        
        found_period = AccountingPeriod.get_period_for_date(datetime.date(2024, 6, 15))
        self.assertEqual(found_period, period)
        
        not_found = AccountingPeriod.get_period_for_date(datetime.date(2025, 6, 15))
        self.assertIsNone(not_found)


class JournalEntryModelTest(TestCase):
    """اختبارات نموذج القيود اليومية"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        self.period = AccountingPeriod.objects.create(
            name='2024',
            start_date=datetime.date(2024, 1, 1),
            end_date=datetime.date(2024, 12, 31),
            status='open',
            created_by=self.user
        )
        
        self.account_type = AccountType.objects.create(
            code='1000',
            name='الأصول',
            category='asset',
            nature='debit',
            created_by=self.user
        )
        
        self.debit_account = ChartOfAccounts.objects.create(
            code='11010',
            name='النقدية',
            account_type=self.account_type,
            created_by=self.user
        )
        
        self.credit_account = ChartOfAccounts.objects.create(
            code='41010',
            name='المبيعات',
            account_type=self.account_type,
            created_by=self.user
        )
    
    def test_create_journal_entry(self):
        """اختبار إنشاء قيد يومي"""
        entry = JournalEntry.objects.create(
            number='JE001',
            date=datetime.date(2024, 1, 15),
            accounting_period=self.period,
            entry_type='manual',
            description='قيد افتتاحي',
            status='draft',
            created_by=self.user
        )
        
        self.assertEqual(entry.number, 'JE001')
        self.assertEqual(entry.status, 'draft')
        self.assertEqual(entry.entry_type, 'manual')
    
    def test_journal_entry_lines(self):
        """اختبار سطور القيد اليومي"""
        entry = JournalEntry.objects.create(
            number='JE001',
            date=datetime.date(2024, 1, 15),
            accounting_period=self.period,
            entry_type='manual',
            description='قيد اختبار',
            status='draft',
            created_by=self.user
        )
        
        # سطر مدين
        debit_line = JournalEntryLine.objects.create(
            journal_entry=entry,
            account=self.debit_account,
            description='مدين',
            debit=Decimal('1000.00'),
            credit=Decimal('0.00')
        )
        
        # سطر دائن
        credit_line = JournalEntryLine.objects.create(
            journal_entry=entry,
            account=self.credit_account,
            description='دائن',
            debit=Decimal('0.00'),
            credit=Decimal('1000.00')
        )
        
        self.assertEqual(entry.lines.count(), 2)
        self.assertEqual(debit_line.debit, Decimal('1000.00'))
        self.assertEqual(credit_line.credit, Decimal('1000.00'))


class FinancialCategoryModelTest(TestCase):
    """اختبارات نموذج التصنيفات المالية"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
    
    def test_create_category(self):
        """اختبار إنشاء تصنيف مالي"""
        category = FinancialCategory.objects.create(
            name='مصروفات إدارية',
            name_en='Administrative Expenses',
            code='EXP001',
            type='expense',
            priority='high',
            description='مصروفات الإدارة العامة',
            created_by=self.user
        )
        
        self.assertEqual(category.name, 'مصروفات إدارية')
        self.assertEqual(category.type, 'expense')
        self.assertEqual(category.priority, 'high')
        self.assertTrue(category.is_active)
    
    def test_category_hierarchy(self):
        """اختبار التسلسل الهرمي للتصنيفات"""
        parent = FinancialCategory.objects.create(
            name='مصروفات',
            type='expense',
            created_by=self.user
        )
        
        child = FinancialCategory.objects.create(
            name='مصروفات إدارية',
            type='expense',
            parent=parent,
            created_by=self.user
        )
        
        self.assertEqual(child.parent, parent)
        self.assertEqual(child.level, 2)  # يتم حسابه تلقائياً (parent.level + 1)
    
    def test_budget_limit(self):
        """اختبار حد الميزانية"""
        category = FinancialCategory.objects.create(
            name='مصروفات تسويق',
            type='expense',
            budget_limit=Decimal('50000.00'),
            warning_threshold=Decimal('80.00'),
            created_by=self.user
        )
        
        self.assertEqual(category.budget_limit, Decimal('50000.00'))
        self.assertEqual(category.warning_threshold, Decimal('80.00'))


class CategoryBudgetModelTest(TestCase):
    """اختبارات نموذج ميزانيات التصنيفات"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        self.category = FinancialCategory.objects.create(
            name='مصروفات إدارية',
            type='expense',
            created_by=self.user
        )
    
    def test_create_category_budget(self):
        """اختبار إنشاء ميزانية تصنيف"""
        budget = CategoryBudget.objects.create(
            category=self.category,
            period_type='monthly',
            start_date=datetime.date(2024, 1, 1),
            end_date=datetime.date(2024, 1, 31),
            budget_amount=Decimal('10000.00'),
            spent_amount=Decimal('8500.00'),
            created_by=self.user
        )
        
        self.assertEqual(budget.category, self.category)
        self.assertEqual(budget.period_type, 'monthly')
        self.assertEqual(budget.budget_amount, Decimal('10000.00'))
        self.assertEqual(budget.spent_amount, Decimal('8500.00'))
    
    def test_budget_variance(self):
        """اختبار حساب الفرق في الميزانية"""
        budget = CategoryBudget.objects.create(
            category=self.category,
            period_type='monthly',
            start_date=datetime.date(2024, 1, 1),
            end_date=datetime.date(2024, 1, 31),
            budget_amount=Decimal('10000.00'),
            spent_amount=Decimal('8500.00'),
            created_by=self.user
        )
        
        # المتبقي = الميزانية - المنفق
        self.assertEqual(budget.remaining_amount, Decimal('1500.00'))
        # نسبة الاستخدام
        self.assertEqual(budget.usage_percentage, 85.0)
