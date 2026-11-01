# -*- coding: utf-8 -*-
"""
Tests for Independent Audit Remediation:
1. Deriving verified contract down payment and preventing clearance on uncollected down payments.
2. Independent financial disbursement permission for booking refund (blocking change_unitbooking alone).
3. Rescuing expired bookings with collected deposits from being trapped outside the refund lifecycle.
"""
from decimal import Decimal
import datetime
import pytest
from django.utils import timezone
from django.core.exceptions import ValidationError, PermissionDenied
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import RequestFactory

from customer.models import Customer
from financial.models.currency import Currency
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyFloor,
    PropertyUnit,
    PropertyContract,
    UnitBooking
)
from real_estate.services.booking_service import UnitBookingService, BookingValidationError
from real_estate.services.booking_sweep_service import UnitBookingSweepService
from real_estate.services.clearance_service import ContractDebtClearanceService
from real_estate.services.accounting_service import RealEstateAccountingService
from real_estate.views.matrix_views import ApiCancelBookingView, ApiRefundBookingView

User = get_user_model()


@pytest.fixture
def audit_setup(db):
    user_admin = User.objects.create_superuser(
        username="admin_audit",
        email="admin_audit@example.com",
        password="password123"
    )

    user_sales = User.objects.create_user(
        username="sales_rep",
        email="sales@example.com",
        password="password123"
    )
    # منح المستخدم العادي صلاحية تعديل الحجز فقط دون صلاحيات مالية
    perm_change_booking = Permission.objects.get(codename='change_unitbooking', content_type__app_label='real_estate')
    user_sales.user_permissions.add(perm_change_booking)

    user_finance = User.objects.create_user(
        username="finance_officer",
        email="finance@example.com",
        password="password123"
    )
    perm_refund_booking = Permission.objects.get(codename='refund_unitbooking', content_type__app_label='real_estate')
    user_finance.user_permissions.add(perm_refund_booking)

    asset_type, _ = AccountType.objects.get_or_create(
        code='asset',
        defaults={'name': 'أصول', 'category': 'asset', 'nature': 'debit'}
    )
    liability_type, _ = AccountType.objects.get_or_create(
        code='liability',
        defaults={'name': 'التزامات', 'category': 'liability', 'nature': 'credit'}
    )
    revenue_type, _ = AccountType.objects.get_or_create(
        code='revenue',
        defaults={'name': 'إيرادات', 'category': 'revenue', 'nature': 'credit'}
    )

    egp_currency, _ = Currency.objects.get_or_create(
        code="EGP",
        defaults={'name': "Egyptian Pound", 'symbol': "ج.م", 'is_functional': True}
    )

    treasury_account, _ = ChartOfAccounts.objects.get_or_create(
        code='11101',
        defaults={
            'name': 'الخزينة الرئيسية',
            'account_type': asset_type,
            'currency': egp_currency,
            'is_leaf': True,
            'is_active': True
        }
    )
    ChartOfAccounts.objects.get_or_create(
        code='21101',
        defaults={
            'name': 'أمانات ودفعات حجز العملاء',
            'account_type': liability_type,
            'currency': egp_currency,
            'is_leaf': True,
            'is_active': True
        }
    )
    ChartOfAccounts.objects.get_or_create(
        code='21102',
        defaults={
            'name': 'التزامات عقود بيع وحدات - دفعات مقدمة',
            'account_type': liability_type,
            'currency': egp_currency,
            'is_leaf': True,
            'is_active': True
        }
    )
    ChartOfAccounts.objects.get_or_create(
        code='42201',
        defaults={
            'name': 'إيرادات غرامات ومصادرات إلغاء حجز الوحدات',
            'account_type': revenue_type,
            'currency': egp_currency,
            'is_leaf': True,
            'is_active': True
        }
    )

    customer = Customer.objects.create(
        code="CUST-AUDIT-01",
        name="عميل اختبار التدقيق",
        customer_type="INDIVIDUAL"
    )

    project = RealEstateProject.objects.create(
        name="مشروع أبراج التدقيق",
        code="PRJ-AUDIT",
        project_type=RealEstateProject.ProjectType.RESIDENTIAL,
        status=RealEstateProject.ProjectStatus.UNDER_CONSTRUCTION,
        start_date=timezone.localdate(),
        expected_completion_date=timezone.localdate() + datetime.timedelta(days=365),
        created_by=user_admin
    )
    block = PropertyBlock.objects.create(project=project, name="برج التدقيق", code="BLK-AUD")
    floor = PropertyFloor.objects.create(block=block, name="الدور الأول", floor_number=1)
    unit = PropertyUnit.objects.create(
        project=project,
        block=block,
        floor=floor,
        unit_code="U-AUD-101",
        gross_area=Decimal("120.00"),
        net_area=Decimal("100.00"),
        meter_price=Decimal("10000.00"),
        base_price=Decimal("1200000.00"),
        total_price=Decimal("1200000.00"),
        status=PropertyUnit.UnitStatus.AVAILABLE
    )
    unit2 = PropertyUnit.objects.create(
        project=project,
        block=block,
        floor=floor,
        unit_code="U-AUD-102",
        gross_area=Decimal("120.00"),
        net_area=Decimal("100.00"),
        meter_price=Decimal("10000.00"),
        base_price=Decimal("1200000.00"),
        total_price=Decimal("1200000.00"),
        status=PropertyUnit.UnitStatus.AVAILABLE
    )

    return {
        'admin': user_admin,
        'sales': user_sales,
        'finance': user_finance,
        'customer': customer,
        'project': project,
        'unit': unit,
        'unit2': unit2,
        'treasury': treasury_account,
        'egp': egp_currency
    }


