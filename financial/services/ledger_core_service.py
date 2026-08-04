"""
LedgerCoreService - الخدمة المركزية الحاكمة لقيود اليومية (Financial Core Engine v1.8)
المسؤولة عن إنشاء القيود المسودة، ترحيل القيود، والعكس المحاسبي المحكوم صراحة بالمعاملات الذرية والقائمة البيضاء.
"""

import logging
from decimal import Decimal
from typing import List, Dict, Any, Optional

from django.db import transaction
from django.utils import timezone

from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.journal_entry import JournalEntry, JournalEntryLine
from financial.exceptions import FinancialCoreError, ImmutableLedgerError

logger = logging.getLogger("financial.ledger_core_service")


class LedgerCoreService:
    """
    محرك القيود اليومية المركزي.
    """

    @classmethod
    def create_draft_entry(
        cls,
        date,
        description: str,
        reference: str,
        entry_type: str,
        created_by,
        lines_data: List[Dict[str, Any]],
        **kwargs
    ) -> JournalEntry:
        """
        إنشاء قيد مسودة جديد متوازن
        """
        with transaction.atomic():
            journal_entry = JournalEntry.objects.create(
                date=date,
                description=description,
                reference=reference,
                entry_type=entry_type,
                created_by=created_by,
                status="draft",
                is_reversal=kwargs.get("is_reversal", False),
                original_entry=kwargs.get("original_entry", None),
                reversal_reason=kwargs.get("reversal_reason", "")
            )

            total_debit = Decimal("0")
            total_credit = Decimal("0")

            for item in lines_data:
                account = item.get("account")
                if not account and item.get("account_code"):
                    account = ChartOfAccounts.objects.get(code=item["account_code"])
                debit = Decimal(str(item.get("debit", 0)))
                credit = Decimal(str(item.get("credit", 0)))
                line_desc = item.get("description", description)

                total_debit += debit
                total_credit += credit

                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=account,
                    debit=debit,
                    credit=credit,
                    description=line_desc
                )

            if total_debit != total_credit:
                raise FinancialCoreError(f"Unbalanced entry: total debit {total_debit} != total credit {total_credit}")

            return journal_entry

    @classmethod
    def register_posting_reference(
        cls,
        source_type: str,
        source_id: str,
        journal_entry: JournalEntry,
        posting_type: str = "MAIN"
    ):
        """
        تسجيل مرجع الترحيل المالي ومنع التكرار صراحة عبر قيد الفردية بدعم التزامن الذري
        """
        from financial.models.posting_reference import FinancialPostingReference
        from django.db import IntegrityError

        try:
            with transaction.atomic():
                return FinancialPostingReference.objects.create(
                    source_type=source_type,
                    source_id=str(source_id),
                    posting_type=posting_type,
                    journal_entry=journal_entry
                )
        except IntegrityError:
            raise FinancialCoreError(
                f"DUPLICATE_POSTING_BLOCKED: Posting reference ({source_type}, {source_id}, {posting_type}) already exists."
            )

    @classmethod
    def post_entry(
        cls,
        entry_id: int,
        user,
        posting_source: str = "MANUAL_JOURNAL",
        posting_reference: Optional[str] = None,
        source_type: Optional[str] = None,
        source_id: Optional[str] = None,
        posting_type: str = "MAIN"
    ) -> JournalEntry:
        """
        ترحيل قيد مسودة وإقفال تعديله بصفة حازمة وتسجيل مرجع الترحيل
        """
        with transaction.atomic():
            entry = JournalEntry.objects.select_for_update().get(pk=entry_id)

            if entry.status == "posted":
                return entry

            if not entry.is_balanced:
                raise FinancialCoreError("Cannot post unbalanced journal entry.")

            # إذا تم تمرير بيانات المصدر للتأكد من عدم التكرار
            if source_type and source_id:
                cls.register_posting_reference(
                    source_type=source_type,
                    source_id=source_id,
                    journal_entry=entry,
                    posting_type=posting_type
                )

            entry.status = "posted"
            entry.posted_at = timezone.now()
            entry.posted_by = user
            entry.posting_source = posting_source
            entry.posting_reference = posting_reference or entry.reference

            entry.save(update_fields=["status", "posted_at", "posted_by", "posting_source", "posting_reference"])

            return entry

    @classmethod
    def reverse_entry(
        cls,
        entry_id: int,
        user,
        reversal_reason: str = ""
    ) -> JournalEntry:
        """
        العكس المحاسبي الحاكم ذو الـ 3 خطوات الذرية والقائمة البيضاء
        """
        with transaction.atomic():
            original_entry = JournalEntry.objects.select_for_update().get(pk=entry_id)

            if original_entry.status != "posted":
                raise FinancialCoreError("Can only reverse posted journal entries.")

            if original_entry.reversed_by_entry_id:
                raise FinancialCoreError(f"Journal entry ID {original_entry.id} is already reversed.")

            # الخطوة 1: تجهيز بنود القيد العاكس (تبادل المدين والدائن)
            reversal_lines = []
            for line in original_entry.lines.all():
                reversal_lines.append({
                    "account": line.account,
                    "debit": line.credit,
                    "credit": line.debit,
                    "description": f"عكس: {line.description or original_entry.description}"
                })

            # الخطوة 2: إنشاء وترحيل القيد العاكس
            reversal_draft = cls.create_draft_entry(
                date=timezone.now().date(),
                description=f"قيد عكسي للقيد رقم {original_entry.number}",
                reference=f"REV-{original_entry.number}",
                entry_type=original_entry.entry_type,
                created_by=user,
                lines_data=reversal_lines,
                is_reversal=True,
                original_entry=original_entry,
                reversal_reason=reversal_reason
            )

            reversal_posted = cls.post_entry(
                entry_id=reversal_draft.id,
                user=user,
                posting_source="REVERSAL",
                posting_reference=original_entry.number
            )

            # الخطوة 3: تحديث القيد الأصلي بمرجع القيد العاكس عبر القائمة البيضاء
            original_entry.reversed_by_entry = reversal_posted
            original_entry.save(update_fields=["reversed_by_entry"])

            return reversal_posted
