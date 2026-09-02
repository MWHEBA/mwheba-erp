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
    
    def calculate_auto_plate_count(
        self,
        colors_front: int = 1,
        colors_back: int = 0,
        print_mode: str = 'work_and_turn'
    ) -> int:
        """
        الحساب الآلي لعدد زنكات CTP
        
        Args:
            colors_front: عدد ألوان الوجه
            colors_back: عدد ألوان الظهر
            print_mode: طريقة السحب (work_and_turn طبع وقلب / sheetwise وجهين منفصل)
            
        Returns:
            int: عدد الزنكات المحسوب
        """
        c_front = max(0, int(colors_front or 0))
        c_back = max(0, int(colors_back or 0))
        
        if c_back == 0:
            return max(1, c_front)
        elif print_mode == 'sheetwise':
            return c_front + c_back
        else:  # work_and_turn طبع وقلب
            return max(c_front, c_back)

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

    def calculate_die_cutting_cost(
        self,
        sheets_count: int,
        run_rate_per_1000: Decimal = Decimal('50.00'),
        min_setup_fee: Decimal = Decimal('100.00'),
        is_archived_mould: bool = False,
        new_mould_cost: Decimal = Decimal('350.00'),
        customer_mould_rack: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        تسعير التكسير (مع التمييز بين اسطمبة جديدة أو استخدام اسطمبة بالأرشيف)
        """
        try:
            cnt = int(sheets_count)
            r_rate = self._to_decimal(run_rate_per_1000)
            setup = self._to_decimal(min_setup_fee)
            m_cost = Decimal('0.00') if is_archived_mould else self._to_decimal(new_mould_cost)

            thousands = Decimal(str(cnt)) / Decimal('1000.00')
            run_pull_cost = max(setup, (thousands * r_rate).quantize(Decimal('0.01')))
            total_cost = (m_cost + run_pull_cost).quantize(Decimal('0.01'))

            return {
                'success': True,
                'sheets_count': cnt,
                'is_archived_mould': is_archived_mould,
                'customer_mould_rack': customer_mould_rack,
                'mould_cost': m_cost,
                'run_pull_cost': run_pull_cost,
                'total_cost': total_cost
            }
        except Exception as e:
            return {'success': False, 'error': str(e), 'details': _('خطأ في تسعير التكسير')}

    def calculate_spot_colors_and_varnish_cost(
        self,
        pantone_colors_count: int = 0,
        pantone_ink_cost_per_color: Decimal = Decimal('300.00'),
        washup_fee_per_color: Decimal = Decimal('150.00'),
        has_aqueous_varnish: bool = False,
        varnish_rate_per_1000: Decimal = Decimal('80.00'),
        sheets_count: int = 1000,
        press_standby_hours: Decimal = Decimal('0.00'),
        standby_hourly_rate: Decimal = Decimal('500.00')
    ) -> Dict[str, Any]:
        """
        تسعير أحبار الألوان المخصوصة وغسيل الأبراج والورنيش المائي وساعات انتظار الماكينة
        """
        try:
            p_count = int(pantone_colors_count)
            p_ink = self._to_decimal(pantone_ink_cost_per_color)
            p_wash = self._to_decimal(washup_fee_per_color)
            v_rate = self._to_decimal(varnish_rate_per_1000)
            s_hours = self._to_decimal(press_standby_hours)
            s_rate = self._to_decimal(standby_hourly_rate)
            cnt = int(sheets_count)

            pantone_cost = (Decimal(str(p_count)) * (p_ink + p_wash)).quantize(Decimal('0.01'))
            thousands = Decimal(str(cnt)) / Decimal('1000.00')
            varnish_cost = (thousands * v_rate).quantize(Decimal('0.01')) if has_aqueous_varnish else Decimal('0.00')
            standby_cost = (s_hours * s_rate).quantize(Decimal('0.01'))
            total_cost = (pantone_cost + varnish_cost + standby_cost).quantize(Decimal('0.01'))

            return {
                'success': True,
                'pantone_colors_count': p_count,
                'pantone_cost': pantone_cost,
                'has_aqueous_varnish': has_aqueous_varnish,
                'varnish_cost': varnish_cost,
                'press_standby_hours': s_hours,
                'standby_cost': standby_cost,
                'total_cost': total_cost
            }
        except Exception as e:
            return {'success': False, 'error': str(e), 'details': _('خطأ في حساب أحبار الألوان المخصوصة والورنيش')}

    def calculate_gang_run_cost(
        self,
        names_count: int,
        quantity_per_name: int,
        total_plate_set_cost: Decimal,
        total_press_run_cost: Decimal
    ) -> Dict[str, Any]:
        """
        محاكاة الطباعة التجميعية للشركات وتوزيع التكلفة بالتساوي على عدد الأسماء
        """
        try:
            n_count = max(1, int(names_count))
            qty = max(1, int(quantity_per_name))
            plates = self._to_decimal(total_plate_set_cost)
            run_c = self._to_decimal(total_press_run_cost)

            shared_fixed_cost = plates + run_c
            cost_per_name = (shared_fixed_cost / Decimal(str(n_count))).quantize(Decimal('0.01'))
            cost_per_item = (cost_per_name / Decimal(str(qty))).quantize(Decimal('0.0001'))

            # حساب تكلفة التنفيذ المنفصل للمقارنة (Standalone)
            standalone_cost_total = shared_fixed_cost * Decimal(str(n_count))
            savings_pct = Decimal('0.00')
            if standalone_cost_total > 0:
                savings_pct = (((standalone_cost_total - shared_fixed_cost) / standalone_cost_total) * Decimal('100.00')).quantize(Decimal('0.01'))

            return {
                'success': True,
                'names_count': n_count,
                'quantity_per_name': qty,
                'shared_fixed_cost': shared_fixed_cost,
                'cost_per_name': cost_per_name,
                'cost_per_item': cost_per_item,
                'standalone_cost_total': standalone_cost_total,
                'savings_percentage': savings_pct
            }
        except Exception as e:
            return {'success': False, 'error': str(e), 'details': _('خطأ في حساب الطباعة التجميعية')}

    def validate_printing_equipment_constraints(
        self,
        print_method: str = 'DIGITAL',
        paper_gsm: int = 150,
        sheet_width_cm: Decimal = Decimal('33.00'),
        sheet_height_cm: Decimal = Decimal('48.00'),
        paper_material_type: str = 'COATED',
        colors_back: int = 0,
        is_back_laminated: bool = False
    ) -> Dict[str, Any]:
        """
        صمامات التحقق من القيود الفيزيائية لماكينات الديجيتال وخامات الدوبلكس
        """
        try:
            gsm = int(paper_gsm)
            sw = self._to_decimal(sheet_width_cm)
            sh = self._to_decimal(sheet_height_cm)
            c_back = int(colors_back or 0)
            mat = (paper_material_type or '').upper()

            # 1. قيود ماكينات الديجيتال
            if print_method.upper() == 'DIGITAL':
                if gsm > 350:
                    return {
                        'is_valid': False,
                        'error': _('تحذير: لا يمكن سحب ورق بجراماج أعلى من 350 جم على ماكينات الديجيتال، ينصح بالتحويل للأوفست'),
                        'code': 'DIGITAL_GSM_LIMIT_EXCEEDED'
                    }
                if max(sw, sh) > Decimal('66.00') or min(sw, sh) > Decimal('33.00'):
                    return {
                        'is_valid': False,
                        'error': _('تحذير: أبعاد الفرخ تتجاوز الحد الأقصى لسحب ماكينات الديجيتال (33x66 سم)'),
                        'code': 'DIGITAL_DIMENSION_LIMIT_EXCEEDED'
                    }

            # 2. قيود ورق الدوبلكس غير المطلي
            if 'DUPLEX' in mat and (c_back > 0 or is_back_laminated):
                return {
                    'is_valid': False,
                    'error': _('تحذير: ورق الدوبلكس غير مطلي من الظهر ولا يقبل طباعة ألوان أو سلوفان من الظهر'),
                    'code': 'DUPLEX_UNCOATED_BACK_INVALID'
                }

            return {'is_valid': True}
        except Exception as e:
            return {'is_valid': False, 'error': str(e)}

