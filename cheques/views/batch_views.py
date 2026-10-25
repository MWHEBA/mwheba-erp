# -*- coding: utf-8 -*-
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import View
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib import messages
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.core.paginator import Paginator
from django.db.models import Q, Sum

from cheques.models import ChequeBatchDeposit, BatchDepositStatus
from cheques.forms.action_forms import ChequeBatchDepositForm
from cheques.services.batch_deposit_service import ChequeBatchDepositService


class ChequeBatchDepositListView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """
    قائمة حافظات إيداع الشيكات المجمعة بالبنوك
    """
    permission_required = 'cheques.view_cheque'
    template_name = 'cheques/batch_deposit_list.html'

    def get(self, request, *args, **kwargs):
        qs = ChequeBatchDeposit.objects.select_related('bank_account', 'created_by').prefetch_related('cheques')

        search_query = request.GET.get('search', '').strip()
        if search_query:
            qs = qs.filter(
                Q(batch_number__icontains=search_query) |
                Q(bank_account__name__icontains=search_query)
            )

        status = request.GET.get('status', '').strip()
        if status:
            qs = qs.filter(status=status)

        paginator = Paginator(qs, 20)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('ajax') == '1'
        if is_ajax:
            table_html = render_to_string(
                'cheques/partials/batch_deposit_table.html',
                {'batches': page_obj, 'request': request}
            )
            pagination_html = render_to_string(
                'partials/pagination.html',
                {'page_obj': page_obj, 'request': request}
            )
            return JsonResponse({
                'table_html': table_html,
                'pagination_html': pagination_html,
            })

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('أوراق القبض'), 'url': reverse('cheques:receivable_list'), 'icon': 'fa-money-check-alt'},
            {'title': _('حافظات الإيداع البنكية'), 'active': True}
        ]

        header_buttons = [
            {
                'url': reverse('cheques:batch_deposit_create'),
                'icon': 'fa-plus',
                'text': _('إنشاء حافظة إيداع جديدة'),
                'class': 'btn-primary'
            }
        ]

        context = {
            'page_title': _('حافظات إيداع الشيكات بالبنوك'),
            'page_subtitle': _('إدارة ومتابعة حافظات تسليم الشيكات المجمعة للبنوك برسم التحصيل'),
            'page_icon': 'fa-layer-group',
            'breadcrumb_items': breadcrumb_items,
            'header_buttons': header_buttons,
            'batches': page_obj,
            'page_obj': page_obj,
            'status_choices': BatchDepositStatus.choices,
        }
        return render(request, self.template_name, context)


class ChequeBatchDepositCreateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """
    إنشاء حافظة إيداع جديدة برقم تسلسلي آلي موحد
    """
    permission_required = 'cheques.deposit_cheque'
    template_name = 'cheques/batch_deposit_form.html'

    def get(self, request, *args, **kwargs):
        form = ChequeBatchDepositForm(user=request.user)
        return self._render(request, form)

    def post(self, request, *args, **kwargs):
        form = ChequeBatchDepositForm(request.POST, user=request.user)
        if form.is_valid():
            bank_account = form.cleaned_data['bank_account']
            deposit_date = form.cleaned_data['deposit_date']
            selected_cheques = form.cleaned_data['cheques']
            notes = form.cleaned_data.get('notes', '')

            cheque_ids = [c.id for c in selected_cheques]
            try:
                batch = ChequeBatchDepositService.create_and_deposit_batch(
                    bank_account_id=bank_account.id,
                    cheque_ids=cheque_ids,
                    deposit_date=deposit_date,
                    user=request.user,
                    notes=notes
                )
                messages.success(request, _(f"تم إنشاء حافظة الإيداع رقم {batch.batch_number} بنجاح وإيداع {len(cheque_ids)} شيك برسم التحصيل."))
                return redirect('cheques:batch_deposit_detail', pk=batch.pk)
            except Exception as e:
                messages.error(request, str(e))

        return self._render(request, form)

    def _render(self, request, form):
        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('أوراق القبض'), 'url': reverse('cheques:receivable_list'), 'icon': 'fa-money-check-alt'},
            {'title': _('حافظات الإيداع'), 'url': reverse('cheques:batch_deposit_list'), 'icon': 'fa-layer-group'},
            {'title': _('إنشاء حافظة إيداع جديدة'), 'active': True}
        ]
        context = {
            'page_title': _('إنشاء حافظة إيداع شيكات بنكية'),
            'page_subtitle': _('تجميع عدة شيكات من المحفظة وتسليمها للبنك بمستند إيداع موحد'),
            'page_icon': 'fa-plus-circle',
            'breadcrumb_items': breadcrumb_items,
            'form': form,
        }
        return render(request, self.template_name, context)


class ChequeBatchDepositDetailView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """
    تفاصيل حافظة الإيداع والشيكات المودعة بها وحالة التحصيل
    """
    permission_required = 'cheques.view_cheque'
    template_name = 'cheques/batch_deposit_detail.html'

    def get(self, request, pk, *args, **kwargs):
        batch = get_object_or_404(
            ChequeBatchDeposit.objects.select_related('bank_account', 'created_by').prefetch_related(
                'cheques', 'cheques__customer', 'cheques__currency'
            ),
            pk=pk
        )

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('أوراق القبض'), 'url': reverse('cheques:receivable_list'), 'icon': 'fa-money-check-alt'},
            {'title': _('حافظات الإيداع'), 'url': reverse('cheques:batch_deposit_list'), 'icon': 'fa-layer-group'},
            {'title': batch.batch_number, 'active': True}
        ]

        context = {
            'page_title': f"{_('حافظة إيداع رقم')} {batch.batch_number}",
            'page_subtitle': f"{_('البنك')}: {batch.bank_account.name} - {_('تاريخ الإيداع')}: {batch.deposit_date}",
            'page_icon': 'fa-receipt',
            'breadcrumb_items': breadcrumb_items,
            'batch': batch,
            'cheques': batch.cheques.all(),
        }
        return render(request, self.template_name, context)
