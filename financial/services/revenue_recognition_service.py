import uuid
import json
import hashlib
import logging
from decimal import Decimal
from typing import Dict, Any, Optional
from django.db import transaction, models
from django.utils import timezone

from financial.models import (
    RevenueRecognitionPolicy,
    RevenueRecognitionAccountMapping,
    RevenueRecognitionSchedule,
    RevenueRecognitionScheduleLine,
    RevenueRecognitionEntry,
    RevenueRecognitionReversal,
)
from financial.services.revenue_recognition_decision import (
    RevenueRecognitionDecision,
    RevenueAccountingCommand,
)
from sale.models.sales_models import SalesInvoiceItem
from governance.services.accounting_gateway import create_revenue_recognition_entry, create_revenue_reversal_entry
from financial.exceptions import FinancialCoreError

logger = logging.getLogger("financial.services.revenue_recognition_service")


class RevenueRecognitionService:
    """
    FIN-AR-002: IFRS 15 Revenue Recognition Policy Engine Service (Locked Master Final)
    محرك حوكمة الاعتراف بالإيراد وفق معيار IFRS 15 بمطابقة أسقف المبالغ وقفل التزامن ونظام الإثبات المشفر
    """

    @classmethod
    def generate_canonical_audit_hash(
        cls,
        correlation_id: str,
        event_id: str,
        document_number: str,
        recognized_amount: Decimal,
        currency: str,
        exchange_rate: Decimal,
        journal_reference: str,
        timestamp: str
    ) -> str:
        """
        إنشاء التوقيع المشفر Canonical JSON SHA256 لحماية القيد المحاسبي وسجل الإثبات من التغيير
        """
        payload = {
            "correlation_id": str(correlation_id),
            "currency": str(currency),
            "document_number": str(document_number),
            "event_id": str(event_id),
            "exchange_rate": str(exchange_rate),
            "journal_reference": str(journal_reference),
            "recognized_amount": str(recognized_amount),
            "timestamp": str(timestamp)
        }
        canonical_json = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    @classmethod
    def create_schedule_for_invoice_item(
        cls,
        invoice_item_id: int,
        policy_id: Optional[int] = None,
        user=None
    ) -> RevenueRecognitionSchedule:
        """
        إنشاء جدول الاعتراف بالإيراد لبند الفاتورة بناءً على السياسة المحوكمة المحددة
        """
        with transaction.atomic():
            inv_item = SalesInvoiceItem.objects.select_related("sales_invoice", "so_item__product").get(pk=invoice_item_id)

            if policy_id:
                policy = RevenueRecognitionPolicy.objects.get(pk=policy_id, is_active=True)
            else:
                # Default Policy lookup
                policy = RevenueRecognitionPolicy.objects.filter(is_active=True, rule_scope="GLOBAL").order_by("-version").first()
                if not policy:
                    policy = RevenueRecognitionPolicy.objects.create(
                        name="Default Global Delivery Policy",
                        code="POL-GLOBAL-DELIVERY",
                        version=1,
                        trigger_event="DELIVERY_CONFIRMED",
                        allocation_method="DIRECT_LINE_VALUE",
                        fx_treatment_type="INVOICE_RATE",
                        is_active=True
                    )

            allocated_price = inv_item.line_total
            so = inv_item.sales_invoice.sales_order

            schedule, created = RevenueRecognitionSchedule.objects.get_or_create(
                invoice_item=inv_item,
                policy=policy,
                policy_version=policy.version,
                defaults={
                    "contract_reference": f"CONTRACT-SO-{so.order_number}" if so else f"CONTRACT-INV-{inv_item.sales_invoice.invoice_number}",
                    "currency": so.currency if so else "EGP",
                    "allocated_transaction_price": allocated_price,
                    "recognized_amount": Decimal("0.00"),
                    "deferred_amount": allocated_price,
                    "contract_asset_amount": Decimal("0.00"),
                    "status": "ACTIVE"
                }
            )

            if created and policy.trigger_event == "TIME_MILESTONE":
                # Create default 3 monthly schedule lines
                monthly_amt = (allocated_price / Decimal("3")).quantize(Decimal("0.01"))
                for seq in range(1, 4):
                    r_date = timezone.now().date() + timezone.timedelta(days=30 * seq)
                    RevenueRecognitionScheduleLine.objects.create(
                        schedule=schedule,
                        sequence=seq,
                        recognition_date=r_date,
                        foreign_amount=monthly_amt,
                        exchange_rate=Decimal("1.000000"),
                        functional_amount=monthly_amt,
                        status="SCHEDULED"
                    )

            logger.info(f"RevenueRecognitionSchedule #{schedule.id} initialized for InvoiceItem #{invoice_item_id}.")
            return schedule

    @classmethod
    def process_recognition_event(
        cls,
        event_id: str,
        schedule_id: int,
        schedule_line_id: Optional[int] = None,
        recognition_event: str = "DELIVERY_CONFIRMED",
        user=None
    ) -> RevenueRecognitionEntry:
        """
        معالجة حدث الاعتراف بالإيراد المحوكم بـ select_for_update ودليل إثبات Canonical SHA256
        """
        with transaction.atomic():
            # Check Database-Level Event Idempotency Guard
            existing_entry = RevenueRecognitionEntry.objects.filter(processed_event_id=event_id).first()
            if existing_entry:
                logger.warning(f"Event ID '{event_id}' already processed in entry #{existing_entry.id}. Returning existing entry.")
                return existing_entry

            # Scoped Row Locking on Schedule
            schedule = RevenueRecognitionSchedule.objects.select_for_update().select_related(
                "invoice_item__sales_invoice", "policy"
            ).get(pk=schedule_id)

            line = None
            if schedule_line_id:
                line = RevenueRecognitionScheduleLine.objects.select_for_update().get(pk=schedule_line_id)
                recognize_amt = line.foreign_amount
            else:
                recognize_amt = schedule.deferred_amount

            if recognize_amt <= Decimal("0.00") or schedule.recognized_amount + recognize_amt > schedule.allocated_transaction_price:
                raise FinancialCoreError(
                    f"Amount Integrity Guard: Recognized ({schedule.recognized_amount}) + Requested ({recognize_amt}) "
                    f"exceeds allocated price ({schedule.allocated_transaction_price})."
                )

            # Resolve Account Mapping
            mapping = RevenueRecognitionAccountMapping.objects.filter(
                policy=schedule.policy, currency=schedule.currency
            ).first()

            rev_account = mapping.revenue_account.code if mapping else "40100"
            def_account = mapping.deferred_revenue_account.code if mapping else "21000"
            asset_account = mapping.contract_asset_account.code if mapping and mapping.contract_asset_account else "11040"

            so = schedule.invoice_item.sales_invoice.sales_order
            ex_rate = so.exchange_rate if so else Decimal("1.000000")
            func_amt = (recognize_amt * ex_rate).quantize(Decimal("0.01"))
            correlation_id = uuid.uuid4()
            now_iso = timezone.now().isoformat()
            doc_num = schedule.invoice_item.sales_invoice.invoice_number

            j_ref = f"REV-REC-{schedule.id}-{event_id}"

            # Post GL Entry via AccountingGateway
            command = RevenueAccountingCommand(
                event_id=event_id,
                correlation_id=str(correlation_id),
                invoice_item_id=schedule.invoice_item.id,
                schedule_id=schedule.id,
                schedule_line_id=schedule_line_id,
                accounting_position="RECOGNIZE_REVENUE",
                foreign_amount=recognize_amt,
                exchange_rate=ex_rate,
                functional_amount=func_amt,
                currency=schedule.currency,
                revenue_account_code=rev_account,
                deferred_account_code=def_account,
                asset_account_code=asset_account,
                journal_reference=j_ref,
                user=user
            )
            journal_entry = create_revenue_recognition_entry(command)

            # Create Immutable RevenueRecognitionEntry
            entry = RevenueRecognitionEntry(
                schedule=schedule,
                schedule_line=line,
                processed_event_id=event_id,
                recognition_event=recognition_event,
                entry_status="POSTED",
                foreign_amount=recognize_amt,
                exchange_rate=ex_rate,
                functional_amount=func_amt,
                audit_hash="",
                correlation_id=correlation_id,
                journal_entry=journal_entry,
                created_by=user
            )
            entry.save()

            # Generate Deterministic Canonical SHA256 Hash Signature using saved timestamp
            audit_hash = cls.generate_canonical_audit_hash(
                correlation_id=str(correlation_id),
                event_id=event_id,
                document_number=doc_num,
                recognized_amount=recognize_amt,
                currency=schedule.currency,
                exchange_rate=ex_rate,
                journal_reference=j_ref,
                timestamp=entry.created_at.isoformat()
            )

            RevenueRecognitionEntry.objects.filter(pk=entry.id).update(audit_hash=audit_hash)
            entry.audit_hash = audit_hash

            # Update Schedule & Line status
            schedule.recognized_amount += recognize_amt
            schedule.deferred_amount -= recognize_amt
            if schedule.recognized_amount >= schedule.allocated_transaction_price:
                schedule.status = "FULLY_RECOGNIZED"
            schedule.save()

            if line:
                line.status = "RECOGNIZED"
                line.save()

            logger.info(f"Revenue Recognition Entry #{entry.id} posted successfully for Event '{event_id}' (Hash: {audit_hash[:8]}...).")
            return entry

    @classmethod
    def process_revenue_reversal(
        cls,
        original_entry_id: int,
        reversal_amount: Decimal,
        reason: str,
        user=None
    ) -> RevenueRecognitionReversal:
        """
        عكس قيد الاعتراف بالإيراد مع التحقق الصارم من سقف العكس Reversal Cap Validation Guard
        """
        with transaction.atomic():
            orig_entry = RevenueRecognitionEntry.objects.select_for_update().get(pk=original_entry_id)
            schedule = RevenueRecognitionSchedule.objects.select_for_update().get(pk=orig_entry.schedule_id)

            # Reversal Cap Validation Guard (reversal_amount <= recognized_amount)
            if reversal_amount > schedule.recognized_amount:
                raise FinancialCoreError(
                    f"Reversal Cap Guard: Reversal amount ({reversal_amount}) exceeds cumulative recognized balance ({schedule.recognized_amount})."
                )

            # Create GL Reversal Entry via AccountingGateway
            rev_journal = create_revenue_reversal_entry(orig_entry.journal_entry, user=user, reason=reason)

            reversal = RevenueRecognitionReversal.objects.create(
                original_entry=orig_entry,
                reversal_type="FULL_REVERSAL" if reversal_amount == orig_entry.functional_amount else "PARTIAL_REVERSAL",
                reversal_amount=reversal_amount,
                reversal_date=timezone.now().date(),
                journal_entry=rev_journal,
                reason=reason,
                created_by=user
            )

            # Update Schedule balances
            schedule.recognized_amount -= reversal_amount
            schedule.deferred_amount += reversal_amount
            schedule.status = "ACTIVE"
            schedule.save()

            orig_entry.entry_status = "REVERSED"

            logger.info(f"Revenue Recognition Reversal #{reversal.id} created for Entry #{original_entry_id}.")
            return reversal

    @classmethod
    def verify_audit_integrity(cls, entry_id: int) -> bool:
        """
        التحقق الصارم من سلامة وعدم تلاعب التوقيع المشفر Canonical SHA256 القيد المحاسبي
        """
        entry = RevenueRecognitionEntry.objects.select_related("schedule__invoice_item__sales_invoice").get(pk=entry_id)
        doc_num = entry.schedule.invoice_item.sales_invoice.invoice_number
        j_ref = f"REV-REC-{entry.schedule.id}-{entry.processed_event_id}"

        expected_hash = cls.generate_canonical_audit_hash(
            correlation_id=str(entry.correlation_id),
            event_id=entry.processed_event_id,
            document_number=doc_num,
            recognized_amount=entry.foreign_amount,
            currency=entry.schedule.currency,
            exchange_rate=entry.exchange_rate,
            journal_reference=j_ref,
            timestamp=entry.created_at.isoformat()
        )
        return entry.audit_hash == expected_hash
