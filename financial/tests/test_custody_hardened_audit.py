# -*- coding: utf-8 -*-
"""
Hardened Custody Audit & Resilience Test Suite
---------------------------------------------
Validates that all 20 audit vulnerabilities identified in the independent review
are definitively resolved and guarded against regression:
1. FX local currency conversion (EGP functional vs foreign amount).
2. Stale settlement concurrent posting and ledger divergence protection.
3. Idempotent permanent custody replenishment preventing duplicate cash outflow.
4. Advance create view returns 200 with HTML form on GET.
5. Legitimate multiple top-ups of active custody advances succeed without collision.
6. Unauthorized custody transfer blocked for users without proper permissions.
7. Posted settlement immutability at ORM level (update, delete, direct save).
8. Rejection of settlements with REJECTED status or unapproved/pending lines.
9. Employee termination blocked when active custody or unresolved assets exist.
10. Supplier invoice lines route strictly to supplier payable account, not expense.
11. Invoice overpayment rejected when exceeding balance due.
12. Settlement reversal correctly restores supplier subledger open amount.
13. Cross-employee settlement posting strictly prohibited.
14. Shortage loss routing correctly debits loss account (54900).
15. Assets under investigation block HR custody clearance.
16. Physical count adjustment protected against duplicate posting.
17. Treasury ACL permissions strictly enforced on custody disbursement.
18. Account unassignment closes active custody assignment history.
19. Custody transfers require valid active source advance.
20. Physical counts reject negative denomination counts.
"""

from decimal import Decimal as D
from datetime import date
import pytest

from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import RequestFactory
from django.contrib.messages.storage.fallback import FallbackStorage

from financial.tests.test_phase6_custody_acceptance import p6_setup
from financial.models.custody import (
    EmployeeCustodyAdvance,
    CustodyAdvanceStatus,
    SettlementLineType,
    PettyCashSettlement,
    SettlementStatus,
    PettyCashSettlementLine,
    SettlementLineStatus,
    CustodyTransfer,
    PettyCashCount,
)
from financial.services.custody_service import CustodyManagementService as S
from financial.views.custody_views import (
    advance_create_view,
    transfer_create_view,
    advance_disburse_action,
)
from financial.views.account_views import assign_custody_account_employee
from financial.models.custody_history import CustodyAssignmentHistory
from hr.models.employee_asset_custody import EmployeeAssetCustody
from hr.services.employee_service import EmployeeService
from financial.services.treasury_security_service import TreasurySecurityService
from financial.models import ChartOfAccounts, JournalEntry, JournalEntryLine
from purchase.models.purchase import Purchase
from supplier.models import SupplierTransaction

pytestmark = pytest.mark.django_db


def create_advance(s, number="AUD-ADV", currency=None, amount="1000", exchange_rate=None):
    a = EmployeeCustodyAdvance.objects.create(
        advance_number=number,
        employee=s["employee1"],
        user=s["user"],
        source_treasury=s["treasury_acc"],
        amount=D(amount),
        currency=currency or s["egp"],
        exchange_rate=exchange_rate or (D("50") if currency else D("1")),
        issue_date=date(2026, 3, 1),
        due_date=date(2026, 12, 31),
        status=CustodyAdvanceStatus.PENDING_APPROVAL,
    )
    S.disburse_advance(a, s["user"])
    a.refresh_from_db()
    return a


def create_settlement(s, a, number="AUD-SET", amount="600", status=SettlementStatus.SUBMITTED):
    obj = PettyCashSettlement.objects.create(
        settlement_number=number,
        custody_advance=a,
        employee=s["employee1"],
        currency=s["egp"],
        settlement_date=date(2026, 3, 25),
        status=status,
        submitted_by=s["user"],
    )
    PettyCashSettlementLine.objects.create(
        settlement=obj,
        line_number=1,
        line_type=SettlementLineType.DIRECT_EXPENSE,
        expense_account=s["expense_acc"],
        currency=s["egp"],
        amount=D(amount),
        status=SettlementLineStatus.APPROVED,
    )
    return obj


def create_purchase(s, total="100"):
    return Purchase.objects.create(
        number=f"AUD-INV-{total}",
        supplier=s["supplier"],
        date=date(2026, 3, 1),
        currency=s["egp"],
        exchange_rate=D("1"),
        subtotal=D(total),
        total=D(total),
        status="confirmed",
        created_by=s["user"],
    )


def create_invoice_settlement(s, a, inv, amount="100", expense_account=None):
    obj = PettyCashSettlement.objects.create(
        settlement_number=f"AUD-INVS-{inv.number}",
        custody_advance=a,
        employee=s["employee1"],
        currency=s["egp"],
        settlement_date=date(2026, 3, 25),
        status=SettlementStatus.SUBMITTED,
        submitted_by=s["user"],
    )
    PettyCashSettlementLine.objects.create(
        settlement=obj,
        line_number=1,
        line_type=SettlementLineType.SUPPLIER_INVOICE,
        supplier=s["supplier"],
        purchase_invoice=inv,
        expense_account=expense_account,
        currency=s["egp"],
        amount=D(amount),
        status=SettlementLineStatus.APPROVED,
    )
    return obj


# =========================================================================
# 1. FX Local Amount Conversion
# =========================================================================
def test_hardened_fx_local_amount(p6_setup):
    """صرف عهدة بعملة أجنبية يسجل في الأستاذ العام بالعملة الوظيفية (الجنيه) مع حفظ العملة الأجنبية"""
    s = p6_setup
    a = create_advance(s, currency=s["usd"])
    line = a.journal_entry.lines.get(account=s["custody_adv_acc"])
    assert line.debit == D("50000.00"), f"Expected 50000 EGP debit, got {line.debit}"
    assert line.foreign_debit == D("1000.00")


