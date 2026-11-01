# -*- coding: utf-8 -*-
"""
Tests for Wave 1 - Phase 0.5:
Full Decoupling of Installments & Cheques Engines from Merchandise Sales Invoices,
ContractInstallmentBindingService Atomic Protocol, Single-Source Guards,
and Historical Financial Movement Immutability.
"""
from decimal import Decimal
import pytest
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from customer.models import Customer
from sale.models.installments import (
    InstallmentPlan,
    InstallmentItem,
    InstallmentRescheduleLog,
    InstallmentSettlement
)
from cheques.models.cheque import Cheque, ChequeType, ChequeStatus
from cheques.models.allocation import ChequeInvoiceAllocation, AllocationStatus
from cheques.services.allocation_service import ChequeAllocationService
from sale.services.contract_installment_binding_service import (
    ContractInstallmentBindingService,
    ContractBindingIntegrityError
)
from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyFloor,
    PropertyUnit,
    PropertyContract
)
from financial.models.currency import Currency
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType

User = get_user_model()


@pytest.fixture
def phase05_setup(db):
    user = User.objects.create_superuser(
        username="admin_p05",
        email="admin_p05@example.com",
        password="password123"
    )

    asset_type, _ = AccountType.objects.get_or_create(
        code='asset',
        defaults={'name': 'أصول', 'category': 'asset', 'nature': 'debit'}
    )
    bank_account, _ = ChartOfAccounts.objects.get_or_create(
        code="11101",
        defaults={'name': "البنك الأهلي التجاري", 'account_type': asset_type, 'is_active': True, 'is_leaf': True}
    )
    egp_currency, _ = Currency.objects.get_or_create(
        code="EGP",
        defaults={'name': "Egyptian Pound", 'symbol': "ج.م", 'is_functional': True}
    )

    customer_a = Customer.objects.create(
        code="CUST-P05-A",
        name="عميل أ - أحمد محمود",
        customer_type="INDIVIDUAL"
    )
    customer_b = Customer.objects.create(
        code="CUST-P05-B",
        name="عميل ب - شركة الاستثمار",
        customer_type="CORPORATE"
    )

    project = RealEstateProject.objects.create(
        name="مشروع المرحلة 0.5",
        code="PRJ-P05",
        project_type=RealEstateProject.ProjectType.RESIDENTIAL,
        status=RealEstateProject.ProjectStatus.UNDER_CONSTRUCTION,
        start_date=timezone.localdate(),
        expected_completion_date=timezone.localdate() + timezone.timedelta(days=365),
        created_by=user
    )
    block = PropertyBlock.objects.create(project=project, name="عمارة 1", code="BLK-1")
    floor = PropertyFloor.objects.create(block=block, name="الدور الأول", floor_number=1)
    unit = PropertyUnit.objects.create(
        project=project,
        block=block,
        floor=floor,
        unit_code="U-P05-101",
        gross_area=Decimal("120.00"),
        net_area=Decimal("100.00"),
        meter_price=Decimal("15000.00"),
        base_price=Decimal("1800000.00"),
        total_price=Decimal("1800000.00"),
        status=PropertyUnit.UnitStatus.AVAILABLE
    )

    contract = PropertyContract.objects.create(
        contract_number="CNT-P05-001",
        project=project,
        unit=unit,
        customer=customer_a,
        final_contract_price=Decimal("1800000.00"),
        down_payment=Decimal("300000.00"),
        currency=egp_currency,
        contract_date=timezone.localdate(),
        delivery_date=timezone.localdate() + timezone.timedelta(days=700),
        status=PropertyContract.ContractStatus.ACTIVE,
        created_by=user
    )

    return {
        "user": user,
        "customer_a": customer_a,
        "customer_b": customer_b,
        "contract": contract,
        "unit": unit,
        "bank_account": bank_account,
        "egp_currency": egp_currency
    }


@pytest.mark.django_db
def test_plan_safe_str_representation_without_sale(phase05_setup):
    """
    اختبار تمثيل السلسلة النصية __str__ لخطة وأقساط لا ترتبط بفاتورة بيع (تجنب AttributeError)
    """
    user = phase05_setup["user"]
    customer = phase05_setup["customer_a"]

    plan = InstallmentPlan.objects.create(
        customer=customer,
        sale=None,
        plan_type=InstallmentPlan.PlanType.ASSET_FINANCING,
        total_principal=Decimal("1500000.00"),
        total_amount=Decimal("1500000.00"),
        number_of_installments=5,
        start_date=timezone.localdate(),
        status=InstallmentPlan.PlanStatus.ACTIVE,
        created_by=user
    )
    item = InstallmentItem.objects.create(
        plan=plan,
        installment_number=1,
        principal_amount=Decimal("300000.00"),
        total_amount=Decimal("300000.00"),
        due_date=timezone.localdate()
    )

    # يجب ألا ترفع أي خطأ عند عدم وجود sale
    plan_str = str(plan)
    item_str = str(item)
    assert "PLAN-" in plan_str
    assert "عميل أ" in plan_str
    assert str(item.installment_number) in item_str


