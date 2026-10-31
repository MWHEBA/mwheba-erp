# -*- coding: utf-8 -*-
"""
Suite for Phase 3 (Sprint 3) - Cheque Portfolio Integration, Amortization, & Contra Settlements
اختبارات شاملة لمحفظة الشيكات، التغطية الورقية، استبدال الشيكات، إطفاء الفوائد، ومقاصة الموردين
"""
from decimal import Decimal
import pytest
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from customer.models import Customer
from supplier.models import Supplier
from financial.models import Currency, ChartOfAccounts, AccountType
from sale.models import Sale, SaleItem
from sale.models.installments import (
    InstallmentPlan,
    InstallmentItem,
    InstallmentCashStatus,
    PaperCoverage,
    PlanStatus,
    InstallmentSettlement,
)
from cheques.models import (
    Cheque,
    ChequeType,
    ChequeStatus,
    ChequePurpose,
    AllocationStatus,
)
from cheques.services.allocation_service import ChequeAllocationService
from cheques.services.swap_service import ChequeSwapService
from cheques.services.dual_signature_service import DualSignatureService
from cheques.services.commission_clawback_service import CommissionClawbackHook
from cheques.services.accounting_service import ChequeAccountingService
from financial.services.installment_amortization_service import InstallmentInterestAmortizationService
from financial.services.contra_settlement_service import PartnerContraSettlementService
from sale.services.custody_clearance_service import CustodyClearanceService
from sale.services.instapay_matcher_service import InstaPayMatcherService

User = get_user_model()


@pytest.fixture
def auth_user(db):
    return User.objects.create_user(
        username="phase3_tester",
        email="p3@mwheba.com",
        password="password123",
        first_name="Ahmed",
        last_name="Financial",
        is_staff=True,
        is_superuser=True
    )


@pytest.fixture
def base_currency(db):
    curr, _ = Currency.objects.get_or_create(
        code="EGP",
        defaults={
            "name": "Egyptian Pound",
            "symbol": "ج.م",
            "is_active": True,
            "is_functional": True
        }
    )
    return curr


@pytest.fixture(autouse=True)
def financial_setup(db, base_currency):
    asset_type, _ = AccountType.objects.get_or_create(
        code="ASSET", defaults={"name": "أصول", "category": "asset", "nature": "debit"}
    )
    liab_type, _ = AccountType.objects.get_or_create(
        code="LIAB", defaults={"name": "خصوم", "category": "liability", "nature": "credit"}
    )
    rev_type, _ = AccountType.objects.get_or_create(
        code="REV", defaults={"name": "إيرادات", "category": "revenue", "nature": "credit"}
    )

    ChartOfAccounts.objects.get_or_create(
        code="11010",
        defaults={"name": "الخزينة الرئيسية", "account_type": asset_type, "is_active": True}
    )
    ChartOfAccounts.objects.get_or_create(
        code="11020",
        defaults={"name": "البنك التجاري", "account_type": asset_type, "is_active": True, "is_bank_account": True}
    )
    ChartOfAccounts.objects.get_or_create(
        code="11220",
        defaults={"name": "أوراق القبض", "account_type": asset_type, "is_active": True}
    )
    ChartOfAccounts.objects.get_or_create(
        code="11190",
        defaults={"name": "شيكات برسم التحصيل", "account_type": asset_type, "is_active": True}
    )
    ChartOfAccounts.objects.get_or_create(
        code="21110",
        defaults={"name": "موردون تجاريون", "account_type": liab_type, "is_active": True}
    )
    ChartOfAccounts.objects.get_or_create(
        code="21120",
        defaults={"name": "أوراق الدفع", "account_type": liab_type, "is_active": True}
    )
    ChartOfAccounts.objects.get_or_create(
        code="21400",
        defaults={"name": "فوائد تقسيط غير محققة", "account_type": liab_type, "is_active": True}
    )
    ChartOfAccounts.objects.get_or_create(
        code="42200",
        defaults={"name": "إيرادات فوائد تقسيط محققة", "account_type": rev_type, "is_active": True}
    )


@pytest.fixture
def base_customer(db, auth_user):
    return Customer.objects.create(
        name="عميل اختبار سبرنت 3",
        code="CUST-P3-001",
        created_by=auth_user
    )


