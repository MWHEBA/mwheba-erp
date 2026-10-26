# -*- coding: utf-8 -*-
"""
Tests for Custody UI-Backend Capability Integration & Permissions
-----------------------------------------------------------------
Validates that all gaps between frontend templates, views, and services are resolved:
1. Advance create view persists work_location.
2. Settlement create view supports "save_draft" -> DRAFT and "post_now" -> SUBMITTED.
3. Settlement create view supports direct permanent custody settlement via custody_account_id.
4. Settlement create view supports multi-currency lines with specific exchange rates.
5. Settlement create view connects shortage_amount and variance_routing.
6. Settlement line review action enables approving, adjusting, or rejecting individual lines.
7. Settlement reverse action enforces can_reverse_settlement and passes reason and reversal_date.
8. Count adjust action processes physical count variance settlement.
9. Count create view provides cached_gl_balance for custody accounts.
"""

from decimal import Decimal as D
from datetime import date
import pytest

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import RequestFactory
from django.contrib.messages.storage.fallback import FallbackStorage
from django.utils import timezone

from financial.tests.test_phase6_custody_acceptance import p6_setup
from financial.models.custody import (
    EmployeeCustodyAdvance,
    CustodyAdvanceStatus,
    SettlementLineType,
    PettyCashSettlement,
    SettlementStatus,
    PettyCashSettlementLine,
    SettlementLineStatus,
    VarianceRouting,
    PettyCashCount,
)
from financial.models.currency import Currency
from financial.models.cost_center import CostCenter
from hr.models.work_location import WorkLocation
from django.core.files.uploadedfile import SimpleUploadedFile
from financial.services.custody_service import CustodyManagementService as S
from financial.views.custody_views import (
    advance_create_view,
    settlement_create_view,
    settlement_detail_view,
    settlement_edit_view,
    settlement_submit_action,
    settlement_line_review_action,
    settlement_reverse_action,
    count_create_view,
    count_adjust_action,
)


@pytest.mark.django_db
def test_advance_create_saves_work_location(p6_setup):
    """التحقق من أن حقل موقع العمل يُحفظ بشكل صحيح عند إنشاء طلب العهدة من الشاشة"""
    s = p6_setup
    loc = WorkLocation.objects.create(name_ar="فرع القاهرة", latitude=30.0, longitude=31.0)

    rf = RequestFactory()
    data = {
        "employee_id": str(s["employee1"].id),
        "source_treasury_id": str(s["treasury_acc"].id),
        "amount": "3000.00",
        "currency_id": str(s["egp"].id),
        "purpose": "مصاريف تشغيل فرع القاهرة",
        "due_date": "2026-04-15",
        "work_location_id": str(loc.id),
        "notes": "عهدة مؤقتة معتمدة",
    }
    req = rf.post("/financial/custody/advances/create/", data=data)
    req.user = s["user"]
    setattr(req, "session", {})
    setattr(req, "_messages", FallbackStorage(req))

    resp = advance_create_view(req)
    assert resp.status_code == 302

    adv = EmployeeCustodyAdvance.objects.filter(employee=s["employee1"], amount=D("3000.00")).first()
    assert adv is not None
    assert adv.work_location == loc


@pytest.mark.django_db
def test_settlement_create_save_draft_status(p6_setup):
    """التحقق من أن زر 'حفظ مسودة' يحفظ سند التسوية بحالة DRAFT وليس SUBMITTED"""
    s = p6_setup

    adv = EmployeeCustodyAdvance.objects.create(
        advance_number="ADV-DRAFT-01",
        employee=s["employee1"],
        source_treasury=s["treasury_acc"],
        amount=D("1000.00"),
        current_balance=D("1000.00"),
        currency=s["egp"],
        status=CustodyAdvanceStatus.ACTIVE,
        due_date=date(2026, 4, 15),
    )

    rf = RequestFactory()
    data = {
        "action": "save_draft",
        "advance_id": str(adv.id),
        "settlement_date": "2026-03-25",
        "line_type[]": [SettlementLineType.DIRECT_EXPENSE],
        "line_expense_acc[]": [str(s["expense_acc"].id)],
        "line_amount[]": ["400.00"],
        "line_currency_id[]": [str(s["egp"].id)],
        "line_exchange_rate[]": ["1.000000"],
        "line_tax_rate[]": ["0"],
        "line_wht_rate[]": ["0"],
        "line_discount_amount[]": ["0"],
        "line_desc[]": ["مسودة شراء مستلزمات"],
    }
    req = rf.post("/financial/custody/settlements/create/", data=data)
    req.user = s["user"]
    setattr(req, "session", {})
    setattr(req, "_messages", FallbackStorage(req))

    resp = settlement_create_view(req)
    assert resp.status_code == 302

    sett = PettyCashSettlement.objects.filter(custody_advance=adv).first()
    assert sett is not None
    assert sett.status == SettlementStatus.DRAFT


