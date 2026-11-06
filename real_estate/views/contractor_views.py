# -*- coding: utf-8 -*-
from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.core.paginator import Paginator
from django.contrib import messages
from django.db.models import Q, Sum

from users.mixins import SmartPermissionRequiredMixin
from real_estate.models import ContractorProgressCertificate, RealEstateProject
from real_estate.services.contractor_service import ContractorProgressService, MissingApprovalRuleError, MutationTamperError
from supplier.models import Supplier
from financial.models.currency import Currency


class ContractorCertificateListView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    قائمة مستخلصات المقاولين الإنشائية ومقاولي الباطن
    """
    permission_required = 'real_estate.view_contractorprogresscertificate'

    def get(self, request):
        search_query = request.GET.get('q', '').strip()
        project_id = request.GET.get('project', '').strip()
        status_filter = request.GET.get('status', '').strip()

        qs = ContractorProgressCertificate.objects.select_related(
            'project', 'contractor', 'currency'
        ).order_by('-period_end', '-id')

        if search_query:
            qs = qs.filter(
                Q(certificate_number__icontains=search_query) |
                Q(contractor__name__icontains=search_query) |
                Q(project__name__icontains=search_query) |
                Q(contract_reference__icontains=search_query)
            )

        if project_id:
            qs = qs.filter(project_id=project_id)

        if status_filter:
            qs = qs.filter(status=status_filter)

        paginator = Paginator(qs, 15)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        total_certs = ContractorProgressCertificate.objects.count()
        total_certified_gross = ContractorProgressCertificate.objects.aggregate(s=Sum('gross_certified_work'))['s'] or Decimal('0.00')
        total_retention = ContractorProgressCertificate.objects.aggregate(s=Sum('retention_amount'))['s'] or Decimal('0.00')
        total_net_payable = ContractorProgressCertificate.objects.filter(
            status=ContractorProgressCertificate.CertificateStatus.APPROVED
        ).aggregate(s=Sum('net_amount'))['s'] or Decimal('0.00')

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
            'search_query': search_query,
            'selected_project': project_id,
            'selected_status': status_filter,
            'status_choices': ContractorProgressCertificate.CertificateStatus.choices,
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
                'project', 'contractor', 'currency', 'approval_request', 'journal_entry', 'created_by'
            ),
            pk=pk
        )

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('القطاع العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('مستخلصات المقاولين'), 'url': reverse('real_estate:contractor_list'), 'icon': 'fa-hard-hat'},
            {'title': cert.certificate_number, 'active': True}
        ]

        header_buttons = []
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
            'breadcrumb_items': breadcrumb_items,
            'header_buttons': header_buttons,
            'active_menu': 're_engineering',
            'active_submenu': 'contractor_certificates',
        }
        return render(request, 'real_estate/contractor_detail.html', context)


class ContractorCertificateCreateView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    إصدار مستخلص مقاول باطن إداري جديد
    """
    permission_required = 'real_estate.add_contractorprogresscertificate'

    def get(self, request):
        projects = RealEstateProject.objects.filter(is_archived=False).order_by('name')
        contractors = Supplier.objects.filter(is_active=True).order_by('name')
        currencies = Currency.objects.all()

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('القطاع العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('مستخلصات المقاولين'), 'url': reverse('real_estate:contractor_list'), 'icon': 'fa-hard-hat'},
            {'title': _('إصدار مستخلص جديد'), 'active': True}
        ]

        context = {
            'projects': projects,
            'contractors': contractors,
            'currencies': currencies,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_engineering',
            'active_submenu': 'contractor_certificates',
            'is_edit': False,
        }
        return render(request, 'real_estate/contractor_form.html', context)

    def post(self, request):
        cert_number = request.POST.get('certificate_number', '').strip().upper()
        project_id = request.POST.get('project')
        contractor_id = request.POST.get('contractor')
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

        cert = ContractorProgressCertificate(
            certificate_number=cert_number,
            project=project,
            contractor=contractor,
            contract_reference=contract_reference,
            period_start=period_start,
            period_end=period_end,
            currency=currency,
            gross_certified_work=gross_work,
            previous_certified_work=prev_work,
            materials_on_site=materials,
            retention_rate=retention_rate,
            advance_payment_recovery=advance_recovery,
            wht_rate=wht_rate,
            penalty_deductions=penalty_deductions,
            notes=notes,
            created_by=request.user,
            status=ContractorProgressCertificate.CertificateStatus.DRAFT
        )

        try:
            cert.clean()
            cert.save()
            messages.success(request, _('تم إنشاء المستخلص رقم %(num)s بنجاح كمسودة.') % {'num': cert.certificate_number})
            return redirect('real_estate:contractor_detail', pk=cert.pk)
        except Exception as e:
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

        projects = RealEstateProject.objects.filter(is_archived=False).order_by('name')
        contractors = Supplier.objects.filter(is_active=True).order_by('name')
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
            'projects': projects,
            'contractors': contractors,
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

        try:
            cert.clean()
            cert.save()
            messages.success(request, _('تم تحديث بيانات المستخلص بنجاح.'))
            return redirect('real_estate:contractor_detail', pk=cert.pk)
        except Exception as e:
            messages.error(request, str(e))
            return redirect('real_estate:contractor_update', pk=cert.pk)


class ContractorCertificateSubmitView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تقديم المستخلص لدورة الاعتمادات المؤسسية
    """
    permission_required = 'real_estate.change_contractorprogresscertificate'

    def post(self, request, pk):
        cert = get_object_or_404(ContractorProgressCertificate, pk=pk)
        try:
            ContractorProgressService.submit_certificate_for_approval(cert, user=request.user)
            messages.success(request, _('تم تقديم المستخلص رقم %(num)s للاعتماد المالي بنجاح.') % {'num': cert.certificate_number})
        except MissingApprovalRuleError as e:
            messages.error(request, str(e))
        except Exception as e:
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
            messages.success(request, _('تم ترحيل قيد استحقاق المستخلص بنجاح برقم قيد: %(entry)s.') % {'entry': entry.entry_number})
        except MutationTamperError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, str(e))
        return redirect('real_estate:contractor_detail', pk=cert.pk)
