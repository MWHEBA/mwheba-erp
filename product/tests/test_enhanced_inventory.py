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


class StockReservationTestCase(BaseInventoryTestCase):
    """اختبارات نظام حجوزات المخزون"""

    def setUp(self):
        super().setUp()
        self.stock = ProductStock.objects.create(
            product=self.product, warehouse=self.warehouse, quantity=100
        )

    def test_create_stock_reservation(self):
        """اختبار إنشاء حجز مخزون"""
        expiry_date = timezone.now() + timedelta(hours=24)

        reservation = StockReservation.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity_reserved=30,
            reference_number="ORDER001",
            expires_at=expiry_date,
            reserved_by=self.user,
            reservation_type="manual",
            status="active",
        )

        self.assertEqual(reservation.quantity_reserved, 30)
        self.assertEqual(reservation.status, "active")
        self.assertFalse(reservation.is_expired)

    def test_reservation_expiry(self):
        """اختبار انتهاء صلاحية الحجز"""
        # إنشاء حجز منتهي الصلاحية
        expiry_date = timezone.now() - timedelta(hours=1)

        reservation = StockReservation.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity_reserved=30,
            reference_number="ORDER001",
            expires_at=expiry_date,
            reserved_by=self.user,
            reservation_type="manual",
            status="expired",
        )

        self.assertTrue(reservation.is_expired)

    def test_reservation_fulfillment(self):
        """اختبار تنفيذ الحجز"""
        reservation = StockReservation.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity_reserved=30,
            reference_number="ORDER001",
            expires_at=timezone.now() + timedelta(hours=24),
            reserved_by=self.user,
            reservation_type="manual",
            status="active",
        )

        # تنفيذ الحجز
        fulfillment = ReservationFulfillment.objects.create(
            reservation=reservation, fulfilled_quantity=25, fulfilled_by=self.user
        )

        self.assertEqual(fulfillment.fulfilled_quantity, 25)
        self.assertEqual(fulfillment.fulfilled_by, self.user)


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
            aisle=self.aisle, name="رف A1", code="SHELF_A1", capacity=100
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
            quantity=50,
            is_primary_location=True,
        )

        self.assertEqual(location.product, self.product)
        self.assertEqual(location.shelf, self.shelf)
        self.assertTrue(location.is_primary_location)

    def test_shelf_capacity_validation(self):
        """اختبار التحقق من سعة الرف"""
        # تخصيص 60 قطعة
        ProductLocation.objects.create(
            product=self.product, shelf=self.shelf, quantity=60
        )

        # محاولة تخصيص 50 قطعة إضافية (المجموع 110 > السعة 100)
        with self.assertRaises(ValidationError):
            location = ProductLocation(
                product=self.product, shelf=self.shelf, quantity=50
            )
            location.full_clean()


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
        # زيادة المخزون
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
        """اختبار إنشاء تسوية مخزون"""
        adjustment = self.service.create_stock_adjustment(
            product=self.product,
            warehouse=self.warehouse,
            actual_quantity=95,
            reason="تلف",
            user=self.user,
        )

        self.assertEqual(adjustment.adjustment_type, "decrease")
        self.assertEqual(adjustment.actual_quantity - adjustment.expected_quantity, -5)


class ReservationServiceTestCase(BaseInventoryTestCase):
    """اختبارات خدمة الحجوزات"""

    def setUp(self):
        super().setUp()
        self.service = ReservationService()
        self.stock = ProductStock.objects.create(
            product=self.product, warehouse=self.warehouse, quantity=100
        )

    def test_create_reservation(self):
        """اختبار إنشاء حجز"""
        reservation = self.service.create_reservation(
            product=self.product,
            warehouse=self.warehouse,
            quantity=30,
            reserved_for="ORDER001",
            user=self.user,
        )

        self.assertEqual(reservation.quantity, 30)
        self.assertEqual(reservation.reserved_for, "ORDER001")

        # التحقق من تحديث المخزون المحجوز
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.reserved_quantity, 30)

    def test_fulfill_reservation(self):
        """اختبار تنفيذ الحجز"""
        # إنشاء حجز
        reservation = self.service.create_reservation(
            product=self.product,
            warehouse=self.warehouse,
            quantity=30,
            reserved_for="ORDER001",
            user=self.user,
        )

        # تنفيذ الحجز
        fulfillment = self.service.fulfill_reservation(
            reservation_id=reservation.id, quantity=25, user=self.user
        )

        self.assertEqual(fulfillment.fulfilled_quantity, 25)

        # التحقق من تحديث المخزون
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity, 75)  # 100 - 25
        self.assertEqual(self.stock.reserved_quantity, 5)  # 30 - 25

    def test_cancel_reservation(self):
        """اختبار إلغاء الحجز"""
        # إنشاء حجز
        reservation = self.service.create_reservation(
            product=self.product,
            warehouse=self.warehouse,
            quantity=30,
            reserved_for="ORDER001",
            user=self.user,
        )

        # إلغاء الحجز
        self.service.cancel_reservation(
            reservation_id=reservation.id, reason="إلغاء الطلب", user=self.user
        )

        reservation.refresh_from_db()
        self.assertEqual(reservation.status, "cancelled")

        # التحقق من إعادة الكمية للمخزون المتاح
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.reserved_quantity, 0)


