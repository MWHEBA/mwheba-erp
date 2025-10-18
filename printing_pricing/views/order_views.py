from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy, reverse
from django.http import JsonResponse, HttpResponseRedirect
from django.utils.translation import gettext_lazy as _
from django.db.models import Q, Sum, Count
from django.core.paginator import Paginator
from decimal import Decimal

from ..models import PrintingOrder, OrderMaterial, OrderService, OrderSummary
from ..forms import PrintingOrderForm, OrderSearchForm
from client.models import Customer


class OrderListView(LoginRequiredMixin, ListView):
    """
    عرض قائمة طلبات التسعير
    """
    model = PrintingOrder
    template_name = 'printing_pricing/orders/order_list.html'
    context_object_name = 'orders'
    paginate_by = 20
    
    def get_queryset(self):
        """تخصيص الاستعلام مع البحث والفلترة"""
        queryset = PrintingOrder.objects.select_related('customer').filter(
            is_active=True
        )
        
        # تطبيق البحث
        search_form = OrderSearchForm(self.request.GET)
        if search_form.is_valid():
            search_query = search_form.cleaned_data.get('search_query')
            status = search_form.cleaned_data.get('status')
            order_type = search_form.cleaned_data.get('order_type')
            customer = search_form.cleaned_data.get('customer')
            date_from = search_form.cleaned_data.get('date_from')
            date_to = search_form.cleaned_data.get('date_to')
            
            if search_query:
                queryset = queryset.filter(
                    Q(order_number__icontains=search_query) |
                    Q(title__icontains=search_query) |
                    Q(customer__name__icontains=search_query) |
                    Q(customer__company_name__icontains=search_query)
                )
            
            if status:
                queryset = queryset.filter(status=status)
            
            if order_type:
                queryset = queryset.filter(order_type=order_type)
            
            if customer:
                queryset = queryset.filter(customer=customer)
            
            if date_from:
                queryset = queryset.filter(created_at__date__gte=date_from)
            
            if date_to:
                queryset = queryset.filter(created_at__date__lte=date_to)
        
        return queryset.order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        """إضافة بيانات إضافية للسياق"""
        context = super().get_context_data(**kwargs)
        context['search_form'] = OrderSearchForm(self.request.GET)
        
        # إحصائيات سريعة
        context['stats'] = {
            'total_orders': PrintingOrder.objects.filter(is_active=True).count(),
            'pending_orders': PrintingOrder.objects.filter(status='pending', is_active=True).count(),
            'approved_orders': PrintingOrder.objects.filter(status='approved', is_active=True).count(),
            'total_value': PrintingOrder.objects.filter(is_active=True).aggregate(
                total=Sum('estimated_cost')
            )['total'] or Decimal('0.00')
        }
        
        return context


class OrderDetailView(LoginRequiredMixin, DetailView):
    """
    عرض تفاصيل طلب التسعير
    """
    model = PrintingOrder
    template_name = 'printing_pricing/orders/order_detail.html'
    context_object_name = 'order'
    
    def get_queryset(self):
        """تحسين الاستعلام"""
        return PrintingOrder.objects.select_related(
            'customer', 'created_by', 'updated_by'
        ).prefetch_related(
            'materials', 'services', 'calculations'
        )
    
    def get_context_data(self, **kwargs):
        """إضافة بيانات إضافية"""
        context = super().get_context_data(**kwargs)
        order = self.object
        
        # المواد والخدمات
        context['materials'] = order.materials.filter(is_active=True)
        context['services'] = order.services.filter(is_active=True)
        
        # ملخص التكاليف
        try:
            context['summary'] = order.summary
        except OrderSummary.DoesNotExist:
            context['summary'] = None
        
        # الحسابات الحالية
        context['current_calculations'] = order.calculations.filter(is_current=True)
        
        return context


class OrderCreateView(LoginRequiredMixin, CreateView):
    """
    إنشاء طلب تسعير جديد
    """
    model = PrintingOrder
    form_class = PrintingOrderForm
    template_name = 'printing_pricing/orders/order_form.html'
    
    def form_valid(self, form):
        """معالجة النموذج الصحيح"""
        # تعيين المستخدم الحالي
        form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        
        # حفظ الطلب
        response = super().form_valid(form)
        
        # إنشاء ملخص التكلفة
        OrderSummary.objects.create(order=self.object)
        
        messages.success(
            self.request, 
            _('تم إنشاء طلب التسعير {} بنجاح').format(self.object.order_number)
        )
        
        return response
    
    def get_success_url(self):
        """الانتقال لصفحة تفاصيل الطلب بعد الإنشاء"""
        return reverse('printing_pricing:order_detail', kwargs={'pk': self.object.pk})


