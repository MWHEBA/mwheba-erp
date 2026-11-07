# -*- coding: utf-8 -*-
"""
Finishing Views & UI/UX Controller
MWHEBA ERP — Track 2: Finishing Packages, Specs Directory, and Governed Dual-Speed Workflow
"""
import logging
from decimal import Decimal
from datetime import date

from django.views.generic import ListView, DetailView, CreateView, UpdateView, TemplateView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse, HttpResponse
from django.urls import reverse, reverse_lazy
from django.db.models import Sum, Count, Q
from django.core.paginator import Paginator
from django.template.loader import render_to_string
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from real_estate.models import (
    RealEstateProject,
    PropertyUnit,
    PropertyContract,
    FinishingWorkspace,
    FinishingBrand,
    ContractualCreditSchedule,
    FinishingItemSpec,
    FinishingPackageTemplate,
    UnitFinishingOrder,
    UnitFinishingOrderItem,
    ClientSelfFinishingPermit,
    FinishingHydrostaticInspection,
    PlasterMoistureInspectionRecord,
    FinishingSecureLockUpRecord,
    FinishingMaterialRequisition,
)
from real_estate.services.finishing_service import (
    FinishingPricingService,
    FinishingWorkflowEngine,
)
from real_estate.services.finishing_inspection_service import (
    FinishingHoldPointEngine,
    FinishingInspectionService,
)
from real_estate.services.finishing_financial_service import (
    FinishingFinancialService,
    FinishingStoreRequisitionService,
    FinishingMaterialReturnService,
)

logger = logging.getLogger(__name__)


class FinishingOrderListView(LoginRequiredMixin, ListView):
    """
    قائمة أوامر تشطيب وتعديلات الوحدات:
    - تدعم التصفية بالبحث العام، المشروع، والمرحلة الميدانية.
    - بطاقات إحصائية للمؤشرات المالية ومؤشرات التنفيذ.
    - دعم التقليب من السيرفر (SSR Pagination) والتحديث التفاعلي عبر AJAX.
    """
    model = UnitFinishingOrder
    template_name = 'real_estate/finishing/finishing_order_list.html'
    context_object_name = 'orders'
    paginate_by = 15

    def get_queryset(self):
        qs = UnitFinishingOrder.objects.select_related('unit', 'unit__project', 'customer', 'contract', 'created_by').all()
        q = self.request.GET.get('q', '').strip()
        project_id = self.request.GET.get('project')
        stage = self.request.GET.get('stage')
        order_type = self.request.GET.get('order_type')

        if q:
            qs = qs.filter(
                Q(order_number__icontains=q) |
                Q(unit__unit_code__icontains=q) |
                Q(customer__name__icontains=q) |
                Q(customer__phone__icontains=q)
            )
        if project_id:
            qs = qs.filter(unit__project_id=project_id)
        if stage:
            qs = qs.filter(current_stage=stage)
        if order_type:
            qs = qs.filter(order_type=order_type)

        return qs.order_by('-id')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        all_orders = UnitFinishingOrder.objects.all()

        context['breadcrumb_items'] = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('التطوير العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('أوامر تشطيب وتعديل الوحدات'), 'active': True}
        ]

        # Header Buttons
        context['header_buttons'] = [
            {
                'url': reverse('real_estate:finishing_kanban'),
                'label': _('لوحة كانبان'),
                'icon': 'fa-columns',
                'class': 'btn-outline-secondary'
            },
            {
                'url': reverse('real_estate:finishing_catalog'),
                'label': _('دليل المواصفات والباقات'),
                'icon': 'fa-palette',
                'class': 'btn-outline-secondary'
            },
            {
                'url': reverse('real_estate:finishing_order_create'),
                'label': _('طلب تشطيب جديد'),
                'icon': 'fa-plus',
                'class': 'btn-primary'
            }
        ]

        # KPI Stats Summary
        context['kpi_stats'] = {
            'total_orders': all_orders.count(),
            'in_execution': all_orders.filter(current_stage='IN_EXECUTION').count(),
            'completed': all_orders.filter(current_stage='COMPLETED').count(),
            'total_volume': all_orders.aggregate(total=Sum('gross_finishing_amount'))['total'] or Decimal('0.00'),
            'total_deposits': all_orders.aggregate(total=Sum('total_deposit_paid'))['total'] or Decimal('0.00'),
        }

        context['projects'] = RealEstateProject.objects.all().only('id', 'name')
        context['stages'] = UnitFinishingOrder.OrderStage.choices
        context['order_types'] = UnitFinishingOrder.OrderType.choices

        context['selected_project'] = self.request.GET.get('project', '')
        context['selected_stage'] = self.request.GET.get('stage', '')
        context['selected_order_type'] = self.request.GET.get('order_type', '')
        context['search_query'] = self.request.GET.get('q', '')

        return context

    def render_to_response(self, context, **response_kwargs):
        if self.request.headers.get('x-requested-with') == 'XMLHttpRequest' or self.request.GET.get('ajax') == '1':
            table_html = render_to_string('real_estate/finishing/partials/finishing_order_table.html', context, request=self.request)
            pagination_html = render_to_string('partials/pagination.html', context, request=self.request)
            summary_html = render_to_string('real_estate/finishing/partials/finishing_order_kpi_cards.html', context, request=self.request)
            return JsonResponse({
                'table_html': table_html,
                'pagination_html': pagination_html,
                'summary_html': summary_html,
            })
        return super().render_to_response(context, **response_kwargs)


