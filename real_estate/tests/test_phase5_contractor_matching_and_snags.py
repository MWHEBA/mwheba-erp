# -*- coding: utf-8 -*-
"""
Phase 5 Comprehensive Verification Test Suite
MWHEBA ERP — Contractor Verified Scope Ceiling, Anti-Silent-Clipping,
Advance Payment Recovery Ceiling Guard, Price Escalation, Concrete Cube Holdback Release,
and Snag-to-Backcharge Bridge.
"""
from decimal import Decimal
from datetime import date, timedelta
import pytest

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyFloor,
    PropertyUnit,
    ContractorContract,
    ContractorContractItem,
    ContractorProgressCertificate,
    ContractorBackcharge,
    UnitSnagItem,
    UnitSiteProgressRecord,
)
from real_estate.services.contractor_service import ContractorProgressService
from supplier.models import Supplier
from financial.models.currency import Currency
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.approval import EnterpriseApprovalRule

User = get_user_model()


@pytest.fixture
def p5_setup(db):
    user_admin = User.objects.create_superuser(
        username="p5_admin",
        email="p5_admin@mwheba.com",
        password="password123"
    )

    asset_type, _ = AccountType.objects.get_or_create(code='asset', defaults={'name': 'أصول', 'category': 'asset', 'nature': 'debit'})
    liability_type, _ = AccountType.objects.get_or_create(code='liability', defaults={'name': 'خصوم', 'category': 'liability', 'nature': 'credit'})
    revenue_type, _ = AccountType.objects.get_or_create(code='revenue', defaults={'name': 'إيرادات', 'category': 'revenue', 'nature': 'credit'})

    currency, _ = Currency.objects.get_or_create(
        code="EGP",
        defaults={'name': "Egyptian Pound", 'symbol': "ج.م", 'is_functional': True}
    )

    accounts = {
        "12101": ("مشروعات تحت التنفيذ - أعمال مقاولات", asset_type),
        "11410": ("ضريبة القيمة المضافة - مدخلات", asset_type),
        "21310": ("تأمينات محتجزة للغير - حسن تنفيذ", liability_type),
        "21315": ("أمانات كسر مكعبات خرسانة معلقة", liability_type),
        "21318": ("أمانات أعمال غير معتمدة استشارياً RFI", liability_type),
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
        "11111": ("الخزينة الرئيسية للمشروع", asset_type),
    }
    for code, (name, a_type) in accounts.items():
        ChartOfAccounts.objects.get_or_create(
            code=code,
            defaults={'name': name, 'account_type': a_type, 'is_active': True, 'is_leaf': True}
        )

    EnterpriseApprovalRule.objects.get_or_create(
        module='REAL_ESTATE',
        rule_name='اعتماد مستخلصات المرحلة 5',
        defaults={
            'min_amount': Decimal('0.00'),
            'max_amount': Decimal('999999999.00'),
            'approver_role': 'site_engineer',
            'approval_level': 1,
            'is_active': True,
        }
    )

    project = RealEstateProject.objects.create(
        code="PRJ-P5",
        name="كمبوند برج الأمل الإنشائي",
        project_type="RESIDENTIAL",
        status="UNDER_CONSTRUCTION",
        start_date=date(2026, 1, 1),
        expected_completion_date=date(2028, 12, 31),
        created_by=user_admin
    )

    block = PropertyBlock.objects.create(
        project=project,
        code="B-P5",
        name="عمارة النخيل"
    )

    floor = PropertyFloor.objects.create(
        block=block,
        floor_number=1,
        name="الدور الأول"
    )

    unit = PropertyUnit.objects.create(
        project=project,
        block=block,
        floor=floor,
        unit_code="U-P5-101",
        unit_type="APARTMENT",
        gross_area=Decimal("140.00"),
        net_area=Decimal("120.00"),
        meter_price=Decimal("15000.00"),
        total_price=Decimal("1500000.00"),
        status=PropertyUnit.UnitStatus.AVAILABLE
    )

    contractor = Supplier.objects.create(
        code="SUP-P5-01",
        name="شركة الصفا لأعمال الخرسانات والتشييد"
    )

    contract = ContractorContract.objects.create(
        contract_number="CTR-P5-2026-001",
        title="عقد الهيكل الخرساني والتشطيبات لعمارة النخيل",
        project=project,
        block=block,
        contractor=contractor,
        currency=currency,
        initial_contract_value=Decimal("1000000.00"),
        revised_contract_value=Decimal("1000000.00"),
        advance_payment_rate=Decimal("10.00"),
        advance_payment_amount=Decimal("100000.00"),
        advance_payment_disbursed=Decimal("100000.00"),
        advance_payment_recovered=Decimal("40000.00"),
        total_retention_retained=Decimal("80000.00"),
        total_retention_released=Decimal("20000.00"),
        retention_rate=Decimal("5.00"),
        wht_rate=Decimal("1.00"),
        tax_regime=ContractorContract.TaxRegime.TABLE_TAX_5,
        status=ContractorContract.ContractStatus.ACTIVE,
        created_by=user_admin
    )

    contract_item = ContractorContractItem.objects.create(
        contract=contract,
        item_code="C-P5-01",
        description="توريد وصب خرسانة مسلحة للأسقف والأعمدة",
        unit="م3",
        contracted_quantity=Decimal("500.000"),
        revised_quantity=Decimal("500.000"),
        unit_rate=Decimal("2000.00"),
        total_budget_amount=Decimal("1000000.00")
    )

    return {
        "admin": user_admin,
        "currency": currency,
        "project": project,
        "block": block,
        "unit": unit,
        "contractor": contractor,
        "contract": contract,
        "contract_item": contract_item,
    }


