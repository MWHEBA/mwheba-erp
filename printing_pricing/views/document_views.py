import math
from decimal import Decimal
from django.views.generic import DetailView
from django.shortcuts import get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.translation import gettext_lazy as _

from printing_pricing.models.order import PrintingOrder, DieMouldCustody, QCSignoff
from printing_pricing.services.pdf_sanitizer_service import CustomerPDFSanitizerService


class ConsolidatedPressJobSheetView(LoginRequiredMixin, DetailView):
    """
    أمر التشغيل المجمع للمطبعة (Consolidated Press Job Sheet)
    مجرد 100% من الأسعار - يركز على التعليمات الفنية واتجاه الألياف وضبط الألوان
    """
    model = PrintingOrder
    template_name = "printing_pricing/orders/consolidated_job_sheet.html"
    context_object_name = "order"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = self.object
        calc = getattr(order, 'cost_calculation', None)
        offset_calc = getattr(calc, 'offset_calc', None) if calc else None
        paper_calc = getattr(calc, 'paper_calc', None) if calc else None

        # حسابات استيكرات فرز الرزم المقصوصة
        items_per_sheet = paper_calc.pieces_per_sheet if paper_calc else 1
        total_piles = items_per_sheet

        context.update({
            'page_title': f"أمر تشغيل مطبعة مجمع - {order.order_number}",
            'offset_calc': offset_calc,
            'paper_calc': paper_calc,
            'total_piles': total_piles,
            'is_press_document': True,
        })
        return context


class OutsourcedJobSheetView(LoginRequiredMixin, DetailView):
    """
    أمر التشغيل المنفصل للورش الخارجية (Outsourced Workshop Job Sheet)
    مجرد 100% من الأسعار - متضمناً مواصفات السلوفان، البصمة، التكسير، والتجليد
    """
    model = PrintingOrder
    template_name = "printing_pricing/orders/outsourced_job_sheet.html"
    context_object_name = "order"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = self.object
        calc = getattr(order, 'cost_calculation', None)
        finishing_calc = getattr(calc, 'finishing_calc', None) if calc else None

        context.update({
            'page_title': f"أمر تشغيل ورشة خارجية - {order.order_number}",
            'finishing_calc': finishing_calc,
            'is_outsourced_document': True,
        })
        return context


class DeliveryNoteView(LoginRequiredMixin, DetailView):
    """
    إذن تسليم بضاعة رسمي للعميل (Delivery Note)
    يدعم تمييز الزيادات المجانية، حساب الكراتين، وسجل تبادل عهدة الطبالي
    """
    model = PrintingOrder
    template_name = "printing_pricing/orders/delivery_note.html"
    context_object_name = "order"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = self.object

        # استخراج الكمية المعتمدة من الجودة
        qc = getattr(order, 'qc_signoff', None)
        delivered_qty = qc.net_quantity_approved if qc else order.quantity
        billed_qty = order.quantity
        complimentary_overrun = max(0, delivered_qty - billed_qty)

        # حساب وزن الشحنة وعدد الكراتين (سقف 15-18 كجم للكرتونة)
        calc = getattr(order, 'cost_calculation', None)
        paper_calc = getattr(calc, 'paper_calc', None) if calc else None
        
        # وزن تقريبي للمنتج الواحد بالجرام
        unit_weight_grams = 25  # افتراضي
        total_weight_kg = (delivered_qty * unit_weight_grams) / 1000.0
        
        # توزيع الكراتين بحد أقصى 15 كجم للكرتونة
        max_carton_weight_kg = 15.0
        total_cartons = max(1, math.ceil(total_weight_kg / max_carton_weight_kg))
        items_per_carton = math.ceil(delivered_qty / total_cartons)

        context.update({
            'page_title': f"إذن تسليم بضاعة - {order.order_number}",
            'delivered_qty': delivered_qty,
            'billed_qty': billed_qty,
            'complimentary_overrun': complimentary_overrun,
            'total_weight_kg': round(total_weight_kg, 2),
            'total_cartons': total_cartons,
            'items_per_carton': items_per_carton,
        })
        return context


class CartonLabelsView(LoginRequiredMixin, DetailView):
    """
    طباعة استيكرات الكراتين الموزونة والمعيارية (Carton Labels View)
    تولد استيكر لكل كرتونة: "كرتونة X من Y" مع الباركود والمحتوى
    """
    model = PrintingOrder
    template_name = "printing_pricing/orders/carton_labels.html"
    context_object_name = "order"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = self.object

        delivered_qty = order.quantity
        unit_weight_grams = 25
        total_weight_kg = (delivered_qty * unit_weight_grams) / 1000.0
        total_cartons = max(1, math.ceil(total_weight_kg / 15.0))
        items_per_carton = math.ceil(delivered_qty / total_cartons)

        carton_list = []
        for i in range(1, total_cartons + 1):
            carton_list.append({
                'number': i,
                'total': total_cartons,
                'items_count': items_per_carton if i < total_cartons else (delivered_qty - (items_per_carton * (total_cartons - 1))),
                'weight_kg': round(total_weight_kg / total_cartons, 1),
            })

        context.update({
            'page_title': f"استيكرات الكراتين - {order.order_number}",
            'cartons': carton_list,
            'total_cartons': total_cartons,
        })
        return context


class ExecutiveSummaryView(LoginRequiredMixin, DetailView):
    """
    ملخص التفاوض التنفيذي السري للمناقصات والصفقات الكبرى (Executive Negotiation Sheet)
    يحتوي على تكاليف التفكيك، الحد الأدنى للربح، مستقطعات حسن التنفيذ، وهوامش التحوط
    """
    model = PrintingOrder
    template_name = "printing_pricing/orders/executive_summary.html"
    context_object_name = "order"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = self.object
        summary = getattr(order, 'summary', None)
        calc = getattr(order, 'cost_calculation', None)

        # حسابات التفاوض ومستقطعات حسن التنفيذ
        subtotal = getattr(summary, 'subtotal', Decimal('0.00')) if summary else Decimal('0.00')
        tax_amount = getattr(summary, 'tax_amount', Decimal('0.00')) if summary else Decimal('0.00')
        discount_amount = getattr(summary, 'discount_amount', Decimal('0.00')) if summary else Decimal('0.00')
        final_price = (subtotal + tax_amount - discount_amount).quantize(Decimal('0.01'))
        total_cost = summary.total_cost if summary else (calc.total_cost if calc else Decimal('0.00'))
        net_profit = summary.profit_amount if summary else (final_price - total_cost)
        margin_pct = summary.profit_margin_percentage if summary else Decimal('0.00')

        # مستقطع حسن التنفيذ 5% و 10%
        retention_5pct = (final_price * Decimal('0.05')).quantize(Decimal('0.01'))
        retention_10pct = (final_price * Decimal('0.10')).quantize(Decimal('0.01'))
        cash_flow_after_retention_5 = final_price - retention_5pct

        # الحد الأدنى لسعر التفاوض (Floor Price at 12% margin)
        floor_price = (total_cost * Decimal('1.12')).quantize(Decimal('0.01'))

        context.update({
            'page_title': f"الملخص التنفيذي السري - {order.order_number}",
            'summary': summary,
            'calc': calc,
            'final_price': final_price,
            'total_cost': total_cost,
            'net_profit': net_profit,
            'margin_pct': margin_pct,
            'retention_5pct': retention_5pct,
            'retention_10pct': retention_10pct,
            'cash_flow_after_retention_5': cash_flow_after_retention_5,
            'floor_price': floor_price,
        })
        return context
