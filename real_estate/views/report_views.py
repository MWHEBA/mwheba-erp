# -*- coding: utf-8 -*-
"""
Real Estate Analytics & Financial Reporting Views
MWHEBA ERP — Real Estate Wave 6 (Phase 6.1: Dual-Perspective Subledger, Cash Flow Radar, WIP & IFRS 15, Broker Radar)
"""
from datetime import datetime
from django.shortcuts import render
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.core.paginator import Paginator

from users.mixins import SmartPermissionRequiredMixin
from customer.models import Customer
from real_estate.models import (
    RealEstateProject,
    PropertyContract,
    RealEstateBroker,
    BrokerCommission,
)
from real_estate.services.reporting_service import RealEstateReportingService


class DualSubledgerReportView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تقرير كشف الحساب المزدوج للعقود والعملاء (المنظور التعاقدي مقابل المنظور المالي والشيكات وIFRS 15)
    """
    permission_required = 'real_estate.view_propertycontract'

    def get(self, request):
        search_query = request.GET.get('q', '').strip()
        project_id = request.GET.get('project', '').strip()
        customer_id = request.GET.get('customer', '').strip()
        status_filter = request.GET.get('status', '').strip()
        clearance_filter = request.GET.get('clearance', '').strip()

        report_data = RealEstateReportingService.get_dual_subledger_report(
            project_id=int(project_id) if project_id.isdigit() else None,
            customer_id=int(customer_id) if customer_id.isdigit() else None,
            status=status_filter or None,
            clearance_filter=clearance_filter or None,
            search_query=search_query,
        )

        paginator = Paginator(report_data['rows'], 25)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        projects = RealEstateProject.objects.filter(is_archived=False).order_by('name')
        customers = Customer.objects.filter(property_contracts__isnull=False).distinct().order_by('name')

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('التقارير العقارية'), 'url': reverse('real_estate:report_dual_subledger'), 'icon': 'fa-chart-line'},
            {'title': _('كشف الحساب المزدوج (تعاقدي / مالي)'), 'active': True},
        ]

        context = {
            **report_data,
            'page_obj': page_obj,
            'contract_rows': page_obj.object_list,
            'projects': projects,
            'customers': customers,
            'status_choices': PropertyContract.ContractStatus.choices,
            'search_query': search_query,
            'selected_project': project_id,
            'selected_customer': customer_id,
            'selected_status': status_filter,
            'selected_clearance': clearance_filter,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_reports',
            'active_submenu': 'report_dual_subledger',
        }
        return render(request, 'real_estate/reports/dual_subledger_report.html', context)


class CashFlowLiquidityReportView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    رادار التدفقات النقدية العقارية ومطابقة السيولة الشهرية
    """
    permission_required = 'real_estate.view_propertycontract'

    def get(self, request):
        project_id = request.GET.get('project', '').strip()
        date_from_str = request.GET.get('date_from', '').strip()
        date_to_str = request.GET.get('date_to', '').strip()

        date_from = None
        date_to = None
        if date_from_str:
            try:
                date_from = datetime.strptime(date_from_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        if date_to_str:
            try:
                date_to = datetime.strptime(date_to_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        report_data = RealEstateReportingService.get_cash_flow_liquidity_report(
            project_id=int(project_id) if project_id.isdigit() else None,
            date_from=date_from,
            date_to=date_to,
        )

        paginator = Paginator(report_data['installment_rows'], 25)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        projects = RealEstateProject.objects.filter(is_archived=False).order_by('name')

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('التقارير العقارية'), 'url': reverse('real_estate:report_dual_subledger'), 'icon': 'fa-chart-line'},
            {'title': _('رادار التدفقات النقدية والسيولة'), 'active': True},
        ]

        context = {
            **report_data,
            'page_obj': page_obj,
            'installments_page': page_obj.object_list,
            'projects': projects,
            'selected_project': project_id,
            'date_from': date_from_str,
            'date_to': date_to_str,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_reports',
            'active_submenu': 'report_cash_flow',
        }
        return render(request, 'real_estate/reports/cash_flow_report.html', context)


class ProjectWIPRevenueReportView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تقرير تكلفة المشروعات تحت التنفيذ (WIP Costing) والاعتراف بالإيراد وفق معيار IFRS 15
    """
    permission_required = 'real_estate.view_realestateproject'

    def get(self, request):
        project_id = request.GET.get('project', '').strip()
        status_filter = request.GET.get('status', '').strip()

        report_data = RealEstateReportingService.get_project_wip_revenue_report(
            project_id=int(project_id) if project_id.isdigit() else None,
            status=status_filter or None,
        )

        projects = RealEstateProject.objects.filter(is_archived=False).order_by('name')

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('التقارير العقارية'), 'url': reverse('real_estate:report_dual_subledger'), 'icon': 'fa-chart-line'},
            {'title': _('تكاليف المشروعات وإيرادات IFRS 15'), 'active': True},
        ]

        context = {
            **report_data,
            'projects': projects,
            'status_choices': RealEstateProject.ProjectStatus.choices,
            'selected_project': project_id,
            'selected_status': status_filter,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_reports',
            'active_submenu': 'report_wip_revenue',
        }
        return render(request, 'real_estate/reports/wip_revenue_report.html', context)


class BrokerCommissionReportView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تقرير أداء الوسطاء العقاريين واستحقاقات العمولات المرحلية
    """
    permission_required = 'real_estate.view_brokercommission'

    def get(self, request):
        broker_id = request.GET.get('broker', '').strip()
        project_id = request.GET.get('project', '').strip()
        tranche_status = request.GET.get('tranche_status', '').strip()

        report_data = RealEstateReportingService.get_broker_commission_report(
            broker_id=int(broker_id) if broker_id.isdigit() else None,
            project_id=int(project_id) if project_id.isdigit() else None,
            tranche_status=tranche_status or None,
        )

        brokers = RealEstateBroker.objects.filter(is_active=True).order_by('name')
        projects = RealEstateProject.objects.filter(is_archived=False).order_by('name')

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('التقارير العقارية'), 'url': reverse('real_estate:report_dual_subledger'), 'icon': 'fa-chart-line'},
            {'title': _('تقرير أداء الوسطاء والعمولات'), 'active': True},
        ]

        context = {
            **report_data,
            'brokers': brokers,
            'projects': projects,
            'tranche_status_choices': BrokerCommission.TrancheStatus.choices,
            'selected_broker': broker_id,
            'selected_project': project_id,
            'selected_tranche_status': tranche_status,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_reports',
            'active_submenu': 'report_broker_commissions',
        }
        return render(request, 'real_estate/reports/broker_commission_report.html', context)
