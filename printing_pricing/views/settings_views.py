"""
Views for managing settings in the new system
"""

import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin as DjangoLoginRequiredMixin
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib import messages
from django.urls import reverse_lazy
from django.db import models
from django.http import JsonResponse
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, View
from django.shortcuts import render

class StaffRequiredMixin(UserPassesTestMixin):
    """Mixin to ensure only staff/admin users can access system settings."""
    raise_exception = True

    def test_func(self):
        return self.request.user.is_authenticated and (self.request.user.is_staff or self.request.user.is_superuser)

# Override LoginRequiredMixin locally so all views in this file inherit StaffRequiredMixin automatically
class LoginRequiredMixin(StaffRequiredMixin):
    pass
from django.utils.translation import gettext_lazy as _
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q


# ==================== Mixins مشتركة ====================

class AjaxDeleteMixin:
    """Mixin لإضافة دعم AJAX للـ DeleteViews مع تمرير متغيرات الكائن بدقة"""
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        model_name = self.model._meta.model_name
        context[model_name] = self.object
        context['item'] = self.object
        context['object'] = self.object
        
        # تمرير الاسم بـ snake_case أيضاً (مثل product_type بدلاً من producttype)
        import re
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', self.model.__name__)
        snake_name = re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
        context[snake_name] = self.object
        
        context['action_url'] = self.request.path
        return context

    def delete(self, request, *args, **kwargs):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            self.object = self.get_object()
            self.object.delete()
            model_verbose_name = self.model._meta.verbose_name
            success_message = _('تم حذف {} بنجاح').format(model_verbose_name)
            return JsonResponse(
                {'success': True, 'message': success_message},
                content_type='application/json'
            )
        response = super().delete(request, *args, **kwargs)
        model_verbose_name = self.model._meta.verbose_name
        success_message = _('تم حذف {} بنجاح').format(model_verbose_name)
        messages.success(request, success_message)
        return response


class AjaxFormMixin:
    """Mixin يضيف AJAX support لـ CreateView و UpdateView تلقائياً مع دعم إعادة رسم الفورم بالأخطاء"""

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            model_verbose_name = self.model._meta.verbose_name
            return JsonResponse({'success': True, 'message': _('تم حفظ {} بنجاح').format(model_verbose_name)})
        return response

    def form_invalid(self, form):
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            from django.template.loader import render_to_string
            context = self.get_context_data(form=form)
            rendered_html = render_to_string(self.template_name, context, request=self.request)
            return JsonResponse({
                'success': False,
                'html': rendered_html,
                'errors': form.errors,
                'message': _('يرجى تصحيح الأخطاء الموضحة بالنموذج')
            })
        return super().form_invalid(form)

from ..models import (
    PaperType, PaperSize, PaperWeight, PaperOrigin,
    CoatingType, FinishingType, PackagingType,
    PieceSize, PlateSize, ProductType, ProductSize,
    OffsetMachineType, DigitalMachineType, OffsetSheetSize, DigitalSheetSize
)
from ..forms.settings_forms import (
    PaperTypeForm, PaperSizeForm, PaperWeightForm, PaperOriginForm,
    CoatingTypeForm, PieceSizeForm, PlateSizeForm,
    ProductTypeForm, ProductSizeForm,
    OffsetMachineTypeForm, DigitalMachineTypeForm, OffsetSheetSizeForm, DigitalSheetSizeForm
)

logger = logging.getLogger(__name__)


# ==================== عروض أنواع الورق ====================

class PaperTypeListView(LoginRequiredMixin, ListView):
    """عرض قائمة أنواع الورق"""
    model = PaperType
    template_name = 'printing_pricing/settings/paper_types/list.html'
    context_object_name = 'paper_types'
    paginate_by = 20

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('أنواع الورق')
        context['page_icon'] = 'fas fa-layer-group'
        context['page_subtitle'] = _('إدارة أنواع الورق المختلفة')
        context['header_buttons'] = [
            {
                'onclick': 'openCreateModal()',
                'icon': 'fa-plus',
                'text': _('إضافة جديد'),
                'class': 'btn-primary',
            },
        ]
        context['breadcrumb_items'] = [
            {
                'title': _('الرئيسية'),
                'url': '/',
                'icon': 'fas fa-home'
            },
            {
                'title': _('الإعدادات'),
                'url': reverse_lazy('printing_pricing:settings_home'),
                'icon': 'fas fa-cog'
            },
            {
                'title': _('أنواع الورق'),
                'url': '',
                'icon': 'fas fa-layer-group',
                'active': True
            }
        ]
        return context

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(description__icontains=search)
            )
        return queryset.order_by('name')


