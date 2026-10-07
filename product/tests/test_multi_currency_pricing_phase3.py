# -*- coding: utf-8 -*-
from decimal import Decimal
import json
import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from product.models import Product, Category, Unit, ProductCurrencyPrice, PriceHistory
from product.views.invoice_lookup import invoice_product_lookup
from product.views.price_manager_views import price_manager_bulk_update_api
from product.services.product_import_service import ProductImportService
from financial.models import Currency, ExchangeRate

User = get_user_model()


@pytest.fixture
def test_setup_phase3(db):
    user = User.objects.create_superuser(username="admin_fx_p3", password="password123", email="admin@example.com")
    egp = Currency.objects.create(code="EGP", name="Egyptian Pound", symbol="ج.م", is_functional=True, is_active=True)
    usd = Currency.objects.create(code="USD", name="US Dollar", symbol="$", is_functional=False, is_active=True)
    
    ExchangeRate.objects.create(from_currency=usd, to_currency=egp, rate=Decimal("50.000000"), effective_date="2026-01-01")

    category = Category.objects.create(name="أجهزة كمبيوتر", code="COM")
    unit = Unit.objects.create(name="قطعة", symbol="قطعة")

    return {
        "user": user,
        "egp": egp,
        "usd": usd,
        "category": category,
        "unit": unit,
    }


@pytest.mark.django_db
def test_invoice_lookup_foreign_and_dynamic_fx(test_setup_phase3):
    """اختبار البحث في الفواتير بالدولار وبالجنيه مع الحساب الديناميكي لسعر الصرف"""
    setup = test_setup_phase3
    product = Product.objects.create(
        name="لابتوب ديل",
        sku="COM-001",
        category=setup["category"],
        unit=setup["unit"],
        pricing_currency=setup["usd"],
        cost_price=Decimal("25000.00"),     # 500 * 50
        selling_price=Decimal("35000.00"),  # 700 * 50
        created_by=setup["user"],
    )
    ProductCurrencyPrice.objects.create(
        product=product,
        currency=setup["usd"],
        indicative_cost_price=Decimal("500.00"),    # $500
        indicative_selling_price=Decimal("700.00"), # $700
        created_by=setup["user"],
    )

    factory = RequestFactory()

    # 1. البحث في فاتورة مبيعات بالدولار
    req_usd = factory.get(f"/products/api/invoice-lookup/?q=لابتوب&currency_id={setup['usd'].id}&type=sale&show_all=true")
    req_usd.user = setup["user"]
    resp_usd = invoice_product_lookup(req_usd)
    assert resp_usd.status_code == 200
    data_usd = json.loads(resp_usd.content)
    assert len(data_usd["products"]) == 1
    item_usd = data_usd["products"][0]
    assert item_usd["selling_price"] == 700.00
    assert item_usd["has_currency_price"] is True
    assert item_usd["pricing_currency_code"] == "USD"
    assert item_usd["is_foreign_currency_priced"] is True

    # 2. البحث في فاتورة مبيعات بالجنيه ولكن بسعر صرف متغير (مثلاً تحرك سعر الصرف إلى 52.00)
    req_egp = factory.get(f"/products/api/invoice-lookup/?q=لابتوب&currency_id={setup['egp'].id}&exchange_rate=52.000000&type=sale&show_all=true")
    req_egp.user = setup["user"]
    resp_egp = invoice_product_lookup(req_egp)
    assert resp_egp.status_code == 200
    data_egp = json.loads(resp_egp.content)
    assert len(data_egp["products"]) == 1
    item_egp = data_egp["products"][0]
    # 700 * 52 = 36400.00
    assert item_egp["selling_price"] == 36400.00
    assert item_egp["pricing_currency_code"] == "USD"
    assert item_egp["is_foreign_currency_priced"] is True


@pytest.mark.django_db
def test_price_manager_bulk_update_syncs_foreign_currency(test_setup_phase3):
    """اختبار التحديث الجماعي في مدير الأسعار وتزامن السعر الأجنبي والمعادل بالجنيه"""
    setup = test_setup_phase3
    product = Product.objects.create(
        name="شاشة عرض",
        sku="COM-002",
        category=setup["category"],
        unit=setup["unit"],
        pricing_currency=setup["usd"],
        cost_price=Decimal("5000.00"),     # 100 * 50
        selling_price=Decimal("10000.00"), # 200 * 50
        created_by=setup["user"],
    )
    cp = ProductCurrencyPrice.objects.create(
        product=product,
        currency=setup["usd"],
        indicative_cost_price=Decimal("100.00"),    # $100
        indicative_selling_price=Decimal("200.00"), # $200
        created_by=setup["user"],
    )

    factory = RequestFactory()
    # تطبيق زيادة جماعية بنسبة 10% على سعر البيع
    payload = {
        "ids": [product.id],
        "field": "selling_price",
        "mode": "percent_increase",
        "value": "10",
    }
    request = factory.post(
        "/products/api/price-manager/bulk-update/",
        data=json.dumps(payload),
        content_type="application/json"
    )
    request.user = setup["user"]
    response = price_manager_bulk_update_api(request)
    assert response.status_code == 200
    res_data = json.loads(response.content)
    assert res_data["success"] is True
    assert res_data["updated"] == 1

    # التحقق من أن السعر بالدولار أصبح 220 ($200 + 10%)
    cp.refresh_from_db()
    assert cp.indicative_selling_price == Decimal("220.00")

    # التحقق من أن معادل الجنيه أصبح 11000 ج.م (220 * 50)
    product.refresh_from_db()
    assert product.selling_price == Decimal("11000.00")

    # التحقق من تسجيل PriceHistory
    history = PriceHistory.objects.filter(product=product, source_type="CATALOG_FX").first()
    assert history is not None
    assert history.new_price == Decimal("11000.00")


@pytest.mark.django_db
def test_product_import_service_with_pricing_currency(test_setup_phase3):
    """اختبار استيراد المنتجات بالعملة الأجنبية عبر ProductImportService"""
    setup = test_setup_phase3
    service = ProductImportService(user=setup["user"])

    row_data = {
        "name": "طابعة ليزر مستوردة",
        "category": setup["category"].name,
        "unit": setup["unit"].name,
        "pricing_currency": "USD",
        "cost_price": "200.00",      # $200
        "selling_price": "300.00",   # $300
        "tax_rate": "14.00",
        "is_active": "1",
    }

    res = service._process_row(row_num=2, row=row_data, update_existing=False)
    assert res["error"] is None

    product = Product.objects.filter(name="طابعة ليزر مستوردة").first()
    assert product is not None
    assert product.pricing_currency == setup["usd"]
    assert product.is_foreign_currency_priced is True
    # 200 * 50 = 10,000 ج.م
    assert product.cost_price == Decimal("10000.00")
    # 300 * 50 = 15,000 ج.م
    assert product.selling_price == Decimal("15000.00")

    cp = ProductCurrencyPrice.objects.filter(product=product, currency=setup["usd"]).first()
    assert cp is not None
    assert cp.indicative_cost_price == Decimal("200.00")
    assert cp.indicative_selling_price == Decimal("300.00")
