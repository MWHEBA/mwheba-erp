# -*- coding: utf-8 -*-
"""
Tests for Phase 6.2 - Enterprise Real Estate Print Views & Digital SHA-256 Seals
MWHEBA ERP — Real Estate Wave 6 (Contract Print, Statement of Account Print, Booking Print, Unit Swap Print)
"""
import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone

from core.models import SystemModule
from core.middleware.module_control import ModuleAccessMiddleware
from customer.models import Customer, CustomerPayment
from financial.models import Currency, ChartOfAccounts, AccountType
from sale.models.installments import InstallmentPlan, InstallmentItem
from cheques.models.cheque import Cheque, ChequeType, ChequeStatus
from cheques.models.allocation import ChequeInvoiceAllocation, AllocationStatus

from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyFloor,
    PropertyUnit,
    UnitBooking,
    PropertyContract,
    ContractCoOwner,
    ContractPaymentReceipt,
    UnitSwapRecord,
)

User = get_user_model()


@pytest.fixture
def print_setup(db):
    cache.delete('enabled_modules_set')
    cache.delete('module_namespace_map')

    mod, _ = SystemModule.objects.get_or_create(
        code='real_estate',
        defaults={'name_ar': 'العقارات', 'is_enabled': True}
    )
    mod.is_enabled = True
    mod.save()
    ModuleAccessMiddleware.invalidate_cache()

    user = User.objects.create_superuser(
        username="print_auditor",
        email="print@test.com",
        password="password123"
    )

    currency, _ = Currency.objects.get_or_create(
        code="EGP",
        defaults={"name": "جنيه مصري", "symbol": "ج.م", "is_functional": True}
    )

    liability_type, _ = AccountType.objects.get_or_create(
        code='liability',
        defaults={'name': 'خصوم', 'category': 'liability', 'nature': 'credit'}
    )
    ChartOfAccounts.objects.get_or_create(
        code="21102",
        defaults={"name": "التزامات عقود عملاء عقاري", "account_type": liability_type, "is_active": True}
    )

    project = RealEstateProject.objects.create(
        code="PRJ-PRT-01",
        name="مشروع أبراج النيل الفندقية",
        project_type=RealEstateProject.ProjectType.RESIDENTIAL,
        status=RealEstateProject.ProjectStatus.UNDER_CONSTRUCTION,
        start_date=date(2025, 1, 1),
        expected_completion_date=date(2027, 12, 31),
        total_land_area=Decimal("4000.00"),
        gross_built_area=Decimal("16000.00"),
        created_by=user
    )

    block = PropertyBlock.objects.create(project=project, code="BLK-PRT-A", name="برج اللوتس")
    floor = PropertyFloor.objects.create(block=block, floor_number=5, name="الطابق الخامس")

    unit_booked = PropertyUnit.objects.create(
        project=project,
        floor=floor,
        unit_code="NILE-501",
        gross_area=Decimal("140.00"),
        net_area=Decimal("120.00"),
        meter_price=Decimal("20000.00"),
        base_price=Decimal("2800000.00"),
        total_price=Decimal("2800000.00"),
        status=PropertyUnit.UnitStatus.RESERVED
    )
    unit_contracted = PropertyUnit.objects.create(
        project=project,
        floor=floor,
        unit_code="NILE-502",
        gross_area=Decimal("180.00"),
        net_area=Decimal("155.00"),
        meter_price=Decimal("20000.00"),
        base_price=Decimal("3600000.00"),
        total_price=Decimal("3600000.00"),
        status=PropertyUnit.UnitStatus.CONTRACTED
    )
    unit_swap_target = PropertyUnit.objects.create(
        project=project,
        floor=floor,
        unit_code="NILE-503",
        gross_area=Decimal("220.00"),
        net_area=Decimal("190.00"),
        meter_price=Decimal("20000.00"),
        base_price=Decimal("4400000.00"),
        total_price=Decimal("4400000.00"),
        status=PropertyUnit.UnitStatus.AVAILABLE
    )

    customer_main = Customer.objects.create(
        code="CUST-PRT-01",
        name="الدكتور خالد عبد العزيز",
        phone="01012345678",
        default_currency=currency
    )
    co_owner_cust = Customer.objects.create(
        code="CUST-PRT-02",
        name="المهندسة سارة خالد",
        default_currency=currency
    )

    # 1. استمارة حجز وحدة
    booking = UnitBooking.objects.create(
        booking_number="BKG-PRT-2026-01",
        unit=unit_booked,
        customer=customer_main,
        booking_date=timezone.localdate(),
        expiry_date=timezone.localdate() + timedelta(days=7),
        holding_deposit=Decimal("100000.00"),
        is_deposit_collected=True,
        status=UnitBooking.BookingStatus.ACTIVE,
        created_by=user
    )

    # 2. عقد بيع رسمي مع شريك على المشاع وخطة أقساط وشيك بالحافظة
    contract = PropertyContract.objects.create(
        contract_number="CTR-PRT-2026-01",
        project=project,
        unit=unit_contracted,
        customer=customer_main,
        final_contract_price=Decimal("3600000.00"),
        down_payment=Decimal("600000.00"),
        currency=currency,
        contract_date=date(2026, 3, 1),
        delivery_date=date(2027, 12, 31),
        status=PropertyContract.ContractStatus.ACTIVE,
        created_by=user
    )
    ContractCoOwner.objects.create(
        contract=contract,
        co_owner=co_owner_cust,
        share_percentage=Decimal("30.00"),
        is_joint_and_several_guarantor=True
    )

    dp_pay = CustomerPayment.objects.create(
        customer=customer_main,
        amount=Decimal("600000.00"),
        payment_date=date(2026, 3, 1),
        payment_method="CASH",
        created_by=user
    )
    ContractPaymentReceipt.objects.create(
        contract=contract,
        customer_payment=dp_pay,
        installment_item=None
    )

    plan = InstallmentPlan.objects.create(
        customer=customer_main,
        total_principal=Decimal("3000000.00"),
        total_amount=Decimal("3000000.00"),
        number_of_installments=2,
        start_date=date(2026, 6, 1),
        status=InstallmentPlan.PlanStatus.ACTIVE,
        created_by=user
    )
    contract.installment_plan = plan
    contract.save(update_fields=['installment_plan'])

    item_1 = InstallmentItem.objects.create(
        plan=plan,
        installment_number=1,
        due_date=date(2026, 6, 1),
        principal_amount=Decimal("1500000.00"),
        total_amount=Decimal("1500000.00"),
        paid_amount=Decimal("500000.00"),
        cash_status=InstallmentItem.CashStatus.PARTIALLY_PAID
    )
    item_2 = InstallmentItem.objects.create(
        plan=plan,
        installment_number=2,
        due_date=date(2026, 12, 1),
        principal_amount=Decimal("1500000.00"),
        total_amount=Decimal("1500000.00"),
        paid_amount=Decimal("0.00"),
        cash_status=InstallmentItem.CashStatus.PENDING
    )

    cheque = Cheque.objects.create(
        cheque_number="CHQ-PRT-9001",
        amount=Decimal("1000000.00"),
        currency=currency,
        issue_date=date(2026, 3, 1),
        due_date=date(2026, 6, 1),
        cheque_type=ChequeType.RECEIVABLE,
        status=ChequeStatus.IN_PORTFOLIO,
        customer=customer_main,
        drawer_bank_name="البنك الأهلي المصري",
        created_by=user
    )
    ChequeInvoiceAllocation.objects.create(
        cheque=cheque,
        installment_item=item_1,
        allocated_amount=Decimal("1000000.00"),
        allocated_amount_functional=Decimal("1000000.00"),
        allocation_date=date(2026, 3, 1),
        allocation_status=AllocationStatus.APPLIED
    )

    # 3. محضر استبدال وترقية وحدة
    swap = UnitSwapRecord.objects.create(
        swap_number="SWP-PRT-2026-01",
        contract=contract,
        customer=customer_main,
        old_unit=unit_contracted,
        new_unit=unit_swap_target,
        old_unit_price=Decimal("3600000.00"),
        new_unit_price=Decimal("4400000.00"),
        price_difference=Decimal("800000.00"),
        administrative_fee=Decimal("25000.00"),
        settlement_method=UnitSwapRecord.SettlementMethod.RE_AMORTIZE_EXISTING,
        status=UnitSwapRecord.SwapStatus.DRAFT,
        created_by=user
    )

    return {
        "user": user,
        "booking": booking,
        "contract": contract,
        "swap": swap,
        "cheque": cheque,
    }


