"""
اختبارات شاملة لـ APIs نظام التسعير
Comprehensive Tests for Pricing System APIs
"""
import pytest
import json
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from decimal import Decimal
from unittest.mock import patch, Mock

from pricing.models import (
    PricingOrder,
    PaperType,
    PaperSize,
    PlateSize,
    CoatingType,
    FinishingType,
    PrintDirection,
)
from client.models import Client as ClientModel
from supplier.models import Supplier


class PricingAPITestCase(TestCase):
    """اختبارات APIs نظام التسعير"""

    def setUp(self):
        """إعداد البيانات للاختبارات"""
        # إنشاء مستخدم للاختبار
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        # إنشاء عميل للاختبار
        self.client_obj = ClientModel.objects.create(
            name="عميل تجريبي", email="client@test.com", phone="01234567890"
        )

        # إنشاء مورد للاختبار
        self.supplier = Supplier.objects.create(
            name="مورد تجريبي", email="supplier@test.com", phone="01234567890"
        )

        # إنشاء البيانات المرجعية
        self.paper_type = PaperType.objects.create(
            name="ورق أبيض", weight=80, price_per_kg=Decimal("15.00")
        )

        self.paper_size = PaperSize.objects.create(name="A4", width=21.0, height=29.7)

        self.plate_size = PlateSize.objects.create(
            name="70x100", width=70.0, height=100.0, price=Decimal("200.00")
        )

        self.coating_type = CoatingType.objects.create(
            name="لامينيشن لامع", price_per_sheet=Decimal("0.25")
        )

        self.finishing_type = FinishingType.objects.create(
            name="تجليد حلزوني", price_per_unit=Decimal("2.00")
        )

        # إنشاء عميل HTTP للاختبار
        self.client = Client()
        self.client.login(username="testuser", password="testpass123")

    def test_calculate_cost_api(self):
        """اختبار API حساب التكلفة"""
        url = reverse("pricing:calculate_cost")
        data = {
            "paper_type": self.paper_type.id,
            "paper_size": self.paper_size.id,
            "quantity": 1000,
            "colors": 4,
            "finishing_required": True,
        }

        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

        response_data = json.loads(response.content)
        self.assertIn("success", response_data)
        self.assertIn("total_cost", response_data)
        self.assertIn("paper_cost", response_data)
        self.assertIn("printing_cost", response_data)

    def test_get_paper_price_api(self):
        """اختبار API جلب سعر الورق"""
        url = reverse("pricing:get_paper_price")
        data = {
            "paper_type": self.paper_type.id,
            "paper_size": self.paper_size.id,
            "quantity": 1000,
            "weight": 80,
        }

        response = self.client.get(url, data)

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)

        self.assertIn("success", response_data)
        self.assertIn("price", response_data)
        self.assertIn("weight", response_data)

    def test_get_plate_price_api(self):
        """اختبار API جلب سعر الزنك"""
        url = reverse("pricing:get_plate_price")
        data = {"plate_size": self.plate_size.id, "colors": 4}

        response = self.client.get(url, data)

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)

        self.assertIn("success", response_data)
        self.assertIn("total_price", response_data)
        self.assertIn("price_per_plate", response_data)

    def test_get_paper_sizes_api(self):
        """اختبار API جلب مقاسات الورق"""
        url = reverse("pricing:get_paper_sizes")

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)

        self.assertIn("success", response_data)
        self.assertIn("sizes", response_data)
        self.assertIsInstance(response_data["sizes"], list)

    def test_get_paper_weights_api(self):
        """اختبار API جلب أوزان الورق"""
        url = reverse("pricing:get_paper_weights")
        data = {"paper_type": self.paper_type.id}

        response = self.client.get(url, data)

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)

        self.assertIn("success", response_data)
        self.assertIn("weights", response_data)

    def test_get_suppliers_by_service_api(self):
        """اختبار API جلب الموردين حسب الخدمة"""
        url = reverse("pricing:get_suppliers_by_service")
        data = {"service_type": "printing"}

        response = self.client.get(url, data)

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)

        self.assertIn("success", response_data)
        self.assertIn("suppliers", response_data)

    def test_coating_services_api(self):
        """اختبار API خدمات الطلاء"""
        url = reverse("pricing:coating_services_api")

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)

        self.assertIn("success", response_data)
        self.assertIn("services", response_data)

    def test_folding_services_api(self):
        """اختبار API خدمات الطي"""
        url = reverse("pricing:folding_services_api")

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)

        self.assertIn("success", response_data)
        self.assertIn("services", response_data)

    def test_die_cut_services_api(self):
        """اختبار API خدمات القص"""
        url = reverse("pricing:die_cut_services_api")

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)

        self.assertIn("success", response_data)
        self.assertIn("services", response_data)