class PaperTypeCreateView(AjaxFormMixin, LoginRequiredMixin, CreateView):
    """عرض إنشاء نوع ورق جديد"""
    model = PaperType
    form_class = PaperTypeForm
    template_name = 'printing_pricing/settings/paper_types/form_modal.html'
    success_url = reverse_lazy('printing_pricing:paper_type_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('إضافة نوع ورق جديد')
        context['action_url'] = self.request.path
        return context

    def form_valid(self, form):
        messages.success(self.request, _('تم إنشاء نوع الورق بنجاح'))
        return super().form_valid(form)


class PaperTypeUpdateView(AjaxFormMixin, LoginRequiredMixin, UpdateView):
    """عرض تحديث نوع الورق"""
    model = PaperType
    form_class = PaperTypeForm
    template_name = 'printing_pricing/settings/paper_types/form_modal.html'
    success_url = reverse_lazy('printing_pricing:paper_type_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('تحديث نوع الورق')
        context['action_url'] = self.request.path
        return context

    def form_valid(self, form):
        messages.success(self.request, _('تم تحديث نوع الورق بنجاح'))
        return super().form_valid(form)


class PaperTypeDeleteView(AjaxDeleteMixin, LoginRequiredMixin, DeleteView):
    """عرض حذف نوع الورق"""
    model = PaperType
    template_name = 'printing_pricing/settings/paper_types/delete_modal.html'
    success_url = reverse_lazy('printing_pricing:paper_type_list')


# ==================== عروض مقاسات الورق ====================

class PaperSizeListView(LoginRequiredMixin, ListView):
    """عرض قائمة مقاسات الورق"""
    model = PaperSize
    template_name = 'printing_pricing/settings/paper_sizes/list.html'
    context_object_name = 'paper_sizes'
    paginate_by = 20

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('مقاسات الورق')
        context['page_icon'] = 'fas fa-ruler-combined'
        context['page_subtitle'] = _('إدارة مقاسات الورق المتاحة')
        context['header_buttons'] = [
            {
                'onclick': 'openCreateModal()',
                'icon': 'fa-plus',
                'text': _('إضافة جديد'),
                'class': 'btn-primary',
            },
        ]
        context['breadcrumb_items'] = [
            {
                'title': _('الرئيسية'),
                'url': '/',
                'icon': 'fas fa-home'
            },
            {
                'title': _('الإعدادات'),
                'url': reverse_lazy('printing_pricing:settings_home'),
                'icon': 'fas fa-cog'
            },
            {
                'title': _('مقاسات الورق'),
                'url': '',
                'icon': 'fas fa-ruler-combined',
                'active': True
            }
        ]
        return context

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search)
        return queryset.order_by('name')


class PaperSizeCreateView(AjaxFormMixin, LoginRequiredMixin, CreateView):
    """عرض إنشاء مقاس ورق جديد"""
    model = PaperSize
    form_class = PaperSizeForm
    template_name = 'printing_pricing/settings/paper_sizes/form_modal.html'
    success_url = reverse_lazy('printing_pricing:paper_size_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('إضافة مقاس ورق جديد')
        context['action_url'] = self.request.path
        return context

    def form_valid(self, form):
        messages.success(self.request, _('تم إنشاء مقاس الورق بنجاح'))
        return super().form_valid(form)


class PaperSizeUpdateView(AjaxFormMixin, LoginRequiredMixin, UpdateView):
    """عرض تحديث مقاس الورق"""
    model = PaperSize
    form_class = PaperSizeForm
    template_name = 'printing_pricing/settings/paper_sizes/form_modal.html'
    success_url = reverse_lazy('printing_pricing:paper_size_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('تحديث مقاس الورق')
        context['action_url'] = self.request.path
        return context

    def form_valid(self, form):
        messages.success(self.request, _('تم تحديث مقاس الورق بنجاح'))
        return super().form_valid(form)


class PaperSizeDeleteView(AjaxDeleteMixin, LoginRequiredMixin, DeleteView):
    """عرض حذف مقاس الورق"""
    model = PaperSize
    template_name = 'printing_pricing/settings/paper_sizes/delete_modal.html'
    success_url = reverse_lazy('printing_pricing:paper_size_list')


# ==================== عروض أوزان الورق ====================

class PaperWeightListView(LoginRequiredMixin, ListView):
    """عرض قائمة أوزان الورق"""
    model = PaperWeight
    template_name = 'printing_pricing/settings/paper_weights/list.html'
    context_object_name = 'paper_weights'
    paginate_by = 20

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('أوزان الورق')
        context['page_icon'] = 'fas fa-weight-hanging'
        context['page_subtitle'] = _('إدارة أوزان الورق المختلفة')
        context['header_buttons'] = [
            {
                'onclick': 'openCreateModal()',
                'icon': 'fa-plus',
                'text': _('إضافة جديد'),
                'class': 'btn-primary',
            },
        ]
        context['breadcrumb_items'] = [
            {
                'title': _('الرئيسية'),
                'url': '/',
                'icon': 'fas fa-home'
            },
            {
                'title': _('الإعدادات'),
                'url': reverse_lazy('printing_pricing:settings_home'),
                'icon': 'fas fa-cog'
            },
            {
                'title': _('أوزان الورق'),
                'url': '',
                'icon': 'fas fa-weight-hanging',
                'active': True
            }
        ]
        return context

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(gsm__icontains=search)
            )
        return queryset.order_by('gsm')


class PaperWeightCreateView(AjaxFormMixin, LoginRequiredMixin, CreateView):
    """عرض إنشاء وزن ورق جديد"""
    model = PaperWeight
    form_class = PaperWeightForm
    template_name = 'printing_pricing/settings/paper_weights/form_modal.html'
    success_url = reverse_lazy('printing_pricing:paper_weight_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('إضافة وزن ورق جديد')
        context['action_url'] = self.request.path
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': _('تم إنشاء وزن الورق بنجاح')})
        messages.success(self.request, _('تم إنشاء وزن الورق بنجاح'))
        return response

    def form_invalid(self, form):
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'errors': form.errors})
        return super().form_invalid(form)


class PaperWeightUpdateView(AjaxFormMixin, LoginRequiredMixin, UpdateView):
    """عرض تحديث وزن الورق"""
    model = PaperWeight
    form_class = PaperWeightForm
    template_name = 'printing_pricing/settings/paper_weights/form_modal.html'
    success_url = reverse_lazy('printing_pricing:paper_weight_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('تحديث وزن الورق')
        context['action_url'] = self.request.path
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': _('تم تحديث وزن الورق بنجاح')})
        messages.success(self.request, _('تم تحديث وزن الورق بنجاح'))
        return response

    def form_invalid(self, form):
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'errors': form.errors})
        return super().form_invalid(form)


class PaperWeightDeleteView(AjaxDeleteMixin, LoginRequiredMixin, DeleteView):
    """عرض حذف وزن الورق"""
    model = PaperWeight
    template_name = 'printing_pricing/settings/paper_weights/delete_modal.html'
    success_url = reverse_lazy('printing_pricing:paper_weight_list')


# ==================== عروض مناشئ الورق ====================

class PaperOriginListView(LoginRequiredMixin, ListView):
    """عرض قائمة مناشئ الورق"""
    model = PaperOrigin
    template_name = 'printing_pricing/settings/paper_origins/list.html'
    context_object_name = 'paper_origins'
    paginate_by = 20

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('مناشئ الورق')
        context['page_icon'] = 'fas fa-globe-americas'
        context['page_subtitle'] = _('إدارة مناشئ الورق')
        context['header_buttons'] = [
            {
                'onclick': 'openCreateModal()',
                'icon': 'fa-plus',
                'text': _('إضافة جديد'),
                'class': 'btn-primary',
            },
        ]
        context['breadcrumb_items'] = [
            {
                'title': _('الرئيسية'),
                'url': '/',
                'icon': 'fas fa-home'
            },
            {
                'title': _('الإعدادات'),
                'url': reverse_lazy('printing_pricing:settings_home'),
                'icon': 'fas fa-cog'
            },
            {
                'title': _('مناشئ الورق'),
                'url': '',
                'icon': 'fas fa-globe-americas',
                'active': True
            }
        ]
        return context

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(code__icontains=search)
            )
        return queryset.order_by('name')


class PaperOriginCreateView(AjaxFormMixin, LoginRequiredMixin, CreateView):
    """عرض إنشاء منشأ ورق جديد"""
    model = PaperOrigin
    form_class = PaperOriginForm
    template_name = 'printing_pricing/settings/paper_origins/form_modal.html'
    success_url = reverse_lazy('printing_pricing:paper_origin_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('إضافة منشأ ورق جديد')
        context['action_url'] = self.request.path
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': _('تم إنشاء منشأ الورق بنجاح')})
        messages.success(self.request, _('تم إنشاء منشأ الورق بنجاح'))
        return response

    def form_invalid(self, form):
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'errors': form.errors})
        return super().form_invalid(form)


