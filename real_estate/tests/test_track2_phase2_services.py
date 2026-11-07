# -*- coding: utf-8 -*-
"""
Track 2 - Phase 2: Pricing, BOQ Calculation & Dual-Speed Workflow Engine Test Suite
MWHEBA ERP - Real Estate App

Verifies 100% integrity of pricing formulas, freeze periods, arrears locks,
co-ownership guards, delivery date amendments, and booking feasibility conversions.
"""
from decimal import Decimal
from datetime import date, timedelta
import pytest
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyFloor,
    PropertyUnit,
    PropertyContract,
    ContractCoOwner,
    UnitPricingMatrixConfig,
    UnitBooking,
    FinishingWorkspace,
    FinishingBrand,
    ContractualCreditSchedule,
    FinishingItemSpec,
    FinishingPackageTemplate,
    FinishingPackageItem,
    UnitFinishingOrder,
    UnitFinishingOrderItem,
    BookingPreContractVariationStudy,
)
from customer.models import Customer
from product.models import Product, Category, Unit as ProductMeasurementUnit
from financial.models.currency import Currency
from financial.models import EnterpriseApprovalRequest
from sale.models.installments import InstallmentPlan, InstallmentItem

from real_estate.services.finishing_service import (
    FinishingPricingService,
    FinishingWorkflowEngine,
    FinishingBulkPricingSyncService,
    FinishingPreContractBookingStudyService,
)

User = get_user_model()


@pytest.fixture
def workflow_setup(db):
    """Sets up user, customer, project, block, floor, unit, contract, and products."""
    user = User.objects.create_user(
        username="engineer_phase2",
        email="eng_p2@example.com",
        password="password123"
    )
    customer = Customer.objects.create(
        name="عميل اختبار المرحلة الثانية",
        code="CUST-P2-001",
        phone="01122334455"
    )
    project = RealEstateProject.objects.create(
        name="مشروع المرحلة الثانية",
        code="P2-PRJ",
        start_date=date(2025, 1, 1),
        expected_completion_date=date(2027, 12, 31),
        created_by=user
    )
    block = PropertyBlock.objects.create(
        project=project,
        name="عمارة 10",
        code="B10"
    )
    floor = PropertyFloor.objects.create(
        block=block,
        floor_number=2,
        name="الدور الثاني"
    )
    unit = PropertyUnit.objects.create(
        project=project,
        block=block,
        floor=floor,
        unit_code="P2-U102",
        unit_type="APARTMENT",
        gross_area=Decimal('200.00'),
        net_area=Decimal('170.00'),
        meter_price=Decimal('25000.00'),
        total_price=Decimal('5000000.00'),
        status='CONTRACTED'
    )
    egp, _ = Currency.objects.get_or_create(code="EGP", defaults={'name': "جنيه مصري", 'symbol': "ج.م", 'is_functional': True})
    contract = PropertyContract.objects.create(
        contract_number="CNT-P2-102",
        project=project,
        unit=unit,
        customer=customer,
        final_contract_price=Decimal('5000000.00'),
        contract_date=date(2025, 2, 1),
        delivery_date=date(2027, 6, 30),
        currency=egp,
        status='ACTIVE',
        created_by=user
    )
    workspace = FinishingWorkspace.objects.create(
        project=project,
        name="الصالة الرئيسية",
        code="LIV-01"
    )
    credit_schedule = ContractualCreditSchedule.objects.create(
        project=project,
        category='FLOORING',
        item_title="استرداد أرضيات نصف التشطيب",
        contractual_credit_rate=Decimal('100.00'),
        measuring_unit="M2"
    )
    spec_flooring = FinishingItemSpec.objects.create(
        workspace=workspace,
        name="بورسلين إسباني فاخر",
        model_code="PORC-SP-01",
        measuring_unit="M2",
        standard_material_cost=Decimal('400.00'),
        standard_labor_cost=Decimal('100.00'),
        client_selling_rate=Decimal('600.00'),
        credit_schedule=credit_schedule
    )
    spec_demolition = FinishingItemSpec.objects.create(
        workspace=workspace,
        name="تكسير قواطع وإعادة بناء",
        model_code="DEMO-01",
        measuring_unit="M2",
        standard_material_cost=Decimal('50.00'),
        standard_labor_cost=Decimal('150.00'),
        client_selling_rate=Decimal('250.00')
    )

    return {
        'user': user,
        'customer': customer,
        'project': project,
        'block': block,
        'floor': floor,
        'unit': unit,
        'contract': contract,
        'workspace': workspace,
        'spec_flooring': spec_flooring,
        'spec_demolition': spec_demolition,
        'credit_schedule': credit_schedule
    }


