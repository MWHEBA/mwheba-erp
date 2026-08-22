import logging
import uuid
from decimal import Decimal
from django.db import models, transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from financial.models.opening_balance import OpeningBalanceBatch, OpeningBalanceLine
from financial.models.journal_entry import JournalEntry, JournalEntryLine
from financial.exceptions import ImmutableLedgerError
from core.services.sequence_service import SequenceService
from core.enums.document_types import DocumentType

logger = logging.getLogger("financial.opening_balance_service")


class RoundingTolerancePolicy:
    """سياسة تحمل فروق تقريب العملات المحاسبية المحسوبة (ديناميكية من جدول العملات Currency master)"""
    DEFAULT_FALLBACK_MAP = {
        'EGP': Decimal('0.05'),
        'USD': Decimal('0.01'),
        'EUR': Decimal('0.01'),
        'GBP': Decimal('0.01'),
        'KWD': Decimal('0.001'),
        'SAR': Decimal('0.05'),
        'AED': Decimal('0.05'),
    }

    @classmethod
    def get_tolerance(cls, currency_code: str = 'EGP') -> Decimal:
        """
        استعلام ديناميكي عن حد تحمل فروق التقريب من موديل العملة في قاعدة البيانات.
        وفي حال عدم توفر السجل بالداتا بيز يرجع للقيم المعيارية الافتراضية للعملة.
        """
        code = str(currency_code).upper()
        try:
            from financial.models.currency import Currency
            curr = Currency.objects.filter(code=code).first()
            if curr and getattr(curr, 'rounding_tolerance', None) is not None:
                return curr.rounding_tolerance
        except Exception:
            pass

        return cls.DEFAULT_FALLBACK_MAP.get(code, Decimal('0.05'))


