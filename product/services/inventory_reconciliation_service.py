"""
InventoryReconciliationService - خدمة مطابقة أستاذ المخزون الفرعي مع أستاذ الحسابات العام (11040 Inventory Control Account)
تضمن دقة المطابقة المحاسبية وعدم وجود فروقات بين تقييم المخزون الفعلي والقيد المالي
"""

import logging
from decimal import Decimal
from typing import Dict, Any, Optional
from django.db.models import Sum, F, ExpressionWrapper, DecimalField

from product.models.cost_layer import InventoryCostLayer
from financial.services.ledger_query_service import LedgerQueryService

logger = logging.getLogger("product.inventory_reconciliation_service")


class InventoryReconciliationService:
    """
    خدمة مطابقة تقييم أصل المخزون المالي الفرعي مع دفتر الأستاذ العام (Inventory Asset Reconciliation)
    """

    @classmethod
    def reconcile_inventory_control_account(
        cls,
        account_code: str = "11040_INV",
        as_of_date: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        مطابقة مجموع تقييم طبقات المخزون النشطة مع رصيد حساب أصل المخزون المالي 11040
        Formula: Subledger Valuation == GL Account 11040 Balance
        """
        # 1. حساب تقييم طبقات المخزون النشطة الفرعية
        active_layers = InventoryCostLayer.objects.filter(status="OPEN")
        if as_of_date:
            active_layers = active_layers.filter(receipt_date__lte=as_of_date)

        annotated_layers = active_layers.annotate(
            layer_valuation=ExpressionWrapper(
                F("remaining_qty") * F("unit_cost"),
                output_field=DecimalField(max_digits=15, decimal_places=2)
            )
        )

        subledger_valuation = annotated_layers.aggregate(total=Sum("layer_valuation"))["total"] or Decimal("0.00")
        subledger_valuation = subledger_valuation.quantize(Decimal("0.01"))

        # 2. الاستعلام عن رصيد الحساب المالي لـ 11040 في دفتر الأستاذ العام
        gl_balance = Decimal("0.00")
        try:
            gl_balance_obj = LedgerQueryService.get_account_balance(
                account_code=account_code,
                as_of_date=as_of_date
            )
            gl_balance = Decimal(str(gl_balance_obj.get("balance", "0.00"))).quantize(Decimal("0.01"))
        except Exception as e:
            logger.warning(f"Could not fetch GL balance for account {account_code}: {str(e)}")

        discrepancy = (gl_balance - subledger_valuation).quantize(Decimal("0.01"))
        is_reconciled = abs(discrepancy) == Decimal("0.00")

        logger.info(
            f"Inventory Control Account Reconciliation ({account_code}): "
            f"Subledger={subledger_valuation}, GL={gl_balance}, Discrepancy={discrepancy}, Reconciled={is_reconciled}"
        )

        return {
            "account_code": account_code,
            "subledger_valuation": subledger_valuation,
            "gl_inventory_balance": gl_balance,
            "discrepancy": discrepancy,
            "is_reconciled": is_reconciled
        }