class ExpiryServiceTestCase(BaseInventoryTestCase):
    """اختبارات خدمة انتهاء الصلاحية"""

    def setUp(self):
        super().setUp()
        self.service = ExpiryService()

    def test_check_expiry_alerts(self):
        """اختبار فحص تنبيهات انتهاء الصلاحية"""
        # إنشاء دفعة قريبة من انتهاء الصلاحية
        batch = ProductBatch.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            batch_number="NEAREXP001",
            production_date=date.today() - timedelta(days=350),
            expiry_date=date.today() + timedelta(days=15),
            received_date=date.today(),
            initial_quantity=50,
            current_quantity=50,
            reserved_quantity=0,
            unit_cost=Decimal("10.00"),
            total_cost=Decimal("500.00"),
            status="active",
            created_by=self.user,
        )

        # فحص التنبيهات
        alerts_created = self.service.check_expiry_alerts()

        self.assertGreater(alerts_created, 0)

        # التحقق من إنشاء التنبيه
        alert = ExpiryAlert.objects.filter(batch=batch).first()
        self.assertIsNotNone(alert)
        self.assertEqual(alert.alert_type, "near_expiry")

    def test_get_expiring_products(self):
        """اختبار الحصول على المنتجات القريبة من انتهاء الصلاحية"""
        # إنشاء دفعات مختلفة
        ProductBatch.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            batch_number="GOOD001",
            production_date=date.today() - timedelta(days=30),
            expiry_date=date.today() + timedelta(days=300),
            received_date=date.today(),
            initial_quantity=100,
            current_quantity=100,
            reserved_quantity=0,
            unit_cost=Decimal("10.00"),
            total_cost=Decimal("1000.00"),
            status="active",
            created_by=self.user,
        )

        ProductBatch.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            batch_number="NEAREXP001",
            production_date=date.today() - timedelta(days=350),
            expiry_date=date.today() + timedelta(days=20),
            received_date=date.today(),
            initial_quantity=50,
            current_quantity=50,
            reserved_quantity=0,
            unit_cost=Decimal("10.00"),
            total_cost=Decimal("500.00"),
            status="active",
            created_by=self.user,
        )

        # الحصول على المنتجات القريبة من انتهاء الصلاحية
        expiring_products = self.service.get_expiring_products(days_ahead=30)

        self.assertEqual(len(expiring_products), 1)
        self.assertEqual(expiring_products[0].batch_number, "NEAREXP001")

    def test_get_expired_products(self):
        """اختبار الحصول على المنتجات منتهية الصلاحية"""
        # إنشاء دفعة منتهية الصلاحية
        ProductBatch.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            batch_number="EXPIRED001",
            production_date=date.today() - timedelta(days=400),
            expiry_date=date.today() - timedelta(days=5),
            received_date=date.today(),
            initial_quantity=25,
            current_quantity=25,
            reserved_quantity=0,
            unit_cost=Decimal("10.00"),
            total_cost=Decimal("250.00"),
            status="active",
            created_by=self.user,
        )

        # الحصول على المنتجات منتهية الصلاحية
        expired_products = self.service.get_expired_products()

        self.assertEqual(len(expired_products), 1)
        self.assertEqual(expired_products[0].batch_number, "EXPIRED001")


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
