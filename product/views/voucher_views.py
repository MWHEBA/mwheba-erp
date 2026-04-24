"""
أذون الصرف والاستلام المخزنية
Warehouse Issue & Receipt Vouchers Views
"""
from django.views.generic import ListView, CreateView, DetailView, View
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.db import transaction
from django.http import JsonResponse
from decimal import Decimal

from product.models.inventory_movement import InventoryMovement
from product.models.stock_management import Stock, Warehouse
from product.models.product_core import Product
from product.forms import ReceiptVoucherForm, IssueVoucherForm
from financial.models.chart_of_accounts import ChartOfAccounts


class GetProductWarehousesView(LoginRequiredMixin, View):
    """الحصول على المخازن المتاحة للمنتج"""
    
    def get(self, request):
        product_id = request.GET.get('product_id')
        if not product_id:
            return JsonResponse({'warehouses': [], 'unit': ''})
        
        try:
            # جلب المنتج للحصول على وحدة القياس
            product = Product.objects.get(id=product_id)
            unit_name = product.unit.name if product.unit else 'وحدة'
            
            # جلب المخازن التي يتوفر فيها المنتج فقط (كمية > 0)
            stocks = Stock.objects.filter(
                product_id=product_id,
                quantity__gt=0
            ).select_related('warehouse').order_by('-quantity')
            
            warehouses = [
                {
                    'id': stock.warehouse.id,
                    'name': stock.warehouse.name,
                    'quantity': stock.quantity
                }
                for stock in stocks
            ]
            
            return JsonResponse({'warehouses': warehouses, 'unit': unit_name})
        except Product.DoesNotExist:
            return JsonResponse({'warehouses': [], 'unit': '', 'error': 'Product not found'})
        except Exception as e:
            return JsonResponse({'warehouses': [], 'unit': '', 'error': str(e)})


class GetAvailableProductsView(LoginRequiredMixin, View):
    """الحصول على المنتجات المتاحة (التي لها stock)"""
    
    def get(self, request):
        try:
            # جلب المنتجات التي لها stock متاح
            products_with_stock = Stock.objects.filter(
                quantity__gt=0
            ).values('product_id').distinct()
            
            product_ids = [item['product_id'] for item in products_with_stock]
            
            products = Product.objects.filter(
                id__in=product_ids,
                is_active=True
            ).select_related('category', 'unit').order_by('name')
            
            products_data = [
                {
                    'id': product.id,
                    'name': product.name,
                    'code': product.code,
                    'category': product.category.name if product.category else '',
                    'unit': product.unit.name if product.unit else 'وحدة',
                    'total_stock': sum(
                        Stock.objects.filter(product=product, quantity__gt=0)
                        .values_list('quantity', flat=True)
                    )
                }
                for product in products
            ]
            
            return JsonResponse({'products': products_data})
        except Exception as e:
            return JsonResponse({'products': [], 'error': str(e)})


class ReceiptVoucherListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """قائمة أذون الاستلام"""
    model = InventoryMovement
    template_name = 'product/vouchers/receipt_voucher_list.html'
    context_object_name = 'vouchers'
    paginate_by = 20
    permission_required = 'product.view_inventorymovement'
    
    def get_queryset(self):
        queryset = InventoryMovement.objects.filter(
            voucher_type='receipt'
        ).select_related(
            'product', 'warehouse', 'created_by', 'approved_by'
        ).order_by('-movement_date', '-created_at')
        
        # فلترة حسب المخزن
        warehouse_id = self.request.GET.get('warehouse')
        if warehouse_id:
            queryset = queryset.filter(warehouse_id=warehouse_id)
        
        # فلترة حسب الحالة
        status = self.request.GET.get('status')
        if status == 'approved':
            queryset = queryset.filter(is_approved=True)
        elif status == 'pending':
            queryset = queryset.filter(is_approved=False)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'active_menu': 'product',
            'title': 'أذون الاستلام',
            'header_buttons': [
                {
                    'onclick': 'openReceiptVoucherModal()',
                    'icon': 'fa-plus',
                    'text': 'إذن استلام جديد',
                    'class': 'btn-primary',
                    'id': 'create-receipt-btn'
                }
            ],
            'breadcrumb_items': [
                {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
                {'title': 'المخزون', 'url': reverse('product:product_list'), 'icon': 'fas fa-boxes'},
                {'title': 'أذون الاستلام', 'active': True}
            ],
            'warehouses': Warehouse.objects.filter(is_active=True),
            'table_headers': self._get_table_headers(),
            'table_data': self._prepare_table_data(),
            'primary_key': 'id',
        })
        return context
    
    def _get_table_headers(self):
        return [
            {'key': 'movement_number', 'label': 'رقم الإذن', 'sortable': True, 'width': '12%'},
            {'key': 'movement_date', 'label': 'التاريخ', 'sortable': True, 'width': '10%', 'format': 'date'},
            {'key': 'product', 'label': 'المنتج', 'sortable': True, 'width': '20%'},
            {'key': 'warehouse', 'label': 'المخزن', 'sortable': True, 'width': '15%'},
            {'key': 'quantity', 'label': 'الكمية', 'sortable': True, 'width': '8%', 'class': 'text-center'},
            {'key': 'total_cost', 'label': 'القيمة', 'sortable': True, 'width': '10%', 'class': 'text-end'},
            {'key': 'purpose', 'label': 'الغرض', 'width': '12%'},
            {'key': 'status', 'label': 'الحالة', 'sortable': True, 'width': '8%', 'class': 'text-center', 'format': 'html'},
            {'key': 'actions', 'label': 'الإجراءات', 'width': '10%', 'class': 'text-center'}
        ]
    
    def _prepare_table_data(self):
        table_data = []
        for voucher in self.get_queryset()[:self.paginate_by]:
            actions = [
                {'url': reverse('product:receipt_voucher_detail', args=[voucher.pk]), 
                 'icon': 'fas fa-eye', 'label': 'عرض', 'class': 'btn-outline-info btn-sm'}
            ]
            
            if not voucher.is_approved and self.request.user.has_perm('product.change_inventorymovement'):
                actions.append({
                    'url': reverse('product:receipt_voucher_approve', args=[voucher.pk]),
                    'icon': 'fas fa-check', 'label': 'اعتماد', 'class': 'btn-outline-success btn-sm'
                })
            
            row_data = {
                'id': voucher.id,
                'movement_number': voucher.movement_number,
                'movement_date': voucher.movement_date,
                'product': voucher.product.name,
                'warehouse': voucher.warehouse.name,
                'quantity': voucher.quantity,
                'total_cost': voucher.total_cost,
                'purpose': voucher.get_purpose_type_display() if voucher.purpose_type else '-',
                'status': f'<span class="badge bg-{"success" if voucher.is_approved else "warning"}">{"معتمد" if voucher.is_approved else "معلق"}</span>',
                'actions': actions
            }
            table_data.append(row_data)
        
        return table_data


class ReceiptVoucherCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """إنشاء إذن استلام جديد"""
    model = InventoryMovement
    form_class = ReceiptVoucherForm
    template_name = 'product/vouchers/receipt_voucher_form.html'
    permission_required = 'product.add_inventorymovement'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'active_menu': 'product',
            'title': 'إذن استلام جديد',
            'is_modal': True,
        })
        return context
    
    def form_valid(self, form):
        form.instance.voucher_type = 'receipt'
        form.instance.movement_type = 'in'
        form.instance.document_type = 'receipt_voucher'
        form.instance.created_by = self.request.user
        form.instance.movement_date = timezone.now()
        
        response = super().form_valid(form)
        
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'message': 'تم إنشاء إذن الاستلام بنجاح',
                'voucher_id': self.object.pk,
                'redirect_url': reverse('product:receipt_voucher_detail', args=[self.object.pk])
            })
        
        messages.success(self.request, 'تم إنشاء إذن الاستلام بنجاح')
        return response
    
    def form_invalid(self, form):
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'errors': form.errors
            }, status=400)
        return super().form_invalid(form)
    
    def get_success_url(self):
        return reverse('product:receipt_voucher_detail', args=[self.object.pk])


class ReceiptVoucherDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    """تفاصيل إذن استلام"""
    model = InventoryMovement
    template_name = 'product/vouchers/receipt_voucher_detail.html'
    context_object_name = 'voucher'
    permission_required = 'product.view_inventorymovement'
    
    def get_queryset(self):
        return InventoryMovement.objects.filter(voucher_type='receipt')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        voucher = self.object
        
        header_buttons = [
            {'url': reverse('product:receipt_voucher_list'), 'icon': 'fa-arrow-right', 
             'text': 'العودة', 'class': 'btn-outline-secondary'}
        ]
        
        if not voucher.is_approved and self.request.user.has_perm('product.change_inventorymovement'):
            header_buttons.insert(0, {
                'onclick': 'document.getElementById("approve-form").submit()',
                'icon': 'fa-check', 
                'text': 'اعتماد', 
                'class': 'btn-success'
            })
        
        context.update({
            'active_menu': 'product',
            'title': f'إذن استلام - {voucher.movement_number}',
            'header_buttons': header_buttons,
            'breadcrumb_items': [
                {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
                {'title': 'أذون الاستلام', 'url': reverse('product:receipt_voucher_list')},
                {'title': voucher.movement_number, 'active': True}
            ],
            'unit_name': voucher.product.unit.name if voucher.product.unit else 'وحدة',
        })
        return context


class ReceiptVoucherApproveView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """اعتماد إذن استلام"""
    permission_required = 'product.change_inventorymovement'
    
    def post(self, request, pk):
        voucher = get_object_or_404(InventoryMovement, pk=pk, voucher_type='receipt')
        
        if voucher.is_approved:
            messages.warning(request, 'الإذن معتمد مسبقاً')
            return redirect('product:receipt_voucher_detail', pk=pk)
        
        try:
            with transaction.atomic():
                # اعتماد الإذن أولاً (يحدث المخزون)
                if voucher.approve(request.user):
                    # بعد الاعتماد، إنشاء القيد المحاسبي
                    from product.services.voucher_accounting_service import create_receipt_voucher_entry
                    create_receipt_voucher_entry(voucher)
                    
                    messages.success(request, 'تم اعتماد إذن الاستلام بنجاح')
                else:
                    messages.error(request, 'فشل اعتماد الإذن')
        except Exception as e:
            messages.error(request, f'حدث خطأ: {str(e)}')
        
        return redirect('product:receipt_voucher_detail', pk=pk)


class IssueVoucherListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """قائمة أذون الصرف"""
    model = InventoryMovement
    template_name = 'product/vouchers/issue_voucher_list.html'
    context_object_name = 'vouchers'
    paginate_by = 20
    permission_required = 'product.view_inventorymovement'
    
    def get_queryset(self):
        queryset = InventoryMovement.objects.filter(
            voucher_type='issue'
        ).select_related(
            'product', 'warehouse', 'created_by', 'approved_by'
        ).order_by('-movement_date', '-created_at')
        
        warehouse_id = self.request.GET.get('warehouse')
        if warehouse_id:
            queryset = queryset.filter(warehouse_id=warehouse_id)
        
        status = self.request.GET.get('status')
        if status == 'approved':
            queryset = queryset.filter(is_approved=True)
        elif status == 'pending':
            queryset = queryset.filter(is_approved=False)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'active_menu': 'product',
            'title': 'أذون الصرف',
            'header_buttons': [
                {
                    'onclick': 'openIssueVoucherModal()',
                    'icon': 'fa-plus',
                    'text': 'إذن صرف جديد',
                    'class': 'btn-primary',
                    'id': 'create-issue-btn'
                }
            ],
            'breadcrumb_items': [
                {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
                {'title': 'المخزون', 'url': reverse('product:product_list'), 'icon': 'fas fa-boxes'},
                {'title': 'أذون الصرف', 'active': True}
            ],
            'warehouses': Warehouse.objects.filter(is_active=True),
            'table_headers': self._get_table_headers(),
            'table_data': self._prepare_table_data(),
            'primary_key': 'id',
        })
        return context
    
    def _get_table_headers(self):
        return [
            {'key': 'movement_number', 'label': 'رقم الإذن', 'sortable': True, 'width': '12%'},
            {'key': 'movement_date', 'label': 'التاريخ', 'sortable': True, 'width': '10%', 'format': 'date'},
            {'key': 'product', 'label': 'المنتج', 'sortable': True, 'width': '20%'},
            {'key': 'warehouse', 'label': 'المخزن', 'sortable': True, 'width': '15%'},
            {'key': 'quantity', 'label': 'الكمية', 'sortable': True, 'width': '8%', 'class': 'text-center'},
            {'key': 'total_cost', 'label': 'القيمة', 'sortable': True, 'width': '10%', 'class': 'text-end'},
            {'key': 'purpose', 'label': 'الغرض', 'width': '12%'},
            {'key': 'status', 'label': 'الحالة', 'sortable': True, 'width': '8%', 'class': 'text-center', 'format': 'html'},
            {'key': 'actions', 'label': 'الإجراءات', 'width': '10%', 'class': 'text-center'}
        ]
    
    def _prepare_table_data(self):
        table_data = []
        for voucher in self.get_queryset()[:self.paginate_by]:
            actions = [
                {'url': reverse('product:issue_voucher_detail', args=[voucher.pk]), 
                 'icon': 'fas fa-eye', 'label': 'عرض', 'class': 'btn-outline-info btn-sm'}
            ]
            
            if not voucher.is_approved and self.request.user.has_perm('product.change_inventorymovement'):
                actions.append({
                    'url': reverse('product:issue_voucher_approve', args=[voucher.pk]),
                    'icon': 'fas fa-check', 'label': 'اعتماد', 'class': 'btn-outline-success btn-sm'
                })
            
            row_data = {
                'id': voucher.id,
                'movement_number': voucher.movement_number,
                'movement_date': voucher.movement_date,
                'product': voucher.product.name,
                'warehouse': voucher.warehouse.name,
                'quantity': voucher.quantity,
                'total_cost': voucher.total_cost,
                'purpose': voucher.get_purpose_type_display() if voucher.purpose_type else '-',
                'status': f'<span class="badge bg-{"success" if voucher.is_approved else "warning"}">{"معتمد" if voucher.is_approved else "معلق"}</span>',
                'actions': actions
            }
            table_data.append(row_data)
        
        return table_data


class IssueVoucherCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """إنشاء إذن صرف جديد"""
    model = InventoryMovement
    form_class = IssueVoucherForm
    template_name = 'product/vouchers/issue_voucher_form.html'
    permission_required = 'product.add_inventorymovement'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'active_menu': 'product',
            'title': 'إذن صرف جديد',
            'is_modal': True,
        })
        return context
    
    def form_valid(self, form):
        product = form.cleaned_data['product']
        warehouse = form.cleaned_data['warehouse']
        quantity = form.cleaned_data['quantity']
        
        # التحقق من توفر الكمية
        try:
            stock = Stock.objects.get(product=product, warehouse=warehouse)
            if stock.quantity < quantity:
                if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'message': f'الكمية المتاحة ({stock.quantity}) أقل من المطلوبة ({quantity})'
                    }, status=400)
                messages.error(self.request, f'الكمية المتاحة ({stock.quantity}) أقل من المطلوبة ({quantity})')
                return self.form_invalid(form)
            
            form.instance.unit_cost = stock.average_cost
        except Stock.DoesNotExist:
            if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': 'المنتج غير متوفر في هذا المخزن'
                }, status=400)
            messages.error(self.request, 'المنتج غير متوفر في هذا المخزن')
            return self.form_invalid(form)
        
        form.instance.voucher_type = 'issue'
        form.instance.movement_type = 'out'
        form.instance.document_type = 'issue_voucher'
        form.instance.created_by = self.request.user
        form.instance.movement_date = timezone.now()
        
        response = super().form_valid(form)
        
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'message': 'تم إنشاء إذن الصرف بنجاح',
                'voucher_id': self.object.pk,
                'redirect_url': reverse('product:issue_voucher_detail', args=[self.object.pk])
            })
        
        messages.success(self.request, 'تم إنشاء إذن الصرف بنجاح')
        return response
    
    def form_invalid(self, form):
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'errors': form.errors
            }, status=400)
        return super().form_invalid(form)
    
    def get_success_url(self):
        return reverse('product:issue_voucher_detail', args=[self.object.pk])


class IssueVoucherDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    """تفاصيل إذن صرف"""
    model = InventoryMovement
    template_name = 'product/vouchers/issue_voucher_detail.html'
    context_object_name = 'voucher'
    permission_required = 'product.view_inventorymovement'
    
    def get_queryset(self):
        return InventoryMovement.objects.filter(voucher_type='issue')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        voucher = self.object
        
        header_buttons = [
            {'url': reverse('product:issue_voucher_list'), 'icon': 'fa-arrow-right', 
             'text': 'العودة', 'class': 'btn-outline-secondary'}
        ]
        
        if not voucher.is_approved and self.request.user.has_perm('product.change_inventorymovement'):
            header_buttons.insert(0, {
                'onclick': 'document.getElementById("approve-form").submit()',
                'icon': 'fa-check', 
                'text': 'اعتماد', 
                'class': 'btn-success'
            })
        
        context.update({
            'active_menu': 'product',
            'title': f'إذن صرف - {voucher.movement_number}',
            'header_buttons': header_buttons,
            'breadcrumb_items': [
                {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
                {'title': 'أذون الصرف', 'url': reverse('product:issue_voucher_list')},
                {'title': voucher.movement_number, 'active': True}
            ],
            'unit_name': voucher.product.unit.name if voucher.product.unit else 'وحدة',
        })
        return context


class IssueVoucherApproveView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """اعتماد إذن صرف"""
    permission_required = 'product.change_inventorymovement'
    
    def post(self, request, pk):
        voucher = get_object_or_404(InventoryMovement, pk=pk, voucher_type='issue')
        
        if voucher.is_approved:
            messages.warning(request, 'الإذن معتمد مسبقاً')
            return redirect('product:issue_voucher_detail', pk=pk)
        
        try:
            with transaction.atomic():
                # اعتماد الإذن أولاً (يحدث المخزون)
                if voucher.approve(request.user):
                    # بعد الاعتماد، إنشاء القيد المحاسبي
                    from product.services.voucher_accounting_service import create_issue_voucher_entry
                    create_issue_voucher_entry(voucher)
                    
                    messages.success(request, 'تم اعتماد إذن الصرف بنجاح')
                else:
                    messages.error(request, 'فشل اعتماد الإذن - تحقق من توفر الكمية')
        except Exception as e:
            messages.error(request, f'حدث خطأ: {str(e)}')
        
        return redirect('product:issue_voucher_detail', pk=pk)
