# financial/tests/test_cash_flow_service.py
"""
حزمة اختبارات خدمة وقالب قائمة التدفقات النقدية المعيارية (IAS 7)
تغطي الطريقة غير المباشرة، تسويات رأس المال العامل، الإهلاك، المقارنات، وفحص التوازن التام.
"""

import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.test import Client

from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.journal_entry import JournalEntry, JournalEntryLine
from financial.models.currency import Currency
from financial.services.cash_flow_service import CashFlowService

User = get_user_model()


@pytest.fixture
def cf_setup(db):
    """
    تجهيز بيئة الاختبار المحاسبية للتدفقات النقدية
    """
    # 1. إنشاء العملة
    currency, _ = Currency.objects.get_or_create(
        code="EGP",
        defaults={"name": "جنيه مصري", "symbol": "ج.م", "is_functional": True, "is_active": True}
    )

    # 2. أنواع الحسابات
    asset_type, _ = AccountType.objects.get_or_create(code="ASSET", defaults={"name": "أصول", "category": "asset", "nature": "debit"})
    liability_type, _ = AccountType.objects.get_or_create(code="LIAB", defaults={"name": "خصوم", "category": "liability", "nature": "credit"})
    equity_type, _ = AccountType.objects.get_or_create(code="EQUITY", defaults={"name": "حقوق ملكية", "category": "equity", "nature": "credit"})
    revenue_type, _ = AccountType.objects.get_or_create(code="REV", defaults={"name": "إيرادات", "category": "revenue", "nature": "credit"})
    expense_type, _ = AccountType.objects.get_or_create(code="EXP", defaults={"name": "مصروفات", "category": "expense", "nature": "debit"})

    # 3. الحسابات الرئيسية والطرفية
    cash_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="11110",
        defaults={"name": "الخزينة الرئيسية", "account_type": asset_type, "level": 3, "is_leaf": True, "currency": currency}
    )

    bank_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="11120",
        defaults={"name": "بنك مصر", "account_type": asset_type, "level": 3, "is_leaf": True, "currency": currency}
    )

    customer_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="11210",
        defaults={"name": "العملاء", "account_type": asset_type, "level": 3, "is_leaf": True, "currency": currency}
    )

    inventory_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="11310",
        defaults={"name": "مخزون البضائع", "account_type": asset_type, "level": 3, "is_leaf": True, "currency": currency}
    )

    fixed_assets_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="12130",
        defaults={"name": "الآلات والمعدات", "account_type": asset_type, "level": 3, "is_leaf": True, "currency": currency}
    )

    accum_depr_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="12230",
        defaults={"name": "مجمع إهلاك الآلات", "account_type": asset_type, "level": 3, "is_leaf": True, "currency": currency}
    )

    supplier_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="21110",
        defaults={"name": "الموردون", "account_type": liability_type, "level": 3, "is_leaf": True, "currency": currency}
    )

    capital_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="31110",
        defaults={"name": "رأس المال المدفوع", "account_type": equity_type, "level": 3, "is_leaf": True, "currency": currency}
    )

    sales_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="41100",
        defaults={"name": "إيرادات المبيعات", "account_type": revenue_type, "level": 3, "is_leaf": True, "currency": currency}
    )

    cogs_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="51100",
        defaults={"name": "تكلفة البضاعة المباعة", "account_type": expense_type, "level": 3, "is_leaf": True, "currency": currency}
    )

    depr_exp_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="52800",
        defaults={"name": "مصروف إهلاك الأصول", "account_type": expense_type, "level": 3, "is_leaf": True, "currency": currency}
    )

    user, _ = User.objects.get_or_create(username="test_cfo", defaults={"email": "cfo@example.com", "is_staff": True})

    return {
        "user": user,
        "cash_acc": cash_acc,
        "bank_acc": bank_acc,
        "customer_acc": customer_acc,
        "inventory_acc": inventory_acc,
        "fixed_assets_acc": fixed_assets_acc,
        "accum_depr_acc": accum_depr_acc,
        "supplier_acc": supplier_acc,
        "capital_acc": capital_acc,
        "sales_acc": sales_acc,
        "cogs_acc": cogs_acc,
        "depr_exp_acc": depr_exp_acc,
    }