# =========================================================================
# 2. Stale Settlements Divergence Prevention
# =========================================================================
def test_hardened_stale_settlements(p6_setup):
    """منع ترحيل تسويتين متزامنتين تتجاوزان رصيد العهدة وحماية تطابق الأستاذ العام"""
    s = p6_setup
    a = create_advance(s, amount="1000")
    first = create_settlement(s, a, "AUD-S1", amount="600")
    second = create_settlement(s, a, "AUD-S2", amount="600")
    second = PettyCashSettlement.objects.select_related("custody_advance").get(pk=second.pk)

    # التسوية الأولى ترحل بنجاح
    S.post_settlement(first, s["user"])

    # التسوية الثانية يجب أن تفشل لعدم كفاية الرصيد
    with pytest.raises(ValidationError):
        S.post_settlement(second, s["user"])

    a.refresh_from_db()
    assert a.settled_amount == D("600.00")
    assert a.current_balance == D("400.00")
    assert s["custody_adv_acc"].get_balance() == D("400.00")


# =========================================================================
# 3. Duplicate Replenishment Idempotency Guard
# =========================================================================
def test_hardened_duplicate_replenishment(p6_setup):
    """منع تكرار صرف الاستعاضة لنفس التسوية المستديمة"""
    s = p6_setup
    obj = PettyCashSettlement.objects.create(
        settlement_number="AUD-PERM",
        employee=s["employee1"],
        custody_account=s["custody_perm_acc"],
        currency=s["egp"],
        status=SettlementStatus.POSTED,
        eligible_replenishment_amount=D("100"),
        submitted_by=s["user"],
    )
    stale = PettyCashSettlement.objects.get(pk=obj.pk)
    e1 = S.replenish_settlement(obj, s["treasury_acc"], s["user"])
    assert e1 is not None

    with pytest.raises(ValidationError):
        S.replenish_settlement(stale, s["treasury_acc"], s["user"])


# =========================================================================
# 4. Advance Create View GET Request
# =========================================================================
def test_hardened_get_advance_create(p6_setup):
    """واجهة طلب سلفة العهدة ترجع صفحة HTML كاملة بنجاح مع كود 200 عند طلب GET"""
    req = RequestFactory().get("/")
    req.user = p6_setup["user"]
    req.session = {}
    req._messages = FallbackStorage(req)
    response = advance_create_view(req)
    assert response is not None
    assert response.status_code == 200


# =========================================================================
# 5. Legitimate Multiple Top-ups
# =========================================================================
def test_hardened_second_valid_topup(p6_setup):
    """السماح بتعزيز العهدة بأكثر من دفعة متتالية دون اصطدام برقم القيد أو قيد التكرار"""
    s = p6_setup
    a = create_advance(s, amount="1000")
    e1 = S.top_up_advance(a, D("100"), s["treasury_acc"], s["user"])
    e2 = S.top_up_advance(a, D("200"), s["treasury_acc"], s["user"])
    assert e1 is not None and e2 is not None
    assert e1.pk != e2.pk
    a.refresh_from_db()
    assert a.current_balance == D("1300.00")


# =========================================================================
# 6. Unauthorized Custody Transfer Block
# =========================================================================
def test_hardened_ordinary_user_transfer(p6_setup):
    """منع المستخدم العادي غير الممنوح لصلاحية صرف العهد من إنشاء مناقلة عهد"""
    s = p6_setup
    a = create_advance(s, amount="1000")
    user = get_user_model().objects.create_user(username="plain_emp", password="pwd")
    req = RequestFactory().post(
        "/",
        {
            "from_employee_id": s["employee1"].pk,
            "to_employee_id": s["employee2"].pk,
            "from_advance_id": a.pk,
            "amount": "100",
        },
    )
    req.user = user
    req.session = {}
    req._messages = FallbackStorage(req)

    response = transfer_create_view(req)
    assert response.status_code in [302, 403]
    a.refresh_from_db()
    assert a.transferred_out_amount == D("0.00")


# =========================================================================
# 7. Posted Settlement & Line Immutability Guard
# =========================================================================
def test_hardened_posted_edit_and_delete(p6_setup):
    """حظر تعديل أو حذف بنود التسوية أو تغيير أصل مبلغ العهدة بعد الترحيل والصرف"""
    s = p6_setup
    a = create_advance(s)
    obj = create_settlement(s, a)
    S.post_settlement(obj, s["user"])

    # محاولة تعديل البنود جماعياً
    with pytest.raises(ValidationError):
        obj.lines.update(amount=D("900"))

    # محاولة حذف البنود جماعياً
    with pytest.raises(ValidationError):
        obj.lines.all().delete()

    # محاولة تعديل أصل العهدة المصروفة
    a.amount = D("5")
    with pytest.raises(ValidationError):
        a.save()


# =========================================================================
# 8. Rejection of Unapproved/Rejected Settlements
# =========================================================================
def test_hardened_rejected_settlement_posts(p6_setup):
    """رفض ترحيل أي تسوية حالتها مرفوضة صراحة"""
    s = p6_setup
    a = create_advance(s)
    obj = create_settlement(s, a, status=SettlementStatus.REJECTED)
    with pytest.raises(ValidationError):
        S.post_settlement(obj, s["user"])


# =========================================================================
# 9. Employee Termination with Open Custody Block
# =========================================================================
def test_hardened_termination_with_open_custody(p6_setup):
    """منع إنهاء خدمة موظف طالما بذمته عهد نقدية أو عينية معلقة"""
    s = p6_setup
    a = create_advance(s)
    with pytest.raises(ValidationError):
        EmployeeService.terminate_employee(
            s["employee1"],
            {"termination_date": date(2026, 10, 26), "reason": "Audit"},
            s["user"],
        )
    s["employee1"].refresh_from_db()
    assert s["employee1"].status != "terminated"


