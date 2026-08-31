"""
حاسبة تكاليف المواد
"""
from decimal import Decimal
from typing import Dict, List, Optional, Any
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

from .base_calculator import BaseCalculator
from ...models import OrderMaterial


class MaterialCalculator(BaseCalculator):
    """حاسبة تكاليف المواد"""
    
    def calculate_material_cost(self, material_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        حساب تكلفة مادة واحدة
        
        Args:
            material_data: بيانات المادة
            
        Returns:
            Dict: نتائج الحساب
        """
        try:
            # استخراج البيانات
            quantity = self._get_decimal(material_data, 'quantity')
            unit_cost = self._get_decimal(material_data, 'unit_cost')
            waste_percentage = self._get_decimal(material_data, 'waste_percentage', Decimal('5.00'))
            
            # التحقق من صحة البيانات
            self._validate_material_data(quantity, unit_cost, waste_percentage)
            
            # الحسابات
            base_cost = quantity * unit_cost
            waste_amount = base_cost * (waste_percentage / 100)
            total_cost = base_cost + waste_amount
            
            return {
                'success': True,
                'base_cost': base_cost,
                'waste_amount': waste_amount,
                'total_cost': total_cost,
                'waste_percentage': waste_percentage,
                'cost_per_unit': unit_cost,
                'quantity': quantity
            }
            
        except ValidationError as e:
            return {
                'success': False,
                'error': str(e),
                'details': _('خطأ في التحقق من بيانات المادة')
            }
        except Exception as e:
            return {
                'success': False,
                'error': _('خطأ غير متوقع في حساب تكلفة المادة: {}').format(str(e)),
                'details': str(e)
            }
    
    def calculate_multiple_materials_cost(self, materials_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        حساب تكلفة مواد متعددة
        
        Args:
            materials_data: قائمة بيانات المواد
            
        Returns:
            Dict: نتائج الحساب الإجمالية
        """
        try:
            results = []
            total_base_cost = Decimal('0.00')
            total_waste_amount = Decimal('0.00')
            total_cost = Decimal('0.00')
            
            for i, material_data in enumerate(materials_data):
                result = self.calculate_material_cost(material_data)
                
                if not result['success']:
                    return {
                        'success': False,
                        'error': _('خطأ في المادة رقم {}: {}').format(i + 1, result['error']),
                        'material_index': i
                    }
                
                results.append(result)
                total_base_cost += result['base_cost']
                total_waste_amount += result['waste_amount']
                total_cost += result['total_cost']
            
            return {
                'success': True,
                'materials': results,
                'summary': {
                    'total_base_cost': total_base_cost,
                    'total_waste_amount': total_waste_amount,
                    'total_cost': total_cost,
                    'materials_count': len(results)
                }
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': _('خطأ في حساب تكلفة المواد المتعددة: {}').format(str(e)),
                'details': str(e)
            }
    
    def calculate_order_materials_cost(self, order) -> Dict[str, Any]:
        """
        حساب تكلفة جميع مواد الطلب
        
        Args:
            order: طلب التسعير
            
        Returns:
            Dict: نتائج الحساب
        """
        try:
            materials = OrderMaterial.objects.filter(order=order, is_active=True)
            
            if not materials.exists():
                return {
                    'success': True,
                    'total_cost': Decimal('0.00'),
                    'materials_count': 0,
                    'message': _('لا توجد مواد مضافة للطلب')
                }
            
            materials_data = []
            for material in materials:
                materials_data.append({
                    'quantity': material.quantity,
                    'unit_cost': material.unit_cost,
                    'waste_percentage': material.waste_percentage,
                    'material_type': material.material_type,
                    'material_name': material.material_name
                })
            
            return self.calculate_multiple_materials_cost(materials_data)
            
        except Exception as e:
            return {
                'success': False,
                'error': _('خطأ في حساب تكلفة مواد الطلب: {}').format(str(e)),
                'details': str(e)
            }
    
    def calculate_cumulative_paper_waste(
        self,
        net_sheets: int,
        printing_waste_pct: Decimal = Decimal('5.00'),
        lamination_waste_pct: Decimal = Decimal('0.00'),
        diecut_waste_pct: Decimal = Decimal('0.00'),
        binding_waste_pct: Decimal = Decimal('0.00'),
        is_client_paper: bool = False,
        sheet_cost: Decimal = Decimal('0.00')
    ) -> Dict[str, Any]:
        """
        حساب الهالك التراكمي المتسلسل لمراحل الورش المختلفة
        
        Args:
            net_sheets: عدد الأفرخ الصافية المطلوبة للطباعة
            printing_waste_pct: نسبة هالك سحب الطباعة (أوفست/ديجيتال)
            lamination_waste_pct: نسبة هالك السلوفان / اللامينيشن
            diecut_waste_pct: نسبة هالك التكسير / الدايكت
            binding_waste_pct: نسبة هالك التجليد والتقفيل
            is_client_paper: هل الورق مُورد من العميل (تكلفة = 0)
            sheet_cost: تكلفة الفرخ الواحد
            
        Returns:
            Dict: تفاصيل الهالك التراكمي وإجمالي الأفرخ والتكلفة
        """
        import math
        
        # المرحلة 1: هالك الطباعة
        waste_printing = float(net_sheets) * (float(printing_waste_pct) / 100.0)
        accumulated_1 = float(net_sheets) + waste_printing
        
        # المرحلة 2: هالك السلوفان
        waste_lamination = accumulated_1 * (float(lamination_waste_pct) / 100.0) if float(lamination_waste_pct) > 0 else 0.0
        accumulated_2 = accumulated_1 + waste_lamination
        
        # المرحلة 3: هالك التكسير
        waste_diecut = accumulated_2 * (float(diecut_waste_pct) / 100.0) if float(diecut_waste_pct) > 0 else 0.0
        accumulated_3 = accumulated_2 + waste_diecut
        
        # المرحلة 4: هالك التجليد
        waste_binding = accumulated_3 * (float(binding_waste_pct) / 100.0) if float(binding_waste_pct) > 0 else 0.0
        
        total_waste_sheets = int(math.ceil(waste_printing + waste_lamination + waste_diecut + waste_binding))
        gross_sheets_needed = net_sheets + total_waste_sheets
        
        unit_cost = Decimal(str(sheet_cost))
        total_cost = Decimal('0.00') if is_client_paper else (Decimal(str(gross_sheets_needed)) * unit_cost)
        
        return {
            'success': True,
            'net_sheets': net_sheets,
            'waste_printing_sheets': int(math.ceil(waste_printing)),
            'waste_lamination_sheets': int(math.ceil(waste_lamination)),
            'waste_diecut_sheets': int(math.ceil(waste_diecut)),
            'waste_binding_sheets': int(math.ceil(waste_binding)),
            'total_waste_sheets': total_waste_sheets,
            'gross_sheets_needed': gross_sheets_needed,
            'is_client_paper': is_client_paper,
            'sheet_cost': unit_cost,
            'total_cost': total_cost,
            'details': {
                'printing_waste_pct': float(printing_waste_pct),
                'lamination_waste_pct': float(lamination_waste_pct),
                'diecut_waste_pct': float(diecut_waste_pct),
                'binding_waste_pct': float(binding_waste_pct)
            }
        }
    
    def _validate_material_data(self, quantity: Decimal, unit_cost: Decimal, waste_percentage: Decimal):
        """التحقق من صحة بيانات المادة"""
        if quantity <= 0:
            raise ValidationError(_('الكمية يجب أن تكون أكبر من صفر'))
        
        if unit_cost < 0:
            raise ValidationError(_('تكلفة الوحدة لا يمكن أن تكون سالبة'))
        
        if waste_percentage < 0 or waste_percentage > 50:
            raise ValidationError(_('نسبة الهالك يجب أن تكون بين 0 و 50%'))
    
    def get_material_suggestions(self, material_type: str) -> List[Dict[str, Any]]:
        """
        الحصول على اقتراحات المواد حسب النوع
        
        Args:
            material_type: نوع المادة
            
        Returns:
            List: قائمة الاقتراحات
        """
        try:
            # يمكن تطوير هذه الدالة لاحقاً للحصول على اقتراحات من قاعدة البيانات
            suggestions = {
                'paper': [
                    {'name': _('ورق أبيض 80 جرام'), 'unit_cost': Decimal('0.50')},
                    {'name': _('ورق أبيض 90 جرام'), 'unit_cost': Decimal('0.60')},
                    {'name': _('ورق كوشيه 115 جرام'), 'unit_cost': Decimal('1.20')},
                    {'name': _('ورق كوشيه 150 جرام'), 'unit_cost': Decimal('1.50')},
                ],
                'ink': [
                    {'name': _('حبر أسود'), 'unit_cost': Decimal('2.00')},
                    {'name': _('حبر ألوان'), 'unit_cost': Decimal('3.50')},
                    {'name': _('حبر ذهبي'), 'unit_cost': Decimal('8.00')},
                ],
                'finishing': [
                    {'name': _('تقفيل'), 'unit_cost': Decimal('0.10')},
                    {'name': _('تجليد'), 'unit_cost': Decimal('2.00')},
                    {'name': _('تقطيع'), 'unit_cost': Decimal('0.05')},
                ]
            }
            
            return suggestions.get(material_type, [])
            
        except Exception as e:
            return []
