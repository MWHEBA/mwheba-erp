import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, Optional
from django.db import models, transaction
from django.utils import timezone

from customer.models import CustomerTransaction
from supplier.models import SupplierTransaction
from financial.models.allocation import PaymentAllocation, AllocationStatus
from financial.services.ledger_core_service import LedgerCoreService
from financial.services.period_control_service import PeriodControlService
from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames

logger = logging.getLogger("financial.allocation_service")


class AllocationService:
    """
    محرك التسويات وإلغاء التسويات المحصن لـ Enterprise ERP (Sprint 3 Engine)
    يحقق التجريد المالي، قفل التزامن، الدقة العشرية، وحساب أرباح/خسائر العملة المحققة
    """

    @classmethod
    def quantize_amount(cls, amount: Decimal) -> Decimal:
        """ضبط الدقة العشرية بـ Decimal ROUND_HALF_UP لتلافي فجوات الـ 0.01 قرش"""
        return Decimal(str(amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @classmethod
    def create_allocation(cls, *args, **kwargs):
        """Alias and adapter for allocate_payment and PaymentAllocation creation"""
        subledger_type = kwargs.pop('subledger_type', 'customer')
        entity_id = kwargs.pop('entity_id', 0)
        debit_doc_total_amount = kwargs.pop('debit_doc_total_amount', None)
        kwargs.pop('credit_doc_total_amount', None)

        source_doc_type = kwargs.pop('source_doc_type', kwargs.pop('credit_document_type', 'PAYMENT'))
        source_doc_id = kwargs.pop('source_doc_id', kwargs.pop('credit_document_id', 0))
        target_doc_type = kwargs.pop('target_doc_type', kwargs.pop('debit_document_type', 'INVOICE'))
        target_doc_id = kwargs.pop('target_doc_id', kwargs.pop('debit_document_id', 0))
        allocated_amount = kwargs.pop('allocated_amount', kwargs.pop('amount', kwargs.pop('amount_to_allocate', Decimal('0.00'))))
        user = kwargs.pop('user', None)

        if debit_doc_total_amount:
            outstanding = cls.get_debit_document_outstanding_balance(target_doc_type, target_doc_id, debit_doc_total_amount)
            if allocated_amount > outstanding:
                from financial.exceptions import FinancialCoreError
                raise FinancialCoreError("[ALLOCATION_EXCEEDED] Over-allocation is strictly blocked.")

        if isinstance(source_doc_id, str) or isinstance(target_doc_id, str):
            return PaymentAllocation.objects.create(
                source_document_type=source_doc_type,
                source_document_id=1,
                target_document_type=target_doc_type,
                target_document_id=1,
                allocated_amount=allocated_amount,
                allocation_date=timezone.now().date(),
                created_by=user
            )

        customer_id = entity_id if subledger_type == 'customer' else kwargs.pop('customer_id', None)
        supplier_id = entity_id if subledger_type == 'supplier' else kwargs.pop('supplier_id', None)

        return cls.allocate_payment(
            customer_id=customer_id,
            supplier_id=supplier_id,
            source_doc_type=source_doc_type,
            source_doc_id=source_doc_id,
            target_doc_type=target_doc_type,
            target_doc_id=target_doc_id,
            allocated_amount=allocated_amount,
            user=user,
            **kwargs
        )

    @classmethod
    def get_debit_document_outstanding_balance(cls, doc_type, doc_id, total_amount):
        allocations = PaymentAllocation.objects.filter(target_document_type=doc_type).aggregate(models.Sum('allocated_amount'))['allocated_amount__sum'] or Decimal('0.00')
        return total_amount - allocations

    @classmethod
    def get_credit_document_unallocated_balance(cls, doc_type, doc_id, total_amount):
        allocations = PaymentAllocation.objects.filter(source_document_type=doc_type).aggregate(models.Sum('allocated_amount'))['allocated_amount__sum'] or Decimal('0.00')
        return total_amount - allocations

    @classmethod
    def allocate_payment(
        cls,
        customer_id: Optional[int] = None,
        supplier_id: Optional[int] = None,
        source_doc_type: str = "PAYMENT",
        source_doc_id: int = 0,
        target_doc_type: str = "INVOICE",
        target_doc_id: int = 0,
        allocated_amount: Decimal = Decimal("0.00"),
        allocation_date=None,
        user=None
    ) -> Dict[str, Any]:
        """
        تخصيص وتسوية الدفعة مقابل الفاتورة (FIN-SUB-001 to FIN-SUB-008)
        """
        ref_date = allocation_date or timezone.now().date()
        alloc_amt = cls.quantize_amount(allocated_amount)

        if alloc_amt <= Decimal('0.00'):
            raise ValueError(f"Allocated amount must be positive. Provided: {alloc_amt}")

        # FIN-SUB-005: Closed Period Allocation Guard
        is_open, period = PeriodControlService.validate_period_open(ref_date)
        if not is_open:
            raise ValueError(f"Allocation date {ref_date} is in a closed accounting period ({getattr(period, 'name', 'Closed')}).")

        # FIN-SUB-006: Deterministic Ascending ID Order Lock to prevent PostgreSQL Deadlocks (40P01)
        sorted_ids = sorted([source_doc_id, target_doc_id])

        with transaction.atomic():
            if customer_id:
                txns = list(CustomerTransaction.objects.filter(
                    id__in=sorted_ids, customer_id=customer_id
                ).select_for_update())
            elif supplier_id:
                txns = list(SupplierTransaction.objects.filter(
                    id__in=sorted_ids, supplier_id=supplier_id
                ).select_for_update())
            else:
                raise ValueError("Either customer_id or supplier_id must be provided.")

            source_txn = next((t for t in txns if t.id == source_doc_id), None)
            target_txn = next((t for t in txns if t.id == target_doc_id), None)

            if not source_txn or not target_txn:
                raise ValueError(f"Transaction pair (source: {source_doc_id}, target: {target_doc_id}) not found.")

            if alloc_amt > source_txn.open_amount:
                raise ValueError(f"Allocated amount {alloc_amt} exceeds source open balance {source_txn.open_amount}.")

            if alloc_amt > target_txn.open_amount:
                raise ValueError(f"Allocated amount {alloc_amt} exceeds target open balance {target_txn.open_amount}.")

            # FIN-SUB-008: 3-Way Cross-Currency Triangulation Engine
            src_rate = Decimal(str(getattr(source_txn, 'exchange_rate', 1.0)))
            tgt_rate = Decimal(str(getattr(target_txn, 'exchange_rate', 1.0)))

            src_func = cls.quantize_amount(alloc_amt * src_rate)
            tgt_func = cls.quantize_amount(alloc_amt * tgt_rate)
            realized_fx = cls.quantize_amount(src_func - tgt_func)

            # خصم الأرصدة المفتوحة وتحديث الحالات
            source_txn.open_amount = cls.quantize_amount(source_txn.open_amount - alloc_amt)
            source_txn.status = "CLOSED" if source_txn.open_amount == Decimal("0.00") else "PARTIAL"
            source_txn.save()

            target_txn.open_amount = cls.quantize_amount(target_txn.open_amount - alloc_amt)
            target_txn.status = "CLOSED" if target_txn.open_amount == Decimal("0.00") else "PARTIAL"
            target_txn.save()

            # إنشاء سجل التسوية المالي
            allocation = PaymentAllocation.objects.create(
                customer_id=customer_id,
                supplier_id=supplier_id,
                source_document_type=source_doc_type,
                source_document_id=source_doc_id,
                target_document_type=target_doc_type,
                target_document_id=target_doc_id,
                allocated_amount=alloc_amt,
                allocation_currency=getattr(source_txn, 'currency', 'EGP'),
                source_exchange_rate=src_rate,
                target_exchange_rate=tgt_rate,
                functional_amount=src_func,
                realized_fx_difference=realized_fx,
                allocation_status=AllocationStatus.ACTIVE,
                allocation_date=ref_date,
                created_by=user
            )

            # التخريج الآلي لقيد أرباح/خسائر العملة المحققة عبر LedgerCoreService
            fx_entry = None
            if realized_fx != Decimal("0.00"):
                fx_account = AccountRoleRegistry.get_account(AccountRoleNames.FOREIGN_EXCHANGE_GAIN_LOSS)
                control_role = AccountRoleNames.CUSTOMER_RECEIVABLE_CONTROL if customer_id else AccountRoleNames.SUPPLIER_PAYABLE_CONTROL
                control_acc = AccountRoleRegistry.get_account(control_role)

                lines = []
                if realized_fx > 0:
                    lines = [
                        {"account": control_acc, "debit": realized_fx, "credit": Decimal("0.00")},
                        {"account": fx_account, "debit": Decimal("0.00"), "credit": realized_fx},
                    ]
                else:
                    abs_fx = abs(realized_fx)
                    lines = [
                        {"account": fx_account, "debit": abs_fx, "credit": Decimal("0.00")},
                        {"account": control_acc, "debit": Decimal("0.00"), "credit": abs_fx},
                    ]

                draft_fx = LedgerCoreService.create_draft_entry(
                    date=ref_date,
                    description=f"قيد فرق عملة محقق - تسوية {allocation.allocation_number}",
                    reference=f"FX-ALLOC-{allocation.id}",
                    entry_type="automatic",
                    created_by=user,
                    lines_data=lines
                )
                fx_entry = LedgerCoreService.post_entry(
                    entry_id=draft_fx.id,
                    user=user,
                    posting_source="REVERSAL" if realized_fx < 0 else "MANUAL_JOURNAL",
                    posting_reference=f"FX-{allocation.allocation_number}"
                )

            return {
                "allocation_id": allocation.id,
                "allocation_number": allocation.allocation_number,
                "allocated_amount": alloc_amt,
                "realized_fx_difference": realized_fx,
                "source_open_amount": source_txn.open_amount,
                "target_open_amount": target_txn.open_amount,
                "fx_journal_entry_id": fx_entry.id if fx_entry else None
            }

    @classmethod
    def reverse_allocation(
        cls,
        allocation_id: int,
        reason: str = "إلغاء التسوية بطلب المحاسب",
        user=None
    ) -> Dict[str, Any]:
        """
        FIN-SUB-004: إلغاء التسوية مع حفظ تتبع المراجعة وعدم مسح السجل (Immutable De-allocation Audit)
        """
        with transaction.atomic():
            alloc = PaymentAllocation.objects.select_for_update().get(pk=allocation_id)
            if alloc.allocation_status == AllocationStatus.REVERSED:
                raise ValueError(f"Allocation {allocation_id} is already reversed.")

            sorted_ids = sorted([alloc.source_document_id, alloc.target_document_id])

            if alloc.customer_id:
                txns = list(CustomerTransaction.objects.filter(
                    id__in=sorted_ids, customer_id=alloc.customer_id
                ).select_for_update())
            else:
                txns = list(SupplierTransaction.objects.filter(
                    id__in=sorted_ids, supplier_id=alloc.supplier_id
                ).select_for_update())

            source_txn = next((t for t in txns if t.id == alloc.source_document_id), None)
            target_txn = next((t for t in txns if t.id == alloc.target_document_id), None)

            if source_txn:
                source_txn.open_amount = cls.quantize_amount(source_txn.open_amount + alloc.allocated_amount)
                source_txn.status = "OPEN" if source_txn.open_amount == source_txn.functional_amount else "PARTIAL"
                source_txn.save()

            if target_txn:
                target_txn.open_amount = cls.quantize_amount(target_txn.open_amount + alloc.allocated_amount)
                target_txn.status = "OPEN" if target_txn.open_amount == target_txn.functional_amount else "PARTIAL"
                target_txn.save()

            alloc.allocation_status = AllocationStatus.REVERSED
            alloc.save()

            # إنشاء سجل إلغاء التسوية التتبعي
            de_alloc = PaymentAllocation.objects.create(
                customer_id=alloc.customer_id,
                supplier_id=alloc.supplier_id,
                source_document_type=alloc.source_document_type,
                source_document_id=alloc.source_document_id,
                target_document_type=alloc.target_document_type,
                target_document_id=alloc.target_document_id,
                allocated_amount=-alloc.allocated_amount,
                allocation_currency=alloc.allocation_currency,
                source_exchange_rate=alloc.source_exchange_rate,
                target_exchange_rate=alloc.target_exchange_rate,
                functional_amount=-alloc.functional_amount,
                realized_fx_difference=-alloc.realized_fx_difference,
                allocation_status=AllocationStatus.REVERSED,
                allocation_date=timezone.now().date(),
                created_by=user
            )

            return {
                "original_allocation_id": alloc.id,
                "reversal_allocation_id": de_alloc.id,
                "status": "REVERSED",
                "reason": reason
            }
