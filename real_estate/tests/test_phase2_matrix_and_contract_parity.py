# -*- coding: utf-8 -*-
"""
Test Suite for Phase 2: Matrix Quick Booking, Unit Extras, Comprehensive Contract Form,
Direct Contract Parity, Flexible Installments & Handover/Annex Integration.
"""
import datetime
from decimal import Decimal
import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from core.models import SystemModule
from django.contrib.auth.models import Permission
from real_estate.models import (
    RealEstateProject, PropertyBlock, PropertyFloor, PropertyUnit, UnitBooking,
    PropertyContract, ContractCoOwner, RealEstateBroker, BrokerAttributionAudit
)
from real_estate.services.booking_service import UnitBookingService
from customer.models import Customer
from financial.models import Currency, ChartOfAccounts, AccountType

User = get_user_model()


@pytest.fixture
def phase2_setup(db):
    SystemModule.objects.update_or_create(
        code='real_estate',
        defaults={'name_ar': 'القطاع العقاري', 'is_enabled': True}
    )

    user_creator = User.objects.create_user(
        username='p2_creator',
        email='p2_creator@test.com',
        password='password123',
        is_staff=True,
        is_superuser=True
    )
    user_reviewer = User.objects.create_user(
        username='p2_reviewer',
        email='p2_reviewer@test.com',
        password='password123',
        is_staff=True
    )
    user_auditor = User.objects.create_user(
        username='p2_auditor',
        email='p2_auditor@test.com',
        password='password123',
        is_staff=True
    )
    user_specialist = User.objects.create_user(
        username='p2_specialist',
        email='p2_specialist@test.com',
        password='password123',
        first_name='Ahmed',
        last_name='Sales'
    )

    change_perm = Permission.objects.get(codename='change_unitbooking', content_type__app_label='real_estate')
    view_perm = Permission.objects.get(codename='view_unitbooking', content_type__app_label='real_estate')
    add_perm = Permission.objects.get(codename='add_unitbooking', content_type__app_label='real_estate')
    for u in (user_creator, user_reviewer, user_auditor):
        u.user_permissions.add(change_perm, view_perm, add_perm)

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
        defaults={'name': 'Current Asset P2', 'category': 'asset', 'nature': 'debit'}
    )
    treasury_account = ChartOfAccounts.objects.filter(code='11101').first()
    if not treasury_account:
        treasury_account = ChartOfAccounts.objects.create(
            code='11101',
            name='Main Treasury P2',
            account_type=asset_type,
            currency=currency,
            is_active=True,
            is_leaf=True
        )

    liability_type, _ = AccountType.objects.get_or_create(
        code='LIABILITY',
        defaults={'name': 'Current Liability P2', 'category': 'liability', 'nature': 'credit'}
    )
    deposit_liability_account = ChartOfAccounts.objects.filter(code='21101').first()
    if not deposit_liability_account:
        deposit_liability_account = ChartOfAccounts.objects.create(
            code='21101',
            name='Holding Deposit Liability P2',
            account_type=liability_type,
            currency=currency,
            is_active=True,
            is_leaf=True
        )

    contract_liability_account = ChartOfAccounts.objects.filter(code='21102').first()
    if not contract_liability_account:
        contract_liability_account = ChartOfAccounts.objects.create(
            code='21102',
            name='Contract Liability P2',
            account_type=liability_type,
            currency=currency,
            is_active=True,
            is_leaf=True
        )

    project = RealEstateProject.objects.create(
        code='PRJ-P2-01',
        name='Parity Heights',
        start_date=timezone.localdate(),
        expected_completion_date=timezone.localdate() + datetime.timedelta(days=730),
        created_by=user_creator
    )

    block = PropertyBlock.objects.create(
        project=project,
        code='BLK-P2-A',
        name='Block A'
    )

    floor = PropertyFloor.objects.create(
        block=block,
        floor_number=3,
        name='Third Floor'
    )

    unit = PropertyUnit.objects.create(
        project=project,
        block=block,
        floor=floor,
        unit_code='U-301',
        status=PropertyUnit.UnitStatus.AVAILABLE,
        net_area=Decimal('120.00'),
        gross_area=Decimal('140.00'),
        meter_price=Decimal('10000.00'),
        base_price=Decimal('1400000.00'),
        total_price=Decimal('1400000.00')
    )

    customer = Customer.objects.create(
        name='Tarek Moustafa',
        code='CUST-P2-001',
        phone='01009876543'
    )
    co_customer = Customer.objects.create(
        name='Mona Moustafa',
        code='CUST-P2-002',
        phone='01009876544'
    )

    broker = RealEstateBroker.objects.create(
        code='BRK-P2-01',
        name='Apex Realty',
        default_commission_rate=Decimal('2.50'),
        is_active=True,
        created_by=user_creator
    )

    return {
        'user_creator': user_creator,
        'user_reviewer': user_reviewer,
        'user_auditor': user_auditor,
        'user_specialist': user_specialist,
        'currency': currency,
        'treasury_account': treasury_account,
        'deposit_liability_account': deposit_liability_account,
        'contract_liability_account': contract_liability_account,
        'project': project,
        'floor': floor,
        'unit': unit,
        'customer': customer,
        'co_customer': co_customer,
        'broker': broker,
    }