class PaperOriginUpdateView(AjaxFormMixin, LoginRequiredMixin, UpdateView):
    """عرض تحديث منشأ الورق"""
    model = PaperOrigin
    form_class = PaperOriginForm
    template_name = 'printing_pricing/settings/paper_origins/form_modal.html'
    success_url = reverse_lazy('printing_pricing:paper_origin_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('تحديث منشأ الورق')
        context['action_url'] = self.request.path
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': _('تم تحديث منشأ الورق بنجاح')})
        messages.success(self.request, _('تم تحديث منشأ الورق بنجاح'))
        return response

    def form_invalid(self, form):
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'errors': form.errors})
        return super().form_invalid(form)


class PaperOriginDeleteView(AjaxDeleteMixin, LoginRequiredMixin, DeleteView):
    """عرض حذف منشأ الورق"""
    model = PaperOrigin
    template_name = 'printing_pricing/settings/paper_origins/delete_modal.html'
    success_url = reverse_lazy('printing_pricing:paper_origin_list')





# ==================== عروض أنواع التغطية ====================

class CoatingTypeListView(LoginRequiredMixin, ListView):
    """عرض قائمة أنواع التغطية"""
    model = CoatingType
    template_name = 'printing_pricing/settings/coating_type/list.html'
    context_object_name = 'coating_types'
    paginate_by = 20

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('أنواع التغطية')
        context['page_icon'] = 'fas fa-paint-brush'
        context['page_subtitle'] = _('إدارة أنواع التغطية والورنيش')
        context['header_buttons'] = [
            {
                'onclick': 'openCreateModal()',
                'icon': 'fa-plus',
                'text': _('إضافة جديد'),
                'class': 'btn-primary',
            },
        ]
        context['breadcrumb_items'] = [
            {
                'title': _('الرئيسية'),
                'url': '/',
                'icon': 'fas fa-home'
            },
            {
                'title': _('الإعدادات'),
                'url': reverse_lazy('printing_pricing:settings_home'),
                'icon': 'fas fa-cog'
            },
            {
                'title': _('أنواع التغطية'),
                'url': '',
                'icon': 'fas fa-paint-brush',
                'active': True
            }
        ]
        return context

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(description__icontains=search)
            )
        return queryset.order_by('name')


class CoatingTypeCreateView(AjaxFormMixin, LoginRequiredMixin, CreateView):
    """عرض إنشاء نوع تغطية جديد"""
    model = CoatingType
    form_class = CoatingTypeForm
    template_name = 'printing_pricing/settings/coating_type/form_modal.html'
    success_url = reverse_lazy('printing_pricing:coating_type_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('إضافة نوع تغطية جديد')
        context['action_url'] = self.request.path
        return context

    def form_valid(self, form):
        messages.success(self.request, _('تم إنشاء نوع التغطية بنجاح'))
        return super().form_valid(form)


class CoatingTypeUpdateView(AjaxFormMixin, LoginRequiredMixin, UpdateView):
    """عرض تحديث نوع التغطية"""
    model = CoatingType
    form_class = CoatingTypeForm
    template_name = 'printing_pricing/settings/coating_type/form_modal.html'
    success_url = reverse_lazy('printing_pricing:coating_type_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('تحديث نوع التغطية')
        context['action_url'] = self.request.path
        return context

    def form_valid(self, form):
        messages.success(self.request, _('تم تحديث نوع التغطية بنجاح'))
        return super().form_valid(form)


class CoatingTypeDeleteView(AjaxDeleteMixin, LoginRequiredMixin, DeleteView):
    """عرض حذف نوع التغطية"""
    model = CoatingType
    template_name = 'printing_pricing/settings/coating_type/delete_modal.html'
    success_url = reverse_lazy('printing_pricing:coating_type_list')


# ==================== عروض أنواع خدمات الطباعة ====================

class FinishingTypeListView(LoginRequiredMixin, ListView):
    """عرض قائمة أنواع خدمات الطباعة"""
    model = FinishingType
    template_name = 'printing_pricing/settings/finishing_types/list.html'
    context_object_name = 'finishing_types'
    paginate_by = 20

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('أنواع خدمات الطباعة')
        context['page_icon'] = 'fas fa-magic'
        context['page_subtitle'] = _('إدارة أنواع التشطيب والتجليد')
        context['header_buttons'] = [
            {
                'onclick': 'openCreateModal()',
                'icon': 'fa-plus',
                'text': _('إضافة جديد'),
                'class': 'btn-primary',
            },
        ]
        context['breadcrumb_items'] = [
            {
                'title': _('الرئيسية'),
                'url': '/',
                'icon': 'fas fa-home'
            },
            {
                'title': _('الإعدادات'),
                'url': reverse_lazy('printing_pricing:settings_home'),
                'icon': 'fas fa-cog'
            },
            {
                'title': _('أنواع خدمات الطباعة'),
                'url': '',
                'icon': 'fas fa-magic',
                'active': True
            }
        ]
        return context

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(description__icontains=search)
            )
        return queryset.order_by('name')


class FinishingTypeCreateView(AjaxFormMixin, LoginRequiredMixin, CreateView):
    """عرض إنشاء نوع تشطيب جديد"""
    model = FinishingType
    template_name = 'printing_pricing/settings/finishing_types/form_modal.html'
    fields = ['name', 'description', 'is_active']
    success_url = reverse_lazy('printing_pricing:finishing_type_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('إضافة نوع تشطيب جديد')
        context['action_url'] = self.request.path
        return context

    def form_valid(self, form):
        messages.success(self.request, _('تم إنشاء نوع التشطيب بنجاح'))
        return super().form_valid(form)


class FinishingTypeUpdateView(AjaxFormMixin, LoginRequiredMixin, UpdateView):
    """عرض تحديث نوع التشطيب"""
    model = FinishingType
    template_name = 'printing_pricing/settings/finishing_types/form_modal.html'
    fields = ['name', 'description', 'is_active']
    success_url = reverse_lazy('printing_pricing:finishing_type_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('تحديث نوع التشطيب')
        context['action_url'] = self.request.path
        return context

    def form_valid(self, form):
        messages.success(self.request, _('تم تحديث نوع التشطيب بنجاح'))
        return super().form_valid(form)


class FinishingTypeDeleteView(AjaxDeleteMixin, LoginRequiredMixin, DeleteView):
    """عرض حذف نوع خدمة الطباعة"""
    model = FinishingType
    template_name = 'printing_pricing/settings/finishing_types/delete_modal.html'
    success_url = reverse_lazy('printing_pricing:finishing_type_list')


# ==================== عروض أنواع التقفيل ====================

class PackagingTypeListView(LoginRequiredMixin, ListView):
    """عرض قائمة أنواع التقفيل"""
    model = PackagingType
    template_name = 'printing_pricing/settings/packaging_types/list.html'
    context_object_name = 'packaging_types'
    paginate_by = 20

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('أنواع التقفيل')
        context['page_icon'] = 'fas fa-box'
        context['page_subtitle'] = _('إدارة أنواع التقفيل والتغليف')
        context['header_buttons'] = [
            {
                'onclick': 'openCreateModal()',
                'icon': 'fa-plus',
                'text': _('إضافة جديد'),
                'class': 'btn-primary',
            },
        ]
        context['breadcrumb_items'] = [
            {
                'title': _('الرئيسية'),
                'url': '/',
                'icon': 'fas fa-home'
            },
            {
                'title': _('الإعدادات'),
                'url': reverse_lazy('printing_pricing:settings_home'),
                'icon': 'fas fa-cog'
            },
            {
                'title': _('أنواع التقفيل'),
                'url': '',
                'icon': 'fas fa-box',
                'active': True
            }
        ]
        return context

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(description__icontains=search)
            )
        return queryset.order_by('name')


class PackagingTypeCreateView(AjaxFormMixin, LoginRequiredMixin, CreateView):
    """عرض إنشاء نوع تقفيل جديد"""
    model = PackagingType
    template_name = 'printing_pricing/settings/packaging_types/form_modal.html'
    fields = ['name', 'description', 'is_active']
    success_url = reverse_lazy('printing_pricing:packaging_type_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': _('تم إضافة نوع التقفيل بنجاح')})
        messages.success(self.request, _('تم إضافة نوع التقفيل بنجاح'))
        return response


class PackagingTypeUpdateView(AjaxFormMixin, LoginRequiredMixin, UpdateView):
    """عرض تحديث نوع التقفيل"""
    model = PackagingType
    template_name = 'printing_pricing/settings/packaging_types/form_modal.html'
    fields = ['name', 'description', 'is_active']
    success_url = reverse_lazy('printing_pricing:packaging_type_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': _('تم تحديث نوع التقفيل بنجاح')})
        messages.success(self.request, _('تم تحديث نوع التقفيل بنجاح'))
        return response


