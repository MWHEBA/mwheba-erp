from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse_lazy, reverse
from django.http import JsonResponse, HttpResponseRedirect
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _
from django.db.models import Q, Sum, Count
from django.core.paginator import Paginator
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from core.utils import UnifiedPaginationMixin
from ..models import (
    PrintingOrder, OrderMaterial, OrderService, OrderSummary,
    PaperSpecification, PricingStatus, OrderType,
    ProductType, ProductSize,
    PaperType, PaperSize, PaperWeight, PaperOrigin, PieceSize,
    PlateSize, CoatingType, PackagingType, FinishingType
)
from ..forms import PricingOrderForm, OrderSearchForm
from customer.models import Customer


class OrderListView(UnifiedPaginationMixin, LoginRequiredMixin, ListView):
    """
    عرض قائمة طلبات التسعير مع الفلترة الموحدة ودعم AJAX
    """
    model = PrintingOrder
    template_name = 'printing_pricing/orders/order_list.html'
    context_object_name = 'orders'
    default_per_page = 25
    
    def get_queryset(self):
        """تخصيص الاستعلام مع البحث والفلترة"""
        queryset = PrintingOrder.objects.select_related('customer').filter(
            is_active=True
        )
        if not (self.request.user.is_superuser or self.request.user.is_staff):
            queryset = queryset.filter(created_by=self.request.user)
        
        search_query = self.request.GET.get('search_query') or self.request.GET.get('search') or self.request.GET.get('q')
        status = self.request.GET.get('status')
        order_type = self.request.GET.get('order_type')
        customer = self.request.GET.get('customer')
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')
        
        if search_query:
            from utils.search import smart_search_filter
            queryset = smart_search_filter(
                queryset,
                search_query.strip(),
                text_fields=['customer__name', 'customer__company_name', 'title'],
                code_fields=['order_number', 'customer__code', 'customer__phone']
            )
        
        if status:
            queryset = queryset.filter(status=status)
        
        if order_type:
            queryset = queryset.filter(order_type=order_type)
        
        if customer:
            if isinstance(customer, str) and customer.isdigit():
                queryset = queryset.filter(customer_id=int(customer))
            elif hasattr(customer, 'id'):
                queryset = queryset.filter(customer=customer)
        
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)
        
        return queryset.order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        """إضافة بيانات إضافية للسياق"""
        context = super().get_context_data(**kwargs)
        
        search_query = self.request.GET.get('search_query') or self.request.GET.get('search') or self.request.GET.get('q') or ''
        status = self.request.GET.get('status') or ''
        order_type = self.request.GET.get('order_type') or ''
        customer = self.request.GET.get('customer') or ''
        date_from = self.request.GET.get('date_from') or ''
        date_to = self.request.GET.get('date_to') or ''
        
        all_orders = PrintingOrder.objects.filter(is_active=True)
        if not (self.request.user.is_superuser or self.request.user.is_staff):
            all_orders = all_orders.filter(created_by=self.request.user)
            
        context['stats'] = {
            'total_orders': all_orders.count(),
            'pending_orders': all_orders.filter(status='pending').count(),
            'approved_orders': all_orders.filter(status='approved').count(),
            'total_value': all_orders.aggregate(
                total=Sum('final_price')
            )['total'] or all_orders.aggregate(
                total=Sum('estimated_cost')
            )['total'] or Decimal('0.00')
        }
        
        context['page_title'] = _('طلبات تسعير الطباعة')
        context['page_subtitle'] = _('عرض وإدارة وتتبع جميع طلبات وتسعيرات أعمال الطباعة')
        context['page_icon'] = 'fas fa-print'
        context['header_buttons'] = [
            {
                'url': reverse('printing_pricing:order_create'),
                'icon': 'fa-plus',
                'text': _('تسعير جديد'),
                'class': 'btn-primary',
            },
        ]
        context['breadcrumb_items'] = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('تسعير الطباعة'), 'url': reverse('printing_pricing:dashboard'), 'icon': 'fa-calculator'},
            {'title': _('طلبات تسعير الطباعة'), 'active': True},
        ]
        
        context['customers'] = Customer.objects.filter(is_active=True).only('id', 'name').order_by('name')
        context['status_choices'] = PricingStatus.choices
        context['order_type_choices'] = OrderType.choices
        context['product_types'] = ProductType.objects.filter(is_active=True).order_by('sort_order', 'id')
        context['product_sizes'] = ProductSize.objects.filter(is_active=True).order_by('sort_order', 'id')
        context['search_query'] = search_query
        context['selected_customer'] = customer
        context['selected_status'] = status
        context['selected_order_type'] = order_type
        context['selected_date_from'] = date_from
        context['selected_date_to'] = date_to

        # تعريف أعمدة جدول البيانات الموحد (Unified Data Table Headers)
        context['headers'] = [
            {
                'key': 'order_number',
                'label': _('رقم الطلب'),
                'sortable': True,
                'class': 'text-center fw-bold',
                'width': '130px',
            },
            {
                'key': 'customer_name',
                'label': _('العميل'),
                'sortable': True,
                'class': 'text-start fw-bold',
            },
            {
                'key': 'title',
                'label': _('عنوان ومسمى الطلب'),
                'sortable': True,
                'class': 'text-start',
            },
            {
                'key': 'product_type_name',
                'label': _('نوع المطبوع'),
                'sortable': False,
                'class': 'text-center',
                'width': '120px',
            },
            {
                'key': 'quantity',
                'label': _('الكمية'),
                'sortable': True,
                'class': 'text-center fw-bold',
                'width': '90px',
                'format': 'number',
            },
            {
                'key': 'final_price',
                'label': _('قيمة التسعير'),
                'sortable': True,
                'class': 'text-center fw-bold text-success',
                'width': '130px',
                'format': 'currency',
            },
            {
                'key': 'status',
                'label': _('الحالة'),
                'sortable': True,
                'class': 'text-center',
                'width': '110px',
                'format': 'status',
            },
            {
                'key': 'created_at',
                'label': _('التاريخ'),
                'sortable': True,
                'class': 'text-center text-muted',
                'width': '110px',
                'format': 'date',
            },
        ]

        # أزرار الإجراءات للجدول الموحد
        context['action_buttons'] = [
            {
                'url': 'printing_pricing:order_detail',
                'icon': 'fa-eye',
                'class': 'action-view text-secondary',
                'label': _('عرض'),
            },
            {
                'url': 'printing_pricing:order_update',
                'icon': 'fa-edit',
                'class': 'action-edit text-primary',
                'label': _('تعديل'),
            },
            {
                'type': 'button',
                'icon': 'fa-trash',
                'class': 'action-delete text-danger',
                'label': _('حذف'),
                'data_attrs': 'onclick="confirmDeleteOrder(this.closest(\'tr\').dataset.id)"',
            },
        ]
        context['primary_key'] = 'id'
        
        return context

    def render_to_response(self, context, **response_kwargs):
        if self.request.headers.get("X-Requested-With") == "XMLHttpRequest" or self.request.GET.get("ajax"):
            ajax_table_context = {
                **context,
                'table_id': 'order-table',
                'data': context.get('orders'),
                'headers': context.get('headers'),
                'action_buttons': context.get('action_buttons'),
                'primary_key': 'id',
                'table_class': 'hover clickable-rows',
                'empty_message': _('لا توجد طلبات تسعير متاحة'),
                'show_search': False,
                'show_length_menu': False,
                'disable_pagination': True,
                'show_currency': True,
                'clickable_rows': True,
                'row_click_url': '/printing-pricing/orders/0/',
            }
            table_html = render_to_string(
                "components/data_table.html",
                ajax_table_context,
                request=self.request
            )
            pagination_html = render_to_string(
                "partials/pagination.html",
                context,
                request=self.request
            )
            return JsonResponse({
                "table_html": table_html,
                "pagination_html": pagination_html,
            })
        return super().render_to_response(context, **response_kwargs)


def check_can_view_margins(user):
    """التحقق من صلاحية رؤية التكاليف وهوامش الأرباح"""
    return user.is_authenticated and (user.is_superuser or user.has_perm('printing_pricing.view_cost_margins') or user.is_staff)


def _get_friendly_bed_plate_name(bed_str):
    """تحويل مقاس الفرخ إلى المصطلح الدارج للزنكات في السوق المصري (ربع / نص / فرخ كامل)"""
    if not bed_str:
        return ""
    bed_norm = str(bed_str).lower().replace(' ', '').replace('×', 'x')
    if any(k in bed_norm for k in ['35x50', '50x35', '52', 'ربع']):
        return 'مقاس ربع'
    elif any(k in bed_norm for k in ['50x70', '70x50', '74', 'نص']):
        return 'مقاس نص'
    elif any(k in bed_norm for k in ['70x100', '100x70', '102', 'كامل', 'فرخ']):
        return 'مقاس كامل'
    dim = str(bed_str).replace('x', '×').replace('X', '×')
    return f"مقاس {dim}"


