"""
أدوات مساعدة للاختبارات
"""
import random
import string
from decimal import Decimal
from datetime import date, timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone

from product.models import (
    Product,
    Category,
    Brand,
    Unit,
    Warehouse,
    ProductStock,
    StockReservation,
    ProductBatch,
    SupplierProductPrice,
)
from supplier.models import Supplier

User = get_user_model()


class TestDataFactory:
    """مصنع إنشاء بيانات الاختبار"""

    @staticmethod
    def create_user(username=None, **kwargs):
        """إنشاء مستخدم للاختبار"""
        if not username:
            username = f"testuser_{TestDataFactory._random_string(6)}"

        # التأكد من أن البريد الإلكتروني فريد
        email = kwargs.get(
            "email", f"{username}_{TestDataFactory._random_string(4)}@example.com"
        )

        defaults = {"email": email, "password": "testpass123"}
        defaults.update(kwargs)

        return User.objects.create_user(username=username, **defaults)

    @staticmethod
    def create_category(name=None, **kwargs):
        """إنشاء فئة للاختبار"""
        if not name:
            name = f"فئة اختبار {TestDataFactory._random_string(4)}"

        defaults = {"description": f"وصف {name}"}
        defaults.update(kwargs)

        return Category.objects.create(name=name, **defaults)

    @staticmethod
    def create_brand(name=None, **kwargs):
        """إنشاء علامة تجارية للاختبار"""
        if not name:
            name = f"علامة {TestDataFactory._random_string(4)}"

        defaults = {"description": f"وصف {name}"}
        defaults.update(kwargs)

        return Brand.objects.create(name=name, **defaults)

    @staticmethod
    def create_unit(name=None, symbol=None, **kwargs):
        """إنشاء وحدة قياس للاختبار"""
        if not name:
            name = f"وحدة {TestDataFactory._random_string(4)}"
        if not symbol:
            symbol = name[:3]

        return Unit.objects.create(name=name, symbol=symbol, **kwargs)

    @staticmethod
    def create_warehouse(name=None, code=None, manager=None, **kwargs):
        """إنشاء مخزن للاختبار"""
        if not name:
            name = f"مخزن {TestDataFactory._random_string(4)}"
        if not code:
            code = TestDataFactory._random_string(4).upper()
        if not manager:
            manager = TestDataFactory.create_user()

        defaults = {"location": "موقع اختبار", "manager": manager}
        defaults.update(kwargs)

        return Warehouse.objects.create(name=name, code=code, **defaults)

    @staticmethod
    def create_product(
        name=None,
        sku=None,
        category=None,
        brand=None,
        unit=None,
        created_by=None,
        **kwargs,
    ):
        """إنشاء منتج للاختبار"""
        if not name:
            name = f"منتج {TestDataFactory._random_string(6)}"
        if not sku:
            sku = f"SKU{TestDataFactory._random_string(6).upper()}"
        if not category:
            category = TestDataFactory.create_category()
        if not brand:
            brand = TestDataFactory.create_brand()
        if not unit:
            unit = TestDataFactory.create_unit()
        if not created_by:
            created_by = TestDataFactory.create_user()

        defaults = {
            "cost_price": Decimal("100.00"),
            "selling_price": Decimal("150.00"),
            "min_stock": 10,
            "created_by": created_by,
        }
        defaults.update(kwargs)

        return Product.objects.create(
            name=name, sku=sku, category=category, brand=brand, unit=unit, **defaults
        )

    @staticmethod
    def create_product_stock(product=None, warehouse=None, **kwargs):
        """إنشاء مخزون منتج للاختبار"""
        if not product:
            product = TestDataFactory.create_product()
        if not warehouse:
            warehouse = TestDataFactory.create_warehouse()

        defaults = {"quantity": 100, "min_stock_level": 10, "max_stock_level": 500}
        defaults.update(kwargs)

        return ProductStock.objects.create(
            product=product, warehouse=warehouse, **defaults
        )

    @staticmethod
    def create_supplier(name=None, code=None, **kwargs):
        """إنشاء مورد للاختبار"""
        if not name:
            name = f"مورد {TestDataFactory._random_string(6)}"
        if not code:
            code = f"SUP{TestDataFactory._random_string(6).upper()}"

        defaults = {
            "email": f"supplier_{TestDataFactory._random_string(4)}@example.com",
            "phone": f"05{random.randint(10000000, 99999999)}",
            "code": code,
        }
        defaults.update(kwargs)

        return Supplier.objects.create(name=name, **defaults)

    @staticmethod
    def create_supplier_price(product=None, supplier=None, created_by=None, **kwargs):
        """إنشاء سعر مورد للاختبار"""
        if not product:
            product = TestDataFactory.create_product()
        if not supplier:
            supplier = TestDataFactory.create_supplier()
        if not created_by:
            created_by = TestDataFactory.create_user()

        defaults = {
            "cost_price": Decimal("95.00"),
            "is_default": False,
            "created_by": created_by,
        }
        defaults.update(kwargs)

        return SupplierProductPrice.objects.create(
            product=product, supplier=supplier, **defaults
        )

    @staticmethod
    def create_stock_reservation(
        product=None, warehouse=None, created_by=None, **kwargs
    ):
        """إنشاء حجز مخزون للاختبار"""
        if not product:
            product = TestDataFactory.create_product()
        if not warehouse:
            warehouse = TestDataFactory.create_warehouse()
        if not created_by:
            created_by = TestDataFactory.create_user()

        defaults = {
            "quantity_reserved": 30,
            "reference_number": f"ORDER{TestDataFactory._random_string(6)}",
            "expires_at": timezone.now() + timedelta(hours=24),
            "reserved_by": created_by,
            "reservation_type": "manual",
            "status": "active",
        }
        defaults.update(kwargs)

        return StockReservation.objects.create(
            product=product, warehouse=warehouse, **defaults
        )

    @staticmethod
    def create_product_batch(product=None, warehouse=None, **kwargs):
        """إنشاء دفعة منتج للاختبار"""
        if not product:
            product = TestDataFactory.create_product()
        if not warehouse:
            warehouse = TestDataFactory.create_warehouse()

        defaults = {
            "batch_number": f"BATCH{TestDataFactory._random_string(6)}",
            "production_date": date.today() - timedelta(days=30),
            "expiry_date": date.today() + timedelta(days=365),
            "received_date": date.today(),
            "initial_quantity": 50,
            "current_quantity": 50,
            "reserved_quantity": 0,
            "unit_cost": Decimal("10.00"),
            "total_cost": Decimal("500.00"),  # initial_quantity * unit_cost
            "status": "active",
            "created_by": TestDataFactory.create_user(),
        }
        defaults.update(kwargs)

        return ProductBatch.objects.create(
            product=product, warehouse=warehouse, **defaults
        )

    @staticmethod
    def _random_string(length=6):
        """إنشاء نص عشوائي"""
        return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


