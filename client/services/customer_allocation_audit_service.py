import hashlib
import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional
from django.db import models, transaction
from django.utils import timezone

from client.models import Customer, CustomerTransaction, CustomerAllocationAudit
from client.services.allocation_result import AllocationResult

logger = logging.getLogger("client.services.customer_allocation_audit_service")


class CustomerAllocationAuditService:
    """
    FIN-AR-004: Customer Allocation Audit Layer Service (v2.0 Event-Ready & Audit Hash Verification)
    طبقة تدقيق وتوثيق وإثبات توقيع توزيعات سداد المستحقات والتحصيلات للعملاء
    """

    @classmethod
    def generate_evidence_hash(
        cls,
        customer_id: int,
        payment_txn_id: int,
        invoice_txn_id: int,
        allocated_amount: Decimal,
        allocation_date,
        created_at
    ) -> str:
        """
        إنشاء التوقيع المشفر SHA256 لإثبات عدم التلاعب بسجل التوزيع
        """
        raw_data = f"{customer_id}:{payment_txn_id}:{invoice_txn_id}:{allocated_amount}:{allocation_date}:{created_at.isoformat() if hasattr(created_at, 'isoformat') else created_at}"
        return hashlib.sha256(raw_data.encode("utf-8")).hexdigest()

    @classmethod
    def create_audit_entry_from_result(
        cls,
        result: AllocationResult,
        user=None
    ) -> CustomerAllocationAudit:
        """
        إنشاء سجل تدقيق محوكم من كائن نتيجة التوزيع AllocationResult
        """
        now = timezone.now()
        customer = Customer.objects.get(pk=result.customer_id)
        pay_txn = CustomerTransaction.objects.get(pk=result.payment_transaction_id)
        inv_txn = CustomerTransaction.objects.get(pk=result.invoice_transaction_id)

        func_amt = result.functional_amount if result.functional_amount is not None else (result.allocated_amount * result.exchange_rate).quantize(Decimal("0.01"))

        ev_hash = cls.generate_evidence_hash(
            customer_id=result.customer_id,
            payment_txn_id=result.payment_transaction_id,
            invoice_txn_id=result.invoice_transaction_id,
            allocated_amount=result.allocated_amount,
            allocation_date=now.date(),
            created_at=now
        )

        audit = CustomerAllocationAudit(
            customer=customer,
            allocation_reference=result.allocation_reference or f"ALLOC-{pay_txn.transaction_number}->{inv_txn.transaction_number}",
            payment_transaction=pay_txn,
            invoice_transaction=inv_txn,
            source_document_type=result.source_document_type or pay_txn.transaction_type,
            source_document_number=result.source_document_number or pay_txn.transaction_number,
            target_document_type=result.target_document_type or inv_txn.transaction_type,
            target_document_number=result.target_document_number or inv_txn.transaction_number,
            allocation_type=result.allocation_type,
            allocated_amount=result.allocated_amount,
            allocation_currency=result.allocation_currency,
            exchange_rate=result.exchange_rate,
            functional_amount=func_amt,
            realized_fx_difference=result.realized_fx_difference,
            allocation_status="APPLIED",
            allocation_date=now.date(),
            created_by=user,
            evidence_hash=ev_hash
        )
        audit.save()

        logger.info(f"Allocation Audit [{result.allocation_type}] recorded: #{audit.id} ({result.allocated_amount} {result.allocation_currency}, Hash: {ev_hash[:8]}...).")
        return audit

    @classmethod
    def record_allocation_audit(
        cls,
        customer: Customer,
        payment_transaction: CustomerTransaction,
        invoice_transaction: CustomerTransaction,
        allocated_amount: Decimal,
        allocation_type: str = "PAYMENT_TO_INVOICE",
        allocation_currency: str = "EGP",
        exchange_rate: Decimal = Decimal("1.000000"),
        functional_amount: Optional[Decimal] = None,
        realized_fx_difference: Decimal = Decimal("0.00"),
        allocation_reference: Optional[str] = None,
        user=None
    ) -> CustomerAllocationAudit:
        """
        Legacy direct record adapter wrapping create_audit_entry_from_result
        """
        result = AllocationResult(
            customer_id=customer.id,
            payment_transaction_id=payment_transaction.id,
            invoice_transaction_id=invoice_transaction.id,
            allocated_amount=allocated_amount,
            allocation_type=allocation_type,
            allocation_currency=allocation_currency,
            exchange_rate=exchange_rate,
            functional_amount=functional_amount,
            realized_fx_difference=realized_fx_difference,
            source_document_type=payment_transaction.transaction_type,
            source_document_number=payment_transaction.transaction_number,
            target_document_type=invoice_transaction.transaction_type,
            target_document_number=invoice_transaction.transaction_number,
            allocation_reference=allocation_reference
        )
        return cls.create_audit_entry_from_result(result, user=user)

    @classmethod
    def reverse_allocation_audit(
        cls,
        audit_id: int,
        reason: str,
        user=None
    ) -> CustomerAllocationAudit:
        """
        تسجيل حدث عكس التوزيع (Reversal Audit) وتوصيل التوزيع المعكوس عبر FK reversed_audit
        """
        with transaction.atomic():
            orig_audit = CustomerAllocationAudit.objects.select_for_update().get(pk=audit_id)
            if orig_audit.allocation_status == "REVERSED":
                raise ValueError(f"Allocation Audit #{audit_id} is already reversed.")

            now = timezone.now()

            # 1. Restore subledger transaction open balances
            pay_txn = CustomerTransaction.objects.select_for_update().get(pk=orig_audit.payment_transaction_id)
            inv_txn = CustomerTransaction.objects.select_for_update().get(pk=orig_audit.invoice_transaction_id)

            pay_txn.open_amount += orig_audit.allocated_amount
            pay_txn.open_amount_functional = pay_txn.open_amount
            if pay_txn.exchange_rate and pay_txn.exchange_rate > Decimal("0.000000"):
                pay_txn.open_amount_foreign = (pay_txn.open_amount / pay_txn.exchange_rate).quantize(Decimal("0.01"))
            pay_txn.status = "OPEN" if pay_txn.open_amount >= pay_txn.functional_amount else "PARTIAL"
            pay_txn.save()

            inv_txn.open_amount += orig_audit.allocated_amount
            inv_txn.open_amount_functional = inv_txn.open_amount
            if inv_txn.exchange_rate and inv_txn.exchange_rate > Decimal("0.000000"):
                inv_txn.open_amount_foreign = (inv_txn.open_amount / inv_txn.exchange_rate).quantize(Decimal("0.01"))
            inv_txn.status = "OPEN" if inv_txn.open_amount >= inv_txn.functional_amount else "PARTIAL"
            inv_txn.save()

            rev_audit = CustomerAllocationAudit(
                customer=orig_audit.customer,
                allocation_reference=f"REV-{orig_audit.allocation_reference}",
                payment_transaction=orig_audit.payment_transaction,
                invoice_transaction=orig_audit.invoice_transaction,
                source_document_type=orig_audit.source_document_type,
                source_document_number=orig_audit.source_document_number,
                target_document_type=orig_audit.target_document_type,
                target_document_number=orig_audit.target_document_number,
                allocation_type=orig_audit.allocation_type,
                allocated_amount=-orig_audit.allocated_amount,
                allocation_currency=orig_audit.allocation_currency,
                exchange_rate=orig_audit.exchange_rate,
                functional_amount=-orig_audit.functional_amount,
                realized_fx_difference=-orig_audit.realized_fx_difference,
                allocation_status="REVERSED",
                reversed_audit=orig_audit,
                allocation_date=now.date(),
                created_by=user,
                evidence_hash=cls.generate_evidence_hash(
                    customer_id=orig_audit.customer.id,
                    payment_txn_id=orig_audit.payment_transaction.id,
                    invoice_txn_id=orig_audit.invoice_transaction.id,
                    allocated_amount=-orig_audit.allocated_amount,
                    allocation_date=now.date(),
                    created_at=now
                )
            )
            rev_audit.save()

            logger.info(f"Allocation Audit #{audit_id} reversed via Reversal Audit #{rev_audit.id} (Reason: {reason}).")
            return rev_audit

    @classmethod
    def verify_audit_integrity(cls, audit_id: int) -> bool:
        """
        التحقق من صحة وقوة التوقيع المشفر SHA256 لسجل التوزيع
        """
        audit = CustomerAllocationAudit.objects.get(pk=audit_id)
        expected_hash = cls.generate_evidence_hash(
            customer_id=audit.customer_id,
            payment_txn_id=audit.payment_transaction_id,
            invoice_txn_id=audit.invoice_transaction_id,
            allocated_amount=audit.allocated_amount,
            allocation_date=audit.allocation_date,
            created_at=audit.created_at
        )
        return audit.evidence_hash == expected_hash

    @classmethod
    def get_customer_allocation_history(cls, customer_id: int, start_date=None, end_date=None) -> models.QuerySet:
        """
        تقرير تتبع وتدقيق سجل توزيعات العميل خلال فترة محددة
        """
        qs = CustomerAllocationAudit.objects.filter(customer_id=customer_id)
        if start_date:
            qs = qs.filter(allocation_date__gte=start_date)
        if end_date:
            qs = qs.filter(allocation_date__lte=end_date)
        return qs.select_related("customer", "payment_transaction", "invoice_transaction", "created_by")

    @classmethod
    def get_invoice_settlement_history(cls, invoice_transaction_id: int) -> models.QuerySet:
        """
        استعلام سجل الدفعات والإشعارات المخصصة لسداد فاتورة محددة
        """
        return CustomerAllocationAudit.objects.filter(
            invoice_transaction_id=invoice_transaction_id
        ).select_related("payment_transaction", "created_by").order_by("-allocation_date", "-id")

    @classmethod
    def get_payment_utilization_report(cls, payment_transaction_id: int) -> models.QuerySet:
        """
        استعلام توزيعات واستخدام دفعة أو إشعار محدد بين الفواتير المختلفة
        """
        return CustomerAllocationAudit.objects.filter(
            payment_transaction_id=payment_transaction_id
        ).select_related("invoice_transaction", "created_by").order_by("-allocation_date", "-id")
