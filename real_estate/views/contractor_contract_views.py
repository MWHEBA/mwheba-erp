# -*- coding: utf-8 -*-
"""
Contractor Contract Views (Track 1 - Phase 3)
واجهات إدارة ومتابعة عقود مقاولي الباطن والمقايسات التنفيذية
"""
from decimal import Decimal
import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.http import JsonResponse, HttpResponse
from django.template.loader import render_to_string
from django.core.paginator import Paginator
from django.contrib import messages
from django.db.models import Q, Sum, Count
from django.db import transaction

from users.mixins import SmartPermissionRequiredMixin
from real_estate.models import (
    ContractorContract,
    ContractorContractItem,
    ContractVariationOrder,
    ContractorProgressCertificate,
    SectionalHandoverRecord,
    ContractorDefaultNotice,
    ContractorScaffoldingLog,
    DewateringPumpingLog,
    JointTerminationSurveyProtocol,
    RealEstateProject,
    PropertyBlock,
)
from supplier.models import Supplier
from financial.models.currency import Currency
from real_estate.forms.contractor_forms import (
    ContractorContractForm,
    ContractorContractItemFormSet,
    ContractVariationOrderForm,
    AdvancePaymentDisbursementForm,
    JointTerminationSurveyForm,
)
from real_estate.services.contractor_contract_service import ContractorContractService

logger = logging.getLogger(__name__)