def _get_friendly_bed_machine_name(bed_str):
    """تحويل مقاس الفرخ إلى المصطلح الدارج لماكينات الأوفست في السوق المصري (ماكينة ربع / ماكينة نص / ماكينة فرخ)"""
    if not bed_str:
        return ""
    bed_norm = str(bed_str).lower().replace(' ', '').replace('×', 'x')
    if any(k in bed_norm for k in ['35x50', '50x35', '52', 'ربع']):
        return 'ماكينة ربع'
    elif any(k in bed_norm for k in ['50x70', '70x50', '74', 'نص']):
        return 'ماكينة نص'
    elif any(k in bed_norm for k in ['70x100', '100x70', '102', 'كامل', 'فرخ']):
        return 'ماكينة فرخ'
    dim = str(bed_str).replace('x', '×').replace('X', '×')
    return f"ماكينة {dim}"


class OrderDetailView(LoginRequiredMixin, DetailView):
    """
    عرض تفاصيل طلب التسعير ومركز الأرباح 360 درجة
    """
    model = PrintingOrder
    template_name = 'printing_pricing/orders/order_detail.html'
    context_object_name = 'order'
    
    def get_queryset(self):
        """تحسين الاستعلام مع الجداول المرتبطة"""
        queryset = PrintingOrder.objects.select_related(
            'customer', 'created_by', 'updated_by', 'currency', 'work_order',
            'product_type', 'product_size', 'sales_rep'
        ).prefetch_related(
            'materials', 'services__supplier_service__supplier',
            'calculations', 'paper_specs'
        )
        if not (self.request.user.is_superuser or self.request.user.is_staff):
            queryset = queryset.filter(created_by=self.request.user)
        return queryset
    
    def get_context_data(self, **kwargs):
        """إضافة بيانات إضافية لمركز التكلفة والأرباح 360 درجة ورأس الصفحة الموحد"""
        context = super().get_context_data(**kwargs)
        order = self.object
        user = self.request.user
        can_view_margins = check_can_view_margins(user)
        context['can_view_margins'] = can_view_margins
        
        # رابط العميل القابل للنقر في رأس الصفحة والكارت
        from customer.models import Customer
        import urllib.parse
        customer_url = None
        if order.customer:
            customer_url = reverse('customer:customer_detail', kwargs={'pk': order.customer.pk})
        elif order.customer_name:
            matched = Customer.objects.filter(name__iexact=order.customer_name.strip(), is_active=True).first()
            if matched:
                customer_url = reverse('customer:customer_detail', kwargs={'pk': matched.pk})
            else:
                customer_url = f"{reverse('customer:customer_list')}?search={urllib.parse.quote(order.customer_name.strip())}"
        else:
            customer_url = reverse('customer:customer_list')

        context['customer_url'] = customer_url

        # رأس الصفحة ومسار التنقل الموحد
        context['page_title'] = order.title or _('تفاصيل طلب التسعير')
        customer_link_html = f'<a href="{customer_url}" class="text-primary fw-bold text-decoration-none hover-primary" title="{_("عرض بيانات العميل")}"><i class="fas fa-user me-1"></i>{order.customer_display_name}</a>'
        context['page_subtitle'] = _('العميل: %(customer)s | تاريخ الطلب: %(date)s') % {
            'customer': customer_link_html,
            'date': order.order_date
        }
        context['page_icon'] = 'fas fa-print'
        context['breadcrumb_items'] = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('تسعير الطباعة'), 'url': reverse('printing_pricing:dashboard'), 'icon': 'fa-calculator'},
            {'title': _('طلبات التسعير'), 'url': reverse('printing_pricing:order_list'), 'icon': 'fa-list'},
            {'title': order.order_number, 'active': True},
        ]
        
        # شارات رأس الصفحة (Header Badges)
        status_badge_class = 'bg-secondary-subtle text-secondary border border-secondary-subtle'
        status_icon = 'fas fa-pencil-alt'
        if order.status == 'approved':
            status_badge_class = 'bg-success-subtle text-success border border-success-subtle'
            status_icon = 'fas fa-check-circle'
        elif order.status == 'completed':
            status_badge_class = 'bg-primary-subtle text-primary border border-primary-subtle'
            status_icon = 'fas fa-flag-checkered'
        elif order.status in ['pending', 'calculated']:
            status_badge_class = 'bg-warning-subtle text-warning border border-warning-subtle'
            status_icon = 'fas fa-clock'
        elif order.status in ['rejected', 'cancelled']:
            status_badge_class = 'bg-danger-subtle text-danger border border-danger-subtle'
            status_icon = 'fas fa-times-circle'
        elif order.status == 'draft':
            status_badge_class = 'bg-secondary-subtle text-secondary border border-secondary-subtle'
            status_icon = 'fas fa-pencil-alt'
            
        header_badges = [
            {
                'text': f"{order.order_number}",
                'class': 'bg-primary',
                'icon': 'fas fa-hashtag'
            },
            {
                'text': order.get_status_display(),
                'class': status_badge_class,
                'icon': status_icon
            }
        ]
        if order.work_order:
            header_badges.append({
                'text': f"{_('أمر شغل')} #{order.work_order.number}",
                'class': 'bg-info-subtle text-info border border-info-subtle',
                'icon': 'fas fa-cogs',
                'url': reverse('work_order:work_order_detail', kwargs={'pk': order.work_order.pk})
            })
        context['header_badges'] = header_badges
        
        # أزرار رأس الصفحة (Header Buttons)
        buttons = [
            {
                'url': reverse('printing_pricing:order_update', kwargs={'pk': order.pk}),
                'icon': 'fa-edit',
                'text': _('تعديل الطلب'),
                'class': 'btn-outline-primary btn-sm',
            },
            {
                'url': reverse('printing_pricing:duplicate_order', kwargs={'pk': order.pk}),
                'icon': 'fa-copy',
                'text': _('نسخ الطلب'),
                'class': 'btn-outline-secondary btn-sm',
            },
        ]
        
        if can_view_margins:
            buttons.append({
                'onclick': f'window.recalculateOrderCost({order.pk})',
                'icon': 'fa-sync-alt',
                'text': _('إعادة حساب التكلفة'),
                'class': 'btn-outline-info btn-sm',
                'id': 'btn_recalculate_cost',
            })
            
        if order.status not in ['approved', 'completed']:
            buttons.append({
                'onclick': f'window.approveOrder({order.pk})',
                'icon': 'fa-check-double',
                'text': _('اعتماد الطلب'),
                'class': 'btn-outline-success btn-sm',
                'id': 'btn_approve_order',
            })
            
        can_convert_to_work_order = not order.work_order and order.status in ['approved', 'completed']
        context['can_convert_to_work_order'] = can_convert_to_work_order
        if can_convert_to_work_order:
            buttons.append({
                'id': 'btn_convert_work_order',
                'icon': 'fa-cogs',
                'text': _('بدء التشغيل وتوليد أمر الشغل (PO)'),
                'class': 'btn-success btn-sm fw-bold shadow-sm',
                'data_attrs': f'data-order-id="{order.pk}"',
            })
        elif order.work_order:
            buttons.append({
                'url': reverse('work_order:work_order_detail', kwargs={'pk': order.work_order.pk}),
                'icon': 'fa-link',
                'text': f"{_('أمر الشغل')} #{order.work_order.number}",
                'class': 'btn-info btn-sm text-white fw-bold',
            })
            
        context['header_buttons'] = buttons
        
        # تنظيف وصياغة الأوجه ونمط الألوان وفقاً للمعايير المطبعية المصرية
        def _format_face_colors(cmyk_count, spot_count):
            parts = []
            if cmyk_count > 0:
                parts.append(f"{cmyk_count} لون")
            if spot_count > 0:
                parts.append(f"{spot_count} لون مخصوص")
            return " + ".join(parts) if parts else ""

        if order.cover_printing_type == 'digital':
            d_mode = order.digital_color_mode
            if d_mode == '4_0':
                sides_display = _('وجه واحد (4 لون)')
            elif d_mode == '1_0':
                sides_display = _('وجه واحد (1 لون أسود)')
            elif d_mode == '4_4':
                sides_display = _('وجهين (4/4 لون)')
            elif d_mode == '4_1':
                sides_display = _('وجهين (الوجه: 4 لون - الظهر: 1 لون أسود)')
            elif d_mode == '1_1':
                sides_display = _('وجهين (1/1 لون أسود)')
            else:
                sides_display = order.get_digital_color_mode_display()
        elif order.cover_printing_type == 'none':
            sides_display = _('بدون طباعة')
        else:  # offset or other
            plate_svc = order.services.filter(service_category='printing', service_name__icontains='زنك', is_active=True).first()
            s_info = plate_svc.supplier_info if (plate_svc and isinstance(plate_svc.supplier_info, dict)) else {}
            
            spot_front = order.spot_colors_front or 0
            spot_back = order.spot_colors_back or 0
            
            raw_fp = s_info.get('front_plates')
            raw_bp = s_info.get('back_plates')
            
            # استخراج ألوان الـ CMYK عبر خصم الألوان المخصوصة من إجمالي الزنكات المسجلة إن وجدت
            if raw_fp is not None:
                front_cmyk = max(0, int(raw_fp) - spot_front)
            else:
                front_cmyk = 4
                
            if raw_bp is not None:
                back_cmyk = max(0, int(raw_bp) - spot_back)
            else:
                back_cmyk = 4 if order.print_sides_mode == 'work_sheet' else 0

            # صياغة النص المطبعي النظيف
            if order.print_sides_mode == 'single':
                face_text = _format_face_colors(front_cmyk, spot_front) or _("4 لون")
                sides_display = f"وجه واحد ({face_text})"
            elif order.print_sides_mode == 'work_turn':
                # طبع وقلب (استخدام نفس الزنكات للوجهين)
                if spot_front == 0:
                    sides_display = f"طبع وقلب ({front_cmyk}/{front_cmyk} لون)"
                else:
                    face_text = _format_face_colors(front_cmyk, spot_front)
                    sides_display = f"طبع وقلب ({face_text})"
            else:  # work_sheet (وجهين)
                if spot_front == 0 and spot_back == 0 and front_cmyk == back_cmyk and front_cmyk > 0:
                    sides_display = f"وجهين ({front_cmyk}/{back_cmyk} لون)"
                else:
                    front_desc = _format_face_colors(front_cmyk, spot_front) or _("بدون طباعة")
                    back_desc = _format_face_colors(back_cmyk, spot_back) or _("بدون طباعة")
                    sides_display = f"وجهين (الوجه: {front_desc} - الظهر: {back_desc})"

        order.clean_sides_and_colors = sides_display
        order.total_spot_colors = (order.spot_colors_front or 0) + (order.spot_colors_back or 0)

        # المواد والخدمات مع ربط المواصفات الفنية للورق والمونتاج
        materials = list(order.materials.filter(is_active=True))
        paper_specs = list(order.paper_specs.filter(is_active=True))
        cover_spec = paper_specs[0] if paper_specs else None
        inner_spec = paper_specs[1] if len(paper_specs) > 1 else None

        has_inner = order.order_type in ['catalog', 'book', 'magazine', 'book_catalog', 'notebook']
        for mat in materials:
            if mat.material_type == 'paper':
                # تنظيف ذكي لاسم المادة: لا يذكر شيء للمطبوع الرئيسي، ويكتب [غلاف] لو فيه صفحات داخلية
                if '[غلاف / مطبوع رئيسي]' in mat.material_name:
                    prefix = '[غلاف] ' if has_inner else ''
                    mat.material_name = mat.material_name.replace('[غلاف / مطبوع رئيسي] ', prefix).replace('[غلاف / مطبوع رئيسي]', prefix).strip()
                elif not has_inner and mat.material_name.startswith('[غلاف]'):
                    mat.material_name = mat.material_name.replace('[غلاف] ', '').replace('[غلاف]', '').strip()

                import re
                mat.material_name = re.sub(r'\s*\(\s*فرخ[^\)]*\)', '', mat.material_name).strip()

                if 'داخلي' in mat.material_name or 'inner' in mat.material_name:
                    mat.paper_spec = inner_spec or cover_spec
                else:
                    mat.paper_spec = cover_spec
            else:
                mat.paper_spec = None

        # تنظيف وضبط مقاسات الورق (اسم ورقم متناسق)
        from ..models import PaperSize
        import re
        for ps in paper_specs:
            raw_name = (ps.paper_size_name or '').strip()
            w = ps.sheet_width or 0
            h = ps.sheet_height or 0
            w_min = min(w, h)
            h_max = max(w, h)
            dim_str = f"({w_min:.0f}×{h_max:.0f} سم)" if (w_min and h_max) else ""

            # تنظيف الاسم من أي أرقام قديمة غير منسقة
            clean_name = re.sub(r'[\(\[\{]?\s*\d+\s*[×xX]\s*\d+\s*(?:سم)?\s*[\)\]\}]?', '', raw_name).strip()
            if not clean_name or clean_name in ['فرخ', 'شيت']:
                matched_ps = PaperSize.objects.filter(width=w_min, height=h_max).first() or PaperSize.objects.filter(width=h_max, height=w_min).first()
                if matched_ps:
                    clean_name = re.sub(r'[\(\[\{]?\s*\d+\s*[×xX]\s*\d+\s*(?:سم)?\s*[\)\]\}]?', '', matched_ps.name).strip()
                else:
                    clean_name = "فرخ قياسي"

            # تركيب الاسم والرقم معاً: اسم الفرخ (العرض×الطول سم)
            ps.clean_paper_size_name = f"{clean_name} {dim_str}".strip() if dim_str else clean_name

            p_raw = (ps.piece_size or '').strip()
            if p_raw in ['ربع', 'quarter']:
                p_name = 'ربع فرخ'
            elif p_raw in ['نصف', 'half']:
                p_name = 'نصف فرخ'
            elif p_raw in ['ثمن', 'eighth']:
                p_name = 'ثمن فرخ'
            elif p_raw in ['كامل', 'full']:
                p_name = 'فرخ كامل'
            elif p_raw:
                p_name = p_raw if 'فرخ' in p_raw else f"{p_raw} فرخ"
            else:
                p_name = 'كامل الفرخ'
            ps.clean_piece_size_name = p_name

        context['materials'] = materials

        # تنظيف وتجهيز خدمات الورش
        services = list(order.services.filter(is_active=True))
        total_services_cost = Decimal('0.00')

        for svc in services:
            total_services_cost += (svc.total_cost or Decimal('0.00'))
            s_name = (svc.service_name or '').strip()
            s_info = svc.supplier_info if isinstance(svc.supplier_info, dict) else {}

            # استخراج مقاس الفرخ من supplier_info أو اسم الخدمة
            bed = s_info.get('bed_size') or ''
            if not bed:
                m = re.search(r'(\d+\s*[xX×]\s*\d+)', s_name)
                if m:
                    bed = m.group(1)

            # تحديد سياق الجزء المطبوع (غلاف أم صفحات داخلية أم بدون بادئة)
            is_inner_part = 'داخلي' in s_name or 'inner' in s_name.lower()
            if is_inner_part:
                prefix = '[داخلي] '
            elif has_inner and ('غلاف' in s_name or 'cover' in s_name.lower()):
                prefix = '[غلاف] '
            else:
                prefix = ''

            # 1. ضبط وتحسين اسم الخدمة حسب الأعراف المهنية للمطابع المصرية
            is_plate = 'زنك' in s_name or 'ctp' in s_name.lower()
            is_offset = ('سحب' in s_name or 'أوفست' in s_name or svc.service_category == 'printing') and not is_plate and 'ديجيتال' not in s_name and 'digital' not in s_name.lower()

            if is_plate:
                friendly_plate = _get_friendly_bed_plate_name(bed)
                svc.clean_service_name = f"{prefix}زنكات CTP ({friendly_plate})" if friendly_plate else f"{prefix}زنكات CTP"
            elif is_offset and ('سحب' in s_name or 'تراج' in s_name):
                friendly_mach = _get_friendly_bed_machine_name(bed)
                svc.clean_service_name = f"{prefix}طباعة أوفست ({friendly_mach})" if friendly_mach else f"{prefix}طباعة أوفست"
            else:
                # تنظيف البادئات والأقواس المكررة من الأسماء الأخرى (سلوفان، تكسير، ديجيتال...)
                if not has_inner:
                    s_name = re.sub(r'^\[(?:غلاف\s*أوفست|غلاف)\]\s*', '', s_name).strip()
                else:
                    s_name = s_name.replace('[غلاف أوفست]', '[غلاف]').strip()
                s_name = re.sub(r'\s*\(\s*عدد\s*\d+\s*(?:زنكة|قطعة)?\s*\)', '', s_name).strip()
                s_name = re.sub(r'\s*\(\s*[\d,]+\s*سحبة\s*-\s*[\d,]+\s*تراج\s*\)', '', s_name).strip()
                svc.clean_service_name = s_name

            # 2. تحديد فئة الخدمة المهنية والأيقونة وشارة العرض
            if is_plate:
                svc.category_display = _('فصل زنكات')
                svc.category_icon = 'fas fa-layer-group'
                svc.category_badge_class = 'bg-info-subtle text-info border border-info-subtle'
            elif is_offset:
                svc.category_display = _('طباعة أوفست')
                svc.category_icon = 'fas fa-print'
                svc.category_badge_class = 'bg-primary-subtle text-primary border border-primary-subtle'
            elif 'ديجيتال' in s_name or 'digital' in s_name.lower():
                svc.category_display = _('طباعة ديجيتال')
                svc.category_icon = 'fas fa-desktop'
                svc.category_badge_class = 'bg-primary-subtle text-primary border border-primary-subtle'
            elif svc.service_category == 'coating' or 'سلوفان' in s_name or 'ورنيش' in s_name or 'uv' in s_name.lower():
                svc.category_display = _('سلوفان وتغطية')
                svc.category_icon = 'fas fa-paint-roller'
                svc.category_badge_class = 'bg-warning-subtle text-warning border border-warning-subtle'
            elif svc.service_category == 'finishing' or any(k in s_name for k in ['تكسير', 'ريجة', 'طي', 'تجليد', 'تدبيس', 'قص', 'فورمة']):
                svc.category_display = _('تشطيب وتجهيز')
                svc.category_icon = 'fas fa-cut'
                svc.category_badge_class = 'bg-success-subtle text-success border border-success-subtle'
            elif svc.service_category == 'packaging' or any(k in s_name for k in ['تعبئة', 'تغليف', 'شرنك', 'كرتون']):
                svc.category_display = _('تقفيل وتغليف')
                svc.category_icon = 'fas fa-box'
                svc.category_badge_class = 'bg-secondary-subtle text-secondary border border-secondary-subtle'
            else:
                svc.category_display = svc.get_service_category_display() or _('خدمات أخرى')
                svc.category_icon = 'fas fa-cogs'
                svc.category_badge_class = 'bg-light text-dark border'

            # 3. تحديد المورد الفعلي لتنظيف جدول الخدمات
            supp_name = ''
            if svc.supplier_service and svc.supplier_service.supplier:
                supp_name = svc.supplier_service.supplier.name
            elif svc.supplier_info and isinstance(svc.supplier_info, dict):
                supp_name = svc.supplier_info.get('supplier_name', '')

            if not supp_name or supp_name == 'مطبعة أوفست معتمدة':
                from supplier.models import Supplier
                pref_supp = Supplier.objects.filter(is_active=True, is_preferred=True, services__service_type__code='offset_printing').first()
                if pref_supp:
                    supp_name = pref_supp.name

            if supp_name:
                supp_name = re.sub(r'\s*/\s*سعر\s*معياري', '', supp_name).strip()
            svc.effective_supplier_name = supp_name

            # 3. صياغة الوصف الفني المركز (بدون تكرار اسم المورد لأن له عمود مخصص)
            desc_parts = []
            if is_plate:
                is_arch = s_info.get('is_archived')
                desc_parts.append("من الأرشيف" if is_arch else "زنكات جديدة")
                if bed:
                    dim_formatted = str(bed).replace('x', '×').replace('X', '×')
                    desc_parts.append(f"أبعاد {dim_formatted} سم")
                svc.clean_description = " • ".join(desc_parts)
            elif is_offset:
                mach = s_info.get('machine') or ''
                # لو اسم الماكينة يحتوي على طراز أو ماركة فعلية وليس مجرد أبعاد (استبعاد حرف x المستخدم في المقاس)
                has_model_name = bool(re.search(r'[a-wy-zA-WY-Z\u0600-\u06FF]', mach))
                if mach and has_model_name:
                    desc_parts.append(mach)
                elif bed or mach:
                    dim_src = bed or mach
                    dim_formatted = str(dim_src).replace('x', '×').replace('X', '×')
                    desc_parts.append(f"أبعاد {dim_formatted} سم")

                pulls = s_info.get('pulls_count')
                if pulls:
                    try:
                        desc_parts.append(f"{int(pulls):,} سحبة فعلية")
                    except (ValueError, TypeError):
                        desc_parts.append(f"{pulls} سحبة فعلية")
                svc.clean_description = " • ".join(desc_parts)
            else:
                raw_desc = svc.service_description or ''
                raw_desc = re.sub(r'(?:المورد|المطبعة)\s*:\s*[^•\|]+[•\|]?', '', raw_desc)
                raw_desc = re.sub(r'سعر التراج:\s*[\d\.]+\s*ج\/تراج\s*\|?', '', raw_desc).strip(' |•')
                svc.clean_description = raw_desc.replace('|', '•').strip()

        context['services'] = services
        context['total_services_cost'] = total_services_cost
        
        # ملخص التكاليف
        try:
            summary = order.summary
            context['summary'] = summary
            if not can_view_margins and summary:
                # عزل الأسرار التجارية والتكلفة عن المناديب
                context['sanitized_final_price'] = summary.final_price
                context['sanitized_tax'] = summary.tax_amount
                context['sanitized_discount'] = summary.discount_amount
        except OrderSummary.DoesNotExist:
            context['summary'] = None
        
        # الحسابات الحالية
        context['current_calculations'] = order.calculations.filter(is_current=True) if can_view_margins else []
        
        # أوامر الشراء المفككة للورش
        from purchase.models import Purchase
        if order.work_order:
            context['unbundled_pos'] = Purchase.objects.filter(work_order=order.work_order).select_related('supplier')
        else:
            context['unbundled_pos'] = Purchase.objects.none()
            
        # فحص بوابة صلاحية أسعار الموردين قبل إصدار أوامر الشراء
        from ..services import ProcurementBridgeService
        context['po_gating'] = ProcurementBridgeService.check_po_gating(order)
        
        return context


