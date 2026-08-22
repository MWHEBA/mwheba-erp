import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from product.models import Product, Category, Unit
from product.forms import ProductForm
from financial.models.tax import TaxCode

User = get_user_model()

@pytest.fixture
def tax_setup(db):
    user = User.objects.create_user(username="taxuser", password="password")
    vat14, _ = TaxCode.objects.get_or_create(
        code="VAT14",
        defaults={
            "name": "ضريبة القيمة المضافة 14%",
            "rate": Decimal("14.0000"),
            "tax_type": "VAT",
            "eta_tax_type": "T1",
            "is_default": True,
            "is_active": True,
        }
    )
    exempt, _ = TaxCode.objects.get_or_create(
        code="EXEMPT",
        defaults={
            "name": "معفى من الضريبة 0%",
            "rate": Decimal("0.0000"),
            "tax_type": "EXEMPT",
            "eta_tax_type": "T2",
            "is_default": False,
            "is_active": True,
        }
    )
    category = Category.objects.create(name="تصنيف تجريبي", code="TESTCAT")
    unit = Unit.objects.create(name="قطعة", symbol="قطعة")
    return {
        "user": user,
        "vat14": vat14,
        "exempt": exempt,
        "category": category,
        "unit": unit,
    }


@pytest.mark.django_db
def test_product_form_initial_tax_defaults(tax_setup):
    """التحقق من أن فورم إنشاء المنتج يحدد كود ونسبة الضريبة الافتراضية 14%"""
    form = ProductForm()
    assert form.fields['tax_code'].initial == tax_setup['vat14'].pk
    assert form.fields['tax_rate'].initial == Decimal("14.0000")


@pytest.mark.django_db
def test_product_form_save_with_tax_code(tax_setup):
    """التحقق من حفظ المنتج مع مزامنة كود الضريبة والنسبة وحساب القيم المشتقة"""
    data = {
        "name": "منتج خاضع للضريبة",
        "category": tax_setup["category"].pk,
        "unit": tax_setup["unit"].pk,
        "cost_price": "100.00",
        "selling_price": "150.00",
        "tax_code": tax_setup["vat14"].pk,
        "tax_rate": "14.00",
        "min_stock": 5,
        "is_active": True,
    }
    form = ProductForm(data=data)
    assert form.is_valid(), form.errors
    product = form.save(commit=False)
    product.created_by = tax_setup["user"]
    product.save()

    assert product.tax_code == tax_setup["vat14"]
    assert product.tax_rate == Decimal("14.00")
    assert product.effective_tax_rate == Decimal("14.0000")
    assert product.estimated_tax_amount == Decimal("21.00")
    assert product.selling_price_with_tax == Decimal("171.00")
    assert product.is_tax_exempt is False


@pytest.mark.django_db
def test_product_form_exempt_tax(tax_setup):
    """التحقق من إنشاء منتج معفى من الضريبة"""
    data = {
        "name": "منتج معفى",
        "category": tax_setup["category"].pk,
        "unit": tax_setup["unit"].pk,
        "cost_price": "50.00",
        "selling_price": "80.00",
        "tax_code": tax_setup["exempt"].pk,
        "tax_rate": "0.00",
        "min_stock": 0,
        "is_active": True,
    }
    form = ProductForm(data=data)
    assert form.is_valid(), form.errors
    product = form.save(commit=False)
    product.created_by = tax_setup["user"]
    product.save()

    assert product.tax_code == tax_setup["exempt"]
    assert product.tax_rate == Decimal("0.00")
    assert product.effective_tax_rate == Decimal("0.00")
    assert product.estimated_tax_amount == Decimal("0.00")
    assert product.selling_price_with_tax == Decimal("80.00")
    assert product.is_tax_exempt is True


@pytest.mark.django_db
def test_product_form_auto_match_tax_code_by_rate(tax_setup):
    """التحقق من أن إدخال نسبة 14% بدون اختيار كود يربطها تلقائياً بكود VAT14"""
    data = {
        "name": "منتج ربط تلقائي",
        "category": tax_setup["category"].pk,
        "unit": tax_setup["unit"].pk,
        "cost_price": "20.00",
        "selling_price": "40.00",
        "tax_code": "",
        "tax_rate": "14.00",
        "min_stock": 0,
        "is_active": True,
    }
    form = ProductForm(data=data)
    assert form.is_valid(), form.errors
    product = form.save(commit=False)
    product.created_by = tax_setup["user"]
    product.save()

    assert product.tax_code == tax_setup["vat14"]
    assert product.effective_tax_rate == Decimal("14.0000")
