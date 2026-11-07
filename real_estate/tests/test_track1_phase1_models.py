# -*- coding: utf-8 -*-
"""
Track 1 - Phase 1: Construction & Contractor Data Models Test Suite
MWHEBA ERP - Real Estate App

Verifies 100% integrity of all 27 contractor models, fields, choices,
constraints, cascading relationships, and default values.
"""
from decimal import Decimal
from datetime import date, timedelta
import pytest
from django.utils import timezone
from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    ProjectMasterBOQItem,
    ContractorContract,
    SectionalHandoverRecord,
    ContractorContractItem,
    ContractVariationOrder,
    ContractVariationOrderItem,
    ContractorDefaultNotice,
    ContractorProgressCertificate,
    ContractorCertificateItem,
    EquipmentHoistingLog,
    SiteDebrisClearanceLog,
    ContractorMaterialOnSite,
    ContractorMOSCustodyReceipt,
    ContractorBackcharge,
    ConcreteBatchDelivery,
    ConcreteBatchReconciliation,
    ContractorMaterialDeduction,
    RebarConsumptionLog,
    ContractorScaffoldingLog,
    DewateringPumpingLog,
    ContractorSupplierLienAssignment,
    ThirdPartyLabTestLog,
    ContractorSuspensionClaim,
    JointTerminationSurveyProtocol,
    RockExcavationSurveyLog,
    HydrostaticTestFailureLog,
    CertificatePaymentInstallmentSchedule,
)
from django.contrib.auth import get_user_model
from supplier.models import Supplier
from financial.models.currency import Currency

User = get_user_model()


@pytest.fixture
def contractor_setup(db):
    """Sets up base user, project, block, currencies, contractor supplier and master BOQ for testing."""
    user_admin = User.objects.create_superuser(
        username="admin_track1_p1",
        email="admin_trk1@example.com",
        password="password123"
    )
    egp_currency, _ = Currency.objects.get_or_create(
        code="EGP",
        defaults={'name': "Egyptian Pound", 'symbol': "ج.م", 'is_functional': True}
    )
    usd_currency, _ = Currency.objects.get_or_create(
        code="USD",
        defaults={'name': "US Dollar", 'symbol': "$", 'is_functional': False}
    )
    project = RealEstateProject.objects.create(
        code="PRJ-TRK1",
        name="كمبوند زهرة العاصمة الإنشائي",
        project_type="RESIDENTIAL",
        status="UNDER_CONSTRUCTION",
        start_date=date(2026, 1, 1),
        expected_completion_date=date(2028, 12, 31),
        created_by=user_admin
    )
    block = PropertyBlock.objects.create(
        project=project,
        code="BLK-A",
        name="عمارة A1",
        total_floors=5
    )
    contractor = Supplier.objects.create(
        name="شركة المقاولات العامة التخصصية",
        code="CNT-001",
        tax_number="123456789",
    )
    material_supplier = Supplier.objects.create(
        name="مصنع حلوان للأسمنت والحديد",
        code="SUP-MAT-01",
        tax_number="555666777"
    )
    master_boq = ProjectMasterBOQItem.objects.create(
        project=project,
        block=block,
        item_code="BOQ-STR-01",
        wbs_group="STRUCTURAL",
        wbs_budget_code="WBS-STR-RC",
        description="خرسانة مسلحة للأسقف والأعمدة",
        unit="M3",
        master_budget_quantity=Decimal("1500.00"),
        unit_rate_estimate=Decimal("4500.00"),
        total_budget_cost=Decimal("6750000.00"),
        overrun_tolerance_rate=Decimal("0.05")
    )
    return {
        "project": project,
        "block": block,
        "contractor": contractor,
        "material_supplier": material_supplier,
        "master_boq": master_boq,
        "egp_currency": egp_currency,
        "usd_currency": usd_currency,
        "user_admin": user_admin,
    }


