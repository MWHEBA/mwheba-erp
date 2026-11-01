# -*- coding: utf-8 -*-
from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.core.paginator import Paginator
from django.contrib import messages
from django.db.models import Q, Count, Sum

from users.mixins import SmartPermissionRequiredMixin
from real_estate.models import RealEstateProject, PropertyBlock, PropertyFloor, PropertyUnit
from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.currency import Currency


class ProjectListView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    قائمة المشروعات العقارية مع فلاتر البحث والترقيم والتبديل الحركي AJAX
    """
    permission_required = 'real_estate.view_realestateproject'

    def get(self, request):
        search_query = request.GET.get('q', '').strip()
        status_filter = request.GET.get('status', '').strip()
        type_filter = request.GET.get('project_type', '').strip()

        projects_qs = RealEstateProject.objects.filter(is_archived=False).annotate(
            units_count=Count('units', filter=Q(units__is_active=True)),
            available_units_count=Count('units', filter=Q(units__is_active=True, units__status='AVAILABLE')),
            contracted_units_count=Count('units', filter=Q(units__is_active=True, units__status='CONTRACTED')),
        ).order_by('-id')

        if search_query:
            projects_qs = projects_qs.filter(
                Q(name__icontains=search_query) |
                Q(code__icontains=search_query)
            )

        if status_filter:
            projects_qs = projects_qs.filter(status=status_filter)

        if type_filter:
            projects_qs = projects_qs.filter(project_type=type_filter)

        paginator = Paginator(projects_qs, 12)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        # استجابة AJAX السريعة للبحث الحركي
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.GET.get('ajax') == '1':
            table_html = render_to_string(
                'real_estate/partials/project_table.html',
                {'page_obj': page_obj, 'projects': page_obj.object_list},
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

        total_projects = RealEstateProject.objects.filter(is_archived=False).count()
        under_construction = RealEstateProject.objects.filter(is_archived=False, status='UNDER_CONSTRUCTION').count()
        completed = RealEstateProject.objects.filter(is_archived=False, status='COMPLETED').count()
        planning = RealEstateProject.objects.filter(is_archived=False, status='PLANNING').count()

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('القطاع العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('المشروعات العقارية'), 'active': True}
        ]

        header_buttons = []
        if request.user.has_perm('real_estate.add_realestateproject') or request.user.is_superuser:
            header_buttons.append({
                'url': reverse('real_estate:project_create'),
                'label': _('مشروع جديد'),
                'icon': 'fa-plus',
                'class': 'btn-primary'
            })

        context = {
            'page_obj': page_obj,
            'projects': page_obj.object_list,
            'total_projects': total_projects,
            'under_construction': under_construction,
            'completed': completed,
            'planning': planning,
            'status_choices': RealEstateProject.ProjectStatus.choices,
            'type_choices': RealEstateProject.ProjectType.choices,
            'breadcrumb_items': breadcrumb_items,
            'header_buttons': header_buttons,
            'active_menu': 'real_estate',
            'active_submenu': 'projects',
        }
        return render(request, 'real_estate/project_list.html', context)


class ProjectDetailView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تفاصيل المشروع العقاري والمباني وإحصاءات الوحدات
    """
    permission_required = 'real_estate.view_realestateproject'

    def get(self, request, pk):
        project = get_object_or_404(RealEstateProject, pk=pk, is_archived=False)
        blocks = project.blocks.filter(is_active=True).prefetch_related('floors')
        units = project.units.filter(is_active=True)

        total_units = units.count()
        available_units = units.filter(status='AVAILABLE').count()
        reserved_units = units.filter(status='RESERVED').count()
        contracted_units = units.filter(status='CONTRACTED').count()

        absorption_rate = (contracted_units / total_units * 100) if total_units > 0 else 0

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('القطاع العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('المشروعات العقارية'), 'url': reverse('real_estate:project_list'), 'icon': 'fa-city'},
            {'title': project.name, 'active': True}
        ]

        header_buttons = [
            {
                'url': reverse('real_estate:project_matrix', kwargs={'project_id': project.id}),
                'label': _('المصفوفة المعمارية'),
                'icon': 'fa-th',
                'class': 'btn-outline-primary'
            },
            {
                'url': reverse('real_estate:project_pricing', kwargs={'project_id': project.id}),
                'label': _('مصفوفة التسعير'),
                'icon': 'fa-tags',
                'class': 'btn-outline-secondary'
            }
        ]

        if request.user.has_perm('real_estate.change_realestateproject') or request.user.is_superuser:
            header_buttons.append({
                'url': reverse('real_estate:project_update', kwargs={'pk': project.id}),
                'label': _('تعديل المشروع'),
                'icon': 'fa-edit',
                'class': 'btn-primary'
            })

        context = {
            'project': project,
            'blocks': blocks,
            'total_units': total_units,
            'available_units': available_units,
            'reserved_units': reserved_units,
            'contracted_units': contracted_units,
            'absorption_rate': round(absorption_rate, 1),
            'recent_units': units.select_related('block', 'floor')[:10],
            'breadcrumb_items': breadcrumb_items,
            'header_buttons': header_buttons,
            'active_menu': 'real_estate',
            'active_submenu': 'projects',
        }
        return render(request, 'real_estate/project_detail.html', context)


