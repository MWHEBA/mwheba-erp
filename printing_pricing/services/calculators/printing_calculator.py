"""
حاسبة تكاليف الطباعة
"""
from decimal import Decimal
from typing import Dict, List, Optional, Any
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

from .base_calculator import BaseCalculator
from ...models import OrderService


class PrintingCalculator(BaseCalculator):
    """حاسبة تكاليف الطباعة"""
    
    def calculate_printing_cost(self, printing_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        حساب تكلفة الطباعة
        
        Args:
            printing_data: بيانات الطباعة
            
        Returns:
            Dict: نتائج الحساب
        """
        try:
            # استخراج البيانات
            quantity = self._get_decimal(printing_data, 'quantity')
            colors_count = self._get_decimal(printing_data, 'colors_count', Decimal('1'))
            setup_cost = self._get_decimal(printing_data, 'setup_cost', Decimal('0.00'))
            unit_cost = self._get_decimal(printing_data, 'unit_cost')
            
            # التحقق من صحة البيانات
            self._validate_printing_data(quantity, colors_count, unit_cost)
            
            # الحسابات
            base_printing_cost = quantity * unit_cost
            colors_multiplier = colors_count if colors_count > 1 else Decimal('1')
            printing_cost = base_printing_cost * colors_multiplier
            total_cost = printing_cost + setup_cost
            
            return {
                'success': True,
                'base_printing_cost': base_printing_cost,
                'printing_cost': printing_cost,
                'setup_cost': setup_cost,
                'total_cost': total_cost,
                'colors_count': colors_count,
                'cost_per_unit': unit_cost,
                'quantity': quantity
            }
            
        except ValidationError as e:
            return {
                'success': False,
                'error': str(e),
                'details': _('خطأ في التحقق من بيانات الطباعة')
            }
        except Exception as e:
            return {
                'success': False,
                'error': _('خطأ غير متوقع في حساب تكلفة الطباعة: {}').format(str(e)),
                'details': str(e)
            }
    
    def calculate_digital_printing_cost(self, printing_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        حساب تكلفة الطباعة الرقمية
        
        Args:
            printing_data: بيانات الطباعة الرقمية
            
        Returns:
            Dict: نتائج الحساب
        """
        try:
            # استخراج البيانات
            quantity = self._get_decimal(printing_data, 'quantity')
            page_size = printing_data.get('page_size', 'A4')
            is_color = printing_data.get('is_color', False)
            paper_type = printing_data.get('paper_type', 'normal')
            
            # تحديد التكلفة حسب النوع
            base_cost_per_page = self._get_digital_printing_rate(page_size, is_color, paper_type)
            
            # الحسابات
            total_cost = quantity * base_cost_per_page
            
            return {
                'success': True,
                'total_cost': total_cost,
                'cost_per_page': base_cost_per_page,
                'quantity': quantity,
                'page_size': page_size,
                'is_color': is_color,
                'paper_type': paper_type
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': _('خطأ في حساب تكلفة الطباعة الرقمية: {}').format(str(e)),
                'details': str(e)
            }
    
    def calculate_offset_printing_cost(self, printing_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        حساب تكلفة الطباعة الأوفست
        
        Args:
            printing_data: بيانات الطباعة الأوفست
            
        Returns:
            Dict: نتائج الحساب
        """
        try:
            # استخراج البيانات
            quantity = self._get_decimal(printing_data, 'quantity')
            colors_count = self._get_decimal(printing_data, 'colors_count', Decimal('1'))
            plate_cost = self._get_decimal(printing_data, 'plate_cost', Decimal('50.00'))
            setup_cost = self._get_decimal(printing_data, 'setup_cost', Decimal('100.00'))
            unit_cost = self._get_decimal(printing_data, 'unit_cost')
            
            # الحسابات
            plates_cost = plate_cost * colors_count
            printing_cost = quantity * unit_cost
            total_cost = printing_cost + plates_cost + setup_cost
            
            return {
                'success': True,
                'printing_cost': printing_cost,
                'plates_cost': plates_cost,
                'setup_cost': setup_cost,
                'total_cost': total_cost,
                'colors_count': colors_count,
                'cost_per_unit': unit_cost,
                'quantity': quantity
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': _('خطأ في حساب تكلفة الطباعة الأوفست: {}').format(str(e)),
                'details': str(e)
            }
    
    def calculate_order_printing_cost(self, order) -> Dict[str, Any]:
        """
        حساب تكلفة طباعة الطلب
        
        Args:
            order: طلب التسعير
            
        Returns:
            Dict: نتائج الحساب
        """
        try:
            printing_services = OrderService.objects.filter(
                order=order, 
                service_type='printing',
                is_active=True
            )
            
            if not printing_services.exists():
                return {
                    'success': True,
                    'total_cost': Decimal('0.00'),
                    'services_count': 0,
                    'message': _('لا توجد خدمات طباعة مضافة للطلب')
                }
            
            total_cost = Decimal('0.00')
            services_results = []
            
            for service in printing_services:
                service_data = {
                    'quantity': service.quantity,
                    'unit_cost': service.unit_cost,
                    'colors_count': getattr(service, 'colors_count', 1),
                    'setup_cost': getattr(service, 'setup_cost', Decimal('0.00'))
                }
                
                result = self.calculate_printing_cost(service_data)
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
                'error': _('خطأ في حساب تكلفة طباعة الطلب: {}').format(str(e)),
                'details': str(e)
            }
    
    def _validate_printing_data(self, quantity: Decimal, colors_count: Decimal, unit_cost: Decimal):
        """التحقق من صحة بيانات الطباعة"""
        if quantity <= 0:
            raise ValidationError(_('الكمية يجب أن تكون أكبر من صفر'))
        
        if colors_count < 1 or colors_count > 10:
            raise ValidationError(_('عدد الألوان يجب أن يكون بين 1 و 10'))
        
        if unit_cost < 0:
            raise ValidationError(_('تكلفة الوحدة لا يمكن أن تكون سالبة'))
    
    def _get_digital_printing_rate(self, page_size: str, is_color: bool, paper_type: str) -> Decimal:
        """الحصول على تعريفة الطباعة الرقمية"""
        # تعريفات أساسية - يمكن تطويرها لاحقاً من قاعدة البيانات
        rates = {
            'A4': {
                'normal': {'bw': Decimal('0.25'), 'color': Decimal('1.00')},
                'photo': {'bw': Decimal('0.50'), 'color': Decimal('2.00')}
            },
            'A3': {
                'normal': {'bw': Decimal('0.50'), 'color': Decimal('2.00')},
                'photo': {'bw': Decimal('1.00'), 'color': Decimal('4.00')}
            }
        }
        
        size_rates = rates.get(page_size, rates['A4'])
        paper_rates = size_rates.get(paper_type, size_rates['normal'])
        
        return paper_rates['color'] if is_color else paper_rates['bw']