@pytest.mark.django_db
def test_uncollected_down_payment_cannot_get_full_clearance(audit_setup):
    """
    [P1] منع تسجيل مقدم غير محصل وحظر منح المخالصة المالية دون إثبات السداد الفعلي:
    - حجز محصل بـ 100
    - محاولة تحويل الحجز لعقد بقيمة 1000 ومقدم 1000 دون تحديد حساب الخزينة يرفض.
    - تقييم المخالصة يشتق المسدد من القيود الفعلية ويرفض المخالصة إذا كان المحصل 100 فقط.
    """
    setup = audit_setup
    user = setup['admin']
    customer = setup['customer']
    unit = setup['unit']
    treasury = setup['treasury']

    # 1. إنشاء حجز بمقدم 100 وإثبات تحصيله محاسبياً
    booking = UnitBookingService.create_booking(
        unit_id=unit.id,
        customer=customer,
        holding_deposit=Decimal("100.00"),
        expiry_date=timezone.localdate() + datetime.timedelta(days=7),
        payment_account=treasury,
        user=user
    )
    assert booking.is_deposit_collected is True
    assert booking.holding_deposit == Decimal("100.00")

    # 2. محاولة تحويل الحجز لعقد بمقدم 1000 دون تحديد حساب لتحصيل الفرق (900) يجب أن تُرْفَض
    with pytest.raises(BookingValidationError) as exc:
        UnitBookingService.convert_booking_to_contract(
            booking_id=booking.id,
            user=user,
            final_contract_price=Decimal("1000.00"),
            down_payment=Decimal("1000.00"),
            payment_account=None
        )
    assert "يتجاوز جدية الحجز المحصلة" in str(exc.value)

    # 3. محاكاة وجود عقد مسجل عليه دفترياً down_payment=1000 مع حجز محصل بـ 100 فقط على الوحدة unit2
    unit2 = setup['unit2']
    booking2 = UnitBookingService.create_booking(
        unit_id=unit2.id,
        customer=customer,
        holding_deposit=Decimal("100.00"),
        expiry_date=timezone.localdate() + datetime.timedelta(days=7),
        payment_account=treasury,
        user=user
    )
    contract_unpaid = PropertyContract.objects.create(
        contract_number="CNT-AUD-001",
        project=unit2.project,
        unit=unit2,
        customer=customer,
        final_contract_price=Decimal("1000.00"),
        down_payment=Decimal("1000.00"),
        currency=setup['egp'],
        contract_date=timezone.localdate(),
        delivery_date=timezone.localdate() + datetime.timedelta(days=365),
        status=PropertyContract.ContractStatus.ACTIVE,
        created_by=user
    )

    # تقييم المخالصة يجب أن يشتق المحصل الفعلي (100) ويرفض منح المخالصة
    evaluation = ContractDebtClearanceService.evaluate_contract_clearance(contract_unpaid)
    assert evaluation['is_cleared'] is False
    assert evaluation['can_issue_clearance_certificate'] is False
    assert evaluation['total_paid'] == Decimal("100.00")
    assert evaluation['remaining_balance'] == Decimal("900.00")

    with pytest.raises(ValidationError) as v_exc:
        ContractDebtClearanceService.issue_clearance_certificate(contract_unpaid, user=user)
    assert "لا يمكن إصدار شهادة المخالصة" in str(v_exc.value)

    # 4. عند التحويل مع تحصيل الفرق ذرياً عبر حساب الخزينة
    contract_paid = UnitBookingService.convert_booking_to_contract(
        booking_id=booking.id,
        user=user,
        final_contract_price=Decimal("1000.00"),
        down_payment=Decimal("1000.00"),
        payment_account=treasury
    )
    eval_paid = ContractDebtClearanceService.evaluate_contract_clearance(contract_paid)
    assert eval_paid['is_cleared'] is True
    assert eval_paid['can_issue_clearance_certificate'] is True
    assert eval_paid['total_paid'] == Decimal("1000.00")
    assert eval_paid['remaining_balance'] == Decimal("0.00")


