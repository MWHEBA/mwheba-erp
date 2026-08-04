"""
LegacyAccountingAdapter - جسر الانتقال المحاسبي للأنظمة القديمة
يوفر واجهة موحدة معززة بالحوكمة والتتبع الرقمي (correlation_id) والوقاية من التكرار والذرية اللامركزية.
"""

import json
import logging
import uuid
from decimal import Decimal
from typing import List, Dict, Any, Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger("financial.legacy_adapter")


class LegacyAdapterDisabledError(Exception):
    """استثناء يرمى عندما تكون ميزة الجسر المحاسبي معطلة لمنع السداد غير المحاسبي"""
    pass


class LegacyAccountingAdapter:
    """
    جسر الاعتماد المحاسبي للأنظمة القديمة والخدمات المباشرة.
    يضمن عدم تخطي القيود المحاسبية صمتاً، وتحديد الذرية الكاملة (Atomic Rollback)، والوقاية من التكرار (Idempotency).
    """

    ADAPTER_VERSION = "1.0"
    FEATURE_FLAG_NAME = "LEGACY_ACCOUNTING_ADAPTER_ENABLED"

    @classmethod
    def is_enabled(cls) -> bool:
        """
        التحقق من تفعيل الجسر عبر إعدادات النظام
        """
        return getattr(settings, cls.FEATURE_FLAG_NAME, True)

    @classmethod
    def _log_audit_event(cls, action: str, correlation_id: str, details: Dict[str, Any]):
        """
        إصدار سجل تدقيق هيكلي بصيغة JSON
        """
        audit_payload = {
            "event": "LEGACY_ACCOUNTING_ADAPTER_AUDIT",
            "action": action,
            "correlation_id": correlation_id,
            "timestamp": timezone.now().isoformat(),
            "adapter_version": cls.ADAPTER_VERSION,
            "details": details
        }
        logger.info(json.dumps(audit_payload, ensure_ascii=False, default=str))

    @classmethod
    def post_journal_entry(
        cls,
        date,
        description: str,
        reference: str,
        entry_type: str,
        created_by,
        lines_data: List[Dict[str, Any]],
        status: str = "draft",
        correlation_id: Optional[str] = None,
        source_module: str = "legacy_bridge",
        **kwargs
    ):
        """
        إنشاء قيد محاسبي كامل وبنوده عبر الجسر المحاسبي مع حماية الذرية والتكرار
        """
        from financial.models.journal_entry import JournalEntry, JournalEntryLine

        if not cls.is_enabled():
            logger.error("LegacyAccountingAdapter is disabled via feature flag. Halting financial transaction for safety.")
            raise LegacyAdapterDisabledError("LEGACY_ACCOUNTING_ADAPTER_ENABLED is False. Financial posting halted.")

        corr_id = correlation_id or f"LEG-CORR-{uuid.uuid4().hex[:12].upper()}"

        with transaction.atomic():
            # الوقاية من التكرار (Duplicate Posting Protection)
            if reference:
                existing_entry = JournalEntry.objects.filter(reference=reference, entry_type=entry_type).first()
                if existing_entry:
                    cls._log_audit_event(
                        action="DUPLICATE_POSTING_PREVENTED",
                        correlation_id=corr_id,
                        details={
                            "existing_journal_id": existing_entry.id,
                            "reference": reference,
                            "entry_type": entry_type,
                            "source_module": source_module
                        }
                    )
                    return existing_entry

            post_kwargs = {
                "date": date,
                "description": description,
                "reference": reference,
                "entry_type": entry_type,
                "created_by": created_by,
                "status": status,
            }
            if status == "posted":
                post_kwargs["posted_at"] = kwargs.get("posted_at") or timezone.now()
                post_kwargs["posted_by"] = kwargs.get("posted_by") or created_by

            journal_entry = JournalEntry.objects.create(**post_kwargs)

            created_lines = []
            for item in lines_data:
                account = item.get("account")
                debit = Decimal(str(item.get("debit", 0)))
                credit = Decimal(str(item.get("credit", 0)))
                line_desc = item.get("description", description)

                line = JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=account,
                    debit=debit,
                    credit=credit,
                    description=line_desc
                )
                created_lines.append(line.id)

            cls._log_audit_event(
                action="POST_JOURNAL_ENTRY",
                correlation_id=corr_id,
                details={
                    "journal_entry_id": journal_entry.id,
                    "journal_number": getattr(journal_entry, "number", None),
                    "entry_type": entry_type,
                    "reference": reference,
                    "line_count": len(created_lines),
                    "total_debit": str(sum(Decimal(str(l.get("debit", 0))) for l in lines_data)),
                    "total_credit": str(sum(Decimal(str(l.get("credit", 0))) for l in lines_data)),
                    "source_module": source_module
                }
            )

            return journal_entry

    @classmethod
    def post_journal_lines_only(
        cls,
        journal_entry,
        lines_data: List[Dict[str, Any]],
        correlation_id: Optional[str] = None,
        source_module: str = "legacy_bridge"
    ):
        """
        إضافة بنود جديدة لقيد قائم عبر الجسر المحاسبي مع الذرية وحماية الأمان
        """
        from financial.models.journal_entry import JournalEntryLine

        if not cls.is_enabled():
            logger.error("LegacyAccountingAdapter is disabled via feature flag. Halting line addition for safety.")
            raise LegacyAdapterDisabledError("LEGACY_ACCOUNTING_ADAPTER_ENABLED is False. Line addition halted.")

        corr_id = correlation_id or f"LEG-CORR-LINE-{uuid.uuid4().hex[:12].upper()}"

        with transaction.atomic():
            created_lines = []
            for item in lines_data:
                account = item.get("account")
                debit = Decimal(str(item.get("debit", 0)))
                credit = Decimal(str(item.get("credit", 0)))
                line_desc = item.get("description", journal_entry.description)

                line = JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=account,
                    debit=debit,
                    credit=credit,
                    description=line_desc
                )
                created_lines.append(line.id)

            cls._log_audit_event(
                action="POST_JOURNAL_LINES_ONLY",
                correlation_id=corr_id,
                details={
                    "journal_entry_id": journal_entry.id,
                    "added_line_count": len(created_lines),
                    "source_module": source_module
                }
            )

            return created_lines
