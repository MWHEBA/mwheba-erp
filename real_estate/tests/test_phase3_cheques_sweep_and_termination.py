# -*- coding: utf-8 -*-
"""
Phase 3 Test Suite: Cheques Refund Engine, Sweeper Automation,
Tower Sales Executive Reports & Landowner JV Allocation, and Contract Termination Lifecycle.
"""
import datetime
from decimal import Decimal
import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.utils import timezone

from core.models import SystemModule
from real_estate.models import (
    RealEstateProject, PropertyBlock, PropertyFloor, PropertyUnit, UnitBooking,
    PropertyContract, BookingCancellationSettlement, RefundDisbursementPayment,
    ResaleContingentRefund
)
from real_estate.services.booking_service import UnitBookingService
from real_estate.services.booking_sweep_service import UnitBookingSweepService
from real_estate.services.contract_service import PropertyContractService
from real_estate.services.reporting_service import RealEstateReportingService
from customer.models import Customer
from financial.models import Currency, ChartOfAccounts, AccountType
from cheques.models.cheque import ChequeStatus

User = get_user_model()


@pytest.fixture
def phase3_setup(db):
    SystemModule.objects.update_or_create(
        code='real_estate',
        defaults={'name_ar': 'القطاع العقاري', 'is_enabled': True}
    )

    admin_user = User.objects.create_user(
        username='p3_admin',
        email='p3_admin@test.com',
        password='password123',
        is_staff=True,
        is_superuser=True
    )
    regular_user = User.objects.create_user(
        username='p3_regular',
        email='p3_regular@test.com',
        password='password123',
        is_staff=True
    )

    currency = Currency.objects.filter(is_functional=True).first()
    if not currency:
        currency, _ = Currency.objects.get_or_create(
            code='EGP',
            defaults={
                'name': 'Egyptian Pound',
                'symbol': 'E£',
                'is_functional': True,
                'decimal_places': 2
            }
        )

    asset_type, _ = AccountType.objects.get_or_create(
        code='ASSET',
        defaults={'name': 'Current Asset P3', 'category': 'asset', 'nature': 'debit'}
    )
    liability_type, _ = AccountType.objects.get_or_create(
        code='LIABILITY',
        defaults={'name': 'Current Liability P3', 'category': 'liability', 'nature': 'credit'}
    )
    revenue_type, _ = AccountType.objects.get_or_create(
        code='REVENUE',
        defaults={'name': 'Operating Revenue P3', 'category': 'revenue', 'nature': 'credit'}
    )

    # Required accounts for real estate workflows
    bank_account, _ = ChartOfAccounts.objects.get_or_create(
        code='11120',
        defaults={'name': 'Main Bank P3', 'account_type': asset_type, 'currency': currency, 'is_active': True, 'is_leaf': True}
    )
    treasury_account, _ = ChartOfAccounts.objects.get_or_create(
        code='11110',
        defaults={'name': 'Main Treasury P3', 'account_type': asset_type, 'currency': currency, 'is_active': True, 'is_leaf': True}
    )
    booking_advance_account, _ = ChartOfAccounts.objects.get_or_create(
        code='21101',
        defaults={'name': 'Booking Advances 21101', 'account_type': liability_type, 'currency': currency, 'is_active': True, 'is_leaf': True}
    )
    contract_liability_account, _ = ChartOfAccounts.objects.get_or_create(
        code='21102',
        defaults={'name': 'Contract Liability 21102', 'account_type': liability_type, 'currency': currency, 'is_active': True, 'is_leaf': True}
    )
    penalty_income_account, _ = ChartOfAccounts.objects.get_or_create(
        code='42201',
        defaults={'name': 'Penalty Income 42201', 'account_type': revenue_type, 'currency': currency, 'is_active': True, 'is_leaf': True}
    )
    forfeited_balances_account, _ = ChartOfAccounts.objects.get_or_create(
        code='21701',
        defaults={'name': 'Forfeited Balances 21701', 'account_type': liability_type, 'currency': currency, 'is_active': True, 'is_leaf': True}
    )
    realized_revenue_account, _ = ChartOfAccounts.objects.get_or_create(
        code='41101',
        defaults={'name': 'Realized Revenue 41101', 'account_type': revenue_type, 'currency': currency, 'is_active': True, 'is_leaf': True}
    )
    notes_payable_account, _ = ChartOfAccounts.objects.get_or_create(
        code='21201',
        defaults={'name': 'Notes Payable 21201', 'account_type': liability_type, 'currency': currency, 'is_active': True, 'is_leaf': True}
    )
    notes_payable_ctrl, _ = ChartOfAccounts.objects.get_or_create(
        code='21120',
        defaults={'name': 'Notes Payable Control 21120', 'account_type': liability_type, 'currency': currency, 'is_active': True, 'is_leaf': True}
    )
    notes_receivable_account, _ = ChartOfAccounts.objects.get_or_create(
        code='11220',
        defaults={'name': 'Notes Receivable Control 11220', 'account_type': asset_type, 'currency': currency, 'is_active': True, 'is_leaf': True}
    )
    cheques_under_coll, _ = ChartOfAccounts.objects.get_or_create(
        code='11190',
        defaults={'name': 'Cheques Under Collection 11190', 'account_type': asset_type, 'currency': currency, 'is_active': True, 'is_leaf': True}
    )

    project = RealEstateProject.objects.create(
        code='PRJ-P3-01',
        name='Phase3 Executive Tower',
        start_date=timezone.localdate(),
        expected_completion_date=timezone.localdate() + datetime.timedelta(days=730),
        created_by=admin_user
    )

    block = PropertyBlock.objects.create(
        project=project,
        code='BLK-P3-A',
        name='Tower A'
    )

    floor = PropertyFloor.objects.create(
        block=block,
        floor_number=5,
        name='Fifth Floor'
    )

    unit = PropertyUnit.objects.create(
        project=project,
        block=block,
        floor=floor,
        unit_code='U-501',
        status=PropertyUnit.UnitStatus.AVAILABLE,
        net_area=Decimal('150.00'),
        gross_area=Decimal('175.00'),
        meter_price=Decimal('12000.00'),
        base_price=Decimal('2100000.00'),
        total_price=Decimal('2100000.00')
    )

    customer = Customer.objects.create(
        name='Karim Hany',
        code='CUST-P3-001',
        phone='01234567890'
    )

    return {
        'admin_user': admin_user,
        'regular_user': regular_user,
        'currency': currency,
        'bank_account': bank_account,
        'treasury_account': treasury_account,
        'project': project,
        'block': block,
        'floor': floor,
        'unit': unit,
        'customer': customer,
    }


