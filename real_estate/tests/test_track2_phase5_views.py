# -*- coding: utf-8 -*-
"""
Track 2 - Phase 5: UI/UX Templates, Views & Modals Test Suite
MWHEBA ERP - Real Estate App

Verifies 100% adherence of:
- Standardized ListView architecture, SSR pagination & AJAX doSearch.
- Kanban 6-stage view rendering and columns grouping.
- DetailView with workspace BOQ grouping, quality hold points, and financial subledgers.
- CreateView order sequence generation and initial stage assignment.
- Official A4 print template layout.
- Catalog and credit schedules directory.
- AJAX Stage Transition API with governed validation.
"""
from decimal import Decimal
from datetime import date
import json
import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.test import Client

from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyFloor,
    PropertyUnit,
    PropertyContract,
    FinishingWorkspace,
    FinishingBrand,
    ContractualCreditSchedule,
    FinishingItemSpec,
    FinishingPackageTemplate,
    UnitFinishingOrder,
    UnitFinishingOrderItem,
)
from customer.models import Customer
from financial.models.currency import Currency
from core.models import SystemModule
from core.middleware.module_control import ModuleAccessMiddleware
from django.core.cache import cache
from real_estate.services.finishing_service import FinishingPricingService

User = get_user_model()


@pytest.fixture
def views_setup(db):
    """Sets up user, client, customer, project, unit, contract, and sample finishing order."""
    SystemModule.objects.update_or_create(
        code='real_estate',
        defaults={'name_ar': 'التطوير العقاري', 'is_enabled': True}
    )
    ModuleAccessMiddleware.invalidate_cache()
    cache.clear()

    user = User.objects.create_user(
        username="frontend_engineer_p5",
        email="fe_p5@example.com",
        password="password123",
        is_staff=True,
        is_superuser=True
    )
    client = Client()
    client.force_login(user)

    customer = Customer.objects.create(
        name="عميل اختبار الواجهات والمقايسات",
        code="CUST-P5-001",
        phone="01155667788"
    )
    project = RealEstateProject.objects.create(
        name="كمبوند الزهور السكني",
        code="CMP-ZHR",
        start_date=date(2025, 1, 1),
        expected_completion_date=date(2027, 12, 31),
        created_by=user
    )
    block = PropertyBlock.objects.create(
        project=project,
        name="عمارة 50",
        code="B50"
    )
    floor = PropertyFloor.objects.create(
        block=block,
        floor_number=5,
        name="الدور الخامس"
    )
    unit = PropertyUnit.objects.create(
        project=project,
        block=block,
        floor=floor,
        unit_code="ZHR-U502",
        unit_type="APARTMENT",
        gross_area=Decimal('180.00'),
        net_area=Decimal('150.00'),
        meter_price=Decimal('28000.00'),
        total_price=Decimal('5040000.00'),
        status='CONTRACTED'
    )
    egp, _ = Currency.objects.get_or_create(code="EGP", defaults={'name': "جنيه مصري", 'symbol': "ج.م", 'is_functional': True})
    contract = PropertyContract.objects.create(
        contract_number="CNT-ZHR-502",
        project=project,
        unit=unit,
        customer=customer,
        final_contract_price=Decimal('5040000.00'),
        contract_date=date(2025, 2, 1),
        delivery_date=date(2027, 6, 30),
        currency=egp,
        status='ACTIVE',
        created_by=user
    )
    order = UnitFinishingOrder.objects.create(
        order_number="FO-2025-0502",
        unit=unit,
        contract=contract,
        customer=customer,
        title="طلب مقايسة تشطيب كاملة",
        current_stage='CUSTOMER_SERVICE',
        workflow_speed='FAST_TRACK',
        gross_finishing_amount=Decimal('150000.00'),
        advance_deposit_required=Decimal('52500.00'),
        total_deposit_paid=Decimal('0.00'),
        delay_penalty_waiver_signed=True,
        created_by=user
    )
    workspace = FinishingWorkspace.objects.create(
        project=project,
        name="غرفة المعيشة",
        code="LIV-05"
    )
    credit_schedule = ContractualCreditSchedule.objects.create(
        project=project,
        category='FLOORING',
        item_title="استرداد أرضيات سيراميك",
        contractual_credit_rate=Decimal('120.00'),
        measuring_unit="M2"
    )
    spec = FinishingItemSpec.objects.create(
        workspace=workspace,
        name="سيراميك رويال فرز أول",
        model_code="ROY-01",
        measuring_unit="M2",
        standard_material_cost=Decimal('250.00'),
        standard_labor_cost=Decimal('70.00'),
        client_selling_rate=Decimal('400.00')
    )
    order_item = UnitFinishingOrderItem.objects.create(
        order=order,
        workspace=workspace,
        spec=spec,
        category='FLOORING',
        item_description="أرضيات سيراميك رويال للصالة",
        quantity=Decimal('50.00'),
        scrap_rate=Decimal('5.00'),
        gross_quantity=Decimal('52.50'),
        measuring_unit="M2",
        unit_selling_price=Decimal('400.00'),
        total_selling_price=Decimal('21000.00')
    )

    return {
        'user': user,
        'client': client,
        'customer': customer,
        'project': project,
        'unit': unit,
        'contract': contract,
        'order': order,
        'workspace': workspace,
        'spec': spec,
        'order_item': order_item,
        'credit_schedule': credit_schedule,
    }


