# -*- coding: utf-8 -*-
"""
Suite for Phase 4 (Sprint 4) - Early Settlement Engine, Curtailment, Dispute/Rework Protocols, & Penalty Waivers
اختبارات شاملة للسداد المعجل بالفرعين أ و ب، وعكس التسويات المركبة، وتقليص العقد، وعيوب التشغيل، وإسقاط الغرامات
"""
from decimal import Decimal
import pytest
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

import uuid
from customer.models import Customer
from sale.models import Sale, SalePayment
from sale.models.sales_models import SalesOrder, DeliveryNote
from product.models.stock_management import Warehouse
from sale.models.installments import (
    InstallmentPlan,
    InstallmentItem,
    InstallmentCashStatus,
    PaperCoverage,
    PlanStatus,
    InstallmentSettlement,
)
from financial.models import Currency, ChartOfAccounts, AccountType
from sale.services.early_settlement_service import EarlySettlementService
from sale.services.settlement_reversal_service import SettlementReversalService
from sale.services.curtailment_service import ContractCurtailmentService
from sale.services.rework_dispute_service import ReworkDisputeService
from sale.services.penalty_waiver_service import PenaltyWaiverService

User = get_user_model()


@pytest.fixture
def auth_user(db):
    return User.objects.create_user(
        username="phase4_tester",
        email="p4@mwheba.com",
        password="password123",
        first_name="Mostafa",
        last_name="Auditor",
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
    exp_type, _ = AccountType.objects.get_or_create(
        code="EXP", defaults={"name": "مصروفات", "category": "expense", "nature": "debit"}
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
        code="21020",
        defaults={"name": "أرصدة دائنة للعملاء", "account_type": liab_type, "is_active": True}
    )
    ChartOfAccounts.objects.get_or_create(
        code="21400",
        defaults={"name": "فوائد تقسيط غير محققة", "account_type": liab_type, "is_active": True}
    )
    ChartOfAccounts.objects.get_or_create(
        code="42200",
        defaults={"name": "إيرادات فوائد تقسيط محققة", "account_type": rev_type, "is_active": True}
    )
    ChartOfAccounts.objects.get_or_create(
        code="53200",
        defaults={"name": "خصم تعجيل سداد تمويلي", "account_type": exp_type, "is_active": True}
    )


@pytest.fixture
def base_customer(db, auth_user):
    return Customer.objects.create(
        name="شركة الأهرام للكرتون (عميل مرحلة 4)",
        code="CUST-P4-001",
        created_by=auth_user
    )


@pytest.fixture
def installment_fixture(db, base_customer, base_currency, auth_user):
    sale = Sale.objects.create(
        customer=base_customer,
        currency=base_currency,
        date=timezone.localdate(),
        number="INV-P4-2001",
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
    # 3 tranches of 20,000 principal + 2,000 interest = 22,000 each
    items = []
    today = timezone.localdate()
    for i in range(1, 4):
        it = InstallmentItem.objects.create(
            plan=plan,
            installment_number=i,
            due_date=today + timezone.timedelta(days=30 * i),
            principal_amount=Decimal("20000.00"),
            interest_amount=Decimal("2000.00"),
            total_amount=Decimal("22000.00"),
            cash_status=InstallmentCashStatus.PENDING,
            paper_coverage=PaperCoverage.UNCOVERED
        )
        items.append(it)
    return sale, plan, items


@pytest.mark.django_db
class TestEarlySettlementEngine:
    """اختبارات محرك السداد المعجل المحاسبي المنضبط"""

    def test_early_settlement_branch_a_cash_payment_with_discount(self, installment_fixture, auth_user):
        sale, plan, items = installment_fixture

        # سداد معجل لكامل الأقساط مع منح خصم تعجيل 1,500 ج.م
        calc = EarlySettlementService.calculate_early_settlement(
            sale=sale,
            early_discount_amount=Decimal("1500.00")
        )

        assert calc["branch"] == 'A'
        assert calc["settlement_principal"] == Decimal("60000.00")
        assert calc["remaining_interest_debt"] == Decimal("6000.00")
        assert calc["customer_real_debt"] == Decimal("66000.00")
        assert calc["discount_amount"] == Decimal("1500.00")
        assert calc["final_cash_required"] == Decimal("58500.00")  # (60,000 - 1,500)
        assert calc["waived_interest_settlement"] == Decimal("6000.00")

        # تنفيذ السداد المعجل
        exec_res = EarlySettlementService.execute_early_settlement(
            sale=sale,
            early_discount_amount=Decimal("1500.00"),
            user=auth_user
        )

        assert exec_res["status"] == "SUCCESS"
        batch_id = exec_res["batch_id"]

        # التحقق من توازن القيد المجمع
        je = exec_res["journal_entry"]
        lines = list(je.lines.all())
        total_debit = sum(l.debit for l in lines)
        total_credit = sum(l.credit for l in lines)
        assert total_debit == total_credit == Decimal("66000.00")

        # فحص أطراف القيد:
        # مدين كاش: 58,500 | مدين خصم (53200): 1,500 | مدين مؤجل (21400): 6,000 | دائن عملاء: 66,000
        cash_debit = sum(l.debit for l in lines if l.account.code in ["11010", "1101"])
        disc_debit = sum(l.debit for l in lines if l.account.code == "53200")
        unearned_debit = sum(l.debit for l in lines if l.account.code == "21400")
        cust_credit = sum(l.credit for l in lines if l.account.code not in ["11010", "1101", "53200", "21400"])

        assert cash_debit == Decimal("58500.00")
        assert disc_debit == Decimal("1500.00")
        assert unearned_debit == Decimal("6000.00")
        assert cust_credit == Decimal("66000.00")

        # التحقق من تصفير الأقساط وإغلاق الخطة
        for it in items:
            it.refresh_from_db()
            assert it.remaining_balance == Decimal("0.00")
            assert it.unearned_interest_balance == Decimal("0.00")
            assert it.cash_status == InstallmentCashStatus.COLLECTED

        plan.refresh_from_db()
        sale.refresh_from_db()
        assert plan.status == PlanStatus.COMPLETED
        assert sale.is_fully_paid is True
        assert sale.amount_due == Decimal("0.00")

    def test_early_settlement_branch_b_prepaid_interest_refund(self, installment_fixture, base_customer, auth_user):
        sale, plan, items = installment_fixture
        item1, item2, item3 = items

        # محاكاة حالة خاصة (الفرع ب): العميل دفع مسبقاً 950 أصل و 95 فوائد في القسط 1 قبل الاعتراف بها
        # نضبط القسط: أصل 50 متبقي، فايدة 5 متبقية، مدفوع مسبقاً فايدة 95
        item1.principal_amount = Decimal("1000.00")
        item1.interest_amount = Decimal("100.00")
        item1.total_amount = Decimal("1100.00")
        item1.paid_principal = Decimal("950.00")
        item1.paid_interest = Decimal("95.00")
        item1.paid_amount = Decimal("1045.00")
        item1.recognized_interest = Decimal("0.00")  # لم يُعترف بها بعد
        item1.save()

        # نستبعد القسطين 2 و 3 لهذا الاختبار لتركيز الحالة على القسط 1
        item2.delete()
        item3.delete()

        calc = EarlySettlementService.calculate_early_settlement(
            sale=sale,
            items=[item1]
        )

        assert calc["branch"] == 'B'
        assert calc["final_cash_required"] == Decimal("0.00")  # حظر التحصيل السالب
        assert calc["settlement_principal"] == Decimal("50.00")
        assert calc["prepaid_interest"] == Decimal("95.00")
        # الفائض المردود للعميل = 95 - 50 = 45 ج.م
        assert calc["customer_net_refund_amount"] == Decimal("45.00")

        # تنفيذ السداد
        exec_res = EarlySettlementService.execute_early_settlement(
            sale=sale,
            items=[item1],
            user=auth_user
        )

        assert exec_res["status"] == "SUCCESS"
        assert exec_res["payment"] is None  # لم يُسجل أي سند نقدية سالب

        # التحقق من توازن القيد في الفرع (ب):
        # مدين مؤجل (21400): 100 | دائن عملاء: 55 | دائن رصيد مسبق للعميل (21020): 45
        je = exec_res["journal_entry"]
        lines = list(je.lines.all())
        total_debit = sum(l.debit for l in lines)
        total_credit = sum(l.credit for l in lines)
        assert total_debit == total_credit == Decimal("100.00")

        base_customer.refresh_from_db()
        assert base_customer.balance == Decimal("-45.00")  # تم ترحيل الفائض لرصيده الدائن


@pytest.mark.django_db
class TestSettlementReversalService:
    """اختبارات عكس التسويات المركبة والفردية (SettlementReversalService)"""

    def test_reverse_composite_settlement_batch(self, installment_fixture, auth_user):
        sale, plan, items = installment_fixture

        # تنفيذ سداد معجل بحزمة مركبة
        exec_res = EarlySettlementService.execute_early_settlement(
            sale=sale,
            early_discount_amount=Decimal("1500.00"),
            user=auth_user
        )
        batch_id = exec_res["batch_id"]

        # التحقق من إغلاق الخطة والفاتورة
        plan.refresh_from_db()
        assert plan.status == PlanStatus.COMPLETED

        # تنفيذ عكس الحزمة المركبة
        rev_res = SettlementReversalService.reverse_composite_settlement_batch(
            batch_id=batch_id,
            user=auth_user,
            reason="طلب العميل التراجع عن السداد المعجل واستكمال الأقساط شهرياً"
        )

        assert rev_res["status"] == "SUCCESS"
        assert rev_res["reversed_settlements_count"] >= 2
        assert rev_res["reversed_payments_count"] == 1

        # التحقق من استعادة الأقساط وحالة الخطة
        plan.refresh_from_db()
        sale.refresh_from_db()
        assert plan.status == PlanStatus.ACTIVE
        assert sale.amount_due == Decimal("66000.00")  # استعادة كامل مديونية الفاتورة

        for it in items:
            it.refresh_from_db()
            assert it.remaining_balance == Decimal("22000.00")
            assert it.cash_status == InstallmentCashStatus.PENDING
            assert it.is_interest_recognized is False


def make_test_delivery_note(sale, user, number, status="DELIVERED"):
    wh, _ = Warehouse.objects.get_or_create(name="المخزن الرئيسي للتسليم", defaults={"is_active": True})
    so = SalesOrder.objects.create(
        order_number=f"SO-{uuid.uuid4().hex[:8].upper()}",
        customer=sale.customer,
        warehouse=wh,
        order_date=timezone.localdate(),
        created_by=user,
    )
    return DeliveryNote.objects.create(
        delivery_number=number,
        sales_order=so,
        customer=sale.customer,
        warehouse=wh,
        delivery_date=timezone.localdate(),
        status=status,
        created_by=user,
    )


@pytest.mark.django_db
class TestContractCurtailmentService:
    """اختبارات تقليص العقد وحماية مديونية الدفعات المسلمة (ContractCurtailmentService)"""

    def test_curtailment_blocks_delivered_tranche_cancellation(self, installment_fixture, auth_user):
        sale, plan, items = installment_fixture
        item1 = items[0]

        # ربط القسط الأول بإذن تسليم معتمد ومسلم
        dn = make_test_delivery_note(
            sale=sale,
            user=auth_user,
            number="DN-P4-001",
            status="DELIVERED"
        )
        item1.linked_delivery_note = dn
        item1.save()

        from sale.models.credit_note import CreditNote
        cn = CreditNote.objects.create(
            credit_note_number=f"CN-CURTAIL-DELIV-{sale.id}",
            customer=sale.customer,
            sale=sale,
            status="POSTED",
            total_amount=Decimal("20000.00"),
            created_by=auth_user
        )
        # محاولة تقليص وإلغاء القسط الأول يجب أن تفشل بحارس حماية الدفعات المسلمة
        with pytest.raises(ValidationError) as exc:
            ContractCurtailmentService.curtail_installment_plan(
                plan=plan,
                cancelled_items=[item1],
                credit_note=cn,
                user=auth_user
            )
        assert "مرتبط بباتش بضاعة تم تسليمها بالفعل" in str(exc.value)

    def test_curtailment_waives_future_unearned_interest(self, installment_fixture, auth_user):
        sale, plan, items = installment_fixture
        item2, item3 = items[1], items[2]

        from sale.models.credit_note import CreditNote
        cn = CreditNote.objects.create(
            credit_note_number=f"CN-CURTAIL-UNEARNED-{sale.id}",
            customer=sale.customer,
            sale=sale,
            status="POSTED",
            total_amount=Decimal("40000.00"),
            created_by=auth_user
        )

        # تقليص العقد بإلغاء القسطين 2 و 3 غير المصنعين
        curtail_res = ContractCurtailmentService.curtail_installment_plan(
            plan=plan,
            cancelled_items=[item2, item3],
            credit_note=cn,
            user=auth_user,
            reason="تعديل العميل لتصميم العبوة وإلغاء التشغيلات المستقبلية"
        )

        assert curtail_res["status"] == "SUCCESS"
        assert curtail_res["unearned_interest_waived"] == Decimal("4000.00")  # 2,000 لكل قسط

        # التحقق من قيد إلغاء الفوائد: مدين 21400 / دائن العملاء بمبلغ 4,000
        je = curtail_res["journal_entry"]
        assert je is not None
        lines = list(je.lines.all())
        assert any(l.account.code == "21400" and l.debit == Decimal("4000.00") for l in lines)
        assert any(l.credit == Decimal("4000.00") and l.account.code != "21400" for l in lines)

        # التحقق من تحويل حالة الأقساط إلى WAIVED وتحويل الخطة لـ CURTAILED
        item2.refresh_from_db()
        item3.refresh_from_db()
        assert item2.cash_status == InstallmentCashStatus.WAIVED
        assert item3.cash_status == InstallmentCashStatus.WAIVED

        plan.refresh_from_db()
        assert plan.status == PlanStatus.CURTAILED


@pytest.mark.django_db
class TestReworkDisputeAndPenaltyWaiver:
    """اختبارات عيوب التشغيل وإسقاط غرامات التأخير خارج الميزانية"""

    def test_rework_hold_and_resolution_protocol(self, installment_fixture, auth_user):
        sale, plan, items = installment_fixture
        item1 = items[0]
        item1.penalty_amount = Decimal("250.00")
        item1.save()

        # 1. تعليق القسط لعيب تشغيل
        ReworkDisputeService.apply_rework_hold(
            installment_item=item1,
            defect_description="عيب طباعة وبهتان في ألوان اللوجو",
            user=auth_user
        )

        item1.refresh_from_db()
        plan.refresh_from_db()
        assert item1.cash_status == InstallmentCashStatus.HOLD_REWORK
        assert item1.penalty_amount == Decimal("0.00")  # تجميد وتصفير الغرامة
        assert plan.status == PlanStatus.DISPUTED

        # 2. فك التعليق بإذن تسليم بديل معتمد
        replacement_dn = make_test_delivery_note(
            sale=sale,
            user=auth_user,
            number="DN-P4-REWORK-001",
            status="DELIVERED"
        )

        ReworkDisputeService.resolve_rework_hold(
            installment_item=item1,
            replacement_delivery_note=replacement_dn,
            user=auth_user
        )

        item1.refresh_from_db()
        plan.refresh_from_db()
        assert item1.cash_status == InstallmentCashStatus.PENDING
        assert item1.linked_delivery_note_id == replacement_dn.id
        assert plan.status == PlanStatus.ACTIVE

    def test_penalty_waiver_does_not_affect_invoice_due(self, installment_fixture, auth_user):
        sale, plan, items = installment_fixture
        item1 = items[0]
        item1.penalty_amount = Decimal("500.00")
        item1.save()

        initial_amount_due = sale.amount_due

        # إسقاط غرامة 500 ج.م
        waiver_res = PenaltyWaiverService.waive_installment_penalty(
            installment_item=item1,
            waived_amount=Decimal("500.00"),
            reason="إعفاء استثنائي معتمد للعميل",
            user=auth_user
        )

        assert waiver_res["status"] == "SUCCESS"
        item1.refresh_from_db()
        assert item1.penalty_amount == Decimal("0.00")

        # التحقق من أن التسوية حقلها affects_invoice_due = False
        settlement = waiver_res["settlement"]
        assert settlement.affects_invoice_due is False

        # التأكد التام من أن رصيد الفاتورة لم ينخفض نهائياً
        sale.refresh_from_db()
        assert sale.amount_due == initial_amount_due
