# -*- coding: utf-8 -*-
"""
Tests for Wave 1 - Phase 3.5:
Dedicated Contract Debt Clearance Service (ContractDebtClearanceService),
Subledger Debt Isolation (Decoupled from commercial trade debts),
Bounced Cheque Guards, and Cryptographic Tamper-Proof Clearance Certificates.
"""
from decimal import Decimal
import pytest
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from customer.models import Customer
from sale.models.installments import InstallmentPlan, InstallmentItem
from cheques.models.cheque import Cheque, ChequeType, ChequeStatus
from cheques.models.allocation import ChequeInvoiceAllocation, AllocationStatus
from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyFloor,
    PropertyUnit,
    PropertyContract
)
from real_estate.services.clearance_service import ContractDebtClearanceService
from financial.models.currency import Currency
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType

User = get_user_model()


@pytest.fixture
def phase35_setup(db):
    user = User.objects.create_superuser(
        username="admin_p35",
        email="admin_p35@example.com",
        password="password123"
    )

    asset_type, _ = AccountType.objects.get_or_create(
        code='asset',
        defaults={'name': 'أصول', 'category': 'asset', 'nature': 'debit'}
    )
    egp_currency, _ = Currency.objects.get_or_create(
        code="EGP",
        defaults={'name': "Egyptian Pound", 'symbol': "ج.م", 'is_functional': True}
    )

    # عميل لديه نشاط تجاري (عليه مديونية تجارية ضخمة في المبيعات التجارية)
    customer = Customer.objects.create(
        code="CUST-P35-DUAL",
        name="مجموعة الشروق للتجارة والمقاولات",
        customer_type="CORPORATE",
        balance=Decimal("2500000.00"),  # مديونية تجارية 2.5 مليون جنيه
        credit_limit=Decimal("500000.00")
    )

    project = RealEstateProject.objects.create(
        name="أبراج النيل 3.5",
        code="PRJ-P35",
        project_type=RealEstateProject.ProjectType.RESIDENTIAL,
        status=RealEstateProject.ProjectStatus.UNDER_CONSTRUCTION,
        start_date=timezone.localdate(),
        expected_completion_date=timezone.localdate() + timezone.timedelta(days=365),
        created_by=user
    )
    block = PropertyBlock.objects.create(project=project, name="برج أ", code="TWR-A")
    floor = PropertyFloor.objects.create(block=block, name="الدور العاشر", floor_number=10)
    unit = PropertyUnit.objects.create(
        project=project,
        block=block,
        floor=floor,
        unit_code="U-P35-1001",
        gross_area=Decimal("200.00"),
        net_area=Decimal("170.00"),
        meter_price=Decimal("20000.00"),
        base_price=Decimal("4000000.00"),
        total_price=Decimal("4000000.00"),
        status=PropertyUnit.UnitStatus.AVAILABLE
    )

    contract = PropertyContract.objects.create(
        contract_number="CNT-P35-001",
        project=project,
        unit=unit,
        customer=customer,
        final_contract_price=Decimal("4000000.00"),
        down_payment=Decimal("1000000.00"),
        currency=egp_currency,
        contract_date=timezone.localdate(),
        delivery_date=timezone.localdate() + timezone.timedelta(days=700),
        status=PropertyContract.ContractStatus.ACTIVE,
        created_by=user
    )

    from customer.models import CustomerPayment
    from real_estate.models.contract import ContractPaymentReceipt
    dp_payment = CustomerPayment.objects.create(
        customer=customer,
        amount=Decimal("1000000.00"),
        payment_date=timezone.localdate(),
        payment_method="CASH",
        created_by=user
    )
    ContractPaymentReceipt.objects.create(
        contract=contract,
        customer_payment=dp_payment,
        installment_item=None
    )

    plan = InstallmentPlan.objects.create(
        customer=customer,
        plan_type=InstallmentPlan.PlanType.ASSET_FINANCING,
        total_principal=Decimal("3000000.00"),
        total_amount=Decimal("3000000.00"),
        number_of_installments=2,
        start_date=timezone.localdate(),
        status=InstallmentPlan.PlanStatus.ACTIVE,
        created_by=user
    )
    contract.installment_plan = plan
    contract.save()

    item_1 = InstallmentItem.objects.create(
        plan=plan,
        installment_number=1,
        principal_amount=Decimal("1500000.00"),
        total_amount=Decimal("1500000.00"),
        paid_amount=Decimal("0.00"),
        due_date=timezone.localdate()
    )
    item_2 = InstallmentItem.objects.create(
        plan=plan,
        installment_number=2,
        principal_amount=Decimal("1500000.00"),
        total_amount=Decimal("1500000.00"),
        paid_amount=Decimal("0.00"),
        due_date=timezone.localdate() + timezone.timedelta(days=90)
    )

    return {
        "user": user,
        "customer": customer,
        "contract": contract,
        "plan": plan,
        "item_1": item_1,
        "item_2": item_2,
        "egp_currency": egp_currency
    }


