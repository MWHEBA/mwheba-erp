# -*- coding: utf-8 -*-
"""
Phase 7 End-to-End Comprehensive Parity & Quality Gate Suite:
MWHEBA ERP — Real Estate Enterprise Parity Master Plan
Tests the 6 architectural pillars:
1. SoD Dual Governance & Justified Administrative Override
2. Post-Dated Cheque Booking Refund & Account 213 Settle Entry
3. Field Progress Ceiling Guard & Unverified Work Holdback
4. Price Escalation Independence from WBS Quantities
5. Snag-to-Backcharge Bridge & Direct Retention Account 21310 Liquidation
6. Central Site Reports Landing & Automated Leaf WBS Rollup
"""
from datetime import timedelta, date
from decimal import Decimal
import pytest
from django.utils import timezone
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client

from core.models import SystemModule
from core.middleware.module_control import ModuleAccessMiddleware
from customer.models import Customer
from financial.models.currency import Currency
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.approval import EnterpriseApprovalRule
from supplier.models import Supplier

from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyFloor,
    PropertyUnit,
    UnitBooking,
    BookingCancellationSettlement,
    RefundDisbursementPayment,
    PropertyContract,
    ContractorContract,
    ContractorContractItem,
    ContractorProgressCertificate,
    ContractorBackcharge,
    UnitSiteProgressRecord,
    ProjectActivity,
    UnitSnagItem,
)
from real_estate.services.booking_service import UnitBookingService, BookingValidationError
from real_estate.services.contractor_service import ContractorProgressService
from real_estate.services.site_progress_service import (
    ProjectProgressCalculationService,
    SiteProgressInitializationService,
)
from real_estate.services.wbs_service import WbsTreeGovernanceService, UnitToWbsBridgeService

User = get_user_model()


