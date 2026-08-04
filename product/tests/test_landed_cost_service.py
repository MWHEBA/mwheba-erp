import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from product.models import Product, Warehouse, Category, Unit, LandedCostDocument
from product.services.stock_ledger_service import StockLedgerService
from product.services.valuation_service import InventoryValuationService
from product.services.landed_cost_service import LandedCostService

User = get_user_model()


@pytest.mark.django_db
class TestLandedCostService:

    @pytest.fixture
    def setup_landed_cost_data(self):
        user = User.objects.create_user(username="lc_user", password="password123")
        category = Category.objects.create(name="Components", code="COMP")
        unit = Unit.objects.create(name="Piece")

        product = Product.objects.create(
            name="Power Module 500W",
            sku="PRD-PWR-500",
            category=category,
            unit=unit,
            cost_price=Decimal("500.00"),
            selling_price=Decimal("800.00"),
            created_by=user
        )
        warehouse = Warehouse.objects.create(name="Import WH", code="WH-IMPORT", is_active=True)

        return user, product, warehouse, unit

    def test_landed_cost_allocation(self, setup_landed_cost_data):
        user, product, warehouse, unit = setup_landed_cost_data

        # Record receipt
        entry = StockLedgerService.record_movement_entry(
            product=product,
            warehouse=warehouse,
            movement_type="RECEIPT",
            quantity=Decimal("100.0000"),
            unit_cost=Decimal("500.0000"),
            movement_service_ref="MOV-REC-LC-1"
        )
        layer = InventoryValuationService.create_receipt_cost_layer(
            product=product,
            warehouse=warehouse,
            stock_ledger_entry=entry,
            quantity=Decimal("100.0000"),
            unit_cost=Decimal("500.0000")
        )

        # Create Landed Cost Voucher for 5000 EGP customs
        voucher = LandedCostService.create_landed_cost_voucher(
            total_landed_cost=Decimal("5000.00"),
            allocation_method="VALUE",
            user=user
        )

        # Allocate and post landed cost
        res = LandedCostService.allocate_and_post_landed_cost(
            voucher_id=voucher.id,
            receipt_ledger_entry_ids=[entry.id],
            user=user
        )

        assert res['total_asset_portion'] == Decimal("5000.00")
        assert res['total_variance_portion'] == Decimal("0.00")

        layer.refresh_from_db()
        # Unit cost should increase by 5000 / 100 = 50 -> From 500 to 550
        assert layer.unit_cost == Decimal("550.0000")
