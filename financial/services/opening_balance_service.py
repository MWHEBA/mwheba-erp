import uuid
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from financial.models.opening_balance import OpeningBalanceBatch, OpeningBalanceLine
from financial.models.journal_entry import JournalEntry, JournalEntryLine
from financial.exceptions import ImmutableLedgerError
from core.services.sequence_service import SequenceService


class OpeningBalancePostingService:
    """
    الخدمة المعمارية المركزية لترحيل وعكس الأرصدة الافتتاحية
    """

    @classmethod
    def post(cls, batch_id, user):
        """
        ترحيل دفعة الأرصدة الافتتاحية في معاملة ذرية مع قفل select_for_update
        """
        with transaction.atomic():
            # 1. Re-fetch and lock batch inside atomic transaction
            batch = OpeningBalanceBatch.objects.select_for_update().get(pk=batch_id)

            # 2. Re-validate status and fiscal year
            if batch.status in ['posted', 'reversed']:
                raise ImmutableLedgerError(_("الدفعة مرحلة أو معكوسة بالفعل."))
            
            if batch.fiscal_year and hasattr(batch.fiscal_year, 'is_closed') and batch.fiscal_year.is_closed:
                raise ValidationError(_("السنة المالية مغلقة ولا يمكن الترحيل عليها."))

            lines = list(batch.lines.select_related('account', 'currency', 'customer', 'supplier', 'treasury_account').all())
            if not lines:
                raise ValidationError(_("لا توجد أسطر في هذه الدفعة للترحيل."))

            # 3. Validate Functional Currency Balance
            total_debit = sum((l.debit for l in lines), Decimal('0.00'))
            total_credit = sum((l.credit for l in lines), Decimal('0.00'))

            if total_debit != total_credit:
                raise ValidationError(_("إجمالي المدين بالعملة الوظيفية ({}) لا يطابق إجمالي الدائن ({}).").format(total_debit, total_credit))

            # 4. Check Database Idempotency / Duplicate Posting
            existing_jv = JournalEntry.objects.filter(
                source_module='OPENING_BALANCE',
                source_id=batch.id
            ).first()

            if existing_jv:
                batch.journal_entry = existing_jv
                batch.status = 'posted'
                batch.posted_by = user
                batch.posted_at = timezone.now()
                batch.save()
                return batch

            # 5. Generate Opening Journal Entry via SequenceService
            jv_number = SequenceService.get_next_number('journal_entry', date=batch.opening_date)
            
            journal_entry = JournalEntry.objects.create(
                number=jv_number,
                date=batch.opening_date,
                entry_type='manual',
                status='posted',
                description=f"قيد افتتاحي للدفعة {batch.batch_number} - {batch.description}".strip(),
                reference=batch.batch_number,
                reference_type='OPENING_BALANCE',
                reference_id=batch.id,
                source_module='OPENING_BALANCE',
                source_id=batch.id,
                created_by=user,
                posted_by=user,
                posted_at=timezone.now()
            )

            # 6. Create Journal Entry Lines & Subledger Items
            line_objects = []
            for line in lines:
                curr_code = line.currency.code if line.currency else 'EGP'
                jl = JournalEntryLine(
                    journal_entry=journal_entry,
                    account=line.account,
                    debit=line.debit,
                    credit=line.credit,
                    currency=curr_code,
                    foreign_debit=line.debit_foreign if line.currency else Decimal('0.00'),
                    foreign_credit=line.credit_foreign if line.currency else Decimal('0.00'),
                    exchange_rate=line.exchange_rate,
                    description=f"رصيد افتتاحي: {line.get_line_type_display()}"
                )
                line_objects.append(jl)

                # Subledger opening items if applicable
                if line.line_type == 'AR' and line.customer:
                    cls._create_customer_opening_item(line, journal_entry, user)
                elif line.line_type == 'AP' and line.supplier:
                    cls._create_supplier_opening_item(line, journal_entry, user)

            JournalEntryLine.objects.bulk_create(line_objects)

            # 7. Update batch status to POSTED
            batch.journal_entry = journal_entry
            batch.status = 'posted'
            batch.posted_by = user
            batch.posted_at = timezone.now()
            batch.save()

            return batch

    @classmethod
    def reverse(cls, batch_id, user, reason):
        """
        عكس دفعة الأرصدة الافتتاحية المرحّلة وإنشاء أثر عكسي موثق
        """
        with transaction.atomic():
            # 1. Lock and validate batch
            batch = OpeningBalanceBatch.objects.select_for_update().get(pk=batch_id)

            if batch.status != 'posted':
                raise ValidationError(_("يمكن فقط عكس الدفعات المرحّلة (POSTED)."))
            
            if batch.status == 'reversed' or batch.reversal_journal_entry_id:
                raise ImmutableLedgerError(_("الدفعة تم عكسها بالفعل ولا يمكن عكسها مرتين."))

            if not reason:
                raise ValidationError(_("يجب تقديم سبب لإلغاء وعكس الدفعة الافتتاحية."))

            original_jv = batch.journal_entry
            if not original_jv:
                raise ValidationError(_("لم يتم العثور على القيد الافتتاحي الأصلي المرتبط بالدفعة."))

            # 2. Generate Reversal Journal Entry
            rev_jv_number = SequenceService.get_next_number('journal_entry', date=timezone.now().date())
            
            reversal_jv = JournalEntry.objects.create(
                number=rev_jv_number,
                date=timezone.now().date(),
                entry_type='reversal',
                status='posted',
                description=f"إلغاء وعكس القيد الافتتاحي للدفعة {batch.batch_number} - السبب: {reason}".strip(),
                reference=f"REV-{batch.batch_number}",
                reference_type='OPENING_BALANCE_REVERSAL',
                reference_id=batch.id,
                source_module='OPENING_BALANCE_REVERSAL',
                source_id=batch.id,
                created_by=user,
                posted_by=user,
                posted_at=timezone.now()
            )

            # 3. Create Inverted Reversal Journal Lines
            orig_lines = original_jv.lines.all()
            rev_lines = []
            for ol in orig_lines:
                rev_lines.append(JournalEntryLine(
                    journal_entry=reversal_jv,
                    account=ol.account,
                    debit=ol.credit,  # Swap Debit & Credit
                    credit=ol.debit,
                    currency=ol.currency or 'EGP',
                    foreign_debit=ol.foreign_credit,
                    foreign_credit=ol.foreign_debit,
                    exchange_rate=ol.exchange_rate,
                    description=f"عكس رصيد افتتاحي: {ol.description}"
                ))
            JournalEntryLine.objects.bulk_create(rev_lines)

            # 4. Reverse AR/AP Subledger Opening Items
            lines = batch.lines.all()
            for line in lines:
                if line.line_type == 'AR' and line.customer:
                    cls._reverse_customer_opening_item(line, reversal_jv, user)
                elif line.line_type == 'AP' and line.supplier:
                    cls._reverse_supplier_opening_item(line, reversal_jv, user)

            # 5. Update Batch Status to REVERSED
            batch.reversal_journal_entry = reversal_jv
            batch.status = 'reversed'
            batch.reversed_by = user
            batch.reversed_at = timezone.now()
            batch.reversal_reason = reason
            batch.save()

            return batch

    @classmethod
    def _create_customer_opening_item(cls, line, journal_entry, user):
        try:
            from client.models import CustomerTransaction
            amt = abs(line.debit - line.credit)
            CustomerTransaction.objects.create(
                customer=line.customer,
                transaction_type="INVOICE",
                transaction_number=f"OPN-{line.batch.batch_number}",
                issue_date=line.batch.opening_date,
                due_date=line.batch.opening_date,
                currency=line.currency.code if line.currency else 'EGP',
                exchange_rate=line.exchange_rate,
                functional_amount=amt,
                open_amount=amt,
                open_amount_functional=amt,
                reference_type="OPENING_BALANCE",
                reference_id=str(line.batch.id)
            )
        except Exception:
            pass

    @classmethod
    def _reverse_customer_opening_item(cls, line, reversal_jv, user):
        try:
            from client.models import CustomerTransaction
            amt = abs(line.debit - line.credit)
            CustomerTransaction.objects.create(
                customer=line.customer,
                transaction_type="CREDIT_NOTE",
                transaction_number=f"REV-OPN-{line.batch.batch_number}",
                issue_date=timezone.now().date(),
                due_date=timezone.now().date(),
                currency=line.currency.code if line.currency else 'EGP',
                exchange_rate=line.exchange_rate,
                functional_amount=amt,
                open_amount=amt,
                open_amount_functional=amt,
                reference_type="OPENING_BALANCE_REVERSAL",
                reference_id=str(line.batch.id)
            )
        except Exception:
            pass

    @classmethod
    def _create_supplier_opening_item(cls, line, journal_entry, user):
        try:
            from supplier.models import SupplierTransaction
            SupplierTransaction.objects.create(
                supplier=line.supplier,
                transaction_type='BILL',
                transaction_number=f"OPN-{line.batch.batch_number}",
                issue_date=line.batch.opening_date,
                due_date=line.batch.opening_date,
                original_amount=abs(line.credit - line.debit),
                open_amount=abs(line.credit - line.debit),
                currency=line.currency,
                exchange_rate=line.exchange_rate,
                reference_type="OPENING_BALANCE",
                reference_id=str(line.batch.id)
            )
        except Exception:
            pass

    @classmethod
    def _reverse_supplier_opening_item(cls, line, reversal_jv, user):
        try:
            from supplier.models import SupplierTransaction
            SupplierTransaction.objects.create(
                supplier=line.supplier,
                transaction_type='DEBIT_NOTE',
                transaction_number=f"REV-OPN-{line.batch.batch_number}",
                issue_date=timezone.now().date(),
                due_date=timezone.now().date(),
                original_amount=abs(line.credit - line.debit),
                open_amount=abs(line.credit - line.debit),
                currency=line.currency,
                exchange_rate=line.exchange_rate,
                reference_type="OPENING_BALANCE_REVERSAL",
                reference_id=str(line.batch.id)
            )
        except Exception:
            pass


# Aliases for backward compatibility
OpeningBalanceService = OpeningBalancePostingService
OpeningBalanceValidationService = OpeningBalancePostingService

