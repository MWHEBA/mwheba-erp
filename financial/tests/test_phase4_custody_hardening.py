from decimal import Decimal
from datetime import date
import pytest
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from core.enums.document_types import DocumentType
from core.services.sequence_service import SequenceService
from financial.models.fiscal_year import FiscalYear
from financial.models.currency import Currency
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.journal_entry import AccountingPeriod, JournalEntry, JournalEntryLine
from financial.models.cost_center import CostCenter
from financial.models.custody import (
    EmployeeCustodyAdvance,
    CustodyAdvanceStatus,
    SettlementLineType,
    PettyCashSettlement,
    SettlementStatus,
    PettyCashSettlementLine,
    SettlementLineStatus,
    PettyCashCount,
)
from financial.services.custody_service import CustodyManagementService
from hr.models import Employee, Department, JobTitle, WorkLocation
from hr.services.employee_service import EmployeeService
from purchase.models.purchase import Purchase
from purchase.models.payment import PurchasePayment
from supplier.models import Supplier

User = get_user_model()


def _fund_account(account, amount, currency, period, asset_type):
    """مساعدة إيداع رصيد مثبت في الأستاذ العام"""
    entry = JournalEntry.objects.create(
        number=f"FUND-{account.code}-{timezone.now().strftime('%f')}",
        date=date(2026, 1, 1),
        accounting_period=period,
        entry_type="opening",
        status="posted",
        description=f"تغذية رصيد {account.name}",
    )
    eq_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="31010",
        defaults={"name": "رأس المال / الأرصدة الافتتاحية", "account_type": asset_type, "is_active": True}
    )
    JournalEntryLine.objects.create(
        journal_entry=entry,
        account=account,
        debit=amount,
        credit=Decimal("0.00"),
        transaction_debit=amount,
        currency=currency.code,
        exchange_rate=Decimal("1.000000"),
    )
    JournalEntryLine.objects.create(
        journal_entry=entry,
        account=eq_acc,
        debit=Decimal("0.00"),
        credit=amount,
        transaction_credit=amount,
        currency=currency.code,
        exchange_rate=Decimal("1.000000"),
    )


