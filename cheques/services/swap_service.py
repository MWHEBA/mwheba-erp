# -*- coding: utf-8 -*-
"""
FIN-CHQ-SWAP: Audit-Compliant Cheque Swap Service
خدمة حوكمة استبدال الشيكات الآجلة وحفظ سلسلة مراجع التدقيق دون إطلاق آثار الارتداد
"""
import logging
from decimal import Decimal
from typing import Optional, Dict, Any

from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from cheques.models import (
    Cheque,
    ChequeStatus,
    ChequeActionLog,
    ChequeActionType,
    AllocationStatus,
)
from cheques.services.allocation_service import ChequeAllocationService

logger = logging.getLogger(__name__)


class ChequeSwapService:
    """
    خدمة الرقابة على استبدال شيكات التقسيط:
    - اشتراط وجود الشيك القديم بحافظة الخزينة حصراً (IN_PORTFOLIO)
    - حظر الاستبدال الجزئي للشيكات المشتركة
    - فك التخصيص وعزل أثر الارتداد (RETURNED_TO_DRAWER وليس BOUNCED)
    - تخصيص الشيك البديل وتحديث تواريخ الاستحقاق والتغطية الورقية
    """

    @classmethod
    def swap_installment_cheque(
        cls,
        old_cheque: Cheque,
        new_cheque: Cheque,
        installment_item,
        user=None,
        reason: str = ""
    ) -> Dict[str, Any]:
        """
        تنفيذ بروتوكول استبدال شيك قسط تجاري:
        1. التحقق من حالة الشيك القديم والجديد
        2. حظر الاستبدال الجزئي للشيكات المشتركة
        3. فك تخصيص الشيك القديم دون آثار الارتداد
        4. تخصيص الشيك الجديد وتحديث القسط
        """
        if not reason or not reason.strip():
            reason = _("استبدال تجاري للشيك باتفاق مع العميل")

        # 1. التحقق الصارم من حالة الشيك القديم
        if old_cheque.status != ChequeStatus.IN_PORTFOLIO:
            raise ValidationError(
                _(f"لا يمكن استبدال الشيك #{old_cheque.voucher_number} وهو في حالة '{old_cheque.get_status_display()}'. "
                  f"يُشترط أن يكون الشيك في الحافظة/الخزينة (IN_PORTFOLIO).")
            )

        # 2. فحص الشيك المشترك متعدد التخصيص
        if old_cheque.is_shared_or_multi_allocated:
            # التحقق هل الشيك البديل يغطي كامل قيمة الشيك القديم المسترد
            if new_cheque.amount < old_cheque.amount:
                raise ValidationError(
                    _("لا يجوز الاستبدال الجزئي لشيك مشترك يغطي عدة فواتير/أقساط بشيك يغطي قسطاً واحداً فقط؛ "
                      "لأن ذلك يُسقط التغطية الورقية عن باقي الأقساط دون مبرر.")
                )

        # 3. التحقق من الشيك البديل الجديد
        if new_cheque.status != ChequeStatus.IN_PORTFOLIO:
            raise ValidationError(
                _(f"الشيك البديل #{new_cheque.voucher_number} يجب أن يكون في حالة الحافظة (IN_PORTFOLIO).")
            )

        if new_cheque.id == old_cheque.id:
            raise ValidationError(_("لا يمكن استبدال الشيك بنفسه."))

        sale = installment_item.plan.sale
        if new_cheque.customer_id and new_cheque.customer_id != sale.customer_id:
            raise ValidationError(_("العميل في الشيك البديل لا يتطابق مع عميل الفاتورة."))

        with transaction.atomic():
            locked_old = Cheque.objects.select_for_update().get(pk=old_cheque.pk)
            locked_new = Cheque.objects.select_for_update().get(pk=new_cheque.pk)
            locked_item = installment_item.__class__.objects.select_for_update().get(pk=installment_item.pk)

            # البحث عن التخصيص الساري للشيك القديم على هذا القسط بالتحديد
            old_alloc = locked_old.invoice_allocations.filter(
                installment_item=locked_item,
                allocation_status=AllocationStatus.APPLIED
            ).first()

            if not old_alloc:
                # محاولة البحث عن تخصيص على الفاتورة التابعة للقسط
                old_alloc = locked_old.invoice_allocations.filter(
                    sale=sale,
                    allocation_status=AllocationStatus.APPLIED
                ).first()

            if not old_alloc:
                raise ValidationError(_("لا يوجد تخصيص ساري للشيك القديم على هذا القسط أو الفاتورة."))

            swap_amount = old_alloc.allocated_amount

            # فحص رصيد الشيك البديل
            if locked_old.is_shared_or_multi_allocated:
                active_allocs = list(locked_old.invoice_allocations.filter(allocation_status=AllocationStatus.APPLIED))
                total_active = sum(a.allocated_amount for a in active_allocs)
                if total_active > locked_new.unallocated_amount:
                    raise ValidationError(
                        _(f"مجموع تخصيصات الشيك المشترك السارية ({total_active}) يتجاوز الرصيد المتاح بالشيك البديل ({locked_new.unallocated_amount}).")
                    )
            elif swap_amount > locked_new.unallocated_amount:
                raise ValidationError(
                    _(f"مبلغ التخصيص المطلوب ({swap_amount}) يتجاوز الرصيد المتاح بالشيك البديل ({locked_new.unallocated_amount}).")
                )

            # أ) نقل التخصيصات من الشيك القديم إلى الشيك البديل
            if locked_old.is_shared_or_multi_allocated:
                new_alloc = None
                for alloc in active_allocs:
                    alloc_item = alloc.installment_item
                    alloc_sale = alloc.sale
                    alloc_amt = alloc.allocated_amount

                    ChequeAllocationService.reverse_cheque_allocation(
                        allocation=alloc,
                        reason=f"CHEQUE_SWAP_SHARED: {reason}",
                        user=user
                    )
                    created_alloc = ChequeAllocationService.allocate_cheque_to_invoice(
                        cheque=locked_new,
                        sale=alloc_sale,
                        amount=alloc_amt,
                        installment_item=alloc_item,
                        user=user,
                        notes=f"استبدال تجاري للشيك المشترك #{locked_old.voucher_number}: {reason}"
                    )
                    if alloc.id == old_alloc.id:
                        new_alloc = created_alloc

                    if alloc_item:
                        if locked_new.due_date:
                            alloc_item.due_date = locked_new.due_date
                        alloc_item.cheques.remove(locked_old)
                        alloc_item.cheques.add(locked_new)
                        alloc_item.save(update_fields=['due_date'])
                        ChequeAllocationService.recalculate_installment_paper_coverage(alloc_item)
            else:
                # فك تخصيص الشيك القديم المنضبط
                ChequeAllocationService.reverse_cheque_allocation(
                    allocation=old_alloc,
                    reason=f"CHEQUE_SWAP: {reason}",
                    user=user
                )
                # تخصيص الشيك البديل الجديد
                new_alloc = ChequeAllocationService.allocate_cheque_to_invoice(
                    cheque=locked_new,
                    sale=sale,
                    amount=swap_amount,
                    installment_item=locked_item,
                    user=user,
                    notes=f"استبدال تجاري للشيك #{locked_old.voucher_number}: {reason}"
                )
                if locked_new.due_date:
                    locked_item.due_date = locked_new.due_date
                locked_item.cheques.remove(locked_old)
                locked_item.cheques.add(locked_new)
                locked_item.save(update_fields=['due_date'])
                ChequeAllocationService.recalculate_installment_paper_coverage(locked_item)

            # عزل آثار الارتداد: تحويل حالة الشيك القديم حصراً إلى RETURNED_TO_DRAWER
            locked_old.status = ChequeStatus.RETURNED_TO_DRAWER
            locked_old.notes = f"{locked_old.notes or ''} [SWAPPED_OUT: استُبدل بالشيك #{locked_new.voucher_number}]".strip()
            locked_old.save(update_fields=['status', 'notes'])

            import uuid, hashlib
            idemp_old = f"SWAP-OUT-{locked_old.id}-{uuid.uuid4().hex[:10]}"
            hash_old = hashlib.sha256(idemp_old.encode('utf-8')).hexdigest()

            ChequeActionLog.objects.create(
                cheque=locked_old,
                action=ChequeActionType.RETURN_TO_DRAWER,
                action_date=timezone.localdate(),
                from_status=ChequeStatus.IN_PORTFOLIO,
                to_status=ChequeStatus.RETURNED_TO_DRAWER,
                idempotency_key=idemp_old,
                request_payload_hash=hash_old,
                reason=f"استبدال تجاري للشيك: تم استرداد الشيك وتسليم الشيك البديل #{locked_new.voucher_number}. {reason}",
                created_by=user,
            )

            # توثيق التدقيق للشيك البديل
            idemp_new = f"SWAP-IN-{locked_new.id}-{uuid.uuid4().hex[:10]}"
            hash_new = hashlib.sha256(idemp_new.encode('utf-8')).hexdigest()

            ChequeActionLog.objects.create(
                cheque=locked_new,
                action=ChequeActionType.RECEIVE,
                action_date=timezone.localdate(),
                from_status=ChequeStatus.IN_PORTFOLIO,
                to_status=ChequeStatus.IN_PORTFOLIO,
                idempotency_key=idemp_new,
                request_payload_hash=hash_new,
                reason=f"شيك بديل مستلم في عملية استبدال تجاري للشيك المسترد #{locked_old.voucher_number}",
                created_by=user,
            )

            logger.info(
                f"✅ تم بنجاح استبدال الشيك #{locked_old.voucher_number} بالشيك #{locked_new.voucher_number} "
                f"للقسط #{locked_item.id} بمبلغ {swap_amount}"
            )

            return {
                "status": "SUCCESS",
                "old_cheque": locked_old,
                "new_cheque": locked_new,
                "installment_item": locked_item,
                "new_allocation": new_alloc,
                "swap_amount": swap_amount,
            }