@pytest.mark.django_db
def test_clearance_evaluation_detects_unpaid_installments(phase35_setup):
    """
    اختبار تقييم المخالصة لعقد به أقساط غير مسددة: يرفض منح شهادة براءة الذمة
    """
    contract = phase35_setup["contract"]
    user = phase35_setup["user"]

    eval_data = ContractDebtClearanceService.evaluate_contract_clearance(contract)
    assert eval_data['is_cleared'] is False
    assert eval_data['can_issue_clearance_certificate'] is False
    assert eval_data['unpaid_installments_count'] == 2
    assert eval_data['remaining_balance'] == Decimal("3000000.00")

    # محاولة إصدار الشهادة مباشرة يجب أن ترفع خطأ تحقق
    with pytest.raises(ValidationError) as exc:
        ContractDebtClearanceService.issue_clearance_certificate(contract, user=user)
    assert "لا يمكن إصدار شهادة المخالصة" in str(exc.value)


@pytest.mark.django_db
def test_clearance_issued_despite_unrelated_commercial_trade_debts(phase35_setup):
    """
    اختبار عزل الحسابات الفرعية (Subledger Isolation):
    عند سداد كامل مستحقات الوحدة العقارية، يتم إصدار شهادة المخالصة بنجاح
    حتى لو كان على العميل مديونية بـ 2.5 مليون جنيه في حساب المبيعات التجارية
    """
    contract = phase35_setup["contract"]
    item_1 = phase35_setup["item_1"]
    item_2 = phase35_setup["item_2"]
    user = phase35_setup["user"]
    customer = phase35_setup["customer"]

    # سداد كامل الأقساط
    item_1.paid_amount = Decimal("1500000.00")
    item_1.save()
    item_2.paid_amount = Decimal("1500000.00")
    item_2.save()

    # رصيد العميل التجاري ما زال مديناً بـ 2.5 مليون
    assert customer.balance == Decimal("2500000.00")

    eval_data = ContractDebtClearanceService.evaluate_contract_clearance(contract)
    assert eval_data['is_cleared'] is True
    assert eval_data['can_issue_clearance_certificate'] is True
    assert eval_data['remaining_balance'] == Decimal("0.00")

    cert = ContractDebtClearanceService.issue_clearance_certificate(contract, user=user)
    assert cert is not None
    assert cert['certificate_number'] == f"CLR-{contract.contract_number}"
    assert cert['verification_hash'] != ""
    assert cert['verification_token'] != ""
    assert len(cert['verification_token']) == 16

    contract.refresh_from_db()
    assert contract.installments_settled is True
    assert contract.status == PropertyContract.ContractStatus.COMPLETED


@pytest.mark.django_db
def test_clearance_blocked_by_bounced_cheque_even_if_book_balance_zero(phase35_setup):
    """
    اختبار فحص الشيكات المرتدة:
    إذا كانت الأقساط مسددة دفترياً لكن يوجد شيك مرتد مرتبط بالعقد، يُحظر إصدار براءة الذمة
    """
    contract = phase35_setup["contract"]
    item_1 = phase35_setup["item_1"]
    item_2 = phase35_setup["item_2"]
    user = phase35_setup["user"]
    customer = phase35_setup["customer"]
    egp_currency = phase35_setup["egp_currency"]

    # سداد الأقساط دفترياً
    item_1.paid_amount = Decimal("1500000.00")
    item_1.save()
    item_2.paid_amount = Decimal("1500000.00")
    item_2.save()

    # شيك مرتبط بالقسط الأول حالته BOUNCED (مرتد)
    bounced_cheque = Cheque.objects.create(
        cheque_number="CHQ-P35-BOUNCED",
        amount=Decimal("1500000.00"),
        currency=egp_currency,
        issue_date=timezone.localdate(),
        due_date=timezone.localdate(),
        cheque_type=ChequeType.RECEIVABLE,
        status=ChequeStatus.BOUNCED,
        customer=customer,
        created_by=user
    )
    ChequeInvoiceAllocation.objects.create(
        cheque=bounced_cheque,
        installment_item=item_1,
        allocated_amount=Decimal("1500000.00"),
        allocated_amount_functional=Decimal("1500000.00"),
        allocation_date=timezone.localdate(),
        allocation_status=AllocationStatus.APPLIED
    )

    eval_data = ContractDebtClearanceService.evaluate_contract_clearance(contract)
    assert eval_data['is_cleared'] is False
    assert eval_data['bounced_cheques_count'] == 1
    assert eval_data['can_issue_clearance_certificate'] is False

    with pytest.raises(ValidationError) as exc:
        ContractDebtClearanceService.issue_clearance_certificate(contract, user=user)
    assert "الشيكات المرتدة" in str(exc.value)
