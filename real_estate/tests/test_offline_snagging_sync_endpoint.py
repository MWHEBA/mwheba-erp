# -*- coding: utf-8 -*-
import uuid
import pytest
from decimal import Decimal
from datetime import date
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from real_estate.models.project import RealEstateProject
from real_estate.models.topology import PropertyBlock, PropertyFloor
from real_estate.models.unit import PropertyUnit
from real_estate.models.engineering import UnitSnagItem
from real_estate.services.snagging_service import OfflineSnaggingSyncService

User = get_user_model()


@pytest.fixture
def snagging_setup(db):
    user, _ = User.objects.get_or_create(username="site_inspector", defaults={"email": "inspector@test.com", "is_staff": True})
    engineer, _ = User.objects.get_or_create(username="consultant_eng", defaults={"email": "consultant@test.com", "is_staff": True})

    project = RealEstateProject.objects.create(
        code="PRJ-SNG-01",
        name="أبراج النيل التخصصية",
        start_date=date(2025, 1, 1),
        expected_completion_date=date(2027, 12, 31),
        total_land_area=Decimal("3000.00"),
        gross_built_area=Decimal("15000.00"),
        created_by=user
    )
    block = PropertyBlock.objects.create(project=project, code="T-01", name="برج 1")
    floor = PropertyFloor.objects.create(block=block, floor_number=5, name="الدور الخامس")

    unit = PropertyUnit.objects.create(
        project=project,
        floor=floor,
        unit_code="SNG-U501",
        gross_area=Decimal("140.00"),
        net_area=Decimal("120.00"),
        meter_price=Decimal("25000.00"),
        total_price=Decimal("3500000.00"),
        status=PropertyUnit.UnitStatus.AVAILABLE
    )

    return {
        "user": user,
        "engineer": engineer,
        "unit": unit
    }


