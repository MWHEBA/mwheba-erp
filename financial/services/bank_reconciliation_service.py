import logging
import csv
import io
import hashlib
import uuid
from decimal import Decimal
from typing import Dict, Any, List, Optional
from django.db import models, transaction
from django.utils import timezone

from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.journal_entry import JournalEntryLine
from financial.models.bank_reconciliation import (
    BankStatementBatch,
    BankStatementLine,
    BankReconciliationMatch
)

logger = logging.getLogger("financial.bank_reconciliation_service")


class GenericCSVParser:
    """محول كشوف الحسابات الموحد (Generic CSV Parser)"""
    @classmethod
    def parse(cls, file_content: str) -> List[Dict[str, Any]]:
        lines = []
        reader = csv.DictReader(io.StringIO(file_content))
        for row in reader:
            date_val = row.get('date') or row.get('Transaction Date') or row.get('التاريخ')
            ref_val = row.get('reference') or row.get('Reference Number') or row.get('المرجع') or ''
            desc_val = row.get('description') or row.get('Description') or row.get('البيان') or ''
            debit_val = Decimal(str(row.get('debit') or row.get('Debit') or row.get('مدين') or '0.00'))
            credit_val = Decimal(str(row.get('credit') or row.get('Credit') or row.get('دائن') or '0.00'))

            lines.append({
                'transaction_date': date_val,
                'reference_number': ref_val,
                'description': desc_val,
                'debit': debit_val,
                'credit': credit_val
            })
        return lines


class BankStatementParserFactory:
    """نمط المصنع لاستيراد كشوف الحسابات البنكية المختلفة (FIN-BANK-004)"""
    @classmethod
    def get_parser(cls, format_type: str = "CSV"):
        return GenericCSVParser


