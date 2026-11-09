# -*- coding: utf-8 -*-
"""
Tests for Track 4 Slice 2: Services, Central Accounting & Two-Way Lifecycle Sync
"""
import uuid
from decimal import Decimal
from datetime import timedelta
import pytest
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyFloor,
    PropertyUnit,
    UnitBooking,
    PropertyContract,
    ContractCoOwner,
    BookingCancellationSettlement,
    RefundDisbursementPayment,
)
from customer.models import Customer
from financial.models import Currency, ChartOfAccounts, AccountType, ExchangeRate
from cheques.models import Cheque, ChequeType, ChequeStatus, ChequePurpose, ChequeActionType
from cheques.services.accounting_service import ChequeAccountingService
from real_estate.services.booking_service import UnitBookingService, BookingValidationError
from real_estate.services.contract_service import PropertyContractService
from real_estate.services.booking_sweep_service import UnitBookingSweepService
from real_estate.services.accounting_service import RealEstateAccountingService
from real_estate.services.meta_whatsapp_payload_builder import MetaWhatsAppPayloadBuilder
from financial.services.exchange_rate_service import ExchangeRateService

User = get_user_model()


@pytest.fixture
def slice2_setup(db):
    user = User.objects.create_superuser(username='slice2_admin', password='password123', email='admin@test.com')

    asset_type, _ = AccountType.objects.get_or_create(code="ASSET", defaults={"name": "أصول", "category": "asset", "nature": "debit"})
    liability_type, _ = AccountType.objects.get_or_create(code="LIABILITY", defaults={"name": "خصوم", "category": "liability", "nature": "credit"})
    revenue_type, _ = AccountType.objects.get_or_create(code="REVENUE", defaults={"name": "إيرادات", "category": "revenue", "nature": "credit"})
    expense_type, _ = AccountType.objects.get_or_create(code="EXPENSE", defaults={"name": "مصروفات", "category": "expense", "nature": "debit"})

    egp, _ = Currency.objects.get_or_create(
        code='EGP',
        defaults={'name': 'Egyptian Pound', 'symbol': '£', 'is_functional': True, 'decimal_places': 2}
    )
    usd, _ = Currency.objects.get_or_create(
        code='USD',
        defaults={'name': 'US Dollar', 'symbol': '$', 'is_functional': False, 'decimal_places': 2}
    )

    ExchangeRateService.set_rate('USD', 'EGP', Decimal('50.000000'), user=user)

    cash_acc, _ = ChartOfAccounts.objects.get_or_create(
        code='11101',
        defaults={'name': 'الخزينة الرئيسية', 'account_type': asset_type, 'currency': egp, 'is_active': True, 'is_leaf': True}
    )
    bank_acc, _ = ChartOfAccounts.objects.get_or_create(
        code='11102',
        defaults={'name': 'البنك التجاري', 'account_type': asset_type, 'currency': egp, 'is_active': True, 'is_leaf': True, 'is_bank_account': True}
    )
    advance_acc, _ = ChartOfAccounts.objects.get_or_create(
        code='21101',
        defaults={'name': 'أمانات جدية حجز العملاء', 'account_type': liability_type, 'currency': egp, 'is_active': True, 'is_leaf': True}
    )
    notes_pay_acc, _ = ChartOfAccounts.objects.get_or_create(
        code='21120',
        defaults={'name': 'أوراق الدفع - شيكات صادرة', 'account_type': liability_type, 'currency': egp, 'is_active': True, 'is_leaf': True}
    )
    ChartOfAccounts.objects.get_or_create(
        code='21301',
        defaults={'name': 'أوراق الدفع البديل', 'account_type': liability_type, 'currency': egp, 'is_active': True, 'is_leaf': True}
    )
    # Notes receivable & Under collection accounts required by central cheques engine
    ChartOfAccounts.objects.get_or_create(
        code='11220',
        defaults={'name': 'أوراق القبض', 'account_type': asset_type, 'currency': egp, 'is_active': True, 'is_leaf': True}
    )
    ChartOfAccounts.objects.get_or_create(
        code='11190',
        defaults={'name': 'شيكات برسم التحصيل', 'account_type': asset_type, 'currency': egp, 'is_active': True, 'is_leaf': True}
    )
    fx_loss_acc, _ = ChartOfAccounts.objects.get_or_create(
        code='54300',
        defaults={'name': 'خسائر فروق عملة محققة', 'account_type': expense_type, 'currency': egp, 'is_active': True, 'is_leaf': True}
    )
    fx_gain_acc, _ = ChartOfAccounts.objects.get_or_create(
        code='43100',
        defaults={'name': 'أرباح فروق عملة محققة', 'account_type': revenue_type, 'currency': egp, 'is_active': True, 'is_leaf': True}
    )
    round_acc, _ = ChartOfAccounts.objects.get_or_create(
        code='54400',
        defaults={'name': 'أرباح وخسائر تقريب العملات', 'account_type': expense_type, 'currency': egp, 'is_active': True, 'is_leaf': True}
    )
    contract_liab, _ = ChartOfAccounts.objects.get_or_create(
        code='21102',
        defaults={'name': 'التزامات عقود العملاء', 'account_type': liability_type, 'currency': egp, 'is_active': True, 'is_leaf': True}
    )

    project = RealEstateProject.objects.create(
        name="Slice 2 Grand Tower",
        code="SL2-PRJ",
        start_date=timezone.localdate(),
        expected_completion_date=timezone.localdate() + timedelta(days=730),
        created_by=user
    )
    block = PropertyBlock.objects.create(
        project=project,
        code="BLK-SL2",
        name="Block SL2"
    )
    floor = PropertyFloor.objects.create(
        block=block,
        floor_number=1,
        name="Floor 1"
    )
    unit1 = PropertyUnit.objects.create(
        project=project,
        block=block,
        floor=floor,
        unit_code="SL2-U101",
        unit_type=PropertyUnit.UnitType.APARTMENT,
        net_area=Decimal("100.00"),
        gross_area=Decimal("120.00"),
        meter_price=Decimal("25000.00"),
        base_price=Decimal("2500000.00"),
        status=PropertyUnit.UnitStatus.AVAILABLE
    )
    unit2 = PropertyUnit.objects.create(
        project=project,
        block=block,
        floor=floor,
        unit_code="SL2-U102",
        unit_type=PropertyUnit.UnitType.APARTMENT,
        net_area=Decimal("110.00"),
        gross_area=Decimal("130.00"),
        meter_price=Decimal("25000.00"),
        base_price=Decimal("2800000.00"),
        status=PropertyUnit.UnitStatus.AVAILABLE
    )

    cust1 = Customer.objects.create(name="Customer Primary", code="CUST-SL2-01", phone="01012345678", email="cust1@test.com")
    cust2 = Customer.objects.create(name="Customer Partner 1", code="CUST-SL2-02", phone="01022345678", email="cust2@test.com")
    cust3 = Customer.objects.create(name="Customer Partner 2", code="CUST-SL2-03", phone="01032345678", email="cust3@test.com")

    return {
        'user': user,
        'egp': egp,
        'usd': usd,
        'project': project,
        'unit1': unit1,
        'unit2': unit2,
        'cust1': cust1,
        'cust2': cust2,
        'cust3': cust3,
        'cash_acc': cash_acc,
        'bank_acc': bank_acc,
        'advance_acc': advance_acc,
        'notes_pay_acc': notes_pay_acc,
        'fx_loss_acc': fx_loss_acc,
        'fx_gain_acc': fx_gain_acc,
        'round_acc': round_acc,
        'contract_liab': contract_liab,
    }


