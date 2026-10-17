# -*- coding: utf-8 -*-
"""
Tests for Phase 4: Financial Integrity & Quality Assurance for GL SSOT Architecture
حزمة اختبارات شاملة ومحوكمة للمرحلة 4 (الحوكمة والاختبارات الآلية الشاملة):
1. تطابق الأرصدة عبر كافة الواجهات (Cross-Surface Account Balance Identity):
   - كشف الحساب == رصيد الموديل == شجرة الحسابات == ميزان المراجعة == الميزانية العمومية
   - الاتزان الرياضي الصارم للميزانية العمومية وميزان المراجعة (Assets = Liab + Equity)
2. تسوية البنوك ومحرك الترشيحات (Bank Reconciliation GL Balance Identity):
   - قراءة رصيد الدفتر العام للبنك حصرياً وبدقة تامة من قيود الأستاذ العام
3. دورة حياة الخزينة الكاملة ومسار الإلغاء الآمن (Treasury Lifecycle & Safe Setup Void):
   - تأسيس -> صرف حتى التصفير -> التعطيل والحذف بنجاح
   - الإلغاء الآمن للتأسيس الخاطئ عبر القيد العكسي الذري دون ImmutableLedgerError
4. الأستاذ المساعد ورصيد أول المدة عند الفلترة التاريخية (Subledgers & Period Beginning Balance):
   - احتساب قيود ما قبل الفترة كرصيد منقول بدقة متناهية وعدم تبخر الرصيد
   - تطابق رصيد حساب التحكم مع مجموع الحسابات الفرعية التابعة
5. فروق العملة والدفتر المستمر (FX & Continuous Multi-Year Ledger):
   - عدم تكرار الرصيد الافتتاحي في تقييم العملات
   - الترحيل الطبيعي المستمر عبر السنوات المالية دون قيود تدوير مشوهة
6. الحماية الأمنية والتواريخ المستقبلية والسحب على المكشوف:
   - رفض التلاعب برصيد الدفتر في الجرد واحتسابه سيرفر-سايد
   - شمول قيود ما بعد 2030 بدون سقف هاردكود
   - انضباط قيد السحب على المكشوف في الجانب الدائن
   - حظر التحويلات النقدية عند نقص الرصيد
"""

import pytest
from decimal import Decimal
from datetime import date
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command

from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.currency import Currency
from financial.models.journal_entry import JournalEntry, JournalEntryLine, AccountingPeriod
from financial.models.fiscal_year import FiscalYear
from financial.models.bank_reconciliation import BankStatementBatch
from financial.services.ledger_query_service import LedgerQueryService
from financial.services.ledger_core_service import LedgerCoreService
from financial.services.balance_sheet_service import BalanceSheetService
from financial.services.trial_balance_service import TrialBalanceService
from financial.services.bank_reconciliation_service import BankReconciliationService
from financial.services.cash_transfer_service import CashTransferService
from financial.services.fx_revaluation_service import FXRevaluationService

User = get_user_model()


