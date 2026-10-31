# -*- coding: utf-8 -*-
"""
FIN-CONTRACT-CURTAIL: Contract Curtailment Protocol
خدمة تقليص العقود الصناعية وحماية مديونية الدفعات المسلمة وعكس الفوائد المؤجلة دون ازدواج ضريبي
"""
import logging
import uuid
from decimal import Decimal
from typing import Optional, Dict, Any, List

from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from financial.models import ChartOfAccounts
from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames
from financial.services.subledger_account_service import SubledgerAccountService
from governance.services.accounting_gateway import AccountingGateway, JournalEntryLineData
from sale.models.installments import (
    InstallmentPlan,
    InstallmentItem,
    InstallmentCashStatus,
    InstallmentSettlement,
    PlanStatus,
)
from sale.models import Sale

logger = logging.getLogger(__name__)


class ContractCurtailmentService:
    """
    خدمة تقليص العقود المجدولة:
    - حماية الدفعات والباتشات المسلمة مسبقاً بإذن تسليم معتمد
    - إلغاء الأقساط المستقبلية غير المسلمة (WAIVED)
    - عكس الفوائد المؤجلة الخاصة بها حصراً من 21400 ضد العملاء
    - تسجيل تسوية دائمة CURTAILMENT_INTEREST_WAIVER
    - حظر تسجيل أصل البضاعة في amount_settled (قصرها على إشعار الدائن الضريبي SalesReturn)
    - تحويل حالة الخطة إلى CURTAILED
    """

    @classmethod
    def get_or_create_unearned_interest_account(cls):
        """حساب فوائد تقسيط غير محققة (21400)"""
        from sale.services.early_settlement_service import EarlySettlementService
        return EarlySettlementService.get_or_create_unearned_interest_account()

    @classmethod
    def curtail_installment_plan(
        cls,
        plan: InstallmentPlan,
        cancelled_items: List[InstallmentItem],
        user=None,
        reason: str = "",
        credit_note=None
    ) -> Dict[str, Any]:
        """
        تنفيذ بروتوكول تقليص العقد
        """
        if not cancelled_items:
            raise ValidationError(_("يجب تحديد الأقساط المستقبلية المراد إلغاؤها بالتقليص."))

        if not credit_note:
            raise ValidationError(
                _("تقليص العقد يتطلب إشعار دائن تجاري معتمد (Commercial Credit Note) لإلغاء أصل البضاعة غير المسلمة.")
            )

        if hasattr(credit_note, 'status') and credit_note.status not in ['POSTED', 'APPROVED']:
            raise ValidationError(
                _("إشعار الدائن التجاري يجب أن يكون معتمداً أو مرحلاً بالدفاتر.")
            )

        if plan.status in [PlanStatus.COMPLETED, PlanStatus.CANCELLED]:
            raise ValidationError(_(f"لا يمكن تقليص خطة في حالة: {plan.get_status_display()}."))

        if not reason or not reason.strip():
            reason = _("تقليص رضائي للكميات المستقبلية غير المصنعة بالعقد")

        with transaction.atomic():
            locked_plan = InstallmentPlan.objects.select_for_update().get(pk=plan.pk)
            sale = locked_plan.sale
            locked_sale = Sale.objects.select_for_update().get(pk=sale.pk)
            customer = locked_sale.customer

            # 1. فحص حماية الدفعات المسلمة
            for it in cancelled_items:
                locked_it = InstallmentItem.objects.select_for_update().get(pk=it.pk)
                if locked_it.plan_id != locked_plan.id:
                    raise ValidationError(_("أحد الأقساط المحددة لا ينتمي لخطة التقسيط."))

                # إذا سُلمت بضاعته مسبقاً بإذن تسليم معتمد
                if locked_it.linked_delivery_note and getattr(locked_it.linked_delivery_note, 'status', '') in ['DELIVERED', 'confirmed', 'posted']:
                    raise ValidationError(
                        _(f"القسط رقم {locked_it.installment_number} مرتبط بباتش بضاعة تم تسليمها بالفعل للعميل "
                          f"بإذن تسليم #{locked_it.linked_delivery_note.delivery_number}؛ ولا يجوز إلغاء مديونيته.")
                    )

                if locked_it.paid_amount > Decimal('0.00'):
                    raise ValidationError(
                        _(f"القسط رقم {locked_it.installment_number} مسدد جزئياً أو كلياً؛ ولا يجوز إلغاؤه.")
                    )

            # 2. حساب الفوائد المؤجلة المستقبلية غير المكتسبة للأقساط الملغاة
            total_unearned_interest = sum(it.unearned_interest_balance for it in cancelled_items)

            entry = None
            settlement_record = None
            curtail_ref = f"CURTAIL-{locked_plan.id}-{uuid.uuid4().hex[:8]}"

            # 3. توليد قيد عكس الفوائد المؤجلة من 21400 ضد حساب العميل
            if total_unearned_interest > Decimal('0.00'):
                unearned_acc = cls.get_or_create_unearned_interest_account()
                cust_acc = None
                try:
                    cust_acc = SubledgerAccountService.get_or_create_customer_account(customer, user=user)
                except Exception:
                    pass
                if not cust_acc:
                    cust_acc = AccountRoleRegistry.get_account(AccountRoleNames.CUSTOMER_CONTROL)

                rate = Decimal(str(locked_sale.exchange_rate or "1.000000"))
                curr_code = locked_sale.currency.code if locked_sale.currency else "EGP"
                func_amount = (total_unearned_interest * rate).quantize(Decimal("0.01"))

                gateway_lines = [
                    JournalEntryLineData(
                        account_code=unearned_acc.code,
                        debit=func_amount,
                        credit=Decimal("0.00"),
                        description=f"إلغاء فوائد تقسيط مستقبلية لتقليص العقد - خطة #{locked_plan.id} فاتورة {locked_sale.number}",
                        currency=curr_code,
                        exchange_rate=rate,
                    ),
                    JournalEntryLineData(
                        account_code=cust_acc.code,
                        debit=Decimal("0.00"),
                        credit=func_amount,
                        description=f"تخفيض مديونية العميل بفوائد تقليص العقد - فاتورة {locked_sale.number}",
                        currency=curr_code,
                        exchange_rate=rate,
                    ),
                ]

                gateway = AccountingGateway()
                entry = gateway.create_journal_entry(
                    source_module="sale",
                    source_model="InstallmentPlan",
                    source_id=locked_plan.id,
                    lines=gateway_lines,
                    idempotency_key=f"JE:CURTAIL:{curtail_ref}",
                    user=user,
                    entry_type="curtailment_interest_waiver",
                    description=f"إلغاء فوائد تقليص العقد لـ {len(cancelled_items)} قسط مستقبلي - فاتورة {locked_sale.number}",
                    reference=curtail_ref,
                    date=timezone.localdate(),
                )

                # تسجيل التسوية التعاقدية الدائمة
                settlement_record = InstallmentSettlement.objects.create(
                    sale=locked_sale,
                    batch_id=curtail_ref,
                    settlement_type=InstallmentSettlement.SettlementType.CURTAILMENT_INTEREST_WAIVER,
                    amount=total_unearned_interest,
                    journal_entry=entry,
                    status="POSTED",
                    affects_invoice_due=True,
                    notes=f"إلغاء فوائد مؤجلة لتقليص العقد ({reason})",
                    created_by=user,
                )

            # 4. تحويل الأقساط الملغاة إلى WAIVED
            for it in cancelled_items:
                locked_it = InstallmentItem.objects.select_for_update().get(pk=it.pk)
                locked_it.waived_interest += locked_it.unearned_interest_balance
                locked_it.cash_status = InstallmentCashStatus.WAIVED
                locked_it.is_interest_recognized = False
                locked_it.save()

            # 5. تحويل حالة الخطة إلى CURTAILED
            locked_plan.status = PlanStatus.CURTAILED
            locked_plan.notes = f"{locked_plan.notes or ''} [CURTAILED: {reason}]".strip()
            locked_plan.save(update_fields=['status', 'notes'])

            # 6. تحديث رصيد الفاتورة
            locked_sale.update_payment_status()

            logger.info(
                f"✅ تم تنفيذ تقليص العقد بنجاح للخطة #{locked_plan.id} وإلغاء {len(cancelled_items)} قسط "
                f"وعكس فوائد مؤجلة بمبلغ {total_unearned_interest}"
            )

            return {
                "status": "SUCCESS",
                "plan": locked_plan,
                "cancelled_items_count": len(cancelled_items),
                "unearned_interest_waived": total_unearned_interest,
                "journal_entry": entry,
                "settlement": settlement_record,
                "curtailment_reference": curtail_ref,
            }
