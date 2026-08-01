"""
اختبارات وظائف عرض المبيعات (بدون تخطي اختبارات)
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal

from sale.models import Sale, SaleItem, SaleReturn
from client.models import Customer
from product.models import Category, Unit, Product, Warehouse

User = get_user_model()


class SaleViewsTest(TestCase):
    """
    اختبارات وظائف عرض المبيعات
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser_sale_views", password="testpass123", email="test@example.com"
        )
        self.client.login(username="testuser_sale_views", password="testpass123")

        self.customer = Customer.objects.create(
            name="عميل المبيعات", code="CUST_SALE_V1", phone="01234567890"
        )

        self.warehouse = Warehouse.objects.create(
            name="المخزن الرئيسي", code="WH_SALE_V1"
        )

        self.category = Category.objects.create(name="فئة اختبار")
        self.unit = Unit.objects.create(name="قطعة", symbol="قطعة")

        self.product1 = Product.objects.create(
            name="منتج اختبار 1",
            sku="TEST_V001",
            category=self.category,
            unit=self.unit,
            cost_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
            created_by=self.user
        )

        self.product2 = Product.objects.create(
            name="منتج اختبار 2",
            sku="TEST_V002",
            category=self.category,
            unit=self.unit,
            cost_price=Decimal("200.00"),
            selling_price=Decimal("300.00"),
            created_by=self.user
        )

        self.sale = Sale.objects.create(
            number="SL-001-V",
            date=timezone.now().date(),
            customer=self.customer,
            warehouse=self.warehouse,
            status="confirmed",
            payment_status="paid",
            subtotal=Decimal("1650.00"),
            total=Decimal("1650.00"),
            payment_method="cash",
            created_by=self.user,
        )

        self.sale_item1 = SaleItem.objects.create(
            sale=self.sale,
            product=self.product1,
            quantity=Decimal("5.00"),
            unit_price=Decimal("150.00")
        )

    def test_sale_list_view(self):
        """اختبار صفحة قائمة المبيعات"""
        url = reverse("sale:sale_list")
        response = self.client.get(url)
        self.assertIn(response.status_code, [200, 302])

    def test_sale_detail_view(self):
        """اختبار صفحة تفاصيل المبيعات"""
        url = reverse("sale:sale_detail", kwargs={"pk": self.sale.pk})
        response = self.client.get(url)
        self.assertIn(response.status_code, [200, 302])

    def test_sale_create_view(self):
        """اختبار صفحة إنشاء مبيعات جديدة"""
        url = reverse("sale:sale_create")
        response = self.client.get(url)
        self.assertIn(response.status_code, [200, 302])


class SaleReturnViewsTest(TestCase):
    """
    اختبارات وظائف عرض مرتجعات المبيعات
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser_return_views", password="testpass123"
        )
        self.client.login(username="testuser_return_views", password="testpass123")

        self.customer = Customer.objects.create(
            name="عميل المرتجعات", code="CUST_RET_V1"
        )

        self.warehouse = Warehouse.objects.create(
            name="المخزن الرئيسي", code="WH_RET_V1"
        )

        self.sale = Sale.objects.create(
            number="SL-002-RET",
            date=timezone.now().date(),
            customer=self.customer,
            warehouse=self.warehouse,
            status="confirmed",
            payment_status="paid",
            subtotal=Decimal("500.00"),
            total=Decimal("500.00"),
            payment_method="cash",
            created_by=self.user,
        )

        self.sale_return = SaleReturn.objects.create(
            sale=self.sale,
            warehouse=self.warehouse,
            number="RET-001-V",
            date=timezone.now().date(),
            subtotal=Decimal("500.00"),
            total=Decimal("500.00"),
            status="draft",
            created_by=self.user
        )

    def test_sale_return_list_view(self):
        """اختبار صفحة قائمة مرتجعات المبيعات"""
        url = reverse("sale:sale_return_list")
        response = self.client.get(url)
        self.assertIn(response.status_code, [200, 302])

    def test_sale_return_detail_view(self):
        """اختبار صفحة تفاصيل مرتجع المبيعات"""
        url = reverse("sale:sale_return_detail", kwargs={"pk": self.sale_return.pk})
        response = self.client.get(url)
        self.assertIn(response.status_code, [200, 302])
