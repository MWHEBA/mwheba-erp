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
from django.core.exceptions import ValidationError
from django.contrib import messages
from django.db.models import Q, Sum
from django.utils import timezone

from users.mixins import SmartPermissionRequiredMixin
from real_estate.models import (
    PropertyContract, PropertyUnit, RealEstateProject, ContractCoOwner, RealEstateBroker, UnitBooking
)
from real_estate.services.clearance_service import ContractDebtClearanceService
from real_estate.services.booking_service import UnitBookingService, BookingValidationError
from customer.models import Customer
from financial.models.currency import Currency
from financial.models.chart_of_accounts import ChartOfAccounts


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
        installment_items = list(contract.installment_plan.items.all().order_by('installment_number')) if contract.installment_plan else []
        milestone_links_map = {
            link.installment_item_id: link
            for link in contract.milestone_installment_links.select_related('milestone_activity').all()
        }
        for it in installment_items:
            it.milestone_link = milestone_links_map.get(it.id)
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

        if contract.status in ['ACTIVE', 'COMPLETED'] and contract.unit.status not in ['DELIVERED', 'DELIVERED_DEEMED']:
            header_buttons.append({
                'url': f"{reverse('real_estate:handover_create')}?contract_id={contract.pk}",
                'label': _('تحرير محضر تسليم الوحدة'),
                'icon': 'fa-key',
                'class': 'btn-outline-warning'
            })

        survey_adjustments = contract.survey_adjustments.all()
        payment_accounts = ChartOfAccounts.objects.filter(is_active=True).filter(
            Q(code__startswith='111') | Q(code__startswith='1020') | Q(is_cash_account=True) | Q(is_bank_account=True)
        ).order_by('code')
        resale_refunds = contract.resale_refunds.select_related('unit', 'customer').all()
        can_terminate = contract.status in ['ACTIVE', 'UNDER_APPROVAL']

        context = {
            'contract': contract,
            'co_owners': co_owners,
            'installment_items': installment_items,
            'commissions': commissions,
            'available_brokers': available_brokers,
            'survey_adjustments': survey_adjustments,
            'payment_accounts': payment_accounts,
            'resale_refunds': resale_refunds,
            'can_terminate': can_terminate,
            'breadcrumb_items': breadcrumb_items,
            'header_buttons': header_buttons,
            'active_menu': 'real_estate',
            'active_submenu': 'contracts',
        }
        return render(request, 'real_estate/contract_detail.html', context)


