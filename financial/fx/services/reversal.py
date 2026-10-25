import logging
from django.db import transaction
from django.utils import timezone
from financial.fx.models import FXRevaluationRun
from financial.services.ledger_core_service import LedgerCoreService

logger = logging.getLogger("financial.fx.services.reversal")


class FXReversalService:
    """
    FXReversalService - محرك التقييم العكسي الشرطي لحماية سجل التدقيق (Audit Trail Preservation)
    """

    @classmethod
    def reverse_run(cls, run: FXRevaluationRun, user=None, reason: str = "إعادة فتح الفترة وتعديل البيانات المالية") -> FXRevaluationRun:
        """
        ترحيل قيد عكسي محوكم لقيد تقييم العملة وربطه بسلسلة التشغيل العكسي reversal_of_run
        """
        run.refresh_from_db()
        if run.status != 'POSTED' or not run.journal_entry:
            logger.info(f"التشغيل #{run.id} ليس بحالة مرحل بالدفتر، لا يتطلب قيد عكسي.")
            return run

        with transaction.atomic():
            locked_run = FXRevaluationRun.objects.select_for_update().get(pk=run.pk)
            if locked_run.status != 'POSTED' or not locked_run.journal_entry:
                return locked_run

            # 1. ترحيل القيد العكسي في الدفتر العام بسلامة ودون مسح القيد الأصلي
            reversal_entry = LedgerCoreService.reverse_entry(
                entry_id=locked_run.journal_entry.id,
                user=user,
                reversal_reason=f"عكس قيد تقييم العملات للتشغيل #{locked_run.id}: {reason}"
            )

            # 2. إنشاء كائن تشغيل عكسي جديد لتوثيق الحركة في سجل التدقيق
            reversal_run = FXRevaluationRun.objects.create(
                company_code=run.company_code,
                period=run.period,
                accounting_book=run.accounting_book,
                valuation_type=run.valuation_type,
                valuation_method=run.valuation_method,
                currency_scope=run.currency_scope,
                target_currency=run.target_currency,
                status='REVERSED',
                run_date=timezone.now().date(),
                rate_source=run.rate_source,
                journal_entry=reversal_entry,
                reversal_of_run=run,
                total_unrealized_gain_loss=-run.total_unrealized_gain_loss,
                created_by=user,
                completed_at=timezone.now()
            )

            # 3. تحديث حالة التشغيل الأصلي إلى REVERSED
            run.status = 'REVERSED'
            run.save(update_fields=['status'])

            # 4. إعادة ضبط القيمة الدفترية للشيكات المشمولة بالتقييم إلى تكلفتها التاريخية الأصلية بشكل ذري
            for line in run.lines.filter(source_type__in=['NOTES_RECEIVABLE', 'NOTES_PAYABLE']):
                from cheques.models import Cheque
                cheque = Cheque.objects.select_for_update().filter(pk=int(line.source_id)).first()
                if not cheque:
                    raise ValidationError(f"تعذر العثور على الشيك #{line.source_id} لاستعادة قيمته الدفترية في الأستاذ العام.")
                cheque.book_value_functional = cheque.functional_amount
                cheque.remaining_functional = cheque.compute_remaining_functional()
                cheque.save(update_fields=['book_value_functional', 'remaining_functional'])

        logger.info(f"🔄 تم عكس تشغيل التقييم #{run.id} بترحيل القيد العكسي #{reversal_entry.id} وإنشاء سجل التشغيل العكسي #{reversal_run.id}.")
        return reversal_run
