"""
إشارات التحقق من المعاملات المالية
Financial Validation Signals

هذا الملف يحتوي على الإشارات (signals) المستخدمة للتحقق التلقائي من المعاملات المالية
المولدة من النظام. يوفر آلية للتحقق من الشروط المحاسبية قبل حفظ أي معاملة مالية.
"""

import logging
import django.dispatch
from django.db.models.signals import pre_save
from django.dispatch import receiver

# Governance integration
from governance.signal_integration import governed_signal_handler

logger = logging.getLogger(__name__)


# تعريف signal مخصص للتحقق من المعاملات المالية
pre_financial_transaction = django.dispatch.Signal()


class FinancialTransactionSignalHandler:
    """
    معالج إشارات المعاملات المالية
    
    يوفر دوال لمعالجة الإشارات المتعلقة بالمعاملات المالية والتحقق منها تلقائياً.
    """
    
    @staticmethod
    def validate_transaction_signal(
        sender,
        entity,
        transaction_date,
        entity_type=None,
        transaction_type=None,
        transaction_amount=None,
        user=None,
        module='financial',
        is_system_generated=False,
        **kwargs
    ):
        """
        معالج signal للتحقق من المعاملة المالية
        
        يُطلق هذا المعالج قبل أي معاملة مالية للتحقق من الشروط المحاسبية.
        يعالج المعاملات المولدة من النظام بشكل خاص.
        
        Args:
            sender: الكلاس الذي أرسل الإشارة
            entity: الكيان المالي
            transaction_date: تاريخ المعاملة
            entity_type: نوع الكيان (اختياري)
            transaction_type: نوع المعاملة (اختياري)
            transaction_amount: مبلغ المعاملة (اختياري)
            user: المستخدم الذي يحاول المعاملة (اختياري)
            module: الوحدة (client, financial, etc.)
            is_system_generated: هل المعاملة مولدة من النظام (افتراضي False)
            **kwargs: معاملات إضافية
            
        Returns:
            dict: نتيجة التحقق
            
        Raises:
            FinancialValidationError: إذا فشل التحقق
        """
        from financial.services.validation_service import FinancialValidationService
        
        # تسجيل محاولة التحقق
        
        # التحقق من المعاملة
        result = FinancialValidationService.validate_transaction(
            entity=entity,
            transaction_date=transaction_date,
            entity_type=entity_type,
            transaction_type=transaction_type,
            transaction_amount=transaction_amount,
            user=user,
            module=module,
            raise_exception=True,  # رفع استثناء عند الفشل
            log_failures=True
        )
        
        # معالجة خاصة للمعاملات المولدة من النظام
        if is_system_generated:
            
            # تسجيل إضافي للمعاملات المولدة من النظام
            if result['is_valid']:
                from financial.models.validation_audit_log import ValidationAuditLog
                
                # تسجيل المعاملة المولدة من النظام بشكل خاص
                ValidationAuditLog.objects.create(
                    user=user,
                    entity_type=entity_type or 'unknown',
                    entity_id=getattr(entity, 'id', 0) or getattr(entity, 'pk', 0),
                    entity_name=str(entity),
                    validation_type='system_generated',
                    failure_reason='N/A',
                    error_message='معاملة مولدة من النظام - تم التحقق بنجاح',
                    module=module,
                    transaction_type=transaction_type or 'system',
                    transaction_date=transaction_date,
                    transaction_amount=transaction_amount,
                    is_bypass_attempt=False,
                    bypass_reason='system_generated_transaction'
                )
        
        return result
    
    @staticmethod
    def connect_to_model(model_class, field_mapping):
        """
        ربط signal بنموذج معين
        
        يربط signal pre_save بنموذج معين للتحقق التلقائي من المعاملات المالية.
        
        Args:
            model_class: كلاس النموذج (مثل: JournalEntry, Sale)
            field_mapping: قاموس يحدد حقول النموذج المقابلة
                {
                    'entity_field': 'customer',  # حقل الكيان
                    'date_field': 'date',         # حقل التاريخ
                    'amount_field': 'amount',     # حقل المبلغ (اختياري)
                    'entity_type': 'customer',    # نوع الكيان
                    'module': 'client',           # الوحدة
                    'transaction_type': 'payment' # نوع المعاملة
                }

        Example:
            >>> from sale.models import Sale
            >>> FinancialTransactionSignalHandler.connect_to_model(
            ...     Sale,
            ...     {
            ...         'entity_field': 'customer',
            ...         'date_field': 'date',
            ...         'amount_field': 'total',
            ...         'entity_type': 'customer',
            ...         'module': 'client',
            ...         'transaction_type': 'sale'
            ...     }
            ... )
        """
        
        @governed_signal_handler(
            signal_name=f"validate_before_save_{model_class.__name__}",
            critical=True,
            description=f"التحقق من المعاملة المالية قبل الحفظ - {model_class.__name__}"
        )
        @receiver(pre_save, sender=model_class)
        def validate_before_save(sender, instance, **kwargs):
            """معالج pre_save للتحقق من المعاملة قبل الحفظ"""
            # استخراج البيانات من النموذج
            entity = getattr(instance, field_mapping['entity_field'], None)
            transaction_date = getattr(instance, field_mapping['date_field'], None)
            transaction_amount = getattr(
                instance,
                field_mapping.get('amount_field', 'amount'),
                None
            )
            
            # التحقق من وجود البيانات المطلوبة
            if entity is None or transaction_date is None:
                logger.warning(
                    f"تخطي التحقق - بيانات غير كاملة: "
                    f"entity={entity}, date={transaction_date}"
                )
                return
            
            # تحديد ما إذا كانت المعاملة مولدة من النظام
            is_system_generated = getattr(
                instance,
                'is_system_generated',
                False
            )
            
            # إطلاق signal للتحقق
            try:
                pre_financial_transaction.send(
                    sender=sender,
                    entity=entity,
                    transaction_date=transaction_date,
                    entity_type=field_mapping.get('entity_type'),
                    transaction_type=field_mapping.get('transaction_type'),
                    transaction_amount=transaction_amount,
                    user=getattr(instance, 'created_by', None),
                    module=field_mapping.get('module', 'financial'),
                    is_system_generated=is_system_generated
                )
            except Exception as e:
                logger.error(
                    f"فشل التحقق من المعاملة المالية: {str(e)}"
                )
                raise
        


