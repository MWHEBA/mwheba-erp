"""
FIN-CORE-018: CashTransferService
خدمة تحويل الأموال بين الخزائن والحسابات البنكية متعددة العملات
مع حوكمة قيود الأستاذ العام وتصفية فروق أسعار الصرف المحققة (Realized FX Gain/Loss)
"""
import logging
from decimal import Decimal
from typing import Dict, Any, Optional
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from financial.models.chart_of_accounts import ChartOfAccounts
from financial.services.exchange_rate_service import ExchangeRateService
from governance.services.accounting_gateway import AccountingGateway, JournalEntryLineData, SourceInfo

logger = logging.getLogger("financial.services.cash_transfer_service")


class CashTransferService:
    """
    خدمة التحويلات النقدية والبنكية بين الحسابات المتقابلة متعددة العملات
    """

    @classmethod
    @transaction.atomic
    def execute_transfer(
        cls,
        from_account_id: int,
        to_account_id: int,
        transfer_amount: Decimal,
        transfer_date=None,
        exchange_rate: Optional[Decimal] = None,
        notes: str = "",
        user=None
    ) -> Dict[str, Any]:
        """
        تنفيذ تحويل نقدي/بنكي بين حسابين وتسجيل قيد متوازن بخصم فروق أسعار الصرف
        """
        if transfer_amount <= Decimal("0.00"):
            raise ValidationError("مبلغ التحويل يجب أن يكون أكبر من صفر.")

        if from_account_id == to_account_id:
            raise ValidationError("لا يمكن التحويل لنفس الحساب.")

        from_acc = ChartOfAccounts.objects.select_for_update().get(pk=from_account_id)
        to_acc = ChartOfAccounts.objects.select_for_update().get(pk=to_account_id)

        if not (from_acc.is_cash_account or from_acc.is_bank_account):
            raise ValidationError(f"الحساب المصدر '{from_acc.name}' ليس حساباً نقدياً أو بنكياً.")

        if not (to_acc.is_cash_account or to_acc.is_bank_account):
            raise ValidationError(f"الحساب المستلم '{to_acc.name}' ليس حساباً نقدياً أو بنكياً.")

        transfer_date = transfer_date or timezone.now().date()
        func_curr = ExchangeRateService.get_functional_currency()
        func_code = func_curr.code if func_curr else "EGP"

        from_curr_code = from_acc.currency_code
        to_curr_code = to_acc.currency_code

        from_rate = Decimal("1.000000") if from_curr_code == func_code else ExchangeRateService.get_rate(from_curr_code, func_code, transfer_date)
        to_rate = exchange_rate if (exchange_rate and exchange_rate > 0) else (Decimal("1.000000") if to_curr_code == func_code else ExchangeRateService.get_rate(to_curr_code, func_code, transfer_date))

        # Base functional amounts
        from_base_amt = (transfer_amount * from_rate).quantize(Decimal("0.01"))
        to_foreign_amt = (from_base_amt / to_rate).quantize(Decimal("0.01")) if to_curr_code != from_curr_code else transfer_amount
        to_base_amt = (to_foreign_amt * to_rate).quantize(Decimal("0.01"))

        diff_base = (from_base_amt - to_base_amt).quantize(Decimal("0.01"))

        lines = []

        # 1. Credit Source Account (دائن الخزنة المحول منها)
        lines.append(JournalEntryLineData(
            account_code=from_acc.code,
            debit=Decimal("0.00"),
            credit=from_base_amt,
            description=f"تحويل نقدي صادرة إلى {to_acc.name} - {notes}".strip(),
            currency=from_curr_code,
            exchange_rate=from_rate,
            foreign_credit=transfer_amount
        ))

        # 2. Debit Target Account (مدين الخزنة المستلمة)
        lines.append(JournalEntryLineData(
            account_code=to_acc.code,
            debit=to_base_amt,
            credit=Decimal("0.00"),
            description=f"تحويل نقدي وارد من {from_acc.name} - {notes}".strip(),
            currency=to_curr_code,
            exchange_rate=to_rate,
            foreign_debit=to_foreign_amt
        ))

        # 3. Balancing Realized FX Line if base variance exists
        if diff_base != Decimal("0.00"):
            abs_diff = abs(diff_base)
            fx_acc = ChartOfAccounts.objects.filter(code__in=["40500", "50500", "71020"], is_active=True).first()
            fx_code = fx_acc.code if fx_acc else "40500"

            if diff_base > Decimal("0.00"):
                # Debit FX Realized Loss
                lines.append(JournalEntryLineData(
                    account_code=fx_code,
                    debit=abs_diff,
                    credit=Decimal("0.00"),
                    description=f"أرباح/خسائر تحويل عملات محققة - {from_curr_code} -> {to_curr_code}"
                ))
            else:
                # Credit FX Realized Gain
                lines.append(JournalEntryLineData(
                    account_code=fx_code,
                    debit=Decimal("0.00"),
                    credit=abs_diff,
                    description=f"أرباح/خسائر تحويل عملات محققة - {from_curr_code} -> {to_curr_code}"
                ))

        gateway = AccountingGateway()
        source_info = SourceInfo(
            module="financial",
            model="CashTransfer",
            object_id=int(timezone.now().timestamp())
        )

        entry = gateway.create_journal_entry(
            entry_type="GENERAL",
            date=transfer_date,
            description=f"تحويل بين الخزائن: من {from_acc.name} إلى {to_acc.name} ({transfer_amount} {from_curr_code})",
            lines=lines,
            source_info=source_info,
            user=user
        )

        logger.info(f"✅ Executed Cash Transfer Entry #{entry.id}: {from_acc.name} -> {to_acc.name} ({transfer_amount} {from_curr_code})")

        return {
            "status": "SUCCESS",
            "journal_entry_id": entry.id,
            "transfer_amount": transfer_amount,
            "from_account": from_acc.name,
            "to_account": to_acc.name,
            "from_base_amount": from_base_amt,
            "to_base_amount": to_base_amt,
        }