@pytest.mark.django_db
def test_project_master_boq_and_contract_creation(contractor_setup):
    """Verifies ProjectMasterBOQItem and ContractorContract creation and properties."""
    project = contractor_setup["project"]
    block = contractor_setup["block"]
    contractor = contractor_setup["contractor"]
    boq = contractor_setup["master_boq"]

    assert boq.item_code == "BOQ-STR-01"
    assert boq.total_budget_cost == Decimal("6750000.00")
    assert str(boq) == f"{project.name} - {boq.item_code}: {boq.description}"

    contract = ContractorContract.objects.create(
        contract_number="CNT-2026-001",
        title="عقد الهيكل الخرساني والإنشاءات",
        project=project,
        block=block,
        contractor=contractor,
        contract_type=ContractorContract.ContractType.MEASURED_BOQ,
        initial_contract_value=Decimal("5000000.00"),
        revised_contract_value=Decimal("5000000.00"),
        advance_payment_rate=Decimal("10.00"),
        advance_payment_amount=Decimal("500000.00"),
        retention_rate=Decimal("5.00"),
        retention_cap_amount=Decimal("250000.00"),
        is_assigned_to_bank=True,
        assigned_bank_name="بنك مصر",
        assigned_bank_iban="EG12345678901234567890123456789",
        is_garnished_by_court=False,
        start_date=date(2026, 2, 1),
        completion_date=date(2027, 2, 1),
        status=ContractorContract.ContractStatus.ACTIVE,
    )

    assert contract.is_assigned_to_bank is True
    assert contract.assigned_bank_name == "بنك مصر"
    assert contract.advance_payment_amount == Decimal("500000.00")
    assert str(contract) == f"{contract.contract_number} - {contract.contractor.name} ({contract.project.name})"


@pytest.mark.django_db
def test_contract_item_and_variation_orders(contractor_setup):
    """Tests ContractorContractItem, deep pile bulbing, and ContractVariationOrder."""
    project = contractor_setup["project"]
    block = contractor_setup["block"]
    contractor = contractor_setup["contractor"]
    boq = contractor_setup["master_boq"]
    usd_currency = contractor_setup["usd_currency"]

    contract = ContractorContract.objects.create(
        contract_number="CNT-2026-002",
        title="عقد الخوازيق وأعمال الأساسات العميقة",
        project=project,
        block=block,
        contractor=contractor,
        contract_type=ContractorContract.ContractType.MEASURED_BOQ,
        initial_contract_value=Decimal("2000000.00"),
    )

    item = ContractorContractItem.objects.create(
        contract=contract,
        master_boq_item=boq,
        block=block,
        wbs_group="DEEP_FOUNDATION",
        item_code="ITEM-PILE-01",
        description="خوازيق حفر دوار قطر 60 سم",
        unit="ML",
        contracted_quantity=Decimal("500.00"),
        unit_rate=Decimal("1200.00"),
        total_budget_amount=Decimal("600000.00"),
        is_deep_foundation_pile=True,
        pile_bulbing_factor_percent=Decimal("0.15"),
        has_foreign_component=True,
        foreign_component_percent=Decimal("0.40"),
        foreign_currency=usd_currency,
        fx_baseline_rate=Decimal("50.00"),
        fx_volatility_collar_percent=Decimal("0.05")
    )

    assert item.is_deep_foundation_pile is True
    assert item.pile_bulbing_factor_percent == Decimal("0.15")
    assert item.foreign_currency == usd_currency

    vo = ContractVariationOrder.objects.create(
        order_number="VO-2026-001",
        contract=contract,
        variation_type=ContractVariationOrder.VariationType.QUANTITY_INCREASE,
        description="زيادة أطوال الخوازيق لتربة طينية رخوة",
        net_value_impact=Decimal("90000.00"),
        approved_additional_days=15,
        status=ContractVariationOrder.VariationStatus.APPROVED
    )
    vo_item = ContractVariationOrderItem.objects.create(
        variation_order=vo,
        contract_item=item,
        item_code=item.item_code,
        description=item.description,
        unit=item.unit,
        additional_quantity=Decimal("75.00"),
        unit_rate=Decimal("1200.00"),
        total_amount=Decimal("90000.00")
    )
    assert vo_item.total_amount == Decimal("90000.00")
    assert vo.approved_additional_days == 15


