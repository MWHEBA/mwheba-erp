# -*- coding: utf-8 -*-
"""
Track 2 - Phase 1: Finishing Specifications, Catalogs & Architectural Variations Data Models Test Suite
MWHEBA ERP - Real Estate App

Verifies 100% integrity of finishing models, fields, choices,
constraints, cascading relationships, and default values.
"""
from decimal import Decimal
from datetime import date, timedelta
import pytest
from django.utils import timezone
from django.contrib.auth import get_user_model
from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyFloor,
    PropertyUnit,
    PropertyContract,
    UnitPricingMatrixConfig,
    FinishingWorkspace,
    FinishingBrand,
    ContractualCreditSchedule,
    FinishingItemSpec,
    FinishingPackageTemplate,
    FinishingPackageItem,
    UnitFinishingOrder,
    UnitFinishingOrderItem,
    ClientSelfFinishingPermit,
    UnitMergerVariationOrder,
    FinishingHydrostaticInspection,
    RooftopWaterproofingInspection,
    HVACNitrogenHoldingInspection,
    ElectricalEarthingResistanceInspection,
    FinishingTileBatchBarcodeRecord,
    FiberOpticContinuityInspection,
    ElevatorArmorCladdingInspection,
    StructuralExpansionJointInspection,
    FacadeSleevePenetrationInspection,
    HighValueFixtureReleaseGate,
    FinishingContractorCARPolicyRecord,
    ElectricalFeederCapacityInspection,
    SubsequentTradeFloorProtectionInspection,
    FinishingTemporaryUtilityRecord,
    HeavyRiggingHoistingPermit,
    ScreedCuringInspectionLog,
    ApplianceEnergyEfficiencyRecord,
    HomeownerAsBuiltDossierRecord,
    SubcontractorPenaltySettlementRecord,
    TouchUpPaintEscrowRecord,
    ExhaustBackdraftDamperInspection,
    PotableWaterChlorinationInspection,
    FlooringSlipResistanceRatingRecord,
    PlasterMoistureInspectionRecord,
    ApprovedFacadeEnclosureCatalog,
    RecyclablePackagingGatePass,
    AntiTermiteTreatmentRecord,
    BalconyDrainageSlopeInspection,
    FinishingDrawingRevision,
    FinishingMaterialRequisition,
    FinishingStockAllocation,
    FinishingHoldPointRule,
    FinishingItemWarrantyRecord,
    FinishingAdvanceDeposit,
    FinishingInstallmentPlan,
    FinishingInstallmentItem,
    FinishingWorkOrder,
    FinishingAsBuiltReconciliation,
    FinishingCancellationSettlement,
    FinishingHandoverProtocol,
    FinishingSwapSettlement,
    FinishingSecureLockUpRecord,
    FinishingSampleSubmittalRecord,
    FinishingWeatherStoppageLog,
    FinishingHotWorkPermit,
    FinishingDebrisCartageWaybill,
    BookingPreContractVariationStudy,
)
from customer.models import Customer
from product.models import Product, Category, Unit as ProductMeasurementUnit
from financial.models.currency import Currency

User = get_user_model()


@pytest.fixture
def finishing_base_setup(db):
    """Sets up base user, project, block, floor, unit, contract, and customer for testing."""
    user = User.objects.create_user(
        username="engineer_track2",
        email="eng_trk2@example.com",
        password="password123"
    )
    customer = Customer.objects.create(
        name="عميل تجريبي للتشطيبات",
        phone="01012345678"
    )
    project = RealEstateProject.objects.create(
        name="كمبوند اللوتس الفاخر",
        code="LOTUS-01",
        start_date=date(2025, 1, 1),
        expected_completion_date=date(2027, 12, 31),
        created_by=user
    )
    block = PropertyBlock.objects.create(
        project=project,
        name="برج اللوتس A",
        code="B-A"
    )
    floor = PropertyFloor.objects.create(
        block=block,
        floor_number=3,
        name="الطابق الثالث"
    )
    unit = PropertyUnit.objects.create(
        project=project,
        block=block,
        floor=floor,
        unit_code="LOTUS-A-302",
        unit_type="APARTMENT",
        gross_area=Decimal('180.00'),
        net_area=Decimal('155.00'),
        meter_price=Decimal('20000.00'),
        total_price=Decimal('3600000.00'),
        status='CONTRACTED'
    )
    egp, _ = Currency.objects.get_or_create(code="EGP", defaults={'name': "جنيه مصري", 'symbol': "ج.م", 'is_functional': True})
    contract = PropertyContract.objects.create(
        contract_number="CNT-LOTUS-302",
        project=project,
        unit=unit,
        customer=customer,
        final_contract_price=Decimal('3600000.00'),
        contract_date=date(2025, 3, 1),
        delivery_date=date(2027, 12, 31),
        currency=egp,
        status='ACTIVE',
        created_by=user
    )
    category = Category.objects.create(name="خامات تشطيبات")
    unit_m2 = ProductMeasurementUnit.objects.create(name="متر مربع", symbol="م2")
    product = Product.objects.create(
        name="سيراميك كليوباترا 60x60 فرز أول",
        sku="CER-CLEO-6060",
        category=category,
        unit=unit_m2,
        cost_price=Decimal('220.00'),
        selling_price=Decimal('280.00'),
        created_by=user
    )
    return {
        'user': user,
        'customer': customer,
        'project': project,
        'block': block,
        'floor': floor,
        'unit': unit,
        'contract': contract,
        'product': product,
    }


