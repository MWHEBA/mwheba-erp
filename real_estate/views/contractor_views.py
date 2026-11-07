# -*- coding: utf-8 -*-
"""
Contractor Progress Certificate Views (Track 1 & Wave 2 - Phase 6 & Phase 3)
واجهات إدارة مستخلصات مقاولي الباطن، الحصر التراكمي، الاعتمادات المؤسسية، والطباعة الرسمية
"""
from decimal import Decimal
import logging
import csv
import io

from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.http import JsonResponse, HttpResponse
from django.template.loader import render_to_string
from django.core.paginator import Paginator
from django.contrib import messages
from django.db.models import Q, Sum
from django.db import transaction
from django.utils import timezone

from users.mixins import SmartPermissionRequiredMixin
from real_estate.models import (
    ContractorProgressCertificate,
    ContractorCertificateItem,
    ContractorContract,
    ContractorContractItem,
    CertificatePaymentInstallmentSchedule,
    RealEstateProject,
)
from real_estate.services.contractor_service import (
    ContractorProgressService,
    MissingApprovalRuleError,
    MutationTamperError,
    SequentialOrderError,
    FinalSettlementComplianceError,
)
from supplier.models import Supplier
from financial.models.currency import Currency
from cheques.models import Cheque
from real_estate.forms.contractor_forms import (
    ContractorProgressCertificateForm,
    ContractorCertificateItemFormSet,
    CertificateExcelImportForm,
    RetentionReleaseForm,
    StornoReversalForm,
    InstallmentChequeSettlementForm,
)

logger = logging.getLogger(__name__)


