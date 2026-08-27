import uuid
import json
import hashlib
import logging
from decimal import Decimal
from typing import List, Dict, Any, Optional
from django.db import transaction
from django.utils import timezone

from sale.models import (
    CreditNote,
    CreditNoteItem,
    CreditNoteAllocation,
    CreditNoteReversal,
    CreditNoteAudit,
    SalesReturnHeader,
    SalesInvoice,
    SalesInvoiceItem,
)
from sale.services.credit_note_decision import (
    CreditNoteDecision,
    CreditNoteAccountingCommand,
)
from client.services.customer_subledger_service import CustomerSubledgerService
from governance.services.accounting_gateway import create_credit_note_posting, create_credit_note_reversal_posting
from financial.exceptions import FinancialCoreError

logger = logging.getLogger("sale.services.sales_reversal_service")


class SalesReversalService:
    """
    FIN-SAL-005 v2.0: Sales Reversal & Credit Note Engine Service (Locked Master Final)
    محرك إصدار ومعالجة الإشعارات الدائنة وعكس المبيعات والضريبة والتسوية بالأستاذ الفرعي للعملاء
    """

    @classmethod
    def generate_canonical_credit_note_hash(
        cls,
        correlation_id: str,
        processed_event_id: str,
        credit_note_number: str,
        total_amount: Decimal,
        timestamp: str
    ) -> str:
        """
        إنشاء التوقيع المشفر Canonical JSON SHA256 لسجل تدقيق وتوثيق الإشعار الدائن المالي
        """
        payload = {
            "correlation_id": str(correlation_id),
            "credit_note_number": str(credit_note_number),
            "processed_event_id": str(processed_event_id),
            "timestamp": str(timestamp),
            "total_amount": str(total_amount)
        }
        canonical_json = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    @classmethod
    def create_credit_note_for_return(
        cls,
        return_header_id: int,
        reason: str = "Sales Return Processing",
        user=None
    ) -> CreditNote:
        """
        إنشاء مسودة إشعار دائن بناءً على مستند إرجاع مبيعات معتمد ومعد لمكافأة العميل
        """
        with transaction.atomic():
            ret_header = SalesReturnHeader.objects.select_for_update().get(pk=return_header_id)
            if ret_header.status not in ["PROCESSED", "INSPECTED", "APPROVED"]:
                raise FinancialCoreError(f"Credit Note Creation Error: Return #{ret_header.return_number} must be inspected/processed.")

            cn_num = f"CN-{uuid.uuid4().hex[:8].upper()}"
            cn = CreditNote.objects.create(
                credit_note_number=cn_num,
                customer=ret_header.customer,
                sales_invoice=ret_header.sales_invoice,
                sales_return=ret_header,
                source_type="SALES_RETURN",
                status="APPROVED",
                reason=reason,
                currency=ret_header.sales_invoice.currency if ret_header.sales_invoice else "EGP",
                exchange_rate=ret_header.sales_invoice.exchange_rate if ret_header.sales_invoice else Decimal("1.000000"),
                created_by=user
            )

            tot_subtotal = Decimal("0.00")
            tot_tax = Decimal("0.00")

            for item in ret_header.items.all():
                qty = item.restored_qty if item.restored_qty > Decimal("0.00") else item.approved_qty
                if qty > Decimal("0.00"):
                    # Find unit selling price from sales invoice item or delivery item so_item
                    unit_p = item.delivery_item.so_item.unit_price if hasattr(item.delivery_item, 'so_item') else Decimal("0.00")
                    line_sub = (qty * unit_p).quantize(Decimal("0.01"))
                    
                    # Dynamically resolve product tax rate from original sales line or product
                    orig_tax_rate = None
                    if hasattr(item, 'delivery_item') and hasattr(item.delivery_item, 'so_item') and getattr(item.delivery_item.so_item, 'tax_rate', None) is not None and item.delivery_item.so_item.tax_rate > Decimal("0.00"):
                        orig_tax_rate = Decimal(str(item.delivery_item.so_item.tax_rate))
                    
                    if orig_tax_rate is not None:
                        rate_val = orig_tax_rate
                    elif getattr(item.product, 'is_tax_exempt', False):
                        rate_val = Decimal("0.00")
                    elif getattr(item.product, 'tax_code', None):
                        rate_val = item.product.tax_code.rate
                    elif getattr(item.product, 'tax_rate', None) is not None and item.product.tax_rate > Decimal("0.00"):
                        rate_val = Decimal(str(item.product.tax_rate))
                    else:
                        from financial.models import TaxCode
                        default_tax = TaxCode.objects.filter(is_default=True, is_active=True).first() or TaxCode.objects.filter(code__in=["T1", "VAT14", "VAT_14", "VAT"]).first()
                        rate_val = default_tax.rate if default_tax else Decimal("14.00")

                    line_vat = (line_sub * (rate_val / Decimal("100.00"))).quantize(Decimal("0.01"))
                    line_tot = line_sub + line_vat

                    CreditNoteItem.objects.create(
                        credit_note=cn,
                        product=item.product,
                        description=f"Sales Return: {item.product.name}",
                        quantity=qty,
                        unit_price=unit_p,
                        subtotal=line_sub,
                        tax_amount=line_vat,
                        total_amount=line_tot
                    )

                    tot_subtotal += line_sub
                    tot_tax += line_vat

            cn.subtotal_amount = tot_subtotal
            cn.tax_amount = tot_tax
            cn.total_amount = tot_subtotal + tot_tax
            cn.save()

            # Trigger Tax Reversal Audit if original invoice audit exists
            try:
                if ret_header.sales_invoice and tot_tax > Decimal("0.00"):
                    from financial.models import TaxDeterminationAudit
                    from financial.services.tax_service import TaxDeterminationService
                    orig_audit = TaxDeterminationAudit.objects.filter(
                        document_type="SalesInvoice",
                        document_id=ret_header.sales_invoice.id
                    ).first()
                    if orig_audit:
                        TaxDeterminationService.process_tax_reversal(
                            audit_id=orig_audit.id,
                            reversal_amount=tot_tax,
                            reason=f"إشعار دائن مرتجع مبيعات #{cn.credit_note_number}",
                            user=user
                        )
            except Exception as tax_rev_err:
                logger.warning(f"Could not log tax reversal for credit note: {tax_rev_err}")

            logger.info(f"CreditNote #{cn.credit_note_number} created for SalesReturn #{ret_header.return_number} (Amount: {cn.total_amount}).")
            return cn

    @classmethod
    def create_credit_note_for_sale(
        cls,
        sale_id: int,
        amount: Decimal,
        reason: str = "Price Adjustment / Credit Note",
        source_type: str = "PRICE_ADJUSTMENT",
        user=None
    ) -> CreditNote:
        """
        إنشاء وتصديق إشعار دائن مالي مباشر لفاتورة مبيعات معتمدة
        """
        from sale.models import Sale
        with transaction.atomic():
            sale_obj = Sale.objects.select_for_update().get(pk=sale_id)
            cn_num = f"CN-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"

            subtotal = (amount / Decimal("1.14")).quantize(Decimal("0.01"))
            tax_amount = (amount - subtotal).quantize(Decimal("0.01"))

            cn = CreditNote.objects.create(
                credit_note_number=cn_num,
                customer=sale_obj.customer,
                sale=sale_obj,
                source_type=source_type,
                status="APPROVED",
                reason=reason,
                subtotal_amount=subtotal,
                tax_amount=tax_amount,
                total_amount=amount,
                currency="EGP",
                exchange_rate=Decimal("1.000000"),
                created_by=user
            )

            logger.info(f"CreditNote #{cn.credit_note_number} created directly for Sale #{sale_obj.number} (Amount: {cn.total_amount}).")
            return cn

    @classmethod
    def post_credit_note(
        cls,
        credit_note_id: int,
        user=None
    ) -> CreditNoteAudit:
        """
        الترحيل المالي لإشعار دائن (تأثير أستاذ العملاء الفرعي + قيد الأستاذ العام عبر AccountingGateway)
        """
        with transaction.atomic():
            event_id = f"CN-POST-{credit_note_id}"

            # Check Database Event Idempotency Guard
            existing = CreditNoteAudit.objects.filter(processed_event_id=event_id).first()
            if existing:
                logger.warning(f"Credit Note Event '{event_id}' already processed in Audit #{existing.id}. Returning existing.")
                return existing

            cn = CreditNote.objects.select_for_update().get(pk=credit_note_id)
            if cn.status == "POSTED":
                raise FinancialCoreError(f"Credit Note #{cn.credit_note_number} is already posted.")

            # Accounting Period Close Guard Protection
            from financial.models import AccountingPeriod
            today = timezone.now().date()
            open_period = AccountingPeriod.objects.filter(
                start_date__lte=today,
                end_date__gte=today,
                status="open"
            ).exists()
            if not open_period:
                raise FinancialCoreError(f"Period Close Guard: Cannot post Credit Note #{cn.credit_note_number} because the current accounting period is closed or inactive.")

            correlation_id = uuid.uuid4()

            # 1. Post GL Entry via AccountingGateway (Dr. Revenue Reversal 41100, Dr. Output VAT 22010, Cr. Customer AR 11010)
            command = CreditNoteAccountingCommand(
                command_id=str(cn.posting_command_id),
                correlation_id=str(correlation_id),
                document_number=cn.credit_note_number,
                revenue_account="41100",
                vat_account="22010",
                customer_account="11010",
                amount=cn.subtotal_amount,
                tax_amount=cn.tax_amount,
                currency=cn.currency,
                exchange_rate=cn.exchange_rate,
                posting_date=timezone.now().date(),
                user=user
            )
            journal_entry = create_credit_note_posting(command)

            # 2. Post AR Subledger Balance Reduction via CustomerSubledgerService
            subledger_entry = CustomerSubledgerService.register_open_item_transaction(
                customer=cn.customer,
                transaction_type="CREDIT_NOTE",
                transaction_number=cn.credit_note_number,
                issue_date=timezone.now().date(),
                due_date=timezone.now().date(),
                currency=cn.currency,
                foreign_amount=cn.total_amount,
                exchange_rate=cn.exchange_rate,
                functional_amount=cn.total_amount,
                journal_entry=journal_entry
            )

            # 3. Create Credit Note Allocation if linked to Sale or SalesInvoice
            if cn.sale:
                CreditNoteAllocation.objects.create(
                    credit_note=cn,
                    invoice_transaction_id=cn.sale.id,
                    allocated_amount=cn.total_amount
                )
            elif cn.sales_invoice:
                CreditNoteAllocation.objects.create(
                    credit_note=cn,
                    invoice_transaction_id=cn.sales_invoice.id,
                    allocated_amount=cn.total_amount
                )
                # Invalidate pending Revenue Recognition schedules for this invoice
                try:
                    from financial.models.revenue_recognition import RevenueRecognitionSchedule, RevenueRecognitionScheduleLine
                    schedules = RevenueRecognitionSchedule.objects.filter(invoice_item__sales_invoice=cn.sales_invoice, status="ACTIVE")
                    for sched in schedules:
                        sched.lines.filter(status="SCHEDULED").update(status="REVERSED")
                        sched.deferred_amount = Decimal("0.00")
                        sched.status = "REVERSED"
                        sched.save(update_fields=["deferred_amount", "status"])
                        logger.info(f"Reversed pending Revenue Recognition Schedule #{sched.id} due to Credit Note #{cn.credit_note_number}")
                except Exception as sched_err:
                    logger.warning(f"Could not reverse revenue schedules for credit note #{cn.credit_note_number}: {sched_err}")

            old_stat = cn.status
            cn.status = "POSTED"
            cn.save()

            audit = CreditNoteAudit(
                credit_note=cn,
                event_type="CREDIT_NOTE_POSTED",
                old_status=old_stat,
                new_status="POSTED",
                journal_reference=f"CN-{cn.credit_note_number}",
                customer_transaction_reference=str(subledger_entry.id) if subledger_entry else "",
                correlation_id=correlation_id,
                processed_event_id=event_id,
                audit_hash="",
                journal_entry=journal_entry
            )
            audit.save()

            # Generate Canonical SHA256 Hash using saved timestamp
            hash_val = cls.generate_canonical_credit_note_hash(
                correlation_id=str(correlation_id),
                processed_event_id=event_id,
                credit_note_number=cn.credit_note_number,
                total_amount=cn.total_amount,
                timestamp=audit.created_at.isoformat()
            )

            logger.info(f"CreditNoteAudit #{audit.id} posted for CreditNote #{cn.credit_note_number} (Hash: {hash_val[:8]}...).")
            return audit

    @classmethod
    def reverse_credit_note(
        cls,
        credit_note_id: int,
        reason: str = "Credit Note Reversal",
        user=None
    ) -> CreditNoteAudit:
        """
        عكس إشعار دائن مرحل وفق الحوكمة المحاسبية والأثر الرجعي FIN-SAL-005
        """
        with transaction.atomic():
            cn = CreditNote.objects.select_for_update().get(pk=credit_note_id)
            if cn.status != "POSTED":
                raise FinancialCoreError(f"Cannot reverse Credit Note #{cn.credit_note_number} in status {cn.status}. Must be POSTED.")

            event_id = uuid.uuid4()
            correlation_id = uuid.uuid4()

            class CreditNoteReversalCommand:
                def __init__(self, original_credit_note, reason, user):
                    self.original_credit_note = original_credit_note
                    self.reason = reason
                    self.user = user

            reversal_command = CreditNoteReversalCommand(
                original_credit_note=cn,
                reason=reason,
                user=user
            )

            journal_entry = create_credit_note_reversal_posting(reversal_command)

            subledger_entry = CustomerSubledgerService.register_open_item_transaction(
                customer=cn.customer,
                transaction_type="DEBIT_NOTE",
                transaction_number=f"REV-{cn.credit_note_number}",
                issue_date=timezone.now().date(),
                due_date=timezone.now().date(),
                currency=cn.currency,
                foreign_amount=cn.total_amount,
                exchange_rate=cn.exchange_rate,
                functional_amount=cn.total_amount,
                journal_entry=journal_entry
            )

            old_stat = cn.status
            cn.status = "CANCELLED"
            cn.save()

            audit = CreditNoteAudit(
                credit_note=cn,
                event_type="CREDIT_NOTE_REVERSED",
                old_status=old_stat,
                new_status="CANCELLED",
                journal_reference=f"REV-CN-{cn.credit_note_number}",
                customer_transaction_reference=str(subledger_entry.id) if subledger_entry else "",
                correlation_id=correlation_id,
                processed_event_id=event_id,
                audit_hash="",
                journal_entry=journal_entry
            )
            audit.save()

            hash_val = cls.generate_canonical_credit_note_hash(
                correlation_id=str(correlation_id),
                processed_event_id=event_id,
                credit_note_number=cn.credit_note_number,
                total_amount=cn.total_amount,
                timestamp=audit.created_at.isoformat()
            )

            CreditNoteAudit.objects.filter(pk=audit.id).update(audit_hash=hash_val)
            audit.audit_hash = hash_val

            logger.info(f"CreditNote #{cn.credit_note_number} reversed successfully.")
            return audit

