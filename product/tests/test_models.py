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
            name="فئة رئيسية", created_by=self.user
        )
        self.child_category = Category.objects.create(
            name="فئة فرعية", parent=self.parent_category, created_by=self.user
        )

    def test_category_creation(self):
        """
        اختبار إنشاء فئة بشكل صحيح
        """
        self.assertEqual(self.parent_category.name, "فئة رئيسية")
        self.assertIsNone(self.parent_category.parent)
        self.assertEqual(self.child_category.name, "فئة فرعية")
        self.assertEqual(self.child_category.parent, self.parent_category)
        self.assertEqual(self.parent_category.created_by, self.user)
        self.assertEqual(self.child_category.created_by, self.user)
        self.assertIsNotNone(self.parent_category.created_at)
        self.assertIsNotNone(self.child_category.created_at)

    def test_category_str(self):
        """
        اختبار تمثيل التصنيف كنص
        """
        self.assertEqual(str(self.parent_category), "فئة رئيسية")
        # يجب أن يحتوي تمثيل التصنيف الفرعية على اسم التصنيف الأب
        self.assertEqual(str(self.child_category), "فئة رئيسية - فئة فرعية")

    def test_category_soft_delete(self):
        """
        اختبار الحذف الناعم للفئة
        """
        category_id = self.parent_category.id
        self.parent_category.delete()

        # يجب أن يكون الكائن غير موجود عند استخدام الدالة الافتراضية للحصول عليه
        self.assertFalse(Category.objects.filter(id=category_id).exists())

        # يجب أن يكون الكائن موجودًا عند استخدام all_objects
        self.assertTrue(Category.all_objects.filter(id=category_id).exists())

        # يجب أن تكون قيمة deleted_at محددة
        deleted_category = Category.all_objects.get(id=category_id)
        self.assertIsNotNone(deleted_category.deleted_at)

    def test_category_child_parent_relationship(self):
        """
        اختبار العلاقة بين التصنيف الأب والتصنيفات الفرعية
        """
        # يجب أن تظهر التصنيف الفرعية في قائمة التصنيفات الفرعية للفئة الأب
        self.assertTrue(self.child_category in self.parent_category.children.all())

        # إنشاء فئة فرعية أخرى
        second_child = Category.objects.create(
            name="فئة فرعية أخرى", parent=self.parent_category, created_by=self.user
        )

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
            name="علامة تجارية اختبار", description="وصف النوع", created_by=self.user
        )

    def test_brand_creation(self):
        """
        اختبار إنشاء علامة تجارية بشكل صحيح
        """
        self.assertEqual(self.brand.name, "علامة تجارية اختبار")
        self.assertEqual(self.brand.description, "وصف النوع")
        self.assertEqual(self.brand.created_by, self.user)
        self.assertIsNotNone(self.brand.created_at)

    def test_brand_str(self):
        """
        اختبار تمثيل النوع كنص
        """
        self.assertEqual(str(self.brand), "علامة تجارية اختبار")

    def test_brand_soft_delete(self):
        """
        اختبار الحذف الناعم للعلامة التجارية
        """
        brand_id = self.brand.id
        self.brand.delete()

        # يجب أن يكون الكائن غير موجود عند استخدام الدالة الافتراضية للحصول عليه
        self.assertFalse(Brand.objects.filter(id=brand_id).exists())

        # يجب أن يكون الكائن موجودًا عند استخدام all_objects
        self.assertTrue(Brand.all_objects.filter(id=brand_id).exists())

        # يجب أن تكون قيمة deleted_at محددة
        deleted_brand = Brand.all_objects.get(id=brand_id)
        self.assertIsNotNone(deleted_brand.deleted_at)


