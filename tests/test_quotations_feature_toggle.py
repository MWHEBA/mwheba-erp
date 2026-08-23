import pytest
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from core.models import SystemSetting

User = get_user_model()

@pytest.mark.django_db
class TestQuotationsFeatureToggle(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_superuser(
            username="admin_quote_test",
            email="admin_quote@example.com",
            password="password123"
        )
        self.client.force_login(self.user)

    def test_quotations_disabled_by_default_hides_from_sidebar_and_blocks_view(self):
        # التأكد من مسح أي إعداد مسبق
        SystemSetting.objects.filter(key="enable_quotations").delete()
        SystemSetting.invalidate_all_system_caches()

        # 1. فحص ظهورها في الـ context processor
        resp = self.client.get("/")
        assert resp.context["enable_quotations"] is False
        assert reverse("sale:quotation_list") not in resp.content.decode("utf-8")

        # 2. فحص محاولة الدخول المباشر للصفحة
        quote_resp = self.client.get("/sales/quotations/")
        assert quote_resp.status_code == 200
        assert "ميزة عروض الأسعار غير مفعلة" in quote_resp.content.decode("utf-8")

    def test_quotations_enabled_shows_in_sidebar_and_allows_access(self):
        SystemSetting.set_setting("enable_quotations", "true", group="sales", data_type="boolean")
        SystemSetting.invalidate_all_system_caches()

        # 1. فحص ظهورها في الـ context processor
        resp = self.client.get("/")
        assert resp.context["enable_quotations"] is True
        assert "عروض الأسعار" in resp.content.decode("utf-8")

        # 2. فحص الدخول المباشر للصفحة
        quote_resp = self.client.get("/sales/quotations/")
        assert quote_resp.status_code == 200
        assert "ميزة عروض الأسعار غير مفعلة" not in quote_resp.content.decode("utf-8")
