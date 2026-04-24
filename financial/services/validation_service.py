"""
خدمة التحقق من المعاملات المالية
Financial Validation Service

هذه الخدمة مسؤولة عن:
1. التحقق من وجود حساب محاسبي صحيح ومفعّل
2. التحقق من وجود فترة محاسبية مفتوحة
3. التحقق الشامل من المعاملات المالية
4. تسجيل محاولات التحقق المرفوضة
5. دعم الحالات الخاصة (opening, adjustment)
"""

import logging
from datetime import date
from typing import Optional, Tuple, Dict, Any
from django.utils import timezone

from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.journal_entry import AccountingPeriod
from financial.models.validation_audit_log import ValidationAuditLog
from financial.services.entity_mapper import EntityAccountMapper
from financial.services.error_messages import ErrorMessageGenerator
from financial.exceptions import (
    ChartOfAccountsValidationError,
    AccountingPeriodValidationError,
    FinancialValidationError
)

logger = logging.getLogger(__name__)


class FinancialValidationService:
    """
    خدمة التحقق من المعاملات المالية
    
    توفر دوال للتحقق من الشروط المحاسبية الأساسية قبل السماح بأي معاملة مالية.
    """
    
    @staticmethod
    def validate_chart_of_accounts(
        entity,
        entity_type: Optional[str] = None,
        raise_exception: bool = False
    ) -> Tuple[bool, str, Optional[ChartOfAccounts]]:
        """
        التحقق من وجود حساب محاسبي صحيح
        
        يتحقق من:
        1. وجود حساب محاسبي مرتبط بالكيان
        2. الحساب المحاسبي مفعّل (is_active=True)
        3. الحساب المحاسبي نهائي (is_leaf=True)
        
        Args:
            entity: الكيان المالي (عميل، مورد، موظف، إلخ)
            entity_type: نوع الكيان (اختياري، يُستنتج تلقائياً)
            raise_exception: رفع استثناء عند الفشل (افتراضي False)
            
        Returns:
            tuple: (is_valid: bool, error_message: str, account: ChartOfAccounts or None)
            
        Raises:
            ChartOfAccountsValidationError: إذا كان raise_exception=True وفشل التحقق
            
        Examples:
            >>> customer = Customer.objects.get(id=1)
            >>> is_valid, error_msg, account = FinancialValidationService.validate_chart_of_accounts(customer)
            >>> if not is_valid:
            ...     print(error_msg)
        """
        # استنتاج نوع الكيان إذا لم يُحدد
        if entity_type is None:
            entity_type = EntityAccountMapper.detect_entity_type(entity)
            if entity_type is None:
                error_msg = f"نوع الكيان غير معروف: {type(entity).__name__}"
                logger.warning(error_msg)
                if raise_exception:
                    raise ChartOfAccountsValidationError(
                        message=error_msg,
                        code='unknown_entity_type',
                        entity=entity
                    )
                return False, error_msg, None
        
        # الحصول على اسم الكيان
        entity_name = str(entity)
        
        # الحصول على الحساب المحاسبي
        account = EntityAccountMapper.get_account(entity, entity_type)
        
        # 1. التحقق من وجود الحساب المحاسبي
        if account is None:
            error_msg = ErrorMessageGenerator.chart_of_accounts_missing(
                entity_name=entity_name,
                entity_type=entity_type
            )
            
            if raise_exception:
                raise ChartOfAccountsValidationError(
                    message=error_msg,
                    code='missing_account',
                    entity=entity,
                    account=None
                )
            
            return False, error_msg, None
        
        # 2. التحقق من تفعيل الحساب المحاسبي
        if not account.is_active:
            error_msg = ErrorMessageGenerator.chart_of_accounts_inactive(
                account_code=account.code,
                account_name=account.name,
                entity_name=entity_name,
                entity_type=entity_type
            )
            
            if raise_exception:
                raise ChartOfAccountsValidationError(
                    message=error_msg,
                    code='inactive_account',
                    entity=entity,
                    account=account
                )
            
            return False, error_msg, account
        
        # 3. التحقق من أن الحساب نهائي
        if not account.is_leaf:
            error_msg = ErrorMessageGenerator.chart_of_accounts_not_leaf(
                account_code=account.code,
                account_name=account.name,
                entity_name=entity_name,
                entity_type=entity_type
            )
            
            if raise_exception:
                raise ChartOfAccountsValidationError(
                    message=error_msg,
                    code='not_leaf_account',
                    entity=entity,
                    account=account
                )
            
            return False, error_msg, account
        
        # جميع الشروط محققة
        logger.debug(f"نجح التحقق من الحساب المحاسبي للكيان: {entity_name}")
        return True, "", account
    
    @staticmethod
    def validate_accounting_period(
        transaction_date,
        entity: Any = None,
        entity_type: Optional[str] = None,
        raise_exception: bool = False
    ) -> Tuple[bool, str, Optional[AccountingPeriod]]:
        """
        التحقق من وجود فترة محاسبية مفتوحة
        
        يتحقق من:
        1. وجود فترة محاسبية للتاريخ المحدد
        2. الفترة المحاسبية مفتوحة (status='open')
        
        Args:
            transaction_date: تاريخ المعاملة (date object)
            entity: الكيان المالي (اختياري، للرسائل الأفضل)
            entity_type: نوع الكيان (اختياري)
            raise_exception: رفع استثناء عند الفشل (افتراضي False)
            
        Returns:
            tuple: (is_valid: bool, error_message: str, period: AccountingPeriod or None)
            
        Raises:
            AccountingPeriodValidationError: إذا كان raise_exception=True وفشل التحقق
            
        Examples:
            >>> from datetime import date
            >>> transaction_date = date(2024, 6, 15)
            >>> is_valid, error_msg, period = FinancialValidationService.validate_accounting_period(transaction_date)
            >>> if not is_valid:
            ...     print(error_msg)
        """
        # تحويل التاريخ إلى date إذا كان datetime
        if hasattr(transaction_date, 'date'):
            transaction_date = transaction_date.date()
        
        # الحصول على اسم الكيان إذا كان متوفراً
        entity_name = str(entity) if entity else None
        
        # البحث عن فترة محاسبية للتاريخ المحدد
        try:
            period = AccountingPeriod.objects.filter(
                start_date__lte=transaction_date,
                end_date__gte=transaction_date
            ).first()
        except Exception as e:
            error_msg = f"خطأ في البحث عن الفترة المحاسبية: {str(e)}"
            logger.error(error_msg)
            if raise_exception:
                raise AccountingPeriodValidationError(
                    message=error_msg,
                    code='database_error',
                    entity=entity,
                    transaction_date=transaction_date
                )
            return False, error_msg, None
        
        # 1. التحقق من وجود فترة محاسبية
        if period is None:
            error_msg = ErrorMessageGenerator.accounting_period_missing(
                transaction_date=transaction_date,
                entity_name=entity_name,
                entity_type=entity_type
            )
            
            if raise_exception:
                raise AccountingPeriodValidationError(
                    message=error_msg,
                    code='missing_period',
                    entity=entity,
                    period=None,
                    transaction_date=transaction_date
                )
            
            return False, error_msg, None
        
        # 2. التحقق من أن الفترة مفتوحة
        if period.status != 'open':
            error_msg = ErrorMessageGenerator.accounting_period_closed(
                period_name=period.name,
                transaction_date=transaction_date,
                entity_name=entity_name,
                entity_type=entity_type
            )
            
            if raise_exception:
                raise AccountingPeriodValidationError(
                    message=error_msg,
                    code='closed_period',
                    entity=entity,
                    period=period,
                    transaction_date=transaction_date
                )
            
            return False, error_msg, period
        
        # جميع الشروط محققة
        logger.debug(f"نجح التحقق من الفترة المحاسبية: {period.name}")
        return True, "", period
    
    @staticmethod
    def validate_transaction(
        entity,
        transaction_date,
        entity_type: Optional[str] = None,
        transaction_type: Optional[str] = None,
        transaction_amount: Optional[float] = None,
        user: Any = None,
        module: str = 'financial',
        view_name: Optional[str] = None,
        request: Any = None,
        raise_exception: bool = False,
        log_failures: bool = True
    ) -> Dict[str, Any]:
        """
        التحقق الشامل من المعاملة المالية
        
        يجمع جميع عمليات التحقق ويدعم الحالات الخاصة.
        
        Args:
            entity: الكيان المالي
            transaction_date: تاريخ المعاملة
            entity_type: نوع الكيان (اختياري)
            transaction_type: نوع المعاملة (اختياري، مثل: opening, adjustment)
            transaction_amount: مبلغ المعاملة (اختياري)
            user: المستخدم الذي يحاول المعاملة (اختياري)
            module: الوحدة (client, financial, etc.)
            view_name: اسم الـ view (اختياري)
            request: كائن الطلب HTTP (اختياري)
            raise_exception: رفع استثناء عند الفشل (افتراضي False)
            log_failures: تسجيل الفشل في ValidationAuditLog (افتراضي True)
            
        Returns:
            dict: {
                'is_valid': bool,
                'errors': list[str],
                'warnings': list[str],
                'period': AccountingPeriod or None,
                'account': ChartOfAccounts or None,
                'validation_details': dict
            }
            
        Examples:
            >>> customer = Customer.objects.get(id=1)
            >>> result = FinancialValidationService.validate_transaction(
            ...     entity=customer,
            ...     transaction_date=date(2024, 6, 15),
            ...     transaction_type='payment',
            ...     user=request.user,
            ...     module='client'
            ... )
            >>> if not result['is_valid']:
            ...     for error in result['errors']:
            ...         print(error)
        """
        # استنتاج نوع الكيان إذا لم يُحدد
        if entity_type is None:
            entity_type = EntityAccountMapper.detect_entity_type(entity)
        
        # تهيئة النتيجة
        result = {
            'is_valid': True,
            'errors': [],
            'warnings': [],
            'period': None,
            'account': None,
            'validation_details': {
                'chart_of_accounts_valid': False,
                'accounting_period_valid': False,
                'special_transaction': False,
                'bypass_applied': False
            }
        }
        
        entity_name = str(entity)
        entity_id = getattr(entity, 'id', None) or getattr(entity, 'pk', None)
        
        # معالجة الحالات الخاصة
        # 1. القيود الافتتاحية - تجاوز التحقق من الفترة المحاسبية
        if transaction_type == 'opening':
            result['warnings'].append(
                ErrorMessageGenerator.special_transaction_info('opening')
            )
            result['validation_details']['special_transaction'] = True
            result['validation_details']['bypass_applied'] = True
            
            # التحقق من الحساب المحاسبي فقط
            account_valid, account_error, account = FinancialValidationService.validate_chart_of_accounts(
                entity=entity,
                entity_type=entity_type,
                raise_exception=False
            )
            
            result['validation_details']['chart_of_accounts_valid'] = account_valid
            result['account'] = account
            
            if not account_valid:
                result['is_valid'] = False
                result['errors'].append(account_error)
                
                # تسجيل الفشل
                if log_failures and entity_id:
                    FinancialValidationService._log_validation_failure(
                        user=user,
                        entity=entity,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        entity_name=entity_name,
                        validation_type='chart_of_accounts',
                        failure_reason='missing_account' if account is None else 'invalid_account',
                        error_message=account_error,
                        module=module,
                        transaction_type=transaction_type,
                        transaction_date=transaction_date,
                        transaction_amount=transaction_amount,
                        view_name=view_name,
                        request=request,
                        is_bypass_attempt=True,
                        bypass_reason='opening_entry'
                    )
            
            return result
        
        # 1.5. دفع الرواتب - تجاوز التحقق من الحساب المحاسبي للموظف
        # الرواتب تُسجل في حساب محاسبي واحد للشركة (مستحقات الرواتب)
        # وليس لكل موظف على حدة
        if transaction_type == 'salary_payment' and entity_type == 'employee':
            result['warnings'].append(
                'دفع راتب - لا يتطلب حساب محاسبي منفصل للموظف'
            )
            result['validation_details']['special_transaction'] = True
            result['validation_details']['bypass_applied'] = True
            
            # التحقق من الفترة المحاسبية فقط
            period_valid, period_error, period = FinancialValidationService.validate_accounting_period(
                transaction_date=transaction_date,
                entity=entity,
                entity_type=entity_type,
                raise_exception=False
            )
            
            result['validation_details']['accounting_period_valid'] = period_valid
            result['period'] = period
            
            if not period_valid:
                result['is_valid'] = False
                result['errors'].append(period_error)
                
                # تسجيل الفشل
                if log_failures and entity_id:
                    FinancialValidationService._log_validation_failure(
                        user=user,
                        entity=entity,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        entity_name=entity_name,
                        validation_type='accounting_period',
                        failure_reason='missing_period' if period is None else 'closed_period',
                        error_message=period_error,
                        module=module,
                        transaction_type=transaction_type,
                        transaction_date=transaction_date,
                        transaction_amount=transaction_amount,
                        view_name=view_name,
                        request=request,
                        is_bypass_attempt=True,
                        bypass_reason='salary_payment_no_employee_account_needed'
                    )
            
            return result
        
        # 2. التسويات مع صلاحيات خاصة
        if transaction_type == 'adjustment' and user and hasattr(user, 'has_perm'):
            if user.has_perm('financial.bypass_period_check'):
                result['warnings'].append(
                    ErrorMessageGenerator.special_transaction_info('adjustment')
                )
                result['validation_details']['special_transaction'] = True
                result['validation_details']['bypass_applied'] = True
                
                # التحقق من الحساب المحاسبي فقط
                account_valid, account_error, account = FinancialValidationService.validate_chart_of_accounts(
                    entity=entity,
                    entity_type=entity_type,
                    raise_exception=False
                )
                
                result['validation_details']['chart_of_accounts_valid'] = account_valid
                result['account'] = account
                
                if not account_valid:
                    result['is_valid'] = False
                    result['errors'].append(account_error)
                    
                    # تسجيل الفشل
                    if log_failures and entity_id:
                        FinancialValidationService._log_validation_failure(
                            user=user,
                            entity=entity,
                            entity_type=entity_type,
                            entity_id=entity_id,
                            entity_name=entity_name,
                            validation_type='chart_of_accounts',
                            failure_reason='missing_account' if account is None else 'invalid_account',
                            error_message=account_error,
                            module=module,
                            transaction_type=transaction_type,
                            transaction_date=transaction_date,
                            transaction_amount=transaction_amount,
                            view_name=view_name,
                            request=request,
                            is_bypass_attempt=True,
                            bypass_reason='adjustment_with_special_permission'
                        )
                
                return result
        
        # التحقق العادي للمعاملات الأخرى
        # 1. التحقق من الحساب المحاسبي
        account_valid, account_error, account = FinancialValidationService.validate_chart_of_accounts(
            entity=entity,
            entity_type=entity_type,
            raise_exception=False
        )
        
        result['validation_details']['chart_of_accounts_valid'] = account_valid
        result['account'] = account
        
        if not account_valid:
            result['is_valid'] = False
            result['errors'].append(account_error)
        
        # 2. التحقق من الفترة المحاسبية
        period_valid, period_error, period = FinancialValidationService.validate_accounting_period(
            transaction_date=transaction_date,
            entity=entity,
            entity_type=entity_type,
            raise_exception=False
        )
        
        result['validation_details']['accounting_period_valid'] = period_valid
        result['period'] = period
        
        if not period_valid:
            result['is_valid'] = False
            result['errors'].append(period_error)
        
        # تسجيل الفشل إذا كان هناك أخطاء
        if not result['is_valid'] and log_failures and entity_id:
            # تحديد نوع التحقق الذي فشل
            if not account_valid and not period_valid:
                validation_type = 'both'
                failure_reason = 'missing_account_and_period'
            elif not account_valid:
                validation_type = 'chart_of_accounts'
                failure_reason = 'missing_account' if account is None else 'invalid_account'
            else:
                validation_type = 'accounting_period'
                failure_reason = 'missing_period' if period is None else 'closed_period'
            
            # توليد رسالة خطأ شاملة
            comprehensive_error = ErrorMessageGenerator.generate_comprehensive_message(
                errors=result['errors'],
                entity_name=entity_name,
                entity_type=entity_type,
                transaction_date=transaction_date,
                transaction_type=transaction_type
            )
            
            FinancialValidationService._log_validation_failure(
                user=user,
                entity=entity,
                entity_type=entity_type,
                entity_id=entity_id,
                entity_name=entity_name,
                validation_type=validation_type,
                failure_reason=failure_reason,
                error_message=comprehensive_error,
                module=module,
                transaction_type=transaction_type,
                transaction_date=transaction_date,
                transaction_amount=transaction_amount,
                view_name=view_name,
                request=request
            )
        
        # رفع استثناء إذا كان مطلوباً
        if not result['is_valid'] and raise_exception:
            comprehensive_error = ErrorMessageGenerator.generate_comprehensive_message(
                errors=result['errors'],
                entity_name=entity_name,
                entity_type=entity_type,
                transaction_date=transaction_date,
                transaction_type=transaction_type
            )
            raise FinancialValidationError(
                message=comprehensive_error,
                code='validation_failed',
                entity=entity,
                validation_type='comprehensive'
            )
        
        # تسجيل النجاح
        if result['is_valid']:
            logger.debug(f"نجح التحقق الشامل من المعاملة المالية للكيان: {entity_name}")
        
        return result
    
    @staticmethod
    def _log_validation_failure(
        user,
        entity,
        entity_type: str,
        entity_id: int,
        entity_name: str,
        validation_type: str,
        failure_reason: str,
        error_message: str,
        module: str,
        transaction_type: Optional[str] = None,
        transaction_date = None,
        transaction_amount: Optional[float] = None,
        view_name: Optional[str] = None,
        request: Any = None,
        is_bypass_attempt: bool = False,
        bypass_reason: Optional[str] = None
    ):
        """
        تسجيل محاولة تحقق فاشلة في ValidationAuditLog
        
        Args:
            user: المستخدم
            entity: الكيان المالي
            entity_type: نوع الكيان
            entity_id: معرف الكيان
            entity_name: اسم الكيان
            validation_type: نوع التحقق
            failure_reason: سبب الفشل
            error_message: رسالة الخطأ
            module: الوحدة
            transaction_type: نوع المعاملة (اختياري)
            transaction_date: تاريخ المعاملة (اختياري)
            transaction_amount: مبلغ المعاملة (اختياري)
            view_name: اسم الـ view (اختياري)
            request: كائن الطلب HTTP (اختياري)
            is_bypass_attempt: هل هي محاولة تجاوز (اختياري)
            bypass_reason: سبب التجاوز (اختياري)
        """
        try:
            ValidationAuditLog.log_validation_failure(
                user=user,
                entity_type=entity_type,
                entity_id=entity_id,
                entity_name=entity_name,
                validation_type=validation_type,
                failure_reason=failure_reason,
                error_message=error_message,
                module=module,
                transaction_type=transaction_type,
                transaction_date=transaction_date,
                transaction_amount=transaction_amount,
                view_name=view_name,
                request_path=request.path if request else None,
                is_bypass_attempt=is_bypass_attempt,
                bypass_reason=bypass_reason,
                request=request
            )
            logger.debug(f"تم تسجيل محاولة التحقق الفاشلة للكيان: {entity_name}")
        except Exception as e:
            logger.error(f"فشل في تسجيل محاولة التحقق الفاشلة: {str(e)}")
    
    @staticmethod
    def check_repeated_attempts(user, hours: int = 1, threshold: int = 3) -> Tuple[bool, int]:
        """
        التحقق من المحاولات المتكررة لمستخدم معين
        
        Args:
            user: المستخدم
            hours: عدد الساعات للبحث (افتراضي 1)
            threshold: عتبة المحاولات (افتراضي 3)
            
        Returns:
            tuple: (has_repeated_attempts: bool, count: int)
        """
        return ValidationAuditLog.check_repeated_attempts(user, hours, threshold)
