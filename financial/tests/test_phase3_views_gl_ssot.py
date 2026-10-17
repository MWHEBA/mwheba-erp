# -*- coding: utf-8 -*-
"""
Tests for Phase 3: Views & UI Standardization GL SSOT Architecture
اختبارات شاملة ومحوكمة للمرحلة 3:
1. شجرة الحسابات (chart_of_accounts_list): التجميع الصافي ومنع مضاعفة الرصيد
2. داشبورد الخزن والبنوك (cash_and_bank_accounts_list): استئصال مضاعفة أرصدة العهد
3. كشف حركات الخزينة (cash_account_movements): الرصيد التراكمي للعملات الأجنبية الصافي
4. مسار الإلغاء الآمن للتأسيس (Safe Setup Void via Reversal in cash_account_delete)
5. تأمين محضر جرد العهد (count_create_view): حساب الرصيد الدفتري سيرفر-سايد
6. إنشاء الحسابات العامة (account_create): توليد القيد الافتتاحي المتزن آلياً
7. تأمين تعديل الحسابات (account_edit): حظر تعديل الرصيد الافتتاحي مباشرة على الموديل
"""

import pytest
from decimal import Decimal
from datetime import date
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.currency import Currency
from financial.models.journal_entry import JournalEntry, JournalEntryLine, AccountingPeriod
from financial.models.fiscal_year import FiscalYear
from financial.models.custody import PettyCashCount
from hr.models.employee import Employee
from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames

User = get_user_model()