class ContractorCertificateListView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    قائمة مستخلصات المقاولين الإنشائية ومقاولي الباطن مع الفلاتر والبحث الحركي AJAX
    """
    permission_required = 'real_estate.view_contractorprogresscertificate'

    def get(self, request):
        search_query = request.GET.get('q', '').strip()
        project_id = request.GET.get('project', '').strip()
        contractor_id = request.GET.get('contractor', '').strip()
        contract_id = request.GET.get('contract', '').strip()
        status_filter = request.GET.get('status', '').strip()
        type_filter = request.GET.get('certificate_type', '').strip()

        qs = ContractorProgressCertificate.objects.select_related(
            'project', 'contractor', 'contract', 'currency', 'created_by'
        ).order_by('-period_end', '-sequence_order', '-id')

        if search_query:
            qs = qs.filter(
                Q(certificate_number__icontains=search_query) |
                Q(contractor__name__icontains=search_query) |
                Q(project__name__icontains=search_query) |
                Q(contract_reference__icontains=search_query) |
                Q(contract__contract_number__icontains=search_query)
            )

        if project_id:
            qs = qs.filter(project_id=project_id)

        if contractor_id:
            qs = qs.filter(contractor_id=contractor_id)

        if contract_id:
            qs = qs.filter(contract_id=contract_id)

        if status_filter:
            qs = qs.filter(status=status_filter)

        if type_filter:
            qs = qs.filter(certificate_type=type_filter)

        paginator = Paginator(qs, 15)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        total_certs = qs.count()
        total_certified_gross = qs.aggregate(s=Sum('gross_certified_work'))['s'] or Decimal('0.00')
        total_retention = qs.aggregate(s=Sum('retention_amount'))['s'] or Decimal('0.00')
        total_net_payable = qs.filter(
            status=ContractorProgressCertificate.CertificateStatus.APPROVED
        ).aggregate(s=Sum('net_amount'))['s'] or Decimal('0.00')

        # استجابة AJAX للبحث الديناميكي والترقيم (Rule 6)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.GET.get('ajax') == '1':
            table_html = render_to_string(
                'real_estate/partials/contractor_certificate_table.html',
                {'page_obj': page_obj, 'certificates': page_obj.object_list},
                request=request
            )
            pagination_html = render_to_string(
                'partials/pagination.html',
                {'page_obj': page_obj},
                request=request
            )
            totals_html = render_to_string(
                'real_estate/partials/contractor_certificate_totals.html',
                {
                    'total_certs': total_certs,
                    'total_certified_gross': total_certified_gross,
                    'total_retention': total_retention,
                    'total_net_payable': total_net_payable,
                },
                request=request
            )
            return JsonResponse({
                'table_html': table_html,
                'pagination_html': pagination_html,
                'totals_html': totals_html,
                'total_count': paginator.count
            })

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('القطاع العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('مستخلصات المقاولين'), 'active': True}
        ]

        header_buttons = []
        if request.user.has_perm('real_estate.add_contractorprogresscertificate') or request.user.is_superuser:
            header_buttons.append({
                'url': reverse('real_estate:contractor_create'),
                'label': _('مستخلص جديد'),
                'icon': 'fa-plus',
                'class': 'btn-primary'
            })

        context = {
            'page_obj': page_obj,
            'certificates': page_obj.object_list,
            'projects': RealEstateProject.objects.filter(is_archived=False).order_by('name'),
            'contractors': Supplier.objects.filter(is_active=True).order_by('name'),
            'contracts': ContractorContract.objects.filter(status=ContractorContract.ContractStatus.ACTIVE).order_by('-created_at', '-id'),
            'search_query': search_query,
            'selected_project': project_id,
            'selected_contractor': contractor_id,
            'selected_contract': contract_id,
            'selected_status': status_filter,
            'selected_type': type_filter,
            'status_choices': ContractorProgressCertificate.CertificateStatus.choices,
            'type_choices': ContractorProgressCertificate.CertificateType.choices,
            'total_certs': total_certs,
            'total_certified_gross': total_certified_gross,
            'total_retention': total_retention,
            'total_net_payable': total_net_payable,
            'breadcrumb_items': breadcrumb_items,
            'header_buttons': header_buttons,
            'active_menu': 're_engineering',
            'active_submenu': 'contractor_certificates',
        }
        return render(request, 'real_estate/contractor_list.html', context)


class ContractorCertificateDetailView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تفاصيل مستخلص المقاول، تفنيد الأعمال، الاستقطاعات، ومتابعة الاعتماد المالي
    """
    permission_required = 'real_estate.view_contractorprogresscertificate'

    def get(self, request, pk):
        cert = get_object_or_404(
            ContractorProgressCertificate.objects.select_related(
                'project', 'contractor', 'contract', 'currency', 'approval_request', 'journal_entry', 'created_by'
            ),
            pk=pk
        )

        items = cert.items.select_related('contract_item').order_by('id')
        mos_list = cert.mos_details.all()
        concrete_deliveries = cert.concrete_batches.all()
        backcharges = cert.backcharges.select_related('snag_item', 'beneficiary_contractor').order_by('-id')
        installments = cert.installment_schedules.select_related('pdc_cheque').order_by('installment_number')
        debris_logs = cert.debris_charges.all()
        hoisting_logs = cert.hoisting_charges.all()

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('القطاع العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('مستخلصات المقاولين'), 'url': reverse('real_estate:contractor_list'), 'icon': 'fa-hard-hat'},
            {'title': cert.certificate_number, 'active': True}
        ]

        header_buttons = [
            {
                'url': reverse('real_estate:contractor_print', kwargs={'pk': cert.pk}),
                'label': _('طباعة المستخلص الهندسي'),
                'icon': 'fa-print',
                'class': 'btn-outline-secondary'
            }
        ]

        if cert.status == ContractorProgressCertificate.CertificateStatus.DRAFT:
            if request.user.has_perm('real_estate.change_contractorprogresscertificate') or request.user.is_superuser:
                header_buttons.append({
                    'url': reverse('real_estate:contractor_update', kwargs={'pk': cert.pk}),
                    'label': _('تعديل المستخلص'),
                    'icon': 'fa-edit',
                    'class': 'btn-outline-primary'
                })

        context = {
            'cert': cert,
            'items': items,
            'mos_list': mos_list,
            'concrete_deliveries': concrete_deliveries,
            'backcharges': backcharges,
            'installments': installments,
            'debris_logs': debris_logs,
            'hoisting_logs': hoisting_logs,
            'breadcrumb_items': breadcrumb_items,
            'header_buttons': header_buttons,
            'active_menu': 're_engineering',
            'active_submenu': 'contractor_certificates',
            'import_form': CertificateExcelImportForm(),
            'storno_form': StornoReversalForm(),
            'cheque_form': InstallmentChequeSettlementForm(),
        }
        return render(request, 'real_estate/contractor_detail.html', context)