class ContractorContractListView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    قائمة عقود مقاولي الباطن مع الفلاتر القابلة للطي والبحث الفوري AJAX
    """
    permission_required = 'real_estate.view_contractorcontract'

    def get(self, request):
        search_query = request.GET.get('q', '').strip()
        project_id = request.GET.get('project', '').strip()
        contractor_id = request.GET.get('contractor', '').strip()
        status_filter = request.GET.get('status', '').strip()
        tax_regime_filter = request.GET.get('tax_regime', '').strip()

        qs = ContractorContract.objects.select_related(
            'project', 'block', 'contractor', 'currency', 'created_by'
        ).annotate(
            items_count=Count('items'),
            certificates_count=Count('certificates')
        ).order_by('-created_at', '-id')

        if search_query:
            qs = qs.filter(
                Q(contract_number__icontains=search_query) |
                Q(title__icontains=search_query) |
                Q(contractor__name__icontains=search_query) |
                Q(project__name__icontains=search_query)
            )

        if project_id:
            qs = qs.filter(project_id=project_id)

        if contractor_id:
            qs = qs.filter(contractor_id=contractor_id)

        if status_filter:
            qs = qs.filter(status=status_filter)

        if tax_regime_filter:
            qs = qs.filter(tax_regime=tax_regime_filter)

        paginator = Paginator(qs, 15)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        # حساب كروت الإحصائيات (KPIs)
        total_contracts = qs.count()
        total_contract_value = qs.aggregate(s=Sum('revised_contract_value'))['s'] or Decimal('0.00')
        total_advance_paid = qs.aggregate(s=Sum('advance_payment_disbursed'))['s'] or Decimal('0.00')
        total_retention_held = qs.aggregate(s=Sum('total_retention_retained'))['s'] or Decimal('0.00')

        # استجابة AJAX للبحث الديناميكي والترقيم (Rule 6)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.GET.get('ajax') == '1':
            table_html = render_to_string(
                'real_estate/partials/contractor_contract_table.html',
                {'page_obj': page_obj, 'contracts': page_obj.object_list},
                request=request
            )
            pagination_html = render_to_string(
                'partials/pagination.html',
                {'page_obj': page_obj},
                request=request
            )
            summary_html = render_to_string(
                'real_estate/partials/contractor_contract_summary.html',
                {
                    'total_contracts': total_contracts,
                    'total_contract_value': total_contract_value,
                    'total_advance_paid': total_advance_paid,
                    'total_retention_held': total_retention_held,
                },
                request=request
            )
            return JsonResponse({
                'table_html': table_html,
                'pagination_html': pagination_html,
                'summary_html': summary_html,
                'total_count': paginator.count
            })

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('القطاع العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('عقود مقاولي الباطن'), 'active': True}
        ]

        header_buttons = []
        if request.user.has_perm('real_estate.add_contractorcontract') or request.user.is_superuser:
            header_buttons.append({
                'url': reverse('real_estate:contractor_contract_create'),
                'label': _('عقد مقاولة جديد'),
                'icon': 'fa-plus',
                'class': 'btn-primary'
            })

        context = {
            'page_obj': page_obj,
            'contracts': page_obj.object_list,
            'projects': RealEstateProject.objects.filter(is_archived=False).order_by('name'),
            'contractors': Supplier.objects.filter(is_active=True).order_by('name'),
            'status_choices': ContractorContract.ContractStatus.choices,
            'tax_choices': ContractorContract.TaxRegime.choices,
            'selected_project': project_id,
            'selected_contractor': contractor_id,
            'selected_status': status_filter,
            'selected_tax': tax_regime_filter,
            'search_query': search_query,
            'total_contracts': total_contracts,
            'total_contract_value': total_contract_value,
            'total_advance_paid': total_advance_paid,
            'total_retention_held': total_retention_held,
            'breadcrumb_items': breadcrumb_items,
            'header_buttons': header_buttons,
            'active_menu': 're_engineering',
            'active_submenu': 'contractor_contracts',
        }
        return render(request, 'real_estate/contractor_contract_list.html', context)


class ContractorContractDetailView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    التفاصيل البانورامية لعقد المقاولة: البنود، التشوينات، أوامر التغيير، والاستلام الجزئي
    """
    permission_required = 'real_estate.view_contractorcontract'

    def get(self, request, pk):
        contract = get_object_or_404(
            ContractorContract.objects.select_related(
                'project', 'block', 'contractor', 'currency', 'created_by'
            ),
            pk=pk
        )

        items = contract.items.select_related('master_boq_item', 'block').order_by('id')
        variation_orders = contract.variation_orders.select_related('created_by').order_by('-created_at')
        certificates = contract.certificates.select_related('created_by', 'currency').order_by('-period_end', '-sequence_order')
        sectional_handovers = contract.sectional_handovers.order_by('-handover_date')
        default_notices = contract.default_notices.order_by('-notice_date')
        scaffolding_logs = contract.scaffolding_logs.order_by('-log_date')
        dewatering_logs = contract.dewatering_logs.order_by('-log_date')
        termination_protocol = getattr(contract, 'termination_protocol', None)

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('القطاع العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('عقود مقاولي الباطن'), 'url': reverse('real_estate:contractor_contract_list'), 'icon': 'fa-file-contract'},
            {'title': contract.contract_number, 'active': True}
        ]

        header_buttons = []
        if contract.status == ContractorContract.ContractStatus.DRAFT:
            if request.user.has_perm('real_estate.change_contractorcontract') or request.user.is_superuser:
                header_buttons.append({
                    'url': reverse('real_estate:contractor_contract_update', kwargs={'pk': contract.pk}),
                    'label': _('تعديل العقد'),
                    'icon': 'fa-edit',
                    'class': 'btn-outline-primary'
                })
        
        if contract.status == ContractorContract.ContractStatus.ACTIVE:
            if request.user.has_perm('real_estate.add_contractorprogresscertificate') or request.user.is_superuser:
                header_buttons.append({
                    'url': f"{reverse('real_estate:contractor_create')}?contract={contract.pk}",
                    'label': _('إصدار مستخلص'),
                    'icon': 'fa-plus',
                    'class': 'btn-success'
                })

        context = {
            'contract': contract,
            'items': items,
            'variation_orders': variation_orders,
            'certificates': certificates,
            'sectional_handovers': sectional_handovers,
            'default_notices': default_notices,
            'scaffolding_logs': scaffolding_logs,
            'dewatering_logs': dewatering_logs,
            'termination_protocol': termination_protocol,
            'breadcrumb_items': breadcrumb_items,
            'header_buttons': header_buttons,
            'active_menu': 're_engineering',
            'active_submenu': 'contractor_contracts',
            'advance_form': AdvancePaymentDisbursementForm(initial={'amount': (contract.revised_contract_value * (contract.advance_payment_rate / Decimal('100.00'))).quantize(Decimal('0.01'))}),
            'vo_form': ContractVariationOrderForm(),
            'termination_form': JointTerminationSurveyForm(initial={'protocol_reference': f"TERM-{contract.contract_number}"}),
        }
        return render(request, 'real_estate/contractor_contract_detail.html', context)


