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
from decimal import Decimal

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


class OrderDetailView(LoginRequiredMixin, DetailView):
    """
    عرض تفاصيل طلب التسعير ومركز الأرباح 360 درجة
    """
    model = PrintingOrder
    template_name = 'printing_pricing/orders/order_detail.html'
    context_object_name = 'order'
    
    def get_queryset(self):
        """تحسين الاستعلام"""
        queryset = PrintingOrder.objects.select_related(
            'customer', 'created_by', 'updated_by', 'currency', 'work_order'
        ).prefetch_related(
            'materials', 'services', 'calculations', 'paper_specs'
        )
        if not (self.request.user.is_superuser or self.request.user.is_staff):
            queryset = queryset.filter(created_by=self.request.user)
        return queryset
    
    def get_context_data(self, **kwargs):
        """إضافة بيانات إضافية لمركز التكلفة والأرباح 360 درجة"""
        context = super().get_context_data(**kwargs)
        order = self.object
        user = self.request.user
        can_view_margins = check_can_view_margins(user)
        context['can_view_margins'] = can_view_margins
        
        # المواد والخدمات
        context['materials'] = order.materials.filter(is_active=True)
        context['services'] = order.services.filter(is_active=True)
        
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
            
        context['can_convert_to_work_order'] = not order.work_order and order.status in ['approved', 'completed']
        
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
            Q(services__attributes__has_key='price_per_plate') |
            Q(services__attributes__has_key='plate_size')
        ).distinct().order_by('name')
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
            Q(services__attributes__has_key='price_per_1000') |
            Q(services__attributes__has_key='machine_type') |
            Q(services__attributes__has_key='sheet_size')
        ).distinct().order_by('name')
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
        ).distinct().order_by('name')
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
            Q(services__attributes__has_key='price_per_sheet') |
            Q(services__attributes__has_key='paper_type')
        ).distinct().order_by('name')
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
        
        # استرجاع مواصفات الورق المحفوظة
        paper_spec = order.paper_specs.filter(is_active=True).first()
        if paper_spec:
            if order.paper_type_id:
                initial['paper_type'] = order.paper_type_id
            initial['paper_weight'] = paper_spec.paper_weight
            initial['sheet_size'] = paper_spec.paper_size_name or '70x100'
            initial['piece_size'] = paper_spec.piece_size
            initial['paper_price'] = paper_spec.sheet_cost
        
        # استرجاع بيانات المورد ومصدر الورق من بنود الخامات
        paper_mat = order.materials.filter(material_type='paper', is_active=True).first()
        if paper_mat and isinstance(paper_mat.supplier_info, dict):
            if 'supplier_id' in paper_mat.supplier_info:
                initial['paper_supplier'] = paper_mat.supplier_info.get('supplier_id')
            if 'origin' in paper_mat.supplier_info:
                initial['paper_origin'] = paper_mat.supplier_info.get('origin')
            if 'source' in paper_mat.supplier_info:
                initial['paper_source'] = paper_mat.supplier_info.get('source')

        # استرجاع بنود الخدمات المحفوظة (زنكات، سلوفان، تشطيب، تغليف)
        ctp_srv = order.services.filter(service_category='printing', service_name__icontains='زنك', is_active=True).first()
        if not ctp_srv:
            ctp_srv = order.services.filter(service_name__icontains='ctp', is_active=True).first()
        if ctp_srv:
            initial['plate_count'] = ctp_srv.quantity
            initial['plate_price'] = ctp_srv.unit_price
            for ps in PlateSize.objects.filter(is_active=True):
                if ps.name in ctp_srv.service_name or (f"{ps.width}" in ctp_srv.service_name):
                    initial['press_bed_size'] = ps.name
                    break

        coat_srv = order.services.filter(service_category='coating', is_active=True).first()
        if coat_srv:
            initial['coating_type'] = coat_srv.coating_type_id or order.coating_type_id
            sup_inf = coat_srv.supplier_info if isinstance(coat_srv.supplier_info, dict) else {}
            lam_val = sup_inf.get('lamination_type')
            if lam_val:
                initial['lamination'] = lam_val
            elif 'وجهين' in coat_srv.service_name or '2_sides' in coat_srv.service_name:
                initial['lamination'] = 'matte_2_sides' if 'مط' in coat_srv.service_name else 'gloss_2_sides'
            else:
                initial['lamination'] = 'matte_1_side' if 'مط' in coat_srv.service_name else 'gloss_1_side'

        # استرجاع كافة خدمات التشطيب المتعددة بالمعرفات الهيكلية أولاً
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

        return initial
        
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['can_view_margins'] = check_can_view_margins(self.request.user)
        context['page_title'] = _('تعديل طلب التسعير {}').format(self.object.order_number)
        context['page_subtitle'] = _('تعديل المواصفات والخامات والخدمات')
        context['page_icon'] = 'fas fa-edit'
        context['header_buttons'] = [
            {
                'url': reverse('printing_pricing:order_detail', kwargs={'pk': self.object.pk}),
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
        context['saved_paper_spec'] = self.object.paper_specs.filter(is_active=True).first()
        
        from financial.models import Currency
        from financial.services.exchange_rate_service import ExchangeRateService
        func_curr = ExchangeRateService.get_functional_currency()
        context['currencies'] = Currency.objects.filter(is_active=True).order_by('-is_functional', 'code')
        context['functional_currency'] = func_curr
        context['currency_symbol'] = self.object.currency_symbol
        context['currency_code'] = self.object.currency_code

        context['breadcrumb_items'] = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': _('طلبات التسعير'), 'url': reverse('printing_pricing:order_list'), 'icon': 'fas fa-print'},
            {'title': self.object.order_number, 'url': reverse('printing_pricing:order_detail', kwargs={'pk': self.object.pk})},
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
            
            subtotal = summary.subtotal or summary.total_cost or Decimal('0.00')
            final_p = summary.final_price or Decimal('0.00')
            margin_pct = summary.profit_margin_percentage or Decimal('0.00')
            profit_amt = summary.profit_amount or Decimal('0.00')
            qty = Decimal(str(order.quantity or 1))
            cost_unit = (subtotal / qty).quantize(Decimal('0.0001'))
            price_unit = (final_p / qty).quantize(Decimal('0.0001'))

        return JsonResponse({
            'success': True,
            'message': _('تم حساب التكلفة والربحية بنجاح'),
            'order_id': order.id,
            'estimated_cost': float(subtotal),
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