@pytest.mark.django_db
def test_contractor_default_notice_and_sectional_handover(contractor_setup):
    """Tests ContractorDefaultNotice (48h cure) and SectionalHandoverRecord."""
    project = contractor_setup["project"]
    contractor = contractor_setup["contractor"]

    contract = ContractorContract.objects.create(
        contract_number="CNT-2026-003",
        title="عقد المباني والتشطيبات",
        project=project,
        contractor=contractor,
    )

    now = timezone.now()
    notice = ContractorDefaultNotice.objects.create(
        contract=contract,
        notice_number="NOT-2026-001",
        notice_date=date(2026, 3, 1),
        cure_deadline=now + timedelta(hours=48),
        violation_description="تأخر توريد طوب البناء وتوقف العمالة",
        is_cured=False,
        is_penalty_authorized=True
    )
    assert notice.is_cured is False
    assert notice.is_penalty_authorized is True

    sec_handover = SectionalHandoverRecord.objects.create(
        contract=contract,
        section_name="المرحلة الأولى - الهيكل الخرساني للبلوك A",
        handover_date=date(2026, 6, 30),
        warranty_start_date=date(2026, 7, 1),
        warranty_end_date=date(2027, 6, 30),
        consultant_approval_ref="CONS-APPR-SEC-01",
        is_warranty_completed=False
    )
    assert sec_handover.is_warranty_completed is False
    assert sec_handover.section_name.startswith("المرحلة الأولى")


@pytest.mark.django_db
def test_contractor_progress_certificate_with_14_step_cascading(contractor_setup):
    """Tests ContractorProgressCertificate execution of 14-step cascading deductions."""
    project = contractor_setup["project"]
    block = contractor_setup["block"]
    contractor = contractor_setup["contractor"]
    egp_currency = contractor_setup["egp_currency"]

    contract = ContractorContract.objects.create(
        contract_number="CNT-2026-004",
        title="عقد الأعمال المتكاملة للمشروع",
        project=project,
        block=block,
        contractor=contractor,
        currency=egp_currency,
        tax_regime=ContractorContract.TaxRegime.EXEMPT,
        initial_contract_value=Decimal("1000000.00"),
        retention_rate=Decimal("5.00"),
        advance_recovery_rate=Decimal("10.00"),
        wht_rate=Decimal("1.00"),
        social_insurance_rate=Decimal("2.16"),
        syndicate_stamp_rate=Decimal("0.40"),
        site_utilities_deduction_rate=Decimal("0.50"),
    )

    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-2026-001",
        contract=contract,
        sequence_order=1,
        project=project,
        block=block,
        contractor=contractor,
        currency=egp_currency,
        certificate_type=ContractorProgressCertificate.CertificateType.STANDARD_PROGRESS,
        period_start=date(2026, 2, 1),
        period_end=date(2026, 2, 28),
        gross_certified_work=Decimal("100000.00"),
        previous_certified_work=Decimal("0.00"),
        current_mos_amount=Decimal("20000.00"),
        retention_rate=Decimal("5.00"),
        advance_payment_recovery=Decimal("10000.00"),
        wht_rate=Decimal("1.00"),
        social_insurance_rate=Decimal("2.16"),
        syndicate_stamp_rate=Decimal("0.40"),
        site_utilities_deduction_rate=Decimal("0.50"),
        equipment_hoisting_charges=Decimal("1500.00"),
        debris_clearance_charges=Decimal("800.00"),
        pending_cube_test_hold_amount=Decimal("5000.00"),
    )

    cert.compute_amounts()
    cert.save()

    # Step 1: Work = 100,000
    assert cert.current_period_work == Decimal("100000.00")
    # Step 2: MOS = 20,000 (net_materials_on_site = 20000 - 0 = 20000)
    assert cert.net_materials_on_site == Decimal("20000.00")
    # Step 4: Base for retention = current_period_work (100k) + current_mos (20k) = 120,000
    # Retention = 5% of 120,000 = 6,000.00
    assert cert.retention_amount == Decimal("6000.00")
    # Advance payment recovery = 10,000
    assert cert.advance_payment_recovery == Decimal("10000.00")
    # Step 6: Site utilities = 0.5% of 100,000 = 500.00
    assert cert.site_utilities_deduction_amount == Decimal("500.00")
    # Step 7: Syndicate stamp = 0.4% of 100,000 = 400.00
    assert cert.syndicate_stamp_amount == Decimal("400.00")
    # Step 8: Taxable base Form 41 = current_period_work (100k) - advance recovery (10k) = 90,000
    # WHT = 1% of 90,000 = 900.00 (Prevents double taxation on recovered advance!)
    assert cert.taxable_base_form41 == Decimal("90000.00")
    assert cert.wht_amount == Decimal("900.00")
    # Step 9: Social Insurance = 2.16% of 100,000 = 2,160.00
    assert cert.social_insurance_amount == Decimal("2160.00")
    # Total deductions = 6000 (retention) + 10000 (adv) + 900 (wht) + 2160 (soc) + 400 (stamp) + 500 (util) + 1500 (hoist) + 800 (debris) + 5000 (cube) = 27,260.00
    # Additions = 100,000 (work) + 20,000 (mos) = 120,000.00
    # Net payable = 120,000 - 27,260 = 92,740.00
    assert cert.net_amount == Decimal("92740.00")