@pytest.mark.django_db
def test_booking_refund_requires_dedicated_disbursement_permission(audit_setup):
    """
    [P1] منع مستخدم بصلاحية تعديل الحجز فقط (change_unitbooking) من صرف واسترداد أموال:
    - استرداد الحجز يشترط صلاحية صرف مالي مستقلة (refund_unitbooking أو صلاحيات مالية).
    - مسار الإلغاء باسترداد فوري يفرض نفس الصلاحية ويمنع المستخدم العادي.
    """
    setup = audit_setup
    sales_rep = setup['sales']
    finance_officer = setup['finance']
    unit = setup['unit']
    treasury = setup['treasury']

    # إنشاء حجز بمقدم محصل
    booking = UnitBookingService.create_booking(
        unit_id=unit.id,
        customer=setup['customer'],
        holding_deposit=Decimal("500.00"),
        expiry_date=timezone.localdate() + datetime.timedelta(days=7),
        payment_account=treasury,
        user=setup['admin']
    )

    # 1. محاولة مسؤول المبيعات (عنده change_unitbooking فقط) إجراء استرداد فوري عند الإلغاء
    with pytest.raises(PermissionDenied):
        UnitBookingService.cancel_booking(
            booking_id=booking.id,
            reason="طلب العميل",
            forfeit_deposit=False,
            payment_account=treasury,
            user=sales_rep
        )

    # لكن يمكنه إلغاء الحجز مع تحويله لبانتظار الرد (بدون صرف مالي)
    cancelled_booking = UnitBookingService.cancel_booking(
        booking_id=booking.id,
        reason="طلب العميل",
        forfeit_deposit=False,
        payment_account=None,
        user=sales_rep
    )
    assert cancelled_booking.status == UnitBooking.BookingStatus.CANCELLED_PENDING_REFUND

    # 2. محاولة مسؤول المبيعات صرف الاسترداد في خدمة الاسترداد تُرْفَض بـ PermissionDenied
    with pytest.raises(PermissionDenied):
        UnitBookingService.process_booking_refund(
            booking_id=cancelled_booking.id,
            payment_account=treasury,
            user=sales_rep
        )

    # 3. اختبار واجهة الـ API للتحقق من إرجاع 403 لمسؤول المبيعات
    factory = RequestFactory()
    request_sales = factory.post(
        f'/real-estate/api/bookings/{cancelled_booking.id}/refund/',
        data={'payment_account_id': treasury.id}
    )
    request_sales.user = sales_rep
    view_refund = ApiRefundBookingView.as_view()
    response_sales = view_refund(request_sales, booking_id=cancelled_booking.id)
    assert response_sales.status_code == 403

    # 4. مسؤول المالية (عنده refund_unitbooking) ينجح في الصرف عبر الخدمة والـ API
    refunded_booking = UnitBookingService.process_booking_refund(
        booking_id=cancelled_booking.id,
        payment_account=treasury,
        user=finance_officer
    )
    assert refunded_booking.status == UnitBooking.BookingStatus.CANCELLED_REFUNDED


