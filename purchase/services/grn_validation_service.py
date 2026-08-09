import hashlib
import json
import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional
from django.conf import settings
from financial.exceptions import FinancialCoreError
from purchase.models.procurement_models import PurchaseOrder, PurchaseOrderItem, GoodsReceivedNote

logger = logging.getLogger("purchase.grn_validation_service")


class GRNValidationService:
    """
    خدمة التحقق والحوكمة المبدئية لأذون الاستلام (GRN Validation Service)
    """

    @classmethod
    def calculate_idempotency_key(
        cls,
        po_id: Optional[int],
        warehouse_id: int,
        items_data: List[Dict[str, Any]]
    ) -> str:
        """
        توليد مفتاح حاسم لمنع التكرار المنطقي (Deterministic HASH Idempotency Key)
        """
        lines_normalized = []
        for item in items_data:
            lines_normalized.append({
                "product_id": int(item.get("product_id") or (item.get("product").id if item.get("product") else 0)),
                "qty": str(Decimal(str(item.get("received_qty", "0"))).quantize(Decimal("0.0001")))
            })
        lines_normalized.sort(key=lambda x: x["product_id"])

        payload = {
            "po_id": po_id or 0,
            "warehouse_id": warehouse_id,
            "lines": lines_normalized
        }
        raw_str = json.dumps(payload, sort_keys=True)
        md5_hash = hashlib.md5(raw_str.encode("utf-8")).hexdigest()
        return f"POST_GRN_{po_id or 0}_{warehouse_id}_{md5_hash}"

    @classmethod
    def validate_grn_creation(
        cls,
        po_id: Optional[int],
        warehouse_id: int,
        items_data: List[Dict[str, Any]],
        user,
        is_direct_override: bool = False
    ) -> None:
        """
        التحقق الصارم من قيود الاستلام الزائد وفترات التفاوت
        """
        if not items_data:
            raise FinancialCoreError("لا يمكن إنشاء إذن استلام بدون بنود.")

        if not po_id and not is_direct_override:
            raise FinancialCoreError("يلزم اختيار أمر شراء معتمد لإصدار إذن استلام (أو تطبيق استثناء الاستلام المباشر).")

        if po_id:
            try:
                po = PurchaseOrder.objects.get(pk=po_id)
            except PurchaseOrder.DoesNotExist:
                raise FinancialCoreError("أمر الشراء المحدد غير موجود.")

            if po.status not in ["APPROVED", "PARTIALLY_RECEIVED"]:
                raise FinancialCoreError(f"لا يمكن إصدار إذن استلام لأمر شراء بحالة {po.get_status_display()}.")

            # جلب نسبة التفاوت المسموحة من الإعدادات (Over-Receipt Tolerance %)
            tolerance_pct = Decimal(str(getattr(settings, "GRN_OVER_RECEIPT_PERCENTAGE", "0")))

            for item in items_data:
                po_item_id = item.get("po_item_id")
                received_qty = Decimal(str(item.get("received_qty", "0")))
                if received_qty <= Decimal("0.0000"):
                    continue

                if po_item_id:
                    try:
                        po_item = PurchaseOrderItem.objects.get(pk=po_item_id, purchase_order=po)
                    except PurchaseOrderItem.DoesNotExist:
                        raise FinancialCoreError(f"بند أمر الشراء #{po_item_id} غير مرتبط بأمر الشراء.")

                    max_allowed = (po_item.ordered_qty * (Decimal("1.00") + (tolerance_pct / Decimal("100")))).quantize(Decimal("0.0001"))
                    current_total = po_item.received_qty + received_qty

                    if current_total > max_allowed:
                        raise FinancialCoreError(
                            f"الكمية المستلمة للمنتج ({po_item.product.name}) تتجاوز الكمية المطلوبة بالفيصل المسموح ({max_allowed}). "
                            f"المستلم سابقاً: {po_item.received_qty}، المطلوبة: {po_item.ordered_qty}."
                        )