@pytest.mark.django_db
def test_settlement_create_direct_permanent_custody(p6_setup):
    """التحقق من ربط تسوية صندوق عهدة مستديم مباشرة عبر custody_account_id بدون سلفة مؤقتة"""
    s = p6_setup

    rf = RequestFactory()
    data = {
        "action": "save_draft",
        "employee_id": str(s["employee1"].id),
        "custody_account_id": str(s["custody_perm_acc"].id),
        "settlement_date": "2026-03-25",
        "line_type[]": [SettlementLineType.DIRECT_EXPENSE],
        "line_expense_acc[]": [str(s["expense_acc"].id)],
        "line_amount[]": ["250.00"],
        "line_currency_id[]": [str(s["egp"].id)],
        "line_exchange_rate[]": ["1.000000"],
        "line_tax_rate[]": ["0"],
        "line_wht_rate[]": ["0"],
        "line_discount_amount[]": ["0"],
        "line_desc[]": ["مصروفات نثرية للصندوق"],
    }
    req = rf.post("/financial/custody/settlements/create/", data=data)
    req.user = s["user"]
    setattr(req, "session", {})
    setattr(req, "_messages", FallbackStorage(req))

    resp = settlement_create_view(req)
    assert resp.status_code == 302

    sett = PettyCashSettlement.objects.filter(employee=s["employee1"], custody_account=s["custody_perm_acc"]).first()
    assert sett is not None
    assert sett.custody_advance is None
    assert sett.custody_account == s["custody_perm_acc"]


@pytest.mark.django_db
def test_settlement_create_multi_currency_lines_and_shortage(p6_setup):
    """التحقق من حفظ عملة وسعر صرف كل بند تسوية وحفظ مبلغ العجز وتوجيه الفارق"""
    s = p6_setup

    usd, _ = Currency.objects.get_or_create(code="USD", defaults={"name": "US Dollar", "exchange_rate": D("50.00")})
    adv = EmployeeCustodyAdvance.objects.create(
        advance_number="ADV-USD-SETT-01",
        employee=s["employee1"],
        source_treasury=s["treasury_acc"],
        amount=D("10000.00"),
        current_balance=D("10000.00"),
        currency=s["egp"],
        status=CustodyAdvanceStatus.ACTIVE,
        due_date=date(2026, 4, 15),
    )

    rf = RequestFactory()
    data = {
        "action": "save_draft",
        "advance_id": str(adv.id),
        "settlement_date": "2026-03-25",
        "shortage_amount": "150.00",
        "variance_routing": VarianceRouting.HR_DEDUCTION,
        "line_type[]": [SettlementLineType.DIRECT_EXPENSE],
        "line_expense_acc[]": [str(s["expense_acc"].id)],
        "line_amount[]": ["100.00"],
        "line_currency_id[]": [str(usd.id)],
        "line_exchange_rate[]": ["50.000000"],
        "line_tax_rate[]": ["0"],
        "line_wht_rate[]": ["0"],
        "line_discount_amount[]": ["0"],
        "line_desc[]": ["شراء برمجيات بالدولار"],
    }
    req = rf.post("/financial/custody/settlements/create/", data=data)
    req.user = s["user"]
    setattr(req, "session", {})
    setattr(req, "_messages", FallbackStorage(req))

    resp = settlement_create_view(req)
    assert resp.status_code == 302

    sett = PettyCashSettlement.objects.filter(custody_advance=adv).first()
    assert sett is not None
    assert sett.shortage_amount == D("150.00")
    assert sett.variance_routing == VarianceRouting.HR_DEDUCTION

    line = sett.lines.first()
    assert line is not None
    assert line.currency == usd
    assert line.exchange_rate == D("50.000000")
    assert line.amount == D("100.00")


