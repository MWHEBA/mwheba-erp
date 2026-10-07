# -*- coding: utf-8 -*-
from decimal import Decimal
import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.urls import reverse

from product.models import Product, Category, Unit, ProductCurrencyPrice, PriceHistory
from product.forms import ProductForm
from product.views.main_views import update_currency_prices
from financial.models import Currency, ExchangeRate
from supplier.models import Supplier
from purchase.models import Purchase, PurchaseItem
from api.serializers import ProductListSerializer, ProductDetailSerializer

User = get_user_model()


@pytest.fixture
def test_setup(db):
    user = User.objects.create_user(username="test_fx_user", password="password123", is_staff=True)
    egp = Currency.objects.create(code="EGP", name="Egyptian Pound", symbol="ج.م", is_functional=True, is_active=True)
    usd = Currency.objects.create(code="USD", name="US Dollar", symbol="$", is_functional=False, is_active=True)
    eur = Currency.objects.create(code="EUR", name="Euro", symbol="€", is_functional=False, is_active=True)
    
    ExchangeRate.objects.create(from_currency=usd, to_currency=egp, rate=Decimal("50.000000"), effective_date="2026-01-01")
    ExchangeRate.objects.create(from_currency=eur, to_currency=egp, rate=Decimal("55.000000"), effective_date="2026-01-01")

    category = Category.objects.create(name="إلكترونيات", code="ELE")
    unit = Unit.objects.create(name="قطعة", symbol="قطعة")

    return {
        "user": user,
        "egp": egp,
        "usd": usd,
        "eur": eur,
        "category": category,
        "unit": unit,
    }


@pytest.mark.django_db
def test_product_form_create_foreign_currency(test_setup):
    """اختبار إنشاء منتج بالدولار وتحويل التكلفة والبيع للجنيه مع حفظ السعر الاسترشادي"""
    setup = test_setup
    form_data = {
        "name": "محول شبكات أجنبي",
        "name_en": "Network Switch",
        "category": setup["category"].id,
        "unit": setup["unit"].id,
        "pricing_currency": setup["usd"].id,
        "exchange_rate": "50.000000",
        "cost_price": "100.00",      # $100
        "selling_price": "150.00",   # $150
        "tax_rate": "14.00",
        "is_active": True,
    }

    form = ProductForm(data=form_data, user=setup["user"])
    assert form.is_valid(), f"Form validation failed: {form.errors}"
    
    product = form.save()
    
    assert product.pricing_currency == setup["usd"]
    assert product.is_foreign_currency_priced is True
    assert product.cost_price == Decimal("5000.00")     # 100 * 50
    assert product.selling_price == Decimal("7500.00")   # 150 * 50

    # فحص جدول ProductCurrencyPrice
    cp = ProductCurrencyPrice.objects.filter(product=product, currency=setup["usd"]).first()
    assert cp is not None
    assert cp.indicative_cost_price == Decimal("100.00")
    assert cp.indicative_selling_price == Decimal("150.00")


@pytest.mark.django_db
def test_product_form_edit_mode_hydration_prevents_inflation(test_setup):
    """اختبار وضع التعديل لمنع تضخيم السعر وقراءة السعر الأجنبي الأصلي"""
    setup = test_setup
    # إنشاء منتج بالدولار
    product = Product.objects.create(
        name="سيرفر سحابي",
        category=setup["category"],
        unit=setup["unit"],
        pricing_currency=setup["usd"],
        cost_price=Decimal("5000.00"),     # 5000 EGP
        selling_price=Decimal("7500.00"),  # 7500 EGP
        created_by=setup["user"],
    )
    ProductCurrencyPrice.objects.create(
        product=product,
        currency=setup["usd"],
        indicative_cost_price=Decimal("100.00"),    # $100
        indicative_selling_price=Decimal("150.00"), # $150
        created_by=setup["user"],
    )

    # فتح الفورم في وضع التعديل
    form = ProductForm(instance=product, user=setup["user"])
    assert form.initial["cost_price"] == Decimal("100.00")
    assert form.initial["selling_price"] == Decimal("150.00")
    assert form.initial["pricing_currency"] in (setup["usd"], setup["usd"].id)

    # إرسال تعديل جديد بـ $110 و $160
    update_data = {
        "name": "سيرفر سحابي مطور",
        "name_en": "Cloud Server Pro",
        "category": setup["category"].id,
        "unit": setup["unit"].id,
        "pricing_currency": setup["usd"].id,
        "exchange_rate": "50.000000",
        "cost_price": "110.00",
        "selling_price": "160.00",
        "tax_rate": "14.00",
        "is_active": True,
    }
    update_form = ProductForm(data=update_data, instance=product, user=setup["user"])
    assert update_form.is_valid(), f"Update failed: {update_form.errors}"
    updated_product = update_form.save()

    assert updated_product.cost_price == Decimal("5500.00")
    assert updated_product.selling_price == Decimal("8000.00")

    cp = ProductCurrencyPrice.objects.get(product=product, currency=setup["usd"])
    assert cp.indicative_cost_price == Decimal("110.00")
    assert cp.indicative_selling_price == Decimal("160.00")


