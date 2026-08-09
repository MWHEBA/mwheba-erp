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
from django.db import transaction, models

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
        if isinstance(as_of_date, str):
            from datetime import datetime
            try:
                as_of_date = datetime.strptime(as_of_date, "%Y-%m-%d").date()
            except ValueError:
                as_of_date = timezone.now().date()
        else:
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

        # 3. Foreign Monetary Cash & Bank Accounts
        from financial.models.chart_of_accounts import ChartOfAccounts
        cash_items = []
        foreign_accounts = ChartOfAccounts.objects.filter(
            is_active=True,
            currency__isnull=False
        ).exclude(currency__code=func_code)

        for acc in foreign_accounts:
            if not (acc.is_cash_account or acc.is_bank_account):
                continue
            curr_code = acc.currency.code
            curr_rate = ExchangeRateService.get_rate(curr_code, func_code, as_of_date)
            
            # calculate foreign balance
            open_foreign = acc.opening_balance_foreign if (acc.opening_balance_foreign and acc.opening_balance_foreign != Decimal("0.00")) else (acc.opening_balance or Decimal("0.00"))
            
            # Get ledger debit/credit movements
            lines_aggr = acc.journal_lines.filter(journal_entry__status="posted", journal_entry__date__lte=as_of_date).aggregate(
                f_debit=models.Sum("transaction_debit"),
                f_credit=models.Sum("transaction_credit"),
                b_debit=models.Sum("debit"),
                b_credit=models.Sum("credit")
            )
            f_deb = lines_aggr["f_debit"] or Decimal("0.00")
            f_cred = lines_aggr["f_credit"] or Decimal("0.00")
            b_deb = lines_aggr["b_debit"] or Decimal("0.00")
            b_cred = lines_aggr["b_credit"] or Decimal("0.00")

            nature = acc.account_type.nature if acc.account_type else "debit"
            if nature == "debit":
                foreign_bal = open_foreign + f_deb - f_cred
                current_gl_base = acc.opening_balance + b_deb - b_cred
            else:
                foreign_bal = open_foreign + f_cred - f_deb
                current_gl_base = acc.opening_balance + b_cred - b_deb

            if foreign_bal != Decimal("0.00"):
                closing_func_val = (foreign_bal * curr_rate).quantize(Decimal("0.01"))
                diff = closing_func_val - current_gl_base
                if diff != Decimal("0.00"):
                    cash_items.append({
                        "account_id": acc.id,
                        "account_code": acc.code,
                        "account_name": acc.name,
                        "type": "CASH",
                        "currency": curr_code,
                        "open_foreign": foreign_bal,
                        "closing_rate": curr_rate,
                        "current_gl_base": current_gl_base,
                        "closing_functional": closing_func_val,
                        "unrealized_diff": diff
                    })
                    total_unrealized_gain_loss += diff

        return {
            "as_of_date": as_of_date,
            "functional_currency": func_code,
            "customer_items": customer_items,
            "supplier_items": supplier_items,
            "cash_items": cash_items,
            "total_unrealized_gain_loss": total_unrealized_gain_loss
        }

    @classmethod
    def _get_or_create_fx_unrealized_account(cls):
        from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
        acc = ChartOfAccounts.objects.filter(
            is_leaf=True,
            is_active=True
        ).filter(
            models.Q(code__in=["71020", "71020_UNREALIZED_FX_GAIN_LOSS", "420101", "520101"]) |
            models.Q(name__icontains="فروق تقييم") |
            models.Q(name__icontains="فروق عملة")
        ).first()
        if not acc:
            acc_type = AccountType.objects.filter(category__in=["revenue", "expense", "other_income"]).first() or AccountType.objects.first()
            acc = ChartOfAccounts.objects.create(
                code="71020_UNREALIZED_FX_GAIN_LOSS",
                name="حساب فروق تقييم أسعار الصرف غير المحققة (IAS 21)",
                account_type=acc_type,
                is_active=True,
                is_leaf=True
            )
        return acc

    @classmethod
    def _get_or_create_ar_revaluation_account(cls):
        from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
        acc = ChartOfAccounts.objects.filter(
            is_leaf=True,
            is_active=True
        ).filter(
            models.Q(code__in=["1101001", "1103001", "11010_AR", "120100"]) |
            models.Q(name__icontains="عملاء") |
            models.Q(name__icontains="مدينون")
        ).first()
        if not acc:
            acc_type = AccountType.objects.filter(category="asset").first() or AccountType.objects.first()
            acc = ChartOfAccounts.objects.create(
                code="11010_AR",
                name="حساب ذمم العملاء والتقييم المحاسبي",
                account_type=acc_type,
                is_active=True,
                is_leaf=True
            )
        return acc

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
            ar_account = cls._get_or_create_ar_revaluation_account()
            fx_account = cls._get_or_create_fx_unrealized_account()

            if total_diff > Decimal("0.00"):
                # Debit AR Revaluation Adjustment / Credit Unrealized Gain
                lines.append({
                    "account": ar_account,
                    "debit": total_diff,
                    "credit": Decimal("0.00"),
                    "description": f"تسوية تقييم ذمم عملاء غير محققة - فترة {data['as_of_date']}"
                })
                lines.append({
                    "account": fx_account,
                    "debit": Decimal("0.00"),
                    "credit": total_diff,
                    "description": f"أرباح فروق تقييم غير محققة (IAS 21) - فترة {data['as_of_date']}"
                })
            else:
                abs_diff = abs(total_diff)
                # Debit Unrealized Loss / Credit AR Revaluation Adjustment
                lines.append({
                    "account": fx_account,
                    "debit": abs_diff,
                    "credit": Decimal("0.00"),
                    "description": f"خسائر فروق تقييم غير محققة (IAS 21) - فترة {data['as_of_date']}"
                })
                lines.append({
                    "account": ar_account,
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
                source_id=int(data["as_of_date"].strftime("%Y%m%d")) if hasattr(data["as_of_date"], "strftime") else int(str(data["as_of_date"]).replace("-", ""))
            )
            posted_entry = LedgerCoreService.post_entry(draft_entry.id, user=user)

            logger.info(f"Posted FX Revaluation Entry #{posted_entry.id} for date {data['as_of_date']}")
            return {
                "status": "POSTED",
                "journal_entry_id": posted_entry.id,
                "total_unrealized_gain_loss": total_diff
            }
