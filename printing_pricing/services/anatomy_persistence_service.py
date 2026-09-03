"""
خدمة الحفظ والتحليل الذري لتشريح الشغلانة وتفكيك بنود الخامات والخدمات
Anatomy-Driven Order Persistence & Procurement Breakdown Service
"""
from decimal import Decimal
import math
from django.db import transaction
from ..models import (
    PrintingOrder, OrderMaterial, OrderService, OrderSummary,
    PriceUnit, ProductType, ProductSize, PaperSpecification, CoatingType,
    PaperSize, PieceSize
)
from .pricing_engine import PrintingCalculationEngine


class OrderAnatomyPersistenceService:
    """
    خدمة تفكيك وتوليد بنود الخامات والخدمات وملخص التكاليف بناءً على معمارية تشريح الشغلانة
    """

    @classmethod
    def persist_order_anatomy(cls, order: PrintingOrder, post_data: dict) -> OrderSummary:
        """
        قراءة بيانات الفورم وتحويلها ذرياً إلى OrderMaterial و OrderService و OrderSummary
        """
        # حماية الطلبات المعتمدة تاريخياً من التعديل أو المسح العرضي
        if order.status == 'approved':
            summary = getattr(order, 'summary', None)
            if not summary:
                summary = OrderSummary.objects.filter(order=order).first()
            return summary

        with transaction.atomic():
            qty = Decimal(str(post_data.get('quantity') or order.quantity or 1000))
            
            # حل نوع المطبوع وتصنيفه التشغيلي بمرونة وأمان
            product_type_id = post_data.get('product_type')
            product_type = None
            if product_type_id:
                try:
                    product_type = ProductType.objects.filter(pk=product_type_id).first()
                except Exception:
                    pass
            elif order.product_type:
                product_type = order.product_type
            
            if product_type:
                order.product_type = product_type
                order.order_type = product_type.base_archetype
            elif post_data.get('order_type'):
                order.order_type = post_data.get('order_type')
                matching_pt = ProductType.objects.filter(base_archetype=order.order_type, is_active=True).first()
                if matching_pt:
                    order.product_type = matching_pt

            # حل مقاس المطبوع واتجاه الطباعة
            product_size_id = post_data.get('product_size')
            if product_size_id and str(product_size_id) != 'custom':
                try:
                    product_size = ProductSize.objects.filter(pk=product_size_id).first()
                    order.product_size = product_size
                except Exception:
                    pass
            elif product_size_id == 'custom':
                order.product_size = None

            print_orient = post_data.get('print_orientation')
            if print_orient in ['portrait', 'landscape']:
                order.print_orientation = print_orient

            is_closed = post_data.get('is_closed_size') in ['true', 'on', '1', True]
            order.is_closed_size = is_closed

            open_dir = post_data.get('open_direction')
            if open_dir in ['right', 'left', 'top']:
                order.open_direction = open_dir

            w_val = Decimal(str(post_data.get('width') or post_data.get('custom_size_width') or order.width or 21))
            h_val = Decimal(str(post_data.get('height') or post_data.get('custom_size_height') or order.height or 29.7))
            order.width = w_val
            order.height = h_val

            # حل تقنيات الطباعة الهجينة والمجالات الجديدة
            cover_print_type = post_data.get('cover_printing_type') or order.cover_printing_type or 'offset'
            inner_print_type = post_data.get('inner_printing_type') or order.inner_printing_type or 'offset'
            if cover_print_type in ['offset', 'digital', 'digital_banner', 'screen', 'none']:
                order.cover_printing_type = cover_print_type
            if inner_print_type in ['offset', 'digital']:
                order.inner_printing_type = inner_print_type

            order.print_sides_mode = post_data.get('print_sides_mode') or order.print_sides_mode or 'single'
            order.digital_color_mode = post_data.get('digital_color_mode') or order.digital_color_mode or '4_0'
            
            try:
                order.spot_colors_front = int(post_data.get('spot_colors_front') or order.spot_colors_front or 0)
            except:
                order.spot_colors_front = 0

            if order.print_sides_mode == 'work_sheet':
                try:
                    order.spot_colors_back = int(post_data.get('spot_colors_back') or order.spot_colors_back or 0)
                except:
                    order.spot_colors_back = 0
            else:
                order.spot_colors_back = 0

            # حفظ حقول الداخلي والتجليد والكعب الجديدة
            order.inner_print_sides_mode = post_data.get('inner_print_sides_mode') or order.inner_print_sides_mode or 'work_sheet'
            order.inner_color_mode = post_data.get('inner_color_mode') or order.inner_color_mode or 'all_color'
            try:
                order.inner_spot_colors = int(post_data.get('inner_spot_colors') or order.inner_spot_colors or 0)
            except:
                order.inner_spot_colors = 0
            try:
                order.inner_color_pages = int(post_data.get('digital_inner_color_pages') or post_data.get('inner_color_pages') or 0)
            except:
                order.inner_color_pages = 0
            try:
                order.inner_bw_pages = int(post_data.get('digital_inner_bw_pages') or post_data.get('inner_bw_pages') or 0)
            except:
                order.inner_bw_pages = 0

            binding_val = post_data.get('binding_type') or order.binding_type or 'staple'
            if binding_val in ['staple', 'perfect_binding', 'hardcover', 'wire_o', 'pad_glue', 'sewing_binding']:
                order.binding_type = binding_val

            order.inner_paper_type = post_data.get('inner_paper_type') or order.inner_paper_type or 'couche'
            order.inner_paper_weight = str(post_data.get('inner_paper_weight') or order.inner_paper_weight or '135')

            # حقول دفاتر الفواتير NCR والجيوب
            try:
                order.ncr_sets_count = int(post_data.get('ncr_sets_count') or order.ncr_sets_count or 2)
                order.ncr_book_capacity = int(post_data.get('ncr_book_capacity') or order.ncr_book_capacity or 50)
                order.ncr_serial_start = int(post_data.get('ncr_serial_start') or order.ncr_serial_start or 1001)
                order.ncr_serial_end = order.ncr_serial_start + (order.ncr_book_capacity * int(qty)) - 1
            except:
                pass

            order.folder_pocket_type = post_data.get('folder_pocket_type') or order.folder_pocket_type or 'same_sheet'
            order.folder_card_slit = post_data.get('folder_card_slit') in ['1', 'true', 'on', True]

            order.save(update_fields=[
                'product_type', 'order_type', 'product_size', 'print_orientation',
                'is_closed_size', 'open_direction', 'width', 'height', 
                'cover_printing_type', 'inner_printing_type', 'print_sides_mode',
                'digital_color_mode', 
                'spot_colors_front', 'spot_colors_back', 
                'inner_print_sides_mode', 'inner_color_mode', 'inner_spot_colors',
                'inner_color_pages', 'inner_bw_pages', 'binding_type',
                'inner_paper_type', 'inner_paper_weight',
                'ncr_sets_count', 'ncr_book_capacity', 'ncr_serial_start', 'ncr_serial_end',
                'folder_pocket_type', 'folder_card_slit'
            ])

            order_type = order.order_type or 'flyer'
            
            # 1. تنظيف البنود السابقة للطلب لتحديثها بشكل نظيف
            order.materials.all().delete()
            order.services.all().delete()

            # 2. حسابات الورق والخامات بديناميكية تامة
            paper_weight_str = post_data.get('paper_weight') or '300'
            try:
                paper_weight = Decimal(str(paper_weight_str))
            except:
                paper_weight = Decimal('300')
                
            open_w, open_h = order.get_open_dimensions()
            # إذا كان المطبوع كتاباً أو كتالوجاً بتجليد غراء أو هاردكفر، احتساب سمك الكعب وإضافته للعرض المفتوح
            if order_type in ['book', 'catalog', 'book_catalog', 'magazine'] and order.binding_type in ['perfect_binding', 'hardcover']:
                inner_pages = Decimal(str(order.pages_count or post_data.get('pages_count') or 64))
                inner_gsm = Decimal(str(order.inner_paper_weight or post_data.get('inner_paper_weight') or 135))
                bulk = Decimal('1.1') if str(order.inner_paper_type) == 'couche' else Decimal('1.4')
                # سمك الكعب بالسم = ((عدد الصفحات / 2) * (الجراماج / 1000) * bulk) / 10
                spine_cm = ((inner_pages / Decimal('2')) * (inner_gsm / Decimal('1000')) * bulk) / Decimal('10')
                spine_cm = max(Decimal('0.3'), spine_cm.quantize(Decimal('0.01')))
                order.spine_thickness = spine_cm * Decimal('10')  # تخزينه بالـ مم في الموديل
                open_w += spine_cm  # إضافة الكعب للغلاف المفتوح
            
            # الاستعلام الديناميكي لمقاس الفرخ من جدول PaperSize (بدون أي هارد كود)
            sheet_size_str = post_data.get('sheet_size') or ''
            paper_size_obj = None
            if sheet_size_str:
                if str(sheet_size_str).isdigit():
                    paper_size_obj = PaperSize.objects.filter(pk=int(sheet_size_str), is_active=True).first()
                if not paper_size_obj:
                    paper_size_obj = PaperSize.objects.filter(name__icontains=str(sheet_size_str), is_active=True).first()

            if paper_size_obj:
                dim1, dim2 = Decimal(str(paper_size_obj.width)), Decimal(str(paper_size_obj.height))
                sheet_w, sheet_h = max(dim1, dim2), min(dim1, dim2)
            else:
                import re
                dims = [Decimal(d) for d in re.findall(r'\d+(?:\.\d+)?', str(sheet_size_str))]
                if len(dims) >= 2:
                    sheet_w, sheet_h = max(dims[0], dims[1]), min(dims[0], dims[1])
                else:
                    first_ps = PaperSize.objects.filter(is_active=True).first()
                    if first_ps:
                        dim1, dim2 = Decimal(str(first_ps.width)), Decimal(str(first_ps.height))
                        sheet_w, sheet_h = max(dim1, dim2), min(dim1, dim2)
                    else:
                        sheet_w, sheet_h = Decimal('100.0'), Decimal('70.0')

            # استدعاء محرك الحسابات الموحد (Single Source of Truth)
            calc_params = dict(post_data)
            calc_params.update({
                'quantity': qty,
                'width': float(w_val),
                'height': float(h_val),
                'is_closed_size': is_closed,
                'open_direction': post_data.get('open_direction', 'right'),
                'product_type': order_type,
                'cover_printing_type': order.cover_printing_type,
                'print_sides_mode': order.print_sides_mode,
                'sheet_size': sheet_size_str,
                'piece_size': post_data.get('piece_size') or getattr(order, 'piece_size', '50x70'),
                'waste_sheets': post_data.get('waste_sheets'),
                'paper_weight': float(paper_weight),
            })
            engine_res = PrintingCalculationEngine.calculate(calc_params)

            # احتساب المونتاج الحقيقي على شيت الماكينة
            if engine_res.get('success'):
                cuts_per_sheet = Decimal(str(engine_res['montage']['cuts_per_sheet']))
            else:
                net_sheet_w = max(Decimal('0.1'), sheet_w - Decimal('2.0'))
                net_sheet_h = max(Decimal('0.1'), sheet_h - Decimal('2.0'))
                cuts_normal = (net_sheet_w // open_w) * (net_sheet_h // open_h)
                cuts_rotated = (net_sheet_w // open_h) * (net_sheet_h // open_w)
                cuts_per_sheet = max(Decimal('1'), cuts_normal, cuts_rotated)
            
            total_materials_cost = Decimal('0.00')
            gross_sheets = Decimal('0')

            if order.cover_printing_type == 'digital_banner':
                total_sqm = ((open_w * open_h) / Decimal('10000')) * qty
                raw_mat_rate = Decimal('25.00')
                banner_mat_cost = total_sqm * raw_mat_rate
                OrderMaterial.objects.create(
                    order=order,
                    material_type='banner',
                    material_name=f"[خامات كبيرة] رول بانر / فينيل لاصق ({total_sqm.quantize(Decimal('0.01'))} م²)",
                    quantity=total_sqm.quantize(Decimal('0.01')),
                    unit=PriceUnit.SQUARE_METER,
                    unit_cost=raw_mat_rate,
                    total_cost=banner_mat_cost.quantize(Decimal('0.01'))
                )
                total_materials_cost += banner_mat_cost
            else:
                if engine_res.get('success') and 'paper' in engine_res:
                    net_sheets = Decimal(str(engine_res['paper']['net_press_sheets']))
                    if post_data.get('waste_sheets'):
                        waste_sheets = Decimal(str(post_data['waste_sheets']))
                        gross_sheets = net_sheets + waste_sheets
                        waste_rate = waste_sheets / net_sheets if net_sheets > 0 else Decimal('0.05')
                    elif post_data.get('waste_percentage'):
                        waste_rate = Decimal(str(post_data['waste_percentage'])) / Decimal('100')
                        waste_sheets = Decimal(str(int(net_sheets * waste_rate)))
                        gross_sheets = net_sheets + waste_sheets
                    elif order.cover_printing_type == 'digital':
                        waste_rate = Decimal('0.02')
                        waste_sheets = Decimal('4')
                        gross_sheets = net_sheets + waste_sheets
                    elif order.print_sides_mode in ['work_turn', 'work_and_turn']:
                        waste_rate = Decimal('0.04')
                        waste_sheets = Decimal(str(int(net_sheets * waste_rate)))
                        gross_sheets = net_sheets + waste_sheets
                    else:
                        waste_sheets = Decimal(str(engine_res['paper']['waste_sheets']))
                        gross_sheets = net_sheets + waste_sheets
                        waste_rate = waste_sheets / net_sheets if net_sheets > 0 else Decimal('0.05')
                else:
                    net_sheets = Decimal(str(int(qty / cuts_per_sheet) + (1 if qty % cuts_per_sheet > 0 else 0)))
                    waste_sheets = Decimal('20')
                    gross_sheets = net_sheets + waste_sheets
                    waste_rate = Decimal('0.05')
                
                # فحص اقتراب الرزمة المقفولة استرشادياً فقط بدون إجبار أو أزرار
                sheets_per_pack = 500
                try:
                    sheets_per_pack = int(post_data.get('sheets_per_pack') or 500)
                    if sheets_per_pack <= 0:
                        sheets_per_pack = 500
                except (ValueError, TypeError):
                    sheets_per_pack = 500

                ream_remainder = int(gross_sheets) % sheets_per_pack
                near_ream_advisory = ""
                if ream_remainder >= (sheets_per_pack - 50):
                    full_reams_needed = math.ceil(int(gross_sheets) / sheets_per_pack)
                    near_ream_advisory = f"تنبيه استرشادي: الكمية ({int(gross_sheets)} فرخ) قاربت من رزمة كاملة ({full_reams_needed * sheets_per_pack} فرخ)."

                # قراءة سعر الشروع ومصدر الورق
                paper_source = post_data.get('paper_source') or 'purchase'
                paper_price_str = post_data.get('paper_price')
                if paper_source == 'customer_supplied':
                    sheet_unit_cost = Decimal('0.00')
                elif paper_price_str:
                    try:
                        sheet_unit_cost = Decimal(str(paper_price_str))
                    except:
                        sheet_unit_cost = Decimal('3.50')
                else:
                    sheet_unit_cost = Decimal('3.50') * (paper_weight / Decimal('300'))

                cover_paper_cost = gross_sheets * sheet_unit_cost

                # بيانات المورد والمنشأ والألياف والرزم
                paper_sup_id = post_data.get('paper_supplier')
                supplier_info_dict = {
                    'origin': post_data.get('paper_origin') or 'ألماني',
                    'source': paper_source,
                    'grain_direction': post_data.get('grain_direction', 'LG'),
                    'gross_sheets': int(gross_sheets),
                    'packs': float(gross_sheets / Decimal(str(sheets_per_pack))),
                    'sheets_per_pack': sheets_per_pack,
                }
                if paper_sup_id:
                    supplier_info_dict['supplier_id'] = paper_sup_id

                # أ. تسجيل خامة ورق الغلاف / المطبوع الرئيسي
                open_desc = f" - مقاس مفتوح ({open_w}×{open_h} سم)" if is_closed else ""
                paper_name_str = post_data.get('paper_type_name') or post_data.get('paper_type') or 'كوشيه'
                if hasattr(paper_name_str, 'name'):
                    paper_name_str = paper_name_str.name
                OrderMaterial.objects.create(
                    order=order,
                    material_type='paper',
                    material_name=f"[غلاف / مطبوع رئيسي] ورق {paper_name_str} {paper_weight} جم{open_desc} (فرخ {sheet_size_str})",
                    quantity=gross_sheets,
                    unit=PriceUnit.SHEET,
                    unit_cost=sheet_unit_cost.quantize(Decimal('0.01')),
                    total_cost=cover_paper_cost.quantize(Decimal('0.01')),
                    waste_percentage=min(Decimal('99.99'), (waste_rate * Decimal('100')).quantize(Decimal('0.01'))),
                    supplier_info=supplier_info_dict
                )
                total_materials_cost += cover_paper_cost

                # حفظ وتحديث مواصفات الورق الرسمية للغلاف PaperSpecification
                PaperSpecification.objects.filter(order=order).delete()
                PaperSpecification.objects.create(
                    order=order,
                    paper_type_name=str(paper_name_str),
                    paper_size_name=sheet_size_str,
                    sheet_width=sheet_w,
                    sheet_height=sheet_h,
                    piece_size=post_data.get('piece_size') or 'custom',
                    paper_weight=int(paper_weight),
                    sheets_needed=int(gross_sheets),
                    montage_count=int(cuts_per_sheet),
                    sheet_cost=sheet_unit_cost.quantize(Decimal('0.01')),
                    total_paper_cost=cover_paper_cost.quantize(Decimal('0.01')),
                    is_active=True,
                )

            # ب. لو كان الصنف كتاب / كتالوج (تسجيل الورق الداخلي والخامات الإضافية)
            pages_count = int(post_data.get('pages_count') or order.pages_count or 32)
            inner_sides = order.inner_print_sides_mode or 'work_sheet'
            actual_sheets_per_unit = pages_count if inner_sides == 'single' else ((pages_count + 1) // 2)
            sig_capacity = 32 if (w_val <= Decimal('15.5') and h_val <= Decimal('22.0')) else 16
            total_signatures = (pages_count + sig_capacity - 1) // sig_capacity
            order.inner_signatures_count = total_signatures

            if order_type in ['catalog', 'book', 'magazine', 'book_catalog']:
                inner_gsm = Decimal(str(order.inner_paper_weight or '135'))
                inner_paper_name = "ورق طبع أبيض فاخر" if order.inner_paper_type == 'woodfree' else f"ورق كوشيه داخلي {inner_gsm} جم"
                
                # مقاس فرخ الداخلي
                inner_sheet_size_str = post_data.get('inner_sheet_size') or '66x88'
                if '70x100' in inner_sheet_size_str:
                    inner_sheet_w, inner_sheet_h = Decimal('100.0'), Decimal('70.0')
                else:
                    inner_sheet_w, inner_sheet_h = Decimal('88.0'), Decimal('66.0')

                inner_net_sheet_w = max(Decimal('0.1'), inner_sheet_w - Decimal('2.0'))
                inner_net_sheet_h = max(Decimal('0.1'), inner_sheet_h - Decimal('2.0'))

                inner_leaf_w = w_val if inner_sides == 'single' else (w_val * Decimal('2'))
                inner_leaf_h = h_val
                inner_cuts_w = max(Decimal('1'), inner_net_sheet_w // inner_leaf_w)
                inner_cuts_h = max(Decimal('1'), inner_net_sheet_h // inner_leaf_h)
                inner_cuts_per_sheet = max(Decimal('1'), inner_cuts_w * inner_cuts_h)

                sheets_needed_total = qty * Decimal(str(actual_sheets_per_unit if inner_sides == 'single' else (actual_sheets_per_unit + 1) // 2))
                net_inner_sheets = Decimal(str(int(sheets_needed_total / inner_cuts_per_sheet) + 1))
                inner_waste_rate = Decimal('0.03') if order.inner_printing_type == 'digital' else Decimal('0.08')
                inner_gross_sheets = Decimal(str(int(net_inner_sheets * (Decimal('1') + inner_waste_rate)) + 1))

                # صمام هدر تضبيط الملازم للأوفست (20 فرخ لكل ملزمة كحد أدنى)
                if order.inner_printing_type == 'offset':
                    min_make_ready = Decimal(str(total_signatures * 20))
                    if (inner_gross_sheets - net_inner_sheets) < min_make_ready:
                        inner_gross_sheets = net_inner_sheets + min_make_ready

                inner_price_str = post_data.get('inner_sheet_price')
                paper_source = post_data.get('paper_source') or 'purchase'
                if paper_source == 'customer_supplied':
                    inner_sheet_cost = Decimal('0.00')
                elif inner_price_str:
                    try:
                        inner_sheet_cost = Decimal(str(inner_price_str))
                    except:
                        inner_sheet_cost = Decimal('2.40')
                else:
                    inner_sheet_cost = (Decimal('2.10') * (inner_gsm / Decimal('80'))) if order.inner_paper_type == 'woodfree' else (Decimal('2.40') * (inner_gsm / Decimal('135')))
                    
                inner_paper_cost = inner_gross_sheets * inner_sheet_cost

                OrderMaterial.objects.create(
                    order=order,
                    material_type='paper',
                    material_name=f"[داخلي] {inner_paper_name} ({pages_count} صفحة - {total_signatures} ملازم) (فرخ {inner_sheet_size_str})",
                    quantity=inner_gross_sheets,
                    unit=PriceUnit.SHEET,
                    unit_cost=inner_sheet_cost.quantize(Decimal('0.01')),
                    total_cost=inner_paper_cost.quantize(Decimal('0.01')),
                    waste_percentage=inner_waste_rate * Decimal('100')
                )
                total_materials_cost += inner_paper_cost

                # حفظ وتحديث مواصفات الورق الداخلي PaperSpecification
                PaperSpecification.objects.create(
                    order=order,
                    paper_type_name=inner_paper_name,
                    paper_size_name=inner_sheet_size_str,
                    sheet_width=inner_sheet_w,
                    sheet_height=inner_sheet_h,
                    piece_size='custom',
                    paper_weight=int(inner_gsm),
                    sheets_needed=int(inner_gross_sheets),
                    montage_count=int(inner_cuts_per_sheet),
                    sheet_cost=inner_sheet_cost.quantize(Decimal('0.01')),
                    total_paper_cost=inner_paper_cost.quantize(Decimal('0.01')),
                    is_active=True,
                )

                # خامات كرتون الهارد كوفر والبطانة
                if order.binding_type == 'hardcover':
                    cardboard_sheets = Decimal(str(int(qty / Decimal('4')) + 1))
                    cardboard_cost = cardboard_sheets * Decimal('18.00')
                    OrderMaterial.objects.create(
                        order=order,
                        material_type='cardboard',
                        material_name=f"[تجليد هارد كوفر] كرتون رمادي مقوى 2.5 مم للشاسيه ({cardboard_sheets} فرخ 70×100)",
                        quantity=cardboard_sheets,
                        unit=PriceUnit.SHEET,
                        unit_cost=Decimal('18.00'),
                        total_cost=cardboard_cost
                    )
                    endpaper_sheets = Decimal(str(int(qty / Decimal('2')) + 1))
                    endpaper_cost = endpaper_sheets * Decimal('1.80')
                    OrderMaterial.objects.create(
                        order=order,
                        material_type='paper',
                        material_name=f"[تجليد هارد كوفر] ورق بطانة بيضاء 150 جم لتثبيت الشاسيه (8 صفحات)",
                        quantity=endpaper_sheets,
                        unit=PriceUnit.SHEET,
                        unit_cost=Decimal('1.80'),
                        total_cost=endpaper_cost
                    )
                    total_materials_cost += (cardboard_cost + endpaper_cost)

                # خامة كرتونة الظهر السفلية للبلوكات
                if order.binding_type == 'pad_glue':
                    backing_sheets = Decimal(str(int(qty / Decimal('8')) + 1))
                    backing_cost = backing_sheets * Decimal('8.00')
                    OrderMaterial.objects.create(
                        order=order,
                        material_type='cardboard',
                        material_name=f"[بلوك] كرتونة ظهر دوبلكس رمادي 350 جم ({backing_sheets} فرخ)",
                        quantity=backing_sheets,
                        unit=PriceUnit.SHEET,
                        unit_cost=Decimal('8.00'),
                        total_cost=backing_cost
                    )
                    total_materials_cost += backing_cost

            elif order_type in ['invoice', 'receipt', 'ncr']:
                # خامات ورق الكربون NCR والكرتون العازل
                ncr_sets = Decimal(str(order.ncr_sets_count or 2))
                ncr_cap = Decimal(str(order.ncr_book_capacity or 50))
                total_ncr_sets = qty * ncr_cap
                ncr_cuts = max(Decimal('1'), (Decimal('70') // w_val) * (Decimal('100') // h_val))
                ncr_reams = Decimal(str(int((total_ncr_sets * ncr_sets) / (ncr_cuts * Decimal('500'))) + 1))
                ncr_cost = ncr_reams * Decimal('450.00')

                OrderMaterial.objects.create(
                    order=order,
                    material_type='paper',
                    material_name=f"[فواتير NCR] ورق كربون ذاتي (طقم {order.ncr_sets_count} ألوان - {ncr_reams} رزمة)",
                    quantity=ncr_reams,
                    unit=PriceUnit.PIECE,
                    unit_cost=Decimal('450.00'),
                    total_cost=ncr_cost
                )
                divider_sheets = Decimal(str(int(qty / Decimal('10')) + 1))
                divider_cost = divider_sheets * Decimal('12.00')
                OrderMaterial.objects.create(
                    order=order,
                    material_type='cardboard',
                    material_name=f"[فواتير] كرتون عازل للكتابة بين الفواتير ({divider_sheets} فرخ)",
                    quantity=divider_sheets,
                    unit=PriceUnit.SHEET,
                    unit_cost=Decimal('12.00'),
                    total_cost=divider_cost
                )
                total_materials_cost += (ncr_cost + divider_cost)

            # 3. خدمات الطباعة المتخصصة للغلاف والداخلي
            total_printing_cost = Decimal('0.00')

            # --- أولاً: طباعة الغلاف / المطبوع الرئيسي ---
            if order.cover_printing_type == 'offset':
                # احتساب عدد الزنكات بدقة
                front_colors = int(post_data.get('colors_front') or 4)
                back_colors = int(post_data.get('colors_back') or 0)
                if order.print_sides_mode != 'work_sheet':
                    back_colors = 0
                
                # إمكانية التعديل اليدوي لعدد الزنكات
                calc_total_plates = front_colors + back_colors + order.spot_colors_front + order.spot_colors_back
                if calc_total_plates == 0:
                    calc_total_plates = 4
                
                try:
                    total_plates_count = int(post_data.get('zinc_plates_count') or calc_total_plates)
                except:
                    total_plates_count = calc_total_plates

                plates_option = post_data.get('plates_option') or 'new'
                is_archived = (
                    plates_option == 'archived' or 
                    post_data.get('is_plates_archived') in ['1', 'true', 'on', True]
                )

                # قراءة مقاس وسعر الزنك
                press_bed_size = post_data.get('press_bed_size') or '70x100'
                default_rate = '150.00' if press_bed_size == '70x100' else ('85.00' if press_bed_size == '50x70' else '60.00')
                plate_rate_str = post_data.get('plate_price') or default_rate
                try:
                    plate_rate = Decimal(str(plate_rate_str))
                except:
                    plate_rate = Decimal(default_rate)
                
                effective_plate_rate = Decimal('0.00') if is_archived else plate_rate
                plates_total = Decimal(str(total_plates_count)) * effective_plate_rate

                # معالجة مورد زنكات CTP
                cover_supplier_id = post_data.get('cover_ctp_supplier')
                cover_supplier = None
                cover_supp_service = None
                if cover_supplier_id:
                    try:
                        from supplier.models import Supplier, SupplierService as SuppSvcModel
                        cover_supplier = Supplier.objects.filter(id=cover_supplier_id, is_active=True).first()
                        if cover_supplier:
                            cover_supp_service = SuppSvcModel.objects.filter(
                                supplier=cover_supplier, service_type__code='ctp_plates', is_active=True
                            ).first()
                    except Exception:
                        pass

                supplier_snapshot = {
                    'supplier_id': cover_supplier.id if cover_supplier else None,
                    'supplier_name': cover_supplier.name if cover_supplier else 'زنكات داخلية / سعر معياري',
                    'bed_size': press_bed_size,
                    'plates_option': plates_option,
                    'is_archived': is_archived,
                    'plate_price': float(plate_rate),
                    'front_plates': front_colors + order.spot_colors_front,
                    'back_plates': back_colors + order.spot_colors_back,
                }

                if total_plates_count > 0:
                    status_desc = "من الأرشيف (0 ج)" if is_archived else f"جديدة ({press_bed_size})"
                    OrderService.objects.create(
                        order=order,
                        service_category='printing',
                        service_name=f"[غلاف أوفست] تجهيز زنكات CTP {status_desc} (عدد {total_plates_count} زنكة)",
                        service_description=f"مقاس الماكينة: {press_bed_size} | المصدر: {'أرشيف' if is_archived else 'جديد'} | المورد: {supplier_snapshot['supplier_name']}",
                        quantity=Decimal(str(total_plates_count)),
                        unit=PriceUnit.PIECE,
                        unit_price=effective_plate_rate,
                        total_cost=plates_total,
                        supplier_service=cover_supp_service,
                        supplier_info=supplier_snapshot
                    )
                    total_printing_cost += plates_total

                # استخراج معامل تفصيل الفرخ للماكينة (machine_cuts)
                piece_size_val = str(post_data.get('piece_size') or '')
                press_bed_val = str(post_data.get('cover_press_machine') or press_bed_size or '')
                if piece_size_val == '35x50' or '35x50' in press_bed_val:
                    machine_cuts = Decimal('4')
                elif piece_size_val == '50x70' or '50x70' in press_bed_val:
                    machine_cuts = Decimal('2')
                else:
                    machine_cuts = Decimal('1')

                # حساب السحبات والتراج (يتضاعف في الطبع والقلب أو الوش والضهر المستقل)
                pulls_multiplier = Decimal('2') if (order.print_sides_mode == 'work_turn' or (order.print_sides_mode == 'work_sheet' and (back_colors > 0 or order.spot_colors_back > 0))) else Decimal('1')
                press_pulls = gross_sheets * machine_cuts * pulls_multiplier
                press_rate_str = post_data.get('press_rate') or '45.00'
                try:
                    press_rate = Decimal(str(press_rate_str))
                except:
                    press_rate = Decimal('45.00')
                
                # جلب مطبعة الأوفست وماكينتها
                cover_offset_supp_id = post_data.get('cover_offset_supplier')
                cover_offset_supp = None
                cover_offset_svc = None
                if cover_offset_supp_id:
                    try:
                        from supplier.models import Supplier, SupplierService as SuppSvcModel
                        cover_offset_supp = Supplier.objects.filter(id=cover_offset_supp_id, is_active=True).first()
                        if cover_offset_supp:
                            cover_offset_svc = SuppSvcModel.objects.filter(
                                supplier=cover_offset_supp, service_type__code='offset_printing', is_active=True
                            ).first()
                    except Exception:
                        pass

                press_machine_name = post_data.get('cover_press_machine') or press_bed_size

                # استخدام مخرجات محرك الحسابات الموحد لضمان التطابق التام بالمليم
                if engine_res.get('success') and 'printing' in engine_res and engine_res['printing']['printing_type'] == 'offset':
                    raw_press = Decimal(str(engine_res['printing']['applied_press_cost']))
                    thousands_pulls = Decimal(str(engine_res['printing']['tirages']))
                    press_pulls = Decimal(str(engine_res['printing']['press_pulls']))
                    press_rate = Decimal(str(engine_res['printing']['rate_per_1000']))
                else:
                    min_press_floor = cover_offset_svc.minimum_charge if (cover_offset_svc and cover_offset_svc.minimum_charge) else Decimal('0.00')
                    calculated_press = thousands_pulls * press_rate
                    raw_press = max(min_press_floor, calculated_press)
                setup_diff = Decimal('0.00')

                offset_press_snapshot = {
                    'supplier_id': cover_offset_supp.id if cover_offset_supp else None,
                    'supplier_name': cover_offset_supp.name if cover_offset_supp else 'مطبعة أوفست معتمدة',
                    'machine': press_machine_name,
                    'bed_size': press_bed_size,
                    'rate_per_1000': float(press_rate),
                    'pulls_count': int(press_pulls),
                }

                OrderService.objects.create(
                    order=order,
                    service_category='printing',
                    service_name=f"[غلاف أوفست] سحبات ماكينة أوفست بالتراج ({press_pulls} سحبة - {thousands_pulls} تراج)",
                    service_description=f"المطبعة: {offset_press_snapshot['supplier_name']} | الماكينة: {press_machine_name} | سعر التراج: {press_rate} ج/تراج",
                    quantity=thousands_pulls,
                    unit=PriceUnit.THOUSAND,
                    unit_price=press_rate,
                    setup_cost=setup_diff,
                    total_cost=(raw_press + setup_diff),
                    supplier_service=cover_offset_svc,
                    supplier_info=offset_press_snapshot
                )
                total_printing_cost += (raw_press + setup_diff)

                # احتساب «صبغة أرضية» وغسيل حوض الحبر للألوان المخصوصة
                total_spot = order.spot_colors_front + order.spot_colors_back
                has_solid_dye = (post_data.get('has_solid_dye') in ['1', 'true', 'on', True]) or (total_spot > 0)
                if has_solid_dye and total_spot > 0:
                    solid_colors = total_spot
                    solid_fee = Decimal(str(solid_colors)) * Decimal('150.00')
                    OrderService.objects.create(
                        order=order,
                        service_category='printing',
                        service_name=f"[أوفست] تجهيز وغسيل حوض حبر لون مخصوص (صبغة أرضية) ({solid_colors} لون)",
                        service_description=f"تجهيز وغسيل حوض حبر للألوان المخصوصة وصبغة الأرضية بالمطبعة",
                        quantity=Decimal(str(solid_colors)),
                        unit=PriceUnit.PIECE,
                        unit_price=Decimal('150.00'),
                        total_cost=solid_fee,
                        supplier_service=cover_offset_svc
                    )
                    total_printing_cost += solid_fee

            elif order.cover_printing_type == 'digital':
                # جلب أبعاد ماكينة مورد الديجيتال ديناميكياً من قاعدة البيانات
                machine_w = Decimal('48.7')
                machine_h = Decimal('33.0')
                digi_machine_name = post_data.get('cover_digital_machine') or 'Digital Laser Press'
                
                try:
                    from ..models import DigitalSheetSize
                    from django.db.models import Q
                    d_size = DigitalSheetSize.objects.filter(Q(code=digi_machine_name) | Q(name__icontains=digi_machine_name), is_active=True).first()
                    if d_size and d_size.width_cm and d_size.height_cm:
                        machine_w = Decimal(str(d_size.width_cm))
                        machine_h = Decimal(str(d_size.height_cm))
                except Exception:
                    pass

                # احتساب المونتاج في شيت ماكينة المورد بكلا الاتجاهين (أفقي ورأسي)
                cuts_opt1 = (machine_w // open_w) * (machine_h // open_h)
                cuts_opt2 = (machine_w // open_h) * (machine_h // open_w)
                digi_cuts = max(Decimal('1'), cuts_opt1, cuts_opt2)
                
                # عدد الطبعات (الشيتات) المطلوبة + هالك ضبط الماكينة (3 أفرخ)
                req_digital_sheets = Decimal(str(int(qty / digi_cuts) + (1 if qty % digi_cuts > 0 else 0))) + Decimal('3')

                click_mode = order.digital_color_mode or '4_0'
                
                # جلب مركز الديجيتال وماكينته
                cover_digi_supp_id = post_data.get('cover_digital_supplier')
                cover_digi_supp = None
                cover_digi_svc = None
                if cover_digi_supp_id:
                    try:
                        from supplier.models import Supplier, SupplierService as SuppSvcModel
                        cover_digi_supp = Supplier.objects.filter(id=cover_digi_supp_id, is_active=True).first()
                        if cover_digi_supp:
                            cover_digi_svc = SuppSvcModel.objects.filter(
                                supplier=cover_digi_supp, service_type__code='digital_printing', is_active=True
                            ).first()
                    except Exception:
                        pass

                # قراءة سعر الطبعة من شرائح كمية المورد التنازلية أو القيمة المدخلة
                if cover_digi_svc:
                    digital_sheet_rate = cover_digi_svc.get_price_for_quantity(int(req_digital_sheets))
                else:
                    digital_sheet_rate_str = post_data.get('digital_sheet_price')
                    if digital_sheet_rate_str:
                        try:
                            digital_sheet_rate = Decimal(str(digital_sheet_rate_str))
                        except:
                            digital_sheet_rate = Decimal('2.50')
                    else:
                        rates_map = {
                            '1_0': Decimal('0.80'),
                            '1_1': Decimal('1.50'),
                            '4_0': Decimal('2.50'),
                            '4_1': Decimal('3.25'),
                            '4_4': Decimal('4.50')
                        }
                        digital_sheet_rate = rates_map.get(click_mode, Decimal('2.50'))

                digi_snapshot = {
                    'supplier_id': cover_digi_supp.id if cover_digi_supp else None,
                    'supplier_name': cover_digi_supp.name if cover_digi_supp else 'مركز ديجيتال معتمد',
                    'machine': digi_machine_name,
                    'color_mode': click_mode,
                    'machine_width': float(machine_w),
                    'machine_height': float(machine_h),
                    'prints_rate': float(digital_sheet_rate),
                    'prints_count': int(req_digital_sheets),
                }

                raw_dig = req_digital_sheets * digital_sheet_rate
                OrderService.objects.create(
                    order=order,
                    service_category='printing',
                    service_name=f"[غلاف ديجيتال] طبعات شيت ليزر ({click_mode}) - ماكينة {machine_w}×{machine_h} سم (عدد {int(req_digital_sheets)} طبعة)",
                    service_description=f"المركز: {digi_snapshot['supplier_name']} | الماكينة: {digi_machine_name} ({machine_w}×{machine_h} سم) | سعر الطبعة: {digital_sheet_rate} ج/طبعة",
                    quantity=req_digital_sheets,
                    unit=PriceUnit.SHEET,
                    unit_price=digital_sheet_rate,
                    total_cost=raw_dig,
                    supplier_service=cover_digi_svc,
                    supplier_info=digi_snapshot
                )
                total_printing_cost += raw_dig


                # مصاريف قص ربع الفرخ على المقص للديجيتال
                guillotine_fee = Decimal('30.00')
                OrderService.objects.create(
                    order=order,
                    service_category='finishing',
                    service_name="قص شيتات الديجيتال على المقص الإلكتروني",
                    quantity=Decimal('1'),
                    unit=PriceUnit.PIECE,
                    unit_price=guillotine_fee,
                    total_cost=guillotine_fee
                )
                total_printing_cost += guillotine_fee



            elif order.cover_printing_type == 'screen':
                screen_colors = Decimal(str(post_data.get('screen_colors_count') or 1))
                screen_setup = screen_colors * Decimal('150.00')
                screen_pulls_cost = qty * screen_colors * Decimal('0.75')
                
                OrderService.objects.create(
                    order=order,
                    service_category='printing',
                    service_name=f"[سلك سكرين] تجهيز شابلونات وسحب يدوي فاخر ({screen_colors} لون)",
                    quantity=qty,
                    unit=PriceUnit.PIECE,
                    unit_price=(screen_colors * Decimal('0.75')),
                    setup_cost=screen_setup
                )
                total_printing_cost += (screen_pulls_cost + screen_setup)

            # --- ثانياً: طباعة الصفحات الداخلية للمطبوعات المجلدة ---
            if order_type in ['catalog', 'book', 'magazine', 'book_catalog']:
                if order.inner_printing_type == 'offset':
                    # إعدادات زنكات الداخلي
                    inner_plates_option = post_data.get('inner_plates_option') or 'new'
                    is_inner_archived = (
                        inner_plates_option == 'archived' or 
                        post_data.get('is_inner_plates_archived') in ['1', 'true', 'on', True]
                    )
                    inner_bed_size = post_data.get('inner_press_bed_size') or '70x100'
                    default_inner_rate = '150.00' if inner_bed_size == '70x100' else ('85.00' if inner_bed_size == '50x70' else '60.00')
                    inner_plate_rate_str = post_data.get('inner_plate_price') or default_inner_rate
                    try:
                        inner_plate_rate = Decimal(str(inner_plate_rate_str))
                    except:
                        inner_plate_rate = Decimal(default_inner_rate)

                    effective_inner_plate_rate = Decimal('0.00') if is_inner_archived else inner_plate_rate

                    # جلب مورد زنكات الداخلي
                    inner_supplier_id = post_data.get('inner_ctp_supplier')
                    inner_supplier = None
                    inner_supp_service = None
                    if inner_supplier_id:
                        try:
                            from supplier.models import Supplier, SupplierService as SuppSvcModel
                            inner_supplier = Supplier.objects.filter(id=inner_supplier_id, is_active=True).first()
                            if inner_supplier:
                                inner_supp_service = SuppSvcModel.objects.filter(
                                    supplier=inner_supplier, service_type__code='ctp_plates', is_active=True
                                ).first()
                        except Exception:
                            pass

                    inner_supplier_snapshot = {
                        'supplier_id': inner_supplier.id if inner_supplier else None,
                        'supplier_name': inner_supplier.name if inner_supplier else 'زنكات داخلية / سعر معياري',
                        'bed_size': inner_bed_size,
                        'plates_option': inner_plates_option,
                        'is_archived': is_inner_archived,
                        'plate_price': float(inner_plate_rate),
                    }

                    if inner_sides == 'single':
                        single_colors = int(post_data.get('inner_colors_single') or 4)
                        single_plates_cost = Decimal(str(single_colors)) * effective_inner_plate_rate
                        single_status = "من الأرشيف (0 ج)" if is_inner_archived else f"جديدة ({inner_bed_size})"
                        OrderService.objects.create(
                            order=order,
                            service_category='printing',
                            service_name=f"[داخلي أوفست] زنكات CTP لوجه واحد {single_status} ({single_colors} زنكة)",
                            service_description=f"مقاس الماكينة: {inner_bed_size} | المصدر: {'أرشيف' if is_inner_archived else 'جديد'} | المورد: {inner_supplier_snapshot['supplier_name']}",
                            quantity=Decimal(str(single_colors)),
                            unit=PriceUnit.PIECE,
                            unit_price=effective_inner_plate_rate,
                            total_cost=single_plates_cost,
                            supplier_service=inner_supp_service,
                            supplier_info=inner_supplier_snapshot
                        )
                        inner_offset_supp_id = post_data.get('inner_offset_supplier')
                        inner_offset_supp = None
                        inner_offset_svc = None
                        if inner_offset_supp_id:
                            try:
                                from supplier.models import Supplier, SupplierService as SuppSvcModel
                                inner_offset_supp = Supplier.objects.filter(id=inner_offset_supp_id, is_active=True).first()
                                if inner_offset_supp:
                                    inner_offset_svc = SuppSvcModel.objects.filter(
                                        supplier=inner_offset_supp, service_type__code='offset_printing', is_active=True
                                    ).first()
                            except Exception:
                                pass

                        inner_press_rate = Decimal(str(post_data.get('inner_press_rate') or '45.00'))
                        inner_press_machine = post_data.get('inner_press_machine') or inner_bed_size

                        single_thousands = Decimal(str(int(inner_gross_sheets / 1000) + 1))
                        single_press_cost = max(Decimal('150.00'), single_thousands * inner_press_rate)

                        single_press_snapshot = {
                            'supplier_id': inner_offset_supp.id if inner_offset_supp else None,
                            'supplier_name': inner_offset_supp.name if inner_offset_supp else 'مطبعة أوفست معتمدة',
                            'machine': inner_press_machine,
                            'rate_per_1000': float(inner_press_rate),
                            'pulls_count': int(inner_gross_sheets),
                        }

                        OrderService.objects.create(
                            order=order,
                            service_category='printing',
                            service_name=f"[داخلي أوفست] سحب أوفست للداخلي ({inner_gross_sheets} سحبة - {single_thousands} تراج)",
                            service_description=f"المطبعة: {single_press_snapshot['supplier_name']} | الماكينة: {inner_press_machine} | سعر التراج: {inner_press_rate} ج/تراج (ألف سحبة)",
                            quantity=single_thousands,
                            unit=PriceUnit.THOUSAND,
                            unit_price=inner_press_rate,
                            total_cost=single_press_cost,
                            supplier_service=inner_offset_svc,
                            supplier_info=single_press_snapshot
                        )
                        total_printing_cost += (single_plates_cost + single_press_cost)
                    else:
                        color_sigs = total_signatures
                        bw_sigs = 0
                        if order.inner_color_mode == 'all_bw':
                            color_sigs = 0
                            bw_sigs = total_signatures
                        elif order.inner_color_mode == 'mixed':
                            try:
                                color_sigs = int(post_data.get('color_signatures_count') or total_signatures)
                                bw_sigs = int(post_data.get('bw_signatures_count') or 0)
                            except:
                                color_sigs = total_signatures
                                bw_sigs = 0

                        inner_spot = order.inner_spot_colors
                        calc_inner_plates = (color_sigs * 8) + (bw_sigs * 2) + (inner_spot * total_signatures)
                        try:
                            inner_plates = int(post_data.get('inner_plates_count_total') or calc_inner_plates)
                        except:
                            inner_plates = calc_inner_plates

                        inner_plates_cost = Decimal(str(inner_plates)) * effective_inner_plate_rate
                        
                        if inner_plates > 0:
                            inner_status = "من الأرشيف (0 ج)" if is_inner_archived else f"جديدة ({inner_bed_size})"
                            OrderService.objects.create(
                                order=order,
                                service_category='printing',
                                service_name=f"[داخلي أوفست] زنكات CTP لملازم الداخلي {inner_status} ({inner_plates} زنكة - {color_sigs} ألوان + {bw_sigs} أسود)",
                                service_description=f"مقاس الماكينة: {inner_bed_size} | المصدر: {'أرشيف' if is_inner_archived else 'جديد'} | المورد: {inner_supplier_snapshot['supplier_name']}",
                                quantity=Decimal(str(inner_plates)),
                                unit=PriceUnit.PIECE,
                                unit_price=effective_inner_plate_rate,
                                total_cost=inner_plates_cost,
                                supplier_service=inner_supp_service,
                                supplier_info=inner_supplier_snapshot
                            )
                            total_printing_cost += inner_plates_cost

                        inner_offset_supp_id = post_data.get('inner_offset_supplier')
                        inner_offset_supp = None
                        inner_offset_svc = None
                        if inner_offset_supp_id:
                            try:
                                from supplier.models import Supplier, SupplierService as SuppSvcModel
                                inner_offset_supp = Supplier.objects.filter(id=inner_offset_supp_id, is_active=True).first()
                                if inner_offset_supp:
                                    inner_offset_svc = SuppSvcModel.objects.filter(
                                        supplier=inner_offset_supp, service_type__code='offset_printing', is_active=True
                                    ).first()
                            except Exception:
                                pass

                        inner_press_rate = Decimal(str(post_data.get('inner_press_rate') or '45.00'))
                        inner_press_machine = post_data.get('inner_press_machine') or inner_bed_size

                        sig_pulls = qty * (Decimal('2') if inner_sides == 'work_turn' else Decimal('1'))
                        sig_tirage = Decimal(str(int(sig_pulls / 1000) + (1 if sig_pulls % 1000 > 0 else 0)))
                        thousands_inner = sig_tirage * Decimal(str(total_signatures))
                        inner_pulls = sig_pulls * Decimal(str(total_signatures))
                        raw_inner_press = thousands_inner * inner_press_rate
                        inner_press_setup = Decimal('0.00')

                        inner_press_snapshot = {
                            'supplier_id': inner_offset_supp.id if inner_offset_supp else None,
                            'supplier_name': inner_offset_supp.name if inner_offset_supp else 'مطبعة أوفست معتمدة',
                            'machine': inner_press_machine,
                            'rate_per_1000': float(inner_press_rate),
                            'pulls_count': int(inner_pulls),
                        }

                        OrderService.objects.create(
                            order=order,
                            service_category='printing',
                            service_name=f"[داخلي أوفست] سحبات ملازم الداخلي ({inner_pulls} سحبة - {thousands_inner} تراج لـ {total_signatures} ملازم)",
                            service_description=f"المطبعة: {inner_press_snapshot['supplier_name']} | الماكينة: {inner_press_machine} | سعر التراج: {inner_press_rate} ج/تراج ({sig_tirage} تراج لكل ملزمة)",
                            quantity=thousands_inner,
                            unit=PriceUnit.THOUSAND,
                            unit_price=inner_press_rate,
                            setup_cost=inner_press_setup,
                            total_cost=raw_inner_press,
                            supplier_service=inner_offset_svc,
                            supplier_info=inner_press_snapshot
                        )
                        total_printing_cost += raw_inner_press

                        # إضافة خدمة تجهيز وغسيل أحواض الألوان المخصوصة للداخلي
                        if order.inner_spot_colors > 0:
                            inner_spot_fee = Decimal(str(order.inner_spot_colors)) * Decimal('150.00')
                            OrderService.objects.create(
                                order=order,
                                service_category='printing',
                                service_name=f"[داخلي أوفست] تجهيز وغسيل حوض حبر لون مخصوص ({order.inner_spot_colors} لون)",
                                service_description=f"تجهيز وغسيل أحواض أحبار البانتون المخصوصة لملازم الداخلي",
                                quantity=Decimal(str(order.inner_spot_colors)),
                                unit=PriceUnit.PIECE,
                                unit_price=Decimal('150.00'),
                                total_cost=inner_spot_fee,
                            )
                            total_printing_cost += inner_spot_fee

                elif order.inner_printing_type == 'digital':
                    color_pages = int(post_data.get('digital_inner_color_pages') or order.inner_color_pages or pages_count)
                    bw_pages = int(post_data.get('digital_inner_bw_pages') or order.inner_bw_pages or 0)
                    
                    color_clicks = (Decimal(str(color_pages)) / Decimal('2')) * qty
                    bw_clicks = (Decimal(str(bw_pages)) / Decimal('2')) * qty

                    inner_digi_supp_id = post_data.get('inner_digital_supplier')
                    inner_digi_supp = None
                    inner_digi_svc = None
                    if inner_digi_supp_id:
                        try:
                            from supplier.models import Supplier, SupplierService as SuppSvcModel
                            inner_digi_supp = Supplier.objects.filter(id=inner_digi_supp_id, is_active=True).first()
                            if inner_digi_supp:
                                inner_digi_svc = SuppSvcModel.objects.filter(
                                    supplier=inner_digi_supp, service_type__code='digital_printing', is_active=True
                                ).first()
                        except Exception:
                            pass

                    inner_digi_snapshot = {
                        'supplier_id': inner_digi_supp.id if inner_digi_supp else None,
                        'supplier_name': inner_digi_supp.name if inner_digi_supp else 'مركز ديجيتال معتمد',
                        'color_pages': color_pages,
                        'bw_pages': bw_pages,
                    }
                    
                    if color_clicks > 0:
                        color_cost = color_clicks * Decimal('0.80')
                        OrderService.objects.create(
                            order=order,
                            service_category='printing',
                            service_name=f"[داخلي ديجيتال] نقرات ليزر ألوان ({color_pages} صفحة ألوان)",
                            service_description=f"المركز: {inner_digi_snapshot['supplier_name']} | صفحات الألوان: {color_pages}",
                            quantity=color_clicks,
                            unit=PriceUnit.PIECE,
                            unit_price=Decimal('0.80'),
                            total_cost=color_cost,
                            supplier_service=inner_digi_svc,
                            supplier_info=inner_digi_snapshot
                        )
                        total_printing_cost += color_cost

                    if bw_clicks > 0:
                        bw_cost = bw_clicks * Decimal('0.25')
                        OrderService.objects.create(
                            order=order,
                            service_category='printing',
                            service_name=f"[داخلي ديجيتال] نقرات ليزر أسود ({bw_pages} صفحة أسود)",
                            service_description=f"المركز: {inner_digi_snapshot['supplier_name']} | صفحات الأسود: {bw_pages}",
                            quantity=bw_clicks,
                            unit=PriceUnit.PIECE,
                            unit_price=Decimal('0.25'),
                            total_cost=bw_cost,
                            supplier_service=inner_digi_svc,
                            supplier_info=inner_digi_snapshot
                        )
                        total_printing_cost += bw_cost

            elif order_type in ['invoice', 'receipt', 'ncr']:
                ncr_plates_cost = Decimal('2') * Decimal('85.00')
                OrderService.objects.create(
                    order=order,
                    service_category='printing',
                    service_name="[فواتير] تجهيز زنكات أوفست للأصل والصور (2 زنكة)",
                    quantity=Decimal('2'),
                    unit=PriceUnit.PIECE,
                    unit_price=Decimal('85.00')
                )
                ncr_pulls_cost = max(Decimal('200.00'), qty * Decimal('0.60'))
                OrderService.objects.create(
                    order=order,
                    service_category='printing',
                    service_name=f"[فواتير] سحب أوفست لدفاتر الفواتير ({qty} دفتر)",
                    quantity=qty,
                    unit=PriceUnit.PIECE,
                    unit_price=Decimal('0.60')
                )
                total_printing_cost += (ncr_plates_cost + ncr_pulls_cost)

            # 4. خدمات التشطيب والسلوفان والتجليد والتكسير (المصفوفة الديناميكية الصناعية)
            total_finishing_cost = Decimal('0.00')
            lamination = post_data.get('coating_type') or post_data.get('lamination') or 'none'
            if lamination not in ['none', '', '0']:
                if order.cover_printing_type == 'digital_banner':
                    total_sqm = ((open_w * open_h) / Decimal('10000')) * qty
                    lam_rate = Decimal(str(post_data.get('lamination_face_price') or '15.00'))
                    raw_lam = total_sqm * lam_rate
                    OrderService.objects.create(
                        order=order,
                        service_category='coating',
                        service_name=f"سلوفان بارد بالمتر المربع للخامات الكبيرة ({total_sqm.quantize(Decimal('0.01'))} م²)",
                        quantity=total_sqm.quantize(Decimal('0.01')),
                        unit=PriceUnit.SQUARE_METER,
                        unit_price=lam_rate,
                        total_cost=raw_lam
                    )
                    total_finishing_cost += raw_lam
                else:
                    lam_sides = int(post_data.get('lamination_sides') or (2 if '2_sides' in str(lamination) else 1))
                    default_face_price = '0.50' if order.cover_printing_type == 'digital' else '0.40'
                    lam_rate = Decimal(str(post_data.get('lamination_face_price') or default_face_price))

                    # الحساب الصناعي: لا حد أدنى للسلوفان نهائياً
                    if order.cover_printing_type == 'digital':
                        raw_lam = qty * lam_rate * Decimal(str(lam_sides))
                        lam_qty = qty
                        lam_unit = PriceUnit.PIECE
                        unit_desc = "طبعة"
                    else:
                        raw_lam = gross_sheets * lam_rate * Decimal(str(lam_sides))
                        lam_qty = gross_sheets
                        lam_unit = PriceUnit.SHEET
                        unit_desc = "فرخ"

                    # ربط نوع التغطية وتنسيق الاسم العربي
                    ctype_kw = 'مط' if 'matte' in str(lamination) else ('لامع' if ('gloss' in str(lamination) or 'لميع' in str(lamination)) else str(lamination))
                    matched_ctype = CoatingType.objects.filter(name__icontains=ctype_kw, is_active=True).first()
                    disp_name = matched_ctype.name if matched_ctype else "سلوفان حراري"

                    disp_sides = "وجهين" if lam_sides == 2 else "وجه واحد"

                    OrderService.objects.create(
                        order=order,
                        service_category='coating',
                        service_name=f"{disp_name} ({disp_sides}) - {lam_rate} ج/وجه",
                        service_description=f"سلوفان بدون حد أدنى | الكمية: {lam_qty} {unit_desc} × {lam_sides} وجه × {lam_rate} ج",
                        quantity=lam_qty,
                        unit=lam_unit,
                        unit_price=lam_rate * Decimal(str(lam_sides)),
                        setup_cost=Decimal('0.00'),
                        total_cost=raw_lam
                    )
                    total_finishing_cost += raw_lam

            # حساب تراجات التشطيب والتكسير (ألف سحبة/شيت)
            tirage_base = qty if order.cover_printing_type == 'digital' else gross_sheets
            tirages_count = max(Decimal('1'), Decimal(str(int((tirage_base + 999) // 1000))))

            # 1. ورنيش موضعي سبوت UV (بالتراج + شابلونة)
            finishing = post_data.get('finishing') or 'none'
            has_spot_uv = post_data.get('has_spot_uv') in ['1', 'true', True] or finishing == 'spot_uv'
            if has_spot_uv:
                spot_override = Decimal(str(post_data.get('spot_uv_override_price') or '0.00'))
                if spot_override > Decimal('0.00'):
                    total_uv = spot_override
                    uv_rate = (spot_override / tirages_count).quantize(Decimal('0.01'))
                    screen_cost = Decimal('0.00')
                    uv_desc = "سعر مقطوع يدوي معتمد"
                else:
                    spot_rate = Decimal(str(post_data.get('spot_uv_tirage_price') or '120.00'))
                    is_screen_archive = post_data.get('spot_uv_screen_mode') == 'archive'
                    screen_cost = Decimal('0.00') if is_screen_archive else Decimal(str(post_data.get('spot_uv_screen_cost') or '150.00'))
                    total_uv = (tirages_count * spot_rate) + screen_cost
                    uv_rate = spot_rate
                    uv_desc = f"{tirages_count} تراج × {spot_rate} ج + شابلونة {'أرشيف (0 ج)' if is_screen_archive else f'{screen_cost} ج'}"

                OrderService.objects.create(
                    order=order,
                    service_category='finishing',
                    service_name="ورنيش موضعي بارز سبوت UV (بالتراج)",
                    service_description=uv_desc,
                    quantity=tirages_count,
                    unit=PriceUnit.THOUSAND,
                    unit_price=uv_rate,
                    setup_cost=screen_cost,
                    total_cost=total_uv
                )
                total_finishing_cost += total_uv

            # 2. تكسير فورمة سكاكين (بالتراج + فورمة)
            die_cutting = post_data.get('die_cutting') or 'straight_cut'
            has_die_cutting = post_data.get('has_die_cutting') in ['1', 'true', True] or 'die_cut' in str(die_cutting) or die_cutting == 'kiss_cut'
            if has_die_cutting:
                die_override = Decimal(str(post_data.get('die_cut_override_price') or '0.00'))
                if die_override > Decimal('0.00'):
                    total_die = die_override
                    die_rate = (die_override / tirages_count).quantize(Decimal('0.01'))
                    tooling_cost = Decimal('0.00')
                    die_desc = "سعر تكسير مقطوع يدوي معتمد"
                else:
                    die_rate = Decimal(str(post_data.get('die_cut_tirage_price') or '80.00'))
                    is_tool_archive = post_data.get('die_tooling_mode') == 'archive'
                    tooling_cost = Decimal('0.00') if is_tool_archive else Decimal(str(post_data.get('die_tooling_cost') or '250.00'))
                    total_die = (tirages_count * die_rate) + tooling_cost
                    die_desc = f"{tirages_count} تراج تكسير × {die_rate} ج + فورمة سكاكين {'أرشيف (0 ج)' if is_tool_archive else f'{tooling_cost} ج'}"

                OrderService.objects.create(
                    order=order,
                    service_category='finishing',
                    service_name="تكسير فورمة سكاكين بالماكينة (بالتراج)",
                    service_description=die_desc,
                    quantity=tirages_count,
                    unit=PriceUnit.THOUSAND,
                    unit_price=die_rate,
                    setup_cost=tooling_cost,
                    total_cost=total_die
                )
                total_finishing_cost += total_die

            # 3. بصمة حرارية (Hot Foil)
            has_foil = post_data.get('has_foil') in ['1', 'true', True] or 'foil' in str(finishing)
            if has_foil:
                foil_override = Decimal(str(post_data.get('foil_override_price') or '0.00'))
                foil_color_label = post_data.get('foil_color') or 'ذهبي'
                if foil_override > Decimal('0.00'):
                    total_foil = foil_override
                    foil_rate = (foil_override / tirages_count).quantize(Decimal('0.01'))
                    cliche_cost = Decimal('0.00')
                else:
                    is_cliche_archive = post_data.get('foil_cliche_mode') == 'archive'
                    cliche_cost = Decimal('0.00') if is_cliche_archive else Decimal(str(post_data.get('foil_cliche_cost') or '150.00'))
                    total_foil = max(Decimal('230.00'), (tirages_count * Decimal('100.00')) + cliche_cost)
                    foil_rate = Decimal('100.00')

                OrderService.objects.create(
                    order=order,
                    service_category='finishing',
                    service_name=f"بصمة حرارية ({foil_color_label}) [تشطيب خاص فاخر وكليشيه]",
                    service_description=f"سحب بصمة بالتراج {tirages_count} تراج + كليشيه {cliche_cost} ج",
                    quantity=tirages_count,
                    unit=PriceUnit.THOUSAND,
                    unit_price=foil_rate,
                    setup_cost=cliche_cost,
                    total_cost=total_foil
                )
                total_finishing_cost += total_foil

            # 4. كوفراج بارز (Embossing)
            has_emboss = post_data.get('has_emboss') in ['1', 'true', True] or 'emboss' in str(finishing)
            if has_emboss:
                emboss_override = Decimal(str(post_data.get('emboss_override_price') or '0.00'))
                if emboss_override > Decimal('0.00'):
                    total_emboss = emboss_override
                    emboss_rate = (emboss_override / tirages_count).quantize(Decimal('0.01'))
                    cliche_cost = Decimal('0.00')
                else:
                    is_emboss_archive = post_data.get('emboss_cliche_mode') == 'archive'
                    cliche_cost = Decimal('0.00') if is_emboss_archive else Decimal(str(post_data.get('emboss_cliche_cost') or '150.00'))
                    total_emboss = (tirages_count * Decimal('80.00')) + cliche_cost
                    emboss_rate = Decimal('80.00')

                OrderService.objects.create(
                    order=order,
                    service_category='finishing',
                    service_name="كوفراج بارز وضغط حراري (بالتراج)",
                    service_description=f"سحب كوفراج بالتراج {tirages_count} تراج + كليشيه {cliche_cost} ج",
                    quantity=tirages_count,
                    unit=PriceUnit.THOUSAND,
                    unit_price=emboss_rate,
                    setup_cost=cliche_cost,
                    total_cost=total_emboss
                )
                total_finishing_cost += total_emboss

            # 5. ريجة طي (Creasing)
            has_creasing = post_data.get('has_creasing') in ['1', 'true', True] or 'creasing' in str(die_cutting) or (is_closed and paper_weight >= Decimal('250'))
            if has_creasing:
                crease_override = Decimal(str(post_data.get('creasing_override_price') or '0.00'))
                lines = int(post_data.get('creasing_lines_count') or (2 if 'creasing_2' in str(die_cutting) else 1))
                if crease_override > Decimal('0.00'):
                    total_crease = crease_override
                else:
                    total_crease = max(Decimal('80.00'), tirages_count * Decimal('40.00') * Decimal(str(lines)))

                OrderService.objects.create(
                    order=order,
                    service_category='finishing',
                    service_name=f"ريجة وتكسير طي بالماكينة ({lines} خط طي)",
                    service_description=f"ريجة وتكسير خط طي بالماكينة ({tirages_count} تراج × {lines} خطوط)",
                    quantity=tirages_count,
                    unit=PriceUnit.THOUSAND,
                    unit_price=Decimal('40.00') * Decimal(str(lines)),
                    setup_cost=Decimal('0.00'),
                    total_cost=total_crease
                )
                total_finishing_cost += total_crease

            # خدمات التجليد المتخصصة
            if order_type in ['catalog', 'book', 'magazine', 'book_catalog']:
                binding = order.binding_type
                
                # جلب ورشة التجليد لو تم تحديدها
                binding_sup_id = post_data.get('binding_supplier')
                binding_sup = None
                binding_svc = None
                if binding_sup_id:
                    try:
                        from supplier.models import Supplier, SupplierService as SuppSvcModel
                        binding_sup = Supplier.objects.filter(id=binding_sup_id, is_active=True).first()
                        if binding_sup:
                            binding_svc = SuppSvcModel.objects.filter(supplier=binding_sup, is_active=True).first()
                    except Exception:
                        pass

                if binding == 'staple':
                    # خدمة مقفولة ومجمعة من ورشة التجليد: تقفيل دبوس (تجميع + دبوس + قص وترفيل)
                    staple_cost = max(Decimal('75.00'), qty * Decimal('0.50'))
                    OrderService.objects.create(
                        order=order,
                        service_category='packaging',
                        service_name="تقفيل دبوس مجمع (تجميع ملازم + ضرب دبوس سرج + قص وترفيل الطهارة)",
                        service_description="خدمة تجليد مجمعة شاملة التجميع والدبوس والقص النهائي على المقص الثلاثي",
                        quantity=qty,
                        unit=PriceUnit.PIECE,
                        unit_price=Decimal('0.50'),
                        total_cost=staple_cost,
                        supplier_service=binding_svc
                    )
                    total_finishing_cost += staple_cost
                elif binding == 'perfect_binding':
                    pb_cost = max(Decimal('150.00'), qty * Decimal('1.80'))
                    OrderService.objects.create(
                        order=order,
                        service_category='packaging',
                        service_name="تجليد غراء حراري كعب مربع بوليمري (PUR Perfect Binding)",
                        quantity=qty,
                        unit=PriceUnit.PIECE,
                        unit_price=Decimal('1.80'),
                        total_cost=pb_cost,
                        supplier_service=binding_svc
                    )
                    total_finishing_cost += pb_cost
                elif binding == 'hardcover':
                    hc_cost = max(Decimal('250.00'), (qty * Decimal('4.50')) + Decimal('150.00'))
                    OrderService.objects.create(
                        order=order,
                        service_category='packaging',
                        service_name="تقفيل وتكسية كرتون مقوى فاخر (Hardcover Case Making)",
                        quantity=qty,
                        unit=PriceUnit.PIECE,
                        unit_price=Decimal('4.50'),
                        setup_cost=Decimal('150.00'),
                        total_cost=hc_cost,
                        supplier_service=binding_svc
                    )
                    total_finishing_cost += hc_cost
                elif binding == 'wire_o':
                    # حساب قطر السلك اللولبي المناسب لسمك البلوك
                    inner_pages_c = int(post_data.get('pages_count') or order.pages_count or 60)
                    wire_rate = Decimal('2.50') if inner_pages_c <= 100 else Decimal('3.50')
                    wire_cost = max(Decimal('120.00'), qty * wire_rate)
                    wire_size_label = '3/8 بوصة' if inner_pages_c <= 80 else ('1/2 بوصة' if inner_pages_c <= 120 else '5/8 بوصة')
                    OrderService.objects.create(
                        order=order,
                        service_category='packaging',
                        service_name=f"تخريم وتركيب سلك لولبي دبل (Wire-O مقاس {wire_size_label})",
                        quantity=qty,
                        unit=PriceUnit.PIECE,
                        unit_price=wire_rate,
                        total_cost=wire_cost,
                        supplier_service=binding_svc
                    )
                    total_finishing_cost += wire_cost
                elif binding == 'pad_glue':
                    pad_cost = max(Decimal('50.00'), qty * Decimal('0.75'))
                    OrderService.objects.create(
                        order=order,
                        service_category='packaging',
                        service_name="تكعيب وتجميع غراء أحمر علوي مع كرتونة الظهر",
                        quantity=qty,
                        unit=PriceUnit.PIECE,
                        unit_price=Decimal('0.75'),
                        total_cost=pad_cost,
                        supplier_service=binding_svc
                    )
                    total_finishing_cost += pad_cost
                elif binding == 'sewing_binding':
                    sewing_rate = Decimal('0.20') * Decimal(str(total_signatures))
                    sewing_total = max(Decimal('200.00'), qty * (Decimal('2.00') + sewing_rate))
                    OrderService.objects.create(
                        order=order,
                        service_category='packaging',
                        service_name=f"خياطة ملازم أوتوماتيك ({total_signatures} ملازم) وتجليد فاخر",
                        quantity=qty,
                        unit=PriceUnit.PIECE,
                        unit_price=(Decimal('2.00') + sewing_rate),
                        total_cost=sewing_total,
                        supplier_service=binding_svc
                    )
                    total_finishing_cost += sewing_total

            elif order_type in ['invoice', 'receipt', 'ncr']:
                ncr_sets = Decimal(str(order.ncr_sets_count or 2))
                ncr_cap = Decimal(str(order.ncr_book_capacity or 50))
                # احتساب الترقيم: عدد أطقم الفواتير بالدفاتر = الكمية * سعة الدفتر
                ncr_sets_total = qty * ncr_cap
                total_hits = ncr_sets_total * ncr_sets
                numbering_cost = max(Decimal('100.00'), (total_hits / Decimal('1000')) * Decimal('25.00'))
                unit_num_rate = (numbering_cost / ncr_sets_total).quantize(Decimal('0.001')) if ncr_sets_total > 0 else Decimal('0.025')
                OrderService.objects.create(
                    order=order,
                    service_category='finishing',
                    service_name=f"ترقيم سيريال أوتوماتيك من {order.ncr_serial_start} إلى {order.ncr_serial_end}",
                    service_description=f"ترقيم أوتوماتيك لدفاتر الفواتير (طقم {int(ncr_sets)} صور - إجمالي ضربات السيريال: {int(total_hits)} ضربة)",
                    quantity=ncr_sets_total,
                    unit=PriceUnit.PIECE,
                    unit_price=unit_num_rate,
                    total_cost=numbering_cost
                )
                pad_binding_cost = qty * Decimal('3.00')
                OrderService.objects.create(
                    order=order,
                    service_category='packaging',
                    service_name="ريجة وتخريم وتجميع وتكعيب دفاتر الفواتير",
                    quantity=qty,
                    unit=PriceUnit.PIECE,
                    unit_price=Decimal('3.00'),
                    total_cost=pad_binding_cost
                )
                total_finishing_cost += (numbering_cost + pad_binding_cost)

            elif order_type in ['folder', 'box', 'folder_packaging']:
                folder_die = Decimal('350.00')
                folder_glue = qty * Decimal('0.60')
                OrderService.objects.create(
                    order=order,
                    service_category='finishing',
                    service_name="تكسير فورمة ولزق جيب الفولدر",
                    quantity=qty,
                    unit=PriceUnit.PIECE,
                    unit_price=Decimal('0.60'),
                    setup_cost=folder_die,
                    total_cost=(folder_die + folder_glue)
                )
                total_finishing_cost += (folder_die + folder_glue)

            # 5. المشال واللوجستيات والنقل اليدوي الصريح (Manual Logistics & Shipping)
            extra_cost_str = post_data.get('extra_cost') or post_data.get('shipping_cost') or post_data.get('logistics_cost') or post_data.get('estimated_shipping_cost')
            if extra_cost_str:
                try:
                    shipping_cost = Decimal(str(extra_cost_str)).quantize(Decimal('0.01'))
                except Exception:
                    shipping_cost = Decimal('0.00')
            else:
                shipping_cost = Decimal('0.00')

            # 6. الحساب الإجمالي وتحديث OrderSummary بالجنيه المصري (EGP) حصراً
            subtotal_cost = total_materials_cost + total_printing_cost + total_finishing_cost + shipping_cost

            profit_margin_pct = Decimal(str(post_data.get('profit_margin') or order.profit_margin or '25.00'))
            margin_factor = profit_margin_pct / Decimal('100')
            
            if margin_factor < Decimal('1'):
                raw_final = subtotal_cost / (Decimal('1') - margin_factor)
                final_sell_price = Decimal(str(math.ceil(float(raw_final)))).quantize(Decimal('0.01'))
            else:
                raw_final = subtotal_cost * Decimal('1.25')
                final_sell_price = Decimal(str(math.ceil(float(raw_final)))).quantize(Decimal('0.01'))

            # حماية السعر المتفق عليه يدوياً مع العميل (Manual Agreed Price Override)
            agreed_price_str = post_data.get('manual_agreed_price') or post_data.get('final_price')
            if agreed_price_str:
                try:
                    agreed_p = Decimal(str(agreed_price_str))
                    if agreed_p > Decimal('0.00'):
                        final_sell_price = agreed_p
                        if agreed_p > subtotal_cost:
                            profit_margin_pct = (((agreed_p - subtotal_cost) / agreed_p) * Decimal('100')).quantize(Decimal('0.01'))
                        else:
                            profit_margin_pct = Decimal('0.00')
                except:
                    pass

            net_sell_price = final_sell_price

            # تحديث حقول الطلب المباشرة بالسعر الصافي
            order.estimated_cost = subtotal_cost
            order.final_price = net_sell_price
            order.profit_margin = profit_margin_pct
            order.save(update_fields=['estimated_cost', 'final_price', 'profit_margin'])

            # إنشاء أو تحديث OrderSummary
            summary, _ = OrderSummary.objects.get_or_create(order=order)
            summary.material_cost = total_materials_cost.quantize(Decimal('0.01'))
            summary.printing_cost = total_printing_cost.quantize(Decimal('0.01'))
            summary.finishing_cost = total_finishing_cost.quantize(Decimal('0.01'))
            summary.other_costs = shipping_cost.quantize(Decimal('0.01'))
            summary.total_cost = subtotal_cost.quantize(Decimal('0.01'))
            summary.subtotal = net_sell_price.quantize(Decimal('0.01'))
            summary.tax_amount = Decimal('0.00')  # التسعير الفني صافي بدون ضريبة
            summary.profit_margin_percentage = profit_margin_pct
            summary.final_price = net_sell_price.quantize(Decimal('0.01'))
            summary.save()

            return summary