class TestOfflineSnaggingSyncEndpoint:
    """
    اختبارات مزامنة حزمة ملاحظات الموقع الميدانية المسجلة دون اتصال (Offline-First Sync)
    """

    def test_sync_batch_snags_creates_and_links_records(self, snagging_setup):
        """مزامنة حزمة ملاحظات مجمعة مسجلة بـ UUID محلي من IndexedDB"""
        data = snagging_setup
        unit = data["unit"]

        uuid1 = uuid.uuid4()
        uuid2 = uuid.uuid4()

        batch_payload = [
            {
                "client_snag_uuid": str(uuid1),
                "unit_id": unit.id,
                "room_location": "حمام الماستر",
                "category": UnitSnagItem.SnagCategory.PLUMBING,
                "severity": UnitSnagItem.SnagSeverity.MAJOR,
                "description": "تسريب خفيف في محبس زاوية شطاف الدش",
                "photo_thumbnail_webp": "data:image/webp;base64,UklGRkAAAABXRUJQVlA4IDQAAADwAQCdASoBAAEAAQAcJaACdLoAA3AA/v39gA==",
            },
            {
                "client_snag_uuid": str(uuid2),
                "unit_id": unit.id,
                "room_location": "الريسبشن",
                "category": UnitSnagItem.SnagCategory.PAINTING,
                "severity": UnitSnagItem.SnagSeverity.MINOR,
                "description": "خشونة وترييح دهان في الجدار الغربي",
                "photo_thumbnail_webp": "",
            }
        ]

        result = OfflineSnaggingSyncService.sync_batch_snags(
            snags_payload=batch_payload,
            user=data["user"]
        )

        assert result["total_received"] == 2
        assert result["created_count"] == 2
        assert result["updated_count"] == 0

        assert UnitSnagItem.objects.filter(unit=unit).count() == 2
        snag1 = UnitSnagItem.objects.get(client_snag_uuid=uuid1)
        assert snag1.room_location == "حمام الماستر"
        assert snag1.severity == UnitSnagItem.SnagSeverity.MAJOR

    def test_idempotent_sync_updates_existing_snag(self, snagging_setup):
        """إعادة إرسال نفس الملاحظة (Idempotent Sync) يُحدث البيانات دون تكرار السجلات"""
        data = snagging_setup
        unit = data["unit"]
        fixed_uuid = uuid.uuid4()

        payload = [
            {
                "client_snag_uuid": str(fixed_uuid),
                "unit_code": unit.unit_code,
                "room_location": "المطبخ",
                "category": UnitSnagItem.SnagCategory.CARPENTRY,
                "severity": UnitSnagItem.SnagSeverity.MINOR,
                "description": "مفصلة درفة المطبخ تحتاج وزنية",
            }
        ]

        # المزامنة الأولى (إنشاء)
        res1 = OfflineSnaggingSyncService.sync_batch_snags(payload, user=data["user"])
        assert res1["created_count"] == 1

        # المزامنة الثانية مع تعديل التوصيف (تحديث)
        payload[0]["description"] = "تم تعديل الملاحظة: المفصلة مكسورة وبحاجة لاستبدال"
        res2 = OfflineSnaggingSyncService.sync_batch_snags(payload, user=data["user"])
        assert res2["created_count"] == 0
        assert res2["updated_count"] == 1

        assert UnitSnagItem.objects.filter(client_snag_uuid=fixed_uuid).count() == 1
        updated_snag = UnitSnagItem.objects.get(client_snag_uuid=fixed_uuid)
        assert "المفصلة مكسورة وبحاجة لاستبدال" in updated_snag.description

    def test_critical_blocker_detection(self, snagging_setup):
        """فحص واكتشاف الملاحظات الحرجة المانعة لإصدار محضر التسليم (Handover Blockers)"""
        data = snagging_setup
        unit = data["unit"]

        # إنشاء ملاحظة بسيطة وأخرى حرجة مانعة للتسليم
        UnitSnagItem.objects.create(
            unit=unit,
            room_location="غرفة النوم",
            category=UnitSnagItem.SnagCategory.PAINTING,
            severity=UnitSnagItem.SnagSeverity.MINOR,
            description="تنقيط دهان على الباركيه",
            status=UnitSnagItem.SnagStatus.OPEN
        )
        blocker = UnitSnagItem.objects.create(
            unit=unit,
            room_location="لوحة الكهرباء الرئيسية",
            category=UnitSnagItem.SnagCategory.ELECTRICAL,
            severity=UnitSnagItem.SnagSeverity.CRITICAL_BLOCKER,
            description="عطل في القاطع الرئيسي وعدم وجود تأريض (خطر أمني)",
            status=UnitSnagItem.SnagStatus.OPEN
        )

        check = OfflineSnaggingSyncService.check_unit_handover_blockers(unit)
        assert check["is_blocked"] is True
        assert check["blockers_count"] == 1
        assert blocker.snag_code in check["blocker_codes"]
        assert check["can_issue_handover"] is False

        # معالجة الملاحظة واعتمادها من المهندس
        OfflineSnaggingSyncService.verify_snag_resolution(
            snag_item=blocker,
            engineer_user=data["engineer"],
            resolution_notes="تم استبدال القاطع الرئيسي وربط كابل التأريض واختباره بنجاح"
        )

        check_after = OfflineSnaggingSyncService.check_unit_handover_blockers(unit)
        assert check_after["is_blocked"] is False
        assert check_after["can_issue_handover"] is True

    def test_sync_rejects_unknown_unit(self, snagging_setup):
        """رفض الملاحظة إذا كان كود الوحدة غير موجود بالنظام"""
        data = snagging_setup

        payload = [
            {
                "client_snag_uuid": str(uuid.uuid4()),
                "unit_code": "NON-EXISTENT-UNIT-CODE-999",
                "room_location": "المدخل",
                "description": "ملاحظة لوحدة غير موجودة",
            }
        ]

        with pytest.raises(ValidationError) as exc:
            OfflineSnaggingSyncService.sync_batch_snags(payload, user=data["user"])

        assert "غير موجودة" in str(exc.value)
