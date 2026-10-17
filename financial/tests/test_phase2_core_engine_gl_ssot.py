# -*- coding: utf-8 -*-
"""
Tests for Phase 2: Core Financial Engine GL SSOT Refactoring
حزمة اختبارات شاملة ومحوكمة للمرحلة 2:
- ChartOfAccounts (get_balance, get_beginning_balance, get_balances_bulk, get_balance_optimized)
- LedgerQueryService (get_account_balance, get_account_statement) ومنع المضاعفة
- FXRevaluationService (تطهير تقييم العملات من الازدواجية)
- OpeningBalancePostingService (حارس منع تكرار الأرصدة الافتتاحية في نفس السنة)
- BalanceSheetService & TrialBalanceService (استئصال الفولباك غير المتوازن)
- CashTransferService (فحص رصيد الخزينة قبل التحويل)
"""

import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.currency import Currency
from financial.models.journal_entry import JournalEntry, JournalEntryLine, AccountingPeriod
from financial.models.fiscal_year import FiscalYear
from financial.models.opening_balance import OpeningBalanceBatch, OpeningBalanceLine
from financial.services.ledger_query_service import LedgerQueryService
from financial.services.fx_revaluation_service import FXRevaluationService
from financial.services.opening_balance_service import OpeningBalancePostingService
from financial.services.balance_sheet_service import BalanceSheetService
from financial.services.trial_balance_service import TrialBalanceService
from financial.services.cash_transfer_service import CashTransferService
from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames

User = get_user_model()


