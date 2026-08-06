"""
FXRevaluationService - محرك إعادة التقييم الدوري لفروق أسعار الصرف غير المحققة (IAS 21)
يقوم بفحص الذمم والفواتير المفتوحة (Customer & Supplier Open Transactions) بتاريخ الإقفال،
ويحسب فروق التقييم الناتجة عن تغير سعر الصرف بين تاريخ الفاتورة وتاريخ الإقفال،
ويولد قيد تسوية محوكم على حساب فروق التقييم غير المحققة (71020_UNREALIZED_FX_GAIN_LOSS).
"""

import logging
from decimal import Decimal
from typing import Dict, Any, List
from django.utils import timezone
from django.db import transaction

from financial.services.exchange_rate_service import ExchangeRateService
from financial.services.ledger_core_service import LedgerCoreService
from client.models import CustomerTransaction
from supplier.models import SupplierTransaction

logger = logging.getLogger("financial.services.fx_revaluation")


class FXRevaluationService:
    """
    خدمة إعادة التقييم الدوري وفق المعيار المحاسبي الدولي IAS 21
    """

    @classmethod
    def calculate_open_items_revaluation(cls, as_of_date=None) -> Dict[str, Any]:
        """
        حساب فروق التقييم غير المحققة لكافة الفواتير والذمم المفتوحة حتى تاريخ معين
        """
        as_of_date = as_of_date or timezone.now().date()
        func_curr = ExchangeRateService.get_functional_currency()
        if not func_curr:
            from django.core.exceptions import ValidationError
            raise ValidationError("لم يتم تعيين العملة الأساسية الوظيفية للمؤسسة.")

        func_code = func_curr.code
        customer_items = []
        supplier_items = []
        total_unrealized_gain_loss = Decimal("0.00")

        # 1. Open Customer Transactions (AR)
        ar_open_txs = CustomerTransaction.objects.filter(
            issue_date__lte=as_of_date,
            open_amount_foreign__gt=Decimal("0.00")
        ).exclude(currency=func_code)

        for tx in ar_open_txs:
            curr_rate = ExchangeRateService.get_rate(tx.currency, func_code, as_of_date)
            original_func_val = (tx.open_amount_foreign * (tx.exchange_rate or Decimal("1.000000"))).quantize(Decimal("0.01"))
            closing_func_val = (tx.open_amount_foreign * curr_rate).quantize(Decimal("0.01"))
            diff = closing_func_val - original_func_val

            customer_items.append({
                "transaction_id": tx.id,
                "type": "AR",
                "customer": tx.customer.name,
                "currency": tx.currency,
                "open_foreign": tx.open_amount_foreign,
                "original_rate": tx.exchange_rate,
                "closing_rate": curr_rate,
                "original_functional": original_func_val,
                "closing_functional": closing_func_val,
                "unrealized_diff": diff
            })
            total_unrealized_gain_loss += diff

        # 2. Open Supplier Transactions (AP)
        ap_open_txs = SupplierTransaction.objects.filter(
            issue_date__lte=as_of_date,
            open_amount_foreign__gt=Decimal("0.00")
        ).exclude(currency=func_code)

        for tx in ap_open_txs:
            curr_rate = ExchangeRateService.get_rate(tx.currency, func_code, as_of_date)
            original_func_val = (tx.open_amount_foreign * (tx.exchange_rate or Decimal("1.000000"))).quantize(Decimal("0.01"))
            closing_func_val = (tx.open_amount_foreign * curr_rate).quantize(Decimal("0.01"))
            diff = original_func_val - closing_func_val  # For liabilities, lower closing func val is a gain

            supplier_items.append({
                "transaction_id": tx.id,
                "type": "AP",
                "supplier": tx.supplier.name,
                "currency": tx.currency,
                "open_foreign": tx.open_amount_foreign,
                "original_rate": tx.exchange_rate,
                "closing_rate": curr_rate,
                "original_functional": original_func_val,
                "closing_functional": closing_func_val,
                "unrealized_diff": diff
            })
            total_unrealized_gain_loss += diff

        return {
            "as_of_date": as_of_date,
            "functional_currency": func_code,
            "customer_items": customer_items,
            "supplier_items": supplier_items,
            "total_unrealized_gain_loss": total_unrealized_gain_loss
        }

    @classmethod
    def post_period_end_revaluation(cls, as_of_date=None, user=None) -> Dict[str, Any]:
        """
        إنشاء وترحيل قيد التقييم الدوري لفروق أسعار الصرف غير المحققة
        """
        data = cls.calculate_open_items_revaluation(as_of_date)
        total_diff = data["total_unrealized_gain_loss"]

        if total_diff == Decimal("0.00"):
            return {"status": "NO_VARIANCE", "message": "لا توجد فروق تقييم غير محققة للفترة."}

        with transaction.atomic():
            lines = []
            func_code = data["functional_currency"]

            if total_diff > Decimal("0.00"):
                # Debit AR Revaluation Adjustment / Credit Unrealized Gain
                lines.append({
                    "account_code": "11010_AR",
                    "debit": total_diff,
                    "credit": Decimal("0.00"),
                    "description": f"تسوية تقييم ذمم عملاء غير محققة - فترة {data['as_of_date']}"
                })
                lines.append({
                    "account_code": "71020_UNREALIZED_FX_GAIN_LOSS",
                    "debit": Decimal("0.00"),
                    "credit": total_diff,
                    "description": f"أرباح فروق تقييم غير محققة (IAS 21) - فترة {data['as_of_date']}"
                })
            else:
                abs_diff = abs(total_diff)
                # Debit Unrealized Loss / Credit AR Revaluation Adjustment
                lines.append({
                    "account_code": "71020_UNREALIZED_FX_GAIN_LOSS",
                    "debit": abs_diff,
                    "credit": Decimal("0.00"),
                    "description": f"خسائر فروق تقييم غير محققة (IAS 21) - فترة {data['as_of_date']}"
                })
                lines.append({
                    "account_code": "11010_AR",
                    "debit": Decimal("0.00"),
                    "credit": abs_diff,
                    "description": f"تسوية تقييم ذمم عملاء غير محققة - فترة {data['as_of_date']}"
                })

            draft_entry = LedgerCoreService.create_draft_entry(
                date=data["as_of_date"],
                description=f"قيد إعادة التقييم الدوري لفروق الصرف غير المحققة (IAS 21) - {data['as_of_date']}",
                reference=f"FXREV-{data['as_of_date']}",
                entry_type="GENERAL",
                created_by=user,
                lines_data=lines,
                source_module="FINANCIAL",
                source_model="FXRevaluation",
                source_id=int(data["as_of_date"].strftime("%Y%m%d"))
            )
            posted_entry = LedgerCoreService.post_entry(draft_entry.id, user=user)

            logger.info(f"Posted FX Revaluation Entry #{posted_entry.id} for date {data['as_of_date']}")
            return {
                "status": "POSTED",
                "journal_entry_id": posted_entry.id,
                "total_unrealized_gain_loss": total_diff
            }
