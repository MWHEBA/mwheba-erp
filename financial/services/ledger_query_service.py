"""
LedgerQueryService - الخدمة المركزية الحاكمة لاستعلامات دفتر الأستاذ العام (FIN-CORE-014 Read Contract)
توفر حقائق دفتر الأستاذ العام حصرياً (حركة الحساب، تجميع المدين والدائن، الرصيد الجاري، وأرصدة البداية والنهاية)
تدعم العملات المتعددة، الحسابات المجمعة، وفروق التقييم وفق معيار المحاسبة الدولي IAS 21
"""

import logging
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, List, Optional, Union
from django.db.models import Sum, Q
from django.utils import timezone

from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.journal_entry import JournalEntry, JournalEntryLine
from financial.services.exchange_rate_service import ExchangeRateService

logger = logging.getLogger("financial.ledger_query_service")


class LedgerQueryService:
    """
    عقد الاستعلام المركزي لدفتر الأستاذ العام وفق المعايير الدولية IAS 21.
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
        cost_center: Optional[Any] = None,
        currency: Optional[str] = None,
        include_unposted: bool = False
    ) -> Dict[str, Any]:
        """
        حساب رصيد الحساب المالي حتى تاريخ محدد من واقع بنود القيود (GL Facts)
        يدعم الحسابات الأب المجمعة وتعدد العملات
        """
        account = cls._resolve_account(account_or_id)

        # تحديد الحسابات المستهدفة (الحساب نفسه أو فروعه الطرفية إذا كان حساباً رئيسياً)
        if not account.is_leaf:
            leaf_accounts = list(account.get_leaf_descendants(include_self=True))
            target_accounts = leaf_accounts if leaf_accounts else [account]
            filters = Q(account__in=target_accounts)
        else:
            target_accounts = [account]
            filters = Q(account=account)

        if not include_unposted:
            filters &= Q(journal_entry__status='posted')

        if as_of_date:
            filters &= Q(journal_entry__date__lte=as_of_date)

        if cost_center:
            filters &= Q(cost_center_id=cost_center if isinstance(cost_center, int) else getattr(cost_center, 'id', cost_center))

        if currency:
            filters &= Q(currency=currency)

        aggregates = JournalEntryLine.objects.filter(filters).aggregate(
            total_debit=Sum('debit'),
            total_credit=Sum('credit'),
            total_foreign_debit=Sum('foreign_debit'),
            total_foreign_credit=Sum('foreign_credit'),
            total_trans_debit=Sum('transaction_debit'),
            total_trans_credit=Sum('transaction_credit')
        )

        total_debit = aggregates['total_debit'] or Decimal('0.00')
        total_credit = aggregates['total_credit'] or Decimal('0.00')
        total_f_debit = (aggregates['total_foreign_debit'] or Decimal('0.00')) or (aggregates['total_trans_debit'] or Decimal('0.00'))
        total_f_credit = (aggregates['total_foreign_credit'] or Decimal('0.00')) or (aggregates['total_trans_credit'] or Decimal('0.00'))

        # تحديد طبيعة الحساب والرصيد الصافي
        category = getattr(getattr(account, 'account_type', None), 'category', 'asset')
        is_debit_nature = str(category).lower() in ['asset', 'expense']

        # إضافة الرصيد الافتتاحي المعرف على مستوى كائن الحساب
        initial_op_local = Decimal('0.00')
        initial_op_foreign = Decimal('0.00')
        for acc in target_accounts:
            initial_op_local += (acc.opening_balance or Decimal('0.00'))
            initial_op_foreign += (acc.opening_balance_foreign or Decimal('0.00'))

        if is_debit_nature:
            balance = initial_op_local + total_debit - total_credit
            foreign_balance = initial_op_foreign + total_f_debit - total_f_credit
            nature = 'debit'
        else:
            balance = initial_op_local + total_credit - total_debit
            foreign_balance = initial_op_foreign + total_f_credit - total_f_debit
            nature = 'credit'

        return {
            'account_id': account.id,
            'account_code': account.code,
            'account_name': account.name,
            'debit': total_debit,
            'credit': total_credit,
            'balance': balance,
            'foreign_debit': total_f_debit,
            'foreign_credit': total_f_credit,
            'foreign_balance': foreign_balance,
            'nature': nature
        }

    @classmethod
    def get_account_statement(
        cls,
        account_or_id: Union[ChartOfAccounts, int, str],
        start_date: Optional[Any] = None,
        end_date: Optional[Any] = None,
        cost_center: Optional[Any] = None,
        currency: Optional[str] = None,
        include_unposted: bool = False
    ) -> Dict[str, Any]:
        """
        توليد كشف حساب تفصيلي جاري مع حساب رصيد الافتتاح وحركة الفترة ورصيد الإغلاق
        وفق المعايير الدولية IAS 21 مع الدعم الكامل لتعدد العملات والحسابات المجمعة
        """
        account = cls._resolve_account(account_or_id)

        # 1. جلب العملة الوظيفية للمؤسسة ديناميكياً
        func_curr = ExchangeRateService.get_functional_currency()
        base_code = func_curr.code if func_curr else "EGP"
        base_symbol = (func_curr.symbol or func_curr.code) if func_curr else "ج.م"

        # 2. تحديد العملة المخصصة للحساب
        account_currency_code = account.currency.code if account.currency else base_code
        account_currency_symbol = (account.currency.symbol or account.currency.code) if account.currency else base_symbol
        is_foreign_account = bool(account.currency and account.currency.code != base_code)

        # 3. تحديد الحسابات المستهدفة (الحساب نفسه أو فروعه الطرفية للحسابات الرئيسية)
        if not account.is_leaf:
            leaf_accounts = list(account.get_leaf_descendants())
            target_accounts = leaf_accounts if leaf_accounts else [account]
            filters = Q(account__in=target_accounts)
            is_consolidated = True
        else:
            target_accounts = [account]
            filters = Q(account=account)
            is_consolidated = False

        category = getattr(getattr(account, 'account_type', None), 'category', 'asset')
        is_debit_nature = str(category).lower() in ['asset', 'expense']

        is_opening_q = (
            Q(journal_entry__entry_type='opening') |
            Q(journal_entry__source_module='OPENING_BALANCE') |
            Q(journal_entry__reference_type='OPENING_BALANCE') |
            Q(journal_entry__reference__startswith='OPB') |
            Q(journal_entry__reference__startswith='OPN')
        )

        # 4. استعلام حركات الفترة والقيود
        if not include_unposted:
            filters &= Q(journal_entry__status='posted')

        if start_date:
            filters &= Q(journal_entry__date__gte=start_date)
        if end_date:
            filters &= Q(journal_entry__date__lte=end_date)
        if cost_center:
            filters &= Q(cost_center_id=cost_center if isinstance(cost_center, int) else getattr(cost_center, 'id', cost_center))
        if currency:
            filters &= Q(currency=currency)

        # 5. حساب رصيد الافتتاح (شاملاً القيود الافتتاحية)
        opening_balance = Decimal('0.00')
        opening_balance_foreign = Decimal('0.00')
        if start_date:
            from datetime import timedelta
            op_data = cls.get_account_balance(
                account,
                as_of_date=start_date - timedelta(days=1),
                cost_center=cost_center,
                currency=currency,
                include_unposted=include_unposted
            )
            opening_balance = op_data['balance']
            opening_balance_foreign = op_data['foreign_balance']

            # إضافة أي قيود افتتاحية مسجلة داخل الفترة إلى رصيد الافتتاح
            op_lines_in_period = JournalEntryLine.objects.filter(filters & is_opening_q).aggregate(
                op_debit=Sum('debit'),
                op_credit=Sum('credit'),
                op_f_debit=Sum('foreign_debit'),
                op_f_credit=Sum('foreign_credit'),
                op_t_debit=Sum('transaction_debit'),
                op_t_credit=Sum('transaction_credit'),
            )
            op_deb = op_lines_in_period['op_debit'] or Decimal('0.00')
            op_crd = op_lines_in_period['op_credit'] or Decimal('0.00')
            op_f_deb = (op_lines_in_period['op_f_debit'] or Decimal('0.00')) or (op_lines_in_period['op_t_debit'] or Decimal('0.00'))
            op_f_crd = (op_lines_in_period['op_f_credit'] or Decimal('0.00')) or (op_lines_in_period['op_t_credit'] or Decimal('0.00'))

            if is_debit_nature:
                opening_balance += (op_deb - op_crd)
                opening_balance_foreign += (op_f_deb - op_f_crd)
            else:
                opening_balance += (op_crd - op_deb)
                opening_balance_foreign += (op_f_crd - op_f_deb)
        else:
            initial_op_local = Decimal('0.00')
            initial_op_foreign = Decimal('0.00')
            for acc in target_accounts:
                initial_op_local += (acc.opening_balance or Decimal('0.00'))
                initial_op_foreign += (acc.opening_balance_foreign or Decimal('0.00'))

            op_lines_agg = JournalEntryLine.objects.filter(filters & is_opening_q).aggregate(
                op_debit=Sum('debit'),
                op_credit=Sum('credit'),
                op_f_debit=Sum('foreign_debit'),
                op_f_credit=Sum('foreign_credit'),
                op_t_debit=Sum('transaction_debit'),
                op_t_credit=Sum('transaction_credit'),
            )
            op_deb = op_lines_agg['op_debit'] or Decimal('0.00')
            op_crd = op_lines_agg['op_credit'] or Decimal('0.00')
            op_f_deb = (op_lines_agg['op_f_debit'] or Decimal('0.00')) or (op_lines_agg['op_t_debit'] or Decimal('0.00'))
            op_f_crd = (op_lines_agg['op_f_credit'] or Decimal('0.00')) or (op_lines_agg['op_t_credit'] or Decimal('0.00'))

            if is_debit_nature:
                opening_balance = initial_op_local + (op_deb - op_crd)
                opening_balance_foreign = initial_op_foreign + (op_f_deb - op_f_crd)
            else:
                opening_balance = initial_op_local + (op_crd - op_deb)
                opening_balance_foreign = initial_op_foreign + (op_f_crd - op_f_deb)

        # استبعاد القيود الافتتاحية من حركات الفترة التشغيلية لضمان عدم تكرارها
        lines = JournalEntryLine.objects.filter(filters).exclude(is_opening_q).select_related(
            'account',
            'journal_entry',
            'journal_entry__reversed_by_entry',
            'journal_entry__original_entry',
            'cost_center'
        ).order_by('journal_entry__date', 'journal_entry__id', 'id')

        transactions = []
        running_balance = opening_balance
        running_foreign_balance = opening_balance_foreign
        period_debit = Decimal('0.00')
        period_credit = Decimal('0.00')
        period_foreign_debit = Decimal('0.00')
        period_foreign_credit = Decimal('0.00')

        by_currency_summary = {}

        for line in lines:
            debit_val = (line.debit or Decimal('0.00')).quantize(Decimal('0.01'))
            credit_val = (line.credit or Decimal('0.00')).quantize(Decimal('0.01'))
            line_currency = line.currency or account_currency_code or base_code
            rate_val = (line.exchange_rate_snapshot or line.exchange_rate or Decimal('1.000000')).quantize(Decimal('0.000001'))

            # استخراج المبالغ الأجنبية مع آلية الاستنتاج الذاتي (Self-Healing Fallback)
            raw_f_debit = line.foreign_debit or line.transaction_debit or Decimal('0.00')
            raw_f_credit = line.foreign_credit or line.transaction_credit or Decimal('0.00')

            if raw_f_debit > 0:
                f_debit_val = Decimal(str(raw_f_debit)).quantize(Decimal('0.01'))
            elif line_currency != base_code and debit_val > 0 and rate_val > 0:
                f_debit_val = (debit_val / rate_val).quantize(Decimal('0.01'))
            else:
                f_debit_val = Decimal('0.00')

            if raw_f_credit > 0:
                f_credit_val = Decimal(str(raw_f_credit)).quantize(Decimal('0.01'))
            elif line_currency != base_code and credit_val > 0 and rate_val > 0:
                f_credit_val = (credit_val / rate_val).quantize(Decimal('0.01'))
            else:
                f_credit_val = Decimal('0.00')

            period_debit += debit_val
            period_credit += credit_val
            period_foreign_debit += f_debit_val
            period_foreign_credit += f_credit_val

            # تمييز قيود إعادة التقييم الدوري (IAS 21 FX Revaluation)
            je_ref = (line.journal_entry.reference or '').upper()
            je_desc_upper = (line.journal_entry.description or '').upper()
            src_model = (line.journal_entry.source_model or '')
            is_fx_revaluation = (
                src_model == 'FXRevaluationRun' or
                'FX-' in je_ref or
                'REVALUATION' in je_desc_upper or
                'تقييم' in je_desc_upper or
                'فروق تقييم' in je_desc_upper or
                (line_currency != base_code and (debit_val > 0 or credit_val > 0) and f_debit_val == 0 and f_credit_val == 0)
            )

            # تمييز فروق العملة المحققة (Realized FX)
            is_realized_fx = (
                'REALIZED' in je_desc_upper or
                'فروق عملة محققة' in (line.journal_entry.description or '') or
                line.account.code.startswith('71010') or
                line.account.code.startswith('72010')
            )

            # تحديث الرصيد التراكمي المحلي بالعملة الوظيفية
            if is_debit_nature:
                running_balance += (debit_val - credit_val)
            else:
                running_balance += (credit_val - debit_val)

            # تحديث الرصيد التراكمي الأجنبي
            # في قيود التقييم الدوري IAS 21 لا يتأثر الرصيد النقدي الأجنبي
            if not is_fx_revaluation:
                if is_debit_nature:
                    running_foreign_balance += (f_debit_val - f_credit_val)
                else:
                    running_foreign_balance += (f_credit_val - f_debit_val)

            # دمج اسم العميل/الطرف والبيان بشكل كامل
            line_desc = (line.description or '').strip()
            je_desc = (line.journal_entry.description or '').strip()
            if not line_desc:
                effective_desc = je_desc
            elif not je_desc:
                effective_desc = line_desc
            elif ' - ' in je_desc:
                party = je_desc.rsplit(' - ', 1)[-1].strip()
                if party and party not in line_desc and not party.startswith('INV-') and not party.startswith('PUR-') and not party.startswith('BILL-'):
                    effective_desc = f"{line_desc} - {party}"
                else:
                    effective_desc = line_desc
            else:
                effective_desc = line_desc

            # ملخص العملات
            if line_currency not in by_currency_summary:
                by_currency_summary[line_currency] = {
                    'debit': Decimal('0.00'),
                    'credit': Decimal('0.00'),
                    'foreign_debit': Decimal('0.00'),
                    'foreign_credit': Decimal('0.00'),
                    'count': 0
                }
            by_currency_summary[line_currency]['debit'] += debit_val
            by_currency_summary[line_currency]['credit'] += credit_val
            by_currency_summary[line_currency]['foreign_debit'] += f_debit_val
            by_currency_summary[line_currency]['foreign_credit'] += f_credit_val
            by_currency_summary[line_currency]['count'] += 1

            transactions.append({
                'line_id': line.id,
                'journal_id': line.journal_entry_id,
                'journal_entry_id': line.journal_entry_id,
                'journal_number': line.journal_entry.number,
                'journal_entry_number': line.journal_entry.number,
                'date': line.journal_entry.date,
                'account_code': line.account.code,
                'account_name': line.account.name,
                'description': effective_desc,
                'reference': getattr(line.journal_entry, 'reference', None) or getattr(line.journal_entry, 'posting_references', None) or '-',
                'debit': debit_val,
                'credit': credit_val,
                'balance': running_balance,
                'running_balance': running_balance,
                'foreign_debit': f_debit_val,
                'foreign_credit': f_credit_val,
                'foreign_balance': running_foreign_balance,
                'running_foreign_balance': running_foreign_balance,
                'currency': line_currency,
                'exchange_rate': rate_val,
                'is_fx_revaluation': is_fx_revaluation,
                'is_realized_fx': is_realized_fx,
                'status': line.journal_entry.status,
                'is_reversal': getattr(line.journal_entry, 'is_reversal', False),
                'reversed_by_entry': getattr(line.journal_entry, 'reversed_by_entry', None),
                'cost_center_name': line.cost_center_name_snapshot or (line.cost_center.name if line.cost_center else None),
                'source_module': getattr(line.journal_entry, 'source_module', None),
                'entry_type': getattr(line.journal_entry, 'entry_type', 'manual'),
                'entry_type_display': line.journal_entry.get_entry_type_display_smart() if hasattr(line.journal_entry, 'get_entry_type_display_smart') else (line.journal_entry.get_entry_type_display() if hasattr(line.journal_entry, 'get_entry_type_display') else getattr(line.journal_entry, 'entry_type', 'manual')),
            })

        closing_balance = running_balance
        closing_balance_foreign = running_foreign_balance

        return {
            'account_id': account.id,
            'account_code': account.code,
            'account_name': account.name,
            'account_currency': account_currency_code,
            'account_currency_symbol': account_currency_symbol,
            'is_foreign_account': is_foreign_account,
            'is_consolidated': is_consolidated,
            'functional_currency': base_code,
            'functional_currency_symbol': base_symbol,
            'opening_balance': opening_balance,
            'opening_balance_foreign': opening_balance_foreign,
            'period_debit': period_debit,
            'period_credit': period_credit,
            'total_debit': period_debit,
            'total_credit': period_credit,
            'total_foreign_debit': period_foreign_debit,
            'total_foreign_credit': period_foreign_credit,
            'period_movement': period_debit - period_credit if is_debit_nature else period_credit - period_debit,
            'period_foreign_movement': period_foreign_debit - period_foreign_credit if is_debit_nature else period_foreign_credit - period_foreign_debit,
            'transaction_count': len(transactions),
            'transactions': transactions,
            'closing_balance': closing_balance,
            'closing_balance_foreign': closing_balance_foreign,
            'by_currency_breakdown': by_currency_summary
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
            'sub_details': sub_details,
            'sub_accounts': sub_details
        }
