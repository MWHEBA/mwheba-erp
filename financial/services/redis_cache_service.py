"""
خدمة Redis Cache المتقدمة للنظام المالي
"""
import json
import redis
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from decimal import Decimal
from typing import Dict, List, Optional, Any, Union
from datetime import date, datetime, timedelta
import logging
import hashlib
import pickle

logger = logging.getLogger(__name__)


class RedisFinancialCache:
    """
    خدمة Redis Cache المتخصصة للبيانات المالية
    """
    
    def __init__(self):
        # إعدادات Redis
        self.redis_host = getattr(settings, 'REDIS_HOST', 'localhost')
        self.redis_port = getattr(settings, 'REDIS_PORT', 6379)
        self.redis_db = getattr(settings, 'REDIS_FINANCIAL_DB', 1)
        self.redis_password = getattr(settings, 'REDIS_PASSWORD', None)
        
        # إعدادات الكاش
        self.default_timeout = getattr(settings, 'FINANCIAL_CACHE_TIMEOUT', 3600)
        self.key_prefix = 'financial:'
        
        # تحديد ما إذا كان يجب استخدام Redis
        # يمكن التحكم عبر الإعداد USE_REDIS_FINANCIAL، والافتراضي: تعطيل Redis إذا كان Backend هو LocMem
        self.use_redis = getattr(settings, 'USE_REDIS_FINANCIAL', None)
        if self.use_redis is None:
            try:
                default_backend = settings.CACHES.get('default', {}).get('BACKEND', '')
            except Exception:
                default_backend = ''
            self.use_redis = 'locmem' not in str(default_backend).lower()

        if not self.use_redis:
            # عدم استخدام Redis - الاعتماد على Django cache
            self.redis_available = False
            self.redis_client = None
            logger.info("سيتم استخدام Django cache للبيانات المالية (Redis معطل).")
        else:
            # الاتصال بـ Redis
            try:
                self.redis_client = redis.Redis(
                    host=self.redis_host,
                    port=self.redis_port,
                    db=self.redis_db,
                    password=self.redis_password,
                    decode_responses=False  # للتعامل مع البيانات المخزنة بـ pickle
                )
                # اختبار الاتصال
                self.redis_client.ping()
                self.redis_available = True
                logger.info("تم الاتصال بـ Redis بنجاح")
            except Exception as e:
                logger.warning(f"فشل الاتصال بـ Redis: {str(e)}، سيتم استخدام Django cache")
                self.redis_available = False
                self.redis_client = None
    
    def _generate_key(self, key_type: str, **kwargs) -> str:
        """
        توليد مفتاح الكاش
        """
        key_parts = [self.key_prefix, key_type]
        
        for k, v in sorted(kwargs.items()):
            if v is not None:
                if isinstance(v, date):
                    v = v.isoformat()
                elif isinstance(v, datetime):
                    v = v.isoformat()
                key_parts.append(f"{k}:{v}")
        
        key = ':'.join(key_parts)
        
        # تشفير المفتاح إذا كان طويلاً باستخدام SHA-256 (آمن)
        if len(key) > 200:
            key = f"{self.key_prefix}hash:{hashlib.sha256(key.encode()).hexdigest()}"
        
        return key
    
    def _serialize_data(self, data: Any) -> bytes:
        """
        تسلسل البيانات للتخزين
        """
        # تحويل Decimal إلى string قبل التسلسل
        if isinstance(data, dict):
            data = self._convert_decimals_to_string(data)
        elif isinstance(data, list):
            data = [self._convert_decimals_to_string(item) if isinstance(item, dict) else item for item in data]
        
        return pickle.dumps(data)
    
    def _deserialize_data(self, data: bytes) -> Any:
        """
        إلغاء تسلسل البيانات
        """
        result = pickle.loads(data)
        
        # تحويل string إلى Decimal
        if isinstance(result, dict):
            result = self._convert_strings_to_decimal(result)
        elif isinstance(result, list):
            result = [self._convert_strings_to_decimal(item) if isinstance(item, dict) else item for item in result]
        
        return result
    
    def _convert_decimals_to_string(self, data: Dict) -> Dict:
        """
        تحويل Decimal إلى string للتسلسل
        """
        result = {}
        for key, value in data.items():
            if isinstance(value, Decimal):
                result[key] = str(value)
            elif isinstance(value, dict):
                result[key] = self._convert_decimals_to_string(value)
            elif isinstance(value, list):
                result[key] = [
                    self._convert_decimals_to_string(item) if isinstance(item, dict) 
                    else str(item) if isinstance(item, Decimal) 
                    else item 
                    for item in value
                ]
            else:
                result[key] = value
        return result
    
    def _convert_strings_to_decimal(self, data: Dict) -> Dict:
        """
        تحويل string إلى Decimal بعد إلغاء التسلسل
        """
        # قائمة الحقول المالية التي يجب تحويلها إلى Decimal
        decimal_fields = {
            'balance', 'current_balance', 'available_balance', 'pending_balance',
            'total_debit', 'total_credit', 'debit', 'credit', 'amount',
            'running_balance', 'min_balance', 'max_balance', 'avg_balance',
            'debit_balance', 'credit_balance', 'total_activity', 'avg_transaction_size',
            'balance_volatility', 'trend_direction', 'daily_change_rate',
            'monthly_debit', 'monthly_credit', 'monthly_net', 'cumulative_balance'
        }
        
        result = {}
        for key, value in data.items():
            if key in decimal_fields and isinstance(value, str):
                try:
                    result[key] = Decimal(value)
                except:
                    result[key] = value
            elif isinstance(value, dict):
                result[key] = self._convert_strings_to_decimal(value)
            elif isinstance(value, list):
                result[key] = [
                    self._convert_strings_to_decimal(item) if isinstance(item, dict) 
                    else Decimal(item) if isinstance(item, str) and key in decimal_fields
                    else item 
                    for item in value
                ]
            else:
                result[key] = value
        return result
    
    def get(self, key_type: str, default=None, **kwargs) -> Any:
        """
        الحصول على قيمة من الكاش
        """
        key = self._generate_key(key_type, **kwargs)
        
        try:
            if self.redis_available:
                data = self.redis_client.get(key)
                if data:
                    return self._deserialize_data(data)
            else:
                # استخدام Django cache كبديل
                return cache.get(key, default)
        except Exception as e:
            logger.error(f"خطأ في الحصول على البيانات من الكاش: {str(e)}")
        
        return default
    
    def set(self, key_type: str, value: Any, timeout: Optional[int] = None, **kwargs) -> bool:
        """
        حفظ قيمة في الكاش
        """
        key = self._generate_key(key_type, **kwargs)
        timeout = timeout or self.default_timeout
        
        try:
            if self.redis_available:
                serialized_data = self._serialize_data(value)
                return self.redis_client.setex(key, timeout, serialized_data)
            else:
                # استخدام Django cache كبديل
                cache.set(key, value, timeout)
                return True
        except Exception as e:
            logger.error(f"خطأ في حفظ البيانات في الكاش: {str(e)}")
            return False
    
    def delete(self, key_type: str, **kwargs) -> bool:
        """
        حذف قيمة من الكاش
        """
        key = self._generate_key(key_type, **kwargs)
        
        try:
            if self.redis_available:
                return bool(self.redis_client.delete(key))
            else:
                cache.delete(key)
                return True
        except Exception as e:
            logger.error(f"خطأ في حذف البيانات من الكاش: {str(e)}")
            return False
    
    def delete_pattern(self, pattern: str) -> int:
        """
        حذف جميع المفاتيح التي تطابق النمط
        """
        if not self.redis_available:
            logger.warning("Redis غير متاح، لا يمكن حذف النمط")
            return 0
        
        try:
            full_pattern = f"{self.key_prefix}{pattern}"
            keys = self.redis_client.keys(full_pattern)
            if keys:
                return self.redis_client.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"خطأ في حذف النمط من الكاش: {str(e)}")
            return 0
    
    def invalidate_account_cache(self, account_id: int) -> int:
        """
        إبطال جميع كاش الحساب
        """
        patterns = [
            f"balance:*account_id:{account_id}*",
            f"statement:*account_id:{account_id}*",
            f"running_balances:*account_id:{account_id}*"
        ]
        
        deleted_count = 0
        for pattern in patterns:
            deleted_count += self.delete_pattern(pattern)
        
        logger.info(f"تم حذف {deleted_count} مفتاح كاش للحساب {account_id}")
        return deleted_count
    
    def get_cache_stats(self) -> Dict:
        """
        إحصائيات الكاش
        """
        if not self.redis_available:
            return {'status': 'Redis غير متاح'}
        
        try:
            info = self.redis_client.info()
            
            # البحث عن المفاتيح المالية
            financial_keys = self.redis_client.keys(f"{self.key_prefix}*")
            
            return {
                'redis_version': info.get('redis_version'),
                'used_memory_human': info.get('used_memory_human'),
                'connected_clients': info.get('connected_clients'),
                'total_commands_processed': info.get('total_commands_processed'),
                'financial_keys_count': len(financial_keys),
                'keyspace_hits': info.get('keyspace_hits', 0),
                'keyspace_misses': info.get('keyspace_misses', 0),
                'hit_rate': self._calculate_hit_rate(
                    info.get('keyspace_hits', 0),
                    info.get('keyspace_misses', 0)
                )
            }
        except Exception as e:
            logger.error(f"خطأ في الحصول على إحصائيات الكاش: {str(e)}")
            return {'error': str(e)}
    
    def _calculate_hit_rate(self, hits: int, misses: int) -> float:
        """
        حساب معدل نجاح الكاش
        """
        total = hits + misses
        if total == 0:
            return 0.0
        return (hits / total) * 100
    
    def clear_all_financial_cache(self) -> int:
        """
        مسح جميع الكاش المالي
        """
        return self.delete_pattern("*")


