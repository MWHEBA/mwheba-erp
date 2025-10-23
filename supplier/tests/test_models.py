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
    PricingTier
)

User = get_user_model()


class SupplierModelTest(TestCase):
    """اختبارات نموذج الموردين"""
    
    fixtures = ['supplier/fixtures/supplier_types.json']
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.supplier_type = SupplierType.objects.filter(
            supplier_type_settings__type_key="paper"
        ).first()
        
    def test_create_supplier(self):
        """اختبار إنشاء مورد جديد"""
        supplier = Supplier.objects.create(
            name="مورد الورق المصري",
            supplier_type=self.supplier_type,
            email="supplier@paper.com",
            phone="01234567890",
            address="القاهرة، مصر"
        )
        
        self.assertEqual(supplier.name, "مورد الورق المصري")
        self.assertEqual(supplier.supplier_type, self.supplier_type)
        self.assertTrue(supplier.is_active)
        
    def test_supplier_str_method(self):
        """اختبار طريقة __str__ للمورد"""
        supplier = Supplier.objects.create(
            name="مورد تجريبي",
            supplier_type=self.supplier_type
        )
        
        self.assertEqual(str(supplier), "مورد تجريبي")


class PaperServiceTest(TestCase):
    """اختبارات خدمات الورق"""
    
    fixtures = ['supplier/fixtures/supplier_types.json']
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        supplier_type = SupplierType.objects.filter(
            supplier_type_settings__type_key="paper"
        ).first()
        
        self.supplier = Supplier.objects.create(
            name="مورد ورق",
            supplier_type=supplier_type
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
            supplier_type_settings__type_key="offset_printing"
        ).first()
        
        self.supplier = Supplier.objects.create(
            name="مطبعة أوفست",
            supplier_type=supplier_type
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
            supplier_type_settings__type_key="digital_printing"
        ).first()
        
        self.supplier = Supplier.objects.create(
            name="مطبعة ديجيتال",
            supplier_type=supplier_type
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
            supplier_type_settings__type_key="plates"
        ).first()
        
        self.supplier = Supplier.objects.create(
            name="مكتب فصل",
            supplier_type=supplier_type
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


class PricingTierTest(TestCase):
    """اختبارات الشرائح السعرية"""
    
    fixtures = ['supplier/fixtures/supplier_types.json']
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        supplier_type = SupplierType.objects.filter(
            supplier_type_settings__type_key="paper"
        ).first()
        
        self.supplier = Supplier.objects.create(
            name="مورد ورق",
            supplier_type=supplier_type
        )
        
        self.service = PaperServiceDetails.objects.create(
            supplier=self.supplier,
            paper_type="كوشيه",
            gsm=120
        )
        
    def test_create_pricing_tier(self):
        """اختبار إنشاء شريحة سعرية"""
        tier = PricingTier.objects.create(
            service_details=self.service,
            min_quantity=1000,
            max_quantity=5000,
            price=Decimal('2.00')
        )
        
        self.assertEqual(tier.min_quantity, 1000)
        self.assertEqual(tier.max_quantity, 5000)
        self.assertEqual(tier.price, Decimal('2.00'))
        
    def test_pricing_tier_str_method(self):
        """اختبار طريقة __str__ للشريحة السعرية"""
        tier = PricingTier.objects.create(
            service_details=self.service,
            min_quantity=1000,
            max_quantity=5000,
            price=Decimal('2.00')
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
            supplier_type_settings__type_key="paper"
        ).first()
        
        offset_type = SupplierType.objects.filter(
            supplier_type_settings__type_key="offset_printing"
        ).first()
        
        self.assertIsNotNone(paper_type)
        self.assertIsNotNone(offset_type)
        
    def test_supplier_type_settings(self):
        """اختبار إعدادات أنواع الموردين"""
        settings = SupplierTypeSettings.objects.filter(
            type_key="paper"
        ).first()
        
        self.assertIsNotNone(settings)
        self.assertEqual(settings.type_key, "paper")
        self.assertTrue(settings.is_active)