@pytest.mark.django_db
def test_settlement_line_review_adjust_and_reject(p6_setup):
    """التحقق من شاشة وخدمة مراجعة البنود: تعديل المبلغ المعتمد ورفض بند منفرد"""
    s = p6_setup

    adv = EmployeeCustodyAdvance.objects.create(
        advance_number="ADV-REV-01",
        employee=s["employee1"],
        source_treasury=s["treasury_acc"],
        amount=D("1000.00"),
        current_balance=D("1000.00"),
        currency=s["egp"],
        status=CustodyAdvanceStatus.ACTIVE,
        due_date=date(2026, 4, 15),
    )
    sett = PettyCashSettlement.objects.create(
        settlement_number="SETT-REV-01",
        employee=s["employee1"],
        custody_advance=adv,
        currency=s["egp"],
        settlement_date=date(2026, 3, 20),
        status=SettlementStatus.SUBMITTED,
        total_expenses=D("500.00"),
        total_settled_amount=D("500.00"),
    )
    ln1 = PettyCashSettlementLine.objects.create(
        settlement=sett,
        line_number=1,
        line_type=SettlementLineType.DIRECT_EXPENSE,
        expense_account=s["expense_acc"],
        currency=s["egp"],
        amount=D("300.00"),
        status=SettlementLineStatus.APPROVED,
        approved_amount=D("300.00"),
    )
    ln2 = PettyCashSettlementLine.objects.create(
        settlement=sett,
        line_number=2,
        line_type=SettlementLineType.DIRECT_EXPENSE,
        expense_account=s["expense_acc"],
        currency=s["egp"],
        amount=D("200.00"),
        status=SettlementLineStatus.APPROVED,
        approved_amount=D("200.00"),
    )

    rf = RequestFactory()

    # 1. تعديل المبلغ المعتمد للبند 1 من 300 إلى 250
    req1 = rf.post(
        f"/financial/custody/settlements/{sett.id}/lines/{ln1.id}/review/",
        data={"action": "adjust", "approved_amount": "250.00"},
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )
    req1.user = s["user"]
    resp1 = settlement_line_review_action(req1, pk=sett.id, line_id=ln1.id)
    assert resp1.status_code == 200

    ln1.refresh_from_db()
    assert ln1.status == SettlementLineStatus.ADJUSTED
    assert ln1.approved_amount == D("250.00")

    # 2. رفض البند 2 مع بيان السبب
    req2 = rf.post(
        f"/financial/custody/settlements/{sett.id}/lines/{ln2.id}/review/",
        data={"action": "reject", "rejection_reason": "فاتورة غير مقبولة ضريبياً"},
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )
    req2.user = s["user"]
    resp2 = settlement_line_review_action(req2, pk=sett.id, line_id=ln2.id)
    assert resp2.status_code == 200

    ln2.refresh_from_db()
    assert ln2.status == SettlementLineStatus.REJECTED
    assert ln2.approved_amount == D("0.00")
    assert ln2.rejection_reason == "فاتورة غير مقبولة ضريبياً"

    # التحقق من إعادة احتساب إجمالي التسوية المعتمدة
    sett.refresh_from_db()
    assert sett.total_settled_amount == D("250.00")