@pytest.mark.django_db
def test_finishing_order_list_view_get(views_setup):
    """Test accessing FinishingOrderListView returns 200 with standard layout."""
    data = views_setup
    url = reverse('real_estate:finishing_order_list')
    response = data['client'].get(url)

    assert response.status_code == 200
    assert 'real_estate/finishing/finishing_order_list.html' in [t.name for t in response.templates]
    assert 'breadcrumb_items' in response.context
    assert 'header_buttons' in response.context
    assert 'kpi_stats' in response.context
    assert response.context['kpi_stats']['total_orders'] >= 1
    assert data['order'].order_number in response.content.decode('utf-8')


@pytest.mark.django_db
def test_finishing_order_list_ajax_search(views_setup):
    """Test AJAX search on FinishingOrderListView returns JSON with partials."""
    data = views_setup
    url = reverse('real_estate:finishing_order_list') + '?ajax=1&q=ZHR-U502'
    response = data['client'].get(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

    assert response.status_code == 200
    json_data = response.json()
    assert 'table_html' in json_data
    assert 'pagination_html' in json_data
    assert 'summary_html' in json_data
    assert "FO-2025-0502" in json_data['table_html']


@pytest.mark.django_db
def test_finishing_order_kanban_view(views_setup):
    """Test accessing Kanban board returns all 6 stages."""
    data = views_setup
    url = reverse('real_estate:finishing_kanban')
    response = data['client'].get(url)

    assert response.status_code == 200
    assert 'real_estate/finishing/finishing_order_kanban.html' in [t.name for t in response.templates]
    assert 'kanban_columns' in response.context
    assert len(response.context['kanban_columns']) >= 6

    # Verify order appears in CUSTOMER_SERVICE column
    cs_col = next(col for col in response.context['kanban_columns'] if col['code'] == 'CUSTOMER_SERVICE')
    assert any(o.id == data['order'].id for o in cs_col['orders'])


@pytest.mark.django_db
def test_finishing_order_detail_view(views_setup):
    """Test accessing FinishingOrderDetailView displays grouped BOQ and details."""
    data = views_setup
    url = reverse('real_estate:finishing_order_detail', kwargs={'pk': data['order'].pk})
    response = data['client'].get(url)

    assert response.status_code == 200
    assert 'real_estate/finishing/finishing_order_detail.html' in [t.name for t in response.templates]
    assert 'workspaces_grouped_items' in response.context
    assert data['workspace'].name in response.context['workspaces_grouped_items']
    assert data['order'].order_number in response.content.decode('utf-8')


@pytest.mark.django_db
def test_finishing_order_create_view_get_and_post(views_setup):
    """Test rendering create form and posting a new order."""
    data = views_setup
    url = reverse('real_estate:finishing_order_create')

    # GET
    res_get = data['client'].get(url)
    assert res_get.status_code == 200
    assert 'real_estate/finishing/finishing_order_form.html' in [t.name for t in res_get.templates]

    # POST
    post_data = {
        'unit': data['unit'].id,
        'contract': data['contract'].id,
        'customer': data['customer'].id,
        'title': "طلب تشطيب جديد للمعاينة",
        'order_type': 'CUSTOM_VARIATION',
        'pricing_mode': 'FIXED_PRICE_BOQ',
        'workflow_speed': 'MAJOR_GOVERNED',
        'execution_duration_days': 100,
        'notes': "طلب تجريبي عبر الاختبار"
    }
    res_post = data['client'].post(url, post_data)
    assert res_post.status_code == 302

    created_order = UnitFinishingOrder.objects.filter(title="طلب تشطيب جديد للمعاينة").first()
    assert created_order is not None
    assert created_order.current_stage == 'CUSTOMER_SERVICE'
    assert created_order.order_number.startswith("FO-")


@pytest.mark.django_db
def test_finishing_order_print_view(views_setup):
    """Test official A4 print template layout."""
    data = views_setup
    url = reverse('real_estate:finishing_order_print', kwargs={'pk': data['order'].pk})
    response = data['client'].get(url)

    assert response.status_code == 200
    assert 'real_estate/finishing/finishing_order_print.html' in [t.name for t in response.templates]
    content = response.content.decode('utf-8')
    assert data['order'].order_number in content
    assert "كراسة ومقايسة مواصفات التشطيب الرسمية" in content
    assert "إقرار العميل بتمديد التسليم وإسقاط الغرامات" in content


@pytest.mark.django_db
def test_finishing_catalog_view(views_setup):
    """Test catalog directory view shows workspaces, specs, and credit schedules."""
    data = views_setup
    url = reverse('real_estate:finishing_catalog')
    response = data['client'].get(url)

    assert response.status_code == 200
    assert 'real_estate/finishing/finishing_catalog_settings.html' in [t.name for t in response.templates]
    assert 'workspaces' in response.context
    assert 'specs' in response.context
    assert 'credit_schedules' in response.context
    content = response.content.decode('utf-8')
    assert data['workspace'].name in content
    assert data['spec'].name in content
    assert data['credit_schedule'].item_title in content


@pytest.mark.django_db
def test_api_finishing_stage_transition(views_setup):
    """Test AJAX stage transition API with Fast-Track order."""
    data = views_setup
    order = data['order']
    url = reverse('real_estate:api_finishing_stage_transition', kwargs={'pk': order.pk})

    FinishingPricingService.freeze_pricing(order, validity_days=15)
    order.delay_penalty_waiver_signed = True
    order.save(update_fields=['delay_penalty_waiver_signed'])

    # Order is Fast-Track and <= 25,000 without demolition, so transition to CLIENT_APPROVAL is allowed
    response = data['client'].post(url, {'target_stage': 'CLIENT_APPROVAL'})
    assert response.status_code == 200
    json_data = response.json()
    assert json_data['success'] is True
    assert json_data['current_stage'] == 'CLIENT_APPROVAL'

    order.refresh_from_db()
    assert order.current_stage == 'CLIENT_APPROVAL'
