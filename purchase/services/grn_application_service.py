import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional
from django.db import transaction
from django.utils import timezone

from purchase.models.procurement_models import GoodsReceivedNote, GoodsReceivedNoteItem, PurchaseOrder
from purchase.models.grn_audit_log import GRNAuditLog
from supplier.models import Supplier
from product.models import Warehouse, Product
from financial.exceptions import FinancialCoreError
from core.services.sequence_service import SequenceService
from core.enums.document_types import DocumentType

from .grn_validation_service import GRNValidationService
from .grn_posting_service import GRNPostingService
from .grn_reversal_service import GRNReversalService

logger = logging.getLogger("purchase.grn_application_service")


class GRNApplicationService:
    """
    المنسق الرقيق بين الشاشات والخدمات المجهرية (Lightweight Application Orchestrator)
    إدارة آلة الحالات (State Machine) وتنسيق طلبات الإنشاء والاعتماد والترحيل والعكس
    """

    @classmethod
    def generate_grn_number(cls) -> str:
        try:
            return SequenceService.get_next_number(DocumentType.GRN) if hasattr(DocumentType, 'GRN') else f"GRN-{timezone.now().strftime('%Y%m%d%H%M%S')}"
        except Exception:
            return f"GRN-{timezone.now().strftime('%Y%m%d%H%M%S')}"

    @classmethod
    def create_grn(
        cls,
        po_id: Optional[int],
        warehouse_id: int,
        supplier_id: int,
        delivery_note_ref: str,
        items_data: List[Dict[str, Any]],
        user,
        is_direct_override: bool = False,
        auto_post: bool = False
    ) -> GoodsReceivedNote:
        """
        إنشاء إذن استلام جديد (مسودة أو ترحيل تلقائي)
        """
        # 1. التحقق الحاكم من قيود الاستلام الزائد والتفاوت
        GRNValidationService.validate_grn_creation(
            po_id=po_id,
            warehouse_id=warehouse_id,
            items_data=items_data,
            user=user,
            is_direct_override=is_direct_override
        )

        idempotency_key = GRNValidationService.calculate_idempotency_key(
            po_id=po_id,
            warehouse_id=warehouse_id,
            items_data=items_data
        )

        # التحقق من وجود إذن بنفس المفتاح المنطقي تم إنشاؤه مسبقاً
        existing_grn = GoodsReceivedNote.objects.filter(idempotency_key=idempotency_key).first()
        if existing_grn:
            logger.info(f"Existing GRN #{existing_grn.grn_number} returned via Idempotency Key match.")
            if auto_post and existing_grn.status != "POSTED":
                return GRNPostingService.post_grn(existing_grn.id, user=user)
            return existing_grn

        with transaction.atomic():
            supplier = Supplier.objects.get(pk=supplier_id)
            warehouse = Warehouse.objects.get(pk=warehouse_id)
            po_obj = PurchaseOrder.objects.filter(pk=po_id).first() if po_id else None

            grn_num = cls.generate_grn_number()

            grn = GoodsReceivedNote.objects.create(
                grn_number=grn_num,
                purchase_order=po_obj,
                supplier=supplier,
                warehouse=warehouse,
                supplier_delivery_note_ref=delivery_note_ref or "",
                status="DRAFT",
                idempotency_key=idempotency_key
            )

            for item in items_data:
                product = item.get("product")
                if not product and item.get("product_id"):
                    product = Product.objects.filter(pk=item["product_id"]).first()
                if not product:
                    continue

                po_item = item.get("po_item")
                if not po_item and item.get("po_item_id"):
                    from purchase.models.procurement_models import PurchaseOrderItem
                    po_item = PurchaseOrderItem.objects.filter(pk=item["po_item_id"]).first()

                received_qty = Decimal(str(item.get("received_qty", "1.0000")))
                if received_qty <= Decimal("0.0000"):
                    continue

                unit_price = Decimal(str(item.get("unit_price") or (po_item.unit_price if po_item else "0.00")))
                total_cost = (received_qty * unit_price).quantize(Decimal("0.01"))

                GoodsReceivedNoteItem.objects.create(
                    grn=grn,
                    po_item=po_item,
                    product=product,
                    received_qty=received_qty,
                    unit_price=unit_price,
                    total_cost=total_cost
                )

            GRNAuditLog.objects.create(
                grn=grn,
                old_status=None,
                new_status="DRAFT",
                action_by=user,
                reason="Creation",
                comment=f"Created GRN #{grn.grn_number} in DRAFT status."
            )

            logger.info(f"GRN #{grn.grn_number} created as DRAFT by {user.username}.")

        if auto_post:
            return GRNPostingService.post_grn(grn.id, user=user)

        return grn

    @classmethod
    def submit_grn(cls, grn_id: int, user, reason: str = "") -> GoodsReceivedNote:
        """تقديم الإذن للمراجعة (DRAFT -> SUBMITTED)"""
        with transaction.atomic():
            grn = GoodsReceivedNote.objects.select_for_update().get(pk=grn_id)
            if grn.status != "DRAFT":
                raise FinancialCoreError(f"لا يمكن تقديم إذن استلام بحالة {grn.get_status_display()}.")

            old_status = grn.status
            grn.status = "SUBMITTED"
            grn.save(update_fields=["status"])

            GRNAuditLog.objects.create(
                grn=grn,
                old_status=old_status,
                new_status="SUBMITTED",
                action_by=user,
                reason=reason or "Submission",
                comment="Submitted GRN for review."
            )
            return grn

    @classmethod
    def approve_grn(cls, grn_id: int, user, reason: str = "") -> GoodsReceivedNote:
        """اعتماد الإذن (SUBMITTED -> APPROVED)"""
        with transaction.atomic():
            grn = GoodsReceivedNote.objects.select_for_update().get(pk=grn_id)
            if grn.status != "SUBMITTED":
                raise FinancialCoreError(f"لا يمكن اعتماد إذن استلام بحالة {grn.get_status_display()}. يلزم التقديم أولاً.")

            old_status = grn.status
            grn.status = "APPROVED"
            grn.save(update_fields=["status"])

            GRNAuditLog.objects.create(
                grn=grn,
                old_status=old_status,
                new_status="APPROVED",
                action_by=user,
                reason=reason or "Approval",
                comment="Approved GRN."
            )
            return grn

    @classmethod
    def post_grn(cls, grn_id: int, user, reason: str = "") -> GoodsReceivedNote:
        """تفويض الترحيل النهائي لـ GRNPostingService"""
        return GRNPostingService.post_grn(grn_id=grn_id, user=user, reason=reason)

    @classmethod
    def reverse_grn(cls, grn_id: int, user, reason: str) -> GoodsReceivedNote:
        """تفويض العكس والقيد المعاكس لـ GRNReversalService"""
        return GRNReversalService.reverse_grn(grn_id=grn_id, user=user, reason=reason)