@pytest.mark.django_db
def test_settlement_reverse_action_reason_date_and_permission(p6_setup):
    """التحقق من فحص صلاحية can_reverse_settlement وتمرير السبب وتاريخ العكس"""
    s = p6_setup

    sett = PettyCashSettlement.objects.create(
        settlement_number="SETT-TO-REV-01",
        employee=s["employee1"],
        settlement_date=date(2026, 3, 20),
        status=SettlementStatus.SUBMITTED,
        total_expenses=D("100.00"),
        total_settled_amount=D("100.00"),
    )
    PettyCashSettlementLine.objects.create(
        settlement=sett,
        line_number=1,
        line_type=SettlementLineType.DIRECT_EXPENSE,
        expense_account=s["expense_acc"],
        currency=s["egp"],
        amount=D("100.00"),
        status=SettlementLineStatus.APPROVED,
        approved_amount=D("100.00"),
    )
    # ترحيل التسوية أولاً
    entry = S.post_settlement(sett, s["user"])
    assert entry.status == "posted"

    rf = RequestFactory()

    # إنشاء مستخدم بدون صلاحية can_reverse_settlement
    User = get_user_model()
    unauth_user = User.objects.create_user(username="normal_user", password="pwd")
    req_unauth = rf.post(
        f"/financial/custody/settlements/{sett.id}/reverse/",
        data={"reason": "خطأ إدخال", "reversal_date": "2026-03-25"},
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )
    req_unauth.user = unauth_user
    resp_unauth = settlement_reverse_action(req_unauth, pk=sett.id)
    assert resp_unauth.status_code == 403

    # إضافة الصلاحية للمستخدم
    perm = Permission.objects.get(codename="can_reverse_settlement")
    unauth_user.user_permissions.add(perm)
    unauth_user = User.objects.get(pk=unauth_user.pk)

    req_auth = rf.post(
        f"/financial/custody/settlements/{sett.id}/reverse/",
        data={"reason": "إلغاء لخطأ في التوجيه", "reversal_date": "2026-03-26"},
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )
    req_auth.user = unauth_user
    resp_auth = settlement_reverse_action(req_auth, pk=sett.id)
    assert resp_auth.status_code == 200

    sett.refresh_from_db()
    assert sett.status == SettlementStatus.REVERSED
    assert sett.reversal_entry is not None
    assert sett.reversal_entry.date == date(2026, 3, 26)


@pytest.mark.django_db
def test_count_create_context_cached_balance_and_adjust_action(p6_setup):
    """التحقق من احتساب الرصيد الدفتري في context الجرد وتشغيل زر وإجراء تسوية فروق الجرد"""
    s = p6_setup

    rf = RequestFactory()
    req = rf.get("/financial/custody/counts/create/")
    req.user = s["user"]
    setattr(req, "session", {})
    setattr(req, "_messages", FallbackStorage(req))

    resp = count_create_view(req)
    assert resp.status_code == 200
    # التحقق من أن القالب يحتوي على الرصيد الدفتري للقراءة فقط وربطه بالحسابات
    assert b'readonly' in resp.content
    assert b'data-balance=' in resp.content

    # إنشاء محضر جرد به عجز وتسويته عبر count_adjust_action
    count_obj = PettyCashCount.objects.create(
        count_number="CNT-TEST-ADJ-01",
        employee=s["employee1"],
        custody_account=s["custody_perm_acc"],
        count_date=timezone.now(),
        auditor=s["user"],
        gl_balance=D("1000.00"),
        actual_cash_amount=D("800.00"),
        pending_vouchers_amount=D("0.00"),
        variance_amount=D("-200.00"),
        variance_type="shortage",
    )

    req_adj = rf.post(
        f"/financial/custody/counts/{count_obj.id}/adjust/",
        data={"adjustment_type": "hr_deduction"},
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )
    req_adj.user = s["user"]
    resp_adj = count_adjust_action(req_adj, pk=count_obj.id)
    assert resp_adj.status_code == 200

    count_obj.refresh_from_db()
    assert count_obj.status == "adjusted"


@pytest.mark.django_db
def test_settlement_attachment_mapping_to_correct_line_uid(p6_setup):
    """[P1] التحقق من أن المرفقات تُربط بالبند الصحيح بناءً على معرّف السطر وليس بترتيب الملفات في المصفوفة"""
    s = p6_setup

    adv = EmployeeCustodyAdvance.objects.create(
        advance_number="ADV-FILE-MAP-01",
        employee=s["employee1"],
        source_treasury=s["treasury_acc"],
        amount=D("2000.00"),
        current_balance=D("2000.00"),
        currency=s["egp"],
        status=CustodyAdvanceStatus.ACTIVE,
        due_date=date(2026, 4, 15),
    )

    test_pdf = SimpleUploadedFile("invoice_line2.pdf", b"%PDF-1.4 test invoice content", content_type="application/pdf")

    rf = RequestFactory()
    data = {
        "advance_id": str(adv.id),
        "settlement_date": "2026-03-25",
        "action": "save_draft",
        "row_uid[]": ["r0", "r1"],
        "line_type[]": [SettlementLineType.DIRECT_EXPENSE, SettlementLineType.DIRECT_EXPENSE],
        "line_expense_acc[]": [str(s["expense_acc"].id), str(s["expense_acc"].id)],
        "line_amount[]": ["100.00", "200.00"],
        "line_currency_id[]": [str(s["egp"].id), str(s["egp"].id)],
        "line_exchange_rate[]": ["1.0", "1.0"],
        "receipt_file_r1": test_pdf,  # الملف مرفق بالسطر الثاني فقط (r1) بينما السطر الأول (r0) بدون ملف
    }
    req = rf.post("/financial/custody/settlements/create/", data=data)
    req.user = s["user"]
    setattr(req, "session", {})
    setattr(req, "_messages", FallbackStorage(req))

    resp = settlement_create_view(req)
    assert resp.status_code == 302

    sett = PettyCashSettlement.objects.filter(custody_advance=adv).first()
    assert sett is not None

    lines = list(sett.lines.order_by("line_number"))
    assert len(lines) == 2
    # البند الأول لا يحتوي على مرفق
    assert not bool(lines[0].receipt_file)
    # البند الثاني يحتوي على المرفق الصحيح
    assert bool(lines[1].receipt_file)
    assert "invoice_line2" in lines[1].receipt_file.name