@pytest.fixture
def base_supplier(db, auth_user):
    return Supplier.objects.create(
        name="مورد ورق كرتون تجريبي",
        code="SUPP-P3-001",
        created_by=auth_user
    )


@pytest.fixture
def installment_sale_and_plan(db, base_customer, base_currency, auth_user):
    sale = Sale.objects.create(
        customer=base_customer,
        currency=base_currency,
        date=timezone.localdate(),
        number="INV-P3-1001",
        subtotal=Decimal("60000.00"),
        total=Decimal("60000.00"),
        tax=Decimal("0.00"),
        is_installment_sale=True,
        markup_amount=Decimal("6000.00"),
        markup_rate=Decimal("0.10"),
        contract_total=Decimal("66000.00"),
        created_by=auth_user
    )
    plan = InstallmentPlan.objects.create(
        sale=sale,
        customer=base_customer,
        plan_type="EQUAL_SPREAD",
        number_of_installments=3,
        start_date=timezone.localdate(),
        total_principal=Decimal("60000.00"),
        total_markup=Decimal("6000.00"),
        total_amount=Decimal("66000.00"),
        status=PlanStatus.ACTIVE,
        created_by=auth_user
    )
    # Tranches of 22,000 each (20,000 principal + 2,000 interest)
    items = []
    today = timezone.localdate()
    for i in range(1, 4):
        item = InstallmentItem.objects.create(
            plan=plan,
            installment_number=i,
            due_date=today + timezone.timedelta(days=30 * i),
            principal_amount=Decimal("20000.00"),
            interest_amount=Decimal("2000.00"),
            total_amount=Decimal("22000.00"),
            cash_status=InstallmentCashStatus.PENDING,
            paper_coverage=PaperCoverage.UNCOVERED
        )
        items.append(item)
    return sale, plan, items


def make_cheque(customer, currency, user, **kwargs):
    today = timezone.localdate()
    defaults = {
        "voucher_number": f"CHQ-TEST-{kwargs.get('cheque_number', '1001')}",
        "cheque_number": "999001",
        "cheque_type": ChequeType.RECEIVABLE,
        "customer": customer,
        "currency": currency,
        "amount": Decimal("22000.00"),
        "issue_date": today,
        "due_date": today + timezone.timedelta(days=30),
        "status": ChequeStatus.IN_PORTFOLIO,
        "created_by": user,
    }
    defaults.update(kwargs)
    return Cheque.objects.create(**defaults)


