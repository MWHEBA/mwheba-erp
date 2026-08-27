"""
Views للأذون الجماعية (Batch Vouchers)
"""
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.views.generic import ListView, CreateView, UpdateView, DetailView, View
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.urls import reverse, reverse_lazy
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from core.utils import UnifiedPaginationMixin
from product.models import BatchVoucher, BatchVoucherItem, Product
from product.models import Category
from product.forms import BatchVoucherForm
from product.services.batch_voucher_service import BatchVoucherService


class BatchVoucherListView(UnifiedPaginationMixin, LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """قائمة الأذون الجماعية"""
    model = BatchVoucher
    template_name = 'product/batch_vouchers/batch_voucher_list.html'
    context_object_name = 'vouchers'
    default_per_page = 25
    permission_required = 'product.view_batchvoucher'
    
    def get_queryset(self):
        queryset = BatchVoucher.objects.select_related(
            'warehouse', 'target_warehouse', 'created_by', 'approved_by'
        ).prefetch_related('items')
        
        # الفلاتر
        voucher_type = self.request.GET.get('voucher_type')
        status = self.request.GET.get('status')
        warehouse_id = self.request.GET.get('warehouse')
        
        if voucher_type:
            queryset = queryset.filter(voucher_type=voucher_type)
        if status:
            queryset = queryset.filter(status=status)
        if warehouse_id:
            queryset = queryset.filter(warehouse_id=warehouse_id)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # إضافة المخازن للفلاتر
        from product.models import Warehouse
        context['warehouses'] = Warehouse.objects.filter(is_active=True)
        
        context.update({
            'active_menu': 'product',
            'title': 'الأذون الجماعية',
            'page_icon': 'fas fa-layer-group',
            'icon': 'fas fa-layer-group',
            'breadcrumb_items': [
                {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
                {'title': 'المنتجات', 'url': reverse('product:product_list'), 'icon': 'fas fa-box'},
                {'title': 'الأذون الجماعية', 'active': True}
            ],
            'header_buttons': [
                {'url': reverse('product:batch_voucher_create'), 'icon': 'fa-plus', 'text': 'إذن جماعي جديد', 'class': 'btn-primary'}
            ] if self.request.user.has_perm('product.add_batchvoucher') else []
        })
        return context


class BatchVoucherCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """إنشاء إذن جماعي جديد"""
    model = BatchVoucher
    form_class = BatchVoucherForm
    template_name = 'product/batch_vouchers/batch_voucher_form.html'
    permission_required = 'product.add_batchvoucher'

    def get_initial(self):
        initial = super().get_initial()
        from product.models.stock_management import Warehouse
        
        warehouse_id = self.request.GET.get('warehouse')
        if warehouse_id:
            try:
                initial['warehouse'] = Warehouse.objects.get(id=warehouse_id, is_active=True)
            except (Warehouse.DoesNotExist, ValueError):
                pass
        
        if 'warehouse' not in initial or not initial['warehouse']:
            default_warehouse = (
                Warehouse.objects.filter(is_active=True, name__icontains='رئيس').first()
                or Warehouse.objects.filter(is_active=True).first()
            )
            if default_warehouse:
                initial['warehouse'] = default_warehouse
        
        initial['voucher_type'] = self.request.GET.get('voucher_type') or 'transfer'
        if self.request.GET.get('target_warehouse'):
            initial['target_warehouse'] = self.request.GET.get('target_warehouse')
        if self.request.GET.get('purpose_type'):
            initial['purpose_type'] = self.request.GET.get('purpose_type')
        initial['voucher_date'] = timezone.now()
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from product.models.stock_management import Warehouse
        from core.models import SystemSetting

        warehouses = Warehouse.objects.filter(is_active=True).order_by('name')
        currency_symbol = SystemSetting.get_currency_symbol()
        product_categories = Category.objects.filter(
            is_active=True, products__is_active=True, products__is_service=False, products__is_bundle=False
        ).distinct().order_by('name')
        context.update({
            'active_menu': 'product',
            'title': 'إذن جماعي جديد',
            'page_icon': 'fas fa-layer-group',
            'icon': 'fas fa-layer-group',
            'warehouses': warehouses,
            'currency_symbol': currency_symbol,
            'product_categories': product_categories,
            'breadcrumb_items': [
                {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
                {'title': 'الأذون الجماعية', 'url': reverse('product:batch_voucher_list'), 'icon': 'fas fa-layer-group'},
                {'title': 'إذن جديد', 'active': True}
            ],
            'header_buttons': [
                {'url': reverse('product:batch_voucher_list'), 'icon': 'fa-arrow-right', 'text': 'العودة للأذون', 'class': 'btn-outline-secondary'}
            ]
        })
        return context

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        self.object = None
        form = self.get_form()
        if not form.is_valid():
            return self.form_invalid(form)

        product_ids = request.POST.getlist('product[]')
        quantities = request.POST.getlist('quantity[]')
        unit_costs = request.POST.getlist('unit_cost[]')
        if not unit_costs:
            unit_costs = request.POST.getlist('unit_price[]')

        # تجميع البنود الصالحة
        valid_items = []
        for pid, qty, cost in zip(product_ids, quantities, unit_costs):
            if pid and qty:
                try:
                    qty_val = int(float(str(qty).replace(',', '')))
                    cost_val = float(str(cost).replace(',', '')) if cost else 0.0
                    if qty_val > 0:
                        valid_items.append({
                            'product_id': int(pid),
                            'quantity': qty_val,
                            'unit_cost': cost_val,
                        })
                except (ValueError, TypeError):
                    continue

        if not valid_items:
            form.add_error(None, 'يرجى إضافة بند واحد على الأقل مع تحديد المنتج والكمية')
            return self.form_invalid(form)

        voucher = form.save(commit=False)
        voucher.created_by = request.user
        if not voucher.voucher_date:
            voucher.voucher_date = timezone.now()
        voucher.save()

        for item in valid_items:
            BatchVoucherItem.objects.create(
                batch_voucher=voucher,
                product_id=item['product_id'],
                quantity=item['quantity'],
                unit_cost=item['unit_cost'],
                total_cost=item['quantity'] * item['unit_cost'],
            )

        voucher.calculate_totals()
        messages.success(request, f'تم إنشاء الإذن {voucher.voucher_number} بنجاح')
        return redirect('product:batch_voucher_detail', pk=voucher.pk)


class BatchVoucherUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """تعديل إذن جماعي"""
    model = BatchVoucher
    form_class = BatchVoucherForm
    template_name = 'product/batch_vouchers/batch_voucher_form.html'
    permission_required = 'product.change_batchvoucher'

    def dispatch(self, request, *args, **kwargs):
        obj = self.get_object()
        if not obj.can_edit():
            messages.error(request, 'لا يمكن تعديل إذن معتمد')
            return redirect('product:batch_voucher_detail', pk=obj.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from core.models import SystemSetting

        warehouses = Warehouse.objects.filter(is_active=True).order_by('name')
        currency_symbol = SystemSetting.get_currency_symbol()
        product_categories = Category.objects.filter(
            is_active=True, products__is_active=True, products__is_service=False, products__is_bundle=False
        ).distinct().order_by('name')
        # البنود الحالية للتعديل
        existing_items = self.object.items.select_related('product').all()
        context.update({
            'active_menu': 'product',
            'title': f'تعديل الإذن {self.object.voucher_number}',
            'page_icon': 'fas fa-layer-group',
            'icon': 'fas fa-layer-group',
            'warehouses': warehouses,
            'currency_symbol': currency_symbol,
            'product_categories': product_categories,
            'existing_items': existing_items,
            'breadcrumb_items': [
                {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
                {'title': 'الأذون الجماعية', 'url': reverse('product:batch_voucher_list'), 'icon': 'fas fa-layer-group'},
                {'title': self.object.voucher_number, 'url': reverse('product:batch_voucher_detail', args=[self.object.pk])},
                {'title': 'تعديل', 'active': True}
            ],
            'header_buttons': [
                {'url': reverse('product:batch_voucher_detail', args=[self.object.pk]), 'icon': 'fa-eye', 'text': 'عرض الإذن', 'class': 'btn-outline-primary'},
                {'url': reverse('product:batch_voucher_list'), 'icon': 'fa-arrow-right', 'text': 'العودة للأذون', 'class': 'btn-outline-secondary'}
            ]
        })
        return context

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        if not form.is_valid():
            return self.form_invalid(form)

        product_ids = request.POST.getlist('product[]')
        quantities = request.POST.getlist('quantity[]')
        unit_costs = request.POST.getlist('unit_cost[]')
        if not unit_costs:
            unit_costs = request.POST.getlist('unit_price[]')

        valid_items = []
        for pid, qty, cost in zip(product_ids, quantities, unit_costs):
            if pid and qty:
                try:
                    qty_val = int(float(str(qty).replace(',', '')))
                    cost_val = float(str(cost).replace(',', '')) if cost else 0.0
                    if qty_val > 0:
                        valid_items.append({
                            'product_id': int(pid),
                            'quantity': qty_val,
                            'unit_cost': cost_val,
                        })
                except (ValueError, TypeError):
                    continue

        if not valid_items:
            form.add_error(None, 'يرجى إضافة بند واحد على الأقل مع تحديد المنتج والكمية')
            return self.form_invalid(form)

        voucher = form.save(commit=False)
        voucher.updated_by = request.user
        voucher.save()

        # حذف البنود القديمة وإعادة إنشاؤها
        voucher.items.all().delete()
        for item in valid_items:
            BatchVoucherItem.objects.create(
                batch_voucher=voucher,
                product_id=item['product_id'],
                quantity=item['quantity'],
                unit_cost=item['unit_cost'],
                total_cost=item['quantity'] * item['unit_cost'],
            )

        voucher.calculate_totals()
        messages.success(request, f'تم تحديث الإذن {voucher.voucher_number} بنجاح')
        return redirect('product:batch_voucher_detail', pk=voucher.pk)


class BatchVoucherDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    """تفاصيل الإذن الجماعي"""
    model = BatchVoucher
    template_name = 'product/batch_vouchers/batch_voucher_detail.html'
    context_object_name = 'voucher'
    permission_required = 'product.view_batchvoucher'
    
    def get_queryset(self):
        return BatchVoucher.objects.select_related(
            'warehouse', 'target_warehouse', 'created_by', 'updated_by', 'approved_by', 'journal_entry'
        ).prefetch_related('items__product', 'items__inventory_movement')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from core.models import SystemSetting
        
        # جلب الحركات الفردية المرتبطة بالإذن الجماعي
        inventory_movements = self.object.inventory_movements.select_related(
            'product', 'warehouse', 'created_by', 'approved_by'
        ).order_by('created_at')
        
        # إعداد الأزرار
        header_buttons = []
        
        if self.object.can_edit() and self.request.user.has_perm('product.change_batchvoucher'):
            header_buttons.append({
                'url': reverse('product:batch_voucher_update', args=[self.object.pk]),
                'icon': 'fa-edit',
                'text': 'تعديل',
                'class': 'btn-primary'
            })
        
        if self.object.can_approve() and self.request.user.has_perm('product.approve_batchvoucher'):
            header_buttons.append({
                'onclick': f'approveBatchVoucher({self.object.pk})',
                'icon': 'fa-check',
                'text': 'اعتماد',
                'class': 'btn-success'
            })
        
        if self.object.can_delete() and self.request.user.has_perm('product.delete_batchvoucher'):
            header_buttons.append({
                'onclick': f'deleteBatchVoucher({self.object.pk})',
                'icon': 'fa-trash',
                'text': 'حذف',
                'class': 'btn-danger'
            })
        
        header_buttons.append({
            'onclick': 'window.print()',
            'icon': 'fa-print',
            'text': 'طباعة',
            'class': 'btn-outline-secondary'
        })

        header_buttons.append({
            'url': reverse('product:batch_voucher_list'),
            'icon': 'fa-arrow-right',
            'text': 'العودة',
            'class': 'btn-outline-secondary'
        })
        
        context.update({
            'active_menu': 'product',
            'title': f'تفاصيل الإذن {self.object.voucher_number}',
            'page_icon': 'fas fa-layer-group',
            'icon': 'fas fa-layer-group',
            'currency_symbol': SystemSetting.get_currency_symbol(),
            'breadcrumb_items': [
                {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
                {'title': 'الأذون الجماعية', 'url': reverse('product:batch_voucher_list'), 'icon': 'fas fa-layer-group'},
                {'title': self.object.voucher_number, 'active': True}
            ],
            'header_buttons': header_buttons,
            'inventory_movements': inventory_movements
        })
        return context


class BatchVoucherApproveView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """اعتماد الإذن الجماعي"""
    permission_required = 'product.approve_batchvoucher'
    
    def post(self, request, pk):
        voucher = get_object_or_404(BatchVoucher, pk=pk)
        service = BatchVoucherService()
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
        
        try:
            service.approve_batch_voucher(voucher, request.user)
            msg = f'تم اعتماد الإذن {voucher.voucher_number} بنجاح'
            if is_ajax:
                return JsonResponse({'success': True, 'message': msg})
            messages.success(request, msg)
            return redirect('product:batch_voucher_detail', pk=pk)
        except ValueError as e:
            err_msg = f'فشل الاعتماد: {str(e)}'
            if is_ajax:
                return JsonResponse({'success': False, 'error': err_msg}, status=400)
            messages.error(request, err_msg)
            return redirect('product:batch_voucher_detail', pk=pk)


class BatchVoucherDeleteView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """حذف الإذن الجماعي"""
    permission_required = 'product.delete_batchvoucher'
    
    def post(self, request, pk):
        voucher = get_object_or_404(BatchVoucher, pk=pk)
        service = BatchVoucherService()
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
        
        try:
            voucher_number = voucher.voucher_number
            service.delete_batch_voucher(voucher)
            msg = f'تم حذف الإذن {voucher_number} بنجاح'
            if is_ajax:
                return JsonResponse({'success': True, 'message': msg, 'redirect_url': reverse('product:batch_voucher_list')})
            messages.success(request, msg)
            return redirect('product:batch_voucher_list')
        except ValueError as e:
            err_msg = f'فشل الحذف: {str(e)}'
            if is_ajax:
                return JsonResponse({'success': False, 'error': err_msg}, status=400)
            messages.error(request, err_msg)
            return redirect('product:batch_voucher_detail', pk=pk)


class GetProductCostView(LoginRequiredMixin, View):
    """API للحصول على تكلفة المنتج"""
    
    def get(self, request):
        product_id = request.GET.get('product_id')
        if not product_id:
            return JsonResponse({'error': 'product_id مطلوب'}, status=400)
        
        try:
            product = Product.objects.get(id=product_id)
            return JsonResponse({
                'unit_cost': float(product.cost_price),
                'product_name': product.name,
                'unit_name': product.unit.name if product.unit else ''
            })
        except Product.DoesNotExist:
            return JsonResponse({'error': 'المنتج غير موجود'}, status=404)
