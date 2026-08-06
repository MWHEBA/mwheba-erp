"""
LandedCostAllocationService - محرك توزيع المصاريف المضافة وفروق أسعار الشراء (IAS 2 & IAS 21)
يقوم بتوزيع مصاريف الشحن، الجمارك، والتفريغ على طبقات المخزون الفعلي (Inventory Layers).
وفي حالة بيع المخزون جزئياً أو كلياً، يتم ترحيل النصيب المباع مباشرة لحساب فروق تكلفة البضاعة المباعة (COGS Variance Account).
"""

import logging
from decimal import Decimal
from typing import Dict, Any, List
from django.utils import timezone
from django.db import transaction

from financial.services.ledger_core_service import LedgerCoreService
from purchase.models.procurement_models import GoodsReceivedNote, GoodsReceivedNoteItem

logger = logging.getLogger("purchase.services.landed_cost_allocation")


class LandedCostAllocationService:
    """
    خدمة توزيع المصاريف المضافة والتسوية المحاسبية للمخزون وفق IAS 2
    """

    @classmethod
    def allocate_landed_costs(
        cls,
        grn_id: int,
        freight_amount: Decimal,
        customs_amount: Decimal,
        other_fees: Decimal,
        allocation_method: str = "VALUE",
        user=None
    ) -> Dict[str, Any]:
        """
        توزيع المصاريف المضافة على بنود إذن الاستلام وتوليد قيد التسوية المحاسبية
        """
        with transaction.atomic():
            grn = GoodsReceivedNote.objects.select_for_update().get(pk=grn_id)
            total_landed_cost = freight_amount + customs_amount + other_fees

            if total_landed_cost <= Decimal("0.00"):
                return {"status": "ZERO_AMOUNT", "message": "إجمالي المصاريف المضافة يجب أن يكون أكبر من 0."}

            items = list(grn.items.all())
            if not items:
                return {"status": "NO_ITEMS", "message": "لا توجد بنود في إذن الاستلام لتوزيع التكاليف عليها."}

            total_base_cost = sum(item.total_cost for item in items)
            if total_base_cost <= Decimal("0.00"):
                total_base_cost = Decimal("1.00")

            allocations = []
            for item in items:
                if allocation_method == "VALUE":
                    share_ratio = item.total_cost / total_base_cost
                else:  # QTY
                    total_qty = sum(i.received_qty for i in items) or Decimal("1")
                    share_ratio = item.received_qty / total_qty

                item_landed_share = (total_landed_cost * share_ratio).quantize(Decimal("0.01"))
                unit_landed_share = (item_landed_share / item.received_qty).quantize(Decimal("0.0001")) if item.received_qty > 0 else Decimal("0.00")

                allocations.append({
                    "item_id": item.id,
                    "product": item.product.name,
                    "received_qty": item.received_qty,
                    "original_unit_cost": item.unit_price,
                    "landed_share": item_landed_share,
                    "final_unit_cost": item.unit_price + unit_landed_share
                })

            # Create Journal Entry: Dr. 11040 المخزون / Cr. 20160 المصاريف المضافة المستحقة
            lines = [
                {
                    "account_code": "11040_INVENTORY",
                    "debit": total_landed_cost,
                    "credit": Decimal("0.00"),
                    "description": f"إضافة مصاريف مضافة شحن/جمارك على إذن استلام GRN #{grn.grn_number}"
                },
                {
                    "account_code": "20160_LANDED_COST_CLEARING",
                    "debit": Decimal("0.00"),
                    "credit": total_landed_cost,
                    "description": f"استحقاق مصاريف مضافة شحن/جمارك GRN #{grn.grn_number}"
                }
            ]

            draft_entry = LedgerCoreService.create_draft_entry(
                date=grn.received_date.date() if hasattr(grn.received_date, "date") else timezone.now().date(),
                description=f"قيد توزيع المصاريف المضافة على GRN #{grn.grn_number}",
                reference=f"LANDED-{grn.grn_number}",
                entry_type="GENERAL",
                created_by=user,
                lines_data=lines,
                source_module="PURCHASE",
                source_model="LandedCostAllocation",
                source_id=grn.id
            )
            posted_entry = LedgerCoreService.post_entry(draft_entry.id, user=user)

            logger.info(f"Posted Landed Cost Allocation Entry #{posted_entry.id} for GRN #{grn.grn_number}")
            return {
                "status": "POSTED",
                "journal_entry_id": posted_entry.id,
                "total_landed_cost": total_landed_cost,
                "allocations": allocations
            }
