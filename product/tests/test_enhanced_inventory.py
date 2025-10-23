"""
اختبارات شاملة لنظام المخزن المحسن
"""
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
import unittest

from product.models import (
    Product,
    Category,
    Brand,
    Unit,
    Warehouse,
    ProductStock,
    StockTransfer,
    StockSnapshot,
    InventoryMovement,
    InventoryAdjustment,
    InventoryAdjustmentItem,
    StockReservation,
    ReservationFulfillment,
    ProductBatch,
    ExpiryAlert,
    LocationZone,
    LocationAisle,
    LocationShelf,
    ProductLocation,
)
from product.services.inventory_service import InventoryService
from product.services.reservation_service import ReservationService
from product.services.expiry_service import ExpiryService

User = get_user_model()


class BaseInventoryTestCase(TestCase):
    """فئة أساسية للاختبارات مع إعداد البيانات الأساسية"""

    def setUp(self):
        # إنشاء مستخدم للاختبار
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        # إنشاء البيانات الأساسية
        self.category = Category.objects.create(
            name="إلكترونيات", description="منتجات إلكترونية"
        )

        self.brand = Brand.objects.create(
            name="سامسونج", description="علامة تجارية كورية"
        )

        self.unit = Unit.objects.create(name="قطعة", symbol="قطعة")

        self.warehouse = Warehouse.objects.create(
            name="المخزن الرئيسي", code="MAIN", location="الرياض", manager=self.user
        )

        self.product = Product.objects.create(
            name="هاتف ذكي",
            sku="PHONE001",
            category=self.category,
            brand=self.brand,
            unit=self.unit,
            cost_price=Decimal("500.00"),
            selling_price=Decimal("750.00"),
            min_stock=10,
            created_by=self.user,
        )


class ProductStockTestCase(BaseInventoryTestCase):
    """اختبارات نموذج مخزون المنتج المحسن"""

    def test_create_product_stock(self):
        """اختبار إنشاء مخزون منتج"""
        stock = ProductStock.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity=100,
            min_stock_level=10,
            max_stock_level=500,
        )

        self.assertEqual(stock.available_quantity, 100)
        self.assertFalse(stock.is_low_stock)
        self.assertFalse(stock.is_out_of_stock)

    def test_stock_reservation(self):
        """اختبار حجز المخزون"""
        stock = ProductStock.objects.create(
            product=self.product, warehouse=self.warehouse, quantity=100
        )

        # حجز 30 قطعة
        stock.reserved_quantity = 30
        stock.save()

        self.assertEqual(stock.available_quantity, 70)
        self.assertEqual(stock.reserved_quantity, 30)

    def test_low_stock_detection(self):
        """اختبار اكتشاف المخزون المنخفض"""
        stock = ProductStock.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity=5,
            min_stock_level=10,
        )

        self.assertTrue(stock.is_low_stock)
        self.assertFalse(stock.is_out_of_stock)

    def test_out_of_stock_detection(self):
        """اختبار اكتشاف نفاد المخزون"""
        stock = ProductStock.objects.create(
            product=self.product, warehouse=self.warehouse, quantity=0
        )

        self.assertTrue(stock.is_out_of_stock)
        self.assertTrue(stock.is_low_stock)

    def test_unique_product_warehouse_constraint(self):
        """اختبار قيد الفرادة للمنتج والمخزن"""
        ProductStock.objects.create(
            product=self.product, warehouse=self.warehouse, quantity=100
        )

        # محاولة إنشاء مخزون آخر لنفس المنتج والمخزن
        with self.assertRaises(IntegrityError):
            ProductStock.objects.create(
                product=self.product, warehouse=self.warehouse, quantity=50
            )


