"""
Views إدارة الإجازات
"""
from .base_imports import *
from ..models import Leave, LeaveBalance, Employee, LeaveType
from ..forms.leave_forms import LeaveRequestForm
from ..services.leave_service import LeaveService
from ..decorators import can_approve_leaves
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from datetime import date
import logging

logger = logging.getLogger(__name__)

__all__ = [
    'leave_list',
    'leave_request',
    'leave_detail',
    'leave_approve',
    'leave_reject',
    'leave_cancel',
    'bulk_approve_leaves',
    'bulk_reject_leaves',
    'employee_leave_info_api',
    'leave_update_multiplier',
]


@login_required
def leave_list(request):
    """قائمة الإجازات"""
    # Query Optimization - استثناء الموظفين المنهي خدمتهم
    leaves = Leave.objects.select_related(
        'employee',
        'employee__department',
        'leave_type',
        'approved_by'
    ).exclude(employee__status='terminated')

    # تطبيق الفلاتر
    employee_id = request.GET.get('employee')
    status = request.GET.get('status')
    leave_type_id = request.GET.get('leave_type')
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')

    if employee_id:
        leaves = leaves.filter(employee_id=employee_id)
    if status:
        leaves = leaves.filter(status=status)
    if leave_type_id:
        leaves = leaves.filter(leave_type_id=leave_type_id)
    if from_date:
        leaves = leaves.filter(start_date__gte=from_date)
    if to_date:
        leaves = leaves.filter(end_date__lte=to_date)
    
    # الإحصائيات
    total_leaves = leaves.count()
    pending_leaves = leaves.filter(status='pending').count()
    approved_leaves = leaves.filter(status='approved').count()
    rejected_leaves = leaves.filter(status='rejected').count()
    
    # جلب الموظفين وأنواع الإجازات للفلاتر
    employees = Employee.objects.filter(status='active', is_insurance_only=False)
    leave_types = LeaveType.objects.filter(is_active=True)
    
    # Pagination - 50 إجازة لكل صفحة
    paginator = Paginator(leaves, 50)
    page = request.GET.get('page', 1)
    leaves_page = paginator.get_page(page)
    
    context = {
        'leaves': leaves_page,
        'employees': employees,
        'leave_types': leave_types,
        'total_leaves': total_leaves,
        'pending_leaves': pending_leaves,
        'approved_leaves': approved_leaves,
        'rejected_leaves': rejected_leaves,
        'show_stats': True,
        
        # بيانات الهيدر
        'page_title': 'قائمة الإجازات',
        'page_subtitle': 'إدارة ومتابعة طلبات الإجازات للموظفين',
        'page_icon': 'fas fa-calendar-alt',
        
        # أزرار الهيدر
        'header_buttons': [
            {
                'url': reverse('hr:leave_balance_list'),
                'icon': 'fa-chart-pie',
                'text': 'أرصدة الإجازات',
                'class': 'btn-info',
            },
            {
                'url': reverse('hr:leave_type_list'),
                'icon': 'fa-tags',
                'text': 'أنواع الإجازات',
                'class': 'btn-secondary',
            },
            {
                'url': reverse('hr:leave_request'),
                'icon': 'fa-plus',
                'text': 'طلب إجازة جديد',
                'class': 'btn-primary',
            },
        ],
        
        # البريدكرمب
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'قائمة الإجازات', 'active': True},
        ],
    }
    
    return render(request, 'hr/leave/list.html', context)


