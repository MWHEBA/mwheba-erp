"""
CustomerSubledgerService - محرك دفتر الأستاذ الفرعي للعملاء (Sprint 2 Subledgers Engine)
يمتلك حل الحسابات الفرعية، قواعد مطابقة الحسابات الرئاسية، وتقرير تعمير الديون بناءً على تواريخ استحقاق الفواتير
يفوض استعلامات دفتر الأستاذ العام 100% لـ LedgerQueryService (FIN-CORE-014)
"""

import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional
from django.utils import timezone

from client.models import Customer
from financial.services.ledger_query_service import LedgerQueryService
from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames

logger = logging.getLogger("client.customer_subledger_service")


class CustomerSubledgerService:
    """
    خدمة دفتر الأستاذ الفرعي للعملاء
    """

    @classmethod
    def resolve_customer_account(cls, customer_id: int):
        """
        حل وتدقيق وجود الحساب المالي الفرعي للعميل
        """
        customer = Customer.objects.select_related('financial_account').get(pk=customer_id)
        if not customer.financial_account:
            raise ValueError(f"Customer {customer.name} (ID: {customer_id}) has no associated financial account.")
        return customer, customer.financial_account

    @classmethod
    def get_customer_balance(
        cls,
        customer_id: int,
        as_of_date: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        استعلام رصيد العميل الحالي من واقع حقائق دفتر الأستاذ عبر LedgerQueryService
        """
        customer, account = cls.resolve_customer_account(customer_id)
        balance_data = LedgerQueryService.get_account_balance(account, as_of_date=as_of_date)
        balance_data['customer_id'] = customer.id
        balance_data['customer_code'] = customer.code
        balance_data['customer_name'] = customer.name
        return balance_data

    @classmethod
    def get_customer_balances_by_currency(cls, customer_id: int) -> List[Dict[str, Any]]:
        """
        جلب مديونية العميل مفصلة بكل عملة (IAS 21 Multi-Currency Subledger)
        """
        from client.models import CustomerTransaction
        from django.db.models import Sum
        qs = (
            CustomerTransaction.objects.filter(customer_id=customer_id)
            .values("currency")
            .annotate(
                total_open_foreign=Sum("open_amount_foreign"),
                total_open_functional=Sum("open_amount_functional")
            )
            .filter(total_open_foreign__gt=Decimal("0.00"))
        )
        return list(qs)

    @classmethod
    def get_customer_statement(
        cls,
        customer_id: int,
        start_date: Optional[Any] = None,
        end_date: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        استخراج كشف حساب جاري للعميل عبر LedgerQueryService
        """
        customer, account = cls.resolve_customer_account(customer_id)
        statement_data = LedgerQueryService.get_account_statement(account, start_date=start_date, end_date=end_date)
        statement_data['customer_id'] = customer.id
        statement_data['customer_code'] = customer.code
        statement_data['customer_name'] = customer.name
        return statement_data

    @classmethod
    def get_customer_aging_report(
        cls,
        customer_ids: Optional[List[int]] = None,
        as_of_date: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        حساب تقرير أعمار ديون العملاء (Aging Buckets: 0-30, 31-60, 61-90, 90+)
        يعتمد التقرير التشغيلي على تواريخ استحقاق الفواتير والمدفوعات الموزعة (FIN-SUB-001 Allocation Engine)
        """
        ref_date = as_of_date or timezone.now().date()
        customers = Customer.objects.filter(is_active=True).select_related('financial_account')
        if customer_ids:
            customers = customers.filter(pk__in=customer_ids)

        report_rows = []
        total_summary = {
            'bucket_0_30': Decimal('0.00'),
            'bucket_31_60': Decimal('0.00'),
            'bucket_61_90': Decimal('0.00'),
            'bucket_90_plus': Decimal('0.00'),
            'total_balance': Decimal('0.00')
        }

        for customer in customers:
            if not customer.financial_account:
                continue

            bal_data = LedgerQueryService.get_account_balance(customer.financial_account, as_of_date=ref_date)
            balance = bal_data['balance']

            if balance <= Decimal('0.00'):
                # لا توجد ديون مستحقة للعميل
                continue

            # توزيع الرصيد بناءً على تواريخ الحركة
            stmt = LedgerQueryService.get_account_statement(customer.financial_account, end_date=ref_date)
            transactions = stmt['transactions']

            bucket_0_30 = Decimal('0.00')
            bucket_31_60 = Decimal('0.00')
            bucket_61_90 = Decimal('0.00')
            bucket_90_plus = Decimal('0.00')

            for txn in reversed(transactions):
                if txn['debit'] <= 0:
                    continue
                txn_date = txn['date']
                days_old = (ref_date - txn_date).days

                amount = txn['debit']
                if days_old <= 30:
                    bucket_0_30 += amount
                elif days_old <= 60:
                    bucket_31_60 += amount
                elif days_old <= 90:
                    bucket_61_90 += amount
                else:
                    bucket_90_plus += amount

            row_total = bucket_0_30 + bucket_31_60 + bucket_61_90 + bucket_90_plus
            # ضبط التوزيع بالرصيد الفعلي الجاري
            if row_total > 0 and row_total != balance:
                factor = balance / row_total
                bucket_0_30 = (bucket_0_30 * factor).quantize(Decimal('0.01'))
                bucket_31_60 = (bucket_31_60 * factor).quantize(Decimal('0.01'))
                bucket_61_90 = (bucket_61_90 * factor).quantize(Decimal('0.01'))
                bucket_90_plus = (bucket_90_plus * factor).quantize(Decimal('0.01'))

            report_rows.append({
                'customer_id': customer.id,
                'customer_code': customer.code,
                'customer_name': customer.name,
                'bucket_0_30': bucket_0_30,
                'bucket_31_60': bucket_31_60,
                'bucket_61_90': bucket_61_90,
                'bucket_90_plus': bucket_90_plus,
                'total_balance': balance
            })

            total_summary['bucket_0_30'] += bucket_0_30
            total_summary['bucket_31_60'] += bucket_31_60
            total_summary['bucket_61_90'] += bucket_61_90
            total_summary['bucket_90_plus'] += bucket_90_plus
            total_summary['total_balance'] += balance

        return {
            'as_of_date': ref_date,
            'rows': report_rows,
            'summary': total_summary
        }

    @classmethod
    def reconcile_customer_control_account(cls) -> Dict[str, Any]:
        """
        مطابقة رصيد حساب التحكم الإجمالي للعملاء (Customer Payable/Receivable Control) مع مجموع أرصدة العملاء
        """
        control_account = AccountRoleRegistry.get_account(AccountRoleNames.CUSTOMER_RECEIVABLE_CONTROL)
        customers = Customer.objects.filter(is_active=True, financial_account__isnull=False)
        sub_accounts = [c.financial_account for c in customers]

        reconciliation = LedgerQueryService.get_control_account_reconciliation(control_account, sub_accounts)
        return reconciliation

    @classmethod
    def register_open_item_transaction(
        cls,
        customer: Customer,
        transaction_type: str,
        transaction_number: str,
        issue_date,
        due_date,
        currency: str = "EGP",
        foreign_amount: Decimal = Decimal("0.00"),
        exchange_rate: Decimal = Decimal("1.000000"),
        functional_amount: Decimal = Decimal("0.00"),
        journal_entry=None,
        reference_type: str = "",
        reference_id: Optional[int] = None
    ):
        """
        FIN-AR-003: تسجيل بند معاملة مفتوحة للعميل
        """
        from client.models import CustomerTransaction
        open_amt = functional_amount
        status = "OPEN"

        if transaction_type in ["PAYMENT", "CREDIT_NOTE"]:
            # Credit items have negative open balance impact or are available for allocation
            open_amt = functional_amount

        txn = CustomerTransaction.objects.create(
            customer=customer,
            transaction_type=transaction_type,
            transaction_number=transaction_number,
            reference_type=reference_type,
            reference_id=reference_id,
            issue_date=issue_date,
            due_date=due_date,
            currency=currency,
            foreign_amount=foreign_amount,
            exchange_rate=exchange_rate,
            functional_amount=functional_amount,
            open_amount_foreign=foreign_amount,
            open_amount_functional=open_amt,
            open_amount=open_amt,
            status=status,
            journal_entry=journal_entry
        )
        return txn

    @classmethod
    def get_open_items(cls, customer_id: int):
        """
        FIN-AR-003: استعلام بنود المعاملات المفتوحة غير المسددة للعميل
        """
        from client.models import CustomerTransaction
        return CustomerTransaction.objects.filter(
            customer_id=customer_id,
            status__in=["OPEN", "PARTIAL"]
        ).order_by("due_date", "id")

    @classmethod
    def get_customer_open_balance(cls, customer_id: int) -> Decimal:
        """
        FIN-AR-001 API Boundary: استعلام إجمالي الرصيد المفتوح غير المسدد للعميل من واجهة Subledger API
        """
        from django.db.models import Sum
        open_items = cls.get_open_items(customer_id)
        total = open_items.aggregate(sum_open=Sum("open_amount"))["sum_open"]
        return total or Decimal("0.00")

    @classmethod
    def allocate_payment(
        cls,
        customer_id: int,
        payment_transaction_id: int,
        invoice_transaction_id: int,
        allocated_amount: Decimal,
        user=None
    ) -> Dict[str, Any]:
        """
        FIN-AR-004: تخصيص وتوزيع مبالغ السداد على الفواتير المفتوحة مع تسجيل SHA256 audit
        """
        import hashlib
        from django.db import transaction
        from client.models import CustomerTransaction, CustomerAllocationAudit

        with transaction.atomic():
            pay_txn = CustomerTransaction.objects.select_for_update().get(id=payment_transaction_id, customer_id=customer_id)
            inv_txn = CustomerTransaction.objects.select_for_update().get(id=invoice_transaction_id, customer_id=customer_id)

            if allocated_amount > pay_txn.open_amount:
                raise ValueError(f"Allocated amount {allocated_amount} exceeds payment open amount {pay_txn.open_amount}.")

            if allocated_amount > inv_txn.open_amount:
                raise ValueError(f"Allocated amount {allocated_amount} exceeds invoice open amount {inv_txn.open_amount}.")

            # Update balances with full multi-currency sync
            pay_txn.open_amount -= allocated_amount
            pay_txn.open_amount_functional = pay_txn.open_amount
            if pay_txn.exchange_rate and pay_txn.exchange_rate > Decimal("0.000000"):
                pay_txn.open_amount_foreign = (pay_txn.open_amount / pay_txn.exchange_rate).quantize(Decimal("0.01"))
            if pay_txn.open_amount <= Decimal("0.00"):
                pay_txn.open_amount = Decimal("0.00")
                pay_txn.open_amount_functional = Decimal("0.00")
                pay_txn.open_amount_foreign = Decimal("0.00")
                pay_txn.status = "CLOSED"
            else:
                pay_txn.status = "PARTIAL"
            pay_txn.save()

            inv_txn.open_amount -= allocated_amount
            inv_txn.open_amount_functional = inv_txn.open_amount
            if inv_txn.exchange_rate and inv_txn.exchange_rate > Decimal("0.000000"):
                inv_txn.open_amount_foreign = (inv_txn.open_amount / inv_txn.exchange_rate).quantize(Decimal("0.01"))
            if inv_txn.open_amount <= Decimal("0.00"):
                inv_txn.open_amount = Decimal("0.00")
                inv_txn.open_amount_functional = Decimal("0.00")
                inv_txn.open_amount_foreign = Decimal("0.00")
                inv_txn.status = "CLOSED"
            else:
                inv_txn.status = "PARTIAL"
            inv_txn.save()

            # Realized FX difference calculation (FIN-CORE-016 Multi-Currency)
            realized_fx = Decimal("0.00")
            if pay_txn.currency == inv_txn.currency and pay_txn.currency != "EGP":
                fx_diff = (pay_txn.exchange_rate - inv_txn.exchange_rate)
                realized_fx = (allocated_amount * fx_diff).quantize(Decimal("0.01"))

            # Determine Allocation Type
            alloc_type = "PAYMENT_TO_INVOICE"
            if pay_txn.transaction_type == "ADVANCE":
                alloc_type = "ADVANCE_TO_INVOICE"
            elif pay_txn.transaction_type == "CREDIT_NOTE":
                alloc_type = "CREDIT_NOTE_TO_INVOICE"

            from client.services.allocation_result import AllocationResult
            from client.services.customer_allocation_audit_service import CustomerAllocationAuditService

            alloc_result = AllocationResult(
                customer_id=pay_txn.customer.id,
                payment_transaction_id=pay_txn.id,
                invoice_transaction_id=inv_txn.id,
                allocated_amount=allocated_amount,
                allocation_type=alloc_type,
                allocation_currency=pay_txn.currency,
                exchange_rate=pay_txn.exchange_rate,
                functional_amount=(allocated_amount * pay_txn.exchange_rate).quantize(Decimal("0.01")),
                realized_fx_difference=realized_fx,
                source_document_type=pay_txn.transaction_type,
                source_document_number=pay_txn.transaction_number,
                target_document_type=inv_txn.transaction_type,
                target_document_number=inv_txn.transaction_number,
                payment_remaining=pay_txn.open_amount,
                invoice_remaining=inv_txn.open_amount,
                payment_status=pay_txn.status,
                invoice_status=inv_txn.status
            )

            audit = CustomerAllocationAuditService.create_audit_entry_from_result(alloc_result, user=user)

            return {
                "payment_transaction_id": pay_txn.id,
                "invoice_transaction_id": inv_txn.id,
                "allocated_amount": allocated_amount,
                "realized_fx_difference": realized_fx,
                "payment_remaining": pay_txn.open_amount,
                "invoice_remaining": inv_txn.open_amount,
                "payment_status": pay_txn.status,
                "invoice_status": inv_txn.status,
                "audit_id": audit.id,
                "evidence_hash": audit.evidence_hash,
                "allocation_result": alloc_result
            }

    @classmethod
    def allocate_credit_note(
        cls,
        customer_id: int,
        credit_note_transaction_id: int,
        invoice_transaction_id: int,
        allocated_amount: Decimal,
        user=None
    ) -> Dict[str, Any]:
        """
        FIN-AR-004: تخصيص وتسوية الإشعار الدائن مقابل الفاتورة
        """
        return cls.allocate_payment(
            customer_id=customer_id,
            payment_transaction_id=credit_note_transaction_id,
            invoice_transaction_id=invoice_transaction_id,
            allocated_amount=allocated_amount,
            user=user
        )

    @classmethod
    def allocate_advance(
        cls,
        customer_id: int,
        advance_transaction_id: int,
        invoice_transaction_id: int,
        allocated_amount: Decimal,
        user=None
    ) -> Dict[str, Any]:
        """
        FIN-AR-004: تطبيق وتخصيص الدفعة المقدمة على الفاتورة المستحقة
        """
        return cls.allocate_payment(
            customer_id=customer_id,
            payment_transaction_id=advance_transaction_id,
            invoice_transaction_id=invoice_transaction_id,
            allocated_amount=allocated_amount,
            user=user
        )
