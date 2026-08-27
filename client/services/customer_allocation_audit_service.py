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
        created_at,
        currency_code: str = "EGP",
        exchange_rate: Decimal = Decimal("1.000000"),
        user_id: Optional[int] = None
    ) -> str:
        """
        إنشاء التوقيع المشفر SHA256 لإثبات عدم التلاعب بسجل التوزيع بشكل دائم ومستقر
        """
        timestamp_str = created_at.strftime("%Y-%m-%dT%H:%M:%S") if hasattr(created_at, "strftime") else str(created_at)[:19]
        raw_data = f"{customer_id}:{payment_txn_id}:{invoice_txn_id}:{allocated_amount}:{currency_code}:{exchange_rate}:{user_id or 0}:{allocation_date}:{timestamp_str}"
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
    def allocate_customer_prepaid_balance_to_sale(
        cls,
        sale,
        amount_to_allocate: Optional[Decimal] = None,
        user=None,
        amount: Optional[Decimal] = None
    ) -> CustomerAllocationAudit:
        """
        خصم وتخصيص مبلغ من الرصيد المسبق/الدفعات المقدمة للعميل على فاتورة مبيعات
        مع محرك الحوكمة والـ IAS 21 والـ CQRS Read Model Event Trigger
        """
        from client.models import CustomerPayment
        from sale.models import SalePayment
        from governance.services import AccountingGateway, JournalEntryLineData
        from financial.services.period_control_service import PeriodControlService
        from financial.services.fx_settlement_strategy import CustomerFXStrategy
        from financial.services.partner_currency_snapshot_updater import PartnerCurrencySnapshotUpdater

        # 1. التحقق من حالة الفاتورة (يُمنع التخصيص للمسودات DRAFT)
        sale_status = str(getattr(sale, "status", "")).lower()
        if sale_status not in ["confirmed", "posted"]:
            raise ValueError("لا يمكن تخصيص رصيد مسبق إلا على الفواتير المعتمدة والمرحلة فقط.")

        target_amount = amount_to_allocate if amount_to_allocate is not None else amount
        if target_amount is None:
            raise ValueError("المبلغ المراد تخصيصه مطلوب.")
        amount_to_allocate = Decimal(str(target_amount)).quantize(Decimal("0.01"))

        if amount_to_allocate <= Decimal("0.00"):
            raise ValueError("المبلغ المراد تخصيصه يجب أن يكون أكبر من صفر.")

        customer = sale.customer
        if not customer:
            raise ValueError("الفاتورة غير مرتبطة بعميل.")

        allocation_date = timezone.now().date()
        PeriodControlService.validate_period_open(allocation_date)

        from utils.templatetags.utils_extras import smart_float
        from core.models import SystemSetting
        currency_sym = sale.currency.symbol if sale.currency else SystemSetting.get_setting('currency_symbol', 'ج.م')

        open_sale_amount = (sale.total - (sale.amount_paid or Decimal("0.00"))).quantize(Decimal("0.01"))
        if amount_to_allocate > open_sale_amount:
            raise ValueError(f"المبلغ المراد تخصيصه ({smart_float(amount_to_allocate)} {currency_sym}) يتجاوز المتبقي من الفاتورة ({smart_float(open_sale_amount)} {currency_sym}).")

        with transaction.atomic():
            # قفل محكم بترتيب محدد لمنع الـ Deadlocks
            locked_customer = Customer.objects.select_for_update().get(pk=customer.id)

            # جلب الدفعات المطابقة بالعملة أقدم فأقدم (FIFO)
            from django.db.models import Q
            sale_curr_id = sale.currency_id or (locked_customer.default_currency_id if locked_customer else None)
            payments_qs = CustomerPayment.objects.select_for_update().filter(
                customer_id=locked_customer.id
            ).exclude(status="cancelled")

            if sale_curr_id:
                payments_qs = payments_qs.filter(Q(currency_id=sale_curr_id) | Q(currency__isnull=True))
            else:
                payments_qs = payments_qs.filter(currency__isnull=True)

            customer_payments = list(payments_qs.order_by("payment_date", "created_at"))

            # حساب الرصيد المتاح الفعلي لهذه العملة تحديداً
            avail_balance = Decimal("0.00")
            for cp in customer_payments:
                used = sum(sp.amount for sp in SalePayment.objects.filter(customer_payment=cp))
                avail_balance += max(Decimal("0.00"), cp.amount - used)

            if amount_to_allocate > avail_balance:
                raise ValueError(f"رصيد العميل المسبق المتاح لعملة {currency_sym} ({smart_float(avail_balance)}) غير كافٍ لسداد المبلغ المطلوب ({smart_float(amount_to_allocate)}).")

            remaining_to_allocate = amount_to_allocate
            last_audit = None
            total_fx_diff = Decimal("0.00")

            # الحصول على أو إنشاء معاملة الأستاذ الفرعي للفاتورة
            inv_txn, _ = CustomerTransaction.objects.select_for_update().get_or_create(
                customer=locked_customer,
                transaction_number=sale.number,
                defaults={
                    "transaction_type": "INVOICE",
                    "reference_type": "Sale",
                    "reference_id": str(sale.id),
                    "issue_date": sale.date,
                    "due_date": sale.date,
                    "functional_amount": sale.total,
                    "open_amount": open_sale_amount,
                    "open_amount_functional": open_sale_amount,
                    "status": "OPEN" if (sale.amount_paid or Decimal("0.00")) == Decimal("0.00") else "PARTIAL"
                }
            )

            fx_strategy = CustomerFXStrategy()

            for cp in customer_payments:
                if remaining_to_allocate <= Decimal("0.00"):
                    break

                # حساب المستغل من هذه الدفعة
                already_allocated = sum(sp.amount for sp in SalePayment.objects.filter(customer_payment=cp))
                cp_remaining = max(Decimal("0.00"), cp.amount - already_allocated)

                if cp_remaining <= Decimal("0.00"):
                    continue

                curr_alloc = min(cp_remaining, remaining_to_allocate)
                remaining_to_allocate -= curr_alloc

                # تحديث الحقل المخزن المخبأ بالدفعة
                cp.allocated_currency_amount_cached += curr_alloc
                cp.save(update_fields=["allocated_currency_amount_cached", "updated_at"])

                # حساب فروق العملة المحققة إن وجدت أسعار صرف مختلفة
                cp_rate = cp.exchange_rate if hasattr(cp, "exchange_rate") and cp.exchange_rate else Decimal("1.0")
                sale_rate = sale.exchange_rate if hasattr(sale, "exchange_rate") and sale.exchange_rate else Decimal("1.0")
                fx_diff = fx_strategy.calculate_difference(cp_rate, sale_rate, curr_alloc)
                total_fx_diff += fx_diff

                # الحصول على/إنشاء معاملة الدفعة المقدمة في الأستاذ الفرعي
                pay_txn, _ = CustomerTransaction.objects.select_for_update().get_or_create(
                    customer=locked_customer,
                    transaction_number=f"PAY-{cp.id}",
                    defaults={
                        "transaction_type": "ADVANCE",
                        "reference_type": "CustomerPayment",
                        "reference_id": str(cp.id),
                        "issue_date": cp.payment_date,
                        "due_date": cp.payment_date,
                        "functional_amount": cp.amount,
                        "open_amount": cp_remaining,
                        "open_amount_functional": cp_remaining,
                        "status": "PARTIAL" if cp_remaining > 0 else "CLOSED"
                    }
                )

                pay_txn.open_amount = max(Decimal("0.00"), pay_txn.open_amount - curr_alloc)
                pay_txn.open_amount_functional = pay_txn.open_amount
                pay_txn.status = "CLOSED" if pay_txn.open_amount == Decimal("0.00") else "PARTIAL"
                pay_txn.save()

                inv_txn.open_amount = max(Decimal("0.00"), inv_txn.open_amount - curr_alloc)
                inv_txn.open_amount_functional = inv_txn.open_amount
                inv_txn.status = "CLOSED" if inv_txn.open_amount == Decimal("0.00") else "PARTIAL"
                inv_txn.save()

                now = timezone.now()
                ev_hash = cls.generate_evidence_hash(
                    customer_id=locked_customer.id,
                    payment_txn_id=pay_txn.id,
                    invoice_txn_id=inv_txn.id,
                    allocated_amount=curr_alloc,
                    allocation_date=now.date(),
                    created_at=now
                )

                last_audit = CustomerAllocationAudit.objects.create(
                    customer=locked_customer,
                    allocation_reference=f"ALLOC-{pay_txn.transaction_number}->{inv_txn.transaction_number}",
                    payment_transaction=pay_txn,
                    invoice_transaction=inv_txn,
                    source_document_type="ADVANCE_PAYMENT",
                    source_document_number=f"PAY-{cp.id}",
                    target_document_type="SALES_INVOICE",
                    target_document_number=sale.number,
                    allocation_type="ADVANCE_TO_INVOICE",
                    allocated_amount=curr_alloc,
                    functional_amount=curr_alloc,
                    allocation_status="APPLIED",
                    allocation_date=now.date(),
                    created_by=user,
                    evidence_hash=ev_hash
                )

                # إنشاء SalePayment مخصصة
                SalePayment.objects.create(
                    sale=sale,
                    amount=curr_alloc,
                    payment_date=cp.payment_date if (cp and getattr(cp, "payment_date", None)) else now.date(),
                    payment_method="prepaid_balance",
                    source_type="PREPAID_BALANCE",
                    customer_payment=cp,
                    reference_number=f"PAY-{cp.id}",
                    notes=f"خصم تلقائي من الرصيد المسبق للعميل (دفعة #{cp.id})",
                    created_by=user or sale.created_by,
                    status="posted",
                    financial_status="synced"
                )

            # تحديث حالة السداد للفاتورة والمبلغ المدفوع
            sale.update_payment_status()

            # إصدار قيد التسوية المحسب المتزن
            if locked_customer.financial_account:
                from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames
                advance_acc = AccountRoleRegistry.get_account(AccountRoleNames.CUSTOMER_ADVANCE_LIABILITY)
                partner_acc_code = locked_customer.financial_account.code
                
                # حساب قيم المعادل بالعملة الوظيفية
                cp_rate = Decimal(str(getattr(customer_payments[0], "exchange_rate", 1.0) or 1.0)) if customer_payments else Decimal("1.0")
                sale_rate = Decimal(str(getattr(sale, "exchange_rate", 1.0) or 1.0))

                adv_func = (amount_to_allocate * cp_rate).quantize(Decimal("0.01"))
                sale_func = (amount_to_allocate * sale_rate).quantize(Decimal("0.01"))

                lines = [
                    JournalEntryLineData(
                        account_code=advance_acc.code,
                        debit=adv_func,
                        credit=Decimal("0.00"),
                        description=f"إغلاق دفعات مقدمة للعميل - فاتورة مبيعات {sale.number}"
                    ),
                    JournalEntryLineData(
                        account_code=partner_acc_code,
                        debit=Decimal("0.00"),
                        credit=sale_func,
                        description=f"تسوية فاتورة مبيعات {sale.number} - تخفيض ذمم العميل"
                    )
                ]

                if total_fx_diff != Decimal("0.00"):
                    fx_lines = fx_strategy.generate_entries(
                        difference=total_fx_diff,
                        advance_account_code=advance_acc.code,
                        partner_account_code=partner_acc_code,
                        reference_note=f"فاتورة {sale.number}"
                    )
                    lines.extend(fx_lines)

                # معالجة فروق التقريب الكسري البسيطة (<= 0.05 ج.م)
                tot_deb = sum(l.debit for l in lines)
                tot_crd = sum(l.credit for l in lines)
                if tot_deb != tot_crd:
                    round_diff = (tot_deb - tot_crd).quantize(Decimal("0.01"))
                    if abs(round_diff) <= Decimal("0.05"):
                        round_acc = AccountRoleRegistry.get_account(AccountRoleNames.ROUNDING_DIFFERENCE_ACCOUNT)
                        if round_diff < Decimal("0.00"):
                            lines.append(JournalEntryLineData(account_code=round_acc.code, debit=abs(round_diff), credit=Decimal("0.00"), description="تسوية فارق تقويم كسر بنيات"))
                        else:
                            lines.append(JournalEntryLineData(account_code=round_acc.code, debit=Decimal("0.00"), credit=abs(round_diff), description="تسوية فارق تقويم كسر بنيات"))

                gateway = AccountingGateway()
                gateway.create_journal_entry(
                    source_module="client",
                    source_model="CustomerAllocationAudit",
                    source_id=last_audit.id if last_audit else sale.id,
                    lines=lines,
                    idempotency_key=f"JE:client:CustomerAllocationAudit:{last_audit.id if last_audit else sale.id}:reclassify",
                    user=user or sale.created_by,
                    entry_type="automatic",
                    description=f"تسوية رصيد مسبق للعميل {locked_customer.name}",
                    reference=f"فاتورة مبيعات {sale.number}"
                )

            PartnerCurrencySnapshotUpdater.trigger_on_commit(
                partner_type="customer",
                partner_id=locked_customer.id,
                currency_code=sale.currency.code if sale.currency else "EGP",
                event_type="ALLOCATION_APPLIED"
            )

            from financial.services.partner_subledger_service import PartnerSubledgerService
            PartnerSubledgerService.record_sale_invoice(sale, user)
            from financial.services.partner_balance_service import PartnerBalanceService
            PartnerBalanceService.update_partner_snapshot("customer", locked_customer.id)

        return last_audit

    @classmethod
    def reverse_customer_allocation(cls, audit_id: int, user=None) -> CustomerAllocationAudit:
        """
        عكس وإلغاء تخصيص رصيد مسبق للعميل (Reversal Engine)
        """
        with transaction.atomic():
            audit = CustomerAllocationAudit.objects.select_for_update().get(pk=audit_id)
            if audit.allocation_status == "REVERSED":
                raise ValueError("سجل التخصيص معكوس بالفعل سابقاً.")

            # تحديث الحقل المخزن المخبأ في الدفعة
            if audit.payment_transaction and audit.payment_transaction.reference_id:
                try:
                    from client.models import CustomerPayment
                    cp = CustomerPayment.objects.select_for_update().filter(pk=int(audit.payment_transaction.reference_id)).first()
                    if cp:
                        cp.allocated_currency_amount_cached = max(Decimal("0.00"), cp.allocated_currency_amount_cached - audit.allocated_amount)
                        cp.save(update_fields=["allocated_currency_amount_cached", "updated_at"])
                except Exception:
                    pass

            # إلغاء مدفوعات SalePayment ذات العلاقة
            from sale.models import SalePayment
            payments = SalePayment.objects.filter(
                customer_payment_id=audit.payment_transaction.reference_id,
                source_type="PREPAID_BALANCE"
            )
            for p in payments:
                sale = p.sale
                p.delete()
                if hasattr(sale, "update_payment_status"):
                    sale.update_payment_status()

            # إنشاء سجل تدقيق عكسي
            now = timezone.now()
            raw_hash_data = f"REV:{audit.id}:{audit.allocated_amount}:{now.isoformat()}"
            rev_hash = hashlib.sha256(raw_hash_data.encode("utf-8")).hexdigest()

            rev_audit = CustomerAllocationAudit.objects.create(
                customer=audit.customer,
                payment_transaction=audit.payment_transaction,
                invoice_transaction=audit.invoice_transaction,
                source_document_type=audit.source_document_type,
                source_document_number=audit.source_document_number,
                target_document_type=audit.target_document_type,
                target_document_number=audit.target_document_number,
                allocation_type="REVERSAL",
                allocated_amount=audit.allocated_amount,
                functional_amount=audit.functional_amount,
                allocation_status="REVERSED",
                reversed_audit=audit,
                allocation_date=now.date(),
                created_by=user,
                evidence_hash=rev_hash
            )

            # ترحيل قيد عكسي في الدفتر العام
            if audit.customer and audit.customer.financial_account:
                try:
                    from governance.services import AccountingGateway, JournalEntryLineData
                    from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames
                    advance_acc = AccountRoleRegistry.get_account(AccountRoleNames.CUSTOMER_ADVANCE_LIABILITY)
                    
                    rev_lines = [
                        JournalEntryLineData(
                            account_code=audit.customer.financial_account.code,
                            debit=audit.functional_amount,
                            credit=Decimal("0.00"),
                            description=f"عكس تسوية فاتورة - إعادة ذمة العميل (إلغاء تخصيص #{audit.id})"
                        ),
                        JournalEntryLineData(
                            account_code=advance_acc.code,
                            debit=Decimal("0.00"),
                            credit=audit.functional_amount,
                            description=f"عكس تسوية دفعة مقدمة للعميل (إلغاء تخصيص #{audit.id})"
                        )
                    ]

                    # عكس فروق العملة المحققة IAS 21 بالكامل بنفس القيمة التاريخية
                    if audit.realized_fx_difference and audit.realized_fx_difference != Decimal("0.00"):
                        fx_strategy = CustomerFXStrategy()
                        fx_rev_lines = fx_strategy.generate_entries(
                            difference=-audit.realized_fx_difference,
                            advance_account_code=advance_acc.code,
                            partner_account_code=audit.customer.financial_account.code,
                            reference_note=f"عكس فروق عملة تخصيص #{audit.id}"
                        )
                        rev_lines.extend(fx_rev_lines)

                    gateway = AccountingGateway()
                    gateway.create_journal_entry(
                        source_module="sale",
                        source_model="CustomerAllocationAudit",
                        source_id=rev_audit.id,
                        lines=rev_lines,
                        idempotency_key=f"JE:sale:CustomerAllocationAudit:REV:{audit.id}",
                        user=user,
                        entry_type="automatic",
                        description=f"قيد عكسي لتسوية رصيد مسبق للعميل {audit.customer.name}",
                        reference=f"عكس تخصيص #{audit.id}"
                    )
                except Exception as e:
                    logger.warning(f"لم يتم توليد قيد العكس المحاسبي: {str(e)}")

            PartnerCurrencySnapshotUpdater.trigger_on_commit(
                partner_type="customer",
                partner_id=audit.customer.id,
                currency_code=audit.allocation_currency or "EGP",
                event_type="ALLOCATION_REVERSED"
            )

            return rev_audit

    @classmethod
    def create_prepaid_payment(cls, *args, **kwargs):
        """اسم بديل موحد لإنشاء الدفعات المقدمة"""
        return cls.create_customer_advance_payment(*args, **kwargs)

    @classmethod
    def create_customer_advance_payment(
        cls,
        customer_id: int,
        amount: Decimal,
        payment_date=None,
        payment_method: str = "cash",
        financial_account_id: Optional[int] = None,
        reference_number: Optional[str] = None,
        notes: Optional[str] = None,
        currency=None,
        user=None,
        sales_order=None,
        cost_center=None,
        salesman=None
    ):
        """
        إضافة رصيد مسبق/دفعة مقدمة جديدة للعميل وتوليد القيد المحاسبي التلقائي
        """
        amount = Decimal(str(amount))
        if amount <= Decimal("0.00"):
            raise ValueError("المبلغ يجب أن يكون أكبر من صفر.")

        if not payment_date:
            payment_date = timezone.now().date()

        try:
            from financial.services.period_control_service import PeriodControlService
            PeriodControlService.validate_period_open(payment_date)
        except Exception as e:
            logger.warning(f"Period validation note: {str(e)}")

        with transaction.atomic():
            customer = Customer.objects.select_for_update().get(pk=customer_id)
            
            from financial.models import ChartOfAccounts
            fin_account = None
            if financial_account_id:
                fin_account = ChartOfAccounts.objects.filter(pk=financial_account_id).first()

            from client.models import CustomerPayment
            payment = CustomerPayment.objects.create(
                customer=customer,
                amount=amount,
                currency=currency or customer.default_currency,
                payment_date=payment_date,
                payment_method=payment_method,
                financial_account=fin_account,
                sales_order=sales_order,
                cost_center=cost_center or (sales_order.cost_center if sales_order else None),
                salesman=salesman or (sales_order.salesman if sales_order else None),
                reference_number=reference_number or (f"SO-{sales_order.order_number}" if sales_order else None),
                notes=notes,
                created_by=user,
                status="posted"
            )

            pay_txn, _ = CustomerTransaction.objects.get_or_create(
                customer=customer,
                transaction_number=f"PAY-{payment.id}",
                defaults={
                    "transaction_type": "ADVANCE",
                    "reference_type": "CustomerPayment",
                    "reference_id": str(payment.id),
                    "issue_date": payment_date,
                    "due_date": payment_date,
                    "functional_amount": amount,
                    "open_amount": amount,
                    "open_amount_functional": amount,
                    "status": "OPEN"
                }
            )

            try:
                from governance.services.accounting_gateway import JournalEntryLineData, AccountingGateway
                from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames
                from financial.services.account_helper import AccountHelperService
                from financial.services.exchange_rate_service import ExchangeRateService

                advance_acc = AccountRoleRegistry.get_account(AccountRoleNames.CUSTOMER_ADVANCE_LIABILITY)
                if not advance_acc:
                    advance_acc = ChartOfAccounts.objects.filter(code__in=["21510", "20200"]).first()

                if fin_account:
                    debit_acc_code = fin_account.code
                elif customer.financial_account:
                    debit_acc_code = customer.financial_account.code
                else:
                    default_cash = AccountHelperService.get_default_cash_account()
                    if default_cash:
                        debit_acc_code = default_cash.code
                    else:
                        cash_role_acc = AccountRoleRegistry.get_account(AccountRoleNames.DEFAULT_CASH_DRAWER)
                        debit_acc_code = cash_role_acc.code if cash_role_acc else "11110"

                payment_curr = currency or customer.default_currency
                currency_rate = Decimal("1.000000")
                if payment_curr:
                    try:
                        currency_rate = Decimal(str(ExchangeRateService.get_exchange_rate(payment_curr) or "1.000000"))
                    except Exception:
                        currency_rate = Decimal("1.000000")

                func_amount = (amount * currency_rate).quantize(Decimal("0.01"))
                so_ref_text = f" عن أمر بيع #{sales_order.order_number}" if sales_order else ""
                
                if advance_acc:
                    lines = [
                        JournalEntryLineData(
                            account_code=debit_acc_code,
                            debit=func_amount,
                            credit=Decimal("0.00"),
                            description=f"تحصيل دفعة مقدمة من العميل {customer.name}{so_ref_text}"
                        ),
                        JournalEntryLineData(
                            account_code=advance_acc.code,
                            debit=Decimal("0.00"),
                            credit=func_amount,
                            description=f"دفعة مقدمة للعميل {customer.name}{so_ref_text} - مرجع #{payment.id}"
                        )
                    ]
                    gateway = AccountingGateway()
                    gateway.create_journal_entry(
                        source_module="client",
                        source_model="CustomerPayment",
                        source_id=payment.id,
                        lines=lines,
                        idempotency_key=f"JE:client:CustomerPayment:{payment.id}",
                        user=user,
                        entry_type="automatic",
                        description=f"إثبات دفعة مقدمة للعميل {customer.name}{so_ref_text}",
                        reference=f"دفعة مقدمة #{payment.id}"
                    )
            except Exception as e:
                logger.warning(f"لم يتم توليد قيد الدفعة المقدمة للعميل تلقائياً: {str(e)}")

            # مزامنة لقطات الأرصدة المسبقة والانكشاف المالي للعميل
            try:
                from financial.services.partner_advance_service import PartnerAdvanceService
                PartnerAdvanceService.rebuild_all_snapshots(customer)
                from financial.services.partner_balance_service import PartnerBalanceService
                PartnerBalanceService.update_partner_snapshot("customer", customer.id)
            except Exception as snap_err:
                logger.warning(f"Failed to sync customer advance snapshot: {snap_err}")

            return payment

    @classmethod
    def allocate_prepaid_bulk(
        cls,
        customer_id: int,
        allocations_dict: Dict[int, Decimal],
        user=None,
        allocation_date=None
    ) -> List[CustomerAllocationAudit]:
        """
        تخصيص جماعي لرصيد العميل المسبق على أكثر من فاتورة مبيعات بأسلوب محصن ذرية
        مع إنشاء قيد تسوية تجميعي واحد بمرجعية تجميعية فريدة batch_reference
        """
        if not allocations_dict:
            raise ValueError("لم يتم تحديد أي فواتير للتخصيص.")

        if not allocation_date:
            allocation_date = timezone.now().date()

        try:
            from financial.services.period_control_service import PeriodControlService
            PeriodControlService.validate_period_open(allocation_date)
        except Exception as e:
            logger.warning(f"Period validation note: {str(e)}")

        from sale.models import Sale, SalePayment
        from client.models import CustomerPayment
        from utils.templatetags.utils_extras import smart_float
        from core.models import SystemSetting
        currency_sym = SystemSetting.get_setting('currency_symbol', 'ج.م')

        valid_allocations = {}
        total_requested = Decimal("0.00")

        for sale_id, amt in allocations_dict.items():
            if amt is None:
                continue
            dec_amt = Decimal(str(amt)).quantize(Decimal("0.01"))
            if dec_amt > Decimal("0.00"):
                valid_allocations[int(sale_id)] = dec_amt
                total_requested += dec_amt

        if not valid_allocations or total_requested <= Decimal("0.00"):
            raise ValueError("يرجى إدخال مبالغ تخصيص أكبر من صفر.")

        import uuid
        batch_reference = f"BATCH-CUST-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

        with transaction.atomic():
            locked_customer = Customer.objects.select_for_update().get(pk=customer_id)
            available_balance = locked_customer.available_prepaid_balance

            if total_requested > available_balance:
                raise ValueError(
                    f"إجمالي مبالغ التخصيص المطلوبة ({smart_float(total_requested)} {currency_sym}) "
                    f"يتجاوز رصيد العميل المسبق المتاح ({smart_float(available_balance)} {currency_sym})."
                )

            sales = list(
                Sale.objects.select_for_update().filter(
                    id__in=valid_allocations.keys(),
                    customer=locked_customer,
                    status__in=["confirmed", "posted"]
                ).order_by("id")
            )

            customer_payments = list(
                CustomerPayment.objects.select_for_update().filter(
                    customer_id=locked_customer.id,
                    status="posted"
                ).order_by("payment_date", "created_at")
            )

            audits_created = []
            total_actually_allocated = Decimal("0.00")
            now = timezone.now()

            for sale in sales:
                req_amt = valid_allocations.get(sale.id, Decimal("0.00"))
                if req_amt <= Decimal("0.00"):
                    continue

                open_sale_amount = sale.total - (sale.amount_paid or Decimal("0.00"))
                if req_amt > open_sale_amount:
                    raise ValueError(
                        f"المبلغ المراد تخصيصه ({smart_float(req_amt)} {currency_sym}) "
                        f"يتجاوز المتبقي من الفاتورة #{sale.number} ({smart_float(open_sale_amount)} {currency_sym})."
                    )

                remaining_for_sale = req_amt

                inv_txn, _ = CustomerTransaction.objects.select_for_update().get_or_create(
                    customer=locked_customer,
                    transaction_number=sale.number,
                    defaults={
                        "transaction_type": "INVOICE",
                        "reference_type": "Sale",
                        "reference_id": str(sale.id),
                        "issue_date": sale.date,
                        "due_date": sale.date,
                        "functional_amount": sale.total,
                        "open_amount": open_sale_amount,
                        "open_amount_functional": open_sale_amount,
                        "status": "OPEN" if (sale.amount_paid or Decimal("0.00")) == Decimal("0.00") else "PARTIAL"
                    }
                )

                sale_curr_id = sale.currency_id
                for cp in customer_payments:
                    if remaining_for_sale <= Decimal("0.00"):
                        break

                    cp_curr_id = cp.currency_id
                    if sale_curr_id != cp_curr_id:
                        is_egp_match = (
                            (sale_curr_id is None and cp.currency and cp.currency.code == "EGP") or
                            (cp_curr_id is None and sale.currency and sale.currency.code == "EGP")
                        )
                        if not is_egp_match:
                            continue

                    already_allocated = sum(sp.amount for sp in SalePayment.objects.filter(customer_payment=cp))
                    cp_remaining = max(Decimal("0.00"), cp.amount - already_allocated)

                    if cp_remaining <= Decimal("0.00"):
                        continue

                    curr_alloc = min(cp_remaining, remaining_for_sale)
                    remaining_for_sale -= curr_alloc
                    total_actually_allocated += curr_alloc

                    pay_txn, _ = CustomerTransaction.objects.select_for_update().get_or_create(
                        customer=locked_customer,
                        transaction_number=f"PAY-{cp.id}",
                        defaults={
                            "transaction_type": "ADVANCE",
                            "reference_type": "CustomerPayment",
                            "reference_id": str(cp.id),
                            "issue_date": cp.payment_date,
                            "due_date": cp.payment_date,
                            "functional_amount": cp.amount,
                            "open_amount": cp_remaining,
                            "open_amount_functional": cp_remaining,
                            "status": "PARTIAL" if cp_remaining > 0 else "CLOSED"
                        }
                    )

                    pay_txn.open_amount = max(Decimal("0.00"), pay_txn.open_amount - curr_alloc)
                    pay_txn.open_amount_functional = pay_txn.open_amount
                    pay_txn.status = "CLOSED" if pay_txn.open_amount == Decimal("0.00") else "PARTIAL"
                    pay_txn.save()

                    inv_txn.open_amount = max(Decimal("0.00"), inv_txn.open_amount - curr_alloc)
                    inv_txn.open_amount_functional = inv_txn.open_amount
                    inv_txn.status = "CLOSED" if inv_txn.open_amount == Decimal("0.00") else "PARTIAL"
                    inv_txn.save()

                    ev_hash = cls.generate_evidence_hash(
                        customer_id=locked_customer.id,
                        payment_txn_id=pay_txn.id,
                        invoice_txn_id=inv_txn.id,
                        allocated_amount=curr_alloc,
                        allocation_date=allocation_date,
                        created_at=now
                    )

                    audit = CustomerAllocationAudit.objects.create(
                        customer=locked_customer,
                        allocation_reference=f"{batch_reference}-{len(audits_created)+1}",
                        payment_transaction=pay_txn,
                        invoice_transaction=inv_txn,
                        source_document_type="ADVANCE_PAYMENT",
                        source_document_number=f"PAY-{cp.id}",
                        target_document_type="SALES_INVOICE",
                        target_document_number=sale.number,
                        allocation_type="ADVANCE_TO_INVOICE",
                        allocated_amount=curr_alloc,
                        functional_amount=curr_alloc,
                        allocation_status="APPLIED",
                        allocation_date=allocation_date,
                        created_by=user,
                        evidence_hash=ev_hash
                    )
                    audits_created.append(audit)

                    SalePayment.objects.create(
                        sale=sale,
                        amount=curr_alloc,
                        payment_date=cp.payment_date if (cp and getattr(cp, "payment_date", None)) else allocation_date,
                        payment_method="prepaid_balance",
                        source_type="PREPAID_BALANCE",
                        customer_payment=cp,
                        reference_number=batch_reference,
                        notes=f"تخصيص جماعي من الرصيد المسبق للعميل (دفعة #{cp.id} - دفعة {batch_reference})",
                        created_by=user or sale.created_by,
                        status="posted",
                        financial_status="synced"
                    )

                if hasattr(sale, "update_payment_status"):
                    sale.update_payment_status()

            if total_actually_allocated > Decimal("0.00") and locked_customer.financial_account:
                try:
                    from financial.models import ChartOfAccounts
                    advance_acc = ChartOfAccounts.objects.filter(code="20200").first()
                    if advance_acc:
                        lines = [
                            JournalEntryLineData(
                                account_code=advance_acc.code,
                                debit=total_actually_allocated,
                                credit=Decimal("0.00"),
                                description=f"إغلاق دفعات مقدمة للعميل {locked_customer.name} - دفعة {batch_reference}"
                            ),
                            JournalEntryLineData(
                                account_code=locked_customer.financial_account.code,
                                debit=Decimal("0.00"),
                                credit=total_actually_allocated,
                                description=f"تخصيص جماعي رصيد مسبق للعميل - دفعة {batch_reference}"
                            )
                        ]
                        gateway = AccountingGateway()
                        gateway.create_journal_entry(
                            source_module="sale",
                            source_model="CustomerAllocationAudit",
                            source_id=audits_created[0].id if audits_created else locked_customer.id,
                            lines=lines,
                            idempotency_key=f"JE:bulk_alloc:{batch_reference}",
                            user=user,
                            entry_type="automatic",
                            description=f"قيد تسوية تجميعي رصيد مسبق للعميل {locked_customer.name}",
                            reference=batch_reference
                        )
                except Exception as e:
                    logger.warning(f"لم يتم توليد قيد التسوية المحاسبي التلقائي لتخصيص العميل الجماعي: {str(e)}")

            return audits_created