def test_anti_silent_clipping_and_unverified_work_holdback(p5_setup):
    """
    اختبار منع القص الصامت:
    عند تجاوز إجمالي الأعمال المطالب بها للسقف الميداني المعتمد استشارياً،
    يتم الإبقاء على gross_certified_work سليماً بدون تشويه،
    واحتساب الفارق كاستقطاع أعمال غير معتمدة (unverified_work_holdback).
    """
    setup = p5_setup
    project = setup["project"]
    contract = setup["contract"]
    contractor = setup["contractor"]
    unit = setup["unit"]
    admin = setup["admin"]

    # إنشاء سجل تنفيذ ميداني معتمد بنسبة 20% (السقف المعتمد = 20% من 1,000,000 = 200,000)
    UnitSiteProgressRecord.objects.create(
        unit=unit,
        trade_stage="CONCRETE_SKELETON",
        contractor=contractor,
        status=UnitSiteProgressRecord.StageStatus.PASSED_AND_VERIFIED,
        completion_percentage=20,
        is_applicable=True,
        verified_by=admin
    )

    # المقاول يطالب بأعمال قدرها 300,000 ج.م (تتجاوز السقف 200,000 بـ 100,000)
    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-P5-CLIP-01",
        contract=contract,
        project=project,
        contractor=contractor,
        currency=setup["currency"],
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        gross_certified_work=Decimal("300000.00"),
        previous_certified_work=Decimal("0.00"),
        retention_rate=Decimal("5.00"),
        advance_payment_recovery=Decimal("0.00"),
        wht_rate=Decimal("1.00"),
        status=ContractorProgressCertificate.CertificateStatus.DRAFT,
        created_by=admin
    )

    # تقديم المستخلص للاعتماد
    submitted_cert = ContractorProgressService.submit_certificate_for_approval(cert, user=admin)

    # التحقق من منع القص الصامت:
    # 1. gross_certified_work لم يتم تعديله بصمت إلى 200,000 بل بقي 300,000 كما هو
    assert submitted_cert.gross_certified_work == Decimal("300000.00")
    # 2. الفارق تم احتجازه صراحة في unverified_work_holdback
    assert submitted_cert.unverified_work_holdback == Decimal("100000.00")
    # 3. صافي المستخلص محسوب بعد خصم unverified_work_holdback
    # الإضافات = 300,000 (أعمال) + 15,000 (ضريبة جدول 5%) = 315,000
    # الاستقطاعات = 15,000 (تأمين 5%) + 3,000 (خصم وإضافة 1%) + 1,350 (دمغة 0.45%) + 1,500 (مرافق 0.5%) + 100,000 (استقطاع غير معتمد) = 120,850
    # الصافي = 315,000 - 120,850 = 194,150
    assert submitted_cert.net_amount == Decimal("194150.00")


