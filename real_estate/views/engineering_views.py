# -*- coding: utf-8 -*-
"""
Engineering Views - شاشات وعمليات الإدارة الهندسية وضبط الجودة
MWHEBA ERP — Real Estate Architectural Variations, Milestone Guards & Field Snagging
"""
import json
import logging
from decimal import Decimal
from datetime import datetime
from django.utils import timezone
from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum

logger = logging.getLogger(__name__)

from users.mixins import SmartPermissionRequiredMixin
from real_estate.models import (
    ClientVariationOrder,
    UnitSnagItem,
    RealEstateProject,
    PropertyBlock,
    PropertyFloor,
    PropertyUnit,
    PropertyContract,
    ProjectActivity,
    MilestoneInstallmentLink,
    MilestoneCollectionAlert,
    SiteDailyLog,
    UnitSiteProgressRecord,
    SiteProgressAuditLog,
)
from real_estate.services.variation_service import VariationOrderService
from real_estate.services.snagging_service import OfflineSnaggingSyncService
from real_estate.services.site_progress_service import (
    ProjectProgressCalculationService,
    SiteProgressInitializationService,
    SiteProgressExecutionService,
    ConcurrencyConflictError,
)
from real_estate.services.wbs_service import WbsTreeGovernanceService, UnitToWbsBridgeService
from real_estate.forms.engineering_forms import SiteDailyLogForm, ProjectActivityForm
from supplier.models import Supplier


