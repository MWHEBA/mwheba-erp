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
    ChequeInvoiceAllocation,
    AllocationStatus,
)
from cheques.forms.cheque_forms import ChequeReceivableForm
from cheques.forms.action_forms import (
    ChequeDepositActionForm,
    ChequeCollectActionForm,
    ChequeBounceActionForm,
    ChequeEndorseActionForm,
    ChequeReversalActionForm,
    ChequeConvertGuaranteeActionForm,
    ChequeReturnToDrawerActionForm,
    ChequeAllocateToInvoiceForm,
    ChequeDeallocateActionForm,
)
from financial.models import ChartOfAccounts
from cheques.services.toggle_service import ChequeToggleService


class ChequeReceivableListView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """
    قائمة أوراق القبض والشيكات الواردة من العملاء
    تدعم البحث اللحظي doSearch وترقيم الصفحات SSR وكروت الإحصاء المالي
    """
    permission_required = 'cheques.view_cheque'
    template_name = 'cheques/receivable_list.html'

    def get(self, request, *args, **kwargs):
        qs = Cheque.objects.filter(cheque_type=ChequeType.RECEIVABLE).select_related(
            'customer', 'currency', 'deposit_bank_account'
        )

        # 1. تطبيق الفلاتر
        search_query = request.GET.get('search', '').strip()
        if search_query:
            qs = qs.filter(
                Q(cheque_number__icontains=search_query) |
                Q(voucher_number__icontains=search_query) |
                Q(drawer_name__icontains=search_query) |
                Q(drawer_bank_name__icontains=search_query) |
                Q(customer__name__icontains=search_query)
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

        # 2. حساب مؤشرات الأداء المالي (KPI Stats)
        today = timezone.localdate()
        in_portfolio_qs = Cheque.objects.filter(
            cheque_type=ChequeType.RECEIVABLE,
            status=ChequeStatus.IN_PORTFOLIO
        )
        under_collection_qs = Cheque.objects.filter(
            cheque_type=ChequeType.RECEIVABLE,
            status=ChequeStatus.UNDER_COLLECTION
        )
        due_soon_qs = Cheque.objects.filter(
            cheque_type=ChequeType.RECEIVABLE,
            status__in=[ChequeStatus.IN_PORTFOLIO, ChequeStatus.UNDER_COLLECTION],
            due_date__lte=today + timezone.timedelta(days=7),
            due_date__gte=today
        )
        bounced_qs = Cheque.objects.filter(
            cheque_type=ChequeType.RECEIVABLE,
            status__in=[ChequeStatus.BOUNCED, ChequeStatus.ENDORSED_BOUNCED]
        )

        stats = {
            'in_portfolio_total': in_portfolio_qs.aggregate(s=Sum('amount'))['s'] or Decimal('0.00'),
            'in_portfolio_count': in_portfolio_qs.count(),
            'under_collection_total': under_collection_qs.aggregate(s=Sum('amount'))['s'] or Decimal('0.00'),
            'under_collection_count': under_collection_qs.count(),
            'due_soon_total': due_soon_qs.aggregate(s=Sum('amount'))['s'] or Decimal('0.00'),
            'due_soon_count': due_soon_qs.count(),
            'bounced_total': bounced_qs.aggregate(s=Sum('remaining_amount'))['s'] or Decimal('0.00'),
            'bounced_count': bounced_qs.count(),
        }

        # 3. الترقيم الخادمي (SSR Pagination)
        per_page = request.GET.get('per_page', '25')
        try:
            per_page = int(per_page)
        except ValueError:
            per_page = 25

        paginator = Paginator(qs, per_page)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        # 4. الاستجابة لطلبات البحث الديناميكي AJAX
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('ajax') == '1'
        if is_ajax:
            table_html = render_to_string(
                'cheques/partials/receivable_table.html',
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
                    'in_portfolio_total': f"{stats['in_portfolio_total']:,.2f}",
                    'under_collection_total': f"{stats['under_collection_total']:,.2f}",
                    'due_soon_total': f"{stats['due_soon_total']:,.2f}",
                    'bounced_total': f"{stats['bounced_total']:,.2f}",
                }
            })

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('الإدارة المالية'), 'url': reverse('financial:cash_accounts_list'), 'icon': 'fa-calculator'},
            {'title': _('أوراق القبض (الشيكات الواردة)'), 'active': True}
        ]

        header_buttons = [
            {
                'url': reverse('cheques:receivable_create'),
                'icon': 'fa-plus',
                'text': _('استلام شيك قبض جديد'),
                'class': 'btn-primary'
            },
            {
                'url': reverse('cheques:batch_deposit_create'),
                'icon': 'fa-layer-group',
                'text': _('إنشاء حافظة إيداع بنكية'),
                'class': 'btn-outline-secondary'
            }
        ]

        context = {
            'page_title': _('أوراق القبض والشيكات الواردة'),
            'page_subtitle': _('متابعة وإدارة دورة حياة الشيكات الواردة من التحصيل وحتى الإقفال'),
            'page_icon': 'fa-money-check-alt',
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


class ChequeReceivableCreateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """
    تسجيل سند استلام شيك ورقة قبض جديد
    """
    permission_required = 'cheques.add_cheque'
    template_name = 'cheques/receivable_form.html'

    def dispatch(self, request, *args, **kwargs):
        from cheques.services.toggle_service import ChequeToggleService
        if not ChequeToggleService.can_create_new_cheques():
            if ChequeToggleService.is_draining():
                messages.error(request, _("منظومة الشيكات في وضع التصفية (Draining Mode). تم تعليق إصدار الشيكات الجديدة لحين اكتمال تسوية الشيكات النشطة."))
            else:
                messages.error(request, _("منظومة الشيكات معطلة حالياً."))
            return redirect('cheques:receivable_list')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        form = ChequeReceivableForm(user=request.user)
        return self._render_form(request, form)

    def post(self, request, *args, **kwargs):
        form = ChequeReceivableForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            cheque = form.save(commit=False)
            cheque.created_by = request.user
            cheque.status = ChequeStatus.DRAFT
            cheque.save()

            # استلام وترحيل الشيك محاسبياً وإيداعه بالمحفظة (ما لم يكن شيك ضمان أو مسودة صريحة)
            if not cheque.is_guarantee and request.POST.get('save_mode') != 'draft':
                try:
                    ChequeAccountingService.receive_cheque(cheque=cheque, user=request.user)
                    messages.success(request, _(f"تم تسجيل شيك القبض رقم {cheque.cheque_number} وإيداعه بالمحفظة بنجاح."))
                except Exception as e:
                    messages.warning(request, _(f"تم حفظ مسودة الشيك بنجاح، لكن تعذر الاستلام المحاسبي التلقائي: {e}"))
            else:
                messages.success(request, _(f"تم تسجيل شيك القبض رقم {cheque.cheque_number} بالإيصال {cheque.voucher_number} كمسودة بنجاح."))
            return redirect('cheques:receivable_detail', pk=cheque.pk)
        return self._render_form(request, form)

    def _render_form(self, request, form):
        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('أوراق القبض'), 'url': reverse('cheques:receivable_list'), 'icon': 'fa-money-check-alt'},
            {'title': _('استلام شيك جديد'), 'active': True}
        ]
        context = {
            'page_title': _('استلام شيك قبض جديد'),
            'page_subtitle': _('تسجيل بيانات الشيك الوارد والساحب ومستندات الضمان أو سداد الفواتير'),
            'page_icon': 'fa-plus-circle',
            'breadcrumb_items': breadcrumb_items,
            'form': form,
        }
        return render(request, self.template_name, context)