class InventoryMovementTestCase(BaseInventoryTestCase):
    """اختبارات حركات المخزون المتقدمة"""

    def setUp(self):
        super().setUp()
        self.stock = ProductStock.objects.create(
            product=self.product, warehouse=self.warehouse, quantity=100
        )

    def test_create_inventory_movement(self):
        """اختبار إنشاء حركة مخزون"""
        movement = InventoryMovement.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            movement_type="in",
            document_type="purchase",
            document_number="REC001",
            quantity=50,
            unit_cost=Decimal("10.00"),
            total_cost=Decimal("500.00"),
            notes="استلام بضاعة جديدة",
            created_by=self.user,
        )

        self.assertEqual(movement.product, self.product)
        self.assertEqual(movement.quantity, 50)
        self.assertFalse(movement.is_approved)

    def test_approve_movement(self):
        """اختبار اعتماد حركة المخزون"""
        movement = InventoryMovement.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            movement_type="in",
            document_type="purchase",
            document_number="REC001",
            quantity=50,
            unit_cost=Decimal("10.00"),
            total_cost=Decimal("500.00"),
            created_by=self.user,
        )

        # اعتماد الحركة
        movement.is_approved = True
        movement.approved_by = self.user
        movement.approved_at = timezone.now()
        movement.save()

        self.assertTrue(movement.is_approved)
        self.assertEqual(movement.approved_by, self.user)

    def test_movement_types(self):
        """اختبار أنواع حركات المخزون المختلفة"""
        movement_types = ["in", "out", "transfer_in", "transfer_out", "adjustment_in"]

        for movement_type in movement_types:
            movement = InventoryMovement.objects.create(
                product=self.product,
                warehouse=self.warehouse,
                movement_type=movement_type,
                document_type="manual",
                document_number=f"REF_{movement_type.upper()}",
                quantity=10,
                unit_cost=Decimal("10.00"),
                total_cost=Decimal("100.00"),
                created_by=self.user,
            )
            self.assertEqual(movement.movement_type, movement_type)



class ProductBatchTestCase(BaseInventoryTestCase):
    """اختبارات نظام دفعات المنتجات وانتهاء الصلاحية"""

    def test_create_product_batch(self):
        """اختبار إنشاء دفعة منتج"""
        manufacturing_date = date.today() - timedelta(days=30)
        expiry_date = date.today() + timedelta(days=365)

        batch = ProductBatch.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            batch_number="BATCH001",
            production_date=manufacturing_date,
            expiry_date=expiry_date,
            received_date=date.today(),
            initial_quantity=100,
            current_quantity=100,
            reserved_quantity=0,
            unit_cost=Decimal("10.00"),
            total_cost=Decimal("1000.00"),
            status="active",
            created_by=self.user,
        )

        self.assertEqual(batch.batch_number, "BATCH001")
        self.assertFalse(batch.is_expired)
        self.assertFalse(batch.is_near_expiry)

    def test_expired_batch(self):
        """اختبار دفعة منتهية الصلاحية"""
        expiry_date = date.today() - timedelta(days=1)

        batch = ProductBatch.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            batch_number="EXPIRED001",
            production_date=date.today() - timedelta(days=400),
            expiry_date=expiry_date,
            received_date=date.today(),
            initial_quantity=50,
            current_quantity=50,
            reserved_quantity=0,
            unit_cost=Decimal("10.00"),
            total_cost=Decimal("500.00"),
            status="active",
            created_by=self.user,
        )

        self.assertTrue(batch.is_expired)
        self.assertTrue(batch.days_to_expiry < 0)

    def test_near_expiry_batch(self):
        """اختبار دفعة قريبة من انتهاء الصلاحية"""
        expiry_date = date.today() + timedelta(days=15)

        batch = ProductBatch.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            batch_number="NEAREXP001",
            production_date=date.today() - timedelta(days=350),
            expiry_date=expiry_date,
            received_date=date.today(),
            initial_quantity=30,
            current_quantity=30,
            reserved_quantity=0,
            unit_cost=Decimal("10.00"),
            total_cost=Decimal("300.00"),
            status="active",
            created_by=self.user,
        )

        self.assertFalse(batch.is_expired)
        self.assertTrue(batch.is_near_expiry)
        self.assertEqual(batch.days_to_expiry, 15)


