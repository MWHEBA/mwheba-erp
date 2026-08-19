# financial/tests/test_balance_sheet_service.py
import pytest
from decimal import Decimal
from datetime import date
from django.urls import reverse
from django.contrib.auth import get_user_model

from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.journal_entry import JournalEntry, JournalEntryLine
from financial.services.balance_sheet_service import BalanceSheetService

User = get_user_model()


@pytest.mark.django_db
class TestBalanceSheetService:
    """
    مجموعة اختبارات شاملة لخدمة الميزانية العمومية المعيارية
    """

    @pytest.fixture(autouse=True)
    def setup_accounts(self):
        # 1. إنشاء أنواع الحسابات
        self.type_asset_cur, _ = AccountType.objects.get_or_create(code="CUR_ASSET", defaults={"name": "أصول متداولة", "category": "asset", "nature": "debit"})
        self.type_asset_fix, _ = AccountType.objects.get_or_create(code="FIX_ASSET", defaults={"name": "أصول ثابتة", "category": "asset", "nature": "debit"})
        self.type_liab_cur, _ = AccountType.objects.get_or_create(code="CUR_LIAB", defaults={"name": "خصوم متداولة", "category": "liability", "nature": "credit"})
        self.type_equity, _ = AccountType.objects.get_or_create(code="EQUITY", defaults={"name": "حقوق الملكية", "category": "equity", "nature": "credit"})
        self.type_rev, _ = AccountType.objects.get_or_create(code="REV", defaults={"name": "إيرادات", "category": "revenue", "nature": "credit"})
        self.type_exp, _ = AccountType.objects.get_or_create(code="EXP", defaults={"name": "مصروفات", "category": "expense", "nature": "debit"})

        # 2. إنشاء شجرة حسابات تجريبية
        self.acc_cash, _ = ChartOfAccounts.objects.get_or_create(code="11101", defaults={"name": "الخزينة التجريبية", "account_type": self.type_asset_cur, "is_leaf": True, "level": 3})
        self.acc_cust, _ = ChartOfAccounts.objects.get_or_create(code="11201", defaults={"name": "عميل تجريبي", "account_type": self.type_asset_cur, "is_leaf": True, "level": 3})
        self.acc_fixed, _ = ChartOfAccounts.objects.get_or_create(code="12101", defaults={"name": "أصول ومعدات", "account_type": self.type_asset_fix, "is_leaf": True, "level": 3})
        self.acc_supp, _ = ChartOfAccounts.objects.get_or_create(code="21101", defaults={"name": "مورد تجريبي", "account_type": self.type_liab_cur, "is_leaf": True, "level": 3})
        self.acc_cap, _ = ChartOfAccounts.objects.get_or_create(code="31110", defaults={"name": "رأس المال", "account_type": self.type_equity, "is_leaf": True, "level": 3})
        self.acc_retained, _ = ChartOfAccounts.objects.get_or_create(code="31410", defaults={"name": "الأرباح المرحلة", "account_type": self.type_equity, "is_leaf": True, "level": 3})
        self.acc_sales, _ = ChartOfAccounts.objects.get_or_create(code="41100", defaults={"name": "المبيعات", "account_type": self.type_rev, "is_leaf": True, "level": 3})
        self.acc_cogs, _ = ChartOfAccounts.objects.get_or_create(code="51100", defaults={"name": "تكلفة البضاعة", "account_type": self.type_exp, "is_leaf": True, "level": 3})

        # 3. إنشاء مستخدم
        self.user, _ = User.objects.get_or_create(username="test_cfo", defaults={"email": "cfo@mwheba.com"})

    def test_balance_sheet_generation_and_equation(self):
        """اختبار صحة توليد الميزانية والتطابق التام للمعادلة المحاسبية"""
        # قيد رأسمال: من حـ/ الخزينة إلى حـ/ رأس المال بمبلغ 100,000
        jv1 = JournalEntry.objects.create(number="JV-BS-001", date=date.today(), status="posted", created_by=self.user)
        JournalEntryLine.objects.create(journal_entry=jv1, account=self.acc_cash, debit=Decimal("100000.00"), credit=Decimal("0.00"))
        JournalEntryLine.objects.create(journal_entry=jv1, account=self.acc_cap, debit=Decimal("0.00"), credit=Decimal("100000.00"))

        # قيد مشتريات: من حـ/ تكلفة البضاعة إلى حـ/ المورد بمبلغ 20,000
        jv2 = JournalEntry.objects.create(number="JV-BS-002", date=date.today(), status="posted", created_by=self.user)
        JournalEntryLine.objects.create(journal_entry=jv2, account=self.acc_cogs, debit=Decimal("20000.00"), credit=Decimal("0.00"))
        JournalEntryLine.objects.create(journal_entry=jv2, account=self.acc_supp, debit=Decimal("0.00"), credit=Decimal("20000.00"))

        # قيد مبيعات: من حـ/ العميل إلى حـ/ المبيعات بمبلغ 35,000
        jv3 = JournalEntry.objects.create(number="JV-BS-003", date=date.today(), status="posted", created_by=self.user)
        JournalEntryLine.objects.create(journal_entry=jv3, account=self.acc_cust, debit=Decimal("35000.00"), credit=Decimal("0.00"))
        JournalEntryLine.objects.create(journal_entry=jv3, account=self.acc_sales, debit=Decimal("0.00"), credit=Decimal("35000.00"))

        # توليد الميزانية
        bs = BalanceSheetService.generate_balance_sheet(as_of_date=date.today())

        assert bs['is_balanced'] is True
        assert abs(bs['difference']) <= Decimal("0.05")
        assert bs['total_assets'] == bs['total_liabilities_equity']
        assert bs['total_assets'] == Decimal("135000.00")  # 100,000 cash + 35,000 customer
        assert bs['total_liabilities'] == Decimal("20000.00")  # 20,000 supplier
        assert bs['equity']['current_net_income'] == Decimal("15000.00")  # 35,000 sales - 20,000 cogs
        assert bs['total_equity'] == Decimal("115000.00")  # 100,000 cap + 15,000 net income

    def test_guarded_financial_ratios(self):
        """اختبار احتساب النسب المالية بأمان"""
        bs = BalanceSheetService.generate_balance_sheet(as_of_date=date.today())
        ratios = bs['financial_ratios']

        assert 'working_capital' in ratios
        assert ratios['working_capital'] is not None

    def test_excel_export(self):
        """اختبار تصدير ملف الإكسيل الرسمي"""
        excel_bytes = BalanceSheetService.export_to_excel(as_of_date=date.today())
        assert excel_bytes is not None
        assert len(excel_bytes) > 1000

    def test_balance_sheet_view_rendered(self, client):
        """اختبار استجابة صفحة الميزانية العمومية للمستخدم المسجل"""
        client.force_login(self.user)
        url = reverse("financial:balance_sheet")
        response = client.get(url)

        assert response.status_code == 200
        assert "bs" in response.context
        assert "page_title" in response.context