@pytest.mark.django_db
def test_expired_booking_with_collected_deposit_not_trapped(audit_setup):
    """
    [P1] عدم حبس مقدم الحجز المنتهي خارج مسار الاسترداد:
    - حجز بمقدم محصل انتهت مهلته.
    - مهمة الكنس تحرر الوحدة وتنقله إلى مسار المراجعة المالية.
    - الحجز المنتهي يقبل الاسترداد المالي والصرف دون أن يُرفض.
    """
    setup = audit_setup
    admin = setup['admin']
    unit = setup['unit']
    treasury = setup['treasury']
    customer = setup['customer']

    # إنشاء حجز بتاريخ منتهٍ ومقدم محصل 100
    today = timezone.localdate()
    past_date = today - datetime.timedelta(days=10)
    past_expiry = today - datetime.timedelta(days=2)

    booking = UnitBookingService.create_booking(
        unit_id=unit.id,
        customer=customer,
        holding_deposit=Decimal("100.00"),
        expiry_date=past_expiry,
        booking_date=past_date,
        payment_account=treasury,
        user=admin
    )
    assert booking.status == UnitBooking.BookingStatus.ACTIVE
    assert booking.is_deposit_collected is True

    # تشغيل كنس الحجوزات المنتهية
    swept = UnitBookingSweepService.sweep_expired_bookings(as_of_date=today)
    assert swept == 1

    booking.refresh_from_db()
    unit.refresh_from_db()

    # الوحدة تحررت للبيع
    assert unit.status == PropertyUnit.UnitStatus.AVAILABLE
    assert unit.current_booking is None

    # الحجز المنتهي بمقدم محصل أصبح قابلاً للاسترداد المالي مباشرة
    refunded = UnitBookingService.process_booking_refund(
        booking_id=booking.id,
        payment_account=treasury,
        user=admin
    )
    assert refunded.status == UnitBooking.BookingStatus.CANCELLED_REFUNDED


@pytest.mark.django_db
def test_manual_contract_without_collection_returns_zero_verified_dp_and_blocks_clearance(audit_setup):
    """
    [P1] التحقق من أن إنشاء العقد بمقدم يدوي بدون إثبات تحصيل محاسبي يرجع صفرًا ويمنع المخالصة:
    - عقد بقيمة 1000 ومقدم 1000 بدون قيد أو إيصال تحصيل.
    - تقييم المخالصة يعتمد 0 للمسدد، والمتبقي 1000، ويرفض إصدار الشهادة.
    """
    setup = audit_setup
    admin = setup['admin']
    unit = setup['unit']
    customer = setup['customer']

    # إنشاء عقد بقيمة 1000 ومقدم 1000 دون أي قيد أو إيصال تحصيل (مثل شاشة إنشاء العقد)
    contract = PropertyContract.objects.create(
        contract_number="CNT-MANUAL-1000",
        project=unit.project,
        unit=unit,
        customer=customer,
        final_contract_price=Decimal("1000.00"),
        down_payment=Decimal("1000.00"),
        currency=setup['egp'],
        contract_date=timezone.localdate(),
        delivery_date=timezone.localdate() + datetime.timedelta(days=365),
        status=PropertyContract.ContractStatus.ACTIVE,
        created_by=admin
    )

    eval_data = ContractDebtClearanceService.evaluate_contract_clearance(contract)
    assert eval_data['total_paid'] == Decimal("0.00")
    assert eval_data['remaining_balance'] == Decimal("1000.00")
    assert eval_data['is_cleared'] is False
    assert eval_data['can_issue_clearance_certificate'] is False

    with pytest.raises(ValidationError):
        ContractDebtClearanceService.issue_clearance_certificate(contract, user=admin)


