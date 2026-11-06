# -*- coding: utf-8 -*-
"""
Tests for Phase 5.4 - Operational CRUD Views & Workflows
MWHEBA ERP — Real Estate Maintenance Escrow, Legal Notices, Landowner Partnerships & Unit Swaps
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
from customer.models import Customer
from supplier.models import Supplier
from financial.models import Currency, ChartOfAccounts, AccountType
from sale.models.installments import InstallmentPlan, InstallmentItem

from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyFloor,
    PropertyUnit,
    PropertyContract,
    LegalNotice,
    LandownerPartnership,
    LandownerUnitAllocation,
    UnitSwapRecord,
    BuildingFacilitySubledger,
    MaintenanceFundOperation,
)
from real_estate.services.facility_service import BuildingFacilityService
from real_estate.services.swap_service import UnitSwapService

User = get_user_model()


@pytest.fixture
def operations_setup(db):
    cache.delete('enabled_modules_set')
    cache.delete('module_namespace_map')

    mod, _ = SystemModule.objects.get_or_create(code='real_estate', defaults={'name_ar': 'العقارات', 'is_enabled': True})
    mod.is_enabled = True
    mod.save()
    ModuleAccessMiddleware.invalidate_cache()

    user = User.objects.create_superuser(
        username="operations_director",
        email="operations_director@test.com",
        password="password123"
    )

    currency, _ = Currency.objects.get_or_create(
        code="EGP",
        defaults={"name": "جنيه مصري", "symbol": "ج.م", "is_functional": True}
    )

    asset_type, _ = AccountType.objects.get_or_create(code='asset', defaults={'name': 'أصول', 'category': 'asset', 'nature': 'debit'})
    liability_type, _ = AccountType.objects.get_or_create(code='liability', defaults={'name': 'خصوم', 'category': 'liability', 'nature': 'credit'})
    revenue_type, _ = AccountType.objects.get_or_create(code='revenue', defaults={'name': 'إيرادات', 'category': 'revenue', 'nature': 'credit'})
    expense_type, _ = AccountType.objects.get_or_create(code='expense', defaults={'name': 'مصروفات', 'category': 'expense', 'nature': 'debit'})

    # Accounts required for Facility Escrow & Subledger
    cash_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="11170",
        defaults={"name": "حساب بنكي مقيد - صندوق صيانة المرافق", "account_type": asset_type, "is_active": True}
    )
    escrow_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="21520",
        defaults={"name": "أمانات صندوق صيانة اتحاد الشاغلين", "account_type": liability_type, "is_active": True}
    )

    # Project, Block, Floor
    project = RealEstateProject.objects.create(
        name="كمبوند زهرة الياسمين",
        code="PRJ-OPR-01",
        start_date=date.today() - timedelta(days=365),
        expected_completion_date=date.today() + timedelta(days=730),
        created_by=user
    )
    block = PropertyBlock.objects.create(project=project, name="عمارة A1", code="BLK-A1")
    floor = PropertyFloor.objects.create(block=block, name="الدور الأول", floor_number=1)

    # Customer
    customer = Customer.objects.create(
        name="عميل العمليات التجريبي",
        phone="01112223334",
        email="ops_customer@test.com"
    )

    # Units
    unit_old = PropertyUnit.objects.create(
        project=project,
        floor=floor,
        unit_code="A1-101",
        unit_type="APARTMENT",
        gross_area=Decimal("120.00"),
        net_area=Decimal("105.00"),
        meter_price=Decimal("12500.00"),
        total_price=Decimal("1500000.00"),
        status=PropertyUnit.UnitStatus.CONTRACTED
    )

    unit_new = PropertyUnit.objects.create(
        project=project,
        floor=floor,
        unit_code="A1-102",
        unit_type="APARTMENT",
        gross_area=Decimal("160.00"),
        net_area=Decimal("140.00"),
        meter_price=Decimal("12500.00"),
        total_price=Decimal("2000000.00"),
        status=PropertyUnit.UnitStatus.AVAILABLE
    )

    unit_for_landowner = PropertyUnit.objects.create(
        project=project,
        floor=floor,
        unit_code="A1-103",
        unit_type="APARTMENT",
        gross_area=Decimal("150.00"),
        net_area=Decimal("130.00"),
        meter_price=Decimal("12000.00"),
        total_price=Decimal("1800000.00"),
        status=PropertyUnit.UnitStatus.AVAILABLE
    )

    # Contract
    contract = PropertyContract.objects.create(
        contract_number="CNT-OPR-001",
        project=project,
        unit=unit_old,
        customer=customer,
        final_contract_price=Decimal("1500000.00"),
        down_payment=Decimal("150000.00"),
        contract_date=date.today() - timedelta(days=60),
        delivery_date=date.today() + timedelta(days=365),
        currency=currency,
        status=PropertyContract.ContractStatus.ACTIVE,
        created_by=user
    )

    # Installment plan with 2 unpaid items
    plan = InstallmentPlan.objects.create(
        customer=customer,
        total_amount=Decimal("1500000.00"),
        total_principal=Decimal("1500000.00"),
        total_markup=Decimal("0.00"),
        number_of_installments=2,
        start_date=date.today(),
        frequency='MONTHLY',
        created_by=user,
        status='active'
    )
    contract.installment_plan = plan
    contract.save(update_fields=['installment_plan'])

    InstallmentItem.objects.create(
        plan=plan,
        installment_number=1,
        due_date=date.today() + timedelta(days=30),
        principal_amount=Decimal("750000.00"),
        interest_amount=Decimal("0.00"),
        total_amount=Decimal("750000.00"),
        paid_amount=Decimal("0.00"),
        paid_principal=Decimal("0.00"),
        cash_status=InstallmentItem.CashStatus.PENDING
    )
    InstallmentItem.objects.create(
        plan=plan,
        installment_number=2,
        due_date=date.today() + timedelta(days=60),
        principal_amount=Decimal("750000.00"),
        interest_amount=Decimal("0.00"),
        total_amount=Decimal("750000.00"),
        paid_amount=Decimal("0.00"),
        paid_principal=Decimal("0.00"),
        cash_status=InstallmentItem.CashStatus.PENDING
    )

    # Subledger for project
    subledger = BuildingFacilitySubledger.objects.create(
        project=project,
        restricted_cash_account=cash_acc,
        maintenance_escrow_account=escrow_acc,
        created_by=user
    )

    return {
        "user": user,
        "currency": currency,
        "project": project,
        "block": block,
        "floor": floor,
        "customer": customer,
        "unit_old": unit_old,
        "unit_new": unit_new,
        "unit_for_landowner": unit_for_landowner,
        "contract": contract,
        "plan": plan,
        "subledger": subledger,
        "cash_acc": cash_acc,
        "escrow_acc": escrow_acc,
    }


# ==============================================================================
# 1. اختبارات صندوق صيانة المرافق والعمليات (Maintenance Fund Ledger)
# ==============================================================================

@pytest.mark.django_db
def test_maintenance_fund_list_view_get(client, operations_setup):
    client.force_login(operations_setup["user"])
    url = reverse("real_estate:facility_list")
    response = client.get(url)

    assert response.status_code == 200
    assert "real_estate/maintenance_fund_list.html" in [t.name for t in response.templates]
    assert "operations" in response.context
    assert "projects" in response.context
    assert "contracts" in response.context
    assert "total_operations" in response.context
    assert "total_deposits" in response.context


@pytest.mark.django_db
def test_maintenance_fund_deposit_collection(client, operations_setup):
    client.force_login(operations_setup["user"])
    url = reverse("real_estate:facility_deposit_create")
    data = {
        "contract": operations_setup["contract"].id,
        "amount": "150000.00",
        "operation_date": date.today().strftime("%Y-%m-%d"),
        "description": "تحصيل وديعة صيانة 10% بموجب العقد",
    }
    response = client.post(url, data, follow=True)

    assert response.status_code == 200
    subledger = BuildingFacilitySubledger.objects.get(pk=operations_setup["subledger"].id)
    assert subledger.total_collected_deposits == Decimal("150000.00")
    assert subledger.current_fund_balance == Decimal("150000.00")

    op = MaintenanceFundOperation.objects.filter(subledger=subledger).latest("id")
    assert op.operation_type == MaintenanceFundOperation.OperationType.DEPOSIT_COLLECTION
    assert op.amount == Decimal("150000.00")
    assert op.contract == operations_setup["contract"]


@pytest.mark.django_db
def test_maintenance_fund_yield_posting(client, operations_setup):
    client.force_login(operations_setup["user"])
    url = reverse("real_estate:facility_yield_create")
    data = {
        "project": operations_setup["project"].id,
        "yield_amount": "25000.00",
        "yield_rate": "18.50",
        "certificate_number": "CERT-2026-001",
        "description": "توزيع عائد شهادة بنكية معفاة ضريبياً لصالح الصندوق",
    }
    response = client.post(url, data, follow=True)

    assert response.status_code == 200
    subledger = BuildingFacilitySubledger.objects.get(pk=operations_setup["subledger"].id)
    assert subledger.total_yield_accumulated == Decimal("25000.00")
    assert subledger.current_fund_balance == Decimal("25000.00")

    op = MaintenanceFundOperation.objects.filter(subledger=subledger).latest("id")
    assert op.operation_type == MaintenanceFundOperation.OperationType.BANK_YIELD
    assert op.amount == Decimal("25000.00")


@pytest.mark.django_db
def test_maintenance_fund_expense_disbursement(client, operations_setup):
    client.force_login(operations_setup["user"])

    # أولاً نضع رصيد في الصندوق
    subledger = operations_setup["subledger"]
    subledger.total_collected_deposits = Decimal("100000.00")
    subledger.recalculate_balances()

    url = reverse("real_estate:facility_expense_create")
    data = {
        "project": operations_setup["project"].id,
        "expense_amount": "12000.00",
        "expense_category": MaintenanceFundOperation.ExpenseCategory.ELEVATOR,
        "operation_date": date.today().strftime("%Y-%m-%d"),
        "description": "سداد فاتورة صيانة دورية لمصاعد البرج",
    }
    response = client.post(url, data, follow=True)

    assert response.status_code == 200
    subledger.refresh_from_db()
    assert subledger.total_expenses_disbursed == Decimal("12000.00")
    assert subledger.current_fund_balance == Decimal("88000.00")

    op = MaintenanceFundOperation.objects.filter(subledger=subledger).latest("id")
    assert op.operation_type == MaintenanceFundOperation.OperationType.FACILITY_EXPENSE
    assert op.amount == Decimal("12000.00")


# ==============================================================================
# 2. اختبارات الإنذارات القانونية والتسليم الحكمي (Legal Notices)
# ==============================================================================

@pytest.mark.django_db
def test_legal_notice_list_view_get(client, operations_setup):
    client.force_login(operations_setup["user"])
    url = reverse("real_estate:legal_list")
    response = client.get(url)

    assert response.status_code == 200
    assert "real_estate/legal_notice_list.html" in [t.name for t in response.templates]
    assert "notices" in response.context
    assert "total_notices" in response.context
    assert "total_demanded" in response.context


@pytest.mark.django_db
def test_legal_notice_create_view_post(client, operations_setup):
    client.force_login(operations_setup["user"])
    url = reverse("real_estate:legal_create")
    data = {
        "contract": operations_setup["contract"].id,
        "stage": LegalNotice.EscalationStage.STAGE_3_FORMAL_DEMAND,
        "channel": LegalNotice.NoticeChannel.REGISTERED_MAIL,
        "overdue_amount": "50000.00",
        "penalty_amount": "5000.00",
        "cure_deadline_days": "15",
        "legal_letter_text": "إخطار تسليم حكمي واستلام الوحدة فوراً وسداد المتأخرات",
    }
    response = client.post(url, data, follow=True)

    assert response.status_code == 200
    notice = LegalNotice.objects.latest("id")
    assert notice.contract == operations_setup["contract"]
    assert notice.customer == operations_setup["customer"]
    assert notice.stage == LegalNotice.EscalationStage.STAGE_3_FORMAL_DEMAND
    assert notice.channel == LegalNotice.NoticeChannel.REGISTERED_MAIL
    assert notice.overdue_amount == Decimal("50000.00")
    assert notice.penalty_amount == Decimal("5000.00")
    assert notice.total_demanded_amount == Decimal("55000.00")
    assert notice.cure_deadline_days == 15
    assert notice.status == LegalNotice.NoticeStatus.SENT


@pytest.mark.django_db
def test_legal_notice_actions_served_and_cured(client, operations_setup):
    client.force_login(operations_setup["user"])

    notice = LegalNotice.objects.create(
        contract=operations_setup["contract"],
        customer=operations_setup["customer"],
        stage=LegalNotice.EscalationStage.STAGE_3_FORMAL_DEMAND,
        channel=LegalNotice.NoticeChannel.COURT_BAILIFF,
        overdue_amount=Decimal("30000.00"),
        total_demanded_amount=Decimal("30000.00"),
        cure_deadline_days=15,
        status=LegalNotice.NoticeStatus.SENT,
        created_by=operations_setup["user"]
    )

    url = reverse("real_estate:legal_action", kwargs={"pk": notice.pk})

    # 1. إثبات الإعلان الرسمي
    resp1 = client.post(url, {"action_type": "mark_served"}, follow=True)
    assert resp1.status_code == 200
    notice.refresh_from_db()
    assert notice.status == LegalNotice.NoticeStatus.SERVED

    # 2. إثبات التسليم
    resp2 = client.post(url, {"action_type": "mark_delivered"}, follow=True)
    assert resp2.status_code == 200
    notice.refresh_from_db()
    assert notice.status == LegalNotice.NoticeStatus.DELIVERED


# ==============================================================================
# 3. اختبارات اتفاقيات ملاك الأراضي والتخصيص العيني (Landowner Partnerships)
# ==============================================================================

@pytest.mark.django_db
def test_landowner_partnership_list_view_get(client, operations_setup):
    client.force_login(operations_setup["user"])
    url = reverse("real_estate:partnership_list")
    response = client.get(url)

    assert response.status_code == 200
    assert "real_estate/partnership_list.html" in [t.name for t in response.templates]
    assert "partnerships" in response.context
    assert "total_partnerships" in response.context
    assert "total_land_valuation" in response.context


@pytest.mark.django_db
def test_landowner_partnership_create_view_post(client, operations_setup):
    client.force_login(operations_setup["user"])
    url = reverse("real_estate:partnership_create")
    data = {
        "project": operations_setup["project"].id,
        "partner_name": "الحاج رضوان مالك الأرض",
        "partner_national_id": "28501011234567",
        "partner_phone": "01009998877",
        "partnership_type": LandownerPartnership.PartnershipType.UNIT_ALLOCATION,
        "revenue_share_percentage": "35.00",
        "land_area_sqm": "2500.00",
        "agreed_land_valuation": "12000000.00",
        "contract_date": date.today().strftime("%Y-%m-%d"),
        "terms_notes": "تخصيص 3 وحدات عينية في البرج A1",
    }
    response = client.post(url, data, follow=True)

    assert response.status_code == 200
    partnership = LandownerPartnership.objects.latest("id")
    assert partnership.project == operations_setup["project"]
    assert partnership.partner_name == "الحاج رضوان مالك الأرض"
    assert partnership.revenue_share_percentage == Decimal("35.00")
    assert partnership.agreed_land_valuation == Decimal("12000000.00")
    assert partnership.status == LandownerPartnership.PartnershipStatus.DRAFT


@pytest.mark.django_db
def test_landowner_partnership_detail_and_unit_allocation(client, operations_setup):
    client.force_login(operations_setup["user"])

    partnership = LandownerPartnership.objects.create(
        project=operations_setup["project"],
        partner_name="المستشار مالك الأرض",
        partnership_type=LandownerPartnership.PartnershipType.UNIT_ALLOCATION,
        revenue_share_percentage=Decimal("30.00"),
        land_area_sqm=Decimal("1800.00"),
        agreed_land_valuation=Decimal("8000000.00"),
        contract_date=date.today(),
        created_by=operations_setup["user"]
    )

    detail_url = reverse("real_estate:partnership_detail", kwargs={"pk": partnership.pk})
    detail_resp = client.get(detail_url)
    assert detail_resp.status_code == 200
    assert "real_estate/partnership_detail.html" in [t.name for t in detail_resp.templates]
    assert detail_resp.context["partnership"] == partnership

    # تخصيص الوحدة عيناً لمالك الأرض
    target_unit = operations_setup["unit_for_landowner"]
    allocate_url = reverse("real_estate:partnership_allocate_unit", kwargs={"pk": partnership.pk})
    alloc_resp = client.post(allocate_url, {
        "unit": target_unit.id,
        "notes": "تخصيص عيني بموجب البند الخامس من عقد الشراكة"
    }, follow=True)

    assert alloc_resp.status_code == 200
    target_unit.refresh_from_db()
    assert target_unit.status == PropertyUnit.UnitStatus.LANDOWNER_ALLOCATED

    allocation = LandownerUnitAllocation.objects.get(partnership=partnership, unit=target_unit)
    assert allocation.allocated_by == operations_setup["user"]


@pytest.mark.django_db
def test_landowner_unit_allocation_rejects_unavailable_unit(client, operations_setup):
    client.force_login(operations_setup["user"])

    partnership = LandownerPartnership.objects.create(
        project=operations_setup["project"],
        partner_name="المالك ش.م.م",
        created_by=operations_setup["user"]
    )

    # وحدة قديمة متعاقد عليها بالفعل CONTRACTED
    contracted_unit = operations_setup["unit_old"]
    allocate_url = reverse("real_estate:partnership_allocate_unit", kwargs={"pk": partnership.pk})
    resp = client.post(allocate_url, {"unit": contracted_unit.id}, follow=True)

    assert resp.status_code == 200
    contracted_unit.refresh_from_db()
    assert contracted_unit.status == PropertyUnit.UnitStatus.CONTRACTED
    assert not LandownerUnitAllocation.objects.filter(partnership=partnership, unit=contracted_unit).exists()


# ==============================================================================
# 4. اختبارات تبديل وترقية الوحدات وإعادة الجدولة (Unit Swaps & Rescheduling)
# ==============================================================================

@pytest.mark.django_db
def test_unit_swap_list_view_get(client, operations_setup):
    client.force_login(operations_setup["user"])
    url = reverse("real_estate:swap_list")
    response = client.get(url)

    assert response.status_code == 200
    assert "real_estate/swap_list.html" in [t.name for t in response.templates]
    assert "swaps" in response.context
    assert "total_swaps" in response.context
    assert "executed_count" in response.context


@pytest.mark.django_db
def test_unit_swap_create_view_post(client, operations_setup):
    client.force_login(operations_setup["user"])
    url = reverse("real_estate:swap_create")

    data = {
        "contract": operations_setup["contract"].id,
        "new_unit": operations_setup["unit_new"].id,
        "administrative_fee": "15000.00",
        "settlement_method": UnitSwapRecord.SettlementMethod.RE_AMORTIZE_EXISTING,
        "notes": "ترقية لوحدة مساحة أكبر بناء على رغبة العميل",
    }
    response = client.post(url, data, follow=True)

    assert response.status_code == 200
    swap = UnitSwapRecord.objects.latest("id")
    assert swap.contract == operations_setup["contract"]
    assert swap.customer == operations_setup["customer"]
    assert swap.old_unit == operations_setup["unit_old"]
    assert swap.new_unit == operations_setup["unit_new"]
    assert swap.old_unit_price == Decimal("1500000.00")
    assert swap.new_unit_price == Decimal("2000000.00")
    assert swap.price_difference == Decimal("500000.00")
    assert swap.administrative_fee == Decimal("15000.00")
    assert swap.status == UnitSwapRecord.SwapStatus.DRAFT


@pytest.mark.django_db
def test_unit_swap_detail_and_execute_atomic_flow(client, operations_setup):
    client.force_login(operations_setup["user"])

    contract = operations_setup["contract"]
    old_unit = operations_setup["unit_old"]
    new_unit = operations_setup["unit_new"]
    plan = operations_setup["plan"]

    # إنشاء محضر الاستبدال
    swap = UnitSwapService.create_swap_record(
        contract=contract,
        new_unit=new_unit,
        administrative_fee=Decimal("10000.00"),
        settlement_method=UnitSwapRecord.SettlementMethod.RE_AMORTIZE_EXISTING,
        notes="طلب ترقية لوحدة A1-102",
        user=operations_setup["user"]
    )

    # فحص شاشة التفاصيل
    detail_url = reverse("real_estate:swap_detail", kwargs={"pk": swap.pk})
    detail_resp = client.get(detail_url)
    assert detail_resp.status_code == 200
    assert "real_estate/swap_detail.html" in [t.name for t in detail_resp.templates]
    assert detail_resp.context["swap"] == swap

    # تنفيذ المحضر ذرياً عبر POST
    exec_url = reverse("real_estate:swap_execute", kwargs={"pk": swap.pk})
    exec_resp = client.post(exec_url, follow=True)

    assert exec_resp.status_code == 200

    # التحقق من حالات الوحدات بعد التنفيذ
    old_unit.refresh_from_db()
    new_unit.refresh_from_db()
    assert old_unit.status == PropertyUnit.UnitStatus.AVAILABLE
    assert new_unit.status == PropertyUnit.UnitStatus.CONTRACTED

    # التحقق من العقد
    contract.refresh_from_db()
    assert contract.unit == new_unit
    assert contract.final_contract_price == Decimal("2000000.00")

    # التحقق من الأقساط (إعادة الجدولة: فارق السعر 500,000 موزعة على قسطين = 250,000 لكل قسط)
    items = list(plan.items.order_by("installment_number"))
    assert len(items) == 2
    assert items[0].principal_amount == Decimal("1000000.00")
    assert items[1].principal_amount == Decimal("1000000.00")

    plan.refresh_from_db()
    assert plan.total_principal == Decimal("2000000.00")
    assert plan.total_amount == Decimal("2000000.00")

    # التحقق من حالة المحضر
    swap.refresh_from_db()
    assert swap.status == UnitSwapRecord.SwapStatus.EXECUTED
    assert swap.executed_at is not None
