# -*- coding: utf-8 -*-
import datetime
from django.shortcuts import render
from django.views.generic import View
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from financial.models import ChartOfAccounts
from customer.models import Customer
from supplier.models import Supplier
from cheques.models import ChequeType
from cheques.services.subledger_reconciliation_service import ChequeSubledgerReconciliationService
from cheques.services.aging_service import ChequeAgingService
from cheques.services.alert_service import ChequeAlertService


class ChequeSubledgerReconciliationReportView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """
    تقرير مطابقة الأستاذ المساعد للأستاذ العام (Point-in-Time Subledger Reconciliation)
    مطابقة حسابات: أوراق القبض (11220)، شيكات برسم التحصيل (11190)، أوراق الدفع (21120)
    """
    permission_required = 'cheques.view_cheque'
    template_name = 'cheques/reports/subledger_reconciliation.html'

    def get(self, request, *args, **kwargs):
        as_of_date_str = request.GET.get('as_of_date')
        if as_of_date_str:
            try:
                as_of_date = datetime.date.fromisoformat(as_of_date_str)
            except ValueError:
                as_of_date = timezone.now().date()
        else:
            as_of_date = timezone.now().date()

        reconciliation = ChequeSubledgerReconciliationService.reconcile_with_details(as_of_date)

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('إدارة الشيكات'), 'url': reverse('cheques:receivable_list'), 'icon': 'fa-money-check'},
            {'title': _('مطابقة الأستاذ المساعد'), 'active': True}
        ]

        context = {
            'as_of_date': as_of_date.isoformat(),
            'reconciliation': reconciliation,
            'breadcrumb_items': breadcrumb_items,
        }
        return render(request, self.template_name, context)


class ChequeAgingReportView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """
    تقرير وميزان أعمار أوراق القبض والدفع
    (Cheque Aging Analysis & Maturity Schedule)
    """
    permission_required = 'cheques.view_cheque'
    template_name = 'cheques/reports/aging_report.html'

    def get(self, request, *args, **kwargs):
        as_of_date_str = request.GET.get('as_of_date')
        if as_of_date_str:
            try:
                as_of_date = datetime.date.fromisoformat(as_of_date_str)
            except ValueError:
                as_of_date = timezone.now().date()
        else:
            as_of_date = timezone.now().date()

        cheque_type = request.GET.get('cheque_type', ChequeType.RECEIVABLE)
        if cheque_type not in [ChequeType.RECEIVABLE, ChequeType.PAYABLE]:
            cheque_type = ChequeType.RECEIVABLE

        partner_id_str = request.GET.get('partner_id')
        partner_id = int(partner_id_str) if partner_id_str and partner_id_str.isdigit() else None

        report = ChequeAgingService.get_aging_report(
            as_of_date=as_of_date,
            cheque_type=cheque_type,
            partner_id=partner_id,
        )

        customers = Customer.objects.filter(is_active=True).order_by('name') if cheque_type == ChequeType.RECEIVABLE else None
        suppliers = Supplier.objects.filter(is_active=True).order_by('name') if cheque_type == ChequeType.PAYABLE else None

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('إدارة الشيكات'), 'url': reverse('cheques:receivable_list'), 'icon': 'fa-money-check'},
            {'title': _('ميزان أعمار الشيكات'), 'active': True}
        ]

        context = {
            'as_of_date': as_of_date.isoformat(),
            'cheque_type': cheque_type,
            'partner_id': partner_id,
            'report': report,
            'customers': customers,
            'suppliers': suppliers,
            'breadcrumb_items': breadcrumb_items,
        }
        return render(request, self.template_name, context)


class ChequeUpcomingDueReportView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """
    تقرير وتنبيهات الشيكات المستحقة والمتأخرة
    (Upcoming Due Cheques & Maturity Alerts)
    """
    permission_required = 'cheques.view_cheque'
    template_name = 'cheques/reports/upcoming_due.html'

    def get(self, request, *args, **kwargs):
        period_filter = request.GET.get('period', '7')
        cheque_type = request.GET.get('cheque_type')
        if cheque_type and cheque_type not in [ChequeType.RECEIVABLE, ChequeType.PAYABLE]:
            cheque_type = None

        bank_account_id_str = request.GET.get('bank_account_id')
        bank_account_id = int(bank_account_id_str) if bank_account_id_str and bank_account_id_str.isdigit() else None

        report = ChequeAlertService.get_upcoming_due_report(
            period_filter=period_filter,
            cheque_type=cheque_type,
            bank_account_id=bank_account_id,
        )

        banks = ChartOfAccounts.objects.filter(is_active=True, is_leaf=True, code__startswith='1116').order_by('code')

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('إدارة الشيكات'), 'url': reverse('cheques:receivable_list'), 'icon': 'fa-money-check'},
            {'title': _('الشيكات المستحقة والتنبيهات'), 'active': True}
        ]

        context = {
            'report': report,
            'period_filter': period_filter,
            'cheque_type': cheque_type or '',
            'bank_account_id': bank_account_id,
            'banks': banks,
            'breadcrumb_items': breadcrumb_items,
        }
        return render(request, self.template_name, context)