@login_required
def leave_request(request):
    """تسجيل إجازة جديدة - HR يطلب نيابة عن الموظف"""

    current_year = date.today().year

    if request.method == 'POST':
        form = LeaveRequestForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                employee = form.cleaned_data['employee']
                leave = form.save(commit=False)
                leave.employee = employee
                leave.requested_by = request.user

                # حساب عدد الأيام
                days_count = (leave.end_date - leave.start_date).days + 1
                leave.days_count = days_count

                # معامل الخصم — يُؤخذ من الفورم لو الإجازة غير مدفوعة
                from decimal import Decimal, InvalidOperation
                user_multiplier = None
                if not leave.leave_type.is_paid:
                    try:
                        multiplier = Decimal(request.POST.get('deduction_multiplier', '1.0'))
                        if multiplier > 0:
                            user_multiplier = multiplier
                    except InvalidOperation:
                        pass  # يبقى الـ default من النوع

                # الإجازات التي لا تحتاج رصيداً مسبقاً تُسجَّل مباشرة
                no_balance_required = not leave.leave_type.requires_balance

                if no_balance_required:
                    leave.save()
                    # تطبيق معامل الخصم بعد الحفظ لتجاوز override الـ save() في الموديل
                    if user_multiplier is not None:
                        Leave.objects.filter(pk=leave.pk).update(deduction_multiplier=user_multiplier)
                    messages.success(request, 'تم تسجيل طلب الإجازة بنجاح')
                    return redirect('hr:leave_detail', pk=leave.pk)

                # التحقق من الرصيد المتاح للإجازات التي تحتاج رصيداً
                balance = LeaveBalance.objects.filter(
                    employee=employee,
                    leave_type=leave.leave_type,
                    year=current_year
                ).first()

                if not balance:
                    messages.error(request, 'لا يوجد رصيد إجازات لهذا النوع للموظف المحدد')
                elif (balance.remaining_days or 0) < days_count:
                    logger.warning(
                        f"رصيد غير كافٍ للموظف {employee.get_full_name_ar()} - "
                        f"المتبقي: {balance.remaining_days}, المطلوب: {days_count}"
                    )
                    messages.error(
                        request,
                        f'رصيد الموظف غير كافٍ. المتبقي: {balance.remaining_days} يوم، المطلوب: {days_count} يوم'
                    )
                else:
                    leave.save()
                    # تطبيق معامل الخصم بعد الحفظ لتجاوز override الـ save() في الموديل
                    if user_multiplier is not None:
                        Leave.objects.filter(pk=leave.pk).update(deduction_multiplier=user_multiplier)
                    messages.success(request, 'تم تسجيل طلب الإجازة بنجاح')
                    return redirect('hr:leave_detail', pk=leave.pk)

            except ValueError as e:
                logger.error(f"خطأ في البيانات عند طلب إجازة: {str(e)}")
                messages.error(request, f'خطأ في البيانات: {str(e)}')
            except Exception as e:
                logger.exception(f"خطأ غير متوقع عند طلب إجازة: {str(e)}")
                messages.error(request, f'حدث خطأ غير متوقع: {str(e)}')
        else:
            messages.error(request, 'يرجى تصحيح الأخطاء في النموذج')
    else:
        form = LeaveRequestForm()

    context = {
        'form': form,
        'current_year': current_year,
        'page_title': 'تسجيل إجازة جديدة',
        'page_subtitle': 'تسجيل طلب إجازة لأحد الموظفين',
        'page_icon': 'fas fa-calendar-plus',
        'header_buttons': [
            {
                'url': reverse('hr:leave_list'),
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'الإجازات', 'url': reverse('hr:leave_list'), 'icon': 'fas fa-calendar-alt'},
            {'title': 'تسجيل إجازة', 'active': True},
        ],
    }
    return render(request, 'hr/leave/request.html', context)


@login_required
def leave_detail(request, pk):
    """تفاصيل الإجازة"""
    leave = get_object_or_404(Leave, pk=pk)
    
    # تحديد الأزرار حسب حالة الإجازة
    header_buttons = []
    if leave.status == 'pending':
        header_buttons.extend([
            {
                'onclick': f'approveLeave({leave.pk})',
                'icon': 'fa-check',
                'text': 'اعتماد',
                'class': 'btn-success',
            },
            {
                'onclick': f'rejectLeave({leave.pk})',
                'icon': 'fa-times',
                'text': 'رفض',
                'class': 'btn-danger',
            },
        ])
    header_buttons.extend([
        {
            'url': reverse('hr:leave_list'),
            'icon': 'fa-arrow-right',
            'text': 'رجوع',
            'class': 'btn-secondary',
        },
    ])
    
    context = {
        'leave': leave,
        'today': date.today(),  # ✅ NEW: لاستخدامه في التحقق من إمكانية الإلغاء
        'page_title': 'تفاصيل الإجازة',
        'page_subtitle': f'{leave.employee.get_full_name_ar()} - {leave.leave_type.name_ar}',
        'page_icon': 'fas fa-calendar-alt',
        'header_buttons': header_buttons,
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': '/', 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': '/hr/', 'icon': 'fas fa-users-cog'},
            {'title': 'الإجازات', 'url': '/hr/leaves/', 'icon': 'fas fa-calendar-alt'},
            {'title': 'تفاصيل الإجازة', 'active': True},
        ],
    }
    return render(request, 'hr/leave/detail.html', context)


