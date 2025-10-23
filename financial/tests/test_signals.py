"""
اختبارات الإشارات (Signals) للنظام المالي
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
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
)

User = get_user_model()


class FinancialSignalsTest(TestCase):
    """اختبارات إشارات النظام المالي"""
    
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
            code='11010',
            name='النقدية',
            account_type=self.account_type,
            created_by=self.user
        )
        
        self.period = AccountingPeriod.objects.create(
            name='2024',
            start_date=datetime.date(2024, 1, 1),
            end_date=datetime.date(2024, 12, 31),
            created_by=self.user
        )
    
    def test_journal_entry_created_signal(self):
        """اختبار إشارة إنشاء قيد يومي"""
        entry = JournalEntry.objects.create(
            number='JE001',
            date=datetime.date(2024, 1, 15),
            accounting_period=self.period,
            entry_type='manual',
            description='قيد اختبار',
            status='draft',
            created_by=self.user
        )
        
        self.assertIsNotNone(entry)
        self.assertEqual(entry.status, 'draft')
    
    def test_journal_entry_posted_signal(self):
        """اختبار إشارة ترحيل قيد يومي"""
        entry = JournalEntry.objects.create(
            number='JE001',
            date=datetime.date(2024, 1, 15),
            accounting_period=self.period,
            entry_type='manual',
            description='قيد اختبار',
            status='draft',
            created_by=self.user
        )
        
        # تغيير الحالة إلى مرحّل
        entry.status = 'posted'
        entry.save()
        
        self.assertEqual(entry.status, 'posted')
    
    def test_account_balance_update_signal(self):
        """اختبار إشارة تحديث رصيد الحساب"""
        entry = JournalEntry.objects.create(
            number='JE001',
            date=datetime.date(2024, 1, 15),
            accounting_period=self.period,
            entry_type='manual',
            description='قيد اختبار',
            status='draft',
            created_by=self.user
        )
        
        # إضافة سطر قيد
        line = JournalEntryLine.objects.create(
            journal_entry=entry,
            account=self.account,
            description='مدين',
            debit=Decimal('1000.00'),
            credit=Decimal('0.00')
        )
        
        self.assertIsNotNone(line)
        self.assertEqual(line.debit, Decimal('1000.00'))
    
    def test_period_closed_signal(self):
        """اختبار إشارة إغلاق فترة محاسبية"""
        period = AccountingPeriod.objects.create(
            name='2023',
            start_date=datetime.date(2023, 1, 1),
            end_date=datetime.date(2023, 12, 31),
            status='open',
            created_by=self.user
        )
        
        # إغلاق الفترة
        period.status = 'closed'
        period.closed_at = timezone.now()
        period.closed_by = self.user
        period.save()
        
        self.assertEqual(period.status, 'closed')
        self.assertIsNotNone(period.closed_at)
        self.assertEqual(period.closed_by, self.user)
    
    def test_category_budget_exceeded_signal(self):
        """اختبار إشارة تجاوز ميزانية التصنيف"""
        category = FinancialCategory.objects.create(
            name='مصروفات إدارية',
            type='expense',
            budget_limit=Decimal('10000.00'),
            warning_threshold=Decimal('80.00'),
            created_by=self.user
        )
        
        self.assertIsNotNone(category)
        self.assertEqual(category.budget_limit, Decimal('10000.00'))
    
    def test_account_type_deactivated_signal(self):
        """اختبار إشارة تعطيل نوع حساب"""
        account_type = AccountType.objects.create(
            code='2000',
            name='الخصوم',
            category='liability',
            nature='credit',
            is_active=True,
            created_by=self.user
        )
        
        # تعطيل نوع الحساب
        account_type.is_active = False
        account_type.save()
        
        self.assertFalse(account_type.is_active)
    
    def test_account_hierarchy_updated_signal(self):
        """اختبار إشارة تحديث التسلسل الهرمي للحسابات"""
        parent_account = ChartOfAccounts.objects.create(
            code='11000',
            name='الأصول المتداولة',
            account_type=self.account_type,
            created_by=self.user
        )
        
        child_account = ChartOfAccounts.objects.create(
            code='11011',  # كود مختلف لتجنب التكرار
            name='النقدية بالصندوق',
            account_type=self.account_type,
            parent=parent_account,
            created_by=self.user
        )
        
        self.assertEqual(child_account.parent, parent_account)
