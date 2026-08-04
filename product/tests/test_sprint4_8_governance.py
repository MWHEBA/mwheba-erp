import pytest
import threading
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from product.models import Product, Warehouse, Category, Unit, InventoryCostLayer, InventoryCostConsumption
from product.services.stock_ledger_service import StockLedgerService
from product.services.valuation_service import InventoryValuationService

User = get_user_model()


@pytest.mark.django_db(transaction=True)
class TestSprint48Governance:

    @pytest.fixture
    def setup_sprint48_data(self):
        user = User.objects.create_user(username="gov_user48", password="password123")
        category = Category.objects.create(name="Industrial Equipment", code="IND-EQP", valuation_method="MOVING_AVERAGE")
        unit = Unit.objects.create(name="Piece")

        product_default = Product.objects.create(
            name="Hydraulic Valve V1",
            sku="PRD-VALVE-V1",
            category=category,
            unit=unit,
            cost_price=Decimal("500.00"),
            selling_price=Decimal("800.00"),
            valuation_method="",
            created_by=user
        )

        product_override = Product.objects.create(
            name="Hydraulic Pump P2",
            sku="PRD-PUMP-P2",
            category=category,
            unit=unit,
            cost_price=Decimal("1200.00"),
            selling_price=Decimal("2000.00"),
            valuation_method="FIFO",
            created_by=user
        )

        warehouse = Warehouse.objects.create(name="Governance WH", code="WH-GOV-48", is_active=True)

        return user, category, product_default, product_override, warehouse, unit

    def test_fin_inv_013_valuation_policy_hierarchy(self, setup_sprint48_data):
        user, category, product_default, product_override, warehouse, unit = setup_sprint48_data

        # 1. Product Override -> Should be FIFO
        assert product_override.get_effective_valuation_method() == "FIFO"

        # 2. Category Policy -> Should be MOVING_AVERAGE
        assert product_default.get_effective_valuation_method() == "MOVING_AVERAGE"

        # 3. System Default -> Should be FIFO if category valuation_method is empty
        category.valuation_method = None
        category.save()
        assert product_default.get_effective_valuation_method() == "FIFO"

    def test_fin_inv_011_return_cost_traceability(self, setup_sprint48_data):
        user, category, product_default, product_override, warehouse, unit = setup_sprint48_data

        # Receipt 1: 10 units @ 500
        rec_entry = StockLedgerService.record_movement_entry(product_override, warehouse, "RECEIPT", Decimal("10.0000"), Decimal("500.0000"), "REC-RET-1")
        rec_layer = InventoryValuationService.create_receipt_cost_layer(product_override, warehouse, rec_entry, Decimal("10.0000"), Decimal("500.0000"))

        # Issue 5 units
        issue_entry = StockLedgerService.record_movement_entry(product_override, warehouse, "ISSUE", Decimal("-5.0000"), Decimal("0.0000"), "ISSUE-RET-1")
        val_res = InventoryValuationService.consume_fifo_layers(product_override, warehouse, Decimal("5.0000"), issue_entry)

        # Sales return of 2 units
        return_layer = InventoryValuationService.process_sales_return(
            product=product_override,
            warehouse=warehouse,
            return_quantity=Decimal("2.0000"),
            original_issue_ledger_entry=issue_entry
        )

        assert return_layer is not None
        assert return_layer.unit_cost == Decimal("500.0000")
        assert return_layer.original_qty == Decimal("2.0000")
        assert return_layer.status == "OPEN"

    def test_fin_inv_010_valuation_control_report(self, setup_sprint48_data):
        user, category, product_default, product_override, warehouse, unit = setup_sprint48_data

        rec_entry = StockLedgerService.record_movement_entry(product_override, warehouse, "RECEIPT", Decimal("15.0000"), Decimal("400.0000"), "REC-REP-1")
        rec_layer = InventoryValuationService.create_receipt_cost_layer(product_override, warehouse, rec_entry, Decimal("15.0000"), Decimal("400.0000"))

        report = InventoryValuationService.get_valuation_control_report(product=product_override, warehouse=warehouse)

        assert report["total_active_layer_qty"] == Decimal("15.0000")
        assert report["total_active_layer_valuation"] == Decimal("6000.00")
        assert "gl_reconciliation" in report

    def test_fin_inv_012_concurrent_inventory_stress_tests(self, setup_sprint48_data):
        user, category, product_default, product_override, warehouse, unit = setup_sprint48_data

        rec_entry = StockLedgerService.record_movement_entry(product_override, warehouse, "RECEIPT", Decimal("100.0000"), Decimal("100.0000"), "STRESS-REC-1")
        rec_layer = InventoryValuationService.create_receipt_cost_layer(product_override, warehouse, rec_entry, Decimal("100.0000"), Decimal("100.0000"))

        errors = []

        def worker_issue(ref_suffix):
            try:
                e = StockLedgerService.record_movement_entry(product_override, warehouse, "ISSUE", Decimal("-10.0000"), Decimal("0.0000"), f"STRESS-ISS-{ref_suffix}")
                InventoryValuationService.consume_fifo_layers(product_override, warehouse, Decimal("10.0000"), e)
            except Exception as ex:
                errors.append(ex)

        threads = [threading.Thread(target=worker_issue, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        rec_layer.refresh_from_db()
        # 100 - (5 * 10) = 50 remaining
        assert rec_layer.remaining_qty == Decimal("50.0000")
        assert len(errors) == 0
