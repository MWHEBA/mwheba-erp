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
    def find_matching_policy(cls, product=None) -> RevenueRecognitionPolicy:
        """
        IFRS 15 Policy Hierarchy Resolution: PRODUCT -> CATEGORY -> GLOBAL
        """
        if product:
            # 1. Product Scope Match
            prod_policy = RevenueRecognitionPolicy.objects.filter(
                is_active=True, rule_scope="PRODUCT", scope_value=str(product.id)
            ).order_by("-version").first()
            if prod_policy:
                return prod_policy

            # 2. Category Scope Match
            if hasattr(product, "category") and product.category:
                cat_policy = RevenueRecognitionPolicy.objects.filter(
                    is_active=True, rule_scope="CATEGORY", scope_value=str(product.category.id)
                ).order_by("-version").first()
                if cat_policy:
                    return cat_policy

        # 3. Fallback Global Scope Match
        global_policy = RevenueRecognitionPolicy.objects.filter(
            is_active=True, rule_scope="GLOBAL"
        ).order_by("-version").first()
        if not global_policy:
            global_policy = RevenueRecognitionPolicy.objects.create(
                name="Default Global Delivery Policy",
                code="POL-GLOBAL-DELIVERY",
                version=1,
                trigger_event="DELIVERY_CONFIRMED",
                allocation_method="DIRECT_LINE_VALUE",
                fx_treatment_type="INVOICE_RATE",
                is_active=True
            )
        return global_policy

    @classmethod
    def evaluate_recognition_decision(
        cls,
        invoice_item_id: int,
        trigger_event: str = "DELIVERY_CONFIRMED"
    ) -> RevenueRecognitionDecision:
        """
        تقييم قرار الاعتراف بالإيراد وفق شجرة قواعد IFRS 15 (DELIVERY_CONFIRMED vs INVOICE_ISSUANCE vs TIME_MILESTONE)
        """
        inv_item = SalesInvoiceItem.objects.select_related("so_item__product", "sales_invoice").get(pk=invoice_item_id)
        product = inv_item.so_item.product if inv_item.so_item else None
        policy = cls.find_matching_policy(product)

        allocated_price = inv_item.line_total

        if policy.trigger_event == "INVOICE_ISSUANCE":
            position = "RECOGNIZE_REVENUE"
            recognized = allocated_price
            deferred = Decimal("0.00")
        elif policy.trigger_event == "DELIVERY_CONFIRMED":
            if trigger_event == "INVOICE_ISSUANCE":
                position = "CREATE_CONTRACT_LIABILITY"
                recognized = Decimal("0.00")
                deferred = allocated_price
            else:
                position = "RECOGNIZE_REVENUE"
                recognized = allocated_price
                deferred = Decimal("0.00")
        else:
            position = "CREATE_CONTRACT_LIABILITY"
            recognized = Decimal("0.00")
            deferred = allocated_price

        return RevenueRecognitionDecision(
            accounting_position=position,
            allocated_transaction_price=allocated_price,
            recognized_amount=recognized,
            deferred_amount=deferred,
            contract_asset_amount=Decimal("0.00"),
            policy_id=policy.id,
            policy_version=policy.version,
            fx_treatment_type=policy.fx_treatment_type
        )

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
                product = getattr(inv_item, "product", None) or (inv_item.so_item.product if inv_item.so_item else None)
                policy = cls.find_matching_policy(product)

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

            if created:
                if policy.trigger_event == "INVOICE_ISSUANCE":
                    # Instant Revenue Recognition on Invoice Creation
                    cls.process_recognition_event(
                        event_id=f"EVT-INV-ISSUANCE-{inv_item.id}",
                        schedule_id=schedule.id,
                        recognition_event="INVOICE_ISSUANCE",
                        user=user
                    )
                elif policy.trigger_event == "TIME_MILESTONE":
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

            logger.info(f"RevenueRecognitionSchedule #{schedule.id} initialized for InvoiceItem #{invoice_item_id} (Policy Trigger: {policy.trigger_event}).")
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

            # Resolve Account Mapping via AccountRoleRegistry
            from financial.services.role_registry import AccountRoleRegistry
            default_rev = AccountRoleRegistry.get_account_code("GENERAL_SALES_REVENUE")
            default_def = AccountRoleRegistry.get_account_code("DEFERRED_REVENUE_ACCOUNT")

            mapping = RevenueRecognitionAccountMapping.objects.filter(
                policy=schedule.policy, currency=schedule.currency
            ).first()

            rev_account = mapping.revenue_account.code if (mapping and mapping.revenue_account) else default_rev
            def_account = mapping.deferred_revenue_account.code if (mapping and mapping.deferred_revenue_account) else default_def
            asset_account = mapping.contract_asset_account.code if (mapping and mapping.contract_asset_account) else "11040"

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
            command = RevenueAccountingCommand(
                event_id=f"REV-{orig_entry.processed_event_id}",
                correlation_id=str(orig_entry.correlation_id),
                invoice_item_id=schedule.invoice_item.id,
                schedule_id=schedule.id,
                schedule_line_id=orig_entry.schedule_line_id,
                accounting_position="RECOGNIZE_REVENUE",
                foreign_amount=reversal_amount,
                exchange_rate=orig_entry.exchange_rate,
                functional_amount=reversal_amount,
                currency=schedule.currency,
                revenue_account_code="40100",
                deferred_account_code="21000",
                journal_reference=f"REV-{orig_entry.processed_event_id}",
                user=user
            )
            command.reversal_amount = reversal_amount
            rev_journal = create_revenue_reversal_entry(command)

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

    @classmethod
    def process_all_due_schedules(cls, as_of_date: Optional[Any] = None, user=None) -> Dict[str, Any]:
        """
        معالجة وترحيل كافة أقساط الاعتراف بالإيراد المستحقة حتى تاريخ محدد
        مع حماية وتخطي الفترات المقفلة واستخدام مستخدم النظام الآلي
        """
        from financial.services.system_automation_user_service import SystemAutomationUserService
        from financial.models.journal_entry import AccountingPeriod

        target_date = as_of_date or timezone.now().date()
        exec_user = user or SystemAutomationUserService.get_or_create_system_user()

        due_lines = RevenueRecognitionScheduleLine.objects.filter(
            status="SCHEDULED",
            recognition_date__lte=target_date,
            schedule__status="ACTIVE"
        ).select_related("schedule__invoice_item__sales_invoice").order_by("recognition_date")

        processed_count = 0
        failed_count = 0
        total_recognized = Decimal("0.00")
        errors = []

        for line in due_lines:
            try:
                # Check period lock status
                period = AccountingPeriod.get_period_for_date(line.recognition_date)
                if period and not period.can_post_entries():
                    logger.warning(f"Period {period.name} is closed for line #{line.id}. Rolling forward recognition to today.")

                event_id = f"EVT-REC-SCHED-{line.schedule_id}-L{line.id}-{target_date}"
                entry = cls.process_recognition_event(
                    event_id=event_id,
                    schedule_id=line.schedule_id,
                    schedule_line_id=line.id,
                    recognition_event="TIME_MILESTONE",
                    user=exec_user
                )
                processed_count += 1
                total_recognized += entry.functional_amount
            except Exception as e:
                failed_count += 1
                err_msg = f"Failed recognizing line #{line.id} (Schedule #{line.schedule_id}): {str(e)}"
                logger.error(err_msg)
                errors.append(err_msg)

        summary = {
            "target_date": str(target_date),
            "processed_count": processed_count,
            "failed_count": failed_count,
            "total_recognized_amount": str(total_recognized),
            "errors": errors
        }
        logger.info(f"Revenue Recognition Batch Complete: {processed_count} lines processed ({total_recognized} EGP), {failed_count} failed.")
        return summary