class PackagingTypeDeleteView(AjaxDeleteMixin, LoginRequiredMixin, DeleteView):
    """عرض حذف نوع التقفيل"""
    model = PackagingType
    template_name = 'printing_pricing/settings/packaging_types/delete_modal.html'
    success_url = reverse_lazy('printing_pricing:packaging_type_list')


# ==================== عروض مقاسات القطع ====================

class PieceSizeListView(LoginRequiredMixin, ListView):
    """عرض قائمة مقاسات القطع"""
    model = PieceSize
    template_name = 'printing_pricing/settings/piece_size/list.html'
    context_object_name = 'piece_sizes'
    paginate_by = 20

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('مقاسات القطع')
        context['page_icon'] = 'fas fa-cut'
        context['page_subtitle'] = _('إدارة مقاسات القطع المتاحة')
        create_url = reverse_lazy('printing_pricing:piece_size_create')
        context['header_buttons'] = [
            {
                'onclick': f"SettingsCRUD.openCreateModal('{create_url}')",
                'icon': 'fa-plus',
                'text': _('إضافة جديد'),
                'class': 'btn-primary',
            },
        ]
        context['breadcrumb_items'] = [
            {
                'title': _('الرئيسية'),
                'url': reverse_lazy('core:dashboard'),
                'icon': 'fas fa-home'
            },
            {
                'title': _('إعدادات التسعير'),
                'url': reverse_lazy('printing_pricing:settings_home'),
                'icon': 'fas fa-cog'
            },
            {
                'title': _('مقاسات القطع'),
                'url': '',
                'icon': 'fas fa-cut',
                'active': True
            }
        ]
        return context

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search)
        return queryset.order_by('name')


class PieceSizeCreateView(AjaxFormMixin, LoginRequiredMixin, CreateView):
    """عرض إنشاء مقاس قطع جديد"""
    model = PieceSize
    form_class = PieceSizeForm
    template_name = 'printing_pricing/settings/piece_size/form_modal.html'
    success_url = reverse_lazy('printing_pricing:piece_size_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('إضافة مقاس قطع جديد')
        context['action_url'] = self.request.path
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': _('تم إنشاء مقاس القطع بنجاح')})
        messages.success(self.request, _('تم إنشاء مقاس القطع بنجاح'))
        return response

    def form_invalid(self, form):
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'errors': form.errors})
        return super().form_invalid(form)


class PieceSizeUpdateView(AjaxFormMixin, LoginRequiredMixin, UpdateView):
    """عرض تحديث مقاس القطع"""
    model = PieceSize
    form_class = PieceSizeForm
    template_name = 'printing_pricing/settings/piece_size/form_modal.html'
    success_url = reverse_lazy('printing_pricing:piece_size_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('تحديث مقاس القطع')
        context['action_url'] = self.request.path
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': _('تم تحديث مقاس القطع بنجاح')})
        messages.success(self.request, _('تم تحديث مقاس القطع بنجاح'))
        return response

    def form_invalid(self, form):
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'errors': form.errors})
        return super().form_invalid(form)


class PieceSizeDeleteView(AjaxDeleteMixin, LoginRequiredMixin, DeleteView):
    """عرض حذف مقاس القطع"""
    model = PieceSize
    template_name = 'printing_pricing/settings/piece_size/delete_modal.html'
    success_url = reverse_lazy('printing_pricing:piece_size_list')


# ==================== صفحة الإعدادات الرئيسية ====================

@login_required
def settings_home(request):
    """الصفحة الرئيسية للإعدادات"""
    if not (request.user.is_staff or request.user.is_superuser):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied(_("غير مصرح لك بالوصول إلى هذه الصفحة."))
    from django.urls import reverse
    
    context = {
        'title': _('إعدادات النظام'),
        'paper_types_count': PaperType.objects.filter(is_active=True).count(),
        'paper_sizes_count': PaperSize.objects.filter(is_active=True).count(),
        'paper_weights_count': PaperWeight.objects.filter(is_active=True).count(),
        'paper_origins_count': PaperOrigin.objects.filter(is_active=True).count(),
        'coating_types_count': CoatingType.objects.filter(is_active=True).count(),
        'finishing_types_count': FinishingType.objects.filter(is_active=True).count(),
        'packaging_types_count': PackagingType.objects.filter(is_active=True).count(),
        'piece_sizes_count': PieceSize.objects.filter(is_active=True).count(),
        'plate_sizes_count': PlateSize.objects.filter(is_active=True).count(),
        'product_types_count': ProductType.objects.filter(is_active=True).count(),
        'product_sizes_count': ProductSize.objects.filter(is_active=True).count(),
        'offset_machine_types_count': OffsetMachineType.objects.filter(is_active=True).count(),
        'offset_sheet_sizes_count': OffsetSheetSize.objects.filter(is_active=True).count(),
        'digital_machine_types_count': DigitalMachineType.objects.filter(is_active=True).count(),
        'digital_sheet_sizes_count': DigitalSheetSize.objects.filter(is_active=True).count(),
        
        # بيانات الهيدر
        'page_title': 'إعدادات التسعير',
        'page_subtitle': 'إدارة وتخصيص إعدادات نظام التسعير',
        'page_icon': 'fas fa-cog',
        
        # البريدكرمب
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'تسعير الطباعة', 'url': reverse('printing_pricing:order_list'), 'icon': 'fas fa-print'},
            {'title': 'إعدادات التسعير', 'active': True},
        ],
    }
    return render(request, 'printing_pricing/settings/settings_home.html', context)