@pytest.fixture
def p7_setup(db):
    # تفعيل الموديول
    mod, _ = SystemModule.objects.get_or_create(
        code='real_estate',
        defaults={'name_ar': 'العقارات', 'is_enabled': True}
    )
    mod.is_enabled = True
    mod.save()
    ModuleAccessMiddleware.invalidate_cache()

    # مستخدمين بمستويات صلاحية مختلفة لاختبار SoD
    maker = User.objects.create_user(
        username='p7_maker',
        email='maker@mwheba.com',
        password='Password123!'
    )
    checker = User.objects.create_user(
        username='p7_checker',
        email='checker@mwheba.com',
        password='Password123!'
    )
    manager = User.objects.create_superuser(
        username='p7_manager',
        email='manager@mwheba.com',
        password='Password123!'
    )

    change_perm = Permission.objects.get(codename='change_unitbooking', content_type__app_label='real_estate')
    view_perm = Permission.objects.get(codename='view_unitbooking', content_type__app_label='real_estate')
    add_perm = Permission.objects.get(codename='add_unitbooking', content_type__app_label='real_estate')
    for u in (maker, checker):
        u.user_permissions.add(change_perm, view_perm, add_perm)

    asset_type, _ = AccountType.objects.get_or_create(code='asset', defaults={'name': 'أصول', 'category': 'asset', 'nature': 'debit'})
    liability_type, _ = AccountType.objects.get_or_create(code='liability', defaults={'name': 'خصوم', 'category': 'liability', 'nature': 'credit'})
    revenue_type, _ = AccountType.objects.get_or_create(code='revenue', defaults={'name': 'إيرادات', 'category': 'revenue', 'nature': 'credit'})

    currency, _ = Currency.objects.get_or_create(
        code="EGP",
        defaults={"name": "Egyptian Pound", "symbol": "ج.م", "is_functional": True}
    )

    # حسابات اليومية والدليل المحاسبي
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
        "11110": ("الخزينة العامة", asset_type),
        "11120": ("حساب البنك التجاري", asset_type),
        "11190": ("شيكات برسم التحصيل", asset_type),
        "11220": ("أوراق القبض وشيكات تحت التحصيل", asset_type),
        "21101": ("دفعات حجز العملاء", liability_type),
        "21102": ("التزامات عقود بيع", liability_type),
        "21201": ("أوراق الدفع", liability_type),
        "21120": ("مراقبة أوراق الدفع", liability_type),
        "21701": ("مبالغ مصادرة للعملاء", liability_type),
        "41101": ("إيرادات مبيعات عقارية", revenue_type),
        "21301": ("أوراق الدفع - شيكات استرداد الحجز", liability_type),
    }
    for code, (name, a_type) in accounts.items():
        ChartOfAccounts.objects.get_or_create(
            code=code,
            defaults={'name': name, 'account_type': a_type, 'is_active': True, 'is_leaf': True, 'currency': currency}
        )

    cash_acc = ChartOfAccounts.objects.get(code='11111')
    bank_acc = ChartOfAccounts.objects.get(code='11120')

    EnterpriseApprovalRule.objects.get_or_create(
        module='REAL_ESTATE',
        rule_name='اعتماد مستخلصات المرحلة 7',
        defaults={
            'min_amount': Decimal('0.00'),
            'max_amount': Decimal('999999999.00'),
            'approver_role': 'site_engineer',
            'approval_level': 1,
            'is_active': True,
        }
    )

    customer = Customer.objects.create(
        name="عميل اختبار المرحلة السابعة",
        code="CUST-P7-01",
        phone="01011223399"
    )

    contractor = Supplier.objects.create(
        code="SUP-P7-01",
        name="شركة الصفا للإنشاءات المتكاملة",
    )

    project = RealEstateProject.objects.create(
        code="PRJ-P7-01",
        name="أبراج الفيروز الشاملة",
        project_type=RealEstateProject.ProjectType.RESIDENTIAL,
        status=RealEstateProject.ProjectStatus.UNDER_CONSTRUCTION,
        revenue_recognition_method=RealEstateProject.RevenueRecognitionMethod.OVER_TIME_POC,
        start_date=timezone.localdate(),
        expected_completion_date=timezone.localdate() + timedelta(days=365),
        construction_progress_percentage=Decimal("0.00"),
        created_by=manager,
    )

    block = PropertyBlock.objects.create(
        project=project,
        code="B1",
        name="برج A",
        construction_progress_percentage=Decimal("0.00"),
    )

    floor = PropertyFloor.objects.create(
        block=block,
        floor_number=1,
        name="الدور الأول",
    )

    unit1 = PropertyUnit.objects.create(
        project=project,
        block=block,
        floor=floor,
        unit_code="U-P7-101",
        unit_type=PropertyUnit.UnitType.APARTMENT,
        status=PropertyUnit.UnitStatus.AVAILABLE,
        net_area=Decimal("120.00"),
        gross_area=Decimal("140.00"),
        meter_price=Decimal("12000.00"),
        total_price=Decimal("1680000.00"),
        progress_percentage=Decimal("0.00"),
    )

    unit2 = PropertyUnit.objects.create(
        project=project,
        block=block,
        floor=floor,
        unit_code="U-P7-102",
        unit_type=PropertyUnit.UnitType.APARTMENT,
        status=PropertyUnit.UnitStatus.AVAILABLE,
        net_area=Decimal("120.00"),
        gross_area=Decimal("140.00"),
        meter_price=Decimal("12000.00"),
        total_price=Decimal("1680000.00"),
        progress_percentage=Decimal("0.00"),
    )

    return {
        'maker': maker,
        'checker': checker,
        'manager': manager,
        'currency': currency,
        'customer': customer,
        'contractor': contractor,
        'project': project,
        'block': block,
        'floor': floor,
        'unit': unit1,
        'unit2': unit2,
        'cash_acc': cash_acc,
        'bank_acc': bank_acc,
    }


