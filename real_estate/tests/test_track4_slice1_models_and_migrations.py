# -*- coding: utf-8 -*-
import uuid
from decimal import Decimal
from datetime import timedelta
import pytest
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
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
from financial.models import Currency, ChartOfAccounts
from cheques.models import Cheque, ChequeType, ChequeStatus, ChequePurpose
from core.models import WhatsAppMessageLog
from core.enums.document_types import DocumentType

User = get_user_model()


@pytest.fixture
def slice1_setup(db):
    user = User.objects.create_user(username='slice1_auditor', password='password123')
    currency, _ = Currency.objects.get_or_create(
        code='EGP',
        defaults={'name': 'Egyptian Pound', 'symbol': '£', 'current_rate': Decimal('1.000000')}
    )
    usd_currency, _ = Currency.objects.get_or_create(
        code='USD',
        defaults={'name': 'US Dollar', 'symbol': '$', 'current_rate': Decimal('50.000000')}
    )
    project = RealEstateProject.objects.create(
        name="Slice 1 Horizon Tower",
        code="SL1-PRJ",
        start_date=timezone.localdate(),
        expected_completion_date=timezone.localdate() + timedelta(days=730),
        created_by=user
    )
    block = PropertyBlock.objects.create(
        project=project,
        code="BLK-SL1",
        name="Block SL1"
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
        unit_code="SL1-U101",
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
        unit_code="SL1-U102",
        unit_type=PropertyUnit.UnitType.APARTMENT,
        net_area=Decimal("110.00"),
        gross_area=Decimal("130.00"),
        meter_price=Decimal("25000.00"),
        base_price=Decimal("2800000.00"),
        status=PropertyUnit.UnitStatus.AVAILABLE
    )
    unit3 = PropertyUnit.objects.create(
        project=project,
        block=block,
        floor=floor,
        unit_code="SL1-U103",
        unit_type=PropertyUnit.UnitType.APARTMENT,
        net_area=Decimal("120.00"),
        gross_area=Decimal("140.00"),
        meter_price=Decimal("25000.00"),
        base_price=Decimal("3000000.00"),
        status=PropertyUnit.UnitStatus.AVAILABLE
    )
    customer1 = Customer.objects.create(
        name="أحمد محمود المحامي",
        code="CUST-SL1-01",
        phone="01011112222"
    )
    customer2 = Customer.objects.create(
        name="سارة علي الشريك",
        code="CUST-SL1-02",
        phone="01033334444"
    )
    return {
        'user': user,
        'currency': currency,
        'usd_currency': usd_currency,
        'project': project,
        'unit1': unit1,
        'unit2': unit2,
        'unit3': unit3,
        'customer1': customer1,
        'customer2': customer2,
    }


