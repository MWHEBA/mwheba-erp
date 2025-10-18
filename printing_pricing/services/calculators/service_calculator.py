"""
حاسبة تكاليف الخدمات
"""
from decimal import Decimal
from typing import Dict, List, Optional, Any
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

from .base_calculator import BaseCalculator
from ...models import OrderService


class ServiceCalculator(BaseCalculator):
    """حاسبة تكاليف الخدمات"""
    
    def calculate_service_cost(self, service_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        حساب تكلفة خدمة واحدة
        
        Args:
            service_data: بيانات الخدمة
            
        Returns:
            Dict: نتائج الحساب
        """
        try:
            # استخراج البيانات
            quantity = self._get_decimal(service_data, 'quantity')
            unit_cost = self._get_decimal(service_data, 'unit_cost')
            setup_cost = self._get_decimal(service_data, 'setup_cost', Decimal('0.00'))
            service_type = service_data.get('service_type', 'general')
            
            # التحقق من صحة البيانات
            self._validate_service_data(quantity, unit_cost)
            
            # الحسابات
            base_cost = quantity * unit_cost
            total_cost = base_cost + setup_cost
            
            return {
                'success': True,
                'base_cost': base_cost,
                'setup_cost': setup_cost,
                'total_cost': total_cost,
                'cost_per_unit': unit_cost,
                'quantity': quantity,
                'service_type': service_type
            }
            
        except ValidationError as e:
            return {
                'success': False,
                'error': str(e),
                'details': _('خطأ في التحقق من بيانات الخدمة')
            }
        except Exception as e:
            return {
                'success': False,
                'error': _('خطأ غير متوقع في حساب تكلفة الخدمة: {}').format(str(e)),
                'details': str(e)
            }
    
    def calculate_finishing_service_cost(self, service_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        حساب تكلفة خدمات التشطيب
        
        Args:
            service_data: بيانات خدمة التشطيب
            
        Returns:
            Dict: نتائج الحساب
        """
        try:
            # استخراج البيانات
            quantity = self._get_decimal(service_data, 'quantity')
            unit_cost = self._get_decimal(service_data, 'unit_cost')
            finishing_type = service_data.get('finishing_type', 'general')
            complexity_factor = self._get_decimal(service_data, 'complexity_factor', Decimal('1.0'))
            
            # التحقق من صحة البيانات
            self._validate_service_data(quantity, unit_cost)
            
            # الحسابات مع عامل التعقيد
            base_cost = quantity * unit_cost
            adjusted_cost = base_cost * complexity_factor
            
            return {
                'success': True,
                'base_cost': base_cost,
                'adjusted_cost': adjusted_cost,
                'total_cost': adjusted_cost,
                'complexity_factor': complexity_factor,
                'finishing_type': finishing_type,
                'cost_per_unit': unit_cost,
                'quantity': quantity
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': _('خطأ في حساب تكلفة خدمة التشطيب: {}').format(str(e)),
                'details': str(e)
            }
    
    def calculate_binding_service_cost(self, service_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        حساب تكلفة خدمات التجليد
        
        Args:
            service_data: بيانات خدمة التجليد
            
        Returns:
            Dict: نتائج الحساب
        """
        try:
            # استخراج البيانات
            quantity = self._get_decimal(service_data, 'quantity')
            binding_type = service_data.get('binding_type', 'saddle_stitch')
            pages_count = self._get_decimal(service_data, 'pages_count', Decimal('1'))
            
            # تحديد التكلفة حسب نوع التجليد
            unit_cost = self._get_binding_rate(binding_type, pages_count)
            
            # الحسابات
            total_cost = quantity * unit_cost
            
            return {
                'success': True,
                'total_cost': total_cost,
                'cost_per_unit': unit_cost,
                'quantity': quantity,
                'binding_type': binding_type,
                'pages_count': pages_count
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': _('خطأ في حساب تكلفة خدمة التجليد: {}').format(str(e)),
                'details': str(e)
            }
    
    def calculate_cutting_service_cost(self, service_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        حساب تكلفة خدمات التقطيع
        
        Args:
            service_data: بيانات خدمة التقطيع
            
        Returns:
            Dict: نتائج الحساب
        """
        try:
            # استخراج البيانات
            quantity = self._get_decimal(service_data, 'quantity')
            cutting_type = service_data.get('cutting_type', 'straight')
            cuts_count = self._get_decimal(service_data, 'cuts_count', Decimal('1'))
            
            # تحديد التكلفة حسب نوع التقطيع
            base_rate = self._get_cutting_rate(cutting_type)
            unit_cost = base_rate * cuts_count
            
            # الحسابات
            total_cost = quantity * unit_cost
            
            return {
                'success': True,
                'total_cost': total_cost,
                'cost_per_unit': unit_cost,
                'quantity': quantity,
                'cutting_type': cutting_type,
                'cuts_count': cuts_count
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': _('خطأ في حساب تكلفة خدمة التقطيع: {}').format(str(e)),
                'details': str(e)
            }
    
    def calculate_order_services_cost(self, order) -> Dict[str, Any]:
        """
        حساب تكلفة جميع خدمات الطلب
        
        Args:
            order: طلب التسعير
            
        Returns:
            Dict: نتائج الحساب
        """
        try:
            services = OrderService.objects.filter(order=order, is_active=True)
            
            if not services.exists():
                return {
                    'success': True,
                    'total_cost': Decimal('0.00'),
                    'services_count': 0,
                    'message': _('لا توجد خدمات مضافة للطلب')
                }
            
            total_cost = Decimal('0.00')
            services_results = []
            
            for service in services:
                service_data = {
                    'quantity': service.quantity,
                    'unit_cost': service.unit_cost,
                    'setup_cost': getattr(service, 'setup_cost', Decimal('0.00')),
                    'service_type': service.service_type
                }
                
                result = self.calculate_service_cost(service_data)
                if result['success']:
                    total_cost += result['total_cost']
                    services_results.append(result)
                else:
                    return result
            
            return {
                'success': True,
                'total_cost': total_cost,
                'services': services_results,
                'services_count': len(services_results)
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': _('خطأ في حساب تكلفة خدمات الطلب: {}').format(str(e)),
                'details': str(e)
            }
    
    def _validate_service_data(self, quantity: Decimal, unit_cost: Decimal):
        """التحقق من صحة بيانات الخدمة"""
        if quantity <= 0:
            raise ValidationError(_('الكمية يجب أن تكون أكبر من صفر'))
        
        if unit_cost < 0:
            raise ValidationError(_('تكلفة الوحدة لا يمكن أن تكون سالبة'))
    
    def _get_binding_rate(self, binding_type: str, pages_count: Decimal) -> Decimal:
        """الحصول على تعريفة التجليد"""
        # تعريفات أساسية - يمكن تطويرها لاحقاً من قاعدة البيانات
        rates = {
            'saddle_stitch': Decimal('0.50'),  # دباسة
            'perfect_binding': Decimal('2.00'),  # تجليد مثالي
            'spiral_binding': Decimal('1.50'),  # تجليد حلزوني
            'wire_binding': Decimal('1.00'),  # تجليد سلكي
            'hardcover': Decimal('5.00')  # غلاف صلب
        }
        
        base_rate = rates.get(binding_type, rates['saddle_stitch'])
        
        # تعديل السعر حسب عدد الصفحات
        if pages_count > 50:
            base_rate *= Decimal('1.5')
        elif pages_count > 20:
            base_rate *= Decimal('1.2')
        
        return base_rate
    
    def _get_cutting_rate(self, cutting_type: str) -> Decimal:
        """الحصول على تعريفة التقطيع"""
        # تعريفات أساسية - يمكن تطويرها لاحقاً من قاعدة البيانات
        rates = {
            'straight': Decimal('0.10'),  # تقطيع مستقيم
            'curved': Decimal('0.25'),  # تقطيع منحني
            'die_cutting': Decimal('0.50'),  # قص بالاستنسل
            'perforation': Decimal('0.15'),  # ثقب
            'scoring': Decimal('0.20')  # خدش للطي
        }
        
        return rates.get(cutting_type, rates['straight'])
    
    def get_service_suggestions(self, service_type: str) -> List[Dict[str, Any]]:
        """
        الحصول على اقتراحات الخدمات حسب النوع
        
        Args:
            service_type: نوع الخدمة
            
        Returns:
            List: قائمة الاقتراحات
        """
        try:
            suggestions = {
                'finishing': [
                    {'name': _('تقفيل'), 'unit_cost': Decimal('0.10')},
                    {'name': _('ورنيش'), 'unit_cost': Decimal('0.15')},
                    {'name': _('طلاء UV'), 'unit_cost': Decimal('0.25')},
                ],
                'binding': [
                    {'name': _('تجليد دباسة'), 'unit_cost': Decimal('0.50')},
                    {'name': _('تجليد حلزوني'), 'unit_cost': Decimal('1.50')},
                    {'name': _('تجليد مثالي'), 'unit_cost': Decimal('2.00')},
                ],
                'cutting': [
                    {'name': _('تقطيع مستقيم'), 'unit_cost': Decimal('0.10')},
                    {'name': _('تقطيع منحني'), 'unit_cost': Decimal('0.25')},
                    {'name': _('قص بالاستنسل'), 'unit_cost': Decimal('0.50')},
                ]
            }
            
            return suggestions.get(service_type, [])
            
        except Exception as e:
            return []
