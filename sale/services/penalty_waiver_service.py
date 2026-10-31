# -*- coding: utf-8 -*-
"""
FIN-PENALTY-WAIVER: Operational Penalty Waiver Service
خدمة حوكمة إسقاط غرامات التأخير التشغيلية خارج الميزانية دون المساس برصيد الفاتورة
"""
import logging
from decimal import Decimal
from typing import Optional, Dict, Any

from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from sale.models.installments import (
    InstallmentItem,
    InstallmentSettlement,
)

logger = logging.getLogger(__name__)


class PenaltyWaiverService:
    """
    خدمة إسقاط غرامات التأخير:
    - تخفيض penalty_amount للقسط
    - تسجيل تسوية دائمة من نوع PENALTY_WAIVER بحقل affects_invoice_due=False
    - ضمان عدم خصم الغرامة نهائياً من أصل دين الفاتورة Sale.amount_due
    """

    @classmethod
    def waive_installment_penalty(
        cls,
        installment_item: InstallmentItem,
        waived_amount: Decimal,
        reason: str = "",
        user=None
    ) -> Dict[str, Any]:
        """
        إسقاط غرامة تأخير تشغيلية للقسط
        """
        if not isinstance(waived_amount, Decimal):
            waived_amount = Decimal(str(waived_amount))

        if waived_amount <= Decimal("0.00"):
            raise ValidationError(_("يجب أن يكون مبلغ الغرامة المراد إسقاطه أكبر من الصفر."))

        if not reason or not reason.strip():
            reason = _("إعفاء تشغيلي معتمد لغرامة التأخير")

        with transaction.atomic():
            locked_it = InstallmentItem.objects.select_for_update().get(pk=installment_item.pk)

            if waived_amount > locked_it.penalty_amount:
                raise ValidationError(
                    _(f"المبلغ المراد إسقاطه ({waived_amount}) يتجاوز رصيد الغرامة القائم على القسط ({locked_it.penalty_amount}).")
                )

            sale = locked_it.plan.sale
            old_penalty = locked_it.penalty_amount
            locked_it.penalty_amount = max(Decimal("0.00"), locked_it.penalty_amount - waived_amount)
            locked_it.save(update_fields=['penalty_amount'])

            settlement = InstallmentSettlement.objects.create(
                sale=sale,
                installment_item=locked_it,
                settlement_type=InstallmentSettlement.SettlementType.PENALTY_WAIVER,
                amount=waived_amount,
                journal_entry=None,  # غرامة تشغيلية خارج الميزانية لا تؤثر على الأستاذ العام
                status="POSTED",
                affects_invoice_due=False,  # لا تخفض رصيد الفاتورة نهائياً
                notes=f"إسقاط غرامة تأخير تشغيلية: {reason}",
                created_by=user,
            )

            logger.info(
                f"Waived penalty of {waived_amount} on installment #{locked_it.id} "
                f"(Remaining penalty: {locked_it.penalty_amount})"
            )

            return {
                "status": "SUCCESS",
                "installment_item": locked_it,
                "settlement": settlement,
                "waived_amount": waived_amount,
                "old_penalty": old_penalty,
                "new_penalty": locked_it.penalty_amount,
            }
