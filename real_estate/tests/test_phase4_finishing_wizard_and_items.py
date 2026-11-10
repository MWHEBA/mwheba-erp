# -*- coding: utf-8 -*-
"""
Phase 4: Finishing Variations, Architectural Dimension Wizard & Flexible Installments Test Suite
MWHEBA ERP — Track 2 Parity Completion Plan
"""
from decimal import Decimal
from datetime import date, timedelta
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
    UnitBooking,
    FinishingWorkspace,
    FinishingBrand,
    FinishingItemSpec,
    UnitFinishingOrder,
    UnitFinishingOrderItem,
    FinishingInstallmentPlan,
)
from customer.models import Customer
from core.models import SystemModule
from core.middleware.module_control import ModuleAccessMiddleware
from django.core.cache import cache
from real_estate.services.finishing_service import FinishingPricingService
from real_estate.services.booking_service import UnitBookingService
from financial.models.currency import Currency
from financial.models import ChartOfAccounts, AccountType

User = get_user_model()


@pytest.fixture
def phase4_setup(db):
    """Sets up user, client, customer, project, unit, contract, and sample finishing order."""
    SystemModule.objects.update_or_create(
        code='real_estate',
        defaults={'name_ar': 'التطوير العقاري', 'is_enabled': True}
    )
    ModuleAccessMiddleware.invalidate_cache()
    cache.clear()

    # Functional currency
    currency, _ = Currency.objects.get_or_create(
        code="EGP",
        defaults={"name": "Egyptian Pound", "symbol": "ج.م", "is_functional": True}
    )

    user = User.objects.create_user(
        username="wizard_engineer_p4",
        email="wizard_p4@example.com",
        password="password123",
        is_staff=True,
        is_superuser=True
    )
    client = Client()
    client.force_login(user)

    customer = Customer.objects.create(
        name="عميل اختبار ساحر التشطيبات",
        code="CUST-WIZ-001",
        phone="01011223344"
    )
    project = RealEstateProject.objects.create(
        name="كمبوند اللوتس السكني الفاخر",
        code="CMP-LOTUS",
        start_date=date(2025, 1, 1),
        expected_completion_date=date(2027, 12, 31),
        created_by=user
    )
    block = PropertyBlock.objects.create(
        project=project,
        name="العمارة أ 100",
        code="B-100"
    )
    floor = PropertyFloor.objects.create(
        block=block,
        name="الدور الرابع",
        floor_number=4
    )
    unit = PropertyUnit.objects.create(
        project=project,
        block=block,
        floor=floor,
        unit_code="LOTUS-402",
        unit_type="APARTMENT",
        status=PropertyUnit.UnitStatus.CONTRACTED,
        gross_area=Decimal("150.00"),
        net_area=Decimal("130.00"),
        meter_price=Decimal("15000.00"),
        total_price=Decimal("2250000.00")
    )
    contract = PropertyContract.objects.create(
        contract_number="CNT-LOTUS-402",
        project=project,
        unit=unit,
        customer=customer,
        status="ACTIVE",
        currency=currency,
        contract_date=date(2025, 1, 15),
        delivery_date=date(2026, 6, 30),
        final_contract_price=Decimal("2250000.00"),
        created_by=user
    )
    order = UnitFinishingOrder.objects.create(
        order_number="FO-2025-0099",
        unit=unit,
        contract=contract,
        customer=customer,
        title="أمر تشطيب الترا سوبر لوكس",
        order_type=UnitFinishingOrder.OrderType.CUSTOM_VARIATION,
        current_stage=UnitFinishingOrder.OrderStage.TECHNICAL_OFFICE,
        execution_duration_days=90,
        created_by=user
    )

    return {
        "user": user,
        "client": client,
        "customer": customer,
        "project": project,
        "unit": unit,
        "contract": contract,
        "order": order,
        "currency": currency,
    }


@pytest.mark.django_db
def test_auto_provision_default_workspaces(phase4_setup):
    """Test auto-provisioning of 7 standard workspaces to prevent white screens."""
    project = phase4_setup["project"]
    assert FinishingWorkspace.objects.filter(project=project).count() == 0

    workspaces = FinishingPricingService.provision_default_workspaces(project)
    assert len(workspaces) == 7

    codes = [ws.code for ws in workspaces]
    assert "REC" in codes
    assert "MBR" in codes
    assert "KIT" in codes
    assert "BTH_MAIN" in codes
    assert "TERRACE" in codes

    # Idempotency test: calling it again should return the same spaces without creating duplicates
    second_call = FinishingPricingService.provision_default_workspaces(project)
    assert len(second_call) == 7
    assert FinishingWorkspace.objects.filter(project=project).count() == 7