@login_required
@can_approve_leaves
def leave_approve(request, pk):
    """اعتماد الإجازة - JSON response للمودال"""
    from django.http import JsonResponse
    leave = get_object_or_404(Leave, pk=pk)
    if request.method == 'POST':
        review_notes = request.POST.get('review_notes', '')
        try:
            LeaveService.approve_leave(leave, request.user, review_notes)
            return JsonResponse({'success': True, 'message': 'تم اعتماد الإجازة بنجاح'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=400)
    return JsonResponse({'success': False, 'message': 'طريقة غير مسموحة'}, status=405)


@login_required
@can_approve_leaves
def leave_reject(request, pk):
    """رفض الإجازة - JSON response للمودال"""
    from django.http import JsonResponse
    leave = get_object_or_404(Leave, pk=pk)
    if request.method == 'POST':
        review_notes = request.POST.get('review_notes', '')
        if not review_notes:
            return JsonResponse({'success': False, 'message': 'يجب إدخال سبب الرفض'}, status=400)
        try:
            LeaveService.reject_leave(leave, request.user, review_notes)
            return JsonResponse({'success': True, 'message': 'تم رفض الإجازة'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=400)
    return JsonResponse({'success': False, 'message': 'طريقة غير مسموحة'}, status=405)


@login_required
@can_approve_leaves
@require_POST
def leave_cancel(request, pk):
    """إلغاء الإجازة - JSON response"""
    from django.http import JsonResponse
    
    leave = get_object_or_404(Leave, pk=pk)
    cancellation_reason = request.POST.get('cancellation_reason', '')
    
    try:
        LeaveService.cancel_leave(leave, request.user, cancellation_reason)
        return JsonResponse({
            'success': True,
            'message': 'تم إلغاء الإجازة واسترداد الرصيد بنجاح'
        })
    except ValueError as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
def employee_leave_info_api(request, employee_id):
    """API - معلومات الموظف وأرصدة إجازاته للاستخدام في فورم الطلب"""
    from django.http import JsonResponse
    try:
        employee = Employee.objects.select_related('department', 'job_title').get(pk=employee_id, status='active')
        current_year = date.today().year

        # جلب كل أنواع الإجازات النشطة
        all_leave_types = LeaveType.objects.filter(is_active=True).order_by('category', 'name_ar')

        # جلب الأرصدة الموجودة للموظف
        balances_qs = LeaveBalance.objects.filter(
            employee=employee,
            year=current_year
        ).select_related('leave_type')

        # تحويل الأرصدة لـ dict للوصول السريع (بدون update — نعرض القيم المحفوظة فقط)
        balances_map = {b.leave_type_id: b for b in balances_qs}

        balances_data = []
        for lt in all_leave_types:
            b = balances_map.get(lt.id)
            no_quota = not lt.requires_balance
            balances_data.append({
                'leave_type_id':       lt.id,
                'leave_type':          lt.name_ar,
                'category':            lt.category,
                'no_quota':            no_quota,
                'is_paid':             lt.is_paid,
                'deduction_multiplier': str(lt.deduction_multiplier),
                'accrued_days':        b.accrued_days if b and not no_quota else 0,
                'used_days':           b.used_days if b else 0,
                'remaining_days':      b.remaining_days if b and not no_quota else 0,
                'has_balance':         b is not None and not no_quota,
                'accrual_phase':       b.accrual_phase if b else 'none',
                'is_manually_adjusted': b.is_manually_adjusted if b else False,
                'adjustment_reason':   b.adjustment_reason if b else '',
            })

        return JsonResponse({
            'success': True,
            'name': employee.get_full_name_ar(),
            'employee_number': employee.employee_number,
            'department': employee.department.name_ar if employee.department else '-',
            'job_title': employee.job_title.title_ar if employee.job_title else '-',
            'balances': balances_data,
        })
    except Employee.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'الموظف غير موجود'}, status=404)


@login_required
@can_approve_leaves
@require_POST
def leave_update_multiplier(request, pk):
    """تعديل معامل الخصم لإجازة غير مدفوعة - JSON"""
    from django.http import JsonResponse
    from decimal import Decimal, InvalidOperation

    leave = get_object_or_404(Leave, pk=pk)

    if leave.leave_type.is_paid:
        return JsonResponse({'success': False, 'error': 'هذه الإجازة مدفوعة — لا يوجد معامل خصم'}, status=400)

    try:
        multiplier = Decimal(request.POST.get('deduction_multiplier', '1.0'))
        if multiplier <= 0:
            return JsonResponse({'success': False, 'error': 'المعامل يجب أن يكون أكبر من صفر'}, status=400)
    except InvalidOperation:
        return JsonResponse({'success': False, 'error': 'قيمة غير صالحة'}, status=400)

    leave.deduction_multiplier = multiplier
    leave.save(update_fields=['deduction_multiplier'])

    return JsonResponse({
        'success': True,
        'message': f'تم تحديث معامل الخصم إلى ×{multiplier}',
        'deduction_multiplier': str(multiplier),
    })
