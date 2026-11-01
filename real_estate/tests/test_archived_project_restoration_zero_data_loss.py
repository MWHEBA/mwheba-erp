# -*- coding: utf-8 -*-
"""
Test Suite: Project Cold Archiving, Restoration & Zero-Data-Loss Retention Exemption
(Wave 3 Phase 14 - Non-Destructive Project Cold Archiving)
"""

import pytest
from decimal import Decimal
from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from core.services.data_retention_service import DataRetentionService, RetentionPolicy
from customer.models import Customer
from financial.models import Currency
from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyFloor,
    PropertyUnit,
    PropertyContract,
)
from real_estate.services.archiving_service import ProjectArchivingService

User = get_user_model()


@pytest.fixture
def archiving_setup(db):
    user, _ = User.objects.get_or_create(
        username="archive_officer",
        defaults={"email": "archive@test.com", "is_staff": True}
    )
    currency, _ = Currency.objects.get_or_create(
        code="EGP",
        defaults={"name": "جنيه مصري", "symbol": "ج.م"}
    )
    customer, _ = Customer.objects.get_or_create(
        code="CUST-ARC-01",
        defaults={"name": "العميل المستلم النهائي", "default_currency": currency}
    )

    # مشروع مكتمل البناء
    completed_project = RealEstateProject.objects.create(
        code="PRJ-ARC-01",
        name="كمبوند الشروق بلازا المكتمل",
        status=RealEstateProject.ProjectStatus.COMPLETED,
        start_date=date(2020, 1, 1),
        expected_completion_date=date(2023, 12, 31),
        actual_completion_date=date(2023, 11, 30),
        total_land_area=Decimal("15000.00"),
        gross_built_area=Decimal("45000.00"),
        created_by=user
    )

    block = PropertyBlock.objects.create(project=completed_project, code="B-01", name="بلوك 1")
    floor = PropertyFloor.objects.create(block=block, floor_number=1, name="الدور الأول")

    unit = PropertyUnit.objects.create(
        project=completed_project,
        floor=floor,
        unit_code="SHR-U101",
        unit_type=PropertyUnit.UnitType.APARTMENT,
        status=PropertyUnit.UnitStatus.DELIVERED,
        net_area=Decimal("95.00"),
        gross_area=Decimal("115.00"),
        meter_price=Decimal("10000.00"),
        base_price=Decimal("1150000.00"),
        total_price=Decimal("1150000.00")
    )

    contract = PropertyContract.objects.create(
        contract_number="CTR-ARC-001",
        project=completed_project,
        unit=unit,
        customer=customer,
        status=PropertyContract.ContractStatus.COMPLETED,
        contract_date=date(2021, 1, 1),
        delivery_date=date(2023, 12, 1),
        final_contract_price=Decimal("1150000.00"),
        down_payment=Decimal("1150000.00"),
        currency=currency,
        created_by=user
    )

    # مشروع تحت الإنشاء النشط
    active_project = RealEstateProject.objects.create(
        code="PRJ-ACTIVE-01",
        name="كمبوند المستقبل سيتي",
        status=RealEstateProject.ProjectStatus.UNDER_CONSTRUCTION,
        start_date=date(2025, 1, 1),
        expected_completion_date=date(2028, 12, 31),
        total_land_area=Decimal("25000.00"),
        gross_built_area=Decimal("80000.00"),
        created_by=user
    )

    return {
        "user": user,
        "completed_project": completed_project,
        "active_project": active_project,
        "unit": unit,
        "contract": contract,
    }


@pytest.mark.django_db
class TestArchivedProjectRestorationZeroDataLoss:

    def test_project_archiving_and_restoration(self, archiving_setup):
        """أرشفة المشروع المكتمل واستعادته لاحقاً مع الحفاظ على سلامة 100% من البيانات التاريخية"""
        user = archiving_setup["user"]
        project = archiving_setup["completed_project"]
        unit = archiving_setup["unit"]
        contract = archiving_setup["contract"]

        assert project.is_archived is False

        # أرشفة المشروع
        archived_proj = ProjectArchivingService.archive_project(
            project=project,
            user=user,
            reason="اكتمال المشروع وتسليم كامل الوحدات للملاك وانتهاء العمليات التشغيلية"
        )

        assert archived_proj.is_archived is True
        project.refresh_from_db()
        assert project.is_archived is True

        # التأكد من بقاء كافة الوحدات والعقود التابعة سليمة ومتاحة للتدقيق والمطالبات
        assert project.units.count() == 1
        assert project.contracts.count() == 1
        assert unit.unit_code == "SHR-U101"
        assert contract.contract_number == "CTR-ARC-001"

        # استعادة المشروع من الأرشيف البارد
        restored_proj = ProjectArchivingService.restore_project(project=project, user=user)
        assert restored_proj.is_archived is False
        project.refresh_from_db()
        assert project.is_archived is False

    def test_cannot_archive_active_under_construction_project(self, archiving_setup):
        """حظر أرشفة أي مشروع لا يزال قيد التخطيط أو تحت الإنشاء النشط"""
        user = archiving_setup["user"]
        active_proj = archiving_setup["active_project"]

        with pytest.raises(ValidationError, match="لا يمكن أرشفة مشروع لا يزال في مرحلة التخطيط أو تحت الإنشاء"):
            ProjectArchivingService.archive_project(project=active_proj, user=user)

    def test_data_retention_service_strictly_exempts_real_estate(self, archiving_setup):
        """التحقق الصارم من استثناء موديلات القطاع العقاري من روتينات الحذف الآلي (Decennial Liability Shield)"""
        retention_service = DataRetentionService()

        # محاولة تطبيق سياسة احتفاظ افتراضية بحذف سجلات عمرها أكثر من 30 يوماً على موديلات العقود العقارية
        test_policy = RetentionPolicy(
            model_name="real_estate.PropertyContract",
            retention_days=30,
            archive_before_delete=False
        )

        result = retention_service._process_retention_policy(policy=test_policy, dry_run=False)

        # التأكد من أن الموديل مستثنى بالكامل ولم يتم حذف أو تدمير أي سجل
        assert result["deleted_count"] == 0
        assert result["archived_count"] == 0

        # التحقق من أن العقد العقاري لا يزال موجوداً في قاعدة البيانات
        contract = archiving_setup["contract"]
        assert PropertyContract.objects.filter(pk=contract.pk).exists()
