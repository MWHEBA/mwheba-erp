# -*- coding: utf-8 -*-
from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.core.paginator import Paginator
from django.contrib import messages
from django.db.models import Q, Sum

from users.mixins import SmartPermissionRequiredMixin
from real_estate.models import RealEstateBroker, BrokerCommission, PropertyContract
from real_estate.services.broker_service import BrokerCommissionService
from financial.models.chart_of_accounts import ChartOfAccounts


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

        paginator = Paginator(qs, 15)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        total_brokers = RealEstateBroker.objects.filter(is_active=True).count()
        total_commissions = BrokerCommission.objects.aggregate(s=Sum('total_commission_amount'))['s'] or Decimal('0.00')
        released_commissions = sum(
            (c.released_commission_amount for c in BrokerCommission.objects.all()),
            Decimal('0.00')
        )

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('القطاع العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('الوسطاء والمسوقين'), 'active': True}
        ]

        header_buttons = []
        if request.user.has_perm('real_estate.add_realestatebroker') or request.user.is_superuser:
            header_buttons.append({
                'url': reverse('real_estate:broker_create'),
                'label': _('وسيط عقاري جديد'),
                'icon': 'fa-plus',
                'class': 'btn-primary'
            })

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
            'header_buttons': header_buttons,
            'active_menu': 're_sales',
            'active_submenu': 'brokers',
        }
        return render(request, 'real_estate/broker_list.html', context)


class BrokerDetailView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تفاصيل الوسيط العقاري، كشف حساب العمولات، والعقود المحالة
    """
    permission_required = 'real_estate.view_realestatebroker'

    def get(self, request, pk):
        broker = get_object_or_404(
            RealEstateBroker.objects.select_related('financial_account', 'created_by'),
            pk=pk
        )
        commissions = broker.commissions.select_related(
            'contract__customer', 'contract__unit__project'
        ).order_by('-created_at')

        total_commissions = sum((c.total_commission_amount for c in commissions), Decimal('0.00'))
        total_released = sum((c.released_commission_amount for c in commissions), Decimal('0.00'))
        total_remaining = sum((c.remaining_commission for c in commissions), Decimal('0.00'))
        total_contracts = commissions.count()

        payment_accounts = ChartOfAccounts.objects.filter(is_active=True, is_leaf=True)

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('القطاع العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('الوسطاء والمسوقين'), 'url': reverse('real_estate:broker_list'), 'icon': 'fa-user-tie'},
            {'title': broker.name, 'active': True}
        ]

        header_buttons = []
        if request.user.has_perm('real_estate.change_realestatebroker') or request.user.is_superuser:
            header_buttons.append({
                'url': reverse('real_estate:broker_update', kwargs={'pk': broker.pk}),
                'label': _('تعديل البيانات'),
                'icon': 'fa-edit',
                'class': 'btn-outline-primary'
            })

        context = {
            'broker': broker,
            'commissions': commissions,
            'total_commissions': total_commissions,
            'total_released': total_released,
            'total_remaining': total_remaining,
            'total_contracts': total_contracts,
            'payment_accounts': payment_accounts,
            'breadcrumb_items': breadcrumb_items,
            'header_buttons': header_buttons,
            'active_menu': 're_sales',
            'active_submenu': 'brokers',
        }
        return render(request, 'real_estate/broker_detail.html', context)


class BrokerCreateView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تسجيل شركة وساطة عقارية أو مسوق جديد
    """
    permission_required = 'real_estate.add_realestatebroker'

    def get(self, request):
        accounts = ChartOfAccounts.objects.filter(is_active=True, is_leaf=True)
        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('القطاع العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('الوسطاء والمسوقين'), 'url': reverse('real_estate:broker_list'), 'icon': 'fa-user-tie'},
            {'title': _('وسيط عقاري جديد'), 'active': True}
        ]

        context = {
            'broker_types': RealEstateBroker.BrokerType.choices,
            'accounts': accounts,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_sales',
            'active_submenu': 'brokers',
            'is_edit': False,
        }
        return render(request, 'real_estate/broker_form.html', context)

    def post(self, request):
        code = request.POST.get('code', '').strip().upper()
        name = request.POST.get('name', '').strip()
        broker_type = request.POST.get('broker_type', RealEstateBroker.BrokerType.AGENCY)
        commercial_registration = request.POST.get('commercial_registration', '').strip()
        tax_id = request.POST.get('tax_id', '').strip()
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()
        contact_person = request.POST.get('contact_person', '').strip()
        commission_rate = Decimal(str(request.POST.get('default_commission_rate', '2.50') or '2.50'))
        account_id = request.POST.get('financial_account')
        notes = request.POST.get('notes', '').strip()

        if not code or not name:
            messages.error(request, _('يرجى إدخال كود واسم الوسيط العقاري.'))
            return redirect('real_estate:broker_create')

        if RealEstateBroker.objects.filter(code=code).exists():
            messages.error(request, _('كود الوسيط مسجل مسبقاً، يرجى استخدام كود فريد.'))
            return redirect('real_estate:broker_create')

        account = ChartOfAccounts.objects.filter(pk=account_id).first() if account_id else None

        broker = RealEstateBroker.objects.create(
            code=code,
            name=name,
            broker_type=broker_type,
            commercial_registration=commercial_registration,
            tax_id=tax_id,
            phone=phone,
            email=email,
            contact_person=contact_person,
            default_commission_rate=commission_rate,
            financial_account=account,
            notes=notes,
            created_by=request.user,
            is_active=True
        )

        messages.success(request, _('تم تسجيل الوسيط العقاري %(name)s بنجاح.') % {'name': broker.name})
        return redirect('real_estate:broker_detail', pk=broker.pk)


