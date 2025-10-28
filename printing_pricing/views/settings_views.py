"""
Views for managing settings in the new system
"""

import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q


# ==================== Mixins مشتركة ====================

class AjaxDeleteMixin:
    """Mixin لإضافة دعم AJAX للـ DeleteViews"""
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # إضافة الكائن المراد حذفه للـ context
        model_name = self.model._meta.model_name
        context[model_name] = self.object
        context['action_url'] = self.request.path
        return context

    def delete(self, request, *args, **kwargs):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            # للطلبات AJAX، حذف الكائن وإرجاع JSON
            self.object = self.get_object()
            self.object.delete()
            
            # إنشاء رسالة النجاح بناءً على اسم النموذج
            model_verbose_name = self.model._meta.verbose_name
            success_message = _('تم حذف {} بنجاح').format(model_verbose_name)
            return JsonResponse(
                {'success': True, 'message': success_message},
                content_type='application/json'
            )
        
        # للطلبات العادية، استخدام السلوك الافتراضي
        response = super().delete(request, *args, **kwargs)
        model_verbose_name = self.model._meta.verbose_name
        success_message = _('تم حذف {} بنجاح').format(model_verbose_name)
        messages.success(request, success_message)
        return response

from ..models import (
    PaperType, PaperSize, PaperWeight, PaperOrigin,
    PrintDirection, PrintSide, CoatingType, FinishingType, PackagingType,
    PieceSize, PlateSize, ProductType, ProductSize, VATSetting,
    OffsetMachineType, OffsetSheetSize, DigitalMachineType, DigitalSheetSize, SystemSetting
)
from ..forms.settings_forms import (
    PaperTypeForm, PaperSizeForm, PaperWeightForm, PaperOriginForm,
    PrintDirectionForm, PrintSideForm, CoatingTypeForm, PieceSizeForm,
    ProductTypeForm, ProductSizeForm, OffsetMachineTypeForm, DigitalMachineTypeForm,
    OffsetSheetSizeForm, DigitalSheetSizeForm
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


class PaperTypeCreateView(LoginRequiredMixin, CreateView):
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


class PaperTypeUpdateView(LoginRequiredMixin, UpdateView):
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


class PaperSizeCreateView(LoginRequiredMixin, CreateView):
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


class PaperSizeUpdateView(LoginRequiredMixin, UpdateView):
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


class PaperWeightCreateView(LoginRequiredMixin, CreateView):
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


class PaperWeightUpdateView(LoginRequiredMixin, UpdateView):
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


class PaperOriginCreateView(LoginRequiredMixin, CreateView):
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


class PaperOriginUpdateView(LoginRequiredMixin, UpdateView):
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


# ==================== عروض اتجاهات الطباعة ====================

class PrintDirectionListView(LoginRequiredMixin, ListView):
    """عرض قائمة اتجاهات الطباعة"""
    model = PrintDirection
    template_name = 'printing_pricing/settings/print_directions/list.html'
    context_object_name = 'print_directions'
    paginate_by = 20

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('اتجاهات الطباعة')
        context['page_icon'] = 'fas fa-arrows-alt'
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
                'title': _('اتجاهات الطباعة'),
                'url': '',
                'icon': 'fas fa-arrows-alt',
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


class PrintDirectionCreateView(LoginRequiredMixin, CreateView):
    """عرض إنشاء اتجاه طباعة جديد"""
    model = PrintDirection
    form_class = PrintDirectionForm
    template_name = 'printing_pricing/settings/print_directions/form_modal.html'
    success_url = reverse_lazy('printing_pricing:print_direction_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('إضافة اتجاه طباعة جديد')
        context['action_url'] = self.request.path
        return context

    def form_valid(self, form):
        messages.success(self.request, _('تم إنشاء اتجاه الطباعة بنجاح'))
        return super().form_valid(form)


class PrintDirectionUpdateView(LoginRequiredMixin, UpdateView):
    """عرض تحديث اتجاه الطباعة"""
    model = PrintDirection
    form_class = PrintDirectionForm
    template_name = 'printing_pricing/settings/print_directions/form_modal.html'
    success_url = reverse_lazy('printing_pricing:print_direction_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('تحديث اتجاه الطباعة')
        context['action_url'] = self.request.path
        return context

    def form_valid(self, form):
        messages.success(self.request, _('تم تحديث اتجاه الطباعة بنجاح'))
        return super().form_valid(form)


class PrintDirectionDeleteView(AjaxDeleteMixin, LoginRequiredMixin, DeleteView):
    """عرض حذف اتجاه الطباعة"""
    model = PrintDirection
    template_name = 'printing_pricing/settings/print_directions/delete_modal.html'
    success_url = reverse_lazy('printing_pricing:print_direction_list')


# ==================== عروض جوانب الطباعة ====================

class PrintSideListView(LoginRequiredMixin, ListView):
    """عرض قائمة جوانب الطباعة"""
    model = PrintSide
    template_name = 'printing_pricing/settings/print_sides/list.html'
    context_object_name = 'print_sides'
    paginate_by = 20


class PrintSideCreateView(LoginRequiredMixin, CreateView):
    """عرض إنشاء جانب طباعة جديد"""
    model = PrintSide
    form_class = PrintSideForm
    template_name = 'printing_pricing/settings/print_sides/form.html'
    success_url = reverse_lazy('printing_pricing:print_side_list')

    def form_valid(self, form):
        messages.success(self.request, _('تم إنشاء جانب الطباعة بنجاح'))
        return super().form_valid(form)


class PrintSideUpdateView(LoginRequiredMixin, UpdateView):
    """عرض تحديث جانب الطباعة"""
    model = PrintSide
    form_class = PrintSideForm
    template_name = 'printing_pricing/settings/print_sides/form.html'
    success_url = reverse_lazy('printing_pricing:print_side_list')

    def form_valid(self, form):
        messages.success(self.request, _('تم تحديث جانب الطباعة بنجاح'))
        return super().form_valid(form)


class PrintSideDeleteView(AjaxDeleteMixin, LoginRequiredMixin, DeleteView):
    """عرض حذف جانب الطباعة"""
    model = PrintSide
    template_name = 'printing_pricing/settings/print_sides/delete_modal.html'
    success_url = reverse_lazy('printing_pricing:print_side_list')


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


class CoatingTypeCreateView(LoginRequiredMixin, CreateView):
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


class CoatingTypeUpdateView(LoginRequiredMixin, UpdateView):
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


class FinishingTypeCreateView(LoginRequiredMixin, CreateView):
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


class FinishingTypeUpdateView(LoginRequiredMixin, UpdateView):
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


class PackagingTypeCreateView(LoginRequiredMixin, CreateView):
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


class PackagingTypeUpdateView(LoginRequiredMixin, UpdateView):
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


class PieceSizeCreateView(LoginRequiredMixin, CreateView):
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


class PieceSizeUpdateView(LoginRequiredMixin, UpdateView):
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
    context = {
        'title': _('إعدادات النظام'),
        'paper_types_count': PaperType.objects.filter(is_active=True).count(),
        'paper_sizes_count': PaperSize.objects.filter(is_active=True).count(),
        'paper_weights_count': PaperWeight.objects.filter(is_active=True).count(),
        'paper_origins_count': PaperOrigin.objects.filter(is_active=True).count(),
        'print_directions_count': PrintDirection.objects.filter(is_active=True).count(),
        'print_sides_count': PrintSide.objects.filter(is_active=True).count(),
        'coating_types_count': CoatingType.objects.filter(is_active=True).count(),
        'finishing_types_count': FinishingType.objects.filter(is_active=True).count(),
        'packaging_types_count': PackagingType.objects.filter(is_active=True).count(),
        'piece_sizes_count': PieceSize.objects.filter(is_active=True).count(),
        'plate_sizes_count': PlateSize.objects.filter(is_active=True).count(),
        'product_types_count': ProductType.objects.filter(is_active=True).count(),
        'product_sizes_count': ProductSize.objects.filter(is_active=True).count(),
        'vat_settings_count': VATSetting.objects.filter(is_enabled=True).count(),
        'offset_machine_types_count': OffsetMachineType.objects.filter(is_active=True).count(),
        'offset_sheet_sizes_count': OffsetSheetSize.objects.filter(is_active=True).count(),
        'digital_machine_types_count': DigitalMachineType.objects.filter(is_active=True).count(),
        'digital_sheet_sizes_count': DigitalSheetSize.objects.filter(is_active=True).count(),
        'system_settings_count': SystemSetting.objects.filter(is_active=True).count(),
    }
    return render(request, 'printing_pricing/settings/settings_home.html', context)


# ==================== عروض إعدادات ضريبة القيمة المضافة ====================

class VATSettingListView(LoginRequiredMixin, ListView):
    """عرض قائمة إعدادات ضريبة القيمة المضافة"""
    model = VATSetting
    template_name = 'printing_pricing/settings/vat_settings/list.html'
    context_object_name = 'vat_settings'
    paginate_by = 20

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(description__icontains=search) | Q(percentage__icontains=search)
            )
        return queryset.order_by('-created_at')


class VATSettingCreateView(LoginRequiredMixin, CreateView):
    """عرض إنشاء إعداد ضريبة قيمة مضافة جديد"""
    model = VATSetting
    template_name = 'printing_pricing/settings/vat_settings/form.html'
    fields = ['percentage', 'description', 'is_enabled']
    success_url = reverse_lazy('printing_pricing:vat_setting_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, _('تم إنشاء إعداد ضريبة القيمة المضافة بنجاح'))
        return super().form_valid(form)


class VATSettingUpdateView(LoginRequiredMixin, UpdateView):
    """عرض تحديث إعداد ضريبة القيمة المضافة"""
    model = VATSetting
    template_name = 'printing_pricing/settings/vat_settings/form.html'
    fields = ['percentage', 'description', 'is_enabled']
    success_url = reverse_lazy('printing_pricing:vat_setting_list')

    def form_valid(self, form):
        messages.success(self.request, _('تم تحديث إعداد ضريبة القيمة المضافة بنجاح'))
        return super().form_valid(form)


class VATSettingDeleteView(AjaxDeleteMixin, LoginRequiredMixin, DeleteView):
    """عرض حذف إعداد ضريبة القيمة المضافة"""
    model = VATSetting
    template_name = 'printing_pricing/settings/vat_settings/confirm_delete.html'
    success_url = reverse_lazy('printing_pricing:vat_setting_list')


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


class OffsetMachineTypeCreateView(LoginRequiredMixin, CreateView):
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


class OffsetMachineTypeUpdateView(LoginRequiredMixin, UpdateView):
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


class OffsetSheetSizeCreateView(LoginRequiredMixin, CreateView):
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


class OffsetSheetSizeUpdateView(LoginRequiredMixin, UpdateView):
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


class DigitalMachineTypeCreateView(LoginRequiredMixin, CreateView):
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


class DigitalMachineTypeUpdateView(LoginRequiredMixin, UpdateView):
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


class DigitalSheetSizeCreateView(LoginRequiredMixin, CreateView):
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


class DigitalSheetSizeUpdateView(LoginRequiredMixin, UpdateView):
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


# ==================== عروض إعدادات النظام ====================

class SystemSettingListView(LoginRequiredMixin, ListView):
    """عرض قائمة إعدادات النظام"""
    model = SystemSetting
    template_name = 'printing_pricing/settings/system_settings/list.html'
    context_object_name = 'settings'
    paginate_by = 20

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.GET.get('search')
        category = self.request.GET.get('category')
        
        if search:
            queryset = queryset.filter(
                Q(key__icontains=search) | Q(description__icontains=search) | Q(value__icontains=search)
            )
        
        if category:
            queryset = queryset.filter(category=category)
            
        return queryset.order_by('category', 'key')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # إضافة قائمة الفئات للفلترة
        context['categories'] = SystemSetting.objects.values_list('category', flat=True).distinct()
        context['selected_category'] = self.request.GET.get('category', '')
        return context


class SystemSettingCreateView(LoginRequiredMixin, CreateView):
    """عرض إنشاء إعداد نظام جديد"""
    model = SystemSetting
    template_name = 'printing_pricing/settings/system_settings/form.html'
    fields = ['key', 'value', 'description', 'category', 'is_active']
    success_url = reverse_lazy('printing_pricing:system_setting_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, _('تم إنشاء إعداد النظام بنجاح'))
        return super().form_valid(form)


class SystemSettingUpdateView(LoginRequiredMixin, UpdateView):
    """عرض تحديث إعداد نظام"""
    model = SystemSetting
    template_name = 'printing_pricing/settings/system_settings/form.html'
    fields = ['key', 'value', 'description', 'category', 'is_active']
    success_url = reverse_lazy('printing_pricing:system_setting_list')

    def form_valid(self, form):
        messages.success(self.request, _('تم تحديث إعداد النظام بنجاح'))
        return super().form_valid(form)


class SystemSettingDeleteView(AjaxDeleteMixin, LoginRequiredMixin, DeleteView):
    """عرض حذف إعداد نظام"""
    model = SystemSetting
    template_name = 'printing_pricing/settings/system_settings/confirm_delete.html'
    success_url = reverse_lazy('printing_pricing:system_setting_list')


# ==================== عروض مقاسات الزنكات ====================

class PlateSizeListView(LoginRequiredMixin, ListView):
    """عرض قائمة مقاسات الزنكات"""
    model = PlateSize
    template_name = 'printing_pricing/settings/plate_size/list.html'
    context_object_name = 'plate_sizes'
    paginate_by = 20

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search)
        return queryset.order_by('name')


class PlateSizeCreateView(LoginRequiredMixin, CreateView):
    """عرض إنشاء مقاس زنك جديد"""
    model = PlateSize
    template_name = 'printing_pricing/settings/plate_sizes/form.html'
    fields = ['name', 'width', 'height', 'is_active']
    success_url = reverse_lazy('printing_pricing:plate_size_list')

    def form_valid(self, form):
        messages.success(self.request, _('تم إنشاء مقاس الزنك بنجاح'))
        return super().form_valid(form)


class PlateSizeUpdateView(LoginRequiredMixin, UpdateView):
    """عرض تحديث مقاس الزنك"""
    model = PlateSize
    template_name = 'printing_pricing/settings/plate_sizes/form.html'
    fields = ['name', 'width', 'height', 'is_active']
    success_url = reverse_lazy('printing_pricing:plate_size_list')

    def form_valid(self, form):
        messages.success(self.request, _('تم تحديث مقاس الزنك بنجاح'))
        return super().form_valid(form)


class PlateSizeDeleteView(AjaxDeleteMixin, LoginRequiredMixin, DeleteView):
    """عرض حذف مقاس الزنك"""
    model = PlateSize
    template_name = 'printing_pricing/settings/plate_size/confirm_delete.html'
    success_url = reverse_lazy('printing_pricing:plate_size_list')


# ==================== عروض أنواع المنتجات ====================

class ProductTypeListView(LoginRequiredMixin, ListView):
    """عرض قائمة أنواع المنتجات"""
    model = ProductType
    template_name = 'printing_pricing/settings/product_types/list.html'
    context_object_name = 'product_types'
    paginate_by = 20

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('أنواع المنتجات')
        context['page_icon'] = 'fas fa-box'
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
                'title': _('أنواع المنتجات'),
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


class ProductTypeCreateView(LoginRequiredMixin, CreateView):
    """عرض إنشاء نوع منتج جديد"""
    model = ProductType
    form_class = ProductTypeForm
    template_name = 'printing_pricing/settings/product_types/form_modal.html'
    success_url = reverse_lazy('printing_pricing:product_type_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('إضافة نوع منتج جديد')
        context['action_url'] = self.request.path
        return context

    def form_valid(self, form):
        messages.success(self.request, _('تم إنشاء نوع المنتج بنجاح'))
        return super().form_valid(form)


class ProductTypeUpdateView(LoginRequiredMixin, UpdateView):
    """عرض تحديث نوع المنتج"""
    model = ProductType
    form_class = ProductTypeForm
    template_name = 'printing_pricing/settings/product_types/form_modal.html'
    success_url = reverse_lazy('printing_pricing:product_type_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('تحديث نوع المنتج')
        context['action_url'] = self.request.path
        return context

    def form_valid(self, form):
        messages.success(self.request, _('تم تحديث نوع المنتج بنجاح'))
        return super().form_valid(form)


class ProductTypeDeleteView(AjaxDeleteMixin, LoginRequiredMixin, DeleteView):
    """عرض حذف نوع المنتج"""
    model = ProductType
    template_name = 'printing_pricing/settings/product_types/delete_modal.html'
    success_url = reverse_lazy('printing_pricing:product_type_list')


# ==================== عروض مقاسات المنتجات ====================

class ProductSizeListView(LoginRequiredMixin, ListView):
    """عرض قائمة مقاسات المنتجات"""
    model = ProductSize
    template_name = 'printing_pricing/settings/product_sizes/list.html'
    context_object_name = 'product_sizes'
    paginate_by = 20

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('مقاسات المنتجات')
        context['page_icon'] = 'fas fa-ruler'
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
                'title': _('مقاسات المنتجات'),
                'url': '',
                'icon': 'fas fa-ruler',
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


class ProductSizeCreateView(LoginRequiredMixin, CreateView):
    """عرض إنشاء مقاس منتج جديد"""
    model = ProductSize
    form_class = ProductSizeForm
    template_name = 'printing_pricing/settings/product_sizes/form_modal.html'
    success_url = reverse_lazy('printing_pricing:product_size_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('إضافة مقاس منتج جديد')
        context['action_url'] = self.request.path
        return context

    def form_valid(self, form):
        messages.success(self.request, _('تم إنشاء مقاس المنتج بنجاح'))
        return super().form_valid(form)


class ProductSizeUpdateView(LoginRequiredMixin, UpdateView):
    """عرض تحديث مقاس المنتج"""
    model = ProductSize
    form_class = ProductSizeForm
    template_name = 'printing_pricing/settings/product_sizes/form_modal.html'
    success_url = reverse_lazy('printing_pricing:product_size_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('تحديث مقاس المنتج')
        context['action_url'] = self.request.path
        return context

    def form_valid(self, form):
        messages.success(self.request, _('تم تحديث مقاس المنتج بنجاح'))
        return super().form_valid(form)


class ProductSizeDeleteView(AjaxDeleteMixin, LoginRequiredMixin, DeleteView):
    """عرض حذف مقاس المنتج"""
    model = ProductSize
    template_name = 'printing_pricing/settings/product_sizes/delete_modal.html'
    success_url = reverse_lazy('printing_pricing:product_size_list')
