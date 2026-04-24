"""
Financial Subcategory Views
واجهات إدارة التصنيفات المالية الفرعية
"""
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.views.generic import ListView, CreateView, UpdateView
from django.urls import reverse_lazy, reverse
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.shortcuts import get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from ..models.categories import FinancialCategory, FinancialSubcategory


class SubcategoryListView(LoginRequiredMixin, ListView):
    """قائمة التصنيفات الفرعية لتصنيف معين"""
    model = FinancialSubcategory
    template_name = 'financial/subcategories/list.html'
    context_object_name = 'subcategories'
    
    def get_queryset(self):
        self.category = get_object_or_404(FinancialCategory, pk=self.kwargs['category_id'])
        return FinancialSubcategory.objects.filter(
            parent_category=self.category
        ).order_by('display_order', 'name')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'active_menu': 'financial',
            'category': self.category,
            'title': f'التصنيفات الفرعية - {self.category.name}',
            'breadcrumb_items': [
                {'title': 'الرئيسية', 'url': reverse_lazy('core:dashboard'), 'icon': 'fas fa-home'},
                {'title': 'المالية', 'url': reverse_lazy('financial:dashboard'), 'icon': 'fas fa-coins'},
                {'title': 'التصنيفات المالية', 'url': reverse_lazy('financial:category_list')},
                {'title': self.category.name, 'active': True}
            ],
            'header_buttons': [
                {
                    'url': reverse_lazy('financial:subcategory_create', kwargs={'category_id': self.category.pk}),
                    'icon': 'fa-plus',
                    'text': 'إضافة تصنيف فرعي',
                    'class': 'btn-primary'
                },
                {
                    'url': reverse_lazy('financial:category_list'),
                    'icon': 'fa-arrow-right',
                    'text': 'العودة',
                    'class': 'btn-outline-secondary'
                }
            ]
        })
        return context


class SubcategoryCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """إضافة تصنيف فرعي جديد"""
    model = FinancialSubcategory
    template_name = 'financial/subcategories/form.html'
    fields = ['code', 'name', 'is_active', 'display_order']
    permission_required = 'financial.add_financialsubcategory'
    
    def dispatch(self, request, *args, **kwargs):
        self.category = get_object_or_404(FinancialCategory, pk=self.kwargs['category_id'])
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        form.instance.parent_category = self.category
        messages.success(self.request, _('تم إضافة التصنيف الفرعي بنجاح'))
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('financial:subcategory_list', kwargs={'category_id': self.category.pk})
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'active_menu': 'financial',
            'category': self.category,
            'title': f'إضافة تصنيف فرعي - {self.category.name}',
            'breadcrumb_items': [
                {'title': 'الرئيسية', 'url': reverse_lazy('core:dashboard'), 'icon': 'fas fa-home'},
                {'title': 'المالية', 'url': reverse_lazy('financial:dashboard'), 'icon': 'fas fa-coins'},
                {'title': 'التصنيفات المالية', 'url': reverse_lazy('financial:category_list')},
                {'title': self.category.name, 'url': reverse_lazy('financial:subcategory_list', kwargs={'category_id': self.category.pk})},
                {'title': 'إضافة تصنيف فرعي', 'active': True}
            ],
            'header_buttons': [
                {
                    'url': reverse_lazy('financial:subcategory_list', kwargs={'category_id': self.category.pk}),
                    'icon': 'fa-arrow-right',
                    'text': 'العودة',
                    'class': 'btn-outline-secondary'
                }
            ]
        })
        return context


class SubcategoryUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """تعديل تصنيف فرعي"""
    model = FinancialSubcategory
    template_name = 'financial/subcategories/form.html'
    fields = ['code', 'name', 'is_active', 'display_order']
    permission_required = 'financial.change_financialsubcategory'
    
    def form_valid(self, form):
        messages.success(self.request, _('تم تحديث التصنيف الفرعي بنجاح'))
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('financial:subcategory_list', kwargs={'category_id': self.object.parent_category.pk})
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'active_menu': 'financial',
            'category': self.object.parent_category,
            'title': f'تعديل تصنيف فرعي: {self.object.name}',
            'breadcrumb_items': [
                {'title': 'الرئيسية', 'url': reverse_lazy('core:dashboard'), 'icon': 'fas fa-home'},
                {'title': 'المالية', 'url': reverse_lazy('financial:dashboard'), 'icon': 'fas fa-coins'},
                {'title': 'التصنيفات المالية', 'url': reverse_lazy('financial:category_list')},
                {'title': self.object.parent_category.name, 'url': reverse_lazy('financial:subcategory_list', kwargs={'category_id': self.object.parent_category.pk})},
                {'title': 'تعديل تصنيف فرعي', 'active': True}
            ],
            'header_buttons': [
                {
                    'url': reverse_lazy('financial:subcategory_list', kwargs={'category_id': self.object.parent_category.pk}),
                    'icon': 'fa-arrow-right',
                    'text': 'العودة',
                    'class': 'btn-outline-secondary'
                }
            ]
        })
        return context


@require_POST
def subcategory_delete(request, pk):
    """حذف تصنيف فرعي - مع التحقق من عدم وجود حركات مالية"""
    from ..models.journal_entry import JournalEntryLine
    subcategory = get_object_or_404(FinancialSubcategory, pk=pk)
    category_id = subcategory.parent_category.pk

    # التحقق من وجود حركات مالية مرتبطة
    has_transactions = JournalEntryLine.objects.filter(financial_subcategory=subcategory).exists()
    if has_transactions:
        messages.error(request, f'لا يمكن حذف "{subcategory.name}" لأنه مرتبط بحركات مالية مسجلة.')
        return redirect('financial:subcategory_list', category_id=category_id)

    try:
        subcategory.delete()
        messages.success(request, _('تم حذف التصنيف الفرعي بنجاح'))
    except Exception as e:
        messages.error(request, f'فشل حذف التصنيف الفرعي: {str(e)}')

    return redirect('financial:subcategory_list', category_id=category_id)
