import pytest
import uuid
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from client.models import Customer, CustomerTransaction
from client.services.customer_subledger_service import CustomerSubledgerService
from financial.models import ChartOfAccounts, AccountType

User = get_user_model()


@pytest.mark.django_db(transaction=True)
class TestMultiCurrencyComplexAllocations:

    @pytest.fixture
    def setup_fx_data(self):
        uid = uuid.uuid4().hex[:6]
        user = User.objects.create_user(username=f"fx_user_{uid}", email=f"fx_{uid}@example.com", password="password123")
        from financial.models import AccountingPeriod
        today = timezone.now().date()
        AccountingPeriod.objects.get_or_create(
            name=f"Period_{today.year}_{today.month}",
            start_date=today.replace(day=1),
            end_date=today.replace(day=28),
            defaults={"status": "open"}
        )

        customer = Customer.objects.create(name=f"FX Trade Customer {uid}", code=f"CUST-FX-{uid}", credit_limit=Decimal("1000000.00"))
        return user, customer

    def test_four_step_partial_fx_payment_allocations(self, setup_fx_data):
        user, customer = setup_fx_data

        # 1. Open USD Invoice: $10,000 @ 48.00 EGP = 480,000 EGP
        inv_txn = CustomerSubledgerService.register_open_item_transaction(
            customer=customer,
            transaction_type="INVOICE",
            transaction_number=f"INV-USD-{uuid.uuid4().hex[:6]}",
            issue_date=timezone.now().date(),
            due_date=timezone.now().date(),
            currency="USD",
            foreign_amount=Decimal("10000.00"),
            exchange_rate=Decimal("48.000000"),
            functional_amount=Decimal("480000.00")
        )

        rates = [Decimal("48.500000"), Decimal("49.000000"), Decimal("50.000000"), Decimal("51.000000")]
        cumulative_fx = Decimal("0.00")

        for idx, rate in enumerate(rates):
            pay_txn = CustomerSubledgerService.register_open_item_transaction(
                customer=customer,
                transaction_type="PAYMENT",
                transaction_number=f"PAY-USD-00{idx+1}",
                issue_date=timezone.now().date(),
                due_date=timezone.now().date(),
                currency="USD",
                foreign_amount=Decimal("2500.00"),
                exchange_rate=rate,
                functional_amount=(Decimal("2500.00") * rate).quantize(Decimal("0.01"))
            )

            inv_txn.refresh_from_db()
            alloc_amt = min((Decimal("2500.00") * rate).quantize(Decimal("0.01")), inv_txn.open_amount)
            res = CustomerSubledgerService.allocate_payment(
                customer_id=customer.id,
                payment_transaction_id=pay_txn.id,
                invoice_transaction_id=inv_txn.id,
                allocated_amount=alloc_amt,
                user=user
            )
            cumulative_fx += res["realized_fx_difference"]

        inv_txn.refresh_from_db()
        assert inv_txn.open_amount == Decimal("0.00")
        assert inv_txn.open_amount_functional == Decimal("0.00")
        assert inv_txn.open_amount_foreign == Decimal("0.00")
        assert inv_txn.status == "CLOSED"
        assert cumulative_fx > Decimal("0.00")
