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
    PaperSpecification, PrintingSpecification, PricingStatus, OrderType,
    ProductType, ProductSize
)
from ..forms import PrintingOrderForm, OrderSearchForm
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
        
        return context

    def render_to_response(self, context, **response_kwargs):
        if self.request.headers.get("X-Requested-With") == "XMLHttpRequest" or self.request.GET.get("ajax"):
            table_html = render_to_string(
                "printing_pricing/orders/partials/order_table.html",
                context,
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
            'customer', 'created_by', 'updated_by', 'currency', 'current_workshop', 'work_order', 'qc_signoff'
        ).prefetch_related(
            'materials', 'services', 'calculations', 'transport_logs', 'vendor_advances', 'used_moulds', 'remakes'
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
        
        # سجل حركة ونقل الشغل ومكلف النقل
        context['transport_logs'] = order.transport_logs.select_related('transporter').all()
        
        # أوامر الشراء المفككة للورش
        from purchase.models import Purchase
        if order.work_order:
            context['unbundled_pos'] = Purchase.objects.filter(work_order=order.work_order).select_related('supplier')
        else:
            context['unbundled_pos'] = Purchase.objects.none()
            
        # العهد والفورمات والجودة والتعويضات والعرابين
        context['die_moulds'] = order.used_moulds.all()
        context['qc_signoff'] = getattr(order, 'qc_signoff', None)
        context['remakes'] = order.remakes.all()
        context['advances'] = order.vendor_advances.select_related('supplier').all()



        
        # حالة صمام الإطلاق لأمر الشغل
        proof_approved = hasattr(order, 'proof_signoff') and order.proof_signoff.status == 'approved'
        context['proof_approved'] = proof_approved
        context['can_convert_to_work_order'] = not order.work_order and order.status in ['approved', 'completed']
        
        return context


class OrderCreateView(LoginRequiredMixin, CreateView):
    """
    إنشاء طلب تسعير جديد
    """
    model = PrintingOrder
    form_class = PrintingOrderForm
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
    form_class = PrintingOrderForm
    template_name = 'printing_pricing/orders/order_form.html'
    
    def get_queryset(self):
        queryset = super().get_queryset()
        if not (self.request.user.is_superuser or self.request.user.is_staff):
            queryset = queryset.filter(created_by=self.request.user)
        return queryset
        
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
        
        from ..models import CostCalculation, CalculationType
        from ..services.calculators import BaseCalculator
        
        with transaction.atomic():
            calculator = BaseCalculator(order)
            result = calculator.calculate(CalculationType.TOTAL)
            
            if not result.get('success'):
                return JsonResponse({'success': False, 'error': result.get('error', _('فشل في حساب التكلفة'))})
            
            details = result.get('details', {})
            mat_cost = Decimal(str(details.get('material_cost', 0)))
            print_cost = Decimal(str(details.get('printing_cost', 0)))
            fin_cost = Decimal(str(details.get('finishing_cost', 0)))
            des_cost = Decimal(str(details.get('design_cost', 0)))
            other_cost = Decimal(str(details.get('installation_cost', 0))) + Decimal(str(details.get('logistics_cost', 0)))
            
            subtotal = Decimal(str(result.get('total_cost', 0)))
            disc_amt = Decimal(str(details.get('discount_amount', 0)))
            tax_amt = Decimal(str(details.get('tax_amount', 0)))
            rush_f = Decimal(str(details.get('rush_fee', 0)))
            final_p = Decimal(str(result.get('final_price', 0)))
            margin_pct = Decimal(str(details.get('profit_margin', 20)))
            profit_amt = max(Decimal('0.00'), final_p - subtotal)
            
            import json
            from django.core.serializers.json import DjangoJSONEncoder

            qty = max(1, order.quantity or 1)
            cost_unit = (subtotal / Decimal(str(qty))).quantize(Decimal('0.0001'))
            price_unit = (final_p / Decimal(str(qty))).quantize(Decimal('0.0001'))
            
            # تحديث أو إنشاء ملخص الطلب OrderSummary
            summary, summary_created = OrderSummary.objects.get_or_create(order=order)
            summary.material_cost = mat_cost
            summary.printing_cost = print_cost
            summary.finishing_cost = fin_cost
            summary.design_cost = des_cost
            summary.other_costs = other_cost
            summary.subtotal = subtotal
            summary.discount_amount = disc_amt
            summary.tax_amount = tax_amt
            summary.rush_fee = rush_f
            summary.total_cost = subtotal
            summary.profit_margin_percentage = margin_pct
            summary.profit_amount = profit_amt
            summary.final_price = final_p
            summary.cost_per_unit = cost_unit
            summary.price_per_unit = price_unit
            summary.save()
            
            # تحويل تفاصيل الحساب إلى JSON آمن
            json_safe_details = json.loads(json.dumps(details, cls=DjangoJSONEncoder))
            
            # تحديث أو إنشاء سجل حساب التكلفة CostCalculation
            CostCalculation.objects.update_or_create(
                order=order,
                calculation_type=CalculationType.TOTAL,
                is_current=True,
                defaults={
                    'base_cost': subtotal,
                    'additional_costs': tax_amt + rush_f - disc_amt,
                    'total_cost': subtotal,
                    'calculation_details': json_safe_details,
                    'created_by': request.user
                }
            )
            
            # تحديث الحقول على رأس أمر التسعير
            order.estimated_cost = subtotal
            order.final_price = final_p
            order.sale_price = final_p
            order.profit_margin = margin_pct
            order.save(update_fields=['estimated_cost', 'final_price', 'sale_price', 'profit_margin', 'updated_at'])
        
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
        from ..services.validators.order_validator import OrderValidator
        validator = OrderValidator()
        validation_result = validator.validate_order_for_approval(order)
        if not validation_result['success']:
            return JsonResponse({
                'success': False,
                'error': _('لا يمكن اعتماد الطلب: ') + ', '.join(validation_result.get('errors', []))
            }, status=400)
        
        # تحديث حالة الطلب
        old_status, new_status = order.update_status('approved', request.user)
        
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
                priority=original_order.priority,
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
                
            # نسخ مواصفات الطباعة
            for pr_spec in original_order.printing_specs.filter(is_active=True):
                PrintingSpecification.objects.create(
                    order=new_order,
                    printing_type=pr_spec.printing_type,
                    colors_front=pr_spec.colors_front,
                    colors_back=pr_spec.colors_back,
                    is_cmyk=pr_spec.is_cmyk,
                    has_spot_colors=pr_spec.has_spot_colors,
                    spot_colors_count=pr_spec.spot_colors_count,
                    resolution_dpi=pr_spec.resolution_dpi,
                    print_quality=pr_spec.print_quality,
                    special_requirements=pr_spec.special_requirements,
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
            
            # نسخ الخدمات
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
                    is_optional=service.is_optional,
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