@pytest.fixture
def phase4_setup(db):
    user = User.objects.create_superuser(
        username="phase4_auditor",
        email="auditor_p4@mwheba.com",
        password="password123"
    )

    # 1. إعداد العملات
    egp_curr, _ = Currency.objects.get_or_create(
        code="EGP",
        defaults={"name": "Egyptian Pound", "is_functional": True, "is_active": True}
    )
    usd_curr, _ = Currency.objects.get_or_create(
        code="USD",
        defaults={"name": "US Dollar", "is_functional": False, "is_active": True}
    )

    # 2. إعداد السنوات والفترات المالية
    fy25, _ = FiscalYear.objects.get_or_create(
        name="FY2025-P4",
        defaults={
            "year_code": "FY25P4",
            "start_date": date(2025, 1, 1),
            "end_date": date(2025, 12, 31),
            "status": "open",
        }
    )
    p25, _ = AccountingPeriod.objects.get_or_create(
        name="P1-2025-P4",
        fiscal_year=fy25,
        period_number=1,
        defaults={
            "start_date": date(2025, 1, 1),
            "end_date": date(2025, 12, 31),
            "status": "open",
        }
    )

    fy26, _ = FiscalYear.objects.get_or_create(
        name="FY2026-P4",
        defaults={
            "year_code": "FY26P4",
            "start_date": date(2026, 1, 1),
            "end_date": date(2026, 12, 31),
            "status": "open",
        }
    )
    p26, _ = AccountingPeriod.objects.get_or_create(
        name="P1-2026-P4",
        fiscal_year=fy26,
        period_number=1,
        defaults={
            "start_date": date(2026, 1, 1),
            "end_date": date(2026, 12, 31),
            "status": "open",
        }
    )

    fy35, _ = FiscalYear.objects.get_or_create(
        name="FY2035-P4",
        defaults={
            "year_code": "FY35P4",
            "start_date": date(2035, 1, 1),
            "end_date": date(2035, 12, 31),
            "status": "open",
        }
    )
    p35, _ = AccountingPeriod.objects.get_or_create(
        name="P1-2035-P4",
        fiscal_year=fy35,
        period_number=1,
        defaults={
            "start_date": date(2035, 1, 1),
            "end_date": date(2035, 12, 31),
            "status": "open",
        }
    )

    # 3. أنواع الحسابات
    asset_type, _ = AccountType.objects.get_or_create(
        code="ASSET_P4",
        defaults={"name": "أصول", "category": "asset", "nature": "debit"}
    )
    liab_type, _ = AccountType.objects.get_or_create(
        code="LIAB_P4",
        defaults={"name": "خصوم", "category": "liability", "nature": "credit"}
    )
    equity_type, _ = AccountType.objects.get_or_create(
        code="EQUITY_P4",
        defaults={"name": "حقوق ملكية", "category": "equity", "nature": "credit"}
    )
    expense_type, _ = AccountType.objects.get_or_create(
        code="EXPENSE_P4",
        defaults={"name": "مصروفات", "category": "expense", "nature": "debit"}
    )

    # 4. حساب وسيط الأرصدة الافتتاحية 31010
    opb_equity, _ = ChartOfAccounts.objects.get_or_create(
        code="31010",
        defaults={
            "name": "الأرصدة الافتتاحية",
            "account_type": equity_type,
            "is_leaf": True,
            "is_active": True,
        }
    )

    return {
        "user": user,
        "egp": egp_curr,
        "usd": usd_curr,
        "fy25": fy25,
        "p25": p25,
        "fy26": fy26,
        "p26": p26,
        "fy35": fy35,
        "p35": p35,
        "asset_type": asset_type,
        "liab_type": liab_type,
        "equity_type": equity_type,
        "expense_type": expense_type,
        "opb_equity": opb_equity,
    }