@pytest.mark.django_db
def test_step3_1_cheque_refund_and_deterministic_idempotency(phase3_setup):
    """
    اختبار صرف استرداد أمانة الحجز بشيك مصرفي مع مفتاح منع تكرار حتمي محكم
    """
    data = phase3_setup
    unit = data['unit']
    customer = data['customer']
    admin = data['admin_user']
    bank_acc = data['bank_account']

    # إنشاء حجز نشط مع تحصيل جدية حجز
    booking = UnitBooking.objects.create(
        booking_number='BKG-P3-CHK-01',
        unit=unit,
        customer=customer,
        booking_date=timezone.localdate(),
        expiry_date=timezone.localdate() + datetime.timedelta(days=7),
        holding_deposit=Decimal('50000.00'),
        currency=data['currency'],
        is_deposit_collected=True,
        status=UnitBooking.BookingStatus.CANCELLED_PENDING_REFUND,
        created_by=admin
    )

    # صرف الاسترداد بشيك مصرفي
    cheque_info = {
        'cheque_number': 'CHQ-998877',
        'due_date': timezone.localdate() + datetime.timedelta(days=30),
        'drawer_bank_name': 'National Bank of Egypt',
        'payee_name': customer.name,
    }

    refunded_booking = UnitBookingService.process_booking_refund(
        booking_id=booking.id,
        payment_account=bank_acc,
        method=RefundDisbursementPayment.DisbursementMethod.CHEQUE,
        cheque_data=cheque_info,
        user=admin
    )

    assert refunded_booking.status == UnitBooking.BookingStatus.CANCELLED_REFUNDED
    settlement = refunded_booking.active_cancellation_settlement
    assert settlement is not None
    assert settlement.remaining_disbursable_amount == Decimal('0.00')

    # التحقق من تسجيل سند الصرف والشيك
    disbursement = settlement.disbursements.first()
    assert disbursement is not None
    assert disbursement.method == RefundDisbursementPayment.DisbursementMethod.CHEQUE
    assert disbursement.idempotency_key == f"REFUND-SETTLE-{settlement.id}"
    assert disbursement.cheque is not None
    assert disbursement.cheque.cheque_number == 'CHQ-998877'
    assert disbursement.cheque.status == ChequeStatus.ISSUED

    # اختبار Idempotency: إعادة الاستدعاء بنفس المعلمات يجب ألا يكرر القيد أو ينشئ شيكاً جديداً
    refund_again = UnitBookingService.process_booking_refund(
        booking_id=booking.id,
        payment_account=bank_acc,
        method=RefundDisbursementPayment.DisbursementMethod.CHEQUE,
        cheque_data=cheque_info,
        user=admin
    )
    assert refund_again.status == UnitBooking.BookingStatus.CANCELLED_REFUNDED
    assert settlement.disbursements.count() == 1


