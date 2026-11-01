# -*- coding: utf-8 -*-
import pytest
from decimal import Decimal
from datetime import date
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from customer.models import Customer
from financial.models import Currency
from sale.models.installments import InstallmentPlan, InstallmentItem
from real_estate.models.project import RealEstateProject
from real_estate.models.topology import PropertyBlock, PropertyFloor
from real_estate.models.unit import PropertyUnit
from real_estate.models.contract import PropertyContract
from real_estate.models.engineering import ClientVariationOrder
from real_estate.services.variation_service import VariationOrderService

User = get_user_model()


@pytest.fixture
def variation_setup(db):
    user, _ = User.objects.get_or_create(username="site_architect", defaults={"email": "architect@test.com", "is_staff": True})
    approver, _ = User.objects.get_or_create(username="chief_eng", defaults={"email": "chief@test.com", "is_staff": True})
    currency, _ = Currency.objects.get_or_create(code="EGP", defaults={"name": "جنيه مصري", "symbol": "ج.م"})

    customer, _ = Customer.objects.get_or_create(
        code="CUST-VO-01",
        defaults={"name": "د. أشرف قنديل", "default_currency": currency}
    )

    project = RealEstateProject.objects.create(
        code="PRJ-VO-01",
        name="كمبوند بالم فالي",
        start_date=date(2025, 1, 1),
        expected_completion_date=date(2027, 12, 31),
        total_land_area=Decimal("10000.00"),
        gross_built_area=Decimal("40000.00"),
        created_by=user
    )
    block = PropertyBlock.objects.create(project=project, code="B-01", name="عمارة 1")
    floor = PropertyFloor.objects.create(block=block, floor_number=2, name="الدور الثاني")

    unit = PropertyUnit.objects.create(
        project=project,
        floor=floor,
        unit_code="PV-U201",
        gross_area=Decimal("160.00"),
        net_area=Decimal("135.00"),
        meter_price=Decimal("35000.00"),
        total_price=Decimal("5600000.00"),
        status=PropertyUnit.UnitStatus.AVAILABLE
    )

    plan = InstallmentPlan.objects.create(
        sale=None,
        total_principal=Decimal("5000000.00"),
        total_amount=Decimal("5000000.00"),
        number_of_installments=2,
        start_date=date(2026, 1, 1),
        customer=customer,
        status=InstallmentPlan.PlanStatus.ACTIVE,
        created_by=user
    )

    contract = PropertyContract.objects.create(
        contract_number="CTR-PV-2026-001",
        project=project,
        unit=unit,
        customer=customer,
        installment_plan=plan,
        contract_date=date(2026, 1, 1),
        delivery_date=date(2027, 12, 31),
        final_contract_price=Decimal("5600000.00"),
        down_payment=Decimal("600000.00"),
        currency=currency,
        created_by=user,
        status=PropertyContract.ContractStatus.ACTIVE
    )

    # قسطان رئيسيان
    InstallmentItem.objects.create(
        plan=plan,
        installment_number=1,
        due_date=date(2026, 6, 1),
        principal_amount=Decimal("2500000.00"),
        total_amount=Decimal("2500000.00"),
        paid_amount=Decimal("0.00"),
        cash_status=InstallmentItem.CashStatus.PENDING
    )
    InstallmentItem.objects.create(
        plan=plan,
        installment_number=2,
        due_date=date(2026, 12, 1),
        principal_amount=Decimal("2500000.00"),
        total_amount=Decimal("2500000.00"),
        paid_amount=Decimal("0.00"),
        cash_status=InstallmentItem.CashStatus.PENDING
    )

    return {
        "user": user,
        "approver": approver,
        "contract": contract,
        "unit": unit,
        "plan": plan,
    }


