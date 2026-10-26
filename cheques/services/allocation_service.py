# -*- coding: utf-8 -*-
"""
FIN-CHQ-ALLOC: Cheque Invoice Allocation Service
خدمة تخصيص أوراق القبض على فواتير المبيعات مع التدقيق المالي المشفر SHA-256
"""
import hashlib
import logging
import uuid
from decimal import Decimal
from typing import Optional, Dict, Any, List

from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from cheques.models import (
    Cheque,
    ChequeType,
    ChequePurpose,
    ChequeStatus,
    ChequeInvoiceAllocation,
    AllocationStatus,
)
from customer.models import Customer, CustomerTransaction, CustomerAllocationAudit
from customer.services.customer_allocation_audit_service import CustomerAllocationAuditService
from financial.services.partner_subledger_service import PartnerSubledgerService
from sale.models import Sale, SalePayment

logger = logging.getLogger(__name__)


class ChequeAllocationService:
    """
    خدمة موحدة لإدارة تخصيص أوراق القبض على فواتير المبيعات
    وتسجيل سجلات التدقيق المشفرة CustomerAllocationAudit دون أي ازدواج قيدي
    """

    @classmethod
    def allocate_cheque_to_invoice(
        cls,
        cheque: Cheque,
        sale: Sale,
        amount: Decimal,
        user=None,
        notes: Optional[str] = None,
        idempotency_key: Optional[str] = None
    ) -> ChequeInvoiceAllocation:
        """
        تخصيص ورقة قبض على فاتورة مبيعات محددة:
        1. التحقق من تطابق العميل والحدود المالية ومنع التكرار الحتمي (Idempotency)
        2. إنشاء أو جلب CustomerTransaction للفاتورة والشيك
        3. تسجيل CustomerAllocationAudit مع التوقيع المشفر SHA-256
        4. تسجيل سجل السداد SalePayment (financial_account=None, source_type='CHEQUE')
        5. إنشاء ChequeInvoiceAllocation
        6. تحديث حالة سداد الفاتورة تلقائياً
        """
        if not isinstance(amount, Decimal):
            amount = Decimal(str(amount))

        if amount <= Decimal("0.00"):
            raise ValidationError(_("يجب أن يكون مبلغ التخصيص أكبر من الصفر."))

        if cheque.cheque_type != ChequeType.RECEIVABLE:
            raise ValidationError(_("يمكن تخصيص شيكات القبض فقط على فواتير المبيعات."))

        if cheque.purpose == ChequePurpose.SECURITY_GUARANTEE:
            raise ValidationError(_("لا يمكن تخصيص شيك الضمان على فواتير المبيعات قبل تحويله إلى شيك تشغيلي."))

        if cheque.status in [ChequeStatus.DRAFT, ChequeStatus.BOUNCED, ChequeStatus.CANCELLED, ChequeStatus.RETURNED_TO_DRAWER]:
            raise ValidationError(_(f"لا يمكن تخصيص شيك في حالة: {cheque.get_status_display()}."))

        # التحقق من تطابق العميل
        if cheque.customer_id and sale.customer_id and cheque.customer_id != sale.customer_id:
            raise ValidationError(_("العميل في الشيك لا يتطابق مع العميل في فاتورة المبيعات."))

        alloc_ref = f"ALLOC:{idempotency_key}" if idempotency_key else f"ALLOC-{cheque.voucher_number}->{sale.number}-{uuid.uuid4().hex[:8]}"

        with transaction.atomic():
            # فحص منع التكرار الحتمي Idempotency Guard
            if idempotency_key:
                existing_audit = CustomerAllocationAudit.objects.filter(
                    allocation_reference=alloc_ref,
                    allocation_status="APPLIED"
                ).first()
                if existing_audit:
                    existing_alloc = ChequeInvoiceAllocation.objects.filter(
                        allocation_audit=existing_audit
                    ).first()
                    if existing_alloc:
                        # فحص تطابق المعلمات الأساسية (الشيك، الفاتورة، المبلغ) لمنع التعارض والنجاح المضلل
                        if (
                            existing_alloc.cheque_id != cheque.id
                            or existing_alloc.sale_id != sale.id
                            or existing_alloc.allocated_amount != amount
                        ):
                            raise ValidationError(
                                _("تعارض في مفتاح عدم التكرار: المفتاح مستخدم مسبقاً لعملية تخصيص أخرى أو بمبلغ مختلف.")
                            )
                        logger.info(f"Idempotent retry hit for allocation: {idempotency_key}")
                        return existing_alloc

            # قفل السجلات لمنع تضارب العمليات المتزامنة
            locked_cheque = Cheque.objects.select_for_update().get(pk=cheque.pk)
            locked_sale = Sale.objects.select_for_update().get(pk=sale.pk)

            # التحقق من المتبقي غير المخصص في الشيك
            already_allocated = locked_cheque.invoice_allocations.filter(
                allocation_status=AllocationStatus.APPLIED
            ).aggregate(total=models.Sum('allocated_amount'))['total'] or Decimal('0.00')

            available_on_cheque = locked_cheque.amount - already_allocated
            if amount > available_on_cheque:
                raise ValidationError(
                    _(f"المبلغ المطلوب تخصيصه ({amount}) يتجاوز الرصيد المتاح في الشيك ({available_on_cheque}).")
                )

            # التحقق من تطابق عملة الشيك والفاتورة لضمان اتساق الأستاذ المساعد
            cheque_curr = locked_cheque.currency.code if locked_cheque.currency else "EGP"
            sale_curr = locked_sale.currency.code if locked_sale.currency else "EGP"
            if cheque_curr != sale_curr:
                raise ValidationError(
                    _(f"لا يمكن تخصيص شيك بعملة ({cheque_curr}) على فاتورة بعملة ({sale_curr}). يجب تطابق عملة الشيك والفاتورة لضمان سلامة الأستاذ المساعد.")
                )

            # التحقق من المتبقي على الفاتورة
            if amount > locked_sale.amount_due:
                raise ValidationError(
                    _(f"المبلغ المطلوب تخصيصه ({amount}) يتجاوز المبلغ المتبقي على الفاتورة ({locked_sale.amount_due}).")
                )

            # 1. ضمان وجود معاملة الأستاذ المساعد للفاتورة
            inv_txn = PartnerSubledgerService.record_sale_invoice(locked_sale)
            if not inv_txn:
                # إنشاء سجل يدوي للأستاذ المساعد إذا تعذر التسجيل التلقائي
                inv_txn, _inv_created = CustomerTransaction.objects.get_or_create(
                    customer=locked_sale.customer,
                    transaction_type="INVOICE",
                    reference_id=str(locked_sale.id),
                    defaults={
                        "transaction_number": locked_sale.number,
                        "issue_date": locked_sale.date,
                        "due_date": locked_sale.date,
                        "currency": locked_sale.currency.code if locked_sale.currency else "EGP",
                        "foreign_amount": locked_sale.total,
                        "exchange_rate": getattr(locked_sale, "exchange_rate", Decimal("1.000000")) or Decimal("1.000000"),
                        "functional_amount": (Decimal(str(locked_sale.total)) * (getattr(locked_sale, "exchange_rate", Decimal("1.000000")) or Decimal("1.000000"))).quantize(Decimal("0.01")),
                        "open_amount": locked_sale.amount_due,
                        "open_amount_functional": locked_sale.amount_due,
                        "open_amount_foreign": locked_sale.amount_due,
                        "status": "OPEN",
                    }
                )

            # 2. ضمان وجود معاملة الأستاذ المساعد للشيك
            rate = locked_cheque.original_exchange_rate or Decimal("1.000000")
            curr_code = locked_cheque.currency.code if locked_cheque.currency else "EGP"
            func_total = (locked_cheque.amount * rate).quantize(Decimal("0.01"))

            pay_txn, _pay_created = CustomerTransaction.objects.get_or_create(
                customer=locked_sale.customer,
                transaction_type="CHEQUE",
                reference_id=str(locked_cheque.id),
                defaults={
                    "transaction_number": locked_cheque.voucher_number,
                    "issue_date": locked_cheque.issue_date or timezone.localdate(),
                    "due_date": locked_cheque.due_date,
                    "currency": curr_code,
                    "foreign_amount": locked_cheque.amount,
                    "exchange_rate": rate,
                    "functional_amount": func_total,
                    "open_amount": func_total,
                    "open_amount_functional": func_total,
                    "open_amount_foreign": locked_cheque.amount,
                    "status": "OPEN",
                }
            )

            now = timezone.now()
            functional_amount = (amount * rate).quantize(Decimal("0.01"))

            # سعر صرف الفاتورة وقيمتها الوظيفية الدفترية وفصل فروق العملة المحققة
            inv_rate = getattr(inv_txn, "exchange_rate", None) or getattr(locked_sale, "exchange_rate", None) or Decimal("1.000000")
            inv_rate = Decimal(str(inv_rate))
            inv_functional_amount = (amount * inv_rate).quantize(Decimal("0.01"))
            realized_fx = (functional_amount - inv_functional_amount).quantize(Decimal("0.01"))

            # 3. إنشاء توقيع التدقيق المشفر SHA-256 وسجل CustomerAllocationAudit
            ev_hash = CustomerAllocationAuditService.generate_evidence_hash(
                customer_id=locked_sale.customer.id,
                payment_txn_id=pay_txn.id,
                invoice_txn_id=inv_txn.id,
                allocated_amount=amount,
                allocation_date=now.date(),
                created_at=now
            )

            audit = CustomerAllocationAudit.objects.create(
                customer=locked_sale.customer,
                allocation_reference=alloc_ref,
                payment_transaction=pay_txn,
                invoice_transaction=inv_txn,
                source_document_type="CHEQUE",
                source_document_number=locked_cheque.voucher_number,
                target_document_type="SALES_INVOICE",
                target_document_number=locked_sale.number,
                allocation_type="PAYMENT_TO_INVOICE",
                allocated_amount=amount,
                allocation_currency=curr_code,
                exchange_rate=rate,
                functional_amount=functional_amount,
                realized_fx_difference=realized_fx,
                allocation_status="APPLIED",
                allocation_date=now.date(),
                created_by=user,
                evidence_hash=ev_hash
            )

            # 4. تسجيل دفعة الفاتورة SalePayment مفوضة الترحيل المحاسبي (financial_account=None)
            sale_payment = SalePayment.objects.create(
                sale=locked_sale,
                amount=amount,
                payment_date=locked_cheque.issue_date or now.date(),
                payment_method="check",
                source_type="CHEQUE",
                reference_number=locked_cheque.voucher_number,
                financial_account=None,
                notes=notes or f"سداد بموجب شيك قبض #{locked_cheque.voucher_number}",
                created_by=user or locked_sale.created_by,
                status="posted",
                financial_status="synced"
            )

            # 5. إنشاء قيد محاسبي لنقل الرصيد من التزام الدفعة المقدمة إلى حساب العميل التجاري (في حالة شيكات الدفعات المقدمة) أو قيد فروق العملة
            alloc_je = None
            if locked_cheque.purpose == ChequePurpose.ADVANCE_PAYMENT:
                try:
                    from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames
                    from financial.services.subledger_account_service import SubledgerAccountService
                    from governance.services.accounting_gateway import AccountingGateway, JournalEntryLineData

                    advance_acc = AccountRoleRegistry.get_account(AccountRoleNames.CUSTOMER_ADVANCE_LIABILITY)
                    cust_acc = SubledgerAccountService.get_or_create_customer_account(locked_sale.customer, user=user)

                    gateway_lines = [
                        JournalEntryLineData(
                            account_code=advance_acc.code,
                            debit=functional_amount,
                            credit=Decimal("0.00"),
                            description=f"تسوية دفعة مقدمة لشيك #{locked_cheque.cheque_number} على فاتورة {locked_sale.number}",
                            cost_center=None,
                            currency=curr_code,
                            exchange_rate=rate,
                        ),
                        JournalEntryLineData(
                            account_code=cust_acc.code,
                            debit=Decimal("0.00"),
                            credit=inv_functional_amount,
                            description=f"سداد فاتورة {locked_sale.number} من دفعة مقدمة لشيك #{locked_cheque.cheque_number}",
                            cost_center=None,
                            currency=curr_code,
                            exchange_rate=inv_rate,
                        ),
                    ]

                    if realized_fx != Decimal("0.00"):
                        if realized_fx > Decimal("0.00"):
                            gain_acc = AccountRoleRegistry.get_account(AccountRoleNames.FX_REALIZED_GAIN)
                            gateway_lines.append(
                                JournalEntryLineData(
                                    account_code=gain_acc.code,
                                    debit=Decimal("0.00"),
                                    credit=realized_fx,
                                    description=f"أرباح فروق عملة محققة - تسوية شيك #{locked_cheque.cheque_number} على فاتورة {locked_sale.number}",
                                    cost_center=None,
                                )
                            )
                        else:
                            loss_acc = AccountRoleRegistry.get_account(AccountRoleNames.FX_REALIZED_LOSS)
                            gateway_lines.append(
                                JournalEntryLineData(
                                    account_code=loss_acc.code,
                                    debit=abs(realized_fx),
                                    credit=Decimal("0.00"),
                                    description=f"خسائر فروق عملة محققة - تسوية شيك #{locked_cheque.cheque_number} على فاتورة {locked_sale.number}",
                                    cost_center=None,
                                )
                            )

                    gateway = AccountingGateway()
                    alloc_je = gateway.create_journal_entry(
                        source_module="cheques",
                        source_model="Cheque",
                        source_id=locked_cheque.id,
                        lines=gateway_lines,
                        idempotency_key=f"JE:cheques:ChequeAllocation:{locked_cheque.id}:{locked_sale.id}:{audit.allocation_reference}",
                        user=user,
                        entry_type="customer_payment",
                        description=f"تسوية دفعة مقدمة لشيك #{locked_cheque.cheque_number} على فاتورة {locked_sale.number}",
                        reference=locked_cheque.voucher_number,
                        date=now.date(),
                    )
                    if not alloc_je:
                        raise ValidationError(_("فشلت بوابة القيود في إنشاء قيد تسوية الدفعة المقدمة."))
                except Exception as alloc_err:
                    logger.error(f"Advance payment allocation GL entry error: {alloc_err}")
                    raise ValidationError(_("فشل ترحيل قيد تسوية الدفعة المقدمة: {err}").format(err=str(alloc_err)))
            elif realized_fx != Decimal("0.00"):
                # شيك قبض عادي بفارق سعر صرف بين الشيك والفاتورة: إثبات قيد فروق الصرف المحققة
                try:
                    from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames
                    from financial.services.subledger_account_service import SubledgerAccountService
                    from governance.services.accounting_gateway import AccountingGateway, JournalEntryLineData

                    cust_acc = SubledgerAccountService.get_or_create_customer_account(locked_sale.customer, user=user)
                    if realized_fx > Decimal("0.00"):
                        gain_acc = AccountRoleRegistry.get_account(AccountRoleNames.FX_REALIZED_GAIN)
                        gateway_lines = [
                            JournalEntryLineData(
                                account_code=cust_acc.code,
                                debit=realized_fx,
                                credit=Decimal("0.00"),
                                description=f"تسوية فرق عملة محقق - سداد فاتورة {locked_sale.number} بشيك #{locked_cheque.cheque_number}",
                                cost_center=None,
                            ),
                            JournalEntryLineData(
                                account_code=gain_acc.code,
                                debit=Decimal("0.00"),
                                credit=realized_fx,
                                description=f"أرباح فروق عملة محققة - تسوية شيك #{locked_cheque.cheque_number} على فاتورة {locked_sale.number}",
                                cost_center=None,
                            )
                        ]
                    else:
                        loss_acc = AccountRoleRegistry.get_account(AccountRoleNames.FX_REALIZED_LOSS)
                        gateway_lines = [
                            JournalEntryLineData(
                                account_code=loss_acc.code,
                                debit=abs(realized_fx),
                                credit=Decimal("0.00"),
                                description=f"خسائر فروق عملة محققة - تسوية شيك #{locked_cheque.cheque_number} على فاتورة {locked_sale.number}",
                                cost_center=None,
                            ),
                            JournalEntryLineData(
                                account_code=cust_acc.code,
                                debit=Decimal("0.00"),
                                credit=abs(realized_fx),
                                description=f"تسوية فرق عملة محقق - سداد فاتورة {locked_sale.number} بشيك #{locked_cheque.cheque_number}",
                                cost_center=None,
                            )
                        ]

                    gateway = AccountingGateway()
                    alloc_je = gateway.create_journal_entry(
                        source_module="cheques",
                        source_model="Cheque",
                        source_id=locked_cheque.id,
                        lines=gateway_lines,
                        idempotency_key=f"JE:cheques:ChequeFXAllocation:{locked_cheque.id}:{locked_sale.id}:{audit.allocation_reference}",
                        user=user,
                        entry_type="fx_settlement",
                        description=f"قيد فروق عملة محققة لتخصيص شيك #{locked_cheque.cheque_number} على فاتورة {locked_sale.number}",
                        reference=locked_cheque.voucher_number,
                        date=now.date(),
                    )
                except Exception as fx_err:
                    logger.error(f"FX allocation GL entry error: {fx_err}")
                    raise ValidationError(_("فشل ترحيل قيد فرق العملة لتخصيص الشيك: {err}").format(err=str(fx_err)))

            # 6. تحديث أرصدة وحالات الأستاذ المساعد للعميل بالقيمة الدفترية للفاتورة
            inv_txn.open_amount = max(Decimal("0.00"), inv_txn.open_amount - inv_functional_amount)
            inv_txn.open_amount_functional = inv_txn.open_amount
            if inv_txn.exchange_rate and inv_txn.exchange_rate > Decimal("0.000000"):
                inv_txn.open_amount_foreign = (inv_txn.open_amount / inv_txn.exchange_rate).quantize(Decimal("0.01"))
            inv_txn.status = "CLOSED" if inv_txn.open_amount <= Decimal("0.00") else "PARTIAL"
            inv_txn.save()

            pay_txn.open_amount = max(Decimal("0.00"), pay_txn.open_amount - functional_amount)
            pay_txn.open_amount_functional = pay_txn.open_amount
            if pay_txn.exchange_rate and pay_txn.exchange_rate > Decimal("0.000000"):
                pay_txn.open_amount_foreign = (pay_txn.open_amount / pay_txn.exchange_rate).quantize(Decimal("0.01"))
            pay_txn.status = "CLOSED" if pay_txn.open_amount <= Decimal("0.00") else "PARTIAL"
            pay_txn.save()

            # 7. إنشاء سجل التخصيص ChequeInvoiceAllocation مع الربط المباشر بسجل السداد والتدقيق
            alloc = ChequeInvoiceAllocation.objects.create(
                cheque=locked_cheque,
                sale=locked_sale,
                allocated_amount=amount,
                allocated_amount_functional=functional_amount,
                allocation_status=AllocationStatus.APPLIED,
                allocation_date=now.date(),
                journal_entry=alloc_je,
                sale_payment=sale_payment,
                allocation_audit=audit,
                notes=notes or f"تخصيص شيك {locked_cheque.voucher_number} على فاتورة {locked_sale.number}"
            )

            # 7. تحديث حالة سداد الفاتورة
            locked_sale.update_payment_status()

            logger.info(
                f"✅ تم تخصيص الشيك {locked_cheque.voucher_number} على الفاتورة {locked_sale.number} "
                f"بمبلغ {amount} {curr_code} (Audit #{audit.id})"
            )
            return alloc

    @classmethod
    def reverse_cheque_allocation(
        cls,
        allocation: ChequeInvoiceAllocation,
        reason: str,
        user=None
    ) -> None:
        """
        عكس تخصيص شيك على فاتورة مبيعات:
        1. تحويل ChequeInvoiceAllocation إلى REVERSED
        2. إنشاء سجل عكس CustomerAllocationAudit
        3. تحويل SalePayment إلى reversed
        4. عكس قيد اليومية المرتبط بالتسوية إن وجد
        5. إعادة احتساب حالة الفاتورة لفتحها مجدداً
        """
        if allocation.allocation_status == AllocationStatus.REVERSED:
            raise ValidationError(_("هذا التخصيص معكوس بالفعل سابقاً."))

        with transaction.atomic():
            locked_alloc = ChequeInvoiceAllocation.objects.select_for_update().get(pk=allocation.pk)
            sale = locked_alloc.sale
            cheque = locked_alloc.cheque

            # 1. تحديث حالة التخصيص
            locked_alloc.allocation_status = AllocationStatus.REVERSED
            locked_alloc.notes = f"{locked_alloc.notes or ''} [MANUAL_REV: {reason}]".strip()
            locked_alloc.save(update_fields=['allocation_status', 'notes'])

            # 2. جلب سجل التدقيق المرتبط بالتخصيص المحدد وإنشاء سجل العكس
            orig_audit = getattr(locked_alloc, "allocation_audit", None)
            if not orig_audit:
                orig_audit = CustomerAllocationAudit.objects.filter(
                    target_document_number=sale.number,
                    source_document_number=cheque.voucher_number,
                    allocated_amount=locked_alloc.allocated_amount,
                    allocation_status="APPLIED"
                ).first() or CustomerAllocationAudit.objects.filter(
                    target_document_number=sale.number,
                    source_document_number=cheque.voucher_number,
                    allocation_status="APPLIED"
                ).first()

            if orig_audit:
                now = timezone.now()
                raw_hash = f"REV:{orig_audit.id}:{locked_alloc.allocated_amount}:{now.isoformat()}"
                rev_hash = hashlib.sha256(raw_hash.encode("utf-8")).hexdigest()
                CustomerAllocationAudit.objects.create(
                    customer=orig_audit.customer,
                    allocation_reference=f"REV-{orig_audit.id}-{uuid.uuid4().hex[:8]}",
                    payment_transaction=orig_audit.payment_transaction,
                    invoice_transaction=orig_audit.invoice_transaction,
                    source_document_type="CHEQUE",
                    source_document_number=cheque.voucher_number,
                    target_document_type="SALES_INVOICE",
                    target_document_number=sale.number,
                    allocation_type="REVERSAL",
                    allocated_amount=locked_alloc.allocated_amount,
                    functional_amount=locked_alloc.allocated_amount_functional,
                    allocation_status="REVERSED",
                    reversed_audit=orig_audit,
                    allocation_date=now.date(),
                    created_by=user,
                    evidence_hash=rev_hash
                )

            # 3. تحويل دفعة الفاتورة SalePayment الخاصة بهذا التخصيص فقط إلى reversed
            if getattr(locked_alloc, "sale_payment", None):
                locked_alloc.sale_payment.status = "reversed"
                locked_alloc.sale_payment.save(update_fields=["status"])
            else:
                target_payment = SalePayment.objects.filter(
                    sale=sale,
                    source_type="CHEQUE",
                    reference_number=cheque.voucher_number,
                    amount=locked_alloc.allocated_amount,
                    status="posted"
                ).first()
                if target_payment:
                    target_payment.status = "reversed"
                    target_payment.save(update_fields=["status"])
                else:
                    SalePayment.objects.filter(
                        sale=sale,
                        source_type="CHEQUE",
                        reference_number=cheque.voucher_number,
                        status="posted"
                    ).order_by("-id")[:1].update(status="reversed")

            # 4. عكس قيد اليومية المرتبط بالتسوية إن وُجد
            if locked_alloc.journal_entry:
                try:
                    from financial.services.ledger_core_service import LedgerCoreService
                    LedgerCoreService.reverse_entry(
                        entry_id=locked_alloc.journal_entry_id,
                        user=user,
                        reversal_reason=f"عكس قيد تسوية الدفعة المقدمة على الفاتورة {sale.number}: {reason}"
                    )
                except Exception as je_err:
                    logger.error(f"Error reversing allocation journal entry: {je_err}")
                    raise ValidationError(_(f"فشل عكس قيد اليومية لتسوية الدفعة المقدمة: {je_err}"))

            # 5. تحديث حالة الفاتورة
            sale.update_payment_status()

            # 6. استعادة أرصدة وحالات الأستاذ المساعد للعميل بالقيمة الدفترية لكل طرف
            if orig_audit and orig_audit.invoice_transaction:
                inv_txn = orig_audit.invoice_transaction
                inv_rate = Decimal(str(inv_txn.exchange_rate or "1.000000"))
                inv_restore_functional = (locked_alloc.allocated_amount * inv_rate).quantize(Decimal("0.01"))
                inv_txn.open_amount = min(inv_txn.functional_amount, inv_txn.open_amount + inv_restore_functional)
                inv_txn.open_amount_functional = inv_txn.open_amount
                if inv_txn.exchange_rate and inv_txn.exchange_rate > Decimal("0.000000"):
                    inv_txn.open_amount_foreign = (inv_txn.open_amount / inv_txn.exchange_rate).quantize(Decimal("0.01"))
                inv_txn.status = "OPEN" if inv_txn.open_amount >= inv_txn.functional_amount else "PARTIAL"
                inv_txn.save()

            if orig_audit and orig_audit.payment_transaction:
                pay_txn = orig_audit.payment_transaction
                pay_rate = Decimal(str(pay_txn.exchange_rate or "1.000000"))
                pay_restore_functional = (locked_alloc.allocated_amount * pay_rate).quantize(Decimal("0.01"))
                pay_txn.open_amount = min(pay_txn.functional_amount, pay_txn.open_amount + pay_restore_functional)
                pay_txn.open_amount_functional = pay_txn.open_amount
                if pay_txn.exchange_rate and pay_txn.exchange_rate > Decimal("0.000000"):
                    pay_txn.open_amount_foreign = (pay_txn.open_amount / pay_txn.exchange_rate).quantize(Decimal("0.01"))
                pay_txn.status = "OPEN" if pay_txn.open_amount >= pay_txn.functional_amount else "PARTIAL"
                pay_txn.save()

            logger.info(
                f"↩️ تم عكس تخصيص الشيك {cheque.voucher_number} على الفاتورة {sale.number} "
                f"بمبلغ {locked_alloc.allocated_amount} (السبب: {reason})"
            )
