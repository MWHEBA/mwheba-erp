"""
ProcurementService - خدمة المايسترو المركزية لإدارة دورة التوريد والمشتريات المحوكمة (FIN-PUR-001 - FIN-PUR-009)
تنسق بين أوامر الشراء والاستلام الفعلي GRN وفواتير الموردين والمطابقة الثلاثية والربط المحاسبي
"""

import logging
import uuid
from decimal import Decimal
from typing import Dict, Any, List, Optional
from django.db import transaction
from django.utils import timezone
from django.db.models import Sum

from purchase.models.procurement_models import (
    PurchaseOrder,
    PurchaseOrderItem,
    GoodsReceivedNote,
    GoodsReceivedNoteItem,
    SupplierBill,
    SupplierBillItem,
    BillLineMatching
)
from purchase.services.matching_service import ThreeWayMatchingService
from governance.services.movement_service import MovementService
from financial.services.ledger_core_service import LedgerCoreService
from financial.exceptions import FinancialCoreError

logger = logging.getLogger("purchase.procurement_service")


class ProcurementService:
    """
    الخدمة الحاكمة المركزية لإدارة عمليات المشتريات والتوريد (Procurement Master Orchestrator)
    """

    @classmethod
    def generate_po_number(cls) -> str:
        date_prefix = timezone.now().strftime("%Y%m%d")
        unique_suffix = str(uuid.uuid4()).split('-')[0].upper()
        return f"PO-{date_prefix}-{unique_suffix}"

    @classmethod
    def generate_grn_number(cls) -> str:
        date_prefix = timezone.now().strftime("%Y%m%d")
        unique_suffix = str(uuid.uuid4()).split('-')[0].upper()
        return f"GRN-{date_prefix}-{unique_suffix}"

    @classmethod
    def generate_bill_number(cls) -> str:
        date_prefix = timezone.now().strftime("%Y%m%d")
        unique_suffix = str(uuid.uuid4()).split('-')[0].upper()
        return f"BILL-{date_prefix}-{unique_suffix}"

    @classmethod
    def create_purchase_order(
        cls,
        supplier,
        warehouse,
        order_date,
        items_data: List[Dict[str, Any]],
        user,
        currency: str = "EGP",
        exchange_rate: Decimal = Decimal("1.0000")
    ) -> PurchaseOrder:
        """
        إنشاء أمر شراء جديد (مسودة)
        """
        with transaction.atomic():
            po_num = cls.generate_po_number()
            po = PurchaseOrder.objects.create(
                order_number=po_num,
                supplier=supplier,
                warehouse=warehouse,
                order_date=order_date,
                currency=currency,
                exchange_rate=exchange_rate,
                status="DRAFT",
                created_by=user
            )

            total_amt = Decimal("0.00")
            for item in items_data:
                product = item["product"]
                ordered_qty = Decimal(str(item["ordered_qty"]))
                unit_price = Decimal(str(item["unit_price"]))
                line_total = (ordered_qty * unit_price).quantize(Decimal("0.01"))

                PurchaseOrderItem.objects.create(
                    purchase_order=po,
                    product=product,
                    variant=item.get("variant"),
                    unit=item.get("unit") or getattr(product, 'unit', None),
                    ordered_qty=ordered_qty,
                    unit_price=unit_price,
                    total_price=line_total
                )
                total_amt += line_total

            po.total_amount = total_amt
            po.functional_amount = (total_amt * exchange_rate).quantize(Decimal("0.01"))
            po.save(update_fields=["total_amount", "functional_amount"])

            logger.info(f"PurchaseOrder created: #{po_num} with total {total_amt} {currency}.")
            return po

    @classmethod
    def approve_purchase_order(cls, po_id: int, user) -> PurchaseOrder:
        """
        اعتماد أمر الشراء للتجهيز والتوريد (Approved State Transition)
        """
        with transaction.atomic():
            po = PurchaseOrder.objects.select_for_update().get(pk=po_id)
            if po.status not in ["DRAFT", "SUBMITTED"]:
                raise FinancialCoreError(f"Cannot approve PO in status {po.status}.")

            po.status = "APPROVED"
            po.approved_by = user
            po.save(update_fields=["status", "approved_by"])

            logger.info(f"PurchaseOrder #{po.order_number} approved by {user.username}.")
            return po

    @classmethod
    def receive_goods_grn(
        cls,
        po_id: int,
        delivery_note_ref: str,
        items_data: List[Dict[str, Any]],
        user
    ) -> GoodsReceivedNote:
        """
        تسجيل استلام مخزني فعلي (GRN) وتوليد حركات المخزون وقيد 11040/20150 GRNI
        """
        with transaction.atomic():
            po = PurchaseOrder.objects.select_for_update().get(pk=po_id)
            if po.status not in ["APPROVED", "PARTIALLY_RECEIVED"]:
                raise FinancialCoreError("Cannot issue GRN for unapproved purchase order.")

            grn_num = cls.generate_grn_number()
            grn = GoodsReceivedNote.objects.create(
                grn_number=grn_num,
                purchase_order=po,
                supplier=po.supplier,
                warehouse=po.warehouse,
                supplier_delivery_note_ref=delivery_note_ref,
                status="RECEIVED"
            )

            total_grn_cost = Decimal("0.00")

            for item in items_data:
                po_item = PurchaseOrderItem.objects.select_for_update().get(pk=item["po_item_id"])
                received_qty = Decimal(str(item["received_qty"]))

                if received_qty <= Decimal("0.0000"):
                    continue

                line_cost = (received_qty * po_item.unit_price).quantize(Decimal("0.01"))

                grn_item = GoodsReceivedNoteItem.objects.create(
                    grn=grn,
                    po_item=po_item,
                    product=po_item.product,
                    received_qty=received_qty,
                    unit_price=po_item.unit_price,
                    total_cost=line_cost
                )

                # تحديث كميات أمر الشراء
                po_item.received_qty += received_qty
                po_item.save(update_fields=["received_qty"])

                # 1. إمرر حركة المخزون للخدمة الموحدة MovementService
                movement_service = MovementService()
                stk_movement = movement_service.process_movement(
                    product_id=po_item.product.id,
                    quantity_change=received_qty,
                    movement_type="in",
                    source_reference=f"GRN-{grn.id}",
                    idempotency_key=f"GRN-STK-{grn.id}-{po_item.product.id}",
                    user=user,
                    unit_cost=po_item.unit_price,
                    warehouse_id=po.warehouse.id
                )

                total_grn_cost += line_cost

            # تحديث حالة أمر الشراء
            total_ordered = po.items.aggregate(sum_ord=Sum("ordered_qty"))["sum_ord"] or Decimal("0.0000")
            total_received = po.items.aggregate(sum_rec=Sum("received_qty"))["sum_rec"] or Decimal("0.0000")

            if total_received >= total_ordered:
                po.status = "FULLY_RECEIVED"
            else:
                po.status = "PARTIALLY_RECEIVED"
            po.save(update_fields=["status"])

            # 2. إنشاء قيد الاستلام المحاسبي: Dr. 10400 Inventory / Cr. 20150 GRNI
            lines_data = [
                {"account_code": "10400", "debit": total_grn_cost, "credit": Decimal("0.00"), "description": f"GRN Inventory Asset Receipt #{grn_num}"},
                {"account_code": "20150_GRNI", "debit": Decimal("0.00"), "credit": total_grn_cost, "description": f"GRNI Account Credit #{grn_num}"}
            ]

            draft_entry = LedgerCoreService.create_draft_entry(
                date=timezone.now().date(),
                description=f"GRN Receipt Entry #{grn_num}",
                reference=f"GRN-{grn.id}",
                entry_type="GENERAL",
                created_by=user,
                lines_data=lines_data
            )
            journal_entry = LedgerCoreService.post_entry(draft_entry.id, user=user)
            grn.journal_entry = journal_entry
            grn.save(update_fields=["journal_entry"])

            logger.info(f"GRN #{grn_num} processed successfully. Stock updated & GL Entry #{journal_entry.id} posted.")
            return grn

    @classmethod
    def create_supplier_bill(
        cls,
        supplier,
        supplier_bill_number: str,
        bill_date,
        due_date,
        items_data: List[Dict[str, Any]],
        user,
        bill_type: str = "INVENTORY_INVOICE",
        currency: str = "EGP",
        exchange_rate: Decimal = Decimal("1.0000")
    ) -> SupplierBill:
        """
        إنشاء وتأكيد فاتورة المورد وإجراء المطابقة الثلاثية Line-Level 3-Way Matching وقيد AP/GRNI/PPV
        """
        with transaction.atomic():
            bill_num = cls.generate_bill_number()
            bill = SupplierBill.objects.create(
                bill_number=bill_num,
                supplier=supplier,
                supplier_bill_number=supplier_bill_number,
                bill_type=bill_type,
                bill_date=bill_date,
                due_date=due_date,
                currency=currency,
                exchange_rate=exchange_rate,
                total_amount=Decimal("0.00"),
                functional_amount=Decimal("0.00"),
                status="POSTED",
                created_by=user
            )

            total_bill_amount = Decimal("0.00")
            total_grni_clearance = Decimal("0.00")
            total_ppv_variance = Decimal("0.00")

            for item in items_data:
                grn_item = GoodsReceivedNoteItem.objects.select_for_update().get(pk=item["grn_item_id"])
                billed_qty = Decimal(str(item["billed_qty"]))
                unit_price = Decimal(str(item["unit_price"]))
                line_total = (billed_qty * unit_price).quantize(Decimal("0.01"))

                bill_item = SupplierBillItem.objects.create(
                    bill=bill,
                    grn_item=grn_item,
                    po_item=grn_item.po_item,
                    product=grn_item.product,
                    billed_qty=billed_qty,
                    unit_price=unit_price,
                    total_amount=line_total
                )

                # إجراء المطابقة الثلاثية الخطية (Line-Level 3-Way Matching)
                matching = ThreeWayMatchingService.match_bill_line_item(
                    bill_item=bill_item,
                    grn_item=grn_item,
                    matched_qty=billed_qty,
                    bill_unit_price=unit_price
                )

                grni_clearance_line = (billed_qty * matching.po_unit_price).quantize(Decimal("0.01"))
                total_grni_clearance += grni_clearance_line
                total_ppv_variance += matching.price_variance
                total_bill_amount += line_total

            bill.total_amount = total_bill_amount
            bill.functional_amount = (total_bill_amount * exchange_rate).quantize(Decimal("0.01"))
            bill.save(update_fields=["total_amount", "functional_amount"])

            # إنشاء القيد المحاسبي للفاتورة: Dr. 20150 GRNI / Dr/Cr. 50120 PPV / Cr. 20100 AP
            lines_data = [
                {"account_code": "20150_GRNI", "debit": total_grni_clearance, "credit": Decimal("0.00"), "description": f"GRNI Clearance for Bill #{supplier_bill_number}"},
                {"account_code": "20100", "debit": Decimal("0.00"), "credit": total_bill_amount, "description": f"AP Payable to {supplier.name}"}
            ]

            if total_ppv_variance > Decimal("0.00"):
                lines_data.append({
                    "account_code": "50120_PPV", "debit": total_ppv_variance, "credit": Decimal("0.00"), "description": "PPV Unfavorable Variance Expense"
                })
            elif total_ppv_variance < Decimal("0.00"):
                lines_data.append({
                    "account_code": "50120_PPV", "debit": Decimal("0.00"), "credit": abs(total_ppv_variance), "description": "PPV Favorable Variance Credit"
                })

            draft_entry = LedgerCoreService.create_draft_entry(
                date=bill_date,
                description=f"Supplier Bill Entry #{bill_num} (Ref: {supplier_bill_number})",
                reference=f"BILL-{bill.id}",
                entry_type="GENERAL",
                created_by=user,
                lines_data=lines_data
            )
            journal_entry = LedgerCoreService.post_entry(draft_entry.id, user=user)
            bill.journal_entry = journal_entry
            bill.save(update_fields=["journal_entry"])

            logger.info(f"SupplierBill #{bill_num} created & posted. Total AP={total_bill_amount}, PPV={total_ppv_variance}.")
            return bill

    @classmethod
    def process_pre_invoice_grn_return(
        cls,
        grn_item_id: int,
        return_qty: Decimal,
        user
    ) -> Dict[str, Any]:
        """
        معالجة مرتجع المشتريات قبل الفاتورة (Pre-Invoice GRN Return)
        قيد المحاسبة: Dr. 20150 GRNI / Cr. 11040 Inventory Asset
        """
        with transaction.atomic():
            grn_item = GoodsReceivedNoteItem.objects.select_for_update().get(pk=grn_item_id)
            if return_qty <= Decimal("0.0000") or return_qty > grn_item.received_qty:
                raise FinancialCoreError("Invalid return quantity.")

            return_value = (return_qty * grn_item.unit_price).quantize(Decimal("0.01"))

            # خصم الكمية المستلمة
            grn_item.received_qty -= return_qty
            grn_item.save(update_fields=["received_qty"])

            # سحب الحركة من أستاذ المخزون عبر MovementService
            movement_service = MovementService()
            stk_movement = movement_service.process_movement(
                product_id=grn_item.product.id,
                quantity_change=-return_qty,
                movement_type="out",
                source_reference=f"GRN-RET-{grn_item.grn.id}",
                idempotency_key=f"GRN-RET-STK-{grn_item.id}-{return_qty}",
                user=user,
                unit_cost=grn_item.unit_price,
                warehouse_id=grn_item.grn.warehouse.id
            )

            # قيد المحاسبة: Dr. 20150 GRNI / Cr. 10400 Inventory Asset
            lines_data = [
                {"account_code": "20150_GRNI", "debit": return_value, "credit": Decimal("0.00"), "description": f"Pre-Invoice Return GRNI Debit"},
                {"account_code": "10400", "debit": Decimal("0.00"), "credit": return_value, "description": f"Pre-Invoice Return Inventory Credit"}
            ]

            draft_entry = LedgerCoreService.create_draft_entry(
                date=timezone.now().date(),
                description=f"GRN Return Entry #{grn_item.grn.grn_number}",
                reference=f"GRN-RET-{grn_item.id}",
                entry_type="GENERAL",
                created_by=user,
                lines_data=lines_data
            )
            journal_entry = LedgerCoreService.post_entry(draft_entry.id, user=user)

            logger.info(f"Pre-Invoice GRN Return processed for GRNItem #{grn_item.id}: Qty={return_qty}, Value={return_value} EGP.")

            return {
                "grn_item_id": grn_item.id,
                "return_qty": return_qty,
                "return_value": return_value,
                "journal_entry_id": journal_entry.id
            }
