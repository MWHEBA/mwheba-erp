# -*- coding: utf-8 -*-
from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import View
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib import messages
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models import Q, Sum

from cheques.models import (
    Cheque,
    ChequeType,
    ChequeStatus,
    ChequePurpose,
    Checkbook,
    CheckbookLeaf,
    CheckbookLeafStatus,
)
from cheques.forms.cheque_forms import ChequePayableForm
from cheques.forms.action_forms import (
    ChequeBounceActionForm,
    ChequeReversalActionForm,
)
from cheques.forms.checkbook_forms import RuinedLeafReplacementForm
from financial.models import ChartOfAccounts
from cheques.services.accounting_service import ChequeAccountingService
from cheques.services.toggle_service import ChequeToggleService


class ChequePayableListView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """
    قائمة أوراق الدفع والشيكات الصادرة للموردين والجهات الخارجية
    تدعم البحث اللحظي doSearch والترقيم الخادمي SSR وكروت الإحصاء المالي
    """
    permission_required = 'cheques.view_cheque'
    template_name = 'cheques/payable_list.html'

    def get(self, request, *args, **kwargs):
        qs = Cheque.objects.filter(cheque_type=ChequeType.PAYABLE).select_related(
            'supplier', 'currency', 'deposit_bank_account', 'checkbook_leaf', 'checkbook_leaf__checkbook'
        )

        # 1. الفلاتر
        search_query = request.GET.get('search', '').strip()
        if search_query:
            qs = qs.filter(
                Q(cheque_number__icontains=search_query) |
                Q(voucher_number__icontains=search_query) |
                Q(payee_name__icontains=search_query) |
                Q(drawer_bank_name__icontains=search_query) |
                Q(supplier__name__icontains=search_query)
            )

        status = request.GET.get('status', '').strip()
        if status:
            qs = qs.filter(status=status)

        purpose = request.GET.get('purpose', '').strip()
        if purpose:
            qs = qs.filter(purpose=purpose)

        bank_account = request.GET.get('bank_account', '').strip()
        if bank_account:
            qs = qs.filter(deposit_bank_account_id=bank_account)

        date_from = request.GET.get('date_from', '').strip()
        if date_from:
            qs = qs.filter(due_date__gte=date_from)

        date_to = request.GET.get('date_to', '').strip()
        if date_to:
            qs = qs.filter(due_date__lte=date_to)

        # 2. مؤشرات الأداء المالي (KPI Stats)
        today = timezone.localdate()
        issued_qs = Cheque.objects.filter(
            cheque_type=ChequeType.PAYABLE,
            status=ChequeStatus.ISSUED
        )
        cleared_qs = Cheque.objects.filter(
            cheque_type=ChequeType.PAYABLE,
            status=ChequeStatus.CLEARED
        )
        due_soon_qs = Cheque.objects.filter(
            cheque_type=ChequeType.PAYABLE,
            status=ChequeStatus.ISSUED,
            due_date__lte=today + timezone.timedelta(days=7),
            due_date__gte=today
        )
        voided_qs = Cheque.objects.filter(
            cheque_type=ChequeType.PAYABLE,
            status=ChequeStatus.CANCELLED
        )

        stats = {
            'issued_total': issued_qs.aggregate(s=Sum('remaining_amount'))['s'] or Decimal('0.00'),
            'issued_count': issued_qs.count(),
            'cleared_total': cleared_qs.aggregate(s=Sum('amount'))['s'] or Decimal('0.00'),
            'cleared_count': cleared_qs.count(),
            'due_soon_total': due_soon_qs.aggregate(s=Sum('amount'))['s'] or Decimal('0.00'),
            'due_soon_count': due_soon_qs.count(),
            'voided_count': voided_qs.count(),
        }

        # 3. الترقيم الخادمي
        per_page = request.GET.get('per_page', '25')
        try:
            per_page = int(per_page)
        except ValueError:
            per_page = 25

        paginator = Paginator(qs, per_page)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        # 4. استجابة AJAX
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('ajax') == '1'
        if is_ajax:
            table_html = render_to_string(
                'cheques/partials/payable_table.html',
                {'cheques': page_obj, 'request': request}
            )
            pagination_html = render_to_string(
                'partials/pagination.html',
                {'page_obj': page_obj, 'request': request}
            )
            return JsonResponse({
                'table_html': table_html,
                'pagination_html': pagination_html,
                'stats': {
                    'issued_total': f"{stats['issued_total']:,.2f}",
                    'cleared_total': f"{stats['cleared_total']:,.2f}",
                    'due_soon_total': f"{stats['due_soon_total']:,.2f}",
                    'voided_count': str(stats['voided_count']),
                }
            })

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('الإدارة المالية'), 'url': reverse('financial:cash_accounts_list'), 'icon': 'fa-calculator'},
            {'title': _('أوراق الدفع (الشيكات الصادرة)'), 'active': True}
        ]

        header_buttons = [
            {
                'url': reverse('cheques:payable_create'),
                'icon': 'fa-plus',
                'text': _('إصدار شيك دفع جديد'),
                'class': 'btn-primary'
            },
            {
                'url': reverse('cheques:checkbook_list'),
                'icon': 'fa-book',
                'text': _('دفاتر الشيكات البنكية'),
                'class': 'btn-outline-secondary'
            }
        ]

        context = {
            'page_title': _('أوراق الدفع والشيكات الصادرة'),
            'page_subtitle': _('متابعة وإدارة الشيكات الصادرة للموردين والخصم البنكي وأرصدة الدفاتر'),
            'page_icon': 'fa-money-bill-wave',
            'breadcrumb_items': breadcrumb_items,
            'header_buttons': header_buttons,
            'cheques': page_obj,
            'page_obj': page_obj,
            'stats': stats,
            'status_choices': ChequeStatus.choices,
            'purpose_choices': ChequePurpose.choices,
            'bank_accounts': ChartOfAccounts.objects.filter(is_active=True, is_leaf=True),
            'is_draining': ChequeToggleService.is_draining(),
            'active_cheques_count': ChequeToggleService.get_active_cheques_count(),
        }
        return render(request, self.template_name, context)


class ChequePayableCreateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """
    إصدار شيك دفع جديد وسحب ورقة من دفتر الشيكات
    """
    permission_required = 'cheques.add_cheque'
    template_name = 'cheques/payable_form.html'

    def dispatch(self, request, *args, **kwargs):
        from cheques.services.toggle_service import ChequeToggleService
        if not ChequeToggleService.can_create_new_cheques():
            if ChequeToggleService.is_draining():
                messages.error(request, _("منظومة الشيكات في وضع التصفية (Draining Mode). تم تعليق إصدار الشيكات الجديدة لحين اكتمال تسوية الشيكات النشطة."))
            else:
                messages.error(request, _("منظومة الشيكات معطلة حالياً."))
            return redirect('cheques:payable_list')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        form = ChequePayableForm(user=request.user)
        return self._render_form(request, form)

    def post(self, request, *args, **kwargs):
        form = ChequePayableForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            cheque = form.save(commit=False)
            cheque.created_by = request.user
            cheque.status = ChequeStatus.DRAFT
            cheque.save()

            # اعتماد وإصدار الشيك محاسبياً إذا كان مكتمل الأركان
            try:
                ChequeAccountingService.issue_cheque(cheque=cheque, user=request.user)
                messages.success(request, _(f"تم إصدار شيك الدفع رقم {cheque.cheque_number} بالإذن {cheque.voucher_number} وترحيله محاسبياً بنجاح."))
            except Exception as e:
                messages.warning(request, _(f"تم حفظ مسودة الشيك بنجاح، لكن تعذر ترحيله المباشر: {e}"))

            return redirect('cheques:payable_detail', pk=cheque.pk)
        return self._render_form(request, form)

    def _render_form(self, request, form):
        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('أوراق الدفع'), 'url': reverse('cheques:payable_list'), 'icon': 'fa-money-bill-wave'},
            {'title': _('إصدار شيك دفع جديد'), 'active': True}
        ]
        context = {
            'page_title': _('إصدار شيك دفع جديد'),
            'page_subtitle': _('تحرير شيك صادر لمورد أو جهة خارجية وتحديد الحساب البنكي المسحوب عليه'),
            'page_icon': 'fa-plus-circle',
            'breadcrumb_items': breadcrumb_items,
            'form': form,
        }
        return render(request, self.template_name, context)


class ChequePayableDetailView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """
    تفاصيل شيك الدفع الصادر وسجل التدقيق وورقة الدفتر وإجراءات الصرف والخصم
    """
    permission_required = 'cheques.view_cheque'
    template_name = 'cheques/payable_detail.html'

    def get(self, request, pk, *args, **kwargs):
        cheque = get_object_or_404(
            Cheque.objects.select_related(
                'supplier', 'currency', 'deposit_bank_account', 'created_by',
                'checkbook_leaf', 'checkbook_leaf__checkbook'
            ),
            pk=pk,
            cheque_type=ChequeType.PAYABLE
        )

        action_logs = cheque.action_logs.select_related(
            'created_by', 'journal_entry'
        ).order_by('-created_at')

        settlement_lines = cheque.settlement_lines.select_related(
            'action_log__journal_entry', 'action_log__created_by', 'deposit_bank_account'
        ).order_by('-settlement_date')

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('أوراق الدفع'), 'url': reverse('cheques:payable_list'), 'icon': 'fa-money-bill-wave'},
            {'title': f"{cheque.cheque_number} ({cheque.voucher_number})", 'active': True}
        ]

        # نماذج المودالات
        bounce_form = ChequeBounceActionForm()
        reverse_form = ChequeReversalActionForm()
        ruined_leaf_form = RuinedLeafReplacementForm()

        header_buttons = [
            {
                'url': reverse('cheques:cheque_print', kwargs={'pk': cheque.pk}),
                'icon': 'fa-print',
                'text': _('طباعة الشيك البنكي'),
                'class': 'btn-primary',
                'target': '_blank'
            }
        ]

        context = {
            'page_title': f"{_('شيك دفع رقم')} {cheque.cheque_number}",
            'page_subtitle': f"{_('إذن صرف')} {cheque.voucher_number} - {_('المستفيد')}: {cheque.payee_name or (cheque.supplier.name if cheque.supplier else '')}",
            'page_icon': 'fa-file-invoice-dollar',
            'breadcrumb_items': breadcrumb_items,
            'header_buttons': header_buttons,
            'cheque': cheque,
            'action_logs': action_logs,
            'settlement_lines': settlement_lines,
            'bounce_form': bounce_form,
            'reverse_form': reverse_form,
            'ruined_leaf_form': ruined_leaf_form,
        }
        return render(request, self.template_name, context)