@pytest.mark.django_db
def test_step3_1_booking_cancellation_with_deduction_fee(phase3_setup):
    """
    اختبار إلغاء استمارة الحجز مع خصم مصاريف إدارية معتمدة وترحيل قيد المصادرة الجزئية
    """
    data = phase3_setup
    unit = data['unit']
    customer = data['customer']
    admin = data['admin_user']

    unit.status = PropertyUnit.UnitStatus.RESERVED
    unit.save()

    booking = UnitBooking.objects.create(
        booking_number='BKG-P3-DED-01',
        unit=unit,
        customer=customer,
        booking_date=timezone.localdate(),
        expiry_date=timezone.localdate() + datetime.timedelta(days=7),
        holding_deposit=Decimal('40000.00'),
        currency=data['currency'],
        is_deposit_collected=True,
        status=UnitBooking.BookingStatus.ACTIVE,
        created_by=admin
    )
    unit.current_booking = booking
    unit.save()

    deduction_fee = Decimal('5000.00')

    # إلغاء الحجز مع خصم 5000 مصاريف إدارية
    cancelled_bkg = UnitBookingService.cancel_booking(
        booking_id=booking.id,
        reason='انسحاب العميل لظروف خاصة',
        forfeit_deposit=False,
        approved_deduction_fees=deduction_fee,
        user=admin
    )

    assert cancelled_bkg.status == UnitBooking.BookingStatus.CANCELLED_PENDING_REFUND
    unit.refresh_from_db()
    assert unit.status == PropertyUnit.UnitStatus.AVAILABLE
    assert unit.current_booking is None

    settlement = cancelled_bkg.active_cancellation_settlement
    assert settlement is not None
    assert settlement.approved_deduction_fees == deduction_fee
    assert settlement.net_refundable_amount == Decimal('35000.00')
    assert settlement.remaining_disbursable_amount == Decimal('35000.00')
    assert settlement.forfeiture_journal_entry is not None