@pytest.mark.django_db
def test_api_add_and_delete_finishing_order_item(phase4_setup):
    """Test adding a priced BOQ item via API and recalculating order pricing, then deleting it."""
    client = phase4_setup["client"]
    order = phase4_setup["order"]
    project = phase4_setup["project"]

    workspaces = FinishingPricingService.provision_default_workspaces(project)
    rec_ws = next(ws for ws in workspaces if ws.code == "REC")

    add_url = reverse("real_estate:api_add_finishing_order_item", kwargs={"pk": order.pk})

    payload = {
        "workspace_id": rec_ws.id,
        "category": "FLOORING",
        "item_description": "توريد وتركيب بورسلين إسباني 80×80",
        "quantity": "40.00",
        "measuring_unit": "M2",
        "unit_selling_price": "600.00",
        "scrap_rate": "5.00",
        "supply_source": "COMPANY_STORE",
    }

    resp = client.post(add_url, data=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True

    # Gross qty = 40.00 * 1.05 = 42.00, Total price = 42.00 * 600 = 25200.00
    item_id = data["item"]["id"]
    assert Decimal(data["item"]["gross_quantity"]) == Decimal("42.00")
    assert Decimal(data["item"]["total_selling_price"]) == Decimal("25200.00")

    order.refresh_from_db()
    assert order.items.count() == 1
    # Check pricing calculation
    assert Decimal(data["pricing"]["net_price"]) > Decimal("0.00")

    # Now test deleting the item
    delete_url = reverse("real_estate:api_delete_finishing_order_item", kwargs={"pk": order.pk, "item_id": item_id})
    del_resp = client.post(delete_url)
    assert del_resp.status_code == 200
    del_data = del_resp.json()
    assert del_data["success"] is True

    order.refresh_from_db()
    assert order.items.count() == 0
    assert order.net_finishing_price == Decimal("0.00")


@pytest.mark.django_db
def test_finishing_order_wizard_view_rendering(phase4_setup):
    """Test accessing the architectural dimension and BOQ wizard view."""
    client = phase4_setup["client"]
    order = phase4_setup["order"]

    url = reverse("real_estate:finishing_order_wizard", kwargs={"pk": order.pk})
    resp = client.get(url)
    assert resp.status_code == 200
    assert "real_estate/finishing/finishing_order_wizard.html" in [t.name for t in resp.templates]

    content = resp.content.decode("utf-8")
    assert order.order_number in content
    assert "ساحر ومقايسة الفراغات" in content
    assert "حاسبة الأبعاد وتفريغ المسطحات" in content
    assert "outFloorArea" in content
    assert "outWallsArea" in content


@pytest.mark.django_db
def test_api_generate_finishing_installments_flexible(phase4_setup):
    """Test generating flexible finishing installments (e.g. 6 monthly installments)."""
    client = phase4_setup["client"]
    order = phase4_setup["order"]
    project = phase4_setup["project"]

    workspaces = FinishingPricingService.provision_default_workspaces(project)
    ws = workspaces[0]

    # Add an item so net price > 0
    item = UnitFinishingOrderItem.objects.create(
        order=order,
        workspace=ws,
        category="PAINTING",
        item_description="دهانات جوتن سافاري وشاسيهات",
        quantity=Decimal("100.00"),
        gross_quantity=Decimal("100.00"),
        unit_selling_price=Decimal("150.00"),
        total_selling_price=Decimal("15000.00")
    )
    FinishingPricingService.calculate_order_pricing(order)
    order.refresh_from_db()
    assert order.net_finishing_price > Decimal("0.00")

    gen_url = reverse("real_estate:api_generate_finishing_installments", kwargs={"pk": order.pk})
    payload = {
        "number_of_installments": 6,
        "frequency_months": 1,
        "start_date": "2025-02-01",
    }
    resp = client.post(gen_url, data=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["installments_count"] == 6

    order.refresh_from_db()
    assert order.finishing_installment_plan is not None
    assert order.finishing_installment_plan.items.count() == 6


@pytest.mark.django_db
def test_booking_conversion_flexible_finishing_installments(phase4_setup):
    """Test that booking conversion to contract respects flexible finishing installment parameters."""
    user = phase4_setup["user"]
    customer = phase4_setup["customer"]
    project = phase4_setup["project"]
    currency = phase4_setup["currency"]

    floor = PropertyFloor.objects.create(
        block=phase4_setup["project"].blocks.first(),
        name="الدور الخامس",
        floor_number=5
    )
    unit = PropertyUnit.objects.create(
        project=project,
        floor=floor,
        unit_code="LOTUS-505",
        status=PropertyUnit.UnitStatus.AVAILABLE,
        gross_area=Decimal("120.00"),
        meter_price=Decimal("15000.00"),
        total_price=Decimal("1800000.00")
    )

    booking = UnitBookingService.create_booking(
        unit_id=unit.id,
        customer=customer,
        holding_deposit=Decimal("50000.00"),
        expiry_date=date.today() + timedelta(days=14),
        currency=currency,
        total_finishing_amount=Decimal("300000.00"),
        notes="حجز مع تشطيب كامل",
        user=user
    )
    reviewer = User.objects.create_user(username="sales_rev_p4", email="s_p4@test.com", password="pwd", is_staff=True, is_superuser=True)
    auditor = User.objects.create_user(username="fin_aud_p4", email="a_p4@test.com", password="pwd", is_staff=True, is_superuser=True)

    UnitBookingService.review_booking_sales(booking.id, user=reviewer)
    UnitBookingService.confirm_booking_audit(booking.id, user=auditor)

    contract = UnitBookingService.convert_booking_to_contract(
        booking_id=booking.id,
        user=user,
        contract_number="CNT-LOTUS-505",
        final_contract_price=Decimal("1800000.00"),
        down_payment=Decimal("50000.00"),
        delivery_date=date(2026, 12, 31),
        has_decoupled_finishing=True,
        finishing_installments_count=3,
        finishing_installment_frequency=2
    )

    assert contract is not None
    fin_order = UnitFinishingOrder.objects.filter(contract=contract).first()
    assert fin_order is not None
    assert fin_order.finishing_installment_plan is not None
    # Verifies flexible count = 3 instead of hardcoded 4!
    assert fin_order.finishing_installment_plan.items.count() == 3