# ==================== عروض أنواع ماكينات الأوفست ====================

class OffsetMachineTypeListView(LoginRequiredMixin, ListView):
    """عرض قائمة أنواع ماكينات الأوفست"""
    model = OffsetMachineType
    template_name = 'printing_pricing/settings/offset_machine_type/list.html'
    context_object_name = 'machine_types'
    paginate_by = 20

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('أنواع ماكينات الأوفست')
        context['page_icon'] = 'fas fa-print'
        context['page_subtitle'] = _('إدارة أنواع ماكينات الأوفست')
        context['header_buttons'] = [
            {
                'onclick': 'openCreateModal()',
                'icon': 'fa-plus',
                'text': _('إضافة جديد'),
                'class': 'btn-primary',
            },
        ]
        context['breadcrumb_items'] = [
            {
                'title': _('الرئيسية'),
                'url': '/',
                'icon': 'fas fa-home'
            },
            {
                'title': _('الإعدادات'),
                'url': reverse_lazy('printing_pricing:settings_home'),
                'icon': 'fas fa-cog'
            },
            {
                'title': _('أنواع ماكينات الأوفست'),
                'url': '',
                'icon': 'fas fa-print',
                'active': True
            }
        ]
        return context

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(description__icontains=search)
            )
        return queryset.order_by('name')


class OffsetMachineTypeCreateView(AjaxFormMixin, LoginRequiredMixin, CreateView):
    """عرض إنشاء نوع ماكينة أوفست جديد"""
    model = OffsetMachineType
    form_class = OffsetMachineTypeForm
    template_name = 'printing_pricing/settings/offset_machine_type/form_modal.html'
    success_url = reverse_lazy('printing_pricing:offset_machine_type_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('إضافة نوع ماكينة أوفست جديد')
        context['action_url'] = self.request.path
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': _('تم إنشاء نوع ماكينة الأوفست بنجاح')})
        messages.success(self.request, _('تم إنشاء نوع ماكينة الأوفست بنجاح'))
        return response

    def form_invalid(self, form):
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'errors': form.errors})
        return super().form_invalid(form)


class OffsetMachineTypeUpdateView(AjaxFormMixin, LoginRequiredMixin, UpdateView):
    """عرض تحديث نوع ماكينة أوفست"""
    model = OffsetMachineType
    form_class = OffsetMachineTypeForm
    template_name = 'printing_pricing/settings/offset_machine_type/form_modal.html'
    success_url = reverse_lazy('printing_pricing:offset_machine_type_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('تحديث نوع ماكينة الأوفست')
        context['action_url'] = self.request.path
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': _('تم تحديث نوع ماكينة الأوفست بنجاح')})
        messages.success(self.request, _('تم تحديث نوع ماكينة الأوفست بنجاح'))
        return response

    def form_invalid(self, form):
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'errors': form.errors})
        return super().form_invalid(form)


class OffsetMachineTypeDeleteView(AjaxDeleteMixin, LoginRequiredMixin, DeleteView):
    """عرض حذف نوع ماكينة أوفست"""
    model = OffsetMachineType
    template_name = 'printing_pricing/settings/offset_machine_type/delete_modal.html'
    success_url = reverse_lazy('printing_pricing:offset_machine_type_list')


# ==================== عروض مقاسات ماكينات الأوفست ====================

class OffsetSheetSizeListView(LoginRequiredMixin, ListView):
    """عرض قائمة مقاسات ماكينات الأوفست"""
    model = OffsetSheetSize
    template_name = 'printing_pricing/settings/offset_sheet_size/list.html'
    context_object_name = 'sheet_sizes'
    paginate_by = 20

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('مقاسات ماكينات الأوفست')
        context['page_icon'] = 'fas fa-expand-arrows-alt'
        context['page_subtitle'] = _('إدارة مقاسات ماكينات الأوفست')
        context['header_buttons'] = [
            {
                'onclick': 'openCreateModal()',
                'icon': 'fa-plus',
                'text': _('إضافة جديد'),
                'class': 'btn-primary',
            },
        ]
        context['breadcrumb_items'] = [
            {
                'title': _('الرئيسية'),
                'url': '/',
                'icon': 'fas fa-home'
            },
            {
                'title': _('الإعدادات'),
                'url': reverse_lazy('printing_pricing:settings_home'),
                'icon': 'fas fa-cog'
            },
            {
                'title': _('مقاسات ماكينات الأوفست'),
                'url': '',
                'icon': 'fas fa-expand-arrows-alt',
                'active': True
            }
        ]
        return context

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search)
        return queryset.order_by('name')