@pytest.mark.django_db
def test_step3_2_sweeper_creates_settlement_and_deduction(phase3_setup):
    """
    اختبار محرك كنس الحجوزات المنتهية (UnitBookingSweepService):
    تحرير الوحدة آلياً وإنشاء قرار تسوية مع المصاريف الإدارية
    """
    data = phase3_setup
    unit = data['unit']
    customer = data['customer']
    admin = data['admin_user']
    project = data['project']

    # تعيين مصاريف إدارية افتراضية للمشروع
    project.default_cancellation_fee = Decimal('3000.00')
    project.save()

    unit.status = PropertyUnit.UnitStatus.RESERVED
    unit.save()

    expired_date = timezone.localdate() - datetime.timedelta(days=2)
    expired_booking = UnitBooking.objects.create(
        booking_number='BKG-P3-SWEEP-01',
        unit=unit,
        customer=customer,
        booking_date=expired_date - datetime.timedelta(days=7),
        expiry_date=expired_date,
        holding_deposit=Decimal('25000.00'),
        currency=data['currency'],
        is_deposit_collected=True,
        status=UnitBooking.BookingStatus.ACTIVE,
        created_by=admin
    )
    unit.current_booking = expired_booking
    unit.save()

    # تشغيل محرك الكنس
    swept_count = UnitBookingSweepService.sweep_expired_bookings(as_of_date=timezone.localdate())
    assert swept_count == 1

    expired_booking.refresh_from_db()
    unit.refresh_from_db()

    assert unit.status == PropertyUnit.UnitStatus.AVAILABLE
    assert unit.current_booking is None
    assert expired_booking.status == UnitBooking.BookingStatus.CANCELLED_PENDING_REFUND

    settlement = expired_booking.active_cancellation_settlement
    assert settlement is not None
    assert settlement.approved_deduction_fees == Decimal('3000.00')
    assert settlement.net_refundable_amount == Decimal('22000.00')
    assert settlement.remaining_disbursable_amount == Decimal('22000.00')
    assert settlement.cancellation_reason == 'ADMIN_EXPIRY_SWEEP'


@pytest.mark.django_db
def test_step3_3_tower_sales_report_permission_and_landowner_jv(phase3_setup, client):
    """
    اختبار حراسة الصلاحيات التنفيذية وحساب تخصيص مالك الأرض (Landowner JV Allocation)
    """
    data = phase3_setup
    project = data['project']
    block = data['block']
    floor = data['floor']
    admin = data['admin_user']
    regular_user = data['regular_user']

    # إنشاء وحدة مخصصة لمالك الأرض
    landowner_unit = PropertyUnit.objects.create(
        project=project,
        block=block,
        floor=floor,
        unit_code='U-502-LO',
        status=PropertyUnit.UnitStatus.LANDOWNER_ALLOCATED,
        net_area=Decimal('160.00'),
        gross_area=Decimal('190.00'),
        meter_price=Decimal('12000.00'),
        base_price=Decimal('2280000.00'),
        total_price=Decimal('2280000.00')
    )

    # 1. فحص الحساب في الخدمة البرمجية
    report_data = RealEstateReportingService.get_tower_sales_brief_report(project_id=project.id)
    assert 'landowner_jv' in report_data
    jv = report_data['landowner_jv']
    assert jv['landowner_count'] == 1
    assert jv['landowner_area'] == Decimal('190.00')
    assert jv['landowner_value'] == Decimal('2280000.00')
    assert jv['company_count'] == 1  # Unit U-501 is company unit

    # 2. فحص حراسة الصلاحيات عبر العرض (View Permission Guard)
    url = reverse('real_estate:report_tower_sales_brief')

    # المستخدم العادي بدون صلاحية view_executive_reports يحصل على 403
    client.force_login(regular_user)
    resp_forbidden = client.get(url)
    assert resp_forbidden.status_code == 403

    # مستخدم بصلاحية view_executive_reports أو Superuser يحصل على 200
    client.force_login(admin)
    resp_ok = client.get(url)
    assert resp_ok.status_code == 200
    assert 'تخصيص ومحفظة حصة مالك الأرض' in resp_ok.content.decode('utf-8')