@pytest.mark.django_db
class TestSlice1ModelsAndMigrations:

    def test_cheque_purpose_customer_refund_exists(self):
        """التحقق من تسجيل غرض الشيك CUSTOMER_REFUND بنجاح"""
        assert 'CUSTOMER_REFUND' in ChequePurpose.values
        assert ChequePurpose.CUSTOMER_REFUND == "CUSTOMER_REFUND"

    def test_whatsapp_message_log_in_flight_and_idempotency_key(self, slice1_setup):
        """التحقق من حالة IN_FLIGHT ومفتاح عدم التكرار في WhatsAppMessageLog"""
        log = WhatsAppMessageLog.objects.create(
            recipient_phone="01011112222",
            status='IN_FLIGHT',
            event_idempotency_key="EVT-WAPP-SL1-001"
        )
        assert log.status == 'IN_FLIGHT'
        assert log.event_idempotency_key == "EVT-WAPP-SL1-001"

        # منع تكرار مفتاح الحدث
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                WhatsAppMessageLog.objects.create(
                    recipient_phone="01011112222",
                    status='PENDING',
                    event_idempotency_key="EVT-WAPP-SL1-001"
                )

    def test_unit_booking_uuid_and_auto_sequence(self, slice1_setup):
        """توليد UUID والترقيم التلقائي للحجز والتحقق من التفرد"""
        data = slice1_setup
        booking = UnitBooking.objects.create(
            unit=data['unit1'],
            customer=data['customer1'],
            booking_date=timezone.localdate(),
            expiry_date=timezone.localdate() + timedelta(days=14),
            holding_deposit=Decimal("50000.00"),
            currency=data['currency'],
            created_by=data['user']
        )
        assert booking.booking_number.startswith("BK")
        assert booking.verification_uuid is not None
        assert isinstance(booking.verification_uuid, uuid.UUID)

    def test_unit_booking_hoarding_limit(self, slice1_setup):
        """منع العميل من حجز أكثر من وحدتين دون سداد جدية الحجز"""
        data = slice1_setup
        # حجز 1 غير مسدد
        b1 = UnitBooking(
            unit=data['unit1'],
            customer=data['customer1'],
            expiry_date=timezone.localdate() + timedelta(days=7),
            holding_deposit=Decimal("20000.00"),
            is_deposit_collected=False,
            created_by=data['user']
        )
        b1.save()

        # حجز 2 غير مسدد
        b2 = UnitBooking(
            unit=data['unit2'],
            customer=data['customer1'],
            expiry_date=timezone.localdate() + timedelta(days=7),
            holding_deposit=Decimal("20000.00"),
            is_deposit_collected=False,
            created_by=data['user']
        )
        b2.save()

        # حجز 3 غير مسدد لنفس العميل في نفس المشروع يجب أن يُرفض
        b3 = UnitBooking(
            unit=data['unit3'],
            customer=data['customer1'],
            expiry_date=timezone.localdate() + timedelta(days=7),
            holding_deposit=Decimal("20000.00"),
            is_deposit_collected=False,
            created_by=data['user']
        )
        with pytest.raises(ValidationError) as exc:
            b3.save()
        assert "لا يمكن للعميل حجز أكثر من وحدتين دون سداد جدية الحجز" in str(exc.value)

    def test_unit_booking_partner_share_validation(self, slice1_setup):
        """التحقق من أن مجموع حصة الشركة والشريك 100%"""
        data = slice1_setup
        b = UnitBooking(
            unit=data['unit1'],
            customer=data['customer1'],
            expiry_date=timezone.localdate() + timedelta(days=7),
            holding_deposit=Decimal("20000.00"),
            company_share_percentage=Decimal("70.00"),
            partner_share_percentage=Decimal("20.00"),  # مجموع 90% خطأ
            created_by=data['user']
        )
        with pytest.raises(ValidationError) as exc:
            b.save()
        assert "يجب أن يساوي 100.00%" in str(exc.value)

    def test_unit_booking_confirmed_audit_immutability(self, slice1_setup):
        """قفل الحصانة البرمجية للحجز المعتمد رقابياً"""
        data = slice1_setup
        booking = UnitBooking.objects.create(
            unit=data['unit1'],
            customer=data['customer1'],
            expiry_date=timezone.localdate() + timedelta(days=14),
            holding_deposit=Decimal("50000.00"),
            is_deposit_collected=True,
            is_reviewed_sales=True,
            is_confirmed_audit=True,
            confirmed_by=data['user'],
            confirmed_at=timezone.now(),
            created_by=data['user']
        )

        # محاولة تعديل مبلغ جدية الحجز بعد الاعتماد الرقابي ترفع ValidationError
        booking.holding_deposit = Decimal("60000.00")
        with pytest.raises(ValidationError) as exc:
            booking.save()
        assert "حظر تعديل الحجز المعتمد رقابياً" in str(exc.value)

        # التجاوز الصريح عبر force_audit_update يمرر التعديل
        booking.holding_deposit = Decimal("60000.00")
        booking.save(force_audit_update=True)
        booking.refresh_from_db()
        assert booking.holding_deposit == Decimal("60000.00")

    def test_property_contract_tax_structure_and_co_owner_integrity(self, slice1_setup):
        """فحص الهيكلة الضريبية ونسب الملكية للشريك والمالك الرئيسي"""
        data = slice1_setup
        contract = PropertyContract.objects.create(
            project=data['project'],
            unit=data['unit1'],
            customer=data['customer1'],
            contract_date=timezone.localdate(),
            delivery_date=timezone.localdate() + timedelta(days=365),
            final_contract_price=Decimal("2500000.00"),
            down_payment=Decimal("500000.00"),
            currency=data['currency'],
            contract_tax_structure=PropertyContract.ContractTaxStructure.SPLIT_SPA_FINISHING_ANNEX,
            has_decoupled_finishing=True,
            finishing_total_amount=Decimal("300000.00"),
            primary_owner_share=Decimal("60.00"),
            created_by=data['user']
        )
        assert contract.contract_tax_structure == "SPLIT_SPA_FINISHING_ANNEX"
        assert contract.has_decoupled_finishing is True

        # إضافة شريك بنسبة 40% (المجموع 100%)
        co_owner = ContractCoOwner.objects.create(
            contract=contract,
            co_owner=data['customer2'],
            share_percentage=Decimal("40.00"),
            relationship=ContractCoOwner.RelationshipType.BUSINESS_PARTNER,
            notes="شريك مستثمر مناصف"
        )
        assert co_owner.relationship == "BUSINESS_PARTNER"

        # إضافة شريك آخر يتجاوز 100% يُرفض
        cust3 = Customer.objects.create(name="شريك ثالث", code="CUST-SL1-03", phone="01099998888")
        with pytest.raises(ValidationError) as exc:
            ContractCoOwner.objects.create(
                contract=contract,
                co_owner=cust3,
                share_percentage=Decimal("15.00")
            )
        assert "إجمالي نسب الملكية في العقد" in str(exc.value)

    def test_booking_cancellation_settlement_and_disbursement(self, slice1_setup):
        """فحص دورة حياة قرار تسوية الإلغاء واحتساب الأرصدة وسندات الصرف"""
        data = slice1_setup
        booking = UnitBooking.objects.create(
            unit=data['unit1'],
            customer=data['customer1'],
            expiry_date=timezone.localdate() + timedelta(days=14),
            holding_deposit=Decimal("100000.00"),
            is_deposit_collected=True,
            created_by=data['user']
        )

        settlement = BookingCancellationSettlement.objects.create(
            booking=booking,
            currency=data['currency'],
            exchange_rate=Decimal("1.000000"),
            total_deposit_paid=Decimal("100000.00"),
            approved_deduction_fees=Decimal("10000.00"),
            net_refundable_amount=Decimal("90000.00"),
            remaining_disbursable_amount=Decimal("90000.00"),
            processed_by=data['user']
        )
        assert settlement.settlement_number.startswith("CSETL")
        assert settlement.status == BookingCancellationSettlement.SettlementStatus.APPROVED_PENDING_PAYMENT

        # ربط مؤشر التسوية السارية بالحجز
        booking.active_cancellation_settlement = settlement
        booking.save()

        # إنشاء سند صرف أولي بشيك
        p1 = RefundDisbursementPayment.objects.create(
            idempotency_key="PAY-IDEMP-001",
            settlement=settlement,
            method=RefundDisbursementPayment.DisbursementMethod.CHEQUE,
            amount=Decimal("40000.00"),
            payout_currency=data['currency'],
            payout_exchange_rate=Decimal("1.000000"),
            settlement_currency_equivalent=Decimal("40000.00"),
            functional_amount=Decimal("40000.00"),
            status=RefundDisbursementPayment.PaymentStatus.ISSUED,
            processed_by=data['user']
        )
        assert p1.payment_number.startswith("RFND")

        # إعادة احتساب الأرصدة
        settlement.recalculate_balances()
        settlement.refresh_from_db()
        assert settlement.committed_amount == Decimal("40000.00")
        assert settlement.cleared_amount == Decimal("0.00")
        assert settlement.remaining_disbursable_amount == Decimal("50000.00")
        assert settlement.status == BookingCancellationSettlement.SettlementStatus.PARTIALLY_DISBURSED

        # تحويل السند الأول إلى CLEARED وصرف المتبقي 50,000
        p1.status = RefundDisbursementPayment.PaymentStatus.CLEARED
        p1.save()

        p2 = RefundDisbursementPayment.objects.create(
            idempotency_key="PAY-IDEMP-002",
            settlement=settlement,
            method=RefundDisbursementPayment.DisbursementMethod.CASH,
            amount=Decimal("50000.00"),
            payout_currency=data['currency'],
            payout_exchange_rate=Decimal("1.000000"),
            settlement_currency_equivalent=Decimal("50000.00"),
            functional_amount=Decimal("50000.00"),
            status=RefundDisbursementPayment.PaymentStatus.CLEARED,
            processed_by=data['user']
        )
        settlement.recalculate_balances()
        settlement.refresh_from_db()
        assert settlement.committed_amount == Decimal("0.00")
        assert settlement.cleared_amount == Decimal("90000.00")
        assert settlement.remaining_disbursable_amount == Decimal("0.00")
        assert settlement.status == BookingCancellationSettlement.SettlementStatus.FULLY_DISBURSED
