from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from product.models import (
    Category,
    Brand,
    Unit,
    Product,
    Warehouse,
    Stock,
    StockMovement,
    ProductImage,
)
from decimal import Decimal
import datetime
import unittest
from django.db import models

User = get_user_model()


class CategoryModelTest(TestCase):
    """
    اختبارات نموذج التصنيفات
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass123", email="test@example.com"
        )
        self.parent_category = Category.objects.create(
            name="فئة رئيسية")
        self.child_category = Category.objects.create(
            name="فئة فرعية", parent=self.parent_category)

    def test_category_creation(self):
        """
        اختبار إنشاء فئة بشكل صحيح
        """
        self.assertEqual(self.parent_category.name, "فئة رئيسية")
        self.assertIsNone(self.parent_category.parent)
        self.assertEqual(self.child_category.name, "فئة فرعية")
        self.assertEqual(self.child_category.parent, self.parent_category)
        self.assertIsNotNone(self.parent_category.created_at)
        self.assertIsNotNone(self.child_category.created_at)

    def test_category_str(self):
        """
        اختبار تمثيل التصنيف كنص
        """
        self.assertEqual(str(self.parent_category), "فئة رئيسية")
        # يجب أن يحتوي تمثيل التصنيف الفرعية على اسم التصنيف الأب
        self.assertEqual(str(self.child_category), "فئة رئيسية > فئة فرعية")

    def test_category_child_parent_relationship(self):
        """
        اختبار العلاقة بين التصنيف الأب والتصنيفات الفرعية
        """
        # يجب أن تظهر التصنيف الفرعية في قائمة التصنيفات الفرعية للفئة الأب
        self.assertTrue(self.child_category in self.parent_category.children.all())

        # إنشاء فئة فرعية أخرى
        second_child = Category.objects.create(
            name="فئة فرعية أخرى", parent=self.parent_category)

        # يجب أن يكون عدد التصنيفات الفرعية للفئة الأب هو 2
        self.assertEqual(self.parent_category.children.count(), 2)

        # يجب أن تظهر التصنيف الفرعية الجديدة في قائمة التصنيفات الفرعية للفئة الأب
        self.assertTrue(second_child in self.parent_category.children.all())


class BrandModelTest(TestCase):
    """
    اختبارات نموذج الأنواع
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass123", email="test@example.com"
        )
        self.brand = Brand.objects.create(
            name="علامة تجارية اختبار", description="وصف النوع")

    def test_brand_creation(self):
        """
        اختبار إنشاء علامة تجارية بشكل صحيح
        """
        self.assertEqual(self.brand.name, "علامة تجارية اختبار")
        self.assertEqual(self.brand.description, "وصف النوع")
        self.assertIsNotNone(self.brand.created_at)

    def test_brand_str(self):
        """
        اختبار تمثيل النوع كنص
        """
        self.assertEqual(str(self.brand), "علامة تجارية اختبار")



