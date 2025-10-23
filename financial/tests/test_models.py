from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone
from decimal import Decimal
import datetime

# استيراد النماذج
from financial.models import (
    AccountType, ChartOfAccounts, AccountGroup,
    JournalEntry, JournalEntryLine, AccountingPeriod,
    FinancialCategory, CategoryBudget,
    PartnerTransaction, PartnerBalance,
    BalanceSnapshot, AccountBalanceCache
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
        """اختبار إنشاء نوع حساب جديد"""
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
        self.assertTrue(account_type.is_active)
        self.assertEqual(account_type.level, 1)
    
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
            level=2,
            created_by=self.user
        )
        
        self.assertEqual(child.parent, parent)
        self.assertEqual(child.level, 2)
        self.assertIn(child, parent.children.all())
    
    def test_unique_code_constraint(self):
        """اختبار قيد الفرادة على كود النوع"""
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
        """اختبار إنشاء حساب في دليل الحسابات"""
        account = ChartOfAccounts.objects.create(
            code='1001',
            name='الصندوق',
            account_type=self.account_type,
            opening_balance=Decimal('5000.00'),
            created_by=self.user
        )
        
        self.assertEqual(account.code, '1001')
        self.assertEqual(account.name, 'الصندوق')
        self.assertEqual(account.account_type, self.account_type)
        self.assertEqual(account.opening_balance, Decimal('5000.00'))
        self.assertTrue(account.is_active)
    
    def test_account_balance_calculation(self):
        """اختبار حساب رصيد الحساب"""
        account = ChartOfAccounts.objects.create(
            code='1001',
            name='الصندوق',
            account_type=self.account_type,
            opening_balance=Decimal('5000.00'),
            created_by=self.user
        )
        
        # الرصيد الحالي يجب أن يساوي الرصيد الافتتاحي في البداية
        self.assertEqual(account.current_balance, Decimal('5000.00'))


class JournalEntryModelTest(TestCase):
    """اختبارات نموذج القيود المحاسبية"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        # إنشاء فترة محاسبية
        self.period = AccountingPeriod.objects.create(
            name='2024',
            start_date=datetime.date(2024, 1, 1),
            end_date=datetime.date(2024, 12, 31),
            is_active=True,
            created_by=self.user
        )
        
        # إنشاء أنواع حسابات
        self.asset_type = AccountType.objects.create(
            code='1000',
            name='الأصول',
            category='asset',
            nature='debit',
            created_by=self.user
        )
        
        self.revenue_type = AccountType.objects.create(
            code='4000',
            name='الإيرادات',
            category='revenue',
            nature='credit',
            created_by=self.user
        )
        
        # إنشاء حسابات
        self.cash_account = ChartOfAccounts.objects.create(
            code='1001',
            name='الصندوق',
            account_type=self.asset_type,
            created_by=self.user
        )
        
        self.sales_account = ChartOfAccounts.objects.create(
            code='4001',
            name='مبيعات',
            account_type=self.revenue_type,
            created_by=self.user
        )
    
    def test_create_journal_entry(self):
        """اختبار إنشاء قيد محاسبي"""
        entry = JournalEntry.objects.create(
            reference='JE001',
            description='قيد مبيعات نقدية',
            entry_date=timezone.now().date(),
            period=self.period,
            created_by=self.user
        )
        
        self.assertEqual(entry.reference, 'JE001')
        self.assertEqual(entry.description, 'قيد مبيعات نقدية')
        self.assertEqual(entry.status, 'draft')
        self.assertFalse(entry.is_posted)
    
    def test_journal_entry_lines(self):
        """اختبار بنود القيد المحاسبي"""
        entry = JournalEntry.objects.create(
            reference='JE001',
            description='قيد مبيعات نقدية',
            entry_date=timezone.now().date(),
            period=self.period,
            created_by=self.user
        )
        
        # بند مدين (الصندوق)
        debit_line = JournalEntryLine.objects.create(
            journal_entry=entry,
            account=self.cash_account,
            description='نقدية من المبيعات',
            debit_amount=Decimal('1000.00'),
            credit_amount=Decimal('0.00')
        )
        
        # بند دائن (المبيعات)
        credit_line = JournalEntryLine.objects.create(
            journal_entry=entry,
            account=self.sales_account,
            description='مبيعات نقدية',
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('1000.00')
        )
        
        self.assertEqual(entry.lines.count(), 2)
        self.assertEqual(debit_line.debit_amount, Decimal('1000.00'))
        self.assertEqual(credit_line.credit_amount, Decimal('1000.00'))


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
            name='مصروفات تشغيلية',
            code='EXP001',
            category_type='expense',
            created_by=self.user
        )
        
        self.assertEqual(category.name, 'مصروفات تشغيلية')
        self.assertEqual(category.code, 'EXP001')
        self.assertEqual(category.category_type, 'expense')
        self.assertTrue(category.is_active)
    
    def test_category_hierarchy(self):
        """اختبار التسلسل الهرمي للتصنيفات"""
        parent = FinancialCategory.objects.create(
            name='المصروفات',
            code='EXP',
            category_type='expense',
            created_by=self.user
        )
        
        child = FinancialCategory.objects.create(
            name='مصروفات إدارية',
            code='EXP001',
            category_type='expense',
            parent=parent,
            created_by=self.user
        )
        
        self.assertEqual(child.parent, parent)
        self.assertIn(child, parent.children.all())


class PartnerTransactionModelTest(TestCase):
    """اختبارات نموذج معاملات الشريك"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        self.partner = User.objects.create_user(
            username='partner',
            password='partnerpass123'
        )
    
    def test_create_partner_transaction(self):
        """اختبار إنشاء معاملة شريك"""
        transaction = PartnerTransaction.objects.create(
            partner=self.partner,
            transaction_type='contribution',
            amount=Decimal('10000.00'),
            description='مساهمة رأس مال',
            created_by=self.user
        )
        
        self.assertEqual(transaction.partner, self.partner)
        self.assertEqual(transaction.transaction_type, 'contribution')
        self.assertEqual(transaction.amount, Decimal('10000.00'))
        self.assertEqual(transaction.status, 'pending')
    
    def test_partner_balance_update(self):
        """اختبار تحديث رصيد الشريك"""
        # إنشاء رصيد شريك
        balance = PartnerBalance.objects.create(
            partner=self.partner,
            balance=Decimal('0.00')
        )
        
        # إنشاء معاملة مساهمة
        transaction = PartnerTransaction.objects.create(
            partner=self.partner,
            transaction_type='contribution',
            amount=Decimal('5000.00'),
            description='مساهمة',
            status='approved',
            created_by=self.user
        )
        
        # تحديث الرصيد يدوياً (في التطبيق الحقيقي يتم عبر signals)
        balance.balance += transaction.amount
        balance.save()
        
        balance.refresh_from_db()
        self.assertEqual(balance.balance, Decimal('5000.00'))