@pytest.mark.django_db
def test_sync_contract_ownership_batch(slice2_setup):
    """اختبار مزامنة ملكية العقد ذرياً وفحص المجموع الإجمالي 100%"""
    user = slice2_setup['user']
    project = slice2_setup['project']
    unit = slice2_setup['unit1']
    cust1 = slice2_setup['cust1']
    cust2 = slice2_setup['cust2']
    cust3 = slice2_setup['cust3']
    egp = slice2_setup['egp']

    contract = PropertyContract.objects.create(
        contract_number="CTR-TEST-SYNC-01",
        project=project,
        unit=unit,
        customer=cust1,
        contract_date=timezone.localdate(),
        delivery_date=timezone.localdate() + timedelta(days=365),
        final_contract_price=Decimal("2500000.00"),
        currency=egp,
        primary_owner_share=Decimal("60.00"),
        created_by=user
    )

    co_owners = [
        {'customer_id': cust2.id, 'share_percentage': Decimal("25.00"), 'is_guarantor': True, 'relationship': 'BROTHER'},
        {'customer_id': cust3.id, 'share_percentage': Decimal("15.00"), 'is_guarantor': False, 'relationship': 'PARTNER'},
    ]

    # Success: 60 + 25 + 15 = 100%
    result = PropertyContractService.sync_contract_ownership(
        contract_id=contract.id,
        co_owners_data=co_owners,
        primary_owner_share=Decimal("60.00"),
        user=user
    )
    assert result.id == contract.id
    contract.refresh_from_db()
    assert contract.primary_owner_share == Decimal("60.00")
    assert contract.co_owners.count() == 2

    # Reject invalid sum (60 + 30 + 15 = 105%)
    invalid_co_owners = [
        {'customer_id': cust2.id, 'share_percentage': Decimal("30.00")},
        {'customer_id': cust3.id, 'share_percentage': Decimal("15.00")},
    ]
    with pytest.raises(ValidationError):
        PropertyContractService.sync_contract_ownership(
            contract_id=contract.id,
            co_owners_data=invalid_co_owners,
            primary_owner_share=Decimal("60.00"),
            user=user
        )

    # Reject negative primary share even if sum is 100% (-50 + 75 + 75 = 100%)
    with pytest.raises(ValidationError):
        PropertyContractService.sync_contract_ownership(
            contract_id=contract.id,
            co_owners_data=[
                {'customer_id': cust2.id, 'share_percentage': Decimal("75.00")},
                {'customer_id': cust3.id, 'share_percentage': Decimal("75.00")},
            ],
            primary_owner_share=Decimal("-50.00"),
            user=user
        )

    # Reject share > 100%
    with pytest.raises(ValidationError):
        PropertyContractService.sync_contract_ownership(
            contract_id=contract.id,
            co_owners_data=[],
            primary_owner_share=Decimal("120.00"),
            user=user
        )