@pytest.mark.django_db
def test_pricing_calculation_and_credit_deductions(workflow_setup):
    """Test full calculation of materials, labor, demolition, supervision, credit, and 35% advance deposit."""
    data = workflow_setup
    order = UnitFinishingOrder.objects.create(
        order_number="FO-PRICING-TEST",
        unit=data['unit'],
        contract=data['contract'],
        customer=data['customer'],
        title="طلب مقايسة متكامل",
        order_type='CUSTOM_VARIATION',
        current_stage='COST_ACCOUNTING',
        created_by=data['user']
    )

    # Add 100 m² flooring with 5% scrap
    UnitFinishingOrderItem.objects.create(
        order=order,
        workspace=data['workspace'],
        spec=data['spec_flooring'],
        quantity=Decimal('100.00'),
        scrap_rate=Decimal('5.00'),
        unit_selling_price=Decimal('600.00'),
        is_demolition_rework=False
    )

    # Add 20 m² demolition rework
    UnitFinishingOrderItem.objects.create(
        order=order,
        workspace=data['workspace'],
        spec=data['spec_demolition'],
        quantity=Decimal('20.00'),
        scrap_rate=Decimal('0.00'),
        unit_selling_price=Decimal('250.00'),
        is_demolition_rework=True
    )

    result = FinishingPricingService.calculate_order_pricing(order)
    order.refresh_from_db()

    # Flooring gross qty = 100 * 1.05 = 105 m²
    # Material cost = 105 * 400 = 42,000 EGP
    # Labor cost = 105 * 100 = 10,500 EGP
    # Demolition cost = 20 * 250 = 5,000 EGP
    # Credit total = 105 * 100 = 10,500 EGP
    # Supervision base = 42,000 + 10,500 + 5,000 = 57,500 EGP
    # Supervision fee 10% = 5,750 EGP
    # Gross amount = 57,500 + 5,750 - 10,500 = 52,750 EGP
    # Advance deposit required (35%) = 52,750 * 0.35 = 18,462.50 EGP

    assert order.material_cost_total == Decimal('42000.00')
    assert order.labor_cost_total == Decimal('10500.00')
    assert order.demolition_cost_total == Decimal('5000.00')
    assert order.core_shell_credit_total == Decimal('10500.00')
    assert order.supervision_fee_total == Decimal('5750.00')
    assert order.gross_finishing_amount == Decimal('52750.00')
    assert order.advance_deposit_required == Decimal('18462.50')


@pytest.mark.django_db
def test_price_freeze_and_validity_lifecycle(workflow_setup):
    """Test freezing prices for 15 days and checking expiration."""
    data = workflow_setup
    order = UnitFinishingOrder.objects.create(
        order_number="FO-FREEZE-TEST",
        unit=data['unit'],
        contract=data['contract'],
        customer=data['customer'],
        title="طلب تجميد أسعار",
        current_stage='COST_ACCOUNTING',
        created_by=data['user']
    )

    FinishingPricingService.freeze_pricing(order, validity_days=15)
    order.refresh_from_db()

    assert order.price_freeze_date is not None
    assert order.offer_validity_days == 15
    assert order.offer_expires_at == timezone.now().date() + timedelta(days=15)
    assert FinishingPricingService.is_price_frozen_and_valid(order) is True