class BalanceSnapshotModelTest(TestCase):
    """اختبارات نموذج لقطات الأرصدة"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        self.account_type = AccountType.objects.create(
            code='1000',
            name='الأصول',
            category='asset',
            nature='debit',
            created_by=self.user
        )
        
        self.account = ChartOfAccounts.objects.create(
            code='1001',
            name='الصندوق',
            account_type=self.account_type,
            opening_balance=Decimal('1000.00'),
            created_by=self.user
        )
    
    def test_create_balance_snapshot(self):
        """اختبار إنشاء لقطة رصيد"""
        snapshot = BalanceSnapshot.objects.create(
            account=self.account,
            snapshot_date=timezone.now().date(),
            opening_balance=Decimal('1000.00'),
            closing_balance=Decimal('1500.00'),
            total_debits=Decimal('500.00'),
            total_credits=Decimal('0.00'),
            created_by=self.user
        )
        
        self.assertEqual(snapshot.account, self.account)
        self.assertEqual(snapshot.opening_balance, Decimal('1000.00'))
        self.assertEqual(snapshot.closing_balance, Decimal('1500.00'))
        self.assertEqual(snapshot.net_change, Decimal('500.00'))


class AccountBalanceCacheModelTest(TestCase):
    """اختبارات نموذج ذاكرة التخزين المؤقت للأرصدة"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        self.account_type = AccountType.objects.create(
            code='1000',
            name='الأصول',
            category='asset',
            nature='debit',
            created_by=self.user
        )
        
        self.account = ChartOfAccounts.objects.create(
            code='1001',
            name='الصندوق',
            account_type=self.account_type,
            opening_balance=Decimal('1000.00'),
            created_by=self.user
        )
    
    def test_create_balance_cache(self):
        """اختبار إنشاء ذاكرة تخزين مؤقت للرصيد"""
        cache = AccountBalanceCache.objects.create(
            account=self.account,
            current_balance=Decimal('1500.00'),
            last_transaction_date=timezone.now().date(),
            last_updated=timezone.now()
        )
        
        self.assertEqual(cache.account, self.account)
        self.assertEqual(cache.current_balance, Decimal('1500.00'))
        self.assertTrue(cache.is_valid)
    
    def test_cache_invalidation(self):
        """اختبار إبطال ذاكرة التخزين المؤقت"""
        cache = AccountBalanceCache.objects.create(
            account=self.account,
            current_balance=Decimal('1500.00'),
            last_transaction_date=timezone.now().date(),
            last_updated=timezone.now(),
            is_valid=False
        )
        
        self.assertFalse(cache.is_valid)
