"""
خدمة تعديل الدفعات - نظام مبسط وفعال
إدارة تعديل وإلغاء ترحيل الدفعات مع الحفاظ على تكامل النظام المالي
"""
from django.db import transaction
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class PaymentEditError(Exception):
    """استثناء خاص بأخطاء تعديل الدفعات"""
    pass


class PaymentEditService:
    """
    خدمة تعديل الدفعات المبسطة
    
    الميزات:
    - تعديل الدفعات المسودة مباشرة
    - إلغاء ترحيل الدفعات المرحّلة وتعديلها
    - نظام صلاحيات بسيط (مستويين)
    - تسجيل التغييرات الأساسي
    """
    
    @classmethod
    def can_edit_payment(cls, user: User, payment) -> bool:
        """فحص صلاحية تعديل الدفعة"""
        
        # المدير العام يمكنه تعديل أي شيء
        if user.is_superuser:
            return True
        
        # صلاحية تعديل الدفعات المرحّلة
        if user.has_perm('financial.can_edit_posted_payments'):
            return True
        
        # المستخدم العادي يمكنه تعديل المسودات فقط
        if payment.status == 'draft':
            return True
        
        return False
    
    @classmethod
    def can_unpost_payment(cls, user: User, payment) -> bool:
        """فحص صلاحية إلغاء ترحيل الدفعة"""
        
        # المدير العام يمكنه إلغاء أي ترحيل
        if user.is_superuser:
            return True
        
        # صلاحية إلغاء الترحيل
        if user.has_perm('financial.can_unpost_payments'):
            return True
        
        return False
    
    @classmethod
    def edit_payment(
        cls,
        payment,
        payment_type: str,  # 'sale' or 'purchase'
        new_data: Dict[str, Any],
        user: User
    ) -> Dict[str, Any]:
        """
        تعديل الدفعة مع معالجة الترحيل
        
        Args:
            payment: كائن الدفعة
            payment_type: نوع الدفعة ('sale' أو 'purchase')
            new_data: البيانات الجديدة
            user: المستخدم المنفذ
            
        Returns:
            Dict يحتوي على نتيجة العملية
        """
        
        try:
            # فحص الصلاحيات
            if not cls.can_edit_payment(user, payment):
                raise PermissionDenied("ليس لديك صلاحية تعديل هذه الدفعة")
            
            # إذا كانت الدفعة مرحّلة، تحقق من صلاحية إلغاء الترحيل
            if payment.is_posted and not cls.can_unpost_payment(user, payment):
                raise PermissionDenied("ليس لديك صلاحية إلغاء ترحيل الدفعات")
            
            # تسجيل البيانات القديمة للمقارنة
            old_data = cls._get_payment_data(payment)
            
            # تنفيذ التعديل
            with transaction.atomic():
                result = payment.update_payment_data(new_data, user)
                
                if result['success']:
                    # تسجيل التغيير
                    cls._log_payment_change(
                        payment=payment,
                        payment_type=payment_type,
                        action='edited',
                        user=user,
                        old_data=old_data,
                        new_data=cls._get_payment_data(payment)
                    )
                    
                    logger.info(f"تم تعديل الدفعة {payment.id} بواسطة {user.username}")
                
                return result
                
        except Exception as e:
            error_message = str(e)
            logger.error(f"خطأ في تعديل الدفعة {payment.id}: {error_message}")
            
            return {
                'success': False,
                'message': f'فشل في تعديل الدفعة: {error_message}',
                'error': error_message
            }
    
    @classmethod
    def unpost_payment(
        cls,
        payment,
        payment_type: str,
        user: User,
        reason: str = ""
    ) -> Dict[str, Any]:
        """
        إلغاء ترحيل الدفعة فقط
        
        Args:
            payment: كائن الدفعة
            payment_type: نوع الدفعة
            user: المستخدم المنفذ
            reason: سبب الإلغاء
            
        Returns:
            Dict يحتوي على نتيجة العملية
        """
        
        try:
            # فحص الصلاحيات
            if not cls.can_unpost_payment(user, payment):
                raise PermissionDenied("ليس لديك صلاحية إلغاء ترحيل الدفعات")
            
            if not payment.is_posted:
                return {'success': False, 'message': 'الدفعة غير مرحّلة أصلاً'}
            
            # تنفيذ إلغاء الترحيل
            with transaction.atomic():
                result = payment.unpost(user)
                
                if result['success']:
                    # تسجيل العملية
                    cls._log_payment_change(
                        payment=payment,
                        payment_type=payment_type,
                        action='unposted',
                        user=user,
                        reason=reason
                    )
                    
                    logger.info(f"تم إلغاء ترحيل الدفعة {payment.id} بواسطة {user.username}")
                
                return result
                
        except Exception as e:
            error_message = str(e)
            logger.error(f"خطأ في إلغاء ترحيل الدفعة {payment.id}: {error_message}")
            
            return {
                'success': False,
                'message': f'فشل في إلغاء الترحيل: {error_message}',
                'error': error_message
            }
    
    @classmethod
    def get_edit_permissions(cls, user: User, payment) -> Dict[str, bool]:
        """الحصول على صلاحيات التعديل للمستخدم"""
        
        return {
            'can_edit': cls.can_edit_payment(user, payment),
            'can_unpost': cls.can_unpost_payment(user, payment),
            'can_delete': payment.can_delete and cls.can_edit_payment(user, payment),
            'is_draft': payment.is_draft,
            'is_posted': payment.is_posted,
            'can_unpost_payment': payment.can_unpost
        }
    
    @classmethod
    def _get_payment_data(cls, payment) -> Dict[str, Any]:
        """استخراج بيانات الدفعة للمقارنة"""
        
        return {
            'amount': float(payment.amount),
            'payment_date': payment.payment_date.isoformat() if payment.payment_date else None,
            'payment_method': payment.payment_method,
            'financial_account_id': payment.financial_account.id if payment.financial_account else None,
            'financial_account_name': payment.financial_account.name if payment.financial_account else None,
            'reference_number': payment.reference_number,
            'notes': payment.notes,
            'status': payment.status,
            'financial_status': payment.financial_status
        }
    
    @classmethod
    def _log_payment_change(
        cls,
        payment,
        payment_type: str,
        action: str,
        user: User,
        old_data: Dict = None,
        new_data: Dict = None,
        reason: str = ""
    ):
        """تسجيل تغيير الدفعة - نظام بسيط"""
        
        # يمكن توسيع هذا لاحقاً بنموذج قاعدة بيانات منفصل
        log_entry = {
            'payment_id': payment.id,
            'payment_type': payment_type,
            'action': action,
            'user': user.username,
            'timestamp': timezone.now().isoformat(),
            'reason': reason
        }
        
        if old_data and new_data:
            # تسجيل الفروقات فقط
            changes = {}
            for key, new_value in new_data.items():
                old_value = old_data.get(key)
                if old_value != new_value:
                    changes[key] = {
                        'old': old_value,
                        'new': new_value
                    }
            log_entry['changes'] = changes
        
        # تسجيل في الـ logger للآن
        logger.info(f"Payment Change Log: {log_entry}")
        
        # TODO: يمكن حفظ في جدول منفصل لاحقاً إذا لزم الأمر
    
    @classmethod
    def validate_payment_data(cls, payment_data: Dict[str, Any]) -> Dict[str, Any]:
        """التحقق من صحة بيانات الدفعة"""
        
        errors = {}
        
        # التحقق من المبلغ
        if 'amount' in payment_data:
            try:
                amount = float(payment_data['amount'])
                if amount <= 0:
                    errors['amount'] = 'يجب أن يكون المبلغ أكبر من صفر'
            except (ValueError, TypeError):
                errors['amount'] = 'مبلغ غير صحيح'
        
        # التحقق من تاريخ الدفع
        if 'payment_date' in payment_data:
            if not payment_data['payment_date']:
                errors['payment_date'] = 'يجب تحديد تاريخ الدفع'
        
        # التحقق من طريقة الدفع
        if 'payment_method' in payment_data:
            valid_methods = ['cash', 'bank_transfer', 'check']
            if payment_data['payment_method'] not in valid_methods:
                errors['payment_method'] = 'طريقة دفع غير صحيحة'
        
        # التحقق من الحساب المالي
        if 'financial_account' in payment_data:
            if not payment_data['financial_account']:
                errors['financial_account'] = 'يجب تحديد الحساب المالي'
        
        return {
            'is_valid': len(errors) == 0,
            'errors': errors
        }


# إنشاء instance عام للخدمة
payment_edit_service = PaymentEditService()
