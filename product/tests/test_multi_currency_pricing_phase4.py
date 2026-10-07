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
def setup_phase4_data(db):
    user = User.objects.create_superuser(username="admin_phase4", password="password123", email="admin@test.com")
    egp = Currency.objects.create(code="EGP", name="Egyptian Pound", symbol="ج.م", is_functional=True, is_active=True)
    usd = Currency.objects.create(code="USD", name="US Dollar", symbol="$", is_functional=False, is_active=True)
    eur = Currency.objects.create(code="EUR", name="Euro", symbol="€", is_functional=False, is_active=True)
    cat = Category.objects.create(name="Phase 4 Category", code="CAT-P4")
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
def test_product_create_view_context_currencies(client, setup_phase4_data):
    data = setup_phase4_data
    client.force_login(data["user"])

    url = reverse("product:product_create")
    response = client.get(url)
    assert response.status_code == 200
    assert "active_currencies_list" in response.context
    assert "active_currencies_json" in response.context
    
    currencies = json.loads(response.context["active_currencies_json"])
    currency_codes = [c["code"] for c in currencies]
    assert "EGP" in currency_codes
    assert "USD" in currency_codes
    assert "EUR" in currency_codes

@pytest.mark.django_db
def test_product_create_post_with_usd_pricing(client, setup_phase4_data):
    data = setup_phase4_data
    client.force_login(data["user"])

    url = reverse("product:product_create")
    post_data = {
        "name": "Phase 4 USD Server",
        "category": data["cat"].id,
        "unit": data["unit"].id,
        "pricing_currency": data["usd"].id,
        "exchange_rate": "50.000000",
        "selling_price": "100.00",  # $100
        "cost_price": "80.00",      # $80
        "tax_code": data["tax"].id,
        "tax_rate": "14.00",
        "min_stock": "5",
        "is_active": "on",
    }
    response = client.post(url, data=post_data)
    assert response.status_code in [302, 200]

    product = Product.objects.get(name="Phase 4 USD Server")
    assert product.pricing_currency == data["usd"]
    assert product.is_foreign_currency_priced is True
    # In database, selling_price and cost_price are converted to EGP: 100 * 50 = 5000, 80 * 50 = 4000
    assert product.selling_price == Decimal("5000.00")
    assert product.cost_price == Decimal("4000.00")

    # In ProductCurrencyPrice, USD indicative prices are stored: $100 and $80
    cp = ProductCurrencyPrice.objects.get(product=product, currency=data["usd"])
    assert cp.indicative_selling_price == Decimal("100.00")
    assert cp.indicative_cost_price == Decimal("80.00")

@pytest.mark.django_db
def test_product_edit_hydrates_usd_price_in_form(client, setup_phase4_data):
    data = setup_phase4_data
    client.force_login(data["user"])

    # Create product directly with USD
    product = Product.objects.create(
        name="Hydration Test Product",
        category=data["cat"],
        unit=data["unit"],
        pricing_currency=data["usd"],
        selling_price=Decimal("7500.00"),  # $150 * 50
        cost_price=Decimal("5000.00"),     # $100 * 50
        created_by=data["user"],
    )
    ProductCurrencyPrice.objects.create(
        product=product,
        currency=data["usd"],
        indicative_selling_price=Decimal("150.00"),
        indicative_cost_price=Decimal("100.00"),
    )

    url = reverse("product:product_edit", kwargs={"pk": product.pk})
    response = client.get(url)
    assert response.status_code == 200
    form = response.context["form"]
    # Hydrated selling_price in form should be $150, not 7500 EGP
    assert form.initial["selling_price"] == Decimal("150.00")
    assert form.initial["cost_price"] == Decimal("100.00")
    assert form.fields["pricing_currency"].initial == data["usd"]

@pytest.mark.django_db
def test_product_create_modal_ajax_with_usd(client, setup_phase4_data):
    data = setup_phase4_data
    client.force_login(data["user"])

    url = reverse("product:product_create_modal")
    post_data = {
        "name": "Modal USD Product",
        "category": data["cat"].id,
        "unit": data["unit"].id,
        "pricing_currency": data["usd"].id,
        "exchange_rate": "50.000000",
        "selling_price": "200.00",
        "cost_price": "150.00",
        "is_active": "on",
    }
    response = client.post(url, data=post_data, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True

    product = Product.objects.get(name="Modal USD Product")
    assert product.pricing_currency == data["usd"]
    assert product.is_foreign_currency_priced is True
    assert product.selling_price == Decimal("10000.00")
