import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from customer.models import Customer, CustomerTransaction, CustomerAllocationAudit
from customer.services.customer_subledger_service import CustomerSubledgerService
from financial.models import ChartOfAccounts, AccountType

User = get_user_model()


@pytest.mark.django_db(transaction=True)
class TestFINAR003CustomerOpenItems:

    @pytest.fixture
    def setup_customer_open_items(self):
        user = User.objects.create_user(username="ar_open_user3", password="password123")
        asset_type, _ = AccountType.objects.get_or_create(code="ASSET", defaults={"name": "Asset", "category": "ASSET"})
        ar_acc = ChartOfAccounts.objects.create(code="11010_CUST1", name="Customer 1 AR Account", account_type=asset_type, is_active=True)

        customer = Customer.objects.create(
            name="Al-Ahram Printing Co",
            code="CUST-AR-001",
            financial_account=ar_acc,
            credit_limit=Decimal("100000.00")
        )
        return user, customer, ar_acc

    def test_fin_ar_003_register_and_query_open_items(self, setup_customer_open_items):
        user, customer, ar_acc = setup_customer_open_items

        inv_txn = CustomerSubledgerService.register_open_item_transaction(
            customer=customer,
            transaction_type="INVOICE",
            transaction_number="INV-2026-001",
            issue_date=timezone.now().date(),
            due_date=timezone.now().date(),
            currency="EGP",
            functional_amount=Decimal("10000.00")
        )
        assert inv_txn.status == "OPEN"
        assert inv_txn.open_amount == Decimal("10000.00")

        open_items = CustomerSubledgerService.get_open_items(customer.id)
        assert open_items.count() == 1
        assert open_items.first().transaction_number == "INV-2026-001"

    def test_fin_ar_004_payment_allocation_and_audit(self, setup_customer_open_items):
        user, customer, ar_acc = setup_customer_open_items

        inv_txn = CustomerSubledgerService.register_open_item_transaction(
            customer=customer,
            transaction_type="INVOICE",
            transaction_number="INV-2026-002",
            issue_date=timezone.now().date(),
            due_date=timezone.now().date(),
            currency="EGP",
            functional_amount=Decimal("5000.00")
        )

        pay_txn = CustomerSubledgerService.register_open_item_transaction(
            customer=customer,
            transaction_type="PAYMENT",
            transaction_number="PAY-2026-002",
            issue_date=timezone.now().date(),
            due_date=timezone.now().date(),
            currency="EGP",
            functional_amount=Decimal("5000.00")
        )

        allocation_res = CustomerSubledgerService.allocate_payment(
            customer_id=customer.id,
            payment_transaction_id=pay_txn.id,
            invoice_transaction_id=inv_txn.id,
            allocated_amount=Decimal("3000.00"),
            user=user
        )

        assert allocation_res["allocated_amount"] == Decimal("3000.00")
        assert allocation_res["invoice_remaining"] == Decimal("2000.00")
        assert "evidence_hash" in allocation_res

        inv_txn.refresh_from_db()
        pay_txn.refresh_from_db()

        assert inv_txn.status == "PARTIAL"
        assert pay_txn.status == "PARTIAL"
        assert CustomerAllocationAudit.objects.filter(customer=customer).count() == 1
