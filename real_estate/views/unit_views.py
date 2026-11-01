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
from django.db.models import Q

from users.mixins import SmartPermissionRequiredMixin
from real_estate.models import RealEstateProject, PropertyBlock, PropertyFloor, PropertyUnit


class UnitListView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    قائمة الوحدات العقارية والمخزون المتاح مع فلاتر البحث وترقيم الصفحات
    """
    permission_required = 'real_estate.view_propertyunit'

    def get(self, request):
        search_query = request.GET.get('q', '').strip()
        project_id = request.GET.get('project', '').strip()
        status_filter = request.GET.get('status', '').strip()
        type_filter = request.GET.get('unit_type', '').strip()

        units_qs = PropertyUnit.objects.filter(is_active=True).select_related('project', 'block', 'floor').order_by('project__name', 'unit_code')

        if search_query:
            units_qs = units_qs.filter(
                Q(unit_code__icontains=search_query) |
                Q(project__name__icontains=search_query) |
                Q(block__name__icontains=search_query)
            )

        if project_id:
            units_qs = units_qs.filter(project_id=project_id)

        if status_filter:
            units_qs = units_qs.filter(status=status_filter)

        if type_filter:
            units_qs = units_qs.filter(unit_type=type_filter)

        paginator = Paginator(units_qs, 20)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.GET.get('ajax') == '1':
            table_html = render_to_string(
                'real_estate/partials/unit_table.html',
                {'page_obj': page_obj, 'units': page_obj.object_list},
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

        total_units = PropertyUnit.objects.filter(is_active=True).count()
        available_count = PropertyUnit.objects.filter(is_active=True, status='AVAILABLE').count()
        reserved_count = PropertyUnit.objects.filter(is_active=True, status='RESERVED').count()
        contracted_count = PropertyUnit.objects.filter(is_active=True, status='CONTRACTED').count()

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('القطاع العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('الوحدات والمخزون العقاري'), 'active': True}
        ]

        header_buttons = []
        if request.user.has_perm('real_estate.add_propertyunit') or request.user.is_superuser:
            header_buttons.append({
                'url': reverse('real_estate:unit_create'),
                'label': _('وحدة جديدة'),
                'icon': 'fa-plus',
                'class': 'btn-primary'
            })

        context = {
            'page_obj': page_obj,
            'units': page_obj.object_list,
            'projects': RealEstateProject.objects.filter(is_archived=False),
            'total_units': total_units,
            'available_count': available_count,
            'reserved_count': reserved_count,
            'contracted_count': contracted_count,
            'status_choices': PropertyUnit.UnitStatus.choices,
            'type_choices': PropertyUnit.UnitType.choices,
            'breadcrumb_items': breadcrumb_items,
            'header_buttons': header_buttons,
            'active_menu': 'real_estate',
            'active_submenu': 'units',
        }
        return render(request, 'real_estate/unit_list.html', context)


class UnitDetailView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تفاصيل ومواصفات الوحدة العقارية
    """
    permission_required = 'real_estate.view_propertyunit'

    def get(self, request, pk):
        unit = get_object_or_404(
            PropertyUnit.objects.select_related('project', 'block', 'floor', 'current_booking__customer'),
            pk=pk,
            is_active=True
        )

        active_contract = unit.contracts.filter(status='ACTIVE').select_related('customer').first()
        bookings = unit.bookings.select_related('customer').order_by('-booking_date')[:5]

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('القطاع العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('الوحدات'), 'url': reverse('real_estate:unit_list'), 'icon': 'fa-th-large'},
            {'title': unit.unit_code, 'active': True}
        ]

        header_buttons = []
        if unit.project:
            header_buttons.append({
                'url': reverse('real_estate:project_matrix', kwargs={'project_id': unit.project_id}),
                'label': _('المصفوفة المعمارية'),
                'icon': 'fa-th',
                'class': 'btn-outline-primary'
            })

        if request.user.has_perm('real_estate.change_propertyunit') or request.user.is_superuser:
            header_buttons.append({
                'url': reverse('real_estate:unit_update', kwargs={'pk': unit.pk}),
                'label': _('تعديل الوحدة'),
                'icon': 'fa-edit',
                'class': 'btn-secondary'
            })

        context = {
            'unit': unit,
            'active_contract': active_contract,
            'bookings': bookings,
            'breadcrumb_items': breadcrumb_items,
            'header_buttons': header_buttons,
            'active_menu': 'real_estate',
            'active_submenu': 'units',
        }
        return render(request, 'real_estate/unit_detail.html', context)