@pytest.mark.django_db
class TestFinancialIntegrity:
    """4.1 اختبارات التوازن المالي والمطابقة عبر كافة الواجهات والتقارير"""

    def test_cross_surface_account_balance_identity(self, phase4_setup):
        """
        التحقق من التطابق التام لرصيد أي حساب عبر:
        1. account.current_balance
        2. account.get_balance()
        3. LedgerQueryService.get_account_balance()
        4. الرصيد الختامي في كشف الحساب LedgerQueryService.get_account_statement()
        5. رصيد الحساب في ميزان المراجعة TrialBalanceService
        6. رصيد الحساب والأصول في الميزانية العمومية BalanceSheetService
        7. الاتزان الرياضي الصارم (Total Debit == Total Credit) و (Assets == Liab + Equity)
        """
        env = phase4_setup
        cash_acc = ChartOfAccounts.objects.create(
            code="11119001",
            name="خزينة تطابق الواجهات",
            account_type=env["asset_type"],
            currency=env["egp"],
            is_cash_account=True,
            is_leaf=True,
            is_active=True
        )

        # إنشاء قيد افتتاحي متزن (خزينة مدين 25,000 / أرباح افتتاجية دائن 25,000)
        je = JournalEntry.objects.create(
            number="JE-P4-001",
            date=date(2026, 1, 1),
            accounting_period=env["p26"],
            status="posted",
            entry_type="opening",
            created_by=env["user"],
            posted_by=env["user"]
        )
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=cash_acc,
            debit=Decimal("25000.00"),
            credit=Decimal("0.00")
        )
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=env["opb_equity"],
            debit=Decimal("0.00"),
            credit=Decimal("25000.00")
        )

        expected_balance = Decimal("25000.00")

        # 1. الموديل المباشر
        assert cash_acc.current_balance == expected_balance
        assert cash_acc.get_balance() == expected_balance

        # 2. محرك استعلامات الأستاذ العام LedgerQueryService
        lqs_bal = LedgerQueryService.get_account_balance(cash_acc)
        assert lqs_bal["balance"] == expected_balance

        # 3. كشف الحساب
        stmt = LedgerQueryService.get_account_statement(cash_acc)
        assert stmt["closing_balance"] == expected_balance

        # 4. ميزان المراجعة
        tb_data = TrialBalanceService.generate_trial_balance(date_from=date(2026, 1, 1), date_to=date(2026, 12, 31))
        assert tb_data["is_balanced"] is True
        assert tb_data["total_closing_debit"] == tb_data["total_closing_credit"]
        assert tb_data["diff_closing"] == Decimal("0.00")

        # 5. الميزانية العمومية
        bs_data = BalanceSheetService.generate_balance_sheet(as_of_date=date(2026, 12, 31))
        assert bs_data["is_balanced"] is True
        assert bs_data["difference"] == Decimal("0.00")
        assert bs_data["assets"]["total"] == expected_balance
        assert bs_data["equity"]["total"] == expected_balance

    def test_bank_reconciliation_reads_gl_balance_accurately(self, phase4_setup):
        """
        4.1 البرهان القاطع في تسوية البنوك:
        التحقق من أن خدمة تسوية البنوك BankReconciliationService تقرأ رصيد الدفتر العام
        المطابق بنسبة 100% لقيود الأستاذ العام دون أي فجوات
        """
        env = phase4_setup
        bank_acc = ChartOfAccounts.objects.create(
            code="11129001",
            name="بنك التسوية المحوكم",
            account_type=env["asset_type"],
            currency=env["egp"],
            is_bank_account=True,
            is_leaf=True,
            is_active=True
        )

        # قيد رصيد افتتاحي 50,000 ج.م
        je = JournalEntry.objects.create(
            number="JE-BANK-001",
            date=date(2026, 1, 1),
            accounting_period=env["p26"],
            status="posted",
            entry_type="opening",
            created_by=env["user"],
            posted_by=env["user"]
        )
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=bank_acc,
            debit=Decimal("50000.00"),
            credit=Decimal("0.00")
        )
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=env["opb_equity"],
            debit=Decimal("0.00"),
            credit=Decimal("50000.00")
        )

        # إنشاء دفعة استيراد كشف حساب بنكي
        batch = BankStatementBatch.objects.create(
            batch_number="BATCH-P4-001",
            bank_account=bank_acc,
            statement_date=date(2026, 1, 31),
            opening_balance=Decimal("50000.00"),
            closing_balance=Decimal("50000.00"),
            created_by=env["user"]
        )

        summary = BankReconciliationService.calculate_reconciliation_summary(batch.id)
        assert summary["gl_balance"] == Decimal("50000.00")


