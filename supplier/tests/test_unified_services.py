"""
اختبارات الموردين - تم حذف الخدمات المتخصصة
"""

from django.test import TestCase
from ..models import Supplier, SupplierType

# ملاحظة: تم حذف اختبارات الخدمات المتخصصة كجزء من تنظيف فئات الموردين
# تم حذف الفئات التالية:
# - UnifiedServicesTest
# - PaperServicesTest  
# - OffsetServicesTest
# - DigitalServicesTest
# - PlateServicesTest
# - FinishingServicesTest
# - PackagingServicesTest
# - CoatingServicesTest
# - OutdoorServicesTest
# - LaserServicesTest
# - VIPGiftServicesTest

class BasicSupplierTest(TestCase):
    """اختبارات أساسية للموردين بعد حذف الخدمات المتخصصة"""
    
    def test_supplier_creation_works(self):
        """اختبار أن إنشاء الموردين يعمل بعد حذف الخدمات المتخصصة"""
        supplier_type = SupplierType.objects.create(
            name="مورد عام",
            code="general"
        )
        
        supplier = Supplier.objects.create(
            name="مورد اختبار",
            code="TEST001",
            primary_type=supplier_type
        )
        
        self.assertEqual(supplier.name, "مورد اختبار")
        self.assertEqual(supplier.code, "TEST001")
        self.assertTrue(supplier.is_active)