def get_active_ctp_suppliers():
    """جلب مراكز زنكات CTP المعتمدة التي لديها خدمات وأسعار زنكات نشطة ومسجلة في النظام حصراً 100%"""
    try:
        from supplier.models import Supplier
        from django.db.models import Q
        return Supplier.objects.filter(
            is_active=True,
            services__service_type__code='ctp_plates',
            services__is_active=True
        ).filter(
            Q(services__base_price__gt=0) |
            Q(services__set_price__gt=0) |
            Q(services__attributes__has_key='price_per_plate') |
            Q(services__attributes__has_key='plate_size')
        ).distinct().order_by('-is_preferred', 'name')
    except Exception:
        return []


def get_active_offset_suppliers():
    """جلب مطابع الأوفست المعتمدة التي لديها خدمات وأسعار طباعة أوفست نشطة ومسجلة في النظام حصراً 100%"""
    try:
        from supplier.models import Supplier
        from django.db.models import Q
        return Supplier.objects.filter(
            is_active=True,
            services__service_type__code='offset_printing',
            services__is_active=True
        ).filter(
            Q(services__base_price__gt=0) |
            Q(services__set_price__gt=0) |
            Q(services__attributes__has_key='price_per_1000') |
            Q(services__attributes__has_key='machine_type') |
            Q(services__attributes__has_key='sheet_size')
        ).distinct().order_by('-is_preferred', 'name')
    except Exception:
        return []