class ChequeReceivableDetailView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """
    عرض تفاصيل شيك القبض والشريط الزمني للعمليات وسجل التدقيق وإجراءات الشيك السريعة
    """
    permission_required = 'cheques.view_cheque'
    template_name = 'cheques/receivable_detail.html'

    def get(self, request, pk, *args, **kwargs):
        cheque = get_object_or_404(
            Cheque.objects.select_related(
                'customer', 'currency', 'deposit_bank_account', 'created_by', 'related_sale'
            ),
            pk=pk,
            cheque_type=ChequeType.RECEIVABLE
        )

        action_logs = cheque.action_logs.select_related(
            'created_by', 'journal_entry'
        ).order_by('-created_at')

        settlement_lines = cheque.settlement_lines.select_related(
            'action_log__journal_entry', 'action_log__created_by', 'deposit_bank_account'
        ).order_by('-settlement_date')

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('أوراق القبض'), 'url': reverse('cheques:receivable_list'), 'icon': 'fa-money-check-alt'},
            {'title': f"{cheque.cheque_number} ({cheque.voucher_number})", 'active': True}
        ]

        # نماذج الإجراءات للمودالات
        today = timezone.localdate()
        deposit_form = ChequeDepositActionForm(user=request.user)
        collect_form = ChequeCollectActionForm(
            initial={
                'collected_amount': cheque.remaining_amount,
                'collection_date': today,
                'exchange_rate': cheque.original_exchange_rate or Decimal('1.000000'),
            },
            user=request.user
        )
        bounce_form = ChequeBounceActionForm()
        endorse_form = ChequeEndorseActionForm()
        reverse_form = ChequeReversalActionForm()
        convert_guarantee_form = ChequeConvertGuaranteeActionForm()
        return_to_drawer_form = ChequeReturnToDrawerActionForm()

        # تخصيصات الشيك على فواتير المبيعات
        allocations = cheque.invoice_allocations.select_related(
            'sale', 'journal_entry', 'sale_payment', 'allocation_audit'
        ).order_by('-allocation_date', '-id')

        applied_allocations_sum = allocations.filter(
            allocation_status=AllocationStatus.APPLIED
        ).aggregate(total=Sum('allocated_amount'))['total'] or Decimal('0.00')

        unallocated_amount = max(Decimal('0.00'), cheque.amount - applied_allocations_sum)

        can_allocate = (
            cheque.status not in [
                ChequeStatus.DRAFT,
                ChequeStatus.BOUNCED,
                ChequeStatus.CANCELLED,
                ChequeStatus.RETURNED_TO_DRAWER,
            ]
            and not cheque.is_guarantee
            and bool(cheque.customer_id)
            and unallocated_amount > Decimal('0.00')
        )

        allocate_invoice_form = ChequeAllocateToInvoiceForm(cheque=cheque, user=request.user) if can_allocate else None
        deallocate_form = ChequeDeallocateActionForm()

        header_buttons = []
        if request.user.has_perm('cheques.print_cheque'):
            header_buttons.append({
                'url': reverse('cheques:cheque_print', kwargs={'pk': cheque.pk}),
                'icon': 'fa-print',
                'text': _('طباعة إشعار الاستلام'),
                'class': 'btn-outline-secondary',
                'target': '_blank'
            })

        context = {
            'page_title': f"{_('شيك قبض رقم')} {cheque.cheque_number}",
            'page_subtitle': f"{_('إيصال')} {cheque.voucher_number} - {_('العميل')}: {cheque.customer.name if cheque.customer else cheque.drawer_name}",
            'page_icon': 'fa-file-invoice',
            'breadcrumb_items': breadcrumb_items,
            'header_buttons': header_buttons,
            'cheque': cheque,
            'action_logs': action_logs,
            'settlement_lines': settlement_lines,
            'allocations': allocations,
            'applied_allocations_sum': applied_allocations_sum,
            'unallocated_amount': unallocated_amount,
            'can_allocate': can_allocate,
            'allocate_invoice_form': allocate_invoice_form,
            'deallocate_form': deallocate_form,
            'deposit_form': deposit_form,
            'collect_form': collect_form,
            'bounce_form': bounce_form,
            'endorse_form': endorse_form,
            'reverse_form': reverse_form,
            'convert_guarantee_form': convert_guarantee_form,
            'return_to_drawer_form': return_to_drawer_form,
        }
        return render(request, self.template_name, context)
