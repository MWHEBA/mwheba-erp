import pytest
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from core.models import SystemSetting, SystemModule

User = get_user_model()

@pytest.mark.django_db
class TestSalesOrdersFeatureToggle(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_superuser(
            username="admin_so_test",
            email="admin_so@example.com",
            password="password123"
        )
        self.client.force_login(self.user)
        # Ensure base customer_sales module is enabled
        SystemModule.objects.update_or_create(
            code="customers_sales",
            defaults={"name_ar": "المبيعات", "is_enabled": True, "module_type": "optional"}
        )

    def test_sales_orders_disabled_hides_from_sidebar_and_blocks_view(self):
        SystemModule.objects.update_or_create(
            code="sales_orders",
            defaults={"name_ar": "أوامر البيع", "is_enabled": False, "module_type": "optional"}
        )
        SystemSetting.invalidate_all_system_caches()

        # 1. فحص ظهورها في الـ context processor
        resp = self.client.get("/")
        assert resp.context["enable_sales_orders"] is False
        assert reverse("sale:sales_order_list") not in resp.content.decode("utf-8")

        # 2. فحص محاولة الدخول المباشر لصفحة قائمة أوامر البيع
        so_list_resp = self.client.get("/sales/orders/")
        assert so_list_resp.status_code == 200
        assert "ميزة أوامر البيع غير مفعلة" in so_list_resp.content.decode("utf-8")

        # 3. فحص محاولة الدخول المباشر لصفحة إنشاء أمر بيع
        so_create_resp = self.client.get("/sales/orders/create/")
        assert so_create_resp.status_code == 200
        assert "ميزة أوامر البيع غير مفعلة" in so_create_resp.content.decode("utf-8")

    def test_sales_orders_enabled_shows_in_sidebar_and_allows_access(self):
        SystemModule.objects.update_or_create(
            code="sales_orders",
            defaults={"name_ar": "أوامر البيع", "is_enabled": True, "module_type": "optional"}
        )
        SystemSetting.invalidate_all_system_caches()

        # 1. فحص ظهورها في الـ context processor
        resp = self.client.get("/")
        assert resp.context["enable_sales_orders"] is True
        assert reverse("sale:sales_order_list") in resp.content.decode("utf-8")

        # 2. فحص الدخول المباشر لصفحة قائمة أوامر البيع
        so_list_resp = self.client.get("/sales/orders/")
        assert so_list_resp.status_code == 200
        assert "ميزة أوامر البيع غير مفعلة" not in so_list_resp.content.decode("utf-8")
