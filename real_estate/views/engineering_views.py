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
from real_estate.models import ClientVariationOrder, UnitSnagItem


class VariationOrderListView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    أوامر التعديلات المعمارية والتشطيبية للعملاء
    """
    permission_required = 'real_estate.view_clientvariationorder'

    def get(self, request):
        search_query = request.GET.get('q', '').strip()
        status_filter = request.GET.get('status', '').strip()
        type_filter = request.GET.get('type', '').strip()

        qs = ClientVariationOrder.objects.select_related('contract__customer', 'contract__unit__project').order_by('-created_at')

        if search_query:
            qs = qs.filter(
                Q(order_number__icontains=search_query) |
                Q(contract__customer__name__icontains=search_query) |
                Q(contract__unit__unit_code__icontains=search_query)
            )

        if status_filter:
            qs = qs.filter(status=status_filter)

        if type_filter:
            qs = qs.filter(variation_type=type_filter)

        paginator = Paginator(qs, 20)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        total_orders = ClientVariationOrder.objects.count()
        total_cost = ClientVariationOrder.objects.aggregate(s=Sum('total_customer_price'))['s'] or Decimal('0.00')
        approved_count = ClientVariationOrder.objects.filter(status=ClientVariationOrder.OrderStatus.APPROVED).count()

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('الإدارة الهندسية'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-hard-hat'},
            {'title': _('أوامر تعديلات العملاء'), 'active': True}
        ]

        context = {
            'page_obj': page_obj,
            'orders': page_obj.object_list,
            'search_query': search_query,
            'selected_status': status_filter,
            'selected_type': type_filter,
            'status_choices': ClientVariationOrder.OrderStatus.choices,
            'type_choices': ClientVariationOrder.VariationType.choices,
            'total_orders': total_orders,
            'total_cost': total_cost,
            'approved_count': approved_count,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_engineering',
            'active_submenu': 'variation_orders',
        }
        return render(request, 'real_estate/variation_list.html', context)


class SnagItemListView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    قوائم وبنود فحص الموقع وملاحظات الاستلام الميدانية
    """
    permission_required = 'real_estate.view_unitsnagitem'

    def get(self, request):
        search_query = request.GET.get('q', '').strip()
        status_filter = request.GET.get('status', '').strip()
        severity_filter = request.GET.get('severity', '').strip()

        qs = UnitSnagItem.objects.select_related('unit__project', 'reported_by').order_by('-reported_at')

        if search_query:
            qs = qs.filter(
                Q(title__icontains=search_query) |
                Q(unit__unit_code__icontains=search_query) |
                Q(description__icontains=search_query)
            )

        if status_filter:
            qs = qs.filter(status=status_filter)

        if severity_filter:
            qs = qs.filter(severity=severity_filter)

        paginator = Paginator(qs, 20)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        total_snags = UnitSnagItem.objects.count()
        open_snags = UnitSnagItem.objects.filter(status__in=[UnitSnagItem.SnagStatus.REPORTED, UnitSnagItem.SnagStatus.IN_PROGRESS]).count()
        rectified_snags = UnitSnagItem.objects.filter(status=UnitSnagItem.SnagStatus.RECTIFIED).count()

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('الإدارة الهندسية'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-hard-hat'},
            {'title': _('بنود الفحص والملاحظات'), 'active': True}
        ]

        context = {
            'page_obj': page_obj,
            'snags': page_obj.object_list,
            'search_query': search_query,
            'selected_status': status_filter,
            'selected_severity': severity_filter,
            'status_choices': UnitSnagItem.SnagStatus.choices,
            'severity_choices': UnitSnagItem.SnagSeverity.choices,
            'total_snags': total_snags,
            'open_snags': open_snags,
            'rectified_snags': rectified_snags,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_engineering',
            'active_submenu': 'snag_items',
        }
        return render(request, 'real_estate/snag_list.html', context)