class BankReconciliationService:
    """
    محرك التسوية والمطابقة البنكية التلقائية عالي السرعة (Sprint 3 Engine)
    """

    @classmethod
    def import_statement_batch(
        cls,
        bank_account_id: Any,
        batch_number: Optional[str] = None,
        statement_date=None,
        file_content: Optional[str] = None,
        lines_data: Optional[List[Dict[str, Any]]] = None,
        format_type: str = "CSV",
        opening_balance: Decimal = Decimal('0.00'),
        closing_balance: Decimal = Decimal('0.00'),
        user=None,
        **kwargs
    ) -> BankStatementBatch:
        """
        FIN-BANK-006: استيراد ذري محصن لكشف الحساب البنكي الخارجي
        """
        bank_acc = bank_account_id if isinstance(bank_account_id, ChartOfAccounts) else ChartOfAccounts.objects.get(pk=bank_account_id)
        if lines_data is not None:
            raw_lines = lines_data
        elif file_content is not None:
            parser = BankStatementParserFactory.get_parser(format_type)
            raw_lines = parser.parse(file_content)
        else:
            raw_lines = []

        ref_date = statement_date or timezone.now().date()
        b_number = batch_number or f"STMT-{uuid.uuid4().hex[:8]}"

        # تغليف الاستيراد داخل @transaction.atomic لضمان Rollback 100% في حالة أي خطأ
        with transaction.atomic():
            batch = BankStatementBatch.objects.create(
                batch_number=b_number,
                bank_account=bank_acc,
                statement_date=ref_date,
                opening_balance=opening_balance,
                closing_balance=closing_balance,
                status='imported',
                created_by=user
            )

            for line_data in raw_lines:
                raw_hash = f"{bank_acc.id}_{line_data.get('transaction_date', ref_date)}_{line_data.get('reference_number', '')}_{line_data.get('debit', 0)}_{line_data.get('credit', 0)}_{line_data.get('description', '')[:30]}"
                l_hash = hashlib.sha256(raw_hash.encode('utf-8')).hexdigest()

                if BankStatementLine.objects.filter(line_hash=l_hash).exists():
                    logger.warning(f"Duplicate line skipped: {line_data.get('reference_number')}")
                    continue

                BankStatementLine.objects.create(
                    batch=batch,
                    transaction_date=line_data.get('transaction_date', ref_date),
                    reference_number=line_data.get('reference_number', ''),
                    description=line_data.get('description', ''),
                    debit=Decimal(str(line_data.get('debit', '0.00'))),
                    credit=Decimal(str(line_data.get('credit', '0.00'))),
                    line_hash=l_hash,
                    is_matched=False
                )

            return batch

    @classmethod
    def auto_match_batch(cls, *args, **kwargs):
        """Alias for auto_reconcile_batch for backward compatibility"""
        return cls.auto_reconcile_batch(*args, **kwargs)

    @classmethod
    def auto_reconcile_batch(cls, batch_id: int, user=None) -> Dict[str, Any]:
        """
        FIN-BANK-003: خوارزمية المطابقة التلقائية بـ Bulk SQL عالي السرعة اعتماداً على فهارس FIN-CORE-015
        """
        batch = BankStatementBatch.objects.select_related('bank_account').get(pk=batch_id)
        unmatched_lines = list(batch.lines.filter(is_matched=False))
        matched_count = 0
        exact_count = 0
        probable_count = 0

        with transaction.atomic():
            for stmt_line in unmatched_lines:
                amt = stmt_line.debit if stmt_line.debit > 0 else stmt_line.credit
                is_debit = stmt_line.debit > 0

                # Level 1: Exact Match (المبلغ + الرقم المرجعي)
                query = JournalEntryLine.objects.filter(
                    account=batch.bank_account,
                    journal_entry__status='posted'
                ).filter(models.Q(debit=amt) | models.Q(credit=amt))

                match_jl = None
                match_type = None

                if stmt_line.reference_number:
                    match_jl = query.filter(
                        journal_entry__reference__icontains=stmt_line.reference_number
                    ).first()
                    if match_jl:
                        match_type = 'EXACT'

                # Level 2: Probable Match (المبلغ المطابق)
                if not match_jl:
                    match_jl = query.first()
                    if match_jl:
                        match_type = 'PROBABLE'

                if match_jl:
                    status_val = 'MATCHED' if match_type == 'EXACT' else 'PENDING_CONFIRMATION'
                    is_matched_val = (match_type == 'EXACT')

                    BankReconciliationMatch.objects.create(
                        statement_line=stmt_line,
                        journal_line=match_jl,
                        matched_amount=amt,
                        match_type=match_type,
                        status=status_val,
                        matched_by=user
                    )
                    stmt_line.is_matched = is_matched_val
                    stmt_line.save()
                    matched_count += 1
                    if match_type == 'EXACT':
                        exact_count += 1
                    else:
                        probable_count += 1

            if matched_count > 0:
                batch.status = 'reconciling' if batch.lines.filter(is_matched=False).exists() else 'completed'
                batch.save()

            return {
                "batch_id": batch.id,
                "lines_processed": len(unmatched_lines),
                "matches_created": matched_count,
                "exact_matches": exact_count,
                "probable_matches": probable_count,
                "probable_matches_pending": probable_count,
                "batch_status": batch.status
            }

    @classmethod
    def confirm_match(cls, match_id: int, user=None) -> Dict[str, Any]:
        """
        FIN-BANK-002: اعتماد المطابقة الترجيحية الملقاة في الانتظار (Confirm Probable Match)
        """
        with transaction.atomic():
            match_rec = BankReconciliationMatch.objects.select_for_update().get(pk=match_id)
            if match_rec.status == 'MATCHED':
                return {"match_id": match_rec.id, "status": "ALREADY_MATCHED"}

            stmt_line = match_rec.statement_line
            stmt_line.is_matched = True
            stmt_line.save()

            match_rec.status = 'MATCHED'
            match_rec.matched_by = user
            match_rec.save()

            return {
                "match_id": match_rec.id,
                "statement_line_id": stmt_line.id,
                "status": "MATCHED"
            }

    @classmethod
    def unmatch_line(cls, match_id: int, user=None) -> Dict[str, Any]:
        """
        FIN-BANK-005: فك المطابقة البنكية وتنسيق تتبع المراجعة (Unmatching Audit Log)
        """
        with transaction.atomic():
            match_rec = BankReconciliationMatch.objects.select_for_update().get(pk=match_id)
            if match_rec.status == 'UNMATCHED':
                raise ValueError(f"Match {match_id} is already unmatched.")

            stmt_line = match_rec.statement_line
            stmt_line.is_matched = False
            stmt_line.save()

            match_rec.status = 'UNMATCHED'
            match_rec.unmatched_at = timezone.now()
            match_rec.unmatched_by = user
            match_rec.save()

            return {
                "match_id": match_rec.id,
                "statement_line_id": stmt_line.id,
                "status": "UNMATCHED"
            }
