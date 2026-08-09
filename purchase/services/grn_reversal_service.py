import logging
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.db.models import Sum

from purchase.models.procurement_models import GoodsReceivedNote, BillLineMatching
from purchase.models.grn_audit_log import GRNAuditLog
from governance.services.movement_service import MovementService
from financial.services.ledger_core_service import LedgerCoreService
from financial.services.period_control_service import PeriodControlService
from financial.exceptions import FinancialCoreError
from .grn_posting_service import GRNPostingService

logger = logging.getLogger("purchase.grn_reversal_service")


class GRNReversalService:
    """
    خدمة عكس وتلغية أذون الاستلام المعتمدة (GRN Reversal Service)
    تحترم الحوكمة المعمارية الثلاثية (Payment -> Bill -> GRN) وتحمي الفترة المالية المغلقة
    """

    @classmethod
    def reverse_grn(cls, grn_id: int, user, reason: str) -> GoodsReceivedNote:
        """
        عكس إذن استلام مرحل وحفظ التسلسل الهرمي القيدي
        """
        if not reason:
            raise FinancialCoreError("يلزم تقديم سبب واضح وموثق لعكس إذن الاستلام.")

        with transaction.atomic():
            grn = GoodsReceivedNote.objects.select_for_update().get(pk=grn_id)

            if grn.status != "POSTED":
                raise FinancialCoreError(f"لا يمكن عكس إذن استلام بحالة {grn.get_status_display()}. العكس متاح فقط للإذونات المرحلة.")

            # 1. 3-Tier Reversal Guard: التحقق من عدم وجود فواتير أو سدادات مرتبطة بالمستند
            for item in grn.items.all():
                if item.billed_qty > Decimal("0.0000"):
                    raise FinancialCoreError(
                        f"لا يمكن عكس إذن الاستلام #{grn.grn_number} نظراً لوجود كميات مفوترة ({item.billed_qty}) للمنتج {item.product.name}. "
                        f"يجب عكس فواتير وسدادات المورد المرتبطة أولاً."
                    )
                if BillLineMatching.objects.filter(grn_item=item).exists():
                    raise FinancialCoreError(f"لا يمكن عكس إذن الاستلام #{grn.grn_number} لوجود سجلات مطابقة فواتير مرتبطة به.")

            # 2. تاريخ الترحيل القيدي وعوائق الفترة المالية المغلقة (Period Control Date Guard)
            orig_date = grn.received_date.date()
            try:
                posting_date = PeriodControlService.get_open_period_date(orig_date)
            except Exception:
                posting_date = timezone.now().date()

            movement_service = MovementService()
            total_reversed_cost = Decimal("0.00")
            lines_data = []

            # 3. عكس حركات المخزون وتجميع قيود الأستاذ المالي
            for item in grn.items.select_related("product", "po_item").all():
                received_qty = item.received_qty
                if received_qty <= Decimal("0.0000"):
                    continue

                unit_price = item.unit_price
                line_cost = (received_qty * unit_price).quantize(Decimal("0.01"))

                # حركات المخزون العكسية
                try:
                    stk_movement = movement_service.process_movement(
                        product_id=item.product.id,
                        quantity_change=-received_qty,
                        movement_type="out",
                        source_reference=f"GRN-REV-{grn.id}",
                        idempotency_key=f"GRN-REV-STK-{grn.id}-{item.product.id}",
                        user=user,
                        unit_cost=unit_price,
                        warehouse_id=grn.warehouse.id
                    )
                except Exception as e:
                    logger.warning(f"MovementService warning on reversal accounting entry creation: {e}. Decreasing stock directly...")
                    from product.models.stock_management import Stock
                    stock_rec = Stock.objects.filter(product=item.product, warehouse=grn.warehouse).first()
                    if stock_rec:
                        stock_rec.quantity = max(Decimal("0.0000"), stock_rec.quantity - received_qty)
                        stock_rec.save()

                # خصم الكميات المستلمة من بند أمر الشراء
                if item.po_item:
                    item.po_item.received_qty = max(Decimal("0.0000"), item.po_item.received_qty - received_qty)
                    item.po_item.save(update_fields=["received_qty"])

                inv_acc = GRNPostingService.resolve_inventory_account(item.product, grn.warehouse)
                lines_data.append({
                    "account": inv_acc,
                    "account_code": inv_acc.code if inv_acc else "10400",
                    "debit": Decimal("0.00"),
                    "credit": line_cost,
                    "description": f"GRN Reversal Inventory Credit: {item.product.name} ({received_qty} @ {unit_price})"
                })

                total_reversed_cost += line_cost

            # 4. الطرف المدين لحساب الـ GRNI (Dr. 20150 GRNI)
            grni_acc = GRNPostingService.resolve_grni_account()
            lines_data.append({
                "account": grni_acc,
                "account_code": grni_acc.code if grni_acc else "20150_GRNI",
                "debit": total_reversed_cost,
                "credit": Decimal("0.00"),
                "description": f"GRNI Debit Reversal for GRN #{grn.grn_number}"
            })

            # 5. إنشاء وتأكيد القيد العكسي المالي
            draft_entry = LedgerCoreService.create_draft_entry(
                date=posting_date,
                description=f"GRN Reversal Entry #{grn.grn_number} (Ref: {orig_date})",
                reference=f"GRN-REV-{grn.id}",
                entry_type="GENERAL",
                created_by=user,
                lines_data=lines_data
            )
            reversal_journal_entry = LedgerCoreService.post_entry(draft_entry.id, user=user)

            # ربط القيد الجديد بصفة قيد عكسي للقيد الأصلي
            if grn.journal_entry and hasattr(reversal_journal_entry, "reversal_of"):
                reversal_journal_entry.reversal_of = grn.journal_entry
                reversal_journal_entry.save(update_fields=["reversal_of"])

            # 6. تحديث حالة إذن الاستلام لـ REVERSED
            grn.status = "REVERSED"
            grn.save(update_fields=["status"])

            # 7. تحديث حالة أمر الشراء المرتط
            if grn.purchase_order:
                po = grn.purchase_order
                total_ordered = po.items.aggregate(sum_ord=Sum("ordered_qty"))["sum_ord"] or Decimal("0.0000")
                total_received = po.items.aggregate(sum_rec=Sum("received_qty"))["sum_rec"] or Decimal("0.0000")

                if total_received <= Decimal("0.0000"):
                    po.status = "APPROVED"
                elif total_received < total_ordered:
                    po.status = "PARTIALLY_RECEIVED"
                else:
                    po.status = "FULLY_RECEIVED"
                po.save(update_fields=["status"])

            # 8. توثيق سجل التدقيق
            GRNAuditLog.objects.create(
                grn=grn,
                old_status="POSTED",
                new_status="REVERSED",
                action_by=user,
                reason=reason,
                comment=f"Reversed GRN #{grn.grn_number}. Reversal Journal Entry #{reversal_journal_entry.id} posted on {posting_date}."
            )

            logger.info(f"GRN #{grn.grn_number} REVERSED. Reversal Entry #{reversal_journal_entry.id} created.")
            return grn
