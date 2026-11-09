# -*- coding: utf-8 -*-
"""
Tests for Track 4 Slice 5: Comprehensive Hardening, Stress Scenarios, and Edge Cases
"""
import uuid
from decimal import Decimal
from datetime import timedelta
import pytest
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.test.utils import CaptureQueriesContext
from django.db import connection

from core.models import SystemModule, WhatsAppMessageLog
from customer.models import Customer
from financial.models import Currency, ChartOfAccounts, AccountType
from financial.services.exchange_rate_service import ExchangeRateService
from cheques.models import Cheque, ChequeStatus, ChequePurpose
from cheques.services.accounting_service import ChequeAccountingService
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
from real_estate.services.booking_service import UnitBookingService, BookingValidationError
from real_estate.services.contract_service import PropertyContractService
from real_estate.services.accounting_service import RealEstateAccountingService
from real_estate.services.reporting_service import RealEstateReportingService

User = get_user_model()


@pytest.fixture
def hardened_setup(db):
    user_admin = User.objects.create_superuser(username='sl5_admin', password='password123', email='admin5@test.com')
    user_closer = User.objects.create_user(username='sl5_closer', password='password123', email='closer5@test.com')

    SystemModule.objects.update_or_create(
        code='real_estate',
        defaults={'name_ar': 'القطاع العقاري', 'is_enabled': True}
    )

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

    ExchangeRateService.set_rate('USD', 'EGP', Decimal('50.000000'), user=user_admin)

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
        name="Hardened Elite Tower",
        code="HD-PRJ",
        start_date=timezone.localdate(),
        expected_completion_date=timezone.localdate() + timedelta(days=730),
        created_by=user_admin
    )
    block = PropertyBlock.objects.create(
        project=project,
        code="BLK-HD",
        name="Block HD",
        construction_progress_percentage=Decimal("75.00")
    )
    floor = PropertyFloor.objects.create(
        block=block,
        floor_number=1,
        name="Floor 1"
    )
    unit1 = PropertyUnit.objects.create(
        project=project, block=block, floor=floor, unit_code="HD-U101",
        unit_type=PropertyUnit.UnitType.APARTMENT, net_area=Decimal("120.00"),
        gross_area=Decimal("140.00"), meter_price=Decimal("25000.00"),
        base_price=Decimal("3500000.00"), status=PropertyUnit.UnitStatus.AVAILABLE
    )
    unit2 = PropertyUnit.objects.create(
        project=project, block=block, floor=floor, unit_code="HD-U102",
        unit_type=PropertyUnit.UnitType.APARTMENT, net_area=Decimal("130.00"),
        gross_area=Decimal("150.00"), meter_price=Decimal("25000.00"),
        base_price=Decimal("3750000.00"), status=PropertyUnit.UnitStatus.AVAILABLE
    )

    cust1 = Customer.objects.create(name="العميل الأصيل", code="CUST-HD-01", phone="01011119999")
    cust2 = Customer.objects.create(name="الشريك الأول", code="CUST-HD-02", phone="01022229999")
    cust3 = Customer.objects.create(name="الشريك الثاني", code="CUST-HD-03", phone="01033339999")

    return {
        'admin': user_admin,
        'closer': user_closer,
        'project': project,
        'block': block,
        'floor': floor,
        'unit1': unit1,
        'unit2': unit2,
        'cust1': cust1,
        'cust2': cust2,
        'cust3': cust3,
        'egp': egp,
        'usd': usd,
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
class TestHardenedSalesBookingSuite:
    """الحزمة المتكاملة للاختبارات الحوكمية ومعايير الإجهاد والاتساق"""

    def test_auto_sequence_and_verification_uuid_generation(self, hardened_setup):
        """اختبار الترقيم التلقائي وتوليد كود التوثيق اللحظي تلقائياً دون أخطاء"""
        s = hardened_setup
        booking = UnitBooking(
            unit=s['unit1'],
            customer=s['cust1'],
            holding_deposit=Decimal("50000.00"),
            currency=s['egp'],
            status=UnitBooking.BookingStatus.ACTIVE,
            booking_date=timezone.localdate(),
            expiry_date=timezone.localdate() + timedelta(days=14),
            created_by=s['admin']
        )
        # قبل الحفظ، الترقيم غير موجود
        assert not booking.booking_number

        booking.save()
        assert booking.booking_number.startswith("BK")
        assert booking.verification_uuid is not None

        # إنشاء قرار تسوية إلغاء والتحقق من رقم التسوية التلقائي
        settlement = BookingCancellationSettlement(
            booking=booking,
            currency=s['egp'],
            total_deposit_paid=Decimal("50000.00"),
            net_refundable_amount=Decimal("50000.00"),
            remaining_disbursable_amount=Decimal("50000.00"),
            processed_by=s['admin']
        )
        settlement.save()
        assert settlement.settlement_number.startswith("CSETL")

        # إنشاء سند صرف استرداد والتحقق من رقم السند التلقائي
        payment = RefundDisbursementPayment(
            settlement=settlement,
            idempotency_key="AUTO-SEQ-PAY-01",
            method=RefundDisbursementPayment.DisbursementMethod.CASH,
            amount=Decimal("20000.00"),
            settlement_currency_equivalent=Decimal("20000.00"),
            payout_currency=s['egp'],
            processed_by=s['admin']
        )
        payment.save()
        assert payment.payment_number.startswith("RFND")

    def test_strict_disbursement_method_validation_pre_lock(self, hardened_setup):
        """اختبار الرفض الاستباقي لوسائل الصرف غير المعروفة قبل حيازة الأقفال وبدون إنشاء أي سجل"""
        s = hardened_setup
        booking = UnitBookingService.create_booking(
            unit_id=s['unit1'].id, customer=s['cust1'],
            holding_deposit=Decimal("40000.00"),
            expiry_date=timezone.localdate() + timedelta(days=7),
            user=s['admin']
        )
        settlement = BookingCancellationSettlement.objects.create(
            booking=booking, currency=s['egp'],
            total_deposit_paid=Decimal("40000.00"),
            net_refundable_amount=Decimal("40000.00"),
            remaining_disbursable_amount=Decimal("40000.00"),
            processed_by=s['admin']
        )

        with pytest.raises(ValidationError) as exc:
            RealEstateAccountingService.disburse_refund(
                settlement_id=settlement.id,
                requested_amount=Decimal("10000.00"),
                payout_currency=s['egp'],
                method="CRYPTOCURRENCY",  # وسيلة غير معتمدة
                payment_account=s['cash_acc'],
                idempotency_key="INVALID-METHOD-01",
                user=s['admin']
            )
        assert "غير مقبولة" in str(exc.value)
        assert RefundDisbursementPayment.objects.filter(idempotency_key="INVALID-METHOD-01").count() == 0

    def test_idempotency_fingerprint_mismatch_guard(self, hardened_setup):
        """اختبار البصمة الشاملة لمفتاح التكرار وصد استخدام نفس المفتاح بمعلمات مختلفة"""
        s = hardened_setup
        booking = UnitBookingService.create_booking(
            unit_id=s['unit1'].id, customer=s['cust1'],
            holding_deposit=Decimal("30000.00"),
            expiry_date=timezone.localdate() + timedelta(days=7),
            user=s['admin']
        )
        settlement = BookingCancellationSettlement.objects.create(
            booking=booking, currency=s['egp'],
            total_deposit_paid=Decimal("30000.00"),
            net_refundable_amount=Decimal("30000.00"),
            remaining_disbursable_amount=Decimal("30000.00"),
            processed_by=s['admin']
        )
        booking.active_cancellation_settlement = settlement
        booking.save()

        # 1. صرف أولي ناجح بمفتاح معين
        pay1 = RealEstateAccountingService.disburse_refund(
            settlement_id=settlement.id,
            requested_amount=Decimal("10000.00"),
            payout_currency=s['egp'],
            method=RefundDisbursementPayment.DisbursementMethod.CASH,
            payment_account=s['cash_acc'],
            idempotency_key="SHARED-IDEMP-KEY-01",
            user=s['admin']
        )
        assert pay1.id is not None

        # 2. محاولة استخدام نفس المفتاح مع تغيير المبلغ -> يجب الرفض بتعارض البصمة
        with pytest.raises(ValidationError) as exc:
            RealEstateAccountingService.disburse_refund(
                settlement_id=settlement.id,
                requested_amount=Decimal("15000.00"),  # مبلغ مختلف
                payout_currency=s['egp'],
                method=RefundDisbursementPayment.DisbursementMethod.CASH,
                payment_account=s['cash_acc'],
                idempotency_key="SHARED-IDEMP-KEY-01",
                user=s['admin']
            )
        assert "تعارض في مفتاح منع التكرار" in str(exc.value)

    def test_cross_currency_cash_disbursement_with_realized_fx(self, hardened_setup):
        """اختبار تكاملي: استرداد أمانات بالدولار وصرفها بالجنيه نقدياً مع قيد فروق عملة محققة متوازن"""
        s = hardened_setup
        # أمانات حجز 1,000 USD بسعر تاريخي 48 EGP
        booking = UnitBookingService.create_booking(
            unit_id=s['unit1'].id, customer=s['cust1'],
            holding_deposit=Decimal("1000.00"),
            currency=s['usd'],
            exchange_rate=Decimal("48.000000"),
            expiry_date=timezone.localdate() + timedelta(days=7),
            user=s['admin']
        )
        settlement = BookingCancellationSettlement.objects.create(
            booking=booking, currency=s['usd'],
            exchange_rate=Decimal("48.000000"),
            total_deposit_paid=Decimal("1000.00"),
            net_refundable_amount=Decimal("1000.00"),
            remaining_disbursable_amount=Decimal("1000.00"),
            processed_by=s['admin']
        )
        booking.active_cancellation_settlement = settlement
        booking.save()

        # سعر الصرف الحالي في النظام 50.00 EGP لكل USD
        # صرف 50,000 EGP نقداً (معادل 1,000 USD بالكامل)
        payment = RealEstateAccountingService.disburse_refund(
            settlement_id=settlement.id,
            requested_amount=Decimal("50000.00"),
            payout_currency=s['egp'],
            method=RefundDisbursementPayment.DisbursementMethod.CASH,
            payment_account=s['cash_acc'],
            idempotency_key="CASH-FX-KEY-01",
            user=s['admin']
        )

        assert payment.status == RefundDisbursementPayment.PaymentStatus.CLEARED
        assert payment.realized_fx_gain_loss == Decimal("2000.00")  # 50,000 - 48,000 = 2,000 EGP خسارة فروق عملة
        assert payment.journal_entry is not None

        je = payment.journal_entry
        assert je.is_balanced is True

        lines = je.lines.all()
        # التحقق من أطراف القيد:
        # مدين أمانات 48,000 (معادل 1,000 USD)
        adv_line = lines.get(account=s['advance_acc'])
        assert adv_line.debit == Decimal("48000.00")
        assert adv_line.foreign_debit == Decimal("1000.00")
        assert adv_line.currency == s['usd'].code

        # دائن الخزينة 50,000
        cash_line = lines.get(account=s['cash_acc'])
        assert cash_line.credit == Decimal("50000.00")

        # مدين خسائر فروق العملة 2,000
        fx_line = lines.get(account=s['fx_loss_acc'])
        assert fx_line.debit == Decimal("2000.00")

        settlement.refresh_from_db()
        assert settlement.remaining_disbursable_amount == Decimal("0.00")
        assert settlement.status == BookingCancellationSettlement.SettlementStatus.FULLY_DISBURSED

    def test_two_way_sync_cheque_bounced_to_cancelled_no_double_reversal(self, hardened_setup):
        """اختبار منع العكس المزدوج والتأكد من عدم تكرار قيد الإلغاء عند تحول الشيك من BOUNCED إلى CANCELLED"""
        s = hardened_setup
        booking = UnitBookingService.create_booking(
            unit_id=s['unit1'].id, customer=s['cust1'],
            holding_deposit=Decimal("60000.00"),
            expiry_date=timezone.localdate() + timedelta(days=7),
            user=s['admin']
        )
        settlement = BookingCancellationSettlement.objects.create(
            booking=booking, currency=s['egp'],
            total_deposit_paid=Decimal("60000.00"),
            net_refundable_amount=Decimal("60000.00"),
            remaining_disbursable_amount=Decimal("60000.00"),
            processed_by=s['admin']
        )
        booking.active_cancellation_settlement = settlement
        booking.save()

        # إصدار شيك
        payment = RealEstateAccountingService.disburse_refund(
            settlement_id=settlement.id,
            requested_amount=Decimal("60000.00"),
            payout_currency=s['egp'],
            method=RefundDisbursementPayment.DisbursementMethod.CHEQUE,
            payment_account=s['bank_acc'],
            cheque_data={'cheque_number': 'CHQ-DOUBLE-REV-01', 'drawer_bank_name': 'Commercial Bank'},
            idempotency_key="CHQ-DOUBLE-REV-KEY",
            user=s['admin']
        )
        cheque = payment.cheque

        # 1. ارتداد الشيك -> تنفيذ القيد العكسي واستعادة الرصيد
        ChequeAccountingService.bounce_cheque(cheque=cheque, reason="Signature mismatch", user=s['admin'])
        payment.refresh_from_db()
        settlement.refresh_from_db()
        assert payment.status == RefundDisbursementPayment.PaymentStatus.BOUNCED
        assert settlement.remaining_disbursable_amount == Decimal("60000.00")
        rev_je_id = payment.reversal_journal_entry_id
        assert rev_je_id is not None

        # 2. إلغاء الشيك المرتد -> يجب ألا يعكس القيد مرة ثانية وألا يضاعف الرصيد المسترد
        ChequeAccountingService.cancel_cheque(cheque=cheque, reason="Cancelled permanently", user=s['admin'])
        payment.refresh_from_db()
        settlement.refresh_from_db()
        assert payment.status == RefundDisbursementPayment.PaymentStatus.CANCELLED
        assert payment.reversal_journal_entry_id == rev_je_id  # نفس قيد العكس السابق دون تكرار
        assert settlement.remaining_disbursable_amount == Decimal("60000.00")  # لم يتضاعف إلى 120,000

    def test_whatsapp_message_log_in_flight_idempotency(self, hardened_setup):
        """اختبار حوكمة إشعارات الواتساب وتسجيل حالة IN_FLIGHT ومفتاح event_idempotency_key"""
        event_key = f"WA:REFUND_CHQ:BKG-101:{uuid.uuid4().hex[:8]}"
        log = WhatsAppMessageLog.objects.create(
            recipient_phone="+201012345678",
            template_name="refund_cheque_issued",
            event_idempotency_key=event_key,
            status='IN_FLIGHT',
            body_text="صرف شيك استرداد"
        )

        assert log.status == 'IN_FLIGHT'
        assert log.event_idempotency_key == event_key

        # محاولة إنشاء سجل بنفس المفتاح تمنع الازدواجية بفضل القيد الفريد
        with pytest.raises(Exception):
            WhatsAppMessageLog.objects.create(
                recipient_phone="+201012345678",
                template_name="refund_cheque_issued",
                event_idempotency_key=event_key,
                status='IN_FLIGHT'
            )

    def test_query_budget_tower_sales_brief_report(self, hardened_setup):
        """اختبار ميزانية الاستعلامات: التحقق من عدم وجود N+1 Query في تقرير الموقف ومبيعات الأبراج"""
        s = hardened_setup
        # إنشاء 10 وحدات إضافية
        for i in range(1, 11):
            PropertyUnit.objects.create(
                project=s['project'], block=s['block'], floor=s['floor'],
                unit_code=f"HD-TEST-U{i:02d}",
                unit_type=PropertyUnit.UnitType.APARTMENT,
                net_area=Decimal("100.00"), gross_area=Decimal("120.00"),
                meter_price=Decimal("20000.00"), base_price=Decimal("2400000.00"),
                status=PropertyUnit.UnitStatus.AVAILABLE
            )

        # قياس عدد الاستعلامات أثناء تشغيل تقرير الموقف للبرج
        with CaptureQueriesContext(connection) as ctx:
            report = RealEstateReportingService.get_tower_sales_brief_report(block_id=s['block'].id)
            assert report['total_units_count'] >= 12
            assert len(report['unit_rows']) >= 12

        # يجب ألا يتجاوز عدد الاستعلامات حداً معقولاً (ميزانية صارمة < 25 استعلاماً مهما زاد عدد الوحدات)
        query_count = len(ctx.captured_queries)
        assert query_count < 25, f"Query count too high: {query_count} queries executed (N+1 danger!)"