@pytest.mark.django_db
def test_settlement_draft_submission_lifecycle(p6_setup):
    """[P2] التحقق من دورة حياة المسودة وإمكانية إرسالها للاعتماد بعد الحفظ بنجاح"""
    s = p6_setup

    adv = EmployeeCustodyAdvance.objects.create(
        advance_number="ADV-DRAFT-SUB-01",
        employee=s["employee1"],
        source_treasury=s["treasury_acc"],
        amount=D("1000.00"),
        current_balance=D("1000.00"),
        currency=s["egp"],
        status=CustodyAdvanceStatus.ACTIVE,
        due_date=date(2026, 4, 15),
    )

    sett = PettyCashSettlement.objects.create(
        settlement_number="SETT-DRAFT-01",
        custody_advance=adv,
        custody_account=adv.custody_account,
        employee=s["employee1"],
        currency=s["egp"],
        settlement_date=date(2026, 3, 25),
        status=SettlementStatus.DRAFT,
    )

    rf = RequestFactory()

    # محاولة إرسال مسودة فارغة يجب أن تفشل
    req_empty = rf.post(f"/financial/custody/settlements/{sett.id}/submit/", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
    req_empty.user = s["user"]
    setattr(req_empty, "session", {})
    setattr(req_empty, "_messages", FallbackStorage(req_empty))
    resp_empty = settlement_submit_action(req_empty, pk=sett.id)
    assert resp_empty.status_code == 400

    # إضافة بند صحيح
    PettyCashSettlementLine.objects.create(
        settlement=sett,
        line_number=1,
        line_type=SettlementLineType.DIRECT_EXPENSE,
        expense_account=s["expense_acc"],
        amount=D("500.00"),
        approved_amount=D("500.00"),
        currency=s["egp"],
        exchange_rate=D("1.0"),
        status=SettlementLineStatus.APPROVED,
    )

    # إرسال المسودة للاعتماد
    req_sub = rf.post(f"/financial/custody/settlements/{sett.id}/submit/", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
    req_sub.user = s["user"]
    setattr(req_sub, "session", {})
    setattr(req_sub, "_messages", FallbackStorage(req_sub))
    resp_sub = settlement_submit_action(req_sub, pk=sett.id)
    assert resp_sub.status_code == 200

    sett.refresh_from_db()
    assert sett.status == SettlementStatus.SUBMITTED
    assert sett.submitted_by == s["user"]


@pytest.mark.django_db
def test_settlement_multi_currency_totals_calculation(p6_setup):
    """[P3] التحقق من احتساب إجمالي المصروفات المحولة بعملة التسوية (100 جنيه + 100 دولار بسعر 50 = 5100 جنيه)"""
    s = p6_setup

    adv = EmployeeCustodyAdvance.objects.create(
        advance_number="ADV-MULTI-CURR-01",
        employee=s["employee1"],
        source_treasury=s["treasury_acc"],
        amount=D("6000.00"),
        current_balance=D("6000.00"),
        currency=s["egp"],
        status=CustodyAdvanceStatus.ACTIVE,
        due_date=date(2026, 4, 15),
    )

    rf = RequestFactory()
    data = {
        "advance_id": str(adv.id),
        "settlement_date": "2026-03-25",
        "action": "save_draft",
        "row_uid[]": ["r0", "r1"],
        "line_type[]": [SettlementLineType.DIRECT_EXPENSE, SettlementLineType.DIRECT_EXPENSE],
        "line_expense_acc[]": [str(s["expense_acc"].id), str(s["expense_acc"].id)],
        "line_amount[]": ["100.00", "100.00"],
        "line_currency_id[]": [str(s["egp"].id), str(s["usd"].id)],
        "line_exchange_rate[]": ["1.0", "50.0"],
    }
    req = rf.post("/financial/custody/settlements/create/", data=data)
    req.user = s["user"]
    setattr(req, "session", {})
    setattr(req, "_messages", FallbackStorage(req))

    resp = settlement_create_view(req)
    assert resp.status_code == 302

    sett = PettyCashSettlement.objects.filter(custody_advance=adv).first()
    assert sett is not None
    # 100 EGP + 100 USD * 50 = 5,100 EGP
    assert sett.total_expenses == D("5100.00")
    assert sett.total_settled_amount == D("5100.00")


@pytest.mark.django_db
def test_count_create_foreign_currency_cached_gl_balance(p6_setup):
    """[P4] التحقق من أن معاينة الجرد للحساب الأجنبي تعرض الرصيد بالعملة الأجنبية وليس ما يعادلها محلياً"""
    s = p6_setup
    from financial.models import ChartOfAccounts, AccountType, JournalEntry, JournalEntryLine

    usd_custody = ChartOfAccounts.objects.create(
        code="11040099",
        name="عهدة أجنبية دولار",
        account_type=s["custody_perm_acc"].account_type,
        currency=s["usd"],
        is_custody_account=True,
        is_active=True,
    )

    # إنشاء قيد إيداع 1000 دولار بسعر 50 (50,000 جنيه محلي و 1,000 دولار أجنبي)
    je = JournalEntry.objects.create(
        date=timezone.localdate(),
        description="تمويل عهدة دولار",
        status="posted",
        created_by=s["user"],
    )
    JournalEntryLine.objects.create(
        journal_entry=je,
        account=usd_custody,
        debit=D("50000.00"),
        credit=D("0.00"),
        currency="USD",
        exchange_rate=D("50.0"),
        foreign_debit=D("1000.00"),
        foreign_credit=D("0.00"),
    )
    JournalEntryLine.objects.create(
        journal_entry=je,
        account=s["treasury_acc"],
        debit=D("0.00"),
        credit=D("50000.00"),
        currency="EGP",
        exchange_rate=D("1.0"),
    )

    rf = RequestFactory()
    req = rf.get("/financial/custody/counts/create/")
    req.user = s["user"]
    setattr(req, "session", {})
    setattr(req, "_messages", FallbackStorage(req))

    resp = count_create_view(req)
    assert resp.status_code == 200

    html = resp.content.decode("utf-8")
    # الرصيد الدفتري المعروض بالنموذج يجب أن يكون 1000.00 دولار (وليس 50000.00 جنيه)
    assert f'value="{usd_custody.id}" data-balance="1000.00" data-currency="USD"' in html
    assert f'value="{usd_custody.id}" data-balance="50000.00"' not in html


@pytest.mark.django_db
def test_settlement_foreign_custody_totals_and_currency_labels(p6_setup):
    """
    [P2] التحقق من اتساق إجماليات وتسمية العملة لعهدة أجنبية:
    - عهدة بالدولار، ومصروف بـ 5,000 جنيه بسعر 50:
      * الباك إند يحسبه 100 دولار (5000 / 50).
      * صفحة التفاصيل تعرض العملة كـ USD بدلاً من الجنيه الثابت.
      * خيارات العهد في شاشة التسوية تحمل خاصية data-currency="USD".
    """
    s = p6_setup

    adv_usd = EmployeeCustodyAdvance.objects.create(
        advance_number="ADV-USD-SETT-TEST",
        employee=s["employee1"],
        source_treasury=s["treasury_acc"],
        amount=D("1000.00"),
        current_balance=D("1000.00"),
        currency=s["usd"],
        status=CustodyAdvanceStatus.ACTIVE,
        due_date=date(2026, 4, 15),
    )

    rf = RequestFactory()
    data = {
        "advance_id": str(adv_usd.id),
        "settlement_date": "2026-03-25",
        "action": "save_draft",
        "row_uid[]": ["r0"],
        "line_type[]": [SettlementLineType.DIRECT_EXPENSE],
        "line_expense_acc[]": [str(s["expense_acc"].id)],
        "line_amount[]": ["5000.00"],
        "line_currency_id[]": [str(s["egp"].id)],
        "line_exchange_rate[]": ["50.000000"],
        "line_desc[]": ["مصروف محلي بالجنيه محسوب على عهدة دولار"],
    }
    req_create = rf.post("/financial/custody/settlements/create/", data=data)
    req_create.user = s["user"]
    setattr(req_create, "session", {})
    setattr(req_create, "_messages", FallbackStorage(req_create))

    resp_create = settlement_create_view(req_create)
    assert resp_create.status_code == 302

    sett = PettyCashSettlement.objects.filter(custody_advance=adv_usd).first()
    assert sett is not None
    assert sett.currency == s["usd"]
    # 5,000 EGP / 50 = 100 USD
    assert sett.total_expenses == D("100.00")
    assert sett.total_settled_amount == D("100.00")

    # فحص صفحة التفاصيل لعرض رمز العملة الصحيح USD
    req_det = rf.get(f"/financial/custody/settlements/{sett.id}/")
    req_det.user = s["user"]
    setattr(req_det, "session", {})
    setattr(req_det, "_messages", FallbackStorage(req_det))
    resp_det = settlement_detail_view(req_det, pk=sett.id)
    assert resp_det.status_code == 200
    html_det = resp_det.content.decode("utf-8")
    assert "USD" in html_det
    assert "100" in html_det

    # فحص وجود خاصية data-currency في خيارات شاشة إنشاء/تعديل التسوية
    req_form = rf.get("/financial/custody/settlements/create/")
    req_form.user = s["user"]
    setattr(req_form, "session", {})
    setattr(req_form, "_messages", FallbackStorage(req_form))
    resp_form = settlement_create_view(req_form)
    assert resp_form.status_code == 200
    html_form = resp_form.content.decode("utf-8")
    assert f'value="{adv_usd.id}"' in html_form
    assert 'data-currency="USD"' in html_form


@pytest.mark.django_db
def test_settlement_edit_view_updates_draft_lines_and_preserves_attachments(p6_setup):
    """
    [P2] التحقق من مسار تعديل واستكمال المسودة:
    - إمكانية تعديل أصل المبلغ، الحساب، العملة، الوصف، وإضافة وحذف بنود بعد الحفظ.
    - الحفاظ على المرفق القديم للبند المعدل إذا لم يُرفع ملف جديد بديل.
    - إضافة مرفق جديد للبند الإضافي.
    - إمكانية إرسال المسودة للاعتماد مباشرة من شاشة التعديل.
    - منع تعديل السندات المعتمدة أو المرحلة.
    """
    s = p6_setup

    adv = EmployeeCustodyAdvance.objects.create(
        advance_number="ADV-EDIT-DRAFT-01",
        employee=s["employee1"],
        source_treasury=s["treasury_acc"],
        amount=D("2000.00"),
        current_balance=D("2000.00"),
        currency=s["egp"],
        status=CustodyAdvanceStatus.ACTIVE,
        due_date=date(2026, 4, 15),
    )

    sett = PettyCashSettlement.objects.create(
        settlement_number="SETT-DRAFT-EDIT-01",
        custody_advance=adv,
        custody_account=adv.custody_account,
        employee=s["employee1"],
        currency=s["egp"],
        settlement_date=date(2026, 3, 25),
        status=SettlementStatus.DRAFT,
    )

    initial_file = SimpleUploadedFile("initial_line1.pdf", b"%PDF-1.4 initial attachment", content_type="application/pdf")
    line1 = PettyCashSettlementLine.objects.create(
        settlement=sett,
        line_number=1,
        line_type=SettlementLineType.DIRECT_EXPENSE,
        expense_account=s["expense_acc"],
        amount=D("100.00"),
        approved_amount=D("100.00"),
        currency=s["egp"],
        exchange_rate=D("1.0"),
        receipt_file=initial_file,
        description="بند أولي بالمسودة",
    )
    sett.total_expenses = D("100.00")
    sett.total_settled_amount = D("100.00")
    sett.save()

    rf = RequestFactory()

    # 1. فحص طلب GET لشاشة التعديل:
    req_get = rf.get(f"/financial/custody/settlements/{sett.id}/edit/")
    req_get.user = s["user"]
    setattr(req_get, "session", {})
    setattr(req_get, "_messages", FallbackStorage(req_get))
    resp_get = settlement_edit_view(req_get, pk=sett.id)
    assert resp_get.status_code == 200
    html_get = resp_get.content.decode("utf-8")
    assert "تعديل واستكمال مسودة سند التسوية" in html_get
    assert "بند أولي بالمسودة" in html_get
    assert f'value="{line1.id}"' in html_get

    # 2. فحص طلب POST للتعديل:
    # تعديل البند 1 (تغيير المبلغ إلى 150 والوصف إلى محدث، بدون رفع ملف جديد للحفاظ على initial_line1.pdf)
    # وإضافة بند 2 بمبلغ 250 مع رفع ملف جديد new_line2.pdf
    new_file = SimpleUploadedFile("new_line2.pdf", b"%PDF-1.4 line2 attachment", content_type="application/pdf")
    post_data = {
        "action": "save_draft",
        "settlement_date": "2026-03-26",
        "cash_returned_to_treasury": "50.00",
        "shortage_amount": "20.00",
        "variance_routing": VarianceRouting.HR_DEDUCTION,
        "notes": "مسودة معدلة",
        "row_uid[]": ["r0", "r1"],
        "existing_line_id[]": [str(line1.id), ""],
        "line_type[]": [SettlementLineType.DIRECT_EXPENSE, SettlementLineType.DIRECT_EXPENSE],
        "line_expense_acc[]": [str(s["expense_acc"].id), str(s["expense_acc"].id)],
        "line_amount[]": ["150.00", "250.00"],
        "line_currency_id[]": [str(s["egp"].id), str(s["egp"].id)],
        "line_exchange_rate[]": ["1.0", "1.0"],
        "line_desc[]": ["بند معدل للمسودة", "بند مضاف جديد"],
        "receipt_file_r1": new_file,
    }
    req_post = rf.post(f"/financial/custody/settlements/{sett.id}/edit/", data=post_data)
    req_post.user = s["user"]
    setattr(req_post, "session", {})
    setattr(req_post, "_messages", FallbackStorage(req_post))
    resp_post = settlement_edit_view(req_post, pk=sett.id)
    assert resp_post.status_code == 302

    sett.refresh_from_db()
    assert sett.status == SettlementStatus.DRAFT
    assert sett.settlement_date == date(2026, 3, 26)
    assert sett.cash_returned_to_treasury == D("50.00")
    assert sett.shortage_amount == D("20.00")
    assert sett.total_expenses == D("400.00")

    lines = list(sett.lines.order_by("line_number"))
    assert len(lines) == 2
    # البند الأول احتفظ بمرفقه القديم
    assert lines[0].amount == D("150.00")
    assert lines[0].description == "بند معدل للمسودة"
    assert bool(lines[0].receipt_file)
    assert "initial_line1" in lines[0].receipt_file.name

    # البند الثاني أخذ المرفق الجديد
    assert lines[1].amount == D("250.00")
    assert lines[1].description == "بند مضاف جديد"
    assert bool(lines[1].receipt_file)
    assert "new_line2" in lines[1].receipt_file.name

    # 3. إرسال المسودة للاعتماد من شاشة التعديل
    post_data_submit = post_data.copy()
    post_data_submit["action"] = "submit"
    req_submit = rf.post(f"/financial/custody/settlements/{sett.id}/edit/", data=post_data_submit)
    req_submit.user = s["user"]
    setattr(req_submit, "session", {})
    setattr(req_submit, "_messages", FallbackStorage(req_submit))
    resp_submit = settlement_edit_view(req_submit, pk=sett.id)
    assert resp_submit.status_code == 302

    sett.refresh_from_db()
    assert sett.status == SettlementStatus.SUBMITTED

    # 4. محاولة تعديل السند بعد إرساله (حيث لم يعد مسودة) يجب أن ترفض
    req_blocked = rf.get(f"/financial/custody/settlements/{sett.id}/edit/")
    req_blocked.user = s["user"]
    setattr(req_blocked, "session", {})
    setattr(req_blocked, "_messages", FallbackStorage(req_blocked))
    resp_blocked = settlement_edit_view(req_blocked, pk=sett.id)
    assert resp_blocked.status_code == 302
    assert resp_blocked.url == f"/financial/custody/settlements/{sett.id}/"