class ContractorContractCreateView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    إنشاء عقد مقاولة باطن جديد مع بنود المقايسة المسعرة
    """
    permission_required = 'real_estate.add_contractorcontract'

    def get(self, request):
        form = ContractorContractForm()
        formset = ContractorContractItemFormSet()

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('القطاع العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('عقود مقاولي الباطن'), 'url': reverse('real_estate:contractor_contract_list'), 'icon': 'fa-file-contract'},
            {'title': _('إنشاء عقد جديد'), 'active': True}
        ]

        context = {
            'form': form,
            'formset': formset,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_engineering',
            'active_submenu': 'contractor_contracts',
            'is_edit': False,
        }
        return render(request, 'real_estate/contractor_contract_form.html', context)

    def post(self, request):
        form = ContractorContractForm(request.POST)
        formset = ContractorContractItemFormSet(request.POST)

        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                contract = form.save(commit=False)
                contract.created_by = request.user
                contract.save()

                formset.instance = contract
                items = formset.save()

                # حساب القيمة التعاقدية من مجموع البنود إذا لم تُحدد
                items_total = sum(i.contracted_quantity * i.unit_rate for i in contract.items.all())
                if items_total > Decimal('0.00') and (contract.initial_contract_value == Decimal('0.00') or not contract.initial_contract_value):
                    contract.initial_contract_value = items_total
                    contract.revised_contract_value = items_total
                    contract.save(update_fields=['initial_contract_value', 'revised_contract_value'])

            messages.success(request, _('تم إنشاء عقد المقاولة %(num)s بنجاح.') % {'num': contract.contract_number})
            return redirect('real_estate:contractor_contract_detail', pk=contract.pk)

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('القطاع العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('عقود مقاولي الباطن'), 'url': reverse('real_estate:contractor_contract_list'), 'icon': 'fa-file-contract'},
            {'title': _('إنشاء عقد جديد'), 'active': True}
        ]
        context = {
            'form': form,
            'formset': formset,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_engineering',
            'active_submenu': 'contractor_contracts',
            'is_edit': False,
        }
        return render(request, 'real_estate/contractor_contract_form.html', context)


class ContractorContractUpdateView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تعديل عقد مقاولة باطن وبنود المقايسة
    """
    permission_required = 'real_estate.change_contractorcontract'

    def get(self, request, pk):
        contract = get_object_or_404(ContractorContract, pk=pk)
        if contract.status not in [ContractorContract.ContractStatus.DRAFT, ContractorContract.ContractStatus.UNDER_REVIEW]:
            messages.error(request, _('لا يمكن تعديل العقد بعد اعتماده أو تفعيله.'))
            return redirect('real_estate:contractor_contract_detail', pk=contract.pk)

        form = ContractorContractForm(instance=contract)
        formset = ContractorContractItemFormSet(instance=contract)

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('القطاع العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('عقود مقاولي الباطن'), 'url': reverse('real_estate:contractor_contract_list'), 'icon': 'fa-file-contract'},
            {'title': contract.contract_number, 'url': reverse('real_estate:contractor_contract_detail', kwargs={'pk': contract.pk})},
            {'title': _('تعديل العقد'), 'active': True}
        ]

        context = {
            'contract': contract,
            'form': form,
            'formset': formset,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_engineering',
            'active_submenu': 'contractor_contracts',
            'is_edit': True,
        }
        return render(request, 'real_estate/contractor_contract_form.html', context)

    def post(self, request, pk):
        contract = get_object_or_404(ContractorContract, pk=pk)
        if contract.status not in [ContractorContract.ContractStatus.DRAFT, ContractorContract.ContractStatus.UNDER_REVIEW]:
            messages.error(request, _('لا يمكن تعديل العقد بعد اعتماده أو تفعيله.'))
            return redirect('real_estate:contractor_contract_detail', pk=contract.pk)

        form = ContractorContractForm(request.POST, instance=contract)
        formset = ContractorContractItemFormSet(request.POST, instance=contract)

        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                contract = form.save()
                formset.save()

                items_total = sum(i.contracted_quantity * i.unit_rate for i in contract.items.all())
                if items_total > Decimal('0.00'):
                    contract.initial_contract_value = items_total
                    contract.revised_contract_value = items_total + (contract.variation_orders.filter(status=ContractVariationOrder.VariationStatus.APPROVED).aggregate(s=Sum('net_value_impact'))['s'] or Decimal('0.00'))
                    contract.save(update_fields=['initial_contract_value', 'revised_contract_value'])

            messages.success(request, _('تم تحديث بيانات عقد المقاولة بنجاح.'))
            return redirect('real_estate:contractor_contract_detail', pk=contract.pk)

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('القطاع العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('عقود مقاولي الباطن'), 'url': reverse('real_estate:contractor_contract_list'), 'icon': 'fa-file-contract'},
            {'title': contract.contract_number, 'url': reverse('real_estate:contractor_contract_detail', kwargs={'pk': contract.pk})},
            {'title': _('تعديل العقد'), 'active': True}
        ]
        context = {
            'contract': contract,
            'form': form,
            'formset': formset,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_engineering',
            'active_submenu': 'contractor_contracts',
            'is_edit': True,
        }
        return render(request, 'real_estate/contractor_contract_form.html', context)


