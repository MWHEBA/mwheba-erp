"""
خدمة تأمين التكامل المالي - Financial Integration Security Service
تتضمن معالجة الأخطاء الشاملة، آلية إعادة المحاولة، والمفاتيح الفريدة
"""

import logging
import time
import hashlib
import hmac
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional, List, Tuple
from django.db import transaction
from django.utils import timezone
from django.conf import settings
from django.core.cache import cache
from governance.services import IdempotencyService, AuditService
from core.utils.circuit_breaker import CircuitBreaker
import requests

logger = logging.getLogger(__name__)


class FinancialIntegrationSecurityService:
    """
    خدمة تأمين التكامل المالي مع معالجة الأخطاء الشاملة
    """
    
    # إعدادات إعادة المحاولة
    MAX_RETRIES = 3
    RETRY_DELAYS = [1, 3, 9]  # ثواني - تأخير متزايد
    REQUEST_TIMEOUT = 30  # ثانية
    
    # إعدادات Circuit Breaker
    CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT = 60
    
    def __init__(self):
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=self.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            recovery_timeout=self.CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
            name="financial_integration"
        )
    
    @classmethod
    def create_financial_transaction_with_security(
        cls, 
        transaction_type: str,
        transaction_data: Dict[str, Any],
        user=None,
        retry_on_failure: bool = True
    ) -> Dict[str, Any]:
        """
        إنشاء معاملة مالية مع تأمين شامل
        
        Args:
            transaction_type: نوع المعاملة (journal_entry, payment, etc.)
            transaction_data: بيانات المعاملة
            user: المستخدم المنفذ للعملية
            retry_on_failure: إعادة المحاولة عند الفشل
            
        Returns:
            Dict: نتيجة العملية مع معلومات الأمان
        """
        service = cls()
        
        # إنشاء مفتاح فريد للعملية
        idempotency_key = service._generate_idempotency_key(
            transaction_type, transaction_data
        )
        
        # فحص العمليات المكررة
        is_duplicate, existing_record, existing_result = IdempotencyService.check_operation_exists(
            operation_type=f"financial_{transaction_type}",
            idempotency_key=idempotency_key
        )
        
        if is_duplicate:
            return {
                'success': True,
                'is_duplicate': True,
                'transaction_id': existing_result.get('transaction_id'),
                'idempotency_key': idempotency_key,
                'message': 'تم تنفيذ العملية مسبقاً'
            }
        
        # تنفيذ العملية مع إعادة المحاولة
        if retry_on_failure:
            result = service._execute_with_retry(
                service._execute_financial_transaction,
                transaction_type,
                transaction_data,
                user,
                idempotency_key
            )
        else:
            result = service._execute_financial_transaction(
                transaction_type, transaction_data, user, idempotency_key
            )
        
        return result
    
    def _execute_financial_transaction(
        self, 
        transaction_type: str,
        transaction_data: Dict[str, Any],
        user,
        idempotency_key: str
    ) -> Dict[str, Any]:
        """
        تنفيذ المعاملة المالية الفعلية
        """
        start_time = time.time()
        
        try:
            with transaction.atomic():
                # تسجيل بداية العملية
                audit_data = {
                    'transaction_type': transaction_type,
                    'idempotency_key': idempotency_key,
                    'data_hash': self._hash_data(transaction_data),
                    'start_time': timezone.now().isoformat()
                }
                
                AuditService.log_operation(
                    operation_type='financial_transaction_start',
                    details=audit_data,
                    user=user
                )
                
                # تنفيذ العملية حسب النوع
                if transaction_type == 'journal_entry':
                    result = self._create_journal_entry_secure(transaction_data, user)
                elif transaction_type == 'payment':
                    result = self._process_payment_secure(transaction_data, user)
                elif transaction_type == 'fee_creation':
                    result = self._create_fee_secure(transaction_data, user)
                else:
                    raise ValueError(f"نوع معاملة غير مدعوم: {transaction_type}")
                
                # تسجيل نجاح العملية
                execution_time = time.time() - start_time
                
                success_result = {
                    'success': True,
                    'is_duplicate': False,
                    'transaction_id': result.get('id'),
                    'idempotency_key': idempotency_key,
                    'execution_time': execution_time,
                    'message': 'تم تنفيذ العملية بنجاح'
                }
                
                # حفظ نتيجة العملية للحماية من التكرار
                IdempotencyService.check_and_record_operation(
                    operation_type=f"financial_{transaction_type}",
                    idempotency_key=idempotency_key,
                    result_data=success_result,
                    user=user,
                    expires_in_hours=24
                )
                
                # تسجيل نهاية العملية
                AuditService.log_operation(
                    operation_type='financial_transaction_success',
                    details={
                        **audit_data,
                        'transaction_id': result.get('id'),
                        'execution_time': execution_time,
                        'end_time': timezone.now().isoformat()
                    },
                    user=user
                )
                
                return success_result
                
        except Exception as e:
            execution_time = time.time() - start_time
            
            # تسجيل فشل العملية
            error_details = {
                **audit_data,
                'error': str(e),
                'error_type': type(e).__name__,
                'execution_time': execution_time,
                'end_time': timezone.now().isoformat()
            }
            
            AuditService.log_operation(
                operation_type='financial_transaction_error',
                details=error_details,
                user=user
            )
            
            logger.error(f"فشل في تنفيذ المعاملة المالية: {e}")
            raise
    
    def _execute_with_retry(self, func, *args, **kwargs) -> Dict[str, Any]:
        """
        تنفيذ العملية مع آلية إعادة المحاولة
        """
        last_exception = None
        
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                # استخدام Circuit Breaker
                with self.circuit_breaker:
                    return func(*args, **kwargs)
                    
            except Exception as e:
                last_exception = e
                
                if attempt < self.MAX_RETRIES:
                    delay = self.RETRY_DELAYS[min(attempt, len(self.RETRY_DELAYS) - 1)]
                    logger.warning(
                        f"فشل في المحاولة {attempt + 1}/{self.MAX_RETRIES + 1}: {e}. "
                        f"إعادة المحاولة خلال {delay} ثانية..."
                    )
                    time.sleep(delay)
                else:
                    logger.error(f"فشل نهائي بعد {self.MAX_RETRIES + 1} محاولات: {e}")
                    break
        
        # إرجاع نتيجة الفشل
        return {
            'success': False,
            'error': str(last_exception),
            'error_type': type(last_exception).__name__,
            'attempts': self.MAX_RETRIES + 1,
            'message': f'فشل في تنفيذ العملية بعد {self.MAX_RETRIES + 1} محاولات'
        }
    
    def _create_journal_entry_secure(self, data: Dict[str, Any], user) -> Dict[str, Any]:
        """
        إنشاء قيد محاسبي مع تأمين
        """
        from financial.services.accounting_integration_service import AccountingIntegrationService
        
        # التحقق من صحة البيانات
        self._validate_journal_entry_data(data)
        
        # إنشاء القيد
        if data.get('entry_type') == 'sale':
            journal_entry = AccountingIntegrationService.create_sale_journal_entry(
                data['sale_object'], user
            )
        elif data.get('entry_type') == 'purchase':
            journal_entry = AccountingIntegrationService.create_purchase_journal_entry(
                data['purchase_object'], user
            )
        elif data.get('entry_type') == 'payment':
            journal_entry = AccountingIntegrationService.create_payment_journal_entry(
                data['payment_object'], data['payment_type'], user
            )
        else:
            raise ValueError(f"نوع قيد غير مدعوم: {data.get('entry_type')}")
        
        if not journal_entry:
            raise Exception("فشل في إنشاء القيد المحاسبي")
        
        return {
            'id': journal_entry.id,
            'number': journal_entry.number,
            'type': 'journal_entry'
        }
    
    def _process_payment_secure(self, data: Dict[str, Any], user) -> Dict[str, Any]:
        """
        معالجة دفعة مع تأمين
        """
        # التحقق من صحة البيانات
        self._validate_payment_data(data)
        
        # معالجة الدفعة (يمكن تخصيص هذا حسب نوع الدفعة)
        payment_result = self._process_payment_internal(data, user)
        
        return {
            'id': payment_result['id'],
            'amount': payment_result['amount'],
            'type': 'payment'
        }
    
    def _create_fee_secure(self, data: Dict[str, Any], user) -> Dict[str, Any]:
        """
        إنشاء رسوم مع تأمين
        """
        # التحقق من صحة البيانات
        self._validate_fee_data(data)
        
        # إنشاء الرسوم (يمكن تخصيص هذا حسب نوع الرسوم)
        fee_result = self._create_fee_internal(data, user)
        
        return {
            'id': fee_result['id'],
            'amount': fee_result['amount'],
            'type': 'fee'
        }
    
    def _validate_journal_entry_data(self, data: Dict[str, Any]):
        """
        التحقق من صحة بيانات القيد المحاسبي
        """
        required_fields = ['entry_type']
        
        for field in required_fields:
            if field not in data:
                raise ValueError(f"حقل مطلوب مفقود: {field}")
        
        entry_type = data['entry_type']
        
        if entry_type == 'sale' and 'sale_object' not in data:
            raise ValueError("كائن المبيعات مطلوب لقيد المبيعات")
        elif entry_type == 'purchase' and 'purchase_object' not in data:
            raise ValueError("كائن المشتريات مطلوب لقيد المشتريات")
        elif entry_type == 'payment' and ('payment_object' not in data or 'payment_type' not in data):
            raise ValueError("كائن الدفعة ونوعها مطلوبان لقيد الدفعة")
    
    def _validate_payment_data(self, data: Dict[str, Any]):
        """
        التحقق من صحة بيانات الدفعة
        """
        required_fields = ['amount', 'payment_method']
        
        for field in required_fields:
            if field not in data:
                raise ValueError(f"حقل مطلوب مفقود: {field}")
        
        # التحقق من صحة المبلغ
        try:
            amount = Decimal(str(data['amount']))
            if amount <= 0:
                raise ValueError("المبلغ يجب أن يكون أكبر من صفر")
        except (ValueError, TypeError):
            raise ValueError("مبلغ غير صحيح")
    
    def _validate_fee_data(self, data: Dict[str, Any]):
        """
        التحقق من صحة بيانات الرسوم
        """
        required_fields = ['customer_id', 'fee_type_id', 'amount']
        
        for field in required_fields:
            if field not in data:
                raise ValueError(f"حقل مطلوب مفقود: {field}")
        
        # التحقق من صحة المبلغ
        try:
            amount = Decimal(str(data['amount']))
            if amount <= 0:
                raise ValueError("مبلغ الرسوم يجب أن يكون أكبر من صفر")
        except (ValueError, TypeError):
            raise ValueError("مبلغ رسوم غير صحيح")
    
    def _process_payment_internal(self, data: Dict[str, Any], user) -> Dict[str, Any]:
        """
        معالجة داخلية للدفعة - يمكن تخصيصها حسب الحاجة
        """
        # هذا مثال بسيط - يجب تخصيصه حسب منطق العمل الفعلي
        return {
            'id': f"PAY_{int(time.time())}",
            'amount': data['amount'],
            'status': 'processed'
        }
    
    def _create_fee_internal(self, data: Dict[str, Any], user) -> Dict[str, Any]:
        """
        إنشاء داخلي للرسوم - يمكن تخصيصه حسب الحاجة
        """
        # هذا مثال بسيط - يجب تخصيصه حسب منطق العمل الفعلي
        return {
            'id': f"FEE_{int(time.time())}",
            'amount': data['amount'],
            'status': 'created'
        }
    
    def _generate_idempotency_key(self, transaction_type: str, data: Dict[str, Any]) -> str:
        """
        إنشاء مفتاح فريد للعملية
        """
        # إنشاء hash من البيانات المهمة
        key_data = {
            'type': transaction_type,
            'timestamp': timezone.now().date().isoformat(),
            'data_hash': self._hash_data(data)
        }
        
        key_string = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_string.encode()).hexdigest()[:32]
    
    def _hash_data(self, data: Dict[str, Any]) -> str:
        """
        إنشاء hash من البيانات
        """
        # إزالة البيانات الحساسة أو المتغيرة
        clean_data = {k: v for k, v in data.items() 
                     if k not in ['created_at', 'updated_at', 'id']}
        
        data_string = json.dumps(clean_data, sort_keys=True, default=str)
        return hashlib.md5(data_string.encode()).hexdigest()
    
    @classmethod
    def get_integration_health_status(cls) -> Dict[str, Any]:
        """
        الحصول على حالة صحة التكامل المالي
        """
        service = cls()
        
        health_status = {
            'status': 'healthy',
            'timestamp': timezone.now().isoformat(),
            'circuit_breaker': service.circuit_breaker.get_status(),
            'recent_operations': cls._get_recent_operations_stats(),
            'error_rate': cls._calculate_error_rate(),
            'recommendations': []
        }
        
        # تحليل الحالة
        if service.circuit_breaker.state == 'open':
            health_status['status'] = 'critical'
            health_status['recommendations'].append('Circuit breaker مفتوح - فحص الخدمات الخارجية')
        
        error_rate = health_status['error_rate']
        if error_rate > 0.1:  # أكثر من 10% أخطاء
            health_status['status'] = 'warning'
            health_status['recommendations'].append(f'معدل أخطاء عالي: {error_rate:.1%}')
        
        return health_status
    
    @classmethod
    def _get_recent_operations_stats(cls) -> Dict[str, int]:
        """
        إحصائيات العمليات الحديثة
        """
        # يمكن تحسين هذا باستخدام قاعدة البيانات أو cache
        cache_key = 'financial_integration_stats'
        stats = cache.get(cache_key, {
            'total_operations': 0,
            'successful_operations': 0,
            'failed_operations': 0
        })
        
        return stats
    
    @classmethod
    def _calculate_error_rate(cls) -> float:
        """
        حساب معدل الأخطاء
        """
        stats = cls._get_recent_operations_stats()
        total = stats.get('total_operations', 0)
        
        if total == 0:
            return 0.0
        
        failed = stats.get('failed_operations', 0)
        return failed / total
    
    @classmethod
    def create_audit_trail(
        cls,
        transaction_id: str,
        transaction_type: str,
        details: Dict[str, Any],
        user=None
    ):
        """
        إنشاء مسار تدقيق للمعاملات المالية
        """
        audit_data = {
            'transaction_id': transaction_id,
            'transaction_type': transaction_type,
            'details': details,
            'timestamp': timezone.now().isoformat(),
            'user_id': user.id if user else None,
            'user_name': user.username if user else 'System'
        }
        
        # حفظ في سجل التدقيق
        AuditService.log_operation(
            operation_type='financial_audit_trail',
            details=audit_data,
            user=user
        )
        
        # حفظ في cache للوصول السريع
        cache_key = f'audit_trail_{transaction_id}'
        cache.set(cache_key, audit_data, timeout=86400)  # 24 ساعة
        
