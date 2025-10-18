"""
مدقق طلبات التسعير
"""
from decimal import Decimal
from typing import Dict, List, Optional, Any
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

from ...models import PrintingOrder, OrderMaterial, OrderService


class OrderValidator:
    """مدقق طلبات التسعير"""
    
    def validate_order_data(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        التحقق من صحة بيانات الطلب
        
        Args:
            order_data: بيانات الطلب
            
        Returns:
            Dict: نتيجة التحقق
        """
        try:
            errors = []
            
            # التحقق من البيانات الأساسية
            basic_errors = self._validate_basic_data(order_data)
            if basic_errors:
                errors.extend(basic_errors)
            
            # التحقق من المواد
            materials_errors = self._validate_materials_data(order_data.get('materials', []))
            if materials_errors:
                errors.extend(materials_errors)
            
            # التحقق من الخدمات
            services_errors = self._validate_services_data(order_data.get('services', []))
            if services_errors:
                errors.extend(services_errors)
            
            if errors:
                return {
                    'success': False,
                    'errors': errors,
                    'error_count': len(errors)
                }
            
            return {
                'success': True,
                'message': _('جميع البيانات صحيحة')
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': _('خطأ في التحقق من بيانات الطلب: {}').format(str(e))
            }
    
    def validate_order_completeness(self, order: PrintingOrder) -> Dict[str, Any]:
        """
        التحقق من اكتمال بيانات الطلب
        
        Args:
            order: طلب التسعير
            
        Returns:
            Dict: نتيجة التحقق
        """
        try:
            missing_fields = []
            warnings = []
            
            # التحقق من البيانات الأساسية
            if not order.client:
                missing_fields.append(_('العميل'))
            
            if not order.product_name:
                missing_fields.append(_('اسم المنتج'))
            
            if not order.quantity or order.quantity <= 0:
                missing_fields.append(_('الكمية'))
            
            # التحقق من وجود المواد
            materials_count = OrderMaterial.objects.filter(order=order, is_active=True).count()
            if materials_count == 0:
                warnings.append(_('لا توجد مواد مضافة للطلب'))
            
            # التحقق من وجود الخدمات
            services_count = OrderService.objects.filter(order=order, is_active=True).count()
            if services_count == 0:
                warnings.append(_('لا توجد خدمات مضافة للطلب'))
            
            # تحديد حالة الاكتمال
            is_complete = len(missing_fields) == 0
            completeness_percentage = self._calculate_completeness_percentage(order)
            
            return {
                'success': True,
                'is_complete': is_complete,
                'completeness_percentage': completeness_percentage,
                'missing_fields': missing_fields,
                'warnings': warnings,
                'materials_count': materials_count,
                'services_count': services_count
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': _('خطأ في التحقق من اكتمال الطلب: {}').format(str(e))
            }
    
    def _validate_basic_data(self, order_data: Dict[str, Any]) -> List[str]:
        """التحقق من البيانات الأساسية"""
        errors = []
        
        # التحقق من اسم المنتج
        if not order_data.get('product_name', '').strip():
            errors.append(_('اسم المنتج مطلوب'))
        
        # التحقق من الكمية
        try:
            quantity = Decimal(str(order_data.get('quantity', 0)))
            if quantity <= 0:
                errors.append(_('الكمية يجب أن تكون أكبر من صفر'))
        except (ValueError, TypeError):
            errors.append(_('الكمية يجب أن تكون رقماً صحيحاً'))
        
        # التحقق من تاريخ التسليم
        delivery_date = order_data.get('delivery_date')
        if delivery_date:
            # يمكن إضافة تحقق من صحة التاريخ هنا
            pass
        
        return errors
    
    def _validate_materials_data(self, materials_data: List[Dict[str, Any]]) -> List[str]:
        """التحقق من بيانات المواد"""
        errors = []
        
        for i, material in enumerate(materials_data, 1):
            # التحقق من نوع المادة
            if not material.get('material_type', '').strip():
                errors.append(_('نوع المادة مطلوب للمادة رقم {}').format(i))
            
            # التحقق من اسم المادة
            if not material.get('material_name', '').strip():
                errors.append(_('اسم المادة مطلوب للمادة رقم {}').format(i))
            
            # التحقق من الكمية
            try:
                quantity = Decimal(str(material.get('quantity', 0)))
                if quantity <= 0:
                    errors.append(_('كمية المادة رقم {} يجب أن تكون أكبر من صفر').format(i))
            except (ValueError, TypeError):
                errors.append(_('كمية المادة رقم {} يجب أن تكون رقماً صحيحاً').format(i))
            
            # التحقق من تكلفة الوحدة
            try:
                unit_cost = Decimal(str(material.get('unit_cost', 0)))
                if unit_cost < 0:
                    errors.append(_('تكلفة وحدة المادة رقم {} لا يمكن أن تكون سالبة').format(i))
            except (ValueError, TypeError):
                errors.append(_('تكلفة وحدة المادة رقم {} يجب أن تكون رقماً صحيحاً').format(i))
        
        return errors
    
    def _validate_services_data(self, services_data: List[Dict[str, Any]]) -> List[str]:
        """التحقق من بيانات الخدمات"""
        errors = []
        
        for i, service in enumerate(services_data, 1):
            # التحقق من نوع الخدمة
            if not service.get('service_type', '').strip():
                errors.append(_('نوع الخدمة مطلوب للخدمة رقم {}').format(i))
            
            # التحقق من اسم الخدمة
            if not service.get('service_name', '').strip():
                errors.append(_('اسم الخدمة مطلوب للخدمة رقم {}').format(i))
            
            # التحقق من الكمية
            try:
                quantity = Decimal(str(service.get('quantity', 0)))
                if quantity <= 0:
                    errors.append(_('كمية الخدمة رقم {} يجب أن تكون أكبر من صفر').format(i))
            except (ValueError, TypeError):
                errors.append(_('كمية الخدمة رقم {} يجب أن تكون رقماً صحيحاً').format(i))
            
            # التحقق من تكلفة الوحدة
            try:
                unit_cost = Decimal(str(service.get('unit_cost', 0)))
                if unit_cost < 0:
                    errors.append(_('تكلفة وحدة الخدمة رقم {} لا يمكن أن تكون سالبة').format(i))
            except (ValueError, TypeError):
                errors.append(_('تكلفة وحدة الخدمة رقم {} يجب أن تكون رقماً صحيحاً').format(i))
        
        return errors
    
    def _calculate_completeness_percentage(self, order: PrintingOrder) -> int:
        """حساب نسبة اكتمال الطلب"""
        total_fields = 10  # إجمالي الحقول المطلوبة
        completed_fields = 0
        
        # البيانات الأساسية
        if order.client:
            completed_fields += 1
        if order.product_name:
            completed_fields += 1
        if order.quantity and order.quantity > 0:
            completed_fields += 1
        if order.delivery_date:
            completed_fields += 1
        if order.notes:
            completed_fields += 1
        
        # المواد والخدمات
        materials_count = OrderMaterial.objects.filter(order=order, is_active=True).count()
        if materials_count > 0:
            completed_fields += 2
        
        services_count = OrderService.objects.filter(order=order, is_active=True).count()
        if services_count > 0:
            completed_fields += 2
        
        # حالة الطلب
        if order.status != 'draft':
            completed_fields += 1
        
        return int((completed_fields / total_fields) * 100)
    
    def validate_order_for_approval(self, order: PrintingOrder) -> Dict[str, Any]:
        """
        التحقق من إمكانية اعتماد الطلب
        
        Args:
            order: طلب التسعير
            
        Returns:
            Dict: نتيجة التحقق
        """
        try:
            errors = []
            
            # التحقق من اكتمال البيانات
            completeness_result = self.validate_order_completeness(order)
            if not completeness_result['success']:
                return completeness_result
            
            if not completeness_result['is_complete']:
                errors.extend(completeness_result['missing_fields'])
            
            # التحقق من وجود تكلفة إجمالية
            if not order.total_cost or order.total_cost <= 0:
                errors.append(_('يجب حساب التكلفة الإجمالية قبل الاعتماد'))
            
            # التحقق من حالة الطلب
            if order.status == 'approved':
                errors.append(_('الطلب معتمد بالفعل'))
            elif order.status == 'cancelled':
                errors.append(_('لا يمكن اعتماد طلب ملغي'))
            
            if errors:
                return {
                    'success': False,
                    'can_approve': False,
                    'errors': errors
                }
            
            return {
                'success': True,
                'can_approve': True,
                'message': _('الطلب جاهز للاعتماد')
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': _('خطأ في التحقق من إمكانية اعتماد الطلب: {}').format(str(e))
            }