@pytest.fixture
def phase2_setup(db):
    user = User.objects.create_superuser(
        username="phase2_cfo",
        email="cfo_p2@mwheba.com",
        password="password123"
    )

    # 1. إعداد العملات
    egp_curr, _ = Currency.objects.get_or_create(code="EGP", defaults={"name": "Egyptian Pound", "is_functional": True, "is_active": True})
    usd_curr, _ = Currency.objects.get_or_create(code="USD", defaults={"name": "US Dollar", "is_functional": False, "is_active": True})

    # 2. إعداد السنة والفترة المالية
    fy, _ = FiscalYear.objects.get_or_create(
        name="FY2026-P2",
        defaults={
            "year_code": "FY26P2",
            "start_date": date(2026, 1, 1),
            "end_date": date(2026, 12, 31),
            "status": "open",
        }
    )
    period, _ = AccountingPeriod.objects.get_or_create(
        name="Period Jan 2026",
        defaults={
            "fiscal_year": fy,
            "period_number": 1,
            "start_date": date(2026, 1, 1),
            "end_date": date(2026, 1, 31),
            "status": "open",
        }
    )

    # 3. إعداد أنواع الحسابات
    asset_type, _ = AccountType.objects.get_or_create(code="P2_ASSET", defaults={"name": "أصول P2", "category": "asset", "nature": "debit"})
    equity_type, _ = AccountType.objects.get_or_create(code="P2_EQUITY", defaults={"name": "حقوق ملكية P2", "category": "equity", "nature": "credit"})
    revenue_type, _ = AccountType.objects.get_or_create(code="P2_REV", defaults={"name": "إيرادات P2", "category": "revenue", "nature": "credit"})

    # 4. حساب وسيط الأرصدة الافتتاحية
    equity_clearing, _ = ChartOfAccounts.objects.get_or_create(
        code="31010",
        defaults={"name": "الأرصدة الافتتاحية", "account_type": equity_type, "is_leaf": True, "is_active": True}
    )

    # 5. حساب أب رئيسي وحسابات فرعية
    parent_cash = ChartOfAccounts.objects.create(
        code="111000",
        name="النقدية وما في حكمها الإجمالي",
        account_type=asset_type,
        is_leaf=False,
        is_active=True,
    )

    cash_1 = ChartOfAccounts.objects.create(
        code="111001",
        name="خزينة الإدارة الرئيسية",
        account_type=asset_type,
        parent=parent_cash,
        opening_balance=Decimal("10000.00"),  # Legacy static field value
        is_leaf=True,
        is_active=True,
        is_cash_account=True,
        currency=egp_curr,
    )

    cash_2 = ChartOfAccounts.objects.create(
        code="111002",
        name="خزينة الفرع ب",
        account_type=asset_type,
        parent=parent_cash,
        is_leaf=True,
        is_active=True,
        is_cash_account=True,
        currency=egp_curr,
    )

    usd_cash = ChartOfAccounts.objects.create(
        code="111003",
        name="خزينة الدولار",
        account_type=asset_type,
        parent=parent_cash,
        opening_balance=Decimal("25000.00"),
        opening_balance_foreign=Decimal("500.00"),
        opening_balance_rate=Decimal("50.000000"),
        is_leaf=True,
        is_active=True,
        is_cash_account=True,
        currency=usd_curr,
    )

    sales_acc = ChartOfAccounts.objects.create(
        code="411001",
        name="إيراد المبيعات P2",
        account_type=revenue_type,
        is_leaf=True,
        is_active=True,
        currency=egp_curr,
    )

    # إنشاء قيد افتتاحي مرحل لـ cash_1 بقيمة 10,000 ج.م
    je_opb = JournalEntry.objects.create(
        number="GL26-P2-01",
        date=date(2026, 1, 1),
        entry_type="opening",
        status="posted",
        reference="OPB-111001",
        description="قيد رصيد افتتاحي مرحل لخزينة الإدارة",
        accounting_period=period,
        created_by=user,
        posted_by=user,
    )
    JournalEntryLine.objects.create(
        journal_entry=je_opb,
        account=cash_1,
        debit=Decimal("10000.00"),
        credit=Decimal("0.00"),
        currency="EGP",
        exchange_rate=Decimal("1.000000"),
        description="افتتاحي خزينة",
    )
    JournalEntryLine.objects.create(
        journal_entry=je_opb,
        account=equity_clearing,
        debit=Decimal("0.00"),
        credit=Decimal("10000.00"),
        currency="EGP",
        exchange_rate=Decimal("1.000000"),
        description="مقابل افتتاحي",
    )

    # إنشاء قيد تشغيلي بتاريخ 2026-01-15: مبيعات نقدية 3,000 ج.م في cash_1
    je_sale = JournalEntry.objects.create(
        number="GL26-P2-02",
        date=date(2026, 1, 15),
        entry_type="manual",
        status="posted",
        reference="SAL-001",
        description="مبيعات نقدية",
        accounting_period=period,
        created_by=user,
        posted_by=user,
    )
    JournalEntryLine.objects.create(
        journal_entry=je_sale,
        account=cash_1,
        debit=Decimal("3000.00"),
        credit=Decimal("0.00"),
        currency="EGP",
        exchange_rate=Decimal("1.000000"),
        description="تحصيل مبيعات",
    )
    JournalEntryLine.objects.create(
        journal_entry=je_sale,
        account=sales_acc,
        debit=Decimal("0.00"),
        credit=Decimal("3000.00"),
        currency="EGP",
        exchange_rate=Decimal("1.000000"),
        description="إيراد مبيعات",
    )

    return {
        "user": user,
        "egp_curr": egp_curr,
        "usd_curr": usd_curr,
        "fy": fy,
        "period": period,
        "parent_cash": parent_cash,
        "cash_1": cash_1,
        "cash_2": cash_2,
        "usd_cash": usd_cash,
        "equity_clearing": equity_clearing,
        "sales_acc": sales_acc,
    }