# =========================================================================
# 10. Supplier Invoice Line Account Routing
# =========================================================================
def test_hardened_supplier_invoice_line_routing(p6_setup):
    """سداد فاتورة المورد عبر العهدة يحمل حساب المورد حصراً ولا يوجه للمصروف"""
    s = p6_setup
    a = create_advance(s)
    inv = create_purchase(s, total="100")
    obj = create_invoice_settlement(s, a, inv, expense_account=s["expense_acc"])
    entry = S.post_settlement(obj, s["user"])
    inv.refresh_from_db()

    assert inv.payment_status == "paid"
    assert not entry.lines.filter(account=s["expense_acc"]).exists()
    assert entry.lines.filter(account__code__startswith="21110", debit=D("100.00")).exists()


# =========================================================================
# 11. Invoice Overpayment Prevention
# =========================================================================
def test_hardened_invoice_overpayment(p6_setup):
    """رفض سداد مبلغ يتجاوز المستحق على فاتورة المورد"""
    s = p6_setup
    a = create_advance(s)
    inv = create_purchase(s, total="100")
    obj = create_invoice_settlement(s, a, inv, amount="200")
    with pytest.raises(ValidationError):
        S.post_settlement(obj, s["user"])


# =========================================================================
# 12. Settlement Reversal Restores Supplier Subledger
# =========================================================================
def test_hardened_reversal_subledger(p6_setup):
    """عكس تسوية مسددة لفاتورة مورد يعيد فتح رصيد الفاتورة في الأستاذ المساعد للمورد"""
    s = p6_setup
    a = create_advance(s)
    inv = create_purchase(s, total="100")
    obj = create_invoice_settlement(s, a, inv)
    S.post_settlement(obj, s["user"])

    S.reverse_settlement(obj, s["user"], reason="Audit Reversal")
    inv.refresh_from_db()
    txn = SupplierTransaction.objects.get(
        supplier=s["supplier"],
        transaction_type="BILL",
        transaction_number=inv.number,
    )
    assert inv.amount_due == D("100.00")
    assert txn.open_amount == D("100.00")
    assert txn.status in ["OPEN", "PARTIAL"]


# =========================================================================
# 13. Cross-Employee Settlement Block
# =========================================================================
def test_hardened_cross_employee_settlement(p6_setup):
    """منع تسوية عهدة موظف بمستندات موظف آخر"""
    s = p6_setup
    a = create_advance(s)
    obj = create_settlement(s, a)
    obj.employee = s["employee2"]
    with pytest.raises(ValidationError):
        obj.save()


# =========================================================================
# 14. Pending Line Settlement Block
# =========================================================================
def test_hardened_pending_line_posts(p6_setup):
    """حظر ترحيل تسوية تتضمن بنوداً ما زالت قيد المراجعة (Pending)"""
    s = p6_setup
    a = create_advance(s)
    obj = create_settlement(s, a)
    obj.lines.update(status=SettlementLineStatus.PENDING)
    with pytest.raises(ValidationError):
        S.post_settlement(obj, s["user"])


# =========================================================================
# 15. Shortage Expense-Loss Routing
# =========================================================================
def test_hardened_shortage_loss_routing(p6_setup):
    """توجيه عجز العهدة لحساب خسائر العهد (54900) عند اختيار مسار تحميل الشركة"""
    s = p6_setup
    a = create_advance(s)
    obj = create_settlement(s, a, amount="100")
    obj.shortage_amount = D("100")
    obj.variance_routing = "expense_loss"
    obj.save()

    entry = S.post_settlement(obj, s["user"])
    assert entry.lines.filter(account=s["loss_acc"], debit=D("100.00")).exists()
    assert not entry.lines.filter(account=s["hr_emp_acc"], debit=D("100.00")).exists()


# =========================================================================
# 16. Asset Under Investigation Blocks Clearance
# =========================================================================
def test_hardened_investigation_asset_clearance(p6_setup):
    """الأصول العينية قيد التحقيق تعطل إخلاء الطرف ولا تعتبر مسواة"""
    s = p6_setup
    EmployeeAssetCustody.objects.create(
        custody_code="AUD-LOST",
        employee=s["employee1"],
        item_name="Laptop under investigation",
        status="under_investigation",
        estimated_value=D("30000"),
    )
    result = EmployeeService.check_custody_clearance(s["employee1"])
    assert result["is_cleared"] is False
    assert result["pending_assets_count"] >= 1


# =========================================================================
# 17. Duplicate Count Adjustment Prevention
# =========================================================================
def test_hardened_duplicate_count_adjustment(p6_setup):
    """منع تكرار إنشاء قيد تسوية لنفس محضر الجرد الفعلي"""
    s = p6_setup
    obj = PettyCashCount.objects.create(
        count_number="AUD-COUNT",
        custody_account=s["custody_perm_acc"],
        employee=s["employee1"],
        auditor=s["user"],
        gl_balance=D("100"),
        actual_cash_amount=D("150"),
        variance_amount=D("50"),
        variance_type="overage",
    )
    stale = PettyCashCount.objects.get(pk=obj.pk)
    e1 = S.adjust_count(obj, approved_by_user=s["user"])
    assert e1 is not None

    with pytest.raises(ValidationError) as exc:
        S.adjust_count(stale, approved_by_user=s["user"])
    assert "تمت تسوية فروق هذا المحضر مسبقاً" in str(exc.value)


