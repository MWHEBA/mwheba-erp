"""
اختبارات بسيطة لنماذج المشتريات
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal

from purchase.models import Purchase, PurchaseItem
from supplier.models import Supplier
from product.models import Product, Category, Unit, Warehouse, Brand

User = get_user_model()


class PurchaseModelTest(TestCase):
    """اختبارات نموذج المشتريات"""

    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.user = User.objects.create_user(
            username="testuser", password="testpass123", email="test@test.com"
        )

        # إنشاء مورد
        self.supplier = Supplier.objects.create(
            name="مورد الاختبار",
            phone="01234567890",
            created_by=self.user,
        )

        # إنشاء مخزن
        self.warehouse = Warehouse.objects.create(
            name="المخزن الرئيسي",
            location="موقع المخزن",
            created_by=self.user,
        )

        # إنشاء منتج
        self.category = Category.objects.create(name="فئة اختبار")
        self.unit = Unit.objects.create(name="قطعة")
        self.brand = Brand.objects.create(name="علامة تجارية", created_by=self.user)

        self.product = Product.objects.create(
            name="منتج اختبار",
            sku="TEST001",
            category=self.category,
            unit=self.unit,
            brand=self.brand,
            cost_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
            created_by=self.user,
        )

    def test_purchase_creation(self):
        """اختبار إنشاء فاتورة مشتريات"""
        purchase = Purchase.objects.create(
            supplier=self.supplier,
            warehouse=self.warehouse,
            date=timezone.now().date(),
            number="PUR-001",
            status="draft",
            payment_method="cash",
            subtotal=Decimal("1000.00"),
            tax=Decimal("150.00"),
            total=Decimal("1150.00"),
            created_by=self.user,
        )

        self.assertEqual(purchase.supplier, self.supplier)
        self.assertEqual(purchase.status, "draft")
        self.assertEqual(purchase.total, Decimal("1150.00"))

    def test_purchase_item_creation(self):
        """اختبار إنشاء بند فاتورة مشتريات"""
        purchase = Purchase.objects.create(
            supplier=self.supplier,
            warehouse=self.warehouse,
            date=timezone.now().date(),
            number="PUR-002",
            status="draft",
            payment_method="cash",
            subtotal=Decimal("500.00"),
            tax=Decimal("75.00"),
            total=Decimal("575.00"),
            created_by=self.user,
        )

        item = PurchaseItem.objects.create(
            purchase=purchase,
            product=self.product,
            quantity=10,
            unit_price=Decimal("50.00"),
            total=Decimal("500.00"),
        )

        self.assertEqual(item.quantity, 10)
        self.assertEqual(item.total, Decimal("500.00"))
        self.assertEqual(purchase.items.count(), 1)