class PricingAPIErrorHandlingTestCase(TestCase):
    """اختبارات معالجة الأخطاء في APIs"""

    def setUp(self):
        """إعداد البيانات للاختبارات"""
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )

        self.client = Client()
        self.client.login(username="testuser", password="testpass123")

    def test_calculate_cost_api_missing_data(self):
        """اختبار API حساب التكلفة مع بيانات ناقصة"""
        url = reverse("pricing:calculate_cost")
        data = {
            "quantity": 1000
            # بيانات ناقصة - لا يوجد paper_type أو paper_size
        }

        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 400)
        response_data = json.loads(response.content)

        self.assertIn("success", response_data)
        self.assertFalse(response_data["success"])
        self.assertIn("error", response_data)

    def test_get_paper_price_api_invalid_data(self):
        """اختبار API جلب سعر الورق مع بيانات غير صحيحة"""
        url = reverse("pricing:get_paper_price")
        data = {
            "paper_type": 999,  # ID غير موجود
            "paper_size": 999,  # ID غير موجود
            "quantity": -100,  # كمية سالبة
        }

        response = self.client.get(url, data)

        self.assertEqual(response.status_code, 400)
        response_data = json.loads(response.content)

        self.assertFalse(response_data["success"])
        self.assertIn("error", response_data)

    def test_api_authentication_required(self):
        """اختبار أن APIs تتطلب تسجيل دخول"""
        # تسجيل خروج
        self.client.logout()

        url = reverse("pricing:calculate_cost")
        data = {"quantity": 1000}

        response = self.client.post(url, data)

        # يجب إعادة التوجيه أو رفض الطلب
        self.assertIn(response.status_code, [302, 401, 403])


class PricingAPIPerformanceTestCase(TestCase):
    """اختبارات الأداء لـ APIs نظام التسعير"""

    def setUp(self):
        """إعداد البيانات للاختبارات"""
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )

        self.paper_type = PaperType.objects.create(
            name="ورق أبيض", weight=80, price_per_kg=Decimal("15.00")
        )

        self.paper_size = PaperSize.objects.create(name="A4", width=21.0, height=29.7)

        self.client = Client()
        self.client.login(username="testuser", password="testpass123")

    def test_calculate_cost_api_performance(self):
        """اختبار أداء API حساب التكلفة"""
        url = reverse("pricing:calculate_cost")
        data = {
            "paper_type": self.paper_type.id,
            "paper_size": self.paper_size.id,
            "quantity": 100000,  # كمية كبيرة
            "colors": 4,
        }

        import time

        start_time = time.time()

        response = self.client.post(url, data)

        end_time = time.time()
        response_time = end_time - start_time

        # يجب أن يكون الرد سريعاً (أقل من 2 ثانية)
        self.assertLess(response_time, 2.0)
        self.assertEqual(response.status_code, 200)

    def test_multiple_api_calls_performance(self):
        """اختبار أداء استدعاءات متعددة للـ API"""
        url = reverse("pricing:get_paper_price")
        data = {
            "paper_type": self.paper_type.id,
            "paper_size": self.paper_size.id,
            "quantity": 1000,
        }

        import time

        start_time = time.time()

        # استدعاء API عدة مرات
        for _ in range(10):
            response = self.client.get(url, data)
            self.assertEqual(response.status_code, 200)

        end_time = time.time()
        total_time = end_time - start_time

        # يجب أن تكون جميع الاستدعاءات سريعة (أقل من 5 ثوان)
        self.assertLess(total_time, 5.0)