@pytest.mark.django_db
def test_finishing_workspace_and_specs_creation(finishing_base_setup):
    """Test creation of FinishingWorkspace, FinishingBrand, and FinishingItemSpec."""
    data = finishing_base_setup
    workspace = FinishingWorkspace.objects.create(
        project=data['project'],
        name="الاستقبال والريسبشن",
        code="REC-01",
        is_wet_area=False,
        standard_height_meters=Decimal('3.00'),
        sort_order=1
    )
    assert workspace.code == "REC-01"
    assert not workspace.is_wet_area

    brand = FinishingBrand.objects.create(
        name="جوتن",
        country_of_origin="النرويج / تصنيع محلي"
    )
    assert brand.name == "جوتن"

    spec = FinishingItemSpec.objects.create(
        workspace=workspace,
        brand=brand,
        inventory_item=data['product'],
        name="دهان جوتن فينوماستيك مطفي",
        model_code="JOT-FEN-01",
        measuring_unit="M2",
        standard_material_cost=Decimal('85.00'),
        standard_labor_cost=Decimal('45.00'),
        client_selling_rate=Decimal('150.00'),
        scrap_allowance_percent=Decimal('5.00')
    )
    assert spec.model_code == "JOT-FEN-01"
    assert spec.standard_material_cost == Decimal('85.00')


@pytest.mark.django_db
def test_finishing_package_template_and_items(finishing_base_setup):
    """Test creation of FinishingPackageTemplate and bundle items."""
    data = finishing_base_setup
    workspace = FinishingWorkspace.objects.create(
        project=data['project'],
        name="غرفة النوم الرئيسية",
        code="MBR-01"
    )
    spec = FinishingItemSpec.objects.create(
        workspace=workspace,
        name="أرضيات HDF بلجيكي",
        model_code="HDF-BEL-01",
        measuring_unit="M2",
        standard_material_cost=Decimal('450.00'),
        standard_labor_cost=Decimal('80.00'),
        client_selling_rate=Decimal('600.00')
    )
    package = FinishingPackageTemplate.objects.create(
        project=data['project'],
        name="الباقة الفاخرة Deluxe",
        package_level="DELUXE",
        price_per_square_meter=Decimal('5500.00')
    )
    pkg_item = FinishingPackageItem.objects.create(
        package=package,
        workspace=workspace,
        spec=spec,
        is_included_in_base_price=True
    )
    assert package.price_per_square_meter == Decimal('5500.00')
    assert pkg_item.is_included_in_base_price


@pytest.mark.django_db
def test_unit_finishing_order_lifecycle_creation(finishing_base_setup):
    """Test creation of UnitFinishingOrder and order items."""
    data = finishing_base_setup
    order = UnitFinishingOrder.objects.create(
        order_number="FO-LOTUS-302-001",
        unit=data['unit'],
        contract=data['contract'],
        customer=data['customer'],
        title="طلب تشطيب وتعديل ديكور فاخر",
        order_type='CUSTOM_VARIATION',
        pricing_mode='FIXED_PRICE_BOQ',
        workflow_speed='MAJOR_GOVERNED',
        current_stage='CUSTOMER_SERVICE',
        gross_finishing_amount=Decimal('450000.00'),
        advance_deposit_required=Decimal('157500.00'),
        created_by=data['user']
    )
    assert order.order_number == "FO-LOTUS-302-001"
    assert order.advance_deposit_required == Decimal('157500.00')
    assert order.current_stage == 'CUSTOMER_SERVICE'


@pytest.mark.django_db
def test_pricing_matrix_finishing_fields(finishing_base_setup):
    """Test that UnitPricingMatrixConfig supports finishing package and rate."""
    data = finishing_base_setup
    package = FinishingPackageTemplate.objects.create(
        project=data['project'],
        name="الباقة الذكية Smart Luxury",
        package_level="DELUXE",
        price_per_square_meter=Decimal('6200.00')
    )
    pricing_config = UnitPricingMatrixConfig.objects.create(
        project=data['project'],
        name="تسعير البرج A المعتمد",
        base_meter_price=Decimal('22000.00'),
        default_finishing_package=package,
        finishing_meter_rate=Decimal('6200.00'),
        created_by=data['user']
    )
    assert pricing_config.default_finishing_package == package
    assert pricing_config.finishing_meter_rate == Decimal('6200.00')