def get_active_digital_suppliers():
    """جلب مراكز الطباعة الديجيتال المعتمدة التي لديها خدمات وأسعار ديجيتال نشطة ومسجلة في النظام حصراً 100%"""
    try:
        from supplier.models import Supplier
        from django.db.models import Q
        return Supplier.objects.filter(
            is_active=True,
            services__service_type__code='digital_printing',
            services__is_active=True
        ).filter(
            Q(services__base_price__gt=0) |
            Q(services__attributes__has_key='price_per_page_bw') |
            Q(services__attributes__has_key='price_per_page_color')
        ).distinct().order_by('-is_preferred', 'name')
    except Exception:
        return []


def get_active_paper_suppliers():
    """جلب تجار وموردي خامات الورق المعتمدين الذين لديهم أصناف وأسعار ورق نشطة ومسجلة في النظام حصراً 100%"""
    try:
        from supplier.models import Supplier
        from django.db.models import Q
        return Supplier.objects.filter(
            is_active=True,
            services__service_type__code='paper',
            services__is_active=True
        ).filter(
            Q(services__base_price__gt=0) |
            Q(services__price_per_ton__gt=0) |
            Q(services__attributes__has_key='price_per_sheet') |
            Q(services__attributes__has_key='paper_type')
        ).distinct().order_by('-is_preferred', 'name')
    except Exception:
        return []