@pytest.mark.django_db
class TestChequeAllocationAndCoverage:
    """اختبارات تخصيص الشيكات والتغطية الورقية والسقف المشترك"""

    def test_allocate_cheque_to_installment_success(self, base_customer, base_currency, installment_sale_and_plan, auth_user):
        sale, plan, items = installment_sale_and_plan
        item1 = items[0]

        cheque = make_cheque(
            customer=base_customer,
            currency=base_currency,
            user=auth_user,
            voucher_number="CHQ-P3-001",
            cheque_number="998811",
            amount=Decimal("22000.00"),
            due_date=item1.due_date,
        )

        alloc = ChequeAllocationService.allocate_cheque_to_invoice(
            cheque=cheque,
            sale=sale,
            amount=Decimal("22000.00"),
            installment_item=item1,
            user=auth_user
        )

        assert alloc.installment_item_id == item1.id
        assert alloc.allocated_amount == Decimal("22000.00")
        assert alloc.allocation_status == AllocationStatus.APPLIED

        item1.refresh_from_db()
        assert item1.paper_coverage == PaperCoverage.PORTFOLIO_CHEQUE
        assert item1.coverage_cheque_amount == Decimal("22000.00")
        assert cheque in item1.cheques.all()

    def test_shared_cheque_allocation_ceiling_guard(self, base_customer, base_currency, installment_sale_and_plan, auth_user):
        sale, plan, items = installment_sale_and_plan
        item1 = items[0]

        # الشيك بـ 30,000 ولكن تم حجز 15,000 كدفعة مقدمة
        cheque = make_cheque(
            customer=base_customer,
            currency=base_currency,
            user=auth_user,
            voucher_number="CHQ-P3-002",
            cheque_number="998812",
            amount=Decimal("30000.00"),
            prepaid_allocated_amount=Decimal("15000.00"),
            due_date=item1.due_date,
        )

        # المتاح في الشيك = 15,000 فقط. محاولة تخصيص 20,000 يجب أن تفشل بحارس السقف المشترك
        with pytest.raises(ValidationError) as exc_info:
            ChequeAllocationService.allocate_cheque_to_invoice(
                cheque=cheque,
                sale=sale,
                amount=Decimal("20000.00"),
                installment_item=item1,
                user=auth_user
            )
        assert "يتجاوز الرصيد المتاح" in str(exc_info.value)

    def test_cheque_bounce_updates_installment_and_triggers_clawback(self, base_customer, base_currency, installment_sale_and_plan, auth_user):
        sale, plan, items = installment_sale_and_plan
        item1 = items[0]

        cheque = make_cheque(
            customer=base_customer,
            currency=base_currency,
            user=auth_user,
            voucher_number="CHQ-P3-003",
            cheque_number="998813",
            amount=Decimal("22000.00"),
            due_date=item1.due_date,
        )

        ChequeAllocationService.allocate_cheque_to_invoice(
            cheque=cheque,
            sale=sale,
            amount=Decimal("22000.00"),
            installment_item=item1,
            user=auth_user
        )

        # تحصيل ثم ارتداد الشيك عبر ChequeAccountingService
        ChequeAccountingService.bounce_cheque(cheque=cheque, user=auth_user, reason="لا يوجد رصيد كاف")

        item1.refresh_from_db()
        assert item1.cash_status == InstallmentCashStatus.BOUNCED
        assert item1.paper_coverage == PaperCoverage.UNCOVERED
        assert plan.status == PlanStatus.ACTIVE


@pytest.mark.django_db
class TestChequeSwapProtocol:
    """اختبارات استبدال الشيكات الآجلة (ChequeSwapService) وحفظ التدقيق"""

    def test_swap_installment_cheque_success(self, base_customer, base_currency, installment_sale_and_plan, auth_user):
        sale, plan, items = installment_sale_and_plan
        item1 = items[0]

        old_cheque = make_cheque(
            customer=base_customer,
            currency=base_currency,
            user=auth_user,
            voucher_number="CHQ-OLD-001",
            cheque_number="111001",
            amount=Decimal("22000.00"),
            due_date=item1.due_date,
        )

        ChequeAllocationService.allocate_cheque_to_invoice(
            cheque=old_cheque,
            sale=sale,
            amount=Decimal("22000.00"),
            installment_item=item1,
            user=auth_user
        )

        new_due_date = item1.due_date + timezone.timedelta(days=15)
        new_cheque = make_cheque(
            customer=base_customer,
            currency=base_currency,
            user=auth_user,
            voucher_number="CHQ-NEW-001",
            cheque_number="222001",
            amount=Decimal("22000.00"),
            due_date=new_due_date,
        )

        swap_res = ChequeSwapService.swap_installment_cheque(
            old_cheque=old_cheque,
            new_cheque=new_cheque,
            installment_item=item1,
            user=auth_user,
            reason="مد أجل القسط 15 يوم بناء على طلب العميل"
        )

        assert swap_res["status"] == "SUCCESS"

        old_cheque.refresh_from_db()
        new_cheque.refresh_from_db()
        item1.refresh_from_db()

        # عزل أثر الارتداد: الشيك القديم RETURNED_TO_DRAWER وليس BOUNCED
        assert old_cheque.status == ChequeStatus.RETURNED_TO_DRAWER
        assert "[SWAPPED_OUT" in old_cheque.notes

        # تحديث بيانات القسط بالشيك الجديد
        assert item1.due_date == new_due_date
        assert new_cheque in item1.cheques.all()
        assert old_cheque not in item1.cheques.all()
        assert item1.paper_coverage == PaperCoverage.PORTFOLIO_CHEQUE

    def test_swap_rejected_if_cheque_not_in_portfolio(self, base_customer, base_currency, installment_sale_and_plan, auth_user):
        sale, plan, items = installment_sale_and_plan
        item1 = items[0]

        # شيك برسم التحصيل في البنك
        under_collection_cheque = make_cheque(
            customer=base_customer,
            currency=base_currency,
            user=auth_user,
            voucher_number="CHQ-BANK-001",
            cheque_number="111002",
            amount=Decimal("22000.00"),
            status=ChequeStatus.UNDER_COLLECTION,
        )
        new_cheque = make_cheque(
            customer=base_customer,
            currency=base_currency,
            user=auth_user,
            voucher_number="CHQ-NEW-002",
            cheque_number="222002",
            amount=Decimal("22000.00"),
            status=ChequeStatus.IN_PORTFOLIO,
        )

        with pytest.raises(ValidationError) as exc:
            ChequeSwapService.swap_installment_cheque(
                old_cheque=under_collection_cheque,
                new_cheque=new_cheque,
                installment_item=item1,
                user=auth_user
            )
        assert "يُشترط أن يكون الشيك في الحافظة/الخزينة" in str(exc.value)