@pytest.mark.django_db
def test_create_booking_accessories_and_collision(slice2_setup):
    """اختبار إنشاء الحجز وتمرير البايكة والمخزن وفحص منع التصادم"""
    user = slice2_setup['user']
    unit1 = slice2_setup['unit1']
    unit2 = slice2_setup['unit2']
    cust1 = slice2_setup['cust1']
    cust2 = slice2_setup['cust2']

    # 1. إنشاء الحجز الأول ببايكة ومخزن
    booking1 = UnitBookingService.create_booking(
        unit_id=unit1.id,
        customer=cust1,
        holding_deposit=Decimal("10000.00"),
        expiry_date=timezone.localdate() + timedelta(days=7),
        user=user,
        parking_slot_code="P-SL2-101",
        parking_slot_price=Decimal("150000.00"),
        storage_locker_code="S-SL2-201",
        storage_locker_price=Decimal("50000.00"),
    )
    assert booking1.parking_slot_code == "P-SL2-101"
    assert booking1.storage_locker_code == "S-SL2-201"

    # 2. محاولة حجز نفس البايكة لوحدة أخرى في نفس المشروع -> رفض بتعارض
    with pytest.raises(BookingValidationError) as exc1:
        UnitBookingService.create_booking(
            unit_id=unit2.id,
            customer=cust2,
            holding_deposit=Decimal("5000.00"),
            expiry_date=timezone.localdate() + timedelta(days=7),
            user=user,
            parking_slot_code="P-SL2-101",
        )
    assert "محجوزة أو متعاقد عليها" in str(exc1.value)

    # 3. محاولة حجز نفس المخزن لوحدة أخرى -> رفض بتعارض
    with pytest.raises(BookingValidationError) as exc2:
        UnitBookingService.create_booking(
            unit_id=unit2.id,
            customer=cust2,
            holding_deposit=Decimal("5000.00"),
            expiry_date=timezone.localdate() + timedelta(days=7),
            user=user,
            storage_locker_code="S-SL2-201",
        )
    assert "محجوز أو متعاقد عليه" in str(exc2.value)


