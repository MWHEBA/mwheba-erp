"""
اختبارات الواجهات والـ APIs لنظام المخزن المحسن
"""
import json
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
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
    ExpiryAlert,
    SupplierProductPrice,
    PriceHistory,
)
from supplier.models import Supplier

User = get_user_model()


class ProductViewsTestCase(TestCase):
    """اختبارات واجهات المنتجات"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        # تسجيل الدخول
        self.client.login(username="testuser", password="testpass123")

        # إنشاء البيانات الأساسية
        self.category = Category.objects.create(name="إلكترونيات")
        self.brand = Brand.objects.create(name="سامسونج")
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
            created_by=self.user,
        )

    def test_product_list_view(self):
        """اختبار صفحة قائمة المنتجات"""
        url = reverse("product:product_list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product.name)
        self.assertContains(response, self.product.sku)

    def test_product_detail_view(self):
        """اختبار صفحة تفاصيل المنتج"""
        url = reverse("product:product_detail", kwargs={"pk": self.product.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product.name)
        self.assertContains(response, self.product.sku)
        self.assertContains(response, str(self.product.selling_price))

    def test_product_create_view(self):
        """اختبار إنشاء منتج جديد"""
        url = reverse("product:product_create")

        # GET request
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # POST request
        data = {
            "name": "منتج جديد",
            "sku": "NEW001",
            "category": self.category.id,
            "brand": self.brand.id,
            "unit": self.unit.id,
            "cost_price": "300.00",
            "selling_price": "450.00",
            "min_stock": "5",
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)  # Redirect after success

        # التحقق من إنشاء المنتج
        new_product = Product.objects.get(sku="NEW001")
        self.assertEqual(new_product.name, "منتج جديد")
        self.assertEqual(new_product.cost_price, Decimal("300.00"))

    def test_product_edit_view(self):
        """اختبار تعديل المنتج"""
        url = reverse("product:product_edit", kwargs={"pk": self.product.pk})

        # GET request
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # POST request
        data = {
            "name": "هاتف ذكي محدث",
            "sku": self.product.sku,
            "category": self.category.id,
            "brand": self.brand.id,
            "unit": self.unit.id,
            "cost_price": "520.00",
            "selling_price": "780.00",
            "min_stock": "8",
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

        # التحقق من التحديث
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, "هاتف ذكي محدث")
        self.assertEqual(self.product.cost_price, Decimal("520.00"))


class InventoryAPITestCase(TestCase):
    """اختبارات APIs المخزون"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="apiuser", email="api@example.com", password="apipass123"
        )

        self.client.login(username="apiuser", password="apipass123")

        # إنشاء البيانات الأساسية
        self.category = Category.objects.create(name="API تست")
        self.brand = Brand.objects.create(name="علامة API")
        self.unit = Unit.objects.create(name="قطعة", symbol="قطعة")

        self.warehouse = Warehouse.objects.create(
            name="مخزن API", code="API", location="اختبار", manager=self.user
        )

        self.product = Product.objects.create(
            name="منتج API",
            sku="API001",
            category=self.category,
            brand=self.brand,
            unit=self.unit,
            cost_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
            created_by=self.user,
        )

        self.stock = ProductStock.objects.create(
            product=self.product, warehouse=self.warehouse, quantity=100
        )

    def test_get_stock_by_warehouse_api(self):
        """اختبار API الحصول على المخزون حسب المخزن"""
        url = reverse("product:get_stock_by_warehouse")

        response = self.client.get(
            url, {"warehouse_id": self.warehouse.id, "product_id": self.product.id}
        )

        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data["quantity"], 100)
        self.assertEqual(data["available_quantity"], 100)

    def test_create_reservation_api(self):
        """اختبار API إنشاء حجز"""
        url = reverse("product:create_reservation_api")

        data = {
            "product_id": self.product.id,
            "warehouse_id": self.warehouse.id,
            "quantity": 30,
            "reference_number": "ORDER001",
            "expiry_hours": 24,
        }

        response = self.client.post(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)

        response_data = json.loads(response.content)
        self.assertTrue(response_data["success"])

        # التحقق من إنشاء الحجز
        reservation = StockReservation.objects.get(
            product=self.product, reference_number="ORDER001"
        )
        self.assertEqual(reservation.quantity, 30)

        # التحقق من تحديث المخزون المحجوز
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.reserved_quantity, 30)


