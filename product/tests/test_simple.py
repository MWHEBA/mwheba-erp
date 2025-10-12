"""
اختبار بسيط للتأكد من عمل النظام
"""
from django.test import TestCase
from django.contrib.auth import get_user_model

User = get_user_model()
from product.models import Category, Brand, Unit, Warehouse


class SimpleInventoryTest(TestCase):
    """اختبارات بسيطة لنظام المخزون"""

    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )

    def test_create_category(self):
        """اختبار إنشاء تصنيف"""
        category = Category.objects.create(name="إلكترونيات")
        self.assertEqual(category.name, "إلكترونيات")
        self.assertTrue(category.is_active)

    def test_create_brand(self):
        """اختبار إنشاء ماركة"""
        brand = Brand.objects.create(name="سامسونج")
        self.assertEqual(brand.name, "سامسونج")

    def test_create_unit(self):
        """اختبار إنشاء وحدة قياس"""
        unit = Unit.objects.create(name="قطعة", symbol="قطعة")
        self.assertEqual(unit.name, "قطعة")
        self.assertEqual(unit.symbol, "قطعة")

    def test_create_warehouse(self):
        """اختبار إنشاء مخزن"""
        warehouse = Warehouse.objects.create(name="المخزن الرئيسي", location="الرياض")
        self.assertEqual(warehouse.name, "المخزن الرئيسي")
        self.assertEqual(warehouse.location, "الرياض")
        self.assertTrue(warehouse.is_active)

    def test_models_string_representation(self):
        """اختبار عرض النماذج كنص"""
        category = Category.objects.create(name="تصنيف تجريبي")
        brand = Brand.objects.create(name="ماركة تجريبية")
        unit = Unit.objects.create(name="وحدة تجريبية", symbol="وحدة")
        warehouse = Warehouse.objects.create(name="مخزن تجريبي")

        self.assertEqual(str(category), "تصنيف تجريبي")
        self.assertEqual(str(brand), "ماركة تجريبية")
        self.assertEqual(str(unit), "وحدة تجريبية (وحدة)")
        self.assertEqual(str(warehouse), "مخزن تجريبي")