class UnitModelTest(TestCase):
    """
    اختبارات نموذج الوحدات
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass123", email="test@example.com"
        )
        self.unit = Unit.objects.create(
            name="قطعة", abbreviation="ق", created_by=self.user
        )

    def test_unit_creation(self):
        """
        اختبار إنشاء وحدة بشكل صحيح
        """
        self.assertEqual(self.unit.name, "قطعة")
        self.assertEqual(self.unit.abbreviation, "ق")
        self.assertEqual(self.unit.created_by, self.user)
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
        self.category = Category.objects.create(name="فئة اختبار", created_by=self.user)
        self.brand = Brand.objects.create(
            name="علامة تجارية اختبار", created_by=self.user
        )
        self.unit = Unit.objects.create(
            name="قطعة", abbreviation="ق", created_by=self.user
        )
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
        self.assertEqual(str(self.product), "منتج اختبار")

    def test_product_soft_delete(self):
        """
        اختبار الحذف الناعم للمنتج
        """
        product_id = self.product.id
        self.product.delete()

        # يجب أن يكون الكائن غير موجود عند استخدام الدالة الافتراضية للحصول عليه
        self.assertFalse(Product.objects.filter(id=product_id).exists())

        # يجب أن يكون الكائن موجودًا عند استخدام all_objects
        self.assertTrue(Product.all_objects.filter(id=product_id).exists())

        # يجب أن تكون قيمة deleted_at محددة
        deleted_product = Product.all_objects.get(id=product_id)
        self.assertIsNotNone(deleted_product.deleted_at)

    def test_product_profit_margin(self):
        """
        اختبار حساب هامش الربح للمنتج
        """
        # هامش الربح = (سعر البيع - تكلفة الشراء) / سعر البيع * 100
        # = (100 - 80) / 100 * 100 = 20%
        self.assertEqual(self.product.profit_margin, 20)

        # تغيير سعر البيع والتكلفة
        self.product.cost_price = Decimal("60.00")
        self.product.selling_price = Decimal("90.00")
        self.product.save()

        # هامش الربح الجديد = (90 - 60) / 90 * 100 = 33.33%
        self.assertAlmostEqual(self.product.profit_margin, 33.33, places=2)


class WarehouseModelTest(TestCase):
    """
    اختبارات نموذج المستودعات
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass123", email="test@example.com"
        )
        self.warehouse = Warehouse.objects.create(
            name="مستودع اختبار",
            code="WH001",
            address="عنوان المستودع",
            description="وصف المستودع",
            created_by=self.user,
        )

    def test_warehouse_creation(self):
        """
        اختبار إنشاء مستودع بشكل صحيح
        """
        self.assertEqual(self.warehouse.name, "مستودع اختبار")
        self.assertEqual(self.warehouse.code, "WH001")
        self.assertEqual(self.warehouse.address, "عنوان المستودع")
        self.assertEqual(self.warehouse.description, "وصف المستودع")
        self.assertEqual(self.warehouse.created_by, self.user)
        self.assertIsNotNone(self.warehouse.created_at)

    def test_warehouse_str(self):
        """
        اختبار تمثيل المستودع كنص
        """
        self.assertEqual(str(self.warehouse), "مستودع اختبار")

    def test_warehouse_soft_delete(self):
        """
        اختبار الحذف الناعم للمستودع
        """
        warehouse_id = self.warehouse.id
        self.warehouse.delete()

        # يجب أن يكون الكائن غير موجود عند استخدام الدالة الافتراضية للحصول عليه
        self.assertFalse(Warehouse.objects.filter(id=warehouse_id).exists())

        # يجب أن يكون الكائن موجودًا عند استخدام all_objects
        self.assertTrue(Warehouse.all_objects.filter(id=warehouse_id).exists())

        # يجب أن تكون قيمة deleted_at محددة
        deleted_warehouse = Warehouse.all_objects.get(id=warehouse_id)
        self.assertIsNotNone(deleted_warehouse.deleted_at)


class StockModelTest(TestCase):
    """
    اختبارات نموذج المخزون
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass123", email="test@example.com"
        )
        self.category = Category.objects.create(name="فئة اختبار", created_by=self.user)
        self.unit = Unit.objects.create(
            name="قطعة", abbreviation="ق", created_by=self.user
        )
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
            name="مستودع اختبار", code="WH001", created_by=self.user
        )
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
        self.assertIsNotNone(self.stock.created_at)

    def test_stock_str(self):
        """
        اختبار تمثيل المخزون كنص
        """
        expected_str = f"منتج اختبار - مستودع اختبار: 50 قطعة"
        self.assertEqual(str(self.stock), expected_str)

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
    """
    اختبارات نموذج حركات المخزون
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass123", email="test@example.com"
        )
        self.category = Category.objects.create(name="فئة اختبار", created_by=self.user)
        self.unit = Unit.objects.create(
            name="قطعة", abbreviation="ق", created_by=self.user
        )
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
            name="مستودع اختبار", code="WH001", created_by=self.user
        )
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
            type="in",
            reference="ADD-001",
            notes="إضافة بضاعة جديدة",
            created_by=self.user,
        )

    def test_movement_creation(self):
        """
        اختبار إنشاء حركة مخزون بشكل صحيح
        """
        self.assertEqual(self.movement.product, self.product)
        self.assertEqual(self.movement.warehouse, self.warehouse)
        self.assertEqual(self.movement.quantity, 10)
        self.assertEqual(self.movement.type, "in")
        self.assertEqual(self.movement.reference, "ADD-001")
        self.assertEqual(self.movement.notes, "إضافة بضاعة جديدة")
        self.assertEqual(self.movement.created_by, self.user)
        self.assertIsNotNone(self.movement.created_at)

    def test_movement_str(self):
        """
        اختبار تمثيل حركة المخزون كنص
        """
        # يجب أن يحتوي تمثيل الحركة على نوعها واسم المنتج
        self.assertIn("منتج اختبار", str(self.movement))
        self.assertIn("إضافة", str(self.movement))

        # إنشاء حركة سحب
        out_movement = StockMovement.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity=5,
            type="out",
            reference="OUT-001",
            notes="سحب بضاعة",
            created_by=self.user,
        )

        # يجب أن يحتوي تمثيل الحركة على نوعها واسم المنتج
        self.assertIn("منتج اختبار", str(out_movement))
        self.assertIn("سحب", str(out_movement))

    def test_movement_types(self):
        """
        اختبار أنواع حركات المخزون وتأثيرها على رصيد المخزون
        """
        # إنشاء حركة إضافة وحركة سحب
        StockMovement.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity=20,
            type="in",
            reference="ADD-002",
            notes="إضافة بضاعة إضافية",
            created_by=self.user,
        )

        StockMovement.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity=15,
            type="out",
            reference="OUT-001",
            notes="سحب بضاعة",
            created_by=self.user,
        )

        # التحقق من عدد الحركات
        movements = StockMovement.objects.filter(
            product=self.product, warehouse=self.warehouse
        )
        self.assertEqual(movements.count(), 3)

        # التحقق من مجموع الكميات المضافة (10 + 20 = 30)
        in_total = movements.filter(type="in").aggregate(total=models.Sum("quantity"))[
            "total"
        ]
        self.assertEqual(in_total, 30)

        # التحقق من مجموع الكميات المسحوبة (15)
        out_total = movements.filter(type="out").aggregate(
            total=models.Sum("quantity")
        )["total"]
        self.assertEqual(out_total, 15)
