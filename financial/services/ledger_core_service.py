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
                idempotency_key=kwargs.get("idempotency_key") or None,
                source_module=kwargs.get("source_module", ""),
                source_model=kwargs.get("source_model", ""),
                source_id=kwargs.get("source_id", None),
                is_reversal=kwargs.get("is_reversal", False),
                original_entry=kwargs.get("original_entry", None),
                reversal_reason=kwargs.get("reversal_reason", "")
            )

            total_debit = Decimal("0")
            total_credit = Decimal("0")

            for item in lines_data:
                account = item.get("account")
                if not account and item.get("account_code"):
                    account = ChartOfAccounts.objects.filter(code=item["account_code"]).first()
                    if not account:
                        from django.core.exceptions import ValidationError
                        raise ValidationError(f"الحساب المحاسبي بالكود '{item['account_code']}' غير موجود في دليل الحسابات.")
                debit = Decimal(str(item.get("debit", 0)))
                credit = Decimal(str(item.get("credit", 0)))
                line_desc = item.get("description", description)

                total_debit += debit
                total_credit += credit

                currency = item.get("currency", "EGP")
                exchange_rate = Decimal(str(item.get("exchange_rate", "1.000000")))
                foreign_debit = Decimal(str(item.get("foreign_debit", 0)))
                foreign_credit = Decimal(str(item.get("foreign_credit", 0)))
                cost_center = item.get("cost_center")
                if cost_center and not hasattr(cost_center, 'pk'):
                    from financial.models import CostCenter
                    if isinstance(cost_center, str):
                        cost_center_obj = CostCenter.objects.filter(code=cost_center).first()
                        if not cost_center_obj and cost_center.isdigit():
                            cost_center_obj = CostCenter.objects.filter(id=int(cost_center)).first()
                        cost_center = cost_center_obj
                    elif isinstance(cost_center, int):
                        cost_center = CostCenter.objects.filter(id=cost_center).first()

                tx_debit = foreign_debit if foreign_debit > Decimal('0') else debit
                tx_credit = foreign_credit if foreign_credit > Decimal('0') else credit

                line_obj = JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=account,
                    debit=debit.quantize(Decimal('0.01')),
                    credit=credit.quantize(Decimal('0.01')),
                    transaction_debit=tx_debit.quantize(Decimal('0.01')),
                    transaction_credit=tx_credit.quantize(Decimal('0.01')),
                    exchange_rate_snapshot=exchange_rate.quantize(Decimal('0.000001')),
                    cost_center=cost_center,
                    description=line_desc,
                    currency=currency,
                    exchange_rate=exchange_rate.quantize(Decimal('0.000001')),
                    foreign_debit=foreign_debit.quantize(Decimal('0.01')),
                    foreign_credit=foreign_credit.quantize(Decimal('0.01'))
                )

                cost_allocations = item.get("cost_allocations")
                if cost_allocations and isinstance(cost_allocations, list):
                    from financial.models.journal_entry import JournalEntryLineCostAllocation
                    for alloc_item in cost_allocations:
                        cc_id = alloc_item.get("cost_center_id") or (alloc_item.get("cost_center").id if hasattr(alloc_item.get("cost_center"), 'id') else alloc_item.get("cost_center"))
                        pct = Decimal(str(alloc_item.get("percentage", 0)))
                        amt = Decimal(str(alloc_item.get("amount", 0)))
                        f_amt = Decimal(str(alloc_item.get("foreign_amount", 0)))
                        if cc_id and (pct > 0 or amt > 0):
                            JournalEntryLineCostAllocation.objects.create(
                                line=line_obj,
                                cost_center_id=cc_id,
                                percentage=pct.quantize(Decimal('0.01')),
                                amount=amt.quantize(Decimal('0.01')),
                                foreign_amount=f_amt.quantize(Decimal('0.01'))
                            )

            diff = (total_debit - total_credit).quantize(Decimal("0.01"))
            abs_diff = abs(diff)

            if Decimal("0.00") < abs_diff <= Decimal("0.05"):
                rounding_acc = ChartOfAccounts.objects.filter(code__in=["50900", "40900", "50900_ROUNDING"], is_active=True).first()
                if rounding_acc:
                    if diff > Decimal("0.00"):
                        JournalEntryLine.objects.create(
                            journal_entry=journal_entry,
                            account=rounding_acc,
                            debit=Decimal("0.00"),
                            credit=abs_diff,
                            transaction_debit=Decimal("0.00"),
                            transaction_credit=abs_diff,
                            exchange_rate_snapshot=Decimal("1.000000"),
                            description="تسوية فروق تقريب كسور العملات البسيطة",
                            currency="EGP",
                            exchange_rate=Decimal("1.000000")
                        )
                        total_credit += abs_diff
                    else:
                        JournalEntryLine.objects.create(
                            journal_entry=journal_entry,
                            account=rounding_acc,
                            debit=abs_diff,
                            credit=Decimal("0.00"),
                            transaction_debit=abs_diff,
                            transaction_credit=Decimal("0.00"),
                            exchange_rate_snapshot=Decimal("1.000000"),
                            description="تسوية فروق تقريب كسور العملات البسيطة",
                            currency="EGP",
                            exchange_rate=Decimal("1.000000")
                        )
                        total_debit += abs_diff

            if (total_debit - total_credit).quantize(Decimal("0.01")) != Decimal("0.00"):
                raise FinancialCoreError(f"Unbalanced entry: Debit ({total_debit}) != Credit ({total_credit})")

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
        posting_source: str = "",
        posting_reference: str = "",
        source_type: str = "",
        source_id: str = "",
        posting_type: str = "MAIN"
    ) -> JournalEntry:
        """
        ترحيل المسودة مع قفل المعاملة وفحص التوازن المالي
        """
        with transaction.atomic():
            entry = JournalEntry.objects.select_for_update().get(pk=entry_id)

            if entry.status == "posted":
                return entry

            if not entry.is_balanced:
                raise FinancialCoreError("Cannot post unbalanced journal entry.")

            # الفحص المزدوج وتجميد لقطات مراكز التكلفة والتحقق الوقائي من الموازنة قبل الترحيل
            from financial.services.budget_control_service import BudgetControlService
            for line in entry.lines.all():
                line.full_clean()
                if line.cost_center:
                    line.cost_center_code_snapshot = line.cost_center.code
                    line.cost_center_name_snapshot = line.cost_center.name
                    line.cost_center_path_snapshot = line.cost_center.tree_path
                    line.save(update_fields=[
                        'cost_center_code_snapshot',
                        'cost_center_name_snapshot',
                        'cost_center_path_snapshot'
                    ])
                    # التحقق الوقائي من سقف الموازنة المتاحة
                    amount = line.debit if line.debit > 0 else line.credit
                    BudgetControlService.validate_budget_limit(
                        cost_center=line.cost_center,
                        account=line.account,
                        accounting_period=entry.accounting_period,
                        amount=amount,
                        user=user
                    )
                elif line.cost_allocations.exists():
                    for alloc in line.cost_allocations.all():
                        BudgetControlService.validate_budget_limit(
                            cost_center=alloc.cost_center,
                            account=line.account,
                            accounting_period=entry.accounting_period,
                            amount=alloc.amount,
                            user=user
                        )

            entry.status = "posted"
            entry.posted_at = timezone.now()
            entry.posted_by = user
            if hasattr(entry, "posting_source"):
                entry.posting_source = posting_source
            if hasattr(entry, "posting_reference"):
                entry.posting_reference = posting_reference or entry.reference

            update_fields = ["status", "posted_at", "posted_by"]
            if hasattr(entry, "posting_source") and "posting_source" in [f.name for f in entry._meta.fields]:
                update_fields.append("posting_source")
            entry.save(update_fields=update_fields)

            if source_type and source_id:
                from financial.models import FinancialPostingReference
                from financial.exceptions import DuplicatePostingError
                existing_ref = FinancialPostingReference.objects.filter(
                    source_type=source_type,
                    source_id=str(source_id),
                    posting_type=posting_type
                ).first()
                if existing_ref and existing_ref.journal_entry_id != entry_id:
                    raise DuplicatePostingError(f"[DUPLICATE_POSTING_BLOCKED] Transaction {source_type}:{source_id} already posted.")

            # تحديث كاش لقطات المنفق الفعلي لجميع مراكز التكلفة المرتبطة فور الترحيل
            from financial.services.budget_actual_service import BudgetActualService
            for line in entry.lines.all():
                if entry.accounting_period:
                    if line.cost_center:
                        BudgetActualService.update_actual_snapshot(
                            cost_center=line.cost_center,
                            account=line.account,
                            accounting_period=entry.accounting_period
                        )
                    elif line.cost_allocations.exists():
                        for alloc in line.cost_allocations.all():
                            BudgetActualService.update_actual_snapshot(
                                cost_center=alloc.cost_center,
                                account=line.account,
                                accounting_period=entry.accounting_period
                            )

            if source_type and source_id:
                from financial.models import FinancialPostingReference
                FinancialPostingReference.objects.get_or_create(
                    source_type=source_type,
                    source_id=str(source_id),
                    posting_type=posting_type,
                    defaults={'journal_entry': entry}
                )

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

            if getattr(original_entry, "reversed_by_entry_id", None) or original_entry.reversal_entries.exists():
                raise FinancialCoreError(f"Journal entry ID {original_entry.id} is already reversed.")

            # الخطوة 1: تجهيز بنود القيد العاكس (تبادل المدين والدائن مع الحفاظ على التوزيع الفرعي)
            reversal_lines = []
            for line in original_entry.lines.all():
                allocations_list = []
                if line.cost_allocations.exists():
                    for alloc in line.cost_allocations.all():
                        allocations_list.append({
                            "cost_center_id": alloc.cost_center_id,
                            "percentage": alloc.percentage,
                            "amount": alloc.amount,
                            "foreign_amount": alloc.foreign_amount
                        })

                reversal_lines.append({
                    "account": line.account,
                    "debit": line.credit,
                    "credit": line.debit,
                    "foreign_debit": line.foreign_credit,
                    "foreign_credit": line.foreign_debit,
                    "currency": line.currency,
                    "exchange_rate": line.exchange_rate,
                    "cost_center": line.cost_center,
                    "cost_allocations": allocations_list if allocations_list else None,
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
            if hasattr(original_entry, "reversed_by_entry"):
                original_entry.reversed_by_entry = reversal_posted
                original_entry.save(update_fields=['reversed_by_entry'])

            return reversal_posted
