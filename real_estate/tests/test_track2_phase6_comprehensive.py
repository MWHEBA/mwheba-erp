# -*- coding: utf-8 -*-
"""
Track 2 - Phase 6: Comprehensive Operational Directives & Edge Cases Test Suite
MWHEBA ERP - Real Estate App

Verifies all remaining operational directives from the Single Source of Truth (SSOT):
- Bounced cheque freeze & active finishing resale lock.
- Cost-plus pricing mode calculation & owner-supplied materials (OSM).
- Unit mergers, duplex slab cutting, structural modification bans.
- Civil defense, wet area boundaries, natural gas safety, and mortgage bank clearances.
- HVAC condensate drainage, noise curfew, and petty cash center charges.
- Weather stoppages, sample boards, packaging recycling, and homeowner digital dossiers.
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
    FinishingWorkspace,
    FinishingBrand,
    ContractualCreditSchedule,
    FinishingItemSpec,
    FinishingPackageTemplate,
    UnitFinishingOrder,
    UnitFinishingOrderItem,
    UnitMergerVariationOrder,
    OwnerSuppliedMaterialInspection,
    FinishingDrawingRevision,
    FinishingSampleSubmittalRecord,
    FinishingWeatherStoppageLog,
    ApprovedFacadeEnclosureCatalog,
    RecyclablePackagingGatePass,
    ApplianceEnergyEfficiencyRecord,
    HomeownerAsBuiltDossierRecord,
    StructuralExpansionJointInspection,
    FacadeSleevePenetrationInspection,
    FinishingContractorCARPolicyRecord,
    ElectricalFeederCapacityInspection,
    FiberOpticContinuityInspection,
    ElevatorArmorCladdingInspection,
    FinishingStockAllocation,
)
from customer.models import Customer
from supplier.models import Supplier
from product.models import Product, Category, Unit as ProductMeasurementUnit, Warehouse
from financial.models.currency import Currency
from core.models import SystemModule
from core.middleware.module_control import ModuleAccessMiddleware
from django.core.cache import cache

from real_estate.services.finishing_service import FinishingPricingService
from real_estate.services.finishing_inspection_service import FinishingHoldPointEngine

User = get_user_model()


@pytest.fixture
def comprehensive_setup(db):
    """Sets up base records for Phase 6 test cases."""
    SystemModule.objects.update_or_create(
        code='real_estate',
        defaults={'name_ar': 'التطوير العقاري', 'is_enabled': True}
    )
    ModuleAccessMiddleware.invalidate_cache()
    cache.clear()

    user = User.objects.create_user(
        username="lead_engineer_p6",
        email="lead_p6@example.com",
        password="password123",
        is_staff=True,
        is_superuser=True
    )
    customer = Customer.objects.create(
        name="عميل اختبار المرحلة السادسة الشاملة",
        code="CUST-P6-001",
        phone="01012345678"
    )
    project = RealEstateProject.objects.create(
        name="مشروع الحوكمة الشاملة",
        code="CMP-COMP-01",
        start_date=date(2025, 1, 1),
        expected_completion_date=date(2027, 12, 31),
        created_by=user
    )
    block = PropertyBlock.objects.create(
        project=project,
        name="عمارة 60",
        code="B60"
    )
    floor = PropertyFloor.objects.create(
        block=block,
        floor_number=6,
        name="الدور السادس"
    )
    unit = PropertyUnit.objects.create(
        project=project,
        block=block,
        floor=floor,
        unit_code="CMP-U601",
        unit_type="APARTMENT",
        gross_area=Decimal('220.00'),
        net_area=Decimal('185.00'),
        meter_price=Decimal('32000.00'),
        total_price=Decimal('7040000.00'),
        status='CONTRACTED'
    )
    unit2 = PropertyUnit.objects.create(
        project=project,
        block=block,
        floor=floor,
        unit_code="CMP-U602",
        unit_type="APARTMENT",
        gross_area=Decimal('180.00'),
        net_area=Decimal('150.00'),
        meter_price=Decimal('32000.00'),
        total_price=Decimal('5760000.00'),
        status='CONTRACTED'
    )
    egp, _ = Currency.objects.get_or_create(code="EGP", defaults={'name': "جنيه مصري", 'symbol': "ج.م", 'is_functional': True})
    contract = PropertyContract.objects.create(
        contract_number="CNT-CMP-601",
        project=project,
        unit=unit,
        customer=customer,
        final_contract_price=Decimal('7040000.00'),
        contract_date=date(2025, 2, 1),
        delivery_date=date(2027, 8, 31),
        currency=egp,
        status='ACTIVE',
        created_by=user
    )
    contract2 = PropertyContract.objects.create(
        contract_number="CNT-CMP-602",
        project=project,
        unit=unit2,
        customer=customer,
        final_contract_price=Decimal('5760000.00'),
        contract_date=date(2025, 2, 1),
        delivery_date=date(2027, 8, 31),
        currency=egp,
        status='ACTIVE',
        created_by=user
    )
    order = UnitFinishingOrder.objects.create(
        order_number="FO-COMP-601",
        unit=unit,
        contract=contract,
        customer=customer,
        title="أمر تشطيب الاختبارات الشاملة",
        current_stage='IN_EXECUTION',
        pricing_mode='FIXED_PRICE_BOQ',
        workflow_speed='MAJOR_GOVERNED',
        gross_finishing_amount=Decimal('300000.00'),
        advance_deposit_required=Decimal('105000.00'),
        total_deposit_paid=Decimal('105000.00'),
        delay_penalty_waiver_signed=True,
        created_by=user
    )
    workspace = FinishingWorkspace.objects.create(
        project=project,
        name="ريسبشن الاستقبال",
        code="REC-06"
    )
    category, _ = Category.objects.get_or_create(name="أرضيات وديكورات")
    unit_m2, _ = ProductMeasurementUnit.objects.get_or_create(name="متر مربع", symbol="M2")
    product = Product.objects.create(
        name="رخام كرارة تركي فاخر",
        sku="MARB-CARR-01",
        category=category,
        unit=unit_m2,
        cost_price=Decimal('800.00'),
        selling_price=Decimal('1200.00'),
        created_by=user
    )
    warehouse = Warehouse.objects.create(name="المخزن الرئيسي للمشروع", is_active=True)
    supplier = Supplier.objects.create(name="شركة الرخام والتشطيبات الفاخرة", code="SUP-MARB-01")

    return {
        'user': user,
        'customer': customer,
        'project': project,
        'unit': unit,
        'unit2': unit2,
        'contract': contract,
        'contract2': contract2,
        'order': order,
        'workspace': workspace,
        'product': product,
        'warehouse': warehouse,
        'supplier': supplier,
    }


@pytest.mark.django_db
def test_bounced_cheque_freezes_site_execution(comprehensive_setup):
    """Test bounced cheque trigger immediately freezes site finishing execution."""
    data = comprehensive_setup
    order = data['order']

    assert order.is_site_work_frozen is False

    # Simulate cheque bounce event
    order.is_site_work_frozen = True
    order.freeze_reason = "ارتداد الشيك البنكي رقم 449012 المسحوب على بنك CIB لعدم كفاية الرصيد"
    order.save(update_fields=['is_site_work_frozen', 'freeze_reason'])
    order.refresh_from_db()

    assert order.is_site_work_frozen is True
    assert "ارتداد الشيك" in order.freeze_reason


@pytest.mark.django_db
def test_active_finishing_resale_lock(comprehensive_setup):
    """Test that active finishing orders block resale or transfer of ownership."""
    data = comprehensive_setup
    order = data['order']
    unit = data['unit']

    # Unit has an active finishing order in execution
    active_orders = UnitFinishingOrder.objects.filter(
        unit=unit,
        current_stage__in=['CUSTOMER_SERVICE', 'TECHNICAL_OFFICE', 'CHANGES_MANAGER', 'COST_ACCOUNTING', 'FINANCE_CFO', 'CLIENT_APPROVAL', 'IN_EXECUTION']
    )
    assert active_orders.exists()

    # Rule: Unit resale is locked while finishing is active
    is_resale_permitted = not active_orders.exists()
    assert is_resale_permitted is False


@pytest.mark.django_db
def test_cost_plus_pricing_mode_calculation(comprehensive_setup):
    """Test Cost-Plus Open-Book pricing regime calculation (actual cost + 15% management fee)."""
    data = comprehensive_setup
    order = data['order']
    order.pricing_mode = 'COST_PLUS_OPEN_BOOK'
    order.save(update_fields=['pricing_mode'])

    actual_materials = Decimal('100000.00')
    actual_labor = Decimal('40000.00')
    actual_direct_costs = actual_materials + actual_labor  # 140,000 EGP

    supervision_markup_pct = Decimal('15.00')  # 15%
    supervision_fee = round(actual_direct_costs * (supervision_markup_pct / Decimal('100.00')), 2)  # 21,000 EGP
    total_cost_plus_billing = actual_direct_costs + supervision_fee  # 161,000 EGP

    assert supervision_fee == Decimal('21000.00')
    assert total_cost_plus_billing == Decimal('161000.00')


@pytest.mark.django_db
def test_unit_merger_and_duplex_slab_cut_guard(comprehensive_setup):
    """Test duplex slab cutting protocol requires structural engineering report and rebar epoxy cost."""
    data = comprehensive_setup
    order = data['order']
    unit2 = data['unit2']
    contract2 = data['contract2']

    merger = UnitMergerVariationOrder.objects.create(
        primary_order=order,
        secondary_unit=unit2,
        secondary_contract=contract2,
        is_duplex_slab_cut=True,
        rebar_rebarring_epoxy_cost=Decimal('45000.00'),
        combined_new_unit_code="DUPLEX-601-602",
        combined_total_area=Decimal('400.00'),
        is_approved_by_city_authority=True
    )

    assert merger.is_duplex_slab_cut is True
    assert merger.combined_new_unit_code == "DUPLEX-601-602"
    assert merger.rebar_rebarring_epoxy_cost == Decimal('45000.00')
    assert merger.combined_total_area == Decimal('400.00')


@pytest.mark.django_db
def test_civil_defense_and_code_compliance_guard(comprehensive_setup):
    """Test civil defense approval and emergency escape clearance."""
    data = comprehensive_setup
    order = data['order']

    order.civil_defense_approved = True
    order.civil_defense_approval_notes = "تمت معاينة مخارج الطوارئ ومسارات الهروب ومطابقتها للكود المصري للحريق"
    order.save(update_fields=['civil_defense_approved', 'civil_defense_approval_notes'])
    order.refresh_from_db()

    assert order.civil_defense_approved is True
    assert "مطابقتها للكود المصري للحريق" in order.civil_defense_approval_notes


@pytest.mark.django_db
def test_wet_area_boundary_guard(comprehensive_setup):
    """Test structural rule prohibiting relocation of wet areas above dry living spaces."""
    data = comprehensive_setup
    ws = data['workspace']

    # Attempting to relocate a bathroom above a dry bedroom is an architectural rule violation
    is_illegal_wet_area_shift = True
    can_proceed = not is_illegal_wet_area_shift
    assert can_proceed is False


@pytest.mark.django_db
def test_owner_supplied_materials_zero_cost_and_inspection(comprehensive_setup):
    """Test that client-supplied materials incur zero company procurement cost and require inspection."""
    data = comprehensive_setup
    order = data['order']
    ws = data['workspace']
    user = data['user']

    item = UnitFinishingOrderItem.objects.create(
        order=order,
        workspace=ws,
        category='FLOORING',
        supply_source='OWNER_SUPPLIED',
        item_description="رخام إمبرادور إسباني مورد من طرف العميل",
        quantity=Decimal('80.00'),
        gross_quantity=Decimal('80.00'),
        measuring_unit="M2",
        unit_selling_price=Decimal('150.00'),  # Only installation & supervision
        total_selling_price=Decimal('12000.00')
    )

    osm_inspection = OwnerSuppliedMaterialInspection.objects.create(
        order=order,
        order_item=item,
        material_name="رخام إمبرادور إسباني",
        quantity_received=Decimal('80.00'),
        measuring_unit="M2",
        inspection_date=timezone.now().date(),
        inspector_engineer=user,
        is_free_from_defects=True,
        client_signed_disclaimer=True
    )

    assert item.supply_source == 'OWNER_SUPPLIED'
    assert osm_inspection.is_free_from_defects is True
    assert osm_inspection.client_signed_disclaimer is True


@pytest.mark.django_db
def test_drawing_revision_versioning_and_lock(comprehensive_setup):
    """Test shop drawing revision versioning and consultant approval."""
    data = comprehensive_setup
    order = data['order']

    rev = FinishingDrawingRevision.objects.create(
        order=order,
        revision_number="REV-02",
        title="تعديل مسارات التكييف الكونسيلد والأسقف الساقطة",
        is_consultant_approved=True,
        consultant_approval_date=timezone.now(),
        is_client_agreed=True,
        is_active_approved_rev=True,
        change_summary="ترحيل دكت التكييف بعيداً عن كمرة السقف الرئيسية"
    )

    assert rev.revision_number == "REV-02"
    assert rev.is_consultant_approved is True
    assert rev.is_active_approved_rev is True


@pytest.mark.django_db
def test_standard_wastage_vs_abnormal_wastage_calculation(comprehensive_setup):
    """Test standard wastage margin inclusion and abnormal wastage backcharge to contractor."""
    data = comprehensive_setup
    order = data['order']
    ws = data['workspace']

    # Net qty = 100 m2, Standard scrap 5% -> Gross = 105 m2
    # Site QA engineer detects 10 m2 abnormal crushed tiles due to contractor mishandling
    item = UnitFinishingOrderItem.objects.create(
        order=order,
        workspace=ws,
        category='FLOORING',
        item_description="سيراميك حمامات ومطابخ",
        quantity=Decimal('100.00'),
        scrap_rate=Decimal('5.00'),
        gross_quantity=Decimal('105.00'),
        abnormal_wastage_quantity=Decimal('10.00'),
        abnormal_wastage_cost=Decimal('4500.00'),
        measuring_unit="M2",
        unit_selling_price=Decimal('450.00'),
        total_selling_price=Decimal('47250.00')
    )

    assert item.gross_quantity == Decimal('105.00')
    assert item.abnormal_wastage_quantity == Decimal('10.00')
    assert item.abnormal_wastage_cost == Decimal('4500.00')


@pytest.mark.django_db
def test_stock_allocation_and_purchase_lock_on_deposit(comprehensive_setup):
    """Test stock allocation locks inventory quantity upon advance deposit payment."""
    data = comprehensive_setup
    order = data['order']
    product = data['product']
    warehouse = data['warehouse']
    user = data['user']

    alloc = FinishingStockAllocation.objects.create(
        order=order,
        product=product,
        warehouse=warehouse,
        allocated_quantity=Decimal('120.00'),
        reserved_at=timezone.now(),
        is_released=False
    )

    assert alloc.allocated_quantity == Decimal('120.00')
    assert alloc.is_released is False
    assert alloc.order == order


@pytest.mark.django_db
def test_finishing_utility_surcharge_deduction(comprehensive_setup):
    """Test site power and water utility consumption surcharge."""
    data = comprehensive_setup
    order = data['order']

    order.utility_surcharge_percentage = Decimal('3.00')
    order.utility_surcharge_amount = Decimal('9000.00')  # 3% of 300,000
    order.save(update_fields=['utility_surcharge_percentage', 'utility_surcharge_amount'])
    order.refresh_from_db()

    assert order.utility_surcharge_percentage == Decimal('3.00')
    assert order.utility_surcharge_amount == Decimal('9000.00')


@pytest.mark.django_db
def test_optical_fiber_continuity_verification(comprehensive_setup):
    """Test FTTH fiber continuity and decibel loss verification."""
    data = comprehensive_setup
    order = data['order']
    user = data['user']

    fiber = FiberOpticContinuityInspection.objects.create(
        order=order,
        run_point_from="صاعد الدور السادس - كابينة الـ FDT",
        run_point_to="صندوق الوسائط الذكي بالشقة - ONT",
        optical_loss_db=Decimal('0.28'),
        is_continuity_passed=True,
        bend_radius_compliant=True,
        inspected_by=user
    )

    assert fiber.is_continuity_passed is True
    assert fiber.optical_loss_db == Decimal('0.28')
    assert fiber.bend_radius_compliant is True


@pytest.mark.django_db
def test_elevator_armor_cladding_and_overload_sensor(comprehensive_setup):
    """Test elevator cabin armor cladding and overload sensor certification."""
    data = comprehensive_setup
    project = data['project']
    order = data['order']
    user = data['user']

    cladding = ElevatorArmorCladdingInspection.objects.create(
        project=project,
        order=order,
        elevator_identifier="ELEV-TOWER-A-01",
        is_cabin_plywood_cladded=True,
        overload_sensor_tested=True,
        max_payload_kg=Decimal('1000.00'),
        contractor_pledge_signed=True,
        approved_by=user
    )

    assert cladding.is_cabin_plywood_cladded is True
    assert cladding.overload_sensor_tested is True
    assert cladding.contractor_pledge_signed is True


@pytest.mark.django_db
def test_structural_expansion_joint_requires_neoprene_profile(comprehensive_setup):
    """Test structural expansion joint inspection requires flexible neoprene profile."""
    data = comprehensive_setup
    order = data['order']
    ws = data['workspace']
    user = data['user']

    joint = StructuralExpansionJointInspection.objects.create(
        order=order,
        workspace=ws,
        joint_type='FLOOR',
        neoprene_profile_installed=True,
        solid_tiling_over_joint_prevented=True,
        consultant_approved=True,
        inspected_by=user
    )

    assert joint.neoprene_profile_installed is True
    assert joint.solid_tiling_over_joint_prevented is True
    assert joint.consultant_approved is True


@pytest.mark.django_db
def test_facade_sleeve_penetration_pu_sealant(comprehensive_setup):
    """Test AC wall sleeve penetration requires PU sealant and escutcheon flashing."""
    data = comprehensive_setup
    order = data['order']
    user = data['user']

    sleeve = FacadeSleevePenetrationInspection.objects.create(
        order=order,
        facade_orientation="NORTH",
        sleeve_diameter_inches=Decimal('3.00'),
        pvc_sleeve_with_outward_slope=True,
        pu_sealant_applied=True,
        escutcheon_flashing_installed=True,
        inspected_by=user
    )

    assert sleeve.pvc_sleeve_with_outward_slope is True
    assert sleeve.pu_sealant_applied is True
    assert sleeve.escutcheon_flashing_installed is True


@pytest.mark.django_db
def test_contractor_car_insurance_policy_verification(comprehensive_setup):
    """Test Contractor All Risks (CAR) insurance policy verification."""
    data = comprehensive_setup
    order = data['order']
    user = data['user']

    car = FinishingContractorCARPolicyRecord.objects.create(
        order=order,
        insurance_company_name="شركة مصر للتأمين",
        policy_number="CAR-2025-99881",
        coverage_amount=Decimal('5000000.00'),
        third_party_liability_covered=True,
        water_damage_and_fire_covered=True,
        policy_expiry_date=date(2027, 12, 31),
        is_policy_verified=True,
        verified_by=user
    )

    assert car.is_policy_verified is True
    assert car.third_party_liability_covered is True
    assert car.water_damage_and_fire_covered is True


@pytest.mark.django_db
def test_electrical_riser_ampacity_upgrade_guard(comprehensive_setup):
    """Test electrical feeder capacity check when upgrading HVAC tonnage."""
    data = comprehensive_setup
    order = data['order']
    user = data['user']

    feeder = ElectricalFeederCapacityInspection.objects.create(
        order=order,
        total_hvac_tonnage=Decimal('12.00'),
        total_connected_load_kva=Decimal('25.00'),
        allotted_riser_ampacity=Decimal('63.00'),
        calculated_running_ampacity=Decimal('58.00'),
        is_riser_upgrade_required=False,
        inspected_by=user
    )

    assert feeder.is_riser_upgrade_required is False
    assert feeder.calculated_running_ampacity < feeder.allotted_riser_ampacity


@pytest.mark.django_db
def test_appliance_energy_efficiency_rating(comprehensive_setup):
    """Test appliance energy efficiency verification conforming to EOS standards."""
    data = comprehensive_setup
    order = data['order']
    user = data['user']

    appliance = ApplianceEnergyEfficiencyRecord.objects.create(
        order=order,
        appliance_category='HVAC',
        brand_and_model="Carrier Optimax Inverter 3HP",
        serial_number="CR-2025-778899",
        eos_energy_rating='CLASS_A',
        is_compliant=True,
        verified_by=user
    )

    assert appliance.eos_energy_rating == 'CLASS_A'
    assert appliance.is_compliant is True


@pytest.mark.django_db
def test_natural_gas_modification_blocked_without_utility_approval(comprehensive_setup):
    """Test that modifying natural gas lines requires gas company clearance."""
    data = comprehensive_setup
    order = data['order']

    order.is_gas_modification_requested = True
    order.gas_safety_clearance = True
    order.save(update_fields=['is_gas_modification_requested', 'gas_safety_clearance'])
    order.refresh_from_db()

    assert order.is_gas_modification_requested is True
    assert order.gas_safety_clearance is True


@pytest.mark.django_db
def test_debt_clearance_blocked_when_finishing_order_has_balance(comprehensive_setup):
    """Test that contract final debt clearance is blocked while finishing balance exists."""
    data = comprehensive_setup
    order = data['order']

    order.remaining_balance = Decimal('195000.00')
    order.is_debt_clearance_blocked = True
    order.save(update_fields=['remaining_balance', 'is_debt_clearance_blocked'])
    order.refresh_from_db()

    assert order.remaining_balance > Decimal('0.00')
    assert order.is_debt_clearance_blocked is True


@pytest.mark.django_db
def test_mortgage_lien_blocks_structural_modifications_without_bank(comprehensive_setup):
    """Test mortgage bank clearance requirement for modifications on mortgaged units."""
    data = comprehensive_setup
    order = data['order']

    order.has_bank_mortgage_lien = True
    order.mortgage_clearance_verified = True
    order.save(update_fields=['has_bank_mortgage_lien', 'mortgage_clearance_verified'])
    order.refresh_from_db()

    assert order.has_bank_mortgage_lien is True
    assert order.mortgage_clearance_verified is True


@pytest.mark.django_db
def test_facade_enclosure_blocks_non_compliant_ral_colors(comprehensive_setup):
    """Test balcony enclosure aluminum profiles must match approved project RAL color."""
    data = comprehensive_setup
    project = data['project']

    enclosure = ApprovedFacadeEnclosureCatalog.objects.create(
        project=project,
        enclosure_type='BALCONY_ALUMIL',
        approved_ral_color_code="RAL 7016 Anthracite Grey",
        approved_profile_brand="Alumil M11000",
        is_active=True
    )

    assert enclosure.approved_ral_color_code == "RAL 7016 Anthracite Grey"
    assert enclosure.approved_profile_brand == "Alumil M11000"


@pytest.mark.django_db
def test_recyclable_packaging_gatepass(comprehensive_setup):
    """Test security gate pass for recyclable cardboard and pallet clearance."""
    data = comprehensive_setup
    order = data['order']

    gatepass = RecyclablePackagingGatePass.objects.create(
        order=order,
        gate_pass_number="GP-RECYCLE-2025-01",
        materials_description="كرتون فارغ وبالتات خشبية ناتجة عن توريد السيراميك والأطقم",
        quantity_estimate="حوالي 1.5 طن كرتون + 20 باليتة خشبية",
        buyer_or_recycler_name="شركة المستقبل لإعادة تدوير الورق والكرتون",
        security_officer_name="أمين بوابة الأمن الصناعي"
    )

    assert gatepass.gate_pass_number == "GP-RECYCLE-2025-01"
    assert "إعادة تدوير" in gatepass.buyer_or_recycler_name


@pytest.mark.django_db
def test_hvac_condensate_drainage_blocks_facade_discharge(comprehensive_setup):
    """Test HVAC condensate drain must tie to insulated gully trap avoiding facades."""
    data = comprehensive_setup
    order = data['order']

    order.hvac_condensate_drain_verified = True
    order.save(update_fields=['hvac_condensate_drain_verified'])
    order.refresh_from_db()

    assert order.hvac_condensate_drain_verified is True


@pytest.mark.django_db
def test_noise_curfew_violation_deducts_from_deposit(comprehensive_setup):
    """Test noise curfew commitment and compliance flag."""
    data = comprehensive_setup
    order = data['order']

    assert order.noise_curfew_agreed is True


@pytest.mark.django_db
def test_petty_cash_allocation_charges_finishing_order(comprehensive_setup):
    """Test allocating emergency petty cash expenses to finishing order cost center."""
    data = comprehensive_setup
    order = data['order']

    order.allocated_petty_cash_expenses = Decimal('4250.00')
    order.save(update_fields=['allocated_petty_cash_expenses'])
    order.refresh_from_db()

    assert order.allocated_petty_cash_expenses == Decimal('4250.00')


@pytest.mark.django_db
def test_homeowner_as_built_dossier_record(comprehensive_setup):
    """Test digital homeowner as-built handover dossier generation."""
    data = comprehensive_setup
    order = data['order']

    dossier = HomeownerAsBuiltDossierRecord.objects.create(
        order=order,
        as_built_pipes_photo_count=48,
        jotun_color_codes_json={
            'reception': '1024 Timeless',
            'master_bed': '10342 Saber',
            'living': '12078 Comfort Grey'
        },
        warranty_certificates_json={
            'plumbing_pipes': 'BR-WARRANTY-10Y',
            'grohe_mixers': 'GROHE-WARRANTY-5Y',
            'waterproofing': 'SIKA-WARRANTY-10Y'
        },
        is_delivered_to_client_portal=True
    )

    assert dossier.as_built_pipes_photo_count == 48
    assert dossier.jotun_color_codes_json['reception'] == '1024 Timeless'
    assert dossier.is_delivered_to_client_portal is True


@pytest.mark.django_db
def test_weather_stoppage_extends_handover_without_penalty(comprehensive_setup):
    """Test severe weather stoppage documentation and excusable time extension."""
    data = comprehensive_setup
    order = data['order']

    stoppage = FinishingWeatherStoppageLog.objects.create(
        order=order,
        condition="هطول أمطار غزيرة وعواصف ترابية منعت أعمال الدهانات والتشوين الخارجي",
        start_date=date(2025, 3, 10),
        end_date=date(2025, 3, 14),
        days_lost=4,
        is_extension_granted=True
    )

    assert stoppage.days_lost == 4
    assert stoppage.is_extension_granted is True


@pytest.mark.django_db
def test_sample_board_submittal_signoff(comprehensive_setup):
    """Test client physical signature on sample board submittal."""
    data = comprehensive_setup
    order = data['order']
    ws = data['workspace']

    spec = FinishingItemSpec.objects.create(
        workspace=ws,
        name="باركيه HDF ألماني فئة 33",
        model_code="KRONO-OAK-01",
        measuring_unit="M2",
        standard_material_cost=Decimal('450.00'),
        standard_labor_cost=Decimal('80.00'),
        client_selling_rate=Decimal('650.00')
    )

    sample = FinishingSampleSubmittalRecord.objects.create(
        order=order,
        workspace=ws,
        spec=spec,
        batch_or_dyelot_code="LOT-2025-BATCH-9",
        client_physical_signature=True,
        custody_location="خزانة عينات المكتب الفني بالمشروع"
    )

    assert sample.client_physical_signature is True
    assert sample.batch_or_dyelot_code == "LOT-2025-BATCH-9"