class UnitCreateView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    إضافة وحدة عقارية جديدة
    """
    permission_required = 'real_estate.add_propertyunit'

    def get(self, request):
        projects = RealEstateProject.objects.filter(is_archived=False)
        blocks = PropertyBlock.objects.filter(is_active=True)
        floors = PropertyFloor.objects.all()

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('القطاع العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('الوحدات'), 'url': reverse('real_estate:unit_list'), 'icon': 'fa-th-large'},
            {'title': _('إضافة وحدة جديدة'), 'active': True}
        ]

        context = {
            'projects': projects,
            'blocks': blocks,
            'floors': floors,
            'unit_types': PropertyUnit.UnitType.choices,
            'status_choices': PropertyUnit.UnitStatus.choices,
            'orientations': PropertyUnit.Orientation.choices,
            'view_types': PropertyUnit.ViewType.choices,
            'finishing_types': PropertyUnit.FinishingType.choices,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 'real_estate',
            'active_submenu': 'units',
            'is_edit': False
        }
        return render(request, 'real_estate/unit_form.html', context)

    def post(self, request):
        project_id = request.POST.get('project')
        block_id = request.POST.get('block') or None
        floor_id = request.POST.get('floor') or None
        unit_code = request.POST.get('unit_code', '').strip().upper()
        unit_type = request.POST.get('unit_type', PropertyUnit.UnitType.APARTMENT)
        gross_area = Decimal(str(request.POST.get('gross_area', '0.00') or '0.00'))
        net_area = Decimal(str(request.POST.get('net_area', '0.00') or '0.00'))
        terrace_area = Decimal(str(request.POST.get('terrace_area', '0.00') or '0.00'))
        garden_area = Decimal(str(request.POST.get('garden_area', '0.00') or '0.00'))
        meter_price = Decimal(str(request.POST.get('meter_price', '0.00') or '0.00'))
        garden_price = Decimal(str(request.POST.get('garden_price', '0.00') or '0.00'))
        parking_price = Decimal(str(request.POST.get('parking_price', '0.00') or '0.00'))
        orientation = request.POST.get('orientation', PropertyUnit.Orientation.NORTH)
        view_type = request.POST.get('view_type', PropertyUnit.ViewType.MAIN_STREET)
        is_corner = bool(request.POST.get('is_corner', False))
        finishing_type = request.POST.get('finishing_type', PropertyUnit.FinishingType.SEMI_FINISHED)

        if not project_id or not unit_code or gross_area <= Decimal('0.00') or meter_price <= Decimal('0.00'):
            messages.error(request, _('يرجى استكمال البيانات الإلزامية للوحدة (المشروع، الكود، المساحة، وسعر المتر).'))
            return redirect('real_estate:unit_create')

        project = get_object_or_404(RealEstateProject, pk=project_id)
        block = PropertyBlock.objects.filter(pk=block_id).first() if block_id else None
        floor = PropertyFloor.objects.filter(pk=floor_id).first() if floor_id else None

        unit = PropertyUnit.objects.create(
            project=project,
            block=block,
            floor=floor,
            unit_code=unit_code,
            unit_type=unit_type,
            gross_area=gross_area,
            net_area=net_area if net_area > Decimal('0.00') else gross_area,
            terrace_area=terrace_area,
            garden_area=garden_area,
            meter_price=meter_price,
            garden_price=garden_price,
            parking_price=parking_price,
            orientation=orientation,
            view_type=view_type,
            is_corner=is_corner,
            finishing_type=finishing_type,
            status=PropertyUnit.UnitStatus.AVAILABLE
        )
        messages.success(request, _('تمت إضافة الوحدة العقارية بنجاح.'))
        return redirect('real_estate:unit_detail', pk=unit.pk)


class UnitUpdateView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تعديل وحدة عقارية
    """
    permission_required = 'real_estate.change_propertyunit'

    def get(self, request, pk):
        unit = get_object_or_404(PropertyUnit, pk=pk, is_active=True)
        projects = RealEstateProject.objects.filter(is_archived=False)
        blocks = PropertyBlock.objects.filter(is_active=True)
        floors = PropertyFloor.objects.all()

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('القطاع العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('الوحدات'), 'url': reverse('real_estate:unit_list'), 'icon': 'fa-th-large'},
            {'title': unit.unit_code, 'url': reverse('real_estate:unit_detail', kwargs={'pk': unit.pk})},
            {'title': _('تعديل'), 'active': True}
        ]

        context = {
            'unit': unit,
            'projects': projects,
            'blocks': blocks,
            'floors': floors,
            'unit_types': PropertyUnit.UnitType.choices,
            'status_choices': PropertyUnit.UnitStatus.choices,
            'orientations': PropertyUnit.Orientation.choices,
            'view_types': PropertyUnit.ViewType.choices,
            'finishing_types': PropertyUnit.FinishingType.choices,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 'real_estate',
            'active_submenu': 'units',
            'is_edit': True
        }
        return render(request, 'real_estate/unit_form.html', context)

    def post(self, request, pk):
        unit = get_object_or_404(PropertyUnit, pk=pk, is_active=True)
        unit.unit_type = request.POST.get('unit_type', unit.unit_type)
        unit.gross_area = Decimal(str(request.POST.get('gross_area', '0.00') or '0.00'))
        net_a = Decimal(str(request.POST.get('net_area', '0.00') or '0.00'))
        unit.net_area = net_a if net_a > Decimal('0.00') else unit.gross_area
        unit.terrace_area = Decimal(str(request.POST.get('terrace_area', '0.00') or '0.00'))
        unit.garden_area = Decimal(str(request.POST.get('garden_area', '0.00') or '0.00'))
        unit.meter_price = Decimal(str(request.POST.get('meter_price', '0.00') or '0.00'))
        unit.garden_price = Decimal(str(request.POST.get('garden_price', '0.00') or '0.00'))
        unit.parking_price = Decimal(str(request.POST.get('parking_price', '0.00') or '0.00'))
        unit.orientation = request.POST.get('orientation', unit.orientation)
        unit.view_type = request.POST.get('view_type', unit.view_type)
        unit.is_corner = bool(request.POST.get('is_corner', False))
        unit.finishing_type = request.POST.get('finishing_type', unit.finishing_type)

        unit.base_price = (unit.gross_area * unit.meter_price).quantize(Decimal('0.01'))
        unit.total_price = (unit.base_price + unit.garden_price + unit.parking_price).quantize(Decimal('0.01'))
        unit.save()

        messages.success(request, _('تم حفظ وتحديث بيانات الوحدة بنجاح.'))
        return redirect('real_estate:unit_detail', pk=unit.pk)
