"""
Views إدارة الأذونات
"""
from .base_imports import *
from ..models import PermissionRequest, PermissionType, Employee
from ..forms.permission_forms import PermissionRequestForm
from hr.services.permission_service import PermissionService
from hr.services.permission_quota_service import PermissionQuotaService
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from ..decorators import require_hr, can_approve_permissions
from django.core.paginator import Paginator
from datetime import date
from dateutil.relativedelta import relativedelta
import logging

logger = logging.getLogger(__name__)

__all__ = [
    'permission_list',
    'permission_request',
    'permission_detail',
    'permission_approve',
    'permission_reject',
    'permission_type_list',
    'permission_type_form',
    'permission_type_delete',
]


@login_required
def permission_list(request):
    """قائمة الأذونات - نسخة من leave_list"""
    # redirect لو مفيش month في الـ URL عشان الفلتر الافتراضي يظهر في الـ select
    from hr.utils.payroll_helpers import get_payroll_month_for_date
    if 'month' not in request.GET:
        current = get_payroll_month_for_date(date.today())
        params = request.GET.copy()
        params['month'] = current.strftime('%Y-%m')
        return redirect(f"{request.path}?{params.urlencode()}")

    # Query Optimization
    permissions = PermissionRequest.objects.select_related(
        'employee',
        'employee__department',
        'permission_type',
        'approved_by'
    ).all()
    
    # الإحصائيات
    total_permissions = permissions.count()
    pending_permissions = permissions.filter(status='pending').count()
    approved_permissions = permissions.filter(status='approved').count()
    rejected_permissions = permissions.filter(status='rejected').count()
    extra_permissions = permissions.filter(is_extra=True).count()

    # بناء قائمة الشهور المتاحة (12 شهر للخلف + الشهر الحالي)
    from hr.utils.payroll_helpers import get_payroll_period, get_payroll_month_for_date
    today = date.today()
    current_payroll_month = get_payroll_month_for_date(today)
    month_choices = []
    for i in range(12):
        m = current_payroll_month - relativedelta(months=i)
        period_start, period_end, _ = get_payroll_period(m)
        month_choices.append({
            'value': m.strftime('%Y-%m'),
            'label': m.strftime('%B %Y'),
            'period_start': period_start,
            'period_end': period_end,
        })

    # تطبيق الفلاتر
    employee_filter = request.GET.get('employee')
    status_filter = request.GET.get('status')
    type_filter = request.GET.get('permission_type')
    is_extra_filter = request.GET.get('is_extra')
    month_filter = request.GET.get('month')

    if employee_filter:
        permissions = permissions.filter(employee_id=employee_filter)
    if status_filter:
        permissions = permissions.filter(status=status_filter)
    if type_filter:
        permissions = permissions.filter(permission_type_id=type_filter)
    if is_extra_filter in ('0', '1'):
        permissions = permissions.filter(is_extra=bool(int(is_extra_filter)))

    # فلتر الشهر مع مراعاة الدورة المرنة
    if month_filter:
        try:
            year, month = map(int, month_filter.split('-'))
            ref_month = date(year, month, 1)
            period_start, period_end, _ = get_payroll_period(ref_month)
            permissions = permissions.filter(date__gte=period_start, date__lte=period_end)
        except (ValueError, AttributeError):
            pass
    else:
        # افتراضياً: الشهر الحالي
        period_start, period_end, _ = get_payroll_period(current_payroll_month)
        permissions = permissions.filter(date__gte=period_start, date__lte=period_end)
        month_filter = current_payroll_month.strftime('%Y-%m')

    # جلب الموظفين وأنواع الأذونات للفلاتر
    employees = Employee.objects.filter(status='active', is_insurance_only=False)
    permission_types = PermissionType.objects.filter(is_active=True)
    
    # Pagination - 30 إذن لكل صفحة
    paginator = Paginator(permissions, 30)
    page = request.GET.get('page', 1)
    permissions_page = paginator.get_page(page)
    
    context = {
        'permissions': permissions_page,
        'employees': employees,
        'permission_types': permission_types,
        'total_permissions': total_permissions,
        'pending_permissions': pending_permissions,
        'approved_permissions': approved_permissions,
        'rejected_permissions': rejected_permissions,
        'extra_permissions': extra_permissions,
        'show_stats': True,
        'month_choices': month_choices,
        'month_filter': month_filter,
        
        # بيانات الهيدر
        'page_title': 'قائمة الأذونات',
        'page_subtitle': 'إدارة ومتابعة طلبات الأذونات للموظفين',
        'page_icon': 'fas fa-clock',
        
        # أزرار الهيدر
        'header_buttons': [
            {
                'url': reverse('hr:permission_type_list'),
                'icon': 'fa-tags',
                'text': 'أنواع الأذونات',
                'class': 'btn-info',
            },
            {
                'url': reverse('hr:permission_request'),
                'icon': 'fa-plus',
                'text': 'تسجيل إذن جديد',
                'class': 'btn-primary',
            },
        ],
        
        # البريدكرمب
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'قائمة الأذونات', 'active': True},
        ],
    }
    
    return render(request, 'hr/permission/list.html', context)


