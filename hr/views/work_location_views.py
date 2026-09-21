"""
Views إدارة المقرات الجغرافية وبصمة الأجهزة (Work Locations & Device Binding Management)
MWHEBA ERP
"""
from decimal import Decimal
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.urls import reverse
from django.db.models import Count

from ..models.work_location import WorkLocation
from ..models.employee import Employee
from ..services.geofencing_service import GeofencingService
from users.decorators import require_permission


__all__ = [
    'work_location_list',
    'work_location_save',
    'work_location_delete',
    'work_location_toggle',
    'reset_employee_device_binding',
]


@login_required
@require_permission('hr.view_attendance')
def work_location_list(request):
    """عرض قائمة مقرات العمل الجغرافية المعتمدة"""
    locations = WorkLocation.objects.annotate(
        employees_count=Count('employees')
    ).all().order_by('-is_default', 'name_ar')

    stats = {
        'total': locations.count(),
        'active': locations.filter(is_active=True).count(),
        'default': locations.filter(is_default=True).first(),
        'total_assigned_employees': sum(loc.employees_count for loc in locations),
    }

    context = {
        'locations': locations,
        'stats': stats,
        'page_title': 'مقرات العمل الجغرافية',
        'page_subtitle': 'إدارة الفروع والنطاق الجغرافي للبصمة (Geofencing)',
        'page_icon': 'fas fa-map-marked-alt',
        'header_buttons': [
            {
                'text': 'إضافة مقر عمل',
                'icon': 'fa-plus',
                'class': 'btn-primary',
                'attrs': 'onclick="openWorkLocationModal()"',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'مقرات العمل الجغرافية', 'active': True},
        ],
    }
    return render(request, 'hr/work_location/list.html', context)


@login_required
@require_POST
def work_location_save(request):
    """إضافة أو تعديل مقر عمل جغرافي عبر AJAX"""
    if not (request.user.has_perm('hr.change_worklocation') or request.user.is_staff or request.user.is_superuser):
        return JsonResponse({'success': False, 'message': 'ليس لديك الصلاحية لإدارة مقرات العمل.'}, status=403)

    location_id = request.POST.get('location_id')
    name_ar = request.POST.get('name_ar', '').strip()
    name_en = request.POST.get('name_en', '').strip()
    address = request.POST.get('address', '').strip()
    latitude_raw = request.POST.get('latitude')
    longitude_raw = request.POST.get('longitude')
    radius_raw = request.POST.get('radius_meters', '100')
    is_active = request.POST.get('is_active') == 'on' or request.POST.get('is_active') == 'true'
    is_default = request.POST.get('is_default') == 'on' or request.POST.get('is_default') == 'true'

    if not name_ar:
        return JsonResponse({'success': False, 'message': 'يرجى إدخال اسم المقر بالعربية.'}, status=400)

    try:
        latitude = Decimal(str(latitude_raw).strip())
        longitude = Decimal(str(longitude_raw).strip())
    except Exception:
        return JsonResponse({'success': False, 'message': 'يرجى إدخال إحداثيات جغرافية صحيحة (خط العرض وخط الطول).'}, status=400)

    if not (-90 <= float(latitude) <= 90) or not (-180 <= float(longitude) <= 180):
        return JsonResponse({'success': False, 'message': 'الإحداثيات المدخلة خارج النطاق الجغرافي للكرة الأرضية.'}, status=400)

    try:
        radius_meters = int(radius_raw)
        if radius_meters < 10 or radius_meters > 50000:
            return JsonResponse({'success': False, 'message': 'نصف قطر البصمة يجب أن يكون بين 10 أمتار و 50000 متر.'}, status=400)
    except ValueError:
        return JsonResponse({'success': False, 'message': 'نصف قطر النطاق غير صالح.'}, status=400)

    if location_id:
        location = get_object_or_404(WorkLocation, pk=location_id)
        location.name_ar = name_ar
        location.name_en = name_en
        location.address = address
        location.latitude = latitude
        location.longitude = longitude
        location.radius_meters = radius_meters
        location.is_active = is_active
        location.is_default = is_default
        location.save()
        action_msg = 'تم تعديل بيانات مقر العمل بنجاح.'
    else:
        location = WorkLocation.objects.create(
            name_ar=name_ar,
            name_en=name_en,
            address=address,
            latitude=latitude,
            longitude=longitude,
            radius_meters=radius_meters,
            is_active=is_active,
            is_default=is_default,
        )
        action_msg = 'تم إنشاء مقر العمل الجغرافي بنجاح.'

    return JsonResponse({
        'success': True,
        'message': action_msg,
        'data': {
            'id': location.id,
            'name_ar': location.name_ar,
            'latitude': float(location.latitude),
            'longitude': float(location.longitude),
            'radius_meters': location.radius_meters,
            'is_active': location.is_active,
            'is_default': location.is_default,
        }
    })


