"""
اختبارات نماذج الموردين
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from decimal import Decimal

from ..models import (
    SupplierType, SupplierTypeSettings, Supplier
)

User = get_user_model()


class SupplierModelTest(TestCase):
    """اختبارات نموذج الموردين"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.supplier_type = SupplierType.objects.create(
            name="مورد متخصص",
            code="educational",
            description="موردي المواد والمستلزمات"
        )
        
    def test_create_supplier(self):
        """اختبار إنشاء مورد جديد"""
        supplier = Supplier.objects.create(
            name="مورد المواد المتخصصة",
            code="EDU001",
            primary_type=self.supplier_type,
            email="supplier@education.com",
            phone="01234567890",
            address="القاهرة، مصر"
        )
        
        self.assertEqual(supplier.name, "مورد المواد المتخصصة")
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


class SupplierFunctionalityTest(TestCase):
    """اختبارات وظائف الموردين الأساسية"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.supplier_type = SupplierType.objects.create(
            name="مورد عام",
            code="general",
            description="موردي الخدمات العامة"
        )
        
        self.supplier = Supplier.objects.create(
            name="مورد اختبار",
            code="TEST001",
            primary_type=self.supplier_type
        )
        
    def test_supplier_functionality_preserved(self):
        """اختبار أن وظائف المورد الأساسية محفوظة"""
        # التأكد من أن المورد يمكن إنشاؤه وحفظه
        self.assertTrue(self.supplier.is_active)
        self.assertEqual(self.supplier.name, "مورد اختبار")
        self.assertEqual(self.supplier.code, "TEST001")


class SupplierTypeTest(TestCase):
    """اختبارات أنواع الموردين"""
    
    def test_create_supplier_type(self):
        """اختبار إنشاء نوع مورد جديد"""
        supplier_type = SupplierType.objects.create(
            name="مورد متخصص",
            code="educational",
            description="موردي المواد والمستلزمات"
        )
        
        self.assertEqual(supplier_type.name, "مورد متخصص")
        self.assertEqual(supplier_type.code, "educational")
        self.assertTrue(supplier_type.is_active)
        
    def test_supplier_type_settings_creation(self):
        """اختبار إنشاء إعدادات نوع المورد"""
        settings = SupplierTypeSettings.objects.create(
            name="مقدم خدمات",
            code="service_provider",
            description="مقدمي الخدمات المختلفة",
            icon="fas fa-tools",
            color="#ffc107"
        )
        
        self.assertEqual(settings.name, "مقدم خدمات")
        self.assertEqual(settings.code, "service_provider")
        self.assertTrue(settings.is_active)
