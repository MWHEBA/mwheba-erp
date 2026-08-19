# financial/tests/test_trial_balance_service.py
import pytest
from decimal import Decimal
from datetime import date
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from financial.models import (
    ChartOfAccounts,
    AccountType,
    JournalEntry,
    JournalEntryLine,
    FiscalYear,
    Currency,
)
from financial.services.trial_balance_service import TrialBalanceService

User = get_user_model()


@pytest.fixture
def setup_tb_test_data(db):
    """إعداد بيئة متكاملة لاختبارات ميزان المراجعة"""
    # 1. مستخدم
    user = User.objects.create_user(username='tb_tester', password='password123')

    # 2. عملة وظيفية
    currency, _ = Currency.objects.get_or_create(
        code='EGP',
        defaults={'name': 'جنيه مصري', 'symbol': 'ج.م', 'is_functional': True, 'is_active': True}
    )

    # 3. سنة مالية
    fy, _ = FiscalYear.objects.get_or_create(
        year_code='FY2026',
        defaults={
            'name': 'السنة المالية 2026',
            'start_date': date(2026, 1, 1),
            'end_date': date(2026, 12, 31),
            'status': 'open'
        }
    )

    # 4. أنواع الحسابات مع كود فريد
    type_asset, _ = AccountType.objects.get_or_create(
        code='ASSET_TYPE',
        defaults={'name': 'أصول متداولة', 'category': 'asset', 'nature': 'debit'}
    )
    type_liability, _ = AccountType.objects.get_or_create(
        code='LIAB_TYPE',
        defaults={'name': 'خصوم متداولة', 'category': 'liability', 'nature': 'credit'}
    )
    type_equity, _ = AccountType.objects.get_or_create(
        code='EQTY_TYPE',
        defaults={'name': 'حقوق ملكية', 'category': 'equity', 'nature': 'credit'}
    )
    type_revenue, _ = AccountType.objects.get_or_create(
        code='REV_TYPE',
        defaults={'name': 'إيرادات النشاط', 'category': 'revenue', 'nature': 'credit'}
    )
    type_expense, _ = AccountType.objects.get_or_create(
        code='EXP_TYPE',
        defaults={'name': 'مصروفات عمومية', 'category': 'expense', 'nature': 'debit'}
    )

    # 5. شجرة الحسابات (أكواد صالحة 4-20 رقم)
    # أصول: أصل رئيسي (1000) -> نقدية (1100) -> خزينة رئيسية (1101)
    acc_assets_root = ChartOfAccounts.objects.create(
        code='1000', name='الأصول', account_type=type_asset, level=1, is_leaf=False
    )
    acc_cash_group = ChartOfAccounts.objects.create(
        code='1100', name='النقدية وما في حكمها', parent=acc_assets_root,
        account_type=type_asset, level=2, is_leaf=False
    )
    acc_cash_safe = ChartOfAccounts.objects.create(
        code='1101', name='الخزينة الرئيسية', parent=acc_cash_group,
        account_type=type_asset, level=3, is_leaf=True
    )

    # خصوم وحقوق ملكية: رأس المال (3101)
    acc_equity_root = ChartOfAccounts.objects.create(
        code='3000', name='حقوق الملكية', account_type=type_equity, level=1, is_leaf=False
    )
    acc_capital = ChartOfAccounts.objects.create(
        code='3101', name='رأس المال المدفوع', parent=acc_equity_root,
        account_type=type_equity, level=2, is_leaf=True
    )

    # إيرادات: مبيعات (4101)
    acc_rev_root = ChartOfAccounts.objects.create(
        code='4000', name='الإيرادات', account_type=type_revenue, level=1, is_leaf=False
    )
    acc_sales = ChartOfAccounts.objects.create(
        code='4101', name='إيراد المبيعات', parent=acc_rev_root,
        account_type=type_revenue, level=2, is_leaf=True
    )

    # مصروفات: إيجار (5101)
    acc_exp_root = ChartOfAccounts.objects.create(
        code='5000', name='المصروفات', account_type=type_expense, level=1, is_leaf=False
    )
    acc_rent = ChartOfAccounts.objects.create(
        code='5101', name='مصروف الإيجار', parent=acc_exp_root,
        account_type=type_expense, level=2, is_leaf=True
    )

    # 6. إنشاء قيود محاسبية مرحلة
    # قيد 1: استثمار رأس المال (بتاريخ 2026-01-01) - 100,000 ج.م
    jv1 = JournalEntry.objects.create(
        number='JV-2026-001',
        date=date(2026, 1, 1),
        status='posted',
        entry_type='manual',
        description='إيداع رأس المال في الخزينة'
    )
    JournalEntryLine.objects.create(journal_entry=jv1, account=acc_cash_safe, debit=Decimal('100000.00'), credit=Decimal('0.00'), currency='EGP')
    JournalEntryLine.objects.create(journal_entry=jv1, account=acc_capital, debit=Decimal('0.00'), credit=Decimal('100000.00'), currency='EGP')

    # قيد 2: إيراد مبيعات نقدي (بتاريخ 2026-02-15) - 25,000 ج.م
    jv2 = JournalEntry.objects.create(
        number='JV-2026-002',
        date=date(2026, 2, 15),
        status='posted',
        entry_type='manual',
        description='مبيعات نقدية'
    )
    JournalEntryLine.objects.create(journal_entry=jv2, account=acc_cash_safe, debit=Decimal('25000.00'), credit=Decimal('0.00'), currency='EGP')
    JournalEntryLine.objects.create(journal_entry=jv2, account=acc_sales, debit=Decimal('0.00'), credit=Decimal('25000.00'), currency='EGP')

    # قيد 3: سداد إيجار نقدي (بتاريخ 2026-03-01) - 5,000 ج.م
    jv3 = JournalEntry.objects.create(
        number='JV-2026-003',
        date=date(2026, 3, 1),
        status='posted',
        entry_type='manual',
        description='سداد إيجار نقداً'
    )
    JournalEntryLine.objects.create(journal_entry=jv3, account=acc_rent, debit=Decimal('5000.00'), credit=Decimal('0.00'), currency='EGP')
    JournalEntryLine.objects.create(journal_entry=jv3, account=acc_cash_safe, debit=Decimal('0.00'), credit=Decimal('5000.00'), currency='EGP')

    return {
        'user': user,
        'fy': fy,
        'acc_cash_safe': acc_cash_safe,
        'acc_capital': acc_capital,
        'acc_sales': acc_sales,
        'acc_rent': acc_rent,
        'acc_assets_root': acc_assets_root,
    }


