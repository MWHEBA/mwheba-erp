# -*- coding: utf-8 -*-
"""
FIN-SETTLE-REV: Settlement Reversal Service
خدمة عكس التسويات المحاسبية وفصل نطاق القيود المركبة عن المنفصلة
المسار (أ): عكس العمليات المركبة ذات القيد المجمع (مثل السداد المعجل) كحزمة ذرية واحدة
المسار (ب): عكس التسويات الفردية المعزولة (مثل مقاصة الموردين أو إسقاط غرامة)
"""
import logging
from decimal import Decimal
from typing import Optional, Dict, Any, List

from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from financial.services.ledger_core_service import LedgerCoreService
from sale.models.installments import (
    InstallmentPlan,
    InstallmentItem,
    InstallmentCashStatus,
    InstallmentSettlement,
    PlanStatus,
)
from sale.models import Sale, SalePayment

logger = logging.getLogger(__name__)


class SettlementReversalService:
    """
    خدمة عكس التسويات المعتمدة:
    - مسار الحزم المركبة (Composite Operations): batch_id
    - مسار التسويات الفردية المستقلة (Isolated Settlements)
    """

    @classmethod
    def reverse_composite_settlement_batch(
        cls,
        batch_id: str,
        user=None,
        reason: str = ""
    ) -> Dict[str, Any]:
        """
        المسار (أ): عكس العملية المركبة ذات القيد المجمع كحزمة ذرية واحدة
        """
        if not batch_id or not batch_id.strip():
            raise ValidationError(_("يجب تحديد معرف الحزمة المراد عكسها (batch_id)."))

        if not reason or not reason.strip():
            reason = _("إلغاء وعكس العملية المركبة للسداد المعجل")

        with transaction.atomic():
            settlements = list(InstallmentSettlement.objects.select_for_update().filter(batch_id=batch_id))
            payments = list(SalePayment.objects.select_for_update().filter(batch_id=batch_id))

            if not settlements and not payments:
                raise ValidationError(_("لم يتم العثور على أي حركات مرتبطة بمعرف الحزمة المحدد."))

            # التحقق من أن الحزمة لم تُعكس سلفاً منعاً للتكرار
            already_reversed_s = any(s.is_reversed or s.status == "REVERSED" for s in settlements)
            already_reversed_p = any(p.status == "reversed" for p in payments)
            if already_reversed_s or already_reversed_p:
                raise ValidationError(_("تم عكس هذه الحزمة مسبقاً ولا يمكن عكسها مرة ثانية."))

            sale = None
            if settlements:
                sale = settlements[0].sale
            elif payments:
                sale = payments[0].sale

            locked_sale = Sale.objects.select_for_update().get(pk=sale.pk)
            plan = getattr(locked_sale, "installment_plan", None)

            # 1. جلب وعكس قيد اليومية المجمع المرتبط بالحزمة
            reversal_entry = None
            target_je = None
            for s in settlements:
                if s.journal_entry:
                    target_je = s.journal_entry
                    break

            if target_je and target_je.status == "posted":
                reversal_entry = LedgerCoreService.reverse_entry(
                    entry_id=target_je.id,
                    user=user,
                    reversal_reason=f"عكس قيد تسوية مركبة لحزمة {batch_id}: {reason}"
                )

            # 2. تحويل سندات السداد SalePayment إلى reversed
            for pmt in payments:
                pmt.status = "reversed"
                pmt.notes = f"{pmt.notes or ''} [REVERSED: {reason}]".strip()
                pmt.save(update_fields=['status', 'notes'])

            # 3. تحويل كافة سجلات التسوية بالحزمة إلى REVERSED
            now = timezone.now()
            for s in settlements:
                s.status = "REVERSED"
                s.is_reversed = True
                s.reversed_by = user
                s.reversed_at = now
                s.notes = f"{s.notes or ''} [REVERSED: {reason}]".strip()
                s.save(update_fields=['status', 'is_reversed', 'reversed_by', 'reversed_at', 'notes'])

            # 4. استعادة حقول الأقساط ذرياً
            # جلب مبالغ التسويات المرتبطة بالحزمة
            total_cash = sum(p.amount for p in payments)
            discount_amount = sum(
                s.amount for s in settlements
                if s.settlement_type == InstallmentSettlement.SettlementType.EARLY_SETTLEMENT_DISCOUNT
            )
            prepaid_rebate_amount = sum(
                s.amount for s in settlements
                if s.settlement_type == InstallmentSettlement.SettlementType.PREPAID_INTEREST_REBATE
            )
            waived_interest_amount = sum(
                s.amount for s in settlements
                if s.settlement_type == InstallmentSettlement.SettlementType.INTEREST_WAIVER
            )

            # استعادة الأقساط بدقة بناء على لقطة التدقيق المسبقة
            today = timezone.localdate()
            if plan:
                from sale.models import InstallmentOperationAudit
                audit = InstallmentOperationAudit.objects.filter(
                    plan=plan,
                    action="EARLY_SETTLEMENT",
                    idempotency_key=f"EARLY_SETTLEMENT:{batch_id}"
                ).first()

                if audit and audit.payload.get("items"):
                    for snap in audit.payload["items"]:
                        it = InstallmentItem.objects.select_for_update().get(pk=snap["item_id"])
                        it.paid_principal = Decimal(snap["paid_principal"])
                        it.paid_interest = Decimal(snap["paid_interest"])
                        it.paid_amount = Decimal(snap["paid_amount"])
                        it.settled_principal = Decimal(snap["settled_principal"])
                        it.waived_interest = Decimal(snap["waived_interest"])
                        it.rebated_interest = Decimal(snap["rebated_interest"])
                        it.is_interest_recognized = snap["is_interest_recognized"]
                        it.cash_status = snap["cash_status"]
                        it.save()

                    # استعادة رصيد العميل المردود إن وجد
                    ref_amt = Decimal(audit.payload.get("customer_net_refund_amount", "0.00"))
                    if ref_amt > Decimal("0.00"):
                        cust = locked_sale.customer
                        if hasattr(cust, 'balance'):
                            cust.balance = getattr(cust, 'balance', Decimal('0.00')) + ref_amt
                            cust.save(update_fields=['balance'])
                        if hasattr(cust, 'prepaid_balance'):
                            cust.prepaid_balance = getattr(cust, 'prepaid_balance', Decimal('0.00')) - ref_amt
                            cust.save(update_fields=['prepaid_balance'])
                else:
                    batch_items = set()
                    for s in settlements:
                        if s.installment_item:
                            batch_items.add(s.installment_item)
                    for it in batch_items:
                        locked_it = InstallmentItem.objects.select_for_update().get(pk=it.pk)
                        locked_it.settled_principal = Decimal('0.00')
                        locked_it.waived_interest = Decimal('0.00')
                        locked_it.rebated_interest = Decimal('0.00')
                        locked_it.is_interest_recognized = False
                        if locked_it.remaining_balance > Decimal('0.00'):
                            locked_it.cash_status = InstallmentCashStatus.PENDING if locked_it.due_date >= today else InstallmentCashStatus.OVERDUE
                        locked_it.save()

                # إعادة ضبط حالة خطة التقسيط
                all_rem = sum(it.remaining_balance for it in plan.items.all())
                if all_rem > Decimal('0.00'):
                    plan.status = PlanStatus.ACTIVE
                else:
                    plan.status = PlanStatus.COMPLETED
                plan.save(update_fields=['status'])

            # 5. تحديث رصيد الفاتورة وحالة السداد
            locked_sale.update_payment_status()

            logger.info(
                f"↩️ تم بنجاح عكس الحزمة المركبة {batch_id} بالكامل للفاتورة {locked_sale.number} "
                f"(القيد العكسي #{reversal_entry.id if reversal_entry else 'None'})"
            )

            return {
                "status": "SUCCESS",
                "batch_id": batch_id,
                "reversal_entry": reversal_entry,
                "reversed_settlements_count": len(settlements),
                "reversed_payments_count": len(payments),
            }

    @classmethod
    def reverse_individual_settlement(
        cls,
        settlement: InstallmentSettlement,
        user=None,
        reason: str = ""
    ) -> Dict[str, Any]:
        """
        المسار (ب): عكس تسوية فردية مستقلة
        """
        if settlement.is_reversed or settlement.status == "REVERSED":
            raise ValidationError(_("هذه التسوية معكوسة بالفعل سابقاً."))

        if getattr(settlement, 'batch_id', None):
            raise ValidationError(_("لا يمكن عكس بند تسوية منفرد ينتمي إلى حزمة تسوية مركبة. يجب عكس الحزمة بالكامل عبر reverse_composite_settlement_batch."))

        if not reason or not reason.strip():
            reason = _("إلغاء وعكس التسوية الفردية")

        with transaction.atomic():
            locked_s = InstallmentSettlement.objects.select_for_update().get(pk=settlement.pk)
            sale = locked_s.sale
            locked_sale = Sale.objects.select_for_update().get(pk=sale.pk)
            installment_item = locked_s.installment_item

            # 1. عكس قيد اليومية المستقل إن وجد
            reversal_entry = None
            if locked_s.journal_entry and locked_s.journal_entry.status == "posted":
                reversal_entry = LedgerCoreService.reverse_entry(
                    entry_id=locked_s.journal_entry.id,
                    user=user,
                    reversal_reason=f"عكس تسوية فردية #{locked_s.id}: {reason}"
                )

            # 2. تحويل التسوية إلى REVERSED
            locked_s.status = "REVERSED"
            locked_s.is_reversed = True
            locked_s.reversed_by = user
            locked_s.reversed_at = timezone.now()
            locked_s.notes = f"{locked_s.notes or ''} [REVERSED: {reason}]".strip()
            locked_s.save(update_fields=['status', 'is_reversed', 'reversed_by', 'reversed_at', 'notes'])

            # 3. تعديل رصيد القسط المرتبط بها حصراً
            if installment_item:
                locked_it = InstallmentItem.objects.select_for_update().get(pk=installment_item.pk)
                stype = locked_s.settlement_type
                if stype in [
                    InstallmentSettlement.SettlementType.EARLY_SETTLEMENT_DISCOUNT,
                    InstallmentSettlement.SettlementType.CONTRA_SETTLEMENT,
                    InstallmentSettlement.SettlementType.BAD_DEBT_WRITE_OFF,
                ]:
                    locked_it.settled_principal = max(Decimal('0.00'), locked_it.settled_principal - locked_s.amount)
                    locked_it.paid_amount = max(Decimal('0.00'), locked_it.paid_amount - locked_s.amount)
                    if locked_it.total_remaining_balance > Decimal('0.00'):
                        locked_it.cash_status = InstallmentCashStatus.PENDING
                elif stype in [
                    InstallmentSettlement.SettlementType.INTEREST_WAIVER,
                    InstallmentSettlement.SettlementType.CURTAILMENT_INTEREST_WAIVER,
                ]:
                    locked_it.waived_interest = max(Decimal('0.00'), locked_it.waived_interest - locked_s.amount)
                    locked_it.is_interest_recognized = False
                elif stype == InstallmentSettlement.SettlementType.PREPAID_INTEREST_REBATE:
                    locked_it.rebated_interest = max(Decimal('0.00'), locked_it.rebated_interest - locked_s.amount)
                elif stype == InstallmentSettlement.SettlementType.PENALTY_WAIVER:
                    locked_it.penalty_amount += locked_s.amount

                locked_it.save()

            # 4. تحديث رصيد الفاتورة
            locked_sale.update_payment_status()

            logger.info(
                f"↩️ تم بنجاح عكس التسوية الفردية #{locked_s.id} للنوع {locked_s.settlement_type} "
                f"للفاتورة {locked_sale.number}"
            )

            return {
                "status": "SUCCESS",
                "settlement_id": locked_s.id,
                "reversal_entry": reversal_entry,
            }
