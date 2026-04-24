# -*- coding: utf-8 -*-
"""
استثناءات نظام المنتجات المجمعة
Bundle Products System Exceptions

يحتوي على جميع الاستثناءات المخصصة لنظام المنتجات المجمعة
Requirements: 10.1, 10.3, 10.4
"""

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class BundleSystemError(Exception):
    """استثناء أساسي لجميع أخطاء نظام المنتجات المجمعة"""
    
    def __init__(self, message, error_code=None, details=None):
        self.message = message
        self.error_code = error_code or 'BUNDLE_ERROR'
        self.details = details or {}
        super().__init__(self.message)
    
    def to_dict(self):
        """تحويل الاستثناء إلى قاموس للاستخدام في API"""
        return {
            'error': True,
            'error_code': self.error_code,
            'message': str(self.message),
            'details': self.details
        }


class BundleValidationError(BundleSystemError):
    """أخطاء التحقق من صحة المنتجات المجمعة"""
    
    def __init__(self, message, field=None, **kwargs):
        self.field = field
        super().__init__(message, error_code='BUNDLE_VALIDATION_ERROR', **kwargs)


class BundleStockError(BundleSystemError):
    """أخطاء مخزون المنتجات المجمعة"""
    
    def __init__(self, message, bundle_product=None, component_shortages=None, **kwargs):
        self.bundle_product = bundle_product
        self.component_shortages = component_shortages or []
        details = kwargs.pop('details', {})
        if bundle_product:
            details['bundle_id'] = bundle_product.id
            details['bundle_name'] = bundle_product.name
        if component_shortages:
            details['component_shortages'] = component_shortages
        super().__init__(message, error_code='BUNDLE_STOCK_ERROR', details=details)


class BundleSalesError(BundleSystemError):
    """أخطاء مبيعات المنتجات المجمعة"""
    
    def __init__(self, message, transaction_id=None, **kwargs):
        self.transaction_id = transaction_id
        details = kwargs.pop('details', {})
        if transaction_id:
            details['transaction_id'] = transaction_id
        super().__init__(message, error_code='BUNDLE_SALES_ERROR', details=details)


class BundleRefundError(BundleSystemError):
    """أخطاء مرتجعات المنتجات المجمعة"""
    
    def __init__(self, message, refund_id=None, **kwargs):
        self.refund_id = refund_id
        details = kwargs.pop('details', {})
        if refund_id:
            details['refund_id'] = refund_id
        super().__init__(message, error_code='BUNDLE_REFUND_ERROR', details=details)


class BundleCircularDependencyError(BundleValidationError):
    """خطأ الاعتماد الدائري في المنتجات المجمعة"""
    
    def __init__(self, message, dependency_chain=None, **kwargs):
        self.dependency_chain = dependency_chain or []
        details = kwargs.pop('details', {})
        if dependency_chain:
            details['dependency_chain'] = dependency_chain
        super().__init__(message, error_code='BUNDLE_CIRCULAR_DEPENDENCY', details=details)


class BundleComponentError(BundleSystemError):
    """أخطاء مكونات المنتجات المجمعة"""
    
    def __init__(self, message, component_product=None, **kwargs):
        self.component_product = component_product
        details = kwargs.pop('details', {})
        if component_product:
            details['component_id'] = component_product.id
            details['component_name'] = component_product.name
        super().__init__(message, error_code='BUNDLE_COMPONENT_ERROR', details=details)


class BundleFinancialError(BundleSystemError):
    """أخطاء المعاملات المالية للمنتجات المجمعة"""
    
    def __init__(self, message, financial_transaction_id=None, **kwargs):
        self.financial_transaction_id = financial_transaction_id
        details = kwargs.pop('details', {})
        if financial_transaction_id:
            details['financial_transaction_id'] = financial_transaction_id
        super().__init__(message, error_code='BUNDLE_FINANCIAL_ERROR', details=details)


class BundleIntegrityError(BundleSystemError):
    """أخطاء تكامل بيانات المنتجات المجمعة"""
    
    def __init__(self, message, integrity_issues=None, **kwargs):
        self.integrity_issues = integrity_issues or []
        details = kwargs.pop('details', {})
        if integrity_issues:
            details['integrity_issues'] = integrity_issues
        super().__init__(message, error_code='BUNDLE_INTEGRITY_ERROR', details=details)


# رسائل الأخطاء المعيارية
BUNDLE_ERROR_MESSAGES = {
    'INSUFFICIENT_STOCK': _('المخزون غير كافي للمنتج المجمع'),
    'COMPONENT_NOT_AVAILABLE': _('أحد مكونات المنتج المجمع غير متاح'),
    'INVALID_QUANTITY': _('الكمية المطلوبة غير صحيحة'),
    'CIRCULAR_DEPENDENCY': _('يوجد اعتماد دائري في تكوين المنتج المجمع'),
    'TRANSACTION_FAILED': _('فشل في معالجة المعاملة'),
    'REFUND_NOT_ALLOWED': _('لا يمكن إجراء مرتجع لهذا المنتج المجمع'),
    'COMPONENT_DEACTIVATED': _('أحد مكونات المنتج المجمع غير مفعل'),
    'BUNDLE_NOT_FOUND': _('المنتج المجمع غير موجود'),
    'INVALID_BUNDLE_CONFIGURATION': _('تكوين المنتج المجمع غير صحيح'),
    'FINANCIAL_TRANSACTION_ERROR': _('خطأ في المعاملة المالية'),
}


def get_error_message(error_code, **kwargs):
    """الحصول على رسالة خطأ معيارية"""
    message = BUNDLE_ERROR_MESSAGES.get(error_code, _('خطأ غير معروف في نظام المنتجات المجمعة'))
    try:
        return message.format(**kwargs)
    except (KeyError, ValueError):
        return str(message)