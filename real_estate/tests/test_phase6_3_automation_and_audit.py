# -*- coding: utf-8 -*-
"""
Tests for Phase 6.3 - Real Estate Scheduled Background Automation & Final System Audit
MWHEBA ERP — Real Estate Wave 6 (Nightly Booking Sweeper Task, Pre-Due & Escalation Radar Task, CLI Commands)
"""
import pytest
from io import StringIO
from decimal import Decimal
from datetime import date, timedelta
from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.core.cache import cache

from core.models import SystemModule
from core.middleware.module_control import ModuleAccessMiddleware
from customer.models import Customer
from financial.models import Currency, ChartOfAccounts, AccountType
from sale.models.installments import InstallmentPlan, InstallmentItem

from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyFloor,
    PropertyUnit,
    UnitBooking,
    PropertyContract,
    LegalNotice,
)
from real_estate.tasks import (
    sweep_expired_unit_bookings_task,
    dispatch_installment_escalation_radar_task,
)
from corporate_erp.celery import app as celery_app

User = get_user_model()


@pytest.fixture
def automation_setup(db):
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
        username="auto_ops_admin",
        email="auto@test.com",
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
        code="PRJ-AUT-01",
        name="كومباوند الروضة الذكي",
        project_type=RealEstateProject.ProjectType.RESIDENTIAL,
        status=RealEstateProject.ProjectStatus.UNDER_CONSTRUCTION,
        start_date=date(2025, 1, 1),
        expected_completion_date=date(2027, 12, 31),
        total_land_area=Decimal("6000.00"),
        gross_built_area=Decimal("18000.00"),
        created_by=user
    )

    block = PropertyBlock.objects.create(project=project, code="BLK-AUT-A", name="مبنى الياسمين")
    floor = PropertyFloor.objects.create(block=block, floor_number=2, name="الدور الثاني")

    unit_expired = PropertyUnit.objects.create(
        project=project,
        floor=floor,
        unit_code="RWD-201",
        gross_area=Decimal("150.00"),
        net_area=Decimal("130.00"),
        meter_price=Decimal("20000.00"),
        base_price=Decimal("3000000.00"),
        total_price=Decimal("3000000.00"),
        status=PropertyUnit.UnitStatus.RESERVED
    )
    unit_active_contract = PropertyUnit.objects.create(
        project=project,
        floor=floor,
        unit_code="RWD-202",
        gross_area=Decimal("180.00"),
        net_area=Decimal("155.00"),
        meter_price=Decimal("20000.00"),
        base_price=Decimal("3600000.00"),
        total_price=Decimal("3600000.00"),
        status=PropertyUnit.UnitStatus.CONTRACTED
    )

    customer = Customer.objects.create(
        code="CUST-AUT-01",
        name="المهندس طارق علام",
        phone="01098765432",
        default_currency=currency
    )

    # 1. حجز منتهي الصلاحية ومربوط بالوحدة RWD-201
    expired_booking = UnitBooking.objects.create(
        booking_number="BKG-AUT-EXP-01",
        unit=unit_expired,
        customer=customer,
        booking_date=date(2026, 4, 1),
        expiry_date=date(2026, 4, 10),
        holding_deposit=Decimal("50000.00"),
        status=UnitBooking.BookingStatus.ACTIVE,
        created_by=user
    )
    unit_expired.current_booking = expired_booking
    unit_expired.save(update_fields=['current_booking'])

    # 2. عقد نشط به قسط يستحق بعد 3 أيام (T-3 Pre-Due) وقسط متأخر بـ 10 أيام (T+10 Overdue)
    contract = PropertyContract.objects.create(
        contract_number="CTR-AUT-2026-01",
        project=project,
        unit=unit_active_contract,
        customer=customer,
        final_contract_price=Decimal("3600000.00"),
        down_payment=Decimal("600000.00"),
        currency=currency,
        contract_date=date(2026, 1, 1),
        delivery_date=date(2027, 12, 31),
        status=PropertyContract.ContractStatus.ACTIVE,
        created_by=user
    )

    plan = InstallmentPlan.objects.create(
        customer=customer,
        total_principal=Decimal("3000000.00"),
        total_amount=Decimal("3000000.00"),
        number_of_installments=2,
        start_date=date(2026, 4, 20),
        status=InstallmentPlan.PlanStatus.ACTIVE,
        created_by=user
    )
    contract.installment_plan = plan
    contract.save(update_fields=['installment_plan'])

    # تقييم بتاريخ مرجعي 2026-05-01:
    # القسط 1 مستحق في 2026-04-21 (متأخر 10 أيام -> STAGE_2_GRACE_EXPIRED)
    item_overdue = InstallmentItem.objects.create(
        plan=plan,
        installment_number=1,
        due_date=date(2026, 4, 21),
        principal_amount=Decimal("1500000.00"),
        total_amount=Decimal("1500000.00"),
        paid_amount=Decimal("0.00"),
        cash_status=InstallmentItem.CashStatus.PENDING
    )
    # القسط 2 مستحق في 2026-05-04 (باقي 3 أيام -> STAGE_1_PRE_DUE)
    item_predue = InstallmentItem.objects.create(
        plan=plan,
        installment_number=2,
        due_date=date(2026, 5, 4),
        principal_amount=Decimal("1500000.00"),
        total_amount=Decimal("1500000.00"),
        paid_amount=Decimal("0.00"),
        cash_status=InstallmentItem.CashStatus.PENDING
    )

    return {
        "user": user,
        "unit_expired": unit_expired,
        "expired_booking": expired_booking,
        "contract": contract,
        "item_overdue": item_overdue,
        "item_predue": item_predue,
    }


