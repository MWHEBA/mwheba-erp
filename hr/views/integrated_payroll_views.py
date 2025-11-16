"""
واجهات معالجة الرواتب المتكاملة
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.db.models import Sum, Count, Q
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.urls import reverse
from datetime import date, timedelta
from ..models import Employee, Payroll, AttendanceSummary, LeaveSummary, PayrollLine
from ..services.integrated_payroll_service import IntegratedPayrollService
from ..services.attendance_summary_service import AttendanceSummaryService
from utils.helpers import arabic_date_format
import logging

logger = logging.getLogger(__name__)


@login_required
@permission_required('hr.can_process_payroll', raise_exception=True)
def integrated_payroll_dashboard(request):
    """لوحة تحكم معالجة الرواتب المتكاملة"""
    
    # الشهر الحالي أو المختار
    selected_month = request.GET.get('month')
    if selected_month:
        try:
            month_date = date.fromisoformat(selected_month + '-01')
        except:
            month_date = date.today().replace(day=1)
    else:
        month_date = date.today().replace(day=1)
    
    # إحصائيات الموظفين
    active_employees = Employee.objects.filter(status='active')
    total_employees = active_employees.count()
    
    # حساب ملخصات الحضور تلقائياً للشهر الحالي (مرة واحدة عند عدم وجود بيانات)
    attendance_summaries = AttendanceSummary.objects.filter(month=month_date)
    if total_employees and not attendance_summaries.exists():
        try:
            AttendanceSummaryService.calculate_all_summaries_for_month(month_date)
            attendance_summaries = AttendanceSummary.objects.filter(month=month_date)
        except Exception as e:
            logger.error(f"فشل التحديث التلقائي لملخصات الحضور لشهر {month_date}: {str(e)}")
            messages.error(request, 'فشل التحديث التلقائي لملخصات الحضور لهذا الشهر، برجاء المراجعة.')
    
    # إحصائيات ملخصات الحضور
    calculated_summaries = attendance_summaries.filter(is_calculated=True).count()
    approved_summaries = attendance_summaries.filter(is_approved=True).count()
    
    # إحصائيات الرواتب
    payrolls = Payroll.objects.filter(month=month_date)
    calculated_payrolls = payrolls.filter(status__in=['calculated', 'approved', 'paid']).count()
    approved_payrolls = payrolls.filter(status__in=['approved', 'paid']).count()
    paid_payrolls = payrolls.filter(status='paid').count()
    
    # الموظفين المتبقيين
    processed_employee_ids = payrolls.values_list('employee_id', flat=True)
    remaining_employees = active_employees.exclude(id__in=processed_employee_ids)
    
    # إحصائيات مالية
    total_gross = payrolls.aggregate(total=Sum('gross_salary'))['total'] or 0
    total_net = payrolls.aggregate(total=Sum('net_salary'))['total'] or 0
    total_deductions = payrolls.aggregate(total=Sum('total_deductions'))['total'] or 0
    
    # إعداد قائمة الأشهر المتاحة (آخر 12 شهر)
    available_months = []
    for i in range(12):
        month = date.today().replace(day=1) - timedelta(days=30 * i)
        available_months.append({
            'value': month.strftime('%Y-%m'),
            'date_obj': month
        })
    
    context = {
        'page_title': 'لوحة معالجة الرواتب',
        'page_subtitle': f'معالجة رواتب شهر {arabic_date_format(month_date).split(" ", 1)[1]}',
        'page_icon': 'fas fa-calculator',
        'month_selector': {
            'current_month': month_date,
            'available_months': available_months
        },
        'header_buttons': [
            {
                'url': reverse('hr:payroll_list'),
                'icon': 'fa-list',
                'text': 'قائمة الرواتب',
                'class': 'btn-outline-primary'
            },
            {
                'onclick': 'submitIntegratedPayroll()',
                'icon': 'fa-play',
                'text': 'معالجة رواتب الشهر',
                'class': 'btn-success',
                'id': 'process-payrolls-header-btn'
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users'},
            {'title': 'الرواتب', 'url': reverse('hr:payroll_list'), 'icon': 'fas fa-money-check-alt'},
            {'title': 'معالجة الرواتب', 'active': True}
        ],
        'current_month': month_date,
        'month_date': month_date,
        'available_months': available_months,
        'total_employees': total_employees,
        'employees_with_contracts': active_employees.filter(contracts__status='active').distinct().count(),
        'employees_without_contracts': total_employees - active_employees.filter(contracts__status='active').distinct().count(),
        'attendance_summaries_count': attendance_summaries.count(),
        'calculated_summaries': calculated_summaries,
        'approved_summaries': approved_summaries,
        'attendance_pending_approval_count': attendance_summaries.filter(is_calculated=True, is_approved=False).count(),
        'attendance_approved_count': attendance_summaries.filter(is_approved=True).count(),
        'payrolls_count': payrolls.count(),
        'calculated_payrolls': calculated_payrolls,
        'approved_payrolls': approved_payrolls,
        'paid_payrolls': paid_payrolls,
        'payroll_calculated_count': calculated_payrolls,
        'payroll_approved_count': approved_payrolls,
        'remaining_employees': remaining_employees,
        'remaining_employees_count': remaining_employees.count(),
        'remaining_count': remaining_employees.count(),
        'total_gross_salary': total_gross,
        'total_net_salary': total_net,
        'total_gross': total_gross,
        'total_net': total_net,
        'total_deductions': total_deductions,
        'progress_percentage': (calculated_payrolls / total_employees * 100) if total_employees > 0 else 0,
        'processing_percentage': (calculated_payrolls / total_employees * 100) if total_employees > 0 else 0,
    }
    
    return render(request, 'hr/payroll/dashboard.html', context)


@login_required
@permission_required('hr.can_process_payroll', raise_exception=True)
@require_POST
def calculate_attendance_summaries(request):
    """حساب ملخصات الحضور لجميع الموظفين"""
    
    month_str = request.POST.get('month')
    if not month_str:
        # استخدام الشهر الحالي إذا لم يتم تحديد شهر
        month_date = date.today().replace(day=1)
    else:
        try:
            month_date = date.fromisoformat(month_str + '-01')
        except (ValueError, TypeError):
            messages.error(request, 'تاريخ غير صحيح')
            return redirect('hr:integrated_payroll_dashboard')
    
    # حساب الملخصات
    results = AttendanceSummaryService.calculate_all_summaries_for_month(month_date)
    
    messages.success(
        request,
        f'تم حساب {len(results["success"])} ملخص حضور بنجاح. '
        f'فشل {len(results["failed"])} ملخص.'
    )
    
    if results['failed']:
        for item in results['failed'][:5]:  # عرض أول 5 أخطاء
            messages.warning(
                request,
                f'{item["employee"].get_full_name_ar()}: {item["error"]}'
            )
    
    url = reverse('hr:integrated_payroll_dashboard') + f'?month={month_date.strftime("%Y-%m")}'
    return redirect(url)


@login_required
@permission_required('hr.can_process_payroll', raise_exception=True)
@require_POST
def process_monthly_payrolls(request):
    """معالجة رواتب الشهر"""
    
    month_str = request.POST.get('month')
    if not month_str:
        # استخدام الشهر الحالي إذا لم يتم تحديد شهر
        month_date = date.today().replace(day=1)
    else:
        try:
            month_date = date.fromisoformat(month_str + '-01')
        except (ValueError, TypeError):
            messages.error(request, 'تاريخ غير صحيح')
            return redirect('hr:integrated_payroll_dashboard')
    
    # معالجة الرواتب
    results = IntegratedPayrollService.process_monthly_payroll_integrated(
        month_date,
        request.user
    )
    
    messages.success(
        request,
        f'تم معالجة {len(results["success"])} راتب بنجاح. '
        f'فشل {len(results["failed"])} راتب.'
    )
    
    if results['failed']:
        for item in results['failed'][:5]:
            messages.warning(
                request,
                f'{item["employee"].get_full_name_ar()}: {item["error"]}'
            )
    
    url = reverse('hr:integrated_payroll_dashboard') + f'?month={month_date.strftime("%Y-%m")}'
    return redirect(url)


@login_required
@permission_required('hr.can_process_payroll', raise_exception=True)
def calculate_single_payroll(request, employee_id):
    """حساب راتب موظف واحد"""
    
    employee = get_object_or_404(Employee, id=employee_id)
    month_str = request.GET.get('month')
    
    try:
        month_date = date.fromisoformat(month_str + '-01')
    except:
        messages.error(request, 'تاريخ غير صحيح')
        return redirect('hr:integrated_payroll_dashboard')
    
    try:
        payroll = IntegratedPayrollService.calculate_integrated_payroll(
            employee,
            month_date,
            request.user
        )
        
        messages.success(
            request,
            f'تم حساب راتب {employee.get_full_name_ar()} بنجاح. '
            f'صافي الراتب: {payroll.net_salary}'
        )
        
        return redirect('hr:payroll_detail', pk=payroll.id)
        
    except Exception as e:
        logger.error(f"فشل حساب راتب {employee.get_full_name_ar()}: {str(e)}")
        messages.error(request, f'فشل حساب الراتب: {str(e)}')
        url = reverse('hr:integrated_payroll_dashboard') + f'?month={month_date.strftime("%Y-%m")}'
    return redirect(url)


@login_required
@permission_required('hr.can_process_payroll', raise_exception=True)
def attendance_summary_detail(request, pk):
    """تفاصيل ملخص الحضور مع عرض احترافي متكامل"""

    summary = get_object_or_404(AttendanceSummary, pk=pk)

    # تحديد بداية ونهاية الشهر
    start_date = summary.month.replace(day=1)
    if summary.month.month == 12:
        end_date = summary.month.replace(year=summary.month.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        end_date = summary.month.replace(month=summary.month.month + 1, day=1) - timedelta(days=1)

    # السجلات اليومية من نموذج Attendance
    daily_records = summary.employee.attendances.filter(
        date__gte=start_date,
        date__lte=end_date,
    ).select_related('shift').order_by('date')

    # إحصائيات ملخص الحضور من AttendanceSummary نفسه
    stats = {
        'total_working_days': summary.total_working_days,
        'present_days': summary.present_days,
        'absent_days': summary.absent_days,
        'late_days': summary.late_days,
        'total_work_hours': summary.total_work_hours,
        'total_late_minutes': summary.total_late_minutes,
        'total_early_leave_minutes': summary.total_early_leave_minutes,
    }

    # عنوان فرعي بالشهر العربي
    month_ar = arabic_date_format(summary.month)
    try:
        # arabic_date_format يرجع مثلاً "السبت 01 يناير 2025" → نأخذ الجزء بعد اليوم
        month_suffix = month_ar.split(' ', 1)[1]
    except Exception:
        month_suffix = summary.month.strftime('%Y-%m')

    context = {
        'summary': summary,
        'employee': summary.employee,
        'daily_records': daily_records,
        'stats': stats,
        'page_title': f'ملخص الحضور - {summary.employee.get_full_name_ar()}',
        'page_subtitle': f'تقرير الحضور لشهر {month_suffix}',
        'page_icon': 'fas fa-calendar-check',
        'header_buttons': [
            {
                'url': reverse('hr:integrated_payroll_dashboard'),
                'icon': 'fa-calculator',
                'text': 'معالجة الرواتب',
                'class': 'btn-outline-primary',
            },
            {
                'url': reverse('hr:payroll_list'),
                'icon': 'fa-money-bill-wave',
                'text': 'قائمة الرواتب',
                'class': 'btn-outline-secondary',
            },
            {
                'onclick': 'window.print()',
                'icon': 'fa-print',
                'text': 'طباعة الملخص',
                'class': 'btn-outline-primary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users-cog'},
            {'title': 'معالجة الرواتب', 'url': reverse('hr:integrated_payroll_dashboard'), 'icon': 'fas fa-calculator'},
            {'title': 'ملخص الحضور', 'active': True},
        ],
    }

    return render(request, 'hr/attendance/attendance_summary_detail.html', context)


@login_required
@permission_required('hr.can_process_payroll', raise_exception=True)
@require_POST
def approve_attendance_summary(request, pk):
    """اعتماد ملخص الحضور"""
    
    summary = get_object_or_404(AttendanceSummary, pk=pk)
    
    if not summary.is_calculated:
        messages.error(request, 'يجب حساب الملخص أولاً قبل الاعتماد')
        return redirect('hr:attendance_summary_detail', pk=pk)
    
    summary.approve(request.user)
    
    messages.success(request, f'تم اعتماد ملخص حضور {summary.employee.get_full_name_ar()}')
    
    return redirect('hr:attendance_summary_detail', pk=pk)


@login_required
@permission_required('hr.can_process_payroll', raise_exception=True)
@require_POST
def recalculate_attendance_summary(request, pk):
    """إعادة حساب ملخص الحضور"""
    
    summary = get_object_or_404(AttendanceSummary, pk=pk)
    
    try:
        AttendanceSummaryService.recalculate_summary(summary)
        messages.success(request, f'تم إعادة حساب ملخص حضور {summary.employee.get_full_name_ar()}')
    except Exception as e:
        logger.error(f"فشل إعادة حساب الملخص: {str(e)}")
        messages.error(request, f'فشل إعادة الحساب: {str(e)}')
    
    return redirect('hr:attendance_summary_detail', pk=pk)


@login_required
def payroll_print(request, pk):
    """طباعة قسيمة راتب"""
    payroll = get_object_or_404(
        Payroll.objects.select_related('employee', 'contract', 'processed_by', 'approved_by'),
        pk=pk
    )
    
    # التحقق من الصلاحيات
    if not request.user.has_perm('hr.can_view_all_salaries'):
        if not hasattr(request.user, 'employee_profile') or request.user.employee_profile != payroll.employee:
            messages.error(request, 'ليس لديك صلاحية لعرض هذه القسيمة')
            return redirect('hr:payroll_list')
    
    # جلب بنود القسيمة
    payroll_lines_earnings = payroll.lines.filter(component_type='earning').order_by('order')
    payroll_lines_deductions = payroll.lines.filter(component_type='deduction').order_by('order')
    
    # جلب ملخص الحضور
    attendance_summary = AttendanceSummary.objects.filter(
        employee=payroll.employee,
        month=payroll.month
    ).first()
    
    context = {
        'payroll': payroll,
        'payroll_lines_earnings': payroll_lines_earnings,
        'payroll_lines_deductions': payroll_lines_deductions,
        'attendance_summary': attendance_summary,
        'company_name': 'اسم الشركة',  # يمكن جلبها من الإعدادات
        'company_logo': None,  # يمكن جلبها من الإعدادات
    }
    
    return render(request, 'hr/payroll/print.html', context)

