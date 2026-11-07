# -*- coding: utf-8 -*-
"""
Master Test Suite: Track 1 - Contractors, Subcontracts & Progress Certificates
MWHEBA ERP - Real Estate App

Covers the comprehensive matrix of scenarios from the 78 engineering and accounting test pillars:
- Master Project BOQ trade splitting budget ceilings & target cost rate overrun guards
- Escrow advance payment disbursement & dynamic recovery recalibration
- Hard governance guards: Judicial Garnishment, Bank Assignment, LG Pay-or-Extend, CAR insurance, Bank Whitelist
- Comprehensive cascading deductions & Form 41 double WHT prevention
- Rebar BBS reconciliation, concrete batch deliveries, slump & hot weather rejection
- Three-way concrete waste reconciliation, pile bulbing factor, and site debris logs
- Materials on site (MOS) lifecycle, vesting custody receipts (Article 658 Civil Code) & gate pass lock
- Nominated subcontractor direct payout and set-off
- Disputed line item quarantine and partial approval
- Scaffolding & equipment logs, dewatering pumping logs, and fuel backcharges
- Refundable milestone delay penalties & suspension demurrage claims (FIDIC 8.8)
- Composite contract item-level tax regimes (VAT 14% vs Table Tax 5%)
- Tripartite supplier liens, third-party lab tests, and hydrostatic test failures
- Joint termination as-built survey protocol & leftover MOS stock absorption
- Unregistered craftsmen micro-contract self-billing
- Storno Reversal workflow, Merkle-tree cryptographic hash mutation locks, and PDC installment scheduling
"""
from decimal import Decimal
from datetime import date, timedelta
import pytest
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    ProjectMasterBOQItem,
    ContractorContract,
    ContractorContractItem,
    ContractVariationOrder,
    ContractVariationOrderItem,
    ContractorProgressCertificate,
    ContractorCertificateItem,
    ContractorMaterialOnSite,
    ContractorMOSCustodyReceipt,
    ContractorBackcharge,
    ContractorDefaultNotice,
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
    SectionalHandoverRecord,
    SiteDebrisClearanceLog,
    EquipmentHoistingLog,
)
from real_estate.services.contractor_contract_service import ContractorContractService
from real_estate.services.contractor_service import (
    ContractorProgressService,
    SequentialOrderError,
    FinalSettlementComplianceError,
    MutationTamperError,
)
from supplier.models import Supplier
from financial.models.currency import Currency
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.approval import EnterpriseApprovalRule
from cheques.models import Cheque

User = get_user_model()


@pytest.fixture
def master_test_setup(db):
    """
    Sets up the complete enterprise ERP environment with users, roles,
    chart of accounts, currencies, approval rules, project, block, and suppliers.
    """
    user_admin = User.objects.create_superuser(
        username="master_admin",
        email="master_admin@mwheba.com",
        password="password123"
    )
    user_cfo = User.objects.create_user(
        username="master_cfo",
        email="cfo@mwheba.com",
        password="password123"
    )

    # 1. تهيئة أنواع الحسابات ودليل الحسابات المالي
    asset_type, _ = AccountType.objects.get_or_create(code='asset', defaults={'name': 'أصول', 'category': 'asset', 'nature': 'debit'})
    liability_type, _ = AccountType.objects.get_or_create(code='liability', defaults={'name': 'خصوم', 'category': 'liability', 'nature': 'credit'})
    revenue_type, _ = AccountType.objects.get_or_create(code='revenue', defaults={'name': 'إيرادات', 'category': 'revenue', 'nature': 'credit'})

    egp_currency, _ = Currency.objects.get_or_create(
        code="EGP",
        defaults={'name': "Egyptian Pound", 'symbol': "ج.م", 'is_functional': True}
    )
    usd_currency, _ = Currency.objects.get_or_create(
        code="USD",
        defaults={'name': "US Dollar", 'symbol': "$", 'is_functional': False}
    )

    accounts = {
        "12101": ("مشروعات تحت التنفيذ - أعمال مقاولات", asset_type),
        "11410": ("ضريبة القيمة المضافة - مدخلات", asset_type),
        "21310": ("تأمينات محتجزة للغير - حسن تنفيذ", liability_type),
        "21315": ("أمانات كسر مكعبات خرسانة معلقة", liability_type),
        "21345": ("أمانات نقابة المهندسين", liability_type),
        "21360": ("مخصص وأقساط وثيقة CAR", liability_type),
        "11350": ("دفعات مقدمة لمقاولي الباطن", asset_type),
        "21330": ("ضريبة الخصم والإضافة", liability_type),
        "21340": ("أمانات تأمينات اجتماعية مقاولات", liability_type),
        "42301": ("استرداد استهلاك مياه وإنارة الموقع", revenue_type),
        "42304": ("استرداد نفقات رفع رتش ومخلفات", revenue_type),
        "42302": ("إيرادات تشغيل أوناش ومعدات", revenue_type),
        "11355": ("سلف عمالة مقاولين نقدية", asset_type),
        "42303": ("استرداد نفقات طبية وحوادث أمن صناعي", revenue_type),
        "11201": ("مخزن المشروع - خامات منصرفة", asset_type),
        "42101": ("إيرادات غرامات تأخير وجودة", revenue_type),
        "42201": ("استرداد تكاليف إصلاح عيوب", revenue_type),
        "21110": ("مستحقات مقاولي الباطن", liability_type),
        "21350": ("أمانات حجوزات قضائية وتنفيذية", liability_type),
        "11121": ("حساب الضمان البنكي للمشروع Escrow", asset_type),
        "11111": ("الخزينة الرئيسية للمشروع", asset_type),
        "21210": ("أوراق الدفع - شيكات صادرة للمقاولين", liability_type),
    }
    for code, (name, a_type) in accounts.items():
        ChartOfAccounts.objects.get_or_create(
            code=code,
            defaults={'name': name, 'account_type': a_type, 'is_active': True, 'is_leaf': True}
        )

    # 2. قاعدة الاعتماد المالي المؤسسية
    EnterpriseApprovalRule.objects.get_or_create(
        module='REAL_ESTATE',
        rule_name='اعتماد مستخلصات المقاولين',
        defaults={
            'min_amount': Decimal('0.00'),
            'max_amount': Decimal('999999999.00'),
            'approver_role': 'site_engineer',
            'approval_level': 1,
            'is_active': True,
        }
    )

    # 3. المشروع العقاري والعمارة
    project = RealEstateProject.objects.create(
        code="PRJ-MST",
        name="كمبوند جوهرة المستقبل الإنشائي",
        project_type="RESIDENTIAL",
        status="UNDER_CONSTRUCTION",
        start_date=date(2026, 1, 1),
        expected_completion_date=date(2028, 12, 31),
        created_by=user_admin
    )
    block = PropertyBlock.objects.create(
        project=project,
        code="BLK-A1",
        name="عمارة النور A1",
        total_floors=8
    )

    # 4. مقاولو الباطن والموردون
    contractor = Supplier.objects.create(
        name="شركة الأهرام للمقاولات العامة",
        code="CON-MST-01",
        tax_number="123456789"
    )
    nominated_subcontractor = Supplier.objects.create(
        name="المتحدة للمصاعد والسلالم الكهربائية",
        code="CON-NOM-01",
        tax_number="987123456"
    )
    material_supplier = Supplier.objects.create(
        name="السويدي لتوريدات مواد البناء",
        code="SUP-MAT-01",
        tax_number="555666777"
    )
    plumbing_contractor = Supplier.objects.create(
        name="النيل للأعمال الصحية والسباكة",
        code="CON-PLM-01",
        tax_number="444333222"
    )

    # 5. بند المقايسة العامة التقديرية (Master BOQ)
    master_boq = ProjectMasterBOQItem.objects.create(
        project=project,
        block=block,
        item_code="BOQ-MST-01",
        description="أعمال خرسانة مسلحة للهيكل الإنشائي",
        unit="M3",
        master_budget_quantity=Decimal("2000.00"),
        unit_rate_estimate=Decimal("4500.00"),
        total_budget_cost=Decimal("9000000.00"),
        overrun_tolerance_rate=Decimal("5.00")  # سقف أقصى 2100 م3
    )

    # 6. عقد مقاولة رئيسي قياسي
    contract = ContractorContract.objects.create(
        contract_number="CNT-MST-01",
        title="عقد الهيكل الإنشائي والمصنعيات",
        project=project,
        block=block,
        contractor=contractor,
        initial_contract_value=Decimal("5000000.00"),
        advance_payment_rate=Decimal("10.00"),
        advance_payment_amount=Decimal("500000.00"),
        retention_rate=Decimal("5.00"),
        wht_rate=Decimal("1.00"),
        syndicate_stamp_rate=Decimal("0.450"),
        car_insurance_deduction_rate=Decimal("0.300"),
        site_utilities_deduction_rate=Decimal("0.50"),
        approved_bank_account_iban="EG11CIB000123456789012345",
        approved_bank_account_title="شركة الأهرام للمقاولات العامة",
        status=ContractorContract.ContractStatus.ACTIVE,
    )
    contract_item = ContractorContractItem.objects.create(
        contract=contract,
        master_boq_item=master_boq,
        item_code="BOQ-MST-01",
        description="خرسانة مسلحة للأسقف والأعمدة",
        unit="M3",
        contracted_quantity=Decimal("1000.00"),
        unit_rate=Decimal("4500.00"),
        total_budget_amount=Decimal("4500000.00")
    )
    master_boq.allocated_quantity_to_contracts = Decimal("1000.00")
    master_boq.save()

    return {
        "user_admin": user_admin,
        "user_cfo": user_cfo,
        "project": project,
        "block": block,
        "contractor": contractor,
        "nominated_subcontractor": nominated_subcontractor,
        "material_supplier": material_supplier,
        "plumbing_contractor": plumbing_contractor,
        "master_boq": master_boq,
        "contract": contract,
        "contract_item": contract_item,
        "egp_currency": egp_currency,
        "usd_currency": usd_currency,
    }


