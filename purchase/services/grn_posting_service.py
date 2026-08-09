import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional
from django.db import transaction
from django.utils import timezone
from django.db.models import Sum

from purchase.models.procurement_models import (
    GoodsReceivedNote,
    GoodsReceivedNoteItem,
    PurchaseOrder,
    PurchaseOrderItem
)
from purchase.models.grn_audit_log import GRNAuditLog
from purchase.models.grn_posting_log import GRNPostingLog
from governance.services.movement_service import MovementService
from financial.services.ledger_core_service import LedgerCoreService
from financial.services.account_role_registry import AccountRoleRegistry
from financial.exceptions import FinancialCoreError

logger = logging.getLogger("purchase.grn_posting_service")


class GRNPostingService:
    """
    خدمة الترحيل الفعلي لإذن الاستلام (GRN Posting Service)
    مسؤولة عن الترحيل المالي والمخزني المزدوج وتحديث كميات أمر الشراء
    """

    @classmethod
    def resolve_inventory_account(cls, product, warehouse):
        """
        تحديد كود وحساب الأصول المخزنية هرمياً (Hierarchical Account Resolution Priority):
        1. Product Specific Account
        2. Category Inventory Account
        3. Warehouse Inventory Account
        4. AccountRoleRegistry ("INVENTORY_CONTROL_ACCOUNT" / "INVENTORY_ASSET")
        5. ChartOfAccounts Fallback
        """
        acc = None
        if hasattr(product, "inventory_account") and product.inventory_account:
            acc = product.inventory_account
        elif hasattr(product, "category") and product.category and hasattr(product.category, "inventory_account") and product.category.inventory_account:
            acc = product.category.inventory_account
        elif hasattr(warehouse, "inventory_account") and warehouse.inventory_account:
            acc = warehouse.inventory_account
        else:
            acc = AccountRoleRegistry.get_account_by_role("INVENTORY_CONTROL_ACCOUNT") or AccountRoleRegistry.get_account_by_role("INVENTORY_ASSET")

        if acc:
            return acc

        from financial.models import ChartOfAccounts
        leaf_accounts = ChartOfAccounts.objects.filter(is_active=True)
        if hasattr(ChartOfAccounts, "is_leaf"):
            leaf_accounts = leaf_accounts.filter(is_leaf=True)

        existing_default = leaf_accounts.filter(code__in=["10400", "1040"]).first()
        if existing_default:
            return existing_default

        asset_fallback = leaf_accounts.filter(account_type__category="asset").first()
        if asset_fallback:
            return asset_fallback

        return leaf_accounts.first()

    @classmethod
    def resolve_grni_account(cls):
        """
        تحديد كود وحساب GRNI الاستحقاقي عبر AccountRoleRegistry والبحث الهرمي
        """
        grni_acc = AccountRoleRegistry.get_account_by_role("GRNI_CLEARING")
        if grni_acc and getattr(grni_acc, "is_active", True) and getattr(grni_acc, "is_leaf", True):
            return grni_acc

        from financial.models import ChartOfAccounts
        leaf_accounts = ChartOfAccounts.objects.filter(is_active=True)
        if hasattr(ChartOfAccounts, "is_leaf"):
            leaf_accounts = leaf_accounts.filter(is_leaf=True)

        existing = leaf_accounts.filter(code__in=["20150", "20150_GRNI"]).first()
        if existing:
            return existing

        liab_fallback = leaf_accounts.filter(account_type__category="liability").first()
        if liab_fallback:
            return liab_fallback

        return leaf_accounts.first()

    @classmethod
    def post_grn(cls, grn_id: int, user, reason: str = "") -> GoodsReceivedNote:
        """
        تنفيذ الترحيل الفعلي لإذن الاستلام بـ transaction.atomic() ونقل الإشعارات لـ on_commit
        """
        with transaction.atomic():
            grn = GoodsReceivedNote.objects.select_for_update().get(pk=grn_id)

            if grn.status in ["POSTED", "REVERSED"]:
                raise FinancialCoreError(f"إذن الاستلام #{grn.grn_number} مرحل بالفعل أو معكوس ولا يمكن ترحيله مرة أخرى.")

            if not grn.items.exists():
                raise FinancialCoreError("لا يمكن ترحيل إذن استلام لا يحتوي على بنود.")

            total_grn_cost = Decimal("0.00")
            stock_movements_count = 0
            lines_data = []

            # 1. إمرار حركات المخزون وتجميع قيود الأستاذ لكل بند
            movement_service = MovementService()
            for item in grn.items.select_related("product", "po_item").all():
                received_qty = item.received_qty
                if received_qty <= Decimal("0.0000"):
                    continue

                unit_price = item.unit_price
                line_cost = (received_qty * unit_price).quantize(Decimal("0.01"))

                # تسجيل حركة المستودع عبر الحركة الموحدة
                try:
                    stk_movement = movement_service.process_movement(
                        product_id=item.product.id,
                        quantity_change=received_qty,
                        movement_type="in",
                        source_reference=f"GRN-{grn.id}",
                        idempotency_key=f"GRN-STK-{grn.id}-{item.product.id}",
                        user=user,
                        unit_cost=unit_price,
                        warehouse_id=grn.warehouse.id
                    )
                except Exception as e:
                    logger.warning(f"MovementService warning on accounting entry creation: {e}. Updating stock directly...")
                    from product.models.stock_management import Stock
                    stock_rec, _ = Stock.objects.get_or_create(
                        product=item.product,
                        warehouse=grn.warehouse,
                        defaults={"quantity": Decimal("0.0000")}
                    )
                    stock_rec.quantity += received_qty
                    stock_rec.save()
                stock_movements_count += 1

                # تحديث الكمية المستلمة في بند أمر الشراء إن وجد
                if item.po_item:
                    item.po_item.received_qty += received_qty
                    item.po_item.save(update_fields=["received_qty"])

                # تحديد كود وحساب أصل المخزون هرمياً لكل منتج
                inv_acc = cls.resolve_inventory_account(item.product, grn.warehouse)
                lines_data.append({
                    "account": inv_acc,
                    "account_code": inv_acc.code if inv_acc else "10400",
                    "debit": line_cost,
                    "credit": Decimal("0.00"),
                    "description": f"GRN Inventory Receipt: {item.product.name} ({received_qty} @ {unit_price})"
                })

                total_grn_cost += line_cost

            # 2. إضافة الطرف الدائن لحساب 20150_GRNI
            grni_acc = cls.resolve_grni_account()
            lines_data.append({
                "account": grni_acc,
                "account_code": grni_acc.code if grni_acc else "20150_GRNI",
                "debit": Decimal("0.00"),
                "credit": total_grn_cost,
                "description": f"GRNI Credit Accrual for GRN #{grn.grn_number}"
            })

            # 3. إنشاء وتأكيد قيد الأستاذ المالي
            draft_entry = LedgerCoreService.create_draft_entry(
                date=timezone.now().date(),
                description=f"GRN Inventory Asset Receipt #{grn.grn_number}",
                reference=f"GRN-{grn.id}",
                entry_type="GENERAL",
                created_by=user,
                lines_data=lines_data
            )
            journal_entry = LedgerCoreService.post_entry(draft_entry.id, user=user)

            # 4. تحديث حالة إذن الاستلام
            old_status = grn.status
            grn.status = "POSTED"
            grn.journal_entry = journal_entry
            grn.save(update_fields=["status", "journal_entry"])

            # 5. تحديث حالة أمر الشراء المرتط
            if grn.purchase_order:
                po = grn.purchase_order
                total_ordered = po.items.aggregate(sum_ord=Sum("ordered_qty"))["sum_ord"] or Decimal("0.0000")
                total_received = po.items.aggregate(sum_rec=Sum("received_qty"))["sum_rec"] or Decimal("0.0000")

                if total_received >= total_ordered:
                    po.status = "FULLY_RECEIVED"
                else:
                    po.status = "PARTIALLY_RECEIVED"
                po.save(update_fields=["status"])

            # 6. تسجيل سجلات التتبع والتدقيق (Posting Log & Audit Log)
            GRNPostingLog.objects.create(
                grn=grn,
                journal_entry=journal_entry,
                stock_movements_count=stock_movements_count,
                total_posted_value=total_grn_cost,
                posted_by=user
            )

            GRNAuditLog.objects.create(
                grn=grn,
                old_status=old_status,
                new_status="POSTED",
                action_by=user,
                reason=reason or "Posting GRN",
                comment=f"Successfully posted GRN #{grn.grn_number} with total value {total_grn_cost} EGP."
            )

            logger.info(f"GRN #{grn.grn_number} POSTED successfully. Entry #{journal_entry.id} posted.")

            # 7. ترحيل التنبيهات والخدمات الإضافية لخارج الترانزاكشن
            transaction.on_commit(lambda: cls._send_post_notifications(grn.id))

            return grn

    @classmethod
    def _send_post_notifications(cls, grn_id: int) -> None:
        """
        إرسال التنبيهات والإشعارات بعد اكتمال الـ Commit
        """
        logger.info(f"Notification queued for POSTED GRN #{grn_id}.")
