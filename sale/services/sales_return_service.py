import uuid
import json
import hashlib
import logging
from decimal import Decimal
from typing import List, Dict, Any, Optional
from django.db import transaction, models
from django.utils import timezone

from sale.models import (
    ReturnAuthorization,
    SalesReturnHeader,
    SalesReturnItem,
    SalesReturnInspection,
    ReturnCostTrace,
    SalesReturnAudit,
)
from sale.models.sales_models import SalesOrder, DeliveryNote, DeliveryNoteItem, SalesInvoice
from sale.services.return_decision import (
    ReturnInspectionDecision,
    InventoryMovementCommand,
    ReturnAccountingCommand,
)
from product.models import Warehouse, Stock
from governance.services.movement_service import MovementService
from governance.services.accounting_gateway import create_return_cogs_reversal_entry
from financial.exceptions import FinancialCoreError

logger = logging.getLogger("sale.services.sales_return_service")


class SalesReturnService:
    """
    FIN-SAL-002 v2.0: Sales Return Inspection & FIFO Cost Traceability Engine Service (Locked Master Final)
    محرك فحص جودة وإرجاع المبيعات وتتبع التكلفة التاريخية FIFO مع العكس المحاسبي الحاكم
    """

    @classmethod
    def generate_canonical_return_hash(
        cls,
        correlation_id: str,
        processed_event_id: str,
        return_number: str,
        total_restored_value: Decimal,
        timestamp: str
    ) -> str:
        """
        إنشاء التوقيع المشفر Canonical JSON SHA256 لسجل تدقيق وإثبات مرتجعات المبيعات
        """
        payload = {
            "correlation_id": str(correlation_id),
            "processed_event_id": str(processed_event_id),
            "return_number": str(return_number),
            "timestamp": str(timestamp),
            "total_restored_value": str(total_restored_value)
        }
        canonical_json = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    @classmethod
    def create_return_authorization(
        cls,
        customer_id: int,
        reason_category: str = "CUSTOMER_COMPLAINT",
        notes: str = "",
        user=None
    ) -> ReturnAuthorization:
        """
        إنشاء وتأكيد تصريح وإذن الإرجاع المحوكم
        """
        auth_num = f"RA-{uuid.uuid4().hex[:8].upper()}"
        auth = ReturnAuthorization.objects.create(
            authorization_number=auth_num,
            customer_id=customer_id,
            reason_category=reason_category,
            notes=notes,
            status="APPROVED",
            approved_by=user,
            approved_at=timezone.now()
        )
        logger.info(f"ReturnAuthorization #{auth.authorization_number} created for Customer ID {customer_id}.")
        return auth

    @classmethod
    def create_sales_return(
        cls,
        authorization_id: int,
        delivery_note_id: int,
        warehouse_id: int,
        items_data: List[Dict[str, Any]],
        user=None
    ) -> SalesReturnHeader:
        """
        إنشاء مستند طلب إرجاع المبيعات مرتبطاً بسطور إذن التسليم الأصلي
        """
        with transaction.atomic():
            auth = ReturnAuthorization.objects.get(pk=authorization_id, status="APPROVED")
            dn = DeliveryNote.objects.select_related("sales_order").get(pk=delivery_note_id)

            ret_num = f"RET-{uuid.uuid4().hex[:8].upper()}"
            inv = SalesInvoice.objects.filter(delivery_note=dn).first()
            ret_header = SalesReturnHeader.objects.create(
                return_number=ret_num,
                authorization=auth,
                customer=auth.customer,
                sales_order=dn.sales_order,
                delivery_note=dn,
                sales_invoice=inv,
                warehouse_id=warehouse_id,
                status="SUBMITTED",
                created_by=user
            )

            for item_info in items_data:
                dn_item_id = item_info["delivery_item_id"]
                req_qty = Decimal(str(item_info["requested_qty"]))

                dn_item = DeliveryNoteItem.objects.get(pk=dn_item_id)
                if req_qty > dn_item.delivered_qty:
                    raise FinancialCoreError(f"Return Quantity Error: Requested return ({req_qty}) exceeds delivered quantity ({dn_item.delivered_qty}).")

                prod = dn_item.so_item.product
                unit_cost = dn_item.unit_cost if hasattr(dn_item, 'unit_cost') and dn_item.unit_cost > Decimal("0.00") else prod.cost_price

                SalesReturnItem.objects.create(
                    return_header=ret_header,
                    delivery_item=dn_item,
                    product=prod,
                    requested_qty=req_qty,
                    approved_qty=req_qty,
                    unit_cost_restored=unit_cost
                )

            logger.info(f"SalesReturnHeader #{ret_header.return_number} created with {len(items_data)} items.")
            return ret_header

    @classmethod
    def inspect_sales_return(
        cls,
        return_header_id: int,
        inspection_items_data: List[Dict[str, Any]],
        user=None
    ) -> List[SalesReturnInspection]:
        """
        تسجيل نواتج الفحص والتفتيش الفني لقطع المرتجع (صالح GOOD / تالف DAMAGED / مكهن SCRAP)
        """
        with transaction.atomic():
            ret_header = SalesReturnHeader.objects.select_for_update().get(pk=return_header_id)
            ret_header.status = "INSPECTED"
            ret_header.save()

            inspections = []
            for insp_data in inspection_items_data:
                ret_item_id = insp_data["return_item_id"]
                good_q = Decimal(str(insp_data.get("good_qty", "0.0000")))
                damaged_q = Decimal(str(insp_data.get("damaged_qty", "0.0000")))
                scrap_q = Decimal(str(insp_data.get("scrap_qty", "0.0000")))

                ret_item = SalesReturnItem.objects.select_for_update().get(pk=ret_item_id)

                if good_q + damaged_q + scrap_q > ret_item.requested_qty:
                    raise FinancialCoreError(f"Inspection Quantity Error: Sum of inspected quantities exceeds requested ({ret_item.requested_qty}).")

                result_type = "GOOD" if good_q > Decimal("0.00") else ("DAMAGED" if damaged_q > Decimal("0.00") else "SCRAP_REJECTED")

                insp = SalesReturnInspection.objects.create(
                    return_item=ret_item,
                    inspection_result=result_type,
                    good_qty=good_q,
                    damaged_qty=damaged_q,
                    scrap_qty=scrap_q,
                    unit_cost_restored=ret_item.unit_cost_restored,
                    damaged_disposition=insp_data.get("damaged_disposition", "QUARANTINE"),
                    inspected_by=user
                )

                ret_item.inspected_qty = good_q + damaged_q + scrap_q
                ret_item.restored_qty = good_q
                ret_item.save()

                inspections.append(insp)

            logger.info(f"Recorded {len(inspections)} quality inspections for SalesReturn #{ret_header.return_number}.")
            return inspections

    @classmethod
    def process_return_stock_and_accounting(
        cls,
        return_header_id: int,
        user=None
    ) -> SalesReturnAudit:
        """
        التنفيذ المحاسبي والمخزني لمرتجع المبيعات (إعادة المخزون السليم لـ Warehouse وعكس COGS)
        """
        with transaction.atomic():
            event_id = f"SALES-RETURN-PROC-{return_header_id}"

            # Check Database Event Idempotency Guard
            existing = SalesReturnAudit.objects.filter(processed_event_id=event_id).first()
            if existing:
                logger.warning(f"Sales Return Event '{event_id}' already processed in Audit #{existing.id}. Returning existing.")
                return existing

            ret_header = SalesReturnHeader.objects.select_for_update().get(pk=return_header_id)
            if ret_header.status not in ["INSPECTED", "APPROVED"]:
                ret_header.status = "APPROVED"
                ret_header.save()

            total_restored_cogs = Decimal("0.00")
            correlation_id = uuid.uuid4()

            for item in ret_header.items.all():
                insps = item.inspections.all()
                for insp in insps:
                    unit_cost = insp.unit_cost_restored

                    # Trace Audit Link
                    ReturnCostTrace.objects.create(
                        return_item=item,
                        original_stock_movement_id=item.delivery_item.id,
                        delivery_document_number=ret_header.delivery_note.delivery_number,
                        original_quantity=item.delivery_item.delivered_qty,
                        returned_quantity=insp.good_qty + insp.damaged_qty,
                        original_unit_cost=unit_cost,
                        restored_value=(insp.good_qty * unit_cost).quantize(Decimal("0.01"))
                    )

                    # 1. Restore Physical Stock for GOOD Items via MovementService
                    if insp.good_qty > Decimal("0.00"):
                        MovementService().process_movement(
                            product_id=item.product.id,
                            quantity_change=insp.good_qty,
                            movement_type="in",
                            source_reference=f"RET-IN-{ret_header.return_number}",
                            idempotency_key=f"STOCK_MVMT_RET_GOOD_{ret_header.id}_{item.id}_{insp.id}",
                            user=user,
                            unit_cost=unit_cost,
                            document_number=f"RET-IN-{ret_header.return_number}",
                            notes=f"Stock restored from Sales Return #{ret_header.return_number}",
                            warehouse_id=ret_header.warehouse.id
                        )
                        total_restored_cogs += (insp.good_qty * unit_cost).quantize(Decimal("0.01"))

                    # 2. Route DAMAGED Items to Quarantine Warehouse
                    if insp.damaged_qty > Decimal("0.00"):
                        quarantine_wh, _ = Warehouse.objects.get_or_create(
                            code="WH-QUARANTINE",
                            defaults={"name": "Quarantine / Damaged Goods Warehouse", "is_active": True}
                        )
                        MovementService().process_movement(
                            product_id=item.product.id,
                            quantity_change=insp.damaged_qty,
                            movement_type="in",
                            source_reference=f"RET-DAMAGED-{ret_header.return_number}",
                            idempotency_key=f"STOCK_MVMT_RET_DAMAGED_{ret_header.id}_{item.id}_{insp.id}",
                            user=user,
                            unit_cost=unit_cost,
                            document_number=f"RET-DAMAGED-{ret_header.return_number}",
                            notes=f"Damaged stock routed to quarantine from Sales Return #{ret_header.return_number}",
                            warehouse_id=quarantine_wh.id
                        )

            # 3. Post COGS GL Reversal Entry via AccountingGateway
            journal_entry = None
            if total_restored_cogs > Decimal("0.00"):
                from financial.services.role_registry import AccountRoleRegistry
                inv_code = AccountRoleRegistry.get_account_code("INVENTORY_GENERAL") or "11310"
                cogs_code = AccountRoleRegistry.get_account_code("COGS_EXPENSE") or "51100"
                command = ReturnAccountingCommand(
                    correlation_id=str(correlation_id),
                    document_number=ret_header.return_number,
                    inventory_account=inv_code,
                    cogs_account=cogs_code,
                    amount=total_restored_cogs,
                    currency="EGP",
                    exchange_rate=Decimal("1.000000"),
                    posting_date=timezone.now().date(),
                    user=user
                )
                journal_entry = create_return_cogs_reversal_entry(command)

            old_stat = ret_header.status
            ret_header.status = "PROCESSED"
            ret_header.save()

            audit = SalesReturnAudit(
                return_header=ret_header,
                event_type="SALES_RETURN_PROCESSED",
                old_status=old_stat,
                new_status="PROCESSED",
                inspection_result="COMPLETED",
                movement_reference=f"RET-IN-{ret_header.return_number}",
                journal_reference=f"RET-COGS-{ret_header.return_number}",
                correlation_id=correlation_id,
                processed_event_id=event_id,
                audit_hash="",
                journal_entry=journal_entry
            )
            audit.save()

            # Generate Canonical SHA256 Hash using saved timestamp
            hash_val = cls.generate_canonical_return_hash(
                correlation_id=str(correlation_id),
                processed_event_id=event_id,
                return_number=ret_header.return_number,
                total_restored_value=total_restored_cogs,
                timestamp=audit.created_at.isoformat()
            )

            SalesReturnAudit.objects.filter(pk=audit.id).update(audit_hash=hash_val)
            audit.audit_hash = hash_val

            logger.info(f"SalesReturnAudit #{audit.id} processed for SalesReturn #{ret_header.return_number} (Hash: {hash_val[:8]}...).")
            return audit