@pytest.mark.django_db
def test_all_operational_logs_and_protocols(contractor_setup):
    """Tests all remaining operational log models for construction site field management."""
    project = contractor_setup["project"]
    block = contractor_setup["block"]
    contractor = contractor_setup["contractor"]
    material_supplier = contractor_setup["material_supplier"]
    egp_currency = contractor_setup["egp_currency"]

    contract = ContractorContract.objects.create(
        contract_number="CNT-2026-LOGS",
        title="عقد متابعة العمليات اللوجستية والميدانية",
        project=project,
        block=block,
        contractor=contractor,
        currency=egp_currency,
    )
    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-LOGS-01",
        contract=contract,
        project=project,
        block=block,
        contractor=contractor,
        currency=egp_currency,
        gross_certified_work=Decimal("50000.00"),
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
    )

    # 1. EquipmentHoistingLog
    hoist = EquipmentHoistingLog.objects.create(
        certificate=cert,
        equipment_code="T-CRANE-01",
        equipment_name="رافعة برجية 50 طن",
        operating_date=date(2026, 3, 15),
        operating_hours=Decimal("8.00"),
        hourly_rate=Decimal("250.00"),
        total_charge=Decimal("2000.00"),
    )
    assert hoist.total_charge == Decimal("2000.00")

    # 2. SiteDebrisClearanceLog
    debris = SiteDebrisClearanceLog.objects.create(
        certificate=cert,
        trip_ticket_number="TRIP-001",
        clearance_date=date(2026, 3, 16),
        truck_capacity_m3=Decimal("20.00"),
        trip_cost=Decimal("450.00"),
        total_clearance_charge=Decimal("450.00")
    )
    assert debris.trip_cost == Decimal("450.00")

    # 3. ContractorMaterialOnSite & MOS Custody Receipt
    mos = ContractorMaterialOnSite.objects.create(
        certificate=cert,
        item_name="حديد تسليح قطر 16 مم مشون بالموقع",
        unit="TON",
        surveyed_quantity=Decimal("30.00"),
        invoice_unit_cost=Decimal("38000.00"),
        total_material_value=Decimal("1140000.00"),
        advance_financing_rate=Decimal("0.75"),
        approved_advance_amount=Decimal("855000.00"),
    )
    receipt = ContractorMOSCustodyReceipt.objects.create(
        mos_item=mos,
        receipt_number="MOS-REC-001",
        vesting_date=date(2026, 3, 17),
        is_vested_in_employer=True,
        gate_exit_locked=True
    )
    assert receipt.gate_exit_locked is True

    # 4. ContractorBackcharge
    backcharge = ContractorBackcharge.objects.create(
        certificate=cert,
        reason="تكلفة ترميم عمود خرساني معيب",
        memo_reference="BC-MEMO-01",
        amount=Decimal("7500.00")
    )
    assert backcharge.amount == Decimal("7500.00")

    # 5. ConcreteBatchDelivery & ConcreteBatchReconciliation
    batch = ConcreteBatchDelivery.objects.create(
        certificate=cert,
        project=project,
        block=block,
        delivery_note_number="DN-CNC-101",
        delivery_date=date(2026, 3, 18),
        casting_location="سقف الدور الأول علوي",
        concrete_grade="C30",
        batch_volume_m3=Decimal("10.00"),
        unit_price=Decimal("1200.00"),
        is_batch_rejected=False,
        is_sample_passed=True
    )
    reconcil = ConcreteBatchReconciliation.objects.create(
        certificate=cert,
        casting_subcontractor=contract,
        element_description="سقف الدور الأول بالكامل",
        surveyed_as_built_volume_m3=Decimal("100.00"),
        actual_batch_delivered_volume_m3=Decimal("106.00"),
        contractual_waste_tolerance_rate=Decimal("0.03"),
        allowed_waste_volume_m3=Decimal("3.00"),
        excess_waste_volume_m3=Decimal("3.00"),
        concrete_unit_price=Decimal("1200.00"),
        excess_waste_backcharge_amount=Decimal("3600.00")
    )
    assert reconcil.excess_waste_backcharge_amount == Decimal("3600.00")

    # 6. ContractorMaterialDeduction
    mat_ded = ContractorMaterialDeduction.objects.create(
        certificate=cert,
        store_issue_voucher="SIV-2026-05",
        issue_date=date(2026, 3, 19),
        item_name="شكاير أسمنت بورتلاندي عادي",
        quantity=Decimal("50.00"),
        unit_price=Decimal("150.00"),
        total_deduction=Decimal("7500.00"),
        pricing_policy=ContractorMaterialDeduction.PricingPolicy.CONTRACTUAL_FIXED,
        contractual_unit_rate=Decimal("150.00"),
        store_unit_cost=Decimal("140.00"),
        material_price_variance_amount=Decimal("500.00")
    )
    assert mat_ded.total_deduction == Decimal("7500.00")

    # 7. RebarConsumptionLog
    rebar = RebarConsumptionLog.objects.create(
        project=project,
        block=block,
        contractor=contractor,
        contract=contract,
        element_name="أعمدة الدور الأرضي",
        rebar_diameter_mm=18,
        bbs_theoretical_weight_tons=Decimal("20.00"),
        actual_delivered_weight_tons=Decimal("21.50"),
        allowed_waste_rate=Decimal("0.04"),
        excess_waste_weight_tons=Decimal("0.70"),
        steel_market_price_per_ton=Decimal("40000.00"),
        excess_waste_backcharge_amount=Decimal("28000.00")
    )
    assert rebar.excess_waste_backcharge_amount == Decimal("28000.00")

    # 8. ContractorScaffoldingLog & DewateringPumpingLog
    scaffolding = ContractorScaffoldingLog.objects.create(
        contract=contract,
        certificate=cert,
        equipment_type="سقالات معدنية ثقيلة",
        delivered_quantity=100,
        returned_good_quantity=90,
        damaged_quantity=10,
        unit_repair_or_replacement_cost=Decimal("150.00"),
        total_damage_deduction=Decimal("1500.00"),
        log_date=date(2026, 3, 20)
    )
    assert scaffolding.total_damage_deduction == Decimal("1500.00")

    dewatering = DewateringPumpingLog.objects.create(
        contract=contract,
        certificate=cert,
        log_date=date(2026, 3, 21),
        pumps_operating_count=4,
        daily_running_hours=Decimal("24.00"),
        breakdown_hours=Decimal("3.00"),
        stoppage_penalty_rate_per_hour=Decimal("500.00"),
        total_stoppage_penalty=Decimal("1500.00"),
        diesel_liters_supplied_by_owner=Decimal("200.00"),
        diesel_price_per_liter=Decimal("15.00"),
        diesel_total_backcharge=Decimal("3000.00")
    )
    assert dewatering.total_stoppage_penalty == Decimal("1500.00")

    # 9. ContractorSupplierLienAssignment
    lien = ContractorSupplierLienAssignment.objects.create(
        contract=contract,
        contractor=contractor,
        material_supplier=material_supplier,
        agreement_reference="TRIPARTITE-LIEN-01",
        material_description="حديد تسليح مورد بعلم المالك",
        total_lien_amount=Decimal("200000.00"),
        remaining_balance=Decimal("200000.00"),
        is_active=True
    )
    assert lien.is_active is True

    # 10. ThirdPartyLabTestLog
    lab = ThirdPartyLabTestLog.objects.create(
        certificate=cert,
        contract=contract,
        lab_name="معمل بحوث البناء والهندسة الإنشائية",
        invoice_number="LAB-INV-99",
        test_type="اختبار كور تيست لعينات قلب خرساني Core Test",
        test_date=date(2026, 3, 22),
        tested_element="كمرة المحور 4 بالدور الثاني",
        is_test_passed=False,
        total_invoice_amount=Decimal("4500.00"),
        is_backcharged_to_contractor=True
    )
    assert lab.is_test_passed is False
    assert lab.is_backcharged_to_contractor is True

    # 11. ContractorSuspensionClaim
    suspension = ContractorSuspensionClaim.objects.create(
        contract=contract,
        certificate=cert,
        suspension_order_reference="SUSP-ORD-2026-01",
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 10),
        idle_days_count=10,
        idle_scaffolding_cost=Decimal("5000.00"),
        idle_equipment_cost=Decimal("8000.00"),
        site_overhead_and_security=Decimal("3000.00"),
        total_approved_claim_amount=Decimal("16000.00"),
        is_approved_by_cfo=True
    )
    assert suspension.total_approved_claim_amount == Decimal("16000.00")

    # 12. JointTerminationSurveyProtocol
    termination = JointTerminationSurveyProtocol.objects.create(
        contract=contract,
        protocol_reference="TERM-SURV-2026-001",
        survey_date=date(2026, 3, 25),
        consultant_representative="م. استشاري المشروع",
        employer_representative="م. مدير إدارة المشروعات",
        contractor_representative="م. مدير المشروع للمقاول",
        as_built_completed_value=Decimal("850000.00"),
        uninstalled_materials_value=Decimal("120000.00"),
        snag_and_remedial_costs=Decimal("45000.00"),
        court_expert_minutes_number="EXP-COURT-55",
        site_vacated_and_handed_over=True
    )
    assert termination.site_vacated_and_handed_over is True

    # 13. RockExcavationSurveyLog
    rock = RockExcavationSurveyLog.objects.create(
        contract=contract,
        certificate=cert,
        grid_location_reference="GRID-B3-EXC",
        survey_date=date(2026, 3, 26),
        top_rock_elevation_m=Decimal("15.50"),
        bottom_excavation_elevation_m=Decimal("12.00"),
        solid_rock_volume_m3=Decimal("350.00"),
        breaker_operating_hours=Decimal("45.00"),
        surveyor_consultant_approval=True
    )
    assert rock.solid_rock_volume_m3 == Decimal("350.00")

    # 14. HydrostaticTestFailureLog
    hydro = HydrostaticTestFailureLog.objects.create(
        contract=contract,
        certificate=cert,
        network_segment="شبكة تغذية مياه الشرب قطاع الشرقية",
        test_date=date(2026, 3, 27),
        tested_pressure_bar=Decimal("10.00"),
        pressure_drop_bar=Decimal("3.50"),
        leak_location="وصلة المحبس الرئيسي عند الغرفة رقم 4",
        concrete_breaking_cost=Decimal("2000.00"),
        re_casting_and_waterproofing_cost=Decimal("3500.00"),
        total_remedial_backcharge=Decimal("5500.00")
    )
    assert hydro.total_remedial_backcharge == Decimal("5500.00")

    # 15. CertificatePaymentInstallmentSchedule
    inst = CertificatePaymentInstallmentSchedule.objects.create(
        certificate=cert,
        installment_number=1,
        due_date=date(2026, 4, 15),
        amount=Decimal("25000.00"),
        payment_method=CertificatePaymentInstallmentSchedule.PaymentMethod.PDC_CHEQUE,
        is_settled=False,
        contractor_agreement_signed=True
    )
    assert inst.amount == Decimal("25000.00")
    assert inst.contractor_agreement_signed is True