class BrokerUpdateView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تعديل بيانات وسيط عقاري قائم
    """
    permission_required = 'real_estate.change_realestatebroker'

    def get(self, request, pk):
        broker = get_object_or_404(RealEstateBroker, pk=pk)
        accounts = ChartOfAccounts.objects.filter(is_active=True, is_leaf=True)

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('القطاع العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('الوسطاء والمسوقين'), 'url': reverse('real_estate:broker_list'), 'icon': 'fa-user-tie'},
            {'title': broker.name, 'url': reverse('real_estate:broker_detail', kwargs={'pk': broker.pk})},
            {'title': _('تعديل البيانات'), 'active': True}
        ]

        context = {
            'broker': broker,
            'broker_types': RealEstateBroker.BrokerType.choices,
            'accounts': accounts,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_sales',
            'active_submenu': 'brokers',
            'is_edit': True,
        }
        return render(request, 'real_estate/broker_form.html', context)

    def post(self, request, pk):
        broker = get_object_or_404(RealEstateBroker, pk=pk)

        name = request.POST.get('name', '').strip()
        broker.broker_type = request.POST.get('broker_type', broker.broker_type)
        broker.commercial_registration = request.POST.get('commercial_registration', '').strip()
        broker.tax_id = request.POST.get('tax_id', '').strip()
        broker.phone = request.POST.get('phone', '').strip()
        broker.email = request.POST.get('email', '').strip()
        broker.contact_person = request.POST.get('contact_person', '').strip()
        broker.default_commission_rate = Decimal(str(request.POST.get('default_commission_rate', '2.50') or '2.50'))
        broker.is_active = request.POST.get('is_active') == 'on' or request.POST.get('is_active') == '1'

        account_id = request.POST.get('financial_account')
        broker.financial_account = ChartOfAccounts.objects.filter(pk=account_id).first() if account_id else None
        broker.notes = request.POST.get('notes', '').strip()

        if not name:
            messages.error(request, _('اسم الوسيط مطلوب.'))
            return redirect('real_estate:broker_update', pk=broker.pk)

        broker.name = name
        broker.save()
        messages.success(request, _('تم تحديث بيانات الوسيط العقاري بنجاح.'))
        return redirect('real_estate:broker_detail', pk=broker.pk)


class BrokerCommissionListView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    بيان عمولات البيع والحجوزات العقارية والشرائح
    """
    permission_required = 'real_estate.view_brokercommission'

    def get(self, request):
        search_query = request.GET.get('q', '').strip()
        tranche_filter = request.GET.get('status', '').strip()

        qs = BrokerCommission.objects.select_related(
            'broker', 'contract__customer', 'contract__unit__project'
        ).order_by('-created_at')

        if search_query:
            qs = qs.filter(
                Q(broker__name__icontains=search_query) |
                Q(contract__contract_number__icontains=search_query) |
                Q(contract__customer__name__icontains=search_query)
            )

        if tranche_filter:
            qs = qs.filter(Q(tranche_1_status=tranche_filter) | Q(tranche_2_status=tranche_filter))

        paginator = Paginator(qs, 20)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        total_records = BrokerCommission.objects.count()
        total_amount = BrokerCommission.objects.aggregate(s=Sum('total_commission_amount'))['s'] or Decimal('0.00')
        released_amount = sum((c.released_commission_amount for c in BrokerCommission.objects.all()), Decimal('0.00'))

        payment_accounts = ChartOfAccounts.objects.filter(is_active=True, is_leaf=True)

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('القطاع العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('عمولات البيع والتسويق'), 'active': True}
        ]

        context = {
            'page_obj': page_obj,
            'commissions': page_obj.object_list,
            'search_query': search_query,
            'selected_status': tranche_filter,
            'status_choices': BrokerCommission.TrancheStatus.choices,
            'total_records': total_records,
            'total_amount': total_amount,
            'released_amount': released_amount,
            'payment_accounts': payment_accounts,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_sales',
            'active_submenu': 'commissions',
        }
        return render(request, 'real_estate/commission_list.html', context)


