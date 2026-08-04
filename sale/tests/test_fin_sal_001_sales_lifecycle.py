import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from client.models import Customer
from product.models.product_core import Product, Category, Unit
from product.models.stock_management import Warehouse
from financial.models import ChartOfAccounts, AccountType, AccountingPeriod, FiscalYear
from sale.services.sales_service import SalesService
from client.services.customer_subledger_service import CustomerSubledgerService

User = get_user_model()


@pytest.mark.django_db(transaction=True)
class TestFINSAL001SalesDocumentLifecycle:

    @pytest.fixture
    def setup_sales_lifecycle_data(self):
        user = User.objects.create_user(username="sale_user1", password="password123")

        asset_type, _ = AccountType.objects.get_or_create(code="ASSET", defaults={"name": "Asset", "category": "ASSET"})
        revenue_type, _ = AccountType.objects.get_or_create(code="REVENUE", defaults={"name": "Revenue", "category": "REVENUE"})
        expense_type, _ = AccountType.objects.get_or_create(code="EXPENSE", defaults={"name": "Expense", "category": "EXPENSE"})

        inv_acc = ChartOfAccounts.objects.create(code="10400", name="Inventory Asset", account_type=asset_type, is_active=True)
        ar_acc = ChartOfAccounts.objects.create(code="11010", name="Customer AR Control", account_type=asset_type, is_active=True)
        sales_acc = ChartOfAccounts.objects.create(code="40100", name="Sales Revenue Control", account_type=revenue_type, is_active=True)
        cogs_acc = ChartOfAccounts.objects.create(code="50100", name="COGS Control", account_type=expense_type, is_active=True)

        fiscal_year = FiscalYear.objects.create(name="FY2026", start_date="2026-01-01", end_date="2026-12-31")
        period = AccountingPeriod.objects.create(fiscal_year=fiscal_year, name="AUG2026", period_number=8, start_date="2026-08-01", end_date="2026-08-31", status="OPEN")

        customer = Customer.objects.create(name="Middle East Trading", code="CUST-SL-001", financial_account=ar_acc, credit_limit=Decimal("100000.00"))
        warehouse = Warehouse.objects.create(code="WH-SALES", name="Sales Central WH", is_active=True)

        category = Category.objects.create(name="Finished Goods")
        unit = Unit.objects.create(name="PCS")
        product = Product.objects.create(name="Commercial Printer X1", category=category, unit=unit, cost_price=Decimal("200.00"), selling_price=Decimal("350.00"), created_by=user)

        # Receive stock into warehouse via MovementService
        from governance.services.movement_service import MovementService
        MovementService().process_movement(
            product_id=product.id,
            quantity_change=Decimal("50.0000"),
            movement_type="in",
            source_reference="SETUP-STOCK",
            idempotency_key="SETUP-STK-001",
            user=user,
            unit_cost=Decimal("200.00"),
            warehouse_id=warehouse.id
        )

        return user, customer, warehouse, product

    def test_sales_lifecycle_so_delivery_invoice_flow(self, setup_sales_lifecycle_data):
        user, customer, warehouse, product = setup_sales_lifecycle_data

        # Step 1: Create SO (Auto-approved if below rule threshold)
        items_data = [{"product": product, "ordered_qty": Decimal("10.0000"), "unit_price": Decimal("350.00"), "discount_percentage": Decimal("0.00")}]
        so = SalesService.create_sales_order(customer=customer, warehouse=warehouse, order_date=timezone.now().date(), items_data=items_data, user=user)

        assert so.status == "APPROVED"
        assert so.total_amount == Decimal("3500.00")

        # Step 2: Deliver Goods (Delivery Note) -> Triggers COGS posting
        so_item = so.items.first()
        deliv_items = [{"so_item_id": so_item.id, "delivered_qty": Decimal("10.0000")}]
        dn = SalesService.deliver_goods(so_id=so.id, delivery_date=timezone.now().date(), items_data=deliv_items, user=user)

        assert dn.status == "DELIVERED"
        assert dn.journal_entry is not None
        assert dn.journal_entry.status == "posted"

        so.refresh_from_db()
        assert so.status == "FULLY_DELIVERED"

        # Step 4: Create Sales Invoice -> Triggers Revenue posting & AR Open Item
        dn_item = dn.items.first()
        inv_items = [{"so_item_id": so_item.id, "dn_item_id": dn_item.id, "billed_qty": Decimal("10.0000"), "unit_price": Decimal("350.00")}]
        inv = SalesService.create_sales_invoice(
            so_id=so.id,
            delivery_note_id=dn.id,
            invoice_date=timezone.now().date(),
            due_date=timezone.now().date(),
            items_data=inv_items,
            user=user
        )

        assert inv.status == "POSTED"
        assert inv.journal_entry is not None
        assert inv.journal_entry.status == "posted"

        open_items = CustomerSubledgerService.get_open_items(customer.id)
        assert open_items.count() == 1
        assert open_items.first().transaction_number == inv.invoice_number

    def test_fast_sale_mode_execution(self, setup_sales_lifecycle_data):
        user, customer, warehouse, product = setup_sales_lifecycle_data

        items_data = [{"product": product, "ordered_qty": Decimal("5.0000"), "unit_price": Decimal("350.00"), "discount_percentage": Decimal("0.00")}]
        result = SalesService.create_fast_sale(customer=customer, warehouse=warehouse, order_date=timezone.now().date(), items_data=items_data, user=user)

        assert result["sales_order"].status == "INVOICED"
        assert result["delivery_note"].status == "DELIVERED"
        assert result["sales_invoice"].status == "POSTED"
        assert result["sales_invoice"].journal_entry is not None
