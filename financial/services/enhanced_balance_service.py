"""
خدمات الأرصدة المحسنة مع تحسينات الأداء
"""
from django.db import models, connection
from django.core.cache import cache
from django.utils import timezone
from django.conf import settings
from decimal import Decimal
from typing import Dict, List, Optional, Union, Tuple
from datetime import date, datetime, timedelta
import logging
import hashlib

from ..models.chart_of_accounts import ChartOfAccounts
from ..models.journal_entry import JournalEntry, JournalEntryLine
from ..models.enhanced_balance import AccountBalanceCache, BalanceSnapshot, BalanceAuditLog

logger = logging.getLogger(__name__)


class EnhancedBalanceService:
    """
    خدمة الأرصدة المحسنة مع تحسينات الأداء
    """
    
    # إعدادات الكاش
    CACHE_TIMEOUT = getattr(settings, 'BALANCE_CACHE_TIMEOUT', 3600)  # ساعة واحدة
    CACHE_PREFIX = 'balance_'
    
    # إعدادات الأداء
    BATCH_SIZE = 1000
    SNAPSHOT_THRESHOLD = 100  # عدد المعاملات قبل إنشاء لقطة جديدة
    
    @classmethod
    def get_account_balance_optimized(
        cls,
        account: Union[str, int, ChartOfAccounts],
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        use_cache: bool = True,
        force_refresh: bool = False
    ) -> Decimal:
        """
        حساب رصيد الحساب بطريقة محسنة
        """
        # الحصول على كائن الحساب
        account_obj = cls._get_account_object(account)
        
        # إنشاء مفتاح الكاش
        cache_key = cls._generate_cache_key(account_obj.id, date_from, date_to)
        
        # محاولة الحصول من الكاش
        if use_cache and not force_refresh:
            cached_balance = cache.get(cache_key)
            if cached_balance is not None:
                logger.debug(f"تم الحصول على الرصيد من الكاش للحساب {account_obj.code}")
                return cached_balance
        
        # حساب الرصيد
        if date_to is None:
            # رصيد حالي - استخدام الكاش المحلي
            balance = cls._get_current_balance_with_cache(account_obj, force_refresh)
        else:
            # رصيد تاريخي - استخدام اللقطات والحساب التدريجي
            balance = cls._get_historical_balance_optimized(account_obj, date_from, date_to)
        
        # حفظ في الكاش
        if use_cache:
            cache.set(cache_key, balance, cls.CACHE_TIMEOUT)
        
        return balance
    
    @classmethod
    def _get_current_balance_with_cache(
        cls, 
        account: ChartOfAccounts, 
        force_refresh: bool = False
    ) -> Decimal:
        """
        الحصول على الرصيد الحالي مع استخدام الكاش المحلي
        """
        try:
            # الحصول على كاش الحساب
            balance_cache, created = AccountBalanceCache.objects.get_or_create(
                account=account,
                defaults={'needs_refresh': True}
            )
            
            # التحقق من صحة الكاش
            if force_refresh or not balance_cache.is_valid or balance_cache.needs_refresh:
                balance_cache.refresh_balance(force=True)
            
            return balance_cache.current_balance
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على الرصيد من الكاش للحساب {account.code}: {str(e)}")
            # العودة للحساب التقليدي
            return cls._calculate_balance_traditional(account)
    
    @classmethod
    def _get_historical_balance_optimized(
        cls,
        account: ChartOfAccounts,
        date_from: Optional[date] = None,
        date_to: date = None
    ) -> Decimal:
        """
        حساب الرصيد التاريخي بطريقة محسنة باستخدام اللقطات
        """
        # البحث عن أقرب لقطة قبل التاريخ المطلوب
        snapshot = BalanceSnapshot.objects.filter(
            account=account,
            snapshot_date__lte=date_to
        ).order_by('-snapshot_date').first()
        
        if snapshot:
            # حساب الرصيد من اللقطة + المعاملات اللاحقة
            base_balance = snapshot.balance
            start_date = snapshot.snapshot_date + timedelta(days=1)
            
            # حساب المعاملات من تاريخ اللقطة حتى التاريخ المطلوب
            additional_balance = cls._calculate_balance_range(
                account, start_date, date_to
            )
            
            return base_balance + additional_balance
        else:
            # لا توجد لقطات - حساب تقليدي
            return cls._calculate_balance_range(account, date_from, date_to)
    
    @classmethod
    def _calculate_balance_range(
        cls,
        account: ChartOfAccounts,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None
    ) -> Decimal:
        """
        حساب الرصيد في فترة معينة باستخدام window functions
        """
        # بناء الاستعلام مع window functions للأداء الأمثل
        query = """
        WITH account_movements AS (
            SELECT 
                jel.debit,
                jel.credit,
                je.date,
                ROW_NUMBER() OVER (ORDER BY je.date, je.id) as rn
            FROM financial_journalentryline jel
            INNER JOIN financial_journalentry je ON jel.journal_entry_id = je.id
            WHERE jel.account_id = %s 
                AND je.status = 'posted'
        """
        
        params = [account.id]
        
        if date_from:
            query += " AND je.date >= %s"
            params.append(date_from)
        
        if date_to:
            query += " AND je.date <= %s"
            params.append(date_to)
        
        query += """
        )
        SELECT 
            COALESCE(SUM(debit), 0) as total_debit,
            COALESCE(SUM(credit), 0) as total_credit
        FROM account_movements
        """
        
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            result = cursor.fetchone()
            
            if result:
                total_debit, total_credit = result
                total_debit = Decimal(str(total_debit or 0))
                total_credit = Decimal(str(total_credit or 0))
                
                # حساب الرصيد حسب طبيعة الحساب
                if account.account_type.nature == 'debit':
                    return total_debit - total_credit
                else:
                    return total_credit - total_debit
        
        return Decimal('0')
    
    @classmethod
    def calculate_account_balance_detailed(
        cls, 
        account: ChartOfAccounts,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None
    ) -> Dict:
        """
        حساب تفصيلي لرصيد الحساب مع معلومات إضافية
        """
        query = """
        SELECT 
            COALESCE(SUM(jel.debit), 0) as total_debit,
            COALESCE(SUM(jel.credit), 0) as total_credit,
            COUNT(*) as transactions_count,
            MAX(je.id) as last_transaction_id
        FROM financial_journalentryline jel
        INNER JOIN financial_journalentry je ON jel.journal_entry_id = je.id
        WHERE jel.account_id = %s AND je.status = 'posted'
        """
        
        params = [account.id]
        
        if date_from:
            query += " AND je.date >= %s"
            params.append(date_from)
        
        if date_to:
            query += " AND je.date <= %s"
            params.append(date_to)
        
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            result = cursor.fetchone()
            
            if result:
                total_debit, total_credit, count, last_id = result
                total_debit = Decimal(str(total_debit or 0))
                total_credit = Decimal(str(total_credit or 0))
                
                # حساب الرصيد
                if account.account_type.nature == 'debit':
                    balance = total_debit - total_credit
                else:
                    balance = total_credit - total_debit
                
                return {
                    'balance': balance,
                    'total_debits': total_debit,
                    'total_credits': total_credit,
                    'transactions_count': count or 0,
                    'last_transaction_id': last_id
                }
        
        return {
            'balance': Decimal('0'),
            'total_debits': Decimal('0'),
            'total_credits': Decimal('0'),
            'transactions_count': 0,
            'last_transaction_id': None
        }
    
    @classmethod
    def get_trial_balance_optimized(
        cls,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        account_types: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        ميزان مراجعة محسن باستخدام Django ORM
        """
        try:
            # الحصول على جميع الحسابات النهائية النشطة
            accounts_query = ChartOfAccounts.objects.filter(
                is_leaf=True,
                is_active=True
            ).select_related('account_type')
            
            if account_types:
                accounts_query = accounts_query.filter(account_type__category__in=account_types)
            
            accounts = accounts_query.order_by('code')
            
            trial_balance = []
            total_debit = Decimal('0')
            total_credit = Decimal('0')
            
            for account in accounts:
                # حساب الرصيد للحساب
                balance_details = cls.calculate_account_balance_detailed(
                    account, date_from, date_to
                )
                
                if abs(balance_details['balance']) > Decimal('0.01'):  # تجاهل الأرصدة الصفرية
                    # تحديد الرصيد المدين والدائن
                    if account.account_type.nature == 'debit':
                        if balance_details['balance'] >= 0:
                            debit_balance = balance_details['balance']
                            credit_balance = Decimal('0')
                        else:
                            debit_balance = Decimal('0')
                            credit_balance = abs(balance_details['balance'])
                    else:  # credit nature
                        if balance_details['balance'] >= 0:
                            debit_balance = Decimal('0')
                            credit_balance = balance_details['balance']
                        else:
                            debit_balance = abs(balance_details['balance'])
                            credit_balance = Decimal('0')
                    
                    row = {
                        'account_code': account.code,
                        'code': account.code,
                        'name': account.name,
                        'account_type_name': account.account_type.name,
                        'nature': account.account_type.nature,
                        'total_debit': balance_details['total_debits'],
                        'total_credit': balance_details['total_credits'],
                        'balance': balance_details['balance'],
                        'debit_balance': debit_balance,
                        'credit_balance': credit_balance
                    }
                    
                    trial_balance.append(row)
                    total_debit += debit_balance
                    total_credit += credit_balance
            
            # إضافة الإجماليات
            trial_balance.append({
                'account_code': '',
                'code': '',
                'name': 'الإجمالي',
                'account_type_name': '',
                'nature': '',
                'total_debit': sum(item['total_debit'] for item in trial_balance),
                'total_credit': sum(item['total_credit'] for item in trial_balance),
                'balance': total_debit - total_credit,
                'debit_balance': total_debit,
                'credit_balance': total_credit
            })
            
            return trial_balance
            
        except Exception as e:
            logger.error(f"خطأ في حساب ميزان المراجعة: {str(e)}")
            return []
    
    @classmethod
    def create_balance_snapshot(cls, account: ChartOfAccounts, snapshot_date: date = None) -> bool:
        """
        إنشاء لقطة رصيد للحساب
        """
        if not snapshot_date:
            snapshot_date = timezone.now().date()
        
        try:
            # حساب الرصيد حتى التاريخ المحدد
            balance = cls.get_account_balance_optimized(
                account, date_to=snapshot_date, use_cache=False
            )
            
            # حساب عدد المعاملات
            transactions_count = JournalEntryLine.objects.filter(
                account=account,
                journal_entry__status='posted',
                journal_entry__date__lte=snapshot_date
            ).count()
            
            # آخر معاملة
            last_transaction = JournalEntryLine.objects.filter(
                account=account,
                journal_entry__status='posted',
                journal_entry__date__lte=snapshot_date
            ).order_by('-journal_entry__date', '-journal_entry__id').first()
            
            # إنشاء أو تحديث اللقطة
            snapshot, created = BalanceSnapshot.objects.update_or_create(
                account=account,
                snapshot_date=snapshot_date,
                defaults={
                    'balance': balance,
                    'transactions_count': transactions_count,
                    'last_transaction_id': last_transaction.journal_entry.id if last_transaction else None
                }
            )
            
            logger.info(f"تم إنشاء لقطة رصيد للحساب {account.code} بتاريخ {snapshot_date}")
            return True
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء لقطة الرصيد: {str(e)}")
            return False
    
    @classmethod
    def invalidate_account_cache(cls, account: ChartOfAccounts):
        """
        إبطال كاش الحساب
        """
        # إبطال الكاش المحلي
        AccountBalanceCache.invalidate_account(account)
        
        # إبطال كاش Redis
        pattern = f"{cls.CACHE_PREFIX}*{account.id}*"
        # يمكن تحسين هذا باستخدام Redis SCAN
        cache.delete_many([
            cls._generate_cache_key(account.id, None, None),
            cls._generate_cache_key(account.id, None, timezone.now().date()),
        ])
        
        logger.info(f"تم إبطال كاش الحساب {account.code}")
    
    @classmethod
    def _get_account_object(cls, account: Union[str, int, ChartOfAccounts]) -> ChartOfAccounts:
        """
        الحصول على كائن الحساب
        """
        if isinstance(account, ChartOfAccounts):
            return account
        elif isinstance(account, str):
            return ChartOfAccounts.objects.get(code=account, is_active=True)
        elif isinstance(account, int):
            return ChartOfAccounts.objects.get(id=account, is_active=True)
        else:
            raise ValueError("نوع الحساب غير صحيح")
    
    @classmethod
    def _generate_cache_key(cls, account_id: int, date_from: Optional[date], date_to: Optional[date]) -> str:
        """
        توليد مفتاح الكاش
        """
        key_parts = [cls.CACHE_PREFIX, str(account_id)]
        
        if date_from:
            key_parts.append(date_from.isoformat())
        else:
            key_parts.append('none')
        
        if date_to:
            key_parts.append(date_to.isoformat())
        else:
            key_parts.append('none')
        
        key = '_'.join(key_parts)
        
        # تشفير المفتاح إذا كان طويلاً
        if len(key) > 200:
            key = hashlib.md5(key.encode()).hexdigest()
        
        return key
    
    @classmethod
    def _calculate_balance_traditional(cls, account: ChartOfAccounts) -> Decimal:
        """
        حساب الرصيد بالطريقة التقليدية (احتياطي)
        """
        lines = JournalEntryLine.objects.filter(
            account=account,
            journal_entry__status='posted'
        ).aggregate(
            total_debit=models.Sum('debit'),
            total_credit=models.Sum('credit')
        )
        
        total_debit = lines['total_debit'] or Decimal('0')
        total_credit = lines['total_credit'] or Decimal('0')
        
        if account.nature == 'debit':
            return total_debit - total_credit
        else:
            return total_credit - total_debit
    
    @classmethod
    def bulk_refresh_balances(cls, accounts: List[ChartOfAccounts] = None) -> Dict:
        """
        تحديث أرصدة متعددة بشكل مجمع
        """
        if accounts is None:
            accounts = ChartOfAccounts.objects.filter(is_leaf=True, is_active=True)
        
        results = {
            'success': 0,
            'failed': 0,
            'errors': []
        }
        
        for account in accounts:
            try:
                cls.invalidate_account_cache(account)
                cls.get_account_balance_optimized(account, force_refresh=True)
                results['success'] += 1
            except Exception as e:
                results['failed'] += 1
                results['errors'].append(f"{account.code}: {str(e)}")
                logger.error(f"خطأ في تحديث رصيد الحساب {account.code}: {str(e)}")
        
        return results
    
    @classmethod
    def get_all_balances(cls, include_zero_balances: bool = False) -> List[Dict]:
        """
        الحصول على جميع أرصدة الحسابات
        """
        try:
            accounts = ChartOfAccounts.objects.filter(is_leaf=True, is_active=True).select_related('account_type')
            balances = []
            
            for account in accounts:
                try:
                    balance = cls.get_account_balance_optimized(account)
                    
                    # تخطي الحسابات ذات الرصيد صفر إذا لم يطلب المستخدم إدراجها
                    if not include_zero_balances and balance == 0:
                        continue
                    
                    # معالجة آمنة للحقول التي قد لا تكون موجودة
                    try:
                        is_bank_account = account.is_bank_account
                        is_cash_account = account.is_cash_account
                    except AttributeError:
                        # في حالة عدم وجود الحقول، استخدم فلترة بديلة
                        is_bank_account = 'بنك' in account.account_type.name.lower()
                        is_cash_account = 'نقدي' in account.account_type.name.lower() or 'صندوق' in account.account_type.name.lower()
                    
                    balances.append({
                        'account': account,
                        'balance': balance,
                        'account_code': account.code,
                        'account_name': account.name,
                        'account_type': account.account_type.name,
                        'account_category': account.account_type.category,
                        'is_bank_account': is_bank_account,
                        'is_cash_account': is_cash_account,
                    })
                except Exception as e:
                    logger.error(f"خطأ في حساب رصيد الحساب {account.code}: {str(e)}")
                    continue
            
            # ترتيب حسب كود الحساب
            balances.sort(key=lambda x: x['account_code'])
            
            return balances
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على جميع الأرصدة: {str(e)}")
            return []