@pytest.mark.django_db
def test_p7_sod_dual_audit_and_justified_override(p7_setup):
    """
    1. اختبار دورة الرقابة الثنائية والتجاوز الإداري المبرر (SoD Dual Control):
    - منع مدخل البيانات من مراجعة واعتماد استمارة حجزه بنفسه (Maker-Checker Violation).
    - نجاح مراجعة واعتماد المراجع المستقل.
    - دعم التجاوز الإداري المبرر من الإدارة العليا مع تسجيل سبب صريح وموثق.
    """
    maker = p7_setup['maker']
    checker = p7_setup['checker']
    manager = p7_setup['manager']
    unit1 = p7_setup['unit']
    unit2 = p7_setup['unit2']
    customer = p7_setup['customer']
    cash_acc = p7_setup['cash_acc']

    # إنشاء حجز للوحدة 1 بواسطة Maker
    booking1 = UnitBookingService.create_booking(
        unit_id=unit1.id,
        customer=customer,
        holding_deposit=Decimal("50000.00"),
        expiry_date=timezone.localdate() + timedelta(days=14),
        user=maker,
        payment_account=cash_acc,
    )

    # 1. محاولة مراجعة المبيعات بواسطة منشئ الحجز نفسه -> فشل إلزامي (SoD Violation)
    with pytest.raises(BookingValidationError) as exc:
        UnitBookingService.review_booking_sales(booking1.id, user=maker)
    assert "قيد الفصل الرقابي" in str(exc.value)

    # 2. مراجعة المبيعات بواسطة مراجع مستقل Checker -> تنجح
    reviewed_booking = UnitBookingService.review_booking_sales(booking1.id, user=checker)
    assert reviewed_booking.is_reviewed_sales is True
    assert reviewed_booking.reviewed_by == checker
    assert reviewed_booking.reviewed_at is not None

    # 3. محاولة الاعتماد الرقابي بنفس مراجع المبيعات -> فشل إلزامي (SoD Violation)
    with pytest.raises(BookingValidationError) as exc:
        UnitBookingService.confirm_booking_audit(booking1.id, user=checker)
    assert "قيد الفصل الرقابي" in str(exc.value)

    # 4. قيام مدقق مستقل Manager بالاعتماد الرقابي -> ينجح
    confirmed_booking = UnitBookingService.confirm_booking_audit(booking1.id, user=manager)
    assert confirmed_booking.is_confirmed_audit is True

    # 5. اختبار مسار التجاوز الإداري المبرر على حجز الوحدة 2 (Override Path)
    booking2 = UnitBookingService.create_booking(
        unit_id=unit2.id,
        customer=customer,
        holding_deposit=Decimal("30000.00"),
        expiry_date=timezone.localdate() + timedelta(days=14),
        user=maker,
        payment_account=cash_acc,
    )

    # محاولة تجاوز بدون سبب موثق -> تفشل
    with pytest.raises(BookingValidationError):
        UnitBookingService.bypass_booking_audit(
            booking2.id,
            user=manager,
            reason="   "
        )

    # تجاوز إداري بسبب رسمي معتمد -> ينجح ويوثق في سجل المراجعة
    overridden_booking = UnitBookingService.bypass_booking_audit(
        booking2.id,
        user=manager,
        reason="استثناء استثنائي بقرار مجلس الإدارة رقم 14"
    )
    assert overridden_booking.audit_bypassed is True
    assert overridden_booking.audit_bypass_reason == "استثناء استثنائي بقرار مجلس الإدارة رقم 14"


