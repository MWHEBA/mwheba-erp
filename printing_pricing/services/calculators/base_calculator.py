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

    def _get_decimal(self, data, key, default=Decimal('0.00')):
        """
        Safely gets a decimal value from a dictionary.
        """
        if not data:
            return default
        val = data.get(key)
        if val is None:
            return default
        try:
            return Decimal(str(val))
        except Exception:
            return default
    
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
        حساب تكلفة التصميم (أتعاب مقطوعة أو حسب ساعات العمل)
        
        Args:
            parameters: معاملات الحساب
            
        Returns:
            dict: نتائج حساب تكلفة التصميم
        """
        try:
            # التحقق أولاً من الأتعاب المقطوعة من الطلب أو المعاملات
            design_service_type = parameters.get('design_service_type') or getattr(self.order, 'design_service_type', 'CLIENT_READY')
            direct_fee = parameters.get('design_fee')
            
            if direct_fee is not None:
                total_cost = Decimal(str(direct_fee))
            elif hasattr(self.order, 'design_fee') and self.order.design_fee > 0:
                total_cost = Decimal(str(self.order.design_fee))
            elif design_service_type == 'CLIENT_READY':
                total_cost = Decimal('0.00')
            elif design_service_type == 'PREPRESS_EDIT':
                total_cost = Decimal('150.00')
            elif design_service_type == 'NEW_CONCEPT':
                total_cost = Decimal('800.00')
            else:
                # دعم الحساب بالساعات كـ fallback
                design_hours = Decimal(str(parameters.get('design_hours', '0')))
                hourly_rate = Decimal(str(parameters.get('hourly_rate', '50.00')))
                complexity_factor = Decimal(str(parameters.get('complexity_factor', '1.0')))
                base_cost = design_hours * hourly_rate
                complexity_cost = base_cost * (complexity_factor - 1)
                total_cost = base_cost + complexity_cost

            return {
                'success': True,
                'base_cost': total_cost,
                'additional_costs': Decimal('0.00'),
                'total_cost': total_cost,
                'details': {
                    'design_service_type': design_service_type,
                    'design_fee': float(total_cost),
                    'calculation_method': 'agency_flat_creative_fee'
                }
            }
            
        except Exception as e:
            raise ValueError(_('خطأ في حساب تكلفة التصميم: {}').format(str(e)))
    
    def _calculate_total_cost(self, parameters):
        """
        حساب التكلفة الإجمالية وتطبيق هامش الوكالة وعمولة المبيعات
        
        Args:
            parameters: معاملات الحساب
            
        Returns:
            dict: نتائج حساب التكلفة الإجمالية
        """
        try:
            # حساب جميع أنواع التكاليف الأساسية
            material_result = self._calculate_material_cost(parameters)
            printing_result = self._calculate_printing_cost(parameters)
            finishing_result = self._calculate_finishing_cost(parameters)
            design_result = self._calculate_design_cost(parameters)
            
            material_cost = material_result['total_cost']
            printing_cost = printing_result['total_cost']
            finishing_cost = finishing_result['total_cost']
            design_cost = design_result['total_cost']
            
            # تكاليف التركيبات واللوجستيات
            installation_cost = Decimal(str(parameters.get('installation_cost', '0.00')))
            logistics_cost = Decimal(str(parameters.get('logistics_cost', '0.00')))
            
            # إجمالي التكاليف المباشرة
            direct_costs = material_cost + printing_cost + finishing_cost + design_cost + installation_cost + logistics_cost
            
            # إضافات وخصومات
            discount_percentage = Decimal(str(parameters.get('discount_percentage', '0')))
            if discount_percentage < 0 or discount_percentage > 100:
                raise ValueError(_('نسبة الخصم يجب أن تكون بين 0 و 100%'))

            tax_percentage = Decimal(str(parameters.get('tax_percentage', '0')))
            if tax_percentage < 0 or tax_percentage > 100:
                raise ValueError(_('نسبة الضريبة يجب أن تكون بين 0 و 100%'))

            rush_fee = Decimal(str(parameters.get('rush_fee', getattr(self.order, 'rush_fee', '0.00') or '0.00')))
            if rush_fee < 0:
                raise ValueError(_('رسوم الاستعجال لا يمكن أن تكون سالبة'))
            
            # هامش الربح
            profit_margin = Decimal(str(parameters.get('profit_margin', getattr(self.order, 'profit_margin', '20.00') or '20.00')))
            if profit_margin >= 100:
                raise ValueError(_('هامش الربح يجب أن يكون أقل من 100%'))
                
            # حساب سعر البيع بمعادلة الهامش الحقيقي
            if profit_margin > 0:
                base_sale_price = direct_costs / (Decimal('1.00') - (profit_margin / Decimal('100.00')))
            else:
                base_sale_price = direct_costs

            discount_amount = base_sale_price * (discount_percentage / Decimal('100.00'))
            after_discount = base_sale_price - discount_amount
            tax_amount = after_discount * (tax_percentage / Decimal('100.00'))
            final_price = after_discount + tax_amount + rush_fee
            
            # عمولة المبيعات على صافي الربح مع صمام الأمان
            gross_profit = max(Decimal('0.00'), final_price - direct_costs)
            sales_commission_rate = Decimal(str(parameters.get('sales_commission_rate', getattr(self.order, 'sales_commission_rate', '0.00') or '0.00')))
            sales_commission_amount = gross_profit * (sales_commission_rate / Decimal('100.00')) if sales_commission_rate > 0 else Decimal('0.00')
            
            return {
                'success': True,
                'base_cost': direct_costs,
                'additional_costs': tax_amount + rush_fee - discount_amount,
                'total_cost': direct_costs,
                'final_price': final_price,
                'sales_commission_amount': sales_commission_amount,
                'details': {
                    'material_cost': float(material_cost),
                    'printing_cost': float(printing_cost),
                    'finishing_cost': float(finishing_cost),
                    'design_cost': float(design_cost),
                    'installation_cost': float(installation_cost),
                    'logistics_cost': float(logistics_cost),
                    'direct_costs': float(direct_costs),
                    'profit_margin': float(profit_margin),
                    'base_sale_price': float(base_sale_price),
                    'discount_percentage': float(discount_percentage),
                    'discount_amount': float(discount_amount),
                    'tax_percentage': float(tax_percentage),
                    'tax_amount': float(tax_amount),
                    'rush_fee': float(rush_fee),
                    'final_price': float(final_price),
                    'sales_commission_rate': float(sales_commission_rate),
                    'sales_commission_amount': float(sales_commission_amount),
                    'calculation_method': 'agency_true_margin_markup',
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