class UnitModelTest(TestCase):
    """
    اختبارات نموذج الوحدات
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass123", email="test@example.com"
        )
        self.unit = Unit.objects.create(
            name="قطعة", symbol="ق")

    def test_unit_creation(self):
        """
        اختبار إنشاء وحدة بشكل صحيح
        """
        self.assertEqual(self.unit.name, "قطعة")
        self.assertEqual(self.unit.symbol, "ق")
        self.assertIsNotNone(self.unit.created_at)

    def test_unit_str(self):
        """
        اختبار تمثيل الوحدة كنص
        """
        self.assertEqual(str(self.unit), "قطعة (ق)")


class ProductModelTest(TestCase):
    """
    اختبارات نموذج المنتجات
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass123", email="test@example.com"
        )
        self.category = Category.objects.create(name="فئة اختبار")
        self.brand = Brand.objects.create(
            name="علامة تجارية اختبار")
        self.unit = Unit.objects.create(
            name="قطعة", symbol="ق")
        self.product = Product.objects.create(
            name="منتج اختبار",
            sku="P001",
            barcode="1234567890123",
            description="وصف المنتج",
            category=self.category,
            brand=self.brand,
            unit=self.unit,
            cost_price=Decimal("80.00"),
            selling_price=Decimal("100.00"),
            created_by=self.user,
        )

    def test_product_creation(self):
        """
        اختبار إنشاء منتج بشكل صحيح
        """
        self.assertEqual(self.product.name, "منتج اختبار")
        self.assertEqual(self.product.sku, "P001")
        self.assertEqual(self.product.barcode, "1234567890123")
        self.assertEqual(self.product.description, "وصف المنتج")
        self.assertEqual(self.product.category, self.category)
        self.assertEqual(self.product.brand, self.brand)
        self.assertEqual(self.product.unit, self.unit)
        self.assertEqual(self.product.cost_price, Decimal("80.00"))
        self.assertEqual(self.product.selling_price, Decimal("100.00"))
        self.assertEqual(self.product.created_by, self.user)
        self.assertIsNotNone(self.product.created_at)

    def test_product_str(self):
        """
        اختبار تمثيل المنتج كنص
        """
        self.assertEqual(str(self.product), "منتج اختبار (P001)")

    def test_product_profit_margin(self):
        """
        اختبار حساب هامش الربح للمنتج
        """
        # هامش الربح = (سعر البيع - تكلفة الشراء) / سعر البيع * 100
        # = (100 - 80) / 100 * 100 = 20%
        self.assertAlmostEqual(float(self.product.profit_margin), 20.0, places=2)

        # تغيير سعر البيع والتكلفة
        self.product.cost_price = Decimal("60.00")
        self.product.selling_price = Decimal("90.00")
        self.product.save()

        # هامش الربح الجديد = (90 - 60) / 90 * 100 = 33.33%
        self.assertAlmostEqual(float(self.product.profit_margin), 33.33, places=2)


class WarehouseModelTest(TestCase):
    """
    اختبارات نموذج المخازن
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass123", email="test@example.com"
        )
        self.warehouse = Warehouse.objects.create(
            name="مخزن اختبار",
            code="WH001",
            location="عنوان المخزن",
            description="وصف المخزن",
            created_by=self.user,
        )

    def test_warehouse_creation(self):
        """
        اختبار إنشاء مخزن بشكل صحيح
        """
        self.assertEqual(self.warehouse.name, "مخزن اختبار")
        self.assertEqual(self.warehouse.code, "WH001")
        self.assertEqual(self.warehouse.location, "عنوان المخزن")
        self.assertEqual(self.warehouse.description, "وصف المخزن")
        self.assertIsNotNone(self.warehouse.created_at)

    def test_warehouse_str(self):
        """
        اختبار تمثيل المخزن كنص
        """
        self.assertEqual(str(self.warehouse), "مخزن اختبار")



class StockModelTest(TestCase):
    """
    اختبارات نموذج المخزون
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass123", email="test@example.com"
        )
        self.category = Category.objects.create(name="فئة اختبار")
        self.unit = Unit.objects.create(
            name="قطعة", symbol="ق")
        self.product = Product.objects.create(
            name="منتج اختبار",
            sku="P001",
            category=self.category,
            unit=self.unit,
            cost_price=Decimal("80.00"),
            selling_price=Decimal("100.00"),
            created_by=self.user,
        )
        self.warehouse = Warehouse.objects.create(
            name="مخزن اختبار", code="WH001")
        self.stock = Stock.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity=50,
            created_by=self.user,
        )

    def test_stock_creation(self):
        """
        اختبار إنشاء رصيد مخزون بشكل صحيح
        """
        self.assertEqual(self.stock.product, self.product)
        self.assertEqual(self.stock.warehouse, self.warehouse)
        self.assertEqual(self.stock.quantity, 50)
        self.assertEqual(self.stock.created_by, self.user)
        self.assertIsNotNone(self.stock.updated_at)

    def test_stock_str(self):
        """
        اختبار تمثيل المخزون كنص
        """
        # Format: "Product (SKU) - Warehouse (Quantity)"
        stock_str = str(self.stock)
        self.assertIn("منتج اختبار", stock_str)
        self.assertIn("P001", stock_str)
        self.assertIn("مخزن اختبار", stock_str)
        self.assertIn("50", stock_str)

    def test_stock_update_quantity(self):
        """
        اختبار تحديث كمية المخزون
        """
        # التحقق من الكمية الأولية
        self.assertEqual(self.stock.quantity, 50)

        # تحديث الكمية
        self.stock.quantity = 60
        self.stock.save()

        # التحقق من الكمية بعد التحديث
        updated_stock = Stock.objects.get(id=self.stock.id)
        self.assertEqual(updated_stock.quantity, 60)


