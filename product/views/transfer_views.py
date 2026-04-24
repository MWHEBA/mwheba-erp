"""
Transfer Voucher Views - عروض أذون التحويل المخزني
"""
from django.views.generic import ListView, DetailView, View
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.db import transaction
from django.http import JsonResponse
from decimal import Decimal
import logging

from product.models.inventory_movement import InventoryMovement
from product.models.stock_management import Stock, Warehouse
from product.models.product_core import Product
from product.forms import TransferVoucherForm
from product.services.transfer_service import TransferService

logger = logging.getLogger(__name__)


class TransferVoucherListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """قائمة أذون التحويل المخزني"""
    model = InventoryMovement
    template_name = 'product/vouchers/transfer_voucher_list.html'
    context_object_name = 'vouchers'
    paginate_by = 20
    permission_required = 'product.view_inventorymovement'
    
    def get_queryset(self):
        # جلب حركات التحويل (transfer_out فقط لأنها الحركة الرئيسية)
        queryset = InventoryMovement.objects.filter(
            movement_type='transfer_out',
            document_type='transfer'
        ).select_related(
            'product', 'warehouse', 'created_by', 'approved_by', 'reference_movement'
        ).order_by('-movement_date', '-created_at')
        
        # فلترة حسب المخزن المصدر
        from_warehouse_id = self.request.GET.get('from_warehouse')
        if from_warehouse_id:
            queryset = queryset.filter(warehouse_id=from_warehouse_id)
        
        # فلترة حسب المخزن الهدف
        to_warehouse_id = self.request.GET.get('to_warehouse')
        if to_warehouse_id:
            queryset = queryset.filter(reference_movement__warehouse_id=to_warehouse_id)
        
        # فلترة حسب الحالة
        status = self.request.GET.get('status')
        if status == 'approved':
            queryset = queryset.filter(is_approved=True)
        elif status == 'pending':
            queryset = queryset.filter(is_approved=False)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # إنشاء form instance للمودال
        from product.forms import TransferVoucherForm
        form = TransferVoucherForm()
        
        context.update({
            'active_menu': 'product',
            'title': 'أذون التحويل المخزني',
            'header_buttons': [
                {
                    'onclick': 'openTransferVoucherModal()',
                    'icon': 'fa-exchange-alt',
                    'text': 'تحويل مخزني جديد',
                    'class': 'btn-primary',
                    'id': 'create-transfer-btn'
                }
            ],
            'breadcrumb_items': [
                {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
                {'title': 'المخزون', 'url': reverse('product:product_list'), 'icon': 'fas fa-boxes'},
                {'title': 'أذون التحويل', 'active': True}
            ],
            'warehouses': Warehouse.objects.filter(is_active=True),
            'form': form,
            'table_headers': self._get_table_headers(),
            'table_data': self._prepare_table_data(),
            'primary_key': 'id',
        })
        return context
    
    def _get_table_headers(self):
        return [
            {'key': 'document_number', 'label': 'رقم الإذن', 'sortable': True, 'width': '10%'},
            {'key': 'movement_date', 'label': 'التاريخ', 'sortable': True, 'width': '10%', 'format': 'html'},
            {'key': 'product', 'label': 'المنتج', 'sortable': True, 'width': '18%'},
            {'key': 'from_warehouse', 'label': 'من مخزن', 'sortable': True, 'width': '13%'},
            {'key': 'to_warehouse', 'label': 'إلى مخزن', 'sortable': True, 'width': '13%'},
            {'key': 'quantity', 'label': 'الكمية', 'sortable': True, 'width': '8%', 'class': 'text-center'},
            {'key': 'total_cost', 'label': 'القيمة', 'sortable': True, 'width': '10%', 'class': 'text-center', 'format': 'html'},
            {'key': 'status', 'label': 'الحالة', 'sortable': True, 'width': '8%', 'class': 'text-center', 'format': 'html'},
            {'key': 'actions', 'label': 'الإجراءات', 'width': '10%', 'class': 'text-center'}
        ]
    
    def _prepare_table_data(self):
        from django.template.defaultfilters import floatformat
        from utils.templatetags.utils_extras import smart_float
        
        table_data = []
        for voucher in self.get_queryset()[:self.paginate_by]:
            actions = [
                {'url': reverse('product:transfer_voucher_detail', args=[voucher.pk]), 
                 'icon': 'fas fa-eye', 'label': 'عرض', 'class': 'btn-outline-info btn-sm'}
            ]
            
            if not voucher.is_approved and self.request.user.has_perm('product.change_inventorymovement'):
                actions.append({
                    'url': reverse('product:transfer_voucher_approve', args=[voucher.pk]),
                    'icon': 'fas fa-check', 'label': 'اعتماد', 'class': 'btn-outline-success btn-sm'
                })
            
            # الحصول على المخزن الهدف من الحركة المرتبطة
            to_warehouse_name = voucher.reference_movement.warehouse.name if voucher.reference_movement else '-'
            
            # تنسيق التاريخ والوقت على سطرين
            from django.utils.formats import date_format
            date_part = date_format(voucher.movement_date, 'Y-m-d')
            time_part = date_format(voucher.movement_date, 'h:i A')
            formatted_date = f'{date_part}<br><small class="text-muted">{time_part}</small>'
            
            row_data = {
                'id': voucher.id,
                'document_number': voucher.document_number,
                'movement_date': formatted_date,
                'product': voucher.product.name,
                'from_warehouse': voucher.warehouse.name,
                'to_warehouse': to_warehouse_name,
                'quantity': voucher.quantity,
                'total_cost': f'{smart_float(voucher.total_cost)} ج.م',
                'status': f'<span class="badge bg-{"success" if voucher.is_approved else "warning"}">{"معتمد" if voucher.is_approved else "معلق"}</span>',
                'actions': actions
            }
            table_data.append(row_data)
        
        return table_data


class TransferVoucherCreateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """إنشاء إذن تحويل مخزني جديد"""
    permission_required = 'product.add_inventorymovement'
    
    def get(self, request):
        from product.forms import TransferVoucherForm
        form = TransferVoucherForm()
        context = {
            'active_menu': 'product',
            'title': 'تحويل مخزني جديد',
            'form': form,
            'is_modal': True,
        }
        return render(request, 'product/vouchers/transfer_voucher_form.html', context)
    
    def post(self, request):
        from product.forms import TransferVoucherForm
        form = TransferVoucherForm(request.POST)
        
        if not form.is_valid():
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'errors': form.errors
                }, status=400)
            return render(request, 'product/vouchers/transfer_voucher_form.html', {
                'form': form,
                'title': 'تحويل مخزني جديد'
            })
        
        product = form.cleaned_data['product']
        from_warehouse = form.cleaned_data['from_warehouse']
        to_warehouse = form.cleaned_data['to_warehouse']
        quantity = form.cleaned_data['quantity']
        reference_document = form.cleaned_data.get('reference_document', '')
        transferred_by_name = form.cleaned_data.get('transferred_by_name', '')
        notes = form.cleaned_data.get('notes', '')
        
        try:
            # استخدام TransferService لإنشاء التحويل
            transfer_service = TransferService()
            movement_out, movement_in = transfer_service.create_transfer(
                product=product,
                from_warehouse=from_warehouse,
                to_warehouse=to_warehouse,
                quantity=quantity,
                user=request.user,
                reference_document=reference_document,
                transferred_by_name=transferred_by_name,
                notes=notes
            )
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': 'تم إنشاء إذن التحويل بنجاح',
                    'voucher_id': movement_out.pk,
                    'redirect_url': reverse('product:transfer_voucher_detail', args=[movement_out.pk])
                })
            
            messages.success(request, 'تم إنشاء إذن التحويل بنجاح')
            return redirect('product:transfer_voucher_detail', pk=movement_out.pk)
            
        except ValueError as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': str(e)
                }, status=400)
            messages.error(request, str(e))
            return render(request, 'product/vouchers/transfer_voucher_form.html', {
                'form': form,
                'title': 'تحويل مخزني جديد'
            })
        except Exception as e:
            import traceback
            logger.error(f"Error creating transfer: {str(e)}\n{traceback.format_exc()}")
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': f'حدث خطأ: {str(e)}'
                }, status=500)
            messages.error(request, f'حدث خطأ: {str(e)}')
            return render(request, 'product/vouchers/transfer_voucher_form.html', {
                'form': form,
                'title': 'تحويل مخزني جديد'
            })
    
    def form_invalid(self, form):
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'errors': form.errors
            }, status=400)
        return super().form_invalid(form)


class TransferVoucherDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    """تفاصيل إذن تحويل مخزني"""
    model = InventoryMovement
    template_name = 'product/vouchers/transfer_voucher_detail.html'
    context_object_name = 'voucher'
    permission_required = 'product.view_inventorymovement'
    
    def get_queryset(self):
        return InventoryMovement.objects.filter(
            movement_type='transfer_out',
            document_type='transfer'
        ).select_related('reference_movement')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        voucher = self.object
        
        header_buttons = [
            {'url': reverse('product:transfer_voucher_list'), 'icon': 'fa-arrow-right', 
             'text': 'العودة', 'class': 'btn-outline-secondary'}
        ]
        
        if not voucher.is_approved and self.request.user.has_perm('product.change_inventorymovement'):
            header_buttons.insert(0, {
                'onclick': 'confirmApprove()',
                'icon': 'fa-check', 
                'text': 'اعتماد', 
                'class': 'btn-success'
            })
        
        # الحصول على حركة الدخول المرتبطة
        movement_in = voucher.reference_movement
        
        context.update({
            'active_menu': 'product',
            'title': f'تحويل مخزني - {voucher.document_number}',
            'header_buttons': header_buttons,
            'breadcrumb_items': [
                {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
                {'title': 'أذون التحويل', 'url': reverse('product:transfer_voucher_list')},
                {'title': voucher.document_number, 'active': True}
            ],
            'unit_name': voucher.product.unit.name if voucher.product.unit else 'وحدة',
            'movement_in': movement_in,
            'to_warehouse': movement_in.warehouse if movement_in else None,
        })
        return context


class TransferVoucherApproveView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """اعتماد إذن تحويل مخزني"""
    permission_required = 'product.change_inventorymovement'
    
    def post(self, request, pk):
        voucher = get_object_or_404(
            InventoryMovement, 
            pk=pk, 
            movement_type='transfer_out',
            document_type='transfer'
        )
        
        if voucher.is_approved:
            messages.warning(request, 'الإذن معتمد مسبقاً')
            return redirect('product:transfer_voucher_detail', pk=pk)
        
        try:
            # استخدام TransferService للاعتماد
            transfer_service = TransferService()
            
            logger.info(f"Starting transfer approval for voucher {pk}")
            
            if transfer_service.approve_transfer(voucher, request.user):
                messages.success(request, 'تم اعتماد إذن التحويل بنجاح')
            else:
                messages.error(request, 'فشل اعتماد الإذن - تحقق من توفر الكمية في المخزن المصدر')
                
        except ValueError as e:
            logger.error(f"ValueError in transfer approval: {str(e)}")
            messages.error(request, f'خطأ في البيانات: {str(e)}')
        except Exception as e:
            logger.error(f"Exception in transfer approval: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            messages.error(request, f'حدث خطأ: {str(e)}')
        
        return redirect('product:transfer_voucher_detail', pk=pk)