@pytest.fixture
def phase4_setup(db):
    user = User.objects.create_user(username="test_phase4_user", password="password123", is_superuser=True)

    egp, _ = Currency.objects.get_or_create(
        code="EGP",
        defaults={"name": "Egyptian Pound", "symbol": "ج.م", "is_functional": True}
    )
    usd, _ = Currency.objects.get_or_create(
        code="USD",
        defaults={"name": "US Dollar", "symbol": "$", "is_functional": False}
    )

    fy, _ = FiscalYear.objects.get_or_create(
        year_code="FY2026",
        defaults={"name": "2026", "start_date": date(2026, 1, 1), "end_date": date(2026, 12, 31), "status": "open"}
    )
    period, _ = AccountingPeriod.objects.get_or_create(
        name="2026-P01",
        defaults={
            "fiscal_year": fy,
            "start_date": date(2026, 1, 1),
            "end_date": date(2026, 12, 31),
            "status": "open",
            "created_by": user,
        }
    )

    asset_type, _ = AccountType.objects.get_or_create(
        code="ASSET_P4",
        defaults={"name": "Current Assets", "category": "asset", "nature": "debit"}
    )
    liability_type, _ = AccountType.objects.get_or_create(
        code="LIAB_P4",
        defaults={"name": "Liabilities", "category": "liability", "nature": "credit"}
    )
    expense_type, _ = AccountType.objects.get_or_create(
        code="EXP_P4",
        defaults={"name": "Expenses", "category": "expense", "nature": "debit"}
    )
    revenue_type, _ = AccountType.objects.get_or_create(
        code="REV_P4",
        defaults={"name": "Revenue", "category": "revenue", "nature": "credit"}
    )

    treasury_acc = ChartOfAccounts.objects.create(
        code="11110",
        name="Main Treasury",
        account_type=asset_type,
        currency=egp,
        is_cash_account=True,
        is_active=True,
    )
    custody_adv_acc = ChartOfAccounts.objects.create(
        code="11130",
        name="Custody Clearing",
        account_type=asset_type,
        currency=egp,
        is_active=True,
        is_custody_account=True,
    )
    custody_perm_acc = ChartOfAccounts.objects.create(
        code="11135",
        name="Permanent Imprest Cash",
        account_type=asset_type,
        currency=egp,
        is_active=True,
        is_custody_account=True,
    )
    hr_emp_acc = ChartOfAccounts.objects.create(
        code="11230",
        name="Employee Advances",
        account_type=asset_type,
        currency=egp,
        is_active=True,
        is_custody_account=True,
    )
    supplier_acc = ChartOfAccounts.objects.create(
        code="21110",
        name="Accounts Payable",
        account_type=liability_type,
        currency=egp,
        is_active=True,
    )
    expense_acc = ChartOfAccounts.objects.create(
        code="51100",
        name="General Expenses",
        account_type=expense_type,
        currency=egp,
        is_active=True,
    )
    loss_acc = ChartOfAccounts.objects.create(
        code="54900",
        name="Custody Shortage Expense",
        account_type=expense_type,
        currency=egp,
        is_active=True,
    )
    overage_acc = ChartOfAccounts.objects.create(
        code="42990",
        name="Other Revenue",
        account_type=revenue_type,
        currency=egp,
        is_active=True,
    )
    overrun_acc = ChartOfAccounts.objects.create(
        code="21230",
        name="Employee Custody Overrun Payable",
        account_type=liability_type,
        currency=egp,
        is_active=True,
    )

    dept, _ = Department.objects.get_or_create(
        code="FIN",
        defaults={"name_ar": "المالية", "name_en": "Finance"}
    )
    job, _ = JobTitle.objects.get_or_create(
        code="ACC",
        defaults={"title_ar": "محاسب", "department": dept}
    )
    employee, _ = Employee.objects.get_or_create(
        employee_number="EMP-P4-01",
        defaults={
            "name": "أحمد عادل",
            "national_id": "29001010101011",
            "birth_date": date(1990, 1, 1),
            "gender": "male",
            "marital_status": "single",
            "hire_date": date(2023, 1, 1),
            "department": dept,
            "job_title": job,
            "created_by": user,
        }
    )

    supplier = Supplier.objects.create(
        name="Global Tech",
        code="SUP-P4-001",
    )

    # تغذية الخزينة برصيد كافٍ في دفتر الأستاذ العام
    _fund_account(treasury_acc, Decimal("200000.00"), egp, period, asset_type)

    return {
        "user": user,
        "egp": egp,
        "usd": usd,
        "period": period,
        "asset_type": asset_type,
        "treasury_acc": treasury_acc,
        "custody_adv_acc": custody_adv_acc,
        "custody_perm_acc": custody_perm_acc,
        "hr_emp_acc": hr_emp_acc,
        "supplier_acc": supplier_acc,
        "expense_acc": expense_acc,
        "loss_acc": loss_acc,
        "overage_acc": overage_acc,
        "employee": employee,
        "supplier": supplier,
    }


