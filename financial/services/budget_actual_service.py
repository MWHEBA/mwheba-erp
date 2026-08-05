from decimal import Decimal
from typing import Optional, Dict, Any
from django.db import models
from django.db.models import Sum, Q
from django.utils import timezone
from financial.models.cost_center import CostCenter
from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.journal_entry import AccountingPeriod, JournalEntryLine
from financial.models.cost_center_budget import CostCenterActualSnapshot


class BudgetActualService:
    """
    خدمة احتساب المنفق الفعلي والالتزامات السريعة (< 50ms) وتحديث كاش الرصيد
    """

    @classmethod
    def update_actual_snapshot(
        cls,
        cost_center: CostCenter,
        account: ChartOfAccounts,
        accounting_period: AccountingPeriod,
    ) -> CostCenterActualSnapshot:
        """
        حساب المنفق الفعلي من أسطر القيود المرحّلة وتحديث لقطة الأرصدة السريعة
        """
        lines = JournalEntryLine.objects.filter(
            journal_entry__status='posted',
            journal_entry__accounting_period=accounting_period,
            account=account
        ).filter(
            models.Q(cost_center=cost_center) | models.Q(cost_allocations__cost_center=cost_center)
        ).distinct()

        actual_sum = Decimal('0.00')
        for line in lines.select_related('journal_entry'):
            if line.cost_center == cost_center:
                net_amount = (line.debit if account.account_type and account.account_type.nature == 'DEBIT' else line.credit) - (line.credit if account.account_type and account.account_type.nature == 'DEBIT' else line.debit)
                actual_sum += net_amount
            for alloc in line.cost_allocations.filter(cost_center=cost_center):
                net_amount = (alloc.amount or Decimal('0.00'))
                if account.account_type and account.account_type.nature == 'DEBIT':
                    actual_sum += net_amount if line.debit > 0 else -net_amount
                else:
                    actual_sum += net_amount if line.credit > 0 else -net_amount

        snapshot, _ = CostCenterActualSnapshot.objects.get_or_create(
            cost_center=cost_center,
            account=account,
            accounting_period=accounting_period
        )
        snapshot.actual_amount = actual_sum
        snapshot.save(update_fields=['actual_amount', 'updated_at'])

        return snapshot

    @classmethod
    def get_actual_and_committed(
        cls,
        cost_center: CostCenter,
        account: ChartOfAccounts,
        accounting_period: AccountingPeriod
    ) -> Dict[str, Decimal]:
        """
        جلب الرصيد الفعلي والالتزامات المعلقة فورياً بأداء فائق
        """
        snapshot = cls.update_actual_snapshot(cost_center, account, accounting_period)
        return {
            'actual': snapshot.actual_amount,
            'committed': snapshot.committed_amount,
            'total_used': snapshot.actual_amount + snapshot.committed_amount
        }