# =========================================================================
# 18. Treasury ACL Disburse Enforcement
# =========================================================================
def test_hardened_treasury_acl_bypass(p6_setup):
    """منع صرف العهدة إذا كان المستخدم ممنوعاً أمنياً من الخزينة المعنية"""
    s = p6_setup
    user = get_user_model().objects.create_user(username="audit_disburser", password="pwd")
    user.user_permissions.add(Permission.objects.get(codename="can_disburse_custody"))

    a = EmployeeCustodyAdvance.objects.create(
        advance_number="AUD-ACL",
        employee=s["employee1"],
        user=user,
        source_treasury=s["treasury_acc"],
        amount=D("100"),
        currency=s["egp"],
        issue_date=date(2026, 3, 1),
        due_date=date(2026, 12, 31),
        status=CustodyAdvanceStatus.PENDING_APPROVAL,
    )
    req = RequestFactory().post("/")
    req.user = user
    req.session = {}
    req._messages = FallbackStorage(req)

    # خزينة غير مصرح له بها
    with pytest.raises(ValidationError) as exc:
        S.disburse_advance(a, user)
    assert "ليس لديك صلاحية صرف" in str(exc.value)

    a.refresh_from_db()
    assert a.status == CustodyAdvanceStatus.PENDING_APPROVAL


# =========================================================================
# 19. Responsibility History Inactivated on Unassignment
# =========================================================================
def test_hardened_unassignment_history(p6_setup):
    """إلغاء إسناد حساب العهدة يغلق سجل المسؤولية التاريخي فوراً"""
    s = p6_setup
    account = s["custody_perm_acc"]
    account.assigned_employee = s["employee1"]
    account.save(update_fields=["assigned_employee"])

    history = CustodyAssignmentHistory.objects.create(
        account=account,
        employee=s["employee1"],
        assigned_by=s["user"],
        is_active=True,
    )

    req = RequestFactory().post("/", {"account_id": account.pk, "employee_id": ""})
    req.user = s["user"]
    response = assign_custody_account_employee(req)
    assert response.status_code == 200

    history.refresh_from_db()
    account.refresh_from_db()
    assert account.assigned_employee_id is None
    assert history.is_active is False
    assert history.end_date is not None


# =========================================================================
# 20. Transfer Requires Valid Active Source Advance
# =========================================================================
def test_hardened_transfer_without_source(p6_setup):
    """رفض ترحيل مناقلة عهد بدون تحديد سلفة عهدة مصدر نشطة"""
    s = p6_setup
    obj = CustodyTransfer.objects.create(
        transfer_number="AUD-EMPTY",
        from_employee=s["employee1"],
        to_employee=s["employee2"],
        currency=s["egp"],
        amount=D("100"),
        transfer_date=date(2026, 3, 25),
    )
    with pytest.raises(ValidationError):
        S.transfer_custody(obj, s["user"])


# =========================================================================
# 21. Physical Counts Reject Negative Denominations
# =========================================================================
def test_hardened_negative_denominations(p6_setup):
    """رفض تسجيل عدد فئات نقدية بالسالب في محضر الجرد الفعلي"""
    s = p6_setup
    obj = PettyCashCount.objects.create(
        count_number="AUD-NEG",
        custody_account=s["custody_perm_acc"],
        employee=s["employee1"],
        auditor=s["user"],
        gl_balance=D("100"),
        actual_cash_amount=D("0"),
    )
    with pytest.raises(ValidationError):
        S.record_petty_cash_count(obj, {"200": -1})


# =========================================================================
# 22. Foreign Currency Settlement Functional GL Conversion (R1)
# =========================================================================
def test_hardened_foreign_settlement_functional_conversion(p6_setup):
    """تسوية عهدة بالعملة الأجنبية تخصم المعادل الوظيفي الدفتري بالجنيه (100 دولار * 50 = 5,000 جنيه)"""
    s = p6_setup
    a = create_advance(s, number="AUD-FX-ADV", currency=s["usd"], amount="1000", exchange_rate=D("50"))
    obj = PettyCashSettlement.objects.create(
        settlement_number="AUD-FX-SET",
        employee=s["employee1"],
        custody_advance=a,
        currency=s["usd"],
        settlement_date=date(2026, 3, 25),
        status=SettlementStatus.SUBMITTED,
    )
    PettyCashSettlementLine.objects.create(
        settlement=obj,
        line_number=1,
        line_type=SettlementLineType.DIRECT_EXPENSE,
        expense_account=s["expense_acc"],
        currency=s["usd"],
        exchange_rate=D("50"),
        amount=D("100"),
        status=SettlementLineStatus.APPROVED,
    )
    entry = S.post_settlement(obj, s["user"])
    a.refresh_from_db()
    line = entry.lines.get(account=s["custody_adv_acc"])

    assert line.credit == D("5000.00")
    assert line.foreign_credit == D("100.00")
    assert a.current_balance == D("900.00")
    assert s["custody_adv_acc"].get_balance() == D("45000.00")


# =========================================================================
# 23. Top-up Advance Idempotency Guard via topup_id (R2)
# =========================================================================
def test_hardened_duplicate_topup_id_rejected(p6_setup):
    """رفض تكرار صرف نفس طلب التعزيز topup_id ومنع تكرار زيادة الرصيد"""
    s = p6_setup
    a = create_advance(s, number="AUD-TOP-ADV")
    first = S.top_up_advance(a, D("100"), s["treasury_acc"], s["user"], topup_id="same-request-id")
    assert first.is_posted
    a.refresh_from_db()
    assert a.current_balance == D("1100.00")

    with pytest.raises(ValidationError) as exc:
        S.top_up_advance(a, D("100"), s["treasury_acc"], s["user"], topup_id="same-request-id")
    assert "تم صرفه مسبقاً" in str(exc.value)

    a.refresh_from_db()
    assert a.current_balance == D("1100.00")