@pytest.mark.django_db
def test_arrears_hard_lock_blocks_transition_without_cfo_override(workflow_setup):
    """Test that overdue contract installments block finishing order approval unless CFO override is given."""
    data = workflow_setup
    plan = InstallmentPlan.objects.create(
        customer=data['customer'],
        total_principal=Decimal('1000000.00'),
        total_amount=Decimal('1000000.00'),
        number_of_installments=12,
        start_date=date(2024, 1, 1),
        created_by=data['user']
    )
    data['contract'].installment_plan = plan
    data['contract'].save(update_fields=['installment_plan'])

    # Create an overdue unpaid installment
    InstallmentItem.objects.create(
        plan=plan,
        installment_number=1,
        due_date=timezone.now().date() - timedelta(days=30),
        principal_amount=Decimal('50000.00'),
        interest_amount=Decimal('0.00'),
        total_amount=Decimal('50000.00'),
        paid_amount=Decimal('0.00'),
        cash_status='UNPAID'
    )

    order = UnitFinishingOrder.objects.create(
        order_number="FO-ARREARS-TEST",
        unit=data['unit'],
        contract=data['contract'],
        customer=data['customer'],
        title="طلب فحص التعثر",
        current_stage='CUSTOMER_SERVICE',
        created_by=data['user']
    )

    # Transition should fail due to Arrears Hard Lock
    can_move, error = FinishingWorkflowEngine.validate_stage_transition(order, 'TECHNICAL_OFFICE', data['user'])
    assert can_move is False
    assert "أقساط مستحقة متأخرة" in error

    # Grant CFO override
    order.cfo_overdue_override = True
    order.cfo_override_notes = "موافقة المدير المالي على الجدولة"
    order.save(update_fields=['cfo_overdue_override', 'cfo_override_notes'])

    can_move, error = FinishingWorkflowEngine.validate_stage_transition(order, 'TECHNICAL_OFFICE', data['user'])
    assert can_move is True
    assert error is None


@pytest.mark.django_db
def test_joint_ownership_guard_requires_all_signatures_or_poa(workflow_setup):
    """Test that co-owners on contract block client approval unless all sign or POA is attached."""
    data = workflow_setup
    order = UnitFinishingOrder.objects.create(
        order_number="FO-COOWNER-TEST",
        unit=data['unit'],
        contract=data['contract'],
        customer=data['customer'],
        title="طلب فحص الشركاء",
        current_stage='FINANCE_CFO',
        all_co_owners_signed=False,
        delay_penalty_waiver_signed=True,
        created_by=data['user']
    )
    FinishingPricingService.freeze_pricing(order, validity_days=15)

    co_owner_customer = Customer.objects.create(
        name="شريك مالك على الشيوع",
        code="CUST-P2-COOWNER",
        phone="01299887766"
    )
    ContractCoOwner.objects.create(
        contract=data['contract'],
        co_owner=co_owner_customer,
        share_percentage=Decimal('50.00')
    )

    # Blocked because not all co-owners signed
    can_move, error = FinishingWorkflowEngine.validate_stage_transition(order, 'CLIENT_APPROVAL', data['user'])
    assert can_move is False
    assert "توقيع كافة الملاك الشركاء" in error

    # Mark all signed
    order.all_co_owners_signed = True
    order.save(update_fields=['all_co_owners_signed'])

    can_move, error = FinishingWorkflowEngine.validate_stage_transition(order, 'CLIENT_APPROVAL', data['user'])
    assert can_move is True


@pytest.mark.django_db
def test_delay_penalty_waiver_and_delivery_extension(workflow_setup):
    """Test that moving to CLIENT_APPROVAL extends contract delivery date and requires waiver."""
    data = workflow_setup
    order = UnitFinishingOrder.objects.create(
        order_number="FO-DELIVERY-TEST",
        unit=data['unit'],
        contract=data['contract'],
        customer=data['customer'],
        title="طلب تمديد التسليم",
        current_stage='FINANCE_CFO',
        execution_duration_days=120,
        all_co_owners_signed=True,
        delay_penalty_waiver_signed=False,
        created_by=data['user']
    )
    FinishingPricingService.freeze_pricing(order, validity_days=15)

    # Blocked without waiver signed
    can_move, error = FinishingWorkflowEngine.validate_stage_transition(order, 'CLIENT_APPROVAL', data['user'])
    assert can_move is False
    assert "إسقاط غرامات التأخير" in error

    # Sign waiver and transition
    order.delay_penalty_waiver_signed = True
    order.save(update_fields=['delay_penalty_waiver_signed'])

    orig_delivery = data['contract'].delivery_date
    updated_order = FinishingWorkflowEngine.transition_order_stage(order, 'CLIENT_APPROVAL', data['user'])
    data['contract'].refresh_from_db()

    assert updated_order.current_stage == 'CLIENT_APPROVAL'
    assert updated_order.original_contract_delivery_date == orig_delivery
    assert updated_order.amended_contract_delivery_date == orig_delivery + timedelta(days=120)
    assert data['contract'].delivery_date == orig_delivery + timedelta(days=120)