@login_required
@require_hr
def permission_request(request):
    """تسجيل إذن جديد - نسخة من leave_request مع تعديلات للـ HR"""
    from django.conf import settings
    
    current_month = date.today()
    
    # تحديد التاريخ الافتراضي ليكون اليوم
    initial_data = {'date': date.today()}
    
    if request.method == 'POST':
        form = PermissionRequestForm(request.POST)
        if form.is_valid():
            try:
                employee = form.cleaned_data['employee']
                permission_type = form.cleaned_data['permission_type']
                perm_date = form.cleaned_data['date']
                start_time = form.cleaned_data['start_time']
                end_time = form.cleaned_data['end_time']
                reason = form.cleaned_data['reason']
                is_extra = form.cleaned_data.get('is_extra', False)
                deduction_hours = form.cleaned_data.get('deduction_hours', None)
                is_deduction_exempt = form.cleaned_data.get('is_deduction_exempt', False)
                
                # Check if new permission system is enabled
                if getattr(settings, 'PERMISSION_SYSTEM_ENABLED', True):
                    from hr.services.permission_quota_service import PermissionQuotaService
                    
                    # Calculate duration
                    duration = PermissionService._calculate_duration(start_time, end_time)
                    
                    permission_data = {
                        'permission_type': permission_type,
                        'date': perm_date,
                        'start_time': start_time,
                        'end_time': end_time,
                        'duration_hours': duration,
                        'reason': reason,
                        'is_extra': is_extra,
                        'deduction_hours': deduction_hours,
                        'is_deduction_exempt': is_deduction_exempt,
                        'requested_by': request.user,
                        'status': 'pending'
                    }
                    
                    success, result = PermissionQuotaService.create_permission_request(
                        employee_id=employee.id,
                        permission_data=permission_data
                    )
                    
                    if not success:
                        messages.error(request, f'لا يمكن تسجيل الإذن: {result}')
                        # Re-render form with errors
                        context = _get_permission_request_context(form, current_month)
                        return render(request, 'hr/permission/request.html', context)
                    
                    permission = result
                else:
                    # استخدام الخدمة القديمة لإنشاء الإذن (Fallback)
                    permission = PermissionService.request_permission(
                        employee=employee,
                        permission_data={
                            'permission_type': permission_type,
                            'date': perm_date,
                            'start_time': start_time,
                            'end_time': end_time,
                            'reason': reason,
                        },
                        requested_by=request.user
                    )
                
                messages.success(request, 'تم تسجيل الإذن بنجاح')
                return redirect('hr:permission_detail', pk=permission.pk)
                    
            except ValueError as e:
                logger.error(f"خطأ في البيانات عند طلب إذن: {str(e)}")
                messages.error(request, f'خطأ في البيانات: {str(e)}')
            except Exception as e:
                logger.exception(f"خطأ غير متوقع عند طلب إذن: {str(e)}")
                messages.error(request, f'حدث خطأ غير متوقع: {str(e)}')
        else:
            messages.error(request, 'يرجى تصحيح الأخطاء في النموذج')
    else:
        form = PermissionRequestForm(initial=initial_data)
    
    context = _get_permission_request_context(form, current_month)
    return render(request, 'hr/permission/request.html', context)