@pytest.mark.django_db
class TestTrialBalanceService:
    """اختبارات محرك ميزان المراجعة المعياري"""

    def test_full_trial_balance_equilibrium(self, setup_tb_test_data):
        """اختبار التوازن المحاسبي الكامل لميزان الـ 6 أعمدة عن كامل السنة"""
        tb = TrialBalanceService.generate_trial_balance(
            date_from=date(2026, 1, 1),
            date_to=date(2026, 12, 31),
            display_mode='6_columns'
        )

        assert tb['is_balanced'] is True
        assert tb['diff_closing'] == Decimal('0.00')
        assert tb['total_closing_debit'] == tb['total_closing_credit']

        # رصيد الخزينة النهائي: 100,000 + 25,000 - 5,000 = 120,000 مدين
        # رصيد الإيجار: 5,000 مدين
        # إجمالي المدين النهائي = 125,000
        # إجمالي الدائن النهائي: رأس المال (100,000) + المبيعات (25,000) = 125,000
        assert tb['total_closing_debit'] == Decimal('125000.00')
        assert tb['total_closing_credit'] == Decimal('125000.00')

    def test_period_filter_and_opening_balance_calculation(self, setup_tb_test_data):
        """اختبار دقة رصيد أول المدة عند طلب فترة تبدأ من مارس 2026"""
        # طلب الميزان من 2026-03-01 إلى 2026-03-31
        # حركات ما قبل مارس: رأس المال (100,000) + مبيعات فبراير (25,000)
        # الخزينة أول مارس = 125,000 مدين
        # رأس المال أول مارس = 100,000 دائن
        # مبيعات أول مارس = 25,000 دائن
        tb = TrialBalanceService.generate_trial_balance(
            date_from=date(2026, 3, 1),
            date_to=date(2026, 3, 31),
            display_mode='6_columns'
        )

        assert tb['is_balanced'] is True
        assert tb['total_opening_debit'] == Decimal('125000.00')
        assert tb['total_opening_credit'] == Decimal('125000.00')

        # حركة شهر مارس فقط: إيجار 5,000 مدين، خزينة 5,000 دائن
        assert tb['total_period_debit'] == Decimal('5000.00')
        assert tb['total_period_credit'] == Decimal('5000.00')

        # رصيد الإقفال في 31 مارس
        assert tb['total_closing_debit'] == Decimal('125000.00')
        assert tb['total_closing_credit'] == Decimal('125000.00')

    def test_hierarchical_level_filtering(self, setup_tb_test_data):
        """اختبار تصفية المستويات الشجرية ودقة التجميع الصاعد للمستوى 1"""
        tb_level_1 = TrialBalanceService.generate_trial_balance(
            date_from=date(2026, 1, 1),
            date_to=date(2026, 12, 31),
            account_level=1
        )

        assert tb_level_1['is_balanced'] is True
        # المستوى 1 يجب ألا يتجاوز الحسابات الرئيسية
        for acc_row in tb_level_1['accounts']:
            assert acc_row['level'] == 1

        # التأكد من أن مجموع المستوى 1 يطابق إجمالي الميزان
        assert tb_level_1['total_closing_debit'] == Decimal('125000.00')
        assert tb_level_1['total_closing_credit'] == Decimal('125000.00')

    def test_excel_export_generation(self, setup_tb_test_data):
        """اختبار توليد ملف Excel بنجاح وصحة البايتات"""
        excel_bytes = TrialBalanceService.export_to_excel(
            date_from=date(2026, 1, 1),
            date_to=date(2026, 12, 31),
            display_mode='6_columns'
        )

        assert excel_bytes is not None
        assert len(excel_bytes) > 1000
        # التأكد من وجود توقيع صيغة ملف Excel (PK..)
        assert excel_bytes.startswith(b'PK')

    def test_trial_balance_view_response(self, client, setup_tb_test_data):
        """اختبار استجابة صفحة ميزان المراجعة عبر الـ HTTP Client"""
        user = setup_tb_test_data['user']
        client.force_login(user)

        url = reverse('financial:trial_balance_report')
        response = client.get(url)
        assert response.status_code == 200
        assert "ميزان المراجعة" in response.content.decode('utf-8')
        assert "stats-card" in response.content.decode('utf-8')

        # تجربة تحميل Excel من الـ View
        excel_resp = client.get(f"{url}?export=excel")
        assert excel_resp.status_code == 200
        assert excel_resp['Content-Type'] == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