@pytest.mark.django_db
def test_reverse_settlement_symmetrical_restoration(phase4_setup):
    """
    اختبار 4.1: العكس المحاسبي المتناظر لتسوية العهدة:
    - إلغاء قيد التسوية بقيد عكسي مقفول.
    - استرجاع رصيد السلفة 100%.
    - إلغاء دفعة المورد برفع راية _allow_custody_reversal.
    - استعادة رصيد المورد.
    """
    s = phase4_setup
    adv = EmployeeCustodyAdvance.objects.create(
        advance_number="ADV-P4-REV-01",
        employee=s["employee"],
        source_treasury=s["treasury_acc"],
        amount=Decimal("5000.00"),
        settlement_principal_amount=Decimal("5000.00"),
        current_balance=Decimal("5000.00"),
        due_date=date(2026, 3, 31),
        status=CustodyAdvanceStatus.ACTIVE,
        currency=s["egp"],
        custody_account=s["custody_adv_acc"],
    )

    # إنشاء تسوية بمصروف ودفع لمورد
    settlement = PettyCashSettlement.objects.create(
        settlement_number="SET-P4-REV-01",
        custody_advance=adv,
        employee=s["employee"],
        currency=s["egp"],
        settlement_date=date(2026, 3, 10),
        status=SettlementStatus.SUBMITTED,
        total_settled_amount=Decimal("3000.00"),
    )

    # سطر مصروف 1,000
    PettyCashSettlementLine.objects.create(
        settlement=settlement,
        line_number=1,
        line_type=SettlementLineType.DIRECT_EXPENSE,
        currency=s["egp"],
        amount=Decimal("1000.00"),
        exchange_rate=Decimal("1.000000"),
        expense_account=s["expense_acc"],
        status=SettlementLineStatus.APPROVED,
    )

    # فاتورة مشتريات مورد بمبلغ 2,000
    purchase = Purchase.objects.create(
        number="PO-P4-001",
        supplier=s["supplier"],
        date=date(2026, 3, 1),
        currency=s["egp"],
        exchange_rate=Decimal("1.000000"),
        subtotal=Decimal("2000.00"),
        total=Decimal("2000.00"),
        status="confirmed",
        created_by=s["user"],
    )

    # سطر سداد مورد 2,000
    PettyCashSettlementLine.objects.create(
        settlement=settlement,
        line_number=2,
        line_type=SettlementLineType.SUPPLIER_INVOICE,
        supplier=s["supplier"],
        purchase_invoice=purchase,
        currency=s["egp"],
        amount=Decimal("2000.00"),
        exchange_rate=Decimal("1.000000"),
        status=SettlementLineStatus.APPROVED,
    )

    # ترحيل التسوية
    entry = CustodyManagementService.post_settlement(settlement, approved_by_user=s["user"])
    assert settlement.status == SettlementStatus.POSTED
    adv.refresh_from_db()
    assert adv.current_balance == Decimal("2000.00")
    assert adv.settled_amount == Decimal("3000.00")

    # التحقق من إنشاء دفعة المورد
    payment = PurchasePayment.objects.filter(reference_number=settlement.settlement_number).first()
    assert payment is not None
    assert payment.status == "posted"

    # الآن استدعاء العكس المحاسبي reverse_settlement
    reversal_entry = CustodyManagementService.reverse_settlement(settlement, approved_by_user=s["user"])

    settlement.refresh_from_db()
    adv.refresh_from_db()
    payment.refresh_from_db()

    # 1. حالة التسوية وقيد العكس
    assert settlement.status == SettlementStatus.REVERSED
    assert settlement.reversal_entry == reversal_entry
    assert reversal_entry.is_locked is True

    # 2. الاستعادة المتناظرة لأرصدة السلفة
    assert adv.current_balance == Decimal("5000.00")
    assert adv.settled_amount == Decimal("0.00")
    assert adv.status == CustodyAdvanceStatus.ACTIVE

    # 3. إبطال دفعة المورد وراية السماح بالعكس
    assert payment.status == "cancelled"
    assert payment.financial_status == "reversed"


@pytest.mark.django_db
def test_reverse_settlement_blocks_replenished_settlement(phase4_setup):
    """
    اختبار 4.2: التحقق من منع عكس تسوية تم استعاضتها مسبقاً قبل إلغاء الاستعاضة.
    """
    s = phase4_setup
    settlement = PettyCashSettlement.objects.create(
        settlement_number="SET-P4-BLOCKED",
        custody_account=s["custody_perm_acc"],
        employee=s["employee"],
        currency=s["egp"],
        settlement_date=date(2026, 3, 10),
        status=SettlementStatus.POSTED,
        total_settled_amount=Decimal("1500.00"),
        is_replenished=True,  # تم استعاضتها
    )

    with pytest.raises(ValidationError):
        CustodyManagementService.reverse_settlement(settlement, approved_by_user=s["user"])