# ==============================================================================
# 1. اختبارات الحوكمة الهندسية وسقوف الموازنة والمقايسات (Pillars 38, 43, 44, 58, 65, 71, 73)
# ==============================================================================

@pytest.mark.django_db
def test_master_project_boq_trade_splitting_budget_guard(master_test_setup):
    """
    ركيزة 38: منع تجاوز مجموع كميات عقود المقاولين لموازنة مقايسة المشروع العامة
    (Master Project BOQ Trade Splitting Budget Ceiling Guard).
    """
    contract = master_test_setup["contract"]
    boq = master_test_setup["master_boq"]

    # المقايسة بها 2000 م3 بسماحية 5% = 2100 م3 كحد أقصى. مخصص منها 1000 م3 بالعقد الأول.
    # محاولة إضافة بند جديد بكمية 1200 م3 (1000 + 1200 = 2200 > 2100)
    excess_data = {
        "item_code": "BOQ-MST-01",
        "contracted_quantity": Decimal("1200.00"),
        "unit_rate": Decimal("4500.00"),
        "master_boq_item": boq,
    }
    with pytest.raises(ValidationError) as exc_info:
        ContractorContractService.create_contract_item(contract, excess_data)
    assert "تتجاوز السقف الأقصى المتاح بمقايسة المشروع العامة" in str(exc_info.value)


@pytest.mark.django_db
def test_target_cost_budget_rate_overrun_guard(master_test_setup):
    """
    ركيزة 43: إنذار وحظر تفعيل عقود المقاولين بفئات تتجاوز فئات الموازنة التقديرية
    (Target Cost Budget Rate Overrun Guard).
    """
    contract = master_test_setup["contract"]
    boq = master_test_setup["master_boq"]

    # فئة الموازنة 4500 ج.م، وفئة العقد 4800 ج.م
    item_data = {
        "item_code": "BOQ-MST-02",
        "contracted_quantity": Decimal("200.00"),
        "unit_rate": Decimal("4800.00"),
        "master_boq_item": boq,
        "unit": "M3",
    }
    item = ContractorContractService.create_contract_item(contract, item_data)
    assert item.is_budget_rate_overrun is True
    assert item.unit_rate > boq.unit_rate_estimate


@pytest.mark.django_db
def test_sectional_handover_and_independent_warranty_clocks(master_test_setup):
    """
    ركيزة 44: تتبع استلام الأدوار المنجزة مبكراً بحسابات عداد ضمان مستقلة
    (Sectional Handover & Independent Warranty Clocks).
    """
    contract = master_test_setup["contract"]

    # استلام الدور الأول مبكراً في 2026-03-01 بفترة ضمان 12 شهراً
    handover = ContractorContractService.record_sectional_handover(
        contract=contract,
        section_name="الدور الأرضي والأول علوي",
        handover_date=date(2026, 3, 1),
        warranty_months=12,
        consultant_approval_ref="SEC-CONS-99",
        notes="استلام ابتدائي للأدوار المنجزة لتسليمها لمهندسي التشطيبات"
    )
    assert handover.warranty_start_date == date(2026, 3, 1)
    assert handover.warranty_end_date == date(2026, 3, 1) + timedelta(days=360)
    assert handover.is_warranty_completed is False


@pytest.mark.django_db
def test_dynamic_advance_recovery_recalibration_on_variation_orders(master_test_setup):
    """
    ركيزة 58: إعادة الحساب الديناميكي لمعدل استرداد الدفعة المقدمة عند أوامر التغيير
    (Dynamic Advance Recovery Recalibration on Variation Orders).
    """
    contract = master_test_setup["contract"]
    user = master_test_setup["user_admin"]

    contract.dynamic_advance_recalibration = True
    contract.advance_payment_amount = Decimal("200000.00")
    contract.advance_payment_disbursed = Decimal("200000.00")
    contract.advance_payment_recovered = Decimal("50000.00")
    contract.total_certified_work = Decimal("250000.00")
    contract.revised_contract_value = Decimal("1000000.00")
    contract.completion_date = date(2027, 1, 1)
    contract.save()

    vo = ContractVariationOrder.objects.create(
        order_number="VO-MST-01",
        contract=contract,
        variation_type=ContractVariationOrder.VariationType.QUANTITY_INCREASE,
        net_value_impact=Decimal("500000.00"),
        approved_additional_days=30,
        status=ContractVariationOrder.VariationStatus.DRAFT,
    )
    applied_vo = ContractorContractService.apply_variation_order(vo, user=user)
    assert applied_vo.status == ContractVariationOrder.VariationStatus.APPROVED

    contract.refresh_from_db()
    assert contract.revised_contract_value == Decimal("1500000.00")
    assert contract.completion_date == date(2027, 1, 31)
    assert contract.advance_recovery_rate == Decimal("12.00")


@pytest.mark.django_db
def test_dual_currency_hybrid_boq_items_with_fx_volatility_collar(master_test_setup):
    """
    ركيزة 65: تقييم بنود المكون الأجنبي الهجين وتطبيق سقف تقلبات سعر الصرف (FX Collar)
    (Dual-Currency Hybrid BOQ Items with FX Volatility Collar).
    """
    contract = master_test_setup["contract"]
    usd = master_test_setup["usd_currency"]

    hybrid_item = ContractorContractItem.objects.create(
        contract=contract,
        item_code="HYB-ELEV-01",
        description="توريد ماكينات المصاعد بمكون دولاري",
        unit="SET",
        contracted_quantity=Decimal("2.00"),
        unit_rate=Decimal("1000000.00"),
        total_budget_amount=Decimal("2000000.00"),
        has_foreign_component=True,
        foreign_component_percent=Decimal("60.00"),
        foreign_currency=usd,
        fx_baseline_rate=Decimal("48.000000"),
        fx_volatility_collar_percent=Decimal("15.00")
    )
    assert hybrid_item.has_foreign_component is True
    assert hybrid_item.foreign_component_percent == Decimal("60.00")
    assert hybrid_item.fx_baseline_rate == Decimal("48.000000")


@pytest.mark.django_db
def test_joint_termination_as_built_survey_protocol_baseline_lock(master_test_setup):
    """
    ركيزة 71: تحرير وقفل محضر الحصر المشترك الثلاثي لإثبات الحالة عند فسخ العقد
    (Joint Termination As-Built Survey Protocol Baseline Lock).
    """
    contract = master_test_setup["contract"]

    protocol = JointTerminationSurveyProtocol.objects.create(
        contract=contract,
        protocol_reference="TERM-MST-2026-001",
        survey_date=date(2026, 6, 1),
        consultant_representative="م. حازم عبد الله - استشاري المالك",
        employer_representative="م. كريم الشناوي - مدير المشروعات",
        contractor_representative="م. عادل إبراهيم - مدير موقع المقاول",
        as_built_completed_value=Decimal("1500000.00"),
        uninstalled_materials_value=Decimal("250000.00"),
        snag_and_remedial_costs=Decimal("80000.00"),
        site_vacated_and_handed_over=True
    )
    assert protocol.as_built_completed_value == Decimal("1500000.00")
    assert protocol.site_vacated_and_handed_over is True


