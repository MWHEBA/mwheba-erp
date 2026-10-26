# -*- coding: utf-8 -*-
"""
Phase 6 Acceptance and Resilience Test Suite
------------------------------------------
Comprehensive verification of:
1. Purchase return cash collected (refunds_collected_amount) and exact balance reconciliation.
2. Per diem split (is_per_diem_split, per_diem_amount, settlement_principal_amount) isolation.
3. Multi-currency purchase settlement signature, exchange rates, and partner subledger updates.
4. Physical inventory count GL cut-off balance verification.
5. Zero and negative amounts strict rejection.
6. Outflow under lock and treasury sufficiency guards.
7. Shortage routing (HR deduction vs expense loss) and HR clearance transparency.
8. Transaction rollback resiliency on step failure.
9. Symmetric safe reversal and idempotency.
"""

from decimal import Decimal
from datetime import date
from unittest.mock import patch
import pytest

from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from core.enums.document_types import DocumentType
from core.services.sequence_service import SequenceService
from financial.models.fiscal_year import FiscalYear
from financial.models.currency import Currency, ExchangeRate
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.journal_entry import AccountingPeriod, JournalEntry, JournalEntryLine
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
from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames
from financial.services.custody_service import CustodyManagementService
from financial.services.ledger_core_service import LedgerCoreService
from hr.models import Employee, Department, JobTitle, WorkLocation
from hr.services.employee_service import EmployeeService
from purchase.models.purchase import Purchase
from purchase.models.payment import PurchasePayment
from supplier.models import Supplier

User = get_user_model()


