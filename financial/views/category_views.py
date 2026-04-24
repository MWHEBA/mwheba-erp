"""
Financial Category Views
واجهات إدارة التصنيفات المالية
"""
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.views.generic import ListView, CreateView, UpdateView
from django.urls import reverse_lazy
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.db.models import Q

from ..models.categories import FinancialCategory
from ..models.chart_of_accounts import ChartOfAccounts


class CategoryListView(LoginRequiredMixin, ListView):
    """قائمة التصنيفات المالية"""
    model = FinancialCategory
    template_name = 'financial/categories/list.html'
    context_object_name = 'categories'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = FinancialCategory.objects.select_related(
            'default_revenue_account',
            'default_expense_account'
        ).prefetch_related('subcategories').order_by('display_order', 'name')
        
        # فلترة حسب الحالة
        status = self.request.GET.get('status')
        if status == 'active':
            queryset = queryset.filter(is_active=True)
        elif status == 'inactive':
            queryset = queryset.filter(is_active=False)
        
        # بحث
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(code__icontains=search)
            )
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'active_menu': 'financial',
            'title': 'التصنيفات المالية',
            'breadcrumb_items': [
                {'title': 'الرئيسية', 'url': reverse_lazy('core:dashboard'), 'icon': 'fas fa-home'},
                {'title': 'المالية', 'url': reverse_lazy('financial:dashboard'), 'icon': 'fas fa-coins'},
                {'title': 'التصنيفات المالية', 'active': True}
            ],
            'header_buttons': [
                {
                    'url': reverse_lazy('financial:category_create'),
                    'icon': 'fa-plus',
                    'text': 'إضافة تصنيف',
                    'class': 'btn-primary'
                }
            ]
        })
        return context


class CategoryCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """إضافة تصنيف مالي جديد"""
    model = FinancialCategory
    template_name = 'financial/categories/form.html'
    fields = [
        'code', 'name', 'description',
        'default_revenue_account', 'default_expense_account',
        'is_active', 'display_order'
    ]
    success_url = reverse_lazy('financial:category_list')
    permission_required = 'financial.add_financialcategory'
    
    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        
        # تحسين عرض الحسابات المحاسبية
        revenue_accounts = ChartOfAccounts.objects.filter(
            account_type__category='revenue',
            is_active=True,
            is_leaf=True
        ).select_related('account_type')
        
        expense_accounts = ChartOfAccounts.objects.filter(
            account_type__category='expense',
            is_active=True,
            is_leaf=True
        ).select_related('account_type')
        
        form.fields['default_revenue_account'].queryset = revenue_accounts
        form.fields['default_expense_account'].queryset = expense_accounts
        
        # تحسين labels
        form.fields['code'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'مثال: tuition'
        })
        form.fields['name'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'مثال: رسوم الخدمات'
        })
        form.fields['description'].widget.attrs.update({
            'class': 'form-control',
            'rows': 3
        })
        form.fields['display_order'].widget.attrs.update({
            'class': 'form-control',
            'value': 0
        })
        
        return form
    
    def form_valid(self, form):
        messages.success(self.request, _('تم إضافة التصنيف المالي بنجاح'))
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'active_menu': 'financial',
            'title': 'إضافة تصنيف مالي',
            'breadcrumb_items': [
                {'title': 'الرئيسية', 'url': reverse_lazy('core:dashboard'), 'icon': 'fas fa-home'},
                {'title': 'المالية', 'url': reverse_lazy('financial:dashboard'), 'icon': 'fas fa-coins'},
                {'title': 'التصنيفات المالية', 'url': reverse_lazy('financial:category_list')},
                {'title': 'إضافة تصنيف', 'active': True}
            ],
            'header_buttons': [
                {
                    'url': reverse_lazy('financial:category_list'),
                    'icon': 'fa-arrow-right',
                    'text': 'العودة',
                    'class': 'btn-outline-secondary'
                }
            ]
        })
        return context


class CategoryUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """تعديل تصنيف مالي"""
    model = FinancialCategory
    template_name = 'financial/categories/form.html'
    fields = [
        'code', 'name', 'description',
        'default_revenue_account', 'default_expense_account',
        'is_active', 'display_order'
    ]
    success_url = reverse_lazy('financial:category_list')
    permission_required = 'financial.change_financialcategory'
    
    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        
        # تحسين عرض الحسابات المحاسبية
        revenue_accounts = ChartOfAccounts.objects.filter(
            account_type__category='revenue',
            is_active=True,
            is_leaf=True
        ).select_related('account_type')
        
        expense_accounts = ChartOfAccounts.objects.filter(
            account_type__category='expense',
            is_active=True,
            is_leaf=True
        ).select_related('account_type')
        
        form.fields['default_revenue_account'].queryset = revenue_accounts
        form.fields['default_expense_account'].queryset = expense_accounts
        
        # تحسين widgets
        form.fields['code'].widget.attrs.update({'class': 'form-control'})
        form.fields['name'].widget.attrs.update({'class': 'form-control'})
        form.fields['description'].widget.attrs.update({'class': 'form-control', 'rows': 3})
        form.fields['display_order'].widget.attrs.update({'class': 'form-control'})
        
        return form
    
    def form_valid(self, form):
        messages.success(self.request, _('تم تحديث التصنيف المالي بنجاح'))
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'active_menu': 'financial',
            'title': f'تعديل تصنيف: {self.object.name}',
            'breadcrumb_items': [
                {'title': 'الرئيسية', 'url': reverse_lazy('core:dashboard'), 'icon': 'fas fa-home'},
                {'title': 'المالية', 'url': reverse_lazy('financial:dashboard'), 'icon': 'fas fa-coins'},
                {'title': 'التصنيفات المالية', 'url': reverse_lazy('financial:category_list')},
                {'title': 'تعديل تصنيف', 'active': True}
            ],
            'header_buttons': [
                {
                    'url': reverse_lazy('financial:category_list'),
                    'icon': 'fa-arrow-right',
                    'text': 'العودة',
                    'class': 'btn-outline-secondary'
                }
            ]
        })
        return context
