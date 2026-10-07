# -*- coding: utf-8 -*-
import pytest
import json
from decimal import Decimal
from django.urls import reverse
from django.contrib.auth import get_user_model
from product.models import Product, Category, Unit
from product.models.product_currency_price import ProductCurrencyPrice
from financial.models.currency import Currency
from financial.models.tax import TaxCode

User = get_user_model()

@pytest.fixture
def setup_phase5_data(db):
    user = User.objects.create_superuser(username="admin_phase5", password="password123", email="admin5@test.com")
    egp = Currency.objects.create(code="EGP", name="Egyptian Pound", symbol="ج.م", is_functional=True, is_active=True)
    usd = Currency.objects.create(code="USD", name="US Dollar", symbol="$", is_functional=False, is_active=True)
    eur = Currency.objects.create(code="EUR", name="Euro", symbol="€", is_functional=False, is_active=True)
    cat = Category.objects.create(name="Phase 5 Category", code="CAT-P5")
    unit = Unit.objects.create(name="Piece", symbol="Pcs")
    tax = TaxCode.objects.create(code="T1", name="VAT 14%", rate=Decimal("14.00"), tax_type="VAT", is_active=True, is_default=True)
    
    return {
        "user": user,
        "egp": egp,
        "usd": usd,
        "eur": eur,
        "cat": cat,
        "unit": unit,
        "tax": tax,
    }

@pytest.mark.django_db
def test_ajax_get_form_data_includes_currencies(client, setup_phase5_data):
    data = setup_phase5_data
    client.force_login(data["user"])

    url = reverse("purchase:ajax_form_data")
    response = client.get(url)
    assert response.status_code == 200
    res_data = response.json()
    assert "currencies" in res_data
    currencies = res_data["currencies"]
    codes = [c["code"] for c in currencies]
    assert "EGP" in codes
    assert "USD" in codes
    assert "EUR" in codes

@pytest.mark.django_db
def test_ajax_create_product_with_foreign_currency(client, setup_phase5_data):
    data = setup_phase5_data
    client.force_login(data["user"])

    url = reverse("purchase:ajax_create_product")
    post_data = {
        "name": "Quick USD Laptop",
        "category": data["cat"].id,
        "unit": data["unit"].id,
        "currency_id": data["usd"].id,
        "exchange_rate": "50.000000",
        "cost_price": "800.00",    # $800
        "selling_price": "1000.00", # $1000
        "tax_rate": "14.00",
        "is_service": "false",
    }
    response = client.post(url, data=post_data)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    product_data = res_data["product"]

    # Verify returned JSON metadata
    assert product_data["pricing_currency_id"] == data["usd"].id
    assert product_data["pricing_currency_code"] == "USD"
    assert product_data["is_foreign_currency_priced"] is True
    assert product_data["indicative_cost_price"] == 800.0
    assert product_data["indicative_selling_price"] == 1000.0

    # Verify Database records
    product = Product.objects.get(id=product_data["id"])
    assert product.pricing_currency == data["usd"]
    assert product.is_foreign_currency_priced is True
    assert product.selling_price == Decimal("50000.00") # $1000 * 50
    assert product.cost_price == Decimal("40000.00")    # $800 * 50

    # Verify ProductCurrencyPrice
    cp = ProductCurrencyPrice.objects.get(product=product, currency=data["usd"])
    assert cp.indicative_cost_price == Decimal("800.00")
    assert cp.indicative_selling_price == Decimal("1000.00")

@pytest.mark.django_db
def test_ajax_create_service_with_foreign_currency(client, setup_phase5_data):
    data = setup_phase5_data
    client.force_login(data["user"])

    url = reverse("purchase:ajax_create_product")
    post_data = {
        "name": "Quick EUR Cloud Hosting",
        "category": data["cat"].id,
        "currency_id": data["eur"].id,
        "exchange_rate": "55.000000",
        "cost_price": "50.00",     # €50
        "selling_price": "70.00",   # €70
        "tax_rate": "14.00",
        "is_service": "true",
    }
    response = client.post(url, data=post_data)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    product_data = res_data["product"]

    product = Product.objects.get(id=product_data["id"])
    assert product.is_service is True
    assert product.pricing_currency == data["eur"]
    assert product.is_foreign_currency_priced is True
    assert product.selling_price == Decimal("3850.00") # €70 * 55
    assert product.cost_price == Decimal("2750.00")    # €50 * 55

@pytest.mark.django_db
def test_product_create_modal_saves_and_returns_currency_pricing(client, setup_phase5_data):
    data = setup_phase5_data
    client.force_login(data["user"])

    url = reverse("product:product_create_modal")
    post_data = {
        "name": "Modal Multi-Currency Item",
        "category": data["cat"].id,
        "unit": data["unit"].id,
        "pricing_currency": data["usd"].id,
        "exchange_rate": "50.000000",
        "cost_price": "120.00",
        "selling_price": "180.00",
        "tax_code": data["tax"].id,
        "tax_rate": "14.00",
        "is_active": "on",
    }
    response = client.post(url, data=post_data, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True

    product = Product.objects.get(name="Modal Multi-Currency Item")
    assert product.pricing_currency == data["usd"]
    assert product.is_foreign_currency_priced is True
    assert product.selling_price == Decimal("9000.00")  # 180 * 50
    assert product.cost_price == Decimal("6000.00")     # 120 * 50
