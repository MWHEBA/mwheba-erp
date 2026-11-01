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
from real_estate.models import PropertyHandoverReceipt, WarrantyTicket


class HandoverReceiptListView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    محاضر استلام وتسليم الوحدات العقارية الرسمية
    """
    permission_required = 'real_estate.view_propertyhandoverreceipt'

    def get(self, request):
        search_query = request.GET.get('q', '').strip()
        status_filter = request.GET.get('status', '').strip()
        type_filter = request.GET.get('type', '').strip()

        qs = PropertyHandoverReceipt.objects.select_related('contract__customer', 'contract__unit__project').order_by('-handover_date', '-id')

        if search_query:
            qs = qs.filter(
                Q(receipt_number__icontains=search_query) |
                Q(contract__customer__name__icontains=search_query) |
                Q(contract__unit__unit_code__icontains=search_query)
            )

        if status_filter:
            qs = qs.filter(status=status_filter)

        if type_filter:
            qs = qs.filter(handover_type=type_filter)

        paginator = Paginator(qs, 20)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        total_handovers = PropertyHandoverReceipt.objects.count()
        executed_count = PropertyHandoverReceipt.objects.filter(status=PropertyHandoverReceipt.HandoverStatus.EXECUTED).count()
        pending_count = PropertyHandoverReceipt.objects.filter(status=PropertyHandoverReceipt.HandoverStatus.PENDING_INSPECTION).count()

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('خدمة العملاء والتسليمات'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-key'},
            {'title': _('محاضر تسليم الوحدات'), 'active': True}
        ]

        context = {
            'page_obj': page_obj,
            'receipts': page_obj.object_list,
            'search_query': search_query,
            'selected_status': status_filter,
            'selected_type': type_filter,
            'status_choices': PropertyHandoverReceipt.HandoverStatus.choices,
            'type_choices': PropertyHandoverReceipt.HandoverType.choices,
            'total_handovers': total_handovers,
            'executed_count': executed_count,
            'pending_count': pending_count,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_service',
            'active_submenu': 'handovers',
        }
        return render(request, 'real_estate/handover_list.html', context)


class WarrantyTicketListView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تذاكر الضمان وخدمات الصيانة بعد التسليم
    """
    permission_required = 'real_estate.view_warrantyticket'

    def get(self, request):
        search_query = request.GET.get('q', '').strip()
        status_filter = request.GET.get('status', '').strip()
        priority_filter = request.GET.get('priority', '').strip()

        qs = WarrantyTicket.objects.select_related('unit__project', 'customer', 'responsible_contractor').order_by('-reported_at')

        if search_query:
            qs = qs.filter(
                Q(ticket_number__icontains=search_query) |
                Q(unit__unit_code__icontains=search_query) |
                Q(customer__name__icontains=search_query) |
                Q(title__icontains=search_query)
            )

        if status_filter:
            qs = qs.filter(status=status_filter)

        if priority_filter:
            qs = qs.filter(priority=priority_filter)

        paginator = Paginator(qs, 20)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        total_tickets = WarrantyTicket.objects.count()
        open_tickets = WarrantyTicket.objects.filter(status__in=[WarrantyTicket.TicketStatus.REPORTED, WarrantyTicket.TicketStatus.INSPECTED, WarrantyTicket.TicketStatus.IN_REPAIR]).count()
        closed_tickets = WarrantyTicket.objects.filter(status=WarrantyTicket.TicketStatus.CLOSED).count()

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('خدمة العملاء والتسليمات'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-key'},
            {'title': _('تذاكر الضمان والصيانة'), 'active': True}
        ]

        context = {
            'page_obj': page_obj,
            'tickets': page_obj.object_list,
            'search_query': search_query,
            'selected_status': status_filter,
            'selected_priority': priority_filter,
            'status_choices': WarrantyTicket.TicketStatus.choices,
            'priority_choices': WarrantyTicket.TicketPriority.choices,
            'total_tickets': total_tickets,
            'open_tickets': open_tickets,
            'closed_tickets': closed_tickets,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_service',
            'active_submenu': 'warranties',
        }
        return render(request, 'real_estate/warranty_list.html', context)