# إنشاء instance عام
financial_cache = RedisFinancialCache()


class CachedBalanceService:
    """
    خدمة الأرصدة مع استخدام الكاش المتقدم
    """
    
    @staticmethod
    def get_account_balance(
        account_id: int,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        use_cache: bool = True
    ) -> Decimal:
        """
        الحصول على رصيد الحساب مع استخدام الكاش
        """
        if not use_cache:
            from .enhanced_balance_service import EnhancedBalanceService
            return EnhancedBalanceService.get_account_balance_optimized(
                account_id, date_from, date_to, use_cache=False
            )
        
        # محاولة الحصول من الكاش
        cached_balance = financial_cache.get(
            'balance',
            account_id=account_id,
            date_from=date_from,
            date_to=date_to
        )
        
        if cached_balance is not None:
            logger.debug(f"تم الحصول على رصيد الحساب {account_id} من الكاش")
            return cached_balance
        
        # حساب الرصيد وحفظه في الكاش
        from .enhanced_balance_service import EnhancedBalanceService
        from ..models.chart_of_accounts import ChartOfAccounts
        
        try:
            account_obj = ChartOfAccounts.objects.get(id=account_id)
            balance = EnhancedBalanceService.get_account_balance_optimized(
                account_obj, date_from, date_to, use_cache=False
            )
        except ChartOfAccounts.DoesNotExist:
            logger.error(f"الحساب {account_id} غير موجود")
            return Decimal('0')
        
        # تحديد مدة الكاش حسب نوع الاستعلام
        if date_to is None:
            # رصيد حالي - كاش قصير المدى
            timeout = 300  # 5 دقائق
        else:
            # رصيد تاريخي - كاش طويل المدى
            timeout = 3600  # ساعة واحدة
        
        financial_cache.set(
            'balance',
            balance,
            timeout=timeout,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to
        )
        
        logger.debug(f"تم حفظ رصيد الحساب {account_id} في الكاش")
        return balance
    
    @staticmethod
    def get_trial_balance_cached(
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        use_cache: bool = True
    ) -> List[Dict]:
        """
        ميزان المراجعة مع الكاش
        """
        if not use_cache:
            from .enhanced_balance_service import EnhancedBalanceService
            return EnhancedBalanceService.get_trial_balance_optimized(date_from, date_to)
        
        # محاولة الحصول من الكاش
        cached_trial_balance = financial_cache.get(
            'trial_balance',
            date_from=date_from,
            date_to=date_to
        )
        
        if cached_trial_balance is not None:
            logger.debug("تم الحصول على ميزان المراجعة من الكاش")
            return cached_trial_balance
        
        # حساب ميزان المراجعة وحفظه في الكاش
        from .enhanced_balance_service import EnhancedBalanceService
        trial_balance = EnhancedBalanceService.get_trial_balance_optimized(date_from, date_to)
        
        # كاش لمدة 30 دقيقة
        financial_cache.set(
            'trial_balance',
            trial_balance,
            timeout=1800,
            date_from=date_from,
            date_to=date_to
        )
        
        logger.debug("تم حفظ ميزان المراجعة في الكاش")
        return trial_balance
    
    @staticmethod
    def invalidate_account_cache(account_id: int):
        """
        إبطال كاش الحساب
        """
        financial_cache.invalidate_account_cache(account_id)
        
        # إبطال ميزان المراجعة أيضاً
        financial_cache.delete_pattern("trial_balance:*")
        
        logger.info(f"تم إبطال كاش الحساب {account_id}")


# تصدير الخدمات
__all__ = ['RedisFinancialCache', 'financial_cache', 'CachedBalanceService']
