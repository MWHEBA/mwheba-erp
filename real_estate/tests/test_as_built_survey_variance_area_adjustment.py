# -*- coding: utf-8 -*-
"""
Test Suite: As-Built Survey Variance & Tolerance Adjustment
(Wave 3 Phase 14 - As-Built Survey Variance & Area Adjustment)
"""

import pytest
from decimal import Decimal
from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from customer.models import Customer
from financial.models import Currency
from sale.models.installments import InstallmentPlan, InstallmentItem
from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyFloor,
    PropertyUnit,
    PropertyContract,
    AsBuiltSurveyAdjustment,
)
from real_estate.services.survey_variance_service import SurveyVarianceService

User = get_user_model()


@pytest.fixture
def survey_setup(db):
    user, _ = User.objects.get_or_create(
        username="surveyor_eng",
        defaults={"email": "surveyor@test.com", "is_staff": True}
    )
    approver, _ = User.objects.get_or_create(
        username="tech_manager",
        defaults={"email": "tech_mgr@test.com", "is_staff": True}
    )
    currency, _ = Currency.objects.get_or_create(
        code="EGP",
        defaults={"name": "جنيه مصري", "symbol": "ج.م"}
    )

    customer, _ = Customer.objects.get_or_create(
        code="CUST-SRV-01",
        defaults={"name": "السيد طارق سليم", "default_currency": currency}
    )

    project = RealEstateProject.objects.create(
        code="PRJ-SRV-01",
        name="كمبوند اللوتس ريزيدنس",
        start_date=date(2024, 1, 1),
        expected_completion_date=date(2026, 12, 31),
        total_land_area=Decimal("10000.00"),
        gross_built_area=Decimal("35000.00"),
        created_by=user
    )
    block = PropertyBlock.objects.create(project=project, code="B-05", name="مبنى الأوركيد")
    floor = PropertyFloor.objects.create(block=block, floor_number=3, name="الدور الثالث")

    unit = PropertyUnit.objects.create(
        project=project,
        floor=floor,
        unit_code="LOTUS-U303",
        unit_type=PropertyUnit.UnitType.APARTMENT,
        status=PropertyUnit.UnitStatus.CONTRACTED,
        net_area=Decimal("85.00"),
        gross_area=Decimal("100.00"),
        meter_price=Decimal("10000.00"),
        base_price=Decimal("1000000.00"),
        total_price=Decimal("1000000.00")
    )

    contract = PropertyContract.objects.create(
        contract_number="CTR-SRV-001",
        project=project,
        unit=unit,
        customer=customer,
        status=PropertyContract.ContractStatus.ACTIVE,
        contract_date=date(2026, 1, 1),
        delivery_date=date(2027, 12, 31),
        final_contract_price=Decimal("1000000.00"),
        down_payment=Decimal("200000.00"),
        currency=currency,
        created_by=user
    )

    plan = InstallmentPlan.objects.create(
        customer=customer,
        total_principal=Decimal("800000.00"),
        total_amount=Decimal("800000.00"),
        number_of_installments=4,
        start_date=date(2026, 4, 1),
        frequency='QUARTERLY',
        created_by=user
    )
    contract.installment_plan = plan
    contract.save(update_fields=['installment_plan'])

    # توليد 4 أقساط كل قسط 200,000
    for i in range(1, 5):
        InstallmentItem.objects.create(
            plan=plan,
            installment_number=i,
            due_date=date(2027, i * 2, 1),
            principal_amount=Decimal("200000.00"),
            interest_amount=Decimal("0.00"),
            total_amount=Decimal("200000.00"),
            paid_amount=Decimal("0.00"),
            paid_principal=Decimal("0.00"),
            cash_status=InstallmentItem.CashStatus.PENDING
        )

    return {
        "user": user,
        "approver": approver,
        "currency": currency,
        "project": project,
        "unit": unit,
        "contract": contract,
        "plan": plan,
        "customer": customer,
    }