def test_advance_payment_recovery_ceiling_guard(p5_setup):
    """
    اختبار سقف استرداد الدفعة المقدمة:
    يمنع النظام تجاوز استقطاع الدفعة المقدمة للرصيد المتبقي الفعلي بالعقد
    (advance_payment_disbursed - advance_payment_recovered)
    """
    setup = p5_setup
    contract = setup["contract"]
    # الرصيد المتاح للدفعة المقدمة بالعقد = 100,000 - 40,000 = 60,000
    available_advance = contract.advance_payment_disbursed - contract.advance_payment_recovered
    assert available_advance == Decimal("60000.00")

    cert = ContractorProgressCertificate(
        certificate_number="CERT-P5-ADV-01",
        contract=contract,
        project=setup["project"],
        contractor=setup["contractor"],
        currency=setup["currency"],
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        gross_certified_work=Decimal("200000.00"),
        previous_certified_work=Decimal("0.00"),
        advance_payment_recovery=Decimal("80000.00"),  # يتجاوز الـ 60,000
        created_by=setup["admin"]
    )

    # التحقق من أن clean() يرفض صراحة التجاوز مع رسالة خطأ واضحة
    with pytest.raises(ValidationError) as exc_info:
        cert.clean()
    assert "يتجاوز الرصيد المتبقي الفعلي للدفعة المقدمة" in str(exc_info.value)

    # التحقق من أن compute_amounts() يقلم المبلغ لسقف الرصيد المتاح
    cert.compute_amounts()
    assert cert.advance_payment_recovery == Decimal("60000.00")