def _get_permission_request_context(form, current_month):
    import json
    # إرسال أكواد أنواع الأذونات للـ template
    permission_type_codes = {
        str(pt.id): pt.code
        for pt in PermissionType.objects.filter(is_active=True)
    }
    return {
        'form': form,
        'current_month': current_month,
        'permission_type_codes_json': json.dumps(permission_type_codes),
        'page_title': 'تسجيل إذن جديد',
        'page_subtitle': 'تسجيل طلب إذن جديد للموظف',
        'page_icon': 'fas fa-clock',
        'header_buttons': [
            {
                'url': reverse('hr:permission_list'),
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'الأذونات', 'url': reverse('hr:permission_list'), 'icon': 'fas fa-clock'},
            {'title': 'تسجيل إذن', 'active': True},
        ],
    }


@login_required
@require_hr
def get_permission_quota_ajax(request):
    """جلب معلومات حصة الأذونات للموظف عبر AJAX"""
    employee_id = request.GET.get('employee_id')
    date_str = request.GET.get('date')
    
    if not employee_id:
        return JsonResponse({'success': False, 'message': 'معرف الموظف مطلوب'}, status=400)
        
    try:
        employee = Employee.objects.get(id=employee_id)
        
        # تحديد التاريخ
        if date_str:
            from datetime import datetime
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        else:
            target_date = date.today()
            
        # جلب الحصة
        quota_info = PermissionQuotaService.get_monthly_quota_info(employee, target_date)
        
        return JsonResponse({
            'success': True,
            'quota': {
                'used_count': quota_info['used_count'],
                'max_count': quota_info['max_count'],
                'remaining_count': quota_info['remaining_count'],
                'used_hours': float(quota_info['used_hours']),
                'max_hours': float(quota_info['max_hours']),
                'remaining_hours': float(quota_info['remaining_hours']),
                'is_ramadan': quota_info.get('is_ramadan', False)
            }
        })
    except Employee.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'الموظف غير موجود'}, status=404)
    except Exception as e:
        logger.exception(f"خطأ في جلب حصة الأذونات: {str(e)}")
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@login_required
def permission_detail(request, pk):
    """تفاصيل الإذن - نسخة من leave_detail"""
    permission = get_object_or_404(PermissionRequest, pk=pk)
    
    # تحديد الأزرار
    header_buttons = []
    header_buttons.append({
        'url': reverse('hr:permission_list'),
        'icon': 'fa-arrow-right',
        'text': 'رجوع',
        'class': 'btn-secondary',
    })
    
    context = {
        'permission': permission,
        'page_title': 'تفاصيل الإذن',
        'page_subtitle': f'{permission.employee.get_full_name_ar()} - {permission.permission_type.name_ar}',
        'page_icon': 'fas fa-clock',
        'header_buttons': header_buttons,
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'الأذونات', 'url': reverse('hr:permission_list'), 'icon': 'fas fa-clock'},
            {'title': 'تفاصيل الإذن', 'active': True},
        ],
    }
    return render(request, 'hr/permission/detail.html', context)