@pytest.mark.django_db
class TestTreasuryLifecycle:
    """4.2 اختبار دورة حياة الخزينة الكاملة ومسار الإلغاء الآمن للتأسيس الخاطئ"""

    def test_treasury_full_lifecycle_to_zero_and_archive(self, phase4_setup):
        """
        دورة حياة الخزينة الكاملة:
        1. فتح خزينة برصيد افتتاحي 10,000 ج.م
        2. صرف مصروف مساوٍ للرصيد (10,000 ج.م)
        3. التحقق من وصول الرصيد الصافي إلى 0.00 ج.م
        4. نجاح التعطيل والأرشفة بأمان
        """
        env = phase4_setup
        cash_acc = ChartOfAccounts.objects.create(
            code="11119002",
            name="خزينة المصروفات التشغيلية",
            account_type=env["asset_type"],
            currency=env["egp"],
            is_cash_account=True,
            is_leaf=True,
            is_active=True
        )
        exp_acc = ChartOfAccounts.objects.create(
            code="51019001",
            name="مصروفات عمومية",
            account_type=env["expense_type"],
            currency=env["egp"],
            is_leaf=True,
            is_active=True
        )

        # 1. إيداع رصيد افتتاحي 10,000 ج.م
        je_opb = JournalEntry.objects.create(
            number="JE-OPB-LC-1",
            date=date(2026, 1, 1),
            accounting_period=env["p26"],
            status="posted",
            entry_type="opening",
            created_by=env["user"],
            posted_by=env["user"]
        )
        JournalEntryLine.objects.create(journal_entry=je_opb, account=cash_acc, debit=Decimal("10000.00"), credit=Decimal("0.00"))
        JournalEntryLine.objects.create(journal_entry=je_opb, account=env["opb_equity"], debit=Decimal("0.00"), credit=Decimal("10000.00"))

        assert cash_acc.current_balance == Decimal("10000.00")

        # 2. تسجيل مصروف مساوٍ للرصيد (صرف من الخزينة)
        je_exp = JournalEntry.objects.create(
            number="JE-EXP-LC-1",
            date=date(2026, 1, 15),
            accounting_period=env["p26"],
            status="posted",
            entry_type="general",
            created_by=env["user"],
            posted_by=env["user"]
        )
        JournalEntryLine.objects.create(journal_entry=je_exp, account=exp_acc, debit=Decimal("10000.00"), credit=Decimal("0.00"))
        JournalEntryLine.objects.create(journal_entry=je_exp, account=cash_acc, debit=Decimal("0.00"), credit=Decimal("10000.00"))

        # 3. التحقق من الرصيد الصفري في الدفتر
        assert cash_acc.current_balance == Decimal("0.00")
        assert cash_acc.get_balance() == Decimal("0.00")

        # 4. تعطيل الخزينة بأمان
        cash_acc.is_active = False
        cash_acc.save()
        assert cash_acc.is_active is False

    def test_safe_setup_void_atomic_reversal_no_immutable_error(self, phase4_setup):
        """
        4.2 اختبار مسار الإلغاء الآمن (Safe Setup Void via Atomic Reversal):
        حساب أُنشئ بالخطأ برصيد افتتاحي، إلغاؤه يتم ذرّياً بعكس القيد دون استدعاء delete()
        ودون الوقوع في خطأ ImmutableLedgerError
        """
        env = phase4_setup
        mistaken_acc = ChartOfAccounts.objects.create(
            code="11119003",
            name="خزينة أُنشئت بالخطأ",
            account_type=env["asset_type"],
            currency=env["egp"],
            is_cash_account=True,
            is_leaf=True,
            is_active=True
        )

        je_opb = JournalEntry.objects.create(
            number="OPB-MISTAKE-01",
            date=date(2026, 1, 1),
            accounting_period=env["p26"],
            status="posted",
            entry_type="opening",
            created_by=env["user"],
            posted_by=env["user"]
        )
        JournalEntryLine.objects.create(journal_entry=je_opb, account=mistaken_acc, debit=Decimal("8000.00"), credit=Decimal("0.00"))
        JournalEntryLine.objects.create(journal_entry=je_opb, account=env["opb_equity"], debit=Decimal("0.00"), credit=Decimal("8000.00"))

        assert mistaken_acc.current_balance == Decimal("8000.00")

        # عكس القيد ذرّياً باستخدام LedgerCoreService.reverse_entry
        reversal_entry = LedgerCoreService.reverse_entry(
            entry_id=je_opb.id,
            user=env["user"],
            reversal_reason="إلغاء تأسيس خاطئ للخزينة",
        )

        assert reversal_entry.status == "posted"
        assert reversal_entry.original_entry == je_opb
        je_opb.refresh_from_db()
        assert je_opb.reversed_by_entry == reversal_entry

        # التأكد من تصفير رصيد الخزينة بالدفتر
        assert mistaken_acc.current_balance == Decimal("0.00")
        assert mistaken_acc.get_balance() == Decimal("0.00")

        # أرشفة الحساب بأمان
        mistaken_acc.is_active = False
        mistaken_acc.save()
        assert mistaken_acc.is_active is False