@pytest.mark.django_db
class TestDualSignatureService:
    """اختبارات التحقق الرقابي للشيكات ذات التوقيع الثنائي"""

    def test_dual_signature_check_and_verification(self, base_customer, base_currency, auth_user):
        # شيك بمبلغ 150,000 يتجاوز سقف 100,000
        large_cheque = make_cheque(
            customer=base_customer,
            currency=base_currency,
            user=auth_user,
            voucher_number="CHQ-LARGE-001",
            cheque_number="555001",
            amount=Decimal("150000.00"),
            status=ChequeStatus.IN_PORTFOLIO,
        )

        check_res = DualSignatureService.check_signature_requirements(large_cheque)
        assert check_res["requires_dual_signature"] is True
        assert check_res["is_pending"] is True
        assert check_res["status_label"] == "CHEQUE_SIGNATURE_PENDING"

        # اعتماد التوقيع الثاني
        updated = DualSignatureService.verify_second_signature(
            cheque=large_cheque,
            user=auth_user,
            signer_name="أ. محمود المدير المالي",
            notes="تم التوقيع والمطابقة مع التوقيعات البنكية"
        )

        updated_check = DualSignatureService.check_signature_requirements(updated)
        assert updated_check["is_verified"] is True
        assert updated_check["is_pending"] is False
        assert updated_check["status_label"] == "AUTHORIZED"


@pytest.mark.django_db
class TestInstallmentInterestAmortizationService:
    """اختبارات المصدر الموحد لإطفاء فوائد التقسيط وحارس الرصيد المؤجل"""

    def test_amortize_interest_creates_balanced_entry(self, installment_sale_and_plan, auth_user):
        sale, plan, items = installment_sale_and_plan
        item1 = items[0]

        entry = InstallmentInterestAmortizationService.amortize_installment_interest(
            installment_item=item1,
            user=auth_user
        )

        assert entry is not None
        item1.refresh_from_db()
        assert item1.is_interest_recognized is True
        assert item1.recognized_interest == Decimal("2000.00")
        assert item1.recognized_interest_entry_id == entry.id

        # التحقق من توازن القيد: مدين 21400 / دائن 42200
        lines = list(entry.lines.all())
        assert len(lines) == 2
        debit_line = next(l for l in lines if l.debit > 0)
        credit_line = next(l for l in lines if l.credit > 0)
        assert debit_line.account.code.startswith("2140")
        assert credit_line.account.code.startswith("4220")
        assert debit_line.debit == Decimal("2000.00")
        assert credit_line.credit == Decimal("2000.00")

    def test_amortizable_interest_guard_prevents_entry_if_waived(self, installment_sale_and_plan, auth_user):
        sale, plan, items = installment_sale_and_plan
        item2 = items[1]

        # إسقاط كامل الفائدة سلفاً (في سداد معجل أو إعفاء)
        item2.waived_interest = Decimal("2000.00")
        item2.save()

        # الحارس يجب أن يمتنع عن إنشاء أي قيد ويتجاوز القسط
        entry = InstallmentInterestAmortizationService.amortize_installment_interest(
            installment_item=item2,
            user=auth_user
        )

        assert entry is None
        item2.refresh_from_db()
        assert item2.is_interest_recognized is False
        assert item2.recognized_interest == Decimal("0.00")