@pytest.mark.django_db
def test_nightly_booking_sweeper_celery_task(automation_setup):
    res = sweep_expired_unit_bookings_task(as_of_date_str="2026-05-01")
    assert res["success"] is True
    assert res["skipped"] is False
    assert res["released_count"] == 1

    booking = automation_setup["expired_booking"]
    unit = automation_setup["unit_expired"]
    booking.refresh_from_db()
    unit.refresh_from_db()

    assert booking.status == UnitBooking.BookingStatus.EXPIRED_RELEASED
    assert unit.status == PropertyUnit.UnitStatus.AVAILABLE
    assert unit.current_booking is None


@pytest.mark.django_db
def test_installment_escalation_radar_task_and_idempotency(automation_setup):
    # التشغيل الأول في 2026-05-01: يصدر إشعارين (واحد T-3 وواحد T+10 مع غرامة 10 أيام)
    res_1 = dispatch_installment_escalation_radar_task(as_of_date_str="2026-05-01")
    assert res_1["success"] is True
    assert res_1["processed_count"] == 2
    assert res_1["skipped_duplicate_count"] == 0
    assert res_1["stage_counts"][LegalNotice.EscalationStage.STAGE_1_PRE_DUE] == 1
    assert res_1["stage_counts"][LegalNotice.EscalationStage.STAGE_2_GRACE_EXPIRED] == 1

    overdue_item = automation_setup["item_overdue"]
    overdue_item.refresh_from_db()
    # غرامة 10 أيام على 1,500,000 بمعدل 0.001 يومياً = 15,000.00
    assert overdue_item.penalty_amount == Decimal("15000.00")

    # التشغيل الثاني في نفس اليوم: يجب تخطي الإشعارين لمنع التكرار (Idempotent)
    res_2 = dispatch_installment_escalation_radar_task(as_of_date_str="2026-05-01")
    assert res_2["processed_count"] == 0
    assert res_2["skipped_duplicate_count"] == 2

    # التشغيل الثالث في اليوم التالي (2026-05-02 -> تأخير 11 يوماً): يحدث الغرامة إلى 16,500 دون تكرار الإشعار
    res_3 = dispatch_installment_escalation_radar_task(as_of_date_str="2026-05-02")
    assert res_3["processed_count"] == 0
    assert res_3["penalties_updated_count"] == 1
    overdue_item.refresh_from_db()
    assert overdue_item.penalty_amount == Decimal("16500.00")


@pytest.mark.django_db
def test_tasks_skip_cleanly_when_real_estate_module_disabled(automation_setup):
    mod = SystemModule.objects.get(code='real_estate')
    mod.is_enabled = False
    mod.save()

    sweep_res = sweep_expired_unit_bookings_task(as_of_date_str="2026-05-01")
    assert sweep_res["skipped"] is True
    assert sweep_res["released_count"] == 0

    radar_res = dispatch_installment_escalation_radar_task(as_of_date_str="2026-05-01")
    assert radar_res["skipped"] is True
    assert radar_res["processed_count"] == 0


@pytest.mark.django_db
def test_management_commands_and_celery_beat_schedule(automation_setup):
    # التحقق من تسجيل المهام في Celery Beat Schedule
    schedule = celery_app.conf.beat_schedule
    assert 'real-estate-nightly-booking-sweeper' in schedule
    assert 'real-estate-installment-escalation-radar' in schedule

    # اختبار أمر الإدارة CLI لرادار الأقساط
    out = StringIO()
    call_command(
        'run_real_estate_escalation_radar',
        '--as-of-date=2026-05-01',
        '--stage=STAGE_1_PRE_DUE',
        stdout=out
    )
    output_text = out.getvalue()
    assert "تم إصدار 1 إشعار" in output_text