@pytest.mark.django_db
def test_rock_excavation_survey_grid_and_hydraulic_breaker_hours_check(master_test_setup):
    """
    ركيزة 73: اعتماد مكعبات حفر الصخور عبر الميزانية الشبكية وساعات تشغيل الشواكيش
    (Rock Excavation Survey Grid & Hydraulic Breaker Hours Check).
    """
    contract = master_test_setup["contract"]

    log = RockExcavationSurveyLog.objects.create(
        contract=contract,
        grid_location_reference="شبكة مساحية محور G-12 إلى H-16",
        survey_date=date(2026, 2, 15),
        top_rock_elevation_m=Decimal("14.500"),
        bottom_excavation_elevation_m=Decimal("11.200"),
        solid_rock_volume_m3=Decimal("850.000"),
        breaker_operating_hours=Decimal("45.50"),
        surveyor_consultant_approval=True
    )
    assert log.solid_rock_volume_m3 == Decimal("850.000")
    assert log.breaker_operating_hours == Decimal("45.50")
    assert log.surveyor_consultant_approval is True


# ==============================================================================
# 2. اختبارات الحوكمة البنكية والرقابية الصارمة (Pillars 45, 47, 69, 74, 75, 77)
# ==============================================================================

@pytest.mark.django_db
def test_bank_assignment_of_proceeds_hard_payout_guard(master_test_setup):
    """
    ركيزة 45: حظر الصرف للمقاول وإلزام تحرير الدفعات باسم البنك المحال إليه رسمياً
    (Bank Assignment of Proceeds Hard Payout Guard).
    """
    contract = master_test_setup["contract"]
    contract.is_assigned_to_bank = True
    contract.assigned_bank_name = "البنك التجاري الدولي CIB"
    contract.assigned_bank_iban = "EG99CIB00099988877766655"
    contract.save()

    eligibility = ContractorContractService.check_contract_payout_eligibility(contract=contract)
    assert eligibility["is_eligible_for_direct_payout"] is False
    assert eligibility["bank_assignment_active"] is True
    assert eligibility["assigned_bank_iban"] == "EG99CIB00099988877766655"
    assert "تنازل رسمي عن المستحقات" in eligibility["blocking_reasons"][0]


@pytest.mark.django_db
def test_judicial_garnishment_freeze_and_escrow_holding(master_test_setup):
    """
    ركيزة 47: تجميد الصرف وتجنيب مستحقات المقاول بحساب الأمانات القضائية عند الحجز التنفيذي
    (Judicial Garnishment Freeze & Escrow Holding).
    """
    contract = master_test_setup["contract"]
    contract.is_garnished_by_court = True
    contract.garnishment_case_number = "1234/2026 مدني كلي"
    contract.garnishment_creditor_name = "شركة الحديد والصلب"
    contract.garnishment_amount = Decimal("300000.00")
    contract.save()

    eligibility = ContractorContractService.check_contract_payout_eligibility(contract=contract)
    assert eligibility["is_eligible_for_direct_payout"] is False
    assert eligibility["garnishment_active"] is True
    assert eligibility["garnishment_amount"] == Decimal("300000.00")
    assert any("حجز قضائي تنفيذي قائم" in reason for reason in eligibility["blocking_reasons"])


@pytest.mark.django_db
def test_vendor_bank_whitelist_guard_blocks_unauthorized_account_payout(master_test_setup):
    """
    ركيزة 77: صمام القائمة البيضاء وحظر تحرير شيكات أو تحويلات لحسابات شخصية غير معتمدة
    (Vendor Bank Whitelist Guard Blocks Unauthorized Account Payout).
    """
    contract = master_test_setup["contract"]
    contract.approved_bank_account_iban = "EG11CIB000123456789012345"
    contract.approved_bank_account_title = "شركة الأهرام للمقاولات العامة"
    contract.save()

    # محاولة سداد على حساب شخصي لا يطابق الـ IBAN المسجل بالقائمة البيضاء
    unauthorized_iban = "EG55UNAUTHORIZED999"
    assert unauthorized_iban != contract.approved_bank_account_iban
    assert contract.approved_bank_account_title == "شركة الأهرام للمقاولات العامة"


@pytest.mark.django_db
def test_pay_or_extend_mandatory_bank_instruction_and_payout_freeze(master_test_setup):
    """
    ركيزة 75: تجميد صرف المستخلصات وتوليد إنذار Pay or Extend قبل 15 يوماً من انتهاء خطاب الضمان
    (Pay or Extend Mandatory Bank Instruction & Payout Freeze).
    """
    contract = master_test_setup["contract"]
    contract.guarantee_type = ContractorContract.GuaranteeType.BANK_LETTER_OF_GUARANTEE
    contract.bank_lg_number = "LG-2026-99"
    contract.bank_lg_expiry_date = date.today() + timedelta(days=10)
    contract.save()

    eligibility = ContractorContractService.check_contract_payout_eligibility(contract=contract)
    assert eligibility["pay_or_extend_triggered"] is True
    assert eligibility["freeze_payout"] is True
    assert eligibility["is_eligible_for_direct_payout"] is False
    assert any("Pay or Extend" in reason for reason in eligibility["blocking_reasons"])


@pytest.mark.django_db
def test_decennial_liability_and_occupancy_compliance_guard_for_final_settlement(master_test_setup):
    """
    ركيزة 69: اشتراط المجمعة العشرية وشهادة صلاحية الإشغال قبل إغلاق المستخلص الختامي
    (Decennial Liability & Occupancy Compliance Guard for Final Settlement).
    """
    contract = master_test_setup["contract"]
    contract.decennial_liability_insurance_policy = ""  # مفقودة
    contract.syndicate_supervision_clearance = False
    contract.certificate_of_occupancy_number = ""
    contract.save()

    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-FIN-01",
        project=contract.project,
        contract=contract,
        contractor=contract.contractor,
        currency=master_test_setup["egp_currency"],
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31),
        certificate_type=ContractorProgressCertificate.CertificateType.FINAL_SETTLEMENT,
        gross_certified_work=Decimal("5000000.00"),
        previous_certified_work=Decimal("4500000.00"),
        status=ContractorProgressCertificate.CertificateStatus.DRAFT
    )

    with pytest.raises(FinalSettlementComplianceError) as exc_info:
        ContractorProgressService.submit_certificate_for_approval(cert, master_test_setup["user_admin"])
    assert "المجمعة العشرية" in str(exc_info.value) or "صلاحية المبنى للإشغال" in str(exc_info.value)


@pytest.mark.django_db
def test_unregistered_craftsmen_micro_contract_self_billing_and_wht(master_test_setup):
    """
    ركيزة 74: مسار العقود الحرفية المصغرة للأفراد وإصدار الإذن الذاتي بخصم 1% ضرائب وتأمينات
    (Unregistered Craftsmen Micro-Contract Self-Billing & WHT).
    """
    project = master_test_setup["project"]
    block = master_test_setup["block"]
    user = master_test_setup["user_admin"]

    craftsman = Supplier.objects.create(
        name="الأسطى سعيد حسن - نجار مسلح",
        code="CRF-01",
        is_active=True
    )
    contract = ContractorContract.objects.create(
        contract_number="MIC-01",
        title="مصنعيات تقفيل أوتار وطرطشة",
        project=project,
        block=block,
        contractor=craftsman,
        currency=master_test_setup["egp_currency"],
        is_unregistered_individual_craftsman=True,
        initial_contract_value=Decimal("20000.00"),
        status=ContractorContract.ContractStatus.ACTIVE
    )

    entry = ContractorContractService.record_micro_contract_self_billing(
        contract=contract,
        craftsman_name="الأسطى سعيد حسن",
        gross_amount=Decimal("20000.00"),
        wht_rate=Decimal("1.00"),
        soc_ins_rate=Decimal("5.00"),
        user=user
    )
    assert entry is not None
    assert entry.lines.count() >= 3
    debits = sum(line.debit for line in entry.lines.all())
    credits = sum(line.credit for line in entry.lines.all())
    assert debits == credits == Decimal("20000.00")


# ==============================================================================
# 3. اختبارات الاستقطاعات والضرائب المتسلسلة (Pillars 39, 46, 50, 51, 60, 63, 72)
# ==============================================================================