@pytest.mark.django_db
class TestPartnerContraSettlementService:
    """اختبارات مقاصة الموردين مع أقساط العملاء"""

    def test_execute_contra_settlement_success(self, base_supplier, installment_sale_and_plan, auth_user):
        sale, plan, items = installment_sale_and_plan
        item1 = items[0]

        res = PartnerContraSettlementService.execute_contra_settlement(
            installment_item=item1,
            supplier=base_supplier,
            amount=Decimal("22000.00"),
            user=auth_user,
            contra_ref="CONTRA-P3-TEST-01"
        )

        assert res["status"] == "SUCCESS"
        assert res["principal_portion"] == Decimal("20000.00")
        assert res["interest_portion"] == Decimal("2000.00")

        item1.refresh_from_db()
        assert item1.cash_status == InstallmentCashStatus.COLLECTED_CONTRA
        assert item1.paid_amount == Decimal("22000.00")
        assert item1.contra_settlement_reference == "CONTRA-P3-TEST-01"

        # التحقق من قيد المقاصة المتزن: مدين الموردين / دائن العملاء
        contra_je = res["contra_entry"]
        assert contra_je is not None
        lines = list(contra_je.lines.all())
        assert len(lines) == 2
        debit_line = next(l for l in lines if l.debit > 0)
        credit_line = next(l for l in lines if l.credit > 0)
        assert debit_line.debit == Decimal("22000.00")
        assert credit_line.credit == Decimal("22000.00")

        # التحقق من إنشاء تسوية تعاقدية وسند سداد بالفاتورة
        assert InstallmentSettlement.objects.filter(
            installment_item=item1,
            settlement_type=InstallmentSettlement.SettlementType.CONTRA_SETTLEMENT
        ).exists()


@pytest.mark.django_db
class TestCustodyAndInstaPayServices:
    """اختبارات التحصيل الميداني وتوريد العهد، ومطابقة إنستاباي"""

    def test_field_collection_and_custody_clearance(self, installment_sale_and_plan, auth_user):
        sale, plan, items = installment_sale_and_plan
        item1 = items[0]

        # 1. تحصيل ميداني بواسطة محصل -> نقدية بالطريق 11030
        col_res = CustodyClearanceService.record_field_collection(
            installment_item=item1,
            collector=auth_user,
            amount=Decimal("22000.00"),
            user=auth_user,
            receipt_number="REC-P3-001"
        )
        assert col_res["status"] == "SUCCESS"

        item1.refresh_from_db()
        assert item1.cash_status == InstallmentCashStatus.COLLECTED_IN_TRANSIT

        # 2. توريد العهدة للخزينة المركزية -> مدين 11010 / دائن 11030 وتحويل لـ COLLECTED
        clear_res = CustodyClearanceService.clear_daily_custody(
            collector=auth_user,
            user=auth_user
        )
        assert clear_res["status"] == "SUCCESS"
        assert clear_res["cleared_count"] == 1
        assert clear_res["total_cleared"] == Decimal("22000.00")

        item1.refresh_from_db()
        assert item1.cash_status == InstallmentCashStatus.COLLECTED

    def test_instapay_matcher_settles_and_waives_late_penalties(self, installment_sale_and_plan, auth_user):
        sale, plan, items = installment_sale_and_plan
        item1 = items[0]

        # افتراض وجود غرامة تأخير ناتجة عن تأخير المحاسب لكن تاريخ التحويل يسبقها
        item1.penalty_amount = Decimal("300.00")
        item1.save()

        res = InstaPayMatcherService.match_and_settle_installment(
            installment_item=item1,
            instapay_reference="INSTA-REF-889922",
            amount=Decimal("22000.00"),
            transfer_date=item1.due_date,  # حول العميل في ميعاد الاستحقاق
            user=auth_user,
            payer_name="محمد المشتري"
        )

        assert res["status"] == "SUCCESS"
        item1.refresh_from_db()
        assert item1.cash_status == InstallmentCashStatus.COLLECTED
        assert item1.penalty_amount == Decimal("0.00")  # تم إسقاط الغرامة
        assert item1.paid_amount == Decimal("22000.00")
