"""
InventoryAccountingBridge - جسر التوجيه المحاسبي للمخزون والـ GRN والـ Landed Costs
يولد القيود المزدوجة المحوكمة لإذون الاستلام GRN، تسويات الـ GRNI، وتوزيع التكاليف المضافة.
"""

import logging
from decimal import Decimal
from typing import Dict, Any, Optional
from django.utils import timezone
from django.db import transaction

from financial.services.exchange_rate_service import ExchangeRateService
from financial.services.ledger_core_service import LedgerCoreService

logger = logging.getLogger("financial.bridges.inventory")


class InventoryAccountingBridge:
    """
    جسر التوجيه المحاسبي المعزول للمخزون وحركات الـ GRN
    """

    @classmethod
    def post_grn_receipt(cls, grn_id: int, user=None) -> Dict[str, Any]:
        """
        إنشاء وترحيل قيد استلام البضاعة الفعلي بالمخزن: Dr. 11040 المخزون / Cr. 20150 GRNI
        """
        from purchase.models.procurement_models import GoodsReceivedNote

        with transaction.atomic():
            grn = GoodsReceivedNote.objects.select_for_update().get(pk=grn_id)
            if grn.journal_entry:
                return {"status": "ALREADY_POSTED", "journal_entry_id": grn.journal_entry.id}

            currency_code = grn.currency if hasattr(grn, "currency") and grn.currency else ExchangeRateService.get_functional_currency().code
            rate = grn.exchange_rate if hasattr(grn, "exchange_rate") and grn.exchange_rate else Decimal("1.000000")

            total_foreign = Decimal("0.00")
            total_functional = Decimal("0.00")

            for item in grn.items.all():
                item_total = (item.received_qty * item.unit_price).quantize(Decimal("0.01"))
                total_foreign += item_total
                total_functional += (item_total * rate).quantize(Decimal("0.01"))

            from financial.services.role_registry import AccountRoleRegistry
            inv_acc = AccountRoleRegistry.get_account_code("INVENTORY_CONTROL_ACCOUNT")
            grni_acc = AccountRoleRegistry.get_account_code("GRNI_CLEARING_ACCOUNT")

            lines = [
                # Debit Inventory Account
                {
                    "account_code": inv_acc,
                    "debit": total_functional,
                    "credit": Decimal("0.00"),
                    "foreign_debit": total_foreign if currency_code != "EGP" else None,
                    "currency_code": currency_code,
                    "exchange_rate": rate,
                    "description": f"إذن استلام مخزني GRN #{grn.grn_number} - {grn.supplier.name}"
                },
                # Credit GRNI Accrual Clearing Account
                {
                    "account_code": grni_acc,
                    "debit": Decimal("0.00"),
                    "credit": total_functional,
                    "foreign_credit": total_foreign if currency_code != "EGP" else None,
                    "currency_code": currency_code,
                    "exchange_rate": rate,
                    "description": f"استحقاق بضاعة غير مفوترة GRNI #{grn.grn_number}"
                },
            ]

            entry_date = grn.received_date.date() if hasattr(grn.received_date, "date") else timezone.now().date()
            draft_entry = LedgerCoreService.create_draft_entry(
                date=entry_date,
                description=f"قيد استلام مخزني GRN #{grn.grn_number}",
                reference=f"GRN-{grn.grn_number}",
                entry_type="GENERAL",
                created_by=user,
                lines_data=lines,
                source_module="INVENTORY",
                source_model="GoodsReceivedNote",
                source_id=grn.id
            )
            posted_entry = LedgerCoreService.post_entry(draft_entry.id, user=user)

            grn.journal_entry = posted_entry
            grn.save(update_fields=["journal_entry"])

            logger.info(f"Posted Inventory Accounting Bridge entry #{posted_entry.id} for GRN #{grn.grn_number}")
            return {"status": "POSTED", "journal_entry_id": posted_entry.id}