def test_concrete_cube_release_and_accounting_posting(p5_setup):
    """
    اختبار رد أمانة كسر مكعبات الخرسانة (28 يوم):
    إضافة مبلغ رد الأمانة لإجمالي المستحق والتأكد من صدور قيد اليومية بمدين حساب 21315
    وتوازن القيد المالي بنسبة 100%.
    """
    setup = p5_setup
    contract = setup["contract"]
    admin = setup["admin"]

    # إنشاء مستخلص سابق بحجز أمانة كسر المكعبات وسجل فحص معملي ناجح
    ContractorProgressCertificate.objects.create(
        certificate_number="CERT-P5-CUBE-PREV",
        sequence_order=1,
        contract=contract,
        project=setup["project"],
        contractor=setup["contractor"],
        currency=setup["currency"],
        period_start=date(2025, 12, 1),
        period_end=date(2025, 12, 31),
        gross_certified_work=Decimal("50000.00"),
        pending_cube_test_hold_amount=Decimal("25000.00"),
        status=ContractorProgressCertificate.CertificateStatus.APPROVED,
        created_by=admin
    )
    from real_estate.models import ThirdPartyLabTestLog
    ThirdPartyLabTestLog.objects.create(
        contract=contract,
        lab_name="معمل كلية الهندسة جامعة القاهرة",
        invoice_number="LAB-INV-001",
        test_type="كسر مكعبات خرسانة 28 يوم",
        test_date=date(2026, 1, 15),
        tested_element="أعمدة وسقف الدور الأول",
        is_test_passed=True,
        total_invoice_amount=Decimal("1500.00"),
    )

    # إنشاء مستخلص مسودة يتضمن رد أمانة مكعبات 28 يوم ناجحة بمبلغ 25,000 ج.م
    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-P5-CUBE-01",
        sequence_order=2,
        contract=contract,
        project=setup["project"],
        contractor=setup["contractor"],
        currency=setup["currency"],
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        gross_certified_work=Decimal("100000.00"),
        previous_certified_work=Decimal("0.00"),
        released_cube_test_hold_amount=Decimal("25000.00"),
        retention_rate=Decimal("5.00"),
        advance_payment_recovery=Decimal("0.00"),
        wht_rate=Decimal("1.00"),
        notes="اعتماد الاستشاري لنتائج كسر مكعبات 28 يوم الناجحة",
        status=ContractorProgressCertificate.CertificateStatus.DRAFT,
        created_by=admin
    )

    cert.compute_amounts()
    # current_work = 100,000
    # vat = 5,000 (5%)
    # released_cube = 25,000
    # gross_additions = 100,000 + 5,000 + 25,000 = 130,000
    # retention = 5,000 (5% of 100,000)
    # wht = 1,000 (1% of 100,000)
    # syndicate_stamp = 450 (0.45% of 100,000)
    # site_utilities = 500 (0.50% of 100,000)
    # deductions = 6,950
    # net_amount = 130,000 - 6,950 = 123,050
    assert cert.net_amount == Decimal("123050.00")
    cert.save()

    # تقديم للاعتماد
    submitted_cert = ContractorProgressService.submit_certificate_for_approval(cert, user=admin)
    # اعتماد الطلب
    submitted_cert.approval_request.status = 'APPROVED'
    submitted_cert.approval_request.save()

    # ترحيل القيد لدفتر الأستاذ
    entry = ContractorProgressService.verify_and_post_certificate(submitted_cert, user=admin)
    assert entry is not None

    # التحقق من وجود سطر مدين لحساب أمانات كسر المكعبات (21315) بمبلغ 25,000
    cube_line = entry.lines.filter(account__code="21315").first()
    assert cube_line is not None
    assert cube_line.debit == Decimal("25000.00")
    assert cube_line.credit == Decimal("0.00")

    # التحقق من توازن القيد الكامل
    total_debits = sum(line.debit for line in entry.lines.all())
    total_credits = sum(line.credit for line in entry.lines.all())
    assert total_debits == total_credits


def test_unverified_work_holdback_accounting_posting(p5_setup):
    """
    اختبار توجيه استقطاع الأعمال غير المعتمدة استشارياً لحساب 21318 في القيد المحاسبي
    مع توازن القيد تاماً.
    """
    setup = p5_setup
    contract = setup["contract"]
    admin = setup["admin"]

    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-P5-HOLD-01",
        contract=contract,
        project=setup["project"],
        contractor=setup["contractor"],
        currency=setup["currency"],
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        gross_certified_work=Decimal("150000.00"),
        previous_certified_work=Decimal("0.00"),
        unverified_work_holdback=Decimal("30000.00"),
        retention_rate=Decimal("5.00"),
        advance_payment_recovery=Decimal("0.00"),
        wht_rate=Decimal("1.00"),
        notes="مبرر استشاري معتمد لتسوية أعمال مؤقتة لحين اكتمال RFI",
        status=ContractorProgressCertificate.CertificateStatus.DRAFT,
        created_by=admin
    )
    cert.compute_amounts()
    cert.save()

    submitted_cert = ContractorProgressService.submit_certificate_for_approval(cert, user=admin)
    submitted_cert.approval_request.status = 'APPROVED'
    submitted_cert.approval_request.save()

    entry = ContractorProgressService.verify_and_post_certificate(submitted_cert, user=admin)
    assert entry is not None

    # التحقق من دائنية حساب أمانات أعمال غير معتمدة RFI (21318)
    hold_line = entry.lines.filter(account__code="21318").first()
    assert hold_line is not None
    assert hold_line.credit == Decimal("30000.00")
    assert hold_line.debit == Decimal("0.00")

    # التحقق من توازن القيد المحاسبي
    total_debits = sum(line.debit for line in entry.lines.all())
    total_credits = sum(line.credit for line in entry.lines.all())
    assert total_debits == total_credits


