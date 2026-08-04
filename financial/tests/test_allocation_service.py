import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from financial.models import PaymentAllocation
from financial.services import AllocationService
from financial.exceptions import FinancialCoreError

User = get_user_model()


@pytest.mark.django_db
class TestAllocationService:

    @pytest.fixture
    def setup_allocation_data(self):
        user = User.objects.create_user(username="alloc_user", password="password123")
        return user

    def test_create_decoupled_allocation(self, setup_allocation_data):
        user = setup_allocation_data

        alloc = AllocationService.create_allocation(
            debit_document_type="SALE_INVOICE",
            debit_document_id="INV-2025-001",
            credit_document_type="CUSTOMER_PAYMENT",
            credit_document_id="PAY-2025-001",
            subledger_type="customer",
            entity_id=10,
            amount_to_allocate=Decimal("1500.00"),
            debit_doc_total_amount=Decimal("2000.00"),
            credit_doc_total_amount=Decimal("2000.00"),
            user=user
        )

        assert alloc is not None
        assert alloc.allocated_amount == Decimal("1500.00")
        assert alloc.subledger_type == "customer"
        assert alloc.entity_id == 10

        # Outstanding calculation check
        outstanding = AllocationService.get_debit_document_outstanding_balance(
            "SALE_INVOICE", "INV-2025-001", Decimal("2000.00")
        )
        assert outstanding == Decimal("500.00")

        # Unallocated calculation check
        unallocated = AllocationService.get_credit_document_unallocated_balance(
            "CUSTOMER_PAYMENT", "PAY-2025-001", Decimal("2000.00")
        )
        assert unallocated == Decimal("500.00")

    def test_over_allocation_blocked(self, setup_allocation_data):
        user = setup_allocation_data

        AllocationService.create_allocation(
            debit_document_type="SALE_INVOICE",
            debit_document_id="INV-2025-002",
            credit_document_type="CUSTOMER_PAYMENT",
            credit_document_id="PAY-2025-002",
            subledger_type="customer",
            entity_id=10,
            amount_to_allocate=Decimal("800.00"),
            debit_doc_total_amount=Decimal("1000.00"),
            credit_doc_total_amount=Decimal("1000.00"),
            user=user
        )

        # Attempt to allocate 500 when outstanding is only 200
        with pytest.raises(FinancialCoreError) as exc_info:
            AllocationService.create_allocation(
                debit_document_type="SALE_INVOICE",
                debit_document_id="INV-2025-002",
                credit_document_type="CUSTOMER_PAYMENT",
                credit_document_id="PAY-2025-003",
                subledger_type="customer",
                entity_id=10,
                amount_to_allocate=Decimal("500.00"),
                debit_doc_total_amount=Decimal("1000.00"),
                credit_doc_total_amount=Decimal("1000.00"),
                user=user
            )
        assert "ALLOCATION_EXCEEDED" in str(exc_info.value)
