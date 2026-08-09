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

        if run.status != 'VALIDATED':
            FXValidationService.validate_run(run, user=user)

        lines = run.lines.all()
        if not lines.exists():
            run.status = 'POSTED'
            run.completed_at = timezone.now()
            run.save(update_fields=['status', 'completed_at'])
            return run

        # 1. تجهيز بيانات أسطر القيد المحاسبي
        lines_data = []
        entry_description = f"قيد إعادة تقييم أسعار الصرف غير المحققة (IAS 21) للفترة: {run.period.name}"

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
            run.status = 'POSTED'
            run.completed_at = timezone.now()
            run.save(update_fields=['status', 'completed_at'])
            return run

        # 2. النطاق الذري الصارم لقاعدة البيانات حصراً (Strict Transactional Boundary)
        with transaction.atomic():
            draft_entry = LedgerCoreService.create_draft_entry(
                entry_date=run.period.end_date, # التثبيت بتاريخ نهاية الفترة المحددة حصراً
                description=entry_description,
                source_module="FINANCIAL",
                source_model="FXRevaluationRun",
                source_id=str(run.id),
                lines_data=lines_data,
                user=user
            )

            posted_entry = LedgerCoreService.post_entry(draft_entry, user=user)

            run.journal_entry = posted_entry
            run.status = 'POSTED'
            run.completed_at = timezone.now()
            run.save(update_fields=['journal_entry', 'status', 'completed_at'])

        logger.info(f"🎉 تم ترحيل قيد التقييم بنجاح بالدفتر العام برقم #{posted_entry.id} للتشغيل #{run.id}")
        return run