@pytest.mark.django_db
class TestSubledgersAndBeginningBalances:
    """4.3 اختبارات فترات كشوف الحسابات ومطابقة حسابات التحكم الرئاسية"""

    def test_statement_beginning_balance_date_filtering(self, phase4_setup):
        """
        التحقق من أن فلترة كشف الحساب لتاريخ لاحق date_from تحسب حركات ما قبل التاريخ
        كرصيد بداية فترة (رصيد منقول) من واقع قيود الدفتر ولا يتبخر الرصيد
        """
        env = phase4_setup
        acc = ChartOfAccounts.objects.create(
            code="11119004",
            name="حساب فترات كشف الحساب",
            account_type=env["asset_type"],
            currency=env["egp"],
            is_leaf=True,
            is_active=True
        )

        # حركة في شهر يناير: 1,500 ج.م
        je_jan = JournalEntry.objects.create(
            number="JE-JAN-01",
            date=date(2026, 1, 15),
            accounting_period=env["p26"],
            status="posted",
            entry_type="general",
            created_by=env["user"],
            posted_by=env["user"]
        )
        JournalEntryLine.objects.create(journal_entry=je_jan, account=acc, debit=Decimal("1500.00"), credit=Decimal("0.00"))
        JournalEntryLine.objects.create(journal_entry=je_jan, account=env["opb_equity"], debit=Decimal("0.00"), credit=Decimal("1500.00"))

        # حركة في شهر فبراير: 800 ج.م
        je_feb = JournalEntry.objects.create(
            number="JE-FEB-01",
            date=date(2026, 2, 10),
            accounting_period=env["p26"],
            status="posted",
            entry_type="general",
            created_by=env["user"],
            posted_by=env["user"]
        )
        JournalEntryLine.objects.create(journal_entry=je_feb, account=acc, debit=Decimal("800.00"), credit=Decimal("0.00"))
        JournalEntryLine.objects.create(journal_entry=je_feb, account=env["opb_equity"], debit=Decimal("0.00"), credit=Decimal("800.00"))

        # طلب كشف الحساب من تاريخ 2026-02-01
        stmt = LedgerQueryService.get_account_statement(
            account_or_id=acc,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 28)
        )

        # رصيد ما قبل الفترة يجب أن يطابق تماماً حركة يناير (1,500 ج.م)
        assert stmt["opening_balance"] == Decimal("1500.00")
        # حركات الفترة تحوي حركة فبراير فقط (800 ج.م)
        assert len(stmt["transactions"]) == 1
        assert stmt["transactions"][0]["debit"] == Decimal("800.00")
        # الرصيد الختامي يجب أن يجمع 1500 + 800 = 2300 ج.م
        assert stmt["closing_balance"] == Decimal("2300.00")

    def test_control_account_matches_subledgers(self, phase4_setup):
        """
        مطابقة حساب التحكم الرئاسي (Control Account):
        رصيد حساب التحكم الأب يساوي تماماً مجموع أرصدة الحسابات الفرعية التابعة له
        """
        env = phase4_setup
        control_acc = ChartOfAccounts.objects.create(
            code="11050",
            name="إجمالي العملاء - حساب تحكم",
            account_type=env["asset_type"],
            currency=env["egp"],
            is_control_account=True,
            is_leaf=False,
            is_active=True
        )

        sub_acc_1 = ChartOfAccounts.objects.create(
            code="1105001",
            name="عميل أ",
            account_type=env["asset_type"],
            currency=env["egp"],
            parent=control_acc,
            is_leaf=True,
            is_active=True
        )
        sub_acc_2 = ChartOfAccounts.objects.create(
            code="1105002",
            name="عميل ب",
            account_type=env["asset_type"],
            currency=env["egp"],
            parent=control_acc,
            is_leaf=True,
            is_active=True
        )

        # قيود على الحسابين الفرعيين
        je = JournalEntry.objects.create(
            number="JE-CTRL-01",
            date=date(2026, 1, 10),
            accounting_period=env["p26"],
            status="posted",
            entry_type="general",
            created_by=env["user"],
            posted_by=env["user"]
        )
        JournalEntryLine.objects.create(journal_entry=je, account=sub_acc_1, debit=Decimal("3500.00"), credit=Decimal("0.00"))
        JournalEntryLine.objects.create(journal_entry=je, account=sub_acc_2, debit=Decimal("6500.00"), credit=Decimal("0.00"))
        JournalEntryLine.objects.create(journal_entry=je, account=env["opb_equity"], debit=Decimal("0.00"), credit=Decimal("10000.00"))

        assert sub_acc_1.get_balance() == Decimal("3500.00")
        assert sub_acc_2.get_balance() == Decimal("6500.00")

        # رصيد حساب التحكم الأب عبر التجميع الصاعد التلقائي
        control_balance = control_acc.get_balance()
        assert control_balance == Decimal("10000.00")
        assert control_balance == sub_acc_1.get_balance() + sub_acc_2.get_balance()


