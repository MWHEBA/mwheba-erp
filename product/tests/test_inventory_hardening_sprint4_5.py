import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from product.models import Product, Warehouse, Category, Unit, InventoryCostLayer
from product.services.stock_ledger_service import StockLedgerService
from product.services.valuation_service import InventoryValuationService
from product.services.inventory_reconciliation_service import InventoryReconciliationService

User = get_user_model()


@pytest.mark.django_db
class TestSprint45InventoryHardening:

    @pytest.fixture
    def setup_hardening_data(self):
        user = User.objects.create_user(username="hardened_user", password="password123")
        category = Category.objects.create(name="Precision Parts", code="PREC")
        unit = Unit.objects.create(name="Piece")

        product = Product.objects.create(
            name="CNC Milling Bit 10mm",
            sku="PRD-CNC-10MM",
            category=category,
            unit=unit,
            cost_price=Decimal("150.00"),
            selling_price=Decimal("250.00"),
            valuation_method="FIFO",
            created_by=user
        )
        warehouse = Warehouse.objects.create(name="Hardened WH", code="WH-HARDENED", is_active=True)

        return user, product, warehouse, unit

    def test_valuation_method_governance(self, setup_hardening_data):
        user, product, warehouse, unit = setup_hardening_data

        method = InventoryValuationService.get_valuation_method(product)
        assert method == "FIFO"

        product.valuation_method = "MOVING_AVERAGE"
        product.save()

        method_avco = InventoryValuationService.get_valuation_method(product)
        assert method_avco == "MOVING_AVERAGE"

    def test_multi_layer_fifo_and_partial_consumption(self, setup_hardening_data):
        user, product, warehouse, unit = setup_hardening_data

        # Receipt 1: 5 units @ 100
        e1 = StockLedgerService.record_movement_entry(product, warehouse, "RECEIPT", Decimal("5.0000"), Decimal("100.0000"), "REF-1")
        l1 = InventoryValuationService.create_receipt_cost_layer(product, warehouse, e1, Decimal("5.0000"), Decimal("100.0000"))

        # Receipt 2: 10 units @ 150
        e2 = StockLedgerService.record_movement_entry(product, warehouse, "RECEIPT", Decimal("10.0000"), Decimal("150.0000"), "REF-2")
        l2 = InventoryValuationService.create_receipt_cost_layer(product, warehouse, e2, Decimal("10.0000"), Decimal("150.0000"))

        # Receipt 3: 15 units @ 200
        e3 = StockLedgerService.record_movement_entry(product, warehouse, "RECEIPT", Decimal("15.0000"), Decimal("200.0000"), "REF-3")
        l3 = InventoryValuationService.create_receipt_cost_layer(product, warehouse, e3, Decimal("15.0000"), Decimal("200.0000"))

        # Issue 12 units (5 from l1 @ 100, 7 from l2 @ 150)
        issue_e = StockLedgerService.record_movement_entry(product, warehouse, "ISSUE", Decimal("-12.0000"), Decimal("0.0000"), "ISSUE-REF-1")
        res = InventoryValuationService.consume_fifo_layers(product, warehouse, Decimal("12.0000"), issue_e)

        # COGS = 5*100 + 7*150 = 500 + 1050 = 1550
        assert res["total_cogs"] == Decimal("1550.00")
        assert res["consumptions_count"] == 2

        l1.refresh_from_db()
        l2.refresh_from_db()
        l3.refresh_from_db()

        assert l1.status == "DEPLETED"
        assert l1.remaining_qty == Decimal("0.0000")

        assert l2.status == "OPEN"
        assert l2.remaining_qty == Decimal("3.0000")

        assert l3.status == "OPEN"
        assert l3.remaining_qty == Decimal("15.0000")

    def test_inventory_vs_gl_reconciliation(self, setup_hardening_data):
        user, product, warehouse, unit = setup_hardening_data

        # Create active layer
        e = StockLedgerService.record_movement_entry(product, warehouse, "RECEIPT", Decimal("20.0000"), Decimal("100.0000"), "REC-REC-1")
        l = InventoryValuationService.create_receipt_cost_layer(product, warehouse, e, Decimal("20.0000"), Decimal("100.0000"))

        recon = InventoryReconciliationService.reconcile_inventory_control_account(account_code="11040_INV")

        assert recon["subledger_valuation"] == Decimal("2000.00")
        assert "discrepancy" in recon
        assert "is_reconciled" in recon

    def test_cost_layer_concurrency_locking(self, setup_hardening_data):
        user, product, warehouse, unit = setup_hardening_data

        e = StockLedgerService.record_movement_entry(product, warehouse, "RECEIPT", Decimal("50.0000"), Decimal("100.0000"), "LOCK-REF-1")
        l = InventoryValuationService.create_receipt_cost_layer(product, warehouse, e, Decimal("50.0000"), Decimal("100.0000"))

        locked_layers = InventoryCostLayer.objects.select_for_update().filter(product=product, warehouse=warehouse, status="OPEN")
        assert locked_layers.count() == 1
        assert locked_layers.first().remaining_qty == Decimal("50.0000")
