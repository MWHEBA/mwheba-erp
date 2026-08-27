"""
FIN-TAX-002: Monthly VAT Settlement & Period Clearing Service
خدمة احتساب وتوليد قيد المقاصة والتسوية الشهرية لضريبة القيمة المضافة وإقفال الفترة الضريبية
"""

import logging
from decimal import Decimal
from typing import Dict, Any, Optional
from datetime import date, datetime, time
from django.db import transaction, models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from financial.models import (
    JournalEntry,
    JournalEntryLine,
    AccountingPeriod,
    TaxDeterminationAudit,
    TaxEvent,
)
from financial.services.role_registry import AccountRoleRegistry
from financial.services.legacy_adapter import LegacyAccountingAdapter
from financial.exceptions import FinancialCoreError

logger = logging.getLogger("financial.services.vat_settlement")


class VATSettlementService:
    """
    سلطة احتساب وإجراء قيود المقاصة الشهرية بين ضريبة المخرجات وضريبة المدخلات
    """

    @classmethod
    def get_monthly_tax_summary(cls, start_date: date, end_date: date) -> Dict[str, Any]:
        """
        تجميع أوعية وضرائب المبيعات والمشتريات والمصروفات والخصم والتحصيل للفترة المحددة
        """
        from datetime import time
        start_dt = timezone.make_aware(datetime.combine(start_date, time.min)) if timezone.is_naive(datetime.combine(start_date, time.min)) else datetime.combine(start_date, time.min)
        end_dt = timezone.make_aware(datetime.combine(end_date, time.max)) if timezone.is_naive(datetime.combine(end_date, time.max)) else datetime.combine(end_date, time.max)

        audits_qs = TaxDeterminationAudit.objects.filter(
            created_at__gte=start_dt,
            created_at__lte=end_dt
        ).select_related("tax_code", "customer", "supplier")

        output_tax_base = Decimal("0.00")
        output_tax_total = Decimal("0.00")
        input_tax_base = Decimal("0.00")
        input_tax_total = Decimal("0.00")
        wht_payable_total = Decimal("0.00")
        wht_receivable_total = Decimal("0.00")
        exempt_sales_base = Decimal("0.00")
        zero_rated_sales_base = Decimal("0.00")

        for a in audits_qs:
            amt = a.functional_tax_amount
            base = a.taxable_amount
            code_nature = a.tax_code.tax_nature if a.tax_code else "OUTPUT"
            code_type = a.tax_code.tax_type if a.tax_code else "VAT"

            if a.document_type in ["SalesInvoice", "POSInvoice"]:
                if code_type == "EXEMPT":
                    exempt_sales_base += base
                elif code_type == "ZERO_RATED":
                    zero_rated_sales_base += base
                else:
                    output_tax_base += base
                    output_tax_total += amt
            elif a.document_type in ["PurchaseInvoice", "Expense", "LandedCost"]:
                input_tax_base += base
                if getattr(a.tax_code, 'is_recoverable', True):
                    input_tax_total += amt

        # Reversals during this period
        from financial.models import TaxReversal
        reversals = TaxReversal.objects.filter(
            created_at__gte=start_dt,
            created_at__lte=end_dt
        ).select_related("original_audit__tax_code")

        for rev in reversals:
            orig = rev.original_audit
            if orig.document_type in ["SalesInvoice", "POSInvoice"]:
                output_tax_total -= rev.reversal_amount
            elif orig.document_type in ["PurchaseInvoice", "Expense"]:
                input_tax_total -= rev.reversal_amount

        net_vat_due = output_tax_total - input_tax_total

        return {
            "start_date": start_date,
            "end_date": end_date,
            "output_tax_base": output_tax_base,
            "output_tax_total": max(Decimal("0.00"), output_tax_total),
            "input_tax_base": input_tax_base,
            "input_tax_total": max(Decimal("0.00"), input_tax_total),
            "exempt_sales_base": exempt_sales_base,
            "zero_rated_sales_base": zero_rated_sales_base,
            "net_vat_due": net_vat_due,
            "is_payable": net_vat_due > Decimal("0.00"),
            "net_payable_amount": net_vat_due if net_vat_due > Decimal("0.00") else Decimal("0.00"),
            "net_credit_carryforward": abs(net_vat_due) if net_vat_due < Decimal("0.00") else Decimal("0.00"),
            "audits_count": audits_qs.count()
        }

    @classmethod
    def post_monthly_vat_settlement(
        cls,
        start_date: date,
        end_date: date,
        user=None,
        notes: str = ""
    ) -> JournalEntry:
        """
        توليد قيد المقاصة والتسوية المحاسبية لضريبة القيمة المضافة للشهر المحدد
        """
        with transaction.atomic():
            summary = cls.get_monthly_tax_summary(start_date, end_date)
            out_tax = summary["output_tax_total"]
            in_tax = summary["input_tax_total"]

            if out_tax == Decimal("0.00") and in_tax == Decimal("0.00"):
                raise FinancialCoreError(_("لا توجد حركات ضريبية مستحقة للتسوية خلال هذه الفترة."))

            from financial.models import ChartOfAccounts
            out_acc_code = AccountRoleRegistry.get_account_code("OUTPUT_TAX_ACCOUNT") or "22010"
            in_acc_code = AccountRoleRegistry.get_account_code("INPUT_TAX_ACCOUNT") or "11050"
            tax_payable_code = "21310"
            tax_credit_code = "11550"

            out_acc_obj = ChartOfAccounts.objects.filter(code=out_acc_code, is_leaf=True, is_active=True).first() or ChartOfAccounts.objects.filter(account_type__category="liability", is_leaf=True, is_active=True).first()
            in_acc_obj = ChartOfAccounts.objects.filter(code=in_acc_code, is_leaf=True, is_active=True).first() or ChartOfAccounts.objects.filter(account_type__category="asset", is_leaf=True, is_active=True).first()
            tax_payable_obj = ChartOfAccounts.objects.filter(code=tax_payable_code, is_leaf=True, is_active=True).first() or out_acc_obj
            tax_credit_obj = ChartOfAccounts.objects.filter(code=tax_credit_code, is_leaf=True, is_active=True).first() or in_acc_obj

            lines = []

            # 1. Debit Output Tax (Close Output VAT)
            if out_tax > Decimal("0.00"):
                lines.append({
                    "account": out_acc_obj,
                    "debit": out_tax,
                    "credit": Decimal("0.00"),
                    "description": f"إقفال ومقاصة ضريبة المخرجات للفترة من {start_date} إلى {end_date}"
                })

            # 2. Credit Input Tax (Close Input VAT)
            if in_tax > Decimal("0.00"):
                lines.append({
                    "account": in_acc_obj,
                    "debit": Decimal("0.00"),
                    "credit": in_tax,
                    "description": f"إقفال ومقاصة ضريبة المدخلات للفترة من {start_date} إلى {end_date}"
                })

            # 3. Balancing Line
            net_due = summary["net_vat_due"]
            if net_due > Decimal("0.00"):
                # We owe tax authority (Credit Liability)
                lines.append({
                    "account": tax_payable_obj,
                    "debit": Decimal("0.00"),
                    "credit": net_due,
                    "description": f"صافي ضريبة القيمة المضافة المستحقة للسداد لمصلحة الضرائب عن فترة {end_date.strftime('%Y-%m')}"
                })
            elif net_due < Decimal("0.00"):
                # Tax authority owes us (Debit Asset / Carryforward)
                lines.append({
                    "account": tax_credit_obj,
                    "debit": abs(net_due),
                    "credit": Decimal("0.00"),
                    "description": f"رصيد ضريبة دائن مرحل للفترة التالية عن فترة {end_date.strftime('%Y-%m')}"
                })

            idem_key = f"JE:VAT_SETTLEMENT:{start_date.isoformat()}:{end_date.isoformat()}"

            entry = LegacyAccountingAdapter.post_journal_entry(
                description=f"قيد تسوية ومقاصة ضريبة القيمة المضافة لشهر {end_date.strftime('%Y-%m')}",
                date=end_date,
                lines=lines,
                user=user,
                idempotency_key=idem_key,
                source_module="financial",
                source_model="VATMonthlySettlement",
                source_id=int(end_date.strftime('%Y%m')),
                entry_type="automatic"
            )

            # Log TaxEvent
            TaxEvent.objects.create(
                event_type="VAT_MONTHLY_SETTLEMENT_POSTED",
                document_type="VATSettlement",
                document_number=f"VAT-SETTLE-{end_date.strftime('%Y-%m')}",
                status="PROCESSED"
            )

            logger.info(f"VAT Settlement Journal Entry #{entry.id} posted for period {start_date} to {end_date}.")
            return entry
