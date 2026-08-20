# financial/tests/test_financial_analytics_service.py
"""
حزمة اختبارات خدمة وقالب لوحة التحليلات والمؤشرات المالية التنفيذية (v3.0)
تغطي المحاور الخمسة، مؤشر ألتمان للسلامة المالية، المقارنة الزمنية المزدوجة، دورة التحول النقدي، وتصدير Excel.
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
from financial.services.financial_analytics_service import FinancialAnalyticsService

User = get_user_model()


@pytest.fixture
def analytics_setup(db):
    """
    تجهيز بيئة الاختبار المحاسبية للتحليلات المالية
    """
    currency, _ = Currency.objects.get_or_create(
        code="EGP",
        defaults={"name": "جنيه مصري", "symbol": "ج.م", "is_functional": True, "is_active": True}
    )

    asset_type, _ = AccountType.objects.get_or_create(code="ASSET", defaults={"name": "أصول", "category": "asset", "nature": "debit"})
    liability_type, _ = AccountType.objects.get_or_create(code="LIAB", defaults={"name": "خصوم", "category": "liability", "nature": "credit"})
    equity_type, _ = AccountType.objects.get_or_create(code="EQUITY", defaults={"name": "حقوق ملكية", "category": "equity", "nature": "credit"})
    revenue_type, _ = AccountType.objects.get_or_create(code="REV", defaults={"name": "إيرادات", "category": "revenue", "nature": "credit"})
    expense_type, _ = AccountType.objects.get_or_create(code="EXP", defaults={"name": "مصروفات", "category": "expense", "nature": "debit"})

    cash_acc, _ = ChartOfAccounts.objects.get_or_create(code="11110", defaults={"name": "الخزينة", "account_type": asset_type, "level": 3, "is_leaf": True})
    ar_acc, _ = ChartOfAccounts.objects.get_or_create(code="11210", defaults={"name": "العملاء", "account_type": asset_type, "level": 3, "is_leaf": True})
    inv_acc, _ = ChartOfAccounts.objects.get_or_create(code="11310", defaults={"name": "المخزون", "account_type": asset_type, "level": 3, "is_leaf": True})
    fa_acc, _ = ChartOfAccounts.objects.get_or_create(code="12110", defaults={"name": "الأصول الثابتة", "account_type": asset_type, "level": 3, "is_leaf": True})

    ap_acc, _ = ChartOfAccounts.objects.get_or_create(code="21110", defaults={"name": "الموردون", "account_type": liability_type, "level": 3, "is_leaf": True})
    capital_acc, _ = ChartOfAccounts.objects.get_or_create(code="31110", defaults={"name": "رأس المال", "account_type": equity_type, "level": 3, "is_leaf": True})
    retained_acc, _ = ChartOfAccounts.objects.get_or_create(code="32210", defaults={"name": "الأرباح المرحلة", "account_type": equity_type, "level": 3, "is_leaf": True})

    sales_acc, _ = ChartOfAccounts.objects.get_or_create(code="41100", defaults={"name": "المبيعات", "account_type": revenue_type, "level": 3, "is_leaf": True})
    cogs_acc, _ = ChartOfAccounts.objects.get_or_create(code="51100", defaults={"name": "تكلفة المبيعات", "account_type": expense_type, "level": 3, "is_leaf": True})
    admin_acc, _ = ChartOfAccounts.objects.get_or_create(code="52100", defaults={"name": "مصروفات إدارية", "account_type": expense_type, "level": 3, "is_leaf": True})

    user, _ = User.objects.get_or_create(username="test_cfo", defaults={"email": "cfo@example.com", "is_staff": True})

    return {
        "user": user,
        "cash_acc": cash_acc,
        "ar_acc": ar_acc,
        "inv_acc": inv_acc,
        "fa_acc": fa_acc,
        "ap_acc": ap_acc,
        "capital_acc": capital_acc,
        "retained_acc": retained_acc,
        "sales_acc": sales_acc,
        "cogs_acc": cogs_acc,
        "admin_acc": admin_acc,
    }


@pytest.mark.django_db
def test_financial_analytics_altman_z_and_comparative(analytics_setup):
    """
    اختبار حساب مؤشر ألتمان للسلامة المالية والمقارنة الزمنية
    """
    s = analytics_setup
    d_from = date(2026, 6, 1)
    d_to = date(2026, 6, 30)

    # 1. رصيد افتتاحي في 2025: رأس مال 500,000 ج.م
    je_open = JournalEntry.objects.create(number="JE-OPEN-01", date=date(2025, 12, 31), status="posted", entry_type="opening", created_by=s["user"])
    JournalEntryLine.objects.create(journal_entry=je_open, account=s["cash_acc"], debit=Decimal("200000"), credit=Decimal("0"))
    JournalEntryLine.objects.create(journal_entry=je_open, account=s["inv_acc"], debit=Decimal("100000"), credit=Decimal("0"))
    JournalEntryLine.objects.create(journal_entry=je_open, account=s["fa_acc"], debit=Decimal("200000"), credit=Decimal("0"))
    JournalEntryLine.objects.create(journal_entry=je_open, account=s["capital_acc"], debit=Decimal("0"), credit=Decimal("500000"))

    # 2. مبيعات مايو 2026 (فترة المقارنة): 100,000 ج.م
    je_sale_may = JournalEntry.objects.create(number="JE-SALE-MAY", date=date(2026, 5, 15), status="posted", entry_type="sales_invoice", created_by=s["user"])
    JournalEntryLine.objects.create(journal_entry=je_sale_may, account=s["cash_acc"], debit=Decimal("100000"), credit=Decimal("0"))
    JournalEntryLine.objects.create(journal_entry=je_sale_may, account=s["sales_acc"], debit=Decimal("0"), credit=Decimal("100000"))

    # 3. مبيعات يونيو 2026 (الفترة الحالية): 300,000 ج.م
    je_sale_jun = JournalEntry.objects.create(number="JE-SALE-JUN", date=date(2026, 6, 15), status="posted", entry_type="sales_invoice", created_by=s["user"])
    JournalEntryLine.objects.create(journal_entry=je_sale_jun, account=s["cash_acc"], debit=Decimal("100000"), credit=Decimal("0"))
    JournalEntryLine.objects.create(journal_entry=je_sale_jun, account=s["ar_acc"], debit=Decimal("200000"), credit=Decimal("0"))
    JournalEntryLine.objects.create(journal_entry=je_sale_jun, account=s["sales_acc"], debit=Decimal("0"), credit=Decimal("300000"))

    # 4. تكلفة مبيعات ومصروفات يونيو
    je_cogs = JournalEntry.objects.create(number="JE-COGS-JUN", date=date(2026, 6, 20), status="posted", entry_type="automatic", created_by=s["user"])
    JournalEntryLine.objects.create(journal_entry=je_cogs, account=s["cogs_acc"], debit=Decimal("120000"), credit=Decimal("0"))
    JournalEntryLine.objects.create(journal_entry=je_cogs, account=s["inv_acc"], debit=Decimal("0"), credit=Decimal("120000"))

    je_pur = JournalEntry.objects.create(number="JE-PUR-JUN", date=date(2026, 6, 25), status="posted", entry_type="purchase_invoice", created_by=s["user"])
    JournalEntryLine.objects.create(journal_entry=je_pur, account=s["inv_acc"], debit=Decimal("150000"), credit=Decimal("0"))
    JournalEntryLine.objects.create(journal_entry=je_pur, account=s["ap_acc"], debit=Decimal("0"), credit=Decimal("150000"))

    # تشغيل الخدمة مع تحديد فترة المقارنة (مايو 2026)
    res = FinancialAnalyticsService.get_complete_analytics(
        date_from=d_from,
        date_to=d_to,
        comp_date_from=date(2026, 5, 1),
        comp_date_to=date(2026, 5, 31)
    )

    # 1. فحص المقارنة
    assert res["has_comparison"] is True
    # مبيعات يونيو 300,000 مقارنة بمايو 100,000 (زيادة +200%)
    assert res["basic_metrics"]["monthly_income"] == Decimal("300000")
    assert res["basic_metrics"]["comp_monthly_income"] == Decimal("100000")
    assert res["basic_metrics"]["delta_income"]["pct"] == Decimal("200.0")

    # 2. فحص مؤشر ألتمان Z-Score
    alt = res["altman_z"]
    assert alt["z_score"] > Decimal("0")
    assert alt["zone"] in ["safe", "grey", "distress"]
    assert alt["zone_class"] in ["success", "warning", "danger"]


@pytest.mark.django_db
def test_financial_analytics_excel_export(analytics_setup):
    """
    اختبار تصدير لوحة التحليلات إلى Excel مع المقارنة
    """
    excel_bytes = FinancialAnalyticsService.export_to_excel(
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
        comp_date_from=date(2026, 5, 1),
        comp_date_to=date(2026, 5, 31)
    )
    assert excel_bytes is not None
    assert len(excel_bytes) > 1000
    assert excel_bytes.startswith(b"PK")


@pytest.mark.django_db
def test_financial_analytics_view_response(analytics_setup):
    """
    اختبار استجابة View التحليلات المالية
    """
    client = Client()
    client.force_login(analytics_setup["user"])

    url = reverse("financial:financial_analytics")
    response = client.get(url, {"date_from": "2026-06-01", "date_to": "2026-06-30", "preset": "this_month"})

    assert response.status_code == 200
    assert "analytics" in response.context
    assert "altman_z" in response.context
    assert "health_scorecard" in response.context
    assert response.context["active_preset"] == "this_month"
    assert "monthlyTrendsChart" in response.content.decode("utf-8")