class ProjectCreateView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    إنشاء مشروع عقاري جديد
    """
    permission_required = 'real_estate.add_realestateproject'

    def get(self, request):
        currencies = Currency.objects.all()
        escrow_accounts = ChartOfAccounts.objects.filter(is_active=True, is_leaf=True)

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('القطاع العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('المشروعات العقارية'), 'url': reverse('real_estate:project_list'), 'icon': 'fa-city'},
            {'title': _('مشروع جديد'), 'active': True}
        ]

        context = {
            'currencies': currencies,
            'escrow_accounts': escrow_accounts,
            'status_choices': RealEstateProject.ProjectStatus.choices,
            'type_choices': RealEstateProject.ProjectType.choices,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 'real_estate',
            'active_submenu': 'projects',
            'is_edit': False
        }
        return render(request, 'real_estate/project_form.html', context)

    def post(self, request):
        code = request.POST.get('code', '').strip().upper()
        name = request.POST.get('name', '').strip()
        project_type = request.POST.get('project_type', RealEstateProject.ProjectType.RESIDENTIAL)
        status = request.POST.get('status', RealEstateProject.ProjectStatus.PLANNING)
        total_land_area = Decimal(str(request.POST.get('total_land_area', '0.00') or '0.00'))
        gross_built_area = Decimal(str(request.POST.get('gross_built_area', '0.00') or '0.00'))
        start_date = request.POST.get('start_date') or None
        expected_completion_date = request.POST.get('expected_completion_date') or None
        escrow_account_id = request.POST.get('escrow_account') or None

        escrow_account = ChartOfAccounts.objects.filter(pk=escrow_account_id).first() if escrow_account_id else None

        if not code or not name:
            messages.error(request, _('يرجى إدخال كود واسم المشروع.'))
            return redirect('real_estate:project_create')

        project = RealEstateProject.objects.create(
            code=code,
            name=name,
            project_type=project_type,
            status=status,
            total_land_area=total_land_area,
            gross_built_area=gross_built_area,
            start_date=start_date or '2026-01-01',
            expected_completion_date=expected_completion_date or '2027-01-01',
            escrow_account=escrow_account,
            created_by=request.user
        )
        messages.success(request, _('تم إنشاء المشروع العقاري بنجاح.'))
        return redirect('real_estate:project_detail', pk=project.pk)


class ProjectUpdateView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تعديل مشروع عقاري قائم
    """
    permission_required = 'real_estate.change_realestateproject'

    def get(self, request, pk):
        project = get_object_or_404(RealEstateProject, pk=pk, is_archived=False)
        currencies = Currency.objects.all()
        escrow_accounts = ChartOfAccounts.objects.filter(is_active=True, is_leaf=True)

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('القطاع العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('المشروعات العقارية'), 'url': reverse('real_estate:project_list'), 'icon': 'fa-city'},
            {'title': project.name, 'url': reverse('real_estate:project_detail', kwargs={'pk': project.pk})},
            {'title': _('تعديل'), 'active': True}
        ]

        context = {
            'project': project,
            'currencies': currencies,
            'escrow_accounts': escrow_accounts,
            'status_choices': RealEstateProject.ProjectStatus.choices,
            'type_choices': RealEstateProject.ProjectType.choices,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 'real_estate',
            'active_submenu': 'projects',
            'is_edit': True
        }
        return render(request, 'real_estate/project_form.html', context)

    def post(self, request, pk):
        project = get_object_or_404(RealEstateProject, pk=pk, is_active=True)
        project.name = request.POST.get('name', '').strip() or project.name
        project.project_type = request.POST.get('project_type', project.project_type)
        project.status = request.POST.get('status', project.status)
        project.city = request.POST.get('city', '').strip()
        project.district = request.POST.get('district', '').strip()
        project.total_land_area = Decimal(str(request.POST.get('total_land_area', '0.00') or '0.00'))
        project.gross_built_area = Decimal(str(request.POST.get('gross_built_area', '0.00') or '0.00'))
        project.start_date = request.POST.get('start_date') or project.start_date
        project.expected_completion_date = request.POST.get('expected_completion_date') or project.expected_completion_date

        escrow_id = request.POST.get('escrow_account') or None
        project.escrow_account = ChartOfAccounts.objects.filter(pk=escrow_id).first() if escrow_id else None

        curr_id = request.POST.get('currency') or None
        project.currency = Currency.objects.filter(pk=curr_id).first() if curr_id else None

        project.save()
        messages.success(request, _('تم تحديث بيانات المشروع بنجاح.'))
        return redirect('real_estate:project_detail', pk=project.pk)