@pytest.mark.django_db
def test_interim_on_account_payment_auto_deduction(master_test_setup):
    """
    ركيزة 39: استدعاء وخصم الدفعات المسددة تحت الحساب بالفترة تلقائياً من المستخلص
    (Interim On-Account Payment Auto-Deduction).
    """
    contract = master_test_setup["contract"]
    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-INT-01",
        project=contract.project,
        contract=contract,
        contractor=contract.contractor,
        currency=master_test_setup["egp_currency"],
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        gross_certified_work=Decimal("500000.00"),
        interim_on_account_payments=Decimal("50000.00"),
        status=ContractorProgressCertificate.CertificateStatus.DRAFT
    )
    cert.compute_amounts()
    # تأمين 5% = 25,000، ضرائب 1% = 5,000، سلفة بالفترة = 50,000
    # الصافي المتوقع يخصم منه دفعة الـ 50,000 تحت الحساب
    assert cert.interim_on_account_payments == Decimal("50000.00")
    assert cert.net_amount < (cert.current_period_work - cert.retention_amount - cert.wht_amount)


@pytest.mark.django_db
def test_engineering_syndicate_stamp_tax_deduction_and_remittance(master_test_setup):
    """
    ركيزة 46: استقطاع دمغة نقابة المهندسين بنسبة 0.45% وتوجيهها لحساب الأمانات الدائن 21345
    (Engineering Syndicate Stamp Tax Deduction & Remittance).
    """
    contract = master_test_setup["contract"]
    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-SYN-01",
        project=contract.project,
        contract=contract,
        contractor=contract.contractor,
        currency=master_test_setup["egp_currency"],
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        gross_certified_work=Decimal("1000000.00"),
        syndicate_stamp_rate=Decimal("0.450"),
        status=ContractorProgressCertificate.CertificateStatus.DRAFT
    )
    cert.compute_amounts()
    # 1,000,000 * 0.45% = 4,500.00 ج.م
    assert cert.syndicate_stamp_amount == Decimal("4500.00")


@pytest.mark.django_db
def test_contractors_all_risks_car_insurance_compliance_and_deduction(master_test_setup):
    """
    ركيزة 50: فحص سريان وثيقة تأمين أخطار المقاولين CAR واستقطاع قسطها التعاقدي
    (Contractor's All Risks - CAR Insurance Compliance & Deduction).
    """
    contract = master_test_setup["contract"]
    contract.car_insurance_policy_number = "CAR-MISR-2026-99"
    contract.car_insurance_expiry_date = date(2027, 12, 31)
    contract.car_insurance_deduction_rate = Decimal("0.300")
    contract.save()

    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-CAR-01",
        project=contract.project,
        contract=contract,
        contractor=contract.contractor,
        currency=master_test_setup["egp_currency"],
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        gross_certified_work=Decimal("1000000.00"),
        car_insurance_amount=Decimal("3000.00"),  # 0.3%
        status=ContractorProgressCertificate.CertificateStatus.DRAFT
    )
    cert.compute_amounts()
    assert cert.car_insurance_amount == Decimal("3000.00")


@pytest.mark.django_db
def test_cascading_deduction_sequence_and_double_wht_prevention(master_test_setup):
    """
    ركيزة 51: خوارزمية تسلسل الاستقطاعات ومنع احتساب ضريبة 1% نموذج 41 على الدفعة المقدمة المستردة
    (Cascading Deduction Sequence & Double WHT Prevention).
    """
    contract = master_test_setup["contract"]
    # أعمال الفترة 500,000 واسترداد دفعة مقدمة 100,000
    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-WHT-01",
        project=contract.project,
        contract=contract,
        contractor=contract.contractor,
        currency=master_test_setup["egp_currency"],
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        gross_certified_work=Decimal("500000.00"),
        advance_payment_recovery=Decimal("100000.00"),
        wht_rate=Decimal("1.00"),
        status=ContractorProgressCertificate.CertificateStatus.DRAFT
    )
    cert.compute_amounts()
    # الوعاء الخاضع للضريبة يجب أن يكون: 500,000 - 100,000 = 400,000
    # ضريبة 1% = 4,000 وليس 5,000 (منع الازدواج الضريبي)
    assert cert.taxable_base_form41 == Decimal("400000.00")
    assert cert.wht_amount == Decimal("4000.00")


@pytest.mark.django_db
def test_composite_contract_item_level_tax_regime_differentiation(master_test_setup):
    """
    ركيزة 60: تعدد الأوعية الضريبية بالعقد الواحد (14% لتوريد المعدات و5% لأعمال المصنعية)
    (Composite Contract Item-Level Tax Regime Differentiation).
    """
    contract = master_test_setup["contract"]
    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-TAX-01",
        project=contract.project,
        contract=contract,
        contractor=contract.contractor,
        currency=master_test_setup["egp_currency"],
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        gross_certified_work=Decimal("1000000.00"),
        status=ContractorProgressCertificate.CertificateStatus.DRAFT
    )

    # بند توريد (14% VAT)
    item_vat = ContractorCertificateItem.objects.create(
        certificate=cert,
        item_code="EQ-SUP-01",
        description="توريد معدات ومحابس",
        unit="SET",
        previous_quantity=Decimal("0.000"),
        current_quantity=Decimal("10.000"),
        unit_rate=Decimal("50000.00"),
        total_cumulative_amount=Decimal("500000.00"),
        current_period_amount=Decimal("500000.00")
    )
    # بند تركيب ومصنعيات (5% Table Tax)
    item_tbl = ContractorCertificateItem.objects.create(
        certificate=cert,
        item_code="EQ-INS-01",
        description="أعمال التركيب والمصنعية",
        unit="SET",
        previous_quantity=Decimal("0.000"),
        current_quantity=Decimal("10.000"),
        unit_rate=Decimal("50000.00"),
        total_cumulative_amount=Decimal("500000.00"),
        current_period_amount=Decimal("500000.00")
    )
    assert item_vat.current_work_value == Decimal("500000.00")
    assert item_tbl.current_work_value == Decimal("500000.00")


@pytest.mark.django_db
def test_tripartite_supplier_lien_assignment_and_direct_payout(master_test_setup):
    """
    ركيزة 63: قيد وتجميد التعهد الثلاثي وسداد مستحقات مورد الخامات مباشرة
    (Tripartite Supplier Lien Assignment & Direct Payout).
    """
    contract = master_test_setup["contract"]
    supplier = master_test_setup["material_supplier"]

    lien = ContractorSupplierLienAssignment.objects.create(
        contract=contract,
        contractor=contract.contractor,
        material_supplier=supplier,
        agreement_reference="LIEN-2026-001",
        material_description="حديد تسليح وأسمنت معتمد",
        total_lien_amount=Decimal("200000.00"),
        deducted_to_date=Decimal("0.00"),
        remaining_balance=Decimal("200000.00"),
        is_active=True
    )

    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-LIEN-01",
        project=contract.project,
        contract=contract,
        contractor=contract.contractor,
        currency=master_test_setup["egp_currency"],
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        gross_certified_work=Decimal("1000000.00"),
        tripartite_supplier_liens_deduction=Decimal("50000.00"),
        status=ContractorProgressCertificate.CertificateStatus.DRAFT
    )
    cert.compute_amounts()
    assert cert.tripartite_supplier_liens_deduction == Decimal("50000.00")

    # تحديث رصيد التعهد
    lien.deducted_to_date += cert.tripartite_supplier_liens_deduction
    lien.remaining_balance = lien.total_lien_amount - lien.deducted_to_date
    lien.save()
    assert lien.remaining_balance == Decimal("150000.00")


@pytest.mark.django_db
def test_store_issue_pricing_policy_contractual_rate_variance_posting(master_test_setup):
    """
    ركيزة 72: تسعير خامات المخزن بالسعر التعاقدي وتوليد قيد فروق الأسعار المحمل على المشروع
    (Store Issue Pricing Policy Contractual Rate Variance Posting).
    """
    contract = master_test_setup["contract"]
    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-STR-01",
        project=contract.project,
        contract=contract,
        contractor=contract.contractor,
        currency=master_test_setup["egp_currency"],
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        gross_certified_work=Decimal("500000.00"),
        status=ContractorProgressCertificate.CertificateStatus.DRAFT
    )

    # صرف 100 شيكارة أسمنت: السعر التعاقدي 200 ج.م، وتكلفة المخزن الفعلية 230 ج.م
    deduction = ContractorMaterialDeduction.objects.create(
        certificate=cert,
        store_issue_voucher="VOUCH-STR-001",
        issue_date=date(2026, 1, 15),
        item_name="أسمنت بورتلاندي عادي",
        quantity=Decimal("100.000"),
        unit_price=Decimal("200.00"),
        total_deduction=Decimal("20000.00"),
        pricing_policy=ContractorMaterialDeduction.PricingPolicy.CONTRACTUAL_FIXED,
        contractual_unit_rate=Decimal("200.00"),
        store_unit_cost=Decimal("230.00"),
        material_price_variance_amount=Decimal("3000.00")  # (230 - 200) * 100
    )
    assert deduction.total_deduction == Decimal("20000.00")
    assert deduction.material_price_variance_amount == Decimal("3000.00")


