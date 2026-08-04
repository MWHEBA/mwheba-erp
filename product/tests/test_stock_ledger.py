import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from product.models import Product, Warehouse, Category, Unit, StockLedgerEntry
from product.services.stock_ledger_service import StockLedgerService

User = get_user_model()


@pytest.mark.django_db
class TestStockLedgerService:

    @pytest.fixture
    def setup_stock_ledger_data(self):
        user = User.objects.create_user(username="stk_ledger_user", password="password123")
        category = Category.objects.create(name="Electronics", code="ELEC")
        unit = Unit.objects.create(name="Piece")

        product = Product.objects.create(
            name="Super Smart Display 15in",
            sku="PRD-DISP-01",
            category=category,
            unit=unit,
            cost_price=Decimal("1000.00"),
            selling_price=Decimal("1500.00"),
            created_by=user
        )
        warehouse = Warehouse.objects.create(name="Main Central WH", code="WH-CENTRAL", is_active=True)

        return user, product, warehouse, unit

    def test_record_immutable_stock_ledger_entry(self, setup_stock_ledger_data):
        user, product, warehouse, unit = setup_stock_ledger_data

        entry = StockLedgerService.record_movement_entry(
            product=product,
            warehouse=warehouse,
            movement_type="RECEIPT",
            quantity=Decimal("50.0000"),
            unit_cost=Decimal("1000.0000"),
            movement_service_ref="MOV-REC-1001",
            base_uom=unit
        )

        assert entry is not None
        assert entry.quantity == Decimal("50.0000")
        assert entry.unit_cost == Decimal("1000.0000")
        assert entry.total_cost == Decimal("50000.00")

        # Balance check
        calc_bal = StockLedgerService.get_product_stock_balance(product, warehouse)
        assert calc_bal == Decimal("50.0000")