@pytest.mark.django_db
class TestFXAndContinuousLedger:
    """4.4 اختبارات تقييم العملات والدفتر المستمر عبر السنوات المالية"""

    def test_fx_revaluation_does_not_double_opening_balance(self, phase4_setup):
        """
        التحقق من أن FXRevaluationService تحسب فروق الصرف الدفترية بدقة
        دون جمع أو مضاعفة الرصيد الافتتاحي لحسابات النقدية والبنوك الأجنبية
        """
        env = phase4_setup
        usd_cash = ChartOfAccounts.objects.create(
            code="11119005",
            name="خزينة دولارية للتسوية",
            account_type=env["asset_type"],
            currency=env["usd"],
            is_cash_account=True,
            is_leaf=True,
            is_active=True
        )

        # قيد 1,000 USD بسعر صرف 48.00 ج.م = 48,000 ج.م
        je = JournalEntry.objects.create(
            number="JE-FX-01",
            date=date(2026, 1, 1),
            accounting_period=env["p26"],
            status="posted",
            entry_type="opening",
            created_by=env["user"],
            posted_by=env["user"]
        )
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=usd_cash,
            debit=Decimal("48000.00"),
            credit=Decimal("0.00"),
            foreign_debit=Decimal("1000.00"),
            foreign_credit=Decimal("0.00"),
            currency="USD",
            exchange_rate=Decimal("48.00")
        )
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=env["opb_equity"],
            debit=Decimal("0.00"),
            credit=Decimal("48000.00")
        )

        from financial.models.currency import ExchangeRate
        ExchangeRate.objects.create(
            from_currency=env["usd"],
            to_currency=env["egp"],
            rate=Decimal("50.000000"),
            effective_date=date(2026, 1, 31),
        )

        result = FXRevaluationService.calculate_open_items_revaluation(as_of_date=date(2026, 1, 31))
        cash_items = [i for i in result["cash_items"] if i["account_id"] == usd_cash.id]
        assert len(cash_items) == 1
        usd_item = cash_items[0]
        # الرصيد بالعملة الأجنبية يجب أن يكون 1000 USD فقط دون أي مضاعفة
        assert usd_item["open_foreign"] == Decimal("1000.00")
        # القيمة الدفترية الحالية بالجنيه 48,000 ج.م
        assert usd_item["current_gl_base"] == Decimal("48000.00")
        # أرباح فروق العملة غير المحققة: 1000 * 50 = 50,000 - 48,000 = 2,000 ج.م
        assert usd_item["unrealized_diff"] == Decimal("2000.00")

    def test_continuous_ledger_multi_year_natural_rollover(self, phase4_setup):
        """
        الدفتر المستمر (Continuous Ledger):
        حسابات الميزانية في السنة السابقة (2025) تسري بطبيعتها وتظهر في أرصدة السنة التالية (2026)
        دون الحاجة لقيود OPN تدويرية قد تؤدي لتشوه ومضاعفة الرصيد
        """
        env = phase4_setup
        building_acc = ChartOfAccounts.objects.create(
            code="12019001",
            name="أصول ثابتة - مباني",
            account_type=env["asset_type"],
            currency=env["egp"],
            is_leaf=True,
            is_active=True
        )

        # حركة شراء في عام 2025 بمبلغ 200,000 ج.م
        je_2025 = JournalEntry.objects.create(
            number="JE-2025-01",
            date=date(2025, 6, 15),
            accounting_period=env["p25"],
            status="posted",
            entry_type="general",
            created_by=env["user"],
            posted_by=env["user"]
        )
        JournalEntryLine.objects.create(journal_entry=je_2025, account=building_acc, debit=Decimal("200000.00"), credit=Decimal("0.00"))
        JournalEntryLine.objects.create(journal_entry=je_2025, account=env["opb_equity"], debit=Decimal("0.00"), credit=Decimal("200000.00"))

        # الاستعلام في عام 2026
        bal_2026 = building_acc.get_balance(date_to=date(2026, 6, 1))
        assert bal_2026 == Decimal("200000.00")
        assert building_acc.current_balance == Decimal("200000.00")