@pytest.mark.django_db
def test_convert_booking_to_contract_dual_audit_guard(slice2_setup):
    """اختبار حظر تحويل الحجز غير المعتمد، والسماح به بعد الاعتماد وفصل التشطيب"""
    user = slice2_setup['user']
    unit1 = slice2_setup['unit1']
    cust1 = slice2_setup['cust1']

    booking = UnitBookingService.create_booking(
        unit_id=unit1.id,
        customer=cust1,
        holding_deposit=Decimal("10000.00"),
        expiry_date=timezone.localdate() + timedelta(days=7),
        user=user,
        parking_slot_code="P-101",
        storage_locker_code="S-101"
    )
    assert not booking.is_confirmed_audit
    assert not booking.is_legacy_pre_audit
    assert not booking.audit_bypassed

    # التحويل يفشل لأن الحجز لم يعتمد رقابياً
    with pytest.raises(BookingValidationError) as exc:
        UnitBookingService.convert_booking_to_contract(
            booking_id=booking.id,
            user=user
        )
    assert "الاعتماد المالي والرقابي الثنائي" in str(exc.value)

    # اعتماد الحجز بمراجعة مبيعات واعتماد رقابي لمستخدمين منفصلين (Segregation of Duties)
    from django.contrib.auth import get_user_model
    sales_rep = get_user_model().objects.create_user(username='slice2_sales_reviewer', email='sl2_sales@test.com')
    audit_rep = get_user_model().objects.create_user(username='slice2_audit_approver', email='sl2_audit@test.com')

    booking.is_reviewed_sales = True
    booking.reviewed_by = sales_rep
    booking.reviewed_at = timezone.now()
    booking.is_confirmed_audit = True
    booking.confirmed_by = audit_rep
    booking.confirmed_at = timezone.now()
    booking.save()

    # الآن ينجح التحويل مع فصل التشطيب التعاقدي
    contract = UnitBookingService.convert_booking_to_contract(
        booking_id=booking.id,
        user=user,
        contract_tax_structure=PropertyContract.ContractTaxStructure.SPLIT_SPA_FINISHING_ANNEX
    )
    assert contract.status == PropertyContract.ContractStatus.ACTIVE
    assert contract.has_decoupled_finishing is True
    assert contract.parking_slot_code == "P-101"
    assert contract.storage_locker_code == "S-101"


@pytest.mark.django_db
def test_sweep_expired_bookings(slice2_setup):
    """اختبار كنس الحجوزات المنتهية ونقل المسددة إلى CANCELLED_PENDING_REFUND وتحرير الوحدة"""
    user = slice2_setup['user']
    unit1 = slice2_setup['unit1']
    unit2 = slice2_setup['unit2']
    cust1 = slice2_setup['cust1']
    cust2 = slice2_setup['cust2']

    # حجز مسدد ومنتهي
    b1 = UnitBookingService.create_booking(
        unit_id=unit1.id,
        customer=cust1,
        holding_deposit=Decimal("10000.00"),
        booking_date=timezone.localdate() - timedelta(days=10),
        expiry_date=timezone.localdate() - timedelta(days=1),
        user=user
    )
    # حجز غير مسدد ومنتهي (بدون إيداع)
    b2 = UnitBookingService.create_booking(
        unit_id=unit2.id,
        customer=cust2,
        holding_deposit=Decimal("0.00"),
        booking_date=timezone.localdate() - timedelta(days=10),
        expiry_date=timezone.localdate() - timedelta(days=1),
        user=user
    )

    swept = UnitBookingSweepService.sweep_expired_bookings()
    assert swept == 2

    b1.refresh_from_db()
    b2.refresh_from_db()
    unit1.refresh_from_db()
    unit2.refresh_from_db()

    assert b1.status == UnitBooking.BookingStatus.CANCELLED_PENDING_REFUND
    assert b2.status == UnitBooking.BookingStatus.EXPIRED_RELEASED
    assert unit1.status == PropertyUnit.UnitStatus.AVAILABLE
    assert unit2.status == PropertyUnit.UnitStatus.AVAILABLE
    assert unit1.current_booking is None
    assert unit2.current_booking is None


