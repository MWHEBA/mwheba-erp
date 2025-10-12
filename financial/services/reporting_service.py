"""
خدمة التقارير المالية المحسنة
"""
from django.db import models
from django.utils import timezone
from decimal import Decimal
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta

from ..models.chart_of_accounts import ChartOfAccounts, AccountType
from ..models.journal_entry import JournalEntry, JournalEntryLine
from ..models.transactions import FinancialTransaction
from ..models.categories import FinancialCategory

logger = logging.getLogger(__name__)


class ReportingService:
    """
    خدمة شاملة للتقارير المالية
    """
    
    @staticmethod
    def generate_trial_balance(
        date_to: Optional[datetime] = None,
        include_zero_balances: bool = False
    ) -> Dict:
        """
        إنشاء تقرير ميزان المراجعة
        """
        try:
            if not date_to:
                date_to = timezone.now().date()
            
            # الحصول على جميع الحسابات النشطة
            accounts = ChartOfAccounts.objects.filter(
                is_active=True,
                is_leaf=True
            ).order_by('code')
            
            trial_balance_data = {
                'date': date_to,
                'accounts': [],
                'totals': {
                    'total_debit': Decimal('0'),
                    'total_credit': Decimal('0'),
                    'difference': Decimal('0')
                }
            }
            
            for account in accounts:
                balance = account.get_balance(date_to=date_to, include_opening=True)
                
                # تحديد المدين والدائن بناءً على طبيعة الحساب
                if account.account_type.nature == 'debit':
                    debit_balance = balance if balance >= 0 else Decimal('0')
                    credit_balance = abs(balance) if balance < 0 else Decimal('0')
                else:  # credit nature
                    credit_balance = balance if balance >= 0 else Decimal('0')
                    debit_balance = abs(balance) if balance < 0 else Decimal('0')
                
                # إضافة الحساب إذا كان له رصيد أو إذا كان مطلوب عرض الأرصدة الصفرية
                if balance != 0 or include_zero_balances:
                    account_data = {
                        'code': account.code,
                        'name': account.name,
                        'account_type': account.account_type.name,
                        'nature': account.account_type.nature,
                        'debit_balance': debit_balance,
                        'credit_balance': credit_balance,
                        'balance': balance
                    }
                    
                    trial_balance_data['accounts'].append(account_data)
                    trial_balance_data['totals']['total_debit'] += debit_balance
                    trial_balance_data['totals']['total_credit'] += credit_balance
            
            # حساب الفرق (يجب أن يكون صفر في ميزان صحيح)
            trial_balance_data['totals']['difference'] = (
                trial_balance_data['totals']['total_debit'] - 
                trial_balance_data['totals']['total_credit']
            )
            
            return trial_balance_data
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء ميزان المراجعة: {str(e)}")
            return {}
    
    @staticmethod
    def generate_balance_sheet(date_to: Optional[datetime] = None) -> Dict:
        """
        إنشاء تقرير الميزانية العمومية
        """
        try:
            if not date_to:
                date_to = timezone.now().date()
            
            balance_sheet = {
                'date': date_to,
                'assets': {
                    'current_assets': [],
                    'non_current_assets': [],
                    'total_assets': Decimal('0')
                },
                'liabilities': {
                    'current_liabilities': [],
                    'non_current_liabilities': [],
                    'total_liabilities': Decimal('0')
                },
                'equity': {
                    'items': [],
                    'total_equity': Decimal('0')
                }
            }
            
            # الأصول
            asset_accounts = ChartOfAccounts.objects.filter(
                account_type__category='asset',
                is_active=True,
                is_leaf=True
            ).order_by('code')
            
            for account in asset_accounts:
                balance = account.get_balance(date_to=date_to, include_opening=True)
                if balance != 0:
                    account_data = {
                        'code': account.code,
                        'name': account.name,
                        'balance': balance
                    }
                    
                    # تصنيف الأصول (يمكن تحسينه بإضافة حقل في النموذج)
                    if account.is_cash_account or account.is_bank_account:
                        balance_sheet['assets']['current_assets'].append(account_data)
                    else:
                        balance_sheet['assets']['non_current_assets'].append(account_data)
                    
                    balance_sheet['assets']['total_assets'] += balance
            
            # الخصوم
            liability_accounts = ChartOfAccounts.objects.filter(
                account_type__category='liability',
                is_active=True,
                is_leaf=True
            ).order_by('code')
            
            for account in liability_accounts:
                balance = account.get_balance(date_to=date_to, include_opening=True)
                if balance != 0:
                    account_data = {
                        'code': account.code,
                        'name': account.name,
                        'balance': balance
                    }
                    
                    # تصنيف الخصوم (يمكن تحسينه)
                    balance_sheet['liabilities']['current_liabilities'].append(account_data)
                    balance_sheet['liabilities']['total_liabilities'] += balance
            
            # حقوق الملكية
            equity_accounts = ChartOfAccounts.objects.filter(
                account_type__category='equity',
                is_active=True,
                is_leaf=True
            ).order_by('code')
            
            for account in equity_accounts:
                balance = account.get_balance(date_to=date_to, include_opening=True)
                if balance != 0:
                    account_data = {
                        'code': account.code,
                        'name': account.name,
                        'balance': balance
                    }
                    
                    balance_sheet['equity']['items'].append(account_data)
                    balance_sheet['equity']['total_equity'] += balance
            
            # إضافة صافي الدخل لحقوق الملكية
            net_income = ReportingService._calculate_net_income(date_to)
            if net_income != 0:
                balance_sheet['equity']['items'].append({
                    'code': 'NET_INCOME',
                    'name': 'صافي الدخل',
                    'balance': net_income
                })
                balance_sheet['equity']['total_equity'] += net_income
            
            # التحقق من توازن الميزانية
            balance_sheet['is_balanced'] = (
                balance_sheet['assets']['total_assets'] == 
                balance_sheet['liabilities']['total_liabilities'] + balance_sheet['equity']['total_equity']
            )
            
            return balance_sheet
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء الميزانية العمومية: {str(e)}")
            return {}
    
    @staticmethod
    def generate_income_statement(
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None
    ) -> Dict:
        """
        إنشاء تقرير قائمة الدخل
        """
        try:
            if not date_to:
                date_to = timezone.now().date()
            if not date_from:
                date_from = date_to.replace(day=1)  # بداية الشهر
            
            income_statement = {
                'period_from': date_from,
                'period_to': date_to,
                'revenues': {
                    'items': [],
                    'total_revenue': Decimal('0')
                },
                'expenses': {
                    'items': [],
                    'total_expenses': Decimal('0')
                },
                'net_income': Decimal('0')
            }
            
            # الإيرادات
            revenue_accounts = ChartOfAccounts.objects.filter(
                account_type__category='revenue',
                is_active=True,
                is_leaf=True
            ).order_by('code')
            
            for account in revenue_accounts:
                # حساب حركة الحساب في الفترة
                lines = JournalEntryLine.objects.filter(
                    account=account,
                    journal_entry__date__gte=date_from,
                    journal_entry__date__lte=date_to,
                    journal_entry__status='posted'
                )
                
                total_credit = lines.aggregate(
                    total=models.Sum('credit')
                )['total'] or Decimal('0')
                
                total_debit = lines.aggregate(
                    total=models.Sum('debit')
                )['total'] or Decimal('0')
                
                net_revenue = total_credit - total_debit
                
                if net_revenue != 0:
                    account_data = {
                        'code': account.code,
                        'name': account.name,
                        'amount': net_revenue
                    }
                    
                    income_statement['revenues']['items'].append(account_data)
                    income_statement['revenues']['total_revenue'] += net_revenue
            
            # المصروفات
            expense_accounts = ChartOfAccounts.objects.filter(
                account_type__category='expense',
                is_active=True,
                is_leaf=True
            ).order_by('code')
            
            for account in expense_accounts:
                # حساب حركة الحساب في الفترة
                lines = JournalEntryLine.objects.filter(
                    account=account,
                    journal_entry__date__gte=date_from,
                    journal_entry__date__lte=date_to,
                    journal_entry__status='posted'
                )
                
                total_debit = lines.aggregate(
                    total=models.Sum('debit')
                )['total'] or Decimal('0')
                
                total_credit = lines.aggregate(
                    total=models.Sum('credit')
                )['total'] or Decimal('0')
                
                net_expense = total_debit - total_credit
                
                if net_expense != 0:
                    account_data = {
                        'code': account.code,
                        'name': account.name,
                        'amount': net_expense
                    }
                    
                    income_statement['expenses']['items'].append(account_data)
                    income_statement['expenses']['total_expenses'] += net_expense
            
            # صافي الدخل
            income_statement['net_income'] = (
                income_statement['revenues']['total_revenue'] - 
                income_statement['expenses']['total_expenses']
            )
            
            return income_statement
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء قائمة الدخل: {str(e)}")
            return {}
    
    @staticmethod
    def generate_cash_flow_statement(
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None
    ) -> Dict:
        """
        إنشاء تقرير قائمة التدفقات النقدية
        """
        try:
            if not date_to:
                date_to = timezone.now().date()
            if not date_from:
                date_from = date_to.replace(day=1)
            
            # الحصول على الحسابات النقدية والبنكية
            cash_accounts = ChartOfAccounts.objects.filter(
                models.Q(is_cash_account=True) | models.Q(is_bank_account=True),
                is_active=True,
                is_leaf=True
            )
            
            cash_flow = {
                'period_from': date_from,
                'period_to': date_to,
                'operating_activities': {
                    'items': [],
                    'total': Decimal('0')
                },
                'investing_activities': {
                    'items': [],
                    'total': Decimal('0')
                },
                'financing_activities': {
                    'items': [],
                    'total': Decimal('0')
                },
                'net_cash_flow': Decimal('0'),
                'beginning_cash': Decimal('0'),
                'ending_cash': Decimal('0')
            }
            
            # حساب الرصيد النقدي في بداية الفترة
            for account in cash_accounts:
                beginning_balance = account.get_balance(date_to=date_from - timedelta(days=1), include_opening=True)
                cash_flow['beginning_cash'] += beginning_balance
            
            # حساب الرصيد النقدي في نهاية الفترة
            for account in cash_accounts:
                ending_balance = account.get_balance(date_to=date_to, include_opening=True)
                cash_flow['ending_cash'] += ending_balance
            
            # صافي التدفق النقدي
            cash_flow['net_cash_flow'] = cash_flow['ending_cash'] - cash_flow['beginning_cash']
            
            # تصنيف التدفقات (يحتاج تطوير أكثر لتصنيف دقيق)
            # الأنشطة التشغيلية - صافي الدخل + تعديلات
            net_income = ReportingService._calculate_net_income(date_to, date_from)
            cash_flow['operating_activities']['items'].append({
                'description': 'صافي الدخل',
                'amount': net_income
            })
            cash_flow['operating_activities']['total'] += net_income
            
            return cash_flow
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء قائمة التدفقات النقدية: {str(e)}")
            return {}
    
    @staticmethod
    def generate_account_ledger(
        account_code: str,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None
    ) -> Dict:
        """
        إنشاء تقرير دفتر الأستاذ لحساب معين
        """
        try:
            account = ChartOfAccounts.objects.get(code=account_code, is_active=True)
            
            if not date_to:
                date_to = timezone.now().date()
            if not date_from:
                date_from = date_to.replace(day=1)
            
            # الحصول على قيود الحساب في الفترة
            lines = JournalEntryLine.objects.filter(
                account=account,
                journal_entry__date__gte=date_from,
                journal_entry__date__lte=date_to,
                journal_entry__status='posted'
            ).order_by('journal_entry__date', 'journal_entry__number')
            
            ledger_data = {
                'account': {
                    'code': account.code,
                    'name': account.name,
                    'type': account.account_type.name,
                    'nature': account.account_type.nature
                },
                'period_from': date_from,
                'period_to': date_to,
                'opening_balance': account.get_balance(date_to=date_from - timedelta(days=1), include_opening=True),
                'transactions': [],
                'closing_balance': account.get_balance(date_to=date_to, include_opening=True),
                'totals': {
                    'total_debit': Decimal('0'),
                    'total_credit': Decimal('0')
                }
            }
            
            running_balance = ledger_data['opening_balance']
            
            for line in lines:
                # حساب الرصيد الجاري
                if account.account_type.nature == 'debit':
                    running_balance += line.debit - line.credit
                else:
                    running_balance += line.credit - line.debit
                
                transaction_data = {
                    'date': line.journal_entry.date,
                    'reference': line.journal_entry.reference,
                    'description': line.description or line.journal_entry.description,
                    'debit': line.debit,
                    'credit': line.credit,
                    'balance': running_balance,
                    'journal_entry_number': line.journal_entry.number
                }
                
                ledger_data['transactions'].append(transaction_data)
                ledger_data['totals']['total_debit'] += line.debit
                ledger_data['totals']['total_credit'] += line.credit
            
            return ledger_data
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء دفتر الأستاذ: {str(e)}")
            return {}
    
    @staticmethod
    def _calculate_net_income(
        date_to: datetime,
        date_from: Optional[datetime] = None
    ) -> Decimal:
        """
        حساب صافي الدخل لفترة معينة
        """
        try:
            if not date_from:
                # من بداية السنة المالية
                date_from = date_to.replace(month=1, day=1)
            
            # إجمالي الإيرادات
            revenue_lines = JournalEntryLine.objects.filter(
                account__account_type__category='revenue',
                journal_entry__date__gte=date_from,
                journal_entry__date__lte=date_to,
                journal_entry__status='posted'
            )
            
            total_revenue = (
                revenue_lines.aggregate(total=models.Sum('credit'))['total'] or Decimal('0')
            ) - (
                revenue_lines.aggregate(total=models.Sum('debit'))['total'] or Decimal('0')
            )
            
            # إجمالي المصروفات
            expense_lines = JournalEntryLine.objects.filter(
                account__account_type__category='expense',
                journal_entry__date__gte=date_from,
                journal_entry__date__lte=date_to,
                journal_entry__status='posted'
            )
            
            total_expenses = (
                expense_lines.aggregate(total=models.Sum('debit'))['total'] or Decimal('0')
            ) - (
                expense_lines.aggregate(total=models.Sum('credit'))['total'] or Decimal('0')
            )
            
            return total_revenue - total_expenses
            
        except Exception as e:
            logger.error(f"خطأ في حساب صافي الدخل: {str(e)}")
            return Decimal('0')
    
    @staticmethod
    def generate_financial_summary(
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None
    ) -> Dict:
        """
        إنشاء ملخص مالي شامل
        """
        try:
            if not date_to:
                date_to = timezone.now().date()
            if not date_from:
                date_from = date_to.replace(day=1)
            
            summary = {
                'period_from': date_from,
                'period_to': date_to,
                'income_statement': ReportingService.generate_income_statement(date_from, date_to),
                'balance_sheet': ReportingService.generate_balance_sheet(date_to),
                'key_metrics': {},
                'alerts': []
            }
            
            # المؤشرات الرئيسية
            total_assets = summary['balance_sheet'].get('assets', {}).get('total_assets', Decimal('0'))
            total_liabilities = summary['balance_sheet'].get('liabilities', {}).get('total_liabilities', Decimal('0'))
            total_equity = summary['balance_sheet'].get('equity', {}).get('total_equity', Decimal('0'))
            net_income = summary['income_statement'].get('net_income', Decimal('0'))
            
            summary['key_metrics'] = {
                'total_assets': total_assets,
                'total_liabilities': total_liabilities,
                'total_equity': total_equity,
                'net_income': net_income,
                'debt_to_equity_ratio': (total_liabilities / total_equity) if total_equity != 0 else None,
                'return_on_assets': (net_income / total_assets) if total_assets != 0 else None,
                'profit_margin': (net_income / summary['income_statement'].get('revenues', {}).get('total_revenue', Decimal('1'))) if summary['income_statement'].get('revenues', {}).get('total_revenue', Decimal('0')) != 0 else None
            }
            
            # التنبيهات
            if not summary['balance_sheet'].get('is_balanced', True):
                summary['alerts'].append({
                    'type': 'error',
                    'message': 'الميزانية العمومية غير متوازنة'
                })
            
            if net_income < 0:
                summary['alerts'].append({
                    'type': 'warning',
                    'message': 'صافي الدخل سالب للفترة'
                })
            
            return summary
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء الملخص المالي: {str(e)}")
            return {}
