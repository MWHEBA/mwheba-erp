"""
اختبارات نماذج الموردين والخدمات المتخصصة
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from decimal import Decimal

from ..models import (
    SupplierType, SupplierTypeSettings, Supplier,
    PaperServiceDetails, OffsetPrintingDetails,
    DigitalPrintingDetails, PlateServiceDetails,
    SpecializedService, ServicePriceTier,
    FinishingServiceDetails, OutdoorPrintingDetails,
    LaserServiceDetails, VIPGiftDetails
)

User = get_user_model()


class SupplierModelTest(TestCase):
    """اختبارات نموذج الموردين"""
    
    fixtures = ['supplier/fixtures/supplier_types.json']
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.supplier_type = SupplierType.objects.filter(
            code="paper"
        ).first()
        
    def test_create_supplier(self):
        """اختبار إنشاء مورد جديد"""
        supplier = Supplier.objects.create(
            name="مورد الورق المصري",
            code="PAPER001",
            primary_type=self.supplier_type,
            email="supplier@paper.com",
            phone="01234567890",
            address="القاهرة، مصر"
        )
        
        self.assertEqual(supplier.name, "مورد الورق المصري")
        self.assertEqual(supplier.primary_type, self.supplier_type)
        self.assertTrue(supplier.is_active)
        
    def test_supplier_str_method(self):
        """اختبار طريقة __str__ للمورد"""
        supplier = Supplier.objects.create(
            name="مورد تجريبي",
            code="TEST001",
            primary_type=self.supplier_type
        )
        
        self.assertEqual(str(supplier), "مورد تجريبي")


class PaperServiceTest(TestCase):
    """اختبارات خدمات الورق"""
    
    fixtures = ['supplier/fixtures/supplier_types.json']
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        supplier_type = SupplierType.objects.filter(
            code="paper"
        ).first()
        
        self.supplier = Supplier.objects.create(
            name="مورد ورق",
            code="PAPER002",
            primary_type=supplier_type
        )
        
    def test_create_paper_service(self):
        """اختبار إنشاء خدمة ورق"""
        service = PaperServiceDetails.objects.create(
            supplier=self.supplier,
            paper_type="كوشيه",
            gsm=120,
            sheet_size="70.00x100.00",
            country_of_origin="مصر",
            price_per_sheet=Decimal('2.50')
        )
        
        self.assertEqual(service.paper_type, "كوشيه")
        self.assertEqual(service.gsm, 120)
        self.assertEqual(service.price_per_sheet, Decimal('2.50'))
        
    def test_paper_service_str_method(self):
        """اختبار طريقة __str__ لخدمة الورق"""
        service = PaperServiceDetails.objects.create(
            supplier=self.supplier,
            paper_type="كوشيه",
            gsm=120,
            sheet_size="70.00x100.00",
            country_of_origin="مصر"
        )
        
        str_result = str(service)
        self.assertIn("كوشيه", str_result)
        self.assertIn("120", str_result)
        
    def test_get_sheet_size_display(self):
        """اختبار عرض مقاس الفرخ"""
        service = PaperServiceDetails.objects.create(
            supplier=self.supplier,
            sheet_size="70.00x100.00"
        )
        
        # يجب أن تعرض المقاس بشكل صحيح
        display = service.get_sheet_size_display()
        self.assertIsNotNone(display)


class OffsetServiceTest(TestCase):
    """اختبارات خدمات الأوفست"""
    
    fixtures = ['supplier/fixtures/supplier_types.json']
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        supplier_type = SupplierType.objects.filter(
            code="offset_printing"
        ).first()
        
        self.supplier = Supplier.objects.create(
            name="مطبعة أوفست",
            code="OFFSET001",
            primary_type=supplier_type
        )
        
    def test_create_offset_service(self):
        """اختبار إنشاء خدمة أوفست"""
        service = OffsetPrintingDetails.objects.create(
            supplier=self.supplier,
            machine_type="sm52",
            sheet_size="quarter_sheet",
            colors=4,
            price_per_impression=Decimal('0.25')
        )
        
        self.assertEqual(service.machine_type, "sm52")
        self.assertEqual(service.colors, 4)
        self.assertEqual(service.price_per_impression, Decimal('0.25'))


class DigitalServiceTest(TestCase):
    """اختبارات خدمات الديجيتال"""
    
    fixtures = ['supplier/fixtures/supplier_types.json']
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        supplier_type = SupplierType.objects.filter(
            code="digital_printing"
        ).first()
        
        self.supplier = Supplier.objects.create(
            name="مطبعة ديجيتال",
            code="DIGITAL001",
            primary_type=supplier_type
        )
        
    def test_create_digital_service(self):
        """اختبار إنشاء خدمة ديجيتال"""
        service = DigitalPrintingDetails.objects.create(
            supplier=self.supplier,
            machine_type="hp7900",
            sheet_size="a4",
            price_per_sheet=Decimal('1.50')
        )
        
        self.assertEqual(service.machine_type, "hp7900")
        self.assertEqual(service.price_per_sheet, Decimal('1.50'))


class PlateServiceTest(TestCase):
    """اختبارات خدمات الزنكات"""
    
    fixtures = ['supplier/fixtures/supplier_types.json']
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        supplier_type = SupplierType.objects.filter(
            code="plates"
        ).first()
        
        self.supplier = Supplier.objects.create(
            name="مكتب فصل",
            code="PLATES001",
            primary_type=supplier_type
        )
        
    def test_create_plate_service(self):
        """اختبار إنشاء خدمة زنكات"""
        service = PlateServiceDetails.objects.create(
            supplier=self.supplier,
            plate_size="35.00x50.00",
            price_per_plate=Decimal('15.00')
        )
        
        self.assertEqual(service.plate_size, "35.00x50.00")
        self.assertEqual(service.price_per_plate, Decimal('15.00'))


class ServicePriceTierTest(TestCase):
    """اختبارات الشرائح السعرية"""
    
    fixtures = ['supplier/fixtures/supplier_types.json']
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        supplier_type = SupplierType.objects.filter(
            code="paper"
        ).first()
        
        self.supplier = Supplier.objects.create(
            name="مورد ورق",
            code="PAPER003",
            primary_type=supplier_type
        )
        
        # إنشاء خدمة متخصصة
        self.service = SpecializedService.objects.create(
            supplier=self.supplier,
            name="خدمة ورق كوشيه",
            service_type="paper",
            base_price=Decimal('2.50')
        )
        
    def test_create_service_price_tier(self):
        """اختبار إنشاء شريحة سعرية"""
        tier = ServicePriceTier.objects.create(
            service=self.service,
            tier_name="1000-5000",
            min_quantity=1000,
            max_quantity=5000,
            price_per_unit=Decimal('2.00')
        )
        
        self.assertEqual(tier.min_quantity, 1000)
        self.assertEqual(tier.max_quantity, 5000)
        self.assertEqual(tier.price_per_unit, Decimal('2.00'))
        
    def test_service_price_tier_str_method(self):
        """اختبار طريقة __str__ للشريحة السعرية"""
        tier = ServicePriceTier.objects.create(
            service=self.service,
            tier_name="1000-5000",
            min_quantity=1000,
            max_quantity=5000,
            price_per_unit=Decimal('2.00')
        )
        
        str_result = str(tier)
        self.assertIn("1000", str_result)
        self.assertIn("5000", str_result)


class SupplierTypeTest(TestCase):
    """اختبارات أنواع الموردين"""
    
    fixtures = ['supplier/fixtures/supplier_types.json']
    
    def test_supplier_types_loaded(self):
        """اختبار تحميل أنواع الموردين من fixtures"""
        # التحقق من وجود أنواع الموردين الأساسية
        paper_type = SupplierType.objects.filter(
            code="paper"
        ).first()
        
        offset_type = SupplierType.objects.filter(
            code="offset_printing"
        ).first()
        
        self.assertIsNotNone(paper_type)
        self.assertIsNotNone(offset_type)
        
    def test_supplier_type_settings(self):
        """اختبار إعدادات أنواع الموردين"""
        settings = SupplierTypeSettings.objects.filter(
            code="paper"
        ).first()
        
        self.assertIsNotNone(settings)
        self.assertEqual(settings.code, "paper")
        self.assertTrue(settings.is_active)
