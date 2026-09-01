import pytest
import json
from decimal import Decimal
from django.urls import reverse
from django.contrib.auth import get_user_model
from customer.models import Customer
from supplier.models import Supplier, ServiceType, SupplierService
from printing_pricing.models import (
    PrintingOrder, OrderVendorAdvance, PriceAuditLog, ProofSignOff,
    PricingStatus, OrderType
)
from printing_pricing.services import (
    VendorAdvanceService, ProofApprovalService, PriceAuditService, BulkPriceUpdaterService
)

User = get_user_model()


@pytest.fixture
def auth_user(db):
    return User.objects.create_user(
        username="phase3_manager",
        email="phase3@mwheba.com",
        password="secure_password_123",
        is_staff=True
    )


@pytest.fixture
def customer(db):
    return Customer.objects.create(
        name="مجموعة الفطيم للسيارات",
        phone="01122334455",
        customer_type="company"
    )


@pytest.fixture
def supplier(db):
    return Supplier.objects.create(
        name="مطبعة السلام الحديثة",
        phone="01234567890",
        contact_person="أحمد فتحي"
    )


@pytest.fixture
def service_type_press(db):
    st, _ = ServiceType.objects.get_or_create(
        code="offset_printing",
        defaults={"name": "طباعة أوفست", "category": "printing"}
    )
    return st


@pytest.fixture
def supplier_service(db, supplier, service_type_press):
    return SupplierService.objects.create(
        supplier=supplier,
        service_type=service_type_press,
        name="سحب ربع فرخ 4 لون",
        base_price=Decimal("120.00"),
        setup_cost=Decimal("50.00"),
        is_active=True
    )


@pytest.fixture
def base_order(db, customer, auth_user):
    return PrintingOrder.objects.create(
        order_number="PR260301",
        customer=customer,
        title="طباعة 5000 فولدر جيب للشركة",
        order_type=OrderType.FOLDER,
        status=PricingStatus.DRAFT,
        quantity=5000,
        pages_count=2,
        estimated_cost=Decimal("15000.00"),
        final_price=Decimal("18750.00"),
        created_by=auth_user
    )


# 1. اختبار تسجيل عربون لمورد ورشة وتحديث الإجمالي
@pytest.mark.django_db
def test_record_vendor_advance(base_order, supplier, auth_user):
    res = VendorAdvanceService.record_advance(
        order=base_order,
        supplier=supplier,
        amount=Decimal("3000.00"),
        payment_method="BANK_TRANSFER",
        reference_number="TXN-998822",
        notes="عربون حجز سحب الماكينة والورق",
        user=auth_user
    )
    assert res['success'] is True
    assert res['amount'] == Decimal("3000.00")
    assert res['supplier_name'] == supplier.name

    # التحقق من الملخص
    summary = VendorAdvanceService.get_advances_summary(base_order)
    assert summary['total_advances'] == Decimal("3000.00")
    assert summary['unsettled_advances'] == Decimal("3000.00")
    assert summary['settled_advances'] == Decimal("0.00")
    assert summary['advances_count'] == 1


# 2. اختبار تسوية العربون مع الفاتورة
@pytest.mark.django_db
def test_settle_vendor_advance(base_order, supplier, auth_user):
    VendorAdvanceService.record_advance(
        order=base_order,
        supplier=supplier,
        amount=Decimal("1500.00"),
        user=auth_user
    )
    advance = base_order.vendor_advances.first()
    assert advance.is_settled is False

    settle_res = VendorAdvanceService.settle_advance(
        advance=advance,
        notes="تمت التسوية مع فاتورة رقم BILL-4401",
        user=auth_user
    )
    assert settle_res['success'] is True
    assert settle_res['is_settled'] is True

    advance.refresh_from_db()
    assert advance.is_settled is True
    assert advance.settled_at is not None
    assert "BILL-4401" in advance.notes