@pytest.mark.django_db
class TestAsBuiltSurveyVarianceAreaAdjustment:

    def test_survey_variance_within_tolerance(self, survey_setup):
        """فارق المساحة ضمن نسبة التفاوت المسموحة (±3%) لا يولد أي تسوية مالية"""
        contract = survey_setup["contract"]
        unit = survey_setup["unit"]
        user = survey_setup["user"]

        # مساحة تعاقدية 100 م²، مساحة فعلية 102 م² (+2.00% <= 3.00%)
        adj = SurveyVarianceService.calculate_and_create_adjustment(
            contract=contract,
            surveyed_gross_area=Decimal("102.00"),
            tolerance_percentage=Decimal("3.00"),
            user=user
        )

        assert adj.area_variance == Decimal("2.00")
        assert adj.area_variance_percentage == Decimal("2.00")
        assert adj.adjustment_type == AsBuiltSurveyAdjustment.AdjustmentType.WITHIN_TOLERANCE

        executed = SurveyVarianceService.execute_adjustment(adj, user=user)
        assert executed.status == AsBuiltSurveyAdjustment.AdjustmentStatus.EXECUTED

        unit.refresh_from_db()
        contract.refresh_from_db()

        # تم تحديث المساحة الفعلية، وبقي السعر التعاقدي دون تغيير
        assert unit.gross_area == Decimal("102.00")
        assert contract.final_contract_price == Decimal("1000000.00")

    def test_survey_variance_surplus_charge(self, survey_setup):
        """زيادة المساحة المشروعة تتجاوز التفاوت (+6%) تولد قسط تسوية ختامي وتزيد قيمة العقد"""
        contract = survey_setup["contract"]
        unit = survey_setup["unit"]
        plan = survey_setup["plan"]
        user = survey_setup["user"]

        # مساحة تعاقدية 100 م²، مساحة فعلية 106 م² (+6.00% > 3.00%)
        # الفارق = +6 م² × 10,000 ج.م/م² = +60,000 ج.م
        adj = SurveyVarianceService.calculate_and_create_adjustment(
            contract=contract,
            surveyed_gross_area=Decimal("106.00"),
            tolerance_percentage=Decimal("3.00"),
            user=user
        )

        assert adj.area_variance == Decimal("6.00")
        assert adj.financial_variance == Decimal("60000.00")
        assert adj.adjustment_type == AsBuiltSurveyAdjustment.AdjustmentType.SURPLUS_CHARGE

        SurveyVarianceService.execute_adjustment(adj, user=user)

        unit.refresh_from_db()
        contract.refresh_from_db()
        plan.refresh_from_db()

        # تحديث مساحة الوحدة وسعر العقد
        assert unit.gross_area == Decimal("106.00")
        assert contract.final_contract_price == Decimal("1060000.00")

        # إضافة قسط تسوية خامس بقيمة 60,000 ج.م
        assert plan.items.count() == 5
        settlement_item = plan.items.order_by('-installment_number').first()
        assert settlement_item.installment_number == 5
        assert settlement_item.principal_amount == Decimal("60000.00")
        assert settlement_item.is_overrun_adjusted is True
        assert settlement_item.is_supplemental is True
        assert plan.total_principal == Decimal("860000.00")

    def test_survey_variance_deficit_credit(self, survey_setup):
        """عجز المساحة يتجاوز التفاوت (-5%) يخصم من قيمة الأقساط الأخيرة ويخفض سعر العقد"""
        contract = survey_setup["contract"]
        unit = survey_setup["unit"]
        plan = survey_setup["plan"]
        user = survey_setup["user"]

        # مساحة تعاقدية 100 م²، مساحة فعلية 95 م² (-5.00% < -3.00%)
        # العجز = -5 م² × 10,000 ج.م = -50,000 ج.م
        adj = SurveyVarianceService.calculate_and_create_adjustment(
            contract=contract,
            surveyed_gross_area=Decimal("95.00"),
            tolerance_percentage=Decimal("3.00"),
            user=user
        )

        assert adj.area_variance == Decimal("-5.00")
        assert adj.financial_variance == Decimal("-50000.00")
        assert adj.adjustment_type == AsBuiltSurveyAdjustment.AdjustmentType.DEFICIT_CREDIT

        SurveyVarianceService.execute_adjustment(adj, user=user)

        unit.refresh_from_db()
        contract.refresh_from_db()
        plan.refresh_from_db()

        # مساحة الوحدة أصبحت 95 م² وسعر العقد انخفض إلى 950,000 ج.م
        assert unit.gross_area == Decimal("95.00")
        assert contract.final_contract_price == Decimal("950000.00")

        # تم تخفيض القسط الأخير من 200,000 إلى 150,000 ج.م
        last_item = plan.items.order_by('-installment_number').first()
        assert last_item.principal_amount == Decimal("150000.00")
        assert plan.total_principal == Decimal("750000.00")

    def test_cannot_reexecute_survey_adjustment(self, survey_setup):
        """منع تكرار تنفيذ ملحق التسوية المساحية المنفذ مسبقاً"""
        contract = survey_setup["contract"]
        user = survey_setup["user"]

        adj = SurveyVarianceService.calculate_and_create_adjustment(
            contract=contract,
            surveyed_gross_area=Decimal("105.00"),
            user=user
        )
        SurveyVarianceService.execute_adjustment(adj, user=user)

        with pytest.raises(ValidationError, match="تم تنفيذه مسبقاً"):
            SurveyVarianceService.execute_adjustment(adj, user=user)