@pytest.mark.django_db
class TestPhase2MatrixAndContractParity:

    def test_project_matrix_view_context_and_breadcrumbs(self, client, phase2_setup):
        s = phase2_setup
        client.force_login(s['user_creator'])

        url = reverse('real_estate:project_matrix', kwargs={'project_id': s['project'].id})
        response = client.get(url)

        assert response.status_code == 200
        # Check breadcrumbs real URLs
        breadcrumbs = response.context['breadcrumb_items']
        for b in breadcrumbs:
            if not b.get('active'):
                assert b['url'] != '#'
                assert len(b['url']) > 0

        # Check context keys for quick booking
        assert 'currencies' in response.context
        assert 'payment_accounts' in response.context
        assert 'brokers' in response.context
        assert 'specialists' in response.context

    def test_api_book_unit_with_extras_and_specialists(self, client, phase2_setup):
        s = phase2_setup
        client.force_login(s['user_creator'])

        url = reverse('real_estate:api_book_unit', kwargs={'unit_id': s['unit'].id})
        payload = {
            'customer_id': s['customer'].id,
            'holding_deposit': '50000.00',
            'expiry_days': 10,
            'parking_slot_code': 'P-12',
            'parking_slot_price': '100000.00',
            'storage_locker_code': 'S-04',
            'storage_locker_price': '30000.00',
            'utilities_deposit_amount': '25000.00',
            'visit_specialist_id': s['user_specialist'].id,
            'broker_id': s['broker'].id,
        }

        response = client.post(url, data=payload, content_type='application/json')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

        booking = UnitBooking.objects.get(pk=data['booking_id'])
        assert booking.parking_slot_code == 'P-12'
        assert booking.parking_slot_price == Decimal('100000.00')
        assert booking.storage_locker_code == 'S-04'
        assert booking.storage_locker_price == Decimal('30000.00')
        assert booking.utilities_deposit_amount == Decimal('25000.00')
        assert booking.visit_specialist_id == s['user_specialist'].id

        # Verify BrokerAttributionAudit was created
        attr = BrokerAttributionAudit.objects.filter(customer=s['customer']).first()
        assert attr is not None
        assert attr.referring_broker_id == s['broker'].id

    def test_convert_booking_to_contract_flexible_installments_and_broker(self, phase2_setup):
        s = phase2_setup
        # Create booking
        booking = UnitBookingService.create_booking(
            unit_id=s['unit'].id,
            customer=s['customer'],
            holding_deposit=Decimal('70000.00'),
            expiry_date=timezone.localdate() + datetime.timedelta(days=14),
            user=s['user_creator'],
            parking_slot_code='P-99',
            parking_slot_price=Decimal('120000.00'),
            utilities_deposit_amount=Decimal('50000.00')
        )

        # Complete Dual-Audit
        UnitBookingService.review_booking_sales(booking.id, s['user_reviewer'])
        UnitBookingService.confirm_booking_audit(booking.id, s['user_auditor'])

        # Convert to contract with 6 monthly installments & broker
        contract = UnitBookingService.convert_booking_to_contract(
            booking_id=booking.id,
            user=s['user_creator'],
            final_contract_price=Decimal('1500000.00'),
            down_payment=Decimal('70000.00'),
            number_of_installments=6,
            installment_frequency='MONTHLY',
            first_installment_date=timezone.localdate() + datetime.timedelta(days=30),
            broker=s['broker'],
            broker_commission_rate=Decimal('3.00'),
            ceo_override_token="APPROVED_BY_CEO"
        )

        assert contract.status == PropertyContract.ContractStatus.ACTIVE
        assert contract.parking_slot_code == 'P-99'
        assert contract.utilities_deposit_amount == Decimal('50000.00')

        # Check Installment Plan
        plan = contract.installment_plan
        assert plan is not None
        assert plan.number_of_installments == 6
        assert plan.frequency == 'MONTHLY'
        items = list(plan.items.all().order_by('installment_number'))
        assert len(items) == 6

        # Check Broker Commission created
        assert contract.broker_commissions.count() == 1
        comm = contract.broker_commissions.first()
        assert comm.broker_id == s['broker'].id
        assert comm.commission_rate == Decimal('3.00')

    def test_direct_contract_creation_post_with_co_owners_and_down_payment(self, client, phase2_setup):
        s = phase2_setup
        client.force_login(s['user_creator'])

        url = reverse('real_estate:contract_create')
        post_data = {
            'customer': s['customer'].id,
            'unit': s['unit'].id,
            'final_contract_price': '2000000.00',
            'down_payment': '200000.00',
            'currency': s['currency'].id,
            'payment_account': s['treasury_account'].id,
            'primary_owner_share': '70.00',
            'co_owner_id': [str(s['co_customer'].id)],
            'co_owner_share': ['30.00'],
            'number_of_installments': '8',
            'installment_frequency': 'QUARTERLY',
            'parking_slot_code': 'P-Direct',
            'parking_slot_price': '150000.00',
            'storage_locker_code': 'S-Direct',
            'storage_locker_price': '40000.00',
            'utilities_deposit_amount': '60000.00',
            'broker': s['broker'].id,
            'broker_commission_rate': '2.50',
        }

        response = client.post(url, data=post_data)
        assert response.status_code == 302

        contract = PropertyContract.objects.filter(unit=s['unit']).first()
        assert contract is not None
        assert contract.final_contract_price == Decimal('2000000.00')
        assert contract.down_payment == Decimal('200000.00')
        assert contract.primary_owner_share == Decimal('70.00')
        assert contract.parking_slot_code == 'P-Direct'
        assert contract.storage_locker_code == 'S-Direct'
        assert contract.utilities_deposit_amount == Decimal('60000.00')

        # Check Co-owner
        assert contract.co_owners.count() == 1
        co = contract.co_owners.first()
        assert co.co_owner_id == s['co_customer'].id
        assert co.share_percentage == Decimal('30.00')

        # Check Installment Plan
        plan = contract.installment_plan
        assert plan is not None
        assert plan.number_of_installments == 8
        assert plan.frequency == 'QUARTERLY'
        assert plan.items.count() == 8

        # Check Unit status updated to CONTRACTED
        s['unit'].refresh_from_db()
        assert s['unit'].status == PropertyUnit.UnitStatus.CONTRACTED

    def test_contract_detail_and_print_views(self, client, phase2_setup):
        s = phase2_setup
        client.force_login(s['user_creator'])

        contract = PropertyContract.objects.create(
            contract_number='CTR-DETAIL-TEST-01',
            project=s['project'],
            unit=s['unit'],
            customer=s['customer'],
            status=PropertyContract.ContractStatus.ACTIVE,
            contract_date=timezone.localdate(),
            delivery_date=timezone.localdate() + datetime.timedelta(days=365),
            final_contract_price=Decimal('1000000.00'),
            down_payment=Decimal('100000.00'),
            currency=s['currency'],
            primary_owner_share=Decimal('60.00'),
            parking_slot_code='P-VIP-1',
            parking_slot_price=Decimal('150000.00'),
            storage_locker_code='S-VIP-1',
            storage_locker_price=Decimal('50000.00'),
            utilities_deposit_amount=Decimal('40000.00'),
            created_by=s['user_creator']
        )
        co = ContractCoOwner(
            contract=contract,
            co_owner=s['co_customer'],
            share_percentage=Decimal('40.00')
        )
        co.save(skip_integrity_check=True)

        # Test Detail View
        detail_url = reverse('real_estate:contract_detail', kwargs={'pk': contract.pk})
        res_detail = client.get(detail_url)
        assert res_detail.status_code == 200
        assert 'P-VIP-1' in res_detail.content.decode('utf-8')
        assert '60.00%' in res_detail.content.decode('utf-8')
        assert '40.00%' in res_detail.content.decode('utf-8')

        # Test Official Print View
        print_url = reverse('real_estate:contract_print', kwargs={'pk': contract.pk})
        res_print = client.get(print_url)
        assert res_print.status_code == 200
        html = res_print.content.decode('utf-8')
        assert 'P-VIP-1' in html
        assert 'S-VIP-1' in html
        assert 'ملحق التجهيزات والملحقات ووديعة المرافق والصيانة' in html
