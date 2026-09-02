"""
خدمة الحفظ والتحليل الذري لتشريح الشغلانة وتفكيك بنود الخامات والخدمات
Anatomy-Driven Order Persistence & Procurement Breakdown Service
"""
from decimal import Decimal
from django.db import transaction
from ..models import (
    PrintingOrder, OrderMaterial, OrderService, OrderSummary,
    PriceUnit, ProductType, ProductSize
)


class OrderAnatomyPersistenceService:
    """
    خدمة تفكيك وتوليد بنود الخامات والخدمات وملخص التكاليف بناءً على معمارية تشريح الشغلانة
    """

    @classmethod
    def persist_order_anatomy(cls, order: PrintingOrder, post_data: dict) -> OrderSummary:
        """
        قراءة بيانات الفورم وتحويلها ذرياً إلى OrderMaterial و OrderService و OrderSummary
        """
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
                order.colors_front = int(post_data.get('colors_front') if post_data.get('colors_front') is not None else (order.colors_front if order.colors_front is not None else 4))
            except:
                order.colors_front = 4

            try:
                order.spot_colors_front = int(post_data.get('spot_colors_front') or order.spot_colors_front or 0)
            except:
                order.spot_colors_front = 0

            if order.print_sides_mode == 'work_sheet':
                try:
                    order.colors_back = int(post_data.get('colors_back') if post_data.get('colors_back') is not None else (order.colors_back or 0))
                except:
                    order.colors_back = 0
                try:
                    order.spot_colors_back = int(post_data.get('spot_colors_back') or order.spot_colors_back or 0)
                except:
                    order.spot_colors_back = 0
            else:
                order.colors_back = 0
                order.spot_colors_back = 0

            try:
                order.banner_sqm_price = Decimal(str(post_data.get('banner_sqm_price') or order.banner_sqm_price or '50.00'))
            except:
                order.banner_sqm_price = Decimal('50.00')
            order.has_white_ink = bool(post_data.get('has_white_ink'))

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
                'colors_front', 'colors_back', 'digital_color_mode', 
                'spot_colors_front', 'spot_colors_back', 
                'banner_sqm_price', 'has_white_ink',
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

            # 2. حسابات الورق والخامات
            paper_weight_str = post_data.get('paper_weight') or '300'
            try:
                paper_weight = Decimal(str(paper_weight_str))
            except:
                paper_weight = Decimal('300')
                
            open_w, open_h = order.get_open_dimensions()
            
            # احتساب تقطيع فرخ الغلاف
            net_sheet_w = Decimal('100.0') - Decimal('1.5')
            net_sheet_h = Decimal('70.0') - Decimal('1.5')
            cuts_w = max(Decimal('1'), net_sheet_w // open_w)
            cuts_h = max(Decimal('1'), net_sheet_h // open_h)
            cuts_per_sheet = max(Decimal('1'), cuts_w * cuts_h)
            
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
                net_sheets = Decimal(str(int(qty / cuts_per_sheet) + (1 if qty % cuts_per_sheet > 0 else 0)))
                
                if order.cover_printing_type == 'digital':
                    waste_rate = Decimal('0.02')
                elif order.print_sides_mode == 'work_turn':
                    waste_rate = Decimal('0.04')
                else:
                    waste_rate = Decimal('0.05') if qty > 2000 else Decimal('0.08')
                    
                gross_sheets = Decimal(str(int(net_sheets * (Decimal('1') + waste_rate)) + 1))
                
                sheet_unit_cost = Decimal('3.50') * (paper_weight / Decimal('300'))
                cover_paper_cost = gross_sheets * sheet_unit_cost

                # أ. تسجيل خامة ورق الغلاف / المطبوع الرئيسي
                open_desc = f" - مقاس مفتوح ({open_w}×{open_h} سم)" if is_closed else ""
                OrderMaterial.objects.create(
                    order=order,
                    material_type='paper',
                    material_name=f"[غلاف / مطبوع رئيسي] ورق {order.paper_type or 'كوشيه'} {paper_weight} جم{open_desc} (فرخ 70×100)",
                    quantity=gross_sheets,
                    unit=PriceUnit.SHEET,
                    unit_cost=sheet_unit_cost.quantize(Decimal('0.01')),
                    total_cost=cover_paper_cost.quantize(Decimal('0.01')),
                    waste_percentage=waste_rate * Decimal('100')
                )
                total_materials_cost += cover_paper_cost

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
                
                inner_leaf_w = w_val if inner_sides == 'single' else (w_val * Decimal('2'))
                inner_leaf_h = h_val
                inner_cuts_w = max(Decimal('1'), net_sheet_w // inner_leaf_w)
                inner_cuts_h = max(Decimal('1'), net_sheet_h // inner_leaf_h)
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

                inner_sheet_cost = (Decimal('2.10') * (inner_gsm / Decimal('80'))) if order.inner_paper_type == 'woodfree' else (Decimal('2.40') * (inner_gsm / Decimal('135')))
                inner_paper_cost = inner_gross_sheets * inner_sheet_cost

                OrderMaterial.objects.create(
                    order=order,
                    material_type='paper',
                    material_name=f"[داخلي] {inner_paper_name} ({pages_count} صفحة - {total_signatures} ملازم)",
                    quantity=inner_gross_sheets,
                    unit=PriceUnit.SHEET,
                    unit_cost=inner_sheet_cost.quantize(Decimal('0.01')),
                    total_cost=inner_paper_cost.quantize(Decimal('0.01')),
                    waste_percentage=inner_waste_rate * Decimal('100')
                )
                total_materials_cost += inner_paper_cost

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
                front_colors = int(post_data.get('colors_front') or order.colors_front or 4)
                back_colors = int(post_data.get('colors_back') or order.colors_back or 0)
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

                # حساب السحبات والتراج (يتضاعف في الطبع والقلب أو الوش والضهر المستقل)
                pulls_multiplier = Decimal('2') if (order.print_sides_mode == 'work_turn' or (order.print_sides_mode == 'work_sheet' and (back_colors > 0 or order.spot_colors_back > 0))) else Decimal('1')
                press_pulls = gross_sheets * pulls_multiplier
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
                min_press_floor = Decimal('400.00') if (order.print_sides_mode == 'work_sheet' and (back_colors > 0 or order.spot_colors_back > 0)) else Decimal('200.00')
                thousands_pulls = Decimal(str(int(press_pulls / 1000) + (1 if press_pulls % 1000 > 0 else 0)))
                raw_press = thousands_pulls * press_rate
                setup_diff = max(Decimal('0.00'), min_press_floor - raw_press)

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
                    service_description=f"المطبعة: {offset_press_snapshot['supplier_name']} | الماكينة: {press_machine_name} | سعر التراج: {press_rate} ج/تراج (ألف سحبة)",
                    quantity=thousands_pulls,
                    unit=PriceUnit.THOUSAND,
                    unit_price=press_rate,
                    setup_cost=setup_diff,
                    total_cost=(raw_press + setup_diff),
                    supplier_service=cover_offset_svc,
                    supplier_info=offset_press_snapshot
                )
                total_printing_cost += (raw_press + setup_diff)

                # تكلفة غسيل حوض الحبر وخام اللون المخصوص
                total_spot = order.spot_colors_front + order.spot_colors_back
                if total_spot > 0:
                    spot_fee = Decimal(str(total_spot)) * Decimal('150.00')
                    OrderService.objects.create(
                        order=order,
                        service_category='printing',
                        service_name=f"[أوفست] تجهيز وغسيل حوض حبر لون مخصوص ({total_spot} لون)",
                        quantity=Decimal(str(total_spot)),
                        unit=PriceUnit.PIECE,
                        unit_price=Decimal('150.00'),
                        total_cost=spot_fee
                    )
                    total_printing_cost += spot_fee

            elif order.cover_printing_type == 'digital':
                # مونتاج شيتات الديجيتال A3+
                digi_cuts_w = max(Decimal('1'), Decimal('48.7') // open_w)
                digi_cuts_h = max(Decimal('1'), Decimal('33.0') // open_h)
                digi_cuts = max(Decimal('1'), digi_cuts_w * digi_cuts_h)
                req_digital_sheets = Decimal(str(int(qty / digi_cuts) + (1 if qty % digi_cuts > 0 else 0)))

                click_mode = order.digital_color_mode or '4_0'
                digital_sheet_rate_str = post_data.get('digital_sheet_price')
                if digital_sheet_rate_str:
                    try:
                        digital_sheet_rate = Decimal(str(digital_sheet_rate_str))
                    except:
                        digital_sheet_rate = Decimal('2.50')
                else:
                    if click_mode == '1_0':
                        digital_sheet_rate = Decimal('0.80')
                    elif click_mode == '4_4':
                        digital_sheet_rate = Decimal('4.50')
                    elif click_mode == '4_1':
                        digital_sheet_rate = Decimal('3.25')
                    elif click_mode == '1_1':
                        digital_sheet_rate = Decimal('1.50')
                    else:
                        digital_sheet_rate = Decimal('2.50')
                
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

                digi_machine_name = post_data.get('cover_digital_machine') or 'Digital Laser Press'
                digi_snapshot = {
                    'supplier_id': cover_digi_supp.id if cover_digi_supp else None,
                    'supplier_name': cover_digi_supp.name if cover_digi_supp else 'مركز ديجيتال معتمد',
                    'machine': digi_machine_name,
                    'color_mode': click_mode,
                    'click_rate': float(digital_sheet_rate),
                    'sheets_count': int(req_digital_sheets),
                }

                raw_dig = req_digital_sheets * digital_sheet_rate
                OrderService.objects.create(
                    order=order,
                    service_category='printing',
                    service_name=f"[غلاف ديجيتال] طباعة ليزر شيتات A3+ ({req_digital_sheets} شيت بمونتاج {digi_cuts} قطع/شيت)",
                    service_description=f"المركز: {digi_snapshot['supplier_name']} | الماكينة: {digi_machine_name} | النمط: {click_mode}",
                    quantity=req_digital_sheets,
                    unit=PriceUnit.PIECE,
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

            elif order.cover_printing_type == 'digital_banner':
                total_sqm = ((open_w * open_h) / Decimal('10000')) * qty
                effective_rate = order.banner_sqm_price + (Decimal('25.00') if order.has_white_ink else Decimal('0.00'))
                banner_cost = max(Decimal('50.00'), total_sqm * effective_rate)
                white_desc = " + طبقة حبر أبيض" if order.has_white_ink else ""
                
                OrderService.objects.create(
                    order=order,
                    service_category='printing',
                    service_name=f"[خامات كبيرة] طباعة عريضة رول بالمتر المربع ({total_sqm.quantize(Decimal('0.01'))} م²{white_desc})",
                    quantity=total_sqm.quantize(Decimal('0.01')),
                    unit=PriceUnit.SQUARE_METER,
                    unit_price=effective_rate,
                    total_cost=banner_cost
                )
                total_printing_cost += banner_cost

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

                        inner_pulls = qty * Decimal(str(total_signatures)) * (Decimal('2') if inner_sides == 'work_turn' else Decimal('1'))
                        thousands_inner = Decimal(str(int(inner_pulls / 1000) + (1 if inner_pulls % 1000 > 0 else 0)))
                        raw_inner_press = thousands_inner * inner_press_rate
                        inner_press_setup = max(Decimal('0.00'), Decimal('250.00') - raw_inner_press)

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
                            service_name=f"[داخلي أوفست] سحبات ملازم الداخلي ({inner_pulls} سحبة - {thousands_inner} تراج)",
                            service_description=f"المطبعة: {inner_press_snapshot['supplier_name']} | الماكينة: {inner_press_machine} | سعر التراج: {inner_press_rate} ج/تراج (ألف سحبة)",
                            quantity=thousands_inner,
                            unit=PriceUnit.THOUSAND,
                            unit_price=inner_press_rate,
                            setup_cost=inner_press_setup,
                            total_cost=(raw_inner_press + inner_press_setup),
                            supplier_service=inner_offset_svc,
                            supplier_info=inner_press_snapshot
                        )
                        total_printing_cost += (raw_inner_press + inner_press_setup)

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

            # 4. خدمات التشطيب والسلوفان والتجليد والتكسير
            total_finishing_cost = Decimal('0.00')
            lamination = post_data.get('coating_type') or post_data.get('lamination') or 'matte_2_sides'
            if lamination not in ['none', '', '0']:
                if order.cover_printing_type == 'digital_banner':
                    total_sqm = ((open_w * open_h) / Decimal('10000')) * qty
                    lam_rate = Decimal('15.00')
                    raw_lam = max(Decimal('30.00'), total_sqm * lam_rate)
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
                    lam_rate = Decimal('0.90') if '2_sides' in str(lamination) else Decimal('0.50')
                    min_lam_floor = Decimal('150.00')
                    raw_lam = gross_sheets * lam_rate
                    lam_setup = max(Decimal('0.00'), min_lam_floor - raw_lam)

                    OrderService.objects.create(
                        order=order,
                        service_category='coating',
                        service_name=f"سلوفان حراري مط/لامع ({lamination})",
                        quantity=gross_sheets,
                        unit=PriceUnit.PIECE,
                        unit_price=lam_rate,
                        setup_cost=lam_setup
                    )
                    total_finishing_cost += (raw_lam + lam_setup)

            # تشطيبات فاخرة وكليشيهات البصمة والكوفراج
            finishing = post_data.get('finishing') or 'none'
            if finishing not in ['none', '']:
                die_setup = Decimal('150.00') if ('foil' in finishing or 'emboss' in finishing) else Decimal('0.00')
                raw_uv = qty * Decimal('0.40')
                uv_setup = die_setup + max(Decimal('0.00'), Decimal('200.00') - raw_uv)

                OrderService.objects.create(
                    order=order,
                    service_category='finishing',
                    service_name=f"تشطيب خاص فاخر وكليشيه ({finishing})",
                    quantity=qty,
                    unit=PriceUnit.PIECE,
                    unit_price=Decimal('0.40'),
                    setup_cost=uv_setup
                )
                total_finishing_cost += (raw_uv + uv_setup)

            # ريجة للورق السميك المطوي لمنع تشقق الطي
            if is_closed and paper_weight >= Decimal('250'):
                raw_cr = qty * Decimal('0.10')
                cr_setup = max(Decimal('0.00'), Decimal('80.00') - raw_cr)
                OrderService.objects.create(
                    order=order,
                    service_category='finishing',
                    service_name="ريجة وتكسير خط طي للورق السميك لمنع التشقق",
                    quantity=qty,
                    unit=PriceUnit.PIECE,
                    unit_price=Decimal('0.10'),
                    setup_cost=cr_setup
                )
                total_finishing_cost += (raw_cr + cr_setup)

            die_cutting = post_data.get('die_cutting') or 'straight_cut'
            if 'die_cut' in str(die_cutting):
                die_total = Decimal('250.00')
                OrderService.objects.create(
                    order=order,
                    service_category='finishing',
                    service_name="فورمة سكاكين وقص وتكسير",
                    quantity=Decimal('1'),
                    unit=PriceUnit.PIECE,
                    unit_price=die_total,
                    total_cost=die_total
                )
                total_finishing_cost += die_total

            # خدمات التجليد المتخصصة
            if order_type in ['catalog', 'book', 'magazine', 'book_catalog']:
                binding = order.binding_type
                if binding == 'staple':
                    staple_cost = max(Decimal('75.00'), qty * Decimal('0.50'))
                    OrderService.objects.create(
                        order=order,
                        service_category='packaging',
                        service_name="تجميع ملازم وتدبيس فرنسي سرج (دبوسين على الكعب)",
                        quantity=qty,
                        unit=PriceUnit.PIECE,
                        unit_price=Decimal('0.50'),
                        total_cost=staple_cost
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
                        total_cost=pb_cost
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
                        setup_cost=Decimal('150.00')
                    )
                    total_finishing_cost += hc_cost
                elif binding == 'wire_o':
                    wire_cost = max(Decimal('120.00'), qty * Decimal('2.50'))
                    OrderService.objects.create(
                        order=order,
                        service_category='packaging',
                        service_name="تخريم وتركيب سلك لولبي دبل (Wire-O Spiral)",
                        quantity=qty,
                        unit=PriceUnit.PIECE,
                        unit_price=Decimal('2.50'),
                        total_cost=wire_cost
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
                        total_cost=pad_cost
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
                        total_cost=sewing_total
                    )
                    total_finishing_cost += sewing_total

            elif order_type in ['invoice', 'receipt', 'ncr']:
                ncr_cap = Decimal(str(order.ncr_book_capacity or 50))
                total_nums = qty * ncr_cap
                numbering_cost = max(Decimal('100.00'), (total_nums / Decimal('1000')) * Decimal('20.00'))
                OrderService.objects.create(
                    order=order,
                    service_category='finishing',
                    service_name=f"ترقيم سيريال أوتوماتيك من {order.ncr_serial_start} إلى {order.ncr_serial_end}",
                    quantity=total_nums,
                    unit=PriceUnit.PIECE,
                    unit_price=Decimal('0.02'),
                    total_cost=numbering_cost
                )
                pad_binding_cost = qty * Decimal('2.50')
                OrderService.objects.create(
                    order=order,
                    service_category='packaging',
                    service_name="ريجة تخريم وتجميع وتكعيب دفاتر الفواتير",
                    quantity=qty,
                    unit=PriceUnit.PIECE,
                    unit_price=Decimal('2.50'),
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
                    setup_cost=folder_die
                )
                total_finishing_cost += (folder_die + folder_glue)

            # 5. اللوجستيات والشحن
            extra_cost_str = post_data.get('extra_cost') or post_data.get('estimated_shipping_cost') or '0.00'
            try:
                shipping_cost = Decimal(str(extra_cost_str))
            except:
                shipping_cost = Decimal('0.00')

            # 6. الحساب الإجمالي وتحديث OrderSummary
            subtotal_cost = total_materials_cost + total_printing_cost + total_finishing_cost + shipping_cost

            profit_margin_pct = Decimal(str(post_data.get('profit_margin') or order.profit_margin or '25.00'))
            margin_factor = profit_margin_pct / Decimal('100')
            
            import math
            if margin_factor < Decimal('1'):
                raw_final = subtotal_cost / (Decimal('1') - margin_factor)
                final_sell_price = Decimal(str(math.ceil(float(raw_final)))).quantize(Decimal('0.01'))
            else:
                raw_final = subtotal_cost * Decimal('1.25')
                final_sell_price = Decimal(str(math.ceil(float(raw_final)))).quantize(Decimal('0.01'))

            # السعر الصافي للبيع (غير شامل الضريبة ومجبور للأعلى)
            net_sell_price = final_sell_price

            # تحديث حقول الطلب المباشرة بالسعر الصافي
            order.estimated_cost = subtotal_cost
            order.final_price = net_sell_price
            order.sale_price = net_sell_price
            order.profit_margin = profit_margin_pct
            order.save(update_fields=['estimated_cost', 'final_price', 'sale_price', 'profit_margin'])

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