class LocationSystemTestCase(BaseInventoryTestCase):
    """اختبارات نظام المواقع الهرمي"""

    def setUp(self):
        super().setUp()

        # إنشاء منطقة
        self.zone = LocationZone.objects.create(
            warehouse=self.warehouse,
            name="منطقة A",
            code="ZONE_A",
            description="المنطقة الرئيسية",
            created_by=self.user,
        )

        # إنشاء ممر
        self.aisle = LocationAisle.objects.create(
            zone=self.zone, name="ممر 1", code="AISLE_1"
        )

        # إنشاء رف
        self.shelf = LocationShelf.objects.create(
            aisle=self.aisle, 
            name="رف A1", 
            code="SHELF_A1", 
            max_weight=Decimal("100.00"),
            max_volume=Decimal("10.00"),
            levels=3
        )

    def test_location_hierarchy(self):
        """اختبار التسلسل الهرمي للمواقع"""
        self.assertEqual(self.shelf.aisle, self.aisle)
        self.assertEqual(self.aisle.zone, self.zone)
        self.assertEqual(self.zone.warehouse, self.warehouse)

    def test_product_location_assignment(self):
        """اختبار تخصيص موقع للمنتج"""
        location = ProductLocation.objects.create(
            product=self.product,
            shelf=self.shelf,
            current_quantity=50,
            location_type="primary",
            created_by=self.user
        )

        self.assertEqual(location.product, self.product)
        self.assertEqual(location.shelf, self.shelf)
        self.assertEqual(location.location_type, "primary")

    def test_shelf_capacity_validation(self):
        """اختبار التحقق من سعة الرف"""
        # إنشاء موقع مع حد أقصى
        location = ProductLocation.objects.create(
            product=self.product, 
            shelf=self.shelf, 
            current_quantity=60,
            max_quantity=100,
            created_by=self.user
        )

        # اختبار can_accommodate method
        self.assertTrue(location.can_accommodate(30))  # 60 + 30 = 90 < 100
        self.assertFalse(location.can_accommodate(50))  # 60 + 50 = 110 > 100


class InventoryServiceTestCase(BaseInventoryTestCase):
    """اختبارات خدمة المخزون"""

    def setUp(self):
        super().setUp()
        self.service = InventoryService()
        self.stock = ProductStock.objects.create(
            product=self.product, warehouse=self.warehouse, quantity=100
        )

    def test_update_stock_quantity(self):
        """اختبار تحديث كمية المخزون"""
        # زيادة المخزون بـ 50 (من 100 إلى 150)
        self.service.update_stock_quantity(
            product=self.product,
            warehouse=self.warehouse,
            quantity_change=50,
            movement_type="receipt",
            reference="TEST001",
            user=self.user,
        )

        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity, 150)

    def test_transfer_stock(self):
        """اختبار تحويل المخزون بين المخازن"""
        # إنشاء مخزن ثاني
        warehouse2 = Warehouse.objects.create(
            name="المخزن الثانوي", code="SEC", location="جدة", manager=self.user
        )

        # تحويل 30 قطعة
        transfer = self.service.transfer_stock(
            product=self.product,
            from_warehouse=self.warehouse,
            to_warehouse=warehouse2,
            quantity=30,
            user=self.user,
        )

        self.assertEqual(transfer.quantity, 30)
        self.assertEqual(transfer.status, "completed")

    def test_create_stock_adjustment(self):
        """اختبار إنشاء تسوية مخزون عبر حركة المخزون"""
        # استخدام record_movement لإنشاء تسوية (نقص 5 قطع)
        movement = self.service.record_movement(
            product=self.product,
            movement_type="out",
            quantity=5,
            warehouse=self.warehouse,
            source="adjustment",
            reference_number="ADJ-TEST-001",
            notes="تسوية مخزون - تلف",
            user=self.user,
        )

        # التحقق من الحركة
        self.assertIsNotNone(movement)
        self.assertEqual(movement.movement_type, "out")
        self.assertEqual(movement.quantity, 5)
        
        # التحقق من تحديث المخزون
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity, 95)