@pytest.mark.django_db
def test_contract_official_print_view(client, print_setup):
    client.force_login(print_setup["user"])
    contract = print_setup["contract"]

    url = reverse("real_estate:contract_print", kwargs={"pk": contract.pk})
    resp = client.get(url)

    assert resp.status_code == 200
    assert "real_estate/contract_print.html" in [t.name for t in resp.templates]
    assert len(resp.context["verification_hash"]) == 64
    assert len(resp.context["verification_token"]) == 16

    html = resp.content.decode("utf-8")
    assert contract.contract_number in html
    assert "الدكتور خالد عبد العزيز" in html
    assert "المهندسة سارة خالد" in html
    assert "NILE-502" in html
    assert resp.context["verification_token"] in html


@pytest.mark.django_db
def test_contract_statement_of_account_print_view(client, print_setup):
    client.force_login(print_setup["user"])
    contract = print_setup["contract"]

    url = reverse("real_estate:contract_statement_print", kwargs={"pk": contract.pk})
    resp = client.get(url)

    assert resp.status_code == 200
    assert "real_estate/contract_statement_print.html" in [t.name for t in resp.templates]
    assert resp.context["verified_down_payment"] == Decimal("600000.00")
    assert resp.context["paid_installments_total"] == Decimal("500000.00")
    assert resp.context["total_paid"] == Decimal("1100000.00")
    assert resp.context["remaining_balance"] == Decimal("2500000.00")
    assert resp.context["is_cleared"] is False
    assert len(resp.context["cheque_allocations"]) == 1

    html = resp.content.decode("utf-8")
    assert "CHQ-PRT-9001" in html
    assert "البنك الأهلي المصري" in html
    assert resp.context["verification_token"] in html