@pytest.fixture
def phase3_setup(db):
    user = User.objects.create_superuser(
        username="phase3_admin",
        email="admin_p3@mwheba.com",
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

    # 2. إعداد السنة والفترة المالية
    fy, _ = FiscalYear.objects.get_or_create(
        name="FY2026-P3",
        defaults={
            "year_code": "FY26P3",
            "start_date": date(2026, 1, 1),
            "end_date": date(2026, 12, 31),
            "status": "open",
        }
    )
    period, _ = AccountingPeriod.objects.get_or_create(
        name="Period Jan 2026 P3",
        defaults={
            "fiscal_year": fy,
            "period_number": 1,
            "start_date": date(2026, 1, 1),
            "end_date": date(2026, 1, 31),
            "status": "open",
        }
    )

    # 3. إعداد أنواع الحسابات
    asset_type, _ = AccountType.objects.get_or_create(
        code="P3_ASSET",
        defaults={"name": "أصول P3", "category": "asset", "nature": "debit"}
    )
    equity_type, _ = AccountType.objects.get_or_create(
        code="P3_EQUITY",
        defaults={"name": "حقوق ملكية P3", "category": "equity", "nature": "credit"}
    )

    # 4. حساب وسيط الأرصدة الافتتاحية 31010
    equity_clearing, _ = ChartOfAccounts.objects.get_or_create(
        code="31010",
        defaults={"name": "الأرصدة الافتتاحية", "account_type": equity_type, "is_leaf": True, "is_active": True}
    )

    # 5. خزينة رئيسية
    cash_main = ChartOfAccounts.objects.create(
        code="111901",
        name="خزينة رئيسية P3",
        account_type=asset_type,
        opening_balance=Decimal("15000.00"),  # Static legacy model field
        is_leaf=True,
        is_active=True,
        is_cash_account=True,
        currency=egp_curr,
    )

    # قيد افتتاحي مرحل للخزينة الرئيسية بمبلغ 15,000 ج.م
    je_main = JournalEntry.objects.create(
        number="GL26-P3-01",
        date=date(2026, 1, 1),
        entry_type="opening",
        status="posted",
        reference="OPB-111901",
        description="افتتاحي خزينة P3",
        accounting_period=period,
        created_by=user,
        posted_by=user,
    )
    JournalEntryLine.objects.create(
        journal_entry=je_main,
        account=cash_main,
        debit=Decimal("15000.00"),
        credit=Decimal("0.00"),
        currency="EGP",
        exchange_rate=Decimal("1.000000"),
        description="افتتاحي خزينة P3",
    )
    JournalEntryLine.objects.create(
        journal_entry=je_main,
        account=equity_clearing,
        debit=Decimal("0.00"),
        credit=Decimal("15000.00"),
        currency="EGP",
        exchange_rate=Decimal("1.000000"),
        description="مقابل افتتاحي خزينة P3",
    )

    # 6. موظف وحساب عهدة
    from hr.models import Department, JobTitle
    dept, _ = Department.objects.get_or_create(code="FIN01_P3", defaults={"name_ar": "الإدارة المالية"})
    job, _ = JobTitle.objects.get_or_create(code="JOB-001_P3", defaults={"title_ar": "أمين خزينة", "department": dept})

    emp = Employee.objects.create(
        name="محمود حسن المحاسب",
        employee_number="EMP-P3-1001",
        national_id="29901011234567",
        birth_date=date(1990, 1, 1),
        gender="male",
        marital_status="single",
        department=dept,
        job_title=job,
        hire_date=date(2025, 1, 1),
        created_by=user,
        status="active",
    )
    custody_acc = ChartOfAccounts.objects.create(
        code="111902",
        name="عهدة محمود حسن P3",
        account_type=asset_type,
        opening_balance=Decimal("3000.00"),
        is_leaf=True,
        is_active=True,
        is_custody_account=True,
        assigned_employee=emp,
        currency=egp_curr,
    )
    je_custody = JournalEntry.objects.create(
        number="GL26-P3-02",
        date=date(2026, 1, 1),
        entry_type="opening",
        status="posted",
        reference="OPB-111902",
        description="افتتاحي عهدة",
        accounting_period=period,
        created_by=user,
        posted_by=user,
    )
    JournalEntryLine.objects.create(
        journal_entry=je_custody,
        account=custody_acc,
        debit=Decimal("3000.00"),
        credit=Decimal("0.00"),
        currency="EGP",
        exchange_rate=Decimal("1.000000"),
        description="افتتاحي عهدة",
    )
    JournalEntryLine.objects.create(
        journal_entry=je_custody,
        account=equity_clearing,
        debit=Decimal("0.00"),
        credit=Decimal("3000.00"),
        currency="EGP",
        exchange_rate=Decimal("1.000000"),
        description="مقابل عهدة",
    )

    return {
        "user": user,
        "egp_curr": egp_curr,
        "usd_curr": usd_curr,
        "period": period,
        "asset_type": asset_type,
        "equity_type": equity_type,
        "equity_clearing": equity_clearing,
        "cash_main": cash_main,
        "custody_acc": custody_acc,
        "emp": emp,
    }


@pytest.mark.django_db
def test_chart_of_accounts_list_no_doubling(client, phase3_setup):
    """
    1. اختبار شجرة الحسابات (chart_of_accounts_list):
    التأكد من أن الرصيد المعروض للحساب لا يتضاعف بجمع opening_balance فوق قيد الـ OPB
    """
    user = phase3_setup["user"]
    cash_main = phase3_setup["cash_main"]
    client.force_login(user)

    response = client.get(reverse("financial:chart_of_accounts_list"))
    assert response.status_code == 200

    # استخراج العقد من الـ context
    nodes_by_id = response.context["nodes_by_id"]
    node = nodes_by_id.get(cash_main.id)
    assert node is not None
    # الرصيد يجب أن يكون 15,000.00 ج.م تماماً (وليس 30,000.00 ج.م بالمضاعفة)
    assert node["balance"] == Decimal("15000.00")
    assert node["roll_up_balance"] == Decimal("15000.00")


@pytest.mark.django_db
def test_cash_and_bank_accounts_list_no_custody_doubling(client, phase3_setup):
    """
    2. اختبار قائمة الخزن والبنوك (cash_and_bank_accounts_list):
    التأكد من عدم مضاعفة رصيد العهدة وإجمالي العهد في الداشبورد
    """
    user = phase3_setup["user"]
    custody_acc = phase3_setup["custody_acc"]
    client.force_login(user)

    response = client.get(reverse("financial:cash_and_bank_accounts_list"))
    assert response.status_code == 200

    custody_list = response.context["custody_accounts"]
    ca_item = next((c for c in custody_list if c.id == custody_acc.id), None)
    assert ca_item is not None
    # رصيد العهدة يجب أن يكون 3,000.00 ج.م تماماً (وليس 6,000.00 ج.م)
    assert ca_item.current_balance == Decimal("3000.00")
    assert response.context["total_custody_balance"] == Decimal("3000.00")


@pytest.mark.django_db
def test_cash_account_delete_safe_setup_void(client, phase3_setup):
    """
    3. اختبار مسار الإلغاء الآمن للتأسيس (Safe Setup Void in cash_account_delete):
    خزينة أنشئت برصيد افتتاحي ولم تتم أي حركة تشغيلية عليها:
    - فحص الـ Precheck يُظهر can_void_setup=True
    - استدعاء action=void_setup يقوم بعكس القيد ذرياً وتعطيل الحساب بنجاح دون ImmutableLedgerError
    """
    user = phase3_setup["user"]
    cash_main = phase3_setup["cash_main"]
    client.force_login(user)

    # 1. طلب الفحص المسبق
    precheck_resp = client.get(
        reverse("financial:cash_account_delete", args=[cash_main.id]),
        {"precheck": "1"}
    )
    assert precheck_resp.status_code == 200
    data = precheck_resp.json()
    assert data["can_void_setup"] is True
    assert data["action_type"] == "void_setup"
    assert data["block_action"] is False

    # 2. تنفيذ الإلغاء الآمن للتأسيس الخاطئ
    void_resp = client.post(
        reverse("financial:cash_account_delete", args=[cash_main.id]),
        {"action": "void_setup"}
    )
    assert void_resp.status_code == 200
    void_data = void_resp.json()
    assert void_data["success"] is True
    assert void_data["action"] == "voided"

    cash_main.refresh_from_db()
    # الحساب تم تعطيله وأرشفته بنجاح
    assert cash_main.is_active is False
    # الرصيد أصبح 0.00 بالضبط بعد عكس القيد ذرياً
    assert cash_main.current_balance == Decimal("0.00")


@pytest.mark.django_db
def test_custody_count_gl_balance_server_side(client, phase3_setup):
    """
    4. اختبار تأمين محضر الجرد الفعلي (count_create_view):
    التأكد من أن السيرفر يتجاهل أي قيمة gl_balance محقونة من الفرونت إند ويحسبها من الدفتر
    """
    user = phase3_setup["user"]
    custody_acc = phase3_setup["custody_acc"]
    emp = phase3_setup["emp"]
    client.force_login(user)

    # محاولة حقن رصيد دفتري مغلوط 999999.00
    post_data = {
        "employee_id": emp.id,
        "custody_account_id": custody_acc.id,
        "gl_balance": "999999.00",
        "pending_vouchers_amount": "0.00",
        "denom_200": "15",  # 15 * 200 = 3000
    }

    resp = client.post(reverse("financial:custody_count_create"), post_data)
    assert resp.status_code == 302

    # التحقق من أن السيرفر احتسب الرصيد الفعلي من دفتر الأستاذ (3,000.00) وتجاهل القيمة المحقونة
    count_obj = PettyCashCount.objects.filter(custody_account=custody_acc).latest("id")
    assert count_obj.gl_balance == Decimal("3000.00")
    assert count_obj.actual_cash_amount == Decimal("3000.00")
    assert count_obj.variance_amount == Decimal("0.00")


@pytest.mark.django_db
def test_account_create_posts_balanced_opb(client, phase3_setup):
    """
    5. اختبار إنشاء الحسابات العامة (account_create):
    التأكد من توليد قيد افتتاحي متزن آلياً عند إدخال رصيد افتتاحي لمنع الحسابات اليتيمة
    """
    user = phase3_setup["user"]
    asset_type = phase3_setup["asset_type"]
    client.force_login(user)

    post_data = {
        "code": "111999",
        "name": "حساب افتتاحي جديد P3",
        "account_type": asset_type.id,
        "opening_balance": "7500.00",
        "opening_balance_date": "2026-01-01",
        "is_leaf": "on",
        "is_active": "on",
    }

    resp = client.post(reverse("financial:account_create"), post_data)
    assert resp.status_code == 302

    new_acc = ChartOfAccounts.objects.get(code="111999")
    # التحقق من وجود قيد افتتاحي مرحل في اليومية لهذا الحساب
    op_lines = JournalEntryLine.objects.filter(account=new_acc, journal_entry__status="posted")
    assert op_lines.exists()
    assert op_lines.first().debit == Decimal("7500.00")
    # رصيد الحساب الدفتري متطابق 100%
    assert new_acc.current_balance == Decimal("7500.00")


@pytest.mark.django_db
def test_account_edit_blocks_direct_opening_balance_mutation(client, phase3_setup):
    """
    6. اختبار تأمين تعديل الحسابات (account_edit):
    التأكد من أن تعديل الرصيد الافتتاحي على الموديل محظور للحسابات التي تمتلك قيوداً مرحلة
    """
    user = phase3_setup["user"]
    cash_main = phase3_setup["cash_main"]
    client.force_login(user)

    # محاولة تعديل الرصيد الافتتاحي مباشرة من 15,000 إلى 50,000
    post_data = {
        "name": cash_main.name,
        "code": cash_main.code,
        "account_type": cash_main.account_type.id,
        "opening_balance": "50000.00",
        "is_active": "on",
    }

    resp = client.post(reverse("financial:account_edit", kwargs={"pk": cash_main.pk}), post_data)
    assert resp.status_code == 302

    cash_main.refresh_from_db()
    # تم حظر التعديل المباشر وظل الرصيد الافتتاحي 15,000.00 ورصيد الدفتر 15,000.00
    assert cash_main.opening_balance == Decimal("15000.00")
    assert cash_main.current_balance == Decimal("15000.00")
