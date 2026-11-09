# -*- coding: utf-8 -*-
"""
Tests for Track 4 Slice 3: Views, Modals, 405 Fixes, QR & Public Verification Portal
"""
import uuid
from decimal import Decimal
from datetime import timedelta
import pytest
from django.utils import timezone
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.test import Client

from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyFloor,
    PropertyUnit,
    UnitBooking,
    PropertyContract,
    BookingCancellationSettlement,
    RefundDisbursementPayment,
)
from core.models import SystemModule
from customer.models import Customer
from financial.models import Currency, ChartOfAccounts, AccountType
from financial.services.exchange_rate_service import ExchangeRateService
from real_estate.services.booking_service import UnitBookingService

User = get_user_model()


@pytest.fixture
def slice3_setup(db):
    user = User.objects.create_superuser(username='slice3_admin', password='password123', email='admin@test.com')

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
    contract_liab, _ = ChartOfAccounts.objects.get_or_create(
        code='21102',
        defaults={'name': 'التزامات عقود العملاء', 'account_type': liability_type, 'currency': egp, 'is_active': True, 'is_leaf': True}
    )
    ChartOfAccounts.objects.get_or_create(
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
    ChartOfAccounts.objects.get_or_create(
        code='54300',
        defaults={'name': 'خسائر فروق عملة محققة', 'account_type': expense_type, 'currency': egp, 'is_active': True, 'is_leaf': True}
    )
    ChartOfAccounts.objects.get_or_create(
        code='43100',
        defaults={'name': 'أرباح فروق عملة محققة', 'account_type': revenue_type, 'currency': egp, 'is_active': True, 'is_leaf': True}
    )
    ChartOfAccounts.objects.get_or_create(
        code='54400',
        defaults={'name': 'أرباح وخسائر تقريب العملات', 'account_type': expense_type, 'currency': egp, 'is_active': True, 'is_leaf': True}
    )
    other_asset, _ = ChartOfAccounts.objects.get_or_create(
        code='12101',
        defaults={'name': 'أصول ثابتة - سيارات', 'account_type': asset_type, 'currency': egp, 'is_active': True, 'is_leaf': True}
    )

    project = RealEstateProject.objects.create(
        name="Slice 3 Elite Tower",
        code="SL3-PRJ",
        start_date=timezone.localdate(),
        expected_completion_date=timezone.localdate() + timedelta(days=730),
        created_by=user
    )
    block = PropertyBlock.objects.create(
        project=project,
        code="BLK-SL3",
        name="Block SL3"
    )
    floor = PropertyFloor.objects.create(
        block=block,
        floor_number=1,
        name="Floor 1"
    )
    unit = PropertyUnit.objects.create(
        project=project,
        block=block,
        floor=floor,
        unit_code="SL3-U101",
        unit_type=PropertyUnit.UnitType.APARTMENT,
        net_area=Decimal("120.00"),
        gross_area=Decimal("140.00"),
        meter_price=Decimal("25000.00"),
        base_price=Decimal("3000000.00"),
        status=PropertyUnit.UnitStatus.AVAILABLE
    )

    customer = Customer.objects.create(
        name="محمود أحمد الشناوي",
        code="CUST-SL3-01",
        phone="01012345678",
        email="customer.sl3@test.com"
    )

    client = Client()
    client.force_login(user)

    return {
        'user': user,
        'client': client,
        'egp': egp,
        'usd': usd,
        'project': project,
        'unit': unit,
        'customer': customer,
        'cash_acc': cash_acc,
        'bank_acc': bank_acc,
        'other_asset': other_asset,
        'advance_acc': advance_acc,
        'contract_liab': contract_liab,
    }


@pytest.mark.django_db
class TestContractCreateViewEnhancements:
    """اختبارات شاشة إبرام العقد وتحويل الحجز مع التعديلات الجديدة"""

    def test_get_contract_create_view_with_booking(self, slice3_setup):
        s = slice3_setup
        # إنشاء حجز نشط معتمد
        booking = UnitBooking.objects.create(
            booking_number="BKG-SL3-001",
            unit=s['unit'],
            customer=s['customer'],
            holding_deposit=Decimal("100000.00"),
            currency=s['egp'],
            status=UnitBooking.BookingStatus.ACTIVE,
            booking_date=timezone.localdate(),
            expiry_date=timezone.localdate() + timedelta(days=14),
            is_confirmed_audit=True,
            created_by=s['user']
        )
        s['unit'].status = PropertyUnit.UnitStatus.RESERVED
        s['unit'].save(update_fields=['status'])

        url = reverse('real_estate:contract_create') + f"?booking_id={booking.id}"
        response = s['client'].get(url)

        assert response.status_code == 200
        assert response.context['selected_booking'] == booking
        # التأكد من إدراج الوحدة المحجوزة ضمن الوحدات المتاحة للاختيار
        assert s['unit'] in response.context['available_units']
        # التأكد من حصر الحسابات المالية على حسابات السيولة النقدية والمصرفية (111xx)
        payment_accounts = response.context['payment_accounts']
        assert s['cash_acc'] in payment_accounts
        assert s['bank_acc'] in payment_accounts
        assert s['other_asset'] not in payment_accounts

    def test_post_contract_create_converts_confirmed_booking(self, slice3_setup):
        s = slice3_setup
        booking = UnitBookingService.create_booking(
            unit_id=s['unit'].id,
            customer=s['customer'],
            holding_deposit=Decimal("100000.00"),
            expiry_date=timezone.localdate() + timedelta(days=14),
            user=s['user']
        )
        booking.is_confirmed_audit = True
        booking.confirmed_by = s['user']
        booking.confirmed_at = timezone.now()
        booking.save()

        url = reverse('real_estate:contract_create')
        post_data = {
            'booking_id': str(booking.id),
            'final_contract_price': '3000000.00',
            'down_payment': '300000.00',
            'contract_tax_structure': PropertyContract.ContractTaxStructure.SPLIT_SPA_FINISHING_ANNEX,
            'primary_owner_share': '100.00',
            'payment_account': str(s['cash_acc'].id),
        }
        response = s['client'].post(url, post_data)

        # يجب إعادة التوجيه لشاشة العقد بعد النجاح
        assert response.status_code == 302
        booking.refresh_from_db()
        assert booking.status == UnitBooking.BookingStatus.CONVERTED_TO_CONTRACT
        s['unit'].refresh_from_db()
        assert s['unit'].status == PropertyUnit.UnitStatus.CONTRACTED

        contract = PropertyContract.objects.get(unit=s['unit'])
        assert contract.contract_tax_structure == PropertyContract.ContractTaxStructure.SPLIT_SPA_FINISHING_ANNEX
        assert contract.final_contract_price == Decimal('3000000.00')

    def test_post_contract_create_rejects_unconfirmed_booking(self, slice3_setup):
        s = slice3_setup
        booking = UnitBooking.objects.create(
            booking_number="BKG-SL3-003",
            unit=s['unit'],
            customer=s['customer'],
            holding_deposit=Decimal("50000.00"),
            currency=s['egp'],
            status=UnitBooking.BookingStatus.ACTIVE,
            booking_date=timezone.localdate(),
            expiry_date=timezone.localdate() + timedelta(days=14),
            is_confirmed_audit=False,  # غير معتمد رقابياً
            audit_bypassed=False,
            is_legacy_pre_audit=False,
            created_by=s['user']
        )

        url = reverse('real_estate:contract_create')
        post_data = {
            'booking_id': str(booking.id),
            'final_contract_price': '3000000.00',
        }
        response = s['client'].post(url, post_data)

        # يجب رفض العملية وإعادة التوجيه لصفحة الحجز مع رسالة خطأ
        assert response.status_code == 302
        assert response.url == reverse('real_estate:booking_detail', kwargs={'pk': booking.pk})
        booking.refresh_from_db()
        assert booking.status == UnitBooking.BookingStatus.ACTIVE
        assert PropertyContract.objects.filter(unit=s['unit']).count() == 0


@pytest.mark.django_db
class TestBookingDetailViewEliminationOf405:
    """اختبارات القضاء على خطأ 405 ودعم الإلغاء والاسترداد عبر POST في BookingDetailView"""

    def test_get_booking_detail_filters_payment_accounts(self, slice3_setup):
        s = slice3_setup
        booking = UnitBooking.objects.create(
            booking_number="BKG-SL3-004",
            unit=s['unit'],
            customer=s['customer'],
            holding_deposit=Decimal("60000.00"),
            currency=s['egp'],
            status=UnitBooking.BookingStatus.ACTIVE,
            booking_date=timezone.localdate(),
            expiry_date=timezone.localdate() + timedelta(days=14),
            is_confirmed_audit=True,
            created_by=s['user']
        )
        url = reverse('real_estate:booking_detail', kwargs={'pk': booking.pk})
        response = s['client'].get(url)

        assert response.status_code == 200
        payment_accounts = response.context['payment_accounts']
        assert s['cash_acc'] in payment_accounts
        assert s['bank_acc'] in payment_accounts
        assert s['other_asset'] not in payment_accounts

    def test_post_cancel_booking_fallback_no_405(self, slice3_setup):
        s = slice3_setup
        booking = UnitBookingService.create_booking(
            unit_id=s['unit'].id,
            customer=s['customer'],
            holding_deposit=Decimal("80000.00"),
            expiry_date=timezone.localdate() + timedelta(days=14),
            user=s['user']
        )

        url = reverse('real_estate:booking_detail', kwargs={'pk': booking.pk})
        post_data = {
            'action': 'cancel',
            'reason': 'عدم الاتفاق على جدول السداد',
            'disposition': 'REFUND',
        }
        # تنفيذ POST عادي بدون AJAX - يجب ألا يعود بـ 405 Method Not Allowed
        response = s['client'].post(url, post_data)

        assert response.status_code == 302
        assert response.url == reverse('real_estate:booking_detail', kwargs={'pk': booking.pk})

        booking.refresh_from_db()
        assert booking.status == UnitBooking.BookingStatus.CANCELLED_PENDING_REFUND
        s['unit'].refresh_from_db()
        assert s['unit'].status == PropertyUnit.UnitStatus.AVAILABLE

    def test_post_refund_booking_fallback_no_405(self, slice3_setup):
        s = slice3_setup
        booking = UnitBookingService.create_booking(
            unit_id=s['unit'].id,
            customer=s['customer'],
            holding_deposit=Decimal("80000.00"),
            expiry_date=timezone.localdate() + timedelta(days=14),
            user=s['user']
        )
        # إلغاء الحجز أولاً مع تعليق الاسترداد
        UnitBookingService.cancel_booking(
            booking_id=booking.id,
            reason="طلب استرداد المبلغ",
            forfeit_deposit=False,
            user=s['user']
        )
        booking.refresh_from_db()
        assert booking.status == UnitBooking.BookingStatus.CANCELLED_PENDING_REFUND

        url = reverse('real_estate:booking_detail', kwargs={'pk': booking.pk})
        post_data = {
            'action': 'refund',
            'refund_account': str(s['cash_acc'].id),
        }
        # تنفيذ POST للاسترداد - يجب ألا يعود بـ 405 أبداً
        response = s['client'].post(url, post_data)

        assert response.status_code == 302
        assert response.url == reverse('real_estate:booking_detail', kwargs={'pk': booking.pk})

        booking.refresh_from_db()
        assert booking.status == UnitBooking.BookingStatus.CANCELLED_REFUNDED


@pytest.mark.django_db
class TestBookingPublicVerificationAndPrintView:
    """اختبارات بوابة التحقق الرقمي العامة وطباعة الاستمارة الرسمية ورمز QR"""

    def test_public_verification_view_valid_active_booking(self, slice3_setup):
        s = slice3_setup
        booking = UnitBooking.objects.create(
            booking_number="BKG-SL3-PUB-01",
            unit=s['unit'],
            customer=s['customer'],
            holding_deposit=Decimal("150000.00"),
            currency=s['egp'],
            status=UnitBooking.BookingStatus.ACTIVE,
            booking_date=timezone.localdate(),
            expiry_date=timezone.localdate() + timedelta(days=14),
            is_confirmed_audit=True,
            created_by=s['user']
        )

        unauth_client = Client()  # عميل عام بدون تسجيل دخول
        url = reverse('real_estate:booking_public_verify', kwargs={'token': booking.verification_uuid})
        response = unauth_client.get(url)

        assert response.status_code == 200
        content = response.content.decode('utf-8')
        # التحقق من إخفاء اسم العميل جزئياً لحماية الخصوصية (Masking)
        assert "محمود ***** الشناوي" in content or "محمود" in content
        assert "01012345678" not in content  # رقم الهاتف لا يظهر للعامة
        assert "BKG-SL3-PUB-01" in content
        assert "SL3-U101" in content
        assert "150,000" in content or "150000" in content

    def test_public_verification_view_shows_warning_for_cancelled_booking(self, slice3_setup):
        s = slice3_setup
        booking = UnitBooking.objects.create(
            booking_number="BKG-SL3-PUB-02",
            unit=s['unit'],
            customer=s['customer'],
            holding_deposit=Decimal("75000.00"),
            currency=s['egp'],
            status=UnitBooking.BookingStatus.CANCELLED_PENDING_REFUND,
            booking_date=timezone.localdate(),
            expiry_date=timezone.localdate() + timedelta(days=14),
            is_confirmed_audit=True,
            created_by=s['user']
        )

        unauth_client = Client()
        url = reverse('real_estate:booking_public_verify', kwargs={'token': booking.verification_uuid})
        response = unauth_client.get(url)

        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert "ملغاة" in content or "CANCELLED" in content
        assert "تنبيه" in content or "alert" in content

    def test_public_verification_view_invalid_uuid_returns_404(self, slice3_setup):
        unauth_client = Client()
        fake_token = uuid.uuid4()
        url = reverse('real_estate:booking_public_verify', kwargs={'token': fake_token})
        response = unauth_client.get(url)

        assert response.status_code == 404

    def test_booking_official_print_view_contains_qr_and_watermark(self, slice3_setup):
        s = slice3_setup
        booking = UnitBooking.objects.create(
            booking_number="BKG-SL3-PRINT-01",
            unit=s['unit'],
            customer=s['customer'],
            holding_deposit=Decimal("90000.00"),
            currency=s['egp'],
            status=UnitBooking.BookingStatus.CANCELLED_REFUNDED,
            booking_date=timezone.localdate(),
            expiry_date=timezone.localdate() + timedelta(days=14),
            is_confirmed_audit=True,
            created_by=s['user']
        )

        url = reverse('real_estate:booking_print', kwargs={'pk': booking.pk})
        response = s['client'].get(url)

        assert response.status_code == 200
        assert 'qr_code_base64' in response.context
        assert len(response.context['qr_code_base64']) > 50
        content = response.content.decode('utf-8')
        assert "data:image/png;base64," in content
        assert "watermark-cancelled" in content