@pytest.mark.django_db
def test_chart_of_accounts_get_balance_pure_gl(phase2_setup):
    """
    اختبار ChartOfAccounts:
    - الرصيد يستخرج 100% من دفتر الأستاذ دون مضاعفة حقل opening_balance
    - الحساب الأب يجمع رصيد أبنائه النهائيين
    - رصيد أول المدة get_beginning_balance يستخرج الحركات قبل التاريخ بدقة
    - استعلام مستقبلي بعد 2030 يعمل دون سقف هاردكود
    """
    cash_1 = phase2_setup["cash_1"]
    parent_cash = phase2_setup["parent_cash"]

    # 1. رصيد cash_1 يجب أن يكون 10,000 (افتتاحي) + 3,000 (مبيعات) = 13,000 ج.م
    # (وليس 23,000 ج.م كما كان يحدث بسبب مضاعفة حقل opening_balance)
    assert cash_1.get_balance() == Decimal("13000.00")
    assert cash_1.current_balance == Decimal("13000.00")

    # 2. رصيد أول المدة لتاريخ 2026-01-15 يجب أن يكون 10,000 ج.م فقط
    assert cash_1.get_beginning_balance(as_of_date=date(2026, 1, 15)) == Decimal("10000.00")

    # 3. الحساب الأب (parent_cash) يجب أن يعكس مجموع الأبناء (13,000 ج.م)
    assert parent_cash.get_balance() == Decimal("13000.00")

    # 4. الاستعلام في تاريخ مستقبلي (مثلاً 2035) يعمل بنجاح
    future_bal = cash_1.get_balance(date_to=date(2035, 1, 1))
    assert future_bal == Decimal("13000.00")


@pytest.mark.django_db
def test_ledger_query_service_no_doubling(phase2_setup):
    """
    اختبار LedgerQueryService:
    - التحقق الصارم من عدم مضاعفة الرصيد في get_account_balance
    - التحقق الصارم من عدم مضاعفة رصيد البداية في get_account_statement
    """
    cash_1 = phase2_setup["cash_1"]

    # 1. فحص get_account_balance
    data = LedgerQueryService.get_account_balance(cash_1)
    assert data["balance"] == Decimal("13000.00"), "الرصيد يجب ألا يتضاعف بإضافة حقل الموديل"

    # 2. فحص get_account_statement بدون start_date
    stmt_all = LedgerQueryService.get_account_statement(cash_1)
    assert stmt_all["opening_balance"] == Decimal("10000.00")
    assert stmt_all["closing_balance"] == Decimal("13000.00")

    # 3. فحص get_account_statement مع start_date=2026-01-15
    stmt_period = LedgerQueryService.get_account_statement(cash_1, start_date=date(2026, 1, 15), end_date=date(2026, 1, 31))
    assert stmt_period["opening_balance"] == Decimal("10000.00")
    assert stmt_period["closing_balance"] == Decimal("13000.00")


@pytest.mark.django_db
def test_opening_balance_posting_duplicate_guard(phase2_setup):
    """
    اختبار حارس منع تكرار الأرصدة الافتتاحية في نفس السنة المالية:
    محاولة ترحيل دفعة افتتاحية جديدة لحساب cash_1 في نفس السنة المالية يجب أن ترمي ValidationError
    """
    batch = OpeningBalanceBatch.objects.create(
        batch_number="OPB-DUP-TEST",
        fiscal_year=phase2_setup["fy"],
        opening_date=date(2026, 1, 1),
        status="draft",
        created_by=phase2_setup["user"]
    )
    OpeningBalanceLine.objects.create(
        batch=batch,
        account=phase2_setup["cash_1"],
        debit=Decimal("5000.00"),
        credit=Decimal("0.00"),
    )
    OpeningBalanceLine.objects.create(
        batch=batch,
        account=phase2_setup["equity_clearing"],
        debit=Decimal("0.00"),
        credit=Decimal("5000.00"),
    )

    with pytest.raises(ValidationError) as exc_info:
        OpeningBalancePostingService.post(batch.id, phase2_setup["user"])

    assert "يوجد قيد رصيد افتتاحي نشط بالفعل" in str(exc_info.value)


