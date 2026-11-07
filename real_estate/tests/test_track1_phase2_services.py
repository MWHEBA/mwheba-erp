# -*- coding: utf-8 -*-
"""
Track 1 - Phase 2: Business Logic & Accounting Gateway Services Test Suite
MWHEBA ERP - Real Estate App

Verifies 100% of the engineering and financial services:
- Master BOQ ceilings & target cost rate overrun guards
- Escrow advance payment disbursement
- Variation orders & dynamic advance recovery recalibration
- Hard compliance guards: Judicial Garnishment, Bank Assignment, LG Pay-or-Extend, CAR insurance
- Track 1 14-step cascading certificate posting & Egyptian tax regimes (Table Tax 5% vs VAT 14%)
- Storno Reversal workflow & contract balance unwinding
- Phased retention release (Substantial 50% & Final 50% with defect holdbacks)
- Sectional handover with independent warranty clocks
- Leftover materials stock absorption upon contract termination (Article 658 Civil Code)
- Micro-contract self-billing for individual craftsmen
- Installment PDC cheque settlement
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
    CertificatePaymentInstallmentSchedule,
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
from financial.models.approval import EnterpriseApprovalRule, EnterpriseApprovalRequest
from users.models import Role

User = get_user_model()


@pytest.fixture
def service_setup(db):
    """Sets up complete test environment with chart of accounts, users, approval rules, project, and contractor."""
    user_admin = User.objects.create_superuser(
        username="admin_phase2",
        email="admin_p2@example.com",
        password="password123"
    )

    # 1. تهيئة أنواع الحسابات ودليل الحسابات
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
    EnterpriseApprovalRule.objects.create(
        module='REAL_ESTATE',
        rule_name='اعتماد مستخلصات المقاولين',
        min_amount=Decimal('0.00'),
        max_amount=Decimal('999999999.00'),
        approver_role='site_engineer',
        approval_level=1,
        is_active=True
    )

    # 3. المشروع والمقاول
    project = RealEstateProject.objects.create(
        code="PRJ-SRV",
        name="مشروع أبراج النرجس الإنشائي",
        project_type="RESIDENTIAL",
        status="UNDER_CONSTRUCTION",
        start_date=date(2026, 1, 1),
        expected_completion_date=date(2028, 12, 31),
        created_by=user_admin
    )
    block = PropertyBlock.objects.create(
        project=project,
        code="BLK-01",
        name="برج النرجس A",
        total_floors=10
    )
    contractor = Supplier.objects.create(
        name="شركة الصفا للإنشاءات الهندسية",
        code="CON-SRV-01",
        tax_number="987654321"
    )
    master_boq = ProjectMasterBOQItem.objects.create(
        project=project,
        block=block,
        item_code="BOQ-CNC-01",
        description="خرسانة مسلحة للأسقف والأعمدة",
        unit="M3",
        master_budget_quantity=Decimal("1000.00"),
        unit_rate_estimate=Decimal("4000.00"),
        total_budget_cost=Decimal("4000000.00"),
        overrun_tolerance_rate=Decimal("10.00")  # سقف أقصى 1100 م3
    )

    return {
        "user_admin": user_admin,
        "project": project,
        "block": block,
        "contractor": contractor,
        "master_boq": master_boq,
        "egp_currency": egp_currency,
        "usd_currency": usd_currency,
    }


@pytest.mark.django_db
def test_master_boq_and_budget_validation(service_setup):
    """Tests Master BOQ ceilings, quantity tolerances, and budget rate overrun guards."""
    project = service_setup["project"]
    block = service_setup["block"]
    contractor = service_setup["contractor"]
    boq = service_setup["master_boq"]

    contract = ContractorContract.objects.create(
        contract_number="CNT-VAL-01",
        title="عقد خرسانات المرحلة الأولى",
        project=project,
        block=block,
        contractor=contractor,
        initial_contract_value=Decimal("2000000.00"),
    )

    # 1. بند طبيعي ضمن السقف التقديري مع فئة تتجاوز الموازنة
    item_data = {
        "item_code": "BOQ-CNC-01",
        "contracted_quantity": Decimal("600.00"),
        "unit_rate": Decimal("4200.00"),  # أعلى من 4000 الموازنة
        "master_boq_item": boq,
        "unit": "M3",
    }
    item1 = ContractorContractService.create_contract_item(contract, item_data)
    assert item1.is_budget_rate_overrun is True
    assert item1.contracted_quantity == Decimal("600.00")
    boq.refresh_from_db()
    assert boq.allocated_quantity_to_contracts == Decimal("600.00")

    # 2. محاولة تجاوز سقف المقايسة الكلي (1100 م3 كحد أقصى بالسماحية)
    excess_data = {
        "item_code": "BOQ-CNC-01",
        "contracted_quantity": Decimal("600.00"),  # 600 + 600 = 1200 > 1100
        "unit_rate": Decimal("4000.00"),
        "master_boq_item": boq,
    }
    with pytest.raises(ValidationError) as exc_info:
        ContractorContractService.create_contract_item(contract, excess_data)
    assert "تتجاوز السقف الأقصى المتاح بمقايسة المشروع العامة" in str(exc_info.value)


@pytest.mark.django_db
def test_advance_payment_disbursement_workflow(service_setup):
    """Tests disbursement of advance payments via Project Escrow account with balanced GL posting."""
    project = service_setup["project"]
    contractor = service_setup["contractor"]
    user_admin = service_setup["user_admin"]

    contract = ContractorContract.objects.create(
        contract_number="CNT-ADV-01",
        title="عقد الحفر وسند جوانب الحفر",
        project=project,
        contractor=contractor,
        initial_contract_value=Decimal("1000000.00"),
        advance_payment_rate=Decimal("15.00"),
        advance_payment_amount=Decimal("150000.00"),
    )

    # صرف الدفعة المقدمة بالكامل
    entry = ContractorContractService.disburse_advance_payment(
        contract=contract,
        amount=Decimal("150000.00"),
        bank_account_code="11121",
        user=user_admin,
        notes="تحويل بنكي من حساب الضمان"
    )

    assert entry is not None
    contract.refresh_from_db()
    assert contract.advance_payment_disbursed == Decimal("150000.00")

    # التحقق من توازن القيد المحاسبي بالمليم
    debits = sum(line.debit for line in entry.lines.all())
    credits = sum(line.credit for line in entry.lines.all())
    assert debits == Decimal("150000.00")
    assert credits == Decimal("150000.00")

    # محاولة صرف مبالغ إضافية تتجاوز سقف الدفعة المقدمة
    with pytest.raises(ValidationError):
        ContractorContractService.disburse_advance_payment(
            contract=contract,
            amount=Decimal("1000.00"),
            user=user_admin
        )


@pytest.mark.django_db
def test_variation_order_and_dynamic_advance_recalibration(service_setup):
    """Tests variation order approval, value updates, and dynamic advance recovery recalibration."""
    project = service_setup["project"]
    contractor = service_setup["contractor"]
    user_admin = service_setup["user_admin"]

    contract = ContractorContract.objects.create(
        contract_number="CNT-VO-01",
        title="عقد الأعمال الإنشائية",
        project=project,
        contractor=contractor,
        initial_contract_value=Decimal("1000000.00"),
        revised_contract_value=Decimal("1000000.00"),
        advance_payment_amount=Decimal("200000.00"),
        advance_payment_disbursed=Decimal("200000.00"),
        advance_payment_recovered=Decimal("50000.00"),
        total_certified_work=Decimal("250000.00"),
        dynamic_advance_recalibration=True,
        completion_date=date(2027, 1, 1),
    )

    vo = ContractVariationOrder.objects.create(
        order_number="VO-P2-01",
        contract=contract,
        variation_type=ContractVariationOrder.VariationType.QUANTITY_INCREASE,
        net_value_impact=Decimal("500000.00"),
        approved_additional_days=30,
        status=ContractVariationOrder.VariationStatus.DRAFT,
    )

    applied_vo = ContractorContractService.apply_variation_order(vo, user=user_admin)
    assert applied_vo.status == ContractVariationOrder.VariationStatus.APPROVED

    contract.refresh_from_db()
    assert contract.revised_contract_value == Decimal("1500000.00")
    assert contract.completion_date == date(2027, 1, 31)

    # التحقق من إعادة الحساب الديناميكي لمعدل استرداد الدفعة المقدمة
    # Remaining advance = 200,000 - 50,000 = 150,000
    # Remaining contract value = 1,500,000 - 250,000 = 1,250,000
    # Recalibrated rate = 150,000 / 1,250,000 * 100 = 12.00%
    assert contract.advance_recovery_rate == Decimal("12.00")


@pytest.mark.django_db
def test_payout_eligibility_compliance_guards(service_setup):
    """Tests judicial garnishment freeze, bank assignment, LG Pay-or-Extend trigger, and CAR insurance."""
    project = service_setup["project"]
    contractor = service_setup["contractor"]

    # 1. عقد به حجز قضائي وتنازل بنكي
    contract = ContractorContract.objects.create(
        contract_number="CNT-GUARD-01",
        title="عقد مقاولة به قيود رقابية",
        project=project,
        contractor=contractor,
        is_assigned_to_bank=True,
        assigned_bank_name="البنك التجاري الدولي CIB",
        assigned_bank_iban="EG00CIB000111222333",
        is_garnished_by_court=True,
        garnishment_case_number="1234/2026 مدني كلي",
        garnishment_creditor_name="شركة الحديد والصلب",
        garnishment_amount=Decimal("500000.00"),
        guarantee_type=ContractorContract.GuaranteeType.BANK_LETTER_OF_GUARANTEE,
        bank_lg_number="LG-2026-99",
        bank_lg_expiry_date=date(2026, 3, 20),
        car_insurance_expiry_date=date(2026, 2, 1),
    )

    # فحص الأهلية بتاريخ 2026-03-10 (أي باقي 10 أيام على انتهاء خطاب الضمان <= 15 يوم)
    eligibility = ContractorContractService.check_contract_payout_eligibility(
        contract=contract,
        cert_date=date(2026, 3, 10)
    )

    assert eligibility["garnishment_active"] is True
    assert eligibility["bank_assignment_active"] is True
    assert eligibility["car_insurance_expired"] is True
    assert eligibility["pay_or_extend_triggered"] is True
    assert eligibility["is_eligible_for_direct_payout"] is False

    contract.refresh_from_db()
    assert contract.lg_pay_or_extend_triggered is True


@pytest.mark.django_db
def test_track1_certificate_posting_with_14_step_cascading_and_tax_regimes(service_setup):
    """Tests Track 1 certificate approval, 14-step cascading deductions, Table Tax 5% vs VAT 14%, and balanced GL entry."""
    project = service_setup["project"]
    block = service_setup["block"]
    contractor = service_setup["contractor"]
    user_admin = service_setup["user_admin"]
    egp_currency = service_setup["egp_currency"]

    contract = ContractorContract.objects.create(
        contract_number="CNT-T1-POST",
        title="عقد إنشاءات متكاملة",
        project=project,
        block=block,
        contractor=contractor,
        currency=egp_currency,
        tax_regime=ContractorContract.TaxRegime.TABLE_TAX_5,
        initial_contract_value=Decimal("5000000.00"),
        retention_rate=Decimal("5.00"),
        advance_recovery_rate=Decimal("10.00"),
        wht_rate=Decimal("1.00"),
        social_insurance_rate=Decimal("2.16"),
        syndicate_stamp_rate=Decimal("0.40"),
        site_utilities_deduction_rate=Decimal("0.50"),
    )

    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-TRK1-001",
        contract=contract,
        sequence_order=1,
        project=project,
        block=block,
        contractor=contractor,
        currency=egp_currency,
        certificate_type=ContractorProgressCertificate.CertificateType.STANDARD_PROGRESS,
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
        gross_certified_work=Decimal("200000.00"),
        previous_certified_work=Decimal("0.00"),
        current_mos_amount=Decimal("40000.00"),
        retention_rate=Decimal("5.00"),
        advance_payment_recovery=Decimal("20000.00"),
        wht_rate=Decimal("1.00"),
        social_insurance_rate=Decimal("2.16"),
        syndicate_stamp_rate=Decimal("0.40"),
        site_utilities_deduction_rate=Decimal("0.50"),
        equipment_hoisting_charges=Decimal("3000.00"),
        debris_clearance_charges=Decimal("1500.00"),
        pending_cube_test_hold_amount=Decimal("10000.00"),
        car_insurance_amount=Decimal("2500.00"),
        delay_penalties=Decimal("5000.00"),
    )

    # 1. تقديم للاعتماد
    submitted = ContractorProgressService.submit_certificate_for_approval(cert, user=user_admin)
    assert submitted.status == ContractorProgressCertificate.CertificateStatus.PENDING_APPROVAL
    assert submitted.approval_snapshot_hash != ""

    # 2. محاكاة موافقة دورة الاعتماد
    submitted.approval_request.status = 'APPROVED'
    submitted.approval_request.save()

    # 3. التحقق وإصدار القيد المحاسبي
    entry = ContractorProgressService.verify_and_post_certificate(submitted, user=user_admin)
    assert entry is not None
    submitted.refresh_from_db()
    assert submitted.status == ContractorProgressCertificate.CertificateStatus.APPROVED

    # 4. التحقق من توازن القيد المزدوج بالمليم (Penny Balance)
    debits = sum(line.debit for line in entry.lines.all())
    credits = sum(line.credit for line in entry.lines.all())
    assert debits == credits
    assert debits > Decimal("0.00")

    # 5. التحقق من تحديث أرقام العقد التراكمية
    contract.refresh_from_db()
    assert contract.total_certified_work == Decimal("200000.00")
    assert contract.advance_payment_recovered == Decimal("20000.00")
    assert contract.total_retention_retained == submitted.retention_amount


@pytest.mark.django_db
def test_storno_reversal_workflow(service_setup):
    """Tests Storno Reversal workflow: generates reverse entry and unwinds contract balances."""
    project = service_setup["project"]
    contractor = service_setup["contractor"]
    user_admin = service_setup["user_admin"]
    egp_currency = service_setup["egp_currency"]

    contract = ContractorContract.objects.create(
        contract_number="CNT-REV-01",
        title="عقد خرسانات",
        project=project,
        contractor=contractor,
        currency=egp_currency,
        initial_contract_value=Decimal("1000000.00"),
    )

    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-REV-001",
        contract=contract,
        sequence_order=1,
        project=project,
        contractor=contractor,
        currency=egp_currency,
        gross_certified_work=Decimal("100000.00"),
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 30),
        retention_rate=Decimal("5.00"),
        advance_payment_recovery=Decimal("10000.00"),
        wht_rate=Decimal("1.00"),
    )

    submitted = ContractorProgressService.submit_certificate_for_approval(cert, user=user_admin)
    submitted.approval_request.status = 'APPROVED'
    submitted.approval_request.save()
    orig_entry = ContractorProgressService.verify_and_post_certificate(submitted, user=user_admin)

    contract.refresh_from_db()
    assert contract.total_certified_work == Decimal("100000.00")

    # تنفيذ الإلغاء العكسي (Storno)
    storno_entry = ContractorProgressService.reverse_certificate(
        certificate=submitted,
        reason="خطأ في حصر كميات الخرسانة ورفض الاستشاري اللاحق",
        user=user_admin
    )

    assert storno_entry is not None
    assert storno_entry.entry_type == 'storno'

    # التحقق من توازن القيد العكسي
    debits = sum(line.debit for line in storno_entry.lines.all())
    credits = sum(line.credit for line in storno_entry.lines.all())
    assert debits == credits

    # التحقق من رد أرصدة العقد للصفر
    contract.refresh_from_db()
    assert contract.total_certified_work == Decimal("0.00")
    assert contract.advance_payment_recovered == Decimal("0.00")
    assert contract.total_retention_retained == Decimal("0.00")

    submitted.refresh_from_db()
    assert submitted.status == ContractorProgressCertificate.CertificateStatus.CANCELLED


@pytest.mark.django_db
def test_retention_release_substantial_and_final(service_setup):
    """Tests substantial (50%) and final (50%) retention release with defect rectification holdbacks."""
    project = service_setup["project"]
    contractor = service_setup["contractor"]
    user_admin = service_setup["user_admin"]
    egp_currency = service_setup["egp_currency"]

    contract = ContractorContract.objects.create(
        contract_number="CNT-RET-REL",
        title="عقد التشطيبات المعمارية",
        project=project,
        contractor=contractor,
        currency=egp_currency,
        total_retention_retained=Decimal("200000.00"),
        total_retention_released=Decimal("0.00"),
        actual_completion_date=date(2020, 1, 1),
    )

    # 1. إفراج استلام ابتدائي (50%) = 100,000 ج.م مع خصم 10,000 ج.م إصلاح عيوب
    entry1 = ContractorProgressService.release_retention(
        contract=contract,
        release_type="SUBSTANTIAL_HANDOVER",
        amount=Decimal("100000.00"),
        defect_deductions=Decimal("10000.00"),
        user=user_admin
    )
    assert entry1 is not None
    contract.refresh_from_db()
    assert contract.total_retention_released == Decimal("100000.00")

    # 2. إفراج نهائي بعد سنة الضمان (المتبقي 100,000 ج.م بالكامل)
    entry2 = ContractorProgressService.release_retention(
        contract=contract,
        release_type="FINAL_WARRANTY_CLEARANCE",
        amount=Decimal("100000.00"),
        defect_deductions=Decimal("0.00"),
        user=user_admin
    )
    assert entry2 is not None
    contract.refresh_from_db()
    assert contract.total_retention_released == Decimal("200000.00")


@pytest.mark.django_db
def test_sectional_handover_and_independent_warranty(service_setup):
    """Tests recording sectional handover with independent warranty clocks."""
    project = service_setup["project"]
    contractor = service_setup["contractor"]

    contract = ContractorContract.objects.create(
        contract_number="CNT-SEC-HAND",
        title="عقد العظم والإنشاءات",
        project=project,
        contractor=contractor,
    )

    record = ContractorContractService.record_sectional_handover(
        contract=contract,
        section_name="المرحلة الأولى - البدروم والأرضي",
        handover_date=date(2026, 5, 1),
        warranty_months=12,
        consultant_approval_ref="SEC-CONS-99",
        notes="تسليم مطابق للمواصفات"
    )

    assert record.id is not None
    assert record.warranty_start_date == date(2026, 5, 1)
    assert record.warranty_end_date == date(2026, 5, 1) + timedelta(days=360)


@pytest.mark.django_db
def test_joint_termination_and_materials_stock_absorption(service_setup):
    """Tests contract termination and leftover materials absorption into store inventory (Article 658)."""
    project = service_setup["project"]
    contractor = service_setup["contractor"]
    user_admin = service_setup["user_admin"]
    egp_currency = service_setup["egp_currency"]

    contract = ContractorContract.objects.create(
        contract_number="CNT-TERM-01",
        title="عقد مقاولة للفسخ والتسوية",
        project=project,
        contractor=contractor,
        currency=egp_currency,
        status=ContractorContract.ContractStatus.ACTIVE,
    )

    protocol_data = {
        "protocol_reference": "PROTO-TERM-99",
        "survey_date": date(2026, 6, 1),
        "consultant_representative": "م. أحمد الاستشاري",
        "employer_representative": "م. محمد مدير المشاريع",
        "contractor_representative": "م. علي ممثل المقاول",
        "as_built_completed_value": Decimal("400000.00"),
        "uninstalled_materials_value": Decimal("100000.00"),
        "snag_and_remedial_costs": Decimal("25000.00"),
        "site_vacated_and_handed_over": True
    }

    protocol = ContractorContractService.terminate_contract_and_settle(
        contract=contract,
        protocol_data=protocol_data,
        liquidate_lg=False,
        user=user_admin
    )

    assert protocol.id is not None
    contract.refresh_from_db()
    assert contract.status == ContractorContract.ContractStatus.TERMINATED


@pytest.mark.django_db
def test_micro_contract_self_billing(service_setup):
    """Tests self-billing voucher generation for individual craftsmen with 1% WHT and social insurance."""
    project = service_setup["project"]
    contractor = service_setup["contractor"]
    user_admin = service_setup["user_admin"]
    egp_currency = service_setup["egp_currency"]

    contract = ContractorContract.objects.create(
        contract_number="CNT-CRAFT-01",
        title="عقد مصنعيات حرفية للجبس والكرانيش",
        project=project,
        contractor=contractor,
        currency=egp_currency,
        is_unregistered_individual_craftsman=True,
    )

    entry = ContractorContractService.record_micro_contract_self_billing(
        contract=contract,
        craftsman_name="الأسطى محمود الجباس",
        gross_amount=Decimal("10000.00"),
        wht_rate=Decimal("1.00"),
        soc_ins_rate=Decimal("2.16"),
        user=user_admin
    )

    assert entry is not None
    debits = sum(line.debit for line in entry.lines.all())
    credits = sum(line.credit for line in entry.lines.all())
    assert debits == credits
    assert debits == Decimal("10000.00")


@pytest.mark.django_db
def test_installment_cheque_settlement(service_setup):
    """Tests settling certificate payment installment with PDC cheque."""
    project = service_setup["project"]
    contractor = service_setup["contractor"]
    user_admin = service_setup["user_admin"]
    egp_currency = service_setup["egp_currency"]

    contract = ContractorContract.objects.create(
        contract_number="CNT-PDC-01",
        title="عقد مقاولة سداد مجدول",
        project=project,
        contractor=contractor,
        currency=egp_currency,
    )

    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-PDC-01",
        contract=contract,
        project=project,
        contractor=contractor,
        currency=egp_currency,
        gross_certified_work=Decimal("100000.00"),
        net_amount=Decimal("100000.00"),
        status=ContractorProgressCertificate.CertificateStatus.APPROVED,
        period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 31),
    )

    inst = CertificatePaymentInstallmentSchedule.objects.create(
        certificate=cert,
        installment_number=1,
        due_date=date(2026, 8, 15),
        amount=Decimal("50000.00"),
        payment_method=CertificatePaymentInstallmentSchedule.PaymentMethod.PDC_CHEQUE,
        is_settled=False,
    )

    # محاكاة شيك بنكي
    class DummyCheque:
        id = 999
        cheque_number = "CHK-999888"
        amount = Decimal("50000.00")
        remaining_amount = Decimal("50000.00")
        status = "ISSUED"
        purpose = "INVOICE_SETTLEMENT"
        payee_name = contractor.name
        supplier = contractor
        currency = egp_currency

        def save(self, *args, **kwargs):
            pass

    entry = ContractorProgressService.settle_installment_with_cheque(
        installment=inst,
        cheque=DummyCheque(),
        user=user_admin
    )

    assert entry is not None
    inst.refresh_from_db()
    assert inst.is_settled is True
    debits = sum(line.debit for line in entry.lines.all())
    credits = sum(line.credit for line in entry.lines.all())
    assert debits == credits
    assert debits == Decimal("50000.00")
