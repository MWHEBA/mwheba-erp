"""
مُزخرفات (Decorators) للتحقق من المعاملات المالية
Financial Validation Decorators

هذا الملف يحتوي على decorators يمكن تطبيقها على الدوال والطرق
التي تتعامل مع معاملات مالية لضمان التحقق التلقائي من الشروط المحاسبية.
"""

import logging
from functools import wraps
from typing import Optional, Callable, Any
from datetime import date

from financial.services.validation_service import FinancialValidationService
from financial.exceptions import FinancialValidationError

logger = logging.getLogger(__name__)


def require_financial_validation(
    entity_param: str = 'entity',
    entity_type_param: Optional[str] = None,
    date_param: str = 'date',
    transaction_type_param: Optional[str] = None,
    transaction_type: Optional[str] = None,
    amount_param: Optional[str] = None,
    allow_bypass: bool = False,
    module: str = 'financial'
):
    """
    مُزخرف للتحقق من المعاملات المالية
    
    يطبق التحقق التلقائي من:
    1. وجود حساب محاسبي صحيح ومفعّل
    2. وجود فترة محاسبية مفتوحة
    
    Args:
        entity_param: اسم المعامل الذي يحتوي على الكيان المالي (افتراضي 'entity')
        entity_type_param: اسم المعامل الذي يحتوي على نوع الكيان (اختياري، يُستنتج تلقائياً)
        date_param: اسم المعامل الذي يحتوي على تاريخ المعاملة (افتراضي 'date')
        transaction_type_param: اسم المعامل الذي يحتوي على نوع المعاملة (اختياري)
        transaction_type: نوع المعاملة الثابت (اختياري، يُستخدم إذا لم يكن transaction_type_param محدداً)
        amount_param: اسم المعامل الذي يحتوي على مبلغ المعاملة (اختياري)
        allow_bypass: السماح بتجاوز التحقق للحالات الخاصة (افتراضي False)
        module: اسم الوحدة (افتراضي 'financial')
        
    Returns:
        Callable: الدالة المزخرفة
        
    Raises:
        FinancialValidationError: إذا فشل التحقق من المعاملة المالية
        
    Usage:
        # مثال بسيط
        @require_financial_validation(entity_param='customer', date_param='payment_date')
        def process_customer_payment(customer, amount, payment_date):
            # معالجة الدفعة
            pass
        
        # مثال مع نوع معاملة
        @require_financial_validation(
            entity_param='supplier',
            date_param='payment_date',
            transaction_type='payment',
            module='supplier'
        )
        def process_supplier_payment(supplier, amount, payment_date):
            # معالجة دفعة المورد
            pass
        
        # مثال مع طريقة في class
        class CustomerPaymentView(View):
            @require_financial_validation(
                entity_param='customer',
                date_param='payment_date',
                module='client'
            )
            def post(self, request, customer_id):
                customer = Customer.objects.get(id=customer_id)
                # معالجة الدفعة
                pass
    """
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # استخراج المعاملات
            entity = kwargs.get(entity_param)
            transaction_date = kwargs.get(date_param)
            entity_type = kwargs.get(entity_type_param) if entity_type_param else None
            
            # استخراج نوع المعاملة
            current_transaction_type = transaction_type
            if transaction_type_param:
                current_transaction_type = kwargs.get(transaction_type_param, transaction_type)
            
            # استخراج مبلغ المعاملة
            transaction_amount = None
            if amount_param:
                transaction_amount = kwargs.get(amount_param)
            
            # استخراج المستخدم من request إذا كان موجوداً
            user = None
            request = None
            
            # محاولة الحصول على request من args (للطرق في class-based views)
            if args and hasattr(args[0], 'request'):
                request = args[0].request
                user = getattr(request, 'user', None)
            # محاولة الحصول على request من kwargs
            elif 'request' in kwargs:
                request = kwargs['request']
                user = getattr(request, 'user', None)
            # محاولة الحصول على user مباشرة من kwargs
            elif 'user' in kwargs:
                user = kwargs['user']
            
            # التحقق من وجود المعاملات المطلوبة
            if entity is None:
                error_msg = f"المعامل '{entity_param}' مطلوب للتحقق من المعاملة المالية"
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            if transaction_date is None:
                error_msg = f"المعامل '{date_param}' مطلوب للتحقق من المعاملة المالية"
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            # تحويل التاريخ إلى date إذا كان datetime
            if hasattr(transaction_date, 'date'):
                transaction_date = transaction_date.date()
            
            # الحصول على اسم الدالة/الطريقة
            view_name = func.__name__
            
            # إجراء التحقق
            try:
                validation_result = FinancialValidationService.validate_transaction(
                    entity=entity,
                    transaction_date=transaction_date,
                    entity_type=entity_type,
                    transaction_type=current_transaction_type,
                    transaction_amount=transaction_amount,
                    user=user,
                    module=module,
                    view_name=view_name,
                    request=request,
                    raise_exception=True,  # رفع استثناء عند الفشل
                    log_failures=True  # تسجيل الفشل
                )
                
                # إضافة نتيجة التحقق إلى kwargs للاستخدام في الدالة
                kwargs['_validation_result'] = validation_result
                
                # تسجيل النجاح
                logger.debug(
                    f"نجح التحقق من المعاملة المالية في {view_name} "
                    f"للكيان: {entity}"
                )
                
            except FinancialValidationError as e:
                # تسجيل الفشل
                logger.warning(
                    f"فشل التحقق من المعاملة المالية في {view_name}: {str(e)}"
                )
                
                # إعادة رفع الاستثناء لمعالجته في الـ view
                raise
            
            # تنفيذ الدالة الأصلية
            return func(*args, **kwargs)
        
        return wrapper
    
    return decorator