class ContractorContractDisburseAdvanceView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    صرف الدفعة المقدمة الأصلية للعقد عبر AccountingGateway
    """
    permission_required = 'real_estate.change_contractorcontract'

    def post(self, request, pk):
        contract = get_object_or_404(ContractorContract, pk=pk)
        form = AdvancePaymentDisbursementForm(request.POST)

        if form.is_valid():
            amount = form.cleaned_data['amount']
            escrow_code = form.cleaned_data['escrow_account_code']
            try:
                entry = ContractorContractService.disburse_advance_payment(
                    contract=contract,
                    amount=amount,
                    user=request.user,
                    bank_account_code=escrow_code
                )
                msg = _('تم صرف الدفعة المقدمة بمبلغ %(amt)s وتوليد قيد اليومية رقم %(entry)s بنجاح.') % {
                    'amt': f"{amount:,.2f}",
                    'entry': getattr(entry, 'number', str(entry.id))
                }
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': True, 'message': msg})
                messages.success(request, msg)
            except Exception as e:
                logger.error(f"Error disbursing advance payment for contract {contract.contract_number}: {e}", exc_info=True)
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'message': str(e)}, status=400)
                messages.error(request, str(e))
        else:
            err_msg = _("بيانات صرف الدفعة المقدمة غير مكتملة.")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': err_msg}, status=400)
            messages.error(request, err_msg)

        return redirect('real_estate:contractor_contract_detail', pk=contract.pk)


class ContractorContractVariationOrderCreateView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    إنشاء واعتماد أمر تغيير تعاقدي مع إعادة المعايرة الديناميكية لمعدل استرداد الدفعة المقدمة
    """
    permission_required = 'real_estate.change_contractorcontract'

    def post(self, request, pk):
        contract = get_object_or_404(ContractorContract, pk=pk)
        form = ContractVariationOrderForm(request.POST)

        if form.is_valid():
            vo_data = {
                'variation_number': form.cleaned_data['order_number'],
                'variation_type': form.cleaned_data['variation_type'],
                'description': form.cleaned_data['description'],
                'amount_impact': form.cleaned_data['net_value_impact'],
                'time_extension_days': form.cleaned_data['approved_additional_days'],
                'consultant_reference': form.cleaned_data['consultant_approval_ref'],
            }
            try:
                vo = ContractorContractService.create_variation_order(
                    contract=contract,
                    vo_data=vo_data,
                    user=request.user
                )
                msg = _('تم إنشاء أمر التغيير رقم %(vo)s وتحديث سقف العقد ومعدل الاسترداد بنجاح.') % {'vo': vo.order_number}
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': True, 'message': msg})
                messages.success(request, msg)
            except Exception as e:
                logger.error(f"Error creating variation order for contract {contract.contract_number}: {e}", exc_info=True)
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'message': str(e)}, status=400)
                messages.error(request, str(e))
        else:
            err_msg = _("يرجى مراجعة بيانات أمر التغيير المدخلة.")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': err_msg}, status=400)
            messages.error(request, err_msg)

        return redirect('real_estate:contractor_contract_detail', pk=contract.pk)