class IntegrationTestCase(TransactionTestCase):
    """اختبارات التكامل الشاملة"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="integrationuser",
            email="integration@example.com",
            password="testpass123",
        )

        # إعداد البيانات الأساسية
        self.category = Category.objects.create(name="أجهزة")
        self.brand = Brand.objects.create(name="آبل")
        self.unit = Unit.objects.create(name="جهاز", symbol="جهاز")
        self.warehouse = Warehouse.objects.create(
            name="المخزن المركزي",
            code="CENTRAL",
            location="الرياض",
            manager=self.user,
        )

        self.product = Product.objects.create(
            name="آيفون 15",
            sku="IPHONE15",
            category=self.category,
            brand=self.brand,
            unit=self.unit,
            cost_price=Decimal("3000.00"),
            selling_price=Decimal("4500.00"),
            created_by=self.user,
        )

    def test_complete_inventory_workflow(self):
        """اختبار سير عمل المخزون الكامل"""
        # 1. إنشاء مخزون أولي
        stock = ProductStock.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity=0,
            min_stock_level=5,
            max_stock_level=100,
        )

        # 2. استلام بضاعة
        receipt_movement = InventoryMovement.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            movement_type="in",
            document_type="purchase",
            document_number="REC001",
            quantity=50,
            unit_cost=Decimal("10.00"),
            total_cost=Decimal("500.00"),
            created_by=self.user,
            is_approved=True,
            approved_by=self.user,
        )

        # تحديث المخزون
        stock.quantity += receipt_movement.quantity
        stock.save()

        # 3. إنشاء حجز
        reservation_service = ReservationService()
        reservation = reservation_service.create_reservation(
            product=self.product,
            warehouse=self.warehouse,
            quantity=20,
            reference_number="SALE001",
            user=self.user,
        )

        # 4. تنفيذ الحجز (بيع)
        fulfillment = reservation_service.fulfill_reservation(
            reservation_id=reservation.id, quantity=15, user=self.user
        )

        # 5. التحقق من النتائج النهائية
        stock.refresh_from_db()
        reservation.refresh_from_db()

        # المخزون الأساسي لا يتغير بالحجز، فقط الكمية المحجوزة
        self.assertEqual(stock.quantity, 50)  # المخزون الأساسي
        self.assertEqual(stock.reserved_quantity, 5)  # 20 - 15 (تم تنفيذ 15)
        self.assertEqual(stock.available_quantity, 45)  # 50 - 5
        self.assertEqual(fulfillment.quantity_fulfilled, 15)

        # 6. إنشاء دفعة مع تاريخ انتهاء صلاحية
        batch = ProductBatch.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            batch_number="BATCH001",
            production_date=date.today(),
            expiry_date=date.today() + timedelta(days=365),
            received_date=date.today(),
            initial_quantity=35,
            current_quantity=35,
            reserved_quantity=0,
            unit_cost=Decimal("10.00"),
            total_cost=Decimal("350.00"),
            status="active",
            created_by=self.user,
        )

        # 7. فحص تنبيهات انتهاء الصلاحية
        expiry_service = ExpiryService()
        alerts_created = expiry_service.check_expiry_alerts()

        # لا يجب إنشاء تنبيهات للدفعة الجديدة
        self.assertEqual(alerts_created, 0)

        # التحقق من عدم وجود تنبيهات
        alerts = ExpiryAlert.objects.filter(batch=batch)
        self.assertEqual(alerts.count(), 0)

    def test_stock_transfer_workflow(self):
        """اختبار سير عمل تحويل المخزون"""
        # إنشاء مخزنين
        warehouse2 = Warehouse.objects.create(
            name="مخزن فرعي", code="BRANCH", location="جدة", manager=self.user
        )

        # إنشاء مخزون في المخزن الأول
        stock1 = ProductStock.objects.create(
            product=self.product, warehouse=self.warehouse, quantity=100
        )

        stock2 = ProductStock.objects.create(
            product=self.product, warehouse=warehouse2, quantity=0
        )

        # إنشاء تحويل
        transfer = StockTransfer.objects.create(
            product=self.product,
            from_warehouse=self.warehouse,
            to_warehouse=warehouse2,
            quantity=30,
            transfer_number="TRANS001",
            requested_by=self.user,
        )

        # اعتماد التحويل
        transfer.status = "approved"
        transfer.approved_by = self.user
        transfer.save()

        # تنفيذ التحويل
        with transaction.atomic():
            stock1.quantity -= transfer.quantity
            stock2.quantity += transfer.quantity
            stock1.save()
            stock2.save()

            transfer.status = "completed"
            transfer.save()

        # التحقق من النتائج
        stock1.refresh_from_db()
        stock2.refresh_from_db()
        transfer.refresh_from_db()

        self.assertEqual(stock1.quantity, 70)
        self.assertEqual(stock2.quantity, 30)
        self.assertEqual(transfer.status, "completed")


# تشغيل الاختبارات
if __name__ == "__main__":
    import django
    from django.conf import settings
    from django.test.utils import get_runner

    django.setup()
    TestRunner = get_runner(settings)
    test_runner = TestRunner()
    failures = test_runner.run_tests(["product.tests.test_enhanced_inventory"])
