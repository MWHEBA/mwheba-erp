"""
اختبارات شاملة لواجهات نظام التسعير
Comprehensive Tests for Pricing System Views
"""
import pytest
from django.test import TestCase, Client as TestClient
from django.urls import reverse
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from decimal import Decimal
from datetime import date

from pricing.models import (
    PricingOrder,
    PaperType,
    PaperSize,
    PlateSize,
    CoatingType,
    FinishingType,
    PrintDirection,
)
from client.models import Client
from supplier.models import Supplier


class PricingViewsTestCase(TestCase):
    """اختبارات واجهات نظام التسعير"""

    def setUp(self):
        """إعداد البيانات للاختبارات"""
        # إنشاء مستخدم للاختبار
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        # إنشاء عميل للاختبار
        self.client_obj = Client.objects.create(
            name="عميل تجريبي", email="client@test.com", phone="01234567890"
        )

        # إنشاء مورد للاختبار
        self.supplier = Supplier.objects.create(
            name="مورد تجريبي", email="supplier@test.com", phone="01234567890"
        )

        # إنشاء البيانات المرجعية
        self.paper_type = PaperType.objects.create(
            name="ورق أبيض", description="ورق أبيض عادي"
        )

        self.paper_size = PaperSize.objects.create(name="A4", width=21.0, height=29.7)

        # إنشاء طلب تسعير للاختبار
        self.pricing_order = PricingOrder.objects.create(
            client=self.client_obj,
            product_name="كتالوج شركة",
            quantity=1000,
            created_by=self.user,
        )

        # إنشاء عميل HTTP للاختبار
        self.client = TestClient()

    def test_pricing_dashboard_view(self):
        """اختبار صفحة لوحة التحكم"""
        self.client.login(username="testuser", password="testpass123")

        url = reverse("pricing:pricing_dashboard")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "لوحة تحكم التسعير")

    def test_pricing_order_list_view(self):
        """اختبار صفحة قائمة طلبات التسعير"""
        self.client.login(username="testuser", password="testpass123")

        url = reverse("pricing:pricing_order_list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "طلبات التسعير")
        self.assertContains(response, self.pricing_order.product_name)

    def test_pricing_order_create_view_get(self):
        """اختبار صفحة إنشاء طلب تسعير - GET"""
        self.client.login(username="testuser", password="testpass123")

        url = reverse("pricing:pricing_order_create")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "إنشاء طلب تسعير جديد")

    def test_pricing_order_create_view_post(self):
        """اختبار صفحة إنشاء طلب تسعير - POST"""
        self.client.login(username="testuser", password="testpass123")

        url = reverse("pricing:pricing_order_create")
        data = {
            "client": self.client_obj.id,
            "product_name": "كتالوج جديد",
            "quantity": 500,
            "paper_type": self.paper_type.id,
            "paper_size": self.paper_size.id,
            "description": "وصف الطلب",
        }

        response = self.client.post(url, data)

        # التحقق من إنشاء الطلب
        self.assertTrue(
            PricingOrder.objects.filter(product_name="كتالوج جديد").exists()
        )

        # التحقق من إعادة التوجيه
        self.assertEqual(response.status_code, 302)

    def test_pricing_order_detail_view(self):
        """اختبار صفحة تفاصيل طلب التسعير"""
        self.client.login(username="testuser", password="testpass123")

        url = reverse("pricing:pricing_detail", kwargs={"pk": self.pricing_order.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.pricing_order.product_name)
        self.assertContains(response, str(self.pricing_order.quantity))

    def test_pricing_order_edit_view_get(self):
        """اختبار صفحة تعديل طلب التسعير - GET"""
        self.client.login(username="testuser", password="testpass123")

        url = reverse("pricing:pricing_edit", kwargs={"pk": self.pricing_order.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "تعديل طلب التسعير")

    def test_pricing_order_edit_view_post(self):
        """اختبار صفحة تعديل طلب التسعير - POST"""
        self.client.login(username="testuser", password="testpass123")

        url = reverse("pricing:pricing_edit", kwargs={"pk": self.pricing_order.pk})
        data = {
            "client": self.client_obj.id,
            "product_name": "كتالوج محدث",
            "quantity": 1500,
            "description": "وصف محدث",
        }

        response = self.client.post(url, data)

        # التحقق من تحديث الطلب
        updated_order = PricingOrder.objects.get(pk=self.pricing_order.pk)
        self.assertEqual(updated_order.product_name, "كتالوج محدث")
        self.assertEqual(updated_order.quantity, 1500)

    def test_pricing_order_delete_view_get(self):
        """اختبار صفحة حذف طلب التسعير - GET"""
        self.client.login(username="testuser", password="testpass123")

        url = reverse("pricing:pricing_delete", kwargs={"pk": self.pricing_order.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "تأكيد الحذف")

    def test_pricing_order_delete_view_post(self):
        """اختبار صفحة حذف طلب التسعير - POST"""
        self.client.login(username="testuser", password="testpass123")

        order_id = self.pricing_order.pk
        url = reverse("pricing:pricing_delete", kwargs={"pk": order_id})

        response = self.client.post(url)

        # التحقق من حذف الطلب
        self.assertFalse(PricingOrder.objects.filter(pk=order_id).exists())

        # التحقق من إعادة التوجيه
        self.assertEqual(response.status_code, 302)

    def test_pricing_order_pdf_view(self):
        """اختبار تصدير طلب التسعير كـ PDF"""
        self.client.login(username="testuser", password="testpass123")

        url = reverse("pricing:pricing_pdf", kwargs={"pk": self.pricing_order.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_unauthorized_access(self):
        """اختبار الوصول غير المصرح به"""
        # محاولة الوصول بدون تسجيل دخول
        url = reverse("pricing:pricing_dashboard")
        response = self.client.get(url)

        # يجب إعادة التوجيه لصفحة تسجيل الدخول
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_pricing_form_validation(self):
        """اختبار التحقق من صحة نموذج التسعير"""
        self.client.login(username="testuser", password="testpass123")

        url = reverse("pricing:pricing_order_create")

        # بيانات غير صحيحة (كمية سالبة)
        data = {
            "client": self.client_obj.id,
            "product_name": "كتالوج",
            "quantity": -100,  # كمية سالبة
        }

        response = self.client.post(url, data)

        # يجب أن تبقى في نفس الصفحة مع رسالة خطأ
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "خطأ")


class PricingAPIViewsTestCase(TestCase):
    """اختبارات APIs نظام التسعير"""

    def setUp(self):
        """إعداد البيانات للاختبارات"""
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )

        self.client = TestClient()
        self.client.login(username="testuser", password="testpass123")

        # إنشاء البيانات المرجعية
        self.paper_type = PaperType.objects.create(name="ورق أبيض", weight=80)

        self.paper_size = PaperSize.objects.create(name="A4", width=21.0, height=29.7)

        self.plate_size = PlateSize.objects.create(
            name="70x100", width=70.0, height=100.0, price=Decimal("200.00")
        )

    def test_get_paper_price_api(self):
        """اختبار API جلب سعر الورق"""
        url = reverse("pricing:get_paper_price")
        data = {
            "paper_type": self.paper_type.id,
            "paper_size": self.paper_size.id,
            "quantity": 1000,
        }

        response = self.client.get(url, data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

    def test_get_plate_price_api(self):
        """اختبار API جلب سعر الزنك"""
        url = reverse("pricing:get_plate_price")
        data = {"plate_size": self.plate_size.id, "colors": 4}

        response = self.client.get(url, data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

    def test_calculate_cost_api(self):
        """اختبار API حساب التكلفة"""
        url = reverse("pricing:calculate_cost")
        data = {
            "paper_type": self.paper_type.id,
            "paper_size": self.paper_size.id,
            "quantity": 1000,
            "colors": 4,
        }

        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

    def test_api_authentication_required(self):
        """اختبار أن APIs تتطلب تسجيل دخول"""
        # تسجيل خروج
        self.client.logout()

        url = reverse("pricing:get_paper_price")
        response = self.client.get(url)

        # يجب إعادة التوجيه أو رفض الطلب
        self.assertIn(response.status_code, [302, 401, 403])


class PricingSettingsViewsTestCase(TestCase):
    """اختبارات واجهات إعدادات التسعير"""

    def setUp(self):
        """إعداد البيانات للاختبارات"""
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )

        self.client = TestClient()
        self.client.login(username="testuser", password="testpass123")

    def test_paper_type_list_view(self):
        """اختبار صفحة قائمة أنواع الورق"""
        url = reverse("pricing:paper_type_list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "أنواع الورق")

    def test_paper_type_create_view(self):
        """اختبار صفحة إنشاء نوع ورق جديد"""
        url = reverse("pricing:paper_type_create")
        data = {"name": "ورق مقوى", "description": "ورق مقوى للأغلفة", "weight": 300}

        response = self.client.post(url, data)

        # التحقق من إنشاء النوع
        self.assertTrue(PaperType.objects.filter(name="ورق مقوى").exists())

    def test_paper_size_list_view(self):
        """اختبار صفحة قائمة مقاسات الورق"""
        url = reverse("pricing:paper_size_list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "مقاسات الورق")

    def test_coating_type_list_view(self):
        """اختبار صفحة قائمة أنواع الطلاء"""
        url = reverse("pricing:coating_type_list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "أنواع الطلاء")


class PricingWorkflowTestCase(TestCase):
    """اختبارات سير العمل في نظام التسعير"""

    def setUp(self):
        """إعداد البيانات للاختبارات"""
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )

        self.client_obj = Client.objects.create(
            name="عميل تجريبي", email="client@test.com"
        )

        self.client = TestClient()
        self.client.login(username="testuser", password="testpass123")

    def test_complete_pricing_workflow(self):
        """اختبار سير العمل الكامل للتسعير"""
        # 1. إنشاء طلب تسعير
        create_url = reverse("pricing:pricing_order_create")
        create_data = {
            "client": self.client_obj.id,
            "product_name": "كتالوج شركة",
            "quantity": 1000,
            "description": "كتالوج تعريفي للشركة",
        }

        response = self.client.post(create_url, create_data)
        self.assertEqual(response.status_code, 302)

        # التحقق من إنشاء الطلب
        order = PricingOrder.objects.get(product_name="كتالوج شركة")
        self.assertEqual(order.status, "draft")

        # 2. عرض تفاصيل الطلب
        detail_url = reverse("pricing:pricing_detail", kwargs={"pk": order.pk})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)

        # 3. تعديل الطلب
        edit_url = reverse("pricing:pricing_edit", kwargs={"pk": order.pk})
        edit_data = {
            "client": self.client_obj.id,
            "product_name": "كتالوج شركة محدث",
            "quantity": 1500,
            "description": "كتالوج تعريفي محدث",
        }

        response = self.client.post(edit_url, edit_data)
        self.assertEqual(response.status_code, 302)

        # التحقق من التحديث
        order.refresh_from_db()
        self.assertEqual(order.product_name, "كتالوج شركة محدث")
        self.assertEqual(order.quantity, 1500)


if __name__ == "__main__":
    pytest.main([__file__])