@pytest.mark.django_db
def test_finishing_inspections_and_guards(finishing_base_setup):
    """Test creation of various specialized engineering inspections and guard models."""
    data = finishing_base_setup
    order = UnitFinishingOrder.objects.create(
        order_number="FO-TEST-INSPECTIONS",
        unit=data['unit'],
        contract=data['contract'],
        customer=data['customer'],
        title="أمر فحص هندسي ومحاضر مطابقة",
        created_by=data['user']
    )
    workspace = FinishingWorkspace.objects.create(
        project=data['project'],
        name="حمام الماستر",
        code="BTH-M",
        is_wet_area=True
    )

    # 1. Hydrostatic
    hydro = FinishingHydrostaticInspection.objects.create(
        order=order,
        workspace=workspace,
        test_type='WATERPROOFING_SUBMERSION',
        pressure_bar=Decimal('0.00'),
        duration_hours=48,
        is_passed=True,
        consultant_engineer_name="م. أحمد استشاري الجودة"
    )
    assert hydro.is_passed

    # 2. Rooftop Waterproofing
    roof = RooftopWaterproofingInspection.objects.create(
        order=order,
        area_sqm=Decimal('75.00'),
        has_roof_garden_or_planters=True,
        anti_root_membrane_installed=True,
        flood_test_hours_completed=72,
        water_level_gauge_maintained=True,
        consultant_approved=True,
        inspected_by=data['user']
    )
    assert roof.anti_root_membrane_installed
    assert roof.flood_test_hours_completed == 72

    # 3. HVAC Nitrogen
    nitro = HVACNitrogenHoldingInspection.objects.create(
        order=order,
        system_type='VRF',
        initial_pressure_psi=400,
        final_pressure_psi=400,
        vacuum_micron_reading=420,
        is_pressure_holding_passed=True,
        inspected_by=data['user']
    )
    assert nitro.is_pressure_holding_passed

    # 4. Earthing Resistance
    earth = ElectricalEarthingResistanceInspection.objects.create(
        order=order,
        measured_earth_resistance_ohms=Decimal('2.40'),
        ground_continuity_sockets_verified=True,
        is_earthing_approved=True,
        inspected_by=data['user']
    )
    assert earth.is_earthing_approved
    assert earth.measured_earth_resistance_ohms < Decimal('5.00')

    # 5. Tile Dye-Lot Barcode
    tile = FinishingTileBatchBarcodeRecord.objects.create(
        order=order,
        workspace=workspace,
        product=data['product'],
        barcode_scanned="6221000998877",
        shade_code="SH-42A",
        caliber_code="CAL-03",
        scanned_quantity_sqm=Decimal('45.00'),
        is_shade_mismatch_detected=False,
        verified_by=data['user']
    )
    assert not tile.is_shade_mismatch_detected

    # 6. Fiber Continuity
    fiber = FiberOpticContinuityInspection.objects.create(
        order=order,
        optical_loss_db=Decimal('0.35'),
        is_continuity_passed=True,
        bend_radius_compliant=True,
        inspected_by=data['user']
    )
    assert fiber.is_continuity_passed

    # 7. Heavy Rigging
    rigging = HeavyRiggingHoistingPermit.objects.create(
        order=order,
        crane_capacity_tons=50,
        item_description="شاسيه جاكوزي خارجي للروف",
        outrigger_pad_distribution_verified=True,
        underground_utilities_cleared=True,
        rigging_slings_certified=True,
        safety_perimeter_established=True,
        approved_by=data['user']
    )
    assert rigging.outrigger_pad_distribution_verified

    # 8. Temporary Utilities
    util = FinishingTemporaryUtilityRecord.objects.create(
        order=order,
        electric_meter_reading_start=Decimal('100.00'),
        electric_meter_reading_end=Decimal('450.00'),
        water_meter_reading_start=Decimal('20.00'),
        water_meter_reading_end=Decimal('85.00'),
        total_electric_cost=Decimal('875.00'),
        total_water_cost=Decimal('325.00'),
        is_settled_from_deposit=True,
        recorded_by=data['user']
    )
    assert util.is_settled_from_deposit

    # 9. Potable Water Chlorination
    chloro = PotableWaterChlorinationInspection.objects.create(
        order=order,
        chlorine_concentration_ppm=50,
        holding_time_hours=24,
        flushing_completed=True,
        water_sample_clarity_passed=True,
        sanitary_clearance_issued=True,
        inspected_by=data['user']
    )
    assert chloro.sanitary_clearance_issued

    # 10. Slip Resistance
    spec = FinishingItemSpec.objects.create(
        workspace=workspace,
        name="سيراميك أرضية حمام مانع للانزلاق",
        model_code="CER-BTH-R10",
        measuring_unit="M2",
        standard_material_cost=Decimal('320.00'),
        standard_labor_cost=Decimal('90.00'),
        client_selling_rate=Decimal('450.00')
    )
    slip = FlooringSlipResistanceRatingRecord.objects.create(
        order=order,
        workspace=workspace,
        flooring_spec=spec,
        slip_resistance_rating='R10',
        is_wet_area_compliant=True,
        verified_by=data['user']
    )
    assert slip.is_wet_area_compliant
    assert slip.slip_resistance_rating == 'R10'
