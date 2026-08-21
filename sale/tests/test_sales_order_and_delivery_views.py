"""
Unit & Integration Tests for Sales Orders, Delivery Notes, and Pricing Views
"""
import pytest
from decimal import Decimal
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from client.models import Customer
from product.models.product_core import Product, Category, Unit
from product.models.stock_management import Warehouse, Stock
from sale.models.sales_models import SalesOrder, SalesOrderItem, DeliveryNote, DeliveryNoteItem
from sale.models.pricing import PriceList, PriceListItem, DiscountRule
from sale.models import Quotation, QuotationItem

User = get_user_model()


@pytest.mark.django_db
class TestSalesOrderAndDeliveryViews:

    @pytest.fixture(autouse=True)
    def setup_data(self):
        self.user = User.objects.create_superuser(
            username="admin_views",
            email="admin_views@test.com",
            password="password123"
        )
        self.customer = Customer.objects.create(
            name="Test Enterprise Customer",
            code="CUST-VIEW-001",
            phone="01011112222",
            client_type="company"
        )
        self.warehouse, _ = Warehouse.objects.get_or_create(
            code="WH-VIEW-01",
            defaults={"name": "View Warehouse", "is_active": True}
        )
        self.category = Category.objects.create(name="Networking Category")
        self.unit = Unit.objects.create(name="Piece")
        self.product = Product.objects.create(
            name="Industrial Router",
            sku="RTR-001",
            category=self.category,
            unit=self.unit,
            created_by=self.user,
            selling_price=Decimal("1500.00"),
            cost_price=Decimal("900.00"),
            is_active=True
        )
        from financial.models import ChartOfAccounts, AccountType, AccountingPeriod
        asset_type, _ = AccountType.objects.get_or_create(name="Current Asset", nature="DEBIT", defaults={"code": "1000"})
        liability_type, _ = AccountType.objects.get_or_create(name="Current Liability", nature="CREDIT", defaults={"code": "2000"})
        revenue_type, _ = AccountType.objects.get_or_create(name="Revenue", nature="CREDIT", defaults={"code": "4000"})
        expense_type, _ = AccountType.objects.get_or_create(name="Expense", nature="DEBIT", defaults={"code": "5000"})

        self.ar_acc, _ = ChartOfAccounts.objects.get_or_create(code="10200", defaults={"name": "Accounts Receivable", "account_type": asset_type, "is_active": True})
        self.inv_acc, _ = ChartOfAccounts.objects.get_or_create(code="10400", defaults={"name": "Inventory", "account_type": asset_type, "is_active": True})
        self.inv_alt, _ = ChartOfAccounts.objects.get_or_create(code="11310", defaults={"name": "Inventory Alt", "account_type": asset_type, "is_active": True})
        self.rev_acc, _ = ChartOfAccounts.objects.get_or_create(code="40100", defaults={"name": "Sales Revenue", "account_type": revenue_type, "is_active": True})
        self.tax_acc, _ = ChartOfAccounts.objects.get_or_create(code="20200", defaults={"name": "VAT Output", "account_type": liability_type, "is_active": True})
        self.cogs_acc, _ = ChartOfAccounts.objects.get_or_create(code="50100", defaults={"name": "Cost of Goods Sold", "account_type": expense_type, "is_active": True})

        today = timezone.now().date()
        AccountingPeriod.objects.get_or_create(
            name=f"Period_{today.year}_{today.month}",
            start_date=today.replace(day=1),
            end_date=today.replace(day=28),
            defaults={"status": "open"}
        )

        Stock.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity=Decimal("50.00")
        )

    def test_sales_order_list_view(self, client):
        client.force_login(self.user)
        url = reverse("sale:sales_order_list")
        response = client.get(url)
        assert response.status_code == 200
        assert "أوامر البيع" in response.content.decode("utf-8")

    def test_sales_order_create_and_detail_view(self, client):
        client.force_login(self.user)
        create_url = reverse("sale:sales_order_create")
        post_data = {
            "customer": self.customer.id,
            "warehouse": self.warehouse.id,
            "order_date": timezone.now().date().isoformat(),
            "currency": "EGP",
            "exchange_rate": "1.000000",
            "product[]": [str(self.product.id)],
            "quantity[]": ["5.00"],
            "unit_price[]": ["1500.00"],
            "discount[]": ["0.00"],
        }
        response = client.post(create_url, post_data)
        assert response.status_code == 302

        so = SalesOrder.objects.filter(customer=self.customer).first()
        assert so is not None
        assert so.total_amount == Decimal("7500.00")

        detail_url = reverse("sale:sales_order_detail", kwargs={"pk": so.pk})
        detail_res = client.get(detail_url)
        assert detail_res.status_code == 200
        assert so.order_number in detail_res.content.decode("utf-8")

    def test_delivery_note_list_and_create_flow(self, client):
        client.force_login(self.user)
        from sale.services.sales_service import SalesService
        items_data = [{
            "product": self.product,
            "ordered_qty": Decimal("5.00"),
            "unit_price": Decimal("1500.00"),
            "discount_percentage": Decimal("0.00")
        }]
        so = SalesService.create_sales_order(
            customer=self.customer,
            warehouse=self.warehouse,
            order_date=timezone.now().date(),
            currency="EGP",
            exchange_rate=Decimal("1.000000"),
            items_data=items_data,
            user=self.user
        )
        if so.status == "PENDING_APPROVAL":
            SalesService.approve_sales_order(so.id, user=self.user)
            so.refresh_from_db()
        so_item = so.items.first()

        dn_list_url = reverse("sale:delivery_note_list")
        res = client.get(dn_list_url)
        assert res.status_code == 200

        dn_create_url = reverse("sale:delivery_note_create")
        post_data = {
            "sales_order": so.id,
            "delivery_date": timezone.now().date().isoformat(),
            "so_item_id[]": [str(so_item.id)],
            "delivered_qty[]": ["5.00"],
        }
        create_res = client.post(dn_create_url, post_data)
        assert create_res.status_code == 302

        dn = DeliveryNote.objects.filter(sales_order=so).first()
        assert dn is not None
        assert dn.status == "DELIVERED"

        dn_detail_url = reverse("sale:delivery_note_detail", kwargs={"pk": dn.pk})
        detail_res = client.get(dn_detail_url)
        assert detail_res.status_code == 200
        assert dn.delivery_number in detail_res.content.decode("utf-8")

    def test_price_list_and_discount_rules_views(self, client):
        client.force_login(self.user)

        # Price Lists List
        pl_list_url = reverse("sale:price_list_list")
        res = client.get(pl_list_url)
        assert res.status_code == 200

        # Price List Create
        pl_create_url = reverse("sale:price_list_create")
        post_data = {
            "name": "VIP Wholesale Price List",
            "currency": "EGP",
            "customer_type": "VIP",
            "effective_from": timezone.now().date().isoformat(),
            "product[]": [str(self.product.id)],
            "price[]": ["1350.00"],
            "min_qty[]": ["10.00"],
        }
        create_res = client.post(pl_create_url, post_data)
        assert create_res.status_code == 302

        pl = PriceList.objects.filter(name="VIP Wholesale Price List").first()
        assert pl is not None
        assert pl.items.count() == 1

        # Discount Rules List & Create
        disc_list_url = reverse("sale:discount_rule_list")
        disc_res = client.get(disc_list_url)
        assert disc_res.status_code == 200

        disc_create_url = reverse("sale:discount_rule_create")
        post_disc = {
            "rule_name": "New Year 10% Off",
            "rule_type": "PERCENTAGE",
            "customer": "",
            "category": "",
            "discount_percentage": "10.00",
            "value": "0.00",
            "min_order_amount": "1000.00",
            "priority": "5",
            "effective_date": timezone.now().date().isoformat(),
        }
        create_disc_res = client.post(disc_create_url, post_disc)
        assert create_disc_res.status_code == 302

        rule = DiscountRule.objects.filter(rule_name="New Year 10% Off").first()
        assert rule is not None
        assert rule.discount_percentage == Decimal("10.00")