@pytest.mark.django_db
def test_disburse_refund_cash_bank_multi_currency_and_fx(slice2_setup):
    """اختبار صرف استرداد نقد/بنك بعملة محلية لتسوية دولار مع قيود فروق العملة"""
    user = slice2_setup['user']
    unit1 = slice2_setup['unit1']
    cust1 = slice2_setup['cust1']
    usd = slice2_setup['usd']
    egp = slice2_setup['egp']
    bank_acc = slice2_setup['bank_acc']

    booking = UnitBookingService.create_booking(
        unit_id=unit1.id,
        customer=cust1,
        holding_deposit=Decimal("1000.00"),
        currency=usd,
        exchange_rate=Decimal("48.000000"),
        expiry_date=timezone.localdate() + timedelta(days=7),
        user=user
    )

    settlement = BookingCancellationSettlement.objects.create(
        booking=booking,
        currency=usd,
        exchange_rate=Decimal("48.000000"),
        total_deposit_paid=Decimal("1000.00"),
        net_refundable_amount=Decimal("1000.00"),
        remaining_disbursable_amount=Decimal("1000.00"),
        processed_by=user
    )
    booking.active_cancellation_settlement = settlement
    booking.save()

    # Rate on payout date: 1 USD = 50.00 EGP
    # Disburse 50,000 EGP (equivalent to 1,000 USD)
    payment = RealEstateAccountingService.disburse_refund(
        settlement_id=settlement.id,
        requested_amount=Decimal("50000.00"),
        payout_currency=egp,
        method=RefundDisbursementPayment.DisbursementMethod.BANK_TRANSFER,
        payment_account=bank_acc,
        idempotency_key="TEST-REFUND-BT-01",
        user=user
    )

    assert payment.status == RefundDisbursementPayment.PaymentStatus.CLEARED
    assert payment.settlement_currency_equivalent == Decimal("1000.00")
    assert payment.functional_amount == Decimal("50000.00")
    # Advance settled functional: 1,000 * 48 = 48,000. Payout: 50,000. FX loss = 2,000 EGP
    assert payment.realized_fx_gain_loss == Decimal("2000.00")

    settlement.refresh_from_db()
    assert settlement.remaining_disbursable_amount == Decimal("0.00")
    assert settlement.cleared_amount == Decimal("1000.00")
    assert settlement.status == BookingCancellationSettlement.SettlementStatus.FULLY_DISBURSED


@pytest.mark.django_db
def test_disburse_refund_cheque_and_two_way_lifecycle_sync(slice2_setup):
    """اختبار صرف استرداد بشيك والربط ثنائي الاتجاه: إصدار -> ارتداد وعكس -> إعادة صرف ومقاصة"""
    user = slice2_setup['user']
    unit1 = slice2_setup['unit1']
    cust1 = slice2_setup['cust1']
    usd = slice2_setup['usd']
    egp = slice2_setup['egp']
    bank_acc = slice2_setup['bank_acc']

    booking = UnitBookingService.create_booking(
        unit_id=unit1.id,
        customer=cust1,
        holding_deposit=Decimal("1000.00"),
        currency=usd,
        exchange_rate=Decimal("48.000000"),
        expiry_date=timezone.localdate() + timedelta(days=7),
        user=user
    )

    settlement = BookingCancellationSettlement.objects.create(
        booking=booking,
        currency=usd,
        exchange_rate=Decimal("48.000000"),
        total_deposit_paid=Decimal("1000.00"),
        net_refundable_amount=Decimal("1000.00"),
        remaining_disbursable_amount=Decimal("1000.00"),
        processed_by=user
    )
    booking.active_cancellation_settlement = settlement
    booking.save()

    # 1. Issue cheque for 50,000 EGP
    payment = RealEstateAccountingService.disburse_refund(
        settlement_id=settlement.id,
        requested_amount=Decimal("50000.00"),
        payout_currency=egp,
        method=RefundDisbursementPayment.DisbursementMethod.CHEQUE,
        payment_account=bank_acc,
        cheque_data={'cheque_number': 'CHQ-REF-9988', 'drawer_bank_name': 'Commercial Bank'},
        idempotency_key="TEST-REFUND-CHQ-01",
        user=user
    )

    assert payment.status == RefundDisbursementPayment.PaymentStatus.ISSUED
    cheque = payment.cheque
    assert cheque is not None
    assert cheque.status == ChequeStatus.ISSUED
    assert cheque.purpose == ChequePurpose.CUSTOMER_REFUND

    settlement.refresh_from_db()
    assert settlement.committed_amount == Decimal("1000.00")
    assert settlement.remaining_disbursable_amount == Decimal("0.00")

    # 2. Bounce the cheque -> Two-Way Hook should update payment to BOUNCED, mirror reverse JE, restore settlement
    ChequeAccountingService.bounce_cheque(cheque=cheque, reason="Insufficient funds", user=user)

    payment.refresh_from_db()
    settlement.refresh_from_db()
    assert payment.status == RefundDisbursementPayment.PaymentStatus.BOUNCED
    assert payment.reversal_journal_entry is not None
    # Remaining restored to 1,000 USD
    assert settlement.committed_amount == Decimal("0.00")
    assert settlement.remaining_disbursable_amount == Decimal("1000.00")

    # 3. Guard: Block BOUNCED -> ISSUED transition for CUSTOMER_REFUND
    with pytest.raises(ValidationError):
        ChequeAccountingService.issue_cheque(cheque_or_id=cheque.id, user=user)

    # 4. Issue replacement cheque and CLEAR it
    payment2 = RealEstateAccountingService.disburse_refund(
        settlement_id=settlement.id,
        requested_amount=Decimal("50000.00"),
        payout_currency=egp,
        method=RefundDisbursementPayment.DisbursementMethod.CHEQUE,
        payment_account=bank_acc,
        cheque_data={'cheque_number': 'CHQ-REF-9989', 'drawer_bank_name': 'Commercial Bank'},
        idempotency_key="TEST-REFUND-CHQ-02",
        user=user
    )
    cheque2 = payment2.cheque
    assert cheque2.status == ChequeStatus.ISSUED

    ChequeAccountingService.clear_cheque(cheque=cheque2, user=user)

    payment2.refresh_from_db()
    settlement.refresh_from_db()
    assert payment2.status == RefundDisbursementPayment.PaymentStatus.CLEARED
    assert payment2.clearing_journal_entry is not None
    assert settlement.cleared_amount == Decimal("1000.00")
    assert settlement.remaining_disbursable_amount == Decimal("0.00")
    assert settlement.status == BookingCancellationSettlement.SettlementStatus.FULLY_DISBURSED


