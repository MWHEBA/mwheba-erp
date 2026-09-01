"""
خدمة الحفظ والتحليل الذري لتشريح الشغلانة وتفكيك بنود الخامات والخدمات
Anatomy-Driven Order Persistence & Procurement Breakdown Service
"""
from decimal import Decimal
from django.db import transaction
from ..models import (
    PrintingOrder, OrderMaterial, OrderService, OrderSummary,
    PriceUnit
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
            order_type = post_data.get('order_type') or order.order_type or 'flyer'
            
            # 1. تنظيف البنود السابقة للطلب لتحديثها بشكل نظيف
            order.materials.all().delete()
            order.services.all().delete()

            # 2. حسابات الورق والخامات
            paper_weight_str = post_data.get('paper_weight') or '300'
            try:
                paper_weight = Decimal(str(paper_weight_str))
            except:
                paper_weight = Decimal('300')
                
            w = Decimal(str(post_data.get('width') or post_data.get('custom_size_width') or order.width or 21))
            h = Decimal(str(post_data.get('height') or post_data.get('custom_size_height') or order.height or 29.7))
            
            # حساب قطع الفرخ والهالك
            cuts_w = max(Decimal('1'), Decimal('100') // w)
            cuts_h = max(Decimal('1'), Decimal('70') // h)
            cuts_per_sheet = max(Decimal('1'), cuts_w * cuts_h)
            
            net_sheets = Decimal(str(int(qty / cuts_per_sheet) + (1 if qty % cuts_per_sheet > 0 else 0)))
            waste_rate = Decimal('0.05') if qty > 2000 else Decimal('0.10')
            gross_sheets = Decimal(str(int(net_sheets * (Decimal('1') + waste_rate)) + 1))
            
            sheet_unit_cost = Decimal('3.50') * (paper_weight / Decimal('300'))
            cover_paper_cost = gross_sheets * sheet_unit_cost

            # أ. تسجيل خامة ورق الغلاف / المطبوع الرئيسي
            OrderMaterial.objects.create(
                order=order,
                material_type='paper',
                material_name=f"ورق كوشيه فاخر {paper_weight} جم (مقاس 70×100)",
                quantity=gross_sheets,
                unit=PriceUnit.SHEET,
                unit_cost=sheet_unit_cost.quantize(Decimal('0.01')),
                total_cost=cover_paper_cost.quantize(Decimal('0.01')),
                waste_percentage=waste_rate * Decimal('100')
            )
            total_materials_cost = cover_paper_cost

            # ب. لو كان الصنف كتاب / كتالوج (تسجيل ورق المتن)
            if order_type in ['catalog', 'book', 'magazine', 'book_catalog']:
                pages_count = int(post_data.get('pages_count') or order.pages_count or 32)
                inner_sheets_per_book = Decimal(str(pages_count / 16))
                inner_gross_sheets = Decimal(str(int((qty * inner_sheets_per_book) * Decimal('1.08')) + 1))
                inner_sheet_cost = Decimal('2.20')
                inner_paper_cost = inner_gross_sheets * inner_sheet_cost

                OrderMaterial.objects.create(
                    order=order,
                    material_type='paper',
                    material_name=f"ورق متن داخلي 135 جم (عدد {pages_count} صفحة)",
                    quantity=inner_gross_sheets,
                    unit=PriceUnit.SHEET,
                    unit_cost=inner_sheet_cost,
                    total_cost=inner_paper_cost.quantize(Decimal('0.01')),
                    waste_percentage=Decimal('8.00')
                )
                total_materials_cost += inner_paper_cost

            # 3. خدمات الطباعة والزنكات CTP
            plates_count_str = post_data.get('zinc_plates_count') or post_data.get('plate_count') or '4'
            try:
                plates_count = int(plates_count_str)
            except:
                plates_count = 4 if qty > 300 else 0
                
            total_printing_cost = Decimal('0.00')
            if plates_count > 0:
                # خدمة زنكات CTP
                plate_rate = Decimal('75.00')
                plates_total = Decimal(str(plates_count)) * plate_rate
                OrderService.objects.create(
                    order=order,
                    service_category='printing',
                    service_name=f"تجهيز وفتح زنكات CTP أوفست (عدد {plates_count} زنكة)",
                    quantity=Decimal(str(plates_count)),
                    unit=PriceUnit.PIECE,
                    unit_price=plate_rate,
                    total_cost=plates_total
                )
                total_printing_cost += plates_total

                # خدمة سحبات التراج
                press_pulls = gross_sheets
                press_rate_per_1000 = Decimal('40.00')
                min_press_floor = Decimal('180.00')
                thousands_pulls = Decimal(str(int(press_pulls / 1000) + (1 if press_pulls % 1000 > 0 else 0)))
                press_total = max(min_press_floor, thousands_pulls * press_rate_per_1000)

                OrderService.objects.create(
                    order=order,
                    service_category='printing',
                    service_name=f"طباعة أوفست بالتراج (سحبات ماكينة {press_pulls} سحبة)",
                    quantity=thousands_pulls,
                    unit=PriceUnit.THOUSAND,
                    unit_price=press_rate_per_1000,
                    total_cost=press_total
                )
                total_printing_cost += press_total
            else:
                # ديجيتال شيتات
                digital_rate = Decimal('2.50')
                digital_total = qty * digital_rate
                OrderService.objects.create(
                    order=order,
                    service_category='printing',
                    service_name="طباعة ديجيتال شيتات A3+ بالألوان",
                    quantity=qty,
                    unit=PriceUnit.PIECE,
                    unit_price=digital_rate,
                    total_cost=digital_total
                )
                total_printing_cost += digital_total

            # 4. خدمات التشطيب والسلوفان والتجليد والتكسير
            total_finishing_cost = Decimal('0.00')
            lamination = post_data.get('coating_type') or post_data.get('lamination') or 'matte_2_sides'
            if lamination not in ['none', '', '0']:
                lam_rate = Decimal('0.90') if '2_sides' in str(lamination) else Decimal('0.50')
                min_lam_floor = Decimal('150.00')
                lam_total = max(min_lam_floor, gross_sheets * lam_rate)

                OrderService.objects.create(
                    order=order,
                    service_category='coating',
                    service_name=f"سلوفان حراري مط/لامع ({lamination})",
                    quantity=gross_sheets,
                    unit=PriceUnit.PIECE,
                    unit_price=lam_rate,
                    total_cost=lam_total
                )
                total_finishing_cost += lam_total

            # تشطيبات فاخرة وتكسير
            finishing = post_data.get('finishing') or 'none'
            if finishing not in ['none', '']:
                uv_total = max(Decimal('200.00'), qty * Decimal('0.40'))
                OrderService.objects.create(
                    order=order,
                    service_category='finishing',
                    service_name=f"تشطيب خاص فاخر ({finishing})",
                    quantity=qty,
                    unit=PriceUnit.PIECE,
                    unit_price=Decimal('0.40'),
                    total_cost=uv_total
                )
                total_finishing_cost += uv_total

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

            if order_type in ['catalog', 'book', 'magazine', 'book_catalog']:
                binding_total = max(Decimal('150.00'), qty * Decimal('1.20'))
                OrderService.objects.create(
                    order=order,
                    service_category='packaging',
                    service_name="تجميع وتجليد كتالوج / كتاب",
                    quantity=qty,
                    unit=PriceUnit.PIECE,
                    unit_price=Decimal('1.20'),
                    total_cost=binding_total
                )
                total_finishing_cost += binding_total

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
            
            if margin_factor < Decimal('1'):
                final_sell_price = (subtotal_cost / (Decimal('1') - margin_factor)).quantize(Decimal('0.01'))
            else:
                final_sell_price = subtotal_cost * Decimal('1.25')

            # السعر الصافي للبيع (غير شامل الضريبة)
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
