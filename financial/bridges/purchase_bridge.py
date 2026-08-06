"""
PurchaseAccountingBridge - جسر التوجيه المحاسبي للمشتريات والموردين
يولد القيود المزدوجة المحوكمة لفواتير الموردين والخدمات والمشتريات الأجنبية والمحلية.
"""

import logging
from decimal import Decimal
from typing import Dict, Any, Optional
from django.utils import timezone
from django.db import transaction

from financial.services.exchange_rate_service import ExchangeRateService
from financial.services.ledger_core_service import LedgerCoreService

logger = logging.getLogger("financial.bridges.purchase")


class PurchaseAccountingBridge:
    """
    جسر التوجيه المحاسبي المعزول للمشتريات
    """

    @classmethod
    def post_purchase_invoice(cls, purchase_id: int, user=None) -> Dict[str, Any]:
        """
        إنشاء وترحيل القيد المحاسبي لفاتورة المشتريات بالعملة الوظيفية والأجنبية
        """
        from purchase.models.purchase import Purchase

        with transaction.atomic():
            purchase = Purchase.objects.select_for_update().get(pk=purchase_id)
            if purchase.journal_entry:
                return {"status": "ALREADY_POSTED", "journal_entry_id": purchase.journal_entry.id}

            currency_code = purchase.currency.code if purchase.currency else ExchangeRateService.get_functional_currency().code
            rate = purchase.exchange_rate or Decimal("1.000000")

            func_total = (purchase.total * rate).quantize(Decimal("0.01"))
            func_tax = (purchase.tax * rate).quantize(Decimal("0.01"))
            func_subtotal = (func_total - func_tax).quantize(Decimal("0.01"))

            lines = []
            # 1. Inventory Clearing / Expense Debit Line
            expense_account = "20150_GRNI" if not purchase.is_service else "51010_EXPENSES"
            lines.append({
                "account_code": expense_account,
                "debit": func_subtotal,
                "credit": Decimal("0.00"),
                "foreign_debit": purchase.subtotal - purchase.discount if currency_code != "EGP" else None,
                "currency_code": currency_code,
                "exchange_rate": rate,
                "description": f"مشتريات/استلامات فاتورة #{purchase.number} - {purchase.supplier.name}"
            })

            # 2. Input VAT Tax Line (if any)
            if func_tax > Decimal("0.00"):
                lines.append({
                    "account_code": "11050_VAT_INPUT",
                    "debit": func_tax,
                    "credit": Decimal("0.00"),
                    "foreign_debit": purchase.tax if currency_code != "EGP" else None,
                    "currency_code": currency_code,
                    "exchange_rate": rate,
                    "description": f"ضريبة مشتريات مستردة #{purchase.number}"
                })

            # 3. AP Supplier Credit Line
            ap_account = getattr(purchase.supplier, "account_code", "20100_AP") or "20100_AP"
            lines.append({
                "account_code": ap_account,
                "debit": Decimal("0.00"),
                "credit": func_total,
                "foreign_credit": purchase.total if currency_code != "EGP" else None,
                "currency_code": currency_code,
                "exchange_rate": rate,
                "description": f"استحقاق مورد فاتورة مشتريات #{purchase.number}"
            })

            draft_entry = LedgerCoreService.create_draft_entry(
                date=purchase.date,
                description=f"قيد فاتورة مشتريات رقم #{purchase.number}",
                reference=f"PURCHASE-{purchase.number}",
                entry_type="PURCHASE",
                created_by=user,
                lines_data=lines,
                source_module="PURCHASE",
                source_model="Purchase",
                source_id=purchase.id
            )
            posted_entry = LedgerCoreService.post_entry(draft_entry.id, user=user)

            purchase.journal_entry = posted_entry
            purchase.save(update_fields=["journal_entry"])

            logger.info(f"Posted Purchase Accounting Bridge entry #{posted_entry.id} for Purchase #{purchase.number}")
            return {"status": "POSTED", "journal_entry_id": posted_entry.id}
