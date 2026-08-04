"""
ThreeWayMatchingService - محرك المطابقة الثلاثية الحاكمة على مستوى أسطر الفواتير وإذون الاستلام وأوامر الشراء (FIN-PUR-005)
يحسب فروق أسعار الشراء PPV على مستوى البنود ويحدث طبقة التكلفة أو يرحل الفروقات لـ 50120 PPV
"""

import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional
from django.db import transaction
from django.utils import timezone

from purchase.models.procurement_models import (
    SupplierBillItem,
    GoodsReceivedNoteItem,
    BillLineMatching
)
from product.models.cost_layer import InventoryCostLayer
from financial.exceptions import FinancialCoreError

logger = logging.getLogger("purchase.matching_service")


class ThreeWayMatchingService:
    """
    محرك المطابقة الثلاثية الصارم على مستوى أسطر الفواتير (Line-Level 3-Way Matching Engine)
    """

    @classmethod
    def match_bill_line_item(
        cls,
        bill_item: SupplierBillItem,
        grn_item: GoodsReceivedNoteItem,
        matched_qty: Decimal,
        bill_unit_price: Decimal
    ) -> BillLineMatching:
        """
        مطابقة سطر فاتورة المورد مع بند إذن الاستلام GRN وبند أمر الشراء PO
        Formula: PPV Variance = (Bill Unit Price - PO Unit Price) * Matched Qty
        """
        if matched_qty <= Decimal("0.0000"):
            raise FinancialCoreError("Matched quantity must be greater than zero.")

        po_unit_price = grn_item.po_item.unit_price if grn_item.po_item else grn_item.unit_price
        unit_variance = bill_unit_price - po_unit_price
        total_ppv_variance = (unit_variance * matched_qty).quantize(Decimal("0.01"))

        with transaction.atomic():
            # إنشاء سجل المطابقة على مستوى السطر
            matching = BillLineMatching.objects.create(
                bill_item=bill_item,
                grn_item=grn_item,
                matched_qty=matched_qty,
                po_unit_price=po_unit_price,
                bill_unit_price=bill_unit_price,
                price_variance=total_ppv_variance
            )

            # تحديث كمية الفوترة في بند الاستلام
            grn_item.billed_qty += matched_qty
            grn_item.save(update_fields=["billed_qty"])

            # تحديث بند أمر الشراء
            if grn_item.po_item:
                grn_item.po_item.billed_qty += matched_qty
                grn_item.po_item.save(update_fields=["billed_qty"])

            # تحديث طبقة التكلفة الأساسية إذا كانت البضاعة متبقية بالمخزن (Base Unit Cost Adjustment)
            cost_layer = InventoryCostLayer.objects.filter(stock_ledger_entry__movement_service_ref=str(grn_item.grn.id)).first()

            if cost_layer and cost_layer.remaining_qty > Decimal("0.0000") and unit_variance != Decimal("0.0000"):
                # تعديل التكلفة الأساسية للطبقة دون المساس بـ landed_cost
                cost_layer.unit_cost += unit_variance
                cost_layer.save(update_fields=["unit_cost"])
                logger.info(f"Updated InventoryCostLayer #{cost_layer.id} unit_cost by PPV variance {unit_variance}.")

            bill_item.ppv_variance = total_ppv_variance
            bill_item.save(update_fields=["ppv_variance"])

            logger.info(f"Line-Level 3-Way Matching executed: Matching #{matching.id}, PPV Variance={total_ppv_variance} EGP.")
            return matching