class OpeningBalancePostingService:
    """
    الخدمة المعمارية المركزية لترحيل وعكس الأرصدة الافتتاحية (Enterprise ERP Governance v2.3)
    """

    @classmethod
    def post(cls, batch_id, user):
        """
        ترحيل دفعة الأرصدة الافتتاحية في معاملة ذرية للـ GL والـ AR/AP مع تفويض محرك المخزون
        """
        with transaction.atomic():
            # 1. Lock batch inside atomic transaction
            batch = OpeningBalanceBatch.objects.select_for_update().get(pk=batch_id)

            # Re-check status & immutability guard
            if batch.status == 'posted':
                raise ImmutableLedgerError(_("الدفعة مرحلة بالفعل ومحصنة ضد إعادة الترحيل."))

            if batch.status == 'reversed':
                raise ImmutableLedgerError(_("الدفعة معكوسة بالفعل ولا يمكن ترحيلها."))

            if batch.fiscal_year and hasattr(batch.fiscal_year, 'is_closed') and batch.fiscal_year.is_closed:
                raise ValidationError(_("السنة المالية مغلقة ولا يمكن الترحيل عليها."))

            # 2. Check Accounting Period Lock Status
            from financial.models.journal_entry import AccountingPeriod
            period_open = AccountingPeriod.objects.filter(
                fiscal_year=batch.fiscal_year,
                start_date__lte=batch.opening_date,
                end_date__gte=batch.opening_date,
                status='open'
            ).exists()
            if not period_open:
                # Fallback check if fiscal year is open and periods are not populated
                if not AccountingPeriod.objects.filter(fiscal_year=batch.fiscal_year).exists():
                    pass
                else:
                    raise ValidationError(_("الفترة المحاسبية المغطاة بتاريخ الرصيد الافتتاحي ({}) مغلقة.").format(batch.opening_date))

            lines = list(batch.lines.select_related('account', 'currency', 'customer', 'supplier', 'treasury_account').all())
            if not lines:
                raise ValidationError(_("لا توجد أسطر في هذه الدفعة للترحيل. يجب إضافة أسطر أولاً."))

            # 3. Currency-Aware Functional Currency Balance Check (Rule 3)
            total_debit = sum((l.debit for l in lines), Decimal('0.00'))
            total_credit = sum((l.credit for l in lines), Decimal('0.00'))
            diff = abs(total_debit - total_credit)

            rounding_line_needed = None
            if diff > Decimal('0.00'):
                tolerance = RoundingTolerancePolicy.get_tolerance('EGP')
                if diff <= tolerance:
                    from financial.services.role_registry import AccountRoleRegistry
                    rounding_account = AccountRoleRegistry.get_account("ROUNDING_DIFFERENCE_ACCOUNT")
                    if total_debit < total_credit:
                        # Add debit line
                        rounding_line_needed = {'account': rounding_account, 'debit': diff, 'credit': Decimal('0.00')}
                    else:
                        # Add credit line
                        rounding_line_needed = {'account': rounding_account, 'debit': Decimal('0.00'), 'credit': diff}
                else:
                    raise ValidationError(_("إجمالي المدين بالعملة الوظيفية ({}) لا يطابق إجمالي الدائن ({}). الفارق ({}) يتجاوز الحد المسموح.").format(total_debit, total_credit, diff))

            # 4. Check Database Idempotency
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
            jv_number = SequenceService.get_next_number(DocumentType.JOURNAL_ENTRY, date=batch.opening_date)

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

                if line.line_type == 'AR' and line.customer:
                    cls._create_customer_opening_item(line, journal_entry, user)
                elif line.line_type == 'AP' and line.supplier:
                    cls._create_supplier_opening_item(line, journal_entry, user)

            if rounding_line_needed:
                line_objects.append(JournalEntryLine(
                    journal_entry=journal_entry,
                    account=rounding_line_needed['account'],
                    debit=rounding_line_needed['debit'],
                    credit=rounding_line_needed['credit'],
                    currency='EGP',
                    exchange_rate=Decimal('1.000000'),
                    description=_("تسوية فروق التقريب المحاسبي آلياً (Rule 3)")
                ))

            JournalEntryLine.objects.bulk_create(line_objects)

            batch.journal_entry = journal_entry
            batch.status = 'posted'
            batch.posted_by = user
            batch.posted_at = timezone.now()

            # Set initial inventory sync status if inventory lines exist
            has_inventory = any(l.line_type == 'INVENTORY' for l in lines)
            if has_inventory:
                batch.inventory_sync_status = 'PENDING'
            else:
                batch.inventory_sync_status = 'NONE'

            batch.save()

        # 7. Decoupled Inventory Opening Request outside Financial Transaction Scope
        if has_inventory:
            cls.trigger_inventory_sync(batch.id, user)

        return batch

    @classmethod
    def trigger_inventory_sync(cls, batch_id, user):
        """
        تفويض معالجة المخزون آلياً لـ InventoryService دون قفل المعاملة المالية
        """
        try:
            batch = OpeningBalanceBatch.objects.get(pk=batch_id)
            sync_key = f"INVENTORY_OPENING:{batch.id}"
            
            if batch.inventory_sync_key == sync_key and batch.inventory_sync_status == 'COMPLETED':
                return batch

            batch.inventory_sync_status = 'PROCESSING'
            batch.inventory_sync_key = sync_key
            batch.last_attempt_at = timezone.now()
            batch.last_attempt_by = user
            batch.save(update_fields=['inventory_sync_status', 'inventory_sync_key', 'last_attempt_at', 'last_attempt_by'])

            # Attempt inventory snapshot processing
            inventory_lines = batch.lines.filter(line_type='INVENTORY')
            if inventory_lines.exists():
                try:
                    from product.services.inventory_service import InventoryService
                    for inv_line in inventory_lines:
                        if hasattr(InventoryService, 'process_opening_line'):
                            InventoryService.process_opening_line(inv_line, user)
                except Exception as ie:
                    logger.warning(f"Inventory processing delegated call error: {ie}")

            batch.inventory_sync_status = 'COMPLETED'
            batch.save(update_fields=['inventory_sync_status'])
            return batch
        except Exception as e:
            logger.error(f"Inventory Opening Processing Failed for Batch {batch_id}: {e}")
            OpeningBalanceBatch.objects.filter(pk=batch_id).update(
                inventory_sync_status='FAILED',
                last_error=str(e),
                last_attempt_at=timezone.now(),
                retry_count=models.F('retry_count') + 1
            )
            return OpeningBalanceBatch.objects.get(pk=batch_id)

    @classmethod
    def retry_inventory_sync(cls, batch_id, user):
        """
        إعادة محاولة مزامنة المخزون مع ضمان عدم التكرار (Idempotency)
        """
        with transaction.atomic():
            batch = OpeningBalanceBatch.objects.select_for_update().get(pk=batch_id)
            if batch.inventory_sync_status == 'COMPLETED':
                return batch
            if batch.inventory_sync_status == 'PROCESSING':
                return batch
        return cls.trigger_inventory_sync(batch_id, user)

    @classmethod
    def reverse(cls, batch_id, user, reason):
        """
        عكس دفعة الأرصدة الافتتاحية المرحّلة مع فحص حظر التخصيصات النشطة
        """
        with transaction.atomic():
            batch = OpeningBalanceBatch.objects.select_for_update().get(pk=batch_id)

            if batch.status != 'posted':
                raise ValidationError(_("يمكن فقط عكس الدفعات المرحّلة (POSTED)."))

            if batch.status == 'reversed' or batch.reversal_journal_entry_id:
                raise ImmutableLedgerError(_("الدفعة تم عكسها بالفعل ولا يمكن عكسها مرتين."))

            if not reason:
                raise ValidationError(_("يجب تقديم سبب لإلغاء وعكس الدفعة الافتتاحية."))

            # Business Rule: Check for active allocations on AR/AP subledger items
            cls._check_subledger_allocations(batch)

            original_jv = batch.journal_entry
            if not original_jv:
                raise ValidationError(_("لم يتم العثور على القيد الافتتاحي الأصلي المرتبط بالدفعة."))

            rev_jv_number = SequenceService.get_next_number(DocumentType.REVERSAL_JOURNAL, date=timezone.now().date())

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

            orig_lines = original_jv.lines.all()
            rev_lines = []
            for ol in orig_lines:
                rev_lines.append(JournalEntryLine(
                    journal_entry=reversal_jv,
                    account=ol.account,
                    debit=ol.credit,
                    credit=ol.debit,
                    currency=ol.currency or 'EGP',
                    foreign_debit=ol.foreign_credit,
                    foreign_credit=ol.foreign_debit,
                    exchange_rate=ol.exchange_rate,
                    description=f"عكس رصيد افتتاحي: {ol.description}"
                ))
            JournalEntryLine.objects.bulk_create(rev_lines)

            lines = batch.lines.all()
            for line in lines:
                if line.line_type == 'AR' and line.customer:
                    cls._reverse_customer_opening_item(line, reversal_jv, user)
                elif line.line_type == 'AP' and line.supplier:
                    cls._reverse_supplier_opening_item(line, reversal_jv, user)

            batch.reversal_journal_entry = reversal_jv
            batch.status = 'reversed'
            batch.reversed_by = user
            batch.reversed_at = timezone.now()
            batch.reversal_reason = reason
            batch.save()

            return batch

    @classmethod
    def _check_subledger_allocations(cls, batch):
        """التحقق من عدم وجود سدادات أو تخصيصات نشطة مرتبطة بالأرصدة الافتتاحية للعملاء أو الموردين"""
        try:
            from client.models import CustomerTransaction
            c_txs = CustomerTransaction.objects.filter(reference_type="OPENING_BALANCE", reference_id=str(batch.id))
            for ctx in c_txs:
                if hasattr(ctx, 'allocations') and ctx.allocations.exists():
                    raise ValidationError(_("لا يمكن عكس الدفعة الافتتاحية لارتباط رصيد العميل ({}) بسدادات وتخصيصات مالية نشطة. يرجى إلغاء التخصيص أولاً.").format(ctx.customer.name))
        except ValidationError:
            raise
        except Exception:
            pass

        try:
            from supplier.models import SupplierTransaction
            s_txs = SupplierTransaction.objects.filter(reference_type="OPENING_BALANCE", reference_id=str(batch.id))
            for stx in s_txs:
                if hasattr(stx, 'allocations') and stx.allocations.exists():
                    raise ValidationError(_("لا يمكن عكس الدفعة الافتتاحية لارتباط رصيد المورد ({}) بسدادات وتخصيصات مالية نشطة. يرجى إلغاء التخصيص أولاً.").format(stx.supplier.name))
        except ValidationError:
            raise
        except Exception:
            pass

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
OpeningBalancePostingService.post_batch = OpeningBalancePostingService.post
OpeningBalancePostingService.reverse_batch = OpeningBalancePostingService.reverse
OpeningBalanceService = OpeningBalancePostingService
OpeningBalanceValidationService = OpeningBalancePostingService