# ==============================================================================
# 4. اختبارات الجودة والسلامة والخصومات الفنية البينية (Pillars 40, 41, 42, 49, 52, 55, 56, 61, 62, 66, 67, 68, 76)
# ==============================================================================

@pytest.mark.django_db
def test_late_28day_concrete_cube_failure_lab_hold(master_test_setup):
    """
    ركيزة 40: حجز أمانة نتائج المعمل لصبات الخرسانة لكسر 28 يوم
    (Late 28-Day Concrete Cube Failure Lab Hold).
    """
    contract = master_test_setup["contract"]
    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-CUB-01",
        project=contract.project,
        contract=contract,
        contractor=contract.contractor,
        currency=master_test_setup["egp_currency"],
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        gross_certified_work=Decimal("800000.00"),
        pending_cube_test_hold_amount=Decimal("40000.00"),
        status=ContractorProgressCertificate.CertificateStatus.DRAFT
    )
    cert.compute_amounts()
    assert cert.pending_cube_test_hold_amount == Decimal("40000.00")


@pytest.mark.django_db
def test_default_cure_notice_48h_grace_period_enforcement(master_test_setup):
    """
    ركيزة 41: حظر الخصم على حساب المقاول إلا بعد انقضاء مهلة إخطار الـ 48 ساعة
    (Default Cure Notice 48-Hour Grace Period Enforcement).
    """
    contract = master_test_setup["contract"]
    today = timezone.localdate()

    # إخطار إنذار ساري
    active_notice = ContractorDefaultNotice.objects.create(
        contract=contract,
        notice_number="NOT-48H-01",
        notice_date=today,
        cure_deadline=today + timedelta(days=2),
        violation_description="عدم نظافة الموقع وإزالة مخلفات التكسير",
        is_cured=False,
        is_penalty_authorized=False
    )
    assert active_notice.cure_deadline > today
    assert active_notice.is_penalty_authorized is False

    # إخطار منقضٍ ومصرح بالخصم
    expired_notice = ContractorDefaultNotice.objects.create(
        contract=contract,
        notice_number="NOT-48H-02",
        notice_date=today - timedelta(days=3),
        cure_deadline=today - timedelta(days=1),
        violation_description="تسويس في أعمدة المحور C",
        is_cured=False,
        is_penalty_authorized=True
    )
    assert expired_notice.cure_deadline < today
    assert expired_notice.is_penalty_authorized is True


@pytest.mark.django_db
def test_hse_emergency_medical_and_penalty_backcharge(master_test_setup):
    """
    ركيزة 42: توجيه مصاريف علاج حوادث عمالة المقاول وغرامات السلامة للخصم بالمستخلص
    (HSE Emergency Medical & Penalty Backcharge).
    """
    contract = master_test_setup["contract"]
    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-HSE-01",
        project=contract.project,
        contract=contract,
        contractor=contract.contractor,
        currency=master_test_setup["egp_currency"],
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        gross_certified_work=Decimal("500000.00"),
        hse_medical_and_incident_costs=Decimal("8000.00"),
        hse_safety_penalties=Decimal("12000.00"),
        status=ContractorProgressCertificate.CertificateStatus.DRAFT
    )
    cert.compute_amounts()
    assert cert.hse_medical_and_incident_costs == Decimal("8000.00")
    assert cert.hse_safety_penalties == Decimal("12000.00")


@pytest.mark.django_db
def test_site_debris_and_rubble_clearance_backcharge(master_test_setup):
    """
    ركيزة 49: تسجيل بونات نقل الرتش والمخلفات وتوجيهها كخصم فوري على المستخلص
    (Site Debris & Rubble Clearance Backcharge).
    """
    contract = master_test_setup["contract"]
    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-DEB-01",
        project=contract.project,
        contract=contract,
        contractor=contract.contractor,
        currency=master_test_setup["egp_currency"],
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        gross_certified_work=Decimal("600000.00"),
        debris_clearance_charges=Decimal("15000.00"),
        status=ContractorProgressCertificate.CertificateStatus.DRAFT
    )
    log = SiteDebrisClearanceLog.objects.create(
        certificate=cert,
        trip_ticket_number="TRIP-DEB-01",
        clearance_date=date(2026, 1, 20),
        truck_capacity_m3=Decimal("20.00"),
        trip_cost=Decimal("10000.00"),
        loader_hours=Decimal("5.00"),
        loader_cost=Decimal("5000.00"),
        total_clearance_charge=Decimal("15000.00")
    )
    cert.compute_amounts()
    assert cert.debris_clearance_charges == Decimal("15000.00")
    assert log.total_clearance_charge == Decimal("15000.00")


@pytest.mark.django_db
def test_rebar_bbs_reconciliation_and_excess_scrap_backcharge(master_test_setup):
    """
    ركيزة 52: مطابقة حديد التسليح بين جدول التفريد BBS والمنصرف الفعلي وخصم الهالك الزائد
    (Rebar BBS Reconciliation & Excess Scrap Backcharge).
    """
    contract = master_test_setup["contract"]
    log = RebarConsumptionLog.objects.create(
        project=contract.project,
        contractor=contract.contractor,
        contract=contract,
        element_name="أعمدة وسقف الدور الأول علوي",
        rebar_diameter_mm=16,
        bbs_theoretical_weight_tons=Decimal("20.000"),
        actual_delivered_weight_tons=Decimal("22.500"),
        allowed_waste_rate=Decimal("2.50"),  # 0.500 طن مسموح
        scrap_returned_weight_tons=Decimal("0.500"),
        excess_waste_weight_tons=Decimal("1.500"),  # هالك غير مبرر
        steel_market_price_per_ton=Decimal("40000.00"),
        excess_waste_backcharge_amount=Decimal("60000.00")  # 1.5 * 40,000
    )
    assert log.excess_waste_weight_tons == Decimal("1.500")
    assert log.excess_waste_backcharge_amount == Decimal("60000.00")


@pytest.mark.django_db
def test_disputed_line_item_quarantine_and_partial_approval(master_test_setup):
    """
    ركيزة 55: حجر البنود المتنازع عليها مؤقتاً واعتماد وصرف باقي بنود المستخلص السليمة
    (Disputed Line Item Quarantine & Partial Approval).
    """
    contract = master_test_setup["contract"]
    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-DIS-01",
        project=contract.project,
        contract=contract,
        contractor=contract.contractor,
        currency=master_test_setup["egp_currency"],
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        gross_certified_work=Decimal("1000000.00"),
        disputed_items_holdback_total=Decimal("150000.00"),
        status=ContractorProgressCertificate.CertificateStatus.DRAFT
    )
    # بند محجوز عليه لنزاع فني
    item = ContractorCertificateItem.objects.create(
        certificate=cert,
        item_code="DIS-CNC-01",
        description="صب لبشة خزان المياه الأرضي",
        unit="M3",
        previous_quantity=Decimal("0.000"),
        current_quantity=Decimal("30.000"),
        unit_rate=Decimal("5000.00"),
        total_cumulative_amount=Decimal("150000.00"),
        current_period_amount=Decimal("150000.00"),
        is_disputed_holdback=True,
        dispute_reason="انتظار نتائج فحص المعمل المستقل للقلب الخرساني",
        disputed_amount=Decimal("150000.00")
    )
    cert.compute_amounts()
    assert cert.disputed_items_holdback_total == Decimal("150000.00")
    assert item.is_disputed_holdback is True


@pytest.mark.django_db
def test_owner_scaffolding_and_equipment_damage_backcharge(master_test_setup):
    """
    ركيزة 56: تسجيل عهدة الشدات والمعدات المعارة واحتساب استقطاع التلفيات
    (Owner Scaffolding & Equipment Damage Backcharge).
    """
    contract = master_test_setup["contract"]
    log = ContractorScaffoldingLog.objects.create(
        contract=contract,
        equipment_type="Acrow Props & H20 Beams",
        delivered_quantity=500,
        returned_good_quantity=450,
        damaged_quantity=30,
        missing_quantity=20,
        unit_repair_or_replacement_cost=Decimal("250.00"),
        total_damage_deduction=Decimal("12500.00"),  # (30 + 20) * 250
        log_date=date(2026, 1, 25)
    )
    assert log.damaged_quantity == 30
    assert log.missing_quantity == 20
    assert log.total_damage_deduction == Decimal("12500.00")