class ContractSurveyAdjustmentView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تسجيل وتنفيذ تسوية الرفع المساحي الفعلي المعتمد للوحدة (As-Built Survey Adjustment)
    """
    permission_required = 'real_estate.change_propertycontract'

    def post(self, request, pk):
        contract = get_object_or_404(PropertyContract, pk=pk)
        actual_area_str = request.POST.get('actual_area', '').strip()
        survey_report_ref = request.POST.get('survey_report_reference', '').strip() or f"SURVEY-{contract.unit.unit_code}"
        survey_date_str = request.POST.get('survey_date', '').strip()
        tolerance_rate_str = request.POST.get('tolerance_percentage', '5.00').strip()
        execute_now = request.POST.get('execute_now') in ['true', '1', 'True', True]

        if not actual_area_str:
            messages.error(request, _("المساحة الفعلية المعتمدة بالرفع المساحي إلزامية."))
            return redirect('real_estate:contract_detail', pk=contract.pk)

        try:
            actual_area = Decimal(actual_area_str)
            tolerance_rate = Decimal(tolerance_rate_str or '5.00')
        except (ValueError, TypeError, InvalidOperation):
            messages.error(request, _("قيمة المساحة أو نسبة السماح غير صالحة."))
            return redirect('real_estate:contract_detail', pk=contract.pk)

        from datetime import datetime as dt
        if survey_date_str:
            try:
                survey_date = dt.strptime(survey_date_str, '%Y-%m-%d').date()
            except Exception:
                survey_date = timezone.localdate()
        else:
            survey_date = timezone.localdate()

        from real_estate.services.survey_variance_service import SurveyVarianceService
        try:
            adj = SurveyVarianceService.calculate_and_create_adjustment(
                contract=contract,
                surveyed_gross_area=actual_area,
                tolerance_percentage=tolerance_rate,
                notes=f"مرجع تقرير الرفع المساحي: {survey_report_ref} - تاريخ الرفع: {survey_date}",
                user=request.user,
            )
            if execute_now:
                if adj.status == adj.AdjustmentStatus.DRAFT:
                    adj.status = adj.AdjustmentStatus.APPROVED
                    adj.approved_by = request.user
                    adj.save(update_fields=['status', 'approved_by', 'updated_at'])
                adj = SurveyVarianceService.execute_adjustment(adj, user=request.user)
                messages.success(request, _("تم تسجيل وتنفيذ تسوية الرفع المساحي وتعديل رصيد العقد بنجاح."))
            else:
                messages.success(request, _("تم تسجيل تسوية الرفع المساحي بنجاح برقم %(ref)s وحفظها بانتظار الاعتماد.") % {'ref': adj.adjustment_number})
        except Exception as err:
            messages.error(request, _("حدث خطأ أثناء معالجة تسوية الرفع المساحي: %(err)s") % {'err': str(err)})

        return redirect('real_estate:contract_detail', pk=contract.pk)


class ContractTerminationView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    فسخ العقد العقاري وإعادة طرح الوحدة للبيع (Contract Rescission & Resale Lifecycle)
    """
    permission_required = 'real_estate.change_propertycontract'

    def post(self, request, pk):
        contract = get_object_or_404(PropertyContract, pk=pk)
        reason = request.POST.get('reason', '').strip()
        if not reason:
            messages.error(request, _('يرجى توضيح سبب فسخ العقد.'))
            return redirect('real_estate:contract_detail', pk=pk)

        penalty_raw = request.POST.get('penalty_amount', '0')
        try:
            penalty_amount = Decimal(str(penalty_raw))
        except Exception:
            penalty_amount = Decimal('0.00')

        disposition = request.POST.get('disposition', 'RESALE_CONTINGENT')
        refund_now = (disposition == 'IMMEDIATE_REFUND')
        payment_account_id = request.POST.get('payment_account_id')
        payment_account = ChartOfAccounts.objects.filter(pk=payment_account_id).first() if payment_account_id else None

        from real_estate.services.contract_service import PropertyContractService
        try:
            result = PropertyContractService.terminate_contract(
                contract_id=contract.id,
                reason=reason,
                penalty_amount=penalty_amount,
                refund_now=refund_now,
                payment_account=payment_account,
                user=request.user
            )
            messages.success(request, _('تم فسخ العقد بنجاح وتحرير الوحدة العقارية وإعادتها لحالة متاح للبيع.'))
        except Exception as e:
            messages.error(request, _('فشل فسخ العقد: %(err)s') % {'err': str(e)})

        return redirect('real_estate:contract_detail', pk=pk)