@pytest.mark.django_db
def test_installment_collection_does_not_double_count_with_down_payment(audit_setup):
    """
    [P1] التحقق من عدم احتساب سداد القسط مرتين:
    - عقد بقيمة 200 ومقدم مكتوب 100 غير محصل، وقسط بقيمة 100.
    - سداد القسط بمبلغ 100 وترحيل قيده المحاسبي.
    - تقييم المخالصة يجمع إجمالي المسدد كـ 100 فقط (وليس 200)، والمتبقي 100، ويرفض المخالصة.
    """
    from sale.models.installments import InstallmentPlan, InstallmentItem

    setup = audit_setup
    admin = setup['admin']
    unit = setup['unit2']
    customer = setup['customer']
    treasury = setup['treasury']

    contract = PropertyContract.objects.create(
        contract_number="CNT-AUD-200",
        project=unit.project,
        unit=unit,
        customer=customer,
        final_contract_price=Decimal("200.00"),
        down_payment=Decimal("100.00"),  # مقدم مكتوب غير محصل
        currency=setup['egp'],
        contract_date=timezone.localdate(),
        delivery_date=timezone.localdate() + datetime.timedelta(days=365),
        status=PropertyContract.ContractStatus.ACTIVE,
        created_by=admin
    )

    plan = InstallmentPlan.objects.create(
        customer=customer,
        plan_type=InstallmentPlan.PlanType.ASSET_FINANCING,
        total_principal=Decimal("100.00"),
        total_amount=Decimal("100.00"),
        number_of_installments=1,
        start_date=timezone.localdate(),
        status=InstallmentPlan.PlanStatus.ACTIVE,
        created_by=admin
    )
    item = InstallmentItem.objects.create(
        plan=plan,
        installment_number=1,
        due_date=timezone.localdate(),
        principal_amount=Decimal("100.00"),
        total_amount=Decimal("100.00"),
        paid_amount=Decimal("0.00")
    )
    contract.installment_plan = plan
    contract.save(update_fields=['installment_plan'])

    # تحصيل القسط فعلياً وترحيل قيده المحاسبي (دائن لحساب التزامات العقود 21102)
    RealEstateAccountingService.post_direct_cash_installment(
        contract=contract,
        installment_item=item,
        amount=Decimal("100.00"),
        payment_account=treasury,
        user=admin,
        reference="INST-PAY-100"
    )
    item.paid_amount = Decimal("100.00")
    item.paid_principal = Decimal("100.00")
    item.save(update_fields=['paid_amount', 'paid_principal'])

    eval_data = ContractDebtClearanceService.evaluate_contract_clearance(contract)
    # إجمالي المسدد يجب أن يكون 100 فقط (وليس 200 باحتساب القسط كمقدم وكمقسط)
    assert eval_data['total_paid'] == Decimal("100.00")
    assert eval_data['remaining_balance'] == Decimal("100.00")
    assert eval_data['is_cleared'] is False
    assert eval_data['can_issue_clearance_certificate'] is False

    with pytest.raises(ValidationError):
        ContractDebtClearanceService.issue_clearance_certificate(contract, user=admin)