def _fund_account(account, amount, currency, period, asset_type):
    """مساعدة تمويل الحساب المحاسبي برصيد دفتري مثبت في الأستاذ العام"""
    entry = JournalEntry.objects.create(
        number=f"FUND-P6-{account.code}-{timezone.now().strftime('%f')}",
        date=date(2026, 1, 1),
        accounting_period=period,
        entry_type="opening",
        status="posted",
        description=f"تغذية رصيد {account.name}",
    )
    eq_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="31010",
        defaults={"name": "الأرصدة الافتتاحية", "account_type": asset_type, "is_active": True}
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
def p6_setup(db):
    user = User.objects.create_user(
        username="p6_auditor",
        email="p6_auditor@test.com",
        password="Password123!",
        is_staff=True,
        is_superuser=True,
    )

    egp, _ = Currency.objects.get_or_create(
        code="EGP",
        defaults={"name": "جنيه مصري", "symbol": "ج.م", "is_functional": True}
    )
    usd, _ = Currency.objects.get_or_create(
        code="USD",
        defaults={"name": "US Dollar", "symbol": "$", "is_functional": False}
    )

    # سعر الصرف المعتمد USD/EGP
    ExchangeRate.objects.get_or_create(
        from_currency=usd,
        to_currency=egp,
        effective_date=date(2026, 1, 1),
        defaults={"rate": Decimal("50.000000")}
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

    asset_type, _ = AccountType.objects.get_or_create(code="AST_P6", defaults={"name": "أصول", "category": "asset", "nature": "debit"})
    liability_type, _ = AccountType.objects.get_or_create(code="LIA_P6", defaults={"name": "التزامات", "category": "liability", "nature": "credit"})
    expense_type, _ = AccountType.objects.get_or_create(code="EXP_P6", defaults={"name": "مصروفات", "category": "expense", "nature": "debit"})
    revenue_type, _ = AccountType.objects.get_or_create(code="REV_P6", defaults={"name": "إيرادات", "category": "revenue", "nature": "credit"})

    treasury_acc = ChartOfAccounts.objects.create(code="11110", name="الخزينة الرئيسية", account_type=asset_type, currency=egp, is_cash_account=True, is_active=True)
    custody_adv_acc = ChartOfAccounts.objects.create(code="11130", name="العهد النقدية المؤقتة", account_type=asset_type, currency=egp, is_custody_account=True, is_active=True)
    custody_perm_acc = ChartOfAccounts.objects.create(code="11135", name="صندوق المصروفات النثرية", account_type=asset_type, currency=egp, is_custody_account=True, is_active=True)
    hr_emp_acc = ChartOfAccounts.objects.create(code="11230", name="سلف العاملين", account_type=asset_type, currency=egp, is_custody_account=True, is_active=True)
    supplier_acc = ChartOfAccounts.objects.create(code="21110", name="الموردون", account_type=liability_type, currency=egp, is_active=True)
    overrun_acc = ChartOfAccounts.objects.create(code="21230", name="مستحقات عهد وتجاوزات منصرفة", account_type=liability_type, currency=egp, is_active=True)
    expense_acc = ChartOfAccounts.objects.create(code="51100", name="مصروفات تشغيلية", account_type=expense_type, currency=egp, is_active=True)
    loss_acc = ChartOfAccounts.objects.create(code="54900", name="خسائر عجز العهد", account_type=expense_type, currency=egp, is_active=True)
    overage_acc = ChartOfAccounts.objects.create(code="42990", name="إيرادات متنوعة وزيادة جرد", account_type=revenue_type, currency=egp, is_active=True)
    fx_loss_acc = ChartOfAccounts.objects.create(code="54300", name="خسائر فروق أسعار الصرف", account_type=expense_type, currency=egp, is_active=True)
    fx_gain_acc = ChartOfAccounts.objects.create(code="43100", name="أرباح فروق أسعار الصرف", account_type=revenue_type, currency=egp, is_active=True)
    vat_acc = ChartOfAccounts.objects.create(code="11510", name="ضريبة القيمة المضافة", account_type=asset_type, currency=egp, is_active=True)
    wht_acc = ChartOfAccounts.objects.create(code="21330", name="ضريبة الخصم من المنبع", account_type=liability_type, currency=egp, is_active=True)
    discount_acc = ChartOfAccounts.objects.create(code="51930", name="الخصم المكتسب", account_type=expense_type, currency=egp, is_active=True)

    dept = Department.objects.create(code="PRJ6", name_ar="إدارة المشروعات الكبرى")
    job = JobTitle.objects.create(code="MGR6", title_ar="مدير موقع", department=dept)
    loc = WorkLocation.objects.create(name_ar="مشروع العلمين الجديدة", latitude=Decimal("30.835"), longitude=Decimal("28.955"))

    employee1 = Employee.objects.create(
        employee_number="EMP-P6-001",
        name="م. إبراهيم شكري",
        national_id="29001010101099",
        birth_date=date(1988, 5, 20),
        gender="male",
        marital_status="married",
        hire_date=date(2022, 1, 1),
        department=dept,
        job_title=job,
        work_location=loc,
        created_by=user,
    )
    employee2 = Employee.objects.create(
        employee_number="EMP-P6-002",
        name="م. طارق يحيى",
        national_id="29102020202088",
        birth_date=date(1991, 8, 15),
        gender="male",
        marital_status="single",
        hire_date=date(2023, 3, 1),
        department=dept,
        job_title=job,
        work_location=loc,
        created_by=user,
    )

    supplier = Supplier.objects.create(name="Delta Industrial Supplies", code="SUP-DELTA-01")

    # تغذية الخزينة برصيد كافٍ
    _fund_account(treasury_acc, Decimal("500000.00"), egp, period, asset_type)

    return {
        "user": user,
        "egp": egp,
        "usd": usd,
        "period": period,
        "treasury_acc": treasury_acc,
        "custody_adv_acc": custody_adv_acc,
        "custody_perm_acc": custody_perm_acc,
        "hr_emp_acc": hr_emp_acc,
        "supplier_acc": supplier_acc,
        "overrun_acc": overrun_acc,
        "expense_acc": expense_acc,
        "loss_acc": loss_acc,
        "overage_acc": overage_acc,
        "fx_loss_acc": fx_loss_acc,
        "fx_gain_acc": fx_gain_acc,
        "vat_acc": vat_acc,
        "wht_acc": wht_acc,
        "discount_acc": discount_acc,
        "dept": dept,
        "job": job,
        "loc": loc,
        "employee1": employee1,
        "employee2": employee2,
        "supplier": supplier,
        "asset_type": asset_type,
    }


@pytest.mark.django_db
class TestCustodyPhase6AcceptanceAndResilience:
    """مجموعة اختبارات القبول المحاسبي والصلابة البرمجية لمرحلة 6"""

    def test_purchase_return_refund_collected_mathematical_accuracy(self, p6_setup):
        """
        6.1.1: اختبار استرداد نقدية المرتجع (refunds_collected_amount):
        - التحقق من زيادة النقدية المتاحة بالعهدة.
        - تحديث رصيد السلفة بدقة متناهية بالقرش.
        - ترحيل القيد المتزن (مدين للعهدة 11130 ودائن للمورد 21110).
        """
        s = p6_setup
        adv = EmployeeCustodyAdvance.objects.create(
            advance_number="CADV-P6-REFUND-01",
            employee=s["employee1"],
            user=s["user"],
            source_treasury=s["treasury_acc"],
            amount=Decimal("10000.00"),
            currency=s["egp"],
            due_date=date(2026, 12, 31),
            purpose="شراء مستلزمات موقع مع احتمال مرتجع",
            status=CustodyAdvanceStatus.PENDING_APPROVAL,
        )
        CustodyManagementService.disburse_advance(advance=adv, disbursed_by_user=s["user"])
        assert adv.current_balance == Decimal("10000.00")

        # تسوية تحتوي على منصرف 6000 ومرتجع نقدي مسترد من مورد 1500
        settlement = PettyCashSettlement.objects.create(
            settlement_number="CSET-P6-REFUND-01",
            custody_advance=adv,
            employee=s["employee1"],
            settlement_date=date(2026, 3, 15),
            status=SettlementStatus.SUBMITTED,
            submitted_by=s["user"],
        )
        # سطر مصروف 6,000
        PettyCashSettlementLine.objects.create(
            settlement=settlement,
            line_number=1,
            line_type=SettlementLineType.DIRECT_EXPENSE,
            expense_account=s["expense_acc"],
            currency=s["egp"],
            amount=Decimal("6000.00"),
            status=SettlementLineStatus.APPROVED,
        )
        # سطر مردود مشتريات نقدي مسترد بالعهدة 1,500
        PettyCashSettlementLine.objects.create(
            settlement=settlement,
            line_number=2,
            line_type=SettlementLineType.PURCHASE_REFUND,
            supplier=s["supplier"],
            currency=s["egp"],
            amount=Decimal("1500.00"),
            status=SettlementLineStatus.APPROVED,
        )

        entry = CustodyManagementService.post_settlement(settlement=settlement, approved_by_user=s["user"])
        assert entry is not None
        assert entry.is_posted is True
        assert settlement.status == SettlementStatus.POSTED

        # التحقق الحسابي للأثر الفعلي
        assert settlement.refunds_collected == Decimal("1500.00")
        assert settlement.expenses_absorbed == Decimal("6000.00")

        adv.refresh_from_db()
        assert adv.refunds_collected_amount == Decimal("1500.00")
        assert adv.settled_amount == Decimal("6000.00")
        # الرصيد المتبقي = 10,000 + 1,500 - 6,000 = 5,500.00
        assert adv.current_balance == Decimal("5500.00")
        assert adv.status == CustodyAdvanceStatus.PARTIALLY_SETTLED

        # التحقق من اتزان بنود قيد المرتجع
        crd_supplier = entry.lines.filter(account__code__startswith="21110").first()
        assert crd_supplier is not None
        assert crd_supplier.credit == Decimal("1500.00")

        deb_total = sum(l.debit for l in entry.lines.all())
        crd_total = sum(l.credit for l in entry.lines.all())
        assert deb_total == crd_total

    def test_per_diem_split_advance_and_principal_isolation(self, p6_setup):
        """
        6.1.2: اختبار فصل بدل السفر المقطوع وتثبيت أصل التمويل (settlement_principal_amount):
        - صرف عهدة 10000 منها 2000 بدل مقطوع (يحمل فوراً لمصروف 51100).
        - أصل التمويل الخاضع للتسوية يثبت عند 8000.
        - صمود الرصيد عند استدعاء update_balance.
        - استهلاك المصروفات حتى 8000 يقفل السلفة بالكامل دون تحميل موظف أو ارتداد.
        - الرفض الصارم إذا كان بدل السفر >= مبلغ العهدة.
        """
        s = p6_setup
        adv = EmployeeCustodyAdvance.objects.create(
            advance_number="CADV-P6-PERDIEM-01",
            employee=s["employee1"],
            user=s["user"],
            source_treasury=s["treasury_acc"],
            amount=Decimal("10000.00"),
            is_per_diem_split=True,
            per_diem_amount=Decimal("2000.00"),
            currency=s["egp"],
            due_date=date(2026, 12, 31),
            purpose="مأمورية ميدانية مع بدل سفر يومي",
            status=CustodyAdvanceStatus.PENDING_APPROVAL,
        )

        entry = CustodyManagementService.disburse_advance(advance=adv, disbursed_by_user=s["user"])
        assert entry is not None
        assert entry.is_posted is True
        adv.refresh_from_db()

        # أصل التمويل مثبت عند 8000 ورصيد العهدة 8000
        assert adv.settlement_principal_amount == Decimal("8000.00")
        assert adv.current_balance == Decimal("8000.00")
        assert adv.status == CustodyAdvanceStatus.ACTIVE

        # اختبار صمود update_balance ضد الارتداد للـ 10000
        adv.update_balance()
        assert adv.current_balance == Decimal("8000.00")

        # التحقق من سطور قيد الصرف الثلاثية
        lines = entry.lines.all()
        assert lines.count() == 3
        deb_travel = lines.filter(account=s["expense_acc"]).first()
        deb_custody = lines.filter(account=s["custody_adv_acc"]).first()
        crd_treasury = lines.filter(account=s["treasury_acc"]).first()

        assert deb_travel.debit == Decimal("2000.00")
        assert deb_custody.debit == Decimal("8000.00")
        assert crd_treasury.credit == Decimal("10000.00")

        # تسوية المصروفات بمبلغ 8000 يغلق السلفة بنجاح
        settlement = PettyCashSettlement.objects.create(
            settlement_number="CSET-P6-PERDIEM-01",
            custody_advance=adv,
            employee=s["employee1"],
            settlement_date=date(2026, 3, 20),
            status=SettlementStatus.SUBMITTED,
            submitted_by=s["user"],
        )
        PettyCashSettlementLine.objects.create(
            settlement=settlement,
            line_number=1,
            line_type=SettlementLineType.DIRECT_EXPENSE,
            expense_account=s["expense_acc"],
            currency=s["egp"],
            amount=Decimal("8000.00"),
            status=SettlementLineStatus.APPROVED,
        )
        CustodyManagementService.post_settlement(settlement=settlement, approved_by_user=s["user"])
        adv.refresh_from_db()
        assert adv.current_balance == Decimal("0.00")
        assert adv.status == CustodyAdvanceStatus.SETTLED

        # اختبار رفض صرف عهدة ببدل مقطوع >= المبلغ الإجمالي
        adv_invalid = EmployeeCustodyAdvance.objects.create(
            advance_number="CADV-P6-INVALID-PERDIEM",
            employee=s["employee1"],
            user=s["user"],
            source_treasury=s["treasury_acc"],
            amount=Decimal("5000.00"),
            is_per_diem_split=True,
            per_diem_amount=Decimal("5000.00"),
            currency=s["egp"],
            due_date=date(2026, 12, 31),
            status=CustodyAdvanceStatus.PENDING_APPROVAL,
        )
        with pytest.raises(ValidationError, match="مبلغ بدل السفر المقطوع يجب أن يكون أقل من إجمالي مبلغ العهدة"):
            CustodyManagementService.disburse_advance(advance=adv_invalid, disbursed_by_user=s["user"])

    def test_multi_currency_purchase_settlement_signature_and_subledger(self, p6_setup):
        """
        6.1.3: اختبار سداد فاتورة مشتريات بالدولار USD من عهدة محلية EGP:
        - استدعاء calculate_payment_settlement بالمعاملات الدقيقة.
        - إنشاء PurchasePayment مع الحقول المحمية وربط الأستاذ المساعد للمورد.
        - قيد فروق الصرف المحققة عند اختلاف سعر صرف التسوية عن الفاتورة.
        - تحديث حالة الفاتورة.
        """
        s = p6_setup
        adv = EmployeeCustodyAdvance.objects.create(
            advance_number="CADV-P6-FX-01",
            employee=s["employee1"],
            user=s["user"],
            source_treasury=s["treasury_acc"],
            amount=Decimal("20000.00"),
            settlement_principal_amount=Decimal("20000.00"),
            current_balance=Decimal("20000.00"),
            currency=s["egp"],
            due_date=date(2026, 12, 31),
            status=CustodyAdvanceStatus.ACTIVE,
        )

        # فاتورة مشتريات بقيمة 100 USD ومسجلة بسعر صرف 48.00 EGP (المعادل الدفتري 4,800 EGP)
        purchase = Purchase.objects.create(
            number="PO-P6-FX-USD-01",
            supplier=s["supplier"],
            date=date(2026, 3, 1),
            currency=s["usd"],
            exchange_rate=Decimal("48.000000"),
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
            status="confirmed",
            created_by=s["user"],
        )

        settlement = PettyCashSettlement.objects.create(
            settlement_number="CSET-P6-FX-01",
            custody_advance=adv,
            employee=s["employee1"],
            currency=s["egp"],
            settlement_date=date(2026, 3, 25),
            status=SettlementStatus.SUBMITTED,
            submitted_by=s["user"],
        )

        # سطر تسوية الفاتورة بسعر الصرف الحالي 50.00 EGP
        # المنصرف الفعلي من العهدة = 100 * 50 = 5,000 EGP
        # الفاتورة الدفترية = 100 * 48 = 4,800 EGP
        # فرق العملة = 200 EGP (خسائر فروق عملة FX Loss)
        PettyCashSettlementLine.objects.create(
            settlement=settlement,
            line_number=1,
            line_type=SettlementLineType.SUPPLIER_INVOICE,
            supplier=s["supplier"],
            purchase_invoice=purchase,
            currency=s["usd"],
            exchange_rate=Decimal("50.000000"),
            amount=Decimal("100.00"),
            status=SettlementLineStatus.APPROVED,
        )

        entry = CustodyManagementService.post_settlement(settlement=settlement, approved_by_user=s["user"])
        assert entry is not None
        assert entry.is_posted is True

        # التحقق من دفعة المشتريات المنشأة
        payment = PurchasePayment.objects.filter(purchase=purchase, source_type="CUSTODY").first()
        assert payment is not None
        assert payment.amount_settled_invoice_currency == Decimal("100.00")
        assert payment.amount_paid_currency == Decimal("5000.00")
        assert payment.realized_fx_difference == Decimal("200.00")
        assert payment.status == "posted"

        purchase.refresh_from_db()
        assert purchase.payment_status == "paid"

        # التحقق من قيد خسائر فروق الصرف (200 EGP)
        fx_line = entry.lines.filter(account=s["fx_loss_acc"]).first()
        assert fx_line is not None
        assert fx_line.debit == Decimal("200.00")

        # التحقق من انخفاض رصيد العهدة بـ 5,000 EGP
        adv.refresh_from_db()
        assert adv.current_balance == Decimal("15000.00")

    def test_physical_inventory_count_gl_balance_and_variance(self, p6_setup):
        """
        6.1.4: اختبار محضر الجرد الفعلي ورصيد الأستاذ العام المقطوع بالتاريخ وحساب الفروق:
        - التحقق من دقة قراءة الرصيد الدفتري المقطوع بتاريخ الجرد.
        - تصنيف الفارق الرياضي (عجز / مطابقة / زيادة).
        """
        s = p6_setup
        # تمويل رصيد الصندوق المستديم 11135 بمبلغ 7,000 EGP
        _fund_account(s["custody_perm_acc"], Decimal("7000.00"), s["egp"], s["period"], s["asset_type"])

        # 1. مطابقة تامة (Matched)
        count_matched = PettyCashCount.objects.create(
            count_number="CCNT-P6-MATCHED",
            custody_account=s["custody_perm_acc"],
            employee=s["employee1"],
            auditor=s["user"],
            gl_balance=Decimal("7000.00"),
            actual_cash_amount=Decimal("5000.00"),
            pending_vouchers_amount=Decimal("2000.00"),
        )
        res_m = CustodyManagementService.record_petty_cash_count(count_matched, denominations_data={"200": 25})
        assert res_m.variance_amount == Decimal("0.00")
        assert res_m.variance_type == "matched"

        # 2. عجز نقدي (Shortage)
        count_short = PettyCashCount.objects.create(
            count_number="CCNT-P6-SHORT",
            custody_account=s["custody_perm_acc"],
            employee=s["employee1"],
            auditor=s["user"],
            gl_balance=Decimal("7000.00"),
            actual_cash_amount=Decimal("4600.00"),
            pending_vouchers_amount=Decimal("2000.00"),
        )
        res_s = CustodyManagementService.record_petty_cash_count(count_short, denominations_data={"200": 23})
        assert res_s.variance_amount == Decimal("-400.00")
        assert res_s.variance_type == "shortage"

        # 3. زيادة نقدية (Overage)
        count_over = PettyCashCount.objects.create(
            count_number="CCNT-P6-OVER",
            custody_account=s["custody_perm_acc"],
            employee=s["employee1"],
            auditor=s["user"],
            gl_balance=Decimal("7000.00"),
            actual_cash_amount=Decimal("5300.00"),
            pending_vouchers_amount=Decimal("2000.00"),
        )
        res_o = CustodyManagementService.record_petty_cash_count(count_over, denominations_data={"200": 26, "100": 1})
        assert res_o.variance_amount == Decimal("300.00")
        assert res_o.variance_type == "overage"

    def test_zero_and_negative_amounts_strict_rejection(self, p6_setup):
        """
        6.1.5: اختبار الرفض الصارم للمبالغ الصفرية والسالبة:
        - صرف سلفة بمبلغ 0 أو سالب.
        - تعزيز سلفة بمبلغ 0 أو سالب.
        - مناقلة عهدة بمبلغ 0 أو سالب.
        - رد نقدية بمبلغ سالب.
        """
        s = p6_setup
        adv_zero = EmployeeCustodyAdvance(
            advance_number="CADV-ZERO",
            employee=s["employee1"],
            user=s["user"],
            source_treasury=s["treasury_acc"],
            currency=s["egp"],
            amount=Decimal("0.00"),
            due_date=date(2026, 12, 31),
        )
        with pytest.raises(ValidationError):
            adv_zero.clean()

        adv_neg = EmployeeCustodyAdvance(
            advance_number="CADV-NEG",
            employee=s["employee1"],
            user=s["user"],
            source_treasury=s["treasury_acc"],
            currency=s["egp"],
            amount=Decimal("-100.00"),
            due_date=date(2026, 12, 31),
        )
        with pytest.raises(ValidationError):
            adv_neg.clean()

        # سلفة نشطة سليمة لاختبار باقي الدوال
        adv_valid = EmployeeCustodyAdvance.objects.create(
            advance_number="CADV-VALID-01",
            employee=s["employee1"],
            user=s["user"],
            source_treasury=s["treasury_acc"],
            currency=s["egp"],
            amount=Decimal("5000.00"),
            settlement_principal_amount=Decimal("5000.00"),
            current_balance=Decimal("5000.00"),
            due_date=date(2026, 12, 31),
            status=CustodyAdvanceStatus.ACTIVE,
        )

        # تعزيز بمبلغ 0
        with pytest.raises(ValidationError, match="أكبر من الصفر"):
            CustodyManagementService.top_up_advance(
                advance=adv_valid,
                amount=Decimal("0.00"),
                treasury_account=s["treasury_acc"],
                user=s["user"],
            )

        # مناقلة بمبلغ سالب
        trf_neg = CustodyTransfer(
            transfer_number="CTRF-NEG",
            from_employee=s["employee1"],
            to_employee=s["employee2"],
            from_advance=adv_valid,
            currency=s["egp"],
            amount=Decimal("-500.00"),
        )
        with pytest.raises(ValidationError):
            trf_neg.clean()

        # تسوية مع نقدية مردودة سالبة
        set_neg_cash = PettyCashSettlement(
            settlement_number="CSET-NEG-CASH",
            custody_advance=adv_valid,
            employee=s["employee1"],
            currency=s["egp"],
            cash_returned_to_treasury=Decimal("-200.00"),
            status=SettlementStatus.SUBMITTED,
        )
        with pytest.raises(ValidationError):
            set_neg_cash.clean()

    def test_outflow_under_lock_and_treasury_sufficiency(self, p6_setup):
        """
        6.1.6: اختبار حوكمة التدفق الخارج تحت القفل الذري وكفاية رصيد الخزينة:
        - منع ترحيل تسوية يتجاوز مجموع تدفقاتها الخارجة (مصروفات + رد نقدية + عجز) الرصيد المتاح تحت القفل.
        - منع صرف سلفة من خزينة رصيدها لا يكفي.
        """
        s = p6_setup
        adv = EmployeeCustodyAdvance.objects.create(
            advance_number="CADV-LOCK-01",
            employee=s["employee1"],
            user=s["user"],
            source_treasury=s["treasury_acc"],
            currency=s["egp"],
            amount=Decimal("3000.00"),
            settlement_principal_amount=Decimal("3000.00"),
            current_balance=Decimal("3000.00"),
            due_date=date(2026, 12, 31),
            status=CustodyAdvanceStatus.ACTIVE,
        )

        settlement = PettyCashSettlement.objects.create(
            settlement_number="CSET-LOCK-OVERFLOW",
            custody_advance=adv,
            employee=s["employee1"],
            currency=s["egp"],
            settlement_date=date(2026, 3, 28),
            status=SettlementStatus.SUBMITTED,
            submitted_by=s["user"],
            # رد نقدية 2,000 + عجز 1,500 = 3,500 > 3,000 رصيد السلفة
            cash_returned_to_treasury=Decimal("2000.00"),
            shortage_amount=Decimal("1500.00"),
        )

        with pytest.raises(ValidationError):
            CustodyManagementService.post_settlement(settlement=settlement, approved_by_user=s["user"])

        # كفاية رصيد الخزينة: محاولة صرف سلفة بمبلغ 999,999 من خزينة رصيدها 500,000
        adv_huge = EmployeeCustodyAdvance.objects.create(
            advance_number="CADV-HUGE-01",
            employee=s["employee1"],
            user=s["user"],
            source_treasury=s["treasury_acc"],
            currency=s["egp"],
            amount=Decimal("999999.00"),
            due_date=date(2026, 12, 31),
            status=CustodyAdvanceStatus.PENDING_APPROVAL,
        )
        with pytest.raises(ValidationError):
            CustodyManagementService.disburse_advance(advance=adv_huge, disbursed_by_user=s["user"])

    def test_shortage_routing_settlement_and_count(self, p6_setup):
        """
        6.1.7: اختبار مسارات معالجة العجز:
        - عجز التسوية المحمل على راتب الموظف (11230).
        - عدم التكرار أو التحميل المزدوج في فحص إخلاء طرف HR.
        - عجز الجرد المعالج كخصم من الراتب (hr_deduction) مقابل المعالج كخسائر (expense_loss 54900).
        """
        s = p6_setup
        adv = EmployeeCustodyAdvance.objects.create(
            advance_number="CADV-SHORTAGE-01",
            employee=s["employee1"],
            user=s["user"],
            source_treasury=s["treasury_acc"],
            currency=s["egp"],
            amount=Decimal("5000.00"),
            settlement_principal_amount=Decimal("5000.00"),
            current_balance=Decimal("5000.00"),
            due_date=date(2026, 12, 31),
            status=CustodyAdvanceStatus.ACTIVE,
        )

        settlement = PettyCashSettlement.objects.create(
            settlement_number="CSET-SHORTAGE-01",
            custody_advance=adv,
            employee=s["employee1"],
            currency=s["egp"],
            settlement_date=date(2026, 3, 29),
            status=SettlementStatus.SUBMITTED,
            submitted_by=s["user"],
            shortage_amount=Decimal("1000.00"),
        )
        # مصروفات معتمدة 4,000
        PettyCashSettlementLine.objects.create(
            settlement=settlement,
            line_number=1,
            line_type=SettlementLineType.DIRECT_EXPENSE,
            expense_account=s["expense_acc"],
            currency=s["egp"],
            amount=Decimal("4000.00"),
            status=SettlementLineStatus.APPROVED,
        )

        entry = CustodyManagementService.post_settlement(settlement=settlement, approved_by_user=s["user"])
        assert entry is not None

        # التحقق من قيد العجز على حساب سلف الموظفين 11230
        hr_line = entry.lines.filter(account=s["hr_emp_acc"]).first()
        assert hr_line is not None
        assert hr_line.debit == Decimal("1000.00")

        adv.refresh_from_db()
        assert adv.shortage_amount == Decimal("1000.00")
        assert adv.settled_amount == Decimal("4000.00")
        assert adv.current_balance == Decimal("0.00")
        assert adv.status == CustodyAdvanceStatus.SETTLED

        # فحص إخلاء الطرف بموديول HR: رصيد العهدة أصبح 0 ولا يوجد تحميل مزدوج
        clearance = EmployeeService.check_custody_clearance(s["employee1"])
        assert clearance["unsettled_advances_count"] == 0
        assert clearance["pending_cash_balance"] == Decimal("0.00")
        assert clearance["is_cleared"] is True

        # اختبار تسوية عجز الجرد عبر adjust_count:
        # 1. مسار hr_deduction
        cnt_hr = PettyCashCount.objects.create(
            count_number="CCNT-ADJ-HR",
            custody_account=s["custody_perm_acc"],
            employee=s["employee1"],
            auditor=s["user"],
            gl_balance=Decimal("3000.00"),
            actual_cash_amount=Decimal("2500.00"),
            variance_amount=Decimal("-500.00"),
            variance_type="shortage",
            status="audited",
        )
        entry_hr = CustodyManagementService.adjust_count(cnt_hr, user=s["user"], variance_routing="hr_deduction")
        assert entry_hr is not None
        deb_hr = entry_hr.lines.filter(account=s["hr_emp_acc"]).first()
        assert deb_hr is not None
        assert deb_hr.debit == Decimal("500.00")

        # 2. مسار expense_loss
        cnt_loss = PettyCashCount.objects.create(
            count_number="CCNT-ADJ-LOSS",
            custody_account=s["custody_perm_acc"],
            employee=s["employee1"],
            auditor=s["user"],
            gl_balance=Decimal("3000.00"),
            actual_cash_amount=Decimal("2700.00"),
            variance_amount=Decimal("-300.00"),
            variance_type="shortage",
            status="audited",
        )
        entry_loss = CustodyManagementService.adjust_count(cnt_loss, user=s["user"], variance_routing="expense_loss")
        assert entry_loss is not None
        deb_loss = entry_loss.lines.filter(account=s["loss_acc"]).first()
        assert deb_loss is not None
        assert deb_loss.debit == Decimal("300.00")

    def test_transaction_rollback_resiliency_on_step_failure(self, p6_setup):
        """
        6.3.1: اختبار صلابة التراجع عند الفشل الذري (Atomic Rollback Resiliency):
        - محاكاة فشل في خطوة متقدمة أثناء الترحيل (مثل عطل بتسجيل الأستاذ المساعد).
        - التأكد من عدم إنشاء أي قيود جزئية أو بقاء السلفة بحالة ملوثة.
        - بقاء التسوية بحالة SUBMITTED ورصيد السلفة كما هو دون تعديل.
        """
        s = p6_setup
        adv = EmployeeCustodyAdvance.objects.create(
            advance_number="CADV-ROLLBACK-01",
            employee=s["employee1"],
            user=s["user"],
            source_treasury=s["treasury_acc"],
            currency=s["egp"],
            amount=Decimal("12000.00"),
            settlement_principal_amount=Decimal("12000.00"),
            current_balance=Decimal("12000.00"),
            due_date=date(2026, 12, 31),
            status=CustodyAdvanceStatus.ACTIVE,
        )

        settlement = PettyCashSettlement.objects.create(
            settlement_number="CSET-ROLLBACK-01",
            custody_advance=adv,
            employee=s["employee1"],
            currency=s["egp"],
            settlement_date=date(2026, 3, 30),
            status=SettlementStatus.SUBMITTED,
            submitted_by=s["user"],
        )
        PettyCashSettlementLine.objects.create(
            settlement=settlement,
            line_number=1,
            line_type=SettlementLineType.DIRECT_EXPENSE,
            expense_account=s["expense_acc"],
            currency=s["egp"],
            amount=Decimal("4000.00"),
            status=SettlementLineStatus.APPROVED,
        )

        entries_count_before = JournalEntry.objects.count()

        # محاكاة إلقاء خطأ في مرحلة إنشاء مسودة القيد
        with patch.object(LedgerCoreService, "create_draft_entry", side_effect=RuntimeError("Simulated DB connection failure")):
            with pytest.raises(RuntimeError, match="Simulated DB connection failure"):
                CustodyManagementService.post_settlement(settlement=settlement, approved_by_user=s["user"])

        # التأكد التام من التراجع الكامل
        adv.refresh_from_db()
        settlement.refresh_from_db()
        assert adv.current_balance == Decimal("12000.00")
        assert adv.settled_amount == Decimal("0.00")
        assert settlement.status == SettlementStatus.SUBMITTED
        assert settlement.journal_entry is None
        assert JournalEntry.objects.count() == entries_count_before

    def test_symmetric_safe_reversal_and_idempotency(self, p6_setup):
        """
        6.3.2: اختبار العكس الآمن المتناظر والحماية من التكرار (Idempotency):
        - ترحيل تسوية كاملة تحتوي على مصروف ونقدية مردودة وعجز.
        - عكس التسوية عبر reverse_settlement.
        - استعادة كافة العدادات والرصيد بدقة 100%.
        - رفض تكرار عكس تسوية سبق عكسها.
        """
        s = p6_setup
        adv = EmployeeCustodyAdvance.objects.create(
            advance_number="CADV-SYMM-REV-01",
            employee=s["employee1"],
            user=s["user"],
            source_treasury=s["treasury_acc"],
            currency=s["egp"],
            amount=Decimal("15000.00"),
            settlement_principal_amount=Decimal("15000.00"),
            current_balance=Decimal("15000.00"),
            due_date=date(2026, 12, 31),
            status=CustodyAdvanceStatus.ACTIVE,
        )

        settlement = PettyCashSettlement.objects.create(
            settlement_number="CSET-SYMM-REV-01",
            custody_advance=adv,
            employee=s["employee1"],
            currency=s["egp"],
            settlement_date=date(2026, 3, 31),
            cash_returned_to_treasury=Decimal("2000.00"),
            shortage_amount=Decimal("1000.00"),
            status=SettlementStatus.SUBMITTED,
            submitted_by=s["user"],
        )
        PettyCashSettlementLine.objects.create(
            settlement=settlement,
            line_number=1,
            line_type=SettlementLineType.DIRECT_EXPENSE,
            expense_account=s["expense_acc"],
            currency=s["egp"],
            amount=Decimal("5000.00"),
            status=SettlementLineStatus.APPROVED,
        )

        CustodyManagementService.post_settlement(settlement=settlement, approved_by_user=s["user"])
        adv.refresh_from_db()
        assert adv.settled_amount == Decimal("5000.00")
        assert adv.returned_cash_amount == Decimal("2000.00")
        assert adv.shortage_amount == Decimal("1000.00")
        # 15000 - 5000 - 2000 - 1000 = 7000
        assert adv.current_balance == Decimal("7000.00")

        # تنفيذ العكس المحاسبي المعتمد
        rev_entry = CustodyManagementService.reverse_settlement(
            settlement=settlement,
            approved_by_user=s["user"],
            reason="خطأ في مطابقة الفواتير المرفقة",
        )
        assert rev_entry is not None
        assert rev_entry.is_posted is True

        settlement.refresh_from_db()
        assert settlement.status == SettlementStatus.REVERSED
        assert settlement.reversal_entry == rev_entry

        adv.refresh_from_db()
        # استرجاع العدادات المتناظر 100%
        assert adv.settled_amount == Decimal("0.00")
        assert adv.returned_cash_amount == Decimal("0.00")
        assert adv.shortage_amount == Decimal("0.00")
        assert adv.current_balance == Decimal("15000.00")
        assert adv.status == CustodyAdvanceStatus.ACTIVE

        # حماية التكرار (Idempotency): محاولة عكس تسوية تم عكسها بالفعل يجب أن ترمي ValidationError
        with pytest.raises(ValidationError):
            CustodyManagementService.reverse_settlement(
                settlement=settlement,
                approved_by_user=s["user"],
                reason="محاولة عكس ثانية غير مصرحة",
            )
