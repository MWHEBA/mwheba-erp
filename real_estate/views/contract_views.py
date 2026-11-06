# -*- coding: utf-8 -*-
from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.http import JsonResponse, HttpResponse
from django.template.loader import render_to_string
from django.core.paginator import Paginator
from django.contrib import messages
from django.db.models import Q, Sum
from django.utils import timezone

from users.mixins import SmartPermissionRequiredMixin
from real_estate.models import (
    PropertyContract, PropertyUnit, RealEstateProject, ContractCoOwner, RealEstateBroker
)
from real_estate.services.clearance_service import ContractDebtClearanceService
from customer.models import Customer
from financial.models.currency import Currency


class ContractListView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    قائمة عقود البيع الرسمية والمحفظة الاستثمارية
    """
    permission_required = 'real_estate.view_propertycontract'

    def get(self, request):
        search_query = request.GET.get('q', '').strip()
        status_filter = request.GET.get('status', '').strip()
        project_id = request.GET.get('project', '').strip()

        contracts_qs = PropertyContract.objects.select_related('customer', 'unit__project', 'installment_plan').order_by('-contract_date', '-id')

        if search_query:
            contracts_qs = contracts_qs.filter(
                Q(contract_number__icontains=search_query) |
                Q(customer__name__icontains=search_query) |
                Q(unit__unit_code__icontains=search_query)
            )

        if status_filter:
            contracts_qs = contracts_qs.filter(status=status_filter)

        if project_id:
            contracts_qs = contracts_qs.filter(project_id=project_id)

        paginator = Paginator(contracts_qs, 15)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.GET.get('ajax') == '1':
            table_html = render_to_string(
                'real_estate/partials/contract_table.html',
                {'page_obj': page_obj, 'contracts': page_obj.object_list},
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

        total_contracts = PropertyContract.objects.count()
        active_contracts = PropertyContract.objects.filter(status='ACTIVE').count()
        total_portfolio_value = PropertyContract.objects.aggregate(s=Sum('final_contract_price'))['s'] or Decimal('0.00')
        total_down_payments = PropertyContract.objects.aggregate(s=Sum('down_payment'))['s'] or Decimal('0.00')

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('القطاع العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('عقود البيع والشركاء'), 'active': True}
        ]

        header_buttons = []
        if request.user.has_perm('real_estate.add_propertycontract') or request.user.is_superuser:
            header_buttons.append({
                'url': reverse('real_estate:contract_create'),
                'label': _('إبرام عقد جديد'),
                'icon': 'fa-file-signature',
                'class': 'btn-primary'
            })

        context = {
            'page_obj': page_obj,
            'contracts': page_obj.object_list,
            'projects': RealEstateProject.objects.filter(is_archived=False),
            'total_contracts': total_contracts,
            'active_contracts': active_contracts,
            'total_portfolio_value': total_portfolio_value,
            'total_down_payments': total_down_payments,
            'status_choices': PropertyContract.ContractStatus.choices,
            'breadcrumb_items': breadcrumb_items,
            'header_buttons': header_buttons,
            'active_menu': 'real_estate',
            'active_submenu': 'contracts',
        }
        return render(request, 'real_estate/contract_list.html', context)


class ContractDetailView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تفاصيل العقد، الشركاء، خطة الأقساط، ومحفظة الشيكات
    """
    permission_required = 'real_estate.view_propertycontract'

    def get(self, request, pk):
        contract = get_object_or_404(
            PropertyContract.objects.select_related('customer', 'unit__project', 'installment_plan', 'currency'),
            pk=pk
        )
        co_owners = contract.co_owners.select_related('co_owner')
        installment_items = contract.installment_plan.items.all().order_by('installment_number') if contract.installment_plan else []
        commissions = contract.broker_commissions.select_related('broker')
        available_brokers = RealEstateBroker.objects.filter(is_active=True)

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('القطاع العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('العقود'), 'url': reverse('real_estate:contract_list'), 'icon': 'fa-file-contract'},
            {'title': contract.contract_number, 'active': True}
        ]

        header_buttons = [
            {
                'url': reverse('real_estate:contract_print', kwargs={'pk': contract.pk}),
                'label': _('طباعة العقد الرسمي'),
                'icon': 'fa-print',
                'class': 'btn-primary',
                'target': '_blank'
            },
            {
                'url': reverse('real_estate:contract_statement_print', kwargs={'pk': contract.pk}),
                'label': _('طباعة كشف الحساب'),
                'icon': 'fa-file-invoice-dollar',
                'class': 'btn-outline-primary',
                'target': '_blank'
            },
            {
                'url': reverse('real_estate:contract_clearance_print', kwargs={'pk': contract.pk}),
                'label': _('شهادة المخالصة المالية'),
                'icon': 'fa-certificate',
                'class': 'btn-outline-success',
                'target': '_blank'
            }
        ]

        context = {
            'contract': contract,
            'co_owners': co_owners,
            'installment_items': installment_items,
            'commissions': commissions,
            'available_brokers': available_brokers,
            'breadcrumb_items': breadcrumb_items,
            'header_buttons': header_buttons,
            'active_menu': 'real_estate',
            'active_submenu': 'contracts',
        }
        return render(request, 'real_estate/contract_detail.html', context)