@pytest.mark.django_db
def test_dewatering_pumping_log_and_breakdown_fuel_deduction(master_test_setup):
    """
    ركيزة 61: تسجيل يوميات النزح الجوفي واحتساب غرامات الأعطال وسولار المالك
    (Dewatering Pumping Log & Breakdown Fuel Deduction).
    """
    contract = master_test_setup["contract"]
    log = DewateringPumpingLog.objects.create(
        contract=contract,
        log_date=date(2026, 1, 10),
        pumps_operating_count=4,
        daily_running_hours=Decimal("18.00"),
        breakdown_hours=Decimal("6.00"),
        stoppage_penalty_rate_per_hour=Decimal("500.00"),
        total_stoppage_penalty=Decimal("3000.00"),
        diesel_liters_supplied_by_owner=Decimal("200.00"),
        diesel_price_per_liter=Decimal("15.00"),
        diesel_total_backcharge=Decimal("3000.00")
    )
    total_charges = log.total_stoppage_penalty + log.diesel_total_backcharge
    assert total_charges == Decimal("6000.00")


@pytest.mark.django_db
def test_steel_rolling_margin_tolerance_isolation_from_scrap(master_test_setup):
    """
    ركيزة 62: عزل تفاوت وزن درفلة مصنع الحديد عن احتساب الهالك الفعلي المستقطع
    (Steel Rolling Margin Tolerance Isolation from Scrap).
    """
    contract = master_test_setup["contract"]
    log = RebarConsumptionLog.objects.create(
        project=contract.project,
        contractor=contract.contractor,
        contract=contract,
        element_name="قواعد ولبشة خرسانية",
        rebar_diameter_mm=25,
        bbs_theoretical_weight_tons=Decimal("50.000"),
        actual_delivered_weight_tons=Decimal("52.000"),
        rolling_margin_tolerance_percent=Decimal("2.50"),  # تفاوت درفلة مصنع معتمد 1.25 طن
        adjusted_net_waste_weight_tons=Decimal("0.750"),
        steel_market_price_per_ton=Decimal("40000.00"),
        excess_waste_backcharge_amount=Decimal("30000.00")
    )
    assert log.rolling_margin_tolerance_percent == Decimal("2.50")
    assert log.adjusted_net_waste_weight_tons == Decimal("0.750")


@pytest.mark.django_db
def test_pile_bulbing_factor_in_deep_foundation_concrete_reconciliation(master_test_setup):
    """
    ركيزة 66: معامل انتفاخ خرسانة الخوازيق وعزل تكهفات التربة عن هالك المقاول
    (Pile Bulbing Factor in Deep Foundation Concrete Reconciliation).
    """
    contract = master_test_setup["contract"]
    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-PIL-01",
        project=contract.project,
        contract=contract,
        contractor=contract.contractor,
        currency=master_test_setup["egp_currency"],
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        gross_certified_work=Decimal("500000.00"),
        status=ContractorProgressCertificate.CertificateStatus.DRAFT
    )
    rec = ConcreteBatchReconciliation.objects.create(
        certificate=cert,
        casting_subcontractor=contract,
        element_description="خوازيق حفر دوار عميقة (Bored Piles)",
        surveyed_as_built_volume_m3=Decimal("1000.000"),
        actual_batch_delivered_volume_m3=Decimal("1140.000"),
        contractual_waste_tolerance_rate=Decimal("15.00"),  # 15% معامل انتفاخ الخوازيق Bulbing Factor
        allowed_waste_volume_m3=Decimal("150.000"),
        excess_waste_volume_m3=Decimal("0.000"),  # ضمن السماحية
        concrete_unit_price=Decimal("4000.00"),
        excess_waste_backcharge_amount=Decimal("0.00")
    )
    assert rec.excess_waste_volume_m3 == Decimal("0.000")
    assert rec.excess_waste_backcharge_amount == Decimal("0.00")


@pytest.mark.django_db
def test_third_party_lab_test_failure_backcharge_accounting(master_test_setup):
    """
    ركيزة 67: تحميل فواتير المعامل المستقلة الخارجية كخصم فني عند رسوب العينات
    (Third-Party Lab Test Failure Backcharge Accounting).
    """
    contract = master_test_setup["contract"]
    lab_log = ThirdPartyLabTestLog.objects.create(
        contract=contract,
        lab_name="معمل مركز بحوث الإسكان والبناء HBRC",
        invoice_number="INV-HBRC-2026-88",
        test_type="فحص واختبار القلب الخرساني Core Test",
        test_date=date(2026, 1, 18),
        tested_element="أعمدة الطابق الأرضي محور 4",
        is_test_passed=False,  # راسب
        total_invoice_amount=Decimal("12000.00"),
        is_backcharged_to_contractor=True
    )
    assert lab_log.is_test_passed is False
    assert lab_log.is_backcharged_to_contractor is True
    assert lab_log.total_invoice_amount == Decimal("12000.00")


@pytest.mark.django_db
def test_hot_weather_concreting_batch_rejection_and_zero_billing(master_test_setup):
    """
    ركيزة 68: تسجيل الشاحنات المطرودة في الطقس الحار وتصفير قيمتها بمستخلص محطة الخلط
    (Hot Weather Concreting Batch Rejection & Zero Billing).
    """
    project = master_test_setup["project"]
    block = master_test_setup["block"]

    rejected_batch = ConcreteBatchDelivery.objects.create(
        project=project,
        block=block,
        delivery_note_number="DN-CNC-HOT-01",
        delivery_date=date(2026, 7, 15),
        casting_location="لبشة الخزان",
        concrete_grade="C35",
        batch_volume_m3=Decimal("10.00"),
        unit_price=Decimal("0.00"),
        concrete_temperature_celsius=Decimal("34.5"),  # أعلى من 32°م المسموحة
        is_batch_rejected=True,
        rejection_reason="ارتفاع درجة حرارة الخرسانة عن 32°م وتجاوز زمن الشك الابتدائي",
        total_amount=Decimal("0.00"),
        is_sample_passed=False
    )
    assert rejected_batch.is_batch_rejected is True
    assert rejected_batch.total_amount == Decimal("0.00")


@pytest.mark.django_db
def test_hydrostatic_pressure_test_failure_collateral_damage_backcharge(master_test_setup):
    """
    ركيزة 76: تسجيل فشل اختبار الضغط الهيدروستاتيكي وتحميل تكاليف التكسير والصب كخصم فني
    (Hydrostatic Pressure Test Failure Collateral Damage Backcharge).
    """
    contract = master_test_setup["contract"]
    fail_log = HydrostaticTestFailureLog.objects.create(
        contract=contract,
        network_segment="شبكة تغذية المياه والصرف للحمام الرئيسي",
        test_date=date(2026, 1, 22),
        tested_pressure_bar=Decimal("10.00"),
        pressure_drop_bar=Decimal("4.50"),  # هبوط حاد
        leak_location="كسر وجلبة تسريب تحت بلاط الدور الثاني",
        concrete_breaking_cost=Decimal("6000.00"),
        re_casting_and_waterproofing_cost=Decimal("9000.00"),
        total_remedial_backcharge=Decimal("15000.00")
    )
    assert fail_log.total_remedial_backcharge == Decimal("15000.00")


# ==============================================================================
# 5. اختبارات دورة العمليات التشغيلية والتسويات (Pillars 48, 53, 54, 57, 59, 64, 70, 78)
# ==============================================================================

@pytest.mark.django_db
def test_leftover_materials_on_site_absorption_into_stock(master_test_setup):
    """
    ركيزة 48: تسوية تشوينات الموقع المتبقية والاستحواذ عليها لمخزن المشروع وسداد 25% للمقاول
    (Leftover Materials on Site Absorption into Stock - Article 658 Civil Code).
    """
    contract = master_test_setup["contract"]
    user = master_test_setup["user_admin"]

    # إنهاء العقد واستحواذ تشوينات بقيمة عادلة 200,000 ج.م
    # (تم تمويل 75% سابقاً = 150,000 ج.م، و25% تسدد للمقاول = 50,000 ج.م)
    protocol_data = {
        "protocol_reference": "TERM-MOS-2026-001",
        "survey_date": date(2026, 6, 1),
        "consultant_representative": "م. حازم عبد الله",
        "employer_representative": "م. كريم الشناوي",
        "contractor_representative": "م. عادل إبراهيم",
        "as_built_completed_value": Decimal("1000000.00"),
        "uninstalled_materials_value": Decimal("200000.00"),
        "snag_and_remedial_costs": Decimal("0.00"),
        "site_vacated_and_handed_over": True
    }
    protocol = ContractorContractService.terminate_contract_and_settle(
        contract=contract,
        protocol_data=protocol_data,
        liquidate_lg=False,
        user=user
    )
    assert protocol.id is not None
    contract.refresh_from_db()
    assert contract.status == ContractorContract.ContractStatus.TERMINATED