class ContractorCertificateCreateView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    إصدار مستخلص مقاول باطن إداري جديد مع إمكانية ربطه بعقد المقاولة
    """
    permission_required = 'real_estate.add_contractorprogresscertificate'

    def get(self, request):
        contract_id = request.GET.get('contract')
        initial_data = {}
        contract = None
        if contract_id:
            contract = get_object_or_404(ContractorContract, pk=contract_id)
            initial_data['contract'] = contract
            initial_data['project'] = contract.project
            initial_data['contractor'] = contract.contractor
            initial_data['currency'] = contract.currency
            initial_data['sequence_order'] = contract.certificates.count() + 1
            initial_data['certificate_number'] = f"CERT-{contract.contract_number}-{initial_data['sequence_order']:02d}"

        form = ContractorProgressCertificateForm(initial=initial_data)
        formset = ContractorCertificateItemFormSet()

        projects = RealEstateProject.objects.filter(is_archived=False).order_by('name')
        contractors = Supplier.objects.filter(is_active=True).order_by('name')
        contracts = ContractorContract.objects.filter(status=ContractorContract.ContractStatus.ACTIVE).order_by('-created_at', '-id')
        currencies = Currency.objects.all()

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('القطاع العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('مستخلصات المقاولين'), 'url': reverse('real_estate:contractor_list'), 'icon': 'fa-hard-hat'},
            {'title': _('إصدار مستخلص جديد'), 'active': True}
        ]

        context = {
            'form': form,
            'formset': formset,
            'selected_contract': contract,
            'projects': projects,
            'contractors': contractors,
            'contracts': contracts,
            'currencies': currencies,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_engineering',
            'active_submenu': 'contractor_certificates',
            'is_edit': False,
        }
        return render(request, 'real_estate/contractor_form.html', context)

    def post(self, request):
        form = ContractorProgressCertificateForm(request.POST)
        formset = ContractorCertificateItemFormSet(request.POST)

        cert_number = request.POST.get('certificate_number', '').strip().upper()
        project_id = request.POST.get('project')
        contractor_id = request.POST.get('contractor')
        contract_id = request.POST.get('contract')
        contract_reference = request.POST.get('contract_reference', '').strip()
        period_start = request.POST.get('period_start')
        period_end = request.POST.get('period_end')
        currency_id = request.POST.get('currency')

        gross_work = Decimal(str(request.POST.get('gross_certified_work', '0.00') or '0.00'))
        prev_work = Decimal(str(request.POST.get('previous_certified_work', '0.00') or '0.00'))
        materials = Decimal(str(request.POST.get('materials_on_site', '0.00') or '0.00'))

        retention_rate = Decimal(str(request.POST.get('retention_rate', '5.00') or '5.00'))
        advance_recovery = Decimal(str(request.POST.get('advance_payment_recovery', '0.00') or '0.00'))
        wht_rate = Decimal(str(request.POST.get('wht_rate', '1.00') or '1.00'))
        penalty_deductions = Decimal(str(request.POST.get('penalty_deductions', '0.00') or '0.00'))
        notes = request.POST.get('notes', '').strip()

        if not cert_number or not project_id or not contractor_id or not period_start or not period_end or not currency_id:
            messages.error(request, _('يرجى ملء جميع الحقول الإلزامية للمستخلص.'))
            return redirect('real_estate:contractor_create')

        if ContractorProgressCertificate.objects.filter(certificate_number=cert_number).exists():
            messages.error(request, _('رقم المستخلص مسجل مسبقاً، يرجى استخدام رقم فريد.'))
            return redirect('real_estate:contractor_create')

        project = get_object_or_404(RealEstateProject, pk=project_id)
        contractor = get_object_or_404(Supplier, pk=contractor_id)
        currency = get_object_or_404(Currency, pk=currency_id)
        contract = ContractorContract.objects.filter(pk=contract_id).first() if contract_id else None

        seq_order = int(request.POST.get('sequence_order', 1) or 1)
        if contract and not seq_order:
            seq_order = contract.certificates.count() + 1

        cert = ContractorProgressCertificate(
            certificate_number=cert_number,
            sequence_order=seq_order,
            certificate_type=request.POST.get('certificate_type', ContractorProgressCertificate.CertificateType.STANDARD_PROGRESS),
            contract=contract,
            project=project,
            contractor=contractor,
            contract_reference=contract_reference or (contract.contract_number if contract else ''),
            period_start=period_start,
            period_end=period_end,
            currency=currency,
            gross_certified_work=gross_work,
            previous_certified_work=prev_work,
            materials_on_site=materials,
            retention_rate=contract.retention_rate if contract else retention_rate,
            advance_payment_recovery=advance_recovery,
            wht_rate=wht_rate,
            penalty_deductions=penalty_deductions,
            notes=notes,
            created_by=request.user,
            status=ContractorProgressCertificate.CertificateStatus.DRAFT
        )

        try:
            with transaction.atomic():
                cert.clean()
                cert.save()

                if formset.is_valid():
                    formset.instance = cert
                    formset.save()
                    items_sum = sum(i.current_work_value for i in cert.items.all())
                    if items_sum > Decimal('0.00'):
                        cert.current_period_work = items_sum
                        cert.gross_certified_work = cert.previous_certified_work + items_sum
                        cert.compute_amounts()
                        cert.save()

            messages.success(request, _('تم إنشاء المستخلص رقم %(num)s بنجاح كمسودة.') % {'num': cert.certificate_number})
            return redirect('real_estate:contractor_detail', pk=cert.pk)
        except Exception as e:
            logger.error(f"Error creating certificate: {e}", exc_info=True)
            messages.error(request, str(e))
            return redirect('real_estate:contractor_create')


class ContractorCertificateUpdateView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تعديل مستخلص مقاول باطن في مرحلة المسودة (DRAFT)
    """
    permission_required = 'real_estate.change_contractorprogresscertificate'

    def get(self, request, pk):
        cert = get_object_or_404(ContractorProgressCertificate, pk=pk)
        if cert.status != ContractorProgressCertificate.CertificateStatus.DRAFT:
            messages.error(request, _('لا يمكن تعديل المستخلص بعد تقديمه للاعتماد أو ترحيله.'))
            return redirect('real_estate:contractor_detail', pk=cert.pk)

        form = ContractorProgressCertificateForm(instance=cert)
        formset = ContractorCertificateItemFormSet(instance=cert)

        projects = RealEstateProject.objects.filter(is_archived=False).order_by('name')
        contractors = Supplier.objects.filter(is_active=True).order_by('name')
        contracts = ContractorContract.objects.filter(status=ContractorContract.ContractStatus.ACTIVE).order_by('-created_at', '-id')
        currencies = Currency.objects.all()

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('القطاع العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('مستخلصات المقاولين'), 'url': reverse('real_estate:contractor_list'), 'icon': 'fa-hard-hat'},
            {'title': cert.certificate_number, 'url': reverse('real_estate:contractor_detail', kwargs={'pk': cert.pk})},
            {'title': _('تعديل المستخلص'), 'active': True}
        ]

        context = {
            'cert': cert,
            'form': form,
            'formset': formset,
            'projects': projects,
            'contractors': contractors,
            'contracts': contracts,
            'currencies': currencies,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_engineering',
            'active_submenu': 'contractor_certificates',
            'is_edit': True,
        }
        return render(request, 'real_estate/contractor_form.html', context)

    def post(self, request, pk):
        cert = get_object_or_404(ContractorProgressCertificate, pk=pk)
        if cert.status != ContractorProgressCertificate.CertificateStatus.DRAFT:
            messages.error(request, _('لا يمكن تعديل المستخلص بعد تقديمه للاعتماد.'))
            return redirect('real_estate:contractor_detail', pk=cert.pk)

        cert.contract_reference = request.POST.get('contract_reference', '').strip()
        cert.period_start = request.POST.get('period_start')
        cert.period_end = request.POST.get('period_end')
        currency_id = request.POST.get('currency')
        if currency_id:
            cert.currency = get_object_or_404(Currency, pk=currency_id)

        cert.gross_certified_work = Decimal(str(request.POST.get('gross_certified_work', '0.00') or '0.00'))
        cert.previous_certified_work = Decimal(str(request.POST.get('previous_certified_work', '0.00') or '0.00'))
        cert.materials_on_site = Decimal(str(request.POST.get('materials_on_site', '0.00') or '0.00'))

        cert.retention_rate = Decimal(str(request.POST.get('retention_rate', '5.00') or '5.00'))
        cert.advance_payment_recovery = Decimal(str(request.POST.get('advance_payment_recovery', '0.00') or '0.00'))
        cert.wht_rate = Decimal(str(request.POST.get('wht_rate', '1.00') or '1.00'))
        cert.penalty_deductions = Decimal(str(request.POST.get('penalty_deductions', '0.00') or '0.00'))
        cert.notes = request.POST.get('notes', '').strip()

        formset = ContractorCertificateItemFormSet(request.POST, instance=cert)

        try:
            with transaction.atomic():
                cert.clean()
                cert.save()

                if formset.is_valid():
                    formset.save()
                    items_sum = sum(i.current_work_value for i in cert.items.all())
                    if items_sum > Decimal('0.00'):
                        cert.current_period_work = items_sum
                        cert.gross_certified_work = cert.previous_certified_work + items_sum
                        cert.compute_amounts()
                        cert.save()

            messages.success(request, _('تم تحديث بيانات المستخلص بنجاح.'))
            return redirect('real_estate:contractor_detail', pk=cert.pk)
        except Exception as e:
            logger.error(f"Error updating certificate: {e}", exc_info=True)
            messages.error(request, str(e))
            return redirect('real_estate:contractor_update', pk=cert.pk)