@pytest.mark.django_db
def test_cash_flow_operating_and_reconciliation(cf_setup):
    """
    اختبار حساب التدفق التشغيلي وتسويات رأس المال العامل والإهلاك وفحص التطابق التام
    """
    s = cf_setup
    today = date(2026, 6, 15)
    d_from = date(2026, 6, 1)
    d_to = date(2026, 6, 30)

    # 1. رصيد افتتاحي في 1 مايو: رأس مال 500,000 ج.م في الخزينة
    je_open = JournalEntry.objects.create(
        number="JE-OPEN-01",
        date=date(2026, 5, 1),
        status="posted",
        entry_type="opening",
        created_by=s["user"]
    )
    JournalEntryLine.objects.create(journal_entry=je_open, account=s["cash_acc"], debit=Decimal("500000"), credit=Decimal("0"))
    JournalEntryLine.objects.create(journal_entry=je_open, account=s["capital_acc"], debit=Decimal("0"), credit=Decimal("500000"))

    # 2. مبيعات نقدية في يونيو: 100,000 ج.م
    je_sale = JournalEntry.objects.create(
        number="JE-SALE-01",
        date=date(2026, 6, 5),
        status="posted",
        entry_type="sales_invoice",
        created_by=s["user"]
    )
    JournalEntryLine.objects.create(journal_entry=je_sale, account=s["cash_acc"], debit=Decimal("100000"), credit=Decimal("0"))
    JournalEntryLine.objects.create(journal_entry=je_sale, account=s["sales_acc"], debit=Decimal("0"), credit=Decimal("100000"))

    # 3. مبيعات آجلة على العملاء: 40,000 ج.م (لم تُحصل نقدياً)
    je_credit_sale = JournalEntry.objects.create(
        number="JE-SALE-02",
        date=date(2026, 6, 10),
        status="posted",
        entry_type="sales_invoice",
        created_by=s["user"]
    )
    JournalEntryLine.objects.create(journal_entry=je_credit_sale, account=s["customer_acc"], debit=Decimal("40000"), credit=Decimal("0"))
    JournalEntryLine.objects.create(journal_entry=je_credit_sale, account=s["sales_acc"], debit=Decimal("0"), credit=Decimal("40000"))

    # 4. مصروف إهلاك غير نقدي: 10,000 ج.م
    je_depr = JournalEntry.objects.create(
        number="JE-DEPR-01",
        date=date(2026, 6, 20),
        status="posted",
        entry_type="adjustment",
        created_by=s["user"]
    )
    JournalEntryLine.objects.create(journal_entry=je_depr, account=s["depr_exp_acc"], debit=Decimal("10000"), credit=Decimal("0"))
    JournalEntryLine.objects.create(journal_entry=je_depr, account=s["accum_depr_acc"], debit=Decimal("0"), credit=Decimal("10000"))

    # 5. شراء آلات نقدية (CAPEX استثماري): 50,000 ج.م
    je_capex = JournalEntry.objects.create(
        number="JE-CAPEX-01",
        date=date(2026, 6, 25),
        status="posted",
        entry_type="automatic",
        created_by=s["user"]
    )
    JournalEntryLine.objects.create(journal_entry=je_capex, account=s["fixed_assets_acc"], debit=Decimal("50000"), credit=Decimal("0"))
    JournalEntryLine.objects.create(journal_entry=je_capex, account=s["cash_acc"], debit=Decimal("0"), credit=Decimal("50000"))

    # تشغيل خدمة التدفقات النقدية
    res = CashFlowService.generate_cash_flow_statement(
        date_from=d_from,
        date_to=d_to,
        hide_zero_balances=False,
    )

    # التحقق من النتائج:
    # 1. الرصيد الافتتاحي للنقدية في 1 يونيو = 500,000 ج.م
    assert res["beginning_cash"] == Decimal("500000")

    # 2. صافي الدخل المحاسبي = 140,000 إيرادات - 10,000 إهلاك = 130,000 ج.م
    assert res["net_income"] == Decimal("130000")

    # 3. إضافة الإهلاك غير النقدي = +10,000 ج.م
    assert res["non_cash_adjustments"]["total"] == Decimal("10000")

    # 4. التغير في رأس المال العامل: العملاء زادوا 40,000 -> تدفق خارج -40,000 ج.م
    assert res["working_capital"]["total"] == Decimal("-40000")

    # 5. صافي التدفق التشغيلي = 130,000 + 10,000 - 40,000 = 100,000 ج.م (تطابق المبيعات النقدية الفعلية!)
    assert res["net_operating_cash_flow"] == Decimal("100000")

    # 6. صافي التدفق الاستثماري = -50,000 ج.م
    assert res["investing_activities"]["total"] == Decimal("-50000")

    # 7. صافي التغير في النقدية = 100,000 تشغيلي - 50,000 استثماري = +50,000 ج.م
    assert res["total_net_cash_flow"] == Decimal("50000")

    # 8. الرصيد الختامي الفعلي = 500,000 + 50,000 = 550,000 ج.م
    assert res["actual_ending_cash"] == Decimal("550000")
    assert res["calculated_ending_cash"] == Decimal("550000")

    # 9. فحص التطابق التام (Reconciliation Check) = 0.00
    assert res["discrepancy"] == Decimal("0.00")
    assert res["is_balanced"] is True