@login_required
@can_approve_permissions
@login_required
@can_approve_permissions
@require_POST
def permission_approve(request, pk):
    """اعتماد الإذن عبر AJAX"""
    permission = get_object_or_404(PermissionRequest, pk=pk)
    
    if permission.status != 'pending':
        return JsonResponse({
            'success': False,
            'message': 'هذا الإذن تمت معالجته بالفعل'
        })
    
    review_notes = request.POST.get('review_notes', '')
    try:
        PermissionService.approve_permission(permission, request.user, review_notes)
        return JsonResponse({
            'success': True,
            'message': 'تم اعتماد الإذن بنجاح'
        })
    except Exception as e:
        logger.exception(f"خطأ عند اعتماد الإذن: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ أثناء اعتماد الإذن: {str(e)}'
        })


@login_required
@can_approve_permissions
@require_POST
def permission_reject(request, pk):
    """رفض الإذن عبر AJAX"""
    permission = get_object_or_404(PermissionRequest, pk=pk)
    
    if permission.status != 'pending':
        return JsonResponse({
            'success': False,
            'message': 'هذا الإذن تمت معالجته بالفعل'
        })
    
    review_notes = request.POST.get('review_notes', '')
    if not review_notes:
        return JsonResponse({
            'success': False,
            'message': 'يجب إدخال سبب الرفض'
        })
        
    try:
        PermissionService.reject_permission(permission, request.user, review_notes)
        return JsonResponse({
            'success': True,
            'message': 'تم رفض الإذن'
        })
    except Exception as e:
        logger.exception(f"خطأ عند رفض الإذن: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ أثناء رفض الإذن: {str(e)}'
        })



@login_required
@require_hr
def permission_type_list(request):
    """قائمة أنواع الأذونات - للإدارة فقط"""
    permission_types = PermissionType.objects.all().order_by('code')
    
    context = {
        'permission_types': permission_types,
        'page_title': 'أنواع الأذونات',
        'page_subtitle': 'إدارة أنواع الأذونات المتاحة',
        'page_icon': 'fas fa-tags',
        'header_buttons': [
            {
                'url': reverse('hr:permission_list'),
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'الأذونات', 'url': reverse('hr:permission_list'), 'icon': 'fas fa-clock'},
            {'title': 'أنواع الأذونات', 'active': True},
        ],
    }
    return render(request, 'hr/permission/type_list.html', context)


@login_required
@require_hr
def permission_type_form(request, pk=None):
    """إضافة أو تعديل نوع إذن"""
    from ..forms.permission_forms import PermissionTypeForm
    
    if pk:
        permission_type = get_object_or_404(PermissionType, pk=pk)
        title = 'تعديل نوع الإذن'
    else:
        permission_type = None
        title = 'إضافة نوع إذن جديد'
    
    if request.method == 'POST':
        form = PermissionTypeForm(request.POST, instance=permission_type)
        if form.is_valid():
            permission_type = form.save()
            messages.success(request, 'تم حفظ نوع الإذن بنجاح')
            return redirect('hr:permission_type_list')
    else:
        form = PermissionTypeForm(instance=permission_type)
    
    context = {
        'form': form,
        'permission_type': permission_type,
        'page_title': title,
        'page_icon': 'fas fa-tag',
        'header_buttons': [
            {
                'url': reverse('hr:permission_type_list'),
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'أنواع الأذونات', 'url': reverse('hr:permission_type_list'), 'icon': 'fas fa-tags'},
            {'title': title, 'active': True},
        ],
    }
    return render(request, 'hr/permission/type_form.html', context)


@login_required
@require_hr
def permission_type_delete(request, pk):
    """حذف نوع إذن"""
    permission_type = get_object_or_404(PermissionType, pk=pk)
    
    if request.method == 'POST':
        try:
            permission_type.delete()
            messages.success(request, 'تم حذف نوع الإذن بنجاح')
        except Exception as e:
            messages.error(request, f'خطأ في الحذف: {str(e)}')
        return redirect('hr:permission_type_list')
    
    context = {
        'permission_type': permission_type,
        'page_title': 'حذف نوع الإذن',
        'page_icon': 'fas fa-trash',
    }
    return render(request, 'hr/permission/type_confirm_delete.html', context)