# =========================================================================
# 24. Imprest Replenishment Enforces Treasury ACL (R3)
# =========================================================================
def test_hardened_replenishment_enforces_treasury_acl(p6_setup):
    """حظر استعاضة الصندوق المستديم إذا لم يكن للمستخدم صلاحية صرف على الخزينة"""
    s = p6_setup
    user = get_user_model().objects.create_user(username="replenish-denied-user")
    user.user_permissions.add(Permission.objects.get(codename="can_disburse_custody"))

    obj = PettyCashSettlement.objects.create(
        settlement_number="AUD-REP-ACL",
        employee=s["employee1"],
        custody_account=s["custody_perm_acc"],
        currency=s["egp"],
        status=SettlementStatus.POSTED,
        eligible_replenishment_amount=D("100"),
    )
    with pytest.raises(ValidationError) as exc:
        S.replenish_settlement(obj, s["treasury_acc"], approved_by_user=user)
    assert "حظر أمني" in str(exc.value)


# =========================================================================
# 25. Settlement Account Must Match Advance Account (R4)
# =========================================================================
def test_hardened_settlement_account_must_match_advance(p6_setup):
    """رفض ترحيل تسوية تخصم من حساب عهدة مختلف عن حساب السلفة المرتبطة"""
    s = p6_setup
    a = create_advance(s, number="AUD-DIFF-ACC")
    obj = create_settlement(s, a, number="AUD-DIFF-SET", amount="100")
    obj.custody_account = s["custody_perm_acc"]
    with pytest.raises(ValidationError):
        obj.save()


# =========================================================================
# 26. Transferred Advance Cannot Be Redisbursed (R5)
# =========================================================================
def test_hardened_transferred_advance_cannot_be_redisbursed(p6_setup):
    """حظر إعادة صرف عهدة تم استلامها بمناقلة مسبقاً بعد التسوية الجزئية"""
    s = p6_setup
    a = create_advance(s, number="AUD-TRANS-REDISB")
    tr = CustodyTransfer.objects.create(
        transfer_number="AUD-TR-R5",
        from_employee=s["employee1"],
        to_employee=s["employee2"],
        from_advance=a,
        currency=s["egp"],
        amount=D("200"),
        transfer_date=date(2026, 3, 25),
    )
    S.transfer_custody(tr, s["user"])
    target = tr.to_advance

    obj = PettyCashSettlement.objects.create(
        settlement_number="AUD-TGT-SET",
        custody_advance=target,
        employee=s["employee2"],
        currency=s["egp"],
        settlement_date=date(2026, 3, 25),
        status=SettlementStatus.SUBMITTED,
    )
    PettyCashSettlementLine.objects.create(
        settlement=obj,
        line_number=1,
        line_type=SettlementLineType.DIRECT_EXPENSE,
        expense_account=s["expense_acc"],
        currency=s["egp"],
        amount=D("100"),
        status=SettlementLineStatus.APPROVED,
    )
    S.post_settlement(obj, s["user"])
    target.refresh_from_db()
    assert target.status == CustodyAdvanceStatus.PARTIALLY_SETTLED

    with pytest.raises(ValidationError):
        S.disburse_advance(target, s["user"])


# =========================================================================
# 27. Transfer Ownership and Currency Validation (R6)
# =========================================================================
def test_hardened_transfer_ownership_and_currency(p6_setup):
    """رفض المناقلة إذا كانت السلفة المختارة لا تعود للموظف المسلّم أو العملة غير متطابقة"""
    s = p6_setup
    a = create_advance(s, number="AUD-OWNER-ADV")
    with pytest.raises(ValidationError):
        CustodyTransfer.objects.create(
            transfer_number="AUD-WRONG-OWNER",
            from_employee=s["employee2"],
            to_employee=s["employee1"],
            from_advance=a,
            currency=s["egp"],
            amount=D("100"),
            transfer_date=date(2026, 3, 25),
        )

    with pytest.raises(ValidationError):
        CustodyTransfer.objects.create(
            transfer_number="AUD-ZERO-AMT",
            from_employee=s["employee1"],
            to_employee=s["employee2"],
            from_advance=a,
            currency=s["egp"],
            amount=D("0"),
            transfer_date=date(2026, 3, 25),
        )


# =========================================================================
# 28. Posted and Reversed Settlement Immutability (R7)
# =========================================================================
def test_hardened_posted_and_reversed_line_immutability(p6_setup):
    """حظر إضافة سطور جديدة لتسوية مرحلة أو تعديل سطور تسوية معكوسة عبر QuerySet"""
    s = p6_setup
    a = create_advance(s, number="AUD-IMMUT-ADV")
    obj = create_settlement(s, a, number="AUD-IMMUT-SET")
    S.post_settlement(obj, s["user"])

    # حظر إضافة سطر جديد لتسوية مرحلة
    with pytest.raises(ValidationError):
        PettyCashSettlementLine.objects.create(
            settlement=obj,
            line_number=2,
            line_type=SettlementLineType.DIRECT_EXPENSE,
            expense_account=s["expense_acc"],
            currency=s["egp"],
            amount=D("999"),
            status=SettlementLineStatus.APPROVED,
        )

    # عكس التسوية
    S.reverse_settlement(obj, s["user"])
    obj.refresh_from_db()
    assert obj.status == SettlementStatus.REVERSED

    # حظر تعديل بنود تسوية معكوسة
    with pytest.raises(ValidationError):
        obj.lines.update(amount=D("999"))


