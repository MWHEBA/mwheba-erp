# -*- coding: utf-8 -*-
import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from product.models import Warehouse, Product, Category, Stock, Unit

User = get_user_model()

@pytest.mark.django_db
class TestStockListView:
    """اختبارات صفحة وعرض جرد المخزون المركزي"""

    @pytest.fixture
    def user(self):
        user = User.objects.create_user(username="wh_manager", password="password123")
        perm = Permission.objects.get(codename="view_product", content_type__app_label="product")
        user.user_permissions.add(perm)
        return user

    @pytest.fixture
    def setup_stock_data(self, user):
        Stock.objects.all().delete()
        warehouse = Warehouse.objects.create(name="المخزن الرئيسي", code="WH001")
        category = Category.objects.create(name="إلكترونيات")
        unit = Unit.objects.create(name="قطعة", symbol="PCS")
        
        product1 = Product.objects.create(
            name="منتج أ",
            sku="SKU-001",
            category=category,
            unit=unit,
            cost_price=100,
            selling_price=150,
            min_stock=10,
            created_by=user,
        )
        product2 = Product.objects.create(
            name="منتج ب",
            sku="SKU-002",
            category=category,
            unit=unit,
            cost_price=200,
            selling_price=280,
            min_stock=5,
            created_by=user,
        )

        stock1 = Stock.objects.create(warehouse=warehouse, product=product1, quantity=25)
        stock2 = Stock.objects.create(warehouse=warehouse, product=product2, quantity=3)  # low stock

        return warehouse, category, [stock1, stock2]

    def test_stock_list_get(self, client, user, setup_stock_data):
        client.force_login(user)
        response = client.get(reverse("product:stock_list"))
        assert response.status_code == 200
        assert "stocks" in response.context
        assert "stats" in response.context
        assert response.context["stats"]["total_records"] == 2
        assert response.context["stats"]["low_stock_count"] == 1
        assert response.context["stats"]["total_units"] == 28

    def test_stock_list_filter_status(self, client, user, setup_stock_data):
        client.force_login(user)
        response = client.get(reverse("product:stock_list") + "?stock_status=low_stock")
        assert response.status_code == 200
        stocks = list(response.context["stocks"])
        assert len(stocks) == 1
        assert stocks[0].product.sku == "SKU-002"

    def test_stock_list_ajax_search(self, client, user, setup_stock_data):
        client.force_login(user)
        response = client.get(
            reverse("product:stock_list") + "?search=SKU-001",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        assert response.status_code == 200
        data = response.json()
        assert "table_html" in data
        assert "pagination_html" in data
        assert "stats_html" in data
        assert "SKU-001" in data["table_html"]
        assert "SKU-002" not in data["table_html"]

    def test_product_detail_view(self, client, user, setup_stock_data):
        warehouse, category, stocks = setup_stock_data
        product = stocks[0].product
        client.force_login(user)
        response = client.get(reverse("product:product_detail", kwargs={"pk": product.pk}))
        assert response.status_code == 200
        assert "product" in response.context
        assert response.context["product"] == product