class OrderUpdateView(LoginRequiredMixin, UpdateView):
    """
    تحديث طلب التسعير
    """
    model = PrintingOrder
    form_class = PrintingOrderForm
    template_name = 'printing_pricing/orders/order_form.html'
    
    def form_valid(self, form):
        """معالجة النموذج الصحيح"""
        # تحديث المستخدم
        form.instance.updated_by = self.request.user
        
        response = super().form_valid(form)
        
        messages.success(
            self.request,
            _('تم تحديث طلب التسعير {} بنجاح').format(self.object.order_number)
        )
        
        return response
    
    def get_success_url(self):
        """الانتقال لصفحة تفاصيل الطلب بعد التحديث"""
        return reverse('printing_pricing:order_detail', kwargs={'pk': self.object.pk})


class OrderDeleteView(LoginRequiredMixin, DeleteView):
    """
    حذف طلب التسعير (حذف منطقي)
    """
    model = PrintingOrder
    template_name = 'printing_pricing/orders/order_delete.html'
    success_url = reverse_lazy('printing_pricing:order_list')
    
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


class DashboardView(LoginRequiredMixin, ListView):
    """
    لوحة التحكم الرئيسية
    """
    template_name = 'printing_pricing/dashboard.html'
    context_object_name = 'recent_orders'
    
    def get_queryset(self):
        """أحدث الطلبات"""
        return PrintingOrder.objects.select_related('customer').filter(
            is_active=True
        ).order_by('-created_at')[:10]
    
    def get_context_data(self, **kwargs):
        """إحصائيات شاملة للوحة التحكم"""
        context = super().get_context_data(**kwargs)
        
        # إحصائيات عامة
        context['stats'] = {
            'total_orders': PrintingOrder.objects.filter(is_active=True).count(),
            'pending_orders': PrintingOrder.objects.filter(
                status='pending', is_active=True
            ).count(),
            'approved_orders': PrintingOrder.objects.filter(
                status='approved', is_active=True
            ).count(),
            'completed_orders': PrintingOrder.objects.filter(
                status='completed', is_active=True
            ).count(),
            'total_customers': Customer.objects.filter(is_active=True).count(),
            'total_value': PrintingOrder.objects.filter(is_active=True).aggregate(
                total=Sum('estimated_cost')
            )['total'] or Decimal('0.00'),
            'avg_order_value': PrintingOrder.objects.filter(is_active=True).aggregate(
                avg=Sum('estimated_cost') / Count('id')
            )['avg'] or Decimal('0.00')
        }
        
        # إحصائيات حسب نوع الطلب
        context['order_type_stats'] = PrintingOrder.objects.filter(
            is_active=True
        ).values('order_type').annotate(
            count=Count('id'),
            total_value=Sum('estimated_cost')
        ).order_by('-count')[:5]
        
        # إحصائيات حسب الحالة
        context['status_stats'] = PrintingOrder.objects.filter(
            is_active=True
        ).values('status').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # أفضل العملاء
        context['top_customers'] = Customer.objects.filter(
            printing_orders__is_active=True
        ).annotate(
            orders_count=Count('printing_orders'),
            total_value=Sum('printing_orders__estimated_cost')
        ).order_by('-total_value')[:5]
        
        return context


# دوال مساعدة للعمليات السريعة

def calculate_order_cost(request, pk):
    """
    حساب تكلفة الطلب عبر AJAX
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': _('طريقة غير مسموحة')})
    
    try:
        order = get_object_or_404(PrintingOrder, pk=pk, is_active=True)
        
        # هنا سيتم استدعاء خدمات الحساب لاحقاً
        # من services/calculators/
        
        # مؤقتاً نرجع استجابة أساسية
        return JsonResponse({
            'success': True,
            'message': _('تم حساب التكلفة بنجاح'),
            'estimated_cost': float(order.estimated_cost or 0),
            'order_id': order.id
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': _('حدث خطأ أثناء حساب التكلفة: {}').format(str(e))
        })


def approve_order(request, pk):
    """
    اعتماد الطلب
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': _('طريقة غير مسموحة')})
    
    try:
        order = get_object_or_404(PrintingOrder, pk=pk, is_active=True)
        
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


def duplicate_order(request, pk):
    """
    نسخ الطلب
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': _('طريقة غير مسموحة')})
    
    try:
        original_order = get_object_or_404(PrintingOrder, pk=pk, is_active=True)
        
        # إنشاء نسخة جديدة
        new_order = PrintingOrder.objects.create(
            customer=original_order.customer,
            title=f"{original_order.title} - نسخة",
            description=original_order.description,
            order_type=original_order.order_type,
            quantity=original_order.quantity,
            pages_count=original_order.pages_count,
            copies_count=original_order.copies_count,
            width=original_order.width,
            height=original_order.height,
            profit_margin=original_order.profit_margin,
            priority=original_order.priority,
            created_by=request.user,
            updated_by=request.user
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
    'OrderUpdateView', 'OrderDeleteView', 'DashboardView',
    'calculate_order_cost', 'approve_order', 'duplicate_order'
]