# 3. اختبار نقطة نهاية API لعرابين الموردين
@pytest.mark.django_db
def test_vendor_advances_api_endpoint(client, auth_user, base_order, supplier):
    client.force_login(auth_user)
    url = reverse('printing_pricing:api_order_advances', kwargs={'order_id': base_order.id})

    # POST لتسجيل عربون
    payload = {
        'supplier_id': supplier.id,
        'amount': '2500.00',
        'payment_method': 'CASH',
        'reference_number': 'REC-1122',
        'notes': 'عربون شراء أفرخ ورق كوشيه'
    }
    post_res = client.post(url, data=json.dumps(payload), content_type='application/json')
    assert post_res.status_code == 200
    data = post_res.json()
    assert data['success'] is True
    assert data['amount'] == 2500.0 or data['amount'] == '2500.00'

    # GET لاسترجاع الملخص
    get_res = client.get(url)
    assert get_res.status_code == 200
    summary_data = get_res.json()
    assert summary_data['success'] is True
    assert summary_data['total_advances'] == '2500.00' or summary_data['total_advances'] == 2500.0
    assert len(summary_data['advances']) == 1


# 4. اختبار إنشاء طلب بروفة رقمية ورمز التحقق
@pytest.mark.django_db
def test_generate_proof_request(base_order, auth_user):
    res = ProofApprovalService.generate_proof_request(order=base_order, user=auth_user)
    assert res['success'] is True
    assert res['status'] == ProofSignOff.ProofStatus.PENDING
    assert res['token'] is not None

    signoff = ProofSignOff.objects.get(order=base_order)
    assert str(signoff.token) == res['token']


# 5. اختبار اعتماد البروفة الرقمية إلكترونياً من العميل عبر الـ Public API
@pytest.mark.django_db
def test_public_proof_approval_endpoint(client, base_order, auth_user):
    proof_req = ProofApprovalService.generate_proof_request(order=base_order, user=auth_user)
    token = proof_req['token']

    url = reverse('printing_pricing:api_proof_signoff', kwargs={'token': token})

    # GET لمعاينة البروفة
    get_res = client.get(url)
    assert get_res.status_code == 200
    assert get_res.json()['order_number'] == base_order.order_number

    # POST للاعتماد
    payload = {
        'action': 'approve',
        'client_name': 'م. كريم الشناوي'
    }
    post_res = client.post(url, data=json.dumps(payload), content_type='application/json')
    assert post_res.status_code == 200
    data = post_res.json()
    assert data['success'] is True

    signoff = ProofSignOff.objects.get(token=token)
    assert signoff.status == ProofSignOff.ProofStatus.APPROVED
    assert signoff.approved_by_name == 'م. كريم الشناوي'
    assert signoff.approved_at is not None


# 6. اختبار رفض البروفة الرقمية مع تسجيل ملاحظات العميل
@pytest.mark.django_db
def test_public_proof_rejection_with_feedback(client, base_order, auth_user):
    proof_req = ProofApprovalService.generate_proof_request(order=base_order, user=auth_user)
    token = proof_req['token']

    url = reverse('printing_pricing:api_proof_signoff', kwargs={'token': token})
    payload = {
        'action': 'reject',
        'client_name': 'أ. سارة ممدوح',
        'feedback': 'برجاء تعديل درجة اللون الذهبي وتصغير اللوجو 10%'
    }
    post_res = client.post(url, data=json.dumps(payload), content_type='application/json')
    assert post_res.status_code == 200
    data = post_res.json()
    assert data['success'] is True

    signoff = ProofSignOff.objects.get(token=token)
    assert signoff.status == ProofSignOff.ProofStatus.REJECTED
    assert 'تصغير اللوجو' in signoff.client_feedback


