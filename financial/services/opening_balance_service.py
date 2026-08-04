"""
OpeningBalanceService & OpeningBalanceValidationService (Financial Core Engine v1.8)
خدمة التحقق والترحيل الحاكم لدفعات الأرصدة الافتتاحية وتجميدها صراحة بمجرد التترحيل.
"""

import logging
from decimal import Decimal
from django.db import transaction

from financial.models.opening_balance import OpeningBalanceBatch, OpeningBalanceLine
from financial.services.ledger_core_service import LedgerCoreService
from financial.exceptions import FinancialCoreError, ImmutableLedgerError

logger = logging.getLogger("financial.opening_balance_service")


class OpeningBalanceValidationService:
    """
    خدمة التحقق من نزاهة دفعة الأرصدة الافتتاحية
    """

    @classmethod
    def validate_batch(cls, batch: OpeningBalanceBatch):
        lines = batch.lines.all()
        if not lines.exists():
            raise FinancialCoreError("Opening balance batch has no lines.")

        total_debit = Decimal("0")
        total_credit = Decimal("0")
        seen_accounts = set()

        for line in lines:
            if not line.account or not line.account.is_active:
                raise FinancialCoreError(f"Account '{line.account}' in opening balance is missing or inactive.")

            if line.account.id in seen_accounts:
                raise FinancialCoreError(f"Duplicate account '{line.account.code}' in opening balance batch.")
            seen_accounts.add(line.account.id)

            total_debit += line.debit
            total_credit += line.credit

        if total_debit != total_credit:
            raise FinancialCoreError(
                f"Unbalanced opening balance batch: total debit {total_debit} != total credit {total_credit}"
            )

        return True


class OpeningBalanceService:
    """
    خدمة اعتماد وترحيل دفعة الأرصدة الافتتاحية
    """

    @classmethod
    def post_batch(cls, batch_id: int, user) -> OpeningBalanceBatch:
        with transaction.atomic():
            batch = OpeningBalanceBatch.objects.select_for_update().get(pk=batch_id)

            if batch.status == "posted":
                raise ImmutableLedgerError("Opening balance batch is already posted.")

            # 1. التحقق من النزاهة والتوازن
            OpeningBalanceValidationService.validate_batch(batch)

            # 2. تحضير بنود القيد المحاسبي المتربط
            lines_data = []
            for line in batch.lines.all():
                lines_data.append({
                    "account": line.account,
                    "debit": line.debit,
                    "credit": line.credit,
                    "description": f"رصيد افتتاحي - {line.account.name}"
                })

            # 3. إنشاء وترحيل القيد اليومي المتربط عبر LedgerCoreService Gateway
            journal_draft = LedgerCoreService.create_draft_entry(
                date=batch.fiscal_year.start_date,
                description=f"قيد أرصدة افتتاحية - {batch.batch_number}",
                reference=batch.batch_number,
                entry_type="opening_balance",
                created_by=user,
                lines_data=lines_data
            )

            posted_journal = LedgerCoreService.post_entry(
                entry_id=journal_draft.id,
                user=user,
                posting_source="OPENING_BALANCE",
                posting_reference=batch.batch_number
            )

            # 4. تحديث الدفعة وتجميدها صراحة
            batch.journal_entry = posted_journal
            batch.status = "posted"
            batch.save(update_fields=["journal_entry", "status"])

            logger.info(f"OpeningBalanceBatch '{batch.batch_number}' posted successfully.")
            return batch
