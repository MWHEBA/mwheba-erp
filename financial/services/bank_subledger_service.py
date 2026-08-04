"""
BankSubledgerService - محرك دفتر الأستاذ الفرعي للبنوك والخزن (Sprint 2 Subledgers Engine)
يدير استعلامات الخزن والبنوك ويحضر كشوفات الحساب وملخصات النقدية
يفوض استعلامات دفتر الأستاذ العام 100% لـ LedgerQueryService (FIN-CORE-014)
يرتبط مستقبلاً بتذكرة التوفيق والتسوية البنكية (FIN-BANK-001 Bank Reconciliation Engine)
"""

import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional, Union
from django.utils import timezone
from django.db.models import Q

from financial.models.chart_of_accounts import ChartOfAccounts
from financial.services.ledger_query_service import LedgerQueryService

logger = logging.getLogger("financial.bank_subledger_service")


class BankSubledgerService:
    """
    خدمة دفتر الأستاذ الفرعي للبنوك والخزن
    """

    @classmethod
    def resolve_bank_or_cash_account(cls, account_code_or_id: Union[ChartOfAccounts, int, str]) -> ChartOfAccounts:
        """
        حل وتدقيق وجود حساب الخزينة أو البنك
        """
        account = LedgerQueryService._resolve_account(account_code_or_id)
        if not (getattr(account, 'is_cash_account', False) or getattr(account, 'is_bank_account', False)):
            # التأكد من طبيعة الحساب الأصول النقدية
            logger.warning(f"Account {account.code} is queried in BankSubledgerService but not marked as cash/bank.")
        return account

    @classmethod
    def get_bank_balance(
        cls,
        account_code_or_id: Union[ChartOfAccounts, int, str],
        as_of_date: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        استعلام رصيد البنك أو الخزينة الحالي عبر LedgerQueryService
        """
        account = cls.resolve_bank_or_cash_account(account_code_or_id)
        balance_data = LedgerQueryService.get_account_balance(account, as_of_date=as_of_date)
        balance_data['is_bank'] = getattr(account, 'is_bank_account', False)
        balance_data['is_cash'] = getattr(account, 'is_cash_account', False)
        return balance_data

    @classmethod
    def get_bank_statement(
        cls,
        account_code_or_id: Union[ChartOfAccounts, int, str],
        start_date: Optional[Any] = None,
        end_date: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        استخراج كشف حساب جاري للبنك أو الخزينة عبر LedgerQueryService
        """
        account = cls.resolve_bank_or_cash_account(account_code_or_id)
        statement_data = LedgerQueryService.get_account_statement(account, start_date=start_date, end_date=end_date)
        statement_data['is_bank'] = getattr(account, 'is_bank_account', False)
        statement_data['is_cash'] = getattr(account, 'is_cash_account', False)
        return statement_data

    @classmethod
    def get_cash_and_bank_summary(cls, as_of_date: Optional[Any] = None) -> Dict[str, Any]:
        """
        استخراج ملخص لجميع حسابات النقدية والبنوك في النظام
        """
        ref_date = as_of_date or timezone.now().date()
        accounts = ChartOfAccounts.objects.filter(
            Q(account_type__category='asset'),
            Q(code__startswith='101') | Q(code__startswith='102') | Q(name__icontains='خزينة') | Q(name__icontains='بنك'),
            is_active=True
        )

        cash_accounts = []
        bank_accounts = []
        total_cash_balance = Decimal('0.00')
        total_bank_balance = Decimal('0.00')

        for acc in accounts:
            bal_data = LedgerQueryService.get_account_balance(acc, as_of_date=ref_date)
            bal_amount = bal_data['balance']

            is_bank = 'بنك' in acc.name or getattr(acc, 'is_bank_account', False) or acc.code.startswith('102')

            acc_info = {
                'account_id': acc.id,
                'account_code': acc.code,
                'account_name': acc.name,
                'balance': bal_amount
            }

            if is_bank:
                bank_accounts.append(acc_info)
                total_bank_balance += bal_amount
            else:
                cash_accounts.append(acc_info)
                total_cash_balance += bal_amount

        return {
            'as_of_date': ref_date,
            'cash_accounts': cash_accounts,
            'bank_accounts': bank_accounts,
            'total_cash_balance': total_cash_balance,
            'total_bank_balance': total_bank_balance,
            'grand_total': total_cash_balance + total_bank_balance
        }