@pytest.mark.django_db
def test_booking_official_print_view(client, print_setup):
    client.force_login(print_setup["user"])
    booking = print_setup["booking"]

    url = reverse("real_estate:booking_print", kwargs={"pk": booking.pk})
    resp = client.get(url)

    assert resp.status_code == 200
    assert "real_estate/booking_print.html" in [t.name for t in resp.templates]
    assert len(resp.context["verification_hash"]) == 64

    html = resp.content.decode("utf-8")
    assert booking.booking_number in html
    assert "NILE-501" in html
    assert "محصل ومقيد بالخزينة" in html
    assert resp.context["verification_token"] in html


@pytest.mark.django_db
def test_unit_swap_official_print_view(client, print_setup):
    client.force_login(print_setup["user"])
    swap = print_setup["swap"]

    url = reverse("real_estate:swap_print", kwargs={"pk": swap.pk})
    resp = client.get(url)

    assert resp.status_code == 200
    assert "real_estate/swap_print.html" in [t.name for t in resp.templates]
    assert len(resp.context["verification_hash"]) == 64
    assert len(resp.context["installment_items"]) == 2

    html = resp.content.decode("utf-8")
    assert swap.swap_number in html
    assert "NILE-502" in html
    assert "NILE-503" in html
    assert resp.context["verification_token"] in html


@pytest.mark.django_db
def test_detail_views_expose_print_header_buttons(client, print_setup):
    client.force_login(print_setup["user"])

    # 1. صفحة تفاصيل العقد
    contract_resp = client.get(reverse("real_estate:contract_detail", kwargs={"pk": print_setup["contract"].pk}))
    assert contract_resp.status_code == 200
    c_buttons = [b["url"] for b in contract_resp.context["header_buttons"]]
    assert reverse("real_estate:contract_print", kwargs={"pk": print_setup["contract"].pk}) in c_buttons
    assert reverse("real_estate:contract_statement_print", kwargs={"pk": print_setup["contract"].pk}) in c_buttons

    # 2. صفحة تفاصيل الحجز
    booking_resp = client.get(reverse("real_estate:booking_detail", kwargs={"pk": print_setup["booking"].pk}))
    assert booking_resp.status_code == 200
    b_buttons = [b["url"] for b in booking_resp.context["header_buttons"]]
    assert reverse("real_estate:booking_print", kwargs={"pk": print_setup["booking"].pk}) in b_buttons

    # 3. صفحة تفاصيل محضر الاستبدال
    swap_resp = client.get(reverse("real_estate:swap_detail", kwargs={"pk": print_setup["swap"].pk}))
    assert swap_resp.status_code == 200
    s_buttons = [b["url"] for b in swap_resp.context["header_buttons"]]
    assert reverse("real_estate:swap_print", kwargs={"pk": print_setup["swap"].pk}) in s_buttons
