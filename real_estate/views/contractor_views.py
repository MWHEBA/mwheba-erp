# -*- coding: utf-8 -*-
from decimal import Decimal
from django.shortcuts import render, get_object_or_404
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.core.paginator import Paginator
from django.db.models import Q, Sum

from users.mixins import SmartPermissionRequiredMixin
from real_estate.models import ContractorProgressCertificate, RealEstateProject
from supplier.models import Supplier


class ContractorCertificateListView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    قائمة مستخلصات المقاولين الإنشائية ومقاولي الباطن
    """
    permission_required = 'real_estate.view_contractorprogresscertificate'

    def get(self, request):
        search_query = request.GET.get('q', '').strip()
        project_id = request.GET.get('project', '').strip()
        status_filter = request.GET.get('status', '').strip()

        qs = ContractorProgressCertificate.objects.select_related('project', 'contractor').order_by('-period_end', '-id')

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
        total_net_payable = ContractorProgressCertificate.objects.filter(status=ContractorProgressCertificate.CertificateStatus.APPROVED).aggregate(s=Sum('net_amount'))['s'] or Decimal('0.00')

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('المشروعات العقارية'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('مستخلصات المقاولين'), 'active': True}
        ]

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
            'active_menu': 're_engineering',
            'active_submenu': 'contractor_certificates',
        }
        return render(request, 'real_estate/contractor_list.html', context)