class TestAssertions:
    """تأكيدات مخصصة للاختبارات"""

    @staticmethod
    def assert_stock_quantity(test_case, product, warehouse, expected_quantity):
        """التأكد من كمية المخزون"""
        try:
            stock = ProductStock.objects.get(product=product, warehouse=warehouse)
            test_case.assertEqual(stock.quantity, expected_quantity)
        except ProductStock.DoesNotExist:
            test_case.fail(
                f"لا يوجد مخزون للمنتج {product.name} في المخزن {warehouse.name}"
            )

    @staticmethod
    def assert_reservation_exists(test_case, product, warehouse, reserved_for):
        """التأكد من وجود حجز"""
        reservation = StockReservation.objects.filter(
            product=product,
            warehouse=warehouse,
            reserved_for=reserved_for,
            status="active",
        ).first()

        test_case.assertIsNotNone(
            reservation, f"لا يوجد حجز نشط للمنتج {product.name} للطلب {reserved_for}"
        )
        return reservation

    @staticmethod
    def assert_batch_expiry_status(test_case, batch, expected_status):
        """التأكد من حالة انتهاء صلاحية الدفعة"""
        if expected_status == "expired":
            test_case.assertTrue(
                batch.is_expired,
                f"الدفعة {batch.batch_number} يجب أن تكون منتهية الصلاحية",
            )
        elif expected_status == "near_expiry":
            test_case.assertTrue(
                batch.is_near_expiry,
                f"الدفعة {batch.batch_number} يجب أن تكون قريبة من انتهاء الصلاحية",
            )
        elif expected_status == "good":
            test_case.assertFalse(
                batch.is_expired,
                f"الدفعة {batch.batch_number} يجب ألا تكون منتهية الصلاحية",
            )
            test_case.assertFalse(
                batch.is_near_expiry,
                f"الدفعة {batch.batch_number} يجب ألا تكون قريبة من انتهاء الصلاحية",
            )

    @staticmethod
    def assert_supplier_is_default(test_case, product, supplier):
        """التأكد من أن المورد هو الافتراضي"""
        supplier_price = SupplierProductPrice.objects.get(
            product=product, supplier=supplier
        )
        test_case.assertTrue(
            supplier_price.is_default,
            f"المورد {supplier.name} يجب أن يكون افتراضي للمنتج {product.name}",
        )

        product.refresh_from_db()
        test_case.assertEqual(
            product.default_supplier,
            supplier,
            f"المورد الافتراضي للمنتج {product.name} يجب أن يكون {supplier.name}",
        )


