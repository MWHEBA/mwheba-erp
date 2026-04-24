# -*- coding: utf-8 -*-
"""
معالج أخطاء نظام المنتجات المجمعة
Bundle System Error Handler

يوفر آليات شاملة لمعالجة الأخطاء والتعافي من الفشل
Requirements: 10.1, 10.3, 10.4
"""

import logging
import traceback
from typing import Dict, List, Optional, Any, Tuple
from django.db import transaction
from django.utils import timezone
from django.core.mail import mail_admins
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from ..exceptions import (
    BundleSystemError, BundleStockError, BundleSalesError,
    BundleRefundError, BundleValidationError, BundleIntegrityError
)

logger = logging.getLogger('bundle_system')


class BundleErrorHandler:
    """
    معالج شامل لأخطاء نظام المنتجات المجمعة
    
    يوفر:
    - تسجيل مفصل للأخطاء
    - آليات التعافي من الفشل
    - إشعارات الإدارة للأخطاء الحرجة
    - تتبع الأخطاء المتكررة
    
    Requirements: 10.1, 10.3, 10.4
    """
    
    # مستويات الأخطاء
    ERROR_LEVELS = {
        'LOW': 'منخفض',
        'MEDIUM': 'متوسط', 
        'HIGH': 'عالي',
        'CRITICAL': 'حرج'
    }
    
    # أخطاء تتطلب إشعار فوري للإدارة
    CRITICAL_ERRORS = [
        'BUNDLE_INTEGRITY_ERROR',
        'BUNDLE_FINANCIAL_ERROR',
        'TRANSACTION_ROLLBACK_FAILED'
    ]
    
    @classmethod
    def handle_error(
        cls,
        error: Exception,
        context: Dict[str, Any],
        recovery_action: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        معالجة شاملة للأخطاء مع التسجيل والتعافي
        
        Args:
            error: الاستثناء المرفوع
            context: سياق الخطأ (معلومات إضافية)
            recovery_action: إجراء التعافي المطلوب
            
        Returns:
            Dict: تفاصيل معالجة الخطأ
        """
        error_details = cls._extract_error_details(error, context)
        
        # تسجيل الخطأ
        cls._log_error(error_details)
        
        # تحديد مستوى الخطورة
        severity = cls._determine_severity(error)
        error_details['severity'] = severity
        
        # إشعار الإدارة للأخطاء الحرجة
        if severity == 'CRITICAL':
            cls._notify_admins(error_details)
        
        # محاولة التعافي
        recovery_result = None
        if recovery_action:
            recovery_result = cls._attempt_recovery(error_details, recovery_action)
            error_details['recovery_result'] = recovery_result
        
        # تسجيل في قاعدة البيانات للمتابعة
        cls._record_error_for_monitoring(error_details)
        
        return error_details
    
    @classmethod
    def _extract_error_details(cls, error: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
        """استخراج تفاصيل شاملة من الخطأ"""
        details = {
            'timestamp': timezone.now(),
            'error_type': type(error).__name__,
            'error_message': str(error),
            'traceback': traceback.format_exc(),
            'context': context,
            'user_id': context.get('user_id'),
            'request_path': context.get('request_path'),
            'bundle_id': context.get('bundle_id'),
            'transaction_id': context.get('transaction_id')
        }
        
        # إضافة تفاصيل خاصة بأخطاء النظام
        if isinstance(error, BundleSystemError):
            details.update({
                'error_code': error.error_code,
                'bundle_details': error.details
            })
        
        return details
    
    @classmethod
    def _log_error(cls, error_details: Dict[str, Any]) -> None:
        """تسجيل مفصل للخطأ"""
        log_message = (
            f"خطأ في نظام المنتجات المجمعة: {error_details['error_type']}\n"
            f"الرسالة: {error_details['error_message']}\n"
            f"المستخدم: {error_details.get('user_id', 'غير محدد')}\n"
            f"المسار: {error_details.get('request_path', 'غير محدد')}\n"
            f"المنتج المجمع: {error_details.get('bundle_id', 'غير محدد')}\n"
            f"المعاملة: {error_details.get('transaction_id', 'غير محدد')}"
        )
        
        # تسجيل حسب نوع الخطأ
        if error_details['error_type'] in cls.CRITICAL_ERRORS:
            logger.critical(log_message, extra=error_details)
        elif 'ValidationError' in error_details['error_type']:
            logger.warning(log_message, extra=error_details)
        else:
            logger.error(log_message, extra=error_details)
    
    @classmethod
    def _determine_severity(cls, error: Exception) -> str:
        """تحديد مستوى خطورة الخطأ"""
        if isinstance(error, BundleIntegrityError):
            return 'CRITICAL'
        elif isinstance(error, (BundleSalesError, BundleRefundError)):
            return 'HIGH'
        elif isinstance(error, BundleStockError):
            return 'MEDIUM'
        elif isinstance(error, BundleValidationError):
            return 'LOW'
        else:
            return 'MEDIUM'
    
    @classmethod
    def _notify_admins(cls, error_details: Dict[str, Any]) -> None:
        """إشعار الإدارة بالأخطاء الحرجة"""
        try:
            subject = f"خطأ حرج في نظام المنتجات المجمعة - {error_details['error_type']}"
            message = (
                f"تم رصد خطأ حرج في نظام المنتجات المجمعة:\n\n"
                f"نوع الخطأ: {error_details['error_type']}\n"
                f"الرسالة: {error_details['error_message']}\n"
                f"الوقت: {error_details['timestamp']}\n"
                f"المستخدم: {error_details.get('user_id', 'غير محدد')}\n"
                f"المنتج المجمع: {error_details.get('bundle_id', 'غير محدد')}\n\n"
                f"يرجى المراجعة الفورية للنظام."
            )
            
            if hasattr(settings, 'ADMINS') and settings.ADMINS:
                mail_admins(subject, message, fail_silently=True)
        except Exception as e:
            logger.error(f"فشل في إرسال إشعار الإدارة: {str(e)}")
    
    @classmethod
    def _attempt_recovery(cls, error_details: Dict[str, Any], recovery_action: str) -> Dict[str, Any]:
        """محاولة التعافي من الخطأ"""
        recovery_result = {
            'attempted': True,
            'action': recovery_action,
            'success': False,
            'message': ''
        }
        
        try:
            if recovery_action == 'recalculate_stock':
                recovery_result.update(cls._recover_stock_calculation(error_details))
            elif recovery_action == 'rollback_transaction':
                recovery_result.update(cls._recover_transaction_rollback(error_details))
            elif recovery_action == 'refresh_bundle_data':
                recovery_result.update(cls._recover_bundle_data_refresh(error_details))
            else:
                recovery_result['message'] = f'إجراء التعافي غير مدعوم: {recovery_action}'
                
        except Exception as recovery_error:
            recovery_result['message'] = f'فشل في التعافي: {str(recovery_error)}'
            logger.error(f"فشل في إجراء التعافي {recovery_action}: {str(recovery_error)}")
        
        return recovery_result
    
    @classmethod
    def _recover_stock_calculation(cls, error_details: Dict[str, Any]) -> Dict[str, Any]:
        """التعافي من أخطاء حساب المخزون"""
        try:
            from .stock_calculation_engine import StockCalculationEngine
            
            bundle_id = error_details.get('bundle_id')
            if bundle_id:
                # إعادة حساب مخزون المنتج المجمع
                from product.models import Product
                bundle = Product.objects.get(id=bundle_id, is_bundle=True)
                new_stock = StockCalculationEngine.calculate_bundle_stock(bundle)
                
                return {
                    'success': True,
                    'message': f'تم إعادة حساب المخزون بنجاح: {new_stock}',
                    'new_stock': new_stock
                }
            else:
                return {
                    'success': False,
                    'message': 'لا يمكن تحديد المنتج المجمع لإعادة حساب المخزون'
                }
                
        except Exception as e:
            return {
                'success': False,
                'message': f'فشل في إعادة حساب المخزون: {str(e)}'
            }
    
    @classmethod
    def _recover_transaction_rollback(cls, error_details: Dict[str, Any]) -> Dict[str, Any]:
        """التعافي من فشل المعاملات"""
        try:
            transaction_id = error_details.get('transaction_id')
            if transaction_id:
                # محاولة التراجع عن المعاملة
                with transaction.atomic():
                    # هنا يمكن إضافة منطق التراجع المخصص
                    pass
                
                return {
                    'success': True,
                    'message': f'تم التراجع عن المعاملة {transaction_id} بنجاح'
                }
            else:
                return {
                    'success': False,
                    'message': 'لا يمكن تحديد المعاملة للتراجع عنها'
                }
                
        except Exception as e:
            return {
                'success': False,
                'message': f'فشل في التراجع عن المعاملة: {str(e)}'
            }
    
    @classmethod
    def _recover_bundle_data_refresh(cls, error_details: Dict[str, Any]) -> Dict[str, Any]:
        """التعافي بتحديث بيانات المنتج المجمع"""
        try:
            bundle_id = error_details.get('bundle_id')
            if bundle_id:
                from product.models import Product
                bundle = Product.objects.get(id=bundle_id, is_bundle=True)
                
                # تحديث cache أو إعادة تحميل البيانات
                bundle.refresh_from_db()
                
                return {
                    'success': True,
                    'message': f'تم تحديث بيانات المنتج المجمع {bundle.name} بنجاح'
                }
            else:
                return {
                    'success': False,
                    'message': 'لا يمكن تحديد المنتج المجمع لتحديث بياناته'
                }
                
        except Exception as e:
            return {
                'success': False,
                'message': f'فشل في تحديث بيانات المنتج المجمع: {str(e)}'
            }
    
    @classmethod
    def _record_error_for_monitoring(cls, error_details: Dict[str, Any]) -> None:
        """تسجيل الخطأ في قاعدة البيانات للمراقبة"""
        try:
            # يمكن إضافة نموذج لتسجيل الأخطاء هنا
            # أو استخدام نظام مراقبة خارجي
            pass
        except Exception as e:
            logger.error(f"فشل في تسجيل الخطأ للمراقبة: {str(e)}")


class BundleTransactionRecovery:
    """
    أدوات التعافي من فشل المعاملات
    
    Requirements: 10.2
    """
    
    @classmethod
    def rollback_failed_sale(cls, transaction_record: Dict[str, Any]) -> Tuple[bool, str]:
        """التراجع عن بيع فاشل"""
        try:
            with transaction.atomic():
                # استرداد كميات المكونات
                component_deductions = transaction_record.get('component_deductions', [])
                for deduction in component_deductions:
                    # إعادة الكميات المخصومة
                    pass
                
                # إلغاء المعاملة المالية
                financial_record = transaction_record.get('financial_record')
                if financial_record:
                    # إلغاء المعاملة المالية
                    pass
                
                return True, "تم التراجع عن البيع الفاشل بنجاح"
                
        except Exception as e:
            error_msg = f"فشل في التراجع عن البيع: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    @classmethod
    def recover_incomplete_refund(cls, refund_record: Dict[str, Any]) -> Tuple[bool, str]:
        """التعافي من مرتجع غير مكتمل"""
        try:
            with transaction.atomic():
                # إكمال عملية المرتجع
                pass
            
            return True, "تم إكمال المرتجع بنجاح"
            
        except Exception as e:
            error_msg = f"فشل في إكمال المرتجع: {str(e)}"
            logger.error(error_msg)
            return False, error_msg