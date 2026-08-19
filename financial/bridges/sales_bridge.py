"""
SalesAccountingBridge - جسر التوجيه المحاسبي للمبيعات والمرتجعات
يولد القيود المزدوجة المحوكمة لفواتير المبيعات، الإشعارات الدائنة، ومرتجعات المبيعات بجميع العملات.
"""

import logging
from decimal import Decimal
from typing import Dict, Any, Optional
from django.utils import timezone
from django.db import transaction

from financial.services.exchange_rate_service import ExchangeRateService
from financial.services.ledger_core_service import LedgerCoreService

logger = logging.getLogger("financial.bridges.sales")


class SalesAccountingBridge:
    """
    جسر التوجيه المحاسبي المعزول للمبيعات
    """

    @classmethod
    def post_sale_invoice(cls, sale_id: int, user=None) -> Dict[str, Any]:
        """
        إنشاء وترحيل القيد المحاسبي لفاتورة المبيعات بالعملة الوظيفية والأجنبية
        """
        from sale.models.sale import Sale

        with transaction.atomic():
            sale = Sale.objects.select_for_update().get(pk=sale_id)
            if sale.journal_entry:
                return {"status": "ALREADY_POSTED", "journal_entry_id": sale.journal_entry.id}

            currency_code = sale.currency.code if sale.currency else ExchangeRateService.get_functional_currency().code
            rate = sale.exchange_rate or Decimal("1.000000")

            func_total = (sale.total * rate).quantize(Decimal("0.01"))
            func_tax = (sale.tax * rate).quantize(Decimal("0.01"))
            func_net_sales = (func_total - func_tax).quantize(Decimal("0.01"))

            from financial.services.account_role_registry import AccountRoleRegistry

            lines = []
            # 1. AR Customer Debit Line
            cust_acc = getattr(sale.customer, "financial_account", None)
            if cust_acc:
                ar_account = cust_acc.code
            else:
                ar_account = getattr(sale.customer, "account_code", None) or AccountRoleRegistry.get_account_code("CUSTOMER_RECEIVABLE_CONTROL")

            lines.append({
                "account_code": ar_account,
                "debit": func_total,
                "credit": Decimal("0.00"),
                "foreign_debit": sale.total if currency_code != "EGP" else None,
                "currency_code": currency_code,
                "exchange_rate": rate,
                "description": f"فاتورة مبيعات #{sale.number} - {sale.customer.name}"
            })

            # 2. Net Sales Revenue Credit Line
            revenue_account = AccountRoleRegistry.get_account_code("SALES_REVENUE_ACCOUNT")
            lines.append({
                "account_code": revenue_account,
                "debit": Decimal("0.00"),
                "credit": func_net_sales,
                "foreign_credit": sale.subtotal - sale.discount if currency_code != "EGP" else None,
                "currency_code": currency_code,
                "exchange_rate": rate,
                "description": f"إيراد مبيعات #{sale.number}"
            })

            # 3. Output VAT Tax Line (if any)
            if func_tax > Decimal("0.00"):
                vat_account = AccountRoleRegistry.get_account_code("SALES_TAX_PAYABLE")
                lines.append({
                    "account_code": vat_account,
                    "debit": Decimal("0.00"),
                    "credit": func_tax,
                    "foreign_credit": sale.tax if currency_code != "EGP" else None,
                    "currency_code": currency_code,
                    "exchange_rate": rate,
                    "description": f"ضريبة مبيعات مستحقة #{sale.number}"
                })

            draft_entry = LedgerCoreService.create_draft_entry(
                date=sale.date,
                description=f"قيد فاتورة مبيعات رقم #{sale.number}",
                reference=f"SALE-{sale.number}",
                entry_type="SALES",
                created_by=user,
                lines_data=lines,
                source_module="SALE",
                source_model="Sale",
                source_id=sale.id
            )
            posted_entry = LedgerCoreService.post_entry(draft_entry.id, user=user)

            sale.journal_entry = posted_entry
            sale.save(update_fields=["journal_entry"])

            logger.info(f"Posted Sales Accounting Bridge entry #{posted_entry.id} for Sale #{sale.number}")
            return {"status": "POSTED", "journal_entry_id": posted_entry.id}