@login_required
@require_POST
def work_location_delete(request, pk):
    """حذف مقر عمل جغرافي"""
    if not (request.user.has_perm('hr.delete_worklocation') or request.user.is_superuser):
        return JsonResponse({'success': False, 'message': 'ليس لديك الصلاحية لحذف مقرات العمل.'}, status=403)

    location = get_object_or_404(WorkLocation, pk=pk)
    if location.is_default:
        return JsonResponse({'success': False, 'message': 'لا يمكن حذف المقر الرئيسي الافتراضي للنظام. يرجى تعيين مقر آخر كافتراضي أولاً.'}, status=400)

    # فحص الموظفين المرتبطين
    emp_count = location.employees.count()
    if emp_count > 0:
        return JsonResponse({
            'success': False,
            'message': f'لا يمكن حذف هذا المقر لوجود {emp_count} موظف مرتبطين به حالياً. يمكنك تعطيل المقر بدلاً من حذفه.'
        }, status=400)

    location.delete()
    return JsonResponse({'success': True, 'message': 'تم حذف مقر العمل بنجاح.'})


@login_required
@require_POST
def work_location_toggle(request, pk):
    """تفعيل أو تعطيل مقر عمل"""
    if not (request.user.has_perm('hr.change_worklocation') or request.user.is_superuser):
        return JsonResponse({'success': False, 'message': 'ليس لديك الصلاحية لتعديل مقرات العمل.'}, status=403)

    location = get_object_or_404(WorkLocation, pk=pk)
    location.is_active = not location.is_active
    location.save()
    status_text = 'تفعيل' if location.is_active else 'تعطيل'
    return JsonResponse({'success': True, 'message': f'تم {status_text} مقر العمل بنجاح.', 'is_active': location.is_active})


@login_required
@require_POST
def reset_employee_device_binding(request, employee_id):
    """فك ارتباط هاتف الموظف (Device Binding Reset)"""
    if not (request.user.has_perm('hr.can_reset_device_binding') or request.user.is_superuser or getattr(request.user, 'is_admin', False)):
        return JsonResponse({'success': False, 'message': 'ليس لديك الصلاحية لفك ارتباط أجهزة الموظفين.'}, status=403)

    employee = get_object_or_404(Employee, pk=employee_id)
    reason = request.POST.get('reason', 'فك ارتباط بواسطة مسؤول الموارد البشرية').strip()

    if not employee.registered_device_uuid:
        return JsonResponse({'success': False, 'message': 'هذا الموظف غير مرتبط بأي هاتف حالياً.'}, status=400)

    GeofencingService.reset_device_binding(employee, request.user, reason=reason)

    return JsonResponse({
        'success': True,
        'message': f'تم فك ارتباط هاتف الموظف ({employee.get_full_name_ar()}) بنجاح. سيتمكن الموظف من ربط هاتفه الجديد عند أول تسجيل دخول.'
    })