class OrderCreateView(LoginRequiredMixin, CreateView):
    """
    إنشاء طلب تسعير جديد
    """
    model = PrintingOrder
    form_class = PricingOrderForm
    template_name = 'printing_pricing/orders/order_form.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['can_view_margins'] = check_can_view_margins(self.request.user)
        context['page_title'] = _('إنشاء طلب تسعير جديد')
        context['page_subtitle'] = _('تسعير ذكي للمطبوعات والهدايا مع حساب التكلفة التلقائي')
        context['page_icon'] = 'fas fa-plus'
        context['header_buttons'] = [
            {
                'url': reverse('printing_pricing:order_list'),
                'icon': 'fa-arrow-right',
                'text': _('رجوع للقائمة'),
                'class': 'btn-secondary',
            },
        ]
        context['product_types'] = ProductType.objects.filter(is_active=True).order_by('sort_order', 'id')
        context['product_sizes'] = ProductSize.objects.filter(is_active=True).order_by('sort_order', 'id')
        context['ctp_suppliers'] = get_active_ctp_suppliers()
        context['offset_suppliers'] = get_active_offset_suppliers()
        context['digital_suppliers'] = get_active_digital_suppliers()
        
        # تمرير إعدادات الورق الخمسة المعيارية وموردي الورق وباقي إعدادات الطباعة
        context['paper_types'] = PaperType.objects.filter(is_active=True).order_by('name')
        context['paper_sizes'] = PaperSize.objects.filter(is_active=True).order_by('name')
        context['paper_weights'] = PaperWeight.objects.filter(is_active=True).order_by('gsm')
        context['paper_origins'] = PaperOrigin.objects.filter(is_active=True).order_by('name')
        context['piece_sizes'] = PieceSize.objects.filter(is_active=True).select_related('paper_type').order_by('name')
        context['plate_sizes'] = PlateSize.objects.filter(is_active=True).order_by('id')
        context['coating_types'] = CoatingType.objects.filter(is_active=True).order_by('name')
        context['packaging_types'] = PackagingType.objects.filter(is_active=True).order_by('name')
        context['finishing_types'] = FinishingType.objects.filter(is_active=True).order_by('name')
        context['paper_suppliers'] = get_active_paper_suppliers()
        
        from financial.models import Currency
        from financial.services.exchange_rate_service import ExchangeRateService
        func_curr = ExchangeRateService.get_functional_currency()
        context['currencies'] = Currency.objects.filter(is_active=True).order_by('-is_functional', 'code')
        context['functional_currency'] = func_curr
        context['currency_symbol'] = func_curr.symbol if func_curr else 'ج.م'
        context['currency_code'] = func_curr.code if func_curr else 'EGP'

        context['breadcrumb_items'] = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': _('طلبات التسعير'), 'url': reverse('printing_pricing:order_list'), 'icon': 'fas fa-print'},
            {'title': _('إنشاء طلب'), 'active': True},
        ]
        return context
    
    def form_valid(self, form):
        """معالجة النموذج الصحيح وتفكيك بنود الخامات والخدمات ذرياً"""
        form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        
        response = super().form_valid(form)
        
        # تفكيك وتوليد بنود الخامات والخدمات وملخص التكاليف بناءً على معمارية تشريح الشغلانة
        try:
            from ..services.anatomy_persistence_service import OrderAnatomyPersistenceService
            OrderAnatomyPersistenceService.persist_order_anatomy(self.object, self.request.POST)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Error persisting order anatomy: {e}")
            OrderSummary.objects.get_or_create(order=self.object)
        
        messages.success(
            self.request, 
            _('تم إنشاء طلب التسعير {} وتفكيك بنود التشغيل بنجاح').format(self.object.order_number)
        )
        
        return response
    
    def get_success_url(self):
        return reverse('printing_pricing:order_detail', kwargs={'pk': self.object.pk})