@pytest.mark.django_db
def test_cash_transfer_insufficient_gl_balance_blocked(phase2_setup):
    """
    اختبار CashTransferService:
    محاولة تحويل مبلغ أكبر من رصيد الخزينة المصدر الفعلي يجب أن تفشل وترمي ValidationError
    """
    cash_1 = phase2_setup["cash_1"]
    cash_2 = phase2_setup["cash_2"]
    user = phase2_setup["user"]

    # رصيد cash_1 الحالي هو 13,000 ج.م
    # محاولة تحويل 20,000 ج.م يجب أن تمنع فوراً
    with pytest.raises(ValidationError) as exc_info:
        CashTransferService.execute_transfer(
            from_account_id=cash_1.id,
            to_account_id=cash_2.id,
            source_amount=Decimal("20000.00"),
            user=user,
            transfer_date=date(2026, 1, 20),
        )

    assert "غير كافٍ لإتمام تحويل" in str(exc_info.value)


@pytest.mark.django_db
def test_fx_revaluation_service_no_doubling(phase2_setup):
    """
    اختبار FXRevaluationService:
    التأكد من أن تقييم العملة لحساب النقدية الأجنبية يستخرج الرصيد 100% من بنود القيود
    ولا يضاعف رصيد العملة الأجنبية أو المعادل المحلي بإضافة حقول الموديل.
    """
    usd_cash = phase2_setup["usd_cash"]
    user = phase2_setup["user"]
    period = phase2_setup["period"]

    # إنشاء قيد افتتاحي مرحل لـ usd_cash بقيمة 500 دولار (معادل 25,000 ج.م بسعر 50.0)
    je_usd = JournalEntry.objects.create(
        number="GL26-P2-USD",
        date=date(2026, 1, 1),
        entry_type="opening",
        status="posted",
        reference="OPB-111003",
        description="افتتاحي خزينة دولار",
        accounting_period=period,
        created_by=user,
        posted_by=user,
    )
    JournalEntryLine.objects.create(
        journal_entry=je_usd,
        account=usd_cash,
        debit=Decimal("25000.00"),
        credit=Decimal("0.00"),
        currency="USD",
        exchange_rate=Decimal("50.000000"),
        foreign_debit=Decimal("500.00"),
        foreign_credit=Decimal("0.00"),
        description="افتتاحي 500 دولار",
    )
    JournalEntryLine.objects.create(
        journal_entry=je_usd,
        account=phase2_setup["equity_clearing"],
        debit=Decimal("0.00"),
        credit=Decimal("25000.00"),
        currency="EGP",
        exchange_rate=Decimal("1.000000"),
        description="مقابل افتتاحي دولار",
    )

    from financial.models.currency import ExchangeRate
    ExchangeRate.objects.create(
        from_currency=usd_cash.currency,
        to_currency=phase2_setup["cash_1"].currency,
        rate=Decimal("52.000000"),
        effective_date=date(2026, 1, 31),
    )

    result = FXRevaluationService.calculate_open_items_revaluation(as_of_date=date(2026, 1, 31))
    cash_items = [i for i in result["cash_items"] if i["account_id"] == usd_cash.id]

    assert len(cash_items) == 1
    usd_item = cash_items[0]
    # رصيد العملة الأجنبية يجب أن يكون 500.00 دولار تماماً (وليس 1,000.00 دولار بالمضاعفة)
    assert usd_item["open_foreign"] == Decimal("500.00")
    # الرصيد الدفتري الحالي المسجل بالدفتر هو 25,000.00 ج.م (وليس 50,000.00 ج.م بالمضاعفة)
    assert usd_item["current_gl_base"] == Decimal("25000.00")
    # التقييم الجديد: 500 * 52 = 26,000 ج.م => فرق تقييم غير محقق 1,000 ج.م
    assert usd_item["unrealized_diff"] == Decimal("1000.00")


@pytest.mark.django_db
def test_balance_sheet_pure_double_entry(phase2_setup):
    """
    اختبار BalanceSheetService:
    التأكد من أن الميزانية العمومية تعتمد 100% على القيود المتزنة دفترياً دون أي فولباك أحادي
    """
    report = BalanceSheetService.generate_balance_sheet(
        as_of_date=date(2026, 1, 31)
    )
    assert report is not None
    # التحقق من أن الميزانية تم توليدها بنجاح ومتزنة تماماً دفترياً
    assert report["is_balanced"] is True
    assert report["total_assets"] == report["total_liabilities_equity"]

