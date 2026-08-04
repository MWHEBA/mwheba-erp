import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from product.models import Product, Warehouse, Category, Unit, InventoryCostLayer, InventoryCostConsumption
from product.services.stock_ledger_service import StockLedgerService
from product.services.valuation_service import InventoryValuationService

User = get_user_model()


@pytest.mark.django_db
class TestInventoryValuationService:

    @pytest.fixture
    def setup_valuation_data(self):
        user = User.objects.create_user(username="val_user", password="password123")
        category = Category.objects.create(name="Hardware", code="HW")
        unit = Unit.objects.create(name="Piece")

        product = Product.objects.create(
            name="Industrial Router X10",
            sku="PRD-ROUTER-10",
            category=category,
            unit=unit,
            cost_price=Decimal("200.00"),
            selling_price=Decimal("300.00"),
            created_by=user
        )
        warehouse = Warehouse.objects.create(name="Tech WH", code="WH-TECH", is_active=True)

        return user, product, warehouse, unit

    def test_fifo_layer_creation_and_consumption(self, setup_valuation_data):
        user, product, warehouse, unit = setup_valuation_data

        # Receipt 1: 10 units @ 200
        entry1 = StockLedgerService.record_movement_entry(
            product=product,
            warehouse=warehouse,
            movement_type="RECEIPT",
            quantity=Decimal("10.0000"),
            unit_cost=Decimal("200.0000"),
            movement_service_ref="MOV-REC-1"
        )
        layer1 = InventoryValuationService.create_receipt_cost_layer(
            product=product,
            warehouse=warehouse,
            stock_ledger_entry=entry1,
            quantity=Decimal("10.0000"),
            unit_cost=Decimal("200.0000")
        )

        # Receipt 2: 10 units @ 300
        entry2 = StockLedgerService.record_movement_entry(
            product=product,
            warehouse=warehouse,
            movement_type="RECEIPT",
            quantity=Decimal("10.0000"),
            unit_cost=Decimal("300.0000"),
            movement_service_ref="MOV-REC-2"
        )
        layer2 = InventoryValuationService.create_receipt_cost_layer(
            product=product,
            warehouse=warehouse,
            stock_ledger_entry=entry2,
            quantity=Decimal("10.0000"),
            unit_cost=Decimal("300.0000")
        )

        # Issue 15 units (Should consume 10 from layer1 @ 200, and 5 from layer2 @ 300)
        issue_entry = StockLedgerService.record_movement_entry(
            product=product,
            warehouse=warehouse,
            movement_type="ISSUE",
            quantity=Decimal("-15.0000"),
            unit_cost=Decimal("0.0000"),
            movement_service_ref="MOV-ISSUE-1"
        )

        val_res = InventoryValuationService.consume_fifo_layers(
            product=product,
            warehouse=warehouse,
            issue_quantity=Decimal("15.0000"),
            issue_ledger_entry=issue_entry
        )

        # Total COGS = (10 * 200) + (5 * 300) = 2000 + 1500 = 3500
        assert val_res['total_cogs'] == Decimal("3500.00")
        assert val_res['consumptions_count'] == 2

        layer1.refresh_from_db()
        layer2.refresh_from_db()

        assert layer1.status == "DEPLETED"
        assert layer1.remaining_qty == Decimal("0.0000")
        assert layer2.status == "OPEN"
        assert layer2.remaining_qty == Decimal("5.0000")
