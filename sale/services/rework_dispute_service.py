# -*- coding: utf-8 -*-
"""
FIN-REWORK-DISPUTE: Defect & Rework Protocol Service
خدمة حوكمة عيوب التشغيل والرفض الفني للباتشات وإعادة التنشيط بعد تسليم التشغيلة البديلة
"""
import logging
from decimal import Decimal
from typing import Optional, Dict, Any

from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from sale.models.installments import (
    InstallmentPlan,
    InstallmentItem,
    InstallmentCashStatus,
    PlanStatus,
)

logger = logging.getLogger(__name__)


class ReworkDisputeService:
    """
    خدمة إدارة عيوب الطباعة والتشغيل:
    - تعليق القسط لحين إعادة التشغيل (HOLD_REWORK) وتجميد غراماته
    - تحويل الخطة إلى DISPUTED
    - بروتوكول فك التعليق (resolve_rework_hold) بإذن تسليم بديل معتمد
    """

    @classmethod
    def apply_rework_hold(
        cls,
        installment_item: InstallmentItem,
        defect_description: str = "",
        user=None
    ) -> InstallmentItem:
        """
        تعليق القسط بسبب عيب تشغيل أو رفض فني للجودة
        """
        with transaction.atomic():
            locked_it = InstallmentItem.objects.select_for_update().get(pk=installment_item.pk)

            if locked_it.cash_status == InstallmentCashStatus.COLLECTED:
                raise ValidationError(_("لا يمكن تعليق قسط محصل بالكامل."))

            locked_it.cash_status = InstallmentCashStatus.HOLD_REWORK
            # تجميد وتصفير غرامات التأخير الناتجة عن فترة النزاع الفني
            locked_it.penalty_amount = Decimal("0.00")
            desc = defect_description or _("عيب تشغيل ورفض فني للباتش")
            locked_it.notes = f"{locked_it.notes or ''} [HOLD_REWORK: {desc}]".strip()
            locked_it.save()

            plan = locked_it.plan
            if plan.status != PlanStatus.DISPUTED:
                plan.status = PlanStatus.DISPUTED
                plan.save(update_fields=['status'])

            logger.info(f"Applied HOLD_REWORK on installment #{locked_it.id}: {desc}")
            return locked_it

    @classmethod
    def resolve_rework_hold(
        cls,
        installment_item: InstallmentItem,
        replacement_delivery_note,
        user=None
    ) -> InstallmentItem:
        """
        فك تعليق القسط بعد تسليم الدفعة البديلة المطابقة واعتماد إذن التسليم
        """
        if not replacement_delivery_note:
            raise ValidationError(_("يجب توفير إذن التسليم البديل المعتمد لفك التعليق."))

        dn_number = getattr(replacement_delivery_note, 'delivery_number', None) or getattr(replacement_delivery_note, 'number', '')
        dn_status = getattr(replacement_delivery_note, 'status', '')
        if dn_status not in ['DELIVERED', 'delivered', 'confirmed', 'posted']:
            raise ValidationError(
                _(f"إذن التسليم البديل #{dn_number} ليس بحالة معتمدة / مسلمة ({dn_status}).")
            )

        with transaction.atomic():
            locked_it = InstallmentItem.objects.select_for_update().get(pk=installment_item.pk)

            if locked_it.cash_status != InstallmentCashStatus.HOLD_REWORK:
                raise ValidationError(_("هذا القسط ليس معلقاً لعيب تشغيل (ليس في حالة HOLD_REWORK)."))

            locked_it.cash_status = InstallmentCashStatus.PENDING
            locked_it.linked_delivery_note = replacement_delivery_note

            # بدء عداد استحقاق جديد من تاريخ التسليم الفعلي البديل
            deliv_date = getattr(replacement_delivery_note, 'delivery_date', None) or getattr(replacement_delivery_note, 'date', None) or timezone.localdate()
            locked_it.due_date = deliv_date + timezone.timedelta(days=30)
            locked_it.notes = f"{locked_it.notes or ''} [REWORK_RESOLVED: بديل #{dn_number}]".strip()
            locked_it.save()

            # فحص حالة الخطة لإعادتها إلى ACTIVE
            plan = locked_it.plan
            has_other_disputes = plan.items.filter(cash_status=InstallmentCashStatus.HOLD_REWORK).exists()
            if not has_other_disputes:
                plan.status = PlanStatus.ACTIVE
                plan.save(update_fields=['status'])

            logger.info(f"Resolved HOLD_REWORK for installment #{locked_it.id} via DN #{dn_number}")
            return locked_it