class StockMovementModelTest(TestCase):
    """Stock Movement Model Tests"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass123", email="test@example.com"
        )
        self.category = Category.objects.create(name="فئة اختبار")
        self.unit = Unit.objects.create(
            name="قطعة", symbol="ق")
        self.product = Product.objects.create(
            name="منتج اختبار",
            sku="P001",
            category=self.category,
            unit=self.unit,
            cost_price=Decimal("80.00"),
            selling_price=Decimal("100.00"),
            created_by=self.user,
        )
        self.warehouse = Warehouse.objects.create(
            name="مخزن اختبار", code="WH001")
        self.stock = Stock.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity=50,
            created_by=self.user,
        )
        self.movement = StockMovement.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity=10,
            movement_type="in",
            reference_number="ADD-001",
            notes="إضافة بضاعة جديدة",
            created_by=self.user,
        )

    def test_movement_creation(self):
        """Test stock movement creation"""
        self.assertEqual(self.movement.product, self.product)
        self.assertEqual(self.movement.warehouse, self.warehouse)
        self.assertEqual(self.movement.quantity, 10)
        self.assertEqual(self.movement.movement_type, "in")
        self.assertEqual(self.movement.reference_number, "ADD-001")
        self.assertEqual(self.movement.notes, "إضافة بضاعة جديدة")
        self.assertEqual(self.movement.created_by, self.user)
        self.assertIsNotNone(self.movement.timestamp)

    def test_movement_str(self):
        """Test stock movement string representation"""
        # يجب أن يحتوي تمثيل الحركة على نوعها واسم المنتج
        movement_str = str(self.movement)
        self.assertIn("منتج اختبار", movement_str)
        self.assertIn("in", movement_str)  # movement_type value

        # إنشاء حركة سحب
        out_movement = StockMovement.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity=5,
            movement_type="out",
            reference_number="OUT-001",
            notes="سحب بضاعة",
            created_by=self.user,
        )

        # يجب أن يحتوي تمثيل الحركة على نوعها واسم المنتج
        out_movement_str = str(out_movement)
        self.assertIn("منتج اختبار", out_movement_str)
        self.assertIn("out", out_movement_str)  # movement_type value

    def test_movement_types(self):
        """Test different stock movement types and their effect on stock quantity"""
        # إنشاء حركة إضافة وحركة سحب
        StockMovement.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity=20,
            movement_type="in",
            reference_number="ADD-002",
            notes="إضافة بضاعة إضافية",
            created_by=self.user,
        )

        StockMovement.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity=15,
            movement_type="out",
            reference_number="OUT-001",
            notes="سحب بضاعة",
            created_by=self.user,
        )

        # التحقق من عدد الحركات
        movements = StockMovement.objects.filter(
            product=self.product, warehouse=self.warehouse
        )
        self.assertEqual(movements.count(), 3)

        # التحقق من مجموع الكميات المضافة (10 + 20 = 30)
        in_total = movements.filter(movement_type="in").aggregate(total=models.Sum("quantity"))[
            "total"
        ]
        self.assertEqual(in_total, 30)

        # التحقق من مجموع الكميات المسحوبة (15)
        out_total = movements.filter(movement_type="out").aggregate(
            total=models.Sum("quantity")
        )["total"]
        self.assertEqual(out_total, 15)
