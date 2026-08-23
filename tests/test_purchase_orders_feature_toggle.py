import pytest
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from core.models import SystemSetting
from supplier.models import Supplier

User = get_user_model()

@pytest.mark.django_db
class TestPurchaseOrdersFeatureToggle(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_superuser(
            username="admin_po_test",
            email="admin_po@example.com",
            password="password123"
        )
        self.client.force_login(self.user)
        self.supplier = Supplier.objects.create(name="مورد تجريبي", code="SUP-PO-01")

    def test_purchase_orders_disabled_by_default_hides_from_sidebar_and_supplier_and_blocks_view(self):
        # التأكد من مسح أي إعداد مسبق
        SystemSetting.objects.filter(key="enable_purchase_orders").delete()
        SystemSetting.invalidate_all_system_caches()

        # 1. فحص ظهورها في الـ context processor
        resp = self.client.get("/")
        assert resp.context["enable_purchase_orders"] is False
        assert reverse("purchase:po_list") not in resp.content.decode("utf-8")

        # 2. فحص صفحة المورد - يجب ألا يظهر تبويب أوامر الشراء
        sup_url = reverse("supplier:supplier_detail", kwargs={"pk": self.supplier.pk})
        sup_resp = self.client.get(sup_url)
        assert sup_resp.status_code == 200
        assert "po-tab" not in sup_resp.content.decode("utf-8")

        # 3. فحص محاولة الدخول المباشر لصفحة قائمة أوامر الشراء
        po_list_resp = self.client.get("/purchases/orders/")
        assert po_list_resp.status_code == 200
        assert "ميزة أوامر الشراء غير مفعلة" in po_list_resp.content.decode("utf-8")

        # 4. فحص محاولة الدخول المباشر لصفحة إنشاء أمر شراء
        po_create_resp = self.client.get("/purchases/orders/create/")
        assert po_create_resp.status_code == 200
        assert "ميزة أوامر الشراء غير مفعلة" in po_create_resp.content.decode("utf-8")

    def test_purchase_orders_enabled_shows_in_sidebar_and_supplier_and_allows_access(self):
        SystemSetting.set_setting("enable_purchase_orders", "true", group="sales", data_type="boolean")
        SystemSetting.invalidate_all_system_caches()

        # 1. فحص ظهورها في الـ context processor
        resp = self.client.get("/")
        assert resp.context["enable_purchase_orders"] is True
        assert reverse("purchase:po_list") in resp.content.decode("utf-8")

        # 2. فحص صفحة المورد - يجب أن يظهر تبويب أوامر الشراء
        sup_url = reverse("supplier:supplier_detail", kwargs={"pk": self.supplier.pk})
        sup_resp = self.client.get(sup_url)
        assert sup_resp.status_code == 200
        assert "po-tab" in sup_resp.content.decode("utf-8")

        # 3. فحص الدخول المباشر لصفحة قائمة أوامر الشراء
        po_list_resp = self.client.get("/purchases/orders/")
        assert po_list_resp.status_code == 200
        assert "ميزة أوامر الشراء غير مفعلة" not in po_list_resp.content.decode("utf-8")
