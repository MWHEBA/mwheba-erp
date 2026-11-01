# -*- coding: utf-8 -*-
from decimal import Decimal
import pytest
from django.urls import reverse
from django.test import Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from real_estate.models import RealEstateProject, PropertyBlock, PropertyFloor, PropertyUnit, PropertyContract, UnitBooking
from customer.models import Customer
from financial.models.currency import Currency
from core.models import SystemModule

User = get_user_model()


@pytest.fixture
def phase4_setup(db):
    mod, _ = SystemModule.objects.get_or_create(code='real_estate', defaults={'name_ar': 'العقارات', 'is_enabled': True})
    mod.is_enabled = True
    mod.save()

    user = User.objects.create_superuser(username='admin_phase4_test', password='password123', email='admin4@test.com')
    client = Client()
    client.login(username='admin_phase4_test', password='password123')

    customer = Customer.objects.create(name='عميل تجربة الحجز والعقود', code='CUST-P4', phone='01000000004')

    project = RealEstateProject.objects.create(
        code='PRJ-P4',
        name='مشروع الروضة التست',
        project_type=RealEstateProject.ProjectType.RESIDENTIAL,
        status=RealEstateProject.ProjectStatus.UNDER_CONSTRUCTION,
        total_land_area=2500,
        gross_built_area=6000,
        start_date='2026-01-01',
        expected_completion_date='2027-01-01',
        created_by=user
    )
    block = PropertyBlock.objects.create(project=project, code='B4', name='عمارة 4')
    floor = PropertyFloor.objects.create(block=block, floor_number=1, name='الدور الأول')
    unit = PropertyUnit.objects.create(
        project=project,
        block=block,
        floor=floor,
        unit_code='U401-P4',
        unit_type=PropertyUnit.UnitType.APARTMENT,
        status=PropertyUnit.UnitStatus.AVAILABLE,
        gross_area=Decimal('140.00'),
        meter_price=Decimal('22000.00'),
        total_price=Decimal('3080000.00')
    )

    booking = UnitBooking.objects.create(
        booking_number='BKG-P4-001',
        unit=unit,
        customer=customer,
        holding_deposit=Decimal('50000.00'),
        expiry_date=timezone.now() + timezone.timedelta(days=7),
        status=UnitBooking.BookingStatus.ACTIVE,
        created_by=user
    )

    currency, _ = Currency.objects.get_or_create(code='EGP', defaults={'name': 'Egyptian Pound', 'is_functional': True})

    contract = PropertyContract.objects.create(
        contract_number='CTR-P4-001',
        project=project,
        unit=unit,
        customer=customer,
        status=PropertyContract.ContractStatus.ACTIVE,
        contract_date=timezone.localdate(),
        delivery_date=timezone.localdate() + timezone.timedelta(days=365),
        final_contract_price=Decimal('3080000.00'),
        down_payment=Decimal('308000.00'),
        currency=currency,
        created_by=user
    )

    return {
        'client': client,
        'user': user,
        'customer': customer,
        'project': project,
        'unit': unit,
        'booking': booking,
        'contract': contract
    }


@pytest.mark.django_db
def test_booking_list_and_ajax_search(phase4_setup):
    client = phase4_setup['client']
    url = reverse('real_estate:booking_list')
    resp = client.get(url)
    assert resp.status_code == 200
    assert 'real_estate/booking_list.html' in [t.name for t in resp.templates]
    assert 'BKG-P4-001' in resp.content.decode('utf-8')

    # AJAX search
    resp_ajax = client.get(url + '?q=BKG-P4&ajax=1', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    assert resp_ajax.status_code == 200
    data = resp_ajax.json()
    assert data['success'] is True
    assert 'table_html' in data
    assert 'BKG-P4-001' in data['table_html']


@pytest.mark.django_db
def test_booking_detail_view(phase4_setup):
    client = phase4_setup['client']
    booking = phase4_setup['booking']
    url = reverse('real_estate:booking_detail', kwargs={'pk': booking.id})
    resp = client.get(url)
    assert resp.status_code == 200
    assert 'real_estate/booking_detail.html' in [t.name for t in resp.templates]
    content = resp.content.decode('utf-8')
    assert booking.booking_number in content
    assert '50,000' in content


@pytest.mark.django_db
def test_contract_list_and_ajax_search(phase4_setup):
    client = phase4_setup['client']
    url = reverse('real_estate:contract_list')
    resp = client.get(url)
    assert resp.status_code == 200
    assert 'real_estate/contract_list.html' in [t.name for t in resp.templates]
    assert 'CTR-P4-001' in resp.content.decode('utf-8')

    # AJAX search
    resp_ajax = client.get(url + '?q=CTR-P4&ajax=1', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    assert resp_ajax.status_code == 200
    data = resp_ajax.json()
    assert data['success'] is True
    assert 'table_html' in data
    assert 'CTR-P4-001' in data['table_html']


@pytest.mark.django_db
def test_contract_detail_and_create_views(phase4_setup):
    client = phase4_setup['client']
    contract = phase4_setup['contract']

    # Detail
    url_detail = reverse('real_estate:contract_detail', kwargs={'pk': contract.id})
    resp_detail = client.get(url_detail)
    assert resp_detail.status_code == 200
    assert 'real_estate/contract_detail.html' in [t.name for t in resp_detail.templates]
    assert contract.contract_number in resp_detail.content.decode('utf-8')

    # Create GET
    url_create = reverse('real_estate:contract_create')
    resp_create = client.get(url_create)
    assert resp_create.status_code == 200
    assert 'real_estate/contract_form.html' in [t.name for t in resp_create.templates]


@pytest.mark.django_db
def test_contract_clearance_certificate_print_view(phase4_setup):
    client = phase4_setup['client']
    contract = phase4_setup['contract']
    # العقد مسدد بالكامل بإيصال تحصيل معتمد حتى تقبل خدمة المخالصة طباعة الشهادة
    contract.final_contract_price = Decimal('308000.00')
    contract.down_payment = Decimal('308000.00')
    contract.save()

    from customer.models import CustomerPayment
    from real_estate.models.contract import ContractPaymentReceipt
    payment = CustomerPayment.objects.create(
        customer=contract.customer,
        amount=Decimal('308000.00'),
        payment_date=timezone.localdate(),
        payment_method="CASH",
        created_by=phase4_setup['user']
    )
    ContractPaymentReceipt.objects.create(
        contract=contract,
        customer_payment=payment,
        installment_item=None
    )

    url = reverse('real_estate:contract_clearance_print', kwargs={'pk': contract.id})
    resp = client.get(url)
    assert resp.status_code == 200
    assert 'real_estate/clearance_certificate_print.html' in [t.name for t in resp.templates]
    content = resp.content.decode('utf-8')
    assert contract.contract_number in content
    assert 'شهادة مخالصة مالية نهائية وبراءة ذمة' in content