@pytest.mark.django_db
def test_fast_track_workflow_eligibility(workflow_setup):
    """Test fast track eligibility for cosmetic items <= 25,000 EGP without demolition."""
    data = workflow_setup
    order = UnitFinishingOrder.objects.create(
        order_number="FO-FAST-TRACK",
        unit=data['unit'],
        contract=data['contract'],
        customer=data['customer'],
        title="تعديل ديكوري سريع",
        order_type='CUSTOM_VARIATION',
        workflow_speed='FAST_TRACK',
        current_stage='CUSTOMER_SERVICE',
        gross_finishing_amount=Decimal('15000.00'),
        demolition_cost_total=Decimal('0.00'),
        delay_penalty_waiver_signed=True,
        created_by=data['user']
    )
    FinishingPricingService.freeze_pricing(order, validity_days=15)

    assert FinishingWorkflowEngine.is_fast_track_eligible(order) is True

    # If demolition rework is added, Fast-Track must be disqualified
    order.demolition_cost_total = Decimal('2000.00')
    assert FinishingWorkflowEngine.is_fast_track_eligible(order) is False


@pytest.mark.django_db
def test_enterprise_approval_created_at_finance_cfo(workflow_setup):
    """Test that moving to FINANCE_CFO creates an EnterpriseApprovalRequest."""
    data = workflow_setup
    order = UnitFinishingOrder.objects.create(
        order_number="FO-CFO-APPROVAL",
        unit=data['unit'],
        contract=data['contract'],
        customer=data['customer'],
        title="طلب اعتماد مالي",
        current_stage='COST_ACCOUNTING',
        created_by=data['user']
    )
    FinishingPricingService.freeze_pricing(order, validity_days=15)

    FinishingWorkflowEngine.transition_order_stage(order, 'FINANCE_CFO', data['user'])
    order.refresh_from_db()

    assert order.current_stage == 'FINANCE_CFO'
    assert order.approval_request is not None
    assert order.approval_request.module == 'REAL_ESTATE'
    assert order.approval_request.status == 'PENDING'
    assert order.order_number in order.approval_request.reference_id


@pytest.mark.django_db
def test_pricing_matrix_finishing_sync(workflow_setup):
    """Test synchronizing finishing meter rate with unit pricing matrix config."""
    data = workflow_setup
    package = FinishingPackageTemplate.objects.create(
        project=data['project'],
        name="باقة التشطيب الموحد",
        package_level="DELUXE",
        price_per_square_meter=Decimal('4500.00')
    )
    config = UnitPricingMatrixConfig.objects.create(
        project=data['project'],
        name="لائحة تسعير تشطيب البرج",
        base_meter_price=Decimal('20000.00'),
        default_finishing_package=package,
        finishing_meter_rate=Decimal('4500.00'),
        created_by=data['user']
    )

    count = FinishingBulkPricingSyncService.sync_pricing_matrix_with_finishing(config)
    data['unit'].refresh_from_db()

    assert count >= 1
    assert 'finishing_meter_rate' in data['unit'].pricing_breakdown
    assert data['unit'].pricing_breakdown['finishing_meter_rate'] == '4500.00'
    assert data['unit'].pricing_breakdown['finishing_total_addon'] == '900000.00'  # 200 sqm * 4500


@pytest.mark.django_db
def test_pre_contract_booking_study_conversion(workflow_setup):
    """Test creating a pre-contract study on UnitBooking and converting it to an official UnitFinishingOrder."""
    data = workflow_setup
    egp = Currency.objects.get(code="EGP")
    booking = UnitBooking.objects.create(
        booking_number="BK-TEST-001",
        unit=data['unit'],
        customer=data['customer'],
        booking_date=date(2025, 1, 15),
        expiry_date=date(2025, 2, 15),
        holding_deposit=Decimal('50000.00'),
        currency=egp,
        created_by=data['user']
    )

    study = FinishingPreContractBookingStudyService.create_study_for_booking(
        booking=booking,
        requested_changes_summary="فتح غرفة المعيشة على الريسبشن وتعديل مسار التكييف",
        preliminary_estimated_cost=Decimal('85000.00'),
        user=data['user']
    )
    assert study.is_architecturally_feasible is True
    assert study.preliminary_estimated_cost == Decimal('85000.00')

    order = FinishingPreContractBookingStudyService.convert_study_to_finishing_order(
        study=study,
        contract=data['contract'],
        user=data['user']
    )
    assert order.order_number == f"FO-{data['contract'].contract_number}"
    assert order.gross_finishing_amount == Decimal('85000.00')
    assert order.advance_deposit_required == Decimal('29750.00')  # 35% of 85,000
    assert "فتح غرفة المعيشة" in order.notes
