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
        is_customer_paper: bool = False,
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
            is_customer_paper: هل الورق مُورد من العميل (تكلفة = 0)
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
        total_cost = Decimal('0.00') if is_customer_paper else (Decimal(str(gross_sheets_needed)) * unit_cost)
        
        return {
            'success': True,
            'net_sheets': net_sheets,
            'waste_printing_sheets': int(math.ceil(waste_printing)),
            'waste_lamination_sheets': int(math.ceil(waste_lamination)),
            'waste_diecut_sheets': int(math.ceil(waste_diecut)),
            'waste_binding_sheets': int(math.ceil(waste_binding)),
            'total_waste_sheets': total_waste_sheets,
            'gross_sheets_needed': gross_sheets_needed,
            'is_customer_paper': is_customer_paper,
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

    def calculate_sheets_with_knife_clearance(
        self,
        sheet_width_cm: Decimal,
        sheet_height_cm: Decimal,
        item_width_cm: Decimal,
        item_height_cm: Decimal,
        is_die_cut: bool = False,
        knife_clearance_mm: int = 5,
        grain_direction_lock: bool = False
    ) -> Dict[str, Any]:
        """
        حساب عدد القطع من الفرخ مع إضافة خلوص سكاكين التكسير ومراعاة اتجاه ألياف الورق
        """
        try:
            sw = self._to_decimal(sheet_width_cm)
            sh = self._to_decimal(sheet_height_cm)
            iw = self._to_decimal(item_width_cm)
            ih = self._to_decimal(item_height_cm)

            if sw <= 0 or sh <= 0 or iw <= 0 or ih <= 0:
                return {
                    'success': False,
                    'error': _('أبعاد الفرخ والمنتج يجب أن تكون أكبر من الصفر'),
                    'field': 'dimensions',
                    'code': 'INVALID_DIMENSIONS'
                }

            # إضافة خلوص سكاكين التكسير (Clearance) إذا كان المنتج يتطلب اسطمبة
            clearance_cm = (Decimal(str(knife_clearance_mm)) / Decimal('10.0')) if is_die_cut else Decimal('0.00')
            effective_iw = iw + clearance_cm
            effective_ih = ih + clearance_cm

            # الاتجاه العادي
            fit_w1 = int(sw // effective_iw)
            fit_h1 = int(sh // effective_ih)
            items_orientation_1 = fit_w1 * fit_h1

            # الاتجاه المعكوس (Rotated)
            fit_w2 = int(sw // effective_ih)
            fit_h2 = int(sh // effective_iw)
            items_orientation_2 = fit_w2 * fit_h2

            if grain_direction_lock:
                # عند قفل اتجاه الألياف يتم الالتزام بالاتجاه الموازي
                items_per_sheet = items_orientation_1
                orientation_used = 'normal'
            else:
                if items_orientation_1 >= items_orientation_2:
                    items_per_sheet = items_orientation_1
                    orientation_used = 'normal'
                else:
                    items_per_sheet = items_orientation_2
                    orientation_used = 'rotated'

            sheet_area = sw * sh
            utilized_area = Decimal(str(items_per_sheet)) * (iw * ih)
            waste_pct = ((sheet_area - utilized_area) / sheet_area * Decimal('100.00')).quantize(Decimal('0.01')) if sheet_area > 0 else Decimal('0.00')

            return {
                'success': True,
                'items_per_sheet': items_per_sheet,
                'orientation_used': orientation_used,
                'is_die_cut': is_die_cut,
                'knife_clearance_mm': knife_clearance_mm,
                'effective_item_width': effective_iw,
                'effective_item_height': effective_ih,
                'waste_percentage': waste_pct,
                'grain_direction_locked': grain_direction_lock
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'details': _('خطأ في حساب تقطيع الورق مع سكاكين التكسير')
            }

    def auto_optimize_sheet_size(
        self,
        item_width_cm: Decimal,
        item_height_cm: Decimal,
        is_die_cut: bool = False,
        knife_clearance_mm: int = 5,
        grain_direction_lock: bool = False,
        cost_70x100: Decimal = Decimal('2.00'),
        cost_66x88: Decimal = Decimal('1.65')
    ) -> Dict[str, Any]:
        """
        محرك المفاضلة الآلية الذكية بين مقاسات الأفرخ (70x100 vs 66x88) لاختيار الأوفر تكلفة
        """
        try:
            # 1. حساب الفرخ 70x100
            res_70x100 = self.calculate_sheets_with_knife_clearance(
                sheet_width_cm=Decimal('100.00'),
                sheet_height_cm=Decimal('70.00'),
                item_width_cm=item_width_cm,
                item_height_cm=item_height_cm,
                is_die_cut=is_die_cut,
                knife_clearance_mm=knife_clearance_mm,
                grain_direction_lock=grain_direction_lock
            )

            # 2. حساب الفرخ 66x88
            res_66x88 = self.calculate_sheets_with_knife_clearance(
                sheet_width_cm=Decimal('88.00'),
                sheet_height_cm=Decimal('66.00'),
                item_width_cm=item_width_cm,
                item_height_cm=item_height_cm,
                is_die_cut=is_die_cut,
                knife_clearance_mm=knife_clearance_mm,
                grain_direction_lock=grain_direction_lock
            )

            items_70 = res_70x100.get('items_per_sheet', 0)
            items_66 = res_66x88.get('items_per_sheet', 0)

            c_70 = self._to_decimal(cost_70x100)
            c_66 = self._to_decimal(cost_66x88)

            cost_per_item_70 = (c_70 / Decimal(str(items_70))).quantize(Decimal('0.0001')) if items_70 > 0 else Decimal('9999.00')
            cost_per_item_66 = (c_66 / Decimal(str(items_66))).quantize(Decimal('0.0001')) if items_66 > 0 else Decimal('9999.00')

            if cost_per_item_66 < cost_per_item_70:
                optimal_sheet = '66x88'
                optimal_items = items_66
                optimal_unit_cost = cost_per_item_66
                optimal_sheet_cost = c_66
                waste_pct = res_66x88.get('waste_percentage', Decimal('0.00'))
            else:
                optimal_sheet = '70x100'
                optimal_items = items_70
                optimal_unit_cost = cost_per_item_70
                optimal_sheet_cost = c_70
                waste_pct = res_70x100.get('waste_percentage', Decimal('0.00'))

            savings_pct = Decimal('0.00')
            if cost_per_item_70 > 0 and cost_per_item_66 < cost_per_item_70:
                savings_pct = (((cost_per_item_70 - cost_per_item_66) / cost_per_item_70) * Decimal('100.00')).quantize(Decimal('0.01'))

            return {
                'success': True,
                'optimal_sheet_size': optimal_sheet,
                'optimal_items_per_sheet': optimal_items,
                'optimal_cost_per_item': optimal_unit_cost,
                'optimal_sheet_cost': optimal_sheet_cost,
                'waste_percentage': waste_pct,
                'savings_percentage': savings_pct,
                'comparison': {
                    '70x100': {
                        'items_per_sheet': items_70,
                        'cost_per_item': cost_per_item_70,
                        'waste_pct': res_70x100.get('waste_percentage', Decimal('0.00'))
                    },
                    '66x88': {
                        'items_per_sheet': items_66,
                        'cost_per_item': cost_per_item_66,
                        'waste_pct': res_66x88.get('waste_percentage', Decimal('0.00'))
                    }
                }
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'details': _('خطأ في المفاضلة الآلية لمقاسات الأفرخ')
            }

    def calculate_shipment_weight_and_vehicle(
        self,
        sheets_count: int,
        sheet_width_cm: Decimal,
        sheet_height_cm: Decimal,
        paper_weight_gsm: int,
        cartons_weight: Decimal = Decimal('0.00')
    ) -> Dict[str, Any]:
        """
        حساب إجمالي وزن الشحنة بالكيلوجرام واقتراح وسيلة النقل المناسبة
        """
        try:
            cnt = int(sheets_count)
            sw = self._to_decimal(sheet_width_cm)
            sh = self._to_decimal(sheet_height_cm)
            gsm = Decimal(str(paper_weight_gsm))
            c_weight = self._to_decimal(cartons_weight)

            # مساحة الفرخ بالمتر المربع
            sheet_area_sqm = (sw * sh) / Decimal('10000.00')
            
            # إجمالي وزن الورق بالكيلوجرام
            paper_weight_kg = (Decimal(str(cnt)) * sheet_area_sqm * gsm) / Decimal('1000.00')
            total_weight_kg = (paper_weight_kg + c_weight).quantize(Decimal('0.01'))

            # اقتراح وسيلة النقل
            if total_weight_kg <= Decimal('25.00'):
                vehicle_code = 'MOTORCYCLE'
                vehicle_name = _('موتوسيكل / دليفري سريع')
            elif total_weight_kg <= Decimal('500.00'):
                vehicle_code = 'SMALL_VAN'
                vehicle_name = _('سيارة فان صغيرة / سوزوكي')
            elif total_weight_kg <= Decimal('1500.00'):
                vehicle_code = 'HALF_TRUCK'
                vehicle_name = _('سيارة نصف نقل / دبابة')
            else:
                vehicle_code = 'JUMBO_TRUCK'
                vehicle_name = _('سيارة جامبو / نقل ثقيل')

            return {
                'success': True,
                'total_weight_kg': total_weight_kg,
                'paper_weight_kg': paper_weight_kg.quantize(Decimal('0.01')),
                'cartons_weight_kg': c_weight,
                'sheet_area_sqm': sheet_area_sqm.quantize(Decimal('0.0001')),
                'sheets_count': cnt,
                'recommended_vehicle_code': vehicle_code,
                'recommended_vehicle_name': vehicle_name
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'details': _('خطأ في حساب وزن الشحنة')
            }

    def validate_artwork_dimensions_match(
        self,
        quoted_width_cm: Decimal,
        quoted_height_cm: Decimal,
        artwork_width_cm: Decimal,
        artwork_height_cm: Decimal,
        tolerance_percentage: Decimal = Decimal('1.00')
    ) -> Dict[str, Any]:
        """
        فحص ومطابقة أبعاد ملف التصميم المرفوع (Artwork) مع التسعير المعتمد
        """
        try:
            qw = self._to_decimal(quoted_width_cm)
            qh = self._to_decimal(quoted_height_cm)
            aw = self._to_decimal(artwork_width_cm)
            ah = self._to_decimal(artwork_height_cm)
            tol = self._to_decimal(tolerance_percentage)

            quoted_area = qw * qh
            artwork_area = aw * ah

            if quoted_area <= 0:
                return {'success': False, 'error': _('المساحة المسعرة غير صحيحة')}

            area_diff_pct = (((artwork_area - quoted_area) / quoted_area) * Decimal('100.00')).quantize(Decimal('0.01'))
            is_matched = abs(area_diff_pct) <= tol
            is_escalation_required = area_diff_pct > tol

            return {
                'success': True,
                'is_matched': is_matched,
                'is_escalation_required': is_escalation_required,
                'quoted_area_sqcm': quoted_area.quantize(Decimal('0.01')),
                'artwork_area_sqcm': artwork_area.quantize(Decimal('0.01')),
                'area_difference_percentage': area_diff_pct,
                'warning_message': _('تنبيه: مساحة التصميم تزيد بنسبة {}% عن التسعير المعتمد').format(area_diff_pct) if is_escalation_required else None
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'details': _('خطأ في مطابقة أبعاد التصميم')
            }

    def calculate_scrap_salvage_value(
        self,
        total_waste_weight_kg: Decimal,
        scrap_rate_per_kg: Decimal = Decimal('8.00')
    ) -> Dict[str, Any]:
        """
        احتساب القيمة الاستردادية لبيع دشت وفضلات الورق
        """
        try:
            weight_kg = self._to_decimal(total_waste_weight_kg)
            rate = self._to_decimal(scrap_rate_per_kg)
            salvage_value = (weight_kg * rate).quantize(Decimal('0.01'))

            return {
                'success': True,
                'total_waste_weight_kg': weight_kg,
                'scrap_rate_per_kg': rate,
                'scrap_salvage_value': salvage_value
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'details': _('خطأ في حساب القيمة الاستردادية للدشت')
            }