def test_critical_snag_blocker_guard(p5_setup):
    """
    اختبار حارس العيوب الحرجة (Critical Snag Blocker Guard):
    وجود عيوب حرجة مانعة للتسليم مفتوحة على المقاول يمنع تقديم المستخلص للاعتماد
    إلا في حال توثيق مبرر استشاري صريح بالملاحظات.
    """
    setup = p5_setup
    project = setup["project"]
    contract = setup["contract"]
    contractor = setup["contractor"]
    unit = setup["unit"]
    admin = setup["admin"]

    # إنشاء عيب حرج مانع للتسليم مسجل على المقاول
    UnitSnagItem.objects.create(
        snag_code="SNG-P5-BLOCK-01",
        unit=unit,
        contractor=contractor,
        room_location="غرفة النوم الرئيسية",
        severity=UnitSnagItem.SnagSeverity.CRITICAL_BLOCKER,
        status=UnitSnagItem.SnagStatus.OPEN,
        description="تسريب مياه حرج في خط الصرف الداخلي يمنع إنهاء بند البياض والدهانات",
        created_by=admin
    )

    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-P5-SNAG-01",
        contract=contract,
        project=project,
        contractor=contractor,
        currency=setup["currency"],
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        gross_certified_work=Decimal("50000.00"),
        previous_certified_work=Decimal("0.00"),
        notes="طلب صرف جاري اعتيادي",
        status=ContractorProgressCertificate.CertificateStatus.DRAFT,
        created_by=admin
    )

    # محاولة التقديم يجب أن تُرفض مع إشعار رقابي مانع
    with pytest.raises(ValidationError) as exc_info:
        ContractorProgressService.submit_certificate_for_approval(cert, user=admin)
    assert "توجد عيوب حرجة مانعة للتسليم" in str(exc_info.value)

    # عند إضافة اعتماد وتجاوز استشاري رسمي موثق، يُسمح بالتقديم
    cert.consultant_waiver_approved = True
    cert.consultant_waiver_reference = "REF-WAIVER-2026-001"
    cert.notes = "تمت معاينة الاستشاري وتوجد موافقة وتجاوز استشاري معتمد لحين إتمام الإصلاح"
    cert.save()
    submitted_cert = ContractorProgressService.submit_certificate_for_approval(cert, user=admin)
    assert submitted_cert.status == ContractorProgressCertificate.CertificateStatus.PENDING_APPROVAL