class OrderUpdateView(LoginRequiredMixin, UpdateView):
    """
    تحديث طلب التسعير
    """
    model = PrintingOrder
    form_class = PricingOrderForm
    template_name = 'printing_pricing/orders/order_form.html'
    
    def get_queryset(self):
        queryset = super().get_queryset()
        if not (self.request.user.is_superuser or self.request.user.is_staff):
            queryset = queryset.filter(created_by=self.request.user)
        return queryset

    def get_initial(self):
        initial = super().get_initial()
        order = self.get_object()
        from django.db.models import Q
        
        # 1. استرجاع مواصفات الورق المحفوظة (PaperSpecification)
        paper_spec = order.paper_specs.filter(is_active=True).first()
        if paper_spec:
            if paper_spec.paper_type_name:
                pt = PaperType.objects.filter(name__iexact=paper_spec.paper_type_name).first() or PaperType.objects.filter(name__icontains=paper_spec.paper_type_name).first()
                if pt:
                    initial['paper_type'] = pt.id
            initial['paper_weight'] = str(paper_spec.paper_weight)
            
            # تحديد مقاس الفرخ المتطابق مع الأبعاد المسجلة أو الاسم بدقة
            sheet_obj = None
            if paper_spec.paper_size_name:
                sheet_obj = PaperSize.objects.filter(name__iexact=paper_spec.paper_size_name).first() or PaperSize.objects.filter(name__icontains=paper_spec.paper_size_name).first()
            if not sheet_obj and paper_spec.sheet_width and paper_spec.sheet_height:
                w, h = paper_spec.sheet_width, paper_spec.sheet_height
                sheet_obj = PaperSize.objects.filter(
                    (Q(width=w, height=h) | Q(width=h, height=w)) & Q(is_active=True)
                ).first()
            if sheet_obj:
                initial['sheet_size'] = sheet_obj.name
            else:
                initial['sheet_size'] = paper_spec.paper_size_name or '70x100'

            # تحديد مقاس القطع (PieceSize)
            piece_obj = None
            if paper_spec.piece_size:
                p_name = paper_spec.piece_size
                piece_obj = PieceSize.objects.filter(
                    (Q(name__iexact=p_name) | Q(name__icontains=p_name)) & Q(is_active=True)
                ).first()
            if not piece_obj and paper_spec.montage_count:
                piece_obj = PieceSize.objects.filter(pieces_per_sheet=paper_spec.montage_count, is_active=True).first()
            
            if piece_obj:
                initial['piece_size'] = str(piece_obj.id)
            else:
                initial['piece_size'] = paper_spec.piece_size or 'auto'

            initial['paper_price'] = paper_spec.sheet_cost
            initial['montage_count'] = paper_spec.montage_count
            initial['sheets_needed'] = paper_spec.sheets_needed
            initial['total_paper_cost'] = paper_spec.total_paper_cost
        
        # 2. استرجاع بيانات المورد ومصدر الورق والهالك من بنود الخامات
        paper_mat = order.materials.filter(material_type='paper', is_active=True).exclude(material_name__icontains='داخلي').first()
        if not paper_mat:
            paper_mat = order.materials.filter(material_type='paper', is_active=True).first()
        if paper_mat:
            s_info = paper_mat.supplier_info if isinstance(paper_mat.supplier_info, dict) else {}
            if s_info.get('supplier_id'):
                initial['paper_supplier'] = s_info['supplier_id']
            if s_info.get('origin'):
                initial['paper_origin'] = s_info['origin']
            if s_info.get('source'):
                initial['paper_source'] = s_info['source']
            if s_info.get('sheets_per_pack'):
                initial['sheets_per_pack'] = s_info['sheets_per_pack']
            if not initial.get('paper_type') and s_info.get('paper_type_id'):
                initial['paper_type'] = s_info['paper_type_id']
            if s_info.get('waste_sheets') is not None:
                initial['waste_sheets'] = s_info['waste_sheets']
            elif paper_spec and paper_mat.quantity and paper_spec.sheets_needed:
                waste = int(paper_mat.quantity) - int(paper_spec.sheets_needed)
                if waste >= 0:
                    initial['waste_sheets'] = waste

        # 3. استرجاع بنود زنكات CTP للغلاف
        ctp_srv = order.services.filter(is_active=True).filter(
            Q(service_name__icontains='زنك') | Q(service_name__icontains='ctp')
        ).exclude(service_name__icontains='داخلي').first()
        if ctp_srv:
            initial['plate_count'] = int(ctp_srv.quantity)
            initial['zinc_plates_count'] = int(ctp_srv.quantity)
            initial['plates_total'] = int(ctp_srv.quantity)
            initial['plate_price'] = ctp_srv.unit_price
            s_info = ctp_srv.supplier_info if isinstance(ctp_srv.supplier_info, dict) else {}
            if s_info.get('supplier_id'):
                initial['cover_ctp_supplier'] = s_info['supplier_id']
            elif ctp_srv.supplier_service and ctp_srv.supplier_service.supplier_id:
                initial['cover_ctp_supplier'] = ctp_srv.supplier_service.supplier_id
            
            bed_size = s_info.get('bed_size')
            if bed_size:
                initial['press_bed_size'] = bed_size
            else:
                for ps in PlateSize.objects.filter(is_active=True):
                    if ps.name in ctp_srv.service_name or f"{ps.width}" in ctp_srv.service_name:
                        initial['press_bed_size'] = ps.code or ps.name
                        break
            
            if s_info.get('front_plates') is not None:
                initial['plate_count_front'] = s_info['front_plates']
            if s_info.get('back_plates') is not None:
                initial['plate_count_back'] = s_info['back_plates']
            if s_info.get('is_archived'):
                initial['is_plates_archived'] = True
                initial['plates_option'] = 'archived'
            elif s_info.get('plates_option'):
                initial['plates_option'] = s_info['plates_option']

        # 4. استرجاع بنود سحب وطباعة الأوفست للغلاف
        press_srv = order.services.filter(service_category='printing', is_active=True).filter(
            Q(service_name__icontains='سحب') | Q(service_name__icontains='أوفست') | Q(service_name__icontains='تراج')
        ).exclude(id=ctp_srv.id if ctp_srv else 0).exclude(service_name__icontains='داخلي').first()
        if press_srv:
            initial['press_rate'] = press_srv.unit_price
            s_info = press_srv.supplier_info if isinstance(press_srv.supplier_info, dict) else {}
            if s_info.get('supplier_id'):
                initial['cover_offset_supplier'] = s_info['supplier_id']
            elif press_srv.supplier_service and press_srv.supplier_service.supplier_id:
                initial['cover_offset_supplier'] = press_srv.supplier_service.supplier_id
            
            if s_info.get('machine'):
                initial['cover_press_machine'] = s_info['machine']
            if not initial.get('press_bed_size') and s_info.get('bed_size'):
                initial['press_bed_size'] = s_info['bed_size']

        # 5. استرجاع بنود الديجيتال والخامات الكبيرة إن وجدت
        digital_srv = order.services.filter(service_category='printing', is_active=True).filter(
            Q(service_name__icontains='ديجيتال') | Q(service_name__icontains='digital')
        ).exclude(service_name__icontains='داخلي').first()
        if digital_srv:
            initial['digital_sheet_price'] = digital_srv.unit_price
            s_info = digital_srv.supplier_info if isinstance(digital_srv.supplier_info, dict) else {}
            if s_info.get('supplier_id'):
                initial['cover_digital_supplier'] = s_info['supplier_id']

        # 6. استرجاع السلوفان والطلاء
        coat_srv = order.services.filter(service_category='coating', is_active=True).first()
        if coat_srv:
            initial['coating_type'] = coat_srv.coating_type_id or getattr(order, 'coating_type_id', None)
            if not initial.get('coating_type') and coat_srv.service_name:
                ct = CoatingType.objects.filter(name__icontains=coat_srv.service_name).first()
                if ct:
                    initial['coating_type'] = ct.id
            sup_inf = coat_srv.supplier_info if isinstance(coat_srv.supplier_info, dict) else {}
            lam_val = sup_inf.get('lamination_type')
            if lam_val:
                initial['lamination'] = lam_val
            elif 'وجهين' in coat_srv.service_name or '2_sides' in coat_srv.service_name:
                initial['lamination'] = 'matte_2_sides' if 'مط' in coat_srv.service_name else 'gloss_2_sides'
            else:
                initial['lamination'] = 'matte_1_side' if 'مط' in coat_srv.service_name else 'gloss_1_side'

        # 7. استرجاع خدمات التشطيب
        fin_srvs = order.services.filter(service_category='finishing', is_active=True)
        initial['finishing_services'] = list(fin_srvs)
        initial['finishing_type_ids'] = [f.finishing_type_id for f in fin_srvs if f.finishing_type_id]
        
        for fin in fin_srvs:
            code = getattr(fin.finishing_type, 'code', '').lower() if fin.finishing_type else ''
            f_name = fin.service_name.lower()
            if code in ['spot_uv', 'uv'] or 'spot' in f_name or 'سبوت' in f_name or 'uv' in f_name:
                initial['has_spot_uv'] = True
                if 'finishing' not in initial:
                    initial['finishing'] = 'spot_uv'
            elif code in ['foil', 'hot_stamp'] or 'بصمة' in f_name or 'foil' in f_name:
                initial['has_foil'] = True
                if 'finishing' not in initial:
                    initial['finishing'] = 'foil'
            elif code in ['emboss', 'deboss'] or 'كوفراج' in f_name or 'emboss' in f_name:
                initial['has_emboss'] = True
                if 'finishing' not in initial:
                    initial['finishing'] = 'emboss'
            elif code in ['die_cut', 'cutting'] or 'تكسير' in f_name or 'die' in f_name:
                initial['has_die_cut'] = True

        pack_srv = order.services.filter(service_category='packaging', is_active=True).first()
        if pack_srv:
            initial['giveaway_packaging_box'] = pack_srv.service_name

        if order.binding_type:
            initial['binding_type'] = order.binding_type

        # 8. استرجاع بيانات الداخلي والتجليد للكتب والكتالوجات
        inner_mat = order.materials.filter(material_type='paper', material_name__icontains='داخلي', is_active=True).first()
        if inner_mat:
            initial['inner_sheet_price'] = inner_mat.unit_cost
            if isinstance(inner_mat.supplier_info, dict):
                if inner_mat.supplier_info.get('supplier_id'):
                    initial['inner_paper_supplier'] = inner_mat.supplier_info['supplier_id']
                if inner_mat.supplier_info.get('inner_sheet_size'):
                    initial['inner_sheet_size'] = inner_mat.supplier_info['inner_sheet_size']

        inner_ctp = order.services.filter(service_category='printing', service_name__icontains='داخلي', is_active=True).filter(
            Q(service_name__icontains='زنك') | Q(service_name__icontains='ctp')
        ).first()
        if inner_ctp:
            initial['inner_plate_price'] = inner_ctp.unit_price
            s_info = inner_ctp.supplier_info if isinstance(inner_ctp.supplier_info, dict) else {}
            if s_info.get('supplier_id'):
                initial['inner_ctp_supplier'] = s_info['supplier_id']
            if s_info.get('bed_size'):
                initial['inner_press_bed_size'] = s_info['bed_size']

        inner_press = order.services.filter(service_category='printing', service_name__icontains='داخلي', is_active=True).filter(
            Q(service_name__icontains='سحب') | Q(service_name__icontains='أوفست')
        ).first()
        if inner_press:
            initial['inner_press_rate'] = inner_press.unit_price
            s_info = inner_press.supplier_info if isinstance(inner_press.supplier_info, dict) else {}
            if s_info.get('supplier_id'):
                initial['inner_offset_supplier'] = s_info['supplier_id']

        # 9. ملخص التكاليف والأسعار
        try:
            summary = order.summary
            if summary:
                initial['material_cost'] = summary.material_cost
                initial['printing_cost'] = summary.printing_cost
                initial['finishing_cost'] = summary.finishing_cost
                initial['extra_cost'] = summary.other_costs
                initial['final_price'] = summary.final_price
        except Exception:
            pass

        return initial
        
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = self.object
        initial = self.get_initial()
        from django.db.models import Q
        
        context['can_view_margins'] = check_can_view_margins(self.request.user)
        context['page_title'] = _('تعديل طلب التسعير {}').format(order.order_number)
        context['page_subtitle'] = _('تعديل المواصفات والخامات والخدمات')
        context['page_icon'] = 'fas fa-edit'
        context['header_buttons'] = [
            {
                'url': reverse('printing_pricing:order_detail', kwargs={'pk': order.pk}),
                'icon': 'fa-eye',
                'text': _('عرض التفاصيل'),
                'class': 'btn-info',
            },
        ]
        context['product_types'] = ProductType.objects.filter(is_active=True).order_by('sort_order', 'id')
        context['product_sizes'] = ProductSize.objects.filter(is_active=True).order_by('sort_order', 'id')
        context['ctp_suppliers'] = get_active_ctp_suppliers()
        context['offset_suppliers'] = get_active_offset_suppliers()
        context['digital_suppliers'] = get_active_digital_suppliers()
        
        context['paper_types'] = PaperType.objects.filter(is_active=True).order_by('name')
        context['paper_sizes'] = PaperSize.objects.filter(is_active=True).order_by('name')
        context['paper_weights'] = PaperWeight.objects.filter(is_active=True).order_by('gsm')
        context['paper_origins'] = PaperOrigin.objects.filter(is_active=True).order_by('name')
        context['piece_sizes'] = PieceSize.objects.filter(is_active=True).select_related('paper_type').order_by('name')
        context['plate_sizes'] = PlateSize.objects.filter(is_active=True).order_by('id')
        context['coating_types'] = CoatingType.objects.filter(is_active=True).order_by('name')
        context['packaging_types'] = PackagingType.objects.filter(is_active=True).order_by('name')
        context['finishing_types'] = FinishingType.objects.filter(is_active=True).order_by('name')
        context['paper_suppliers'] = get_active_paper_suppliers()
        
        # استرجاع ملخص التكاليف والمواصفات للحقن المباشر في القالب
        paper_spec = order.paper_specs.filter(is_active=True).first()
        context['saved_paper_spec'] = paper_spec
        
        ctp_srv = order.services.filter(is_active=True).filter(
            Q(service_name__icontains='زنك') | Q(service_name__icontains='ctp')
        ).exclude(service_name__icontains='داخلي').first()
        
        press_srv = order.services.filter(service_category='printing', is_active=True).filter(
            Q(service_name__icontains='سحب') | Q(service_name__icontains='أوفست') | Q(service_name__icontains='تراج')
        ).exclude(id=ctp_srv.id if ctp_srv else 0).exclude(service_name__icontains='داخلي').first()

        inner_press = order.services.filter(service_category='printing', service_name__icontains='داخلي', is_active=True).filter(
            Q(service_name__icontains='سحب') | Q(service_name__icontains='أوفست')
        ).first()

        inner_ctp = order.services.filter(is_active=True, service_name__icontains='داخلي').filter(
            Q(service_name__icontains='زنك') | Q(service_name__icontains='ctp')
        ).first()

        try:
            summary = getattr(order, 'summary', None)
        except Exception:
            summary = None

        if not summary:
            # ضمان استرجاع 100% من التكاليف والأرقام من مواد وخدمات الطلب حتى مع غياب جدول summary
            mat_cost = sum([m.total_cost for m in order.materials.filter(is_active=True)]) or Decimal('0.00')
            prt_cost = sum([s.total_cost for s in order.services.filter(service_category='printing', is_active=True)]) or Decimal('0.00')
            fin_cost = sum([s.total_cost for s in order.services.filter(service_category__in=['finishing', 'coating', 'packaging'], is_active=True)]) or Decimal('0.00')
            other_cost = getattr(order, 'extra_cost', Decimal('0.00')) or Decimal('0.00')
            tot_cost = mat_cost + prt_cost + fin_cost + other_cost
            final_prc = order.final_price or Decimal('0.00')
            profit_amt = max(Decimal('0.00'), final_prc - tot_cost)
            summary = {
                'material_cost': mat_cost,
                'printing_cost': prt_cost,
                'finishing_cost': fin_cost,
                'binding_cost': Decimal('0.00'),
                'other_costs': other_cost,
                'total_cost': tot_cost,
                'profit_amount': profit_amt,
                'final_price': final_prc
            }
        context['summary'] = summary

        # تمرير المتغيرات المسترجعة للقوالب الجزئية
        context['saved_sheet_size'] = initial.get('sheet_size')
        context['saved_piece_size_id'] = initial.get('piece_size')
        context['saved_press_rate'] = initial.get('press_rate')
        context['saved_plate_price'] = initial.get('plate_price')
        context['saved_cover_offset_supplier_id'] = initial.get('cover_offset_supplier')
        context['saved_cover_ctp_supplier_id'] = initial.get('cover_ctp_supplier')
        context['saved_press_bed_size'] = initial.get('press_bed_size')
        context['saved_cover_press_machine'] = initial.get('cover_press_machine')
        context['saved_cover_press_cost'] = press_srv.total_cost if press_srv else Decimal('0.00')
        context['saved_cover_ctp_cost'] = ctp_srv.total_cost if ctp_srv else Decimal('0.00')
        context['saved_waste_sheets'] = initial.get('waste_sheets', 20)
        context['saved_pulls_count'] = press_srv.quantity * 1000 if press_srv else 1000

        # قيم الداخلي
        context['saved_inner_sheet_price'] = initial.get('inner_sheet_price')
        context['saved_inner_press_rate'] = initial.get('inner_press_rate')
        context['saved_inner_plate_price'] = initial.get('inner_plate_price')
        context['saved_inner_offset_supplier_id'] = initial.get('inner_offset_supplier')
        context['saved_inner_ctp_supplier_id'] = initial.get('inner_ctp_supplier')
        context['saved_inner_press_cost'] = inner_press.total_cost if inner_press else Decimal('0.00')
        context['saved_inner_ctp_cost'] = inner_ctp.total_cost if inner_ctp else Decimal('0.00')
        
        from financial.models import Currency
        from financial.services.exchange_rate_service import ExchangeRateService
        func_curr = ExchangeRateService.get_functional_currency()
        context['currencies'] = Currency.objects.filter(is_active=True).order_by('-is_functional', 'code')
        context['functional_currency'] = func_curr
        context['currency_symbol'] = order.currency_symbol
        context['currency_code'] = order.currency_code

        context['breadcrumb_items'] = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': _('طلبات التسعير'), 'url': reverse('printing_pricing:order_list'), 'icon': 'fas fa-print'},
            {'title': order.order_number, 'url': reverse('printing_pricing:order_detail', kwargs={'pk': order.pk})},
            {'title': _('تعديل'), 'active': True},
        ]
        return context
    
    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        response = super().form_valid(form)
        
        # تسجيل أي تعديل يدوي في السعر النهائي في سجل التدقيق المالي
        old_price = form.initial.get('final_price')
        new_price = form.cleaned_data.get('final_price')
        if old_price is not None and new_price is not None and old_price != new_price:
            try:
                from ..services.price_audit_service import PriceAuditService
                PriceAuditService.log_price_change(
                    order=self.object,
                    field_name='final_price',
                    old_value=old_price,
                    new_value=new_price,
                    reason=self.request.POST.get('price_override_reason', 'تعديل يدوي للسعر النهائي'),
                    user=self.request.user
                )
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Error logging price audit: {e}")

        # تفكيك وتوليد بنود الخامات والخدمات وملخص التكاليف بناءً على معمارية تشريح الشغلانة
        try:
            from ..services.anatomy_persistence_service import OrderAnatomyPersistenceService
            OrderAnatomyPersistenceService.persist_order_anatomy(self.object, self.request.POST)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Error persisting order anatomy on update: {e}")
            OrderSummary.objects.get_or_create(order=self.object)
        
        messages.success(
            self.request,
            _('تم تحديث طلب التسعير {} وتحديث بنود التشغيل بنجاح').format(self.object.order_number)
        )
        return response
    
    def get_success_url(self):
        return reverse('printing_pricing:order_detail', kwargs={'pk': self.object.pk})



