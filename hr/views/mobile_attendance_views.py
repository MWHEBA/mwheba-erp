"""
Views بصمة الجوال الذكية PWA وسيلفي الحضور والمزامنة (Mobile Attendance & Supervisor Views)
MWHEBA ERP - Mobile Punch Engine
"""
import json
import logging
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.urls import reverse
from django.utils import timezone

from ..models import Employee, WorkLocation, Shift
from ..services.mobile_punch_service import MobilePunchService
from ..services.geofencing_service import GeofencingService

logger = logging.getLogger(__name__)


from typing import Optional

def _get_current_employee(request) -> Optional[Employee]:
    """استرجاع الموظف المرتبط بالمستخدم الحالي"""
    if hasattr(request.user, 'employee'):
        return request.user.employee
    # البحث بالربط العكسي
    return Employee.objects.filter(user=request.user).first()


@login_required
def self_attendance_view(request):
    """
    عرض واجهة بصمة الموبايل الذكية (PWA Mobile Punch Interface)
    للموظف لتسجيل الحضور والانصراف بالسيلفي والموقع الجغرافي
    """
    employee = _get_current_employee(request)
    if not employee:
        # إذا كان مدير أو مستخدم بدون بروفايل موظف
        first_emp = Employee.objects.filter(status='active').first()
        if request.user.is_superuser and first_emp:
            employee = first_emp
        else:
            return render(request, 'hr/attendance/no_employee_profile.html', {
                'page_title': 'بصمة الجوال الذكية',
                'message': 'حسابك غير مرتبط بملف موظف نشط في النظام. يرجى مراجعة إدارة الموارد البشرية لربط حسابك.'
            })

    context = {
        'employee': employee,
        'page_title': 'بصمة الجوال الذكية',
        'page_subtitle': 'تسجيل الحضور والانصراف الموثق عبر GPS والسيلفي',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:attendance_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'بصمة الجوال الذكية', 'active': True},
        ],
    }
    return render(request, 'hr/attendance/self_attendance.html', context)


@login_required
def supervisor_attendance_view(request):
    """
    عرض واجهة بصمة طاقم العمل للمشرف الميداني (Supervisor Crew Punch)
    """
    if not (request.user.has_perm('hr.add_attendance') or request.user.is_staff or request.user.is_superuser):
        return HttpResponseForbidden('ليس لديك الصلاحية لتسجيل بصمة طواقم العمل.')

    employees = Employee.objects.filter(status='active').order_by('department__name_ar', 'name')

    context = {
        'employees': employees,
        'page_title': 'بصمة طاقم العمل الميداني',
        'page_subtitle': 'تسجيل حضور وانصراف جماعي لفرق العمل والمواقع الإنشائية',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:attendance_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'بصمة طاقم العمل', 'active': True},
        ],
    }
    return render(request, 'hr/attendance/supervisor_crew_punch.html', context)


@login_required
@require_GET
def api_get_punch_context(request):
    """API جلب سياق البصمة الحالي والتوكن الأمني"""
    employee = _get_current_employee(request)
    if not employee:
        emp_id = request.GET.get('employee_id')
        if emp_id and (request.user.is_staff or request.user.is_superuser):
            employee = get_object_or_404(Employee, pk=emp_id)
        else:
            return JsonResponse({'success': False, 'message': 'لا يوجد موظف مرتبط بهذا الحساب.'}, status=400)

    data = MobilePunchService.get_punch_context(employee, request.user)
    return JsonResponse({'success': True, 'data': data})