# =========================================================================
# 29. Consumed PPE Does Not Block Employee Clearance (R8)
# =========================================================================
def test_hardened_consumed_ppe_does_not_block_clearance(p6_setup):
    """مهمات الوقاية المستهلكة (consumed) لا تعطل إخلاء طرف الموظف"""
    s = p6_setup
    EmployeeAssetCustody.objects.create(
        custody_code="AUD-PPE-CON",
        employee=s["employee1"],
        item_name="Safety Gloves",
        is_consumable=True,
        status="consumed",
    )
    result = EmployeeService.check_custody_clearance(s["employee1"])
    assert result["is_cleared"] is True


# =========================================================================
# 30. Foreign Advance View Creation Saves Real Rate (Round 3 - Item 1)
# =========================================================================
def test_hardened_foreign_advance_view_creation_saves_real_rate(p6_setup):
    """إنشاء عهدة أجنبية من الشاشة يحفظ سعر الصرف الحقيقي ويصرف القيد بالقيمة الوظيفية الصحيحة"""
    s = p6_setup
    rf = RequestFactory()
    req = rf.post("/financial/custody/advances/create/", {
        "employee_id": s["employee1"].id,
        "source_treasury_id": s["treasury_acc"].id,
        "amount": "1000.00",
        "currency_id": s["usd"].id,
        "due_date": "2026-04-30",
        "purpose": "سفر مأمورية خارجية بالدولار",
    })
    req.user = s["user"]
    req.session = {}
    req._messages = FallbackStorage(req)

    resp = advance_create_view(req)
    assert resp.status_code == 302

    adv = EmployeeCustodyAdvance.objects.filter(employee=s["employee1"], currency=s["usd"]).order_by("-id").first()
    assert adv is not None
    assert adv.amount == D("1000.00")
    # التحقق من أن سعر الصرف تم تعيينه 50.00 وليس 1.00
    assert adv.exchange_rate == D("50.000000")

    # صرف العهدة والتحقق من أن القيد سُجل بـ 50,000 جنيه وليس 1,000 جنيه
    entry = S.disburse_advance(adv, s["user"])
    line = entry.lines.get(account=s["custody_adv_acc"])
    assert line.debit == D("50000.00")
    assert line.foreign_debit == D("1000.00")


# =========================================================================
# 31. Multi-Currency WHT and Discount Component Proportions (Round 3 - Item 2)
# =========================================================================
def test_hardened_wht_and_discount_multi_currency_proportions(p6_setup):
    """حساب خصم المنبع والخصم التجاري والمصروف بالعملة الوظيفية الصحيحة دون خلط وحدات العملة"""
    s = p6_setup
    adv = create_advance(s, number="AUD-DISC-ADV", currency=s["usd"])
    sett = PettyCashSettlement.objects.create(
        settlement_number="SET-DISC-001",
        employee=s["employee1"],
        custody_advance=adv,
        currency=s["usd"],
        settlement_date=date(2026, 3, 20),
        status=SettlementStatus.SUBMITTED,
    )
    # مصروف 100 دولار بسعر 50، عليه خصم منبع 10 دولارات وخصم تجاري 5 دولارات
    PettyCashSettlementLine.objects.create(
        settlement=sett,
        line_number=1,
        line_type=SettlementLineType.DIRECT_EXPENSE,
        expense_account=s["expense_acc"],
        currency=s["usd"],
        exchange_rate=D("50.000000"),
        amount=D("100.00"),
        wht_amount=D("10.00"),
        discount_amount=D("5.00"),
        status=SettlementLineStatus.APPROVED,
    )

    entry = S.post_settlement(sett, s["user"])
    assert entry.status == "posted"

    # التحقق من أن المصروف 5,000 وليس 4,265 جنيه
    exp_line = entry.lines.get(account=s["expense_acc"])
    assert exp_line.debit == D("5000.00")

    # التحقق من أن خصم المنبع 500 وليس 10 جنيهات
    wht_line = entry.lines.get(account=s["wht_acc"])
    assert wht_line.credit == D("500.00")

    # التحقق من أن الخصم التجاري 250 وليس 5 جنيهات
    disc_line = entry.lines.get(account=s["discount_acc"])
    assert disc_line.credit == D("250.00")

    # التحقق من أن دائن العهدة 4,250 جنيه (85 * 50)
    cust_line = entry.lines.get(account=s["custody_adv_acc"])
    assert cust_line.credit == D("4250.00")

    # التحقق من توازن القيد التام
    assert exp_line.debit == wht_line.credit + disc_line.credit + cust_line.credit


