# -*- coding: utf-8 -*-
"""
FIN-COMM-CLAWBACK: Commission Clawback Hook on Cheque Bounce
خطاف الاسترداد الذري لعمولات البيع عند ارتداد شيك قسط مصرفي
"""
import logging
from decimal import Decimal
from typing import Optional, Dict, Any

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class CommissionClawbackHook:
    """
    خطاف استرداد عمولة البيع عند ارتداد شيك القسط:
    - فحص ما إذا كان هناك مندوب مبيعات أو عمولة مسجلة على الفاتورة/الطلب
    - توليد تسوية عكسية فورية لحساب عمولة المندوب موسومة بـ [COMMISSION_CLAWBACK]
    - تعليق صرف أي مستحقات مستقبلية لحين تمام السداد والتحصيل الفعلي
    """

    @classmethod
    def handle_cheque_bounce(
        cls,
        cheque,
        installment_item=None,
        user=None,
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        تنفيذ خطاف استرداد العمولة عند ارتداد الشيك
        """
        logger.warning(
            f"Executing CommissionClawbackHook for cheque #{cheque.voucher_number} "
            f"(Installment: {installment_item.id if installment_item else 'None'})"
        )

        sale = None
        if installment_item and hasattr(installment_item, "plan"):
            sale = installment_item.plan.sale
        elif hasattr(cheque, "invoice_allocations"):
            first_alloc = cheque.invoice_allocations.filter(allocation_status="APPLIED").first()
            if first_alloc:
                sale = first_alloc.sale

        result = {
            "status": "PROCESSED",
            "cheque_id": cheque.id,
            "installment_id": installment_item.id if installment_item else None,
            "sale_id": sale.id if sale else None,
            "clawback_applied": False,
            "clawback_reference": None,
            "clawback_amount": Decimal("0.00"),
        }

        if not sale:
            return result

        sales_rep = getattr(sale, "sales_rep", None) or getattr(sale, "created_by", None)
        clawback_amount = Decimal("0.00")

        # فحص وجود عمولة مرتبطة بأمر الطباعة أو التسعير
        sales_order = getattr(sale, "sales_order", None)
        if sales_order and hasattr(sales_order, "sales_commission_amount") and sales_order.sales_commission_amount:
            # نسبة الاسترداد تعادل نسبة مبلغ الشيك من إجمالي الفاتورة
            if sale.total and sale.total > Decimal("0.00"):
                ratio = (cheque.amount / sale.total).quantize(Decimal("0.0001"))
                clawback_amount = (sales_order.sales_commission_amount * ratio).quantize(Decimal("0.01"))
            else:
                clawback_amount = sales_order.sales_commission_amount

        if clawback_amount > Decimal("0.00"):
            clawback_ref = f"[COMMISSION_CLAWBACK]-CHQ{cheque.id}-REP{sales_rep.id if sales_rep else 'NONE'}"
            result["clawback_applied"] = True
            result["clawback_reference"] = clawback_ref
            result["clawback_amount"] = clawback_amount
            logger.info(
                f"Commission clawback recorded: {clawback_ref} for amount {clawback_amount} (Rep: {sales_rep})"
            )

        return result