class TestScenarios:
    """سيناريوهات اختبار شائعة"""

    @staticmethod
    def setup_basic_inventory_scenario():
        """إعداد سيناريو مخزون أساسي"""
        user = TestDataFactory.create_user(
            username=f"inventory_manager_{TestDataFactory._random_string(4)}"
        )
        warehouse = TestDataFactory.create_warehouse(manager=user)

        products = []
        for i in range(3):
            product = TestDataFactory.create_product(
                name=f"منتج {i+1}",
                sku=f"PROD{i+1:03d}_{TestDataFactory._random_string(4)}",
                created_by=user,
            )

            TestDataFactory.create_product_stock(
                product=product,
                warehouse=warehouse,
                quantity=100 - i * 20,  # كميات متدرجة
            )

            products.append(product)

        return {"user": user, "warehouse": warehouse, "products": products}

    @staticmethod
    def setup_supplier_pricing_scenario():
        """إعداد سيناريو تسعير الموردين"""
        user = TestDataFactory.create_user(
            username=f"pricing_manager_{TestDataFactory._random_string(4)}"
        )
        product = TestDataFactory.create_product(created_by=user)

        suppliers = []
        prices = [Decimal("95.00"), Decimal("98.00"), Decimal("92.00")]

        for i, price in enumerate(prices):
            supplier = TestDataFactory.create_supplier(name=f"مورد {i+1}")

            TestDataFactory.create_supplier_price(
                product=product,
                supplier=supplier,
                cost_price=price,
                is_default=(i == 0),  # الأول افتراضي
                created_by=user,
            )

            suppliers.append(supplier)

        return {"user": user, "product": product, "suppliers": suppliers}

    @staticmethod
    def setup_expiry_tracking_scenario():
        """إعداد سيناريو تتبع انتهاء الصلاحية"""
        user = TestDataFactory.create_user(
            username=f"expiry_manager_{TestDataFactory._random_string(4)}"
        )
        warehouse = TestDataFactory.create_warehouse(manager=user)
        product = TestDataFactory.create_product(created_by=user)

        # دفعة جيدة
        good_batch = TestDataFactory.create_product_batch(
            product=product,
            warehouse=warehouse,
            batch_number=f"GOOD{TestDataFactory._random_string(6)}",
            expiry_date=date.today() + timedelta(days=300),
        )

        # دفعة قريبة من انتهاء الصلاحية
        near_expiry_batch = TestDataFactory.create_product_batch(
            product=product,
            warehouse=warehouse,
            batch_number=f"NEAREXP{TestDataFactory._random_string(6)}",
            expiry_date=date.today() + timedelta(days=20),
        )

        # دفعة منتهية الصلاحية
        expired_batch = TestDataFactory.create_product_batch(
            product=product,
            warehouse=warehouse,
            batch_number=f"EXPIRED{TestDataFactory._random_string(6)}",
            expiry_date=date.today() - timedelta(days=5),
        )

        return {
            "user": user,
            "warehouse": warehouse,
            "product": product,
            "batches": {
                "good": good_batch,
                "near_expiry": near_expiry_batch,
                "expired": expired_batch,
            },
        }

    @staticmethod
    def setup_reservation_scenario():
        """إعداد سيناريو الحجوزات"""
        user = TestDataFactory.create_user(
            username=f"reservation_manager_{TestDataFactory._random_string(4)}"
        )
        warehouse = TestDataFactory.create_warehouse(manager=user)
        product = TestDataFactory.create_product(created_by=user)

        # إنشاء مخزون
        stock = TestDataFactory.create_product_stock(
            product=product, warehouse=warehouse, quantity=100
        )

        # حجز نشط
        active_reservation = TestDataFactory.create_stock_reservation(
            product=product,
            warehouse=warehouse,
            reference_number="ORDER001",
            quantity_reserved=30,
            created_by=user,
        )

        # حجز منتهي الصلاحية
        expired_reservation = TestDataFactory.create_stock_reservation(
            product=product,
            warehouse=warehouse,
            reference_number="ORDER002",
            quantity_reserved=20,
            expires_at=timezone.now() - timedelta(hours=1),
            created_by=user,
        )

        return {
            "user": user,
            "warehouse": warehouse,
            "product": product,
            "stock": stock,
            "reservations": {
                "active": active_reservation,
                "expired": expired_reservation,
            },
        }