class SupplierPricingAPITestCase(TestCase):
    """اختبارات APIs تسعير الموردين"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="pricinguser",
            email="pricing@example.com",
            password="pricingpass123",
        )

        self.client.login(username="pricinguser", password="pricingpass123")

        # إنشاء البيانات الأساسية
        self.category = Category.objects.create(name="تسعير")
        self.brand = Brand.objects.create(name="علامة التسعير")
        self.unit = Unit.objects.create(name="قطعة", symbol="قطعة")

        self.product = Product.objects.create(
            name="منتج التسعير",
            sku="PRICING001",
            category=self.category,
            brand=self.brand,
            unit=self.unit,
            cost_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
            created_by=self.user,
        )

        self.supplier = Supplier.objects.create(
            name="مورد الاختبار", email="supplier@example.com", phone="123456789"
        )

    def test_add_supplier_price_api(self):
        """اختبار API إضافة سعر مورد"""
        url = reverse("product:add_supplier_price_api")

        data = {
            "product_id": self.product.id,
            "supplier_id": self.supplier.id,
            "cost_price": "95.00",
            "is_default": True,
        }

        response = self.client.post(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)

        response_data = json.loads(response.content)
        self.assertTrue(response_data["success"])

        # التحقق من إنشاء السعر
        supplier_price = SupplierProductPrice.objects.get(
            product=self.product, supplier=self.supplier
        )
        self.assertEqual(supplier_price.cost_price, Decimal("95.00"))
        self.assertTrue(supplier_price.is_default)

    def test_edit_supplier_price_api(self):
        """اختبار API تعديل سعر مورد"""
        # إنشاء سعر أولي
        supplier_price = SupplierProductPrice.objects.create(
            product=self.product,
            supplier=self.supplier,
            cost_price=Decimal("100.00"),
            created_by=self.user,
        )

        url = reverse(
            "product:edit_supplier_price_api", kwargs={"pk": supplier_price.pk}
        )

        data = {"cost_price": "92.00"}

        response = self.client.post(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)

        response_data = json.loads(response.content)
        self.assertTrue(response_data["success"])

        # التحقق من التحديث
        supplier_price.refresh_from_db()
        self.assertEqual(supplier_price.cost_price, Decimal("92.00"))

        # التحقق من تسجيل التاريخ
        history = PriceHistory.objects.filter(
            supplier_product_price=supplier_price
        ).first()
        self.assertIsNotNone(history)
        self.assertEqual(history.old_price, Decimal("100.00"))
        self.assertEqual(history.new_price, Decimal("92.00"))

    def test_set_default_supplier_api(self):
        """اختبار API تعيين مورد افتراضي"""
        # إنشاء أسعار لموردين
        supplier_price1 = SupplierProductPrice.objects.create(
            product=self.product,
            supplier=self.supplier,
            cost_price=Decimal("100.00"),
            is_default=True,
            created_by=self.user,
        )

        # إنشاء مورد ثاني
        supplier2 = Supplier.objects.create(
            name="مورد ثاني",
            email="supplier2@example.com",
            phone="987654321",
            code="SUP003",
        )

        supplier_price2 = SupplierProductPrice.objects.create(
            product=self.product,
            supplier=supplier2,
            cost_price=Decimal("95.00"),
            created_by=self.user,
        )

        url = reverse(
            "product:set_default_supplier_api", kwargs={"pk": supplier_price2.pk}
        )

        response = self.client.post(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)

        response_data = json.loads(response.content)
        self.assertTrue(response_data["success"])

        # التحقق من التحديث
        supplier_price1.refresh_from_db()
        supplier_price2.refresh_from_db()
        self.product.refresh_from_db()

        self.assertFalse(supplier_price1.is_default)
        self.assertTrue(supplier_price2.is_default)
        self.assertEqual(self.product.default_supplier, supplier2)

    def test_supplier_price_history_api(self):
        """اختبار API تاريخ أسعار المورد"""
        # إنشاء سعر مع تاريخ
        supplier_price = SupplierProductPrice.objects.create(
            product=self.product,
            supplier=self.supplier,
            cost_price=Decimal("100.00"),
            created_by=self.user,
        )

        # إنشاء تاريخ تغيير
        PriceHistory.objects.create(
            supplier_product_price=supplier_price,
            old_price=Decimal("105.00"),
            new_price=Decimal("100.00"),
            change_reason="purchase",
            changed_by=self.user,
        )

        url = reverse(
            "product:supplier_price_history_api", kwargs={"pk": supplier_price.pk}
        )

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        response_data = json.loads(response.content)
        self.assertTrue(response_data["success"])

        # التحقق من وجود تاريخ الأسعار
        self.assertIn("data", response_data)
        self.assertIn("history", response_data["data"])
        self.assertEqual(len(response_data["data"]["history"]), 1)

        history_item = response_data["data"]["history"][0]
        self.assertEqual(history_item["old_price"], 105.0)
        self.assertEqual(history_item["new_price"], 100.0)
        self.assertEqual(history_item["change_reason"], "شراء جديد")

    def test_product_price_comparison_api(self):
        """اختبار API مقارنة أسعار المنتج"""
        # إنشاء أسعار متعددة
        SupplierProductPrice.objects.create(
            product=self.product,
            supplier=self.supplier,
            cost_price=Decimal("100.00"),
            is_default=True,
            created_by=self.user,
        )

        # إنشاء مورد ثاني
        supplier2 = Supplier.objects.create(
            name="مورد ثاني",
            email="supplier2@example.com",
            phone="987654321",
            code="SUP002",
        )

        SupplierProductPrice.objects.create(
            product=self.product,
            supplier=supplier2,
            cost_price=Decimal("95.00"),
            created_by=self.user,
        )

        url = reverse(
            "product:product_price_comparison_api",
            kwargs={"product_id": self.product.id},
        )

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        response_data = json.loads(response.content)

        # إذا فشل API، تحقق من الخطأ
        if not response_data.get("success", False):
            print(f"API Error: {response_data}")

        self.assertTrue(response_data.get("success", False))

        comparison = response_data.get("comparison", response_data.get("data", {}))
        self.assertGreaterEqual(len(comparison.get("prices", [])), 1)

        # التحقق من وجود البيانات الأساسية
        self.assertIn("product", comparison)
        if comparison.get("lowest_price"):
            self.assertIsNotNone(comparison["lowest_price"])


class ExpirySystemTestCase(TestCase):
    """اختبارات نظام انتهاء الصلاحية"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="expiryuser", email="expiry@example.com", password="expirypass123"
        )

        self.client.login(username="expiryuser", password="expirypass123")

        # إنشاء البيانات الأساسية
        self.category = Category.objects.create(name="انتهاء صلاحية")
        self.brand = Brand.objects.create(name="علامة الصلاحية")
        self.unit = Unit.objects.create(name="قطعة", symbol="قطعة")

        self.warehouse = Warehouse.objects.create(
            name="مخزن الصلاحية", code="EXPIRY", location="اختبار", manager=self.user
        )

        self.product = Product.objects.create(
            name="منتج قابل للانتهاء",
            sku="EXPIRY001",
            category=self.category,
            brand=self.brand,
            unit=self.unit,
            cost_price=Decimal("50.00"),
            selling_price=Decimal("75.00"),
            created_by=self.user,
        )

    def test_expiry_dashboard_view(self):
        """اختبار لوحة تحكم انتهاء الصلاحية"""
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

        url = reverse("product:expiry_dashboard")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "NEAREXP001")
        self.assertContains(response, "EXPIRED001")

    def test_acknowledge_expiry_alert_api(self):
        """اختبار API تأكيد تنبيه انتهاء الصلاحية"""
        # إنشاء دفعة ونتبيه
        batch = ProductBatch.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            batch_number="ALERT001",
            production_date=date.today() - timedelta(days=350),
            expiry_date=date.today() + timedelta(days=15),
            received_date=date.today(),
            initial_quantity=30,
            current_quantity=30,
            reserved_quantity=0,
            unit_cost=Decimal("10.00"),
            total_cost=Decimal("300.00"),
            status="active",
            created_by=self.user,
        )

        alert = ExpiryAlert.objects.create(
            batch=batch,
            alert_type="near_expiry",
            days_to_expiry=15,
            created_by=self.user,
        )

        url = reverse("product:acknowledge_expiry_alert_api")

        data = {"alert_id": alert.id}

        response = self.client.post(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)

        response_data = json.loads(response.content)
        self.assertTrue(response_data["success"])

        # التحقق من تأكيد التنبيه
        alert.refresh_from_db()
        self.assertTrue(alert.is_acknowledged)
        self.assertEqual(alert.acknowledged_by, self.user)


