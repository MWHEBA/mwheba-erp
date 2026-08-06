"""
GRNISubledgerService - خدمة أستاذ البضائع المستلمة غير المفوترة ومطابقتها مع الأستاذ العام (FIN-PUR-003 & FIN-PUR-007)
يدير حساب 20150 GRNI وتعتيق المبالغ المعلقة وحوكمة التسويات Clearing Write-Off
"""

import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional
from django.utils import timezone
from django.db import transaction
from django.db.models import Sum, F, ExpressionWrapper, DecimalField

from purchase.models.procurement_models import GoodsReceivedNoteItem
from financial.services.ledger_query_service import LedgerQueryService
from financial.services.ledger_core_service import LedgerCoreService
from financial.exceptions import FinancialCoreError

logger = logging.getLogger("purchase.grni_subledger_service")


class GRNISubledgerService:
    """
    خدمة أستاذ البضائع المستلمة غير المفوترة (GRNI Subledger Service)
    """

    @classmethod
    def get_open_grni_summary(cls, as_of_date: Optional[Any] = None) -> Dict[str, Any]:
        """
        تقرير البضائع المستلمة غير المفوترة وتقسيم فترات التعتيق (GRNI Aging Breakdown)
        """
        now = timezone.now()
        items = GoodsReceivedNoteItem.objects.filter(billed_qty__lt=F("received_qty"))

        if as_of_date:
            items = items.filter(grn__received_date__lte=as_of_date)

        total_open_value = Decimal("0.00")
        aging_under_30 = Decimal("0.00")
        aging_30_60 = Decimal("0.00")
        aging_over_60 = Decimal("0.00")

        open_items_count = 0

        for item in items:
            unbilled_qty = item.received_qty - item.billed_qty
            rate = getattr(item.grn, "exchange_rate", None) or Decimal("1.000000")
            unbilled_val = (unbilled_qty * item.unit_price * rate).quantize(Decimal("0.01"))

            total_open_value += unbilled_val
            open_items_count += 1

            age_days = (now - item.grn.received_date).days
            if age_days < 30:
                aging_under_30 += unbilled_val
            elif age_days <= 60:
                aging_30_60 += unbilled_val
            else:
                aging_over_60 += unbilled_val

        return {
            "open_items_count": open_items_count,
            "total_open_grni_value": total_open_value,
            "aging_under_30_days": aging_under_30,
            "aging_30_to_60_days": aging_30_60,
            "aging_over_60_days": aging_over_60
        }

    @classmethod
    def reconcile_grni_control_account(
        cls,
        account_code: str = "20150_GRNI",
        as_of_date: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        مطابقة مجموع أستاذ GRNI الفرعي مع رصيد حساب الأستاذ العام 20150
        """
        grni_summary = cls.get_open_grni_summary(as_of_date=as_of_date)
        subledger_grni_value = grni_summary["total_open_grni_value"]

        gl_balance = Decimal("0.00")
        try:
            gl_fact = LedgerQueryService.get_account_balance(account_or_id=account_code, as_of_date=as_of_date)
            gl_balance = abs(Decimal(str(gl_fact.get("balance", "0.00")))).quantize(Decimal("0.01"))
        except Exception as e:
            logger.warning(f"Could not fetch GL balance for GRNI account {account_code}: {str(e)}")

        discrepancy = (gl_balance - subledger_grni_value).quantize(Decimal("0.01"))
        is_reconciled = abs(discrepancy) == Decimal("0.00")

        return {
            "account_code": account_code,
            "subledger_grni_value": subledger_grni_value,
            "gl_grni_balance": gl_balance,
            "discrepancy": discrepancy,
            "is_reconciled": is_reconciled,
            "aging_summary": grni_summary
        }

    @classmethod
    def create_grni_clearing_entry(
        cls,
        grn_item_id: int,
        reason: str,
        user
    ) -> Dict[str, Any]:
        """
        تسوية وإغلاق المبالغ المعلقة في حساب 20150 GRNI للحالات الاستثنائية بطلب حوكمة معتمد
        """
        with transaction.atomic():
            item = GoodsReceivedNoteItem.objects.select_for_update().get(pk=grn_item_id)
            unbilled_qty = item.received_qty - item.billed_qty

            if unbilled_qty <= Decimal("0.0000"):
                raise FinancialCoreError("GRN Item is already fully billed or cleared.")

            rate = getattr(item.grn, "exchange_rate", None) or Decimal("1.000000")
            clearing_val = (unbilled_qty * item.unit_price * rate).quantize(Decimal("0.01"))

            # إغلاق السطر كأنه تم فوترته للتسوية
            item.billed_qty = item.received_qty
            item.save(update_fields=["billed_qty"])

            # قيد التسوية المحاسبية: Dr. 20150 GRNI / Cr. 50120 PPV Variance
            lines_data = [
                {"account_code": "20150_GRNI", "debit": clearing_val, "credit": Decimal("0.00"), "description": f"GRNI Clearing: {reason}"},
                {"account_code": "50120_PPV", "debit": Decimal("0.00"), "credit": clearing_val, "description": f"GRNI Clearing Variance Credit"}
            ]

            draft_entry = LedgerCoreService.create_draft_entry(
                date=timezone.now().date(),
                description=f"GRNI Clearing: {reason}",
                reference=f"GRNI-CLEAR-{item.id}",
                entry_type="GENERAL",
                created_by=user,
                lines_data=lines_data
            )
            journal_entry = LedgerCoreService.post_entry(draft_entry.id, user=user)

            logger.info(f"GRNI Clearing entry created for GRNItem #{item.id}: Amount={clearing_val} EGP.")

            return {
                "grn_item_id": item.id,
                "cleared_qty": unbilled_qty,
                "cleared_value": clearing_val,
                "journal_entry_id": journal_entry.id
            }

    @classmethod
    def write_off_stale_grni(cls, grn_item_id: int, reason: str, user) -> Dict[str, Any]:
        """
        FIN-PUR-010: GRNI Write-Off Alias for create_grni_clearing_entry
        """
        return cls.create_grni_clearing_entry(grn_item_id=grn_item_id, reason=reason, user=user)
