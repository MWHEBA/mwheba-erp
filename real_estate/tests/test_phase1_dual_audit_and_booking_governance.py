# -*- coding: utf-8 -*-
"""
Tests for Phase 1: Dual-Audit Governance, SoD Enforcement, and Booking Official Printout
MWHEBA ERP - Real Estate Track 4 Parity
"""
from decimal import Decimal
import datetime
import pytest
from django.utils import timezone
from django.core.exceptions import PermissionDenied, ValidationError
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.test import Client

from core.models import SystemModule
from customer.models import Customer
from financial.models import Currency, ChartOfAccounts, AccountType
from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyFloor,
    PropertyUnit,
    UnitBooking,
)
from real_estate.services.booking_service import UnitBookingService, BookingValidationError

User = get_user_model()


@pytest.fixture
def phase1_setup(db):
    SystemModule.objects.update_or_create(
        code='real_estate',
        defaults={'name_ar': 'القطاع العقاري', 'is_enabled': True}
    )

    user_admin = User.objects.create_superuser(username='p1_admin', password='password123', email='p1_admin@test.com')
    user_creator = User.objects.create_user(username='p1_creator', password='password123', email='p1_creator@test.com')
    user_reviewer = User.objects.create_user(username='p1_reviewer', password='password123', email='p1_reviewer@test.com')
    user_auditor = User.objects.create_user(username='p1_auditor', password='password123', email='p1_auditor@test.com')
    user_regular = User.objects.create_user(username='p1_regular', password='password123', email='p1_regular@test.com')

    change_perm = Permission.objects.get(codename='change_unitbooking', content_type__app_label='real_estate')
    view_perm = Permission.objects.get(codename='view_unitbooking', content_type__app_label='real_estate')
    add_perm = Permission.objects.get(codename='add_unitbooking', content_type__app_label='real_estate')

    for u in (user_creator, user_reviewer, user_auditor):
        u.user_permissions.add(change_perm, view_perm, add_perm)

    asset_type, _ = AccountType.objects.get_or_create(code="ASSET", defaults={"name": "أصول", "category": "asset", "nature": "debit"})
    liability_type, _ = AccountType.objects.get_or_create(code="LIABILITY", defaults={"name": "خصوم", "category": "liability", "nature": "credit"})

    egp, _ = Currency.objects.get_or_create(
        code='EGP',
        defaults={'name': 'Egyptian Pound', 'symbol': '£', 'is_functional': True, 'decimal_places': 2}
    )

    cash_acc, _ = ChartOfAccounts.objects.get_or_create(
        code='11101',
        defaults={'name': 'الخزينة الرئيسية', 'account_type': asset_type, 'currency': egp, 'is_active': True, 'is_leaf': True}
    )
    holding_deposit_acc, _ = ChartOfAccounts.objects.get_or_create(
        code='11410',
        defaults={'name': 'أمانات حجز وحدات عقارية', 'account_type': liability_type, 'currency': egp, 'is_active': True, 'is_leaf': True}
    )

    project = RealEstateProject.objects.create(
        name="برج الموهبة 1",
        code="PRJ-P1",
        start_date=timezone.localdate(),
        expected_completion_date=timezone.localdate() + datetime.timedelta(days=730),
        created_by=user_admin
    )
    block = PropertyBlock.objects.create(project=project, name="عمارة أ", code="BLK-A")
    floor = PropertyFloor.objects.create(block=block, floor_number=1, name="الدور الأول")
    unit = PropertyUnit.objects.create(
        project=project,
        floor=floor,
        unit_code="U-P1-101",
        unit_type="APARTMENT",
        net_area=Decimal('120.00'),
        gross_area=Decimal('150.00'),
        meter_price=Decimal('10000.00'),
        base_price=Decimal('1500000.00'),
        total_price=Decimal('1500000.00'),
        status=PropertyUnit.UnitStatus.AVAILABLE
    )

    customer = Customer.objects.create(
        name="أحمد محمود السيد",
        code="CUST-P1-001",
        phone="01012345678"
    )

    # إنشاء حجز نشط عبر user_creator
    booking = UnitBookingService.create_booking(
        unit_id=unit.id,
        customer=customer,
        holding_deposit=Decimal('50000.00'),
        expiry_date=timezone.localdate() + datetime.timedelta(days=14),
        user=user_creator,
        payment_account=cash_acc,
    )

    return {
        'admin': user_admin,
        'creator': user_creator,
        'reviewer': user_reviewer,
        'auditor': user_auditor,
        'regular': user_regular,
        'project': project,
        'unit': unit,
        'customer': customer,
        'booking': booking,
        'cash_acc': cash_acc,
        'holding_deposit_acc': holding_deposit_acc,
    }


def test_review_booking_sales_lifecycle_and_sod(phase1_setup):
    s = phase1_setup
    booking = s['booking']

    # 1. منع منشئ الحجز من مراجعة حجزه بنفسه (SoD)
    with pytest.raises(BookingValidationError) as exc:
        UnitBookingService.review_booking_sales(booking.id, user=s['creator'])
    assert "قيد الفصل الرقابي" in str(exc.value)

    # 2. قيام مراجع مستقل بالمراجعة بنجاح
    reviewed = UnitBookingService.review_booking_sales(booking.id, user=s['reviewer'])
    assert reviewed.is_reviewed_sales is True
    assert reviewed.reviewed_by == s['reviewer']
    assert reviewed.reviewed_at is not None


