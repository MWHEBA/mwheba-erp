# -*- coding: utf-8 -*-
"""
Engineering Views - شاشات وعمليات الإدارة الهندسية وضبط الجودة
MWHEBA ERP — Real Estate Architectural Variations, Milestone Guards & Field Snagging
"""
import json
from decimal import Decimal
from datetime import datetime
from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse
from django.core.exceptions import ValidationError
from django.db.models import Q, Sum

from users.mixins import SmartPermissionRequiredMixin
from real_estate.models import (
    ClientVariationOrder,
    UnitSnagItem,
    RealEstateProject,
    PropertyUnit,
    PropertyContract
)
from real_estate.services.variation_service import VariationOrderService
from real_estate.services.snagging_service import OfflineSnaggingSyncService
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
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