@pytest.mark.django_db
def test_step3_4_booking_recovery_list_view(phase3_setup, client):
    """
    اختبار شاشة سجل تسويات واسترداد الحجوزات (Booking Recovery List) ومؤشرات الـ KPI
    """
    data = phase3_setup
    admin = data['admin_user']
    unit = data['unit']
    customer = data['customer']

    booking = UnitBooking.objects.create(
        booking_number='BKG-P3-REC-01',
        unit=unit,
        customer=customer,
        booking_date=timezone.localdate(),
        expiry_date=timezone.localdate() + datetime.timedelta(days=7),
        holding_deposit=Decimal('30000.00'),
        is_deposit_collected=True,
        status=UnitBooking.BookingStatus.CANCELLED_PENDING_REFUND,
        created_by=admin
    )
    settlement = BookingCancellationSettlement.objects.create(
        booking=booking,
        currency=data['currency'],
        exchange_rate=Decimal('1.000000'),
        total_deposit_paid=Decimal('30000.00'),
        approved_deduction_fees=Decimal('2000.00'),
        net_refundable_amount=Decimal('28000.00'),
        remaining_disbursable_amount=Decimal('28000.00'),
        cancellation_reason='CUSTOMER_REQUEST',
        processed_by=admin
    )
    booking.active_cancellation_settlement = settlement
    booking.save()

    client.force_login(admin)
    url = reverse('real_estate:booking_recovery_list')
    resp = client.get(url)
    assert resp.status_code == 200
    content = resp.content.decode('utf-8')
    assert 'سجل تسويات واسترداد الحجوزات' in content
    assert settlement.settlement_number in content
    assert '30,000' in content
    assert '28,000' in content


@pytest.mark.django_db
def test_step3_5_contract_termination_and_resale_lifecycle(phase3_setup, client):
    """
    اختبار دورة فسخ العقد وإعادة طرح الوحدة للبيع (Contract Rescission & Resale Lifecycle):
    إلغاء الأقساط، ترحيل قيد الفسخ، إنشاء مستحق رد معلق لإعادة الطرح، وتحرير الوحدة
    """
    data = phase3_setup
    admin = data['admin_user']
    unit = data['unit']
    customer = data['customer']

    unit.status = PropertyUnit.UnitStatus.CONTRACTED
    unit.save()

    contract = PropertyContract.objects.create(
        contract_number='CNT-P3-TERM-01',
        project=data['project'],
        unit=unit,
        customer=customer,
        contract_date=timezone.localdate(),
        delivery_date=timezone.localdate() + datetime.timedelta(days=730),
        final_contract_price=Decimal('2100000.00'),
        down_payment=Decimal('300000.00'),
        currency=data['currency'],
        exchange_rate=Decimal('1.000000'),
        status=PropertyContract.ContractStatus.ACTIVE,
        created_by=admin
    )

    # تنفيذ فسخ العقد بغرامة 50000 جنيه وتعليق المستحق لحين إعادة الطرح
    res = PropertyContractService.terminate_contract(
        contract_id=contract.id,
        reason='تعثر مالي للعميل وطلب فسخ رسمي',
        penalty_amount=Decimal('50000.00'),
        refund_now=False,
        user=admin
    )

    contract.refresh_from_db()
    unit.refresh_from_db()

    assert contract.status == PropertyContract.ContractStatus.TERMINATED
    assert unit.status == PropertyUnit.UnitStatus.AVAILABLE

    # التحقق من مستحق الرد المعلق لإعادة الطرح (ResaleContingentRefund)
    refund_record = res['refund_record']
    assert refund_record is not None
    assert refund_record.total_paid_before_cancellation == Decimal('300000.00')
    assert refund_record.cancellation_penalty_amount == Decimal('50000.00')
    assert refund_record.net_refundable_amount == Decimal('250000.00')
    assert refund_record.status == ResaleContingentRefund.RefundStatus.PENDING_RESALE

    # التحقق من قيد فسخ العقد
    cancel_entry = res['journal_entry']
    assert cancel_entry is not None

    # فحص شاشة تفاصيل العقد لعرض بطاقة المستحقات المعلقة
    client.force_login(admin)
    detail_url = reverse('real_estate:contract_detail', kwargs={'pk': contract.pk})
    resp = client.get(detail_url)
    assert resp.status_code == 200
    assert 'مستحقات فسخ معلقة لإعادة الطرح' in resp.content.decode('utf-8')
    assert refund_record.refund_number in resp.content.decode('utf-8')