class MockServices:
    """خدمات وهمية للاختبار"""

    @staticmethod
    def mock_notification_service():
        """خدمة إشعارات وهمية"""

        class MockNotificationService:
            def __init__(self):
                self.sent_notifications = []

            def send_notification(self, user, title, message, notification_type="info"):
                self.sent_notifications.append(
                    {
                        "user": user,
                        "title": title,
                        "message": message,
                        "type": notification_type,
                    }
                )
                return True

            def get_sent_notifications(self):
                return self.sent_notifications

            def clear_notifications(self):
                self.sent_notifications = []

        return MockNotificationService()

    @staticmethod
    def mock_email_service():
        """خدمة بريد إلكتروني وهمية"""

        class MockEmailService:
            def __init__(self):
                self.sent_emails = []

            def send_email(self, to_email, subject, message, from_email=None):
                self.sent_emails.append(
                    {
                        "to": to_email,
                        "subject": subject,
                        "message": message,
                        "from": from_email,
                    }
                )
                return True

            def get_sent_emails(self):
                return self.sent_emails

            def clear_emails(self):
                self.sent_emails = []

        return MockEmailService()


# دوال مساعدة للاختبارات
def skip_if_no_database(test_func):
    """تخطي الاختبار إذا لم تكن قاعدة البيانات متاحة"""

    def wrapper(*args, **kwargs):
        try:
            from django.db import connection

            connection.ensure_connection()
            return test_func(*args, **kwargs)
        except Exception:
            import unittest

            raise unittest.SkipTest("قاعدة البيانات غير متاحة")

    return wrapper


def with_test_data(scenario_func):
    """ديكوريتر لإعداد بيانات الاختبار"""

    def decorator(test_func):
        def wrapper(self, *args, **kwargs):
            # إعداد البيانات
            test_data = scenario_func()

            # تمرير البيانات للاختبار
            return test_func(self, test_data, *args, **kwargs)

        return wrapper

    return decorator
