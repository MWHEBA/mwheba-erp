"""
LedgerQueryService - الخدمة المركزية الحاكمة لاستعلامات دفتر الأستاذ العام (FIN-CORE-014 Read Contract)
توفر حقائق دفتر الأستاذ العام حصرياً (حركة الحساب، تجميع المدين والدائن، الرصيد الجاري، وأرصدة البداية والنهاية)
"""

import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional, Union
from django.db.models import Sum, Q
from django.utils import timezone

from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.journal_entry import JournalEntry, JournalEntryLine

logger = logging.getLogger("financial.ledger_query_service")


class LedgerQueryService:
    """
    عقد الاستعلام المركزي لدفتر الأستاذ العام.
    يحتوي حصرياً على حقائق ومعادلات دفتر الأستاذ دون معالجة فترات الـ Aging التشغيلية.
    """

    @classmethod
    def _resolve_account(cls, account_or_id: Union[ChartOfAccounts, int, str]) -> ChartOfAccounts:
        if isinstance(account_or_id, ChartOfAccounts):
            return account_or_id
        if isinstance(account_or_id, int):
            return ChartOfAccounts.objects.get(pk=account_or_id)
        if isinstance(account_or_id, str):
            acc = ChartOfAccounts.objects.filter(code=account_or_id).first()
            if acc:
                return acc
            if account_or_id.isdigit():
                return ChartOfAccounts.objects.get(pk=int(account_or_id))
            return ChartOfAccounts.objects.get(code=account_or_id)
        raise ValueError(f"Invalid account parameter: {account_or_id}")

    @classmethod
    def get_account_balance(
        cls,
        account_or_id: Union[ChartOfAccounts, int, str],
        as_of_date: Optional[Any] = None,
        include_unposted: bool = False
    ) -> Dict[str, Any]:
        """
        حساب رصيد الحساب المالي حتى تاريخ محدد من واقع بنود القيود المرحلة (GL Facts)
        """
        account = cls._resolve_account(account_or_id)

        filters = Q(account=account)

        if not include_unposted:
            filters &= Q(journal_entry__status='posted')

        if as_of_date:
            filters &= Q(journal_entry__date__lte=as_of_date)

        aggregates = JournalEntryLine.objects.filter(filters).aggregate(
            total_debit=Sum('debit'),
            total_credit=Sum('credit')
        )

        total_debit = aggregates['total_debit'] or Decimal('0.00')
        total_credit = aggregates['total_credit'] or Decimal('0.00')

        # تحديد طبيعة الحساب والرصيد الصافي
        category = getattr(getattr(account, 'account_type', None), 'category', 'asset')
        is_debit_nature = str(category).lower() in ['asset', 'expense']

        if is_debit_nature:
            balance = total_debit - total_credit
            nature = 'debit'
        else:
            balance = total_credit - total_debit
            nature = 'credit'

        return {
            'account_id': account.id,
            'account_code': account.code,
            'account_name': account.name,
            'debit': total_debit,
            'credit': total_credit,
            'balance': balance,
            'nature': nature
        }

    @classmethod
    def get_account_statement(
        cls,
        account_or_id: Union[ChartOfAccounts, int, str],
        start_date: Optional[Any] = None,
        end_date: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        توليد كشف حساب تفصيلي جاري مع حساب رصيد الافتتاح وحركة الفترة ورصيد الإغلاق
        """
        account = cls._resolve_account(account_or_id)

        # حساب رصيد الافتتاح قبل start_date
        opening_balance = Decimal('0.00')
        if start_date:
            op_data = cls.get_account_balance(account, as_of_date=start_date - timezone.timedelta(days=1))
            opening_balance = op_data['balance']

        # استعلام حركات الفترة الحالية
        filters = Q(account=account, journal_entry__status='posted')
        if start_date:
            filters &= Q(journal_entry__date__gte=start_date)
        if end_date:
            filters &= Q(journal_entry__date__lte=end_date)

        lines = JournalEntryLine.objects.filter(filters).select_related(
            'journal_entry'
        ).order_by('journal_entry__date', 'id')

        category = getattr(getattr(account, 'account_type', None), 'category', 'asset')
        is_debit_nature = category in ['asset', 'expense']

        transactions = []
        running_balance = opening_balance

        for line in lines:
            if is_debit_nature:
                running_balance += (line.debit - line.credit)
            else:
                running_balance += (line.credit - line.debit)

            transactions.append({
                'line_id': line.id,
                'journal_entry_id': line.journal_entry_id,
                'journal_entry_number': line.journal_entry.number,
                'date': line.journal_entry.date,
                'description': line.description or line.journal_entry.description,
                'reference': line.journal_entry.reference or line.journal_entry.posting_reference,
                'debit': line.debit,
                'credit': line.credit,
                'running_balance': running_balance
            })

        closing_balance = running_balance

        return {
            'account_id': account.id,
            'account_code': account.code,
            'account_name': account.name,
            'opening_balance': opening_balance,
            'transactions': transactions,
            'closing_balance': closing_balance
        }

    @classmethod
    def get_control_account_reconciliation(
        cls,
        control_account_or_id: Union[ChartOfAccounts, int, str],
        sub_accounts: List[Union[ChartOfAccounts, int, str]]
    ) -> Dict[str, Any]:
        """
        مطابقة رصيد حساب التحكم الإجمالي مع مجموع أرصدة الحسابات الفرعية
        """
        control_account = cls._resolve_account(control_account_or_id)
        control_data = cls.get_account_balance(control_account)
        control_balance = control_data['balance']

        sub_details = []
        sub_total = Decimal('0.00')

        for sub in sub_accounts:
            sub_acc = cls._resolve_account(sub)
            sub_data = cls.get_account_balance(sub_acc)
            sub_balance = sub_data['balance']
            sub_total += sub_balance
            sub_details.append({
                'account_id': sub_acc.id,
                'account_code': sub_acc.code,
                'account_name': sub_acc.name,
                'balance': sub_balance
            })

        difference = control_balance - sub_total
        is_reconciled = abs(difference) < Decimal('0.001')

        return {
            'is_reconciled': is_reconciled,
            'control_account_id': control_account.id,
            'control_account_code': control_account.code,
            'control_balance': control_balance,
            'sub_accounts_total': sub_total,
            'difference': difference,
            'sub_accounts': sub_details
        }