class ContractCreateView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    إبرام عقد بيع رسمي جديد
    """
    permission_required = 'real_estate.add_propertycontract'

    def get(self, request):
        customers = Customer.objects.filter(is_active=True).order_by('name')
        available_units = PropertyUnit.objects.filter(is_active=True, status='AVAILABLE').select_related('project')
        currencies = Currency.objects.all()

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('القطاع العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('العقود'), 'url': reverse('real_estate:contract_list'), 'icon': 'fa-file-contract'},
            {'title': _('إبرام عقد جديد'), 'active': True}
        ]

        context = {
            'customers': customers,
            'available_units': available_units,
            'currencies': currencies,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 'real_estate',
            'active_submenu': 'contracts',
        }
        return render(request, 'real_estate/contract_form.html', context)

    def post(self, request):
        customer_id = request.POST.get('customer')
        unit_id = request.POST.get('unit')
        contract_price = Decimal(str(request.POST.get('final_contract_price', '0.00') or '0.00'))
        down_payment = Decimal(str(request.POST.get('down_payment', '0.00') or '0.00'))
        contract_date = request.POST.get('contract_date') or timezone.localdate()
        delivery_date = request.POST.get('delivery_date') or None
        currency_id = request.POST.get('currency') or None

        if not customer_id or not unit_id or contract_price <= Decimal('0.00'):
            messages.error(request, _('يرجى اختيار العميل والوحدة وتحديد القيمة التعاقدية الصحيحة.'))
            return redirect('real_estate:contract_create')

        customer = get_object_or_404(Customer, pk=customer_id)
        unit = get_object_or_404(PropertyUnit, pk=unit_id)
        currency = Currency.objects.filter(pk=currency_id).first() if currency_id else None

        if unit.status != PropertyUnit.UnitStatus.AVAILABLE:
            messages.error(request, _('الوحدة المختارة غير متاحة للتعاقد حالياً.'))
            return redirect('real_estate:contract_create')

        import uuid
        cnt_num = f"CTR-{unit.unit_code}-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"

        contract = PropertyContract.objects.create(
            contract_number=cnt_num,
            project=unit.project,
            unit=unit,
            customer=customer,
            status=PropertyContract.ContractStatus.ACTIVE,
            contract_date=contract_date,
            delivery_date=delivery_date,
            final_contract_price=contract_price,
            down_payment=down_payment,
            currency=currency,
            created_by=request.user
        )

        unit.status = PropertyUnit.UnitStatus.CONTRACTED
        unit.status_version += 1
        unit.save(update_fields=['status', 'status_version'])

        messages.success(request, _('تم إبرام العقد العقاري بنجاح برقم: %(num)s') % {'num': contract.contract_number})
        return redirect('real_estate:contract_detail', pk=contract.pk)


class ContractDebtClearancePrintView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    طباعة ومعاينة شهادة المخالصة المالية الموثقة رقمياً
    """
    permission_required = 'real_estate.view_propertycontract'

    def get(self, request, pk):
        contract = get_object_or_404(PropertyContract, pk=pk)
        try:
            cert_data = ContractDebtClearanceService.issue_clearance_certificate(contract, user=request.user)
            context = {
                'contract': contract,
                'cert': cert_data,
                'today': timezone.localdate(),
            }
            return render(request, 'real_estate/clearance_certificate_print.html', context)
        except Exception as e:
            messages.error(request, str(e))
            return redirect('real_estate:contract_detail', pk=contract.pk)


