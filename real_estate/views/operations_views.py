# -*- coding: utf-8 -*-
from decimal import Decimal
from django.shortcuts import render, get_object_or_404
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.core.paginator import Paginator
from django.db.models import Q, Sum

from users.mixins import SmartPermissionRequiredMixin
from real_estate.models import MaintenanceFundOperation, LegalNotice, LandownerPartnership, UnitSwapRecord


class MaintenanceFundListView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    سجل عمليات وصندوق وديعة صيانة المرافق
    """
    permission_required = 'real_estate.view_maintenancefundoperation'

    def get(self, request):
        search_query = request.GET.get('q', '').strip()
        type_filter = request.GET.get('type', '').strip()

        qs = MaintenanceFundOperation.objects.select_related('subledger__block__project').order_by('-transaction_date', '-id')

        if search_query:
            qs = qs.filter(
                Q(reference_document__icontains=search_query) |
                Q(description__icontains=search_query) |
                Q(subledger__block__project__name__icontains=search_query)
            )

        if type_filter:
            qs = qs.filter(operation_type=type_filter)

        paginator = Paginator(qs, 20)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        total_operations = MaintenanceFundOperation.objects.count()
        total_amount = MaintenanceFundOperation.objects.aggregate(s=Sum('amount'))['s'] or Decimal('0.00')

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('خدمة العملاء والتسليمات'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-key'},
            {'title': _('صندوق وديعة الصيانة'), 'active': True}
        ]

        context = {
            'page_obj': page_obj,
            'operations': page_obj.object_list,
            'search_query': search_query,
            'selected_type': type_filter,
            'type_choices': MaintenanceFundOperation.OperationType.choices,
            'total_operations': total_operations,
            'total_amount': total_amount,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_service',
            'active_submenu': 'maintenance_fund',
        }
        return render(request, 'real_estate/maintenance_fund_list.html', context)


class LegalNoticeListView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    سجل الإنذارات والمتابعة القانونية للمتعثرين
    """
    permission_required = 'real_estate.view_legalnotice'

    def get(self, request):
        search_query = request.GET.get('q', '').strip()
        status_filter = request.GET.get('status', '').strip()
        stage_filter = request.GET.get('stage', '').strip()

        qs = LegalNotice.objects.select_related('contract__customer', 'contract__unit__project').order_by('-sent_at')

        if search_query:
            qs = qs.filter(
                Q(notice_number__icontains=search_query) |
                Q(customer__name__icontains=search_query) |
                Q(contract__contract_number__icontains=search_query)
            )

        if status_filter:
            qs = qs.filter(status=status_filter)

        if stage_filter:
            qs = qs.filter(stage=stage_filter)

        paginator = Paginator(qs, 20)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        total_notices = LegalNotice.objects.count()
        total_demanded = LegalNotice.objects.aggregate(s=Sum('total_demanded_amount'))['s'] or Decimal('0.00')

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('خدمة العملاء والتسليمات'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-key'},
            {'title': _('الإنذارات القانونية'), 'active': True}
        ]

        context = {
            'page_obj': page_obj,
            'notices': page_obj.object_list,
            'search_query': search_query,
            'selected_status': status_filter,
            'selected_stage': stage_filter,
            'status_choices': LegalNotice.NoticeStatus.choices,
            'stage_choices': LegalNotice.EscalationStage.choices,
            'total_notices': total_notices,
            'total_demanded': total_demanded,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_service',
            'active_submenu': 'legal_notices',
        }
        return render(request, 'real_estate/legal_notice_list.html', context)


class LandownerPartnershipListView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    سجل الشركاء وملاك الأراضي ونسب التطوير العقاري
    """
    permission_required = 'real_estate.view_landownerpartnership'

    def get(self, request):
        search_query = request.GET.get('q', '').strip()
        status_filter = request.GET.get('status', '').strip()

        qs = LandownerPartnership.objects.select_related('project', 'partner').order_by('-partnership_start_date')

        if search_query:
            qs = qs.filter(
                Q(project__name__icontains=search_query) |
                Q(partner__name__icontains=search_query)
            )

        if status_filter:
            qs = qs.filter(status=status_filter)

        paginator = Paginator(qs, 20)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        total_partnerships = LandownerPartnership.objects.count()

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('المشروعات العقارية'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('الشركاء وملاك الأراضي'), 'active': True}
        ]

        context = {
            'page_obj': page_obj,
            'partnerships': page_obj.object_list,
            'search_query': search_query,
            'selected_status': status_filter,
            'status_choices': LandownerPartnership.PartnershipStatus.choices,
            'total_partnerships': total_partnerships,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_projects',
            'active_submenu': 'partnerships',
        }
        return render(request, 'real_estate/partnership_list.html', context)


class UnitSwapListView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    سجل تبديل الوحدات والتنازلات وإعادة البيع
    """
    permission_required = 'real_estate.view_unitswaprecord'

    def get(self, request):
        search_query = request.GET.get('q', '').strip()
        status_filter = request.GET.get('status', '').strip()

        qs = UnitSwapRecord.objects.select_related('source_contract__customer', 'source_unit', 'target_unit').order_by('-swap_date')

        if search_query:
            qs = qs.filter(
                Q(swap_number__icontains=search_query) |
                Q(source_contract__customer__name__icontains=search_query) |
                Q(source_unit__unit_code__icontains=search_query) |
                Q(target_unit__unit_code__icontains=search_query)
            )

        if status_filter:
            qs = qs.filter(status=status_filter)

        paginator = Paginator(qs, 20)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        total_swaps = UnitSwapRecord.objects.count()

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('المبيعات والحجوزات'), 'url': reverse('real_estate:contract_list'), 'icon': 'fa-file-signature'},
            {'title': _('تبديل الوحدات والتنازلات'), 'active': True}
        ]

        context = {
            'page_obj': page_obj,
            'swaps': page_obj.object_list,
            'search_query': search_query,
            'selected_status': status_filter,
            'status_choices': UnitSwapRecord.SwapStatus.choices,
            'total_swaps': total_swaps,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_sales',
            'active_submenu': 'unit_swaps',
        }
        return render(request, 'real_estate/swap_list.html', context)