class ContractorCertificateSubmitView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تقديم المستخلص لدورة الاعتمادات المؤسسية وتثبيت البصمة التشفيرية Merkle Hash
    """
    permission_required = 'real_estate.change_contractorprogresscertificate'

    def post(self, request, pk):
        cert = get_object_or_404(ContractorProgressCertificate, pk=pk)
        try:
            ContractorProgressService.submit_certificate_for_approval(cert, user=request.user)
            msg = _('تم تقديم المستخلص رقم %(num)s للاعتماد المالي وتثبيت بصمته الرقمية المشفرة بنجاح.') % {'num': cert.certificate_number}
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': msg})
            messages.success(request, msg)
        except (MissingApprovalRuleError, SequentialOrderError, FinalSettlementComplianceError) as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': str(e)}, status=400)
            messages.error(request, str(e))
        except Exception as e:
            logger.error(f"Error submitting certificate {cert.certificate_number}: {e}", exc_info=True)
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': str(e)}, status=400)
            messages.error(request, str(e))

        return redirect('real_estate:contractor_detail', pk=cert.pk)


class ContractorCertificatePostGLView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    اعتماد وصرف المستخلص وترحيل القيد المحاسبي للدفاتر العامة عبر AccountingGateway
    """
    permission_required = 'real_estate.change_contractorprogresscertificate'

    def post(self, request, pk):
        cert = get_object_or_404(ContractorProgressCertificate, pk=pk)
        try:
            entry = ContractorProgressService.verify_and_post_certificate(cert, user=request.user)
            msg = _('تم ترحيل قيد استحقاق المستخلص بنجاح برقم قيد: %(entry)s.') % {'entry': getattr(entry, 'number', str(entry.id))}
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': msg, 'entry_number': getattr(entry, 'number', str(entry.id))})
            messages.success(request, msg)
        except MutationTamperError as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': str(e)}, status=400)
            messages.error(request, str(e))
        except Exception as e:
            logger.error(f"Error posting certificate {cert.certificate_number}: {e}", exc_info=True)
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': str(e)}, status=400)
            messages.error(request, str(e))

        return redirect('real_estate:contractor_detail', pk=cert.pk)