class OrderDeleteView(LoginRequiredMixin, DeleteView):
    """
    حذف طلب التسعير (حذف منطقي)
    """
    model = PrintingOrder
    template_name = 'printing_pricing/orders/order_detail.html'
    success_url = reverse_lazy('printing_pricing:order_list')

    def get_queryset(self):
        queryset = super().get_queryset()
        if not (self.request.user.is_superuser or self.request.user.is_staff):
            queryset = queryset.filter(created_by=self.request.user)
        return queryset

    def get(self, request, *args, **kwargs):
        """GET request يعمل redirect للقائمة - الحذف يتم بـ POST فقط"""
        return HttpResponseRedirect(self.success_url)

    def delete(self, request, *args, **kwargs):
        """حذف منطقي بدلاً من الحذف الفعلي"""
        self.object = self.get_object()
        
        # حذف منطقي
        self.object.is_active = False
        self.object.updated_by = request.user
        self.object.save()
        
        messages.success(
            request,
            _('تم حذف طلب التسعير {} بنجاح').format(self.object.order_number)
        )
        
        return HttpResponseRedirect(self.get_success_url())


class DashboardView(LoginRequiredMixin, TemplateView):
    """لوحة تحكم مؤشرات الأداء لتسعير المطبوعات والهدايا"""
    template_name = 'printing_pricing/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        total_orders = PrintingOrder.objects.filter(is_active=True).count()
        pending_orders = PrintingOrder.objects.filter(status='pending', is_active=True).count()
        completed_orders = PrintingOrder.objects.filter(status='completed', is_active=True).count()
        total_rev = PrintingOrder.objects.filter(is_active=True).aggregate(t=Sum('final_price'))['t'] or Decimal('0.00')

        context['stats'] = {
            'total_orders': total_orders,
            'pending_orders': pending_orders,
            'completed_orders': completed_orders,
            'total_revenue': total_rev
        }
        context['recent_orders'] = PrintingOrder.objects.filter(is_active=True).select_related('customer').order_by('-created_at')[:10]
        context['page_title'] = 'لوحة التحكم - تسعير المطبوعات'
        context['page_subtitle'] = 'مؤشرات الأداء ومقايسات الطباعة والهدايا'
        context['page_icon'] = 'fas fa-chart-line'
        context['breadcrumb_items'] = [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'تسعير المطبوعات', 'active': True},
        ]
        return context


