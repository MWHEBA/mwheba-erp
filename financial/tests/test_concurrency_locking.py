import pytest
import uuid
import concurrent.futures
from decimal import Decimal
from django.utils import timezone
from django.db import connections, transaction
from django.contrib.auth import get_user_model

from product.models import Product, Category, Unit, Warehouse, Stock
from client.models import Customer
from client.services.credit_exposure_service import CreditExposureService
from client.services.customer_subledger_service import CustomerSubledgerService
from product.services.inventory_reservation_service import InventoryReservationService
from financial.models import ChartOfAccounts, AccountType

User = get_user_model()


@pytest.mark.django_db(transaction=True)
class TestConcurrencyLocking:

    @pytest.fixture
    def setup_concurrency_data(self):
        uid = uuid.uuid4().hex[:6]
        user = User.objects.create_user(username=f"conc_user_{uid}", email=f"conc_{uid}@example.com", password="password123")
        from financial.models import AccountingPeriod
        today = timezone.now().date()
        AccountingPeriod.objects.get_or_create(
            name=f"Period_{today.year}_{today.month}",
            start_date=today.replace(day=1),
            end_date=today.replace(day=28),
            defaults={"status": "open"}
        )

        from client.models import CustomerCreditProfile
        customer = Customer.objects.create(name=f"Concurrency Customer {uid}", code=f"CUST-CONC-{uid}", credit_limit=Decimal("100000.00"))
        CustomerCreditProfile.objects.create(customer=customer, credit_limit=Decimal("100000.00"))

        category = Category.objects.create(name=f"Conc Category {uid}")
        unit = Unit.objects.create(name=f"PCS-{uid}")
        product = Product.objects.create(name=f"Conc Product {uid}", category=category, unit=unit, cost_price=Decimal("100.00"), selling_price=Decimal("200.00"), created_by=user)
        warehouse = Warehouse.objects.create(code=f"WH-CONC-{uid}", name=f"Conc Warehouse {uid}", is_active=True)
        Stock.objects.create(product=product, warehouse=warehouse, quantity=50)

        return user, customer, product, warehouse

    def test_concurrent_credit_exposure_evaluation(self, setup_concurrency_data):
        user, customer, product, warehouse = setup_concurrency_data

        def worker_task(customer_id):
            connections.close_all()
            with transaction.atomic():
                decision = CreditExposureService.evaluate_credit_check(customer_id, requested_amount=Decimal("10000.00"))
                return decision.decision.value if hasattr(decision.decision, 'value') else str(decision.decision)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future1 = executor.submit(worker_task, customer.id)
            future2 = executor.submit(worker_task, customer.id)

            res1 = future1.result()
            res2 = future2.result()

        assert res1 is not None
        assert res2 is not None

    def test_concurrent_inventory_reservation(self, setup_concurrency_data):
        user, customer, product, warehouse = setup_concurrency_data
        from sale.services.sales_service import SalesService

        # Create 2 sales orders for the product
        items = [{"product": product, "ordered_qty": Decimal("10.0000"), "unit_price": Decimal("200.00")}]
        so1 = SalesService.create_sales_order(customer=customer, warehouse=warehouse, order_date=timezone.now().date(), items_data=items, user=user)
        so2 = SalesService.create_sales_order(customer=customer, warehouse=warehouse, order_date=timezone.now().date(), items_data=items, user=user)

        def reservation_worker(so_id):
            connections.close_all()
            try:
                res = InventoryReservationService.reserve_sales_order_lines(sales_order_id=so_id, user=user)
                return len(res)
            except Exception as e:
                return str(e)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(reservation_worker, so1.id)
            f2 = executor.submit(reservation_worker, so2.id)

            r1 = f1.result()
            r2 = f2.result()

        assert r1 == 1
        assert r2 == 1
