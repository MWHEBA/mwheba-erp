"""
AccountBalanceSyncService - محرك مزامنة الأرصدة اللحظية والزحزحة الأمامية (FIN-REP-005)
يقوم بالتحديث الذري السريع لسجلات AccountBalancePeriod مع كل قيد مرحل
ودعم ضبط وتمرير الأرصدة للشهور اللاحقة (Forward Propagation) عند وجود قيود بأثر رجعي.
"""

import logging
from decimal import Decimal
from typing import Optional
from django.db import transaction, models
from django.utils import timezone

from financial.models.account_balance_period import AccountBalancePeriod
from financial.models.journal_entry import JournalEntry, JournalEntryLine
from financial.models.chart_of_accounts import ChartOfAccounts

logger = logging.getLogger("financial.account_balance_sync")


class AccountBalanceSyncService:
    """
    خدمة مزامنة الأرصدة التجميعية اللحظية للحسابات (Fast Snapshot Balance Sync Engine)
    """

    @classmethod
    def sync_journal_entry(cls, journal_entry: JournalEntry) -> None:
        """
        مزامنة وتحديث أرصدة الحسابات المتأثرة بالقيد المرحل
        """
        if not journal_entry:
            return

        entry_date = getattr(journal_entry, 'date', None) or timezone.now().date()
        year = entry_date.year
        month = entry_date.month

        lines = journal_entry.lines.select_related("account").all()
        affected_accounts = set()

        for line in lines:
            acc = line.account
            if not acc:
                continue

            curr_code = getattr(line, 'currency', 'EGP') or 'EGP'
            debit = line.debit or Decimal("0.00")
            credit = line.credit or Decimal("0.00")

            if debit == Decimal("0.00") and credit == Decimal("0.00"):
                continue

            # 1. Get or create snapshot record for (account, year, month, currency)
            period_bal, created = AccountBalancePeriod.objects.get_or_create(
                account=acc,
                year=year,
                month=month,
                currency_code=curr_code,
                defaults={
                    "beginning_debit": Decimal("0.00"),
                    "beginning_credit": Decimal("0.00"),
                    "period_debit": Decimal("0.00"),
                    "period_credit": Decimal("0.00"),
                    "ending_debit": Decimal("0.00"),
                    "ending_credit": Decimal("0.00"),
                    "net_balance": Decimal("0.00"),
                }
            )

            # 2. Atomic increment
            AccountBalancePeriod.objects.filter(pk=period_bal.pk).update(
                period_debit=models.F("period_debit") + debit,
                period_credit=models.F("period_credit") + credit
            )

            # Refresh and recalculate ending balances
            period_bal.refresh_from_db()
            period_bal.recalculate_totals()
            period_bal.save(update_fields=["ending_debit", "ending_credit", "net_balance", "updated_at"])

            affected_accounts.add((acc.id, year, month, curr_code))

        # 3. Propagate forward if this might be a backdated period
        now_date = timezone.now().date()
        for acc_id, y, m, c_code in affected_accounts:
            if y < now_date.year or (y == now_date.year and m < now_date.month):
                cls.propagate_forward(acc_id, y, m, c_code)

        logger.info(f"AccountBalanceSync: Synchronized balances for JournalEntry #{journal_entry.number} ({len(affected_accounts)} accounts updated).")

    @classmethod
    def propagate_forward(cls, account_id: int, from_year: int, from_month: int, currency_code: str = "EGP") -> None:
        """
        ضبط وتمرير رصيد النهاية كرصيد بداية لكافة الشهور التالية لنفس الحساب والعملة
        """
        # جلب الفترات اللاحقة مرتبة تصاعدياً
        future_periods = AccountBalancePeriod.objects.filter(
            account_id=account_id,
            currency_code=currency_code
        ).filter(
            models.Q(year__gt=from_year) | models.Q(year=from_year, month__gt=from_month)
        ).order_by("year", "month")

        if not future_periods.exists():
            return

        # رصيد نهاية الفترة المرجعية
        current_ref = AccountBalancePeriod.objects.filter(
            account_id=account_id,
            year=from_year,
            month=from_month,
            currency_code=currency_code
        ).first()

        if not current_ref:
            return

        prev_end_debit = current_ref.ending_debit
        prev_end_credit = current_ref.ending_credit

        for p in future_periods:
            p.beginning_debit = prev_end_debit
            p.beginning_credit = prev_end_credit
            p.recalculate_totals()
            p.save(update_fields=["beginning_debit", "beginning_credit", "ending_debit", "ending_credit", "net_balance", "updated_at"])
            prev_end_debit = p.ending_debit
            prev_end_credit = p.ending_credit

        logger.info(f"AccountBalanceSync: Propagated forward balances for Account #{account_id} ({currency_code}) from {from_year}/{from_month:02d}.")