class FinishingOrderKanbanView(LoginRequiredMixin, TemplateView):
    """
    لوحة كانبان السداسية المحوكمة لأوامر التشطيب:
    تعرض الطلبات حسب المراحل مع بطاقات الإنجاز والمؤشرات المالية.
    """
    template_name = 'real_estate/finishing/finishing_order_kanban.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['breadcrumb_items'] = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('التطوير العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('أوامر التشطيب'), 'url': reverse('real_estate:finishing_order_list'), 'icon': 'fa-paint-roller'},
            {'title': _('لوحة كانبان'), 'active': True}
        ]

        orders = UnitFinishingOrder.objects.select_related('unit', 'customer').all().order_by('-id')

        kanban_columns = []
        for stage_code, stage_label in UnitFinishingOrder.OrderStage.choices:
            stage_orders = [o for o in orders if o.current_stage == stage_code]
            kanban_columns.append({
                'code': stage_code,
                'title': stage_label,
                'orders': stage_orders,
                'count': len(stage_orders),
                'total_amount': sum(o.gross_finishing_amount for o in stage_orders)
            })

        context['kanban_columns'] = kanban_columns
        return context


class FinishingOrderDetailView(LoginRequiredMixin, DetailView):
    """
    شاشة العرض التفصيلي الشاملة لأمر التشطيب والتعديلات:
    - تفاصيل البنود والمقايسة لكل فراغ معماري.
    - رادار الصمامات الفنية ونقاط التوقف (Hold Points).
    - القيود المالية، الدفعات، وخطة أقساط التشطيب المستقلة.
    """
    model = UnitFinishingOrder
    template_name = 'real_estate/finishing/finishing_order_detail.html'
    context_object_name = 'order'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = self.object

        context['breadcrumb_items'] = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('التطوير العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('أوامر التشطيب'), 'url': reverse('real_estate:finishing_order_list'), 'icon': 'fa-paint-roller'},
            {'title': order.order_number, 'active': True}
        ]

        context['header_buttons'] = [
            {
                'url': reverse('real_estate:finishing_order_print', kwargs={'pk': order.pk}),
                'label': _('طباعة المقايسة والكراسة'),
                'icon': 'fa-print',
                'class': 'btn-outline-secondary',
                'target': '_blank'
            }
        ]

        # بنود المقايسة مصنفة حسب الفراغ المعماري
        items = order.items.select_related('workspace', 'spec', 'brand').all()
        workspaces_dict = {}
        for item in items:
            ws_name = item.workspace.name
            if ws_name not in workspaces_dict:
                workspaces_dict[ws_name] = []
            workspaces_dict[ws_name].append(item)
        context['workspaces_grouped_items'] = workspaces_dict

        # الاختبارات الفنية والميدانية
        context['hydrostatic_tests'] = FinishingHydrostaticInspection.objects.filter(order=order).select_related('workspace')
        context['moisture_records'] = PlasterMoistureInspectionRecord.objects.filter(order=order).select_related('workspace')
        context['lockup_records'] = FinishingSecureLockUpRecord.objects.filter(order=order)
        context['material_requisitions'] = FinishingMaterialRequisition.objects.filter(order=order).select_related('order_item', 'product', 'warehouse')

        # الجدولة المالية
        context['deposits'] = order.deposits.all().order_by('-receipt_date')
        if hasattr(order, 'finishing_installment_plan') and order.finishing_installment_plan:
            context['installment_items'] = order.finishing_installment_plan.items.all().order_by('installment_number')

        return context


