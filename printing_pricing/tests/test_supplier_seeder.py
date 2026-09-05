import pytest
from core.models import SystemModule
from supplier.models import SupplierType, SupplierTypeSettings, ServiceType
from printing_pricing.services.supplier_seeder_service import PricingSupplierSeederService


@pytest.mark.django_db
class TestPricingSupplierSeeder:
    """اختبارات خدمة بذر وتكامل أنواع الموردين لموديول التسعير"""

    def test_seeder_creates_all_printing_types(self):
        """التأكد من إنشاء كافة أنواع الموردين الستة الخاصة بالطباعة"""
        result = PricingSupplierSeederService.seed_all()
        
        expected_codes = [
            "paper_supplier",
            "offset_press",
            "digital_center",
            "ctp_center",
            "finishing_workshop",
            "printing_supplies",
        ]
        
        for code in expected_codes:
            setting = SupplierTypeSettings.objects.filter(code=code).first()
            assert setting is not None, f"نوع المورد {code} غير موجود في SupplierTypeSettings"
            assert setting.is_system is False
            
            # التأكد من المزامنة مع SupplierType
            legacy_type = SupplierType.objects.filter(code=code).first()
            assert legacy_type is not None, f"نوع المورد {code} غير متزامن مع SupplierType"
            assert legacy_type.name == setting.name

    def test_seeder_idempotency(self):
        """التأكد من أن تكرار تشغيل الـ Seeder لا يسبب تكرار السجلات (Strict Idempotency)"""
        # تشغيل أول مرة
        PricingSupplierSeederService.seed_all()
        initial_types_count = SupplierTypeSettings.objects.count()
        initial_services_count = ServiceType.objects.count()
        
        # تشغيل مرة ثانية
        second_result = PricingSupplierSeederService.seed_all()
        assert second_result["supplier_types_created"] == 0
        
        assert SupplierTypeSettings.objects.count() == initial_types_count
        assert ServiceType.objects.count() == initial_services_count

    def test_service_provider_flag_accuracy(self):
        """التأكد من صحة التصنيف المحاسبي بين الخدمي والمخزني"""
        PricingSupplierSeederService.seed_all()
        
        # المخزني: ورق وأحبار
        assert SupplierTypeSettings.objects.get(code="paper_supplier").is_service_provider is False
        assert SupplierTypeSettings.objects.get(code="printing_supplies").is_service_provider is False
        
        # الخدمي: أوفست، ديجيتال، زنكات، تشطيب
        assert SupplierTypeSettings.objects.get(code="offset_press").is_service_provider is True
        assert SupplierTypeSettings.objects.get(code="digital_center").is_service_provider is True
        assert SupplierTypeSettings.objects.get(code="ctp_center").is_service_provider is True
        assert SupplierTypeSettings.objects.get(code="finishing_workshop").is_service_provider is True

    def test_recommended_services_mapping(self):
        recommended_offset = PricingSupplierSeederService.get_recommended_services("offset_press")
        assert "offset_printing" in recommended_offset
        assert "ctp_plates" in recommended_offset
        assert PricingSupplierSeederService.get_recommended_services("ctp_center") == ["ctp_plates"]
        assert PricingSupplierSeederService.get_recommended_services("paper_supplier") == ["paper"]
        assert "finishing" in PricingSupplierSeederService.get_recommended_services("finishing_workshop")

    def test_system_module_signal_integration(self):
        """التأكد من أن تفعيل موديول التسعير في SystemModule يطلق التثبيت التلقائي"""
        # حذف أنواع الطباعة لمحاكاة بيئة نظيفة
        SupplierTypeSettings.objects.filter(code__in=[
            "paper_supplier", "offset_press", "digital_center",
            "ctp_center", "finishing_workshop", "printing_supplies"
        ]).delete()
        
        module, _ = SystemModule.objects.get_or_create(code="printing_pricing", defaults={"name_ar": "تسعير الطباعة"})
        module.is_enabled = True
        module.save()  # يطلق post_save signal
        
        # التحقق من أن الإشارة أطلقت الـ Seeder وتمت استعادة الأنواع بنجاح
        assert SupplierTypeSettings.objects.filter(code="offset_press").exists()
        assert SupplierTypeSettings.objects.filter(code="paper_supplier").exists()
        assert SupplierTypeSettings.objects.filter(code="ctp_center").exists()

    def test_supplier_type_settings_create_default_types_does_not_crash(self):
        """التأكد من أن الدالة create_default_types تعمل بسلاسة ولا تنهار"""
        count = SupplierTypeSettings.create_default_types()
        assert count >= 0
        assert SupplierTypeSettings.objects.filter(code="product_supplier").exists()
        assert SupplierTypeSettings.objects.filter(code="service_provider").exists()
