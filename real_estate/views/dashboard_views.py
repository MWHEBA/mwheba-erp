# -*- coding: utf-8 -*-
from decimal import Decimal
from django.shortcuts import render
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.db.models import Sum, Count, Q

from users.mixins import SmartPermissionRequiredMixin
from real_estate.models import (
    RealEstateProject,
    PropertyUnit,
    UnitBooking,
    PropertyContract,
)


class RealEstateDashboardView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    لوحة مؤشرات القطاع العقاري التنفيذية والمالية
    """
    permission_required = 'real_estate.view_realestateproject'

    def get(self, request):
        projects = RealEstateProject.objects.filter(is_archived=False)
        total_projects = projects.count()

        units = PropertyUnit.objects.filter(is_active=True)
        total_units = units.count()
        available_units = units.filter(status=PropertyUnit.UnitStatus.AVAILABLE).count()
        reserved_units = units.filter(status=PropertyUnit.UnitStatus.RESERVED).count()
        contracted_units = units.filter(status=PropertyUnit.UnitStatus.CONTRACTED).count()

        contracts = PropertyContract.objects.all()
        total_contracts = contracts.count()
        total_portfolio_value = contracts.aggregate(s=Sum('final_contract_price'))['s'] or Decimal('0.00')
        total_down_payments = contracts.aggregate(s=Sum('down_payment'))['s'] or Decimal('0.00')

        active_bookings = UnitBooking.objects.filter(status=UnitBooking.BookingStatus.ACTIVE)
        total_active_bookings = active_bookings.count()
        total_holding_deposits = active_bookings.aggregate(s=Sum('holding_deposit'))['s'] or Decimal('0.00')

        recent_contracts = contracts.select_related('customer', 'unit', 'project').order_by('-contract_date', '-id')[:5]
        recent_bookings = active_bookings.select_related('customer', 'unit').order_by('-booking_date', '-id')[:5]

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('القطاع العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('لوحة المؤشرات'), 'active': True}
        ]

        context = {
            'total_projects': total_projects,
            'total_units': total_units,
            'available_units': available_units,
            'reserved_units': reserved_units,
            'contracted_units': contracted_units,
            'total_contracts': total_contracts,
            'total_portfolio_value': total_portfolio_value,
            'total_down_payments': total_down_payments,
            'total_active_bookings': total_active_bookings,
            'total_holding_deposits': total_holding_deposits,
            'projects': projects[:6],
            'recent_contracts': recent_contracts,
            'recent_bookings': recent_bookings,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 'real_estate',
            'active_submenu': 're_dashboard',
        }
        return render(request, 'real_estate/dashboard.html', context)
