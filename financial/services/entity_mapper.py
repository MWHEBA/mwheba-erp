"""
خدمة ربط الكيانات بالحسابات المحاسبية
Entity Account Mapper Service

هذه الخدمة مسؤولة عن:
1. تحديد الحساب المحاسبي المرتبط بكل نوع كيان
2. الاستنتاج التلقائي لنوع الكيان من النموذج
3. دعم جميع أنواع الكيانات في النظام
"""

import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class EntityAccountMapper:
    """
    خدمة لتحديد الحساب المحاسبي المرتبط بكل نوع كيان
    """
    
    # خريطة أنواع الكيانات إلى حقول الحسابات المحاسبية
    # يحدد هذا القاموس اسم الحقل الذي يحتوي على الحساب المحاسبي لكل نوع كيان
    ENTITY_ACCOUNT_FIELDS = {
        # العملاء
        'customer': 'financial_account',  # Customer.financial_account

        # الموردين
        'supplier': 'financial_account',  # Supplier.financial_account

        # الموظفين - لا يحتاجون حساب محاسبي منفصل
        'employee': None,
    }

    MODEL_TO_ENTITY_TYPE = {
        'Customer': 'customer',
        'Supplier': 'supplier',
        'Employee': 'employee',
    }
    
    @classmethod
    def get_account(cls, entity, entity_type: Optional[str] = None, account_field: Optional[str] = None):
        """
        الحصول على الحساب المحاسبي للكيان
        
        Args:
            entity: الكيان المالي (مثل Customer, Supplier, Employee, إلخ)
            entity_type: نوع الكيان (اختياري، يُستنتج تلقائياً إذا لم يُحدد)
            account_field: حقل الحساب المحدد (اختياري، للحصول على حساب بديل)
            
        Returns:
            ChartOfAccounts or None: الحساب المحاسبي المرتبط بالكيان أو None
            
        Examples:
            >>> supplier = Supplier.objects.get(id=1)
            >>> account = EntityAccountMapper.get_account(supplier, 'supplier')
            >>> # يعيد supplier.financial_account
            
            >>> fee_type = FeeType.objects.get(id=1)
            >>> revenue_account = EntityAccountMapper.get_account(fee_type)
            >>> # يعيد fee_type.get_revenue_account() (من التصنيف المالي)
        """
        if entity is None:
            logger.warning("تم تمرير كيان None إلى get_account")
            return None
        
        # استنتاج نوع الكيان إذا لم يُحدد
        if entity_type is None:
            entity_type = cls.detect_entity_type(entity)
            if entity_type is None:
                logger.warning(f"فشل في استنتاج نوع الكيان لـ {type(entity).__name__}")
                return None
        
        # الحصول على اسم حقل الحساب المحاسبي
        if account_field:
            # استخدام الحقل المحدد مباشرة
            account_field_path = account_field
        else:
            # استخدام الحقل الافتراضي من القاموس
            account_field_path = cls.ENTITY_ACCOUNT_FIELDS.get(entity_type)
        
        # معالجة خاصة لـ FeeType - استخدام get_revenue_account()
        if entity_type == 'fee_type' and not account_field:
            if hasattr(entity, 'get_revenue_account'):
                return entity.get_revenue_account()
            logger.debug("FeeType لا يحتوي على get_revenue_account()")
            return None
        
        if account_field_path is None:
            logger.debug(f"لا يوجد حساب محاسبي محدد لنوع الكيان: {entity_type}")
            return None

        # التعامل مع المسارات المتداخلة
        try:
            account = entity
            for field_name in account_field_path.split('.'):
                if account is None:
                    logger.debug(f"الحقل {field_name} يساوي None في المسار {account_field_path}")
                    return None
                
                # ✅ Try to get from database first (for ForeignKey fields)
                # Then fall back to getattr for dynamic attributes
                if hasattr(account, field_name):
                    account = getattr(account, field_name, None)
                else:
                    # Field doesn't exist in model
                    logger.debug(f"الحقل {field_name} غير موجود في {type(account).__name__}")
                    return None
            
            return account
            
        except AttributeError as e:
            logger.warning(
                f"فشل في الوصول إلى الحساب المحاسبي للكيان {entity_type}: {str(e)}"
            )
            return None
        except Exception as e:
            logger.error(
                f"خطأ غير متوقع عند الحصول على الحساب المحاسبي للكيان {entity_type}: {str(e)}"
            )
            return None
    
    @classmethod
    def detect_entity_type(cls, entity) -> Optional[str]:
        """
        استنتاج نوع الكيان من النموذج
        
        Args:
            entity: الكيان المالي
            
        Returns:
            str or None: نوع الكيان أو None إذا فشل الاستنتاج
            
        Examples:
            >>> supplier = Supplier.objects.get(id=1)
            >>> entity_type = EntityAccountMapper.detect_entity_type(supplier)
            >>> print(entity_type)  # 'supplier'
        """
        if entity is None:
            return None
        
        # الحصول على اسم النموذج
        model_name = type(entity).__name__
        
        # البحث في الخريطة
        entity_type = cls.MODEL_TO_ENTITY_TYPE.get(model_name)
        
        if entity_type is None:
            logger.debug(f"نوع الكيان غير معروف للنموذج: {model_name}")
        
        return entity_type
    
    @classmethod
    def get_entity_info(cls, entity, entity_type: Optional[str] = None) -> dict:
        """
        الحصول على معلومات شاملة عن الكيان والحساب المحاسبي المرتبط به
        
        Args:
            entity: الكيان المالي
            entity_type: نوع الكيان (اختياري)
            
        Returns:
            dict: معلومات الكيان والحساب المحاسبي
            
        Example:
            >>> supplier = Supplier.objects.get(id=1)
            >>> info = EntityAccountMapper.get_entity_info(supplier)
            >>> print(info)
            {
                'entity': <Supplier object>,
                'entity_type': 'supplier',
                'entity_name': 'شركة المورد',
                'model_name': 'Supplier',
                'account': <ChartOfAccounts object>,
                'account_field_path': 'financial_account',
                'has_account': True
            }
        """
        # استنتاج نوع الكيان إذا لم يُحدد
        if entity_type is None:
            entity_type = cls.detect_entity_type(entity)
        
        # الحصول على الحساب المحاسبي
        account = cls.get_account(entity, entity_type)
        
        # الحصول على اسم الكيان
        entity_name = str(entity) if entity else 'غير محدد'
        
        # الحصول على اسم النموذج
        model_name = type(entity).__name__ if entity else 'Unknown'
        
        # الحصول على مسار حقل الحساب
        account_field_path = cls.ENTITY_ACCOUNT_FIELDS.get(entity_type) if entity_type else None
        
        return {
            'entity': entity,
            'entity_type': entity_type,
            'entity_name': entity_name,
            'model_name': model_name,
            'account': account,
            'account_field_path': account_field_path,
            'has_account': account is not None
        }
    
    @classmethod
    def validate_entity_account(cls, entity, entity_type: Optional[str] = None) -> Tuple[bool, str]:
        """
        التحقق من وجود حساب محاسبي صحيح للكيان
        
        Args:
            entity: الكيان المالي
            entity_type: نوع الكيان (اختياري)
            
        Returns:
            tuple: (is_valid: bool, message: str)
            
        Example:
            >>> supplier = Supplier.objects.get(id=1)
            >>> is_valid, message = EntityAccountMapper.validate_entity_account(supplier)
            >>> if not is_valid:
            ...     print(message)
        """
        if entity is None:
            return False, "الكيان غير موجود"
        
        # استنتاج نوع الكيان
        if entity_type is None:
            entity_type = cls.detect_entity_type(entity)
            if entity_type is None:
                return False, f"نوع الكيان غير معروف: {type(entity).__name__}"
        
        # التحقق من وجود تعريف للحساب المحاسبي لهذا النوع
        account_field_path = cls.ENTITY_ACCOUNT_FIELDS.get(entity_type)
        if account_field_path is None:
            # بعض الكيانات لا تحتاج حساب محاسبي مباشر
            return True, f"نوع الكيان {entity_type} لا يتطلب حساب محاسبي مباشر"
        
        # الحصول على الحساب المحاسبي
        account = cls.get_account(entity, entity_type)
        
        if account is None:
            entity_name = str(entity)
            return False, f"لا يوجد حساب محاسبي مرتبط بـ {entity_name}"
        
        return True, "الحساب المحاسبي موجود وصحيح"
    
    @classmethod
    def get_supported_entity_types(cls) -> list:
        """
        الحصول على قائمة بجميع أنواع الكيانات المدعومة
        
        Returns:
            list: قائمة بأنواع الكيانات المدعومة
        """
        return list(cls.ENTITY_ACCOUNT_FIELDS.keys())
    
    @classmethod
    def is_entity_type_supported(cls, entity_type: str) -> bool:
        """
        التحقق من دعم نوع كيان معين
        
        Args:
            entity_type: نوع الكيان
            
        Returns:
            bool: True إذا كان نوع الكيان مدعوم
        """
        return entity_type in cls.ENTITY_ACCOUNT_FIELDS
    
    @classmethod
    def get_entity_by_type(cls, entity_type: str, entity_id: int):
        """
        الحصول على الكيان حسب النوع والمعرف
        
        Args:
            entity_type: نوع الكيان
            entity_id: معرف الكيان
            
        Returns:
            الكيان أو None
        """
        try:
            if entity_type == 'customer':
                from client.models import Customer
                return Customer.objects.get(id=entity_id)

            elif entity_type == 'supplier':
                from supplier.models import Supplier
                return Supplier.objects.get(id=entity_id)

            elif entity_type == 'employee':
                from hr.models import Employee
                return Employee.objects.get(id=entity_id)

            else:
                logger.warning(f"نوع كيان غير مدعوم: {entity_type}")
                return None
        
        except Exception as e:
            logger.error(f"خطأ في الحصول على الكيان {entity_type}#{entity_id}: {str(e)}")
            return None