class ContractorContractTerminateView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    فسخ العقد وإجراء الحصر المشترك وتسوية تشوينات الموقع لمخزن المشروع
    """
    permission_required = 'real_estate.change_contractorcontract'

    def post(self, request, pk):
        contract = get_object_or_404(ContractorContract, pk=pk)
        form = JointTerminationSurveyForm(request.POST)

        if form.is_valid():
            protocol_data = form.cleaned_data
            try:
                protocol = ContractorContractService.terminate_contract_and_settle(
                    contract=contract,
                    protocol_data=protocol_data,
                    user=request.user
                )
                msg = _('تم فسخ العقد وتوثيق محضر الحصر المشترك %(ref)s واستيعاب التشوينات بنجاح.') % {'ref': protocol.protocol_reference}
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': True, 'message': msg})
                messages.success(request, msg)
            except Exception as e:
                logger.error(f"Error terminating contract {contract.contract_number}: {e}", exc_info=True)
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'message': str(e)}, status=400)
                messages.error(request, str(e))
        else:
            err_msg = _("يرجى استيفاء بيانات محضر الفسخ والحصر المشترك.")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': err_msg}, status=400)
            messages.error(request, err_msg)

        return redirect('real_estate:contractor_contract_detail', pk=contract.pk)


class ApiContractorContractItemsView(LoginRequiredMixin, View):
    """
    واجهة برمجية JSON لجلب بنود المقايسة المسعرة للعقد مع الكميات السابقة لتغذية شاشة إنشاء المستخلص
    """
    def get(self, request, contract_id):
        contract = get_object_or_404(ContractorContract, pk=contract_id)
        items = contract.items.select_related('block', 'master_boq_item').order_by('id')

        # استدعاء الحصر التراكمي السابق المعتمد لكل بند
        items_data = []
        for item in items:
            prev_qty = ContractorContractService.get_cumulative_certified_quantity(contract, item.item_code)
            items_data.append({
                'id': item.id,
                'item_code': item.item_code,
                'description': item.description,
                'unit': item.unit,
                'unit_rate': str(item.unit_rate),
                'contracted_quantity': str(item.contracted_quantity),
                'previous_quantity': str(prev_qty),
                'remaining_quantity': str(max(Decimal('0.00'), item.contracted_quantity - prev_qty)),
                'block_id': item.block_id,
                'block_code': item.block.code if item.block else '',
            })

        return JsonResponse({
            'success': True,
            'contract_number': contract.contract_number,
            'currency_code': getattr(contract.currency, 'code', 'EGP'),
            'retention_percentage': str(contract.retention_rate),
            'advance_payment_recovery_cap_percentage': str(contract.advance_recovery_rate),
            'tax_regime': contract.tax_regime,
            'syndicate_stamp_rate': str(contract.syndicate_stamp_rate),
            'site_utilities_deduction_rate': str(contract.site_utilities_deduction_rate),
            'is_assigned_to_bank': contract.is_assigned_to_bank,
            'assigned_bank_name': contract.assigned_bank_name,
            'assigned_bank_iban': contract.assigned_bank_iban,
            'is_garnished_by_court': contract.is_garnished_by_court,
            'items': items_data
        })