def test_snag_conversion_to_backcharge_and_direct_retention_liquidation(p5_setup):
    """
    اختبار جسر تحويل العيب لخصم والتسييل المباشر من رصيد التأمين (21310):
    تحويل ملاحظة العيب المعماري إلى ContractorBackcharge مع تسييل فوري من رصيد تأمين المقاول
    دون الحاجة لوجود مستخلص مفتوح، وتوليد قيد اليومية وإغلاق العيب وتحديث رصيد العقد.
    """
    setup = p5_setup
    contract = setup["contract"]
    contractor = setup["contractor"]
    unit = setup["unit"]
    admin = setup["admin"]

    # رصيد التأمين المتاح قبل التسييل: 80,000 محتجز - 20,000 مفرج = 60,000 متاح
    initial_available = contract.total_retention_retained - contract.total_retention_released
    assert initial_available == Decimal("60000.00")

    snag = UnitSnagItem.objects.create(
        snag_code="SNG-P5-LIQ-01",
        unit=unit,
        contractor=contractor,
        room_location="صالة الاستقبال",
        severity=UnitSnagItem.SnagSeverity.MAJOR,
        status=UnitSnagItem.SnagStatus.OPEN,
        description="تلفيات في أعمال السيراميك بعد تقاعس المقاول عن الإصلاح",
        created_by=admin
    )

    # إنشاء خصم بيني بدون مستخلص (certificate=None)
    backcharge = ContractorBackcharge.objects.create(
        snag_item=snag,
        contractor=contractor,
        contract=contract,
        certificate=None,
        amount=Decimal("15000.00"),
        reason="تكاليف إصلاح ذاتي بواسطة مقاول بديل",
        memo_reference="MEMO-LIQ-01",
        settlement_method=ContractorBackcharge.SettlementMethod.RETENTION_LIQUIDATION,
        is_settled=False
    )

    # تنفيذ التسييل المباشر
    entry = ContractorProgressService.liquidate_backcharge_against_retention(backcharge.id, user=admin)
    assert entry is not None

    # التحقق من قيد اليومية:
    # مدين: تأمينات مقاولي الباطن (21310) = 15,000
    ret_line = entry.lines.filter(account__code="21310").first()
    assert ret_line is not None
    assert ret_line.debit == Decimal("15000.00")
    assert ret_line.credit == Decimal("0.00")

    # دائن: استرداد تكاليف إصلاح العيوب (42201) = 15,000
    rec_line = entry.lines.filter(account__code="42201").first()
    assert rec_line is not None
    assert rec_line.credit == Decimal("15000.00")
    assert rec_line.debit == Decimal("0.00")

    # التحقق من حالة الخصم والعيب
    backcharge.refresh_from_db()
    assert backcharge.is_settled is True
    assert backcharge.settlement_journal_entry == entry

    snag.refresh_from_db()
    assert snag.status == UnitSnagItem.SnagStatus.RESOLVED
    assert "تأمين المقاول" in snag.resolution_notes

    # التحقق من تحديث رصيد التأمين في العقد
    contract.refresh_from_db()
    new_available = contract.total_retention_retained - contract.total_retention_released
    assert new_available == Decimal("45000.00")  # تم تسييل 15,000


def test_absorb_pending_backcharges_workflow(p5_setup):
    """
    اختبار امتصاص محفظة الخصومات المعلقة تلقائياً في أول مسودة مستخلص قادمة
    """
    setup = p5_setup
    contract = setup["contract"]
    contractor = setup["contractor"]
    admin = setup["admin"]

    # إنشاء خصمين معلقين في محفظة المقاول بدون مستخلص
    bc1 = ContractorBackcharge.objects.create(
        contractor=contractor,
        contract=contract,
        certificate=None,
        amount=Decimal("5000.00"),
        reason="تلفيات كهرباء",
        settlement_method=ContractorBackcharge.SettlementMethod.PENDING,
        is_settled=False
    )
    bc2 = ContractorBackcharge.objects.create(
        contractor=contractor,
        contract=contract,
        certificate=None,
        amount=Decimal("3000.00"),
        reason="كسر مواسير صرف",
        settlement_method=ContractorBackcharge.SettlementMethod.PENDING,
        is_settled=False
    )

    # إنشاء مسودة مستخلص جديدة للمقاول
    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-P5-ABSORB-01",
        contract=contract,
        project=setup["project"],
        contractor=contractor,
        currency=setup["currency"],
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        gross_certified_work=Decimal("100000.00"),
        previous_certified_work=Decimal("0.00"),
        status=ContractorProgressCertificate.CertificateStatus.DRAFT,
        created_by=admin
    )

    # تشغيل خدمة الامتصاص
    absorbed_count = ContractorProgressService.absorb_pending_backcharges(cert)
    assert absorbed_count == 2

    # التحقق من ربط الخصمين بالمستخلص
    bc1.refresh_from_db()
    bc2.refresh_from_db()
    assert bc1.certificate == cert
    assert bc2.certificate == cert
    assert bc1.settlement_method == ContractorBackcharge.SettlementMethod.CERTIFICATE

    # التحقق من تحديث إجمالي الخصومات وصافي المستخلص
    cert.refresh_from_db()
    assert cert.total_backcharges == Decimal("8000.00")
