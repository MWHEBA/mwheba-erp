import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from product.models import Product, Category, Unit, Warehouse, Stock
from product.models.inventory_reservation import InventoryReservation, InventoryReservationAudit
from product.services.inventory_availability_service import InventoryAvailabilityService
from product.services.atp_service import ATPService
from product.services.inventory_reservation_service import InventoryReservationService
from sale.services.sales_service import SalesService
from financial.exceptions import FinancialCoreError

User = get_user_model()


@pytest.mark.django_db(transaction=True)
class TestFINSAL003InventoryReservation:

    @pytest.fixture
    def setup_reservation_data(self):
        user = User.objects.create_user(username="res_user1", email="res1@example.com", password="password123")
        from financial.models import AccountingPeriod
        today = timezone.now().date()
        AccountingPeriod.objects.get_or_create(
            name=f"ResPeriod_{today.year}_{today.month}",
            start_date=today.replace(day=1),
            end_date=today.replace(day=28),
            defaults={"status": "open"}
        )
        from client.models import Customer
        customer = Customer.objects.create(name="Delta Electronics", code="CUST-RES-001", credit_limit=Decimal("100000.00"))

        from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
        asset_type, _ = AccountType.objects.get_or_create(code="ASSET", defaults={"name": "Assets", "category": "ASSET"})
        exp_type, _ = AccountType.objects.get_or_create(code="EXPENSE", defaults={"name": "Expenses", "category": "EXPENSE"})

        ChartOfAccounts.objects.get_or_create(code="10400", defaults={"name": "Inventory Asset Account", "account_type": asset_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="50100", defaults={"name": "Cost of Goods Sold Account", "account_type": exp_type, "is_active": True})

        category = Category.objects.create(name="Components")
        unit = Unit.objects.create(name="PCS")
        product = Product.objects.create(name="Microcontroller IC", category=category, unit=unit, cost_price=Decimal("10.00"), selling_price=Decimal("15.00"), created_by=user)
        warehouse = Warehouse.objects.create(code="WH-RES-01", name="Reservation Warehouse", is_active=True)

        # Create physical stock of 100 units
        Stock.objects.create(product=product, warehouse=warehouse, quantity=100)

        return user, customer, product, warehouse

    def test_soft_reservation_creation_and_atp_validation(self, setup_reservation_data):
        user, customer, product, warehouse = setup_reservation_data

        # Verify initial ATP is 100
        atp_before = ATPService.get_atp_quantity(warehouse.id, product.id)
        assert atp_before == Decimal("100.0000")

        # Create SO for 40 units
        items_data = [{"product": product, "ordered_qty": Decimal("40.0000"), "unit_price": Decimal("15.00")}]
        so = SalesService.create_sales_order(customer=customer, warehouse=warehouse, order_date=timezone.now().date(), items_data=items_data, user=user)

        # Verify InventoryReservation created with status ACTIVE
        res = InventoryReservation.objects.get(sales_order=so)
        assert res.quantity == Decimal("40.0000")
        assert res.reservation_status == "ACTIVE"

        # Verify net ATP reduced to 60 (Physical stock remains 100)
        on_hand = InventoryAvailabilityService.get_on_hand_quantity(warehouse.id, product.id)
        atp_after = ATPService.get_atp_quantity(warehouse.id, product.id)
        assert on_hand == Decimal("100.0000")
        assert atp_after == Decimal("60.0000")

    def test_overselling_prevention(self, setup_reservation_data):
        user, customer, product, warehouse = setup_reservation_data

        # Attempt SO for 150 units (Exceeds 100 ATP)
        items_data = [{"product": product, "ordered_qty": Decimal("150.0000"), "unit_price": Decimal("15.00")}]
        with pytest.raises(FinancialCoreError, match="Overselling Error"):
            SalesService.create_sales_order(customer=customer, warehouse=warehouse, order_date=timezone.now().date(), items_data=items_data, user=user)

    def test_partial_delivery_reservation_consumption(self, setup_reservation_data):
        user, customer, product, warehouse = setup_reservation_data

        # SO for 40 units
        items_data = [{"product": product, "ordered_qty": Decimal("40.0000"), "unit_price": Decimal("15.00")}]
        so = SalesService.create_sales_order(customer=customer, warehouse=warehouse, order_date=timezone.now().date(), items_data=items_data, user=user)

        # Deliver partial 15 units
        so_item = so.items.first()
        deliv_items = [{"so_item_id": so_item.id, "delivered_qty": Decimal("15.0000")}]
        dn = SalesService.deliver_goods(so_id=so.id, delivery_date=timezone.now().date(), items_data=deliv_items, user=user)

        # Reservation status should be PARTIALLY_FULFILLED
        res = InventoryReservation.objects.get(sales_order=so)
        assert res.reservation_status == "PARTIALLY_FULFILLED"
        assert res.fulfilled_quantity == Decimal("15.0000")
        assert res.remaining_reserved_quantity == Decimal("25.0000")

    def test_reservation_cancellation_release(self, setup_reservation_data):
        user, customer, product, warehouse = setup_reservation_data

        # SO for 30 units
        items_data = [{"product": product, "ordered_qty": Decimal("30.0000"), "unit_price": Decimal("15.00")}]
        so = SalesService.create_sales_order(customer=customer, warehouse=warehouse, order_date=timezone.now().date(), items_data=items_data, user=user)

        # Release reservation
        released = InventoryReservationService.release_reservation_for_sales_order(so.id, reason="Customer cancelled order", user=user)
        assert len(released) == 1
        assert released[0].reservation_status == "CANCELLED"

        # ATP restored to 100
        atp = ATPService.get_atp_quantity(warehouse.id, product.id)
        assert atp == Decimal("100.0000")

    def test_reservation_audit_immutability(self, setup_reservation_data):
        user, customer, product, warehouse = setup_reservation_data

        items_data = [{"product": product, "ordered_qty": Decimal("20.0000"), "unit_price": Decimal("15.00")}]
        so = SalesService.create_sales_order(customer=customer, warehouse=warehouse, order_date=timezone.now().date(), items_data=items_data, user=user)

        audit = InventoryReservationAudit.objects.filter(reservation__sales_order=so).first()
        assert audit is not None

        # Attempt to edit audit record must raise ValueError
        with pytest.raises(ValueError, match="INSERT-ONLY"):
            audit.reason = "Modified"
            audit.save()

        # Attempt to delete audit record must raise ValueError
        with pytest.raises(ValueError, match="cannot be deleted"):
            audit.delete()