class ReservationSystemTestCase(TestCase):
    """اختبارات نظام الحجوزات"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="reservationuser",
            email="reservation@example.com",
            password="reservationpass123",
        )

        self.client.login(username="reservationuser", password="reservationpass123")

        # إنشاء البيانات الأساسية
        self.category = Category.objects.create(name="حجوزات")
        self.brand = Brand.objects.create(name="علامة الحجز")
        self.unit = Unit.objects.create(name="قطعة", symbol="قطعة")

        self.warehouse = Warehouse.objects.create(
            name="مخزن الحجوزات", code="RESERVE", location="اختبار", manager=self.user
        )

        self.product = Product.objects.create(
            name="منتج قابل للحجز",
            sku="RESERVE001",
            category=self.category,
            brand=self.brand,
            unit=self.unit,
            cost_price=Decimal("200.00"),
            selling_price=Decimal("300.00"),
            created_by=self.user,
        )

        self.stock = ProductStock.objects.create(
            product=self.product, warehouse=self.warehouse, quantity=100
        )

    def test_reservation_dashboard_view(self):
        """اختبار لوحة تحكم الحجوزات"""
        # إنشاء حجوزات مختلفة
        StockReservation.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity_reserved=30,
            reference_number="ORDER001",
            expires_at=timezone.now() + timedelta(hours=24),
            reserved_by=self.user,
            reservation_type="manual",
            status="active",
        )

        StockReservation.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity_reserved=20,
            reference_number="ORDER002",
            expires_at=timezone.now() - timedelta(hours=1),  # منتهي الصلاحية
            reserved_by=self.user,
            reservation_type="manual",
            status="expired",
        )

        url = reverse("product:reservation_dashboard")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ORDER001")
        self.assertContains(response, "ORDER002")

    def test_reservation_list_view(self):
        """اختبار قائمة الحجوزات"""
        # إنشاء حجز
        reservation = StockReservation.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity_reserved=25,
            reference_number="ORDER003",
            expires_at=timezone.now() + timedelta(hours=48),
            reserved_by=self.user,
            reservation_type="manual",
            status="active",
        )

        url = reverse("product:reservation_list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ORDER003")
        self.assertContains(response, str(reservation.quantity))


class ErrorHandlingTestCase(TestCase):
    """اختبارات معالجة الأخطاء"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="erroruser", email="error@example.com", password="errorpass123"
        )

        self.client.login(username="erroruser", password="errorpass123")

    def test_invalid_product_id_api(self):
        """اختبار API مع معرف منتج غير صحيح"""
        url = reverse("product:get_stock_by_warehouse")

        response = self.client.get(
            url,
            {
                "warehouse_id": 999,  # معرف غير موجود
                "product_id": 999,  # معرف غير موجود
            },
        )

        self.assertEqual(response.status_code, 404)

    def test_insufficient_stock_reservation(self):
        """اختبار حجز كمية أكبر من المتاح"""
        # إنشاء منتج ومخزون محدود
        category = Category.objects.create(name="اختبار خطأ")
        brand = Brand.objects.create(name="علامة خطأ")
        unit = Unit.objects.create(name="قطعة", symbol="قطعة")

        warehouse = Warehouse.objects.create(
            name="مخزن الخطأ", code="ERROR", location="اختبار", manager=self.user
        )

        product = Product.objects.create(
            name="منتج محدود",
            sku="LIMITED001",
            category=category,
            brand=brand,
            unit=unit,
            cost_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
            created_by=self.user,
        )

        ProductStock.objects.create(
            product=product, warehouse=warehouse, quantity=10  # كمية محدودة
        )

        url = reverse("product:create_reservation_api")

        data = {
            "product_id": product.id,
            "warehouse_id": warehouse.id,
            "quantity": 20,  # أكبر من المتاح
            "reserved_for": "ORDER_ERROR",
            "expiry_hours": 24,
        }

        response = self.client.post(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 400)

        response_data = json.loads(response.content)
        self.assertFalse(response_data["success"])
        self.assertIn("insufficient_stock", response_data["error"])

    def test_unauthorized_access(self):
        """اختبار الوصول غير المصرح به"""
        # تسجيل الخروج
        self.client.logout()

        # محاولة الوصول لصفحة محمية
        url = reverse("product:product_create")
        response = self.client.get(url)

        # يجب إعادة التوجيه لصفحة تسجيل الدخول
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)


# إعداد تشغيل الاختبارات
if __name__ == "__main__":
    import django
    from django.conf import settings
    from django.test.utils import get_runner

    django.setup()
    TestRunner = get_runner(settings)
    test_runner = TestRunner()
    failures = test_runner.run_tests(["product.tests.test_views_and_apis"])
