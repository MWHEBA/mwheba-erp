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

    @classmethod
    def validate_grn_for_posting(cls, grn: GoodsReceivedNote) -> None:
        """
        التحقق الصارم من جاهزية وصحة إذن الاستلام للترحيل المخزني والمالي (GRN Posting Validation)
        """
        if not grn:
            raise FinancialCoreError("إذن الاستلام غير موجود.")

        if grn.status in ["POSTED", "REVERSED"]:
            raise FinancialCoreError(f"لا يمكن ترحيل إذن استلام بحالة {grn.get_status_display()}.")

        items = grn.items.all()
        if not items.exists():
            raise FinancialCoreError("لا يمكن ترحيل إذن استلام لا يحتوي على بنود.")

        if not grn.warehouse:
            raise FinancialCoreError("يلزم تحديد المخزن المستهدف لإتمام الترحيل المخزني.")

        has_valid_qty = False
        tolerance_pct = Decimal(str(getattr(settings, "GRN_OVER_RECEIPT_PERCENTAGE", "0")))

        for item in items:
            if not item.product:
                raise FinancialCoreError("أحد بنود إذن الاستلام لا يحتوي على منتج محدد.")

            received_qty = Decimal(str(item.received_qty or "0"))
            if received_qty < Decimal("0.0000"):
                raise FinancialCoreError(f"لا يمكن أن تكون الكمية المستلمة سالبة للمنتج ({item.product.name}).")
            elif received_qty > Decimal("0.0000"):
                has_valid_qty = True

            unit_price = Decimal(str(item.unit_price or "0"))
            if unit_price < Decimal("0.00"):
                raise FinancialCoreError(f"سعر الوحدة للمنتج ({item.product.name}) لا يمكن أن يكون سالباً.")

            if item.po_item and received_qty > Decimal("0.0000"):
                max_allowed = (item.po_item.ordered_qty * (Decimal("1.00") + (tolerance_pct / Decimal("100")))).quantize(Decimal("0.0001"))
                current_total = item.po_item.received_qty + received_qty
                if current_total > max_allowed:
                    raise FinancialCoreError(
                        f"الكمية المستلمة للمنتج ({item.product.name}) تتجاوز الكمية المطلوبة بأمر الشراء بالفيصل المسموح ({max_allowed}). "
                        f"المستلم سابقاً: {item.po_item.received_qty}، المطلوبة: {item.po_item.ordered_qty}."
                    )

        if not has_valid_qty:
            raise FinancialCoreError("لا توجد كميات مستلمة أكبر من الصفر في بنود إذن الاستلام.")

