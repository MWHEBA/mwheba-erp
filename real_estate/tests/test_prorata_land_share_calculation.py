# -*- coding: utf-8 -*-
import pytest
from decimal import Decimal
from datetime import date
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from real_estate.models.project import RealEstateProject
from real_estate.models.topology import PropertyBlock, PropertyFloor
from real_estate.models.unit import PropertyUnit
from real_estate.services.prorata_land_share_service import ProrataLandShareService

User = get_user_model()


@pytest.fixture
def engineering_setup(db):
    user, _ = User.objects.get_or_create(username="civil_eng", defaults={"is_staff": True})

    # مشروع أرضه 2,000 م² ومسطحه البنائي 10,000 م²
    project = RealEstateProject.objects.create(
        code="PRJ-ENG-01",
        name="برج اللؤلؤة السكني",
        start_date=date(2025, 1, 1),
        expected_completion_date=date(2027, 12, 31),
        total_land_area=Decimal("2000.00"),
        gross_built_area=Decimal("10000.00"),
        created_by=user
    )
    block = PropertyBlock.objects.create(project=project, code="BLK-1", name="برج 1")
    floor = PropertyFloor.objects.create(block=block, floor_number=4, name="الدور الرابع")

    # وحدة مساحتها 200 م² (تمثل بالضبط 200 / 10,000 = 2% من المبنى)
    unit = PropertyUnit.objects.create(
        project=project,
        floor=floor,
        unit_code="ENG-U401",
        gross_area=Decimal("200.00"),
        net_area=Decimal("170.00"),
        meter_price=Decimal("20000.00"),
        total_price=Decimal("4000000.00"),
        status=PropertyUnit.UnitStatus.AVAILABLE
    )

    return {
        "user": user,
        "project": project,
        "unit": unit
    }


class TestProrataLandShareCalculation:
    """
    اختبارات الحسابات الهندسية للحصة الشائعة في الأرض وفق قانون الشهر العقاري 9 لسنة 2022
    """

    def test_basic_pro_rata_land_calculation(self, engineering_setup):
        """حساب الحصة الشائعة بدقة: 200م² من 10,000م² بناء على 2,000م² أرض"""
        unit = engineering_setup["unit"]

        result = ProrataLandShareService.calculate_pro_rata_shares(unit)

        # النسبة: 200 / 10000 = 0.02 (2.0000%)
        assert result["percentage"] == Decimal("2.0000")

        # مساحة الأرض الشائعة: 2,000 * 2% = 40.0000 م²
        assert result["land_share_sqm"] == Decimal("40.0000")

        # الكسر الاعتيادي المبسط: 200 / 10000 = 1 / 50
        assert result["fraction_str"] == "1/50"
        assert result["simplified_numerator"] == 1
        assert result["simplified_denominator"] == 50

    def test_qirat_and_sahm_traditional_expression(self, engineering_setup):
        """التعبير القانوني بالقراريط والأسهم من أصل 24 قيراط"""
        unit = engineering_setup["unit"]

        result = ProrataLandShareService.calculate_pro_rata_shares(unit)

        # 2% من 24 قيراط = 0.48 قيراط = 0 قيراط و (0.48 * 24 = 11.52 سهم)
        assert "0 ط و 11.52 سهم من 24 قيراط" in result["qirat_expression"]

    def test_legal_clause_conforming_to_law_9_2022(self, engineering_setup):
        """التحقق من اشتمال البند القانوني على نص القانون 9 لسنة 2022 والمساحات المشهرة"""
        unit = engineering_setup["unit"]

        result = ProrataLandShareService.calculate_pro_rata_shares(unit)
        clause = result["legal_clause_ar"]

        assert "القانون رقم 9 لسنة 2022" in clause
        assert "حصة شائعة في أرض وبناء العقار" in clause
        assert "200.00 م²" in clause
        assert "10,000.00 م²" in clause
        assert "40.0000 م²" in clause
        assert "2,000.00 م²" in clause

    def test_validation_on_zero_land_area(self, engineering_setup):
        """رفع خطأ تحقق إذا كانت مساحة أرض المشروع تساوي صفراً"""
        project = engineering_setup["project"]
        project.total_land_area = Decimal("0.00")
        project.save()

        unit = engineering_setup["unit"]

        with pytest.raises(ValidationError) as exc:
            ProrataLandShareService.calculate_pro_rata_shares(unit)

        assert "مساحة أرض المشروع" in str(exc.value)

    def test_fallback_to_sum_of_unit_areas_if_gba_zero(self, engineering_setup):
        """إذا لم يكن المسطح الإجمالي محدداً على المشروع، يتم احتسابه من مجموع مساحات الوحدات"""
        project = engineering_setup["project"]
        project.gross_built_area = Decimal("0.00")
        project.save()

        unit = engineering_setup["unit"]

        # إضافة وحدة أخرى مساحتها 300 م² ليصبح الإجمالي 500 م²
        floor = unit.floor
        PropertyUnit.objects.create(
            project=project,
            floor=floor,
            unit_code="ENG-U402",
            gross_area=Decimal("300.00"),
            net_area=Decimal("250.00"),
            meter_price=Decimal("20000.00"),
            total_price=Decimal("6000000.00"),
            status=PropertyUnit.UnitStatus.AVAILABLE
        )

        result = ProrataLandShareService.calculate_pro_rata_shares(unit)

        # الإجمالي المحسوب = 200 + 300 = 500 م²
        # نسبة الوحدة الأولى = 200 / 500 = 40.0000%
        # حصة الأرض = 2000 * 40% = 800.0000 م²
        assert result["total_project_gba"] == Decimal("500.00")
        assert result["percentage"] == Decimal("40.0000")
        assert result["land_share_sqm"] == Decimal("800.0000")
        assert result["fraction_str"] == "2/5"