# ربط معالج التحقق بـ signal
pre_financial_transaction.connect(
    FinancialTransactionSignalHandler.validate_transaction_signal
)


# دوال مساعدة للاستخدام السهل
def trigger_validation(
    entity,
    transaction_date,
    entity_type=None,
    transaction_type=None,
    transaction_amount=None,
    user=None,
    module='financial',
    is_system_generated=False
):
    """
    إطلاق التحقق من معاملة مالية يدوياً
    
    دالة مساعدة لإطلاق signal التحقق من معاملة مالية بدون الحاجة
    لاستخدام send() مباشرة.
    
    Args:
        entity: الكيان المالي
        transaction_date: تاريخ المعاملة
        entity_type: نوع الكيان (اختياري)
        transaction_type: نوع المعاملة (اختياري)
        transaction_amount: مبلغ المعاملة (اختياري)
        user: المستخدم (اختياري)
        module: الوحدة (افتراضي 'financial')
        is_system_generated: هل المعاملة مولدة من النظام (افتراضي False)
        
    Returns:
        list: نتائج المعالجات
        
    Raises:
        FinancialValidationError: إذا فشل التحقق
        
    Example:
        >>> from datetime import date
        >>> customer = Customer.objects.get(id=1)
        >>> trigger_validation(
        ...     entity=customer,
        ...     transaction_date=date.today(),
        ...     entity_type='customer',
        ...     transaction_type='payment',
        ...     transaction_amount=1000,
        ...     module='client'
        ... )
    """
    return pre_financial_transaction.send(
        sender=None,
        entity=entity,
        transaction_date=transaction_date,
        entity_type=entity_type,
        transaction_type=transaction_type,
        transaction_amount=transaction_amount,
        user=user,
        module=module,
        is_system_generated=is_system_generated
    )


def connect_model_validation(model_class, field_mapping):
    """
    ربط التحقق التلقائي بنموذج
    
    دالة مساعدة لربط التحقق التلقائي بنموذج معين.
    
    Args:
        model_class: كلاس النموذج
        field_mapping: قاموس تعيين الحقول

    Example:
        >>> from sale.models import Sale
        >>> connect_model_validation(
        ...     Sale,
        ...     {
        ...         'entity_field': 'customer',
        ...         'date_field': 'date',
        ...         'amount_field': 'total',
        ...         'entity_type': 'customer',
        ...         'module': 'client',
        ...         'transaction_type': 'sale'
        ...     }
        ... )
    """
    FinancialTransactionSignalHandler.connect_to_model(
        model_class,
        field_mapping
    )
