# -*- coding: utf-8 -*-
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import View
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib import messages
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.core.paginator import Paginator

from cheques.models import Checkbook, CheckbookLeaf, CheckbookLeafStatus
from cheques.forms.checkbook_forms import CheckbookForm, RuinedLeafReplacementForm
from cheques.services.checkbook_service import CheckbookService


class CheckbookListView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """
    قائمة دفاتر الشيكات البنكية ومتابعة الأوراق المتاحة والمصروفة
    """
    permission_required = 'cheques.manage_checkbooks'
    template_name = 'cheques/checkbook_list.html'

    def get(self, request, *args, **kwargs):
        checkbooks = Checkbook.objects.select_related('bank_account', 'created_by').prefetch_related('leaves')

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('أوراق الدفع'), 'url': reverse('cheques:payable_list'), 'icon': 'fa-money-bill-wave'},
            {'title': _('دفاتر الشيكات البنكية'), 'active': True}
        ]

        header_buttons = [
            {
                'url': reverse('cheques:checkbook_create'),
                'icon': 'fa-plus',
                'text': _('تسجيل دفتر شيكات جديد'),
                'class': 'btn-primary'
            }
        ]

        context = {
            'page_title': _('دفاتر الشيكات البنكية'),
            'page_subtitle': _('حصر دفاتر الشيكات المستلمة من البنوك وأرصدة الأوراق التسلسلية المتبقية'),
            'page_icon': 'fa-book',
            'breadcrumb_items': breadcrumb_items,
            'header_buttons': header_buttons,
            'checkbooks': checkbooks,
        }
        return render(request, self.template_name, context)


class CheckbookCreateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """
    تسجيل دفتر شيكات جديد وتوليد أوراقه تسلسلياً تلقائياً
    """
    permission_required = 'cheques.manage_checkbooks'
    template_name = 'cheques/checkbook_form.html'

    def get(self, request, *args, **kwargs):
        form = CheckbookForm(user=request.user)
        return self._render(request, form)

    def post(self, request, *args, **kwargs):
        form = CheckbookForm(request.POST, user=request.user)
        if form.is_valid():
            checkbook = form.save()
            messages.success(request, _(f"تم تسجيل دفتر الشيكات {checkbook.name} وتوليد {checkbook.leaf_count} ورقة شيك بنجاح."))
            return redirect('cheques:checkbook_detail', pk=checkbook.pk)
        return self._render(request, form)

    def _render(self, request, form):
        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('أوراق الدفع'), 'url': reverse('cheques:payable_list'), 'icon': 'fa-money-bill-wave'},
            {'title': _('دفاتر الشيكات'), 'url': reverse('cheques:checkbook_list'), 'icon': 'fa-book'},
            {'title': _('تسجيل دفتر جديد'), 'active': True}
        ]
        context = {
            'page_title': _('تسجيل دفتر شيكات جديد'),
            'page_subtitle': _('إدخال بيانات الدفتر البنكي المستلم وتحديد نطاق الأرقام التسلسلية'),
            'page_icon': 'fa-plus-circle',
            'breadcrumb_items': breadcrumb_items,
            'form': form,
        }
        return render(request, self.template_name, context)


class CheckbookDetailView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """
    استعراض تفاصيل الدفتر وكامل أوراقه التسلسلية مع حالاتها
    """
    permission_required = 'cheques.manage_checkbooks'
    template_name = 'cheques/checkbook_detail.html'

    def get(self, request, pk, *args, **kwargs):
        checkbook = get_object_or_404(
            Checkbook.objects.select_related('bank_account', 'created_by'),
            pk=pk
        )
        leaves = checkbook.leaves.select_related('cheque').order_by('id')

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('أوراق الدفع'), 'url': reverse('cheques:payable_list'), 'icon': 'fa-money-bill-wave'},
            {'title': _('دفاتر الشيكات'), 'url': reverse('cheques:checkbook_list'), 'icon': 'fa-book'},
            {'title': checkbook.name, 'active': True}
        ]

        # إحصائيات الدفتر
        available_count = leaves.filter(status=CheckbookLeafStatus.AVAILABLE).count()
        issued_count = leaves.filter(status=CheckbookLeafStatus.ISSUED).count()
        voided_count = leaves.filter(status=CheckbookLeafStatus.VOIDED).count()

        context = {
            'page_title': f"{_('دفتر شيكات')}: {checkbook.name}",
            'page_subtitle': f"{_('الحساب البنكي')}: {checkbook.bank_account.name} - {_('النطاق')}: {checkbook.serial_from} ⬅️ {checkbook.serial_to}",
            'page_icon': 'fa-book-open',
            'breadcrumb_items': breadcrumb_items,
            'checkbook': checkbook,
            'leaves': leaves,
            'available_count': available_count,
            'issued_count': issued_count,
            'voided_count': voided_count,
        }
        return render(request, self.template_name, context)


class CheckbookRuinedLeafView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """
    إثبات استبدال ورقة شيك تالفة بورقة جديدة من الدفتر
    """
    permission_required = 'cheques.manage_checkbooks'
    template_name = 'cheques/checkbook_ruined_leaf_form.html'

    def get(self, request, pk, *args, **kwargs):
        leaf = get_object_or_404(CheckbookLeaf.objects.select_related('checkbook', 'cheque'), pk=pk)
        form = RuinedLeafReplacementForm(initial={'ruined_leaf': leaf})
        return self._render(request, leaf, form)

    def post(self, request, pk, *args, **kwargs):
        leaf = get_object_or_404(CheckbookLeaf.objects.select_related('checkbook', 'cheque'), pk=pk)
        form = RuinedLeafReplacementForm(request.POST, request.FILES)
        if form.is_valid():
            replacement_leaf = form.cleaned_data['replacement_leaf']
            voided_reason = form.cleaned_data['voided_reason']
            voided_image = form.cleaned_data.get('voided_image')

            try:
                new_leaf = CheckbookService.replace_ruined_leaf(
                    ruined_leaf=leaf,
                    replacement_leaf=replacement_leaf,
                    voided_reason=voided_reason,
                    voided_image=voided_image,
                    user=request.user
                )
                messages.success(request, _(f"تم استبدال الورقة التالفة {leaf.serial_number} بالورقة الجديدة {new_leaf.serial_number} بنجاح."))
                if leaf.cheque:
                    return redirect('cheques:payable_detail', pk=leaf.cheque.pk)
                return redirect('cheques:checkbook_detail', pk=leaf.checkbook.pk)
            except Exception as e:
                messages.error(request, str(e))

        return self._render(request, leaf, form)

    def _render(self, request, leaf, form):
        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('أوراق الدفع'), 'url': reverse('cheques:payable_list'), 'icon': 'fa-money-bill-wave'},
            {'title': _('دفاتر الشيكات'), 'url': reverse('cheques:checkbook_list'), 'icon': 'fa-book'},
            {'title': _('استبدال ورقة تالفة'), 'active': True}
        ]
        context = {
            'page_title': f"{_('استبدال الورقة التالفة رقم')} {leaf.serial_number}",
            'page_subtitle': _('إثبات إتلاف الورقة وتخصيص ورقة بديلة لنفس الشيك مع التوثيق بالصورة والسبب'),
            'page_icon': 'fa-file-excel',
            'breadcrumb_items': breadcrumb_items,
            'leaf': leaf,
            'form': form,
        }
        return render(request, self.template_name, context)
