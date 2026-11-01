# -*- coding: utf-8 -*-
"""
ResaleContingentRefundService - محرك تسوية وصرف مستحقات العملاء لعقود مفسوخة معلقة لإعادة الطرح
(Wave 3 Phase 14 - Resale-Contingent Refund Workflow)
"""

import logging
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from core.enums.document_types import DocumentType
from core.services.sequence_service import SequenceService
from real_estate.models.contract import PropertyContract
from real_estate.models.refund import ResaleContingentRefund
from real_estate.services.accounting_service import RealEstateAccountingService

logger = logging.getLogger(__name__)


class ResaleContingentRefundService:
    """
    خدمة إدارة وحماية مستحقات العملاء بعد فسخ التعاقد:
    - تعليق المستحقات في حساب 21701 لحماية السيولة النقدية للشركة
    - ربط الإفراج عن المستحقات بإعادة طرح الوحدة وإبرام عقد بيع جديد وتحصيل الدفعة المقدمة
    - إصدار قيد صرف المستحقات وسدادها دفترياً
    """

    @classmethod
    def create_contingent_refund(
        cls,
        cancelled_contract: PropertyContract,
        cancellation_penalty_amount: Decimal = Decimal('0.00'),
        notes: str = "",
        user=None
    ) -> ResaleContingentRefund:
        """
        إنشاء سجل مستحقات رد معلقة لحين إعادة الطرح
        """
        total_paid = Decimal(str(cancelled_contract.down_payment or Decimal('0.00')))
        if cancelled_contract.installment_plan:
            for item in cancelled_contract.installment_plan.items.all():
                total_paid += Decimal(str(item.paid_amount or Decimal('0.00')))

        penalty_dec = Decimal(str(cancellation_penalty_amount or Decimal('0.00')))
        net_refund = max(Decimal('0.00'), total_paid - penalty_dec)

        if net_refund <= Decimal('0.00'):
            raise ValidationError(_("صافي المبلغ المستحق رده بعد خصم غرامة الفسخ يجب أن يكون أكبر من الصفر."))

        try:
            refund_number = SequenceService.get_next_number(
                document_type=DocumentType.RESALE_REFUND,
                date=timezone.localdate()
            )
        except Exception as exc:
            logger.warning(f"Failed to generate sequence via SequenceService: {exc}")
            refund_number = f"RRF-{timezone.now().strftime('%Y%m%d%H%M%S')}-{cancelled_contract.id}"

        refund_record = ResaleContingentRefund.objects.create(
            refund_number=refund_number,
            original_contract=cancelled_contract,
            unit=cancelled_contract.unit,
            customer=cancelled_contract.customer,
            total_paid_before_cancellation=total_paid,
            cancellation_penalty_amount=penalty_dec,
            net_refundable_amount=net_refund,
            status=ResaleContingentRefund.RefundStatus.PENDING_RESALE,
            notes=notes,
            created_by=user
        )
        return refund_record

    @classmethod
    def link_resale_contract_and_authorize_disbursement(
        cls,
        refund_record: ResaleContingentRefund,
        new_contract: PropertyContract,
        user
    ) -> ResaleContingentRefund:
        """
        الربط بعقد المشتري الجديد والتحقق من تحصيل مقدم التعاقد والتصريح بصرف المستحقات
        """
        if refund_record.status != ResaleContingentRefund.RefundStatus.PENDING_RESALE:
            raise ValidationError(
                _("سجل المستحقات ليس في حالة التعليق لإعادة الطرح (الحالة: %(status)s).") % {
                    'status': refund_record.get_status_display()
                }
            )

        if new_contract.unit_id != refund_record.unit_id:
            raise ValidationError(_("العقد الجديد لا يخص نفس الوحدة العقارية المعاد طرحها."))

        if new_contract.down_payment <= Decimal('0.00'):
            raise ValidationError(_("يجب سداد وتحصيل مقدم تعاقد العقد الجديد للتصريح بصرف المستحقات."))

        refund_record.resale_contract = new_contract
        refund_record.status = ResaleContingentRefund.RefundStatus.DISBURSEMENT_AUTHORIZED
        refund_record.authorized_by = user
        refund_record.save(update_fields=['resale_contract', 'status', 'authorized_by', 'updated_at'])

        logger.info(
            f"Disbursement authorized for refund {refund_record.refund_number} "
            f"following new contract {new_contract.contract_number} on unit {refund_record.unit.unit_code}"
        )
        return refund_record

    @classmethod
    def disburse_refund(
        cls,
        refund_record: ResaleContingentRefund,
        payment_account,
        user
    ) -> ResaleContingentRefund:
        """
        صرف المستحقات وإصدار القيد الدفتري من حساب 21701 إلى حساب الخزينة أو البنك
        """
        with transaction.atomic():
            locked_refund = ResaleContingentRefund.objects.select_for_update().get(pk=refund_record.pk)
            if locked_refund.status == ResaleContingentRefund.RefundStatus.DISBURSED:
                raise ValidationError(_("تم صرف هذه المستحقات وسدادها بالدفاتر مسبقاً."))

            if locked_refund.status != ResaleContingentRefund.RefundStatus.DISBURSEMENT_AUTHORIZED:
                raise ValidationError(
                    _("لا يمكن صرف المستحقات قبل التصريح بالصرف والتحقق من إعادة بيع الوحدة (الحالة: %(status)s).") % {
                        'status': locked_refund.get_status_display()
                    }
                )

            entry = RealEstateAccountingService.post_resale_contingent_refund_disbursement(
                refund_record=locked_refund,
                payment_account=payment_account,
                user=user,
                reference=locked_refund.refund_number
            )

            locked_refund.disbursement_entry = entry
            locked_refund.status = ResaleContingentRefund.RefundStatus.DISBURSED
            locked_refund.disbursed_at = timezone.now()
            locked_refund.save(update_fields=['disbursement_entry', 'status', 'disbursed_at', 'updated_at'])

            logger.info(
                f"Refund {locked_refund.refund_number} disbursed successfully: "
                f"amount={locked_refund.net_refundable_amount}, JE={entry.number}"
            )
            return locked_refund
