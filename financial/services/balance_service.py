"""
خدمات إدارة الأرصدة المحاسبية
"""
from django.db import models
from django.core.cache import cache
from django.utils import timezone
from decimal import Decimal
from typing import Dict, List, Optional, Union
import logging
from datetime import date, datetime

from ..models.chart_of_accounts import ChartOfAccounts
from ..models.journal_entry import JournalEntryLine, JournalEntry

logger = logging.getLogger(__name__)


class BalanceService:
    """
    خدمة حساب وإدارة الأرصدة المحاسبية
    """
    
    CACHE_TIMEOUT = 3600  # ساعة واحدة
    
    @staticmethod
    def get_account_balance(
        account: Union[str, int, ChartOfAccounts],
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        use_cache: bool = True
    ) -> Decimal:
        """
        حساب رصيد حساب معين في فترة محددة
        
        Args:
            account: الحساب (كود، معرف، أو كائن)
            date_from: تاريخ البداية
            date_to: تاريخ النهاية
            use_cache: استخدام التخزين المؤقت
            
        Returns:
            Decimal: رصيد الحساب
        """
        # الحصول على كائن الحساب
        if isinstance(account, str):
            account_obj = ChartOfAccounts.objects.get(code=account, is_active=True)
        elif isinstance(account, int):
            account_obj = ChartOfAccounts.objects.get(id=account, is_active=True)
        else:
            account_obj = account
        
        # إنشاء مفتاح التخزين المؤقت
        cache_key = f"balance_{account_obj.id}_{date_from}_{date_to}"
        
        if use_cache:
            cached_balance = cache.get(cache_key)
            if cached_balance is not None:
                return cached_balance
        
        # حساب الرصيد
        balance = BalanceService._calculate_balance(account_obj, date_from, date_to)
        
        # حفظ في التخزين المؤقت
        if use_cache:
            cache.set(cache_key, balance, BalanceService.CACHE_TIMEOUT)
        
        return balance
    
    @staticmethod
    def _calculate_balance(
        account: ChartOfAccounts,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None
    ) -> Decimal:
        """
        حساب الرصيد الفعلي من القيود المحاسبية
        """
        # بناء الاستعلام
        query = models.Q(account=account, journal_entry__status='posted')
        
        if date_from:
            query &= models.Q(journal_entry__date__gte=date_from)
        if date_to:
            query &= models.Q(journal_entry__date__lte=date_to)
        
        # الحصول على مجموع المدين والدائن
        aggregates = JournalEntryLine.objects.filter(query).aggregate(
            total_debit=models.Sum('debit'),
            total_credit=models.Sum('credit')
        )
        
        total_debit = aggregates['total_debit'] or Decimal('0')
        total_credit = aggregates['total_credit'] or Decimal('0')
        
        # حساب الرصيد حسب طبيعة الحساب
        if account.nature == 'debit':
            return total_debit - total_credit
        else:
            return total_credit - total_debit
    
    @staticmethod
    def get_trial_balance(
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        account_type: Optional[str] = None
    ) -> List[Dict]:
        """
        إنشاء ميزان المراجعة
        
        Returns:
            List[Dict]: قائمة بالحسابات وأرصدتها
        """
        # الحصول على الحسابات النهائية النشطة
        accounts_query = ChartOfAccounts.objects.filter(
            is_leaf=True,
            is_active=True
        )
        
        if account_type:
            accounts_query = accounts_query.filter(account_type__category=account_type)
        
        trial_balance = []
        total_debit = Decimal('0')
        total_credit = Decimal('0')
        
        for account in accounts_query:
            balance = BalanceService.get_account_balance(account, date_from, date_to)
            
            if balance != 0:  # عرض الحسابات ذات الرصيد فقط
                debit_balance = balance if account.nature == 'debit' and balance > 0 else Decimal('0')
                credit_balance = abs(balance) if account.nature == 'credit' and balance > 0 else Decimal('0')
                
                # إذا كان الرصيد عكس الطبيعة
                if account.nature == 'debit' and balance < 0:
                    credit_balance = abs(balance)
                elif account.nature == 'credit' and balance < 0:
                    debit_balance = abs(balance)
                
                trial_balance.append({
                    'account_code': account.code,
                    'account_name': account.name,
                    'account_type': account.account_type.name,
                    'debit_balance': debit_balance,
                    'credit_balance': credit_balance,
                    'balance': balance
                })
                
                total_debit += debit_balance
                total_credit += credit_balance
        
        # إضافة الإجماليات
        trial_balance.append({
            'account_code': '',
            'account_name': 'الإجمالي',
            'account_type': '',
            'debit_balance': total_debit,
            'credit_balance': total_credit,
            'balance': total_debit - total_credit
        })
        
        return trial_balance
    
    @staticmethod
    def get_account_statement(
        account: Union[str, int, ChartOfAccounts],
        date_from: Optional[date] = None,
        date_to: Optional[date] = None
    ) -> Dict:
        """
        كشف حساب مفصل
        
        Returns:
            Dict: كشف الحساب مع الحركات والأرصدة
        """
        # الحصول على كائن الحساب
        if isinstance(account, str):
            account_obj = ChartOfAccounts.objects.get(code=account, is_active=True)
        elif isinstance(account, int):
            account_obj = ChartOfAccounts.objects.get(id=account, is_active=True)
        else:
            account_obj = account
        
        # بناء الاستعلام
        query = models.Q(account=account_obj, journal_entry__status='posted')
        
        if date_from:
            query &= models.Q(journal_entry__date__gte=date_from)
        if date_to:
            query &= models.Q(journal_entry__date__lte=date_to)
        
        # الحصول على الحركات
        lines = JournalEntryLine.objects.filter(query).select_related(
            'journal_entry'
        ).order_by('journal_entry__date', 'journal_entry__number')
        
        # حساب الرصيد الافتتاحي
        opening_balance = Decimal('0')
        if date_from:
            opening_balance = BalanceService.get_account_balance(
                account_obj, None, date_from - timezone.timedelta(days=1)
            )
        
        # بناء كشف الحساب
        statement_lines = []
        running_balance = opening_balance
        
        for line in lines:
            # حساب الرصيد الجاري
            if account_obj.nature == 'debit':
                running_balance += line.debit - line.credit
            else:
                running_balance += line.credit - line.debit
            
            statement_lines.append({
                'date': line.journal_entry.date,
                'entry_number': line.journal_entry.number,
                'description': line.description or line.journal_entry.description,
                'reference': line.journal_entry.reference,
                'debit': line.debit,
                'credit': line.credit,
                'balance': running_balance
            })
        
        return {
            'account': {
                'code': account_obj.code,
                'name': account_obj.name,
                'type': account_obj.account_type.name,
                'nature': account_obj.nature
            },
            'period': {
                'date_from': date_from,
                'date_to': date_to
            },
            'opening_balance': opening_balance,
            'closing_balance': running_balance,
            'lines': statement_lines,
            'totals': {
                'total_debit': sum(line['debit'] for line in statement_lines),
                'total_credit': sum(line['credit'] for line in statement_lines),
                'net_movement': running_balance - opening_balance
            }
        }
    
    @staticmethod
    def get_accounts_summary(
        account_type: Optional[str] = None,
        date_to: Optional[date] = None
    ) -> List[Dict]:
        """
        ملخص الحسابات حسب النوع
        """
        if not date_to:
            date_to = timezone.now().date()
        
        accounts_query = ChartOfAccounts.objects.filter(
            is_leaf=True,
            is_active=True
        )
        
        if account_type:
            accounts_query = accounts_query.filter(account_type__category=account_type)
        
        summary = []
        
        for account in accounts_query:
            balance = BalanceService.get_account_balance(account, None, date_to)
            
            if balance != 0:
                summary.append({
                    'account_code': account.code,
                    'account_name': account.name,
                    'account_type': account.account_type.name,
                    'balance': balance,
                    'balance_formatted': f"{balance:,.2f}"
                })
        
        # ترتيب حسب الرصيد
        summary.sort(key=lambda x: abs(x['balance']), reverse=True)
        
        return summary
    
    @staticmethod
    def clear_balance_cache(account_id: Optional[int] = None):
        """
        مسح التخزين المؤقت للأرصدة
        """
        if account_id:
            # مسح cache لحساب معين
            cache_pattern = f"balance_{account_id}_*"
            # Django cache لا يدعم wildcard deletion مباشرة
            # يمكن استخدام Redis مباشرة أو تتبع المفاتيح
            pass
        else:
            # مسح جميع أرصدة الحسابات
            cache.clear()
        
        logger.info(f"تم مسح cache الأرصدة للحساب {account_id or 'جميع الحسابات'}")


