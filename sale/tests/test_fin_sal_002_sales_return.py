import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from sale.models import (
    ReturnAuthorization,
    SalesReturnHeader,
    SalesReturnItem,
    SalesReturnInspection,
    ReturnCostTrace,
    SalesReturnAudit,
)
from sale.services.sales_return_service import SalesReturnService
from sale.services.sales_service import SalesService
from product.models import Product, Category, Unit, Warehouse, Stock
from client.models import Customer
from financial.models import ChartOfAccounts, AccountType
from financial.exceptions import FinancialCoreError

User = get_user_model()


@pytest.mark.django_db(transaction=True)
class TestFINSAL002SalesReturn:

    @pytest.fixture
    def setup_return_data(self):
        user = User.objects.create_user(username="ret_user1", email="ret1@example.com", password="password123")
        from financial.models import AccountingPeriod
        today = timezone.now().date()
        AccountingPeriod.objects.get_or_create(
            name=f"Period_{today.year}_{today.month}",
            start_date=today.replace(day=1),
            end_date=today.replace(day=28),
            defaults={"status": "open"}
        )
        customer = Customer.objects.create(name="Alexandria Trading", code="CUST-RET-001", credit_limit=Decimal("500000.00"))

        asset_type, _ = AccountType.objects.get_or_create(code="ASSET", name="Assets", category="ASSET")
        liab_type, _ = AccountType.objects.get_or_create(code="LIAB", name="Liabilities", category="LIABILITY")
        rev_type, _ = AccountType.objects.get_or_create(code="REV", name="Revenues", category="REVENUE")
        exp_type, _ = AccountType.objects.get_or_create(code="EXPENSE", name="Expenses", category="EXPENSE")

        ChartOfAccounts.objects.get_or_create(code="10400", defaults={"name": "Inventory Asset", "account_type": asset_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="11010", defaults={"name": "Customer AR", "account_type": asset_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="11050", defaults={"name": "Input VAT Recoverable", "account_type": asset_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="22010", defaults={"name": "Output VAT Payable", "account_type": liab_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="21000", defaults={"name": "Deferred Revenue", "account_type": liab_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="40100", defaults={"name": "Sales Revenue Account", "account_type": rev_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="50100", defaults={"name": "COGS Control", "account_type": exp_type, "is_active": True})

        category = Category.objects.create(name="Consumer Electronics")
        unit = Unit.objects.create(name="PCS")
        product = Product.objects.create(name="Smart Display 10inch", category=category, unit=unit, cost_price=Decimal("150.00"), selling_price=Decimal("300.00"), created_by=user)
        warehouse = Warehouse.objects.create(code="WH-RET-01", name="Main Delivery Warehouse", is_active=True)
        Stock.objects.create(product=product, warehouse=warehouse, quantity=100)

        # Execute Fast Sale for 10 units
        items_data = [{"product": product, "ordered_qty": Decimal("10.0000"), "unit_price": Decimal("300.00")}]
        sale_res = SalesService.create_fast_sale(customer=customer, warehouse=warehouse, order_date=timezone.now().date(), items_data=items_data, user=user)

        delivery_note = sale_res["delivery_note"]
        return user, customer, product, warehouse, delivery_note

    def test_return_authorization_and_header_creation(self, setup_return_data):
        user, customer, product, warehouse, delivery_note = setup_return_data

        auth = SalesReturnService.create_return_authorization(customer.id, reason_category="CUSTOMER_COMPLAINT", notes="Wrong Color Sent", user=user)
        assert auth.status == "APPROVED"

        dn_item = delivery_note.items.first()
        items_data = [{"delivery_item_id": dn_item.id, "requested_qty": Decimal("4.0000")}]

        ret_header = SalesReturnService.create_sales_return(auth.id, delivery_note.id, warehouse.id, items_data, user=user)
        assert ret_header.status == "SUBMITTED"
        assert ret_header.items.count() == 1

    def test_quality_inspection_good_vs_damaged(self, setup_return_data):
        user, customer, product, warehouse, delivery_note = setup_return_data

        auth = SalesReturnService.create_return_authorization(customer.id, user=user)
        dn_item = delivery_note.items.first()
        items_data = [{"delivery_item_id": dn_item.id, "requested_qty": Decimal("5.0000")}]
        ret_header = SalesReturnService.create_sales_return(auth.id, delivery_note.id, warehouse.id, items_data, user=user)

        ret_item = ret_header.items.first()
        insp_items = [{"return_item_id": ret_item.id, "good_qty": Decimal("3.0000"), "damaged_qty": Decimal("2.0000")}]

        inspections = SalesReturnService.inspect_sales_return(ret_header.id, insp_items, user=user)
        assert len(inspections) == 1
        assert inspections[0].good_qty == Decimal("3.0000")
        assert inspections[0].damaged_qty == Decimal("2.0000")

        ret_header.refresh_from_db()
        assert ret_header.status == "INSPECTED"

    def test_process_return_stock_restoration_and_cogs_reversal(self, setup_return_data):
        user, customer, product, warehouse, delivery_note = setup_return_data

        auth = SalesReturnService.create_return_authorization(customer.id, user=user)
        dn_item = delivery_note.items.first()
        items_data = [{"delivery_item_id": dn_item.id, "requested_qty": Decimal("4.0000")}]
        ret_header = SalesReturnService.create_sales_return(auth.id, delivery_note.id, warehouse.id, items_data, user=user)

        ret_item = ret_header.items.first()
        insp_items = [{"return_item_id": ret_item.id, "good_qty": Decimal("3.0000"), "damaged_qty": Decimal("1.0000")}]
        SalesReturnService.inspect_sales_return(ret_header.id, insp_items, user=user)

        stock_before = Stock.objects.get(product=product, warehouse=warehouse).quantity

        # Process return stock & accounting
        audit = SalesReturnService.process_return_stock_and_accounting(ret_header.id, user=user)

        assert audit.new_status == "PROCESSED"
        assert audit.audit_hash is not None

        # Verify ReturnCostTrace recorded exact FIFO unit cost (150 EGP)
        trace = ReturnCostTrace.objects.get(return_item=ret_item)
        assert trace.original_unit_cost == Decimal("150.0000")
        assert trace.restored_value == Decimal("450.00") # 3 GOOD * 150

        # Verify Stock restored for GOOD units to sellable warehouse
        stock_after = Stock.objects.get(product=product, warehouse=warehouse).quantity
        assert stock_after > stock_before

    def test_audit_immutability_protection(self, setup_return_data):
        user, customer, product, warehouse, delivery_note = setup_return_data

        auth = SalesReturnService.create_return_authorization(customer.id, user=user)
        dn_item = delivery_note.items.first()
        items_data = [{"delivery_item_id": dn_item.id, "requested_qty": Decimal("2.0000")}]
        ret_header = SalesReturnService.create_sales_return(auth.id, delivery_note.id, warehouse.id, items_data, user=user)

        ret_item = ret_header.items.first()
        insp_items = [{"return_item_id": ret_item.id, "good_qty": Decimal("2.0000")}]
        SalesReturnService.inspect_sales_return(ret_header.id, insp_items, user=user)

        audit = SalesReturnService.process_return_stock_and_accounting(ret_header.id, user=user)

        # Attempt to modify audit record must raise ValueError
        with pytest.raises(ValueError, match="INSERT-ONLY"):
            audit.new_status = "CANCELLED"
            audit.save()

        # Attempt to delete audit record must raise ValueError
        with pytest.raises(ValueError, match="cannot be deleted"):
            audit.delete()
