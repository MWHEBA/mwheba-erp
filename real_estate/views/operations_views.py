# -*- coding: utf-8 -*-
"""
Operations & Facilities Views - شاشات وعمليات المرافق، الإنذارات، الشركاء، وتبديل الوحدات
MWHEBA ERP — Real Estate Maintenance Escrow, Legal Notices, Landowner Partnerships & Unit Swaps
"""
from decimal import Decimal
from datetime import datetime, date
from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.core.paginator import Paginator
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q, Sum
from django.utils import timezone

from users.mixins import SmartPermissionRequiredMixin
from real_estate.models import (
    MaintenanceFundOperation,
    BuildingFacilitySubledger,
    LegalNotice,
    LandownerPartnership,
    LandownerUnitAllocation,
    UnitSwapRecord,
    PropertyContract,
    PropertyUnit,
    RealEstateProject,
)
from real_estate.services.facility_service import BuildingFacilityService
from real_estate.services.legal_escalation_service import LegalEscalationPipeline
from real_estate.services.swap_service import UnitSwapService
from sale.models.installments import InstallmentItem


# ==============================================================================
# 1. صندوق وديعة الصيانة والمرافق (Facility Maintenance Fund)
# ==============================================================================

class MaintenanceFundListView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    سجل عمليات وصندوق وديعة صيانة المرافق والتحصيلات والعوائد البنكية
    """
    permission_required = 'real_estate.view_maintenancefundoperation'

    def get(self, request):
        search_query = request.GET.get('q', '').strip()
        type_filter = request.GET.get('type', '').strip()
        project_id = request.GET.get('project', '').strip()

        qs = MaintenanceFundOperation.objects.select_related(
            'subledger__project', 'contract__customer', 'unit'
        ).order_by('-operation_date', '-id')

        if search_query:
            qs = qs.filter(
                Q(operation_number__icontains=search_query) |
                Q(description__icontains=search_query) |
                Q(subledger__project__name__icontains=search_query) |
                Q(contract__contract_number__icontains=search_query) |
                Q(unit__unit_code__icontains=search_query)
            )

        if type_filter:
            qs = qs.filter(operation_type=type_filter)

        if project_id:
            qs = qs.filter(subledger__project_id=project_id)

        paginator = Paginator(qs, 20)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        total_operations = MaintenanceFundOperation.objects.count()
        total_deposits = MaintenanceFundOperation.objects.filter(
            operation_type=MaintenanceFundOperation.OperationType.DEPOSIT_COLLECTION
        ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')

        total_yield = MaintenanceFundOperation.objects.filter(
            operation_type=MaintenanceFundOperation.OperationType.BANK_YIELD
        ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')

        total_expenses = MaintenanceFundOperation.objects.filter(
            operation_type=MaintenanceFundOperation.OperationType.FACILITY_EXPENSE
        ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('المرافق والعمليات'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-cogs'},
            {'title': _('صندوق وديعة الصيانة'), 'active': True}
        ]

        projects = RealEstateProject.objects.filter(is_archived=False).order_by('name')
        active_contracts = PropertyContract.objects.filter(
            status__in=[PropertyContract.ContractStatus.ACTIVE, PropertyContract.ContractStatus.COMPLETED]
        ).select_related('customer', 'unit__project').order_by('contract_number')

        context = {
            'page_obj': page_obj,
            'operations': page_obj.object_list,
            'projects': projects,
            'contracts': active_contracts,
            'search_query': search_query,
            'selected_type': type_filter,
            'selected_project': project_id,
            'type_choices': MaintenanceFundOperation.OperationType.choices,
            'expense_categories': MaintenanceFundOperation.ExpenseCategory.choices,
            'total_operations': total_operations,
            'total_deposits': total_deposits,
            'total_yield': total_yield,
            'total_expenses': total_expenses,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_service',
            'active_submenu': 'maintenance_fund',
        }
        return render(request, 'real_estate/maintenance_fund_list.html', context)


class MaintenanceFundDepositCreateView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تحصيل وإيداع وديعة صيانة من العميل لصالح صندوق المشروع
    """
    permission_required = 'real_estate.add_maintenancefundoperation'

    def post(self, request):
        contract_id = request.POST.get('contract')
        contract = get_object_or_404(PropertyContract.objects.select_related('unit__project'), pk=contract_id)
        project = contract.unit.project

        try:
            amount = Decimal(request.POST.get('amount', '0') or '0')
        except Exception:
            messages.error(request, _('يرجى التحقق من صحة مبلغ وديعة الصيانة.'))
            return redirect('real_estate:facility_list')

        description = request.POST.get('description', '').strip()
        op_date_str = request.POST.get('operation_date')
        op_date = None
        if op_date_str:
            try:
                op_date = datetime.strptime(op_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        try:
            subledger = BuildingFacilityService.get_or_create_subledger(project=project, user=request.user)
            op = BuildingFacilityService.record_deposit_collection(
                subledger=subledger,
                contract=contract,
                amount=amount,
                user=request.user,
                operation_date=op_date,
                description=description
            )
            messages.success(request, _(f'تم تحصيل وإيداع وديعة الصيانة {amount:,.2f} ج.م للوحدة {contract.unit.unit_code} بنجاح برقم {op.operation_number}.'))
        except ValidationError as e:
            error_msg = e.message if hasattr(e, 'message') else str(e)
            messages.error(request, error_msg)
        except Exception as e:
            messages.error(request, str(e))

        return redirect('real_estate:facility_list')


class MaintenanceFundYieldCreateView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    توزيع عائد استثمار وديعة الصيانة البنكي (معفى من الضرائب دفترياً)
    """
    permission_required = 'real_estate.add_maintenancefundoperation'

    def post(self, request):
        project_id = request.POST.get('project')
        project = get_object_or_404(RealEstateProject, pk=project_id)

        try:
            yield_amount = Decimal(request.POST.get('yield_amount', '0') or '0')
            yield_rate = Decimal(request.POST.get('yield_rate', '0') or '0')
        except Exception:
            messages.error(request, _('يرجى التحقق من صحة مبلغ العائد ومعدل الفائدة.'))
            return redirect('real_estate:facility_list')

        certificate_number = request.POST.get('certificate_number', '').strip()
        description = request.POST.get('description', '').strip()

        period_start = None
        period_end = None
        p_start_str = request.POST.get('period_start')
        p_end_str = request.POST.get('period_end')
        if p_start_str:
            try:
                period_start = datetime.strptime(p_start_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        if p_end_str:
            try:
                period_end = datetime.strptime(p_end_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        try:
            subledger = BuildingFacilityService.get_or_create_subledger(project=project, user=request.user)
            op = BuildingFacilityService.post_bank_yield(
                subledger=subledger,
                yield_amount=yield_amount,
                certificate_number=certificate_number,
                yield_rate=yield_rate,
                period_start=period_start,
                period_end=period_end,
                user=request.user,
                description=description
            )
            messages.success(request, _(f'تم إثبات العائد البنكي بمبلغ {yield_amount:,.2f} ج.م في صندوق صيانة {project.name} بنجاح برقم {op.operation_number}.'))
        except ValidationError as e:
            error_msg = e.message if hasattr(e, 'message') else str(e)
            messages.error(request, error_msg)
        except Exception as e:
            messages.error(request, str(e))

        return redirect('real_estate:facility_list')


class MaintenanceFundExpenseCreateView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    صرف مصاريف صيانة وتشغيل مرافق من صندوق وديعة الصيانة
    """
    permission_required = 'real_estate.add_maintenancefundoperation'

    def post(self, request):
        project_id = request.POST.get('project')
        project = get_object_or_404(RealEstateProject, pk=project_id)

        try:
            expense_amount = Decimal(request.POST.get('expense_amount', '0') or '0')
        except Exception:
            messages.error(request, _('يرجى التحقق من صحة مبلغ مصروفات الصيانة.'))
            return redirect('real_estate:facility_list')

        expense_category = request.POST.get('expense_category', MaintenanceFundOperation.ExpenseCategory.OTHER)
        description = request.POST.get('description', '').strip()

        op_date_str = request.POST.get('operation_date')
        op_date = None
        if op_date_str:
            try:
                op_date = datetime.strptime(op_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        try:
            subledger = BuildingFacilityService.get_or_create_subledger(project=project, user=request.user)
            op = BuildingFacilityService.record_facility_expense(
                subledger=subledger,
                expense_amount=expense_amount,
                expense_category=expense_category,
                description=description,
                user=request.user,
                operation_date=op_date
            )
            messages.success(request, _(f'تم صرف مصروفات الصيانة بمبلغ {expense_amount:,.2f} ج.م برقم {op.operation_number}.'))
        except ValidationError as e:
            error_msg = e.message if hasattr(e, 'message') else str(e)
            messages.error(request, error_msg)
        except Exception as e:
            messages.error(request, str(e))

        return redirect('real_estate:facility_list')


# ==============================================================================
# 2. الإنذارات القانونية ومتابعة التعثر (Legal Notices & Escalation)
# ==============================================================================

class LegalNoticeListView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    سجل الإنذارات والمتابعة القانونية للمتعثرين والتصعيد للتسليم الحكمي أو الفسخ
    """
    permission_required = 'real_estate.view_legalnotice'

    def get(self, request):
        search_query = request.GET.get('q', '').strip()
        status_filter = request.GET.get('status', '').strip()
        stage_filter = request.GET.get('stage', '').strip()
        channel_filter = request.GET.get('channel', '').strip()

        qs = LegalNotice.objects.select_related(
            'customer', 'contract__unit__project', 'installment_item'
        ).order_by('-created_at', '-id')

        if search_query:
            qs = qs.filter(
                Q(notice_number__icontains=search_query) |
                Q(customer__name__icontains=search_query) |
                Q(contract__contract_number__icontains=search_query) |
                Q(contract__unit__unit_code__icontains=search_query)
            )

        if status_filter:
            qs = qs.filter(status=status_filter)

        if stage_filter:
            qs = qs.filter(stage=stage_filter)

        if channel_filter:
            qs = qs.filter(channel=channel_filter)

        paginator = Paginator(qs, 20)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        total_notices = LegalNotice.objects.count()
        total_demanded = LegalNotice.objects.aggregate(s=Sum('total_demanded_amount'))['s'] or Decimal('0.00')
        served_count = LegalNotice.objects.filter(status='SERVED').count()
        cured_count = LegalNotice.objects.filter(status='CURED').count()

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('المرافق والعمليات'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-cogs'},
            {'title': _('الإنذارات القانونية'), 'active': True}
        ]

        header_buttons = []
        if request.user.has_perm('real_estate.add_legalnotice') or request.user.is_superuser:
            header_buttons.append({
                'url': reverse('real_estate:legal_create'),
                'label': _('إصدار إنذار قانوني'),
                'icon': 'fa-plus',
                'class': 'btn-primary'
            })

        context = {
            'page_obj': page_obj,
            'notices': page_obj.object_list,
            'search_query': search_query,
            'selected_status': status_filter,
            'selected_stage': stage_filter,
            'selected_channel': channel_filter,
            'status_choices': LegalNotice.NoticeStatus.choices,
            'stage_choices': LegalNotice.EscalationStage.choices,
            'channel_choices': LegalNotice.NoticeChannel.choices,
            'total_notices': total_notices,
            'total_demanded': total_demanded,
            'served_count': served_count,
            'cured_count': cured_count,
            'breadcrumb_items': breadcrumb_items,
            'header_buttons': header_buttons,
            'active_menu': 're_service',
            'active_submenu': 'legal_notices',
        }
        return render(request, 'real_estate/legal_notice_list.html', context)


class LegalNoticeCreateView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    إصدار إنذار قانوني رسمي أو إخطار تسليم حكمي ضد عميل متعثر
    """
    permission_required = 'real_estate.add_legalnotice'

    def get(self, request):
        contracts = PropertyContract.objects.filter(
            status=PropertyContract.ContractStatus.ACTIVE
        ).select_related('customer', 'unit__project').order_by('contract_number')

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('المرافق والعمليات'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-cogs'},
            {'title': _('الإنذارات القانونية'), 'url': reverse('real_estate:legal_list')},
            {'title': _('إصدار إنذار جديد'), 'active': True}
        ]

        context = {
            'contracts': contracts,
            'stage_choices': LegalNotice.EscalationStage.choices,
            'channel_choices': LegalNotice.NoticeChannel.choices,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_service',
            'active_submenu': 'legal_notices',
        }
        return render(request, 'real_estate/legal_notice_form.html', context)

    def post(self, request):
        contract_id = request.POST.get('contract')
        contract = get_object_or_404(PropertyContract.objects.select_related('customer', 'unit'), pk=contract_id)

        stage = request.POST.get('stage', LegalNotice.EscalationStage.STAGE_3_FORMAL_DEMAND)
        channel = request.POST.get('channel', LegalNotice.NoticeChannel.COURT_BAILIFF)

        try:
            overdue_amount = Decimal(request.POST.get('overdue_amount', '0') or '0')
            penalty_amount = Decimal(request.POST.get('penalty_amount', '0') or '0')
            cure_deadline_days = int(request.POST.get('cure_deadline_days', '15') or '15')
        except Exception:
            messages.error(request, _('يرجى التحقق من صحة المبالغ والمهلة المحددة.'))
            return redirect('real_estate:legal_create')

        total_demanded = overdue_amount + penalty_amount
        cure_deadline_date = timezone.localdate() + timezone.timedelta(days=cure_deadline_days)
        legal_letter_text = request.POST.get('legal_letter_text', '').strip()

        notice = LegalNotice.objects.create(
            contract=contract,
            customer=contract.customer,
            stage=stage,
            channel=channel,
            overdue_amount=overdue_amount,
            penalty_amount=penalty_amount,
            total_demanded_amount=total_demanded,
            cure_deadline_days=cure_deadline_days,
            cure_deadline_date=cure_deadline_date,
            legal_letter_text=legal_letter_text,
            status=LegalNotice.NoticeStatus.SENT,
            sent_at=timezone.now(),
            created_by=request.user
        )

        messages.success(request, _(f'تم إصدار الإنذار القانوني {notice.notice_number} للعميل {contract.customer.name} بنجاح.'))
        return redirect('real_estate:legal_list')


class LegalNoticeActionView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تحديث موقف الإنذار القانوني (إثبات الإعلان الرسمي SERVED أو إثبات السداد CURED)
    """
    permission_required = 'real_estate.change_legalnotice'

    def post(self, request, pk):
        notice = get_object_or_404(LegalNotice, pk=pk)
        action_type = request.POST.get('action_type')

        if action_type == 'mark_served':
            notice.status = LegalNotice.NoticeStatus.SERVED
            notice.save(update_fields=['status', 'updated_at'])
            messages.success(request, _(f'تم إثبات إعلان الإنذار {notice.notice_number} رسمياً.'))
        elif action_type in ['mark_delivered', 'mark_cured']:
            notice.status = LegalNotice.NoticeStatus.DELIVERED
            notice.save(update_fields=['status', 'updated_at'])
            messages.success(request, _(f'تم إثبات استلام وتسليم الإنذار {notice.notice_number} بنجاح.'))
        else:
            messages.error(request, _('إجراء غير معروف.'))

        return redirect('real_estate:legal_list')


# ==============================================================================
# 3. مشاركات ملاك الأراضي وتخصيص الوحدات (Landowner Partnerships)
# ==============================================================================

class LandownerPartnershipListView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    سجل الشركاء وملاك الأراضي ونسب التطوير العقاري
    """
    permission_required = 'real_estate.view_landownerpartnership'

    def get(self, request):
        search_query = request.GET.get('q', '').strip()
        status_filter = request.GET.get('status', '').strip()

        qs = LandownerPartnership.objects.select_related(
            'project', 'customer', 'supplier'
        ).order_by('-contract_date', '-id')

        if search_query:
            qs = qs.filter(
                Q(partnership_number__icontains=search_query) |
                Q(partner_name__icontains=search_query) |
                Q(project__name__icontains=search_query)
            )

        if status_filter:
            qs = qs.filter(status=status_filter)

        paginator = Paginator(qs, 20)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        total_partnerships = LandownerPartnership.objects.count()
        total_land_valuation = LandownerPartnership.objects.aggregate(s=Sum('agreed_land_valuation'))['s'] or Decimal('0.00')

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('المرافق والعمليات'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-cogs'},
            {'title': _('الشركاء وملاك الأراضي'), 'active': True}
        ]

        header_buttons = []
        if request.user.has_perm('real_estate.add_landownerpartnership') or request.user.is_superuser:
            header_buttons.append({
                'url': reverse('real_estate:partnership_create'),
                'label': _('شراكة أرض جديدة'),
                'icon': 'fa-plus',
                'class': 'btn-primary'
            })

        context = {
            'page_obj': page_obj,
            'partnerships': page_obj.object_list,
            'search_query': search_query,
            'selected_status': status_filter,
            'status_choices': LandownerPartnership.PartnershipStatus.choices,
            'total_partnerships': total_partnerships,
            'total_land_valuation': total_land_valuation,
            'breadcrumb_items': breadcrumb_items,
            'header_buttons': header_buttons,
            'active_menu': 're_projects',
            'active_submenu': 'partnerships',
        }
        return render(request, 'real_estate/partnership_list.html', context)


class LandownerPartnershipCreateView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تسجيل عقد شراكة تطوير عقاري جديدة مع مالك أرض
    """
    permission_required = 'real_estate.add_landownerpartnership'

    def get(self, request):
        projects = RealEstateProject.objects.filter(is_archived=False).order_by('name')

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('المرافق والعمليات'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-cogs'},
            {'title': _('الشركاء وملاك الأراضي'), 'url': reverse('real_estate:partnership_list')},
            {'title': _('شراكة جديدة'), 'active': True}
        ]

        context = {
            'projects': projects,
            'type_choices': LandownerPartnership.PartnershipType.choices,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_projects',
            'active_submenu': 'partnerships',
        }
        return render(request, 'real_estate/partnership_form.html', context)

    def post(self, request):
        project_id = request.POST.get('project')
        project = get_object_or_404(RealEstateProject, pk=project_id)

        partner_name = request.POST.get('partner_name', '').strip()
        partner_national_id = request.POST.get('partner_national_id', '').strip()
        partner_phone = request.POST.get('partner_phone', '').strip()
        partnership_type = request.POST.get('partnership_type', LandownerPartnership.PartnershipType.UNIT_ALLOCATION)

        try:
            revenue_share = Decimal(request.POST.get('revenue_share_percentage', '0') or '0')
            land_area = Decimal(request.POST.get('land_area_sqm', '0') or '0')
            valuation = Decimal(request.POST.get('agreed_land_valuation', '0') or '0')
        except Exception:
            messages.error(request, _('يرجى التحقق من صحة النسب والمساحة والتقييم المالي للأرض.'))
            return redirect('real_estate:partnership_create')

        contract_date_str = request.POST.get('contract_date')
        contract_date = None
        if contract_date_str:
            try:
                contract_date = datetime.strptime(contract_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        terms_notes = request.POST.get('terms_notes', '').strip()

        partnership = LandownerPartnership.objects.create(
            project=project,
            partner_name=partner_name,
            partner_national_id=partner_national_id,
            partner_phone=partner_phone,
            partnership_type=partnership_type,
            revenue_share_percentage=revenue_share,
            land_area_sqm=land_area,
            agreed_land_valuation=valuation,
            contract_date=contract_date or timezone.localdate(),
            terms_notes=terms_notes,
            created_by=request.user
        )

        messages.success(request, _(f'تم تسجيل اتفاقية شراكة الأرض {partnership.partnership_number} بنجاح.'))
        return redirect('real_estate:partnership_detail', pk=partnership.pk)


class LandownerPartnershipDetailView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تفاصيل اتفاقية شراكة الأرض والوحدات المخصصة عيناً لمالك الأرض
    """
    permission_required = 'real_estate.view_landownerpartnership'

    def get(self, request, pk):
        partnership = get_object_or_404(
            LandownerPartnership.objects.select_related('project', 'customer', 'supplier'),
            pk=pk
        )

        allocations = partnership.unit_allocations.select_related('unit').order_by('-allocated_at')
        available_units = PropertyUnit.objects.filter(
            project=partnership.project,
            status=PropertyUnit.UnitStatus.AVAILABLE
        ).order_by('unit_code')

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('المرافق والعمليات'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-cogs'},
            {'title': _('الشركاء وملاك الأراضي'), 'url': reverse('real_estate:partnership_list')},
            {'title': partnership.partnership_number, 'active': True}
        ]

        context = {
            'partnership': partnership,
            'allocations': allocations,
            'available_units': available_units,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_projects',
            'active_submenu': 'partnerships',
        }
        return render(request, 'real_estate/partnership_detail.html', context)


class LandownerUnitAllocateView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تخصيص وحدة عينية لمالك الأرض وحظر التعاقد عليها للعملاء
    """
    permission_required = 'real_estate.change_landownerpartnership'

    def post(self, request, pk):
        partnership = get_object_or_404(LandownerPartnership, pk=pk)
        unit_id = request.POST.get('unit')
        unit = get_object_or_404(PropertyUnit, pk=unit_id, project=partnership.project)

        if unit.status != PropertyUnit.UnitStatus.AVAILABLE:
            messages.error(request, _('لا يمكن تخصيص وحدة غير متاحة.'))
            return redirect('real_estate:partnership_detail', pk=partnership.pk)

        notes = request.POST.get('notes', '').strip()

        LandownerUnitAllocation.objects.create(
            partnership=partnership,
            unit=unit,
            allocated_by=request.user,
            notes=notes
        )

        unit.status = PropertyUnit.UnitStatus.LANDOWNER_ALLOCATED
        unit.status_version += 1
        unit.save(update_fields=['status', 'status_version'])

        messages.success(request, _(f'تم تخصيص الوحدة {unit.unit_code} عيناً لمالك الأرض {partnership.partner_name} بنجاح.'))
        return redirect('real_estate:partnership_detail', pk=partnership.pk)


# ==============================================================================
# 4. تبديل وترقية الوحدات العقارية (Unit Swaps & Rescheduling)
# ==============================================================================

class UnitSwapListView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    سجل طلبات ومحاضر تبديل وترقية/تخفيض الوحدات العقارية
    """
    permission_required = 'real_estate.view_unitswaprecord'

    def get(self, request):
        search_query = request.GET.get('q', '').strip()
        status_filter = request.GET.get('status', '').strip()

        qs = UnitSwapRecord.objects.select_related(
            'contract__customer', 'old_unit__project', 'new_unit__project'
        ).order_by('-swap_date', '-id')

        if search_query:
            qs = qs.filter(
                Q(swap_number__icontains=search_query) |
                Q(contract__customer__name__icontains=search_query) |
                Q(old_unit__unit_code__icontains=search_query) |
                Q(new_unit__unit_code__icontains=search_query)
            )

        if status_filter:
            qs = qs.filter(status=status_filter)

        paginator = Paginator(qs, 20)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        total_swaps = UnitSwapRecord.objects.count()
        executed_count = UnitSwapRecord.objects.filter(status=UnitSwapRecord.SwapStatus.EXECUTED).count()

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('المبيعات والتعاقدات'), 'url': reverse('real_estate:contract_list'), 'icon': 'fa-file-signature'},
            {'title': _('تبديل وترقية الوحدات'), 'active': True}
        ]

        header_buttons = []
        if request.user.has_perm('real_estate.add_unitswaprecord') or request.user.is_superuser:
            header_buttons.append({
                'url': reverse('real_estate:swap_create'),
                'label': _('طلب استبدال وحدة'),
                'icon': 'fa-exchange-alt',
                'class': 'btn-primary'
            })

        context = {
            'page_obj': page_obj,
            'swaps': page_obj.object_list,
            'search_query': search_query,
            'selected_status': status_filter,
            'status_choices': UnitSwapRecord.SwapStatus.choices,
            'total_swaps': total_swaps,
            'executed_count': executed_count,
            'breadcrumb_items': breadcrumb_items,
            'header_buttons': header_buttons,
            'active_menu': 're_sales',
            'active_submenu': 'unit_swaps',
        }
        return render(request, 'real_estate/swap_list.html', context)