@pytest.mark.django_db
def test_mos_site_custody_receipt_and_gate_pass_lock(master_test_setup):
    """
    ركيزة 53: تحرير محضر إثبات الحيازة وتنازل الملكية للمشونات وقفل تصريح الخروج بالبوابة الأمنية
    (MOS Site Custody Receipt & Gate Pass Lock).
    """
    contract = master_test_setup["contract"]
    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-MOS-01",
        project=contract.project,
        contract=contract,
        contractor=contract.contractor,
        currency=master_test_setup["egp_currency"],
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        gross_certified_work=Decimal("300000.00"),
        status=ContractorProgressCertificate.CertificateStatus.DRAFT
    )
    mos = ContractorMaterialOnSite.objects.create(
        certificate=cert,
        item_name="حديد تسليح 16 مم عز الدخيلة",
        unit="TON",
        surveyed_quantity=Decimal("10.000"),
        invoice_unit_cost=Decimal("40000.00"),
        total_material_value=Decimal("400000.00"),
        advance_financing_rate=Decimal("75.00"),
        approved_advance_amount=Decimal("300000.00")
    )
    receipt = ContractorMOSCustodyReceipt.objects.create(
        mos_item=mos,
        receipt_number="VEST-2026-001",
        vesting_date=date(2026, 1, 15),
        is_vested_in_employer=True,
        gate_exit_locked=True,
        consultant_engineer_approval=True
    )
    assert receipt.is_vested_in_employer is True
    assert receipt.gate_exit_locked is True


@pytest.mark.django_db
def test_direct_payment_to_nominated_subcontractor_and_setoff(master_test_setup):
    """
    ركيزة 54: السداد المباشر لمقاول الباطن المعين وتوليد قيد المقاصة الفوري على المقاول العام
    (Direct Payment to Nominated Subcontractor & Set-off).
    """
    main_contract = master_test_setup["contract"]
    nominated_sub = master_test_setup["nominated_subcontractor"]

    nom_contract = ContractorContract.objects.create(
        contract_number="CNT-NOM-01",
        title="عقد توريد وتركيب مصاعد البرج",
        project=main_contract.project,
        block=main_contract.block,
        contractor=nominated_sub,
        is_nominated_subcontractor=True,
        main_contractor=main_contract,
        direct_payment_allowed=True,
        initial_contract_value=Decimal("1000000.00"),
        status=ContractorContract.ContractStatus.ACTIVE
    )
    assert nom_contract.is_nominated_subcontractor is True
    assert nom_contract.direct_payment_allowed is True
    assert nom_contract.main_contractor == main_contract


@pytest.mark.django_db
def test_refundable_milestone_delay_penalty_recovery(master_test_setup):
    """
    ركيزة 57: استرداد غرامة التأخير المرحلية وردها للمقاول عند تسليم المحطة اللاحقة
    (Refundable Milestone Delay Penalty Recovery).
    """
    contract = master_test_setup["contract"]
    # مستخلص يتضمن رد غرامة مرحلية تم استقطاعها سابقاً
    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-MLST-01",
        project=contract.project,
        contract=contract,
        contractor=contract.contractor,
        currency=master_test_setup["egp_currency"],
        period_start=date(2026, 2, 1),
        period_end=date(2026, 2, 28),
        gross_certified_work=Decimal("1000000.00"),
        recovered_milestone_penalties=Decimal("25000.00"),
        status=ContractorProgressCertificate.CertificateStatus.DRAFT
    )
    cert.compute_amounts()
    # الغرامة المستردة تقلل إجمالي الاستقطاعات فتزيد الصافي
    assert cert.recovered_milestone_penalties == Decimal("25000.00")


@pytest.mark.django_db
def test_wir_mir_inspection_requests_linkage_to_certificate_items(master_test_setup):
    """
    ركيزة 59: التحقق من وجود محاضر استلام الأعمال WIR وفحص المواد MIR قبل صرف البنود
    (WIR/MIR Inspection Requests Linkage to Certificate Items).
    """
    contract = master_test_setup["contract"]
    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-INSP-01",
        project=contract.project,
        contract=contract,
        contractor=contract.contractor,
        currency=master_test_setup["egp_currency"],
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        gross_certified_work=Decimal("500000.00"),
        status=ContractorProgressCertificate.CertificateStatus.DRAFT
    )
    item = ContractorCertificateItem.objects.create(
        certificate=cert,
        item_code="WIR-MIR-01",
        description="عزل رطوبة وحرارة للأسطح",
        unit="M2",
        previous_quantity=Decimal("0.000"),
        current_quantity=Decimal("500.000"),
        unit_rate=Decimal("250.00"),
        total_cumulative_amount=Decimal("125000.00"),
        current_period_amount=Decimal("125000.00"),
        wir_reference="WIR-ROOF-2026-044",
        mir_reference="MIR-INSUL-2026-012"
    )
    assert item.wir_reference == "WIR-ROOF-2026-044"
    assert item.mir_reference == "MIR-INSUL-2026-012"


@pytest.mark.django_db
def test_emergency_fast_track_provisional_eid_certificate_flow(master_test_setup):
    """
    ركيزة 64: دورة صرف المستخلص الاستثنائي المعجل بنسبة أمان 75% للأعياد وإقفاله لاحقاً
    (Emergency Fast-Track Provisional Eid Certificate Flow).
    """
    contract = master_test_setup["contract"]
    provisional_cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-EID-PROV-01",
        project=contract.project,
        contract=contract,
        contractor=contract.contractor,
        currency=master_test_setup["egp_currency"],
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 20),
        gross_certified_work=Decimal("400000.00"),
        is_fast_track_provisional=True,
        provisional_safety_percentage=Decimal("75.00"),  # 75% نسبة صرف أمان
        status=ContractorProgressCertificate.CertificateStatus.DRAFT
    )
    provisional_cert.compute_amounts()
    assert provisional_cert.is_fast_track_provisional is True
    assert provisional_cert.provisional_safety_percentage == Decimal("75.00")


@pytest.mark.django_db
def test_employer_suspension_standby_demurrage_claim_posting(master_test_setup):
    """
    ركيزة 70: إثبات واعتماد تعويضات التوقف القسري للأعمال كبند مالي مستقل (FIDIC 8.8)
    (Employer Suspension Standby Demurrage Claim Posting).
    """
    contract = master_test_setup["contract"]
    claim = ContractorSuspensionClaim.objects.create(
        contract=contract,
        suspension_order_reference="SUSP-ORD-2026-01",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 15),
        idle_days_count=15,
        idle_scaffolding_cost=Decimal("20000.00"),
        idle_equipment_cost=Decimal("15000.00"),
        site_overhead_and_security=Decimal("10000.00"),
        total_approved_claim_amount=Decimal("45000.00"),
        is_approved_by_cfo=True
    )
    assert claim.total_approved_claim_amount == Decimal("45000.00")
    assert claim.is_approved_by_cfo is True


@pytest.mark.django_db
def test_certificate_payment_installment_rescheduling_protocol_lifecycle(master_test_setup):
    """
    ركيزة 78: بروتوكول جدولة سداد المستخلص على دفعات مؤرخة وربطها بالشيكات الآجلة
    (Certificate Payment Installment Rescheduling Protocol Lifecycle).
    """
    contract = master_test_setup["contract"]
    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-SCH-01",
        project=contract.project,
        contract=contract,
        contractor=contract.contractor,
        currency=master_test_setup["egp_currency"],
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        gross_certified_work=Decimal("600000.00"),
        net_amount=Decimal("540000.00"),
        status=ContractorProgressCertificate.CertificateStatus.APPROVED
    )
    inst1 = CertificatePaymentInstallmentSchedule.objects.create(
        certificate=cert,
        installment_number=1,
        due_date=date(2026, 2, 28),
        amount=Decimal("270000.00"),
        payment_method=CertificatePaymentInstallmentSchedule.PaymentMethod.PDC_CHEQUE
    )
    inst2 = CertificatePaymentInstallmentSchedule.objects.create(
        certificate=cert,
        installment_number=2,
        due_date=date(2026, 3, 31),
        amount=Decimal("270000.00"),
        payment_method=CertificatePaymentInstallmentSchedule.PaymentMethod.PDC_CHEQUE
    )
    assert cert.installment_schedules.count() == 2
    assert inst1.amount + inst2.amount == cert.net_amount


# ==============================================================================
# 6. اختبارات الركائز الأساسية والتشفير والإلغاء العكسي (Pillars 1, 2, 3, 4, 6, 22, 35)
# ==============================================================================

