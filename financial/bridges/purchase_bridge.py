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
            func_discount = ((purchase.discount or Decimal("0.00")) * rate).quantize(Decimal("0.01"))
            func_gross_subtotal = (func_total + func_discount - func_tax).quantize(Decimal("0.01"))

            from financial.services.role_registry import AccountRoleRegistry
            lines = []
            # 1. Inventory Clearing / Expense Debit Line (Gross amount)
            grni_acc = AccountRoleRegistry.get_account_code("GRNI_CLEARING_ACCOUNT")
            cogs_acc = AccountRoleRegistry.get_account_code("COGS_EXPENSE_ACCOUNT")
            expense_account = grni_acc if not purchase.is_service else cogs_acc
            lines.append({
                "account_code": expense_account,
                "debit": func_gross_subtotal,
                "credit": Decimal("0.00"),
                "foreign_debit": purchase.subtotal if currency_code != "EGP" else None,
                "currency_code": currency_code,
                "exchange_rate": rate,
                "description": f"مشتريات/استلامات فاتورة #{purchase.number} - {purchase.supplier.name}"
            })

            # 2. Input VAT Tax Line (if any)
            if func_tax > Decimal("0.00"):
                input_tax_acc = AccountRoleRegistry.get_account_code("INPUT_TAX_ACCOUNT")
                lines.append({
                    "account_code": input_tax_acc,
                    "debit": func_tax,
                    "credit": Decimal("0.00"),
                    "foreign_debit": purchase.tax if currency_code != "EGP" else None,
                    "currency_code": currency_code,
                    "exchange_rate": rate,
                    "description": f"ضريبة مشتريات مستردة #{purchase.number}"
                })

            # 3. Earned Discount Credit Line (51930 - الخصم المكتسب - تخفيض تكلفة)
            if func_discount > Decimal("0.00"):
                discount_acc = AccountRoleRegistry.get_account_code("PURCHASE_DISCOUNTS_ACCOUNT")
                lines.append({
                    "account_code": discount_acc,
                    "debit": Decimal("0.00"),
                    "credit": func_discount,
                    "foreign_credit": purchase.discount if currency_code != "EGP" else None,
                    "currency_code": currency_code,
                    "exchange_rate": rate,
                    "description": f"خصم مكتسب فاتورة مشتريات #{purchase.number}"
                })

            # 4. AP Supplier Credit Line
            default_ap = AccountRoleRegistry.get_account_code("AP_CONTROL_ACCOUNT")
            ap_account = (
                purchase.supplier.financial_account.code
                if (hasattr(purchase.supplier, "financial_account") and purchase.supplier.financial_account)
                else getattr(purchase.supplier, "account_code", default_ap) or default_ap
            )
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