class UnitSwapCreateView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    إنشاء طلب استبدال وترقية لوحدة عقارية
    """
    permission_required = 'real_estate.add_unitswaprecord'

    def get(self, request):
        contracts = PropertyContract.objects.filter(
            status=PropertyContract.ContractStatus.ACTIVE
        ).exclude(
            unit__status__in=[PropertyUnit.UnitStatus.DELIVERED, PropertyUnit.UnitStatus.DELIVERED_DEEMED]
        ).select_related('customer', 'unit__project').order_by('contract_number')

        available_units = PropertyUnit.objects.filter(
            status=PropertyUnit.UnitStatus.AVAILABLE
        ).select_related('project').order_by('project__name', 'unit_code')

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('المبيعات والتعاقدات'), 'url': reverse('real_estate:contract_list'), 'icon': 'fa-file-signature'},
            {'title': _('تبديل وترقية الوحدات'), 'url': reverse('real_estate:swap_list')},
            {'title': _('طلب استبدال جديد'), 'active': True}
        ]

        context = {
            'contracts': contracts,
            'available_units': available_units,
            'settlement_methods': UnitSwapRecord.SettlementMethod.choices,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_sales',
            'active_submenu': 'unit_swaps',
        }
        return render(request, 'real_estate/swap_form.html', context)

    def post(self, request):
        contract_id = request.POST.get('contract')
        contract = get_object_or_404(PropertyContract.objects.select_related('unit', 'customer'), pk=contract_id)

        new_unit_id = request.POST.get('new_unit')
        new_unit = get_object_or_404(PropertyUnit, pk=new_unit_id)

        try:
            admin_fee = Decimal(request.POST.get('administrative_fee', '0') or '0')
        except Exception:
            admin_fee = Decimal('0.00')

        settlement_method = request.POST.get('settlement_method', UnitSwapRecord.SettlementMethod.RE_AMORTIZE_EXISTING)
        notes = request.POST.get('notes', '').strip()

        try:
            swap_record = UnitSwapService.create_swap_record(
                contract=contract,
                new_unit=new_unit,
                administrative_fee=admin_fee,
                settlement_method=settlement_method,
                notes=notes,
                user=request.user
            )
            messages.success(request, _(f'تم تسجيل محضر الاستبدال {swap_record.swap_number} بنجاح.'))
            return redirect('real_estate:swap_detail', pk=swap_record.pk)
        except ValidationError as e:
            error_msg = e.message if hasattr(e, 'message') else str(e)
            messages.error(request, error_msg)
            return redirect('real_estate:swap_create')


class UnitSwapDetailView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تفاصيل محضر استبدال الوحدة وفارق السعر وإعادة جدولة الأقساط
    """
    permission_required = 'real_estate.view_unitswaprecord'

    def get(self, request, pk):
        swap = get_object_or_404(
            UnitSwapRecord.objects.select_related(
                'contract__customer',
                'old_unit__project',
                'new_unit__project',
                'created_by'
            ),
            pk=pk
        )

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('المبيعات والتعاقدات'), 'url': reverse('real_estate:contract_list'), 'icon': 'fa-file-signature'},
            {'title': _('تبديل وترقية الوحدات'), 'url': reverse('real_estate:swap_list')},
            {'title': swap.swap_number, 'active': True}
        ]

        header_buttons = [
            {
                'url': reverse('real_estate:swap_print', kwargs={'pk': swap.pk}),
                'icon': 'fa-print',
                'text': _('طباعة محضر الاستبدال'),
                'class': 'btn-outline-primary',
                'target': '_blank',
            }
        ]

        context = {
            'swap': swap,
            'breadcrumb_items': breadcrumb_items,
            'header_buttons': header_buttons,
            'active_menu': 're_sales',
            'active_submenu': 'unit_swaps',
        }
        return render(request, 'real_estate/swap_detail.html', context)