class ContractorCertificateStornoReverseView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    إلغاء المستخلص المعتمد وتوليد القيد العكسي المعياري (Storno Reversal Workflow)
    """
    permission_required = 'real_estate.change_contractorprogresscertificate'

    def post(self, request, pk):
        cert = get_object_or_404(ContractorProgressCertificate, pk=pk)
        form = StornoReversalForm(request.POST)

        if form.is_valid():
            reason = form.cleaned_data['reversal_reason']
            try:
                rev_entry = ContractorProgressService.reverse_certificate(
                    certificate=cert,
                    reason=reason,
                    user=request.user
                )
                msg = _('تم إلغاء المستخلص %(cert)s بنجاح وإصدار القيد العكسي رقم %(entry)s مع رد الأرصدة للعقد.') % {
                    'cert': cert.certificate_number,
                    'entry': getattr(rev_entry, 'number', str(rev_entry.id))
                }
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': True, 'message': msg})
                messages.success(request, msg)
            except Exception as e:
                logger.error(f"Error reversing certificate {cert.certificate_number}: {e}", exc_info=True)
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'message': str(e)}, status=400)
                messages.error(request, str(e))
        else:
            err_msg = _("يرجى ذكر سبب الإلغاء والقيد العكسي بدقة.")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': err_msg}, status=400)
            messages.error(request, err_msg)

        return redirect('real_estate:contractor_detail', pk=cert.pk)


class ContractorCertificateRetentionReleaseView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    الإفراج عن تأمين حسن التنفيذ (استلام ابتدائي 50% أو استلام نهائي 50%)
    """
    permission_required = 'real_estate.change_contractorprogresscertificate'

    def post(self, request, contract_id):
        contract = get_object_or_404(ContractorContract, pk=contract_id)
        form = RetentionReleaseForm(request.POST)

        if form.is_valid():
            rel_type = form.cleaned_data['release_type']
            amount = form.cleaned_data['amount']
            defect_deductions = form.cleaned_data['defect_deductions'] or Decimal('0.00')
            try:
                entry = ContractorProgressService.release_retention_guarantee(
                    contract=contract,
                    release_type=rel_type,
                    amount=amount,
                    defect_deductions=defect_deductions,
                    user=request.user
                )
                msg = _('تم الإفراج عن مبلغ %(amt)s من تأمين حسن التنفيذ وتوليد القيد رقم %(entry)s بنجاح.') % {
                    'amt': f"{amount:,.2f}",
                    'entry': getattr(entry, 'number', str(entry.id))
                }
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': True, 'message': msg})
                messages.success(request, msg)
            except Exception as e:
                logger.error(f"Error releasing retention for contract {contract.contract_number}: {e}", exc_info=True)
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'message': str(e)}, status=400)
                messages.error(request, str(e))
        else:
            err_msg = _("يرجى استيفاء بيانات الإفراج عن التأمين.")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': err_msg}, status=400)
            messages.error(request, err_msg)

        return redirect('real_estate:contractor_contract_detail', pk=contract.pk)