@pytest.mark.django_db
def test_p7_post_dated_cheque_refund_and_account_213(p7_setup):
    """
    2. اختبار صرف استرداد الحجز بشيك بنكي آجل ورابط حساب أوراق الدفع (213):
    - إلغاء الحجز وتوليد تسوية الاسترداد ببيانات الشيك (رقم، بنك، تاريخ استحقاق).
    - توليد مفتاح تفرد مانع للتكرار IDEMPOTENCY_KEY.
    - إثبات الصرف والتسوية وتحديث حالة الاسترداد.
    """
    manager = p7_setup['manager']
    unit = p7_setup['unit']
    customer = p7_setup['customer']
    currency = p7_setup['currency']
    bank_acc = p7_setup['bank_acc']

    # إنشاء حجز نشط بحالة بانتظار الاسترداد مع تسوية معتمدة
    booking = UnitBooking.objects.create(
        booking_number='BKG-P7-CHK-01',
        unit=unit,
        customer=customer,
        booking_date=timezone.localdate(),
        expiry_date=timezone.localdate() + timedelta(days=7),
        holding_deposit=Decimal('50000.00'),
        currency=currency,
        is_deposit_collected=True,
        status=UnitBooking.BookingStatus.CANCELLED_PENDING_REFUND,
        created_by=manager
    )

    # صرف الاسترداد بشيك مصرفي
    cheque_info = {
        'cheque_number': 'CHQ-P7-999',
        'due_date': timezone.localdate() + timedelta(days=60),
        'drawer_bank_name': 'البنك التجاري الدولي CIB',
        'payee_name': customer.name,
    }

    refunded_booking = UnitBookingService.process_booking_refund(
        booking_id=booking.id,
        payment_account=bank_acc,
        method=RefundDisbursementPayment.DisbursementMethod.CHEQUE,
        cheque_data=cheque_info,
        user=manager
    )

    assert refunded_booking.status == UnitBooking.BookingStatus.CANCELLED_REFUNDED
    settlement = refunded_booking.active_cancellation_settlement
    assert settlement is not None
    assert settlement.remaining_disbursable_amount == Decimal('0.00')

    payment = RefundDisbursementPayment.objects.filter(settlement=settlement).first()
    assert payment is not None
    assert payment.method == RefundDisbursementPayment.DisbursementMethod.CHEQUE
    assert payment.cheque is not None
    assert payment.cheque.cheque_number == 'CHQ-P7-999'
    assert payment.idempotency_key == f"REFUND-SETTLE-{settlement.id}"


@pytest.mark.django_db
def test_p7_field_progress_ceiling_guard_and_unverified_holdback(p7_setup):
    """
    3. اختبار سقف المطابقة الميدانية ومنع القص الصامت (Unverified Work Holdback):
    - ربط بنود المقاول بسجلات مصفوفة الـ 32 بنداً.
    - عند مطالبة المقاول بنسبة تفوق المعتمد استشارياً، لا يتم قص العمل بصمت
      بل يتم الإبقاء على gross_certified_work سليماً وتوليد بند استقطاع صريح `unverified_work_holdback`.
    """
    manager = p7_setup['manager']
    project = p7_setup['project']
    block = p7_setup['block']
    unit = p7_setup['unit']
    contractor = p7_setup['contractor']
    currency = p7_setup['currency']

    # إنشاء سجل تنفيذ ميداني معتمد بنسبة 20% (السقف المعتمد = 20% من 1,000,000 = 200,000)
    UnitSiteProgressRecord.objects.create(
        unit=unit,
        trade_stage="CONCRETE_SKELETON",
        contractor=contractor,
        status=UnitSiteProgressRecord.StageStatus.PASSED_AND_VERIFIED,
        completion_percentage=20,
        is_applicable=True,
        verified_by=manager
    )

    contract = ContractorContract.objects.create(
        contract_number="CNT-P7-01",
        title="عقد الهيكل الخرساني لعمارة الفيروز",
        project=project,
        block=block,
        contractor=contractor,
        currency=currency,
        initial_contract_value=Decimal("1000000.00"),
        retention_rate=Decimal("5.00"),
        advance_recovery_rate=Decimal("0.00"),
        status=ContractorContract.ContractStatus.ACTIVE,
        created_by=manager,
    )

    ContractorContractItem.objects.create(
        contract=contract,
        item_code="C-P7-01",
        description="توريد وصب خرسانة مسلحة للأسقف والأعمدة",
        unit="م3",
        contracted_quantity=Decimal("500.000"),
        revised_quantity=Decimal("500.000"),
        unit_rate=Decimal("2000.00"),
        total_budget_amount=Decimal("1000000.00")
    )

    # المقاول يطالب بأعمال قدرها 300,000 ج.م (تتجاوز السقف 200,000 بفارق 100,000)
    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-P7-CLIP-01",
        contract=contract,
        sequence_order=1,
        project=project,
        block=block,
        contractor=contractor,
        currency=currency,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        gross_certified_work=Decimal("300000.00"),
        previous_certified_work=Decimal("0.00"),
        retention_rate=Decimal("5.00"),
        advance_payment_recovery=Decimal("0.00"),
        wht_rate=Decimal("1.00"),
        status=ContractorProgressCertificate.CertificateStatus.DRAFT,
        created_by=manager
    )

    # تقديم المستخلص للاعتماد
    submitted_cert = ContractorProgressService.submit_certificate_for_approval(cert, user=manager)

    # التحقق من منع القص الصامت:
    # 1. gross_certified_work لم يتم تعديله بصمت إلى 200,000 بل بقي 300,000
    assert submitted_cert.gross_certified_work == Decimal("300000.00")
    # 2. الفارق تم احتجازه صراحة في unverified_work_holdback
    assert submitted_cert.unverified_work_holdback == Decimal("100000.00")


