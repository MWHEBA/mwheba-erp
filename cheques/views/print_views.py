# -*- coding: utf-8 -*-
from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import View
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib import messages
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from cheques.models import Cheque, BankChequeLayout
from cheques.forms.layout_forms import BankChequeLayoutForm
from utils.arabic_numbers import amount_to_arabic_words


class ChequePrintView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """
    طباعة الشيك البنكي أو إشعار الاستلام بمعايرة الأبعاد الدقيقة والتفقيط بالعربية
    """
    permission_required = 'cheques.print_cheque'
    template_name = 'cheques/cheque_print.html'

    def get(self, request, pk, *args, **kwargs):
        cheque = get_object_or_404(
            Cheque.objects.select_related('currency', 'supplier', 'customer', 'deposit_bank_account'),
            pk=pk
        )

        # تحويل المبلغ إلى تفقيط عربي معتمد
        curr_code = cheque.currency.code if cheque.currency else "EGP"
        amount_words = amount_to_arabic_words(cheque.amount, curr_code)

        # جلب قالب المعايرة الخاص بالبنك إن وجد
        layout = None
        if cheque.deposit_bank_account:
            layout = BankChequeLayout.objects.filter(
                bank_account=cheque.deposit_bank_account,
                is_active=True
            ).first()

        context = {
            'cheque': cheque,
            'amount_words': amount_words,
            'layout': layout,
        }
        return render(request, self.template_name, context)


class BankChequeLayoutListView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """
    قائمة قوالب معايرة أبعاد طباعة الشيكات للبنوك
    """
    permission_required = 'cheques.manage_checkbooks'
    template_name = 'cheques/layout_list.html'

    def get(self, request, *args, **kwargs):
        layouts = BankChequeLayout.objects.select_related('bank_account')

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('أوراق الدفع'), 'url': reverse('cheques:payable_list'), 'icon': 'fa-money-bill-wave'},
            {'title': _('معايرة طباعة الشيكات'), 'active': True}
        ]

        header_buttons = [
            {
                'url': reverse('cheques:layout_create'),
                'icon': 'fa-plus',
                'text': _('إضافة قالب بنك جديد'),
                'class': 'btn-primary'
            }
        ]

        context = {
            'page_title': _('قوالب معايرة طباعة الشيكات'),
            'page_subtitle': _('ضبط إحداثيات ومسافات الطباعة بالمليمتر لدفاتر شيكات البنوك المختلفة'),
            'page_icon': 'fa-ruler-combined',
            'breadcrumb_items': breadcrumb_items,
            'header_buttons': header_buttons,
            'layouts': layouts,
        }
        return render(request, self.template_name, context)


class BankChequeLayoutCreateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """
    إضافة قالب معايرة جديد لحساب بنكي
    """
    permission_required = 'cheques.manage_checkbooks'
    template_name = 'cheques/layout_form.html'

    def get(self, request, *args, **kwargs):
        form = BankChequeLayoutForm()
        return self._render(request, form)

    def post(self, request, *args, **kwargs):
        form = BankChequeLayoutForm(request.POST)
        if form.is_valid():
            layout = form.save()
            messages.success(request, _(f"تم حفظ قالب الطباعة {layout.name} بنجاح."))
            return redirect('cheques:layout_list')
        return self._render(request, form)

    def _render(self, request, form):
        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('أوراق الدفع'), 'url': reverse('cheques:payable_list'), 'icon': 'fa-money-bill-wave'},
            {'title': _('معايرة الطباعة'), 'url': reverse('cheques:layout_list'), 'icon': 'fa-ruler-combined'},
            {'title': _('إضافة قالب جديد'), 'active': True}
        ]
        context = {
            'page_title': _('إضافة قالب طباعة بنكي جديد'),
            'page_subtitle': _('تحديد أبعاد ومسافات حقول التاريخ والمستفيد والمبلغ والتفقيط بالمليمتر'),
            'page_icon': 'fa-plus-circle',
            'breadcrumb_items': breadcrumb_items,
            'form': form,
        }
        return render(request, self.template_name, context)


class BankChequeLayoutUpdateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """
    تعديل وضبط أبعاد قالب الطباعة
    """
    permission_required = 'cheques.manage_checkbooks'
    template_name = 'cheques/layout_form.html'

    def get(self, request, pk, *args, **kwargs):
        layout = get_object_or_404(BankChequeLayout, pk=pk)
        form = BankChequeLayoutForm(instance=layout)
        return self._render(request, form, layout)

    def post(self, request, pk, *args, **kwargs):
        layout = get_object_or_404(BankChequeLayout, pk=pk)
        form = BankChequeLayoutForm(request.POST, instance=layout)
        if form.is_valid():
            form.save()
            messages.success(request, _(f"تم تحديث قالب الطباعة {layout.name} بنجاح."))
            return redirect('cheques:layout_list')
        return self._render(request, form, layout)

    def _render(self, request, form, layout):
        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('أوراق الدفع'), 'url': reverse('cheques:payable_list'), 'icon': 'fa-money-bill-wave'},
            {'title': _('معايرة الطباعة'), 'url': reverse('cheques:layout_list'), 'icon': 'fa-ruler-combined'},
            {'title': layout.name, 'active': True}
        ]
        context = {
            'page_title': f"{_('تعديل قالب')}: {layout.name}",
            'page_subtitle': _('معايرة الأبعاد بالمليمتر لشيكات هذا الحساب البنكي'),
            'page_icon': 'fa-edit',
            'breadcrumb_items': breadcrumb_items,
            'form': form,
            'layout': layout,
        }
        return render(request, self.template_name, context)