@pytest.mark.django_db
def test_replenish_settlement_six_conditions(phase4_setup):
    """
    اختبار 4.2: استعاضة الصندوق المستديم بالشروط الستة الإلزامية:
    1) POSTED
    2) permanent only (custody_account is not None, advance is None)
    3) is_replenished is False
    4) eligible_amount > 0
    5) كفاية رصيد الخزينة
    6) قيد مقفول مدين 11135 ودائن الخزينة 11110
    """
    s = phase4_setup

    # 1. رفض الاستعاضة لسلفة مؤقتة
    adv = EmployeeCustodyAdvance.objects.create(
        advance_number="ADV-P4-TMP",
        employee=s["employee"],
        source_treasury=s["treasury_acc"],
        amount=Decimal("2000.00"),
        current_balance=Decimal("2000.00"),
        due_date=date(2026, 3, 31),
        currency=s["egp"],
    )
    temp_settlement = PettyCashSettlement.objects.create(
        settlement_number="SET-P4-TEMP",
        custody_advance=adv,
        employee=s["employee"],
        currency=s["egp"],
        settlement_date=date(2026, 3, 10),
        status=SettlementStatus.POSTED,
        total_settled_amount=Decimal("1000.00"),
    )
    with pytest.raises(ValidationError):
        CustodyManagementService.replenish_settlement(temp_settlement, s["treasury_acc"], approved_by_user=s["user"])

    # 2. إنشاء تسوية مستديمة صالحة
    perm_settlement = PettyCashSettlement.objects.create(
        settlement_number="SET-P4-PERM-01",
        custody_account=s["custody_perm_acc"],
        employee=s["employee"],
        currency=s["egp"],
        settlement_date=date(2026, 3, 10),
        status=SettlementStatus.POSTED,
        total_settled_amount=Decimal("4000.00"),
        eligible_replenishment_amount=Decimal("4000.00"),
    )

    # 3. نجاح الاستعاضة عند توفر الرصيد والشروط
    rep_entry = CustodyManagementService.replenish_settlement(
        perm_settlement, s["treasury_acc"], approved_by_user=s["user"]
    )
    perm_settlement.refresh_from_db()

    assert perm_settlement.is_replenished is True
    assert perm_settlement.replenishment_entry == rep_entry
    assert rep_entry.is_locked is True

    lines = list(rep_entry.lines.all())
    assert len(lines) == 2
    debit_line = [l for l in lines if l.debit > 0][0]
    credit_line = [l for l in lines if l.credit > 0][0]

    assert debit_line.account == s["custody_perm_acc"]
    assert debit_line.debit == Decimal("4000.00")
    assert credit_line.account == s["treasury_acc"]
    assert credit_line.credit == Decimal("4000.00")


@pytest.mark.django_db
def test_adjust_count_gl_variance(phase4_setup):
    """
    اختبار 4.3: تسوية فروق الجرد الفعلي:
    - عجز مع خصم HR
    - عجز مع خسارة مصروف
    - زيادة مع إيرادات متنوعة
    """
    s = phase4_setup

    # 1. جرد بعجز 500 واستقطاع HR
    count_shortage_hr = PettyCashCount.objects.create(
        count_number="CNT-P4-001",
        custody_account=s["custody_adv_acc"],
        employee=s["employee"],
        count_date=timezone.now(),
        auditor=s["user"],
        gl_balance=Decimal("2000.00"),
        actual_cash_amount=Decimal("1500.00"),
        variance_amount=Decimal("-500.00"),
        variance_type="shortage",
        status="audited",
    )
    entry_hr = CustodyManagementService.adjust_count(
        count_obj=count_shortage_hr, variance_routing="hr_deduction", approved_by_user=s["user"]
    )
    count_shortage_hr.refresh_from_db()
    assert count_shortage_hr.status == "adjusted"
    assert entry_hr is not None
    assert entry_hr.is_locked is True

    lines_hr = list(entry_hr.lines.all())
    debit_hr = [l for l in lines_hr if l.debit > 0][0]
    credit_hr = [l for l in lines_hr if l.credit > 0][0]
    assert debit_hr.account == s["hr_emp_acc"]
    assert debit_hr.debit == Decimal("500.00")
    assert credit_hr.account == s["custody_adv_acc"]
    assert credit_hr.credit == Decimal("500.00")

    # 2. جرد بعجز 300 وتحميل خسائر تشغيلية
    count_shortage_exp = PettyCashCount.objects.create(
        count_number="CNT-P4-002",
        custody_account=s["custody_adv_acc"],
        employee=s["employee"],
        count_date=timezone.now(),
        auditor=s["user"],
        gl_balance=Decimal("2000.00"),
        actual_cash_amount=Decimal("1700.00"),
        variance_amount=Decimal("-300.00"),
        variance_type="shortage",
        status="audited",
    )
    entry_exp = CustodyManagementService.adjust_count(
        count_obj=count_shortage_exp, variance_routing="expense_loss", approved_by_user=s["user"]
    )
    lines_exp = list(entry_exp.lines.all())
    debit_exp = [l for l in lines_exp if l.debit > 0][0]
    assert debit_exp.account == s["loss_acc"]
    assert debit_exp.debit == Decimal("300.00")

    # 3. جرد بزيادة 200 وقيد إيرادات متنوعة
    count_overage = PettyCashCount.objects.create(
        count_number="CNT-P4-003",
        custody_account=s["custody_adv_acc"],
        employee=s["employee"],
        count_date=timezone.now(),
        auditor=s["user"],
        gl_balance=Decimal("2000.00"),
        actual_cash_amount=Decimal("2200.00"),
        variance_amount=Decimal("200.00"),
        variance_type="overage",
        status="audited",
    )
    entry_over = CustodyManagementService.adjust_count(
        count_obj=count_overage, variance_routing="other_revenue", approved_by_user=s["user"]
    )
    count_overage.refresh_from_db()
    assert count_overage.status == "adjusted"
    lines_over = list(entry_over.lines.all())
    debit_over = [l for l in lines_over if l.debit > 0][0]
    credit_over = [l for l in lines_over if l.credit > 0][0]
    assert debit_over.account == s["custody_adv_acc"]
    assert debit_over.debit == Decimal("200.00")
    assert credit_over.account == s["overage_acc"]
    assert credit_over.credit == Decimal("200.00")


