from decimal import Decimal
from django.utils.translation import gettext_lazy as _
from abc import ABC, abstractmethod

from ...models import CalculationType


class BaseCalculator(ABC):
    """
    الفئة الأساسية لجميع حاسبات التكلفة
    """
    
    def __init__(self, order):
        """
        تهيئة الحاسبة
        
        Args:
            order: طلب التسعير
        """
        self.order = order
        self.errors = []
        self.warnings = []
        self.calculation_details = {}
    
    def calculate(self, calculation_type, parameters=None):
        """
        تنفيذ الحساب حسب النوع
        
        Args:
            calculation_type: نوع الحساب
            parameters: معاملات إضافية
            
        Returns:
            dict: نتائج الحساب
        """
        if parameters is None:
            parameters = {}
        
        try:
            # تنظيف البيانات
            self._validate_parameters(parameters)
            
            # تنفيذ الحساب حسب النوع
            if calculation_type == CalculationType.MATERIAL:
                return self._calculate_material_cost(parameters)
            elif calculation_type == CalculationType.PRINTING:
                return self._calculate_printing_cost(parameters)
            elif calculation_type == CalculationType.FINISHING:
                return self._calculate_finishing_cost(parameters)
            elif calculation_type == CalculationType.DESIGN:
                return self._calculate_design_cost(parameters)
            elif calculation_type == CalculationType.TOTAL:
                return self._calculate_total_cost(parameters)
            else:
                raise ValueError(_('نوع حساب غير مدعوم: {}').format(calculation_type))
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'base_cost': Decimal('0.00'),
                'additional_costs': Decimal('0.00'),
                'total_cost': Decimal('0.00'),
                'details': {'error': str(e)}
            }
    
    def _validate_parameters(self, parameters):
        """
        التحقق من صحة المعاملات
        
        Args:
            parameters: المعاملات المرسلة
        """
        # التحقق الأساسي من الطلب
        if not self.order:
            raise ValueError(_('طلب التسعير مطلوب'))
        
        if not self.order.quantity or self.order.quantity <= 0:
            raise ValueError(_('كمية الطلب يجب أن تكون أكبر من صفر'))
    
    def _calculate_material_cost(self, parameters):
        """
        حساب تكلفة المواد
        
        Args:
            parameters: معاملات الحساب
            
        Returns:
            dict: نتائج حساب تكلفة المواد
        """
        try:
            # جمع تكاليف جميع المواد
            materials = self.order.materials.filter(is_active=True)
            
            if not materials.exists():
                return {
                    'success': True,
                    'base_cost': Decimal('0.00'),
                    'additional_costs': Decimal('0.00'),
                    'total_cost': Decimal('0.00'),
                    'details': {
                        'message': _('لا توجد مواد محددة للطلب'),
                        'materials_count': 0
                    }
                }
            
            total_cost = Decimal('0.00')
            materials_breakdown = []
            
            for material in materials:
                # إعادة حساب تكلفة المادة
                material.calculate_total_cost()
                material.save()
                
                total_cost += material.total_cost
                
                materials_breakdown.append({
                    'id': material.id,
                    'name': material.material_name,
                    'type': material.material_type,
                    'quantity': float(material.quantity),
                    'unit': material.unit,
                    'unit_cost': float(material.unit_cost),
                    'waste_percentage': float(material.waste_percentage),
                    'total_cost': float(material.total_cost)
                })
            
            return {
                'success': True,
                'base_cost': total_cost,
                'additional_costs': Decimal('0.00'),
                'total_cost': total_cost,
                'details': {
                    'materials_count': materials.count(),
                    'materials_breakdown': materials_breakdown,
                    'calculation_method': 'sum_of_materials'
                }
            }
            
        except Exception as e:
            raise ValueError(_('خطأ في حساب تكلفة المواد: {}').format(str(e)))
    
    def _calculate_printing_cost(self, parameters):
        """
        حساب تكلفة الطباعة
        
        Args:
            parameters: معاملات الحساب
            
        Returns:
            dict: نتائج حساب تكلفة الطباعة
        """
        try:
            # الحصول على مواصفات الطباعة
            try:
                printing_spec = self.order.printing_spec
            except:
                # إنشاء مواصفات افتراضية
                printing_spec = None
            
            # معاملات افتراضية
            default_params = {
                'colors_front': parameters.get('colors_front', 1),
                'colors_back': parameters.get('colors_back', 0),
                'spot_colors_count': parameters.get('spot_colors_count', 0),
                'plates_cost_per_color': Decimal(str(parameters.get('plates_cost_per_color', '50.00'))),
                'printing_cost_per_thousand': Decimal(str(parameters.get('printing_cost_per_thousand', '100.00')))
            }
            
            # استخدام مواصفات الطباعة إذا كانت متوفرة
            if printing_spec:
                colors_front = printing_spec.colors_front
                colors_back = printing_spec.colors_back
                spot_colors = printing_spec.spot_colors_count
                plates_cost_per_color = default_params['plates_cost_per_color']
            else:
                colors_front = default_params['colors_front']
                colors_back = default_params['colors_back']
                spot_colors = default_params['spot_colors_count']
                plates_cost_per_color = default_params['plates_cost_per_color']
            
            # حساب تكلفة الزنكات
            total_colors = colors_front + colors_back + spot_colors
            plates_cost = total_colors * plates_cost_per_color
            
            # حساب تكلفة الطباعة
            quantity = self.order.quantity
            thousands = Decimal(quantity) / 1000
            printing_cost_per_thousand = default_params['printing_cost_per_thousand']
            printing_cost = thousands * printing_cost_per_thousand
            
            total_cost = plates_cost + printing_cost
            
            return {
                'success': True,
                'base_cost': printing_cost,
                'additional_costs': plates_cost,
                'total_cost': total_cost,
                'details': {
                    'colors_front': colors_front,
                    'colors_back': colors_back,
                    'spot_colors': spot_colors,
                    'total_colors': total_colors,
                    'plates_cost': float(plates_cost),
                    'printing_cost': float(printing_cost),
                    'quantity': quantity,
                    'thousands': float(thousands),
                    'cost_per_thousand': float(printing_cost_per_thousand),
                    'calculation_method': 'plates_plus_printing'
                }
            }
            
        except Exception as e:
            raise ValueError(_('خطأ في حساب تكلفة الطباعة: {}').format(str(e)))
    
    def _calculate_finishing_cost(self, parameters):
        """
        حساب تكلفة خدمات الطباعة
        
        Args:
            parameters: معاملات الحساب
            
        Returns:
            dict: نتائج حساب تكلفة خدمات الطباعة
        """
        try:
            # جمع تكاليف جميع خدمات الطباعة والتقفيل
            finishing_services = self.order.services.filter(
                service_category__in=['finishing', 'packaging'],  # خدمات الطباعة + خدمات التقفيل
                is_active=True
            )
            
            if not finishing_services.exists():
                return {
                    'success': True,
                    'base_cost': Decimal('0.00'),
                    'additional_costs': Decimal('0.00'),
                    'total_cost': Decimal('0.00'),
                    'details': {
                        'message': _('لا توجد خدمات تشطيبات محددة للطلب'),
                        'services_count': 0
                    }
                }
            
            total_cost = Decimal('0.00')
            services_breakdown = []
            
            for service in finishing_services:
                # إعادة حساب تكلفة الخدمة
                service.calculate_total_cost()
                service.save()
                
                total_cost += service.total_cost
                
                services_breakdown.append({
                    'id': service.id,
                    'name': service.service_name,
                    'category': service.service_category,
                    'quantity': float(service.quantity),
                    'unit': service.unit,
                    'unit_price': float(service.unit_price),
                    'setup_cost': float(service.setup_cost),
                    'total_cost': float(service.total_cost),
                    'is_optional': service.is_optional
                })
            
            return {
                'success': True,
                'base_cost': total_cost,
                'additional_costs': Decimal('0.00'),
                'total_cost': total_cost,
                'details': {
                    'services_count': finishing_services.count(),
                    'services_breakdown': services_breakdown,
                    'calculation_method': 'sum_of_finishing_services'
                }
            }
            
        except Exception as e:
            raise ValueError(_('خطأ في حساب تكلفة خدمات الطباعة: {}').format(str(e)))
    
    def _calculate_design_cost(self, parameters):
        """
        حساب تكلفة التصميم
        
        Args:
            parameters: معاملات الحساب
            
        Returns:
            dict: نتائج حساب تكلفة التصميم
        """
        try:
            # معاملات التصميم
            design_hours = Decimal(str(parameters.get('design_hours', '0')))
            hourly_rate = Decimal(str(parameters.get('hourly_rate', '50.00')))
            complexity_factor = Decimal(str(parameters.get('complexity_factor', '1.0')))
            
            if design_hours <= 0:
                return {
                    'success': True,
                    'base_cost': Decimal('0.00'),
                    'additional_costs': Decimal('0.00'),
                    'total_cost': Decimal('0.00'),
                    'details': {
                        'message': _('لا توجد ساعات تصميم محددة'),
                        'design_hours': 0
                    }
                }
            
            # حساب التكلفة
            base_cost = design_hours * hourly_rate
            complexity_cost = base_cost * (complexity_factor - 1)
            total_cost = base_cost + complexity_cost
            
            return {
                'success': True,
                'base_cost': base_cost,
                'additional_costs': complexity_cost,
                'total_cost': total_cost,
                'details': {
                    'design_hours': float(design_hours),
                    'hourly_rate': float(hourly_rate),
                    'complexity_factor': float(complexity_factor),
                    'base_cost': float(base_cost),
                    'complexity_cost': float(complexity_cost),
                    'calculation_method': 'hours_times_rate_with_complexity'
                }
            }
            
        except Exception as e:
            raise ValueError(_('خطأ في حساب تكلفة التصميم: {}').format(str(e)))
    
    def _calculate_total_cost(self, parameters):
        """
        حساب التكلفة الإجمالية
        
        Args:
            parameters: معاملات الحساب
            
        Returns:
            dict: نتائج حساب التكلفة الإجمالية
        """
        try:
            # حساب جميع أنواع التكاليف
            material_result = self._calculate_material_cost(parameters)
            printing_result = self._calculate_printing_cost(parameters)
            finishing_result = self._calculate_finishing_cost(parameters)
            design_result = self._calculate_design_cost(parameters)
            
            # جمع التكاليف
            material_cost = material_result['total_cost']
            printing_cost = printing_result['total_cost']
            finishing_cost = finishing_result['total_cost']
            design_cost = design_result['total_cost']
            
            subtotal = material_cost + printing_cost + finishing_cost + design_cost
            
            # إضافات وخصومات
            discount_percentage = Decimal(str(parameters.get('discount_percentage', '0')))
            tax_percentage = Decimal(str(parameters.get('tax_percentage', '0')))
            rush_fee = Decimal(str(parameters.get('rush_fee', '0')))
            
            discount_amount = subtotal * (discount_percentage / 100)
            after_discount = subtotal - discount_amount
            tax_amount = after_discount * (tax_percentage / 100)
            
            total_cost = after_discount + tax_amount + rush_fee
            
            return {
                'success': True,
                'base_cost': subtotal,
                'additional_costs': tax_amount + rush_fee - discount_amount,
                'total_cost': total_cost,
                'details': {
                    'material_cost': float(material_cost),
                    'printing_cost': float(printing_cost),
                    'finishing_cost': float(finishing_cost),
                    'design_cost': float(design_cost),
                    'subtotal': float(subtotal),
                    'discount_percentage': float(discount_percentage),
                    'discount_amount': float(discount_amount),
                    'tax_percentage': float(tax_percentage),
                    'tax_amount': float(tax_amount),
                    'rush_fee': float(rush_fee),
                    'total_cost': float(total_cost),
                    'calculation_method': 'comprehensive_total',
                    'breakdown_results': {
                        'material': material_result,
                        'printing': printing_result,
                        'finishing': finishing_result,
                        'design': design_result
                    }
                }
            }
            
        except Exception as e:
            raise ValueError(_('خطأ في حساب التكلفة الإجمالية: {}').format(str(e)))
    
    def get_calculation_summary(self):
        """
        الحصول على ملخص الحساب
        
        Returns:
            dict: ملخص الحساب
        """
        return {
            'order_id': self.order.id,
            'order_number': self.order.order_number,
            'errors': self.errors,
            'warnings': self.warnings,
            'calculation_details': self.calculation_details
        }


__all__ = ['BaseCalculator']
