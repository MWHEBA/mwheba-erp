"""
محرك الحسابات النقي والموحد لتسعير المطبوعات
PrintingCalculationEngine (Single Source of Truth)
مبني بالكامل في الذاكرة RAM بدون أي اعتمادية إجبارية على وجود طلب مسبق في الداتابيز.
كافة المعاملات والأسعار والأرباح بالجنيه المصري (EGP) حصراً.
"""
import math
from decimal import Decimal
from typing import Dict, Any, Optional, Tuple


class PrintingCalculationEngine:
    """
    المحرك الرياضي الصناعي لتسعير المطبوعات التجارية وخامات الورق والطباعة والتشطيب.
    """

    # أسعار معيارية استرشادية للسوق المصري (Fallback Benchmark Rates بالجنيه المصري)
    BENCHMARK_RATES = {
        'press_rate_50x70': Decimal('45.00'),       # سعر التراج (لكل 1,000 سحبة) لماكينة نصف فرخ
        'press_rate_70x100': Decimal('75.00'),      # سعر التراج لماكينة فرخ كامل
        'press_floor_50x70': Decimal('200.00'),     # الحد الأدنى لفتحة ماكينة نصف فرخ
        'press_floor_70x100': Decimal('350.00'),    # الحد الأدنى لفتحة ماكينة فرخ كامل
        'plate_price_50x70': Decimal('85.00'),      # سعر زنكة CTP حرارية 50×70
        'plate_price_70x100': Decimal('160.00'),    # سعر زنكة CTP حرارية 70×100
        'plate_price_35x50': Decimal('55.00'),      # سعر زنكة CTP حرارية 35×50
        'spot_color_wash_fee': Decimal('150.00'),   # مصاريف غسيل حوض الحبر ولون مخصوص
        'paper_base_rate_300g': Decimal('3.50'),    # سعر فرخ كوشيه 300 جم استرشادي
        'digital_click_a3_color': Decimal('3.50'),  # سعر كليك ليزر ملون A3/شيت ديجيتال
        'digital_click_a3_bw': Decimal('1.00'),     # سعر كليك ليزر أبيض وأسود
        'lamination_sqm_gloss': Decimal('0.35'),    # سعر متر السلوفان اللامع
        'lamination_sqm_matte': Decimal('0.40'),    # سعر متر السلوفان المط
        'lamination_floor': Decimal('100.00'),      # الحد الأدنى للسلوفان
    }

    @classmethod
    def calculate(cls, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        نقطة الدخول الرئيسية للحسابات اللحظية وحفظ الطلبات.
        
        Args:
            params: قاموس المعطيات الخام من الـ Request أو من الموديل.
            
        Returns:
            Dict: هيكل بيانات متكامل ومفصل لتكاليف ومخرجات الشغلانة.
        """
        try:
            # 1. استخراج وتدقيق المعاملات الأساسية
            qty = cls._to_int(params.get('quantity'), 1000)
            if qty <= 0:
                qty = 1000

            product_type = str(params.get('product_type') or params.get('order_type') or 'flyer').lower()
            cover_type = str(params.get('cover_printing_type') or params.get('printing_type') or 'offset').lower()
            sides_mode = str(params.get('print_sides_mode') or 'single').lower()

            # 2. حساب الأبعاد المفتوحة للمطبوع (Open Dimensions)
            w_raw = cls._to_decimal(params.get('width'), Decimal('21.0'))
            h_raw = cls._to_decimal(params.get('height'), Decimal('29.7'))
            is_closed = cls._to_bool(params.get('is_closed_size'))
            open_dir = str(params.get('open_direction') or 'right').lower()

            open_w, open_h = cls._resolve_open_dimensions(
                w_raw, h_raw, is_closed, open_dir, product_type, params
            )

            # 3. اشتقاق مقاس القطع وشيت الماكينة
            sheet_size_str = str(params.get('sheet_size') or '70x100')
            piece_size_str = str(params.get('piece_size') or '50x70')
            w_cut, h_cut, machine_cuts = cls._resolve_cut_dimensions(sheet_size_str, piece_size_str)

            # 4. حساب المونتاج هندسياً (عدد القطع في مقاس القطع)
            grain_dir = str(params.get('grain_direction') or 'LG').upper()
            imposition = cls._calculate_imposition(open_w, open_h, w_cut, h_cut, grain_dir)

            # فحص صمام الأمان لمنع القسمة على صفر
            if imposition['montage'] <= 0:
                return {
                    'success': False,
                    'error_code': 'DIMENSIONS_EXCEED_SHEET',
                    'message': f'مقاس المطبوع المفتوح ({open_w}×{open_h} سم) أكبر من مقاس شيت الماكينة المختار ({w_cut}×{h_cut} سم)',
                    'details': {
                        'open_w': float(open_w),
                        'open_h': float(open_h),
                        'w_cut': float(w_cut),
                        'h_cut': float(h_cut)
                    }
                }

            montage = imposition['montage']
            parent_yield = montage * machine_cuts

            # 5. فحص نمط الطباعة وصمامات الأمان الخاصة بالطبع والقلب
            if sides_mode in ['work_turn', 'work_and_turn']:
                if montage < 2:
                    # صمام أمان فيزيائي: لا يمكن طبع وقلب لقطعة واحدة في الشيت
                    sides_mode = 'work_sheet'  # تحويل تلقائي لسكتين
                is_work_turn = (sides_mode in ['work_turn', 'work_and_turn'])
            else:
                is_work_turn = False

            # 6. حسابات الورق والهالك الصريح
            paper_res = cls._calculate_paper_requirements(
                qty=qty,
                montage=montage,
                machine_cuts=machine_cuts,
                w_cut=w_cut,
                h_cut=h_cut,
                params=params
            )

            # 7. حسابات الطباعة (أوفست / ديجيتال / بانر)
            printing_res = cls._calculate_printing_costs(
                cover_type=cover_type,
                sides_mode=sides_mode,
                gross_press_sheets=paper_res['gross_press_sheets'],
                w_cut=w_cut,
                h_cut=h_cut,
                params=params
            )

            # 8. حسابات الزنكات CTP
            plates_res = cls._calculate_ctp_plates(
                cover_type=cover_type,
                sides_mode=sides_mode,
                w_cut=w_cut,
                h_cut=h_cut,
                params=params
            )

            # 9. حسابات ما بعد الطباعة والتشطيب (سلوفان، تكسير، يو في، بصمة)
            finishing_res = cls._calculate_finishing_costs(
                params=params,
                gross_press_sheets=paper_res['gross_press_sheets'],
                parent_sheets=paper_res['parent_sheets'],
                w_cut=w_cut,
                h_cut=h_cut
            )

            # 10. حسابات الصفحات الداخلية (لو كان كتالوج أو كتاب)
            inner_res = cls._calculate_inner_pages(
                params=params,
                product_type=product_type,
                qty=qty
            )

            # 11. حسابات التغليف واللوجستيات
            logistics_res = cls._calculate_logistics(params, qty)

            # 12. تجميع التكاليف الإجمالية وهوامش الربح
            totals_res = cls._aggregate_totals(
                paper_res=paper_res,
                printing_res=printing_res,
                plates_res=plates_res,
                finishing_res=finishing_res,
                inner_res=inner_res,
                logistics_res=logistics_res,
                params=params,
                qty=qty
            )

            return {
                'success': True,
                'dimensions': {
                    'open_width': float(open_w),
                    'open_height': float(open_h),
                    'is_closed': is_closed,
                    'open_direction': open_dir,
                },
                'montage': {
                    'cuts_per_sheet': montage,
                    'parent_sheet_yield': parent_yield,
                    'machine_cuts': machine_cuts,
                    'press_sheet_w': float(w_cut),
                    'press_sheet_h': float(h_cut),
                    'net_press_w': float(imposition['net_w']),
                    'net_press_h': float(imposition['net_h']),
                    'orientation_applied': imposition['orientation'],
                    'is_work_turn_allowed': (montage >= 2),
                },
                'paper': paper_res,
                'printing': printing_res,
                'plates': plates_res,
                'finishing': finishing_res,
                'inner': inner_res,
                'logistics': logistics_res,
                'totals': totals_res,
                'currency': 'EGP'
            }

        except Exception as e:
            return {
                'success': False,
                'error_code': 'CALCULATION_ENGINE_ERROR',
                'message': f'خطأ أثناء معالجة الحسابات: {str(e)}',
                'details': str(e)
            }

    # -------------------------------------------------------------------------
    # الدوال المساعدة الداخلية لحساب الأركان الصناعية
    # -------------------------------------------------------------------------

    @classmethod
    def _resolve_open_dimensions(
        cls, w: Decimal, h: Decimal, is_closed: bool, open_dir: str, 
        product_type: str, params: Dict[str, Any]
    ) -> Tuple[Decimal, Decimal]:
        """حساب المقاس المفتوح مع مراعاة جهة الفتح وسماكة الكعب في الكتب والمجلات."""
        open_w, open_h = w, h
        if is_closed:
            if open_dir == 'top':
                open_h = h * Decimal('2.0')
            else:
                open_w = w * Decimal('2.0')

        # لو كتاب أو كتالوج بتجليد كعب (غراء أو هاردكفر)
        binding_type = str(params.get('binding_type') or 'saddle_stitch').lower()
        if product_type in ['book', 'catalog', 'book_catalog', 'magazine'] and binding_type in ['perfect_binding', 'hardcover']:
            pages = cls._to_decimal(params.get('pages_count') or params.get('inner_pages_count'), Decimal('64'))
            gsm = cls._to_decimal(params.get('inner_paper_weight'), Decimal('135'))
            paper_type = str(params.get('inner_paper_type') or 'couche').lower()
            bulk = Decimal('1.1') if 'couche' in paper_type else Decimal('1.4')
            # سمك الكعب بالسم = ((عدد الصفحات / 2) * (الجراماج / 1000) * bulk) / 10
            spine_cm = ((pages / Decimal('2.0')) * (gsm / Decimal('1000.0')) * bulk) / Decimal('10.0')
            spine_cm = max(Decimal('0.3'), spine_cm.quantize(Decimal('0.01')))
            open_w += spine_cm

        return open_w, open_h

    @classmethod
    def _resolve_cut_dimensions(cls, sheet_size_str: str, piece_size_str: str) -> Tuple[Decimal, Decimal, int]:
        """
        اشتقاق الأبعاد الدقيقة لشيت الماكينة (W_cut, H_cut) بناءً على الفرخ الخام المختار.
        """
        # 1. تحديد أبعاد الفرخ الخام القياسية بمصر
        if '66x88' in sheet_size_str or '88x66' in sheet_size_str:
            p_w, p_h = Decimal('88.0'), Decimal('66.0')
        elif '60x85' in sheet_size_str or '85x60' in sheet_size_str or '60x90' in sheet_size_str or '90x60' in sheet_size_str:
            p_w, p_h = Decimal('85.0'), Decimal('60.0')
        elif '57x86' in sheet_size_str or '86x57' in sheet_size_str:
            p_w, p_h = Decimal('86.0'), Decimal('57.0')
        else:
            p_w, p_h = Decimal('100.0'), Decimal('70.0')  # الافتراضي 70×100

        # 2. تحديد مقاس القطع ومعامل تفصيل الفرخ
        piece_lower = piece_size_str.lower()
        if 'full' in piece_lower or '100' in piece_lower or 'فرخ كامل' in piece_lower:
            return p_w, p_h, 1
        elif 'half' in piece_lower or 'نصف' in piece_lower or '50x70' in piece_lower or '42' in piece_lower or '44' in piece_lower:
            # نصف الفرخ: يقص الضلع الأكبر للفرخ بالنصف
            return p_h, (p_w / Decimal('2.0')), 2
        elif 'quarter' in piece_lower or 'ربع' in piece_lower or '35x50' in piece_lower or '30' in piece_lower or '33' in piece_lower:
            # ربع الفرخ: نصف النصف
            return (p_w / Decimal('2.0')), (p_h / Decimal('2.0')), 4
        elif 'eighth' in piece_lower or 'ثمن' in piece_lower or '25x35' in piece_lower:
            # ثمن الفرخ
            return (p_h / Decimal('2.0')), (p_w / Decimal('4.0')), 8
        else:
            # الافتراضي الشائع نصف فرخ
            return p_h, (p_w / Decimal('2.0')), 2

    @classmethod
    def _calculate_imposition(
        cls, open_w: Decimal, open_h: Decimal, w_cut: Decimal, h_cut: Decimal, grain_dir: str
    ) -> Dict[str, Any]:
        """
        حساب المونتاج هندسياً بعد استقطاع 2.0 سم (1.5 سم بنسة ماكينة + 0.5 سم طهارة مقص).
        """
        margin = Decimal('2.0')
        net_w = max(Decimal('0.1'), w_cut - margin)
        net_h = max(Decimal('0.1'), h_cut - margin)

        if open_w <= 0 or open_h <= 0 or (net_w < open_w and net_w < open_h) or (net_h < open_w and net_h < open_h):
            return {'montage': 0, 'net_w': net_w, 'net_h': net_h, 'orientation': 'none'}

        cuts_normal = int(net_w // open_w) * int(net_h // open_h)
        cuts_rotated = int(net_w // open_h) * int(net_h // open_w)

        if cuts_rotated > cuts_normal:
            montage = cuts_rotated
            orientation = 'rotated'
        else:
            montage = cuts_normal
            orientation = 'normal'

        return {
            'montage': montage,
            'net_w': net_w,
            'net_h': net_h,
            'orientation': orientation
        }

    @classmethod
    def _calculate_paper_requirements(
        cls, qty: int, montage: int, machine_cuts: int, w_cut: Decimal, h_cut: Decimal, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """حساب شيتات الماكينة الصافية، الهادر التفاعلي، وأفرخ الورق الخام وتكلفتها بالجنيه المصري."""
        net_press_sheets = math.ceil(qty / montage)

        # الهادر التفاعلي من المستخدم، أو اقتراح أولي ذكي
        waste_input = params.get('waste_sheets')
        if waste_input is not None and str(waste_input).strip() != '':
            waste_sheets = cls._to_int(waste_input, 20)
        else:
            # اقتراح ذكي استرشادي: 20 فرخ لتظبيط الماكينة + 10 لكل مرحلة تشطيب
            waste_sheets = 20

        gross_press_sheets = net_press_sheets + waste_sheets
        parent_sheets = math.ceil(gross_press_sheets / machine_cuts)

        # قراءة سعر الفرخ الخام من خدمة المورد إن وجدت، أو السعر الاسترشادي
        sheet_price = cls._resolve_paper_price(params, w_cut, h_cut)
        total_paper_cost = (Decimal(str(parent_sheets)) * sheet_price).quantize(Decimal('0.01'))

        # حساب عدد الرزم (500 فرخ للرزمة قياسياً)
        sheets_per_pack = cls._to_int(params.get('sheets_per_pack'), 500)
        if sheets_per_pack <= 0:
            sheets_per_pack = 500
        packs_count = round(parent_sheets / sheets_per_pack, 2)

        return {
            'net_press_sheets': net_press_sheets,
            'waste_sheets': waste_sheets,
            'gross_press_sheets': gross_press_sheets,
            'parent_sheets': parent_sheets,
            'sheets_per_pack': sheets_per_pack,
            'packs_count': packs_count,
            'sheet_unit_price': float(sheet_price),
            'total_cost': float(total_paper_cost)
        }

    @classmethod
    def _resolve_paper_price(cls, params: Dict[str, Any], w_cut: Decimal, h_cut: Decimal) -> Decimal:
        """جلب سعر الفرخ الخام بالجنيه المصري من SupplierService أو استخدام السعر الاسترشادي."""
        paper_price_input = params.get('paper_price')
        if paper_price_input is not None and str(paper_price_input).strip() != '':
            try:
                return cls._to_decimal(paper_price_input, Decimal('0.00'))
            except Exception:
                pass

        # محاولة قراءة الخدمة من موديول الموردين إذا تم تمرير المعرف
        paper_svc_id = params.get('paper_service_id') or params.get('paper_type_id')
        if paper_svc_id:
            try:
                from supplier.models import SupplierService
                svc = SupplierService.objects.filter(id=paper_svc_id, is_active=True).first()
                if svc and svc.base_price > 0:
                    return Decimal(str(svc.base_price))
            except Exception:
                pass

        # السعر الاسترشادي بحسب الجراماج
        gsm = cls._to_decimal(params.get('paper_weight'), Decimal('300.0'))
        base_rate = cls.BENCHMARK_RATES['paper_base_rate_300g']
        return (base_rate * (gsm / Decimal('300.0'))).quantize(Decimal('0.01'))

    @classmethod
    def _calculate_printing_costs(
        cls, cover_type: str, sides_mode: str, gross_press_sheets: int, 
        w_cut: Decimal, h_cut: Decimal, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """حساب تكاليف الطباعة (أوفست مع صمام فتحة الماكينة والتراج / ديجيتال / بانر) بالجنيه المصري."""
        if cover_type == 'none':
            return {'total_cost': 0.0, 'press_pulls': 0, 'tirages': 0, 'printing_type': 'none'}

        if cover_type == 'digital':
            # طباعة ليزر ديجيتال
            is_color = cls._to_bool(params.get('is_digital_color', True))
            click_rate = cls.BENCHMARK_RATES['digital_click_a3_color'] if is_color else cls.BENCHMARK_RATES['digital_click_a3_bw']
            sides_mult = 2 if 'double' in sides_mode or 'work' in sides_mode else 1
            total_clicks = gross_press_sheets * sides_mult
            cost = (Decimal(str(total_clicks)) * click_rate).quantize(Decimal('0.01'))
            return {
                'total_cost': float(cost),
                'press_pulls': total_clicks,
                'tirages': 0,
                'click_rate': float(click_rate),
                'printing_type': 'digital'
            }

        # طباعة أوفست (Offset)
        pulls_mult = 2 if sides_mode in ['work_turn', 'work_and_turn', 'work_sheet'] else 1
        press_pulls = gross_press_sheets * pulls_mult
        tirages = math.ceil(press_pulls / 1000)

        # استدعاء سعر التراج والحد الأدنى لفتحة الماكينة من ماكينة المورد المحددة
        rate_per_1000, min_floor = cls._resolve_press_machine_rates(params, w_cut, h_cut)

        base_press_cost = Decimal(str(tirages)) * rate_per_1000
        applied_press_cost = max(min_floor, base_press_cost)
        is_floor_applied = (base_press_cost < min_floor)

        # مصاريف الألوان المخصوصة (بنتون - 150 ج لكل لون مخصوص لغسيل حوض الحبر)
        spot_front = cls._to_int(params.get('spot_colors_front'), 0)
        spot_back = cls._to_int(params.get('spot_colors_back'), 0) if sides_mode == 'work_sheet' else 0
        spot_colors_cost = Decimal(str(spot_front + spot_back)) * cls.BENCHMARK_RATES['spot_color_wash_fee']

        total_offset_cost = (applied_press_cost + spot_colors_cost).quantize(Decimal('0.01'))

        return {
            'total_cost': float(total_offset_cost),
            'base_press_cost': float(base_press_cost),
            'applied_press_cost': float(applied_press_cost),
            'is_floor_applied': is_floor_applied,
            'press_pulls': press_pulls,
            'tirages': tirages,
            'rate_per_1000': float(rate_per_1000),
            'minimum_charge': float(min_floor),
            'spot_colors_cost': float(spot_colors_cost),
            'printing_type': 'offset'
        }

    @classmethod
    def _resolve_press_machine_rates(
        cls, params: Dict[str, Any], w_cut: Decimal, h_cut: Decimal
    ) -> Tuple[Decimal, Decimal]:
        # قراءة سعر التراج الصريح إذا تم تمريره من الفورم أو الاختبار
        press_rate_input = params.get('press_rate')
        if press_rate_input:
            try:
                explicit_rate = cls._to_decimal(press_rate_input, Decimal('0.0'))
                if explicit_rate > 0:
                    return explicit_rate, Decimal('0.00')
            except Exception:
                pass

        press_svc_id = params.get('cover_press_machine') or params.get('press_service_id')
        if press_svc_id:
            try:
                from supplier.models import SupplierService
                svc = SupplierService.objects.filter(id=press_svc_id, is_active=True).first()
                if svc:
                    rate = Decimal(str(svc.base_price)) if svc.base_price > 0 else cls.BENCHMARK_RATES['press_rate_50x70']
                    floor = Decimal(str(svc.minimum_charge)) if (svc.minimum_charge and svc.minimum_charge > 0) else Decimal('0.00')
                    return rate, floor
            except Exception:
                pass

        # قراءة الحد الأدنى لفتحة الماكينة إن وجد صراحة
        explicit_floor = params.get('press_floor') or params.get('minimum_charge')
        floor = cls._to_decimal(explicit_floor, Decimal('0.00')) if explicit_floor is not None else Decimal('0.00')

        # التسعيرة الاسترشادية بحسب مقاس الماكينة (50×70 نصف فرخ = 45 ج، أكبر من 70 سم فرخ كامل = 75 ج)
        is_full_sheet = (w_cut > Decimal('70.0') or h_cut > Decimal('70.0'))
        if is_full_sheet:
            return cls.BENCHMARK_RATES['press_rate_70x100'], floor
        else:
            return cls.BENCHMARK_RATES['press_rate_50x70'], floor

    @classmethod
    def _calculate_ctp_plates(
        cls, cover_type: str, sides_mode: str, w_cut: Decimal, h_cut: Decimal, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """حساب عدد زنكات CTP وتكلفتها بالجنيه المصري مع تصفير الظهر في الطبع والقلب."""
        if cover_type != 'offset':
            return {'total_cost': 0.0, 'total_plates': 0, 'is_archived': False}

        is_archived = cls._to_bool(params.get('is_plates_archived')) or (params.get('plates_option') == 'archived')

        front_colors = cls._to_int(params.get('colors_front'), 4)
        spot_front = cls._to_int(params.get('spot_colors_front'), 0)
        back_colors = cls._to_int(params.get('colors_back'), 4)
        spot_back = cls._to_int(params.get('spot_colors_back'), 0)

        # حساب زنكات الوجه
        plates_front = front_colors + spot_front

        # حساب زنكات الظهر (تتصفر تماماً في الوجه الواحد وفي الطبع والقلب)
        if sides_mode == 'work_sheet':
            plates_back = back_colors + spot_back
        else:
            plates_back = 0  # توفير 50% في الطبع والقلب

        total_plates = plates_front + plates_back

        # سعر الزنكة من خدمة المورد أو الاسترشادي
        plate_price = cls._resolve_plate_price(params, w_cut, h_cut)

        total_cost = Decimal('0.00') if is_archived else (Decimal(str(total_plates)) * plate_price).quantize(Decimal('0.01'))

        return {
            'total_cost': float(total_cost),
            'total_plates': total_plates,
            'plates_front': plates_front,
            'plates_back': plates_back,
            'unit_price': float(plate_price),
            'is_archived': is_archived,
            'is_work_turn_savings': (sides_mode in ['work_turn', 'work_and_turn'])
        }

    @classmethod
    def _resolve_plate_price(cls, params: Dict[str, Any], w_cut: Decimal, h_cut: Decimal) -> Decimal:
        """جلب سعر الزنكة بالجنيه المصري."""
        plate_price_input = params.get('plate_price')
        if plate_price_input:
            try:
                return cls._to_decimal(plate_price_input, cls.BENCHMARK_RATES['plate_price_50x70'])
            except Exception:
                pass

        ctp_svc_id = params.get('ctp_supplier') or params.get('ctp_service_id')
        if ctp_svc_id:
            try:
                from supplier.models import SupplierService
                svc = SupplierService.objects.filter(id=ctp_svc_id, is_active=True).first()
                if svc and svc.base_price > 0:
                    return Decimal(str(svc.base_price))
            except Exception:
                pass

        is_full = (w_cut > Decimal('55.0') or h_cut > Decimal('75.0'))
        return cls.BENCHMARK_RATES['plate_price_70x100'] if is_full else cls.BENCHMARK_RATES['plate_price_50x70']

    @classmethod
    def _calculate_finishing_costs(
        cls, params: Dict[str, Any], gross_press_sheets: int, parent_sheets: int, w_cut: Decimal, h_cut: Decimal
    ) -> Dict[str, Any]:
        """حساب خدمات ما بعد الطباعة (السلوفان، التكسير، البصمة، اليو في) بالجنيه المصري."""
        total_finishing = Decimal('0.00')
        details = {}

        # 1. السلوفان (Lamination)
        lam_type = str(params.get('lamination') or params.get('lamination_type') or 'none').lower()
        if lam_type not in ['none', '']:
            sqm_per_sheet = (w_cut * h_cut) / Decimal('10000.0')
            total_sqm = sqm_per_sheet * Decimal(str(gross_press_sheets))
            sides = 2 if 'double' in lam_type or params.get('lamination_sides') == 'double' else 1
            rate = cls.BENCHMARK_RATES['lamination_sqm_matte'] if 'matte' in lam_type else cls.BENCHMARK_RATES['lamination_sqm_gloss']
            lam_cost = max(cls.BENCHMARK_RATES['lamination_floor'], total_sqm * Decimal(str(sides)) * rate)
            lam_cost = lam_cost.quantize(Decimal('0.01'))
            total_finishing += lam_cost
            details['lamination'] = float(lam_cost)

        # 2. التكسير (Die-Cutting)
        has_die = cls._to_bool(params.get('has_die_cut')) or cls._to_bool(params.get('die_cutting'))
        if has_die:
            die_mould_cost = Decimal('250.00')  # فورمة خشب وسكاكين
            die_pull_cost = Decimal(str(math.ceil(gross_press_sheets / 1000))) * Decimal('50.00')
            die_total = die_mould_cost + die_pull_cost
            total_finishing += die_total
            details['die_cutting'] = float(die_total)

        # 3. السبوت يو في (Spot UV)
        if cls._to_bool(params.get('has_spot_uv')):
            uv_cost = max(Decimal('200.00'), Decimal(str(gross_press_sheets)) * Decimal('0.20'))
            total_finishing += uv_cost
            details['spot_uv'] = float(uv_cost)

        return {
            'total_cost': float(total_finishing),
            'details': details
        }

    @classmethod
    def _calculate_inner_pages(cls, params: Dict[str, Any], product_type: str, qty: int) -> Dict[str, Any]:
        """حساب الملازم والصفحات الداخلية للكتب والكتالوجات بالجنيه المصري."""
        if product_type not in ['book', 'catalog', 'book_catalog', 'magazine']:
            return {'total_cost': 0.0, 'pages_count': 0, 'signatures_count': 0}

        pages = cls._to_int(params.get('pages_count') or params.get('inner_pages'), 32)
        sig_capacity = 16  # ملزمة 16 صفحة
        signatures = math.ceil(pages / sig_capacity)

        # ورق الداخلي: كل ملزمة 16 صفحة تأخذ نصف فرخ وش وضهر
        sheets_per_book = signatures
        total_inner_sheets = sheets_per_book * qty
        inner_waste = math.ceil(total_inner_sheets * 0.05)
        gross_inner = total_inner_sheets + inner_waste

        # سعر ورق الداخلي (مثلاً 115 جم أو 135 جم كوشيه = 2.00 ج للفرخ)
        inner_sheet_price = Decimal('2.00')
        inner_paper_cost = (Decimal(str(gross_inner)) * inner_sheet_price).quantize(Decimal('0.01'))

        # طباعة الداخلي: كل ملزمة تحتاج 4 زنكات وش وضهر طبع وقلب أو 8 زنكات
        inner_plates = signatures * 4
        inner_plate_cost = Decimal(str(inner_plates)) * cls.BENCHMARK_RATES['plate_price_50x70']

        # سحبات الداخلي
        inner_pulls = gross_inner * 2
        inner_tirages = math.ceil(inner_pulls / 1000)
        inner_press_cost = Decimal(str(inner_tirages)) * cls.BENCHMARK_RATES['press_rate_50x70']

        total_inner_cost = inner_paper_cost + inner_plate_cost + inner_press_cost

        return {
            'total_cost': float(total_inner_cost),
            'pages_count': pages,
            'signatures_count': signatures,
            'inner_paper_cost': float(inner_paper_cost),
            'inner_press_cost': float(inner_press_cost),
            'inner_plates_cost': float(inner_plate_cost),
        }

    @classmethod
    def _calculate_logistics(cls, params: Dict[str, Any], qty: int) -> Dict[str, Any]:
        """حساب كراتين التعبئة وتكاليف الشحن والتوصيل بالجنيه المصري."""
        carton_cost = Decimal('0.00')
        delivery_cost = cls._to_decimal(params.get('shipping_cost') or params.get('delivery_cost'), Decimal('0.00'))

        capacity_per_box = cls._to_int(params.get('units_per_box') or params.get('carton_capacity'), 500)
        if capacity_per_box > 0 and cls._to_bool(params.get('has_cartons', True)):
            boxes_count = math.ceil(qty / capacity_per_box)
            carton_price = Decimal('15.00')  # 15 ج للكرتونة المعيارية
            carton_cost = Decimal(str(boxes_count)) * carton_price
        else:
            boxes_count = 0

        total_logistics = (carton_cost + delivery_cost).quantize(Decimal('0.01'))
        return {
            'total_cost': float(total_logistics),
            'boxes_count': boxes_count,
            'carton_cost': float(carton_cost),
            'delivery_cost': float(delivery_cost)
        }

    @classmethod
    def _aggregate_totals(
        cls, paper_res: Dict[str, Any], printing_res: Dict[str, Any], plates_res: Dict[str, Any],
        finishing_res: Dict[str, Any], inner_res: Dict[str, Any], logistics_res: Dict[str, Any],
        params: Dict[str, Any], qty: int
    ) -> Dict[str, Any]:
        """تجميع تكاليف الإنتاج الإجمالية وحساب الأرباح وسعر البيع النهائي بالجنيه المصري."""
        materials_cost = Decimal(str(paper_res['total_cost'])) + Decimal(str(inner_res.get('inner_paper_cost', 0.0)))
        services_cost = (
            Decimal(str(printing_res['total_cost'])) +
            Decimal(str(plates_res['total_cost'])) +
            Decimal(str(finishing_res['total_cost'])) +
            Decimal(str(inner_res.get('inner_press_cost', 0.0))) +
            Decimal(str(inner_res.get('inner_plates_cost', 0.0))) +
            Decimal(str(logistics_res['total_cost']))
        )

        total_cost = (materials_cost + services_cost).quantize(Decimal('0.01'))

        margin_percent = cls._to_decimal(params.get('profit_margin') or params.get('margin_percentage'), Decimal('25.0'))
        profit_amount = (total_cost * (margin_percent / Decimal('100.0'))).quantize(Decimal('0.01'))
        final_price = total_cost + profit_amount
        unit_price = (final_price / Decimal(str(qty))).quantize(Decimal('0.01'))

        return {
            'materials_cost': float(materials_cost),
            'services_cost': float(services_cost),
            'total_production_cost': float(total_cost),
            'profit_margin_percent': float(margin_percent),
            'profit_amount': float(profit_amount),
            'total_selling_price': float(final_price),
            'unit_selling_price': float(unit_price)
        }

    # -------------------------------------------------------------------------
    # دوال التحويل الصارم للأرقام بأمان تام
    # -------------------------------------------------------------------------

    @staticmethod
    def _to_decimal(val: Any, default: Decimal = Decimal('0.0')) -> Decimal:
        if val is None or str(val).strip() == '':
            return default
        try:
            return Decimal(str(val))
        except Exception:
            return default

    @staticmethod
    def _to_int(val: Any, default: int = 0) -> int:
        if val is None or str(val).strip() == '':
            return default
        try:
            return int(float(str(val)))
        except Exception:
            return default

    @staticmethod
    def _to_bool(val: Any) -> bool:
        if isinstance(val, bool):
            return val
        s = str(val).lower().strip()
        return s in ['true', '1', 'on', 'yes', 't']

    @classmethod
    def calculate_multi_leg_freight(
        cls, legs: list, minimum_drop_fee: Decimal = Decimal('150.00'),
        staggered_drops_count: int = 1, is_insured_cargo: bool = False,
        cargo_value: Decimal = Decimal('0.00'), payer: str = 'AGENCY'
    ) -> dict:
        """حساب تكاليف النقل متعدد المحطات مع صمام الحد الأدنى والتأمين"""
        total_legs_cost = Decimal('0.00')
        for leg in legs:
            total_legs_cost += cls._to_decimal(leg.get('cost', 0), Decimal('0.00'))

        per_drop_fee = max(minimum_drop_fee, total_legs_cost)
        total_freight_drops = per_drop_fee * Decimal(str(max(1, staggered_drops_count)))
        insurance_fee = (cargo_value * Decimal('0.005')) if is_insured_cargo else Decimal('0.00')
        total_freight_cost = total_freight_drops + insurance_fee
        return {
            'success': True,
            'per_drop_fee': float(per_drop_fee),
            'total_freight_drops': float(total_freight_drops),
            'insurance_fee': float(insurance_fee),
            'total_freight_cost': float(total_freight_cost),
            'payer': payer
        }