class ContractOfficialPrintView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    طباعة العقد العقاري النهائي المعتمد (مع جدول الأقساط والشركاء وختم التوثيق الرقمي SHA-256)
    """
    permission_required = 'real_estate.view_propertycontract'

    def get(self, request, pk):
        import hashlib
        contract = get_object_or_404(
            PropertyContract.objects.select_related(
                'customer', 'unit__project', 'unit__floor__block', 'installment_plan', 'currency', 'created_by'
            ),
            pk=pk
        )
        co_owners = contract.co_owners.select_related('co_owner')
        installment_items = (
            contract.installment_plan.items.all().order_by('installment_number')
            if contract.installment_plan else []
        )

        raw_seed = (
            f"{contract.contract_number}:{contract.customer_id}:{contract.unit_id}:"
            f"{contract.final_contract_price}:{contract.down_payment}:{contract.contract_date}"
        )
        verification_hash = hashlib.sha256(raw_seed.encode('utf-8')).hexdigest()

        context = {
            'contract': contract,
            'co_owners': co_owners,
            'installment_items': installment_items,
            'verification_hash': verification_hash,
            'verification_token': verification_hash[:16].upper(),
            'today': timezone.localdate(),
        }
        return render(request, 'real_estate/contract_print.html', context)


class ContractStatementPrintView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    طباعة كشف حساب الوحدة والعميل التفصيلي (تعاقدي / مالي / شيكات)
    """
    permission_required = 'real_estate.view_propertycontract'

    def get(self, request, pk):
        import hashlib
        from cheques.models.allocation import ChequeInvoiceAllocation

        contract = get_object_or_404(
            PropertyContract.objects.select_related(
                'customer', 'unit__project', 'installment_plan', 'currency'
            ),
            pk=pk
        )
        verified_dp = ContractDebtClearanceService.get_verified_down_payment(contract)
        clearance_eval = ContractDebtClearanceService.evaluate_contract_clearance(contract)

        installment_items = []
        cheque_allocations = []
        paid_installments_total = Decimal('0.00')

        if contract.installment_plan:
            installment_items = list(contract.installment_plan.items.all().order_by('installment_number'))
            paid_installments_total = sum((Decimal(str(i.paid_amount)) for i in installment_items), Decimal('0.00'))
            cheque_allocations = list(
                ChequeInvoiceAllocation.objects.filter(
                    installment_item__plan=contract.installment_plan,
                    allocation_status='APPLIED'
                ).select_related('cheque', 'installment_item').order_by('cheque__due_date')
            )

        raw_seed = (
            f"SOA:{contract.contract_number}:{contract.final_contract_price}:"
            f"{clearance_eval['total_paid']}:{clearance_eval['remaining_balance']}:{timezone.localdate()}"
        )
        verification_hash = hashlib.sha256(raw_seed.encode('utf-8')).hexdigest()

        context = {
            'contract': contract,
            'verified_down_payment': verified_dp,
            'paid_installments_total': paid_installments_total,
            'total_paid': clearance_eval['total_paid'],
            'remaining_balance': clearance_eval['remaining_balance'],
            'is_cleared': clearance_eval['is_cleared'],
            'installment_items': installment_items,
            'cheque_allocations': cheque_allocations,
            'verification_hash': verification_hash,
            'verification_token': verification_hash[:16].upper(),
            'today': timezone.localdate(),
        }
        return render(request, 'real_estate/contract_statement_print.html', context)