def dashboard_redirect(request):
    """عرض لوحة التحكم"""
    return DashboardView.as_view()(request)



# دوال مساعدة للعمليات السريعة

def _has_order_permission(user, order):
    if user.is_superuser or getattr(user, 'is_staff', False):
        return True
    return order.created_by == user


@login_required
def calculate_order_cost(request, pk):
    """
    حساب تكلفة الطلب وتحديث ملخص التكاليف وحساب التكلفة ذرياً
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': _('طريقة غير مسموحة')})
    
    try:
        order = get_object_or_404(PrintingOrder, pk=pk, is_active=True)
        
        # التحقق من الصلاحية (IDOR)
        if not _has_order_permission(request.user, order):
            return JsonResponse({'success': False, 'error': _('غير مصرح لك بحساب تكلفة هذا الطلب')}, status=403)
        
        from ..services import OrderAnatomyPersistenceService
        
        with transaction.atomic():
            summary = OrderAnatomyPersistenceService.persist_order_anatomy(order, {})
            if not summary:
                return JsonResponse({'success': False, 'error': _('فشل في حساب التكلفة')})
            
            cost = summary.total_cost or order.estimated_cost or Decimal('0.00')
            final_p = summary.final_price or order.final_price or Decimal('0.00')
            margin_pct = summary.profit_margin_percentage or order.profit_margin or Decimal('0.00')
            profit_amt = summary.net_profit or summary.profit_amount or (final_p - cost)
            qty = Decimal(str(order.quantity or 1))
            cost_unit = (cost / qty).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
            price_unit = (final_p / qty).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)

        return JsonResponse({
            'success': True,
            'message': _('تم حساب التكلفة والربحية بنجاح'),
            'order_id': order.id,
            'estimated_cost': float(cost),
            'final_price': float(final_p),
            'cost_per_unit': float(cost_unit),
            'price_per_unit': float(price_unit),
            'profit_margin': float(margin_pct),
            'profit_amount': float(profit_amt)
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': _('حدث خطأ أثناء حساب التكلفة: {}').format(str(e))
        })



@login_required
def approve_order(request, pk):
    """
    اعتماد الطلب
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': _('طريقة غير مسموحة')})
    
    try:
        order = get_object_or_404(PrintingOrder, pk=pk, is_active=True)
        
        # التحقق من الصلاحية (IDOR)
        if not _has_order_permission(request.user, order):
            return JsonResponse({'success': False, 'error': _('غير مصرح لك باعتماد هذا الطلب')}, status=403)
        
        # التحقق من صحة واكتمال الطلب قبل الاعتماد
        from ..services import OrderValidator
        validator = OrderValidator()
        validation_result = validator.validate_order_for_approval(order, user=request.user)
        if not validation_result.get('success') or not validation_result.get('can_approve'):
            err_msg = ', '.join([str(e) for e in validation_result.get('errors', [])])
            return JsonResponse({
                'success': False,
                'error': _('لا يمكن اعتماد الطلب: ') + err_msg
            }, status=400)
        
        # تحديث حالة الطلب
        old_status, new_status = order.update_status('approved', request.user)
        
        # توليد أمر الشغل التنفيذي لصالة الإنتاج بعد الاعتماد
        order.create_work_order(user=request.user)
        
        messages.success(
            request,
            _('تم اعتماد طلب التسعير {} بنجاح').format(order.order_number)
        )
        
        return JsonResponse({
            'success': True,
            'message': _('تم اعتماد الطلب بنجاح'),
            'old_status': old_status,
            'new_status': new_status
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': _('حدث خطأ أثناء اعتماد الطلب: {}').format(str(e))
        })


@login_required
def duplicate_order(request, pk):
    """
    نسخ الطلب
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': _('طريقة غير مسموحة')})
    
    try:
        original_order = get_object_or_404(PrintingOrder, pk=pk, is_active=True)
        
        # التحقق من الصلاحية (IDOR)
        if not _has_order_permission(request.user, original_order):
            return JsonResponse({'success': False, 'error': _('غير مصرح لك بنسخ هذا الطلب')}, status=403)
        
        # إنشاء نسخة جديدة داخل معاملة ذرية
        with transaction.atomic():
            new_order = PrintingOrder.objects.create(
                customer=original_order.customer,
                title=f"{original_order.title} - نسخة",
                description=original_order.description,
                product_type=original_order.product_type,
                order_type=original_order.order_type,
                product_size=original_order.product_size,
                print_orientation=original_order.print_orientation,
                is_closed_size=original_order.is_closed_size,
                open_direction=original_order.open_direction,
                quantity=original_order.quantity,
                pages_count=original_order.pages_count,
                copies_count=original_order.copies_count,
                width=original_order.width,
                height=original_order.height,
                profit_margin=original_order.profit_margin,
                currency=original_order.currency,
                exchange_rate=original_order.exchange_rate,
                design_service_type=original_order.design_service_type,
                design_fee=original_order.design_fee,
                sales_rep=original_order.sales_rep,
                sales_commission_rate=original_order.sales_commission_rate,
                created_by=request.user,
                updated_by=request.user
            )
            
            # نسخ مواصفات الورق
            for p_spec in original_order.paper_specs.filter(is_active=True):
                PaperSpecification.objects.create(
                    order=new_order,
                    paper_type_name=p_spec.paper_type_name,
                    paper_weight=p_spec.paper_weight,
                    paper_size_name=p_spec.paper_size_name,
                    sheet_width=p_spec.sheet_width,
                    sheet_height=p_spec.sheet_height,
                    sheets_needed=p_spec.sheets_needed,
                    montage_count=p_spec.montage_count,
                    piece_size=p_spec.piece_size,
                    sheet_cost=p_spec.sheet_cost,
                    total_paper_cost=p_spec.total_paper_cost,
                    created_by=request.user
                )
                

            # نسخ المواد
            for material in original_order.materials.filter(is_active=True):
                OrderMaterial.objects.create(
                    order=new_order,
                    material_type=material.material_type,
                    material_name=material.material_name,
                    quantity=material.quantity,
                    unit=material.unit,
                    unit_cost=material.unit_cost,
                    waste_percentage=material.waste_percentage,
                    created_by=request.user
                )
            
            # نسخ الخدمات مع الحفاظ على ارتباط المورد ولقطة البيانات
            for service in original_order.services.filter(is_active=True):
                OrderService.objects.create(
                    order=new_order,
                    service_category=service.service_category,
                    service_name=service.service_name,
                    service_description=service.service_description,
                    quantity=service.quantity,
                    unit=service.unit,
                    unit_price=service.unit_price,
                    setup_cost=service.setup_cost,
                    total_cost=service.total_cost,
                    is_optional=service.is_optional,
                    supplier_service=service.supplier_service,
                    supplier_info=service.supplier_info,
                    execution_time=service.execution_time,
                    created_by=request.user
                )
            
            # إنشاء ملخص للطلب الجديد
            OrderSummary.objects.create(order=new_order)
        
        messages.success(
            request,
            _('تم نسخ الطلب بنجاح. رقم الطلب الجديد: {}').format(new_order.order_number)
        )
        
        return JsonResponse({
            'success': True,
            'message': _('تم نسخ الطلب بنجاح'),
            'new_order_id': new_order.id,
            'new_order_number': new_order.order_number,
            'redirect_url': reverse('printing_pricing:order_detail', kwargs={'pk': new_order.pk})
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': _('حدث خطأ أثناء نسخ الطلب: {}').format(str(e))
        })


__all__ = [
    'OrderListView', 'OrderDetailView', 'OrderCreateView', 
    'OrderUpdateView', 'OrderDeleteView', 'dashboard_redirect',
    'calculate_order_cost', 'approve_order', 'duplicate_order'
]
