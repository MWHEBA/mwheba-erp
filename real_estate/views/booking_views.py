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
from django.db.models import Q, Sum

from users.mixins import SmartPermissionRequiredMixin
from real_estate.models import UnitBooking, RealEstateProject
from customer.models import Customer
from financial.models.chart_of_accounts import ChartOfAccounts


class BookingListView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    قائمة استمارات الحجز وأمانات جدية الحجز
    """
    permission_required = 'real_estate.view_unitbooking'

    def get(self, request):
        search_query = request.GET.get('q', '').strip()
        status_filter = request.GET.get('status', '').strip()
        project_id = request.GET.get('project', '').strip()

        bookings_qs = UnitBooking.objects.select_related('customer', 'unit__project').order_by('-booking_date', '-id')

        if search_query:
            bookings_qs = bookings_qs.filter(
                Q(booking_number__icontains=search_query) |
                Q(customer__name__icontains=search_query) |
                Q(unit__unit_code__icontains=search_query)
            )

        if status_filter:
            bookings_qs = bookings_qs.filter(status=status_filter)

        if project_id:
            bookings_qs = bookings_qs.filter(unit__project_id=project_id)

        paginator = Paginator(bookings_qs, 15)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.GET.get('ajax') == '1':
            table_html = render_to_string(
                'real_estate/partials/booking_table.html',
                {'page_obj': page_obj, 'bookings': page_obj.object_list},
                request=request
            )
            pagination_html = render_to_string(
                'partials/pagination.html',
                {'page_obj': page_obj},
                request=request
            )
            return JsonResponse({
                'success': True,
                'table_html': table_html,
                'pagination_html': pagination_html,
                'total_count': paginator.count
            })

        total_bookings = UnitBooking.objects.count()
        active_count = UnitBooking.objects.filter(status=UnitBooking.BookingStatus.ACTIVE).count()
        pending_refund_count = UnitBooking.objects.filter(status=UnitBooking.BookingStatus.CANCELLED_PENDING_REFUND).count()
        total_holding_deposits = UnitBooking.objects.filter(status=UnitBooking.BookingStatus.ACTIVE).aggregate(s=Sum('holding_deposit'))['s'] or Decimal('0.00')

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('القطاع العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('استمارات الحجز والأمانات'), 'active': True}
        ]

        context = {
            'page_obj': page_obj,
            'bookings': page_obj.object_list,
            'projects': RealEstateProject.objects.filter(is_archived=False),
            'total_bookings': total_bookings,
            'active_count': active_count,
            'pending_refund_count': pending_refund_count,
            'total_holding_deposits': total_holding_deposits,
            'status_choices': UnitBooking.BookingStatus.choices,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 'real_estate',
            'active_submenu': 'bookings',
        }
        return render(request, 'real_estate/booking_list.html', context)


class BookingDetailView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تفاصيل استمارة الحجز وسند التحصيل وقيد الأمانات
    """
    permission_required = 'real_estate.view_unitbooking'

    def get(self, request, pk):
        booking = get_object_or_404(
            UnitBooking.objects.select_related('customer', 'unit__project', 'journal_entry', 'created_by'),
            pk=pk
        )
        payment_accounts = ChartOfAccounts.objects.filter(is_active=True, is_leaf=True)

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('القطاع العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('الحجوزات'), 'url': reverse('real_estate:booking_list'), 'icon': 'fa-bookmark'},
            {'title': booking.booking_number, 'active': True}
        ]

        header_buttons = [
            {
                'url': reverse('real_estate:booking_print', kwargs={'pk': booking.pk}),
                'icon': 'fa-print',
                'text': _('طباعة استمارة الحجز'),
                'class': 'btn-outline-primary',
                'target': '_blank',
            }
        ]

        context = {
            'booking': booking,
            'payment_accounts': payment_accounts,
            'breadcrumb_items': breadcrumb_items,
            'header_buttons': header_buttons,
            'active_menu': 'real_estate',
            'active_submenu': 'bookings',
        }
        return render(request, 'real_estate/booking_detail.html', context)


class BookingOfficialPrintView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    طباعة استمارة حجز الوحدة وإيصال أمانة جدية الحجز (مع ختم التوثيق الرقمي SHA-256)
    """
    permission_required = 'real_estate.view_unitbooking'

    def get(self, request, pk):
        import hashlib
        from django.utils import timezone

        booking = get_object_or_404(
            UnitBooking.objects.select_related(
                'customer', 'unit__project', 'unit__floor__block', 'journal_entry', 'created_by'
            ),
            pk=pk
        )

        raw_seed = (
            f"BKG:{booking.booking_number}:{booking.customer_id}:{booking.unit_id}:"
            f"{booking.holding_deposit}:{booking.booking_date}:{booking.status}"
        )
        verification_hash = hashlib.sha256(raw_seed.encode('utf-8')).hexdigest()

        context = {
            'booking': booking,
            'verification_hash': verification_hash,
            'verification_token': verification_hash[:16].upper(),
            'today': timezone.localdate(),
        }
        return render(request, 'real_estate/booking_print.html', context)