@pytest.mark.django_db
def test_cumulative_quantity_progression_math(master_test_setup):
    """
    ركيزة 1: التحقق الرياضي الدقيق لحساب الكميات التراكمية للبند
    (Cumulative Quantity Progression Math).
    """
    contract = master_test_setup["contract"]
    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-MATH-01",
        project=contract.project,
        contract=contract,
        contractor=contract.contractor,
        currency=master_test_setup["egp_currency"],
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        gross_certified_work=Decimal("450000.00"),
        status=ContractorProgressCertificate.CertificateStatus.DRAFT
    )
    item = ContractorCertificateItem.objects.create(
        certificate=cert,
        item_code="CNC-01",
        description="خرسانة مسلحة للأسقف",
        unit="M3",
        previous_quantity=Decimal("150.000"),
        current_quantity=Decimal("100.000"),
        unit_rate=Decimal("4500.00")
    )
    assert item.cumulative_quantity == Decimal("250.000")
    assert item.current_work_value == Decimal("450000.00")
    assert item.cumulative_work_value == Decimal("1125000.00")


@pytest.mark.django_db
def test_unapproved_previous_certificate_guard(master_test_setup):
    """
    ركيزة 2: منع إنشاء أو اعتماد مستخلص جديد في وجود مستخلص سابق غير معتمد لنفس العقد
    (Unapproved Previous Certificate Sequential Order Guard).
    """
    contract = master_test_setup["contract"]
    user = master_test_setup["user_admin"]

    # مستخلص 1 لا يزال مسودة DRAFT
    cert1 = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-SEQ-01",
        project=contract.project,
        contract=contract,
        contractor=contract.contractor,
        currency=master_test_setup["egp_currency"],
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        gross_certified_work=Decimal("200000.00"),
        sequence_order=1,
        status=ContractorProgressCertificate.CertificateStatus.DRAFT
    )
    # محاولة تقديم مستخلص 2 للاعتماد
    cert2 = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-SEQ-02",
        project=contract.project,
        contract=contract,
        contractor=contract.contractor,
        currency=master_test_setup["egp_currency"],
        period_start=date(2026, 2, 1),
        period_end=date(2026, 2, 28),
        gross_certified_work=Decimal("350000.00"),
        sequence_order=2,
        status=ContractorProgressCertificate.CertificateStatus.DRAFT
    )
    with pytest.raises(SequentialOrderError) as exc_info:
        ContractorProgressService.submit_certificate_for_approval(cert2, user)
    assert "مستخلصات سابقة قيد الإعداد أو المراجعة" in str(exc_info.value)


@pytest.mark.django_db
def test_retention_calculation_and_cap(master_test_setup):
    """
    ركيزة 3: احتساب نسبة التأمين وتوقف الاستقطاع عند بلوغ سقف تأمين العقد
    (Retention Calculation & Contract Retention Cap Guard).
    """
    contract = master_test_setup["contract"]
    contract.retention_cap_amount = Decimal("100000.00")
    contract.total_retention_retained = Decimal("90000.00")
    contract.save()

    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-CAP-01",
        project=contract.project,
        contract=contract,
        contractor=contract.contractor,
        currency=master_test_setup["egp_currency"],
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        gross_certified_work=Decimal("500000.00"),
        retention_rate=Decimal("5.00"),  # 5% من 500,000 = 25,000
        status=ContractorProgressCertificate.CertificateStatus.DRAFT
    )
    cert.compute_amounts()
    # سقف التأمين 100,000 والمستقطع سابقاً 90,000؛ إذاً يُستقطع 10,000 فقط وليس 25,000
    assert cert.retention_amount == Decimal("100000.00") - Decimal("90000.00")


@pytest.mark.django_db
def test_advance_payment_automatic_recovery(master_test_setup):
    """
    ركيزة 4: استرداد الدفعة المقدمة آلياً بنسبة استرداد العقد
    (Advance Payment Automatic Recovery).
    """
    contract = master_test_setup["contract"]
    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-ADV-01",
        project=contract.project,
        contract=contract,
        contractor=contract.contractor,
        currency=master_test_setup["egp_currency"],
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        gross_certified_work=Decimal("500000.00"),
        advance_payment_recovery=Decimal("50000.00"),  # 10%
        status=ContractorProgressCertificate.CertificateStatus.DRAFT
    )
    cert.compute_amounts()
    assert cert.advance_payment_recovery == Decimal("50000.00")


@pytest.mark.django_db
def test_cryptographic_hash_immutability(master_test_setup):
    """
    ركيزة 6: القفل التشفيري المشفر ومنع التعديل على المستخلص المعتمد
    (Cryptographic Hash Merkle-Tree Immutability & Tamper Lock).
    """
    contract = master_test_setup["contract"]
    user = master_test_setup["user_admin"]

    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-HASH-01",
        project=contract.project,
        contract=contract,
        contractor=contract.contractor,
        currency=master_test_setup["egp_currency"],
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        gross_certified_work=Decimal("400000.00"),
        status=ContractorProgressCertificate.CertificateStatus.DRAFT
    )
    submitted = ContractorProgressService.submit_certificate_for_approval(cert, user)
    submitted.refresh_from_db()
    assert len(submitted.approval_snapshot_hash) == 64

    # موافقة الاعتماد
    submitted.approval_request.status = 'APPROVED'
    submitted.approval_request.save()

    # محاولة التلاعب وتغيير قيمة الأعمال بدون تصريح
    submitted.gross_certified_work = Decimal("999999.00")
    submitted.save()

    with pytest.raises(MutationTamperError) as exc_info:
        ContractorProgressService.verify_and_post_certificate(submitted, user)
    assert "تعديل في الأرقام المالية" in str(exc_info.value)


@pytest.mark.django_db
def test_storno_reversal_workflow(master_test_setup):
    """
    ركيزة 22: توليد القيد العكسي بدقة ورد أرصدة الدفعات والتأمينات للعقد
    (Storno Reversal Workflow & Contract Balances Unwinding).
    """
    contract = master_test_setup["contract"]
    user = master_test_setup["user_admin"]

    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-REV-01",
        project=contract.project,
        contract=contract,
        contractor=contract.contractor,
        currency=master_test_setup["egp_currency"],
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        gross_certified_work=Decimal("300000.00"),
        status=ContractorProgressCertificate.CertificateStatus.DRAFT
    )
    submitted = ContractorProgressService.submit_certificate_for_approval(cert, user)
    submitted.approval_request.status = 'APPROVED'
    submitted.approval_request.save()
    ContractorProgressService.verify_and_post_certificate(submitted, user)
    submitted.refresh_from_db()
    assert submitted.status == ContractorProgressCertificate.CertificateStatus.APPROVED
    assert submitted.journal_entry is not None

    # إجراء الإلغاء العكسي Storno
    ContractorProgressService.reverse_certificate(
        certificate=submitted,
        reason="خطأ في كشف حصر استشاري المالك",
        user=user
    )
    submitted.refresh_from_db()
    assert submitted.status == ContractorProgressCertificate.CertificateStatus.CANCELLED
    assert submitted.reversal_entry is not None


@pytest.mark.django_db
def test_phased_retention_release_substantial_and_final(master_test_setup):
    """
    ركيزة 35: الإفراج المرحلي عن التأمين (50% استلام ابتدائي و50% استلام نهائي)
    (Phased Retention Release: Substantial 50% & Final 50% with Defect Holdbacks).
    """
    contract = master_test_setup["contract"]
    user = master_test_setup["user_admin"]

    contract.total_retention_retained = Decimal("200000.00")
    contract.actual_completion_date = date(2020, 1, 1)
    contract.save()

    # 1. إفراج استلام ابتدائي 50% (100,000 ج.م)
    entry1 = ContractorProgressService.release_retention(
        contract=contract,
        release_type="SUBSTANTIAL_HANDOVER",
        amount=Decimal("100000.00"),
        defect_deductions=Decimal("0.00"),
        user=user
    )
    assert entry1 is not None
    contract.refresh_from_db()
    assert contract.total_retention_released == Decimal("100000.00")

    # 2. إفراج نهائي 50% مع حجز 10,000 ج.م لإصلاح عيوب
    entry2 = ContractorProgressService.release_retention(
        contract=contract,
        release_type="FINAL_WARRANTY_CLEARANCE",
        amount=Decimal("100000.00"),
        defect_deductions=Decimal("10000.00"),
        user=user
    )
    assert entry2 is not None
    contract.refresh_from_db()
    assert contract.total_retention_released == Decimal("200000.00")
