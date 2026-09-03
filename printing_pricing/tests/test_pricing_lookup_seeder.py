"""
اختبارات وحدة لخدمة بذر جداول تسعير المطبوعات والتأكد من Idempotency
Unit tests for PricingLookupSeederService
"""
import pytest
from decimal import Decimal
from core.models import SystemModule
from printing_pricing.services.pricing_lookup_seeder_service import PricingLookupSeederService
from printing_pricing.models import (
    PaperType, PaperSize, PaperWeight, PaperOrigin, PieceSize,
    PrintingMachine, MachineDimension,
    OffsetMachineType, DigitalMachineType, OffsetSheetSize, DigitalSheetSize, PlateSize,
    CoatingType, FinishingType, PackagingType,
    ProductType, ProductSize
)


@pytest.mark.django_db
class TestPricingLookupSeederService:
    """اختبارات خدمة بذر جداول تسعير المطبوعات"""

    def test_seed_all_success_and_data_integrity(self):
        """التحقق من نجاح البذر الكامل وسلامة ترابط البيانات"""
        result = PricingLookupSeederService.seed_all()
        assert result["success"] is True
        assert result["total_created"] > 0

        # التحقق من خامات الورق
        assert PaperType.objects.filter(name="كوشيه", is_default=True).exists()
        duplex = PaperType.objects.filter(name="دوبلكس").first()
        assert duplex is not None
        assert duplex.override_sheets_per_pack == 100

        # التحقق من تصحيح وزن 150 جم وسعة الرزمة
        pw_150 = PaperWeight.objects.filter(gsm=150).first()
        assert pw_150 is not None
        assert pw_150.name == "150 جرام"
        assert pw_150.sheets_per_pack == 250
        assert pw_150.is_default is True

        # التحقق من مقاسات الفروخ
        assert PaperSize.objects.filter(width=Decimal("70.00"), height=Decimal("100.00")).exists()

        # التحقق من ربط مقاسات القص بالفروخ الخام
        piece_half = PieceSize.objects.filter(width=Decimal("50.00"), height=Decimal("70.00")).first()
        assert piece_half is not None
        assert piece_half.paper_type is not None
        assert piece_half.paper_type.width == Decimal("70.00")
        assert piece_half.pieces_per_sheet == 2

        # التحقق من ماكينات الأوفست والديجيتال والـ Proxy Models
        assert OffsetMachineType.objects.filter(code="sm74").exists()
        assert DigitalMachineType.objects.filter(code="indigo_7900").exists()
        assert OffsetMachineType.objects.count() == 5
        assert DigitalMachineType.objects.count() == 4

        # التحقق من شيتات التشغيل والزنكات CTP مع التأكد من الفصل التام بين الأوفست والديجيتال
        assert OffsetSheetSize.objects.filter(code="half_sheet").exists()
        assert not OffsetSheetSize.objects.filter(code="digital_a3").exists()
        assert OffsetSheetSize.objects.count() == 3

        assert DigitalSheetSize.objects.filter(code="digital_a3").exists()
        assert not DigitalSheetSize.objects.filter(code="half_sheet").exists()
        assert DigitalSheetSize.objects.count() == 3

        assert PlateSize.objects.filter(code="plate_sm74").exists()
        assert PlateSize.objects.count() == 3

        # التحقق من ثلاثي ما بعد الطباعة
        assert CoatingType.objects.filter(name__icontains="سلوفان لامع").exists()
        assert FinishingType.objects.filter(name__icontains="قص وتقطيع").exists()
        assert PackagingType.objects.filter(name__icontains="تدبيس حصان").exists()

        # التحقق من أنماط المنتجات الأربعة
        assert ProductType.objects.filter(base_archetype="flyer").exists()
        assert ProductType.objects.filter(base_archetype="catalog").exists()
        assert ProductType.objects.filter(base_archetype="folder").exists()
        assert ProductType.objects.filter(base_archetype="invoice").exists()
        assert ProductSize.objects.filter(name="A4").exists()

    def test_seeder_is_strictly_idempotent(self):
        """التحقق من أن تشغيل السيرفس مرة ثانية لا يُنشئ أي سجلات مكررة"""
        # تشغيل أول
        PricingLookupSeederService.seed_all()
        counts_before = {
            "paper_types": PaperType.objects.count(),
            "paper_sizes": PaperSize.objects.count(),
            "paper_weights": PaperWeight.objects.count(),
            "machines": PrintingMachine.objects.count(),
            "dimensions": MachineDimension.objects.count(),
            "coatings": CoatingType.objects.count(),
            "finishings": FinishingType.objects.count(),
            "packagings": PackagingType.objects.count(),
            "products": ProductType.objects.count(),
            "product_sizes": ProductSize.objects.count(),
        }

        # تشغيل ثانٍ
        second_result = PricingLookupSeederService.seed_all()
        assert second_result["success"] is True
        assert second_result["total_created"] == 0

        counts_after = {
            "paper_types": PaperType.objects.count(),
            "paper_sizes": PaperSize.objects.count(),
            "paper_weights": PaperWeight.objects.count(),
            "machines": PrintingMachine.objects.count(),
            "dimensions": MachineDimension.objects.count(),
            "coatings": CoatingType.objects.count(),
            "finishings": FinishingType.objects.count(),
            "packagings": PackagingType.objects.count(),
            "products": ProductType.objects.count(),
            "product_sizes": ProductSize.objects.count(),
        }

        assert counts_before == counts_after

    def test_module_activation_triggers_full_seeder(self):
        """التحقق من أن تفعيل موديول التسعير في SystemModule يشغل بذر التسعير والموردين معاً"""
        module, _ = SystemModule.objects.get_or_create(
            code="printing_pricing",
            defaults={"name_ar": "تسعير الطباعة"}
        )
        module.is_enabled = True
        module.save()

        assert PrintingMachine.objects.exists()
        assert OffsetMachineType.objects.count() == 5
        assert PackagingType.objects.exists()