def test_confirm_booking_audit_lifecycle_and_sod(phase1_setup):
    s = phase1_setup
    booking = s['booking']

    # 1. محاولة الاعتماد الرقابي قبل مراجعة المبيعات -> فشل إلزامي
    with pytest.raises(BookingValidationError) as exc:
        UnitBookingService.confirm_booking_audit(booking.id, user=s['auditor'])
    assert "لا يجوز الاعتماد الرقابي لحجز لم تستوفَ فيه مراجعة المبيعات أولاً" in str(exc.value)

    # 2. مراجعة المبيعات أولاً
    UnitBookingService.review_booking_sales(booking.id, user=s['reviewer'])
    booking.refresh_from_db()

    # 3. منع مراجع المبيعات من اعتماد الرقابة بنفسه (SoD)
    with pytest.raises(BookingValidationError) as exc:
        UnitBookingService.confirm_booking_audit(booking.id, user=s['reviewer'])
    assert "قيد الفصل الرقابي" in str(exc.value)

    # 4. منع منشئ الحجز من اعتماد الرقابة بنفسه (SoD)
    with pytest.raises(BookingValidationError) as exc:
        UnitBookingService.confirm_booking_audit(booking.id, user=s['creator'])
    assert "قيد الفصل الرقابي" in str(exc.value)

    # 5. قيام مدقق رقابي مستقل بالاعتماد بنجاح
    confirmed = UnitBookingService.confirm_booking_audit(booking.id, user=s['auditor'])
    assert confirmed.is_confirmed_audit is True
    assert confirmed.confirmed_by == s['auditor']
    assert confirmed.confirmed_at is not None


def test_bypass_booking_audit_authorization_and_validation(phase1_setup):
    s = phase1_setup
    booking = s['booking']

    # 1. مستخدم غير مخول يحاول التجاوز -> رفض PermissionDenied
    with pytest.raises(PermissionDenied):
        UnitBookingService.bypass_booking_audit(booking.id, user=s['regular'], reason="ظرف طارئ")

    # 2. التجاوز بسبب فارغ -> رفض ValidationError
    with pytest.raises(BookingValidationError):
        UnitBookingService.bypass_booking_audit(booking.id, user=s['admin'], reason="   ")

    # 3. سوبر يوزر يتجاوز مع توثيق السبب -> نجاح كامل
    bypassed = UnitBookingService.bypass_booking_audit(
        booking.id,
        user=s['admin'],
        reason="موافقة رئيس مجلس الإدارة رقم 104"
    )
    assert bypassed.audit_bypassed is True
    assert bypassed.audit_bypassed_by == s['admin']
    assert bypassed.audit_bypass_reason == "موافقة رئيس مجلس الإدارة رقم 104"


def test_booking_detail_view_post_review_and_audit(phase1_setup):
    s = phase1_setup
    booking = s['booking']
    client = Client()

    url = reverse('real_estate:booking_detail', kwargs={'pk': booking.id})

    # POST action=review_sales بواسطة reviewer
    client.force_login(s['reviewer'])
    res_review = client.post(url, {'action': 'review_sales'})
    assert res_review.status_code == 302
    booking.refresh_from_db()
    assert booking.is_reviewed_sales is True

    # POST action=confirm_audit بواسطة auditor
    client.force_login(s['auditor'])
    res_audit = client.post(url, {'action': 'confirm_audit'})
    assert res_audit.status_code == 302
    booking.refresh_from_db()
    assert booking.is_confirmed_audit is True


def test_booking_detail_view_post_bypass(phase1_setup):
    s = phase1_setup
    booking = s['booking']
    client = Client()

    url = reverse('real_estate:booking_detail', kwargs={'pk': booking.id})
    client.force_login(s['admin'])

    res_bypass = client.post(url, {
        'action': 'bypass_audit',
        'bypass_reason': 'تجاوز معتمد من الإدارة العليا'
    })
    assert res_bypass.status_code == 302
    booking.refresh_from_db()
    assert booking.audit_bypassed is True
    assert booking.audit_bypass_reason == 'تجاوز معتمد من الإدارة العليا'


def test_convert_booking_unlocked_after_dual_audit(phase1_setup):
    s = phase1_setup
    booking = s['booking']

    # محاولة التحويل قبل الاعتماد -> تفشل
    with pytest.raises(BookingValidationError) as exc:
        UnitBookingService.convert_booking_to_contract(booking.id, user=s['admin'])
    assert "الاعتماد المالي والرقابي الثنائي" in str(exc.value)

    # إتمام الرقابة الثنائية
    UnitBookingService.review_booking_sales(booking.id, user=s['reviewer'])
    UnitBookingService.confirm_booking_audit(booking.id, user=s['auditor'])
    booking.refresh_from_db()

    # الآن التحويل ينجح 100%
    contract = UnitBookingService.convert_booking_to_contract(booking.id, user=s['admin'])
    assert contract is not None
    assert contract.status == contract.ContractStatus.ACTIVE
    booking.refresh_from_db()
    assert booking.status == UnitBooking.BookingStatus.CONVERTED_TO_CONTRACT


def test_booking_print_view_renders_legal_payment_instrument(phase1_setup):
    s = phase1_setup
    booking = s['booking']
    client = Client()
    client.force_login(s['admin'])

    url = reverse('real_estate:booking_print', kwargs={'pk': booking.id})
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode('utf-8')
    assert "بيان دفعة جدية الحجز وسند السداد المالي" in content
    assert "حساب التحصيل (الخزينة/البنك)" in content
    assert "حجية إيصال الأمانة" in content
    assert "الخزينة الرئيسية" in content
