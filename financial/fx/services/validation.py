import hashlib
import logging
from decimal import Decimal
from django.utils import timezone
from django.core.exceptions import ValidationError
from financial.fx.models import FXRevaluationRun, FXApprovalWorkflow

logger = logging.getLogger("financial.fx.services.validation")


class FXValidationService:
    """
    FXValidationService - محرك التحقق المعماري وحظر أسعار الصرف المتقادمة والتغييرات المتزامنة
    """

    @classmethod
    def validate_run(cls, run: FXRevaluationRun, user=None) -> bool:
        """
        التحقق الصارم من صحة ونزاهة تشغيل التقييم قبل التترحيل بالدفتر
        """
        if run.status not in ['CALCULATED', 'DRAFT']:
            if run.status == 'VALIDATED':
                return True
            raise ValidationError(f"لا يمكن اعتماد تشغيل بحالة '{run.get_status_display()}'.")

        as_of_date = run.period.end_date
        today = timezone.now().date()

        # 1. فحص فجوة عمر سعر الصرف (Rate Age Guard > 7 Days)
        snapshots = run.rate_snapshots.all()
        for snap in snapshots:
            age_days = (today - snap.rate_date).days
            if age_days > 7:
                # التحقق من وجود موافقة صريحة من المدير المالي على التجاوز
                override_approved = FXApprovalWorkflow.objects.filter(
                    entity_type="FXRevaluationRun",
                    entity_id=str(run.id),
                    approval_type='RATE_OVERRIDE_APPROVAL',
                    decision='APPROVED'
                ).exists()

                if not override_approved:
                    raise ValidationError(
                        f"سعر الصرف المعتمد للعملة '{snap.currency.code}' متقادم ({age_days} يوماً). "
                        f"يتطلب التقييم موافقة صريحة وموثقة من المدير المالي (CFO Approval) لتجاوز عمر السعر."
                    )

        # 2. فحص قفل التعديل المتزامن المصردي (Source Hash Concurrency Guard)
        lines = run.lines.all()
        for line in lines:
            if line.source_type == 'AR_INVOICE':
                try:
                    from sale.models import CustomerTransaction
                    tx = CustomerTransaction.objects.get(id=int(line.source_id))
                    curr_str = f"AR_{tx.id}_{tx.amount}_{tx.updated_at if hasattr(tx, 'updated_at') else ''}"
                    curr_hash = hashlib.sha256(curr_str.encode('utf-8')).hexdigest()
                    if curr_hash != line.source_hash:
                        raise ValidationError(
                            f"تنبيه: تم تعديل بيانات العقد/الفاتورة #{line.source_id} بعد عملية الحساب. "
                            f"يرجى إعادة حساب التقييم لتعديل الأرقام."
                        )
                except CustomerTransaction.DoesNotExist:
                    raise ValidationError(f"المستند المصدر #{line.source_id} لم يعد موجوداً.")
            elif line.source_type == 'AP_INVOICE':
                try:
                    from purchase.models import PurchaseInvoice
                    inv = PurchaseInvoice.objects.get(id=int(line.source_id))
                    curr_str = f"AP_{inv.id}_{inv.total_amount}_{inv.updated_at if hasattr(inv, 'updated_at') else ''}"
                    curr_hash = hashlib.sha256(curr_str.encode('utf-8')).hexdigest()
                    if curr_hash != line.source_hash:
                        raise ValidationError(
                            f"تنبيه: تم تعديل فاتورة المشتريات #{line.source_id} بعد عملية الحساب. "
                            f"يرجى إعادة حساب التقييم لتعديل الأرقام."
                        )
                except PurchaseInvoice.DoesNotExist:
                    raise ValidationError(f"فاتورة المشتريات #{line.source_id} لم تعد موجودة.")

        # 3. فحص دقة التقريب وحفظ حالة VALIDATED
        sum_diffs = sum((line.unrealized_difference for line in lines), Decimal("0.00"))
        if abs(sum_diffs - run.total_unrealized_gain_loss) > Decimal("0.05"):
            raise ValidationError(
                f"فروق دقة تقريب المحاسبة تتجاوز التسامح المسموح: "
                f"المحسوب ({run.total_unrealized_gain_loss}) vs التراكمي ({sum_diffs})."
            )

        run.status = 'VALIDATED'
        run.save(update_fields=['status'])
        logger.info(f"✅ تم اعتماد تشغيل التقييم #{run.id} بنجاح.")
        return True