class ContractCreateView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    إبرام عقد بيع رسمي جديد أو تحويل استمارة حجز معتمدة إلى تعاقد نهائي
    """
    permission_required = 'real_estate.add_propertycontract'

    def get(self, request):
        booking_id = request.GET.get('booking_id')
        selected_booking = None
        if booking_id:
            selected_booking = get_object_or_404(
                UnitBooking.objects.select_related('customer', 'unit__project', 'currency'),
                pk=booking_id
            )

        customers = Customer.objects.filter(is_active=True).order_by('name')
        if selected_booking:
            available_units = PropertyUnit.objects.filter(is_active=True).filter(
                Q(status=PropertyUnit.UnitStatus.AVAILABLE) | Q(id=selected_booking.unit_id)
            ).select_related('project')
        else:
            available_units = PropertyUnit.objects.filter(is_active=True, status=PropertyUnit.UnitStatus.AVAILABLE).select_related('project')

        currencies = Currency.objects.all()
        payment_accounts = ChartOfAccounts.objects.filter(
            is_active=True,
            is_leaf=True,
            account_type__category='asset',
            code__startswith='111'
        )
        from django.contrib.auth import get_user_model
        User = get_user_model()
        brokers = RealEstateBroker.objects.filter(is_active=True)
        specialists = User.objects.filter(is_active=True).only('id', 'first_name', 'last_name', 'username')

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
            'payment_accounts': payment_accounts,
            'brokers': brokers,
            'specialists': specialists,
            'selected_booking': selected_booking,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 'real_estate',
            'active_submenu': 'contracts',
        }
        return render(request, 'real_estate/contract_form.html', context)

    def post(self, request):
        booking_id = request.POST.get('booking_id')
        customer_id = request.POST.get('customer')
        unit_id = request.POST.get('unit')
        contract_price = Decimal(str(request.POST.get('final_contract_price', '0.00') or '0.00'))
        down_payment = Decimal(str(request.POST.get('down_payment', '0.00') or '0.00'))
        
        # تحويل وضبط تواريخ التعاقد والتسليم بدقة
        contract_date_raw = request.POST.get('contract_date')
        if contract_date_raw:
            if isinstance(contract_date_raw, str):
                try:
                    from datetime import datetime as dt
                    contract_date = dt.strptime(contract_date_raw, '%Y-%m-%d').date()
                except Exception:
                    contract_date = timezone.localdate()
            else:
                contract_date = contract_date_raw
        else:
            contract_date = timezone.localdate()

        delivery_date_raw = request.POST.get('delivery_date')
        if delivery_date_raw:
            if isinstance(delivery_date_raw, str):
                try:
                    from datetime import datetime as dt
                    delivery_date = dt.strptime(delivery_date_raw, '%Y-%m-%d').date()
                except Exception:
                    import datetime as dt_mod
                    delivery_date = contract_date + dt_mod.timedelta(days=730)
            else:
                delivery_date = delivery_date_raw
        else:
            import datetime as dt_mod
            delivery_date = contract_date + dt_mod.timedelta(days=730)

        currency_id = request.POST.get('currency') or None
        payment_account_id = request.POST.get('payment_account')
        contract_tax_structure = request.POST.get('contract_tax_structure') or PropertyContract.ContractTaxStructure.UNIFIED_SPA
        primary_owner_share_raw = request.POST.get('primary_owner_share')
        primary_owner_share = Decimal(str(primary_owner_share_raw)) if primary_owner_share_raw else None

        # استخراج خيارات الأقساط والوسيط والتجهيزات
        number_of_installments_raw = request.POST.get('number_of_installments')
        number_of_installments = int(number_of_installments_raw) if number_of_installments_raw and str(number_of_installments_raw).isdigit() else None
        installment_frequency = request.POST.get('installment_frequency') or 'QUARTERLY'
        first_installment_date_raw = request.POST.get('first_installment_date')
        first_installment_date = None
        if first_installment_date_raw:
            try:
                from datetime import datetime as dt
                first_installment_date = dt.strptime(first_installment_date_raw, '%Y-%m-%d').date()
            except Exception:
                first_installment_date = None

        broker_id = request.POST.get('broker') or request.POST.get('broker_id')
        broker_commission_rate_raw = request.POST.get('broker_commission_rate')
        broker_commission_rate = Decimal(str(broker_commission_rate_raw)) if broker_commission_rate_raw else None
        broker = RealEstateBroker.objects.filter(pk=broker_id, is_active=True).first() if broker_id else None

        # التجهيزات والملحقات
        parking_slot_code = request.POST.get('parking_slot_code', '').strip()
        parking_slot_price = Decimal(str(request.POST.get('parking_slot_price', '0.00') or '0.00'))
        storage_locker_code = request.POST.get('storage_locker_code', '').strip()
        storage_locker_price = Decimal(str(request.POST.get('storage_locker_price', '0.00') or '0.00'))
        finishing_meter_rate = Decimal(str(request.POST.get('finishing_meter_rate', '0.00') or '0.00'))
        finishing_total_amount = Decimal(str(request.POST.get('finishing_total_amount', '0.00') or '0.00'))
        utilities_deposit_amount = Decimal(str(request.POST.get('utilities_deposit_amount', '0.00') or '0.00'))
        maintenance_deposit_amount = Decimal(str(request.POST.get('maintenance_deposit_amount', '0.00') or '0.00'))

        # مسؤولو المبيعات
        from django.contrib.auth import get_user_model
        User = get_user_model()
        call_specialist_id = request.POST.get('call_specialist')
        visit_specialist_id = request.POST.get('visit_specialist')
        site_specialist_id = request.POST.get('site_specialist')
        call_specialist = User.objects.filter(pk=call_specialist_id).first() if call_specialist_id else None
        visit_specialist = User.objects.filter(pk=visit_specialist_id).first() if visit_specialist_id else None
        site_specialist = User.objects.filter(pk=site_specialist_id).first() if site_specialist_id else None

        # استخراج بيانات الشركاء المتضامنين (co-owners batch)
        co_owners_data = []
        raw_co_owners = request.POST.get('co_owners') or request.POST.get('co_owners_data')
        if raw_co_owners:
            import json
            try:
                if isinstance(raw_co_owners, str):
                    co_owners_data = json.loads(raw_co_owners)
                elif isinstance(raw_co_owners, list):
                    co_owners_data = raw_co_owners
            except Exception:
                pass
        if not co_owners_data:
            co_owner_ids = request.POST.getlist('co_owner_id') or request.POST.getlist('co_owner_id[]')
            co_owner_shares = request.POST.getlist('co_owner_share') or request.POST.getlist('share_percentage') or request.POST.getlist('co_owner_share[]')
            poa_numbers = request.POST.getlist('power_of_attorney_number') or request.POST.getlist('power_of_attorney_number[]')
            registry_offices = request.POST.getlist('issuing_registry_office') or request.POST.getlist('issuing_registry_office[]')
            capacities = request.POST.getlist('representation_capacity') or request.POST.getlist('representation_capacity[]')

            if co_owner_ids and co_owner_shares:
                for idx, (cid, cshare) in enumerate(zip(co_owner_ids, co_owner_shares)):
                    if cid and cshare:
                        poa = poa_numbers[idx].strip() if idx < len(poa_numbers) else ''
                        reg = registry_offices[idx].strip() if idx < len(registry_offices) else ''
                        cap = capacities[idx].strip() if idx < len(capacities) else ''
                        co_owners_data.append({
                            'customer_id': cid,
                            'share_percentage': cshare,
                            'power_of_attorney_number': poa,
                            'issuing_registry_office': reg,
                            'representation_capacity': cap,
                        })

        currency = Currency.objects.filter(pk=currency_id).first() if currency_id else None
        payment_account = ChartOfAccounts.objects.filter(pk=payment_account_id).first() if payment_account_id else None

        # مسار تحويل استمارة الحجز إلى تعاقد عبر محرك الخدمات المركزي
        if booking_id:
            booking = get_object_or_404(
                UnitBooking.objects.select_related('customer', 'unit__project'),
                pk=booking_id
            )
            if booking.status != UnitBooking.BookingStatus.ACTIVE:
                messages.error(request, _('لا يمكن تحويل استمارة حجز غير نشطة إلى عقد (الحالة الحالية: %(st)s).') % {'st': booking.get_status_display()})
                return redirect('real_estate:booking_detail', pk=booking.pk)

            if primary_owner_share is not None and (primary_owner_share < Decimal('0.00') or primary_owner_share > Decimal('100.00')):
                messages.error(request, _('نسبة ملكية العميل الرئيسي يجب أن تكون بين 0.00% و 100.00%.'))
                return redirect('real_estate:booking_detail', pk=booking.pk)

            if not (booking.is_confirmed_audit or booking.is_legacy_pre_audit or booking.audit_bypassed):
                messages.error(request, _('لا يمكن تحويل الحجز لعقد: الحجز لم يحصل على الاعتماد المالي والرقابي الثنائي، ولم يتم استثناؤه إدارياً.'))
                return redirect('real_estate:booking_detail', pk=booking.pk)

            try:
                contract = UnitBookingService.convert_booking_to_contract(
                    booking_id=booking.id,
                    user=request.user,
                    final_contract_price=contract_price if contract_price > Decimal('0.00') else None,
                    down_payment=down_payment if down_payment > Decimal('0.00') else None,
                    contract_date=contract_date,
                    delivery_date=delivery_date,
                    currency=currency,
                    payment_account=payment_account,
                    contract_tax_structure=contract_tax_structure,
                    primary_owner_share=primary_owner_share,
                    co_owners_data=co_owners_data if co_owners_data else None,
                    number_of_installments=number_of_installments,
                    installment_frequency=installment_frequency,
                    first_installment_date=first_installment_date,
                    broker=broker,
                    broker_commission_rate=broker_commission_rate,
                    parking_slot_code=parking_slot_code,
                    parking_slot_price=parking_slot_price,
                    storage_locker_code=storage_locker_code,
                    storage_locker_price=storage_locker_price,
                    finishing_meter_rate=finishing_meter_rate,
                    finishing_total_amount=finishing_total_amount,
                    utilities_deposit_amount=utilities_deposit_amount,
                    maintenance_deposit_amount=maintenance_deposit_amount,
                    call_specialist=call_specialist,
                    visit_specialist=visit_specialist,
                    site_specialist=site_specialist,
                )
                messages.success(request, _('تم تحويل الحجز وإبرام العقد العقاري بنجاح برقم: %(num)s') % {'num': contract.contract_number})
                return redirect('real_estate:contract_detail', pk=contract.pk)
            except (BookingValidationError, ValidationError) as b_err:
                messages.error(request, str(b_err))
                return redirect('real_estate:booking_detail', pk=booking.pk)
            except Exception as err:
                messages.error(request, _('حدث خطأ أثناء تحويل الحجز: %(err)s') % {'err': str(err)})
                return redirect('real_estate:booking_detail', pk=booking.pk)

        # مسار إبرام عقد جديد مباشر بدون حجز مسبق
        if not customer_id or not unit_id or contract_price <= Decimal('0.00'):
            messages.error(request, _('يرجى اختيار العميل والوحدة وتحديد القيمة التعاقدية الصحيحة.'))
            return redirect('real_estate:contract_create')

        customer = get_object_or_404(Customer, pk=customer_id)
        unit = get_object_or_404(PropertyUnit, pk=unit_id)

        if unit.status != PropertyUnit.UnitStatus.AVAILABLE:
            messages.error(request, _('الوحدة المختارة غير متاحة للتعاقد حالياً.'))
            return redirect('real_estate:contract_create')

        p_share = Decimal(str(primary_owner_share)).quantize(Decimal('0.01')) if primary_owner_share is not None else Decimal('100.00')
        if p_share < Decimal('0.00') or p_share > Decimal('100.00'):
            messages.error(request, _('نسبة ملكية العميل الرئيسي يجب أن تكون بين 0.00% و 100.00%.'))
            return redirect('real_estate:contract_create')

        co_share_sum = sum(
            Decimal(str(item.get('share_percentage', '0'))).quantize(Decimal('0.01'))
            for item in co_owners_data
        )
        if p_share + co_share_sum != Decimal('100.00'):
            messages.error(request, _('إجمالي نسب الملكية في العقد يجب أن يساوي 100.00% بالضبط.'))
            return redirect('real_estate:contract_create')

        import uuid
        import datetime as dt_module
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
            currency=currency or getattr(unit.project, 'currency', None),
            contract_tax_structure=contract_tax_structure,
            primary_owner_share=p_share,
            parking_slot_code=parking_slot_code,
            parking_slot_price=parking_slot_price,
            storage_locker_code=storage_locker_code,
            storage_locker_price=storage_locker_price,
            finishing_meter_rate=finishing_meter_rate,
            finishing_total_amount=finishing_total_amount,
            utilities_deposit_amount=utilities_deposit_amount,
            maintenance_deposit_amount=maintenance_deposit_amount,
            call_specialist=call_specialist,
            visit_specialist=visit_specialist,
            site_specialist=site_specialist,
            created_by=request.user
        )

        if co_owners_data:
            from real_estate.services.contract_service import PropertyContractService
            PropertyContractService.sync_contract_ownership(
                contract_id=contract.id,
                co_owners_data=co_owners_data,
                primary_owner_share=p_share,
                user=request.user
            )

        contract.refresh_from_db()
        contract.validate_ownership_integrity()

        # إثبات تحصيل مقدم التعاقد المباشر محاسبياً
        dp_collected = False
        if down_payment > Decimal('0.00') and payment_account:
            from real_estate.services.accounting_service import RealEstateAccountingService
            RealEstateAccountingService.post_direct_contract_down_payment(
                contract=contract,
                payment_account=payment_account,
                user=request.user,
                down_payment=down_payment,
            )
            dp_collected = True

        # توليد خطة الأقساط التعاقدية
        from sale.models.installments import InstallmentPlan, InstallmentItem
        tot_price = contract.final_contract_price
        c_date = contract.contract_date if isinstance(contract.contract_date, dt_module.date) else timezone.localdate()
        num_inst = number_of_installments if (number_of_installments and number_of_installments > 0) else 4
        freq = installment_frequency or 'QUARTERLY'
        start_d = first_installment_date or c_date
        months_step = {
            'MONTHLY': 1,
            'QUARTERLY': 3,
            'SEMI_ANNUAL': 6,
            'ANNUAL': 12,
        }.get(freq, 3)

        if not dp_collected and (contract.down_payment or Decimal('0.00')) > Decimal('0.00'):
            # في حال عدم تحصيل المقدم محاسبياً، يُمثل المقدم صراحة كالتزام مستحق في جدول السداد
            uncollected_dp = contract.down_payment
            rem_financed = max(Decimal('0.00'), tot_price - uncollected_dp)
            plan = InstallmentPlan.objects.create(
                customer=contract.customer,
                total_principal=tot_price,
                total_markup=Decimal('0.00'),
                total_amount=tot_price,
                down_payment=Decimal('0.00'),
                number_of_installments=num_inst + 1,
                frequency=freq,
                start_date=c_date,
                status=InstallmentPlan.PlanStatus.DRAFT,
                created_by=request.user,
            )
            # 1. بند استحقاق دفعة المقدم المعلقة للتحصيل
            InstallmentItem.objects.create(
                plan=plan,
                installment_number=1,
                trigger_type=InstallmentItem.TriggerType.DATE_BASED,
                due_date=c_date,
                principal_amount=uncollected_dp,
                interest_amount=Decimal('0.00'),
                total_amount=uncollected_dp,
            )
            # 2. بنود الأقساط الدورية المتبقية
            if rem_financed > Decimal('0.00'):
                base_inst_val = (rem_financed / Decimal(num_inst)).quantize(Decimal('0.01'))
                running_sum = Decimal('0.00')
                inst_due = start_d
                for idx in range(1, num_inst + 1):
                    if idx == num_inst:
                        item_val = rem_financed - running_sum
                    else:
                        item_val = base_inst_val
                        running_sum += item_val
                    InstallmentItem.objects.create(
                        plan=plan,
                        installment_number=idx + 1,
                        trigger_type=InstallmentItem.TriggerType.DATE_BASED,
                        due_date=inst_due,
                        principal_amount=item_val,
                        interest_amount=Decimal('0.00'),
                        total_amount=item_val,
                    )
                    y = inst_due.year + (inst_due.month + months_step - 1) // 12
                    m = (inst_due.month + months_step - 1) % 12 + 1
                    d = min(inst_due.day, 28)
                    inst_due = dt_module.date(y, m, d)

            contract.installment_plan = plan
            contract.save(update_fields=['installment_plan', 'updated_at'])
            plan.status = InstallmentPlan.PlanStatus.ACTIVE
            plan.save(update_fields=['status'])
        else:
            net_financed = max(Decimal('0.00'), tot_price - (contract.down_payment or Decimal('0.00')))
            if net_financed <= Decimal('0.00'):
                plan = InstallmentPlan.objects.create(
                    customer=contract.customer,
                    total_principal=Decimal('0.00'),
                    total_markup=Decimal('0.00'),
                    total_amount=tot_price,
                    down_payment=tot_price,
                    number_of_installments=1,
                    frequency='CUSTOM',
                    start_date=c_date,
                    status=InstallmentPlan.PlanStatus.COMPLETED,
                    created_by=request.user,
                )
                InstallmentItem.objects.create(
                    plan=plan,
                    installment_number=1,
                    trigger_type=InstallmentItem.TriggerType.DATE_BASED,
                    due_date=c_date,
                    principal_amount=Decimal('0.00'),
                    interest_amount=Decimal('0.00'),
                    total_amount=Decimal('0.00'),
                    paid_amount=Decimal('0.00'),
                )
                contract.installment_plan = plan
                contract.save(update_fields=['installment_plan', 'updated_at'])
            else:
                plan = InstallmentPlan.objects.create(
                    customer=contract.customer,
                    total_principal=net_financed,
                    total_markup=Decimal('0.00'),
                    total_amount=tot_price,
                    down_payment=contract.down_payment or Decimal('0.00'),
                    number_of_installments=num_inst,
                    frequency=freq,
                    start_date=start_d,
                    status=InstallmentPlan.PlanStatus.DRAFT,
                    created_by=request.user,
                )
                base_inst_val = (net_financed / Decimal(num_inst)).quantize(Decimal('0.01'))
                running_sum = Decimal('0.00')
                inst_due = start_d
                for idx in range(1, num_inst + 1):
                    if idx == num_inst:
                        item_val = net_financed - running_sum
                    else:
                        item_val = base_inst_val
                        running_sum += item_val
                    InstallmentItem.objects.create(
                        plan=plan,
                        installment_number=idx,
                        trigger_type=InstallmentItem.TriggerType.DATE_BASED,
                        due_date=inst_due,
                        principal_amount=item_val,
                        interest_amount=Decimal('0.00'),
                        total_amount=item_val,
                    )
                    y = inst_due.year + (inst_due.month + months_step - 1) // 12
                    m = (inst_due.month + months_step - 1) % 12 + 1
                    d = min(inst_due.day, 28)
                    inst_due = dt_module.date(y, m, d)

                contract.installment_plan = plan
                contract.save(update_fields=['installment_plan', 'updated_at'])
                plan.status = InstallmentPlan.PlanStatus.ACTIVE
                plan.save(update_fields=['status'])

        # ربط الوسيط العقاري إن وُجد
        if broker:
            from real_estate.services.broker_service import BrokerCommissionService
            BrokerCommissionService.assign_broker_to_contract(
                contract=contract,
                broker=broker,
                commission_rate=broker_commission_rate,
                user=request.user,
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

