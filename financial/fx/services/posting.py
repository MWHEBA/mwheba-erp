import logging
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from financial.fx.models import FXRevaluationRun
from financial.fx.services.validation import FXValidationService
from financial.services.ledger_core_service import LedgerCoreService

logger = logging.getLogger("financial.fx.services.posting")


class FXPostingService:
    """
    FXPostingService - محرك ترحيل قيد التقييم بالدفتر العام بحدود معاملات ذرية صريحة (Strict Atomic DB Boundary)
    """

    @classmethod
    def post_run(cls, run: FXRevaluationRun, user=None) -> FXRevaluationRun:
        """
        ترحيل قيد إعادة التقييم الرسمي بالدفتر العام بشكل ذري مائة بالمائة
        """
        if run.status == 'POSTED':
            logger.info(f"التشغيل #{run.id} مرحل بالفعل بالدفتر برقم القيد #{run.journal_entry_id}.")
            return run

        with transaction.atomic():
            # قفل صف التشغيل وإعادة التحقق الحتمي من سلامة ومطابقة المصادر لمنع السباق التزامني
            locked_run = FXRevaluationRun.objects.select_for_update().get(pk=run.pk)
            if locked_run.status == 'POSTED':
                return locked_run

            # إعادة التحقق الصارم من سلامة المصادر والأسعار حتى لو كانت الحالة مسبقاً VALIDATED
            FXValidationService.validate_run(locked_run, user=user)

            lines = locked_run.lines.all()
            if not lines.exists():
                locked_run.status = 'POSTED'
                locked_run.completed_at = timezone.now()
                locked_run.save(update_fields=['status', 'completed_at'])
                return locked_run

            # 1. تجهيز بيانات أسطر القيد المحاسبي
            lines_data = []
            entry_description = f"قيد إعادة تقييم أسعار الصرف غير المحققة للفترة: {locked_run.period.name}"

            for line in lines:
                diff = line.unrealized_difference
                if abs(diff) < Decimal("0.01"):
                    continue

                # في حالة الربح (diff > 0): مدين بالحساب الأساسي (AR/Cash) ودائن بحساب أرباح التقييم
                # في حالة الخسارة (diff < 0): مدين بحساب خسائر التقييم ودائن بالحساب الأساسي
                if diff > 0:
                    lines_data.append({
                        "account": line.account,
                        "debit": abs(diff),
                        "credit": Decimal("0.00"),
                        "description": f"فرق تقييم موجب - {line.partner_name} ({line.source_id})"
                    })
                    lines_data.append({
                        "account": line.gain_loss_account,
                        "debit": Decimal("0.00"),
                        "credit": abs(diff),
                        "description": f"أرباح تقييم عملة غير محققة - {line.currency.code}"
                    })
                else:
                    lines_data.append({
                        "account": line.gain_loss_account,
                        "debit": abs(diff),
                        "credit": Decimal("0.00"),
                        "description": f"خسائر تقييم عملة غير محققة - {line.currency.code}"
                    })
                    lines_data.append({
                        "account": line.account,
                        "debit": Decimal("0.00"),
                        "credit": abs(diff),
                        "description": f"فرق تقييم سالب - {line.partner_name} ({line.source_id})"
                    })

            if not lines_data:
                locked_run.status = 'POSTED'
                locked_run.completed_at = timezone.now()
                locked_run.save(update_fields=['status', 'completed_at'])
                return locked_run

            # 2. إنشاء وترحيل قيد اليومية
            draft_entry = LedgerCoreService.create_draft_entry(
                date=locked_run.period.end_date,
                description=entry_description,
                reference=f"FX-REV-{locked_run.id}",
                entry_type="ADJUSTMENT",
                created_by=user,
                lines_data=lines_data,
                source_module="FINANCIAL",
                source_model="FXRevaluationRun",
                source_id=str(locked_run.id),
            )

            posted_entry = LedgerCoreService.post_entry(entry_id=draft_entry.id, user=user)

            # تحديث القيمة الدفترية لشيكات أوراق القبض والدفع المشمولة بالتقييم بشكل ذري
            for line in lines.filter(source_type__in=['NOTES_RECEIVABLE', 'NOTES_PAYABLE']):
                from cheques.models import Cheque
                cheque = Cheque.objects.select_for_update().filter(pk=int(line.source_id)).first()
                if not cheque:
                    raise ValidationError(f"تعذر العثور على الشيك #{line.source_id} لتحديث قيمته الدفترية في الأستاذ العام.")
                cheque.book_value_functional = (cheque.amount * line.new_rate).quantize(Decimal('0.01'))
                cheque.remaining_functional = cheque.compute_remaining_functional()
                cheque.save(update_fields=['book_value_functional', 'remaining_functional'])

            locked_run.journal_entry = posted_entry
            locked_run.status = 'POSTED'
            locked_run.completed_at = timezone.now()
            locked_run.save(update_fields=['journal_entry', 'status', 'completed_at'])

            run.journal_entry = posted_entry
            run.status = 'POSTED'
            run.completed_at = locked_run.completed_at

        logger.info(f"🎉 تم ترحيل قيد التقييم بنجاح بالدفتر العام برقم #{posted_entry.id} للتشغيل #{locked_run.id}")
        return locked_run
