from decimal import Decimal
import pytest
from django.test import TestCase
from django.urls import reverse
from customer.models import Customer
from supplier.models import Supplier, SupplierType
from financial.models.currency import Currency


class TestCustomerSupplierFilters(TestCase):
    def setUp(self):
        super().setUp()
        self.curr_egp, _ = Currency.objects.get_or_create(
            code="EGP",
            defaults={"name": "جنيه مصري", "symbol": "ج.م", "is_functional": True}
        )
        self.curr_usd, _ = Currency.objects.get_or_create(
            code="USD",
            defaults={"name": "دولار أمريكي", "symbol": "$", "is_functional": False}
        )
        self.curr_eur, _ = Currency.objects.get_or_create(
            code="EUR",
            defaults={"name": "يورو", "symbol": "€", "is_functional": False}
        )

        # Customers with EGP and USD only (EUR is unused)
        self.c1 = Customer.objects.create(
            name="عميل محلي",
            code="CUST-FLT-1",
            customer_type="individual",
            default_currency=self.curr_egp
        )
        self.c2 = Customer.objects.create(
            name="شركة دولية",
            code="CUST-FLT-2",
            customer_type="company",
            default_currency=self.curr_usd
        )

        # Supplier types
        self.st1, _ = SupplierType.objects.get_or_create(
            code="LOCAL_GOODS",
            defaults={"name": "بضائع محلية"}
        )
        self.st2, _ = SupplierType.objects.get_or_create(
            code="IMPORT_GOODS",
            defaults={"name": "بضائع مستوردة"}
        )

        # Suppliers with EGP and USD only
        self.s1 = Supplier.objects.create(
            name="مورد محلي",
            code="SUPP-FLT-1",
            primary_type=self.st1,
            default_currency=self.curr_egp
        )
        self.s2 = Supplier.objects.create(
            name="مورد أجنبي",
            code="SUPP-FLT-2",
            primary_type=self.st2,
            default_currency=self.curr_usd
        )

    def test_customer_currency_filter(self):
        # Filter by EGP
        qs = Customer.objects.filter(default_currency=self.curr_egp)
        assert qs.filter(id=self.c1.id).exists()
        assert not qs.filter(id=self.c2.id).exists()

        # Only used currencies should be returned
        used_curr_ids = Customer.objects.exclude(default_currency__isnull=True).values_list('default_currency_id', flat=True).distinct()
        currencies = Currency.objects.filter(id__in=used_curr_ids)
        curr_codes = set(currencies.values_list('code', flat=True))
        assert "EGP" in curr_codes
        assert "USD" in curr_codes
        assert "EUR" not in curr_codes

    def test_customer_customer_type_filter(self):
        qs = Customer.objects.filter(customer_type="company")
        assert qs.filter(id=self.c2.id).exists()
        assert not qs.filter(id=self.c1.id).exists()

    def test_supplier_currency_filter(self):
        # Filter by USD
        qs = Supplier.objects.filter(default_currency=self.curr_usd)
        assert qs.filter(id=self.s2.id).exists()
        assert not qs.filter(id=self.s1.id).exists()

        # Only used currencies should be returned
        used_curr_ids = Supplier.objects.exclude(default_currency__isnull=True).values_list('default_currency_id', flat=True).distinct()
        currencies = Currency.objects.filter(id__in=used_curr_ids)
        curr_codes = set(currencies.values_list('code', flat=True))
        assert "EGP" in curr_codes
        assert "USD" in curr_codes
        assert "EUR" not in curr_codes

    def test_supplier_type_filter(self):
        qs = Supplier.objects.filter(primary_type=self.st1)
        assert qs.filter(id=self.s1.id).exists()
        assert not qs.filter(id=self.s2.id).exists()

    def test_supplier_list_search_and_ajax(self):
        from users.models import User
        user = User.objects.create_user(username="test_search_user", password="password123")
        self.client.force_login(user)

        # 1. Direct GET search
        resp = self.client.get(reverse("supplier:supplier_list"), {"search": "محلي"})
        assert resp.status_code == 200
        assert "مورد محلي" in resp.content.decode("utf-8")
        assert "مورد أجنبي" not in resp.content.decode("utf-8")

        # 2. AJAX search
        resp_ajax = self.client.get(
            reverse("supplier:supplier_list"),
            {"search": "أجنبي"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        assert resp_ajax.status_code == 200
        data = resp_ajax.json()
        assert "table_html" in data
        assert "pagination_html" in data
        assert "مورد أجنبي" in data["table_html"]
        assert "مورد محلي" not in data["table_html"]