def require_chart_of_accounts_only(
    entity_param: str = 'entity',
    entity_type_param: Optional[str] = None,
    module: str = 'financial'
):
    """
    مُزخرف للتحقق من الحساب المحاسبي فقط (بدون التحقق من الفترة المحاسبية)
    
    يستخدم للحالات التي تحتاج التحقق من الحساب المحاسبي فقط،
    مثل القيود الافتتاحية أو التقارير.
    
    Args:
        entity_param: اسم المعامل الذي يحتوي على الكيان المالي
        entity_type_param: اسم المعامل الذي يحتوي على نوع الكيان (اختياري)
        module: اسم الوحدة
        
    Returns:
        Callable: الدالة المزخرفة
        
    Raises:
        FinancialValidationError: إذا فشل التحقق من الحساب المحاسبي
        
    Usage:
        @require_chart_of_accounts_only(entity_param='customer')
        def generate_customer_report(customer):
            # توليد التقرير
            pass
    """
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # استخراج المعاملات
            entity = kwargs.get(entity_param)
            entity_type = kwargs.get(entity_type_param) if entity_type_param else None
            
            # التحقق من وجود الكيان
            if entity is None:
                error_msg = f"المعامل '{entity_param}' مطلوب للتحقق من الحساب المحاسبي"
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            # الحصول على اسم الدالة/الطريقة
            view_name = func.__name__
            
            # إجراء التحقق من الحساب المحاسبي فقط
            try:
                is_valid, error_msg, account = FinancialValidationService.validate_chart_of_accounts(
                    entity=entity,
                    entity_type=entity_type,
                    raise_exception=True
                )
                
                # إضافة الحساب المحاسبي إلى kwargs للاستخدام في الدالة
                kwargs['_account'] = account
                
                # تسجيل النجاح
                logger.debug(
                    f"نجح التحقق من الحساب المحاسبي في {view_name} "
                    f"للكيان: {entity}"
                )
                
            except FinancialValidationError as e:
                # تسجيل الفشل
                logger.warning(
                    f"فشل التحقق من الحساب المحاسبي في {view_name}: {str(e)}"
                )
                
                # إعادة رفع الاستثناء
                raise
            
            # تنفيذ الدالة الأصلية
            return func(*args, **kwargs)
        
        return wrapper
    
    return decorator


def require_accounting_period_only(
    date_param: str = 'date',
    module: str = 'financial'
):
    """
    مُزخرف للتحقق من الفترة المحاسبية فقط (بدون التحقق من الحساب المحاسبي)
    
    يستخدم للحالات التي تحتاج التحقق من الفترة المحاسبية فقط،
    مثل القيود اليومية العامة.
    
    Args:
        date_param: اسم المعامل الذي يحتوي على تاريخ المعاملة
        module: اسم الوحدة
        
    Returns:
        Callable: الدالة المزخرفة
        
    Raises:
        FinancialValidationError: إذا فشل التحقق من الفترة المحاسبية
        
    Usage:
        @require_accounting_period_only(date_param='entry_date')
        def create_journal_entry(entry_date, description, amount):
            # إنشاء القيد اليومي
            pass
    """
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # استخراج التاريخ
            transaction_date = kwargs.get(date_param)
            
            # التحقق من وجود التاريخ
            if transaction_date is None:
                error_msg = f"المعامل '{date_param}' مطلوب للتحقق من الفترة المحاسبية"
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            # تحويل التاريخ إلى date إذا كان datetime
            if hasattr(transaction_date, 'date'):
                transaction_date = transaction_date.date()
            
            # الحصول على اسم الدالة/الطريقة
            view_name = func.__name__
            
            # إجراء التحقق من الفترة المحاسبية فقط
            try:
                is_valid, error_msg, period = FinancialValidationService.validate_accounting_period(
                    transaction_date=transaction_date,
                    raise_exception=True
                )
                
                # إضافة الفترة المحاسبية إلى kwargs للاستخدام في الدالة
                kwargs['_period'] = period
                
                # تسجيل النجاح
                logger.debug(
                    f"نجح التحقق من الفترة المحاسبية في {view_name} "
                    f"للتاريخ: {transaction_date}"
                )
                
            except FinancialValidationError as e:
                # تسجيل الفشل
                logger.warning(
                    f"فشل التحقق من الفترة المحاسبية في {view_name}: {str(e)}"
                )
                
                # إعادة رفع الاستثناء
                raise
            
            # تنفيذ الدالة الأصلية
            return func(*args, **kwargs)
        
        return wrapper
    
    return decorator