@pytest.mark.django_db
def test_cash_flow_closing_entry_exclusion(cf_setup):
    """
    اختبار استبعاد قيود الإقفال السنوية لضمان سلامة التدفقات لفترة تاريخية مقفلة
    """
    s = cf_setup
    d_from = date(2025, 1, 1)
    d_to = date(2025, 12, 31)

    # مبيعات نقدية في 2025
    je_sale = JournalEntry.objects.create(
        number="JE-SALE-2025",
        date=date(2025, 6, 1),
        status="posted",
        entry_type="sales_invoice",
        created_by=s["user"]
    )
    JournalEntryLine.objects.create(journal_entry=je_sale, account=s["cash_acc"], debit=Decimal("200000"), credit=Decimal("0"))
    JournalEntryLine.objects.create(journal_entry=je_sale, account=s["sales_acc"], debit=Decimal("0"), credit=Decimal("200000"))

    # قيد إقفال أرباح وخسائر في نهاية 2025
    je_close = JournalEntry.objects.create(
        number="JE-CLOSE-2025",
        date=date(2025, 12, 31),
        status="posted",
        entry_type="closing",
        created_by=s["user"]
    )
    JournalEntryLine.objects.create(journal_entry=je_close, account=s["sales_acc"], debit=Decimal("200000"), credit=Decimal("0"))
    JournalEntryLine.objects.create(journal_entry=je_close, account=s["capital_acc"], debit=Decimal("0"), credit=Decimal("200000"))

    res = CashFlowService.generate_cash_flow_statement(date_from=d_from, date_to=d_to)

    # صافي الدخل والتشغيلي يجب أن يظلا 200,000 ج.م بالرغم من وجود قيد الإقفال
    assert res["net_income"] == Decimal("200000")
    assert res["net_operating_cash_flow"] == Decimal("200000")
    assert res["is_balanced"] is True


@pytest.mark.django_db
def test_cash_flow_excel_export(cf_setup):
    """
    اختبار توليد وتصدير ملف Excel لقائمة التدفقات النقدية
    """
    excel_bytes = CashFlowService.export_to_excel(
        date_from=date(2026, 1, 1),
        date_to=date(2026, 12, 31)
    )
    assert excel_bytes is not None
    assert len(excel_bytes) > 1000
    assert excel_bytes.startswith(b"PK")  # ZIP header for XLSX


@pytest.mark.django_db
def test_cash_flow_view_response(cf_setup):
    """
    اختبار استجابة View قائمة التدفقات النقدية وحضور الفلاتر والأزرار المعيارية
    """
    client = Client()
    client.force_login(cf_setup["user"])

    url = reverse("financial:cash_flow_statement")
    response = client.get(url, {"date_from": "2026-01-01", "date_to": "2026-12-31", "preset": "ytd"})

    assert response.status_code == 200
    assert "cf" in response.context
    assert response.context["active_preset"] == "ytd"
    assert "incomeStatementTable" not in response.content.decode("utf-8")  # Confirm clean ID
    assert "cashFlowTable" in response.content.decode("utf-8")
