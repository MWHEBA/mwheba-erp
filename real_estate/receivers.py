# -*- coding: utf-8 -*-
"""
real_estate/receivers.py - مستقبلات الإشارات لربط منظومة الشيكات بتسويات الحجوزات العقارية
(Two-Way Sync Hook between Central Cheques Engine and Real Estate Booking Settlements)
"""
import logging
from decimal import Decimal
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from cheques.models import ChequeActionLog, ChequePurpose, ChequeStatus
from real_estate.models import BookingCancellationSettlement, RefundDisbursementPayment

logger = logging.getLogger(__name__)


@receiver(post_save, sender=ChequeActionLog)
def sync_refund_cheque_lifecycle(sender, instance, created, **kwargs):
    """
    مزامنة حالة وحركات الشيكات الصادرة لاسترداد الحجوزات العقارية مع سندات الصرف وقرار التسوية
    """
    # معالجة عند الإنشاء أو عند ربط القيد المحاسبي لاحقاً
    passed_update_fields = kwargs.get('update_fields')
    if not created and (not passed_update_fields or 'journal_entry' not in passed_update_fields):
        return

    cheque = instance.cheque
    if not cheque or cheque.purpose != ChequePurpose.CUSTOMER_REFUND:
        return

    payment = RefundDisbursementPayment.objects.filter(cheque_id=cheque.id).first()
    if not payment:
        return

    # الالتزام بالترتيب الهرمي للأقفال (Level 2: التسوية، Level 3: سند الصرف)
    with transaction.atomic():
        try:
            locked_settlement = BookingCancellationSettlement.objects.select_for_update().get(pk=payment.settlement_id)
            locked_payment = RefundDisbursementPayment.objects.select_for_update().get(pk=payment.id)
        except (BookingCancellationSettlement.DoesNotExist, RefundDisbursementPayment.DoesNotExist):
            return

        to_status = instance.to_status
        updated_fields = ['updated_at']

        if to_status == ChequeStatus.CLEARED:
            locked_payment.status = RefundDisbursementPayment.PaymentStatus.CLEARED
            updated_fields.append('status')
            if instance.journal_entry_id:
                locked_payment.clearing_journal_entry = instance.journal_entry
                updated_fields.append('clearing_journal_entry')

        elif to_status == ChequeStatus.BOUNCED:
            locked_payment.status = RefundDisbursementPayment.PaymentStatus.BOUNCED
            updated_fields.append('status')
            if instance.journal_entry_id:
                locked_payment.reversal_journal_entry = instance.journal_entry
                updated_fields.append('reversal_journal_entry')

        elif to_status == ChequeStatus.CANCELLED:
            locked_payment.status = RefundDisbursementPayment.PaymentStatus.CANCELLED
            updated_fields.append('status')
            if instance.journal_entry_id and not locked_payment.reversal_journal_entry_id:
                locked_payment.reversal_journal_entry = instance.journal_entry
                updated_fields.append('reversal_journal_entry')

        locked_payment.save(update_fields=updated_fields)
        locked_settlement.recalculate_balances()

        # مزامنة حالة الحجز بحسب الرصيد المتبقي والمسيل فعلياً بعد حركة الشيك
        if locked_settlement.booking:
            from real_estate.models import UnitBooking
            if locked_settlement.remaining_disbursable_amount > Decimal('0.00'):
                if locked_settlement.booking.status == UnitBooking.BookingStatus.CANCELLED_REFUNDED:
                    locked_settlement.booking.status = UnitBooking.BookingStatus.CANCELLED_PENDING_REFUND
                    locked_settlement.booking.save(update_fields=['status', 'updated_at'])
            elif locked_settlement.cleared_amount >= locked_settlement.net_refundable_amount and locked_settlement.net_refundable_amount > Decimal('0.00'):
                if locked_settlement.booking.status != UnitBooking.BookingStatus.CANCELLED_REFUNDED:
                    locked_settlement.booking.status = UnitBooking.BookingStatus.CANCELLED_REFUNDED
                    locked_settlement.booking.save(update_fields=['status', 'updated_at'])

        logger.info(
            f"🔄 [ChequeSyncHook] تم مزامنة حركة الشيك #{cheque.cheque_number} ({to_status}) "
            f"مع سند الصرف {locked_payment.payment_number} وتسوية الحجز {locked_settlement.settlement_number}"
        )
