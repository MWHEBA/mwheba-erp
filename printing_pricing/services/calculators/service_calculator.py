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
        حساب تكلفة خدمات الطباعة
        
        Args:
            service_data: بيانات خدمات الطباعة
            
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
                'error': _('خطأ في حساب تكلفة خدمات الطباعة: {}').format(str(e)),
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

    def calculate_vendor_uv_and_uvdtf_cost(
        self,
        service_subtype: str,
        quantity: Decimal,
        unit_rate: Decimal,
        setup_fee: Decimal = Decimal('0.00'),
        manual_application_fee_per_item: Decimal = Decimal('0.00')
    ) -> Dict[str, Any]:
        """
        تسعير خدمات الـ UV المباشر والـ UV-DTF (ستيكر الكريستال البارز) عند الموردين
        """
        try:
            qty = self._to_decimal(quantity)
            rate = self._to_decimal(unit_rate)
            setup = self._to_decimal(setup_fee)
            app_fee = self._to_decimal(manual_application_fee_per_item)

            if qty <= 0 or rate < 0:
                return {
                    'success': False,
                    'error': _('الكمية وسعر الوحدة يجب أن تكون أرقاماً موجبة'),
                    'field': 'quantity',
                    'code': 'INVALID_QUANTITY'
                }

            vendor_cost = setup + (qty * rate)
            application_cost = (qty * app_fee).quantize(Decimal('0.01'))
            total_cost = (vendor_cost + application_cost).quantize(Decimal('0.01'))

            return {
                'success': True,
                'service_subtype': service_subtype,
                'quantity': qty,
                'unit_rate': rate,
                'setup_fee': setup,
                'vendor_cost': vendor_cost.quantize(Decimal('0.01')),
                'manual_application_cost': application_cost,
                'total_cost': total_cost
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'details': _('خطأ في حساب تكلفة الـ UV / UV-DTF')
            }

    def calculate_merchandise_cost(
        self,
        blank_item_cost: Decimal,
        quantity: int,
        setup_fee: Decimal = Decimal('0.00'),
        print_technique_cost_per_item: Decimal = Decimal('0.00'),
        is_electronics: bool = False,
        defect_buffer_percentage: Decimal = Decimal('0.00')
    ) -> Dict[str, Any]:
        """
        تسعير الهدايا الدعائية للشركات مع نسبة احتياطي فحص الإلكترونيات
        """
        import math
        try:
            qty = int(quantity)
            b_cost = self._to_decimal(blank_item_cost)
            s_fee = self._to_decimal(setup_fee)
            p_cost = self._to_decimal(print_technique_cost_per_item)

            if qty <= 0 or b_cost < 0:
                return {'success': False, 'error': _('الكمية وسعر الخامة يجب أن تكون أرقاماً موجبة')}

            buffer_pct = Decimal('3.00') if (is_electronics and defect_buffer_percentage == Decimal('0.00')) else self._to_decimal(defect_buffer_percentage)
            purchase_qty = int(math.ceil(float(qty) * (1.0 + float(buffer_pct) / 100.0)))
            defect_buffer_items = purchase_qty - qty

            blank_material_cost = (Decimal(str(purchase_qty)) * b_cost).quantize(Decimal('0.01'))
            printing_cost = (Decimal(str(qty)) * p_cost).quantize(Decimal('0.01'))
            total_cost = (blank_material_cost + s_fee + printing_cost).quantize(Decimal('0.01'))
            unit_cost = (total_cost / Decimal(str(qty))).quantize(Decimal('0.01'))

            return {
                'success': True,
                'ordered_quantity': qty,
                'purchased_quantity': purchase_qty,
                'defect_buffer_items': defect_buffer_items,
                'defect_buffer_percentage': buffer_pct,
                'blank_material_cost': blank_material_cost,
                'setup_fee': s_fee,
                'printing_cost': printing_cost,
                'total_cost': total_cost,
                'cost_per_unit': unit_cost,
                'is_electronics': is_electronics
            }
        except Exception as e:
            return {'success': False, 'error': str(e), 'details': _('خطأ في تسعير الهدايا الدعائية')}

    def calculate_spine_thickness_and_binding(
        self,
        pages_count: int,
        paper_type: str = 'COATED',
        paper_gsm: int = 150,
        binding_method: str = 'SADDLE_STITCH',
        quantity: int = 1,
        unit_rate: Decimal = Decimal('0.50'),
        chipboard_cover_cost: Decimal = Decimal('0.00')
    ) -> Dict[str, Any]:
        """
        حساب سمك كعب الكتاب بالمليمتر ومطابقة نوع التجليد فيزيائياً
        """
        try:
            pages = int(pages_count)
            qty = int(quantity)
            u_rate = self._to_decimal(unit_rate)
            cover_cost = self._to_decimal(chipboard_cover_cost)

            # معامل سماكة الصفحة الواحدة (Caliper mm)
            caliper_map = {
                'COATED': (Decimal('0.0008') * Decimal(str(paper_gsm))),
                'WOODFREE': (Decimal('0.0012') * Decimal(str(paper_gsm))),
                'BULKY': (Decimal('0.0020') * Decimal(str(paper_gsm)))
            }
            caliper_mm = caliper_map.get(paper_type.upper(), Decimal('0.12'))
            leaves_count = Decimal(str(pages // 2))
            spine_thickness_mm = (leaves_count * caliper_mm).quantize(Decimal('0.1'))

            # الفحص الفيزيائي للملاءمة
            warning_msg = None
            if pages > 64 and binding_method == 'SADDLE_STITCH':
                warning_msg = _('تحذير فيزيائي: عدد الصفحات كبير للتجليد دبوس وسط، ينصح بغراء وبشر أو سلك')
            elif pages < 32 and binding_method == 'PERFECT_BINDING':
                warning_msg = _('تحذير فيزيائي: عدد الصفحات قليل جداً للتجليد غراء وبشر، ينصح بدبوس وسط')

            total_binding_cost = ((Decimal(str(qty)) * u_rate) + cover_cost).quantize(Decimal('0.01'))

            return {
                'success': True,
                'pages_count': pages,
                'paper_type': paper_type,
                'paper_gsm': paper_gsm,
                'caliper_mm': caliper_mm.quantize(Decimal('0.0001')),
                'spine_thickness_mm': spine_thickness_mm,
                'binding_method': binding_method,
                'quantity': qty,
                'unit_rate': u_rate,
                'total_binding_cost': total_binding_cost,
                'warning_message': warning_msg
            }
        except Exception as e:
            return {'success': False, 'error': str(e), 'details': _('خطأ في حساب كعب وتجليد الكتاب')}

    def calculate_wire_o_and_calendar_hanger_cost(
        self,
        books_count: int,
        wire_pitch: str = 'PITCH_3_TO_1',
        has_calendar_wall_hanger: bool = False,
        wire_unit_cost: Decimal = Decimal('1.50'),
        hanger_unit_cost: Decimal = Decimal('0.50'),
        punch_thumbcut_rate: Decimal = Decimal('0.20')
    ) -> Dict[str, Any]:
        """
        حساب تجليد السلك المزدوج Wire-O وشماعات نتائج الحائط
        """
        try:
            cnt = int(books_count)
            w_cost = self._to_decimal(wire_unit_cost)
            h_cost = self._to_decimal(hanger_unit_cost)
            p_cost = self._to_decimal(punch_thumbcut_rate)

            total_wire = (Decimal(str(cnt)) * w_cost).quantize(Decimal('0.01'))
            total_hanger = (Decimal(str(cnt)) * (h_cost + p_cost)).quantize(Decimal('0.01')) if has_calendar_wall_hanger else Decimal('0.00')
            total_cost = (total_wire + total_hanger).quantize(Decimal('0.01'))

            return {
                'success': True,
                'books_count': cnt,
                'wire_pitch': wire_pitch,
                'has_calendar_wall_hanger': has_calendar_wall_hanger,
                'total_wire_cost': total_wire,
                'total_hanger_cost': total_hanger,
                'total_cost': total_cost
            }
        except Exception as e:
            return {'success': False, 'error': str(e), 'details': _('خطأ في حساب سلك النتائج')}

    def calculate_ncr_carbonless_books_cost(
        self,
        books_count: int,
        sets_per_book: int = 50,
        parts_count: int = 3,
        numbering_rate_per_1000: Decimal = Decimal('15.00'),
        perforation_rate_per_book: Decimal = Decimal('1.00'),
        binding_tape_cost_per_book: Decimal = Decimal('2.00'),
        ncr_waste_pct: Decimal = Decimal('8.00'),
        sheet_unit_cost: Decimal = Decimal('0.30')
    ) -> Dict[str, Any]:
        """
        حساب دفاتر الفواتير والإيصالات الكربونية NCR والترقيم والتثقيب
        """
        import math
        try:
            b_cnt = int(books_count)
            sets = int(sets_per_book)
            parts = int(parts_count)
            waste = self._to_decimal(ncr_waste_pct)
            s_cost = self._to_decimal(sheet_unit_cost)
            num_rate = self._to_decimal(numbering_rate_per_1000)
            perf_rate = self._to_decimal(perforation_rate_per_book)
            tape_rate = self._to_decimal(binding_tape_cost_per_book)

            total_sets_gross = int(math.ceil(float(b_cnt * sets) * (1.0 + float(waste) / 100.0)))
            total_sheets_needed = total_sets_gross * parts
            total_paper_cost = (Decimal(str(total_sheets_needed)) * s_cost).quantize(Decimal('0.01'))

            total_numbers = b_cnt * sets
            numbering_cost = ((Decimal(str(total_numbers)) / Decimal('1000.00')) * num_rate).quantize(Decimal('0.01'))
            finishing_cost = (Decimal(str(b_cnt)) * (perf_rate + tape_rate)).quantize(Decimal('0.01'))
            total_cost = (total_paper_cost + numbering_cost + finishing_cost).quantize(Decimal('0.01'))

            return {
                'success': True,
                'books_count': b_cnt,
                'sets_per_book': sets,
                'parts_count': parts,
                'total_sheets_needed': total_sheets_needed,
                'total_paper_cost': total_paper_cost,
                'numbering_cost': numbering_cost,
                'finishing_cost': finishing_cost,
                'total_cost': total_cost,
                'cost_per_book': (total_cost / Decimal(str(b_cnt))).quantize(Decimal('0.01'))
            }
        except Exception as e:
            return {'success': False, 'error': str(e), 'details': _('خطأ في حساب دفاتر الفواتير NCR')}

    def calculate_finishing_special_effects_cost(
        self,
        effect_type: str,
        quantity: int,
        unit_run_rate: Decimal = Decimal('0.10'),
        cliche_tooling_cost: Decimal = Decimal('0.00'),
        is_foil_receptive_required: bool = False,
        foil_receptive_upgrade_fee: Decimal = Decimal('0.00'),
        paper_gsm: int = 250,
        is_single_sided_lamination: bool = False
    ) -> Dict[str, Any]:
        """
        حساب خدمات التشطيب الخاصة (البصمة، اليوفي، وترقية السلوفان) وصمام منع التقوس
        """
        try:
            qty = int(quantity)
            r_rate = self._to_decimal(unit_run_rate)
            c_cost = self._to_decimal(cliche_tooling_cost)
            upgrade = self._to_decimal(foil_receptive_upgrade_fee) if is_foil_receptive_required else Decimal('0.00')

            anti_curl_warning = None
            if is_single_sided_lamination and paper_gsm < 170:
                anti_curl_warning = _('تحذير فيزيائي: السلوفان وجه واحد لورق خفيف يسبب تقوس الورقة، ينصح بسلوفان وجهين')

            run_cost = (Decimal(str(qty)) * r_rate).quantize(Decimal('0.01'))
            total_cost = (run_cost + c_cost + upgrade).quantize(Decimal('0.01'))

            return {
                'success': True,
                'effect_type': effect_type,
                'quantity': qty,
                'run_cost': run_cost,
                'cliche_tooling_cost': c_cost,
                'foil_receptive_upgrade_cost': upgrade,
                'total_cost': total_cost,
                'anti_curl_warning': anti_curl_warning
            }
        except Exception as e:
            return {'success': False, 'error': str(e), 'details': _('خطأ في حساب التشطيبات الخاصة')}

    def calculate_prepress_trapping_and_design_fee(
        self,
        creative_design_fee: Decimal = Decimal('0.00'),
        color_separation_fee: Decimal = Decimal('0.00'),
        prepress_trapping_fee: Decimal = Decimal('0.00')
    ) -> Dict[str, Any]:
        """
        حساب أتعاب التصميم وفصل الألوان والـ Trapping المتقدم
        """
        try:
            d_fee = self._to_decimal(creative_design_fee)
            c_fee = self._to_decimal(color_separation_fee)
            t_fee = self._to_decimal(prepress_trapping_fee)
            total = (d_fee + c_fee + t_fee).quantize(Decimal('0.01'))

            return {
                'success': True,
                'creative_design_fee': d_fee,
                'color_separation_fee': c_fee,
                'prepress_trapping_fee': t_fee,
                'total_prepress_cost': total
            }
        except Exception as e:
            return {'success': False, 'error': str(e), 'details': _('خطأ في حساب أتعاب التصميم والـ Pre-Press')}

    def calculate_tender_financials_and_samples(
        self,
        specs_portal_fee: Decimal = Decimal('0.00'),
        lab_testing_fee: Decimal = Decimal('0.00'),
        contract_estimated_value: Decimal = Decimal('0.00'),
        lg_bid_bond_rate_pct: Decimal = Decimal('1.00'),
        lg_performance_bond_rate_pct: Decimal = Decimal('5.00'),
        bank_lg_commission_rate_pct: Decimal = Decimal('0.50'),
        has_bank_lg: bool = False
    ) -> Dict[str, Any]:
        """
        حساب مصاريف المناقصات وعمولات خطابات الضمان البنكية
        """
        try:
            p_fee = self._to_decimal(specs_portal_fee)
            l_fee = self._to_decimal(lab_testing_fee)
            val = self._to_decimal(contract_estimated_value)
            bid_pct = self._to_decimal(lg_bid_bond_rate_pct)
            perf_pct = self._to_decimal(lg_performance_bond_rate_pct)
            comm_pct = self._to_decimal(bank_lg_commission_rate_pct)

            bid_bond_amount = (val * (bid_pct / Decimal('100.00'))).quantize(Decimal('0.01'))
            perf_bond_amount = (val * (perf_pct / Decimal('100.00'))).quantize(Decimal('0.01'))
            
            bank_commission = ((bid_bond_amount + perf_bond_amount) * (comm_pct / Decimal('100.00'))).quantize(Decimal('0.01')) if has_bank_lg else Decimal('0.00')
            total_tender_cost = (p_fee + l_fee + bank_commission).quantize(Decimal('0.01'))

            return {
                'success': True,
                'specs_portal_fee': p_fee,
                'lab_testing_fee': l_fee,
                'bid_bond_amount': bid_bond_amount,
                'performance_bond_amount': perf_bond_amount,
                'bank_commission_cost': bank_commission,
                'total_tender_cost': total_tender_cost,
                'has_bank_lg': has_bank_lg
            }
        except Exception as e:
            return {'success': False, 'error': str(e), 'details': _('خطأ في حساب مصاريف المناقصات وخطابات الضمان')}

    def calculate_multi_leg_freight(
        self,
        legs: List[Dict[str, Any]],
        minimum_drop_fee: Decimal = Decimal('150.00'),
        staggered_drops_count: int = 1,
        is_insured_cargo: bool = False,
        cargo_value: Decimal = Decimal('0.00'),
        insurance_rate_pct: Decimal = Decimal('0.50'),
        payer: str = 'AGENCY'
    ) -> Dict[str, Any]:
        """
        حساب مشاوير النقل والتوريد المجدول على دفعات وبوليصة التأمين وصمام الحد الأدنى
        """
        try:
            min_fee = self._to_decimal(minimum_drop_fee)
            drops = max(1, int(staggered_drops_count))
            c_val = self._to_decimal(cargo_value)
            ins_pct = self._to_decimal(insurance_rate_pct)

            raw_legs_sum = Decimal('0.00')
            for leg in legs:
                raw_legs_sum += self._to_decimal(leg.get('cost', 0))

            # تطبيق الحد الأدنى لكل دفعة
            base_drop_cost = max(raw_legs_sum, min_fee)
            total_freight_drops = (base_drop_cost * Decimal(str(drops))).quantize(Decimal('0.01'))

            insurance_fee = (c_val * (ins_pct / Decimal('100.00'))).quantize(Decimal('0.01')) if is_insured_cargo else Decimal('0.00')
            total_freight_cost = (total_freight_drops + insurance_fee).quantize(Decimal('0.01'))

            return {
                'success': True,
                'legs_count': len(legs),
                'staggered_drops_count': drops,
                'minimum_drop_fee': min_fee,
                'raw_legs_sum': raw_legs_sum.quantize(Decimal('0.01')),
                'total_freight_drops': total_freight_drops,
                'insurance_fee': insurance_fee,
                'total_freight_cost': total_freight_cost,
                'payer': payer,
                'is_insured_cargo': is_insured_cargo
            }
        except Exception as e:
            return {'success': False, 'error': str(e), 'details': _('خطأ في حساب تكلفة النقل والشحن')}