class TestVariationOrderStructuralMilestoneGuard:
    """
    اختبارات فرملة مراحل البناء الهندسية لأوامر التعديلات المعمارية
    """

    def test_permits_structural_variation_under_construction_with_demolition_cost(self, variation_setup):
        """السماح بالتعديلات الإنشائية في مرحلة الهيكل المفتوح مع احتساب تكلفة التكسير وإعادة البناء"""
        data = variation_setup

        order = VariationOrderService.validate_and_create_variation_order(
            contract=data["contract"],
            variation_type=ClientVariationOrder.VariationType.STRUCTURAL,
            stage_at_request=ClientVariationOrder.ProjectStage.UNDER_CONSTRUCTION,
            title="إزالة القاطع بين غرفة المعيشة والتراس",
            description="دمج التراس مع الصالة وإزالة الحائط الفاصل",
            demolition_rework_cost=Decimal("15000.00"),
            material_cost=Decimal("20000.00"),
            labor_cost=Decimal("12000.00"),
            supervision_fee=Decimal("5000.00"),
            user=data["user"]
        )

        assert order.status == ClientVariationOrder.OrderStatus.ENGINEERING_REVIEW
        assert order.demolition_rework_cost == Decimal("15000.00")
        assert order.total_cost == Decimal("52000.00")

    def test_rejects_structural_variation_in_post_rough_in_stage(self, variation_setup):
        """الحظر الصارم للتعديل الإنشائي بعد مرحلة تمديد السباكة والعزل لحماية العزل المائي"""
        data = variation_setup

        with pytest.raises(ValidationError) as exc:
            VariationOrderService.validate_and_create_variation_order(
                contract=data["contract"],
                variation_type=ClientVariationOrder.VariationType.STRUCTURAL,
                stage_at_request=ClientVariationOrder.ProjectStage.POST_ROUGH_IN,
                title="نقل حائط حمام الماستر",
                description="توسيع الحمام على حساب الممر",
                demolition_rework_cost=Decimal("25000.00"),
                user=data["user"]
            )

        assert "يُحظر إجراء أي تعديلات إنشائية" in str(exc.value)
        assert "POST_ROUGH_IN" in str(exc.value)

    def test_permits_cosmetic_variation_in_post_rough_in_stage(self, variation_setup):
        """السماح بتعديلات التشطيبات السطحية والديكور فقط في مرحلة ما بعد السباكة والعزل"""
        data = variation_setup

        order = VariationOrderService.validate_and_create_variation_order(
            contract=data["contract"],
            variation_type=ClientVariationOrder.VariationType.FINISHING_COSMETIC,
            stage_at_request=ClientVariationOrder.ProjectStage.POST_ROUGH_IN,
            title="تغيير نوع دهانات الصالون وتعديل ورق الحائط",
            description="دهانات قطيفة إيطالية بدلاً من البلاستيك نصف لمعة",
            demolition_rework_cost=Decimal("0.00"),
            material_cost=Decimal("18000.00"),
            labor_cost=Decimal("8000.00"),
            supervision_fee=Decimal("2000.00"),
            user=data["user"]
        )

        assert order.status == ClientVariationOrder.OrderStatus.ENGINEERING_REVIEW
        assert order.total_cost == Decimal("28000.00")

    def test_approval_schedules_supplemental_installment(self, variation_setup):
        """اعتماد أمر التعديل يُنشئ قسطاً ملحقاً إضافياً (is_supplemental=True) داخل خطة التقسيط"""
        data = variation_setup
        plan = data["plan"]

        order = VariationOrderService.validate_and_create_variation_order(
            contract=data["contract"],
            variation_type=ClientVariationOrder.VariationType.FINISHING_COSMETIC,
            stage_at_request=ClientVariationOrder.ProjectStage.UNDER_CONSTRUCTION,
            title="إضافة ديكورات جبس بورد وإنارة مخفية",
            description="بيت نور في السقف المعلق",
            material_cost=Decimal("30000.00"),
            labor_cost=Decimal("15000.00"),
            supervision_fee=Decimal("5000.00"),
            user=data["user"]
        )
        assert order.total_cost == Decimal("50000.00")

        # اعتماد وجدولة القسط الملحق
        supp_item = VariationOrderService.approve_and_schedule_variation_order(
            order=order,
            approver_user=data["approver"],
            due_date=date(2027, 6, 1)
        )

        order.refresh_from_db()
        assert order.status == ClientVariationOrder.OrderStatus.APPROVED
        assert order.approved_by == data["approver"]
        assert order.supplemental_installment_item == supp_item

        assert supp_item.is_supplemental is True
        assert supp_item.principal_amount == Decimal("50000.00")
        assert supp_item.total_amount == Decimal("50000.00")
        assert supp_item.due_date == date(2027, 6, 1)
        assert supp_item.installment_number == 3

        # التحقق من تحديث إجمالي خطة التقسيط
        plan.refresh_from_db()
        assert plan.total_principal == Decimal("5050000.00")
        assert plan.total_amount == Decimal("5050000.00")
        assert plan.number_of_installments == 3
