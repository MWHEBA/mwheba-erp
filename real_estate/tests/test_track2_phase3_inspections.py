# -*- coding: utf-8 -*-
"""
Track 2 - Phase 3: Hold-Points, Inspections & Quality Verification Test Suite
MWHEBA ERP - Real Estate App

Verifies 100% adherence to technical hold points, MEP verification, civil quality,
HSE safety permits, and handover prerequisites.
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
    FinishingItemSpec,
    UnitFinishingOrder,
    FinishingHydrostaticInspection,
    PlasterMoistureInspectionRecord,
    HVACNitrogenHoldingInspection,
    ElectricalEarthingResistanceInspection,
    ScreedCuringInspectionLog,
    AntiTermiteTreatmentRecord,
    BalconyDrainageSlopeInspection,
    RooftopWaterproofingInspection,
    ExhaustBackdraftDamperInspection,
    PotableWaterChlorinationInspection,
    FlooringSlipResistanceRatingRecord,
    HighValueFixtureReleaseGate,
    FinishingSecureLockUpRecord,
    FinishingHotWorkPermit,
    FinishingTileBatchBarcodeRecord,
    FiberOpticContinuityInspection,
    ElevatorArmorCladdingInspection,
    SubsequentTradeFloorProtectionInspection,
    TouchUpPaintEscrowRecord,
)
from customer.models import Customer
from financial.models.currency import Currency
from supplier.models import Supplier
from product.models import Product, Category, Unit as ProductMeasurementUnit

from real_estate.services.finishing_inspection_service import (
    FinishingHoldPointEngine,
    FinishingInspectionService,
)

User = get_user_model()


@pytest.fixture
def inspection_setup(db):
    """Sets up base records for inspection test cases."""
    user = User.objects.create_user(
        username="qa_engineer_phase3",
        email="qa_p3@example.com",
        password="password123"
    )
    customer = Customer.objects.create(
        name="عميل اختبار المرحلة الثالثة",
        code="CUST-P3-001",
        phone="01099887766"
    )
    project = RealEstateProject.objects.create(
        name="مشروع الجودة الهندسية",
        code="QA-PRJ-01",
        start_date=date(2025, 1, 1),
        expected_completion_date=date(2027, 12, 31),
        created_by=user
    )
    block = PropertyBlock.objects.create(
        project=project,
        name="عمارة 20",
        code="B20"
    )
    floor = PropertyFloor.objects.create(
        block=block,
        floor_number=3,
        name="الدور الثالث"
    )
    unit = PropertyUnit.objects.create(
        project=project,
        block=block,
        floor=floor,
        unit_code="QA-U301",
        unit_type="APARTMENT",
        gross_area=Decimal('220.00'),
        net_area=Decimal('190.00'),
        meter_price=Decimal('30000.00'),
        total_price=Decimal('6600000.00'),
        status='CONTRACTED'
    )
    egp, _ = Currency.objects.get_or_create(code="EGP", defaults={'name': "جنيه مصري", 'symbol': "ج.م", 'is_functional': True})
    contract = PropertyContract.objects.create(
        contract_number="CNT-QA-301",
        project=project,
        unit=unit,
        customer=customer,
        final_contract_price=Decimal('6600000.00'),
        contract_date=date(2025, 3, 1),
        delivery_date=date(2027, 8, 31),
        currency=egp,
        status='ACTIVE',
        created_by=user
    )
    order = UnitFinishingOrder.objects.create(
        order_number="FO-QA-TEST-001",
        unit=unit,
        contract=contract,
        customer=customer,
        title="أمر تشطيب فحص الجودة الميدانية",
        current_stage='IN_EXECUTION',
        created_by=user
    )
    bath_ws = FinishingWorkspace.objects.create(
        project=project,
        name="حمام الماستر",
        code="M-BATH"
    )
    reception_ws = FinishingWorkspace.objects.create(
        project=project,
        name="ريسبشن الاستقبال",
        code="RECEP-01"
    )
    balcony_ws = FinishingWorkspace.objects.create(
        project=project,
        name="شرفة الواجهة الرئيسية",
        code="BALC-01"
    )

    return {
        'user': user,
        'customer': customer,
        'project': project,
        'unit': unit,
        'contract': contract,
        'order': order,
        'bath_ws': bath_ws,
        'reception_ws': reception_ws,
        'balcony_ws': balcony_ws,
    }


@pytest.mark.django_db
def test_sequential_hold_point_blocks_flooring_materials_without_hydrostatic_test(inspection_setup):
    """Test that flooring materials for wet areas are blocked without a passed hydrostatic test."""
    data = inspection_setup
    order = data['order']
    bath = data['bath_ws']

    # Blocked initially because no test recorded
    can_issue, error = FinishingHoldPointEngine.can_issue_flooring_materials(order, bath)
    assert can_issue is False
    assert "اختبار العزل والضغط الهيدروستاتيكي" in error

    # Record a failed test (e.g., pressure dropped)
    FinishingInspectionService.record_hydrostatic_test(
        order=order,
        workspace=bath,
        test_type='WATER_PROOFING',
        pressure_bar=Decimal('0.00'),
        duration_hours=48,
        is_passed=False,
        consultant_engineer_name="م. أحمد استشاري العزل",
        notes="تسريب طفيف عند زاوية الصرف"
    )
    can_issue, error = FinishingHoldPointEngine.can_issue_flooring_materials(order, bath)
    assert can_issue is False

    # Record a successful test after re-waterproofing
    FinishingInspectionService.record_hydrostatic_test(
        order=order,
        workspace=bath,
        test_type='WATER_PROOFING',
        pressure_bar=Decimal('0.00'),
        duration_hours=48,
        is_passed=True,
        consultant_engineer_name="م. أحمد استشاري العزل",
        notes="ثبات منسوب المياه 48 ساعة وبدون أي نشع"
    )
    can_issue, error = FinishingHoldPointEngine.can_issue_flooring_materials(order, bath)
    assert can_issue is True
    assert error is None


@pytest.mark.django_db
def test_screed_curing_blocks_flooring_before_7_days(inspection_setup):
    """Test that tiling is blocked before completing 7 days of water curing for screed."""
    data = inspection_setup
    order = data['order']
    reception = data['reception_ws']

    # Record screed log with only 4 days of curing
    FinishingInspectionService.record_screed_curing(
        order=order,
        workspace=reception,
        screed_pouring_date=timezone.now().date() - timedelta(days=4),
        water_curing_days_completed=4,
        moisture_percentage=Decimal('18.00'),
        inspected_by=data['user']
    )
    can_issue, error = FinishingHoldPointEngine.can_issue_flooring_materials(order, reception)
    assert can_issue is False
    assert "7 أيام معالجة بالماء" in error

    # Update/Record completed curing after 7 days
    FinishingInspectionService.record_screed_curing(
        order=order,
        workspace=reception,
        screed_pouring_date=timezone.now().date() - timedelta(days=7),
        water_curing_days_completed=7,
        moisture_percentage=Decimal('6.50'),
        inspected_by=data['user']
    )
    can_issue, error = FinishingHoldPointEngine.can_issue_flooring_materials(order, reception)
    assert can_issue is True
    assert error is None


@pytest.mark.django_db
def test_plaster_moisture_blocks_painting_above_12_pct(inspection_setup):
    """Test that paint materials are blocked if plaster moisture exceeds 12%."""
    data = inspection_setup
    order = data['order']
    reception = data['reception_ws']

    # Record high moisture reading (15.5%)
    FinishingInspectionService.record_plaster_moisture(
        order=order,
        workspace=reception,
        tested_wall_description="الحائط الشرقي للريسبشن",
        moisture_percentage=Decimal('15.50'),
        site_qa_engineer=data['user']
    )
    can_issue, error = FinishingHoldPointEngine.can_issue_painting_materials(order, reception)
    assert can_issue is False
    assert "تجاوز رطوبة المحارة" in error
    assert "15.5" in error

    # Record safe moisture reading after proper ventilation (8.2%)
    FinishingInspectionService.record_plaster_moisture(
        order=order,
        workspace=reception,
        tested_wall_description="الحائط الشرقي للريسبشن - إعادة فحص",
        moisture_percentage=Decimal('8.20'),
        site_qa_engineer=data['user']
    )
    can_issue, error = FinishingHoldPointEngine.can_issue_painting_materials(order, reception)
    assert can_issue is True
    assert error is None


@pytest.mark.django_db
def test_hvac_nitrogen_pressure_and_backdraft_damper_block_ceiling_closure(inspection_setup):
    """Test ceiling closure hold points: HVAC nitrogen pressure & exhaust backdraft damper."""
    data = inspection_setup
    order = data['order']
    bath = data['bath_ws']

    # Ceiling closure initially blocked because no HVAC test
    can_close, error = FinishingHoldPointEngine.can_close_ceilings(order, bath)
    assert can_close is False
    assert "كبس النيتروجين" in error

    # Pass HVAC nitrogen test
    FinishingInspectionService.record_hvac_pressure_test(
        order=order,
        system_type='CONCEALED',
        initial_pressure_psi=Decimal('450.00'),
        final_pressure_psi=Decimal('450.00'),
        test_duration_hours=24,
        vacuum_micron_reading=Decimal('350.00'),
        inspected_by=data['user']
    )

    # In bathroom, still blocked without backdraft damper inspection
    can_close, error = FinishingHoldPointEngine.can_close_ceilings(order, bath)
    assert can_close is False
    assert "رداد عدم الرجوع" in error

    # Pass damper inspection
    ExhaustBackdraftDamperInspection.objects.create(
        order=order,
        workspace=bath,
        damper_type='BUTTERFLY',
        damper_direction_verified=True,
        free_blade_movement_tested=True,
        ceiling_closure_permitted=True,
        inspected_by=data['user']
    )
    can_close, error = FinishingHoldPointEngine.can_close_ceilings(order, bath)
    assert can_close is True
    assert error is None


@pytest.mark.django_db
def test_earthing_resistance_blocks_smart_home_power_above_5_ohms(inspection_setup):
    """Test that main power energization is blocked if earthing pit resistance > 5 ohms."""
    data = inspection_setup
    order = data['order']

    # Initially blocked without earthing inspection
    can_power, error = FinishingHoldPointEngine.can_energize_main_power(order)
    assert can_power is False
    assert "بئر التأريض" in error

    # Fail test with high resistance (7.8 ohms)
    FinishingInspectionService.record_earthing_resistance(
        order=order,
        measured_earth_resistance_ohms=Decimal('7.80'),
        ground_continuity_sockets_verified=True,
        inspected_by=data['user']
    )
    can_power, error = FinishingHoldPointEngine.can_energize_main_power(order)
    assert can_power is False
    assert "7.8" in error

    # Pass test with proper earthing chemical treatment (2.9 ohms)
    FinishingInspectionService.record_earthing_resistance(
        order=order,
        measured_earth_resistance_ohms=Decimal('2.90'),
        ground_continuity_sockets_verified=True,
        inspected_by=data['user']
    )
    can_power, error = FinishingHoldPointEngine.can_energize_main_power(order)
    assert can_power is True
    assert error is None


@pytest.mark.django_db
def test_anti_termite_treatment_blocks_parquet_installation(inspection_setup):
    """Test that parquet installation requires verified anti-termite chemical treatment."""
    data = inspection_setup
    order = data['order']
    reception = data['reception_ws']

    # Blocked without termite record
    can_install, error = FinishingHoldPointEngine.can_install_wood_parquet(order, reception)
    assert can_install is False
    assert "النمل الأبيض" in error

    # Record verified anti-termite treatment
    AntiTermiteTreatmentRecord.objects.create(
        order=order,
        workspace=reception,
        chemical_used="Bifenthrin 10% EC",
        treated_area_m2=Decimal('85.00'),
        certified_pest_control_company="المجموعة الألمانية لمكافحة الحشرات والآفات",
        warranty_certificate_number="TERM-CERT-2025-09",
        is_verified_by_site_engineer=True
    )
    can_install, error = FinishingHoldPointEngine.can_install_wood_parquet(order, reception)
    assert can_install is True
    assert error is None


@pytest.mark.django_db
def test_high_value_fixtures_blocked_before_final_paint_and_secure_lockup(inspection_setup):
    """Test release gates for high-value smart/sanitary fixtures."""
    data = inspection_setup
    order = data['order']
    spec = FinishingItemSpec.objects.create(
        workspace=data['bath_ws'],
        name="خلاط دفن ذهبي سمارت جروهي",
        model_code="GROHE-SMART-GOLD-01",
        measuring_unit="PCE",
        standard_material_cost=Decimal('25000.00'),
        standard_labor_cost=Decimal('1000.00'),
        client_selling_rate=Decimal('35000.00')
    )

    # Blocked without lockup record
    can_release, error = FinishingHoldPointEngine.can_release_high_value_fixtures(order, spec)
    assert can_release is False
    assert "قفل وتأمين الشقة" in error

    # Create lockup record
    FinishingInspectionService.record_secure_lockup(
        order=order,
        key_custody_officer=data['user'],
        key_tag_code="KEY-QA-301",
        exterior_door_installed=True,
        access_restricted=True
    )

    # Blocked without authorized release gate
    can_release, error = FinishingHoldPointEngine.can_release_high_value_fixtures(order, spec)
    assert can_release is False
    assert "إذن الصرف الاستثنائي" in error

    # Authorize release gate
    HighValueFixtureReleaseGate.objects.create(
        order=order,
        item_spec=spec,
        is_painting_completed=True,
        is_main_door_securely_locked=True,
        warehouse_release_authorized=True,
        authorized_by=data['user']
    )
    can_release, error = FinishingHoldPointEngine.can_release_high_value_fixtures(order, spec)
    assert can_release is True
    assert error is None


@pytest.mark.django_db
def test_balcony_slope_blocks_signoff_on_ponding(inspection_setup):
    """Test that balcony signoff is blocked if ponding or poor slope is detected."""
    data = inspection_setup
    order = data['order']
    balcony = data['balcony_ws']

    # Record inspection with water ponding
    BalconyDrainageSlopeInspection.objects.create(
        order=order,
        workspace=balcony,
        is_gravity_flow_successful=False,
        water_ponding_detected=True,
        drainage_slope_percentage=Decimal('0.20'),
        inspected_by=data['user']
    )
    can_signoff, error = FinishingHoldPointEngine.can_signoff_balcony(order, balcony)
    assert can_signoff is False
    assert "ركود مائي" in error

    # Rectify tiles and record successful slope inspection (1.5% slope)
    BalconyDrainageSlopeInspection.objects.create(
        order=order,
        workspace=balcony,
        is_gravity_flow_successful=True,
        water_ponding_detected=False,
        drainage_slope_percentage=Decimal('1.50'),
        inspected_by=data['user']
    )
    can_signoff, error = FinishingHoldPointEngine.can_signoff_balcony(order, balcony)
    assert can_signoff is True
    assert error is None


@pytest.mark.django_db
def test_rooftop_waterproofing_requires_72h_flood_and_anti_root_membrane(inspection_setup):
    """Test penthouse roof waterproofing requires 72h flood test and anti-root barrier."""
    data = inspection_setup
    order = data['order']

    # Incomplete flood test (only 36h) and no anti-root membrane
    RooftopWaterproofingInspection.objects.create(
        order=order,
        area_sqm=Decimal('150.00'),
        has_roof_garden_or_planters=True,
        anti_root_membrane_installed=False,
        flood_test_hours_completed=36,
        water_level_gauge_maintained=True,
        consultant_approved=False,
        inspected_by=data['user']
    )
    can_signoff, error = FinishingHoldPointEngine.can_signoff_rooftop_waterproofing(order)
    assert can_signoff is False
    assert "36 ساعة من أصل 72" in error

    # Complete 72h but missing anti-root
    RooftopWaterproofingInspection.objects.create(
        order=order,
        area_sqm=Decimal('150.00'),
        has_roof_garden_or_planters=True,
        anti_root_membrane_installed=False,
        flood_test_hours_completed=72,
        water_level_gauge_maintained=True,
        consultant_approved=True,
        inspected_by=data['user']
    )
    can_signoff, error = FinishingHoldPointEngine.can_signoff_rooftop_waterproofing(order)
    assert can_signoff is False
    assert "Anti-Root Membrane" in error

    # Fully compliant
    RooftopWaterproofingInspection.objects.create(
        order=order,
        area_sqm=Decimal('150.00'),
        has_roof_garden_or_planters=True,
        anti_root_membrane_installed=True,
        flood_test_hours_completed=72,
        water_level_gauge_maintained=True,
        consultant_approved=True,
        inspected_by=data['user']
    )
    can_signoff, error = FinishingHoldPointEngine.can_signoff_rooftop_waterproofing(order)
    assert can_signoff is True
    assert error is None


@pytest.mark.django_db
def test_subsequent_trade_floor_protection_signoff_required(inspection_setup):
    """Test that entry of carpentry and painting trades requires floor protection inspection."""
    data = inspection_setup
    order = data['order']
    reception = data['reception_ws']

    # Blocked initially
    can_enter, error = FinishingHoldPointEngine.can_allow_subsequent_trades(order, reception)
    assert can_enter is False
    assert "تغليف وحماية الأرضيات" in error

    # Record verified floor protection
    SubsequentTradeFloorProtectionInspection.objects.create(
        order=order,
        workspace=reception,
        flooring_type='MARBLE',
        heavy_polyethylene_sheet_installed=True,
        corrugated_cardboard_or_geotextile_installed=True,
        joints_taped_securely=True,
        carpentry_painting_entry_permitted=True,
        inspected_by=data['user']
    )
    can_enter, error = FinishingHoldPointEngine.can_allow_subsequent_trades(order, reception)
    assert can_enter is True
    assert error is None


@pytest.mark.django_db
def test_hot_work_permit_blocks_open_flame_without_extinguishers(inspection_setup):
    """Test that hot works (torches, welding) require safety permit and fire extinguishers."""
    data = inspection_setup
    order = data['order']
    bath = data['bath_ws']

    supplier = Supplier.objects.create(
        name="شركة الأهرام للعزل",
        code="SUP-AHR-01"
    )

    # Blocked without permit
    can_weld, error = FinishingHoldPointEngine.can_allow_hot_works(order, bath, "شركة الأهرام للعزل")
    assert can_weld is False
    assert "تصريح أعمال ساخنة" in error

    # Permit missing fire extinguishers
    FinishingHotWorkPermit.objects.create(
        order=order,
        workspace=bath,
        contractor=supplier,
        work_description="لحام ممبرين بيتومين بالمشعل",
        permit_date=timezone.now().date(),
        fire_extinguishers_verified=False,
        combustible_materials_cleared=True,
        safety_officer_signature="م. مصطفى HSE",
        is_approved=True
    )
    can_weld, error = FinishingHoldPointEngine.can_allow_hot_works(order, bath, "شركة الأهرام للعزل")
    assert can_weld is False
    assert "توفير الطفايات" in error

    # Full compliance
    FinishingHotWorkPermit.objects.create(
        order=order,
        workspace=bath,
        contractor=supplier,
        work_description="لحام ممبرين بيتومين بالمشعل",
        permit_date=timezone.now().date(),
        fire_extinguishers_verified=True,
        combustible_materials_cleared=True,
        safety_officer_signature="م. مصطفى HSE",
        is_approved=True
    )
    can_weld, error = FinishingHoldPointEngine.can_allow_hot_works(order, bath, "شركة الأهرام للعزل")
    assert can_weld is True
    assert error is None


@pytest.mark.django_db
def test_tile_dye_lot_barcode_blocks_mismatched_shade_in_same_workspace(inspection_setup):
    """Test that issuing tiles with mismatched shade or caliber to the same room is flagged and prevented."""
    data = inspection_setup
    order = data['order']
    reception = data['reception_ws']

    category, _ = Category.objects.get_or_create(name="سيراميك وبورسلين")
    measurement_unit, _ = ProductMeasurementUnit.objects.get_or_create(name="متر مربع", symbol="M2")
    product = Product.objects.create(
        name="بورسلين كليوباترا 60x120",
        sku="PORC-CLEO-60120",
        category=category,
        unit=measurement_unit,
        cost_price=Decimal('350.00'),
        selling_price=Decimal('500.00'),
        created_by=data['user']
    )

    # First pallet recorded with Shade A12, Caliber C3
    FinishingTileBatchBarcodeRecord.objects.create(
        order=order,
        workspace=reception,
        product=product,
        barcode_scanned="8430099881122",
        shade_code="A12",
        caliber_code="C3",
        scanned_quantity_sqm=Decimal('50.00'),
        is_shade_mismatch_detected=False,
        verified_by=data['user']
    )

    # Next pallet scanned with identical Shade A12 and Caliber C3
    is_valid, error = FinishingHoldPointEngine.validate_tile_batch_consistency(order, reception, "A12", "C3")
    assert is_valid is True
    assert error is None

    # Next pallet scanned with different Shade B04
    is_valid, error = FinishingHoldPointEngine.validate_tile_batch_consistency(order, reception, "B04", "C3")
    assert is_valid is False
    assert "تفاوت في كود التشغيلة" in error
    assert "B04" in error


@pytest.mark.django_db
def test_final_handover_requires_chlorination_touchup_paint_and_rekeying(inspection_setup):
    """Test client final handover hold points: chlorination certificate, touch-up paint, and cylinder rekeying."""
    data = inspection_setup
    order = data['order']
    reception = data['reception_ws']

    # Handover blocked initially
    can_handover, error = FinishingHoldPointEngine.can_authorize_final_handover(order)
    assert can_handover is False
    assert "تطهير شبكة مياه الشرب بالكلور" in error

    # Pass water chlorination test
    FinishingInspectionService.record_water_chlorination_test(
        order=order,
        chlorine_concentration_ppm=Decimal('55.00'),
        holding_time_hours=24,
        flushing_completed=True,
        water_sample_clarity_passed=True,
        inspected_by=data['user']
    )

    # Handover still blocked without touch-up paint canisters
    can_handover, error = FinishingHoldPointEngine.can_authorize_final_handover(order)
    assert can_handover is False
    assert "دهان الرتوش" in error

    # Escrow touch-up paint
    FinishingInspectionService.record_touchup_paint_escrow(
        order=order,
        workspace=reception,
        paint_brand="Jotun Fenomastic",
        color_code="JOTUN-1024-TIMELESS",
        can_volume_liters=Decimal('1.00'),
        is_sealed_and_labeled=True,
        handed_over_to_site_escrow=True,
        verified_by=data['user']
    )

    # Handover still blocked without builder key deactivation
    can_handover, error = FinishingHoldPointEngine.can_authorize_final_handover(order)
    assert can_handover is False
    assert "إبطال مفتاح الإنشاءات" in error

    # Complete cylinder rekeying and builder key deactivation
    FinishingSecureLockUpRecord.objects.create(
        order=order,
        lockup_date=timezone.now().date(),
        exterior_door_installed=True,
        key_custody_officer=data['user'],
        key_tag_code="KEY-QA-301",
        access_restricted=True,
        builder_key_deactivated=True,
        cylinder_rekeyed_successfully=True
    )

    # All criteria met, handover authorized
    can_handover, error = FinishingHoldPointEngine.can_authorize_final_handover(order)
    assert can_handover is True
    assert error is None