@pytest.mark.django_db
def test_disburse_refund_idempotency_and_zero_balance_guards(slice2_setup):
    """اختبار أسبقية فحص التكرار بعد القفل وحراسة الرصيد الصفري للطلبات الجديدة"""
    user = slice2_setup['user']
    unit1 = slice2_setup['unit1']
    cust1 = slice2_setup['cust1']
    egp = slice2_setup['egp']
    bank_acc = slice2_setup['bank_acc']

    booking = UnitBookingService.create_booking(
        unit_id=unit1.id,
        customer=cust1,
        holding_deposit=Decimal("5000.00"),
        currency=egp,
        expiry_date=timezone.localdate() + timedelta(days=7),
        user=user
    )
    settlement = BookingCancellationSettlement.objects.create(
        booking=booking,
        currency=egp,
        total_deposit_paid=Decimal("5000.00"),
        net_refundable_amount=Decimal("5000.00"),
        remaining_disbursable_amount=Decimal("5000.00"),
        processed_by=user
    )
    booking.active_cancellation_settlement = settlement
    booking.save()

    # أول استدعاء ينجح ويستنفد الرصيد بالكامل
    pay1 = RealEstateAccountingService.disburse_refund(
        settlement_id=settlement.id,
        requested_amount=Decimal("5000.00"),
        payout_currency=egp,
        method=RefundDisbursementPayment.DisbursementMethod.BANK_TRANSFER,
        payment_account=bank_acc,
        idempotency_key="UNIQUE-KEY-001",
        user=user
    )
    assert pay1.status == RefundDisbursementPayment.PaymentStatus.CLEARED

    settlement.refresh_from_db()
    assert settlement.remaining_disbursable_amount == Decimal("0.00")

    # إعادة نفس الطلب بنفس المفتاح بعد نفاد الرصيد -> نجاح وإرجاع نفس السجل دون خطأ رصيد صفري
    pay_retry = RealEstateAccountingService.disburse_refund(
        settlement_id=settlement.id,
        requested_amount=Decimal("5000.00"),
        payout_currency=egp,
        method=RefundDisbursementPayment.DisbursementMethod.BANK_TRANSFER,
        payment_account=bank_acc,
        idempotency_key="UNIQUE-KEY-001",
        user=user
    )
    assert pay_retry.id == pay1.id

    # طلب جديد بمفتاح جديد على رصيد صفري -> رفض بحراسة الرصيد الصفري
    with pytest.raises(ValidationError) as exc:
        RealEstateAccountingService.disburse_refund(
            settlement_id=settlement.id,
            requested_amount=Decimal("100.00"),
            payout_currency=egp,
            method=RefundDisbursementPayment.DisbursementMethod.BANK_TRANSFER,
            payment_account=bank_acc,
            idempotency_key="NEW-KEY-002",
            user=user
        )
    assert "لا يوجد رصيد متبقٍ متاح للصرف" in str(exc.value)