@pytest.mark.django_db
def test_primary_currency_deletion_guard(test_setup):
    """اختبار صمام أمان منع حذف السعر الاسترشادي للعملة المرجعية الأساسية"""
    setup = test_setup
    product = Product.objects.create(
        name="راوتر رئيسي",
        category=setup["category"],
        unit=setup["unit"],
        pricing_currency=setup["usd"],
        cost_price=Decimal("5000.00"),
        selling_price=Decimal("7500.00"),
        created_by=setup["user"],
    )
    ProductCurrencyPrice.objects.create(
        product=product,
        currency=setup["usd"],
        indicative_cost_price=Decimal("100.00"),
        indicative_selling_price=Decimal("150.00"),
        created_by=setup["user"],
    )
    ProductCurrencyPrice.objects.create(
        product=product,
        currency=setup["eur"],
        indicative_cost_price=Decimal("90.00"),
        indicative_selling_price=Decimal("140.00"),
        created_by=setup["user"],
    )

    factory = RequestFactory()
    
    # 1. محاولة حذف السعر المخصص للدولار (وهي العملة الأساسية) -> يجب أن يفشل 400
    request_del_usd = factory.post(
        f"/products/{product.id}/currency-prices/",
        data={"currency_code": "USD", "form_action": "delete"},
        HTTP_X_REQUESTED_WITH="XMLHttpRequest"
    )
    request_del_usd.user = setup["user"]
    resp_usd = update_currency_prices(request_del_usd, pk=product.pk)
    assert resp_usd.status_code == 400
    assert ProductCurrencyPrice.objects.filter(product=product, currency=setup["usd"]).exists()

    # 2. محاولة حذف السعر المخصص لليورو (عملة إضافية وليست الأساسية) -> ينجح 200
    request_del_eur = factory.post(
        f"/products/{product.id}/currency-prices/",
        data={"currency_code": "EUR", "form_action": "delete"},
        HTTP_X_REQUESTED_WITH="XMLHttpRequest"
    )
    request_del_eur.user = setup["user"]
    resp_eur = update_currency_prices(request_del_eur, pk=product.pk)
    assert resp_eur.status_code == 200
    assert not ProductCurrencyPrice.objects.filter(product=product, currency=setup["eur"]).exists()


@pytest.mark.django_db
def test_purchase_signals_foreign_currency_protection(test_setup):
    """اختبار سيجنال المشتريات الأجنبية وتحديث السعر بالدولار وحساب التكلفة بالجنيه بدقة"""
    setup = test_setup
    supplier = Supplier.objects.create(name="Global Tech Supplier")
    product = Product.objects.create(
        name="كاميرا مراقبة ذكية",
        category=setup["category"],
        unit=setup["unit"],
        cost_price=Decimal("1000.00"),
        selling_price=Decimal("2000.00"),
        created_by=setup["user"],
    )

    # إنشاء فاتورة شراء مؤكدة بالدولار بسعر $120 وسعر صرف 50.0
    purchase = Purchase.objects.create(
        number="PO-USD-001",
        supplier=supplier,
        date="2026-01-01",
        subtotal=Decimal("600.00"),
        total=Decimal("600.00"),
        payment_method="credit",
        currency=setup["usd"],
        exchange_rate=Decimal("50.000000"),
        status="confirmed",
        created_by=setup["user"],
    )
    PurchaseItem.objects.create(
        purchase=purchase,
        product=product,
        quantity=5,
        unit_price=Decimal("120.00"),  # $120
    )

    # التحقق من أن السعر الاسترشادي للدولار أصبح $120
    cp = ProductCurrencyPrice.objects.filter(product=product, currency=setup["usd"]).first()
    assert cp is not None
    assert cp.indicative_cost_price == Decimal("120.00")

    # التحقق من أن سعر التكلفة بالجنيه تم حسابه كـ 120 * 50 = 6000 ج.م
    product.refresh_from_db()
    assert product.cost_price == Decimal("6000.00")


@pytest.mark.django_db
def test_product_serializers_multi_currency_and_rbac(test_setup):
    """اختبار تسلسل بيانات المنتجات متعددة العملات مع حوكمة الصلاحيات"""
    setup = test_setup
    product = Product.objects.create(
        name="موزع طاقة",
        sku="ELE-001",
        category=setup["category"],
        unit=setup["unit"],
        pricing_currency=setup["usd"],
        cost_price=Decimal("2500.00"),
        selling_price=Decimal("3500.00"),
        created_by=setup["user"],
    )
    ProductCurrencyPrice.objects.create(
        product=product,
        currency=setup["usd"],
        indicative_cost_price=Decimal("50.00"),
        indicative_selling_price=Decimal("70.00"),
        created_by=setup["user"],
    )

    # 1. استدعاء ProductListSerializer
    list_serializer = ProductListSerializer(product)
    data = list_serializer.data
    assert data["pricing_currency"] == setup["usd"].id
    assert data["pricing_currency_code"] == "USD"
    assert data["pricing_currency_symbol"] == "$"
    assert data["is_foreign_currency_priced"] is True

    # 2. استدعاء ProductDetailSerializer
    detail_serializer = ProductDetailSerializer(product)
    d_data = detail_serializer.data
    assert d_data["pricing_currency_code"] == "USD"
    assert len(d_data["currency_prices"]) == 1
    assert d_data["currency_prices"][0]["currency_code"] == "USD"
    assert Decimal(str(d_data["currency_prices"][0]["indicative_selling_price"])) == Decimal("70.00")
    assert Decimal(str(d_data["currency_prices"][0]["indicative_cost_price"])) == Decimal("50.00")