# 7. اختبار تسجيل تدقيق السعر واسترجاع سجل التعديلات المالية
@pytest.mark.django_db
def test_price_audit_service_logging(base_order, auth_user):
    log_res = PriceAuditService.log_price_change(
        order=base_order,
        field_name="profit_margin",
        old_value="20.00",
        new_value="25.00",
        reason="تعديل نسبة الربح للعميل بناءً على شروط الدفع الآجل",
        user=auth_user
    )
    assert log_res['success'] is True

    audit_trail = PriceAuditService.get_order_audit_trail(base_order)
    assert audit_trail['success'] is True
    assert audit_trail['logs_count'] == 1
    assert audit_trail['audit_trail'][0]['field_name'] == 'profit_margin'
    assert audit_trail['audit_trail'][0]['old_value'] == '20.00'
    assert audit_trail['audit_trail'][0]['new_value'] == '25.00'


# 8. اختبار نقطة نهاية API لسجل تدقيق الأسعار
@pytest.mark.django_db
def test_price_audit_trail_api(client, auth_user, base_order):
    client.force_login(auth_user)
    url = reverse('printing_pricing:api_price_audit_trail', kwargs={'order_id': base_order.id})

    # تسجيل قيد تدقيق عبر POST
    payload = {
        'field_name': 'estimated_cost',
        'old_value': '15000.00',
        'new_value': '16200.00',
        'reason': 'ارتفاع سعر أفرخ الورق لدى التاجر'
    }
    post_res = client.post(url, data=json.dumps(payload), content_type='application/json')
    assert post_res.status_code == 200
    assert post_res.json()['success'] is True

    # GET لاسترجاع السجل
    get_res = client.get(url)
    assert get_res.status_code == 200
    data = get_res.json()
    assert data['success'] is True
    assert data['logs_count'] >= 1


# 9. اختبار التحديث المجمع لأسعار خدمات الموردين (Bulk Price Updater)
@pytest.mark.django_db
def test_bulk_price_updater_service(supplier_service, auth_user):
    old_price = supplier_service.base_price  # 120.00
    updates = [
        {'service_id': supplier_service.id, 'new_price': Decimal('145.00')}
    ]
    res = BulkPriceUpdaterService.bulk_update_supplier_services(updates, user=auth_user)
    assert res['success'] is True
    assert res['updated_count'] == 1

    supplier_service.refresh_from_db()
    assert supplier_service.base_price == Decimal('145.00')


# 10. اختبار نقطة نهاية API للتحديث المجمع للأسعار
@pytest.mark.django_db
def test_bulk_price_update_api(client, auth_user, supplier_service):
    client.force_login(auth_user)
    url = reverse('printing_pricing:api_bulk_price_update')

    payload = {
        'updates': [
            {'service_id': supplier_service.id, 'new_price': '155.00'}
        ]
    }
    post_res = client.post(url, data=json.dumps(payload), content_type='application/json')
    assert post_res.status_code == 200
    assert post_res.json()['success'] is True

    supplier_service.refresh_from_db()
    assert supplier_service.base_price == Decimal('155.00')


# 11. اختبار نقطة نهاية API لحساب النقل متعدد المحطات وصمام الحد الأدنى
@pytest.mark.django_db
def test_multi_leg_freight_api(client, auth_user):
    client.force_login(auth_user)
    url = reverse('printing_pricing:api_calculate_freight')

    payload = {
        'legs': [
            {'from': 'المطبعة', 'to': 'ورشة السلوفان', 'cost': 80},
            {'from': 'ورشة السلوفان', 'to': 'مخزن العميل', 'cost': 90}
        ],
        'minimum_drop_fee': '200.00',  # مجموع 170 يرتفع لـ 200
        'staggered_drops_count': 3,     # 3 دفعات
        'is_insured_cargo': True,
        'cargo_value': '50000.00'       # تأمين 250 ج
    }
    post_res = client.post(url, data=json.dumps(payload), content_type='application/json')
    assert post_res.status_code == 200
    data = post_res.json()
    assert data['success'] is True
    assert data['total_freight_drops'] == 600.0 or data['total_freight_drops'] == '600.00'  # 3 * 200
    assert data['insurance_fee'] == 250.0 or data['insurance_fee'] == '250.00'
    assert data['total_freight_cost'] == 850.0 or data['total_freight_cost'] == '850.00'