@pytest.mark.django_db
def test_binding_service_ownership_guards(phase05_setup):
    """
    اختبار حراس ملكية الخطة:
    1. حظر ربط خطة تنتمي لعميل مختلف.
    2. إعادة ربط نفس الخطة آمن ولا يرفع خطأ (Idempotent).
    """
    user = phase05_setup["user"]
    customer_a = phase05_setup["customer_a"]
    customer_b = phase05_setup["customer_b"]
    contract = phase05_setup["contract"]

    # خطة للعميل ب
    plan_b = InstallmentPlan.objects.create(
        customer=customer_b,
        plan_type=InstallmentPlan.PlanType.ASSET_FINANCING,
        total_principal=Decimal("1500000.00"),
        total_amount=Decimal("1500000.00"),
        number_of_installments=5,
        start_date=timezone.localdate(),
        status=InstallmentPlan.PlanStatus.ACTIVE,
        created_by=user
    )

    # محاولة ربط خطة العميل ب بالعقد (الذي يخص العميل أ)
    with pytest.raises(ContractBindingIntegrityError) as exc_info:
        ContractInstallmentBindingService.bind_plan_to_contract(contract, plan_b)
    assert exc_info.type == ContractBindingIntegrityError

    # إنشاء خطة صالحة للعميل أ وربطها
    plan_a = InstallmentPlan.objects.create(
        customer=customer_a,
        plan_type=InstallmentPlan.PlanType.ASSET_FINANCING,
        total_principal=Decimal("1500000.00"),
        total_amount=Decimal("1500000.00"),
        number_of_installments=5,
        start_date=timezone.localdate(),
        status=InstallmentPlan.PlanStatus.ACTIVE,
        created_by=user
    )

    bound_contract = ContractInstallmentBindingService.bind_plan_to_contract(contract, plan_a)
    assert bound_contract.installment_plan == plan_a

    # إعادة نفس الربط (Idempotency) يجب أن ينجح بدون أخطاء
    rebound_contract = ContractInstallmentBindingService.bind_plan_to_contract(contract, plan_a)
    assert rebound_contract.installment_plan == plan_a


@pytest.mark.django_db
def test_binding_blocks_plan_switching_after_active_payment(phase05_setup):
    """
    اختبار حظر تبديل خطة الأقساط بعد بدء السداد الفعلي:
    إذا تم تحصيل أي جزء من قسط، يُحظر استبدال الخطة حتى لنفس العميل لحماية التوازن المحاسبي
    """
    user = phase05_setup["user"]
    customer = phase05_setup["customer_a"]
    contract = phase05_setup["contract"]

    plan_1 = InstallmentPlan.objects.create(
        customer=customer,
        plan_type=InstallmentPlan.PlanType.ASSET_FINANCING,
        total_principal=Decimal("1500000.00"),
        total_amount=Decimal("1500000.00"),
        number_of_installments=5,
        start_date=timezone.localdate(),
        status=InstallmentPlan.PlanStatus.ACTIVE,
        created_by=user
    )
    item_1 = InstallmentItem.objects.create(
        plan=plan_1,
        installment_number=1,
        principal_amount=Decimal("300000.00"),
        total_amount=Decimal("300000.00"),
        due_date=timezone.localdate()
    )

    ContractInstallmentBindingService.bind_plan_to_contract(contract, plan_1)

    # إنشاء خطة بديلة لنفس العميل
    plan_2 = InstallmentPlan.objects.create(
        customer=customer,
        plan_type=InstallmentPlan.PlanType.ASSET_FINANCING,
        total_principal=Decimal("1500000.00"),
        total_amount=Decimal("1500000.00"),
        number_of_installments=10,
        start_date=timezone.localdate(),
        status=InstallmentPlan.PlanStatus.ACTIVE,
        created_by=user
    )

    # سداد 50,000 ج.م في القسط الأول
    item_1.paid_amount = Decimal("50000.00")
    item_1.save()

    # محاولة تبديل الخطة الآن يجب أن تُرفض قطعياً
    with pytest.raises(ContractBindingIntegrityError) as exc:
        ContractInstallmentBindingService.bind_plan_to_contract(contract, plan_2)
    assert exc.type == ContractBindingIntegrityError


