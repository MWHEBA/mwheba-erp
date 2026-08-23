import pytest
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from core.models import SystemSetting

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

    def test_sales_orders_disabled_by_default_hides_from_sidebar_and_blocks_view(self):
        # التأكد من مسح أي إعداد مسبق
        SystemSetting.objects.filter(key="enable_sales_orders").delete()
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
        SystemSetting.set_setting("enable_sales_orders", "true", group="sales", data_type="boolean")
        SystemSetting.invalidate_all_system_caches()

        # 1. فحص ظهورها في الـ context processor
        resp = self.client.get("/")
        assert resp.context["enable_sales_orders"] is True
        assert reverse("sale:sales_order_list") in resp.content.decode("utf-8")

        # 2. فحص الدخول المباشر لصفحة قائمة أوامر البيع
        so_list_resp = self.client.get("/sales/orders/")
        assert so_list_resp.status_code == 200
        assert "ميزة أوامر البيع غير مفعلة" not in so_list_resp.content.decode("utf-8")
