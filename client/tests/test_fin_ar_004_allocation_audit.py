import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from client.models import Customer, CustomerTransaction, CustomerAllocationAudit
from client.services.customer_subledger_service import CustomerSubledgerService
from client.services.customer_allocation_audit_service import CustomerAllocationAuditService

User = get_user_model()


@pytest.mark.django_db(transaction=True)
class TestFINAR004CustomerAllocationAudit:

    @pytest.fixture
    def setup_allocation_audit_data(self):
        user = User.objects.create_user(username="alloc_auditor", email="alloc@example.com", password="password123")
        customer = Customer.objects.create(name="Delta Trading Co.", code="CUST-AUDIT-01")

        # Create Invoice Transaction (100,000 EGP)
        inv_txn = CustomerSubledgerService.register_open_item_transaction(
            customer=customer,
            transaction_type="INVOICE",
            transaction_number="INV-AUD-001",
            issue_date=timezone.now().date(),
            due_date=timezone.now().date(),
            functional_amount=Decimal("100000.00")
        )

        # Create Payment Transaction (40,000 EGP)
        pay_txn = CustomerSubledgerService.register_open_item_transaction(
            customer=customer,
            transaction_type="PAYMENT",
            transaction_number="PAY-AUD-001",
            issue_date=timezone.now().date(),
            due_date=timezone.now().date(),
            functional_amount=Decimal("40000.00")
        )

        return user, customer, inv_txn, pay_txn

    def test_partial_payment_allocation_audit(self, setup_allocation_audit_data):
        user, customer, inv_txn, pay_txn = setup_allocation_audit_data

        # Allocate 40,000 EGP payment against 100,000 EGP invoice
        res = CustomerSubledgerService.allocate_payment(
            customer_id=customer.id,
            payment_transaction_id=pay_txn.id,
            invoice_transaction_id=inv_txn.id,
            allocated_amount=Decimal("40000.00"),
            user=user
        )

        assert res["payment_status"] == "CLOSED"
        assert res["invoice_status"] == "PARTIAL"
        assert res["evidence_hash"] is not None

        # Verify CustomerAllocationAudit record
        audit = CustomerAllocationAudit.objects.get(pk=res["audit_id"])
        assert audit.customer == customer
        assert audit.payment_transaction == pay_txn
        assert audit.invoice_transaction == inv_txn
        assert audit.allocated_amount == Decimal("40000.00")
        assert audit.allocation_type == "PAYMENT_TO_INVOICE"
        assert audit.allocation_status == "APPLIED"

    def test_advance_payment_allocation_audit(self, setup_allocation_audit_data):
        user, customer, inv_txn, _ = setup_allocation_audit_data

        adv_txn = CustomerSubledgerService.register_open_item_transaction(
            customer=customer,
            transaction_type="ADVANCE",
            transaction_number="ADV-AUD-001",
            issue_date=timezone.now().date(),
            due_date=timezone.now().date(),
            functional_amount=Decimal("30000.00")
        )

        res = CustomerSubledgerService.allocate_payment(
            customer_id=customer.id,
            payment_transaction_id=adv_txn.id,
            invoice_transaction_id=inv_txn.id,
            allocated_amount=Decimal("30000.00"),
            user=user
        )

        audit = CustomerAllocationAudit.objects.get(pk=res["audit_id"])
        assert audit.allocation_type == "ADVANCE_TO_INVOICE"
        assert audit.allocated_amount == Decimal("30000.00")

    def test_allocation_reversal_audit_immutability(self, setup_allocation_audit_data):
        user, customer, inv_txn, pay_txn = setup_allocation_audit_data

        res = CustomerSubledgerService.allocate_payment(
            customer_id=customer.id,
            payment_transaction_id=pay_txn.id,
            invoice_transaction_id=inv_txn.id,
            allocated_amount=Decimal("40000.00"),
            user=user
        )

        rev_audit = CustomerAllocationAuditService.reverse_allocation_audit(
            audit_id=res["audit_id"],
            reason="Erroneous payment matching",
            user=user
        )

        assert rev_audit.allocation_status == "REVERSED"
        assert rev_audit.allocated_amount == Decimal("-40000.00")

        # Test Immutability Guards (Single & Bulk ORM operations)
        orig_audit = CustomerAllocationAudit.objects.get(pk=res["audit_id"])
        with pytest.raises(ValueError, match="INSERT-ONLY"):
            orig_audit.allocated_amount = Decimal("50000.00")
            orig_audit.save()

        with pytest.raises(ValueError, match="cannot be deleted"):
            orig_audit.delete()

        with pytest.raises(ValueError, match="Bulk UPDATE operations"):
            CustomerAllocationAudit.objects.filter(id=res["audit_id"]).update(allocated_amount=Decimal("50000.00"))

        with pytest.raises(ValueError, match="Bulk DELETE operations"):
            CustomerAllocationAudit.objects.filter(id=res["audit_id"]).delete()
        assert rev_audit.reversed_audit == CustomerAllocationAudit.objects.get(pk=res["audit_id"])
        assert CustomerAllocationAudit.objects.filter(customer=customer).count() == 2

    def test_immutability_protection_guards(self, setup_allocation_audit_data):
        user, customer, inv_txn, pay_txn = setup_allocation_audit_data

        res = CustomerSubledgerService.allocate_payment(
            customer_id=customer.id,
            payment_transaction_id=pay_txn.id,
            invoice_transaction_id=inv_txn.id,
            allocated_amount=Decimal("40000.00"),
            user=user
        )

        audit = CustomerAllocationAudit.objects.get(pk=res["audit_id"])

        # Attempt to modify existing audit record must raise ValueError
        with pytest.raises(ValueError, match="INSERT-ONLY"):
            audit.allocation_status = "REVERSED"
            audit.save()

        # Attempt to delete existing audit record must raise ValueError
        with pytest.raises(ValueError, match="cannot be deleted"):
            audit.delete()
