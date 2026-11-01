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
from real_estate.models import RealEstateBroker, BrokerCommission


class BrokerListView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    سجل ودليل شركات الوساطة والمسوقين العقاريين
    """
    permission_required = 'real_estate.view_realestatebroker'

    def get(self, request):
        search_query = request.GET.get('q', '').strip()
        type_filter = request.GET.get('type', '').strip()

        qs = RealEstateBroker.objects.filter(is_active=True).order_by('name')

        if search_query:
            qs = qs.filter(
                Q(code__icontains=search_query) |
                Q(name__icontains=search_query) |
                Q(phone__icontains=search_query) |
                Q(contact_person__icontains=search_query)
            )

        if type_filter:
            qs = qs.filter(broker_type=type_filter)

        paginator = Paginator(qs, 20)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        total_brokers = RealEstateBroker.objects.filter(is_active=True).count()
        total_commissions = BrokerCommission.objects.aggregate(s=Sum('total_commission_amount'))['s'] or Decimal('0.00')
        released_commissions = BrokerCommission.objects.aggregate(s=Sum('released_commission_amount'))['s'] or Decimal('0.00')

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('المبيعات والحجوزات'), 'url': reverse('real_estate:contract_list'), 'icon': 'fa-file-signature'},
            {'title': _('الوسطاء والمسوقين'), 'active': True}
        ]

        context = {
            'page_obj': page_obj,
            'brokers': page_obj.object_list,
            'search_query': search_query,
            'selected_type': type_filter,
            'type_choices': RealEstateBroker.BrokerType.choices,
            'total_brokers': total_brokers,
            'total_commissions': total_commissions,
            'released_commissions': released_commissions,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_sales',
            'active_submenu': 'brokers',
        }
        return render(request, 'real_estate/broker_list.html', context)


class BrokerCommissionListView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    بيان عمولات البيع والحجوزات العقارية
    """
    permission_required = 'real_estate.view_brokercommission'

    def get(self, request):
        search_query = request.GET.get('q', '').strip()
        status_filter = request.GET.get('status', '').strip()

        qs = BrokerCommission.objects.select_related('broker', 'contract__customer', 'contract__unit').order_by('-created_at')

        if search_query:
            qs = qs.filter(
                Q(broker__name__icontains=search_query) |
                Q(contract__contract_number__icontains=search_query) |
                Q(contract__customer__name__icontains=search_query)
            )

        if status_filter:
            qs = qs.filter(status=status_filter)

        paginator = Paginator(qs, 20)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        total_records = BrokerCommission.objects.count()
        total_amount = BrokerCommission.objects.aggregate(s=Sum('total_commission_amount'))['s'] or Decimal('0.00')
        released_amount = BrokerCommission.objects.aggregate(s=Sum('released_commission_amount'))['s'] or Decimal('0.00')

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('المبيعات والحجوزات'), 'url': reverse('real_estate:contract_list'), 'icon': 'fa-file-signature'},
            {'title': _('عمولات البيع والتسويق'), 'active': True}
        ]

        context = {
            'page_obj': page_obj,
            'commissions': page_obj.object_list,
            'search_query': search_query,
            'selected_status': status_filter,
            'status_choices': BrokerCommission.CommissionStatus.choices,
            'total_records': total_records,
            'total_amount': total_amount,
            'released_amount': released_amount,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_sales',
            'active_submenu': 'commissions',
        }
        return render(request, 'real_estate/commission_list.html', context)
