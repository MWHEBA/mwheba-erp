# financial/tests/test_income_statement_service.py
import pytest
from decimal import Decimal
from datetime import date
from django.urls import reverse
from django.contrib.auth import get_user_model

from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.journal_entry import JournalEntry, JournalEntryLine
from financial.models.cost_center import CostCenter
from financial.services.income_statement_service import IncomeStatementService

User = get_user_model()


@pytest.mark.django_db
class TestIncomeStatementService:
    """
    مجموعة اختبارات شاملة لخدمة قائمة الدخل المعيارية متعددة المراحل
    """

    @pytest.fixture(autouse=True)
    def setup_test_data(self):
        # 1. أنواع الحسابات
        self.type_asset_cur, _ = AccountType.objects.get_or_create(code="CUR_ASSET", defaults={"name": "أصول متداولة", "category": "asset", "nature": "debit"})
        self.type_rev, _ = AccountType.objects.get_or_create(code="REV", defaults={"name": "إيرادات", "category": "revenue", "nature": "credit"})
        self.type_exp, _ = AccountType.objects.get_or_create(code="EXP", defaults={"name": "مصروفات", "category": "expense", "nature": "debit"})

        # 2. حسابات شجرة الدخل
        self.acc_cash, _ = ChartOfAccounts.objects.get_or_create(code="11101", defaults={"name": "الخزينة", "account_type": self.type_asset_cur, "is_leaf": True, "level": 3})
        
        # إيرادات
        self.acc_sales, _ = ChartOfAccounts.objects.get_or_create(code="41100", defaults={"name": "المبيعات", "account_type": self.type_rev, "is_leaf": True, "level": 3})
        self.acc_sales_returns, _ = ChartOfAccounts.objects.get_or_create(code="41910", defaults={"name": "مردودات المبيعات", "account_type": self.type_rev, "is_leaf": True, "level": 3})
        self.acc_other_rev, _ = ChartOfAccounts.objects.get_or_create(code="42110", defaults={"name": "فوائد بنكية", "account_type": self.type_rev, "is_leaf": True, "level": 3})
        self.acc_fx_gain, _ = ChartOfAccounts.objects.get_or_create(code="43100", defaults={"name": "أرباح فروق العملة", "account_type": self.type_rev, "is_leaf": True, "level": 3})

        # مصروفات
        self.acc_cogs, _ = ChartOfAccounts.objects.get_or_create(code="51100", defaults={"name": "تكلفة البضاعة المباعة", "account_type": self.type_exp, "is_leaf": True, "level": 3})
        self.acc_pur_returns, _ = ChartOfAccounts.objects.get_or_create(code="51910", defaults={"name": "مردودات المشتريات", "account_type": self.type_exp, "is_leaf": True, "level": 3})
        self.acc_salaries, _ = ChartOfAccounts.objects.get_or_create(code="52100", defaults={"name": "الرواتب والأجور", "account_type": self.type_exp, "is_leaf": True, "level": 3})
        self.acc_bank_fees, _ = ChartOfAccounts.objects.get_or_create(code="54100", defaults={"name": "مصاريف بنكية", "account_type": self.type_exp, "is_leaf": True, "level": 3})
        self.acc_fx_loss, _ = ChartOfAccounts.objects.get_or_create(code="54300", defaults={"name": "خسائر فروق العملة", "account_type": self.type_exp, "is_leaf": True, "level": 3})

        # 3. مركز تكلفة
        self.cost_center, _ = CostCenter.objects.get_or_create(code="CC-01", defaults={"name": "فرع القاهرة", "is_active": True})

        # 4. مستخدم
        self.user, _ = User.objects.get_or_create(username="test_accountant", defaults={"email": "acc@mwheba.com"})

    def test_multi_step_calculation_and_contra_accounts(self):
        """اختبار صحة الاحتساب متعدد المراحل والمعالجة الدقيقة للحسابات المقابلة"""
        today = date.today()

        # قيد مبيعات: 100,000 دائن مبيعات
        jv1 = JournalEntry.objects.create(number="JV-INC-001", date=today, status="posted", created_by=self.user)
        JournalEntryLine.objects.create(journal_entry=jv1, account=self.acc_cash, debit=Decimal("100000.00"), credit=Decimal("0.00"))
        JournalEntryLine.objects.create(journal_entry=jv1, account=self.acc_sales, debit=Decimal("0.00"), credit=Decimal("100000.00"))

        # قيد مردودات مبيعات: 5,000 مدين مردودات
        jv2 = JournalEntry.objects.create(number="JV-INC-002", date=today, status="posted", created_by=self.user)
        JournalEntryLine.objects.create(journal_entry=jv2, account=self.acc_sales_returns, debit=Decimal("5000.00"), credit=Decimal("0.00"))
        JournalEntryLine.objects.create(journal_entry=jv2, account=self.acc_cash, debit=Decimal("0.00"), credit=Decimal("5000.00"))

        # قيد تكلفة مبيعات: 40,000 مدين تكلفة بضاعة
        jv3 = JournalEntry.objects.create(number="JV-INC-003", date=today, status="posted", created_by=self.user)
        JournalEntryLine.objects.create(journal_entry=jv3, account=self.acc_cogs, debit=Decimal("40000.00"), credit=Decimal("0.00"))
        JournalEntryLine.objects.create(journal_entry=jv3, account=self.acc_cash, debit=Decimal("0.00"), credit=Decimal("40000.00"))

        # قيد مردودات مشتريات: 2,000 دائن مردودات مشتريات
        jv4 = JournalEntry.objects.create(number="JV-INC-004", date=today, status="posted", created_by=self.user)
        JournalEntryLine.objects.create(journal_entry=jv4, account=self.acc_cash, debit=Decimal("2000.00"), credit=Decimal("0.00"))
        JournalEntryLine.objects.create(journal_entry=jv4, account=self.acc_pur_returns, debit=Decimal("0.00"), credit=Decimal("2000.00"))

        # قيد رواتب: 15,000 مدين رواتب
        jv5 = JournalEntry.objects.create(number="JV-INC-005", date=today, status="posted", created_by=self.user)
        JournalEntryLine.objects.create(journal_entry=jv5, account=self.acc_salaries, debit=Decimal("15000.00"), credit=Decimal("0.00"))
        JournalEntryLine.objects.create(journal_entry=jv5, account=self.acc_cash, debit=Decimal("0.00"), credit=Decimal("15000.00"))

        # قيد فوائد بنكية: 3,000 دائن إيرادات أخرى
        jv6 = JournalEntry.objects.create(number="JV-INC-006", date=today, status="posted", created_by=self.user)
        JournalEntryLine.objects.create(journal_entry=jv6, account=self.acc_cash, debit=Decimal("3000.00"), credit=Decimal("0.00"))
        JournalEntryLine.objects.create(journal_entry=jv6, account=self.acc_other_rev, debit=Decimal("0.00"), credit=Decimal("3000.00"))

        # توليد قائمة الدخل
        inc = IncomeStatementService.generate_income_statement(date_from=today, date_to=today)

        # 1. صافي إيرادات النشاط = 100,000 - 5,000 = 95,000
        assert inc['operating_revenues']['total'] == Decimal("95000.00")

        # 2. صافي تكلفة المبيعات = 40,000 - 2,000 = 38,000
        assert inc['cogs']['total'] == Decimal("38000.00")

        # 3. مجمل الربح = 95,000 - 38,000 = 57,000
        assert inc['gross_profit'] == Decimal("57000.00")
        assert inc['gross_margin'] == Decimal("60.00")  # (57,000 / 95,000) * 100 = 60.00%

        # 4. المصروفات التشغيلية = 15,000
        assert inc['operating_expenses']['total'] == Decimal("15000.00")

        # 5. الربح التشغيلي = 57,000 - 15,000 = 42,000
        assert inc['operating_profit'] == Decimal("42000.00")
        assert inc['operating_margin'] == Decimal("44.21")  # (42,000 / 95,000) * 100 = 44.21%

        # 6. صافي الربح النهائي = 42,000 + 3,000 = 45,000
        assert inc['net_income'] == Decimal("45000.00")
        assert inc['net_margin'] == Decimal("47.37")  # (45,000 / 95,000) * 100 = 47.37%
        assert inc['is_profit'] is True

    def test_closing_entries_are_excluded(self):
        """اختبار عزل قيود الإقفال السنوية لضمان عدم تصفير الأرقام التاريخية"""
        today = date.today()

        # قيد مبيعات
        jv_sales = JournalEntry.objects.create(number="JV-S-01", date=today, status="posted", created_by=self.user)
        JournalEntryLine.objects.create(journal_entry=jv_sales, account=self.acc_cash, debit=Decimal("50000.00"), credit=Decimal("0.00"))
        JournalEntryLine.objects.create(journal_entry=jv_sales, account=self.acc_sales, debit=Decimal("0.00"), credit=Decimal("50000.00"))

        # قيد إقفال سنوي وهمي
        jv_close = JournalEntry.objects.create(number="JV-CLOSE-01", date=today, entry_type="closing", status="posted", created_by=self.user)
        JournalEntryLine.objects.create(journal_entry=jv_close, account=self.acc_sales, debit=Decimal("50000.00"), credit=Decimal("0.00"))
        JournalEntryLine.objects.create(journal_entry=jv_close, account=self.acc_cash, debit=Decimal("0.00"), credit=Decimal("50000.00"))

        inc = IncomeStatementService.generate_income_statement(date_from=today, date_to=today)

        # المبيعات يجب أن تظل 50,000 دون أن تتصفر بقيد الإقفال
        assert inc['operating_revenues']['total'] == Decimal("50000.00")

    def test_guarded_margins_on_zero_revenue(self):
        """اختبار حماية الهوامش من أخطاء القسمة على صفر عند انعدام الإيرادات"""
        today = date.today()
        inc = IncomeStatementService.generate_income_statement(date_from=today, date_to=today)

        assert inc['gross_margin'] == Decimal("0.00")
        assert inc['operating_margin'] == Decimal("0.00")
        assert inc['net_margin'] == Decimal("0.00")

    def test_excel_export_income_statement(self):
        """اختبار تصدير ملف الإكسيل الرسمي لقائمة الدخل"""
        today = date.today()
        excel_bytes = IncomeStatementService.export_to_excel(date_from=today, date_to=today)

        assert excel_bytes is not None
        assert len(excel_bytes) > 1000

    def test_income_statement_view_rendered(self, client):
        """اختبار استجابة صفحة قائمة الدخل للمستخدم المسجل"""
        client.force_login(self.user)
        url = reverse("financial:income_statement")
        response = client.get(url)

        assert response.status_code == 200
        assert "inc" in response.context
        assert "page_title" in response.context