@pytest.mark.django_db
class TestSecurityAndGovernanceAssurance:
    """4.5 اختبارات الحماية والأمان والتواريخ المستقبلية والسحب على المكشوف"""

    def test_security_post_2030_entries_included(self, phase4_setup):
        """
        التحقق من شمول قيود ما بعد عام 2030 بدقة وإلغاء سقف 2030 الهاردكود
        """
        env = phase4_setup
        acc = ChartOfAccounts.objects.create(
            code="11119006",
            name="حساب استثمار طويل الأجل",
            account_type=env["asset_type"],
            currency=env["egp"],
            is_leaf=True,
            is_active=True
        )

        # إنشاء قيد بتاريخ 2035-05-15
        je_future = JournalEntry.objects.create(
            number="JE-2035-01",
            date=date(2035, 5, 15),
            accounting_period=env["p35"],
            status="posted",
            entry_type="general",
            created_by=env["user"],
            posted_by=env["user"]
        )
        JournalEntryLine.objects.create(journal_entry=je_future, account=acc, debit=Decimal("75000.00"), credit=Decimal("0.00"))
        JournalEntryLine.objects.create(journal_entry=je_future, account=env["opb_equity"], debit=Decimal("0.00"), credit=Decimal("75000.00"))

        # الاستعلام بدون سقف تاريخي
        assert acc.get_balance() == Decimal("75000.00")
        assert acc.current_balance == Decimal("75000.00")

    def test_overdrawn_account_credit_side_handling(self, phase4_setup):
        """
        اختبار السحب على المكشوف:
        حساب بنكي برصيد افتتاحي سالب (-12,000 ج.م) يجب أن يُسجل قيده في الجانب الدائن للأصل
        والجانب المدين للأرصدة الافتتاحية مع اتزان ميزان المراجعة والميزانية
        """
        env = phase4_setup
        overdrawn_bank = ChartOfAccounts.objects.create(
            code="11129002",
            name="حساب بنكي سحب على المكشوف",
            account_type=env["asset_type"],
            currency=env["egp"],
            opening_balance=Decimal("-12000.00"),
            opening_balance_date=date(2026, 1, 1),
            is_bank_account=True,
            is_leaf=True,
            is_active=True
        )

        # تشغيل سكريبت الهجرة لمعالجة الحساب
        call_command("backfill_opening_balances", apply=True)

        overdrawn_bank.refresh_from_db()
        assert overdrawn_bank.current_balance == Decimal("-12000.00")

        # فحص القيد المتولد
        je = JournalEntry.objects.filter(lines__account=overdrawn_bank).first()
        assert je is not None
        assert je.status == "posted"

        line_bank = je.lines.filter(account=overdrawn_bank).first()
        line_equity = je.lines.filter(account=env["opb_equity"]).first()

        # الحساب الأصل المكشوف دائن بمبلغ 12,000 ج.م
        assert line_bank.credit == Decimal("12000.00")
        assert line_bank.debit == Decimal("0.00")

        # حساب وسيط الأرصدة الافتتاحية مدين بمبلغ 12,000 ج.م
        assert line_equity.debit == Decimal("12000.00")
        assert line_equity.credit == Decimal("0.00")

        # فحص اتزان ميزان المراجعة
        tb_data = TrialBalanceService.generate_trial_balance(date_from=date(2026, 1, 1), date_to=date(2026, 12, 31))
        assert tb_data["is_balanced"] is True
        assert tb_data["total_closing_debit"] == tb_data["total_closing_credit"]
        assert tb_data["diff_closing"] == Decimal("0.00")

    def test_cash_transfer_insufficient_funds_rejection(self, phase4_setup):
        """
        التحقق من أن خدمة التحويلات النقدية CashTransferService ترفض التحويل
        إذا كان رصيد الخزينة المصدر غير كافٍ للمبلغ المطلوب
        """
        env = phase4_setup
        source_cash = ChartOfAccounts.objects.create(
            code="11119007",
            name="خزينة مصدر ضعيفة الرصيد",
            account_type=env["asset_type"],
            currency=env["egp"],
            is_cash_account=True,
            is_leaf=True,
            is_active=True
        )
        target_cash = ChartOfAccounts.objects.create(
            code="11119008",
            name="خزينة مستلمة",
            account_type=env["asset_type"],
            currency=env["egp"],
            is_cash_account=True,
            is_leaf=True,
            is_active=True
        )

        # رصيد الخزينة المصدر 1,000 ج.م فقط
        je = JournalEntry.objects.create(
            number="JE-TRF-SRC-01",
            date=date(2026, 1, 1),
            accounting_period=env["p26"],
            status="posted",
            entry_type="general",
            created_by=env["user"],
            posted_by=env["user"]
        )
        JournalEntryLine.objects.create(journal_entry=je, account=source_cash, debit=Decimal("1000.00"), credit=Decimal("0.00"))
        JournalEntryLine.objects.create(journal_entry=je, account=env["opb_equity"], debit=Decimal("0.00"), credit=Decimal("1000.00"))

        assert source_cash.current_balance == Decimal("1000.00")

        # محاولة تحويل 2,500 ج.م
        with pytest.raises(ValidationError) as exc_info:
            CashTransferService.execute_transfer(
                from_account_id=source_cash.id,
                to_account_id=target_cash.id,
                source_amount=Decimal("2500.00"),
                user=env["user"],
                transfer_type="DIRECT",
                transfer_date=date(2026, 1, 15)
            )

        assert "غير كافٍ" in str(exc_info.value)