# =========================================================================
# 32. Permanent Foreign Custody Settlement Uses Real Rate (Round 3 - Item 3)
# =========================================================================
def test_hardened_permanent_foreign_custody_settlement_uses_real_rate(p6_setup):
    """تسوية صندوق عهدة مستديمة بالدولار تستخدم سعر الصرف الحقيقي 50 وليس 1"""
    s = p6_setup
    perm_usd_acc = ChartOfAccounts.objects.create(
        code="11136",
        name="صندوق عهدة مستديمة - دولار",
        account_type=s["asset_type"],
        currency=s["usd"],
        is_custody_account=True,
        is_active=True,
    )
    # تمويل الصندوق بـ 1000 دولار بسعر 50 (50,000 جنيه)
    fund_entry = JournalEntry.objects.create(
        number="FUND-PERM-USD",
        date=date(2026, 1, 1),
        accounting_period=s["period"],
        entry_type="opening",
        status="posted",
        description="تمويل الصندوق بالدولار",
    )
    JournalEntryLine.objects.create(
        journal_entry=fund_entry,
        account=perm_usd_acc,
        debit=D("50000.00"),
        credit=D("0.00"),
        foreign_debit=D("1000.00"),
        currency=s["usd"].code,
        exchange_rate=D("50.000000"),
    )
    JournalEntryLine.objects.create(
        journal_entry=fund_entry,
        account=s["treasury_acc"],
        debit=D("0.00"),
        credit=D("50000.00"),
        currency=s["egp"].code,
        exchange_rate=D("1.000000"),
    )

    sett = PettyCashSettlement.objects.create(
        settlement_number="SET-PERM-USD-01",
        employee=s["employee1"],
        custody_account=perm_usd_acc,
        currency=s["usd"],
        settlement_date=date(2026, 3, 20),
        status=SettlementStatus.SUBMITTED,
    )
    PettyCashSettlementLine.objects.create(
        settlement=sett,
        line_number=1,
        line_type=SettlementLineType.DIRECT_EXPENSE,
        expense_account=s["expense_acc"],
        currency=s["usd"],
        exchange_rate=D("50.000000"),
        amount=D("100.00"),
        status=SettlementLineStatus.APPROVED,
    )

    entry = S.post_settlement(sett, s["user"])
    assert entry.status == "posted"

    # التحقق من أن حساب الصندوق الدائن خصم 5,000 جنيه وليس 100 جنيه
    perm_line = entry.lines.get(account=perm_usd_acc)
    assert perm_line.credit == D("5000.00")
    assert perm_line.foreign_credit == D("100.00")


# =========================================================================
# 33. Top-Up Screen Form Prevents Duplicate Replays (Round 3 - Item 4)
# =========================================================================
def test_hardened_topup_screen_form_prevents_duplicate_replays(p6_setup):
    """منع تكرار طلب التعزيز من الشاشة وفرض topup_id ورفض إعادة الطلب المتطابق"""
    from financial.views.custody_views import advance_top_up_action
    s = p6_setup
    adv = create_advance(s, number="AUD-TOP-SCR")
    init_balance = adv.current_balance

    rf = RequestFactory()
    # 1. طلب بدون topup_id يُرفض
    req_no_id = rf.post(f"/financial/custody/advances/{adv.id}/top-up/", {
        "additional_amount": "100.00",
        "notes": "تعزيز أول",
    })
    req_no_id.user = s["user"]
    resp_no_id = advance_top_up_action(req_no_id, adv.id)
    assert resp_no_id.status_code == 400

    # 2. الطلب الأول برقم topup_id فريد ينجح
    req1 = rf.post(f"/financial/custody/advances/{adv.id}/top-up/", {
        "additional_amount": "100.00",
        "topup_id": f"TOP-FORM-{adv.id}-9999",
        "notes": "تعزيز معتمد",
    })
    req1.user = s["user"]
    resp1 = advance_top_up_action(req1, adv.id)
    assert resp1.status_code == 200

    adv.refresh_from_db()
    assert adv.current_balance == init_balance + D("100.00")

    # 3. إعادة إرسال نفس الطلب بنفس topup_id يُرفض فوراً ولا يضاعف الرصيد
    req2 = rf.post(f"/financial/custody/advances/{adv.id}/top-up/", {
        "additional_amount": "100.00",
        "topup_id": f"TOP-FORM-{adv.id}-9999",
        "notes": "تعزيز مكرر",
    })
    req2.user = s["user"]
    resp2 = advance_top_up_action(req2, adv.id)
    assert resp2.status_code == 400

    adv.refresh_from_db()
    assert adv.current_balance == init_balance + D("100.00")


# =========================================================================
# 34. Foreign Purchase Refund Converts to Custody Currency (Round 3 - Item 5)
# =========================================================================
def test_hardened_foreign_purchase_refund_converts_to_custody_currency(p6_setup):
    """مرتجع نقدي أجنبي (100 دولار بسعر 50) لعهدة بالجنيه يزيدها بـ 5,000 جنيه وليس 100 جنيه"""
    s = p6_setup
    adv = create_advance(s, number="AUD-REF-ADV", currency=s["egp"])
    adv.current_balance = D("1000.00")
    adv.save(update_fields=["current_balance"])

    sett = PettyCashSettlement.objects.create(
        settlement_number="SET-REF-001",
        employee=s["employee1"],
        custody_advance=adv,
        currency=s["egp"],
        settlement_date=date(2026, 3, 20),
        status=SettlementStatus.SUBMITTED,
    )
    # مرتجع 100 دولار بسعر 50
    PettyCashSettlementLine.objects.create(
        settlement=sett,
        line_number=1,
        line_type=SettlementLineType.PURCHASE_REFUND,
        supplier=s["supplier"],
        currency=s["usd"],
        exchange_rate=D("50.000000"),
        amount=D("100.00"),
        status=SettlementLineStatus.APPROVED,
    )

    totals = S.calculate_settlement_totals(sett)
    # التحقق من أن المرتجع في الإجماليات حُسب 5,000 جنيه
    assert totals["refunds_collected"] == D("5000.00")

    entry = S.post_settlement(sett, s["user"])
    assert entry.status == "posted"

    adv.refresh_from_db()
    # رصيد العهدة يجب أن يرتفع من 1,000 إلى 6,000 جنيه (1000 + 5000)
    assert adv.refunds_collected_amount == D("5000.00")
    assert adv.current_balance == D("6000.00")

    # التحقق من قيد اليومية: مدين العهدة بـ 5,000 جنيه ودائن المورد بـ 5,000 جنيه
    cust_line = entry.lines.get(account=s["custody_adv_acc"])
    assert cust_line.debit == D("5000.00")
    sup_line = entry.lines.filter(credit=D("5000.00")).first()
    assert sup_line is not None
    assert sup_line.account.code.startswith("21110")