class ContractorCertificateSettleInstallmentView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    سداد دفعة مجدولة من المستخلص بشيك بنكي آجل (PDC Cheque)
    """
    permission_required = 'real_estate.change_contractorprogresscertificate'

    def post(self, request, installment_id):
        installment = get_object_or_404(CertificatePaymentInstallmentSchedule, pk=installment_id)
        cheque_id = request.POST.get('cheque')
        cheque = get_object_or_404(Cheque, pk=cheque_id)

        try:
            entry = ContractorProgressService.settle_installment_with_cheque(
                installment=installment,
                cheque=cheque,
                user=request.user
            )
            msg = _('تم سداد الدفعة رقم %(num)s بشيك بنكي رقم %(chk)s وتوليد القيد رقم %(entry)s بنجاح.') % {
                'num': installment.installment_number,
                'chk': getattr(cheque, 'cheque_number', str(cheque.id)),
                'entry': getattr(entry, 'number', str(entry.id))
            }
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': msg})
            messages.success(request, msg)
        except Exception as e:
            logger.error(f"Error settling installment {installment.id}: {e}", exc_info=True)
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': str(e)}, status=400)
            messages.error(request, str(e))

        return redirect('real_estate:contractor_detail', pk=installment.certificate.pk)


class ContractorCertificateExcelImportView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    استيراد شيت حصر بنود المستخلص من ملف Excel أو CSV
    """
    permission_required = 'real_estate.change_contractorprogresscertificate'

    def post(self, request, pk):
        cert = get_object_or_404(ContractorProgressCertificate, pk=pk)
        if cert.status != ContractorProgressCertificate.CertificateStatus.DRAFT:
            messages.error(request, _('لا يمكن استيراد بنود لمستخلص معتمد أو قيد المراجعة.'))
            return redirect('real_estate:contractor_detail', pk=cert.pk)

        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            messages.error(request, _('يرجى اختيار ملف الحصر الهندسي.'))
            return redirect('real_estate:contractor_detail', pk=cert.pk)

        filename = uploaded_file.name.lower()
        replace_items = request.POST.get('replace_existing_items') == 'on'

        imported_count = 0
        try:
            with transaction.atomic():
                if replace_items:
                    cert.items.all().delete()

                if filename.endswith('.csv'):
                    decoded_file = uploaded_file.read().decode('utf-8-sig', errors='ignore')
                    reader = csv.DictReader(io.StringIO(decoded_file))
                    for row in reader:
                        item_code = row.get('item_code') or row.get('كود البند') or row.get('code', '')
                        if not item_code:
                            continue
                        desc = row.get('description') or row.get('الوصف') or row.get('توصيف البند', '')
                        unit = row.get('unit') or row.get('الوحدة', 'م2')
                        rate = Decimal(str(row.get('unit_rate') or row.get('الفئة', '0.00') or '0.00'))
                        curr_qty = Decimal(str(row.get('current_quantity') or row.get('الكمية الحالية', '0.00') or '0.00'))
                        prev_qty = Decimal(str(row.get('previous_quantity') or row.get('الكمية السابقة', '0.00') or '0.00'))

                        ContractorCertificateItem.objects.create(
                            certificate=cert,
                            item_code=item_code.strip(),
                            description=desc.strip(),
                            unit=unit.strip(),
                            unit_rate=rate,
                            previous_quantity=prev_qty,
                            current_quantity=curr_qty,
                        )
                        imported_count += 1
                else:
                    import openpyxl
                    wb = openpyxl.load_workbook(uploaded_file, data_only=True)
                    ws = wb.active
                    headers = [str(cell.value or '').strip().lower() for cell in next(ws.iter_rows(max_row=1))]
                    for row_cells in ws.iter_rows(min_row=2, values_only=True):
                        if not any(row_cells):
                            continue
                        row_dict = dict(zip(headers, row_cells))
                        item_code = str(row_dict.get('item_code') or row_dict.get('كود البند') or row_dict.get('code') or '').strip()
                        if not item_code:
                            continue
                        desc = str(row_dict.get('description') or row_dict.get('الوصف') or row_dict.get('توصيف البند') or '').strip()
                        unit = str(row_dict.get('unit') or row_dict.get('الوحدة') or 'م2').strip()
                        rate = Decimal(str(row_dict.get('unit_rate') or row_dict.get('الفئة') or '0.00'))
                        curr_qty = Decimal(str(row_dict.get('current_quantity') or row_dict.get('الكمية الحالية') or '0.00'))
                        prev_qty = Decimal(str(row_dict.get('previous_quantity') or row_dict.get('الكمية السابقة') or '0.00'))

                        ContractorCertificateItem.objects.create(
                            certificate=cert,
                            item_code=item_code,
                            description=desc,
                            unit=unit,
                            unit_rate=rate,
                            previous_quantity=prev_qty,
                            current_quantity=curr_qty,
                        )
                        imported_count += 1

                # إعادة حساب إجمالي الأعمال بالفترة
                items_sum = sum(i.current_work_value for i in cert.items.all())
                cert.current_period_work = items_sum
                cert.gross_certified_work = cert.previous_certified_work + items_sum
                cert.compute_amounts()
                cert.save()

            messages.success(request, _('تم استيراد %(count)d بند من ملف الحصر الهندسي بنجاح.') % {'count': imported_count})
        except Exception as e:
            logger.error(f"Error importing certificate items from file: {e}", exc_info=True)
            messages.error(request, _('حدث خطأ أثناء استيراد الملف: %(err)s') % {'err': str(e)})

        return redirect('real_estate:contractor_detail', pk=cert.pk)


class ContractorCertificatePrintView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    قالب الطباعة الهندسي المعتمد للمستخلص بالتوقيعات الرباعية الرسمية
    """
    permission_required = 'real_estate.view_contractorprogresscertificate'

    def get(self, request, pk):
        cert = get_object_or_404(
            ContractorProgressCertificate.objects.select_related(
                'project', 'contractor', 'contract', 'currency', 'created_by'
            ),
            pk=pk
        )
        items = cert.items.select_related('contract_item').order_by('id')
        mos_list = cert.mos_details.all()
        backcharges = cert.backcharges.select_related('snag_item', 'beneficiary_contractor').order_by('-id')

        context = {
            'cert': cert,
            'items': items,
            'mos_list': mos_list,
            'backcharges': backcharges,
            'company_name': _("شركة موهبة للاستثمار العقاري والمقاولات"),
            'print_date': timezone.now(),
        }
        return render(request, 'real_estate/contractor_certificate_print.html', context)
