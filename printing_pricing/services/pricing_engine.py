"""
محرك الحسابات النقي والموحد لتسعير المطبوعات
PrintingCalculationEngine (Single Source of Truth)
مبني بالكامل في الذاكرة RAM بدون أي اعتمادية إجبارية على وجود طلب مسبق في الداتابيز.
كافة المعاملات والأسعار والأرباح بالجنيه المصري (EGP) حصراً.
"""
import math
from decimal import Decimal, ROUND_HALF_UP
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
            Dict: هيكل بيانات متكامل ومفصل لتكاليف ومخرجات أمر الطباعة.
        """
        try:
            # 0. تطبيع المعطيات المدخلة وفك أي قوائم صادرة من QueryDict
            if hasattr(params, 'dict'):
                params = params.dict()
            elif isinstance(params, dict):
                params = {k: (v[0] if isinstance(v, (list, tuple)) and len(v) == 1 else v) for k, v in params.items()}

            # 1. تحديد العملة المستهدفة لحسابات التسعير وتاريخ سعر الصرف وفق IAS 21
            target_curr = params.get('currency')
            if not target_curr:
                curr_code = params.get('currency_code')
                if curr_code:
                    try:
                        from financial.models import Currency
                        target_curr = Currency.objects.filter(code__iexact=curr_code).first()
                    except Exception:
                        pass
            if not target_curr:
                try:
                    from financial.services.exchange_rate_service import ExchangeRateService
                    target_curr = ExchangeRateService.get_functional_currency()
                except Exception:
                    pass

            order_date = params.get('order_date')
            params['_target_curr'] = target_curr
            params['_order_date'] = order_date

            # 2. استخراج وتدقيق المعاملات الأساسية
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
            piece_size_str = str(params.get('piece_size') or '35x50')
            w_cut, h_cut, machine_cuts = cls._resolve_cut_dimensions(sheet_size_str, piece_size_str, params)

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

            max_montage = imposition['montage']

            # فحص إمكانية تعديل المونتاج للأسفل فقط (سقف أقصى لا يمكن تجاوزه)
            raw_manual = params.get('montage_count')
            if raw_manual is None or str(raw_manual).strip() == '':
                raw_manual = params.get('custom_montage')
            if raw_manual is not None and str(raw_manual).strip() != '':
                try:
                    val = int(raw_manual)
                    if 1 <= val <= max_montage:
                        montage = val
                    elif val > max_montage:
                        montage = max_montage
                    else:
                        montage = 1
                except (ValueError, TypeError):
                    montage = max_montage
            else:
                montage = max_montage

            piece_name = cls._resolve_piece_name(sheet_size_str, piece_size_str, machine_cuts, params)
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

            # استخراج العملة والرمز بشكل نقي وديناميكي
            final_curr_code = getattr(target_curr, 'code', 'EGP')
            final_curr_symbol = getattr(target_curr, 'symbol', '')
            if not final_curr_symbol:
                try:
                    from financial.services.exchange_rate_service import ExchangeRateService
                    func_c = ExchangeRateService.get_functional_currency()
                    final_curr_symbol = func_c.symbol if func_c else 'ج.م'
                except Exception:
                    final_curr_symbol = 'ج.م'

            # حساب الوزن الإجمالي بالكيلوجرام للطلب
            sheet_w_cm = float(w_cut * Decimal(str(machine_cuts)))
            sheet_h_cm = float(h_cut)
            paper_gsm = float(cls._to_decimal(params.get('paper_weight'), Decimal('300.0')))
            gross_p_sheets = float(paper_res.get('gross_press_sheets', 0))
            # معادلة الوزن: (الطول بالسم * العرض بالسم * الجراماج * عدد الأفرخ) / 10,000,000
            total_weight_kg = round((sheet_w_cm * sheet_h_cm * paper_gsm * gross_p_sheets) / 10000000.0, 2)
            boxes_count = logistics_res.get('boxes_count', 0)

            # سعر الصرف المستخدم مقابل العملة الوظيفية
            applied_exchange_rate = 1.0
            if target_curr:
                try:
                    from financial.services.exchange_rate_service import ExchangeRateService
                    func_curr = ExchangeRateService.get_functional_currency()
                    if func_curr and getattr(target_curr, 'code', '') != func_curr.code:
                        rate_dec = ExchangeRateService.get_rate(from_code=func_curr.code, to_code=target_curr.code, date=order_date)
                        if rate_dec:
                            applied_exchange_rate = float(rate_dec)
                except Exception:
                    pass

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
                    'max_cuts_per_sheet': max_montage,
                    'is_manual': (montage < max_montage),
                    'piece_size_name': piece_name,
                    'montage_text': f"{montage} / {piece_name}",
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
                'weight': {
                    'total_kg': total_weight_kg,
                    'boxes_count': boxes_count,
                },
                'currency': final_curr_code,
                'currency_code': final_curr_code,
                'currency_symbol': final_curr_symbol,
                'exchange_rate': applied_exchange_rate,
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
    def _resolve_cut_dimensions(
        cls, sheet_size_str: str, piece_size_str: str, params: Optional[Dict[str, Any]] = None
    ) -> Tuple[Decimal, Decimal, int]:
        """
        اشتقاق الأبعاد الدقيقة لشيت الماكينة (W_cut, H_cut) بناءً على الفرخ الخام ومقاس القطع المختار.
        """
        params = params or {}

        # 1. أبعاد صريحة ممررة مباشرة من الواجهة
        if params.get('piece_width') and params.get('piece_height'):
            try:
                w_val = Decimal(str(params['piece_width']))
                h_val = Decimal(str(params['piece_height']))
                if w_val > 0 and h_val > 0:
                    cuts = int(params.get('machine_cuts') or 4)
                    if cuts <= 0:
                        cuts = 4
                    return w_val, h_val, cuts
            except Exception:
                pass

        # 2. فحص إذا كان المعطى هو ID لموديل PieceSize
        if piece_size_str and str(piece_size_str).strip().isdigit():
            try:
                from ..models import PieceSize
                ps = PieceSize.objects.filter(id=int(piece_size_str)).first()
                if ps and ps.width and ps.height:
                    w_cut = Decimal(str(ps.width))
                    h_cut = Decimal(str(ps.height))
                    cuts = ps.pieces_per_sheet or (4 if w_cut <= 35 and h_cut <= 50 else 2)
                    return w_cut, h_cut, cuts
            except Exception:
                pass

        # 3. تحديد أبعاد الفرخ الخام القياسية بمصر
        if '66x88' in sheet_size_str or '88x66' in sheet_size_str:
            p_w, p_h = Decimal('88.0'), Decimal('66.0')
        elif '60x85' in sheet_size_str or '85x60' in sheet_size_str or '60x90' in sheet_size_str or '90x60' in sheet_size_str:
            p_w, p_h = Decimal('85.0'), Decimal('60.0')
        elif '57x86' in sheet_size_str or '86x57' in sheet_size_str:
            p_w, p_h = Decimal('86.0'), Decimal('57.0')
        else:
            p_w, p_h = Decimal('100.0'), Decimal('70.0')  # الافتراضي 70×100

        # 4. تحديد مقاس القطع ومعامل تفصيل الفرخ
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
            # الافتراضي الشائع ربع فرخ 35×50 سم (4 قطع بالفرخ)
            # ولكن إذا كانت أبعاد المطبوع المفتوح كبيرة لا تتسع لربع الفرخ، نختار هندسياً نصف الفرخ أو الفرخ الكامل
            prod_w = Decimal(str(params.get('open_size_width') or params.get('width') or 0))
            prod_h = Decimal(str(params.get('open_size_height') or params.get('height') or 0))
            qw, qh = (p_w / Decimal('2.0')), (p_h / Decimal('2.0'))
            hw, hh = p_h, (p_w / Decimal('2.0'))
            fw, fh = p_w, p_h
            if prod_w > 0 and prod_h > 0:
                fits_quarter = (prod_w <= qw and prod_h <= qh) or (prod_w <= qh and prod_h <= qw)
                if fits_quarter:
                    return qw, qh, 4
                fits_half = (prod_w <= hw and prod_h <= hh) or (prod_w <= hh and prod_h <= hw)
                if fits_half:
                    return hw, hh, 2
                return fw, fh, 1
            return qw, qh, 4

    @classmethod
    def _resolve_piece_name(
        cls, sheet_size_str: str, piece_size_str: str, machine_cuts: int, params: Dict[str, Any]
    ) -> str:
        """
        تحديد المسمى المعتمد لمقاس القطع في المطابع المصرية (مثلاً: ربع، ربع جاير، نصف، نصف جاير).
        """
        explicit_name = params.get('piece_size_name')
        if explicit_name and str(explicit_name).strip() and str(explicit_name).lower() != 'auto':
            name = str(explicit_name).strip()
            import re
            name = re.sub(r'\(.*?\)', '', name).strip()
            if name.endswith(' فرخ') and 'جاير' not in name:
                name = name[:-4].strip()
            if name == 'فرخ كامل':
                name = 'فرخ'
            if name:
                return name

        # اشتقاق المسمى من مقاس الفرخ الخام ونسبة القص للماكينة
        sheet_str = sheet_size_str.lower()
        is_taba_gayer = ('60x85' in sheet_str or '85x60' in sheet_str or 'طبع جاير' in sheet_str)
        is_gayer = ('66x88' in sheet_str or '88x66' in sheet_str or 'جاير' in sheet_str)

        if machine_cuts == 4:
            if is_taba_gayer:
                return 'ربع طبع جاير'
            elif is_gayer:
                return 'ربع جاير'
            return 'ربع'
        elif machine_cuts == 2:
            if is_taba_gayer:
                return 'نصف طبع جاير'
            elif is_gayer:
                return 'نصف جاير'
            return 'نصف'
        elif machine_cuts == 1:
            if is_taba_gayer:
                return 'فرخ طبع جاير'
            elif is_gayer:
                return 'فرخ جاير'
            return 'فرخ'
        elif machine_cuts == 8:
            return 'ثمن'

        return f'{machine_cuts} قطعات'

    @classmethod
    def _convert_currency(
        cls, amount: Decimal, from_curr=None, to_curr=None, date=None
    ) -> Decimal:
        """
        تحويل المبلغ بين أي عملتين طبقاً لمعيار IAS 21 والخدمة المركزية ExchangeRateService.
        إذا لم يتم تمرير to_curr أو from_curr يتم استخدام العملة الوظيفية للنظام.
        """
        if not amount or amount <= Decimal('0.00'):
            return Decimal('0.0000')

        try:
            from financial.services.exchange_rate_service import ExchangeRateService
            func_curr = ExchangeRateService.get_functional_currency()
            func_code = func_curr.code if func_curr else 'EGP'

            from_code = getattr(from_curr, 'code', str(from_curr)) if from_curr else func_code
            to_code = getattr(to_curr, 'code', str(to_curr)) if to_curr else func_code

            if from_code == to_code:
                return amount

            rate = ExchangeRateService.get_rate(from_code=from_code, to_code=to_code, date=date)
            if rate and rate > 0:
                return (amount * rate).quantize(Decimal('0.0001'))
        except Exception:
            pass
        return amount

    @classmethod
    def _convert_to_egp(cls, amount: Decimal, currency=None) -> Decimal:
        """دالة متوافقة مع الاستدعاءات القديمة - تحول للعملة الوظيفية للنظام"""
        return cls._convert_currency(amount, from_curr=currency)

    @classmethod
    def _get_benchmark_rate(cls, key: str, target_curr=None, date=None) -> Decimal:
        """جلب السعر الاسترشادي وتحويله لعملة التسعير المستهدفة إذا كانت أجنبية"""
        base = cls.BENCHMARK_RATES.get(key, Decimal('0.00'))
        if not target_curr:
            return base
        return cls._convert_currency(base, from_curr=None, to_curr=target_curr, date=date)

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
        """حساب شيتات الماكينة الصافية، الهادر التفاعلي ومراحل التشطيب، وأفرخ الورق الخام وتكلفتها بالجنيه المصري."""
        net_press_sheets = math.ceil(qty / montage)

        # الهادر التفاعلي: تظبيط الماكينة + أفرخ هدر التظبيط لمراحل التشطيب والسلوفان
        waste_input = params.get('waste_sheets')
        if waste_input is not None and str(waste_input).strip() != '':
            waste_sheets = cls._to_int(waste_input, 20)
        else:
            waste_sheets = 20
            # إضافة أفرخ هدر السلوفان إن وجد
            if str(params.get('lamination') or params.get('coating_type') or 'none').lower() not in ['none', '']:
                waste_sheets += 15
            # إضافة أفرخ هدر التكسير إن وجد
            if cls._to_bool(params.get('has_die_cut')) or cls._to_bool(params.get('has_die_cutting')) or cls._to_bool(params.get('die_cutting')):
                waste_sheets += 10
            # إضافة أفرخ هدر البصمة أو الكوفراج
            if cls._to_bool(params.get('has_foil')) or cls._to_bool(params.get('has_emboss')):
                waste_sheets += 10

        gross_press_sheets = net_press_sheets + waste_sheets
        parent_sheets = math.ceil(gross_press_sheets / machine_cuts)

        # قراءة سعر الفرخ الخام من خدمة المورد إن وجدت، أو السعر الاسترشادي
        paper_source = str(params.get('paper_source') or 'purchase').lower()
        if paper_source == 'customer_supplied':
            sheet_price = Decimal('0.00')
            total_paper_cost = Decimal('0.00')
        else:
            sheet_price = cls._resolve_paper_price(params, w_cut, h_cut, machine_cuts)
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
    def _resolve_paper_price(cls, params: Dict[str, Any], w_cut: Decimal, h_cut: Decimal, machine_cuts: int = 1) -> Decimal:
        """
        جلب سعر الفرخ الخام الكامل بالجنيه المصري من SupplierService المعتمد أو استخدام السعر الاسترشادي.
        يتم حساب سعر الفرخ استناداً إلى أبعاد الفرخ الخام الحقيقي للمورد لتجنب عجز التكلفة.
        """
        paper_source = str(params.get('paper_source') or 'purchase').lower()
        if paper_source == 'customer_supplied':
            return Decimal('0.00')

        paper_price_input = params.get('paper_price')
        target_curr = params.get('_target_curr')
        order_date = params.get('_order_date')

        if paper_price_input is not None and str(paper_price_input).strip() != '':
            try:
                return cls._to_decimal(paper_price_input, Decimal('0.00'))
            except Exception:
                pass

        gsm = cls._to_decimal(params.get('paper_weight'), Decimal('300.0'))

        # محاولة قراءة الخدمة من موديول الموردين إذا تم تمرير المعرف
        paper_svc_id = params.get('paper_service_id') or params.get('paper_type_id')
        if paper_svc_id:
            try:
                from supplier.models import SupplierService
                svc = SupplierService.objects.filter(id=paper_svc_id, is_active=True, supplier__is_active=True).first()
                if svc:
                    # تحديد أبعاد الفرخ الخام الحقيقي
                    if svc.paper_size:
                        raw_w = Decimal(str(svc.paper_size.width))
                        raw_h = Decimal(str(svc.paper_size.height))
                    else:
                        raw_w = w_cut * Decimal(str(machine_cuts))
                        raw_h = h_cut

                    eff_price = svc.get_effective_sheet_price(width_cm=raw_w, height_cm=raw_h, gsm=gsm)
                    eff_price = cls._convert_currency(eff_price, from_curr=svc.effective_currency, to_curr=target_curr, date=order_date)
                    if eff_price and eff_price > Decimal('0.00'):
                        return Decimal(str(eff_price))
                    elif svc.base_price > Decimal('0.00'):
                        return cls._convert_currency(Decimal(str(svc.base_price)), from_curr=svc.effective_currency, to_curr=target_curr, date=order_date)
            except Exception:
                pass

        # استدعاء المورد المفضل لخامات الورق إن وجد
        try:
            from supplier.models import SupplierService
            pref_svc = SupplierService.objects.filter(
                service_type__code='paper',
                is_active=True,
                supplier__is_active=True,
                supplier__is_preferred=True
            ).first()
            if pref_svc:
                raw_w = Decimal(str(pref_svc.paper_size.width)) if pref_svc.paper_size else (w_cut * Decimal(str(machine_cuts)))
                raw_h = Decimal(str(pref_svc.paper_size.height)) if pref_svc.paper_size else h_cut
                eff_price = pref_svc.get_effective_sheet_price(width_cm=raw_w, height_cm=raw_h, gsm=gsm)
                eff_price = cls._convert_currency(eff_price, from_curr=pref_svc.effective_currency, to_curr=target_curr, date=order_date)
                if eff_price and eff_price > Decimal('0.00'):
                    return Decimal(str(eff_price))
        except Exception:
            pass

        # السعر الاسترشادي بحسب الجراماج
        base_rate = cls._get_benchmark_rate('paper_base_rate_300g', target_curr=target_curr, date=order_date)
        return (base_rate * (gsm / Decimal('300.0'))).quantize(Decimal('0.01'))

    @classmethod
    def _calculate_printing_costs(
        cls, cover_type: str, sides_mode: str, gross_press_sheets: int, 
        w_cut: Decimal, h_cut: Decimal, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """حساب تكاليف الطباعة (أوفست مع صمام فتحة الماكينة والتراج / ديجيتال / بانر) بالعملة المحددة."""
        if cover_type == 'none':
            return {'total_cost': 0.0, 'press_pulls': 0, 'tirages': 0, 'printing_type': 'none'}

        target_curr = params.get('_target_curr')
        order_date = params.get('_order_date')

        # طباعة خامات كبيرة / لافتات (Banner/Vinyl)
        if cover_type in ['digital_banner', 'banner', 'large_format']:
            sqm_per_sheet = (w_cut * h_cut) / Decimal('10000.0')
            total_sqm = sqm_per_sheet * Decimal(str(gross_press_sheets))
            raw_banner_rate = params.get('banner_sqm_rate')
            if raw_banner_rate is not None and str(raw_banner_rate).strip() != '':
                banner_rate = cls._to_decimal(raw_banner_rate, Decimal('85.00'))
            else:
                banner_rate = cls._convert_currency(Decimal('85.00'), to_curr=target_curr, date=order_date)
            banner_cost = (total_sqm * banner_rate).quantize(Decimal('0.01'))
            return {
                'total_cost': float(banner_cost),
                'total_sqm': float(total_sqm),
                'sqm_rate': float(banner_rate),
                'press_pulls': gross_press_sheets,
                'tirages': 0,
                'printing_type': 'digital_banner'
            }

        # طباعة ديجيتال (Digital Sheet-fed)
        if cover_type == 'digital':
            is_color = cls._to_bool(params.get('is_color', True))
            raw_click = params.get('digital_sheet_price') if 'digital_sheet_price' in params else params.get('digital_click_rate')
            if raw_click is not None:
                if str(raw_click).strip() == '':
                    click_rate = Decimal('0.00')
                else:
                    click_rate = cls._to_decimal(raw_click, Decimal('0.00'))
            else:
                dig_svc = cls._resolve_press_service(params)
                if dig_svc:
                    attrs = dig_svc.attributes or {}
                    p_val = attrs.get('price_per_page_color') if is_color else (attrs.get('price_per_page_bw') or dig_svc.base_price)
                    click_rate = cls._convert_currency(Decimal(str(p_val or 0.0)), from_curr=dig_svc.effective_currency, to_curr=target_curr, date=order_date)
                elif 'cover_digital_supplier' in params or 'cover_digital_machine' in params:
                    click_rate = Decimal('0.00')
                else:
                    default_click = cls._get_benchmark_rate('digital_click_a3_color' if is_color else 'digital_click_a3_bw', target_curr=target_curr, date=order_date)
                    click_rate = default_click

            clicks_mult = 2 if sides_mode in ['work_turn', 'work_and_turn', 'work_sheet'] else 1
            total_clicks = gross_press_sheets * clicks_mult
            digital_cost = (Decimal(str(total_clicks)) * click_rate).quantize(Decimal('0.01'))
            return {
                'total_cost': float(digital_cost),
                'total_clicks': total_clicks,
                'press_pulls': total_clicks,
                'tirages': 0,
                'click_rate': float(click_rate),
                'printing_type': 'digital'
            }


        # مصاريف الألوان المخصوصة (بنتون - لغسيل حوض الحبر)
        spot_front = cls._to_int(params.get('spot_colors_front'), 0)
        spot_back = cls._to_int(params.get('spot_colors_back'), 0) if sides_mode == 'work_sheet' else 0
        spot_wash_fee = cls._get_benchmark_rate('spot_color_wash_fee', target_curr=target_curr, date=order_date)
        spot_colors_cost = Decimal(str(spot_front + spot_back)) * spot_wash_fee

        back_colors = cls._to_int(params.get('colors_back'), 4)
        has_back_print = (sides_mode == 'work_sheet' and (back_colors > 0 or spot_back > 0))
        machine_sets = 2 if has_back_print else 1

        # طباعة أوفست (Offset): احتساب السحبات والتراجات بالمعادلة الصناعية الدقيقة
        tirages_front = 0
        tirages_back = 0
        if sides_mode == 'work_sheet':
            if has_back_print:
                press_pulls = gross_press_sheets * 2
                tirages_front = max(1, math.ceil(gross_press_sheets / 1000)) if gross_press_sheets > 0 else 0
                tirages_back = max(1, math.ceil(gross_press_sheets / 1000)) if gross_press_sheets > 0 else 0
                tirages = tirages_front + tirages_back
            else:
                press_pulls = gross_press_sheets
                tirages_front = max(1, math.ceil(gross_press_sheets / 1000)) if gross_press_sheets > 0 else 0
                tirages_back = 0
                tirages = tirages_front
        elif sides_mode in ['work_turn', 'work_and_turn']:
            press_pulls = gross_press_sheets * 2
            tirages = max(1, math.ceil(press_pulls / 1000)) if gross_press_sheets > 0 else 0
        else:
            press_pulls = gross_press_sheets
            tirages = max(1, math.ceil(press_pulls / 1000)) if gross_press_sheets > 0 else 0
            tirages_front = tirages

        # فحص وجود خدمة ماكينة بمواصفات الطقم (Set Pricing)
        press_svc = cls._resolve_press_service(params)

        press_rate_input = params.get('press_rate')
        has_explicit_rate = False
        if press_rate_input is not None and str(press_rate_input).strip() != '':
            try:
                exp_r = cls._to_decimal(press_rate_input, Decimal('0.0'))
                if exp_r > Decimal('0.00'):
                    has_explicit_rate = True
            except Exception:
                pass

        is_set_pricing = False
        if press_svc and press_svc.set_price and press_svc.set_price > Decimal('0.00') and not has_explicit_rate:
            raw_cost = press_svc.calculate_cost(tirages, machine_sets=machine_sets)
            applied_press_cost = cls._convert_currency(raw_cost, from_curr=press_svc.effective_currency, to_curr=target_curr, date=order_date)
            base_press_cost = applied_press_cost
            rate_per_1000 = (applied_press_cost / Decimal(str(tirages))).quantize(Decimal('0.01')) if tirages > 0 else Decimal('0.00')
            min_floor = cls._convert_currency(Decimal(str(press_svc.minimum_charge)), from_curr=press_svc.effective_currency, to_curr=target_curr, date=order_date) if (press_svc.minimum_charge and press_svc.minimum_charge > 0) else Decimal('0.00')
            is_floor_applied = (applied_press_cost == min_floor and min_floor > 0)
            is_set_pricing = True
        else:
            rate_per_1000, min_floor = cls._resolve_press_machine_rates(params, w_cut, h_cut, tirages=tirages)
            base_press_cost = Decimal(str(tirages)) * rate_per_1000
            applied_press_cost = max(min_floor, base_press_cost)
            is_floor_applied = (base_press_cost < min_floor)

        total_offset_cost = (applied_press_cost + spot_colors_cost).quantize(Decimal('0.01'))

        return {
            'total_cost': float(total_offset_cost),
            'base_press_cost': float(base_press_cost),
            'applied_press_cost': float(applied_press_cost),
            'is_floor_applied': is_floor_applied,
            'press_pulls': press_pulls,
            'tirages': tirages,
            'tirages_front': tirages_front,
            'tirages_back': tirages_back,
            'rate_per_1000': float(rate_per_1000),
            'minimum_charge': float(min_floor),
            'spot_colors_cost': float(spot_colors_cost),
            'spot_wash_fee': float(spot_wash_fee),
            'spot_colors_count': spot_front + spot_back,
            'machine_sets': machine_sets,
            'is_set_pricing': is_set_pricing,
            'set_price': float(press_svc.set_price) if (press_svc and press_svc.set_price) else None,
            'set_included_tirages': press_svc.set_included_tirages if (press_svc and press_svc.set_included_tirages) else 1,
            'printing_type': 'offset'
        }

    @classmethod
    def _resolve_press_service(cls, params: Dict[str, Any]):
        from supplier.models import SupplierService
        press_param = str(params.get('cover_press_machine') or params.get('press_service_id') or '')
        svc_id = None
        if press_param.startswith('offset_'):
            try:
                svc_id = int(press_param.split('_')[1])
            except (IndexError, ValueError):
                pass
        elif press_param.isdigit():
            svc_id = int(press_param)

        if svc_id:
            svc = SupplierService.objects.filter(id=svc_id, is_active=True, supplier__is_active=True).first()
            if svc:
                return svc

        supp_id = params.get('cover_offset_supplier') or params.get('offset_supplier')
        if supp_id and str(supp_id).isdigit():
            return SupplierService.objects.filter(
                supplier_id=int(supp_id), service_type__code='offset_printing', is_active=True, supplier__is_active=True
            ).first()
        return None

    @classmethod
    def _resolve_press_machine_rates(
        cls, params: Dict[str, Any], w_cut: Decimal, h_cut: Decimal, tirages: int = 1
    ) -> Tuple[Decimal, Decimal]:
        target_curr = params.get('_target_curr')
        order_date = params.get('_order_date')

        # قراءة سعر التراج الصريح إذا تم تمريره من الفورم أو ماكينة المورد
        press_rate_input = params.get('press_rate')
        if press_rate_input is not None:
            if str(press_rate_input).strip() == '':
                # تم إرسال حقل الفورم فارغاً (لم يتم اختيار ماكينة مورد بعد)
                return Decimal('0.00'), Decimal('0.00')
            try:
                explicit_rate = cls._to_decimal(press_rate_input, Decimal('0.0'))
                return explicit_rate, Decimal('0.00')
            except Exception:
                return Decimal('0.00'), Decimal('0.00')

        press_svc = cls._resolve_press_service(params)
        if press_svc:
            unit_rate = press_svc.get_price_for_quantity(tirages)
            unit_rate = cls._convert_currency(unit_rate, from_curr=press_svc.effective_currency, to_curr=target_curr, date=order_date)
            rate = unit_rate if unit_rate > 0 else (press_svc.base_price or Decimal('0.00'))
            floor = cls._convert_currency(Decimal(str(press_svc.minimum_charge)), from_curr=press_svc.effective_currency, to_curr=target_curr, date=order_date) if (press_svc.minimum_charge and press_svc.minimum_charge > 0) else Decimal('0.00')
            return rate, floor

        # قراءة الحد الأدنى لفتحة الماكينة إن وجد صراحة
        explicit_floor = params.get('press_floor') or params.get('minimum_charge')
        floor = cls._to_decimal(explicit_floor, Decimal('0.00')) if explicit_floor is not None else Decimal('0.00')

        # إذا كانت حقول الفورم موجودة ولم يختر المستخدم ماكينة مورد
        if 'cover_press_machine' in params or 'cover_offset_supplier' in params:
            return Decimal('0.00'), floor

        # التسعيرة الاسترشادية فقط للاختبارات التي لا ترسل حقول الفورم
        is_full_sheet = (w_cut > Decimal('70.0') or h_cut > Decimal('70.0'))
        bm_key = 'press_rate_70x100' if is_full_sheet else 'press_rate_50x70'
        return cls._get_benchmark_rate(bm_key, target_curr=target_curr, date=order_date), floor

    @classmethod
    def _resolve_plate_service(cls, params: Dict[str, Any], press_bed_size: str = ''):
        from supplier.models import SupplierService
        from django.db.models import Q

        svc_id = params.get('ctp_service_id') or params.get('cover_ctp_service_id')
        if svc_id and str(svc_id).isdigit():
            svc = SupplierService.objects.filter(id=int(svc_id), is_active=True, supplier__is_active=True).first()
            if svc:
                return svc

        supp_id = params.get('ctp_supplier') or params.get('cover_ctp_supplier')
        if supp_id and str(supp_id).isdigit():
            bed_qs = SupplierService.objects.filter(
                supplier_id=int(supp_id), service_type__code='ctp_plates', is_active=True, supplier__is_active=True
            )
            if not bed_qs.exists():
                svc = SupplierService.objects.filter(id=int(supp_id), is_active=True, supplier__is_active=True).first()
                if svc:
                    return svc
            else:
                svc = None
                if '100' in press_bed_size:
                    svc = bed_qs.filter(Q(plate_size__code__icontains='100') | Q(plate_size__name__icontains='100') | Q(name__icontains='100')).first()
                elif '70' in press_bed_size:
                    svc = bed_qs.filter(Q(plate_size__code__icontains='70') | Q(plate_size__name__icontains='70') | Q(name__icontains='70')).first()
                elif '50' in press_bed_size or '35' in press_bed_size:
                    svc = bed_qs.filter(Q(plate_size__code__icontains='35') | Q(plate_size__name__icontains='35') | Q(name__icontains='35') | Q(name__icontains='50')).first()
                if not svc:
                    svc = bed_qs.first()
                if svc:
                    return svc

        # لا يتم تطبيق مورد افتراضي إذا لم يحدده المستخدم صراحة
        return None

    @classmethod
    def _calculate_ctp_plates(
        cls, cover_type: str, sides_mode: str, w_cut: Decimal, h_cut: Decimal, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """حساب عدد زنكات CTP وتكلفتها بالجنيه المصري مع تصفير الظهر في الطبع والقلب ودعم تسعير الطقم."""
        if cover_type != 'offset':
            return {'total_cost': 0.0, 'total_plates': 0, 'is_archived': False}

        is_archived = cls._to_bool(params.get('is_plates_archived')) or (params.get('plates_option') == 'archived')

        front_colors = cls._to_int(params.get('colors_front'), 4)
        spot_front = cls._to_int(params.get('spot_colors_front'), 0)
        back_colors = cls._to_int(params.get('colors_back'), 4)
        spot_back = cls._to_int(params.get('spot_colors_back'), 0)

        # حساب زنكات الوجه
        raw_front_plates = params.get('plate_count_front')
        if raw_front_plates is not None and str(raw_front_plates).strip() != '':
            plates_front = cls._to_int(raw_front_plates, front_colors + spot_front)
        else:
            plates_front = front_colors + spot_front

        # حساب زنكات الظهر (تتصفر تماماً في الوجه الواحد وفي الطبع والقلب)
        if sides_mode == 'work_sheet':
            raw_back_plates = params.get('plate_count_back')
            if raw_back_plates is not None and str(raw_back_plates).strip() != '':
                plates_back = cls._to_int(raw_back_plates, back_colors + spot_back)
            else:
                plates_back = back_colors + spot_back
        else:
            plates_back = 0  # توفير 50% في الطبع والقلب

        calculated_plates = plates_front + plates_back
        manual_plates = params.get('zinc_plates_count') or params.get('plates_total')
        if manual_plates is not None and str(manual_plates).strip() != '':
            try:
                m_plates = cls._to_int(manual_plates, 0)
                if m_plates > 0:
                    total_plates = m_plates
                else:
                    total_plates = calculated_plates
            except Exception:
                total_plates = calculated_plates
        else:
            total_plates = calculated_plates

        if total_plates <= 0:
            total_plates = 4

        target_curr = params.get('_target_curr')
        order_date = params.get('_order_date')
        press_bed_size = str(params.get('press_bed_size') or '')

        ctp_svc = cls._resolve_plate_service(params, press_bed_size=press_bed_size)

        explicit_plate_price = params.get('plate_price')
        has_explicit_plate_price = False
        if explicit_plate_price is not None and str(explicit_plate_price).strip() != '':
            try:
                exp_p = cls._to_decimal(explicit_plate_price, Decimal('-1.0'))
                if exp_p >= Decimal('0.00'):
                    has_explicit_plate_price = True
            except Exception:
                pass

        is_set_pricing = False
        converted_set_price = None

        if is_archived:
            total_cost = Decimal('0.00')
            effective_plate_price = Decimal('0.00')
        elif ctp_svc and ctp_svc.set_price and ctp_svc.set_price > Decimal('0.00') and not has_explicit_plate_price:
            full_sets = total_plates // 4
            remainder = total_plates % 4
            converted_set_price = cls._convert_currency(Decimal(str(ctp_svc.set_price)), from_curr=ctp_svc.effective_currency, to_curr=target_curr, date=order_date)
            if ctp_svc.base_price and ctp_svc.base_price > Decimal('0.00'):
                converted_base_price = cls._convert_currency(Decimal(str(ctp_svc.base_price)), from_curr=ctp_svc.effective_currency, to_curr=target_curr, date=order_date)
            else:
                converted_base_price = max((converted_set_price / Decimal('4.00')) * Decimal('1.25'), cls._convert_currency(Decimal('50.00'), to_curr=target_curr, date=order_date))

            cost_unit = (Decimal(str(total_plates)) * converted_base_price).quantize(Decimal('0.01'))
            cost_set_rem = (Decimal(str(full_sets)) * converted_set_price + Decimal(str(remainder)) * converted_base_price).quantize(Decimal('0.01'))
            cost_next_set = (Decimal(str(full_sets + (1 if remainder > 0 else 0))) * converted_set_price).quantize(Decimal('0.01'))

            total_cost = min(cost_unit, cost_set_rem, cost_next_set)
            effective_plate_price = (total_cost / Decimal(str(total_plates))).quantize(Decimal('0.01')) if total_plates > 0 else Decimal('0.00')
            is_set_pricing = True
        else:
            plate_price = cls._resolve_plate_price(params, w_cut, h_cut)
            total_cost = (Decimal(str(total_plates)) * plate_price).quantize(Decimal('0.01'))
            effective_plate_price = plate_price

        return {
            'total_cost': float(total_cost),
            'total_plates': total_plates,
            'plates_front': plates_front,
            'plates_back': plates_back,
            'unit_price': float(effective_plate_price),
            'set_price': float(converted_set_price) if converted_set_price else None,
            'is_set_pricing': is_set_pricing,
            'is_archived': is_archived,
            'is_work_turn_savings': (sides_mode in ['work_turn', 'work_and_turn'])
        }

    @classmethod
    def _resolve_plate_price(cls, params: Dict[str, Any], w_cut: Decimal, h_cut: Decimal) -> Decimal:
        """جلب سعر الزنكة بناءً على مواصفات المورد المختار فقط دون فرض أسعار افتراضية."""
        target_curr = params.get('_target_curr')
        order_date = params.get('_order_date')

        plate_price_input = params.get('plate_price')
        if plate_price_input is not None:
            if str(plate_price_input).strip() == '':
                return Decimal('0.00')
            try:
                return cls._to_decimal(plate_price_input, Decimal('0.00'))
            except Exception:
                return Decimal('0.00')

        press_bed_size = str(params.get('press_bed_size') or '')
        svc = cls._resolve_plate_service(params, press_bed_size=press_bed_size)
        if svc:
            if svc.base_price and svc.base_price > Decimal('0.00'):
                return cls._convert_currency(Decimal(str(svc.base_price)), from_curr=svc.effective_currency, to_curr=target_curr, date=order_date)
            elif svc.set_price and svc.set_price > Decimal('0.00'):
                calc_unit = max((svc.set_price / Decimal('4.00')) * Decimal('1.25'), Decimal('50.00'))
                return cls._convert_currency(calc_unit, from_curr=svc.effective_currency, to_curr=target_curr, date=order_date)

        # إذا كانت حقول الفورم موجودة ولم يحدد المستخدم مورد
        if 'cover_ctp_supplier' in params or 'ctp_supplier' in params:
            return Decimal('0.00')

        # التسعيرة الاسترشادية فقط للاختبارات التي لا ترسل حقول الفورم
        is_full = (w_cut > Decimal('55.0') or h_cut > Decimal('75.0'))
        bm_key = 'plate_price_70x100' if is_full else 'plate_price_50x70'
        return cls._get_benchmark_rate(bm_key, target_curr=target_curr, date=order_date)

    @classmethod
    def _calculate_finishing_costs(
        cls, params: Dict[str, Any], gross_press_sheets: int, parent_sheets: int, w_cut: Decimal, h_cut: Decimal
    ) -> Dict[str, Any]:
        """حساب خدمات ما بعد الطباعة (السلوفان، التكسير، البصمة، اليو في) بالعملة المحددة مع استدعاء أسعار الموردين المعتمدة."""
        total_finishing = Decimal('0.00')
        details = {}

        target_curr = params.get('_target_curr')
        order_date = params.get('_order_date')

        from supplier.models import SupplierService

        # 1. السلوفان (Lamination)
        lam_type = str(params.get('lamination') or params.get('lamination_type') or params.get('coating_type') or 'none').lower()
        if lam_type not in ['none', '']:
            sides = 2 if 'double' in lam_type or str(params.get('lamination_sides')) == '2' else 1
            lam_face_price = params.get('lamination_face_price')
            if lam_face_price is not None and str(lam_face_price).strip() != '':
                face_rate = cls._to_decimal(lam_face_price, Decimal('0.00'))
                lam_cost = (Decimal(str(gross_press_sheets)) * Decimal(str(sides)) * face_rate).quantize(Decimal('0.01'))
            else:
                sqm_per_sheet = (w_cut * h_cut) / Decimal('10000.0')
                total_sqm = sqm_per_sheet * Decimal(str(gross_press_sheets))

                # البحث عن خدمة المورد المعتمدة للسلوفان
                lam_svc = None
                coating_svc_id = params.get('coating_service_id')
                if coating_svc_id:
                    lam_svc = SupplierService.objects.filter(id=coating_svc_id, is_active=True, supplier__is_active=True).first()
                if not lam_svc:
                    lam_svc = SupplierService.objects.filter(
                        service_type__code='coating',
                        is_active=True,
                        supplier__is_active=True
                    ).order_by('-supplier__is_preferred', 'base_price').first()

                if lam_svc and lam_svc.base_price > 0:
                    rate = cls._convert_currency(Decimal(str(lam_svc.base_price)), from_curr=lam_svc.effective_currency, to_curr=target_curr, date=order_date)
                    floor = cls._convert_currency(Decimal(str(lam_svc.minimum_charge or '0.00')), from_curr=lam_svc.effective_currency, to_curr=target_curr, date=order_date)
                else:
                    rate = cls._get_benchmark_rate('lamination_sqm_matte' if 'matte' in lam_type else 'lamination_sqm_gloss', target_curr=target_curr, date=order_date)
                    floor = Decimal('0.00')  # إلغاء الحد الأدنى الإجباري للتطابق مع السيرفس

                lam_cost = max(floor, total_sqm * Decimal(str(sides)) * rate)
                lam_cost = lam_cost.quantize(Decimal('0.01'))
            total_finishing += lam_cost
            details['lamination'] = float(lam_cost)

        # 2. التكسير (Die-Cutting)
        has_die = cls._to_bool(params.get('has_die_cut')) or cls._to_bool(params.get('has_die_cutting')) or cls._to_bool(params.get('die_cutting')) or str(params.get('die_cutting') or '') in ['die_cut', 'kiss_cut']
        if has_die:
            finishing_tirages = max(1, math.ceil(gross_press_sheets / 1000)) if gross_press_sheets > 0 else 0
            die_override = cls._to_decimal(params.get('die_cut_override_price'), Decimal('0.00'))
            if die_override > Decimal('0.00'):
                die_total = die_override
            else:
                is_tool_archive = (str(params.get('die_tooling_mode') or '').lower() == 'archive')
                die_svc = SupplierService.objects.filter(
                    service_type__code='finishing',
                    finishing_type__name__icontains='تكسير',
                    is_active=True,
                    supplier__is_active=True
                ).order_by('-supplier__is_preferred', 'base_price').first()

                if is_tool_archive:
                    die_mould_cost = Decimal('0.00')
                elif params.get('die_tooling_cost'):
                    die_mould_cost = cls._to_decimal(params.get('die_tooling_cost'), Decimal('250.00'))
                elif die_svc:
                    die_mould_cost = cls._convert_currency(Decimal(str(die_svc.tooling_cost or '250.00')), from_curr=die_svc.effective_currency, to_curr=target_curr, date=order_date)
                else:
                    die_mould_cost = cls._convert_currency(Decimal('250.00'), to_curr=target_curr, date=order_date)

                if params.get('die_cut_tirage_price'):
                    die_pull_rate = cls._to_decimal(params.get('die_cut_tirage_price'), Decimal('80.00'))
                elif die_svc:
                    die_pull_rate = cls._convert_currency(Decimal(str(die_svc.base_price or '80.00')), from_curr=die_svc.effective_currency, to_curr=target_curr, date=order_date)
                else:
                    die_pull_rate = cls._convert_currency(Decimal('80.00'), to_curr=target_curr, date=order_date)

                die_pull_cost = Decimal(str(finishing_tirages)) * die_pull_rate
                die_total = die_mould_cost + die_pull_cost

            total_finishing += die_total
            details['die_cutting'] = float(die_total)
            details['die_cutting_tirages'] = finishing_tirages

        # 3. السبوت يو في (Spot UV)
        has_spot = cls._to_bool(params.get('has_spot_uv')) or str(params.get('finishing') or '') == 'spot_uv'
        if has_spot:
            finishing_tirages = max(1, math.ceil(gross_press_sheets / 1000)) if gross_press_sheets > 0 else 0
            spot_override = cls._to_decimal(params.get('spot_uv_override_price'), Decimal('0.00'))
            if spot_override > Decimal('0.00'):
                uv_cost = spot_override
            else:
                is_screen_archive = (str(params.get('spot_uv_screen_mode') or '').lower() == 'archive')
                screen_cost = Decimal('0.00') if is_screen_archive else cls._to_decimal(params.get('spot_uv_screen_cost'), Decimal('150.00'))
                spot_rate = cls._to_decimal(params.get('spot_uv_tirage_price'), Decimal('120.00'))
                uv_cost = (Decimal(str(finishing_tirages)) * spot_rate) + screen_cost
            total_finishing += uv_cost
            details['spot_uv'] = float(uv_cost)
            details['spot_uv_tirages'] = finishing_tirages

        # 4. البصمة الحرارية (Foil)
        has_foil_flag = cls._to_bool(params.get('has_foil')) or 'foil' in str(params.get('finishing') or '')
        if has_foil_flag:
            foil_override = cls._to_decimal(params.get('foil_override_price'), Decimal('0.00'))
            if foil_override > Decimal('0.00'):
                foil_cost = foil_override
            else:
                is_cliche_archive = (str(params.get('foil_cliche_mode') or '').lower() == 'archive')
                cliche_cost = Decimal('0.00') if is_cliche_archive else cls._to_decimal(params.get('foil_cliche_cost'), Decimal('150.00'))
                foil_tirages = max(1, math.ceil(gross_press_sheets / 1000))
                foil_cost = max(Decimal('230.00'), (Decimal(str(foil_tirages)) * Decimal('100.00')) + cliche_cost)
            total_finishing += foil_cost
            details['foil'] = float(foil_cost)

        # 5. كوفراج بارز (Embossing)
        has_emboss_flag = cls._to_bool(params.get('has_emboss')) or 'emboss' in str(params.get('finishing') or '')
        if has_emboss_flag:
            emboss_override = cls._to_decimal(params.get('emboss_override_price'), Decimal('0.00'))
            if emboss_override > Decimal('0.00'):
                emboss_cost = emboss_override
            else:
                is_emboss_archive = (str(params.get('emboss_cliche_mode') or '').lower() == 'archive')
                cliche_cost = Decimal('0.00') if is_emboss_archive else cls._to_decimal(params.get('emboss_cliche_cost'), Decimal('150.00'))
                emboss_tirages = max(1, math.ceil(gross_press_sheets / 1000))
                emboss_cost = (Decimal(str(emboss_tirages)) * Decimal('80.00')) + cliche_cost
            total_finishing += emboss_cost
            details['emboss'] = float(emboss_cost)

        # 6. خط ريجة / طي (Creasing)
        if cls._to_bool(params.get('has_creasing')):
            crease_override = cls._to_decimal(params.get('creasing_override_price'), Decimal('0.00'))
            if crease_override > Decimal('0.00'):
                crease_cost = crease_override
            else:
                crease_rate = cls._convert_currency(Decimal('25.00'), to_curr=target_curr, date=order_date)
                crease_cost = Decimal(str(math.ceil(gross_press_sheets / 1000))) * crease_rate
            total_finishing += crease_cost
            details['creasing'] = float(crease_cost)

        return {
            'total_cost': float(total_finishing),
            'details': details
        }

    @classmethod
    def _calculate_inner_pages(cls, params: Dict[str, Any], product_type: str, qty: int) -> Dict[str, Any]:
        """حساب الملازم والصفحات الداخلية للكتب والكتالوجات بالعملة المحددة."""
        if product_type not in ['book', 'catalog', 'book_catalog', 'magazine']:
            return {'total_cost': 0.0, 'pages_count': 0, 'signatures_count': 0}

        target_curr = params.get('_target_curr')
        order_date = params.get('_order_date')

        pages = cls._to_int(params.get('pages_count') or params.get('inner_pages'), 32)
        w_val = cls._to_decimal(params.get('width'), Decimal('21.0'))
        h_val = cls._to_decimal(params.get('height'), Decimal('29.7'))
        # إذا كان مقاس الصفحة A5 أو أصغر (15.5 × 22 سم أو أقل)، الفرخ يستوعب ملزمة 32 صفحة
        sig_capacity = 32 if ((w_val <= Decimal('15.5') and h_val <= Decimal('22.0')) or (h_val <= Decimal('15.5') and w_val <= Decimal('22.0'))) else 16
        signatures = math.ceil(pages / sig_capacity)

        # ورق الداخلي: كل ملزمة 16 صفحة تأخذ نصف فرخ وش وضهر
        sheets_per_book = signatures
        total_inner_sheets = sheets_per_book * qty
        inner_waste = math.ceil(total_inner_sheets * 0.05)
        gross_inner = total_inner_sheets + inner_waste

        # فحص مصدر ورق الداخلي وسعره
        inner_source = str(params.get('inner_paper_source') or params.get('paper_source') or 'purchase').lower()
        if inner_source == 'customer_supplied':
            inner_sheet_price = Decimal('0.00')
            inner_paper_cost = Decimal('0.00')
        elif params.get('inner_sheet_price') and str(params.get('inner_sheet_price')).strip() != '':
            inner_sheet_price = cls._to_decimal(params.get('inner_sheet_price'), Decimal('0.00'))
            inner_paper_cost = (Decimal(str(gross_inner)) * inner_sheet_price).quantize(Decimal('0.01'))
        elif 'inner_paper_supplier' in params or 'inner_sheet_price' in params:
            # تم تفريغ أو عدم اختيار مورد ورق الداخلي في الفورم -> صفر تكلفة وهمية
            inner_sheet_price = Decimal('0.00')
            inner_paper_cost = Decimal('0.00')
        else:
            inner_sheet_price = cls._convert_currency(Decimal('2.00'), to_curr=target_curr, date=order_date)
            inner_paper_cost = (Decimal(str(gross_inner)) * inner_sheet_price).quantize(Decimal('0.01'))

        # طباعة الداخلي: كل ملزمة تحتاج 4 زنكات وش وضهر طبع وقلب أو 8 زنكات
        inner_plates = signatures * 4
        inner_bed_size = str(params.get('inner_bed_size') or '50x70')
        inner_ctp_svc = cls._resolve_plate_service({
            'ctp_service_id': params.get('inner_ctp_service_id'),
            'ctp_supplier': params.get('inner_ctp_supplier'),
        }, press_bed_size=inner_bed_size)

        if inner_ctp_svc and inner_ctp_svc.set_price and inner_ctp_svc.set_price > Decimal('0.00') and not params.get('inner_plate_price'):
            # كل ملزمة تحتاج طقم زنكات 4 ألوان: signatures * set_price
            converted_inner_set_price = cls._convert_currency(Decimal(str(inner_ctp_svc.set_price)), from_curr=inner_ctp_svc.effective_currency, to_curr=target_curr, date=order_date)
            inner_plate_cost = Decimal(str(signatures)) * converted_inner_set_price
        else:
            raw_inner_plate = params.get('inner_plate_price')
            if raw_inner_plate is not None:
                if str(raw_inner_plate).strip() == '':
                    inner_plate_rate = Decimal('0.00')
                else:
                    inner_plate_rate = cls._to_decimal(raw_inner_plate, Decimal('0.00'))
            elif inner_ctp_svc and inner_ctp_svc.base_price:
                inner_plate_rate = cls._convert_currency(Decimal(str(inner_ctp_svc.base_price)), from_curr=inner_ctp_svc.effective_currency, to_curr=target_curr, date=order_date)
            elif 'inner_ctp_supplier' in params or 'inner_plate_price' in params:
                inner_plate_rate = Decimal('0.00')
            else:
                inner_plate_rate = cls._get_benchmark_rate('plate_price_50x70', target_curr=target_curr, date=order_date)
            inner_plate_cost = Decimal(str(inner_plates)) * inner_plate_rate

        # سحبات الداخلي: كل ملزمة تُطبع كوظيفة مستقلة على الماكينة
        inner_sides = params.get('inner_print_sides_mode') or params.get('print_sides_mode') or 'work_turn'
        sig_multiplier = 2 if inner_sides in ['work_turn', 'work_and_turn', 'work_sheet'] else 1
        sig_pulls = qty * sig_multiplier

        if inner_sides == 'work_sheet':
            sig_t_front = max(1, math.ceil(qty / 1000)) if qty > 0 else 0
            sig_t_back = max(1, math.ceil(qty / 1000)) if qty > 0 else 0
            sig_tirage = sig_t_front + sig_t_back
        else:
            sig_tirage = max(1, math.ceil(sig_pulls / 1000)) if sig_pulls > 0 else 0

        total_inner_tirages = sig_tirage * signatures
        total_inner_pulls = sig_pulls * signatures

        # ماكينة طباعة الداخلي
        inner_press_svc = cls._resolve_press_service({
            'cover_press_machine': params.get('inner_press_machine'),
            'cover_offset_supplier': params.get('inner_offset_supplier'),
        })

        if inner_press_svc and inner_press_svc.set_price and inner_press_svc.set_price > Decimal('0.00') and not params.get('inner_press_rate'):
            machine_sets_per_sig = 2 if inner_sides == 'work_sheet' else 1
            sig_cost = inner_press_svc.calculate_cost(sig_tirage, machine_sets=machine_sets_per_sig)
            sig_cost_converted = cls._convert_currency(sig_cost, from_curr=inner_press_svc.effective_currency, to_curr=target_curr, date=order_date)
            inner_press_cost = Decimal(str(signatures)) * sig_cost_converted
        else:
            raw_inner_press = params.get('inner_press_rate')
            if raw_inner_press is not None:
                if str(raw_inner_press).strip() == '':
                    inner_press_rate = Decimal('0.00')
                else:
                    inner_press_rate = cls._to_decimal(raw_inner_press, Decimal('0.00'))
            elif inner_press_svc and inner_press_svc.base_price:
                inner_press_rate = cls._convert_currency(Decimal(str(inner_press_svc.base_price)), from_curr=inner_press_svc.effective_currency, to_curr=target_curr, date=order_date)
            elif 'inner_offset_supplier' in params or 'inner_press_machine' in params:
                inner_press_rate = Decimal('0.00')
            else:
                inner_press_rate = cls._get_benchmark_rate('press_rate_50x70', target_curr=target_curr, date=order_date)
            inner_press_cost = Decimal(str(total_inner_tirages)) * inner_press_rate

        total_inner_cost = inner_paper_cost + inner_plate_cost + inner_press_cost

        return {
            'total_cost': float(total_inner_cost),
            'pages_count': pages,
            'signatures_count': signatures,
            'inner_paper_cost': float(inner_paper_cost),
            'inner_press_cost': float(inner_press_cost),
            'inner_plates_cost': float(inner_plate_cost),
            'inner_pulls': int(total_inner_pulls),
            'inner_tirages': int(total_inner_tirages),
            'sig_tirage': int(sig_tirage),
            'sig_pulls': int(sig_pulls),
        }

    @classmethod
    def _calculate_binding_cost(cls, params: Dict[str, Any], product_type: str, qty: int, signatures: int) -> Decimal:
        """حساب تكلفة خدمات التجليد والتقفيل للكتالوجات والكتب والدفاتر بالعملة المحددة."""
        binding = str(params.get('binding_type') or 'staple').lower()
        target_curr = params.get('_target_curr')
        order_date = params.get('_order_date')
        cost = Decimal('0.00')

        if product_type in ['book', 'catalog', 'book_catalog', 'magazine']:
            if binding in ['staple', 'saddle_stitch']:
                cost = max(Decimal('75.00'), Decimal(str(qty)) * Decimal('0.50'))
            elif binding == 'perfect_binding':
                cost = max(Decimal('150.00'), Decimal(str(qty)) * Decimal('1.80'))
            elif binding == 'hardcover':
                cost = max(Decimal('250.00'), (Decimal(str(qty)) * Decimal('4.50')) + Decimal('150.00'))
            elif binding == 'wire_o':
                inner_pages_c = cls._to_int(params.get('pages_count') or params.get('inner_pages'), 60)
                wire_rate = Decimal('2.50') if inner_pages_c <= 100 else Decimal('3.50')
                cost = max(Decimal('120.00'), Decimal(str(qty)) * wire_rate)
            elif binding == 'pad_glue':
                cost = max(Decimal('50.00'), Decimal(str(qty)) * Decimal('0.75'))
            elif binding == 'sewing_binding':
                sewing_rate = Decimal('0.20') * Decimal(str(signatures))
                cost = max(Decimal('200.00'), Decimal(str(qty)) * (Decimal('2.00') + sewing_rate))
        elif product_type in ['folder', 'box', 'folder_packaging']:
            cost = Decimal('350.00') + (Decimal(str(qty)) * Decimal('0.60'))

        return cls._convert_currency(cost, to_curr=target_curr, date=order_date)

    @classmethod
    def _calculate_logistics(cls, params: Dict[str, Any], qty: int) -> Dict[str, Any]:
        """حساب كراتين التعبئة وتكاليف الشحن والتوصيل بالعملة المحددة."""
        target_curr = params.get('_target_curr')
        order_date = params.get('_order_date')

        carton_cost = Decimal('0.00')
        delivery_cost = cls._to_decimal(
            params.get('extra_cost') or params.get('shipping_cost') or params.get('delivery_cost'), 
            Decimal('0.00')
        )

        capacity_per_box = cls._to_int(params.get('units_per_box') or params.get('carton_capacity'), 500)
        if capacity_per_box > 0 and cls._to_bool(params.get('has_cartons', False)):
            boxes_count = math.ceil(qty / capacity_per_box)
            carton_price = cls._convert_currency(Decimal('15.00'), to_curr=target_curr, date=order_date)
            carton_cost = Decimal(str(boxes_count)) * carton_price
        else:
            boxes_count = 0

        total_logistics = (carton_cost + delivery_cost).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
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
        binding_cost = cls._calculate_binding_cost(
            params=params,
            product_type=params.get('product_type') or params.get('order_type') or 'flyer',
            qty=qty,
            signatures=inner_res.get('signatures_count', 0)
        )
        services_cost = (
            Decimal(str(printing_res['total_cost'])) +
            Decimal(str(plates_res['total_cost'])) +
            Decimal(str(finishing_res['total_cost'])) +
            Decimal(str(inner_res.get('inner_press_cost', 0.0))) +
            Decimal(str(inner_res.get('inner_plates_cost', 0.0))) +
            Decimal(str(logistics_res['total_cost'])) +
            binding_cost
        )

        total_cost = (materials_cost + services_cost).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        raw_margin = params.get('profit_margin')
        if raw_margin is None or str(raw_margin).strip() == '':
            raw_margin = params.get('margin_percentage')
        margin_percent = cls._to_decimal(raw_margin, Decimal('30.0'))
        margin_percent = min(Decimal('500.00'), max(Decimal('0.00'), margin_percent))

        profit_amount = (total_cost * (margin_percent / Decimal('100.0'))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        raw_final = total_cost + profit_amount
        production_selling_price = Decimal(str(math.ceil(float(raw_final)))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        pure_unit_price = (production_selling_price / Decimal(str(qty))).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)

        # أتعاب التصميم والتجهيز الفني المستقلة
        design_service_type = params.get('design_service_type', 'CUSTOMER_READY')
        if design_service_type == 'CUSTOMER_READY':
            design_fee = Decimal('0.00')
        else:
            design_fee = cls._to_decimal(params.get('design_fee'), Decimal('0.00'))
            if design_fee < Decimal('0.00'):
                design_fee = Decimal('0.00')

        total_selling_price = (production_selling_price + design_fee).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        return {
            'materials_cost': float(materials_cost),
            'services_cost': float(services_cost),
            'total_production_cost': float(total_cost),
            'design_cost': float(design_fee),
            'design_fee': float(design_fee),
            'design_service_type': design_service_type,
            'profit_margin_percent': float(margin_percent),
            'profit_amount': float(profit_amount),
            'production_selling_price': float(production_selling_price),
            'total_selling_price': float(total_selling_price),
            'unit_selling_price': float(pure_unit_price),
            'pure_unit_price': float(pure_unit_price)
        }

    # -------------------------------------------------------------------------
    # دوال التحويل الصارم للأرقام بأمان تام
    # -------------------------------------------------------------------------

    @staticmethod
    def _to_decimal(val: Any, default: Decimal = Decimal('0.0')) -> Decimal:
        if isinstance(val, (list, tuple)):
            val = val[0] if val else None
        if val is None or str(val).strip() == '':
            return default
        try:
            return Decimal(str(val).strip())
        except Exception:
            return default

    @staticmethod
    def _to_int(val: Any, default: int = 0) -> int:
        if isinstance(val, (list, tuple)):
            val = val[0] if val else None
        if val is None or str(val).strip() == '':
            return default
        try:
            return int(float(str(val).strip()))
        except Exception:
            return default

    @staticmethod
    def _to_bool(val: Any) -> bool:
        if isinstance(val, (list, tuple)):
            val = val[0] if val else False
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