class OffsetSheetSizeCreateView(AjaxFormMixin, LoginRequiredMixin, CreateView):
    """عرض إنشاء مقاس ماكينة أوفست جديد"""
    model = OffsetSheetSize
    form_class = OffsetSheetSizeForm
    template_name = 'printing_pricing/settings/offset_sheet_size/form_modal.html'
    success_url = reverse_lazy('printing_pricing:offset_sheet_size_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('إضافة مقاس ماكينة أوفست جديد')
        context['action_url'] = self.request.path
        return context

    def form_valid(self, form):
        messages.success(self.request, _('تم إنشاء مقاس ماكينة الأوفست بنجاح'))
        return super().form_valid(form)


class OffsetSheetSizeUpdateView(AjaxFormMixin, LoginRequiredMixin, UpdateView):
    """عرض تحديث مقاس ماكينة أوفست"""
    model = OffsetSheetSize
    form_class = OffsetSheetSizeForm
    template_name = 'printing_pricing/settings/offset_sheet_size/form_modal.html'
    success_url = reverse_lazy('printing_pricing:offset_sheet_size_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('تحديث مقاس ماكينة الأوفست')
        context['action_url'] = self.request.path
        return context

    def form_valid(self, form):
        messages.success(self.request, _('تم تحديث مقاس ماكينة الأوفست بنجاح'))
        return super().form_valid(form)


class OffsetSheetSizeDeleteView(AjaxDeleteMixin, LoginRequiredMixin, DeleteView):
    """عرض حذف مقاس ماكينة أوفست"""
    model = OffsetSheetSize
    template_name = 'printing_pricing/settings/offset_sheet_size/delete_modal.html'
    success_url = reverse_lazy('printing_pricing:offset_sheet_size_list')


# ==================== عروض أنواع ماكينات الديجيتال ====================

class DigitalMachineTypeListView(LoginRequiredMixin, ListView):
    """عرض قائمة أنواع ماكينات الديجيتال"""
    model = DigitalMachineType
    template_name = 'printing_pricing/settings/digital_machine_type/list.html'
    context_object_name = 'machine_types'
    paginate_by = 20

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('أنواع ماكينات الديجيتال')
        context['page_icon'] = 'fas fa-desktop'
        context['page_subtitle'] = _('إدارة أنواع ماكينات الديجيتال')
        context['header_buttons'] = [
            {
                'onclick': 'openCreateModal()',
                'icon': 'fa-plus',
                'text': _('إضافة جديد'),
                'class': 'btn-primary',
            },
        ]
        context['breadcrumb_items'] = [
            {
                'title': _('الرئيسية'),
                'url': '/',
                'icon': 'fas fa-home'
            },
            {
                'title': _('الإعدادات'),
                'url': reverse_lazy('printing_pricing:settings_home'),
                'icon': 'fas fa-cog'
            },
            {
                'title': _('أنواع ماكينات الديجيتال'),
                'url': '',
                'icon': 'fas fa-desktop',
                'active': True
            }
        ]
        return context

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(description__icontains=search)
            )
        return queryset.order_by('name')


class DigitalMachineTypeCreateView(AjaxFormMixin, LoginRequiredMixin, CreateView):
    """عرض إنشاء نوع ماكينة ديجيتال جديد"""
    model = DigitalMachineType
    form_class = DigitalMachineTypeForm
    template_name = 'printing_pricing/settings/digital_machine_type/form_modal.html'
    success_url = reverse_lazy('printing_pricing:digital_machine_type_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('إضافة نوع ماكينة ديجيتال جديد')
        context['action_url'] = self.request.path
        return context

    def form_valid(self, form):
        messages.success(self.request, _('تم إنشاء نوع ماكينة الديجيتال بنجاح'))
        return super().form_valid(form)


class DigitalMachineTypeUpdateView(AjaxFormMixin, LoginRequiredMixin, UpdateView):
    """عرض تحديث نوع ماكينة ديجيتال"""
    model = DigitalMachineType
    form_class = DigitalMachineTypeForm
    template_name = 'printing_pricing/settings/digital_machine_type/form_modal.html'
    success_url = reverse_lazy('printing_pricing:digital_machine_type_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('تحديث نوع ماكينة الديجيتال')
        context['action_url'] = self.request.path
        return context

    def form_valid(self, form):
        messages.success(self.request, _('تم تحديث نوع ماكينة الديجيتال بنجاح'))
        return super().form_valid(form)


class DigitalMachineTypeDeleteView(AjaxDeleteMixin, LoginRequiredMixin, DeleteView):
    """عرض حذف نوع ماكينة ديجيتال"""
    model = DigitalMachineType
    template_name = 'printing_pricing/settings/digital_machine_type/delete_modal.html'
    success_url = reverse_lazy('printing_pricing:digital_machine_type_list')


# ==================== عروض مقاسات ماكينات الديجيتال ====================

class DigitalSheetSizeListView(LoginRequiredMixin, ListView):
    """عرض قائمة مقاسات ماكينات الديجيتال"""
    model = DigitalSheetSize
    template_name = 'printing_pricing/settings/digital_sheet_size/list.html'
    context_object_name = 'sheet_sizes'
    paginate_by = 20

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('مقاسات ماكينات الديجيتال')
        context['page_icon'] = 'fas fa-tablet-alt'
        context['page_subtitle'] = _('إدارة مقاسات ماكينات الديجيتال')
        context['header_buttons'] = [
            {
                'onclick': 'openCreateModal()',
                'icon': 'fa-plus',
                'text': _('إضافة جديد'),
                'class': 'btn-primary',
            },
        ]
        context['breadcrumb_items'] = [
            {
                'title': _('الرئيسية'),
                'url': '/',
                'icon': 'fas fa-home'
            },
            {
                'title': _('الإعدادات'),
                'url': reverse_lazy('printing_pricing:settings_home'),
                'icon': 'fas fa-cog'
            },
            {
                'title': _('مقاسات ماكينات الديجيتال'),
                'url': '',
                'icon': 'fas fa-tablet-alt',
                'active': True
            }
        ]
        return context

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search)
        return queryset.order_by('name')


class DigitalSheetSizeCreateView(AjaxFormMixin, LoginRequiredMixin, CreateView):
    """عرض إنشاء مقاس ماكينة ديجيتال جديد"""
    model = DigitalSheetSize
    form_class = DigitalSheetSizeForm
    template_name = 'printing_pricing/settings/digital_sheet_size/form_modal.html'
    success_url = reverse_lazy('printing_pricing:digital_sheet_size_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('إضافة مقاس ماكينة ديجيتال جديد')
        context['action_url'] = self.request.path
        return context

    def form_valid(self, form):
        messages.success(self.request, _('تم إنشاء مقاس ماكينة الديجيتال بنجاح'))
        return super().form_valid(form)


class DigitalSheetSizeUpdateView(AjaxFormMixin, LoginRequiredMixin, UpdateView):
    """عرض تحديث مقاس ماكينة ديجيتال"""
    model = DigitalSheetSize
    form_class = DigitalSheetSizeForm
    template_name = 'printing_pricing/settings/digital_sheet_size/form_modal.html'
    success_url = reverse_lazy('printing_pricing:digital_sheet_size_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('تحديث مقاس ماكينة الديجيتال')
        context['action_url'] = self.request.path
        return context

    def form_valid(self, form):
        messages.success(self.request, _('تم تحديث مقاس ماكينة الديجيتال بنجاح'))
        return super().form_valid(form)


class DigitalSheetSizeDeleteView(AjaxDeleteMixin, LoginRequiredMixin, DeleteView):
    """عرض حذف مقاس ماكينة ديجيتال"""
    model = DigitalSheetSize
    template_name = 'printing_pricing/settings/digital_sheet_size/delete_modal.html'
    success_url = reverse_lazy('printing_pricing:digital_sheet_size_list')


# ==================== عروض مقاسات الزنكات ====================

class PlateSizeListView(LoginRequiredMixin, ListView):
    """عرض قائمة مقاسات الزنكات"""
    model = PlateSize
    template_name = 'printing_pricing/settings/plate_sizes/list.html'
    context_object_name = 'plate_sizes'
    paginate_by = 20

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search)
        return queryset.order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('مقاسات زنكات CTP')
        context['page_icon'] = 'fas fa-clone'
        context['page_subtitle'] = _('إدارة وتخصيص مقاسات زنكات CTP وماكينات الطباعة')
        context['header_buttons'] = [
            {
                'onclick': 'openCreateModal()',
                'icon': 'fa-plus',
                'text': _('إضافة مقاس زنك جديد'),
                'class': 'btn-primary',
            },
        ]
        context['breadcrumb_items'] = [
            {'title': _('الرئيسية'), 'url': reverse_lazy('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': _('إعدادات التسعير'), 'url': reverse_lazy('printing_pricing:settings_home'), 'icon': 'fas fa-cog'},
            {'title': _('مقاسات الزنكات'), 'active': True}
        ]
        return context


class PlateSizeCreateView(AjaxFormMixin, LoginRequiredMixin, CreateView):
    """عرض إنشاء مقاس زنك جديد"""
    model = PlateSize
    form_class = PlateSizeForm
    template_name = 'printing_pricing/settings/plate_sizes/form_modal.html'
    success_url = reverse_lazy('printing_pricing:plate_size_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('إضافة مقاس زنك جديد')
        context['action_url'] = self.request.path
        return context

    def form_valid(self, form):
        messages.success(self.request, _('تم إنشاء مقاس الزنك بنجاح'))
        return super().form_valid(form)


class PlateSizeUpdateView(AjaxFormMixin, LoginRequiredMixin, UpdateView):
    """عرض تحديث مقاس الزنك"""
    model = PlateSize
    form_class = PlateSizeForm
    template_name = 'printing_pricing/settings/plate_sizes/form_modal.html'
    success_url = reverse_lazy('printing_pricing:plate_size_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('تعديل مقاس الزنك')
        context['action_url'] = self.request.path
        return context

    def form_valid(self, form):
        messages.success(self.request, _('تم تحديث مقاس الزنك بنجاح'))
        return super().form_valid(form)


class PlateSizeDeleteView(AjaxDeleteMixin, LoginRequiredMixin, DeleteView):
    """عرض حذف مقاس الزنك"""
    model = PlateSize
    template_name = 'printing_pricing/settings/plate_sizes/delete_modal.html'
    context_object_name = 'plate_size'
    success_url = reverse_lazy('printing_pricing:plate_size_list')


# ==================== عروض أنواع المطبوعات ====================

class ProductTypeListView(LoginRequiredMixin, ListView):
    """عرض قائمة أنواع المطبوعات"""
    model = ProductType
    template_name = 'printing_pricing/settings/product_types/list.html'
    context_object_name = 'product_types'
    paginate_by = 50

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('أنواع المطبوعات')
        context['page_icon'] = 'fas fa-layer-group'
        context['page_subtitle'] = _('إدارة وتخصيص وترتيب أنواع المطبوعات ومسارات تشغيلها')
        context['header_buttons'] = [
            {
                'onclick': 'openCreateModal()',
                'icon': 'fa-plus',
                'text': _('إضافة نوع مطبوع جديد'),
                'class': 'btn-primary fw-bold',
            },
        ]
        context['breadcrumb_items'] = [
            {
                'title': _('الرئيسية'),
                'url': reverse_lazy('core:dashboard'),
                'icon': 'fas fa-home'
            },
            {
                'title': _('تسعير المطبوعات'),
                'url': reverse_lazy('printing_pricing:order_list'),
                'icon': 'fas fa-calculator'
            },
            {
                'title': _('الإعدادات'),
                'url': reverse_lazy('printing_pricing:settings_home'),
                'icon': 'fas fa-cog'
            },
            {
                'title': _('أنواع المطبوعات'),
                'url': '',
                'icon': 'fas fa-layer-group',
                'active': True
            }
        ]
        return context

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(description__icontains=search)
            )
        return queryset.order_by('sort_order', 'id')


class ProductTypeCreateView(AjaxFormMixin, LoginRequiredMixin, CreateView):
    """عرض إنشاء نوع مطبوع جديد"""
    model = ProductType
    form_class = ProductTypeForm
    template_name = 'printing_pricing/settings/product_types/form_modal.html'
    success_url = reverse_lazy('printing_pricing:product_type_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('إضافة نوع مطبوع جديد')
        context['action_url'] = self.request.path
        return context

    def form_valid(self, form):
        # في حالة عدم تحديد ترتيب، وضعه في نهاية القائمة
        if not form.cleaned_data.get('sort_order'):
            max_order = ProductType.objects.aggregate(models.Max('sort_order'))['sort_order__max'] or 0
            form.instance.sort_order = max_order + 10
        messages.success(self.request, _('تم إنشاء نوع المطبوع بنجاح'))
        return super().form_valid(form)


class ProductTypeUpdateView(AjaxFormMixin, LoginRequiredMixin, UpdateView):
    """عرض تحديث نوع المطبوع"""
    model = ProductType
    form_class = ProductTypeForm
    template_name = 'printing_pricing/settings/product_types/form_modal.html'
    success_url = reverse_lazy('printing_pricing:product_type_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('تحديث نوع المطبوع')
        context['action_url'] = self.request.path
        return context

    def form_valid(self, form):
        messages.success(self.request, _('تم تحديث نوع المطبوع بنجاح'))
        return super().form_valid(form)


class ProductTypeDeleteView(AjaxDeleteMixin, LoginRequiredMixin, DeleteView):
    """عرض حذف نوع المطبوع مع الحماية ضد ProtectedError"""
    model = ProductType
    template_name = 'printing_pricing/settings/product_types/delete_modal.html'
    success_url = reverse_lazy('printing_pricing:product_type_list')

    def post(self, request, *args, **kwargs):
        try:
            return super().post(request, *args, **kwargs)
        except models.ProtectedError:
            err_msg = _('لا يمكن حذف هذا الصنف لوجود طلبات تسعير سابقة مرتبطة به. يرجى إيقاف تفعيله بدلاً من الحذف.')
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.is_ajax():
                return JsonResponse({'success': False, 'message': err_msg}, status=400)
            messages.error(request, err_msg)
            return redirect(self.success_url)


class ProductTypeReorderView(LoginRequiredMixin, View):
    """إعادة ترتيب أنواع المطبوعات بالـ AJAX"""
    def post(self, request, *args, **kwargs):
        import json
        try:
            body = json.loads(request.body.decode('utf-8'))
            item_id = body.get('item_id')
            direction = body.get('direction') # 'up' or 'down'

            items = list(ProductType.objects.all().order_by('sort_order', 'id'))
            target_idx = next((i for i, item in enumerate(items) if item.pk == int(item_id)), None)

            if target_idx is not None:
                if direction == 'up' and target_idx > 0:
                    items[target_idx], items[target_idx - 1] = items[target_idx - 1], items[target_idx]
                elif direction == 'down' and target_idx < len(items) - 1:
                    items[target_idx], items[target_idx + 1] = items[target_idx + 1], items[target_idx]

                # إعادة ترقيم متسلسل متوازن بفروق 10
                for idx, pt in enumerate(items):
                    pt.sort_order = (idx + 1) * 10
                    pt.save(update_fields=['sort_order'])

                return JsonResponse({'success': True, 'message': _('تم تحديث الترتيب بنجاح')})
            return JsonResponse({'success': False, 'message': _('العنصر غير موجود')}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=400)


class ProductTypeToggleActiveView(LoginRequiredMixin, View):
    """تفعيل أو إيقاف نوع المطبوع سريعاً بالـ AJAX"""
    def post(self, request, pk, *args, **kwargs):
        try:
            pt = get_object_or_404(ProductType, pk=pk)
            pt.is_active = not pt.is_active
            pt.save(update_fields=['is_active'])
            status_text = _('تم التفعيل') if pt.is_active else _('تم الإيقاف')
            return JsonResponse({'success': True, 'is_active': pt.is_active, 'message': f"{pt.name}: {status_text}"})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=400)



# ==================== عروض مقاسات المطبوعات ====================

class ProductSizeListView(LoginRequiredMixin, ListView):
    """عرض قائمة مقاسات المطبوعات"""
    model = ProductSize
    template_name = 'printing_pricing/settings/product_sizes/list.html'
    context_object_name = 'product_sizes'
    paginate_by = 25

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('مقاسات المطبوعات')
        context['page_icon'] = 'fas fa-ruler-combined'
        context['page_subtitle'] = _('إدارة وتنسيق المقاسات القياسية المعتمدة في شاشة التسعير')
        context['header_buttons'] = [
            {
                'onclick': 'openCreateModal()',
                'icon': 'fa-plus',
                'text': _('إضافة مقاس جديد'),
                'class': 'btn-primary',
            },
        ]
        context['breadcrumb_items'] = [
            {
                'title': _('الرئيسية'),
                'url': reverse_lazy('core:dashboard'),
                'icon': 'fas fa-home'
            },
            {
                'title': _('إعدادات التسعير والطباعة'),
                'url': reverse_lazy('printing_pricing:settings_home'),
                'icon': 'fas fa-cog'
            },
            {
                'title': _('مقاسات المطبوعات'),
                'url': '',
                'icon': 'fas fa-ruler-combined',
                'active': True
            }
        ]
        return context

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search)
        return queryset.order_by('sort_order', 'id')


class ProductSizeCreateView(AjaxFormMixin, LoginRequiredMixin, CreateView):
    """عرض إنشاء مقاس مطبوع جديد"""
    model = ProductSize
    form_class = ProductSizeForm
    template_name = 'printing_pricing/settings/product_sizes/form_modal.html'
    success_url = reverse_lazy('printing_pricing:product_size_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('إضافة مقاس مطبوع جديد')
        context['action_url'] = self.request.path
        return context

    def form_valid(self, form):
        messages.success(self.request, _('تم إنشاء مقاس المطبوع بنجاح'))
        return super().form_valid(form)


class ProductSizeUpdateView(AjaxFormMixin, LoginRequiredMixin, UpdateView):
    """عرض تحديث مقاس المطبوع"""
    model = ProductSize
    form_class = ProductSizeForm
    template_name = 'printing_pricing/settings/product_sizes/form_modal.html'
    success_url = reverse_lazy('printing_pricing:product_size_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('تحديث مقاس المطبوع')
        context['action_url'] = self.request.path
        return context

    def form_valid(self, form):
        messages.success(self.request, _('تم تحديث مقاس المطبوع بنجاح'))
        return super().form_valid(form)


class ProductSizeDeleteView(AjaxDeleteMixin, LoginRequiredMixin, DeleteView):
    """عرض حذف مقاس المطبوع مع الحماية ضد ProtectedError"""
    model = ProductSize
    template_name = 'printing_pricing/settings/product_sizes/delete_modal.html'
    success_url = reverse_lazy('printing_pricing:product_size_list')

    def delete(self, request, *args, **kwargs):
        try:
            return super().delete(request, *args, **kwargs)
        except models.ProtectedError:
            err_msg = _('لا يمكن حذف هذا المقاس لوجود طلبات تسعير مرتبطة به. يرجى إيقاف تفعيله بدلاً من الحذف.')
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': str(err_msg)}, status=400)
            messages.error(request, err_msg)
            return redirect(self.success_url)

    def post(self, request, *args, **kwargs):
        return self.delete(request, *args, **kwargs)


class ProductSizeReorderView(LoginRequiredMixin, View):
    """إعادة ترتيب مقاسات المطبوعات بالـ AJAX"""
    def post(self, request, *args, **kwargs):
        import json
        try:
            body = json.loads(request.body.decode('utf-8'))
            item_id = body.get('item_id')
            direction = body.get('direction')

            items = list(ProductSize.objects.all().order_by('sort_order', 'id'))
            target_idx = next((i for i, item in enumerate(items) if item.pk == int(item_id)), None)

            if target_idx is not None:
                if direction == 'up' and target_idx > 0:
                    items[target_idx], items[target_idx - 1] = items[target_idx - 1], items[target_idx]
                elif direction == 'down' and target_idx < len(items) - 1:
                    items[target_idx], items[target_idx + 1] = items[target_idx + 1], items[target_idx]

                # إعادة ترقيم متسلسل متوازن بفروق 10
                for idx, ps in enumerate(items):
                    ps.sort_order = (idx + 1) * 10
                    ps.save(update_fields=['sort_order'])

                return JsonResponse({'success': True, 'message': _('تم تحديث الترتيب بنجاح')})
            return JsonResponse({'success': False, 'message': _('العنصر غير موجود')}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=400)


class ProductSizeToggleActiveView(LoginRequiredMixin, View):
    """تفعيل أو إيقاف مقاس المطبوع سريعاً بالـ AJAX"""
    def post(self, request, pk, *args, **kwargs):
        try:
            ps = get_object_or_404(ProductSize, pk=pk)
            ps.is_active = not ps.is_active
            ps.save(update_fields=['is_active'])
            status_text = _('تم التفعيل') if ps.is_active else _('تم الإيقاف')
            return JsonResponse({'success': True, 'is_active': ps.is_active, 'message': f"{ps.name}: {status_text}"})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=400)

