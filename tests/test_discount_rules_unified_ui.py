import pytest
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from sale.models.pricing import DiscountRule
from customer.models import Customer
from product.models.product_core import Category

User = get_user_model()

@pytest.mark.django_db
class TestDiscountRulesUnifiedUI(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_superuser(
            username="admin_discount_test",
            email="admin_disc@example.com",
            password="password123"
        )
        self.client.force_login(self.user)
        self.customer = Customer.objects.create(name="عميل مميز", code="CUST-DISC-01")
        self.category = Category.objects.create(name="إلكترونيات")

        self.rule1 = DiscountRule.objects.create(
            rule_name="خصم ترويجي 15%",
            rule_type="PERCENTAGE",
            customer=self.customer,
            category=self.category,
            discount_percentage=Decimal("15.00"),
            min_order_amount=Decimal("1000.00"),
            priority=1,
            is_active=True
        )
        self.rule2 = DiscountRule.objects.create(
            rule_name="خصم نقدي 50 جنيه",
            rule_type="FIXED_AMOUNT",
            value=Decimal("50.00"),
            priority=5,
            is_active=False
        )

    def test_discount_rule_list_view(self):
        url = reverse("sale:discount_rule_list")
        resp = self.client.get(url)
        assert resp.status_code == 200
        assert "خصم ترويجي 15%" in resp.content.decode("utf-8")
        assert "خصم نقدي 50 جنيه" in resp.content.decode("utf-8")
        assert "stats" in resp.context
        assert resp.context["stats"]["total_count"] == 2
        assert resp.context["stats"]["active_count"] == 1

    def test_discount_rule_ajax_search(self):
        url = reverse("sale:discount_rule_list")
        resp = self.client.get(url, {"q": "ترويجي", "ajax": "1"}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert resp.status_code == 200
        data = resp.json()
        assert "table_html" in data
        assert "خصم ترويجي 15%" in data["table_html"]
        assert "خصم نقدي 50 جنيه" not in data["table_html"]

    def test_discount_rule_create_view(self):
        url = reverse("sale:discount_rule_create")
        resp = self.client.get(url)
        assert resp.status_code == 200

        post_data = {
            "rule_name": "خصم VIP 20%",
            "rule_type": "PERCENTAGE",
            "customer": self.customer.id,
            "discount_percentage": "20.00",
            "priority": "2",
            "effective_date": "2026-08-23",
            "is_active": "on"
        }
        create_resp = self.client.post(url, post_data)
        assert create_resp.status_code == 302
        assert DiscountRule.objects.filter(rule_name="خصم VIP 20%").exists()

    def test_discount_rule_edit_view(self):
        url = reverse("sale:discount_rule_edit", kwargs={"pk": self.rule1.pk})
        resp = self.client.get(url)
        assert resp.status_code == 200

        post_data = {
            "rule_name": "خصم ترويجي معدل 25%",
            "rule_type": "PERCENTAGE",
            "discount_percentage": "25.00",
            "priority": "1",
            "effective_date": "2026-08-23",
            "is_active": "on"
        }
        edit_resp = self.client.post(url, post_data)
        assert edit_resp.status_code == 302
        self.rule1.refresh_from_db()
        assert self.rule1.rule_name == "خصم ترويجي معدل 25%"
        assert self.rule1.discount_percentage == Decimal("25.00")

    def test_discount_rule_toggle_status(self):
        url = reverse("sale:discount_rule_toggle", kwargs={"pk": self.rule1.pk})
        resp = self.client.post(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["is_active"] is False

        self.rule1.refresh_from_db()
        assert self.rule1.is_active is False

    def test_discount_rule_delete(self):
        url = reverse("sale:discount_rule_delete", kwargs={"pk": self.rule2.pk})
        resp = self.client.post(url)
        assert resp.status_code == 302
        assert not DiscountRule.objects.filter(pk=self.rule2.pk).exists()