@pytest.mark.django_db
def test_hr_custody_clearance_blocks_under_review(phase4_setup):
    """
    اختبار 4.4: فحص إخلاء طرف الموظف بالموارد البشرية وتجميده طالما توجد تسويات قيد المراجعة.
    """
    s = phase4_setup
    adv = EmployeeCustodyAdvance.objects.create(
        advance_number="ADV-P4-HR-01",
        employee=s["employee"],
        source_treasury=s["treasury_acc"],
        amount=Decimal("3000.00"),
        settlement_principal_amount=Decimal("3000.00"),
        current_balance=Decimal("3000.00"),
        due_date=date(2026, 3, 31),
        status=CustodyAdvanceStatus.ACTIVE,
        currency=s["egp"],
    )

    # تقديم تسوية قيد المراجعة بمبلغ 2,500
    settlement = PettyCashSettlement.objects.create(
        settlement_number="SET-P4-HR-SUB",
        custody_advance=adv,
        employee=s["employee"],
        currency=s["egp"],
        settlement_date=date(2026, 3, 10),
        status=SettlementStatus.SUBMITTED,
        total_settled_amount=Decimal("2500.00"),
    )

    res = EmployeeService.check_custody_clearance(s["employee"])

    assert res["is_cleared"] is False
    assert res["pending_cash_balance"] == Decimal("3000.00")
    assert res["under_review_amount"] == Decimal("2500.00")
    assert res["under_review_count"] == 1
    assert res["net_unsettled_exposure"] == Decimal("500.00")
    assert "قيد المراجعة والاعتماد" in res["clearance_status_text"]

    # عند اعتماد التسوية وإلغاء الرصيد المتبقي
    settlement.status = SettlementStatus.POSTED
    settlement.save()
    adv.current_balance = Decimal("0.00")
    adv.status = CustodyAdvanceStatus.SETTLED
    adv.save()

    res_after = EmployeeService.check_custody_clearance(s["employee"])
    assert res_after["is_cleared"] is True
    assert res_after["pending_cash_balance"] == Decimal("0.00")
    assert res_after["under_review_count"] == 0
    assert res_after["net_unsettled_exposure"] == Decimal("0.00")
    assert res_after["clearance_status_text"] == "تم إخلاء الطرف بالكامل"


@pytest.mark.django_db
def test_count_create_view_book_balance_cutoff(client, phase4_setup):
    """
    اختبار 4.6: احتساب الرصيد الدفتري في محضر الجرد بتاريخ القطع والعملة الصحيحة
    """
    s = phase4_setup
    client.force_login(s["user"])

    # إيداع رصيد 15,000 في حساب العهدة 11130
    _fund_account(s["custody_adv_acc"], Decimal("15000.00"), s["egp"], s["period"], s["asset_type"])

    post_data = {
        "employee_id": s["employee"].id,
        "custody_account_id": s["custody_adv_acc"].id,
        "pending_vouchers_amount": "500.00",
        "notes": "محضر جرد مفاجئ",
        "denom_200": 70,  # 14,000
        "denom_100": 10,  # 1,000 -> الإجمالي الفعلي 15,000
    }

    from django.urls import reverse
    url = reverse("financial:custody_count_create")
    response = client.post(url, post_data)
    assert response.status_code == 302

    count_obj = PettyCashCount.objects.filter(employee=s["employee"]).first()
    assert count_obj is not None
    assert count_obj.gl_balance == Decimal("15000.00")

