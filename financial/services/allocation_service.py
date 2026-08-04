"""
AllocationService - محرك تخصيص السداد المحكوم بدعم حماية التزامن الذري (FIN-SUB-001 & FIN-SUB-002)
يدير التخصيص المستقل دون اعتماد على نماذج المبيعات أو المشتريات المباشرة.
"""

import logging
import uuid
from decimal import Decimal
from typing import Dict, Any, Optional
from django.db import transaction, models
from django.utils import timezone
from django.db.models import Sum

from financial.models.allocation import PaymentAllocation
from financial.exceptions import FinancialCoreError

logger = logging.getLogger("financial.allocation_service")


class AllocationService:
    """
    خدمة محرك تخصيص السداد (Decoupled Allocation Engine)
    """

    @classmethod
    def generate_allocation_number(cls) -> str:
        date_prefix = timezone.now().strftime("%Y%m%d")
        unique_suffix = str(uuid.uuid4()).split('-')[0].upper()
        return f"ALLOC-{date_prefix}-{unique_suffix}"

    @classmethod
    def get_debit_document_outstanding_balance(
        cls,
        debit_document_type: str,
        debit_document_id: str,
        doc_total_amount: Decimal
    ) -> Decimal:
        """
        حساب رصيد مستند المدين المستحق الحالي (Invoice / Bill Outstanding Balance)
        Outstanding = Total Amount - SUM(Allocated Amounts)
        """
        total_allocated = PaymentAllocation.objects.filter(
            debit_document_type=debit_document_type,
            debit_document_id=str(debit_document_id)
        ).aggregate(total=Sum('allocated_amount'))['total'] or Decimal('0.00')

        outstanding = doc_total_amount - total_allocated
        return max(Decimal('0.00'), outstanding)

    @classmethod
    def get_credit_document_unallocated_balance(
        cls,
        credit_document_type: str,
        credit_document_id: str,
        doc_total_amount: Decimal
    ) -> Decimal:
        """
        حساب المبلغ الدائن غير المخصص الحالي (Unallocated Payment / Credit Balance)
        Unallocated = Total Amount - SUM(Allocated Amounts)
        """
        total_allocated = PaymentAllocation.objects.filter(
            credit_document_type=credit_document_type,
            credit_document_id=str(credit_document_id)
        ).aggregate(total=Sum('allocated_amount'))['total'] or Decimal('0.00')

        unallocated = doc_total_amount - total_allocated
        return max(Decimal('0.00'), unallocated)

    @classmethod
    def create_allocation(
        cls,
        debit_document_type: str,
        debit_document_id: str,
        credit_document_type: str,
        credit_document_id: str,
        subledger_type: str,
        entity_id: int,
        amount_to_allocate: Decimal,
        debit_doc_total_amount: Decimal,
        credit_doc_total_amount: Decimal,
        user,
        allocation_date: Optional[Any] = None
    ) -> PaymentAllocation:
        """
        إنشاء تخصيص جديد محكوم وحمايته ضد حوادث التخصيص المتزامن عبر select_for_update (FIN-SUB-002)
        """
        if amount_to_allocate <= Decimal('0.00'):
            raise FinancialCoreError("Allocated amount must be greater than zero.")

        with transaction.atomic():
            # (FIN-SUB-004 Lock Hardening): Lock parent document rows to guarantee lock acquisition when zero allocation records exist
            if debit_document_type == "SALE_INVOICE":
                try:
                    from sale.models import Sale
                    Sale.objects.select_for_update().filter(pk=debit_document_id).first()
                except Exception:
                    pass
            elif debit_document_type == "PURCHASE_BILL":
                try:
                    from purchase.models import Purchase
                    Purchase.objects.select_for_update().filter(pk=debit_document_id).first()
                except Exception:
                    pass

            if credit_document_type == "CUSTOMER_PAYMENT":
                try:
                    from sale.models import SalePayment
                    SalePayment.objects.select_for_update().filter(pk=credit_document_id).first()
                except Exception:
                    pass

            # قفل سجلات التخصيص الحالية لمنع التجاوزات المتزامنة (FIN-SUB-002 & FIN-SUB-004 Allocation Concurrency Lock)
            existing_allocs = PaymentAllocation.objects.select_for_update().filter(
                models.Q(debit_document_type=debit_document_type, debit_document_id=str(debit_document_id)) |
                models.Q(credit_document_type=credit_document_type, credit_document_id=str(credit_document_id))
            )
            list(existing_allocs)

            # فحص رصيد المدين المتبقي
            outstanding = cls.get_debit_document_outstanding_balance(
                debit_document_type, debit_document_id, debit_doc_total_amount
            )
            if amount_to_allocate > outstanding:
                raise FinancialCoreError(
                    f"ALLOCATION_EXCEEDED: Cannot allocate {amount_to_allocate}. Outstanding balance is {outstanding}."
                )

            # فحص رصيد الدائن المتبقي
            unallocated = cls.get_credit_document_unallocated_balance(
                credit_document_type, credit_document_id, credit_doc_total_amount
            )
            if amount_to_allocate > unallocated:
                raise FinancialCoreError(
                    f"ALLOCATION_EXCEEDED: Cannot allocate {amount_to_allocate}. Unallocated balance is {unallocated}."
                )

            allocation_num = cls.generate_allocation_number()

            allocation = PaymentAllocation.objects.create(
                allocation_number=allocation_num,
                debit_document_type=debit_document_type,
                debit_document_id=str(debit_document_id),
                credit_document_type=credit_document_type,
                credit_document_id=str(credit_document_id),
                subledger_type=subledger_type,
                entity_id=entity_id,
                allocated_amount=amount_to_allocate,
                allocation_date=allocation_date or timezone.now().date(),
                created_by=user
            )

            logger.info(
                f"Payment Allocation created successfully: {allocation_num} "
                f"({amount_to_allocate} for {subledger_type}#{entity_id})"
            )

            return allocation

    @classmethod
    def cancel_allocation(cls, allocation_id: int, user) -> bool:
        """
        إلغاء تخصيص سداد قائم
        """
        with transaction.atomic():
            allocation = PaymentAllocation.objects.select_for_update().get(pk=allocation_id)
            alloc_num = allocation.allocation_number
            allocation.delete()
            logger.info(f"Payment Allocation #{alloc_num} cancelled by user {user}")
            return True