@login_required
@require_POST
def api_submit_mobile_punch(request):
    """API تسجيل بصمة الجوال الذكية"""
    try:
        if request.content_type == 'application/json':
            payload = json.loads(request.body.decode('utf-8'))
        else:
            payload = request.POST.dict()
    except Exception:
        return JsonResponse({'success': False, 'message': 'بيانات الطلب غير صالحة.'}, status=400)

    employee = _get_current_employee(request)
    target_emp_id = payload.get('employee_id')
    if target_emp_id and (request.user.is_staff or request.user.is_superuser):
        employee = get_object_or_404(Employee, pk=target_emp_id)

    if not employee:
        return JsonResponse({'success': False, 'message': 'تعذر تحديد هوية الموظف.'}, status=400)

    try:
        latitude = float(payload.get('latitude', 0.0))
        longitude = float(payload.get('longitude', 0.0))
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'message': 'الإحداثيات الجغرافية غير صالحة.'}, status=400)

    punch_type = payload.get('punch_type', 'check_in')
    if punch_type not in ['check_in', 'check_out']:
        return JsonResponse({'success': False, 'message': 'نوع البصمة غير صالح (يجب أن يكون check_in أو check_out).'}, status=400)

    res = MobilePunchService.process_mobile_punch(
        employee=employee,
        user=request.user,
        punch_type=punch_type,
        latitude=latitude,
        longitude=longitude,
        location_accuracy=float(payload.get('accuracy', 10.0)) if payload.get('accuracy') else None,
        device_uuid=payload.get('device_uuid'),
        is_mock_flag=bool(payload.get('is_mock', False)),
        speed_kmh=float(payload.get('speed_kmh', 0.0)) if payload.get('speed_kmh') else None,
        punch_token=payload.get('punch_token'),
        selfie_base64=payload.get('selfie_image'),
        is_field_visit=bool(payload.get('is_field_visit', False)),
        field_visit_reason=payload.get('field_visit_reason', ''),
        customer_id=int(payload.get('customer_id')) if payload.get('customer_id') else None,
        work_order_id=int(payload.get('work_order_id')) if payload.get('work_order_id') else None,
        is_emergency=bool(payload.get('is_emergency', False)),
    )

    status_code = 200 if res.get('success') else 400
    return JsonResponse(res, status=status_code)


@login_required
@require_POST
def api_sync_offline_punches(request):
    """API مزامنة البصمات المجمعة أوفلاين"""
    try:
        if request.content_type == 'application/json':
            payload = json.loads(request.body.decode('utf-8'))
        else:
            payload = json.loads(request.POST.get('punches', '[]'))
    except Exception:
        return JsonResponse({'success': False, 'message': 'تنسيق حزمة المزامنة غير صالح.'}, status=400)

    employee = _get_current_employee(request)
    if not employee:
        return JsonResponse({'success': False, 'message': 'تعذر تحديد هوية الموظف.'}, status=400)

    punches_list = payload.get('punches', payload) if isinstance(payload, dict) else payload
    if not isinstance(punches_list, list):
        return JsonResponse({'success': False, 'message': 'قائمة البصمات غير صالحة.'}, status=400)

    res = MobilePunchService.process_offline_sync(
        employee=employee,
        user=request.user,
        punches=punches_list
    )
    return JsonResponse(res)


@login_required
@require_POST
def api_supervisor_crew_punch(request):
    """API تسجيل بصمة طاقم العمل للمشرف"""
    if not (request.user.has_perm('hr.add_attendance') or request.user.is_staff or request.user.is_superuser):
        return JsonResponse({'success': False, 'message': 'ليس لديك الصلاحية لتسجيل بصمة طواقم العمل.'}, status=403)

    try:
        if request.content_type == 'application/json':
            payload = json.loads(request.body.decode('utf-8'))
        else:
            payload = request.POST.dict()
            if 'crew_employee_ids' in payload and isinstance(payload['crew_employee_ids'], str):
                payload['crew_employee_ids'] = json.loads(payload['crew_employee_ids'])
    except Exception:
        return JsonResponse({'success': False, 'message': 'بيانات الطلب غير صالحة.'}, status=400)

    crew_ids = payload.get('crew_employee_ids', [])
    punch_type = payload.get('punch_type', 'check_in')

    try:
        latitude = float(payload.get('latitude', 0.0))
        longitude = float(payload.get('longitude', 0.0))
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'message': 'الإحداثيات الجغرافية غير صالحة.'}, status=400)

    res = MobilePunchService.process_supervisor_crew_punch(
        supervisor_user=request.user,
        crew_employee_ids=crew_ids,
        punch_type=punch_type,
        latitude=latitude,
        longitude=longitude,
        location_accuracy=float(payload.get('accuracy', 10.0)) if payload.get('accuracy') else None,
        selfie_base64=payload.get('selfie_image'),
        notes=payload.get('notes', ''),
    )

    status_code = 200 if res.get('success') else 400
    return JsonResponse(res, status=status_code)