@pytest.mark.django_db
def test_binding_blocks_plan_switching_on_historical_reversed_audit_records(phase05_setup):
    """
    اختبار فحص الحركات التاريخية والمعكوسة:
    وجود سجل إعادة جدولة أو سجل تسوية بالخطة يُقفل ملكيتها ومصدرها حتى لو كانت الأقساط تظهر كصفر مدفوع
    """
    user = phase05_setup["user"]
    customer = phase05_setup["customer_a"]
    contract = phase05_setup["contract"]

    plan_hist = InstallmentPlan.objects.create(
        customer=customer,
        plan_type=InstallmentPlan.PlanType.ASSET_FINANCING,
        total_principal=Decimal("1500000.00"),
        total_amount=Decimal("1500000.00"),
        number_of_installments=5,
        start_date=timezone.localdate(),
        status=InstallmentPlan.PlanStatus.ACTIVE,
        created_by=user
    )
    item_hist = InstallmentItem.objects.create(
        plan=plan_hist,
        installment_number=1,
        principal_amount=Decimal("300000.00"),
        total_amount=Decimal("300000.00"),
        due_date=timezone.localdate()
    )

    ContractInstallmentBindingService.bind_plan_to_contract(contract, plan_hist)

    # إضافة سجل إعادة جدولة تاريخي
    InstallmentRescheduleLog.objects.create(
        installment=item_hist,
        old_due_date=timezone.localdate(),
        new_due_date=timezone.localdate() + timezone.timedelta(days=30),
        reason="طلب العميل ترحيل تاريخ السداد",
        approved_by=user
    )

    new_plan = InstallmentPlan.objects.create(
        customer=customer,
        plan_type=InstallmentPlan.PlanType.ASSET_FINANCING,
        total_principal=Decimal("1500000.00"),
        total_amount=Decimal("1500000.00"),
        number_of_installments=10,
        start_date=timezone.localdate(),
        status=InstallmentPlan.PlanStatus.ACTIVE,
        created_by=user
    )

    # محاولة تبديل الخطة يجب أن تُرفض لوجود أثر تدقيقي تاريخي
    with pytest.raises(ContractBindingIntegrityError) as exc:
        ContractInstallmentBindingService.bind_plan_to_contract(contract, new_plan)
    assert exc.type == ContractBindingIntegrityError


@pytest.mark.django_db
def test_decoupled_cheque_allocation_to_contract_installment(phase05_setup):
    """
    اختبار تخصيص الشيك مباشرة لقسط عقاري دون وجود فاتورة بيع تجارية
    """
    user = phase05_setup["user"]
    customer = phase05_setup["customer_a"]
    contract = phase05_setup["contract"]
    bank_account = phase05_setup["bank_account"]
    egp_currency = phase05_setup["egp_currency"]

    plan = InstallmentPlan.objects.create(
        customer=customer,
        plan_type=InstallmentPlan.PlanType.ASSET_FINANCING,
        total_principal=Decimal("1500000.00"),
        total_amount=Decimal("1500000.00"),
        number_of_installments=5,
        start_date=timezone.localdate(),
        status=InstallmentPlan.PlanStatus.ACTIVE,
        created_by=user
    )
    item = InstallmentItem.objects.create(
        plan=plan,
        installment_number=1,
        principal_amount=Decimal("300000.00"),
        total_amount=Decimal("300000.00"),
        due_date=timezone.localdate()
    )
    ContractInstallmentBindingService.bind_plan_to_contract(contract, plan)

    # إنشاء ورقة قبض شيك
    cheque = Cheque.objects.create(
        cheque_number="CHQ-P05-9988",
        amount=Decimal("300000.00"),
        currency=egp_currency,
        issue_date=timezone.localdate(),
        due_date=timezone.localdate() + timezone.timedelta(days=60),
        cheque_type=ChequeType.RECEIVABLE,
        status=ChequeStatus.UNDER_COLLECTION,
        customer=customer,
        created_by=user
    )

    # تخصيص الشيك للقسط العقاري
    allocation = ChequeAllocationService.allocate_cheque_to_invoice(
        cheque=cheque,
        sale=None,
        amount=Decimal("300000.00"),
        installment_item=item,
        user=user
    )

    assert allocation is not None
    assert allocation.sale is None
    assert allocation.installment_item == item
    assert allocation.allocation_status == AllocationStatus.APPLIED
    assert allocation.allocated_amount == Decimal("300000.00")

    item.refresh_from_db()
    assert item.paper_coverage == InstallmentItem.PaperCoverage.BANK_DEPOSITED
