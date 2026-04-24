"""
اختبارات خدمة تحليل الربحية حسب التصنيفات
"""
import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone

from financial.models import (
    FinancialCategory,
    ChartOfAccounts,
    AccountType,
    AccountingPeriod,
    JournalEntry,
    JournalEntryLine,
)
from financial.services.category_profitability_service import CategoryProfitabilityService

User = get_user_model()


@pytest.mark.django_db
class TestCategoryProfitabilityService:
    """اختبارات خدمة تحليل الربحية"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """إعداد البيانات للاختبارات"""
        # إنشاء مستخدم
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        # إنشاء أنواع الحسابات
        self.revenue_type = AccountType.objects.create(
            code='4000',
            name='الإيرادات',
            category='revenue',
            nature='credit',
            created_by=self.user
        )
        
        self.expense_type = AccountType.objects.create(
            code='5000',
            name='المصروفات',
            category='expense',
            nature='debit',
            created_by=self.user
        )
        
        # إنشاء حسابات محاسبية
        self.revenue_account = ChartOfAccounts.objects.create(
            code='40100',
            name='إيرادات الرسوم',
            account_type=self.revenue_type,
            is_leaf=True,
            created_by=self.user
        )
        
        self.expense_account = ChartOfAccounts.objects.create(
            code='50100',
            name='مصروفات المنهجيات',
            account_type=self.expense_type,
            is_leaf=True,
            created_by=self.user
        )
        
        # إنشاء تصنيف مالي
        self.category = FinancialCategory.objects.create(
            code='sales',
            name='مبيعات',
            default_revenue_account=self.revenue_account,
            default_expense_account=self.expense_account
        )
        
        # إنشاء فترة محاسبية
        today = timezone.now().date()
        self.period = AccountingPeriod.objects.create(
            name='فترة اختبار',
            start_date=today.replace(day=1),
            end_date=today,
            status='open',
            created_by=self.user
        )
        
        # إنشاء قيد محاسبي (draft أولاً)
        self.entry = JournalEntry.objects.create(
            number='JE-TEST-001',
            date=today,
            description='قيد اختبار',
            accounting_period=self.period,
            financial_category=self.category,
            status='draft',  # draft أولاً
            created_by=self.user
        )
        self.entry._gateway_approved = True
        
        # إضافة بنود القيد المتوازنة
        # إيراد 10000 (دائن) + حساب نقدي 10000 (مدين)
        # مصروف 6000 (مدين) + حساب نقدي 6000 (دائن)
        
        # إنشاء حساب نقدي
        cash_type = AccountType.objects.create(
            code='1000',
            name='الأصول',
            category='asset',
            nature='debit',
            created_by=self.user
        )
        cash_account = ChartOfAccounts.objects.create(
            code='10100',
            name='الصندوق',
            account_type=cash_type,
            is_leaf=True,
            created_by=self.user
        )
        
        # بند الإيراد: مدين صندوق 10000
        JournalEntryLine.objects.create(
            journal_entry=self.entry,
            account=cash_account,
            debit=Decimal('10000.00'),
            credit=Decimal('0.00'),
            description='تحصيل إيراد'
        )
        
        # بند الإيراد: دائن إيرادات 10000
        JournalEntryLine.objects.create(
            journal_entry=self.entry,
            account=self.revenue_account,
            credit=Decimal('10000.00'),
            debit=Decimal('0.00'),
            description='إيراد'
        )
        
        # بند المصروف: مدين مصروفات 6000
        JournalEntryLine.objects.create(
            journal_entry=self.entry,
            account=self.expense_account,
            debit=Decimal('6000.00'),
            credit=Decimal('0.00'),
            description='مصروف'
        )
        
        # بند المصروف: دائن صندوق 6000
        JournalEntryLine.objects.create(
            journal_entry=self.entry,
            account=cash_account,
            credit=Decimal('6000.00'),
            debit=Decimal('0.00'),
            description='دفع مصروف'
        )
        
        # ترحيل القيد
        self.entry.post(user=self.user)
    
    def test_get_category_report(self):
        """اختبار الحصول على تقرير تصنيف واحد"""
        report = CategoryProfitabilityService.get_category_report('sales')
        
        assert report['success'] is True
        assert report['category']['code'] == 'sales'
        assert report['summary']['revenues'] == Decimal('10000.00')
        assert report['summary']['expenses'] == Decimal('6000.00')
        assert report['summary']['profit'] == Decimal('4000.00')
        assert report['summary']['margin'] == Decimal('40.00')
    
    def test_get_category_report_invalid_code(self):
        """اختبار تقرير لتصنيف غير موجود"""
        report = CategoryProfitabilityService.get_category_report('invalid')
        
        assert report['success'] is False
        assert 'error' in report
    
    def test_get_all_summary(self):
        """اختبار ملخص جميع التصنيفات"""
        summary = CategoryProfitabilityService.get_all_summary()
        
        assert summary['success'] is True
        assert len(summary['categories']) == 1
        assert summary['totals']['revenues'] == Decimal('10000.00')
        assert summary['totals']['expenses'] == Decimal('6000.00')
        assert summary['totals']['profit'] == Decimal('4000.00')
    
    def test_get_top_profitable_categories(self):
        """اختبار أفضل التصنيفات ربحاً"""
        top = CategoryProfitabilityService.get_top_profitable_categories(limit=3)
        
        assert len(top) == 1
        assert top[0]['code'] == 'sales'
        assert top[0]['profit'] == Decimal('4000.00')
    
    def test_get_loss_making_categories(self):
        """اختبار التصنيفات الخاسرة"""
        # إنشاء تصنيف خاسر
        loss_category = FinancialCategory.objects.create(
            code='loss_test',
            name='تصنيف خاسر',
            default_revenue_account=self.revenue_account,
            default_expense_account=self.expense_account
        )
        
        # إنشاء حساب نقدي للقيد الخاسر
        cash_type_loss = AccountType.objects.get_or_create(
            code='1000',
            defaults={
                'name': 'الأصول',
                'category': 'asset',
                'nature': 'debit',
                'created_by': self.user
            }
        )[0]
        
        cash_account_loss = ChartOfAccounts.objects.get_or_create(
            code='10100',
            defaults={
                'name': 'الصندوق',
                'account_type': cash_type_loss,
                'is_leaf': True,
                'created_by': self.user
            }
        )[0]
        
        # إنشاء قيد خاسر (draft أولاً)
        loss_entry = JournalEntry.objects.create(
            number='JE-LOSS-001',
            date=timezone.now().date(),
            description='قيد خسارة',
            accounting_period=self.period,
            financial_category=loss_category,
            status='draft',
            created_by=self.user
        )
        loss_entry._gateway_approved = True
        
        # بنود القيد المتوازنة: إيراد 1000، مصروف 5000
        # إيراد: مدين صندوق 1000
        JournalEntryLine.objects.create(
            journal_entry=loss_entry,
            account=cash_account_loss,
            debit=Decimal('1000.00'),
            credit=Decimal('0.00'),
            description='تحصيل إيراد قليل'
        )
        
        # إيراد: دائن إيرادات 1000
        JournalEntryLine.objects.create(
            journal_entry=loss_entry,
            account=self.revenue_account,
            credit=Decimal('1000.00'),
            debit=Decimal('0.00'),
            description='إيراد قليل'
        )
        
        # مصروف: مدين مصروفات 5000
        JournalEntryLine.objects.create(
            journal_entry=loss_entry,
            account=self.expense_account,
            debit=Decimal('5000.00'),
            credit=Decimal('0.00'),
            description='مصروف كبير'
        )
        
        # مصروف: دائن صندوق 5000
        JournalEntryLine.objects.create(
            journal_entry=loss_entry,
            account=cash_account_loss,
            credit=Decimal('5000.00'),
            debit=Decimal('0.00'),
            description='دفع مصروف كبير'
        )
        
        # ترحيل القيد
        loss_entry.post(user=self.user)
        
        # اختبار
        losses = CategoryProfitabilityService.get_loss_making_categories()
        
        assert len(losses) == 1
        assert losses[0]['code'] == 'loss_test'
        assert losses[0]['profit'] < 0