class VariationOrderListView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    أوامر التعديلات المعمارية والتشطيبية للعملاء
    """
    permission_required = 'real_estate.view_clientvariationorder'

    def get(self, request):
        search_query = request.GET.get('q', '').strip()
        status_filter = request.GET.get('status', '').strip()
        type_filter = request.GET.get('type', '').strip()
        project_id = request.GET.get('project', '').strip()

        qs = ClientVariationOrder.objects.select_related(
            'contract__customer', 'contract__unit__project'
        ).order_by('-created_at')

        if search_query:
            qs = qs.filter(
                Q(order_number__icontains=search_query) |
                Q(title__icontains=search_query) |
                Q(contract__customer__name__icontains=search_query) |
                Q(contract__unit__unit_code__icontains=search_query)
            )

        if status_filter:
            qs = qs.filter(status=status_filter)

        if type_filter:
            qs = qs.filter(variation_type=type_filter)

        if project_id:
            qs = qs.filter(contract__unit__project_id=project_id)

        paginator = Paginator(qs, 20)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        total_orders = ClientVariationOrder.objects.count()
        total_cost = ClientVariationOrder.objects.aggregate(s=Sum('total_cost'))['s'] or Decimal('0.00')
        approved_count = ClientVariationOrder.objects.filter(
            status=ClientVariationOrder.OrderStatus.APPROVED
        ).count()

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('الإدارة الهندسية'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-hard-hat'},
            {'title': _('أوامر تعديلات العملاء'), 'active': True}
        ]

        header_buttons = []
        if request.user.has_perm('real_estate.add_clientvariationorder') or request.user.is_superuser:
            header_buttons.append({
                'url': reverse('real_estate:variation_create'),
                'label': _('أمر تعديل جديد'),
                'icon': 'fa-plus',
                'class': 'btn-primary'
            })

        projects = RealEstateProject.objects.filter(is_archived=False).order_by('name')

        context = {
            'page_obj': page_obj,
            'orders': page_obj.object_list,
            'projects': projects,
            'search_query': search_query,
            'selected_status': status_filter,
            'selected_type': type_filter,
            'selected_project': project_id,
            'status_choices': ClientVariationOrder.OrderStatus.choices,
            'type_choices': ClientVariationOrder.VariationType.choices,
            'total_orders': total_orders,
            'total_cost': total_cost,
            'approved_count': approved_count,
            'breadcrumb_items': breadcrumb_items,
            'header_buttons': header_buttons,
            'active_menu': 're_engineering',
            'active_submenu': 'variation_orders',
        }
        return render(request, 'real_estate/variation_list.html', context)


class VariationOrderCreateView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    إنشاء أمر تعديل معماري جديد مع مقايسة التكاليف وتطبيق فرملة مراحل التنفيذ
    """
    permission_required = 'real_estate.add_clientvariationorder'

    def get(self, request):
        contracts = PropertyContract.objects.filter(
            status__in=[
                PropertyContract.ContractStatus.ACTIVE,
                PropertyContract.ContractStatus.UNDER_APPROVAL
            ]
        ).select_related('customer', 'unit__project').order_by('-contract_date')

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('الإدارة الهندسية'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-hard-hat'},
            {'title': _('أوامر تعديلات العملاء'), 'url': reverse('real_estate:variation_list')},
            {'title': _('أمر تعديل جديد'), 'active': True}
        ]

        context = {
            'contracts': contracts,
            'variation_types': ClientVariationOrder.VariationType.choices,
            'project_stages': ClientVariationOrder.ProjectStage.choices,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_engineering',
            'active_submenu': 'variation_orders',
        }
        return render(request, 'real_estate/variation_form.html', context)

    def post(self, request):
        contract_id = request.POST.get('contract')
        variation_type = request.POST.get('variation_type')
        stage_at_request = request.POST.get('stage_at_request')
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()

        try:
            demolition_rework_cost = Decimal(request.POST.get('demolition_rework_cost', '0') or '0')
            material_cost = Decimal(request.POST.get('material_cost', '0') or '0')
            labor_cost = Decimal(request.POST.get('labor_cost', '0') or '0')
            supervision_fee = Decimal(request.POST.get('supervision_fee', '0') or '0')
        except Exception:
            messages.error(request, _('يرجى التأكد من صحة المبالغ وتكاليف المقايسة الهندسية.'))
            return redirect('real_estate:variation_create')

        contract = get_object_or_404(PropertyContract, pk=contract_id)

        try:
            order = VariationOrderService.validate_and_create_variation_order(
                contract=contract,
                variation_type=variation_type,
                stage_at_request=stage_at_request,
                title=title,
                description=description,
                demolition_rework_cost=demolition_rework_cost,
                material_cost=material_cost,
                labor_cost=labor_cost,
                supervision_fee=supervision_fee,
                user=request.user
            )
            messages.success(request, _(f'تم تسجيل أمر التعديل {order.order_number} بنجاح وقيده تحت المراجعة الهندسية.'))
            return redirect('real_estate:variation_detail', pk=order.pk)
        except ValidationError as e:
            error_msg = e.message if hasattr(e, 'message') else str(e)
            messages.error(request, error_msg)
            contracts = PropertyContract.objects.filter(
                status__in=[
                    PropertyContract.ContractStatus.ACTIVE,
                    PropertyContract.ContractStatus.UNDER_APPROVAL
                ]
            ).select_related('customer', 'unit__project').order_by('-contract_date')

            breadcrumb_items = [
                {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
                {'title': _('الإدارة الهندسية'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-hard-hat'},
                {'title': _('أوامر تعديلات العملاء'), 'url': reverse('real_estate:variation_list')},
                {'title': _('أمر تعديل جديد'), 'active': True}
            ]

            context = {
                'contracts': contracts,
                'variation_types': ClientVariationOrder.VariationType.choices,
                'project_stages': ClientVariationOrder.ProjectStage.choices,
                'form_data': request.POST,
                'breadcrumb_items': breadcrumb_items,
                'active_menu': 're_engineering',
                'active_submenu': 'variation_orders',
            }
            return render(request, 'real_estate/variation_form.html', context)


class VariationOrderUpdateView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تعديل أمر تعديل معماري قيد المراجعة قبل الاعتماد
    """
    permission_required = 'real_estate.change_clientvariationorder'

    def get(self, request, pk):
        order = get_object_or_404(
            ClientVariationOrder.objects.select_related('contract__customer', 'contract__unit__project'),
            pk=pk
        )
        if order.status not in [ClientVariationOrder.OrderStatus.DRAFT, ClientVariationOrder.OrderStatus.ENGINEERING_REVIEW]:
            messages.error(request, _('لا يمكن تعديل أمر التعديل بعد اعتماده أو بدء تنفيذه.'))
            return redirect('real_estate:variation_detail', pk=order.pk)

        contracts = PropertyContract.objects.filter(pk=order.contract_id).select_related('customer', 'unit__project')
        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('الإدارة الهندسية'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-hard-hat'},
            {'title': _('أوامر تعديلات العملاء'), 'url': reverse('real_estate:variation_list')},
            {'title': order.order_number, 'url': reverse('real_estate:variation_detail', kwargs={'pk': order.pk})},
            {'title': _('تعديل أمر التعديل'), 'active': True}
        ]

        context = {
            'order': order,
            'contracts': contracts,
            'variation_types': ClientVariationOrder.VariationType.choices,
            'project_stages': ClientVariationOrder.ProjectStage.choices,
            'is_edit': True,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_engineering',
            'active_submenu': 'variation_orders',
        }
        return render(request, 'real_estate/variation_form.html', context)

    def post(self, request, pk):
        order = get_object_or_404(ClientVariationOrder, pk=pk)
        if order.status not in [ClientVariationOrder.OrderStatus.DRAFT, ClientVariationOrder.OrderStatus.ENGINEERING_REVIEW]:
            messages.error(request, _('لا يمكن تعديل أمر التعديل بعد اعتماده أو بدء تنفيذه.'))
            return redirect('real_estate:variation_detail', pk=order.pk)

        order.variation_type = request.POST.get('variation_type', order.variation_type)
        order.stage_at_request = request.POST.get('stage_at_request', order.stage_at_request)
        order.title = request.POST.get('title', order.title).strip()
        order.description = request.POST.get('description', order.description).strip()

        try:
            order.demolition_rework_cost = Decimal(request.POST.get('demolition_rework_cost', '0') or '0')
            order.material_cost = Decimal(request.POST.get('material_cost', '0') or '0')
            order.labor_cost = Decimal(request.POST.get('labor_cost', '0') or '0')
            order.supervision_fee = Decimal(request.POST.get('supervision_fee', '0') or '0')
            order.clean()
            order.save()
            messages.success(request, _('تم تحديث أمر التعديل بنجاح.'))
            return redirect('real_estate:variation_detail', pk=order.pk)
        except ValidationError as e:
            error_msg = e.message if hasattr(e, 'message') else str(e)
            messages.error(request, error_msg)
            contracts = PropertyContract.objects.filter(pk=order.contract_id).select_related('customer', 'unit__project')
            breadcrumb_items = [
                {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
                {'title': _('الإدارة الهندسية'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-hard-hat'},
                {'title': _('أوامر تعديلات العملاء'), 'url': reverse('real_estate:variation_list')},
                {'title': order.order_number, 'url': reverse('real_estate:variation_detail', kwargs={'pk': order.pk})},
                {'title': _('تعديل أمر التعديل'), 'active': True}
            ]
            context = {
                'order': order,
                'contracts': contracts,
                'variation_types': ClientVariationOrder.VariationType.choices,
                'project_stages': ClientVariationOrder.ProjectStage.choices,
                'is_edit': True,
                'breadcrumb_items': breadcrumb_items,
                'active_menu': 're_engineering',
                'active_submenu': 'variation_orders',
            }
            return render(request, 'real_estate/variation_form.html', context)


class VariationOrderDetailView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تفاصيل أمر التعديل المعماري ومقايسة التكاليف والاعتماد وجدولة الملحق المالي
    """
    permission_required = 'real_estate.view_clientvariationorder'

    def get(self, request, pk):
        order = get_object_or_404(
            ClientVariationOrder.objects.select_related(
                'contract__customer',
                'contract__unit__project',
                'approved_by',
                'created_by',
                'supplemental_installment_item'
            ),
            pk=pk
        )

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('الإدارة الهندسية'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-hard-hat'},
            {'title': _('أوامر تعديلات العملاء'), 'url': reverse('real_estate:variation_list')},
            {'title': order.order_number, 'active': True}
        ]

        # فحص مطابقة مرحلة البناء هندسياً (Structural Milestone Cut-off Guard)
        is_milestone_restricted = (
            order.stage_at_request in [
                ClientVariationOrder.ProjectStage.POST_ROUGH_IN,
                ClientVariationOrder.ProjectStage.FINAL_FINISHING
            ]
            and order.variation_type in [
                ClientVariationOrder.VariationType.STRUCTURAL,
                ClientVariationOrder.VariationType.PLUMBING_HVAC
            ]
        )

        context = {
            'order': order,
            'breadcrumb_items': breadcrumb_items,
            'is_milestone_restricted': is_milestone_restricted,
            'active_menu': 're_engineering',
            'active_submenu': 'variation_orders',
        }
        return render(request, 'real_estate/variation_detail.html', context)


class VariationOrderApproveView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    اعتماد أمر التعديل وجدولة قيمته كقسط ملحق إضافي في خطة أقساط العقد
    """
    permission_required = 'real_estate.change_clientvariationorder'

    def post(self, request, pk):
        order = get_object_or_404(
            ClientVariationOrder.objects.select_related('contract__installment_plan'),
            pk=pk
        )
        due_date_str = request.POST.get('due_date', '').strip()
        due_date = None
        if due_date_str:
            try:
                due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        try:
            item = VariationOrderService.approve_and_schedule_variation_order(
                order=order,
                approver_user=request.user,
                due_date=due_date
            )
            messages.success(
                request,
                _(f'تم اعتماد أمر التعديل {order.order_number} بنجاح، وتوليد القسط الملحق رقم {item.installment_number} '
                  f'بمبلغ {order.total_cost:,.2f} مستحق بتاريخ {item.due_date}.')
            )
        except ValidationError as e:
            error_msg = e.message if hasattr(e, 'message') else str(e)
            messages.error(request, error_msg)
        except Exception as e:
            messages.error(request, str(e))

        return redirect('real_estate:variation_detail', pk=order.pk)


class VariationOrderRejectView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    رفض أمر التعديل المعماري لمخالفته المعايير الهندسية
    """
    permission_required = 'real_estate.change_clientvariationorder'

    def post(self, request, pk):
        order = get_object_or_404(ClientVariationOrder, pk=pk)
        if order.status not in [ClientVariationOrder.OrderStatus.DRAFT, ClientVariationOrder.OrderStatus.ENGINEERING_REVIEW]:
            messages.error(request, _('لا يمكن رفض أمر التعديل في حالته الحالية.'))
            return redirect('real_estate:variation_detail', pk=order.pk)

        rejection_reason = request.POST.get('rejection_reason', '').strip()
        if not rejection_reason:
            messages.error(request, _('يرجى توضيح سبب الرفض الهندسي.'))
            return redirect('real_estate:variation_detail', pk=order.pk)

        order.status = ClientVariationOrder.OrderStatus.REJECTED
        order.rejection_reason = rejection_reason
        order.save(update_fields=['status', 'rejection_reason', 'updated_at'])
        messages.warning(request, _(f'تم رفض أمر التعديل {order.order_number}.'))
        return redirect('real_estate:variation_detail', pk=order.pk)


class SnagItemListView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    قوائم وبنود فحص الموقع وملاحظات الاستلام الميدانية
    """
    permission_required = 'real_estate.view_unitsnagitem'

    def get(self, request):
        search_query = request.GET.get('q', '').strip()
        status_filter = request.GET.get('status', '').strip()
        severity_filter = request.GET.get('severity', '').strip()
        category_filter = request.GET.get('category', '').strip()
        project_id = request.GET.get('project', '').strip()

        qs = UnitSnagItem.objects.select_related(
            'unit__project', 'contract__customer', 'contractor', 'created_by'
        ).order_by('-created_at', '-id')

        if search_query:
            qs = qs.filter(
                Q(snag_code__icontains=search_query) |
                Q(unit__unit_code__icontains=search_query) |
                Q(room_location__icontains=search_query) |
                Q(description__icontains=search_query)
            )

        if status_filter:
            qs = qs.filter(status=status_filter)

        if severity_filter:
            qs = qs.filter(severity=severity_filter)

        if category_filter:
            qs = qs.filter(category=category_filter)

        if project_id:
            qs = qs.filter(unit__project_id=project_id)

        paginator = Paginator(qs, 20)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        total_snags = UnitSnagItem.objects.count()
        open_snags = UnitSnagItem.objects.filter(
            status__in=[UnitSnagItem.SnagStatus.OPEN, UnitSnagItem.SnagStatus.IN_PROGRESS]
        ).count()
        resolved_snags = UnitSnagItem.objects.filter(
            status__in=[UnitSnagItem.SnagStatus.RESOLVED, UnitSnagItem.SnagStatus.VERIFIED_BY_ENGINEER]
        ).count()
        blockers_count = UnitSnagItem.objects.filter(
            severity=UnitSnagItem.SnagSeverity.CRITICAL_BLOCKER,
            status__in=[UnitSnagItem.SnagStatus.OPEN, UnitSnagItem.SnagStatus.IN_PROGRESS]
        ).count()

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('الإدارة الهندسية'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-hard-hat'},
            {'title': _('بنود وملاحظات فحص الموقع'), 'active': True}
        ]

        header_buttons = []
        if request.user.has_perm('real_estate.add_unitsnagitem') or request.user.is_superuser:
            header_buttons.append({
                'url': '#',
                'label': _('تسجيل ملاحظة فحص'),
                'icon': 'fa-plus',
                'class': 'btn-primary',
                'data_bs_toggle': 'modal',
                'data_bs_target': '#addSnagModal'
            })

        units = PropertyUnit.objects.select_related('project').order_by('project__name', 'unit_code')
        contractors = Supplier.objects.filter(is_active=True).order_by('name')
        projects = RealEstateProject.objects.filter(is_archived=False).order_by('name')

        context = {
            'page_obj': page_obj,
            'snags': page_obj.object_list,
            'units': units,
            'contractors': contractors,
            'projects': projects,
            'search_query': search_query,
            'selected_status': status_filter,
            'selected_severity': severity_filter,
            'selected_category': category_filter,
            'selected_project': project_id,
            'status_choices': UnitSnagItem.SnagStatus.choices,
            'severity_choices': UnitSnagItem.SnagSeverity.choices,
            'category_choices': UnitSnagItem.SnagCategory.choices,
            'total_snags': total_snags,
            'open_snags': open_snags,
            'resolved_snags': resolved_snags,
            'blockers_count': blockers_count,
            'breadcrumb_items': breadcrumb_items,
            'header_buttons': header_buttons,
            'active_menu': 're_engineering',
            'active_submenu': 'snag_items',
        }
        return render(request, 'real_estate/snag_list.html', context)


class SnagItemCreateView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تسجيل ملاحظة فحص موقع ميدانية جديدة
    """
    permission_required = 'real_estate.add_unitsnagitem'

    def post(self, request):
        unit_id = request.POST.get('unit')
        unit = get_object_or_404(PropertyUnit, pk=unit_id)
        room_location = request.POST.get('room_location', '').strip()
        category = request.POST.get('category', UnitSnagItem.SnagCategory.PAINTING)
        severity = request.POST.get('severity', UnitSnagItem.SnagSeverity.MINOR)
        description = request.POST.get('description', '').strip()
        contractor_id = request.POST.get('contractor')
        contractor = Supplier.objects.filter(pk=contractor_id).first() if contractor_id else None

        # ربط العقد العقاري الساري للوحدة إن وجد
        contract = PropertyContract.objects.filter(
            unit=unit,
            status__in=[
                PropertyContract.ContractStatus.ACTIVE,
                PropertyContract.ContractStatus.UNDER_APPROVAL
            ]
        ).first()

        photo_thumbnail_webp = request.POST.get('photo_thumbnail_webp', '').strip()

        snag = UnitSnagItem.objects.create(
            unit=unit,
            contract=contract,
            room_location=room_location or _('الموقع العام للوحدة'),
            category=category,
            severity=severity,
            description=description,
            contractor=contractor,
            photo_thumbnail_webp=photo_thumbnail_webp,
            status=UnitSnagItem.SnagStatus.OPEN,
            created_by=request.user
        )

        messages.success(request, _(f'تم تسجيل الملاحظة الفنية {snag.snag_code} بنجاح.'))
        return redirect('real_estate:snag_list')


class SnagItemResolveView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    اعتماد وإغلاق الملاحظة الميدانية رسمياً بعد إتمام الإصلاحات
    """
    permission_required = 'real_estate.change_unitsnagitem'

    def post(self, request, pk):
        snag = get_object_or_404(UnitSnagItem, pk=pk)
        resolution_notes = request.POST.get('resolution_notes', '').strip()

        OfflineSnaggingSyncService.verify_snag_resolution(
            snag_item=snag,
            engineer_user=request.user,
            resolution_notes=resolution_notes
        )

        messages.success(request, _(f'تم اعتماد وإغلاق الملاحظة الفنية {snag.snag_code} رسمياً.'))
        return redirect('real_estate:snag_list')


class ApiSnagSyncView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    واجهة برمجة التطبيقات (API) لمزامنة حزم الملاحظات الميدانية المسجلة دون اتصال (Offline-First Sync)
    """
    permission_required = 'real_estate.add_unitsnagitem'

    def post(self, request):
        try:
            payload = json.loads(request.body.decode('utf-8'))
            if isinstance(payload, dict) and 'snags' in payload:
                snags_data = payload['snags']
            elif isinstance(payload, list):
                snags_data = payload
            else:
                return JsonResponse({'error': 'Invalid payload format'}, status=400)

            result = OfflineSnaggingSyncService.sync_batch_snags(
                snags_payload=snags_data,
                user=request.user
            )
            return JsonResponse({'success': True, 'result': result})
        except Exception as e:
            logger.error(f"Sync batch error: {e}", exc_info=True)
            return JsonResponse({'success': False, 'error': str(e)}, status=400)


# ==============================================================================
# Track 3: عروض مصفوفة المتابعة الميدانية للوحدات والـ AJAX والتقارير والطباعة
# ==============================================================================

class SiteProjectReportView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تقرير ومصفوفة المتابعة الميدانية التفاعلية للوحدات (32 بنداً معمارياً):
    - أداء فائق وسريع للغاية بدون أي استعلامات N+1 (Zero N+1 In-Memory Map).
    - كروت مؤشرات الجاهزية للتسليم (Handover Readiness KPI Cards).
    - فلاتر مرنة بالمشروع والعمارة والدور مع تفعيل RTL في Select2.
    """
    permission_required = 'real_estate.view_unitsiteprogressrecord'

    def get(self, request, project_id):
        project = get_object_or_404(RealEstateProject, pk=project_id)

        block_id = request.GET.get('block', '').strip()
        floor_id = request.GET.get('floor', '').strip()
        rfi_filter = request.GET.get('rfi', '').strip()

        # جلب العمارات التابعة
        blocks = project.blocks.all().order_by('code')

        # جلب الوحدات المستهدفة
        units_qs = PropertyUnit.objects.filter(
            project=project,
            is_active=True
        ).select_related('block', 'floor')

        if block_id:
            units_qs = units_qs.filter(block_id=block_id)
        if floor_id:
            units_qs = units_qs.filter(floor_id=floor_id)

        units = list(units_qs.order_by('-floor__floor_number', 'unit_code'))
        unit_ids = [u.id for u in units]

        # جلب كافة سجلات الموقع دفعة واحدة باستعلام SQL وحيد مسبق الربط
        records_qs = UnitSiteProgressRecord.objects.filter(
            unit_id__in=unit_ids
        ).select_related('contractor', 'linked_snag')

        if rfi_filter:
            records_qs = records_qs.filter(rfi_number__icontains=rfi_filter)

        # بناء خريطة الذاكرة O(1) Zero N+1 Map
        matrix_data = {u.id: {} for u in units}
        for rec in records_qs:
            if rec.unit_id in matrix_data:
                matrix_data[rec.unit_id][rec.trade_stage] = rec

        trade_choices = UnitSiteProgressRecord.InspectionTrade.choices

        # هيكلة صفوف مصفوفة البنود مع السجلات الفعلية
        unit_rows = []
        for u in units:
            u_records = matrix_data.get(u.id, {})
            cells = []
            for trade_key, trade_label in trade_choices:
                rec = u_records.get(trade_key)
                cells.append({
                    'trade_key': trade_key,
                    'trade_label': trade_label,
                    'record': rec,
                })
            unit_rows.append({
                'unit': u,
                'cells': cells,
            })

        # حساب كروت المؤشرات الإحصائية في الهيدر (Handover Readiness KPIs)
        total_units_count = len(units)
        ready_units_count = sum(1 for u in units if u.progress_percentage >= Decimal('100.00'))
        in_progress_count = sum(1 for u in units if Decimal('0.00') < u.progress_percentage < Decimal('100.00'))
        
        # الوحدات المعطلة بعيوب حرجة
        blocked_units_count = PropertyUnit.objects.filter(
            id__in=unit_ids,
            snag_items__severity=UnitSnagItem.SnagSeverity.CRITICAL_BLOCKER
        ).exclude(
            snag_items__status=UnitSnagItem.SnagStatus.VERIFIED_BY_ENGINEER
        ).distinct().count()

        contractors = Supplier.objects.filter(is_active=True).order_by('name')

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('إدارة المشروعات العقارية'), 'url': reverse('real_estate:project_list'), 'icon': 'fa-city'},
            {'title': project.name, 'url': reverse('real_estate:project_detail', kwargs={'pk': project.pk})},
            {'title': _('متابعة التنفيذ الميداني وشبكة البنود'), 'active': True},
        ]

        context = {
            'project': project,
            'blocks': blocks,
            'units': units,
            'unit_rows': unit_rows,
            'contractors': contractors,
            'matrix_data': matrix_data,
            'trade_choices': trade_choices,
            'selected_block': block_id,
            'selected_floor': floor_id,
            'rfi_filter': rfi_filter,
            'total_units_count': total_units_count,
            'ready_units_count': ready_units_count,
            'in_progress_count': in_progress_count,
            'blocked_units_count': blocked_units_count,
            'breadcrumb_items': breadcrumb_items,
        }
        return render(request, 'real_estate/site_project_report.html', context)


class QuickUpdateStageAjaxView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    نقطة النهاية السريعة لتحديث خلية البند في مصفوفة الموقع (AJAX Cell Quick Update):
    - قفل التزامن المتفائل (Optimistic Concurrency Control OCC) عبر فحص version.
    - التحقق من الأسبقية الهندسية الصارمة (Finish-to-Start Prerequisites).
    - حظر تخفيض النسبة للبنود المفوترة (is_billed Lock).
    - توليد ملاحظة عيب فني فورية (Snag Item) عند الرفض أو الاعتماد المشروط.
    - إعادة احتساب وتصعيد نسب الإنجاز التراكمية لحظياً.
    """
    permission_required = 'real_estate.can_verify_site_stages'

    def post(self, request, record_id):
        sent_version = request.POST.get('version')
        if sent_version is None or str(sent_version).strip() == '':
            return JsonResponse({
                'success': False,
                'message': _('رقم الإصدار (Version) إلزامي للتحكم في التزامن المتفائل.')
            }, status=400)

        status_val = request.POST.get('status')
        pct_str = request.POST.get('completion_percentage')
        contractor_id = request.POST.get('contractor_id', '').strip()
        rfi_number = request.POST.get('rfi_number', '').strip()
        notes = request.POST.get('notes', '').strip()

        # قراءة الحالة الحالية إن لم تُمرر
        if not status_val or not pct_str:
            curr_rec = get_object_or_404(UnitSiteProgressRecord, pk=record_id)
            if not status_val:
                status_val = curr_rec.status
            if not pct_str:
                pct_str = str(curr_rec.completion_percentage)

        try:
            pct_val = int(pct_str)
        except (ValueError, TypeError):
            return JsonResponse({'success': False, 'message': _('نسبة الإنجاز غير صالحة.')}, status=400)

        resolved_contractor_id = None
        if contractor_id:
            try:
                resolved_contractor_id = int(contractor_id)
            except ValueError:
                pass

        try:
            record, created_snag_code, new_unit_pct = SiteProgressExecutionService.update_stage_record_atomic(
                record_id=record_id,
                expected_version=sent_version,
                status_val=status_val,
                completion_percentage=pct_val,
                user=request.user,
                contractor_id=resolved_contractor_id,
                rfi_number=rfi_number,
                notes=notes,
                inspection_photo=request.FILES.get('inspection_photo')
            )
            return JsonResponse({
                'success': True,
                'message': _('تم تحديث بند الموقع واحتساب نسب الإنجاز التراكمية بنجاح.'),
                'new_percentage': record.completion_percentage,
                'new_status': record.status,
                'status_display': record.get_status_display(),
                'unit_progress': float(new_unit_pct),
                'version': record.version,
                'created_snag_code': created_snag_code,
            })
        except ConcurrencyConflictError as cce:
            return JsonResponse({
                'success': False,
                'conflict': True,
                'message': str(cce)
            }, status=409)
        except ValidationError as ve:
            msg = ve.messages[0] if hasattr(ve, 'messages') and ve.messages else (ve.message if hasattr(ve, 'message') else str(ve))
            return JsonResponse({'success': False, 'message': msg}, status=400)


class StageRecordSpecPreviewAjaxView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    نقطة استرجاع ومعاينة المواصفات التعاقدية المعتمدة للبند (Approved Spec Preview AJAX):
    - تزود مهندس الموقع بالمواصفات والخامات المعتمدة في باقة تشطيب العميل لمنع الغش أو الأخطاء.
    """
    permission_required = 'real_estate.can_verify_site_stages'

    def get(self, request, record_id):
        record = get_object_or_404(
            UnitSiteProgressRecord.objects.select_related('unit__project'),
            pk=record_id
        )
        from real_estate.services.site_progress_service import StageRecordSpecPreviewService
        data = StageRecordSpecPreviewService.get_spec_preview(record)
        return JsonResponse({
            'success': True,
            'preview': data
        })



class BulkUpdateFloorStageAjaxView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    نقطة النهاية للتحديث المجمع لشقق الدور كاملاً (Bulk Floor Stage Update):
    - يتيح اعتماد بند لجميع شقق الدور بنقرة زر واحدة.
    - يتضمن صمام أمان حاسم للوحدات المعدلة (Customized Units Guard):
      يستثني الشقق ذات أوامر التعديل السارية ClientVariationOrder لحماية مواصفاتها.
    """
    permission_required = 'real_estate.can_verify_site_stages'

    def post(self, request):
        floor_id = request.POST.get('floor_id')
        trade_stage = request.POST.get('trade_stage')
        status_val = request.POST.get('status', UnitSiteProgressRecord.StageStatus.PASSED_AND_VERIFIED)

        if status_val not in UnitSiteProgressRecord.StageStatus.values:
            return JsonResponse({
                'success': False,
                'message': _('حالة البند غير صالحة أو غير معتمدة.')
            }, status=400)

        try:
            pct_val = int(request.POST.get('completion_percentage', 100))
            if pct_val < 0 or pct_val > 100:
                return JsonResponse({
                    'success': False,
                    'message': _('نسبة الإنجاز يجب أن تكون بين 0 و 100.')
                }, status=400)
        except (ValueError, TypeError):
            return JsonResponse({
                'success': False,
                'message': _('نسبة الإنجاز غير صالحة.')
            }, status=400)

        contractor_id = request.POST.get('contractor_id', '').strip()
        rfi_number = request.POST.get('rfi_number', '').strip()
        excluded_unit_ids = request.POST.getlist('excluded_unit_ids[]')

        floor = get_object_or_404(PropertyFloor.objects.select_related('block__project'), pk=floor_id)

        units = floor.units.filter(is_active=True)
        if excluded_unit_ids:
            units = units.exclude(id__in=excluded_unit_ids)

        contractor = None
        if contractor_id:
            contractor = Supplier.objects.filter(pk=contractor_id).first()

        updated_records_count = 0
        for unit in units:
            if unit.status in [PropertyUnit.UnitStatus.DELIVERED, PropertyUnit.UnitStatus.DELIVERED_DEEMED]:
                continue

            # حماية الوحدات ذات أوامر التعديل المعمارية إن لم يحدد المهندس إدراجها
            has_variation = unit.variation_orders.filter(
                status__in=[ClientVariationOrder.OrderStatus.APPROVED, ClientVariationOrder.OrderStatus.IN_PROGRESS]
            ).exists()
            if has_variation and str(unit.id) not in request.POST.getlist('explicit_included_units[]'):
                continue

            # صمام أمان الأسبقيات الهندسية
            if pct_val > 0 and status_val != UnitSiteProgressRecord.StageStatus.NOT_APPLICABLE:
                valid, prereq_errs = ProjectProgressCalculationService.validate_trade_prerequisites(
                    unit=unit,
                    target_trade=trade_stage
                )
                if not valid:
                    continue

            rec, created_flag = UnitSiteProgressRecord.objects.get_or_create(
                unit=unit,
                trade_stage=trade_stage,
                defaults={
                    'is_applicable': True,
                    'status': status_val,
                    'completion_percentage': pct_val,
                }
            )

            # تخطي البنود غير الخاضعة للوحدة أو المفوترة مسبقاً عند الرغبة في التخفيض
            if not rec.is_applicable:
                continue
            if rec.is_billed:
                if pct_val < rec.completion_percentage:
                    continue
                if rec.status == UnitSiteProgressRecord.StageStatus.PASSED_AND_VERIFIED and status_val != UnitSiteProgressRecord.StageStatus.PASSED_AND_VERIFIED:
                    continue

            prev_pct = rec.completion_percentage
            prev_status = rec.status

            rec.status = status_val
            rec.completion_percentage = pct_val
            if contractor:
                rec.contractor = contractor
            if rfi_number:
                rec.rfi_number = rfi_number
            rec.version += 1
            if status_val == UnitSiteProgressRecord.StageStatus.PASSED_AND_VERIFIED:
                rec.verified_by = request.user
                rec.verified_at = timezone.now()

            # توليد Snag عند الرفض أو الاعتماد المشروط
            if status_val in [
                UnitSiteProgressRecord.StageStatus.REJECTED_DEFECT,
                UnitSiteProgressRecord.StageStatus.APPROVED_WITH_COMMENTS
            ]:
                severity_choice = (
                    UnitSnagItem.SnagSeverity.CRITICAL_BLOCKER
                    if status_val == UnitSiteProgressRecord.StageStatus.REJECTED_DEFECT
                    else UnitSnagItem.SnagSeverity.MAJOR
                )
                snag = UnitSnagItem.objects.create(
                    unit=unit,
                    room_location=rec.get_trade_stage_display(),
                    category=UnitSnagItem.SnagCategory.CIVIL_MASONRY if hasattr(UnitSnagItem.SnagCategory, 'CIVIL_MASONRY') else 'OTHER',
                    severity=severity_choice,
                    description=_('ملاحظة جودة مسجلة من التحديث المجمع للدور للبند: %(stage)s') % {
                        'stage': rec.get_trade_stage_display()
                    },
                    contractor=rec.contractor,
                    status=UnitSnagItem.SnagStatus.OPEN,
                    created_by=request.user
                )
                rec.linked_snag = snag

            rec.save()

            SiteProgressAuditLog.objects.create(
                unit=unit,
                unit_code_snapshot=unit.unit_code,
                trade_stage=trade_stage,
                previous_percentage=prev_pct,
                new_percentage=pct_val,
                previous_status=prev_status,
                new_status=status_val,
                defect_notes=_('تحديث مجمع لشقق الدور'),
                changed_by=request.user
            )

            ProjectProgressCalculationService.calculate_and_save_unit_progress(unit)
            updated_records_count += 1

        ProjectProgressCalculationService.rollup_project_and_block_progress(
            project=floor.block.project,
            user=request.user,
            post_ifrs15=True
        )

        return JsonResponse({
            'success': True,
            'message': _(
                'تم التحديث المجمع بنجاح لعدد (%(count)s) وحدة بالدور، وتحديث الحسابات التراكمية.'
            ) % {'count': updated_records_count},
            'updated_count': updated_records_count,
        })


class BulkUpdateRfiAjaxView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    التحديث المجمع باعتماد طلب الفحص الاستشاري الموحد (Bulk Update by RFI):
    - يتيح اعتماد كافة الشقق المشمولة برقم طلب فحص RFI دفعة واحدة.
    """
    permission_required = 'real_estate.can_verify_site_stages'

    def post(self, request):
        project_id = request.POST.get('project_id')
        rfi_number = request.POST.get('rfi_number', '').strip()
        status_val = request.POST.get('status', UnitSiteProgressRecord.StageStatus.PASSED_AND_VERIFIED)
        if status_val not in UnitSiteProgressRecord.StageStatus.values:
            return JsonResponse({'success': False, 'message': _('حالة البند غير صالحة أو غير معتمدة.')}, status=400)

        try:
            pct_val = int(request.POST.get('completion_percentage', 100))
            if pct_val < 0 or pct_val > 100:
                return JsonResponse({'success': False, 'message': _('نسبة الإنجاز يجب أن تكون بين 0 و 100.')}, status=400)
        except (ValueError, TypeError):
            return JsonResponse({'success': False, 'message': _('نسبة الإنجاز غير صالحة.')}, status=400)

        if not rfi_number:
            return JsonResponse({'success': False, 'message': _('رقم طلب الفحص RFI مطلوب.')}, status=400)

        project = get_object_or_404(RealEstateProject, pk=project_id)
        records = UnitSiteProgressRecord.objects.filter(
            unit__project=project,
            rfi_number=rfi_number,
            is_applicable=True,
            is_billed=False
        ).select_related('unit')

        count = 0
        touched_units = set()
        for rec in records:
            if rec.unit.status in [PropertyUnit.UnitStatus.DELIVERED, PropertyUnit.UnitStatus.DELIVERED_DEEMED]:
                continue
            if rec.is_billed:
                if pct_val < rec.completion_percentage:
                    continue
                if rec.status == UnitSiteProgressRecord.StageStatus.PASSED_AND_VERIFIED and status_val != UnitSiteProgressRecord.StageStatus.PASSED_AND_VERIFIED:
                    continue

            if pct_val > 0 and status_val != UnitSiteProgressRecord.StageStatus.NOT_APPLICABLE:
                valid, prereq_errs = ProjectProgressCalculationService.validate_trade_prerequisites(
                    unit=rec.unit,
                    target_trade=rec.trade_stage
                )
                if not valid:
                    continue

            prev_pct = rec.completion_percentage
            prev_status = rec.status

            rec.status = status_val
            rec.completion_percentage = pct_val
            rec.version += 1
            if status_val == UnitSiteProgressRecord.StageStatus.PASSED_AND_VERIFIED:
                rec.verified_by = request.user
                rec.verified_at = timezone.now()

            # توليد Snag عند الرفض أو الاعتماد المشروط
            if status_val in [
                UnitSiteProgressRecord.StageStatus.REJECTED_DEFECT,
                UnitSiteProgressRecord.StageStatus.APPROVED_WITH_COMMENTS
            ]:
                severity_choice = (
                    UnitSnagItem.SnagSeverity.CRITICAL_BLOCKER
                    if status_val == UnitSiteProgressRecord.StageStatus.REJECTED_DEFECT
                    else UnitSnagItem.SnagSeverity.MAJOR
                )
                snag = UnitSnagItem.objects.create(
                    unit=rec.unit,
                    room_location=rec.get_trade_stage_display(),
                    category=UnitSnagItem.SnagCategory.CIVIL_MASONRY if hasattr(UnitSnagItem.SnagCategory, 'CIVIL_MASONRY') else 'OTHER',
                    severity=severity_choice,
                    description=_('ملاحظة جودة مسجلة من تحديث RFI للبند: %(stage)s') % {
                        'stage': rec.get_trade_stage_display()
                    },
                    contractor=rec.contractor,
                    status=UnitSnagItem.SnagStatus.OPEN,
                    created_by=request.user
                )
                rec.linked_snag = snag

            rec.save()

            SiteProgressAuditLog.objects.create(
                unit=rec.unit,
                unit_code_snapshot=rec.unit.unit_code,
                trade_stage=rec.trade_stage,
                previous_percentage=prev_pct,
                new_percentage=pct_val,
                previous_status=prev_status,
                new_status=status_val,
                defect_notes=f"تحديث مجمع RFI: {rfi_number}",
                changed_by=request.user
            )

            touched_units.add(rec.unit)
            count += 1

        for u in touched_units:
            ProjectProgressCalculationService.calculate_and_save_unit_progress(u)

        ProjectProgressCalculationService.rollup_project_and_block_progress(
            project=project,
            user=request.user,
            post_ifrs15=True
        )

        return JsonResponse({
            'success': True,
            'message': _('تم اعتماد وتحديث عدد %(count)s بند مرتبط برقم RFI: %(rfi)s بنجاح.') % {
                'count': count,
                'rfi': rfi_number
            },
            'updated_count': count,
        })


class ApiSiteProgressBatchSyncView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    واجهة برمجة التطبيقات (API) لمزامنة حزم المعاينات الميدانية المسجلة دون اتصال (Offline Mobile Sync)
    """
    permission_required = 'real_estate.can_verify_site_stages'

    def post(self, request):
        try:
            payload = json.loads(request.body.decode('utf-8'))
            stages_data = payload.get('stages', [])
            if not isinstance(stages_data, list):
                return JsonResponse({'success': False, 'error': 'Invalid payload format: stages must be a list'}, status=400)

            # 1. التحقق الاستباقي الصارم من نوع وصلاحية الحقول لكافة عناصر الحزمة قبل التعديل
            for item in stages_data:
                if not isinstance(item, dict):
                    return JsonResponse({'success': False, 'error': 'Invalid stage item format'}, status=400)
                if 'completion_percentage' in item and item['completion_percentage'] is not None:
                    try:
                        pct_chk = int(item['completion_percentage'])
                        if pct_chk < 0 or pct_chk > 100:
                            return JsonResponse({
                                'success': False,
                                'error': f"نسبة الإنجاز يجب أن تكون بين 0 و 100: {item['completion_percentage']}"
                            }, status=400)
                    except (ValueError, TypeError):
                        return JsonResponse({
                            'success': False,
                            'error': f"قيمة نسبة الإنجاز غير صالحة: {item['completion_percentage']}"
                        }, status=400)
                if 'status' in item and item['status'] is not None:
                    if item['status'] not in UnitSiteProgressRecord.StageStatus.values:
                        return JsonResponse({
                            'success': False,
                            'error': f"حالة البند غير صالحة: {item['status']}"
                        }, status=400)

            synced_count = 0
            synced_record_ids = []
            conflicts = []
            touched_units = set()

            with transaction.atomic():
                for item in stages_data:
                    rec_id = item.get('record_id')
                    sent_ver = item.get('version')
                    rec = UnitSiteProgressRecord.objects.select_related('unit__project').filter(pk=rec_id).first()
                    if not rec:
                        conflicts.append({'record_id': rec_id, 'unit_code': '', 'reason': 'not_found'})
                        continue

                    if rec.unit.status in [PropertyUnit.UnitStatus.DELIVERED, PropertyUnit.UnitStatus.DELIVERED_DEEMED]:
                        conflicts.append({'record_id': rec_id, 'unit_code': rec.unit.unit_code, 'reason': 'unit_already_delivered'})
                        continue

                    new_pct = int(item.get('completion_percentage', rec.completion_percentage))
                    new_status = item.get('status', rec.status)

                    contractor_val = item.get('contractor_id')
                    res_contractor_id = None
                    if contractor_val:
                        try:
                            res_contractor_id = int(contractor_val)
                        except ValueError:
                            pass

                    try:
                        updated_rec, snag_code, unit_pct = SiteProgressExecutionService.update_stage_record_atomic(
                            record_id=rec_id,
                            expected_version=sent_ver,
                            status_val=new_status,
                            completion_percentage=new_pct,
                            user=request.user,
                            contractor_id=res_contractor_id,
                            rfi_number=item.get('rfi_number', ''),
                            notes=item.get('notes', ''),
                            audit_note=_('مزامنة أجهزة دون اتصال (Offline Sync)')
                        )
                        touched_units.add(updated_rec.unit)
                        synced_count += 1
                        synced_record_ids.append(rec_id)
                    except ConcurrencyConflictError:
                        conflicts.append({'record_id': rec_id, 'unit_code': rec.unit.unit_code, 'reason': 'version_mismatch'})
                    except ValidationError as ve:
                        msg = ve.messages[0] if hasattr(ve, 'messages') and ve.messages else (ve.message if hasattr(ve, 'message') else str(ve))
                        conflicts.append({'record_id': rec_id, 'unit_code': rec.unit.unit_code, 'reason': msg})

                touched_projects = set()
                for u in touched_units:
                    ProjectProgressCalculationService.calculate_and_save_unit_progress(u)
                    if u.project:
                        touched_projects.add(u.project)

                for p in touched_projects:
                    ProjectProgressCalculationService.rollup_project_and_block_progress(
                        project=p,
                        user=request.user,
                        post_ifrs15=True
                    )

            return JsonResponse({
                'success': True,
                'synced_count': synced_count,
                'synced_record_ids': synced_record_ids,
                'conflicts': conflicts
            })
        except Exception as e:
            logger.error(f"Sync batch error: {e}", exc_info=True)
            return JsonResponse({'success': False, 'error': str(e)}, status=400)


class SiteDailyLogCreateView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تسجيل يومية الموقع الميدانية (FIDIC Standard Daily Log)
    """
    permission_required = 'real_estate.can_record_site_log'

    def get(self, request, project_id):
        project = get_object_or_404(RealEstateProject, pk=project_id)
        form = SiteDailyLogForm(initial={'project': project, 'log_date': timezone.localdate()})
        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('إدارة المشروعات العقارية'), 'url': reverse('real_estate:project_list'), 'icon': 'fa-city'},
            {'title': project.name, 'url': reverse('real_estate:project_detail', kwargs={'pk': project.pk})},
            {'title': _('تسجيل يومية موقع ميدانية'), 'active': True},
        ]
        return render(request, 'real_estate/site_daily_log_form.html', {
            'form': form,
            'project': project,
            'breadcrumb_items': breadcrumb_items
        })

    def post(self, request, project_id):
        project = get_object_or_404(RealEstateProject, pk=project_id)
        form = SiteDailyLogForm(request.POST)
        if form.is_valid():
            log_instance = form.save(commit=False)
            log_instance.project = project
            log_instance.recorded_by = request.user
            log_instance.save()
            messages.success(request, _('تم توثيق يومية الموقع الميدانية بنجاح.'))
            return redirect('real_estate:site_project_report', project_id=project.id)

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('إدارة المشروعات العقارية'), 'url': reverse('real_estate:project_list'), 'icon': 'fa-city'},
            {'title': project.name, 'url': reverse('real_estate:project_detail', kwargs={'pk': project.pk})},
            {'title': _('تسجيل يومية موقع ميدانية'), 'active': True},
        ]
        return render(request, 'real_estate/site_daily_log_form.html', {
            'form': form,
            'project': project,
            'breadcrumb_items': breadcrumb_items
        })


class SiteFloorInspectionPrintView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    كراسة ومحضر استلام أعمال الدور المعتمد للاستشاري (Printable A4 Floor Sign-off Dossier):
    - تصميم A4 مهيأ للطباعة الرسمية والمطابقة الميدانية.
    - يحتوي على جداول شقق الدور وحالة كل بند واسم المقاول المنفذ.
    - يتضمن مربعات التوقيعات الثلاثية الحية وكود الـ QR للتحقق الرقمي.
    """
    permission_required = 'real_estate.view_unitsiteprogressrecord'

    def get(self, request, floor_id):
        floor = get_object_or_404(
            PropertyFloor.objects.select_related('block__project'),
            pk=floor_id
        )
        project = floor.block.project
        units = floor.units.filter(is_active=True).order_by('unit_code')

        records = UnitSiteProgressRecord.objects.filter(
            unit__in=units
        ).select_related('contractor', 'linked_snag')

        matrix_data = {u.id: {} for u in units}
        for rec in records:
            matrix_data[rec.unit_id][rec.trade_stage] = rec

        trade_choices = UnitSiteProgressRecord.InspectionTrade.choices

        unit_rows = []
        for u in units:
            u_records = matrix_data.get(u.id, {})
            cells = []
            for trade_key, trade_label in trade_choices:
                rec = u_records.get(trade_key)
                cells.append({
                    'trade_key': trade_key,
                    'trade_label': trade_label,
                    'record': rec,
                })
            unit_rows.append({
                'unit': u,
                'cells': cells,
            })

        context = {
            'floor': floor,
            'project': project,
            'units': units,
            'unit_rows': unit_rows,
            'matrix_data': matrix_data,
            'trade_choices': trade_choices,
            'print_date': timezone.localdate(),
            'inspector': request.user,
        }
        return render(request, 'real_estate/site_floor_inspection_dossier.html', context)


class ExportSiteProgressExcelView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تصدير تقرير ومصفوفة الموقع الميدانية إلى إكسيل احترافي (openpyxl):
    - توجيه RTL إجباري.
    - ترويسة ثنائية المستويات مدمجة (Two-Tier Headers).
    - تجميد الألواح على أعمدة الوحدة والدور.
    - أرقام مئوية حقيقية صالحة للعمليات الحسابية.
    """
    permission_required = 'real_estate.view_unitsiteprogressrecord'
    def get(self, request, project_id):
        import openpyxl
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
        from django.http import HttpResponse

        project = get_object_or_404(RealEstateProject, pk=project_id)
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = f"Site_{project.code[:15]}"
        ws.views.sheetView[0].rightToLeft = True

        # الأنماط والتنسيقات المسطحة
        header_fill = PatternFill(start_color="F2F4F7", end_color="F2F4F7", fill_type="solid")
        title_font = Font(name="Arial", size=12, bold=True, color="101828")
        data_font = Font(name="Arial", size=10)
        center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
        thin_border = Border(
            left=Side(style='thin', color='D0D5DD'),
            right=Side(style='thin', color='D0D5DD'),
            top=Side(style='thin', color='D0D5DD'),
            bottom=Side(style='thin', color='D0D5DD')
        )

        # الترويسة الرئيسية
        ws.merge_cells('A1:C1')
        ws['A1'] = f"{project.name} - مصفوفة المتابعة الميدانية للوحدات"
        ws['A1'].font = title_font
        ws['A1'].alignment = Alignment(horizontal="right", vertical="center")

        ws.append([])  # سطر فارغ

        # إعداد أعمدة الجدول
        headers = [
            'البلوك / العمارة',
            'الطابق',
            'كود الوحدة',
            'نسبة إنجاز الوحدة %',
        ]
        trade_choices = UnitSiteProgressRecord.InspectionTrade.choices
        for trade_k, trade_label in trade_choices:
            headers.append(str(trade_label))

        ws.append(headers)
        header_row_idx = ws.max_row
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=header_row_idx, column=col_idx)
            cell.font = Font(name="Arial", size=10, bold=True, color="344054")
            cell.fill = header_fill
            cell.alignment = center_align
            cell.border = thin_border

        # تجميد الألواح عند العمود E
        ws.freeze_panes = 'E4'

        units = PropertyUnit.objects.filter(
            project=project,
            is_active=True
        ).select_related('block', 'floor').order_by('block__code', '-floor__floor_number', 'unit_code')

        records = UnitSiteProgressRecord.objects.filter(
            unit__in=units
        )
        rec_map = {(r.unit_id, r.trade_stage): r.completion_percentage for r in records}

        for u in units:
            row_data = [
                u.block.name if u.block else '-',
                u.floor.name if u.floor else str(u.floor.floor_number if u.floor else '-'),
                u.unit_code,
                float(u.progress_percentage) / 100.0,
            ]
            for trade_key, trade_lbl_val in trade_choices:
                val = rec_map.get((u.id, trade_key), 0)
                row_data.append(float(val) / 100.0)

            ws.append(row_data)
            row_idx = ws.max_row

            # تنسيق النسب المئوية
            ws.cell(row=row_idx, column=4).number_format = '0.0%'
            for col_i in range(5, len(row_data) + 1):
                c = ws.cell(row=row_idx, column=col_i)
                c.number_format = '0%'
                c.alignment = center_align
                c.border = thin_border

        # ضبط عرض الأعمدة
        for col in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="site_progress_{project.code}_{timezone.localdate().strftime("%Y%m%d")}.xlsx"'
        wb.save(response)
        return response


# ==============================================================================
# شاشة وإدارات شجرة مقايسة المشروع WBS وحوكمة الأوزان وجسر التنفيذ الميداني
# ==============================================================================

class ProjectWbsTreeView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    استعراض وإدارة شجرة مقايسة المشروع الهرمية WBS:
    - فحص ومطابقة الأوزان وتوزيع النسب حتى 100%.
    - ربط الحزم بمراحل تنفيذ الوحدات (Unit-to-WBS Bridge).
    - متابعة محطات الإنجاز Milestones وخط الأساس الزمني.
    """
    permission_required = 'real_estate.can_manage_wbs'

    def get(self, request, project_id):
        project = get_object_or_404(RealEstateProject, pk=project_id)
        tree_hierarchy = WbsTreeGovernanceService.build_wbs_tree_hierarchy(project)
        validation_report = WbsTreeGovernanceService.validate_tree_weights(project)

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('الإدارة الهندسية'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-hard-hat'},
            {'title': project.name, 'url': reverse('real_estate:project_detail', kwargs={'pk': project.id})},
            {'title': _('شجرة مقايسة المشروع (WBS)'), 'active': True},
        ]

        header_buttons = [
            {
                'label': _('مصفوفة التنفيذ الميداني'),
                'url': reverse('real_estate:site_project_report', kwargs={'project_id': project.id}),
                'icon': 'fas fa-th',
                'class': 'btn-outline-primary',
            },
            {
                'label': _('تفاصيل المشروع'),
                'url': reverse('real_estate:project_detail', kwargs={'pk': project.id}),
                'icon': 'fas fa-arrow-right',
                'class': 'btn-outline-secondary',
            }
        ]

        form = ProjectActivityForm(initial={'project': project})

        from real_estate.services.evm_service import EarnedValueManagementService
        project_evm = EarnedValueManagementService.calculate_project_evm(project)
        s_curve_data = EarnedValueManagementService.generate_s_curve_data(project)

        context = {
            'project': project,
            'tree_hierarchy': tree_hierarchy,
            'validation_report': validation_report,
            'project_evm': project_evm,
            's_curve_data': s_curve_data,
            'form': form,
            'breadcrumb_items': breadcrumb_items,
            'header_buttons': header_buttons,
        }
        return render(request, 'real_estate/wbs_tree.html', context)


class ProjectWbsSyncUnitProgressAjaxView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    نقطة AJAX لمزامنة شجرة WBS مع سجلات الموقع الميدانية وإعادة تصعيد النسب فورياً:
    """
    permission_required = 'real_estate.can_manage_wbs'

    def post(self, request, project_id):
        project = get_object_or_404(RealEstateProject, pk=project_id)
        synced_count = UnitToWbsBridgeService.sync_unit_progress_to_wbs(project)
        new_progress = WbsTreeGovernanceService.recalculate_tree_rollup(project)

        return JsonResponse({
            'success': True,
            'message': _('تمت مزامنة أنشطة المقايسة المربوطة بالموقع وتحديث نسبة المشروع إلى %(pct)s%% بنجاح.') % {
                'pct': new_progress
            },
            'project_progress': str(new_progress),
            'synced_activities_count': synced_count,
        })


class ProjectWbsActivitySaveAjaxView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    نقطة AJAX لحفظ أو تعديل نشاط WBS مع التحقق الصارم من الحوكمة والأوزان:
    """
    permission_required = 'real_estate.can_manage_wbs'

    def post(self, request, project_id):
        project = get_object_or_404(RealEstateProject, pk=project_id)
        activity_id = request.POST.get('activity_id')
        instance = None
        if activity_id:
            instance = get_object_or_404(ProjectActivity, pk=activity_id, project=project)

        form = ProjectActivityForm(request.POST, instance=instance)
        if form.is_valid():
            activity = form.save(commit=False)
            activity.project = project
            try:
                activity.full_clean()
                activity.save()
                # إعادة تصعيد النسب
                WbsTreeGovernanceService.recalculate_tree_rollup(project)
                return JsonResponse({
                    'success': True,
                    'message': _('تم حفظ نشاط المقايسة بنجاح.'),
                    'activity_id': activity.id,
                })
            except ValidationError as e:
                return JsonResponse({
                    'success': False,
                    'message': ' / '.join(e.messages) if hasattr(e, 'messages') else str(e),
                }, status=400)

        errors_dict = {f: [str(e) for e in errs] for f, errs in form.errors.items()}
        return JsonResponse({
            'success': False,
            'message': _('يرجى تصحيح أخطاء الإدخال الموضحة.'),
            'errors': errors_dict,
        }, status=400)


class ProjectWbsActivityDeleteAjaxView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    نقطة AJAX لحذف نشاط WBS مع التحقق من عدم وجود أنشطة فرعية أو قيود حماية:
    """
    permission_required = 'real_estate.can_manage_wbs'

    def post(self, request, project_id, activity_id):
        project = get_object_or_404(RealEstateProject, pk=project_id)
        activity = get_object_or_404(ProjectActivity, pk=activity_id, project=project)

        if activity.sub_activities.exists():
            return JsonResponse({
                'success': False,
                'message': _('لا يمكن حذف هذا النشاط لوجود أنشطة فرعية تابعة له. يرجى حذف الأنشطة الفرعية أولاً.'),
            }, status=400)

        try:
            activity.delete()
            WbsTreeGovernanceService.recalculate_tree_rollup(project)
            return JsonResponse({
                'success': True,
                'message': _('تم حذف نشاط المقايسة وإعادة احتساب توازن الشجرة بنجاح.'),
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': _('تعذر حذف النشاط لارتباطه بسجلات تشغيلية أخرى: %(err)s') % {'err': str(e)},
            }, status=400)


class ProjectEvmDashboardView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    لوحة تحكم إدارة القيمة المكتسبة ومؤشرات الأداء EVM (CPI / SPI / CV / SV / S-Curve):
    """
    permission_required = 'real_estate.can_manage_wbs'

    def get(self, request, project_id):
        project = get_object_or_404(RealEstateProject, pk=project_id)
        from real_estate.services.evm_service import EarnedValueManagementService

        project_evm = EarnedValueManagementService.calculate_project_evm(project)
        s_curve_data = EarnedValueManagementService.generate_s_curve_data(project)

        # حساب EVM لكافة أنشطة المقايسة
        activities = list(project.wbs_activities.order_by('code'))
        activities_evm = [EarnedValueManagementService.calculate_activity_evm(act) for act in activities]

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('الإدارة الهندسية'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-hard-hat'},
            {'title': project.name, 'url': reverse('real_estate:project_detail', kwargs={'pk': project.id})},
            {'title': _('إدارة القيمة المكتسبة (EVM)'), 'active': True},
        ]

        header_buttons = [
            {
                'label': _('شجرة المقايسة WBS'),
                'url': reverse('real_estate:project_wbs_tree', kwargs={'project_id': project.id}),
                'icon': 'fas fa-sitemap',
                'class': 'btn-outline-primary',
            },
            {
                'label': _('مصفوفة الموقع'),
                'url': reverse('real_estate:site_project_report', kwargs={'project_id': project.id}),
                'icon': 'fas fa-th',
                'class': 'btn-outline-secondary',
            }
        ]

        context = {
            'project': project,
            'project_evm': project_evm,
            'activities_evm': activities_evm,
            's_curve_data': s_curve_data,
            'breadcrumb_items': breadcrumb_items,
            'header_buttons': header_buttons,
        }
        return render(request, 'real_estate/evm_dashboard.html', context)


class ProjectEvmApiView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    نقطة API لاسترجاع مؤشرات EVM ومنحنى S-Curve بتنسيق JSON:
    """
    permission_required = 'real_estate.can_manage_wbs'

    def get(self, request, project_id):
        project = get_object_or_404(RealEstateProject, pk=project_id)
        from real_estate.services.evm_service import EarnedValueManagementService

        project_evm = EarnedValueManagementService.calculate_project_evm(project)
        s_curve_data = EarnedValueManagementService.generate_s_curve_data(project)

        # تحويل القيم المالية لعرضها كـ float/str لتجنب مشاكل Decimal serialization
        serializable_evm = {k: (str(v) if isinstance(v, Decimal) else (v.strftime('%Y-%m-%d') if hasattr(v, 'strftime') else v)) for k, v in project_evm.items()}

        return JsonResponse({
            'success': True,
            'evm': serializable_evm,
            's_curve': s_curve_data,
        })


class MilestoneCollectionAlertsListView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    لوحة متابعة تحصيل أقساط محطات الإنجاز الميدانية (Milestone Collection Alerts Dashboard):
    تعرض للأقسام المالية والتحصيل كافة الأقساط المستحقة بإنجاز محطات WBS بنسبة 100%.
    """
    permission_required = 'real_estate.view_propertycontract'

    def get(self, request):
        alerts_qs = MilestoneCollectionAlert.objects.select_related(
            'contract__customer',
            'contract__project',
            'milestone_activity',
            'milestone_link__installment_item'
        ).order_by('-notified_at')

        # Filters
        project_id = request.GET.get('project')
        if project_id:
            alerts_qs = alerts_qs.filter(contract__project_id=project_id)

        status_filter = request.GET.get('status')
        if status_filter:
            alerts_qs = alerts_qs.filter(status=status_filter)

        search_query = request.GET.get('q', '').strip()
        if search_query:
            alerts_qs = alerts_qs.filter(
                Q(contract__contract_number__icontains=search_query) |
                Q(customer__name__icontains=search_query) |
                Q(milestone_activity__name__icontains=search_query) |
                Q(milestone_activity__code__icontains=search_query)
            )

        # KPIs Calculation
        base_qs = MilestoneCollectionAlert.objects.all()
        if project_id:
            base_qs = base_qs.filter(contract__project_id=project_id)

        total_pending = base_qs.filter(status=MilestoneCollectionAlert.AlertStatus.PENDING)
        total_pending_count = total_pending.count()
        total_pending_amount = total_pending.aggregate(total=Sum('installment_amount'))['total'] or Decimal('0.00')

        total_contacted = base_qs.filter(status=MilestoneCollectionAlert.AlertStatus.CONTACTED)
        total_contacted_count = total_contacted.count()
        total_contacted_amount = total_contacted.aggregate(total=Sum('installment_amount'))['total'] or Decimal('0.00')

        total_collected = base_qs.filter(status=MilestoneCollectionAlert.AlertStatus.COLLECTED)
        total_collected_count = total_collected.count()
        total_collected_amount = total_collected.aggregate(total=Sum('installment_amount'))['total'] or Decimal('0.00')

        total_disputed = base_qs.filter(status=MilestoneCollectionAlert.AlertStatus.DISPUTED)
        total_disputed_count = total_disputed.count()
        total_disputed_amount = total_disputed.aggregate(total=Sum('installment_amount'))['total'] or Decimal('0.00')

        # Pagination
        paginator = Paginator(alerts_qs, 25)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('القطاع العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('إشعارات تحصيل محطات الإنجاز'), 'active': True},
        ]

        context = {
            'page_obj': page_obj,
            'alerts': page_obj.object_list,
            'projects': RealEstateProject.objects.filter(is_archived=False),
            'selected_project': int(project_id) if project_id and project_id.isdigit() else '',
            'selected_status': status_filter or '',
            'search_query': search_query,
            'status_choices': MilestoneCollectionAlert.AlertStatus.choices,
            'total_pending_count': total_pending_count,
            'total_pending_amount': total_pending_amount,
            'total_contacted_count': total_contacted_count,
            'total_contacted_amount': total_contacted_amount,
            'total_collected_count': total_collected_count,
            'total_collected_amount': total_collected_amount,
            'total_disputed_count': total_disputed_count,
            'total_disputed_amount': total_disputed_amount,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 'real_estate',
            'active_submenu': 'milestone_alerts',
        }
        return render(request, 'real_estate/milestone_alerts_list.html', context)


class MilestoneAlertUpdateStatusAjaxView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    نقطة AJAX لتحديث حالة إشعار التحصيل وتدوين إجراءات المتابعة:
    """
    permission_required = 'real_estate.change_propertycontract'

    def post(self, request, alert_id):
        new_status = request.POST.get('status')
        notes = request.POST.get('action_notes', '').strip()

        if not new_status:
            return JsonResponse({'success': False, 'message': _('يرجى تحديد الحالة الجديدة.')}, status=400)

        from real_estate.services.milestone_service import MilestoneCollectionBridgeService
        try:
            alert = MilestoneCollectionBridgeService.update_alert_status(
                alert_id=alert_id,
                new_status=new_status,
                notes=notes,
                user=request.user
            )
            return JsonResponse({
                'success': True,
                'message': _('تم تحديث حالة تنبيه التحصيل بنجاح.'),
                'alert_id': alert.id,
                'new_status': alert.status,
                'new_status_display': alert.get_status_display(),
            })
        except ValidationError as e:
            return JsonResponse({'success': False, 'message': ' / '.join(e.messages) if hasattr(e, 'messages') else str(e)}, status=400)
        except Exception as e:
            logger.error("Failed to update milestone alert %s: %s", alert_id, e)
            return JsonResponse({'success': False, 'message': str(e)}, status=500)