class BrokerCommissionEvaluateView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    فحص وإعادة تقييم استحقاق شرائح العمولة وفق شروط السداد والتحصيل
    """
    permission_required = 'real_estate.change_brokercommission'

    def post(self, request, pk):
        commission = get_object_or_404(BrokerCommission, pk=pk)
        try:
            BrokerCommissionService.evaluate_milestones_and_release(commission, user=request.user)
            messages.success(request, _('تم تقييم استحقاق شرائح العمولة بنجاح وفق متحصلات العقد.'))
        except Exception as e:
            messages.error(request, str(e))
        return redirect(request.META.get('HTTP_REFERER') or reverse('real_estate:broker_detail', kwargs={'pk': commission.broker.pk}))


class BrokerCommissionPayoutView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    صرف شريحة عمولة معتمدة وترحيل قيد المصروف للدفاتر العامة
    """
    permission_required = 'real_estate.change_brokercommission'

    def post(self, request, pk):
        commission = get_object_or_404(BrokerCommission, pk=pk)
        tranche_num = int(request.POST.get('tranche', 1))
        account_id = request.POST.get('payment_account')

        if not account_id:
            messages.error(request, _('يرجى اختيار حساب الخزينة أو البنك لصرف العمولة.'))
            return redirect(request.META.get('HTTP_REFERER') or reverse('real_estate:broker_detail', kwargs={'pk': commission.broker.pk}))

        payment_account = get_object_or_404(ChartOfAccounts, pk=account_id)

        try:
            entry = BrokerCommissionService.payout_commission_tranche(
                broker_commission=commission,
                tranche_number=tranche_num,
                payment_account=payment_account,
                user=request.user
            )
            messages.success(request, _('تم صرف الشريحة %(num)d بنجاح وترحيل القيد رقم %(entry)s.') % {
                'num': tranche_num,
                'entry': entry.entry_number
            })
        except Exception as e:
            messages.error(request, str(e))

        return redirect(request.META.get('HTTP_REFERER') or reverse('real_estate:broker_detail', kwargs={'pk': commission.broker.pk}))


class BrokerAssignContractView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    ربط وسيط عقاري بعقد مبيعات قائم مع تدقيق أسبقية المصدر وتفويض الـ CEO
    """
    permission_required = 'real_estate.add_brokercommission'

    def post(self, request, contract_id):
        contract = get_object_or_404(PropertyContract, pk=contract_id)
        broker_id = request.POST.get('broker')
        rate = request.POST.get('commission_rate')
        ceo_token = request.POST.get('ceo_override_token', '').strip()
        ceo_reason = request.POST.get('ceo_override_reason', '').strip()

        if not broker_id:
            messages.error(request, _('يرجى اختيار الوسيط العقاري المراد ربطه.'))
            return redirect('real_estate:contract_detail', pk=contract.pk)

        broker = get_object_or_404(RealEstateBroker, pk=broker_id)
        rate_dec = Decimal(str(rate)) if rate else None

        try:
            comm = BrokerCommissionService.assign_broker_to_contract(
                contract=contract,
                broker=broker,
                commission_rate=rate_dec,
                user=request.user,
                ceo_override_token=ceo_token or None,
                ceo_override_reason=ceo_reason
            )
            messages.success(request, _('تم ربط الوسيط %(name)s بالعقد واحتساب عمولة بمبلغ %(amt)s ج.م بنجاح.') % {
                'name': broker.name,
                'amt': comm.total_commission_amount
            })
        except Exception as e:
            messages.error(request, str(e))

        return redirect('real_estate:contract_detail', pk=contract.pk)