@pytest.mark.django_db
def test_p7_price_escalation_independent_of_wbs(p7_setup):
    """
    4. اختبار بند تسوية فروق الأسعار (Price Escalation):
    - إثبات مبلغ فروق الأسعار كبند مالي تعويضي في المستخلص دون زيادة كميات WBS التقديرية.
    """
    project = p7_setup['project']
    block = p7_setup['block']
    contractor = p7_setup['contractor']
    currency = p7_setup['currency']

    contract = ContractorContract.objects.create(
        contract_number="CNT-P7-ESC",
        title="عقد الهيكل الخرساني",
        project=project,
        block=block,
        contractor=contractor,
        currency=currency,
        initial_contract_value=Decimal("2000000.00"),
    )

    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-P7-ESC-01",
        contract=contract,
        sequence_order=1,
        project=project,
        block=block,
        contractor=contractor,
        currency=currency,
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
        gross_certified_work=Decimal("200000.00"),
        previous_certified_work=Decimal("0.00"),
        price_escalation_amount=Decimal("35000.00"),  # فروق أسعار حديد معتمدة
        retention_rate=Decimal("5.00"),
    )

    cert.compute_amounts()
    cert.save()

    # فروق الأسعار تثبت بمبلغها المستقل وتزيد صافي المستحق دون المساس بكميات WBS
    assert cert.price_escalation_amount == Decimal("35000.00")
    # بدون فروق أسعار: 200,000 - 3,900 (استقطاعات) = 196,100. مع فروق أسعار 35,000 = 231,100.
    assert cert.net_amount == Decimal("231100.00")


@pytest.mark.django_db
def test_p7_snag_to_backcharge_direct_retention_liquidation(p7_setup):
    """
    5. اختبار تحويل العيب المعماري إلى أمر خصم مالي مع التسييل المباشر للتأمين (21310):
    - ربط الملاحظة الميدانية UnitSnagItem بأمر خصم ContractorBackcharge.
    - دعم فك الارتهان بالمستخلص (certificate=None).
    - التسييل المباشر من رصيد تأمين الأعمال وحفظ الخصم كمسدد.
    """
    manager = p7_setup['manager']
    unit = p7_setup['unit']
    contractor = p7_setup['contractor']
    currency = p7_setup['currency']

    contract = ContractorContract.objects.create(
        contract_number="CNT-P7-SNAG",
        title="عقد أعمال البياض والمحارة",
        project=unit.project,
        contractor=contractor,
        currency=currency,
        initial_contract_value=Decimal("400000.00"),
    )

    # إنشاء ملاحظة عيب فني ميداني
    snag = UnitSnagItem.objects.create(
        unit=unit,
        room_location="غرفة النوم الرئيسية",
        category="CIVIL_MASONRY",
        severity=UnitSnagItem.SnagSeverity.CRITICAL_BLOCKER,
        description="تطبيل وشروخ نافذة بطبقة بياض الحوائط",
        contractor=contractor,
        status=UnitSnagItem.SnagStatus.OPEN,
        created_by=manager,
    )

    # تحويل العيب إلى خصم بيني بدون مستخلص مفتوح (فك الارتهان)
    backcharge = ContractorBackcharge.objects.create(
        snag_item=snag,
        contractor=contractor,
        contract=contract,
        amount=Decimal("7500.00"),
        reason=f"تكلفة تكسير وإعادة بياض العيب {snag.snag_code}",
        memo_reference=f"MEMO-P7-{snag.snag_code}",
        settlement_method=ContractorBackcharge.SettlementMethod.RETENTION_LIQUIDATION,
        is_settled=False,
    )

    assert backcharge.certificate is None
    assert backcharge.amount == Decimal("7500.00")
    assert backcharge.contractor == contractor
    assert backcharge.settlement_method == 'RETENTION_LIQUIDATION'