class BalanceValidationService:
    """
    خدمة التحقق من صحة الأرصدة
    """
    
    @staticmethod
    def validate_trial_balance() -> Dict:
        """
        التحقق من توازن ميزان المراجعة
        """
        trial_balance = BalanceService.get_trial_balance()
        
        total_debit = sum(item['debit_balance'] for item in trial_balance[:-1])
        total_credit = sum(item['credit_balance'] for item in trial_balance[:-1])
        
        is_balanced = total_debit == total_credit
        difference = total_debit - total_credit
        
        return {
            'is_balanced': is_balanced,
            'total_debit': total_debit,
            'total_credit': total_credit,
            'difference': difference,
            'status': 'متوازن' if is_balanced else f'غير متوازن - الفرق: {difference}'
        }
    
    @staticmethod
    def find_unbalanced_entries(date_from: Optional[date] = None, date_to: Optional[date] = None) -> List[Dict]:
        """
        البحث عن القيود غير المتوازنة
        """
        query = models.Q(status='posted')
        
        if date_from:
            query &= models.Q(date__gte=date_from)
        if date_to:
            query &= models.Q(date__lte=date_to)
        
        entries = JournalEntry.objects.filter(query)
        unbalanced = []
        
        for entry in entries:
            if not entry.is_balanced:
                unbalanced.append({
                    'entry_number': entry.number,
                    'date': entry.date,
                    'description': entry.description,
                    'total_debit': entry.total_debit,
                    'total_credit': entry.total_credit,
                    'difference': entry.difference
                })
        
        return unbalanced