class FinishingOrderCreateView(LoginRequiredMixin, CreateView):
    """
    إنشاء أمر تشطيب وتعديل جديد
    """
    model = UnitFinishingOrder
    fields = [
        'unit', 'contract', 'customer', 'title', 'order_type', 'pricing_mode',
        'workflow_speed', 'package', 'execution_duration_days', 'notes'
    ]
    template_name = 'real_estate/finishing/finishing_order_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['breadcrumb_items'] = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('التطوير العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('أوامر التشطيب'), 'url': reverse('real_estate:finishing_order_list'), 'icon': 'fa-paint-roller'},
            {'title': _('طلب تشطيب جديد'), 'active': True}
        ]
        context['units'] = PropertyUnit.objects.filter(status='CONTRACTED').select_related('project')
        context['packages'] = FinishingPackageTemplate.objects.all()
        return context

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.current_stage = 'CUSTOMER_SERVICE'
        # Generate order number
        last_order = UnitFinishingOrder.objects.order_by('-id').first()
        next_seq = (last_order.id + 1) if last_order else 1
        form.instance.order_number = f"FO-{timezone.now().year}-{next_seq:04d}"
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('real_estate:finishing_order_detail', kwargs={'pk': self.object.pk})


class FinishingOrderPrintView(LoginRequiredMixin, DetailView):
    """
    طباعة كراسة ومقايسة مواصفات التشطيب الرسمية A4 للعميل
    """
    model = UnitFinishingOrder
    template_name = 'real_estate/finishing/finishing_order_print.html'
    context_object_name = 'order'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = self.object
        items = order.items.select_related('workspace', 'spec', 'brand').all()

        workspaces_grouped = {}
        for item in items:
            ws_name = item.workspace.name
            if ws_name not in workspaces_grouped:
                workspaces_grouped[ws_name] = []
            workspaces_grouped[ws_name].append(item)

        context['workspaces_grouped_items'] = workspaces_grouped
        if hasattr(order, 'finishing_installment_plan') and order.finishing_installment_plan:
            context['installments'] = order.finishing_installment_plan.items.all().order_by('installment_number')
        return context


class FinishingCatalogView(LoginRequiredMixin, TemplateView):
    """
    دليل كتالوج الخامات والمواصفات وباقات التشطيب
    """
    template_name = 'real_estate/finishing/finishing_catalog_settings.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['breadcrumb_items'] = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('التطوير العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('دليل كتالوج ومواصفات التشطيب'), 'active': True}
        ]
        context['workspaces'] = FinishingWorkspace.objects.all().order_by('project', 'name')
        context['specs'] = FinishingItemSpec.objects.select_related('workspace', 'brand').filter(is_active=True)
        context['packages'] = FinishingPackageTemplate.objects.filter(is_active=True).prefetch_related('items')
        context['credit_schedules'] = ContractualCreditSchedule.objects.all()
        return context


# ==============================================================================
# AJAX Action Endpoints
# ==============================================================================

class ApiFinishingStageTransitionView(LoginRequiredMixin, View):
    """انتقال مرحلة أمر التشطيب محوكماً مع صمامات الأمان"""

    def post(self, request, pk):
        order = get_object_or_404(UnitFinishingOrder, pk=pk)
        target_stage = request.POST.get('target_stage')

        try:
            updated_order = FinishingWorkflowEngine.transition_order_stage(
                order=order,
                target_stage=target_stage,
                user=request.user
            )
            return JsonResponse({
                'success': True,
                'message': _(f"تم بنجاح نقل الطلب للمرحلة: {updated_order.get_current_stage_display()}"),
                'current_stage': updated_order.current_stage,
                'stage_display': updated_order.get_current_stage_display()
            })
        except ValidationError as e:
            return JsonResponse({'success': False, 'message': str(e.message if hasattr(e, 'message') else e)}, status=400)
        except Exception as e:
            logger.exception("Error transitioning finishing stage")
            return JsonResponse({'success': False, 'message': str(e)}, status=500)


class ApiRecordHydrostaticTestView(LoginRequiredMixin, View):
    """تسجيل محضر اختبار كبس أو غمر العزل المائي للفراغ المبتل"""

    def post(self, request, pk):
        order = get_object_or_404(UnitFinishingOrder, pk=pk)
        workspace_id = request.POST.get('workspace_id')
        workspace = get_object_or_404(FinishingWorkspace, pk=workspace_id)
        test_type = request.POST.get('test_type', 'WATER_PROOFING')
        duration_hours = int(request.POST.get('duration_hours', 48))
        pressure_bar = Decimal(request.POST.get('pressure_bar', '0.00'))
        is_passed = request.POST.get('is_passed') == 'true'
        consultant_name = request.POST.get('consultant_name', '')
        notes = request.POST.get('notes', '')

        inspection = FinishingInspectionService.record_hydrostatic_test(
            order=order,
            workspace=workspace,
            test_type=test_type,
            pressure_bar=pressure_bar,
            duration_hours=duration_hours,
            is_passed=is_passed,
            consultant_engineer_name=consultant_name,
            notes=notes
        )
        return JsonResponse({
            'success': True,
            'message': _("تم تسجيل محضر الفحص الهيدروستاتيكي بنجاح."),
            'inspection_id': inspection.id
        })
