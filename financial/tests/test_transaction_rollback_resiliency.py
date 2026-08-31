import pytest
import uuid
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.contrib.auth import get_user_model

from sale.models import SalesReturnHeader, SalesReturnAudit
from sale.services.sales_return_service import SalesReturnService
from sale.services.sales_service import SalesService
from product.models import Product, Category, Unit, Warehouse, Stock
from customer.models import Customer
from financial.models import ChartOfAccounts, AccountType
from financial.exceptions import FinancialCoreError

User = get_user_model()


@pytest.mark.django_db(transaction=True)
class TestTransactionRollbackResiliency:

    @pytest.fixture
    def setup_rollback_data(self):
        uid = uuid.uuid4().hex[:6]
        user = User.objects.create_user(username=f"roll_user_{uid}", email=f"roll_{uid}@example.com", password="password123")
        from financial.models import AccountingPeriod
        today = timezone.now().date()
        AccountingPeriod.objects.get_or_create(
            name=f"Period_{today.year}_{today.month}",
            start_date=today.replace(day=1),
            end_date=today.replace(day=28),
            defaults={"status": "open"}
        )

        customer = Customer.objects.create(name=f"Rollback Customer {uid}", code=f"CUST-ROLL-{uid}", credit_limit=Decimal("500000.00"))

        asset_type, _ = AccountType.objects.get_or_create(code="ASSET", defaults={"name": "Assets", "category": "asset", "nature": "debit"})
        liab_type, _ = AccountType.objects.get_or_create(code="LIAB", defaults={"name": "Liabilities", "category": "liability", "nature": "credit"})
        rev_type, _ = AccountType.objects.get_or_create(code="REV", defaults={"name": "Revenues", "category": "revenue", "nature": "credit"})
        exp_type, _ = AccountType.objects.get_or_create(code="EXPENSE", defaults={"name": "Expenses", "category": "expense", "nature": "debit"})

        ChartOfAccounts.objects.get_or_create(code="10400", defaults={"name": "Inventory Asset", "account_type": asset_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="11010", defaults={"name": "Customer AR", "account_type": asset_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="22010", defaults={"name": "Output VAT Payable", "account_type": liab_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="40100", defaults={"name": "Sales Revenue Account", "account_type": rev_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="50100", defaults={"name": "COGS Control", "account_type": exp_type, "is_active": True})

        category = Category.objects.create(name=f"Roll Category {uid}")
        unit = Unit.objects.create(name=f"PCS-{uid}")
        product = Product.objects.create(name=f"Roll Product {uid}", category=category, unit=unit, cost_price=Decimal("100.00"), selling_price=Decimal("200.00"), created_by=user)
        warehouse = Warehouse.objects.create(code=f"WH-ROLL-{uid}", name=f"Roll Warehouse {uid}", is_active=True)
        Stock.objects.create(product=product, warehouse=warehouse, quantity=50)

        return user, customer, product, warehouse

    def test_atomic_rollback_on_simulated_mid_process_failure(self, setup_rollback_data):
        user, customer, product, warehouse = setup_rollback_data

        items_data = [{"product": product, "ordered_qty": Decimal("5.0000"), "unit_price": Decimal("200.00")}]
        sale_res = SalesService.create_fast_sale(customer=customer, warehouse=warehouse, order_date=timezone.now().date(), items_data=items_data, user=user)
        dn = sale_res["delivery_note"]

        auth = SalesReturnService.create_return_authorization(customer.id, user=user)
        dn_item = dn.items.first()
        ret_header = SalesReturnService.create_sales_return(auth.id, dn.id, warehouse.id, [{"delivery_item_id": dn_item.id, "requested_qty": Decimal("2.0000")}], user=user)

        ret_item = ret_header.items.first()
        SalesReturnService.inspect_sales_return(ret_header.id, [{"return_item_id": ret_item.id, "good_qty": Decimal("2.0000")}], user=user)

        stock_before = Stock.objects.get(product=product, warehouse=warehouse).quantity
        audit_count_before = SalesReturnAudit.objects.count()

        # Simulate exception during atomic processing block by monkeypatching/raising error
        with pytest.raises(RuntimeError, match="Simulated Mid-Process Failure"):
            with transaction.atomic():
                # Perform stock movement
                from governance.services.movement_service import MovementService
                MovementService().process_movement(
                    product_id=product.id,
                    quantity_change=Decimal("2.0000"),
                    movement_type="in",
                    source_reference="TEST-FAIL",
                    idempotency_key=f"FAIL_MVMT_{uuid.uuid4().hex}",
                    user=user,
                    unit_cost=Decimal("100.00"),
                    warehouse_id=warehouse.id
                )
                # Forced failure mid-way
                raise RuntimeError("Simulated Mid-Process Failure")

        # Verify 100% Rollback: stock restored, zero orphan audit records created
        stock_after = Stock.objects.get(product=product, warehouse=warehouse).quantity
        audit_count_after = SalesReturnAudit.objects.count()

        assert stock_before == stock_after
        assert audit_count_before == audit_count_after