class UnitSwapExecuteView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تنفيذ محضر الاستبدال ذرياً: قلب الحالات، تعديل العقد، وإعادة جدولة الأقساط
    """
    permission_required = 'real_estate.change_unitswaprecord'

    def post(self, request, pk):
        swap = get_object_or_404(UnitSwapRecord, pk=pk)

        try:
            UnitSwapService.execute_unit_swap(swap_record=swap, user=request.user)
            messages.success(
                request,
                _(f'تم تنفيذ محضر الاستبدال {swap.swap_number} بنجاح. '
                  f'الوحدة السابقة {swap.old_unit.unit_code} أصبحت متاحة، والجديدة {swap.new_unit.unit_code} تم التعاقد عليها '
                  f'وإعادة جدولة الأقساط المتبقية.')
            )
        except ValidationError as e:
            error_msg = e.message if hasattr(e, 'message') else str(e)
            messages.error(request, error_msg)
        except Exception as e:
            messages.error(request, str(e))

        return redirect('real_estate:swap_detail', pk=swap.pk)


class UnitSwapOfficialPrintView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    طباعة محضر استبدال وترقية الوحدة وإعادة جدولة الأقساط (مع ختم التوثيق الرقمي SHA-256)
    """
    permission_required = 'real_estate.view_unitswaprecord'

    def get(self, request, pk):
        import hashlib
        swap = get_object_or_404(
            UnitSwapRecord.objects.select_related(
                'contract__customer',
                'contract__installment_plan',
                'old_unit__project',
                'old_unit__floor__block',
                'new_unit__project',
                'new_unit__floor__block',
                'created_by'
            ),
            pk=pk
        )
        installment_items = (
            swap.contract.installment_plan.items.all().order_by('installment_number')
            if swap.contract.installment_plan else []
        )

        raw_seed = (
            f"SWP:{swap.swap_number}:{swap.contract.contract_number}:"
            f"{swap.old_unit.unit_code}:{swap.new_unit.unit_code}:"
            f"{swap.price_difference}:{swap.status}"
        )
        verification_hash = hashlib.sha256(raw_seed.encode('utf-8')).hexdigest()

        context = {
            'swap': swap,
            'installment_items': installment_items,
            'verification_hash': verification_hash,
            'verification_token': verification_hash[:16].upper(),
            'today': timezone.localdate(),
        }
        return render(request, 'real_estate/swap_print.html', context)

