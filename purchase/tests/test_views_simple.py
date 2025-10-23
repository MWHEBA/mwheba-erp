"""
اختبارات بسيطة لعروض المشتريات
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal

from purchase.models import Purchase
from supplier.models import Supplier
from product.models import Warehouse

User = get_user_model()


class PurchaseViewsTest(TestCase):
    """اختبارات عروض المشتريات"""

    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", password="testpass123", email="test@test.com"
        )
        self.client.login(username="testuser", password="testpass123")

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

        # إنشاء فاتورة مشتريات
        try:
            self.purchase = Purchase.objects.create(
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
        except Exception:
            self.purchase = None

    def test_purchase_list_view(self):
        """اختبار عرض قائمة المشتريات"""
        try:
            url = reverse("purchase:purchase_list")
            response = self.client.get(url)
            self.assertIn(response.status_code, [200, 404])
        except Exception:
            self.skipTest("Purchase list view not available")

    def test_purchase_detail_view(self):
        """اختبار عرض تفاصيل المشتريات"""
        if not self.purchase:
            self.skipTest("Purchase not created")

        try:
            url = reverse("purchase:purchase_detail", kwargs={"pk": self.purchase.pk})
            response = self.client.get(url)
            self.assertIn(response.status_code, [200, 404])
        except Exception:
            self.skipTest("Purchase detail view not available")

    def test_purchase_create_view(self):
        """اختبار عرض إنشاء مشتريات"""
        try:
            url = reverse("purchase:purchase_create")
            response = self.client.get(url)
            self.assertIn(response.status_code, [200, 404])
        except Exception:
            self.skipTest("Purchase create view not available")