@pytest.mark.django_db
def test_disburse_refund_full_sweep_tolerance(slice2_setup):
    """اختبار حصر سماحية التقريب باشتراط التصفية الكاملة صراحة is_full_sweep=True"""
    user = slice2_setup['user']
    unit1 = slice2_setup['unit1']
    cust1 = slice2_setup['cust1']
    usd = slice2_setup['usd']
    egp = slice2_setup['egp']
    bank_acc = slice2_setup['bank_acc']

    booking = UnitBookingService.create_booking(
        unit_id=unit1.id,
        customer=cust1,
        holding_deposit=Decimal("1000.00"),
        currency=usd,
        exchange_rate=Decimal("50.000000"),
        expiry_date=timezone.localdate() + timedelta(days=7),
        user=user
    )
    settlement = BookingCancellationSettlement.objects.create(
        booking=booking,
        currency=usd,
        exchange_rate=Decimal("50.000000"),
        total_deposit_paid=Decimal("1000.00"),
        net_refundable_amount=Decimal("1000.00"),
        remaining_disbursable_amount=Decimal("1000.00"),
        processed_by=user
    )
    booking.active_cancellation_settlement = settlement
    booking.save()

    # صرف 50,001 EGP بسعر 50 يعطي معادل 1,000.02 USD (فارق 0.02 ضمن سماحية 0.05)
    # 1. بدون تفعيل is_full_sweep -> يجب أن يرفض لأن 1000.02 > 1000.00
    with pytest.raises(ValidationError) as exc:
        RealEstateAccountingService.disburse_refund(
            settlement_id=settlement.id,
            requested_amount=Decimal("50001.00"),
            payout_currency=egp,
            method=RefundDisbursementPayment.DisbursementMethod.BANK_TRANSFER,
            payment_account=bank_acc,
            idempotency_key="SWEEP-FALSE-01",
            is_full_sweep=False,
            user=user
        )
    assert "يتجاوز الرصيد المتبقي" in str(exc.value)

    # 2. مع تفعيل is_full_sweep=True -> يتم قبول الطلب مع الـ Snap وتوجيه الفرق لحساب التقريب
    pay_sweep = RealEstateAccountingService.disburse_refund(
        settlement_id=settlement.id,
        requested_amount=Decimal("50001.00"),
        payout_currency=egp,
        method=RefundDisbursementPayment.DisbursementMethod.BANK_TRANSFER,
        payment_account=bank_acc,
        idempotency_key="SWEEP-TRUE-01",
        is_full_sweep=True,
        user=user
    )
    assert pay_sweep.settlement_currency_equivalent == Decimal("1000.00")
    assert pay_sweep.rounding_difference == Decimal("0.02")
    settlement.refresh_from_db()
    assert settlement.remaining_disbursable_amount == Decimal("0.00")
    assert settlement.status == BookingCancellationSettlement.SettlementStatus.FULLY_DISBURSED


def test_meta_whatsapp_payload_builder():
    """اختبار بناء حمولة إشعار تحرير شيك الاسترداد لواتساب وفق معيار Meta Graph API"""
    payload = MetaWhatsAppPayloadBuilder.build_refund_cheque_payload(
        recipient_phone="01012345678",
        customer_name="أحمد محمود",
        unit_code="SL2-U101",
        cheque_number="CHQ-987654",
        amount=Decimal("75000.00"),
        due_date="2026-12-01",
        bank_name="البنك الأهلي المصري",
        currency_code="EGP"
    )
    assert payload["to"] == "+201012345678"
    assert payload["template"]["name"] == MetaWhatsAppPayloadBuilder.TEMPLATE_REFUND_CHEQUE_ISSUED
    body_params = payload["template"]["components"][0]["parameters"]
    assert len(body_params) == 6
    assert body_params[0]["text"] == "أحمد محمود"
    assert body_params[1]["text"] == "SL2-U101"
    assert body_params[2]["text"] == "CHQ-987654"
    assert body_params[3]["text"] == "75,000.00 EGP"
    assert body_params[4]["text"] == "2026-12-01"
    assert body_params[5]["text"] == "البنك الأهلي المصري"