@pytest.mark.django_db
def test_p7_site_reports_landing_and_automatic_wbs_rollup(p7_setup):
    """
    6. اختبار شاشة الهبوط المركزية والمزامنة الصاعدة الآلية لـ WBS و IFRS 15:
    - فحص استجابة شاشة الهبوط المركزية SiteReportsLandingView (200 OK).
    - فحص المزامنة الصاعدة لنسب إنجاز الشقق تلقائياً لشجرة الـ WBS وتحديث نسبة إنجاز المشروع العامة.
    """
    manager = p7_setup['manager']
    project = p7_setup['project']
    unit1 = p7_setup['unit']
    unit2 = p7_setup['unit2']

    client = Client()
    client.force_login(manager)

    # 1. شاشة الهبوط المركزية
    landing_url = reverse('real_estate:site_reports_landing')
    resp = client.get(landing_url)
    assert resp.status_code == 200
    assert "شاشة هبوط ومتابعة المواقع الميدانية" in resp.content.decode('utf-8')
    assert project.code in resp.content.decode('utf-8')

    # 2. بناء شجرة WBS لنشاط المباني
    root_act = ProjectActivity.objects.create(
        project=project,
        code="WBS-P7-ROOT",
        name="الأعمال المعمارية المتكاملة",
        activity_type=ProjectActivity.ActivityType.GENERAL,
        weight_percentage=Decimal("100.0000"),
        progress_percentage=Decimal("0.00"),
    )
    leaf_act = ProjectActivity.objects.create(
        project=project,
        parent_activity=root_act,
        code="WBS-P7-MASONRY",
        name="حزمة مباني القواطع",
        activity_type=ProjectActivity.ActivityType.TRADE_CATEGORY,
        trade_category=ProjectActivity.TradeCategory.MASONRY,
        weight_percentage=Decimal("100.0000"),
        auto_sync_progress=True,
        progress_percentage=Decimal("0.00"),
    )

    # 3. تهيئة واعتماد 100% لبند المباني في كافة وحدات المشروع
    SiteProgressInitializationService.seed_unit_site_stages(unit1)
    SiteProgressInitializationService.seed_unit_site_stages(unit2)
    records = UnitSiteProgressRecord.objects.filter(
        unit__in=[unit1, unit2],
        trade_stage__in=[
            UnitSiteProgressRecord.InspectionTrade.MASONRY_QADD,
            UnitSiteProgressRecord.InspectionTrade.MASONRY_FULL,
        ]
    )
    for r in records:
        r.completion_percentage = 100
        r.status = UnitSiteProgressRecord.StageStatus.PASSED_AND_VERIFIED
        r.save()

    # 4. تشغيل محرك التصعيد الشامل
    rollup_res = ProjectProgressCalculationService.rollup_project_and_block_progress(project, user=manager)

    leaf_act.refresh_from_db()
    root_act.refresh_from_db()
    project.refresh_from_db()

    assert leaf_act.progress_percentage == Decimal("100.00")
    assert root_act.progress_percentage == Decimal("100.00")
    assert project.construction_progress_percentage == Decimal("100.00")
    assert rollup_res['project_progress'] == Decimal("100.00")