class EnhancedPricingAPITestCase(TestCase):
    """اختبارات APIs التسعير المحسنة"""

    def setUp(self):
        """إعداد البيانات للاختبارات"""
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )

        self.paper_type = PaperType.objects.create(
            name="ورق أبيض", weight=80, price_per_kg=Decimal("15.00")
        )

        self.client = Client()
        self.client.login(username="testuser", password="testpass123")

    def test_enhanced_paper_price_api(self):
        """اختبار API سعر الورق المحسن"""
        url = reverse("pricing:enhanced_paper_price_api")
        data = {
            "paper_type": self.paper_type.id,
            "quantity": 1000,
            "supplier_preference": "cheapest",
        }

        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)

        self.assertIn("success", response_data)
        self.assertIn("price_details", response_data)

    def test_enhanced_total_cost_api(self):
        """اختبار API التكلفة الإجمالية المحسنة"""
        url = reverse("pricing:enhanced_total_cost_api")
        data = {
            "paper_type": self.paper_type.id,
            "quantity": 1000,
            "colors": 4,
            "finishing_options": ["lamination", "binding"],
            "profit_margin": 20,
        }

        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)

        self.assertIn("success", response_data)
        self.assertIn("cost_breakdown", response_data)
        self.assertIn("total_cost", response_data)
        self.assertIn("selling_price", response_data)

    def test_enhanced_suppliers_by_service_api(self):
        """اختبار API الموردين حسب الخدمة المحسن"""
        url = reverse("pricing:enhanced_suppliers_by_service_api")
        data = {
            "service_type": "printing",
            "location_preference": "nearby",
            "quality_rating_min": 4,
        }

        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)

        self.assertIn("success", response_data)
        self.assertIn("suppliers", response_data)


class PricingAPIIntegrationTestCase(TestCase):
    """اختبارات التكامل بين APIs نظام التسعير"""

    def setUp(self):
        """إعداد البيانات للاختبارات"""
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )

        self.client_obj = ClientModel.objects.create(
            name="عميل تجريبي", email="client@test.com"
        )

        self.paper_type = PaperType.objects.create(
            name="ورق أبيض", weight=80, price_per_kg=Decimal("15.00")
        )

        self.paper_size = PaperSize.objects.create(name="A4", width=21.0, height=29.7)

        self.client = Client()
        self.client.login(username="testuser", password="testpass123")

    def test_complete_pricing_workflow_via_apis(self):
        """اختبار سير العمل الكامل للتسعير عبر APIs"""
        # 1. جلب أنواع الورق
        paper_types_url = reverse("pricing:get_paper_types")
        response = self.client.get(paper_types_url)
        self.assertEqual(response.status_code, 200)

        # 2. جلب مقاسات الورق
        paper_sizes_url = reverse("pricing:get_paper_sizes")
        response = self.client.get(paper_sizes_url)
        self.assertEqual(response.status_code, 200)

        # 3. حساب سعر الورق
        paper_price_url = reverse("pricing:get_paper_price")
        paper_data = {
            "paper_type": self.paper_type.id,
            "paper_size": self.paper_size.id,
            "quantity": 1000,
        }
        response = self.client.get(paper_price_url, paper_data)
        self.assertEqual(response.status_code, 200)

        # 4. حساب التكلفة الإجمالية
        cost_url = reverse("pricing:calculate_cost")
        cost_data = {
            "paper_type": self.paper_type.id,
            "paper_size": self.paper_size.id,
            "quantity": 1000,
            "colors": 4,
        }
        response = self.client.post(cost_url, cost_data)
        self.assertEqual(response.status_code, 200)

        response_data = json.loads(response.content)
        self.assertTrue(response_data["success"])
        self.assertIn("total_cost", response_data)


class PricingAPIMockTestCase(TestCase):
    """اختبارات APIs مع محاكاة الخدمات الخارجية"""

    def setUp(self):
        """إعداد البيانات للاختبارات"""
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )

        self.client = Client()
        self.client.login(username="testuser", password="testpass123")

    @patch("pricing.services.calculator.PricingCalculator.calculate_total_cost")
    def test_calculate_cost_api_with_mock(self, mock_calculate):
        """اختبار API حساب التكلفة مع محاكاة الخدمة"""
        # إعداد المحاكاة
        mock_calculate.return_value = Decimal("1500.00")

        url = reverse("pricing:calculate_cost")
        data = {
            "quantity": 1000,
            "paper_cost": 500,
            "printing_cost": 300,
            "finishing_cost": 200,
        }

        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)

        # التحقق من استدعاء الدالة المحاكاة
        mock_calculate.assert_called_once()

        # التحقق من النتيجة
        self.assertTrue(response_data["success"])
        self.assertEqual(response_data["total_cost"], "1500.00")


if __name__ == "__main__":
    pytest.main([__file__])