# =========================================================================
# 35. Foreign Imprest Full Cycle: Funding -> Settlement -> Replenishment
# =========================================================================
def test_hardened_foreign_imprest_cycle_funding_settlement_replenishment_balances(p6_setup):
    """
    اختبار دورة كاملة للعهدة المستديمة الأجنبية بسعر صرف 50:
    1. تمويل الصندوق: 1,000 دولار = 50,000 جنيه من الخزينة.
    2. تسوية 100 دولار: خصم 5,000 جنيه (100 دولار) مصروف.
    3. استعاضة 100 دولار: تعويض 5,000 جنيه (100 دولار) من الخزينة.
    مطابقة الرصيد بالجنيه والدولار والخزينة:
    - رصيد الصندوق بالجنيه يعود إلى 50,000.00 جنيه بالتمام (بدل 45,100).
    - رصيد الصندوق بالدولار يعود إلى 1,000.00 دولار بالتمام.
    - إجمالي المنصرف من الخزينة 55,000.00 جنيه (50,000 تمويل + 5,000 استعاضة).
    """
    s = p6_setup

    perm_usd_acc = ChartOfAccounts.objects.create(
        code="11210088",
        name="صندوق عهدة مستديمة بالدولار للمصروفات",
        account_type=s["asset_type"],
        currency=s["usd"],
        is_custody_account=True,
        is_active=True,
    )

    # 1. تمويل الصندوق بـ 1,000 دولار بسعر 50 = 50,000 جنيه
    fund_entry = JournalEntry.objects.create(
        number="JE-FUND-USD-01",
        date=date(2026, 1, 1),
        accounting_period=s["period"],
        entry_type="cash_payment",
        status="posted",
        description="تمويل الصندوق المستديم بالدولار",
    )
    JournalEntryLine.objects.create(
        journal_entry=fund_entry,
        account=perm_usd_acc,
        debit=D("50000.00"),
        credit=D("0.00"),
        foreign_debit=D("1000.00"),
        currency=s["usd"].code,
        exchange_rate=D("50.000000"),
    )
    JournalEntryLine.objects.create(
        journal_entry=fund_entry,
        account=s["treasury_acc"],
        debit=D("0.00"),
        credit=D("50000.00"),
        currency=s["egp"].code,
        exchange_rate=D("1.000000"),
    )

    # التحقق من رصيد الصندوق بعد التمويل
    p_lines_1 = JournalEntryLine.objects.filter(account=perm_usd_acc, journal_entry__status="posted")
    assert sum(l.debit - l.credit for l in p_lines_1) == D("50000.00")
    assert sum(l.foreign_debit - l.foreign_credit for l in p_lines_1) == D("1000.00")

    # 2. تسوية 100 دولار بسعر 50
    sett = PettyCashSettlement.objects.create(
        settlement_number="SET-IMP-CYCLE-01",
        employee=s["employee1"],
        custody_account=perm_usd_acc,
        currency=s["usd"],
        settlement_date=date(2026, 3, 20),
        status=SettlementStatus.SUBMITTED,
    )
    PettyCashSettlementLine.objects.create(
        settlement=sett,
        line_number=1,
        line_type=SettlementLineType.DIRECT_EXPENSE,
        expense_account=s["expense_acc"],
        currency=s["usd"],
        exchange_rate=D("50.000000"),
        amount=D("100.00"),
        status=SettlementLineStatus.APPROVED,
    )

    sett_entry = S.post_settlement(sett, s["user"])
    assert sett_entry.status == "posted"

    # التحقق من رصيد الصندوق بعد التسوية: أصبح 45,000 جنيه و 900 دولار
    p_lines_2 = JournalEntryLine.objects.filter(account=perm_usd_acc, journal_entry__status="posted")
    assert sum(l.debit - l.credit for l in p_lines_2) == D("45000.00")
    assert sum(l.foreign_debit - l.foreign_credit for l in p_lines_2) == D("900.00")

    sett.refresh_from_db()
    assert sett.eligible_replenishment_amount == D("100.00")

    # 3. استعاضة 100 دولار من الخزينة
    repl_entry = S.replenish_settlement(sett, s["treasury_acc"], approved_by_user=s["user"])
    assert repl_entry.status == "posted"

    # التحقق من بنود قيد الاستعاضة: مدين الصندوق 5,000 جنيه (100 دولار) ودائن الخزينة 5,000 جنيه
    repl_cust_line = repl_entry.lines.get(account=perm_usd_acc)
    assert repl_cust_line.debit == D("5000.00")
    assert repl_cust_line.foreign_debit == D("100.00")
    assert repl_cust_line.exchange_rate == D("50.000000")

    repl_trs_line = repl_entry.lines.get(account=s["treasury_acc"])
    assert repl_trs_line.credit == D("5000.00")
    assert repl_trs_line.exchange_rate == D("50.000000")

    # 4. مطابقة الأرصدة النهائية بالجنيه والدولار والخزينة
    p_lines_final = JournalEntryLine.objects.filter(account=perm_usd_acc, journal_entry__status="posted")
    final_egp_balance = sum(l.debit - l.credit for l in p_lines_final)
    final_usd_balance = sum(l.foreign_debit - l.foreign_credit for l in p_lines_final)

    # رصيد الصندوق عاد 50,000 جنيه بالكامل بدل أن ينقص إلى 45,100!
    assert final_egp_balance == D("50000.00")
    assert final_usd_balance == D("1000.00")

    # رصيد الخزينة المصدرة: تم خصم 55,000 جنيه (50,000 تمويل + 5,000 استعاضة)
    trs_lines_final = JournalEntryLine.objects.filter(account=s["treasury_acc"], journal_entry__status="posted")
    final_treasury_credit = sum(l.credit for l in trs_lines_final)
    assert final_treasury_credit == D("55000.00")



