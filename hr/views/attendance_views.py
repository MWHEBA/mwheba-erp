"""
Views إدارة الحضور
"""
from .base_imports import *
from django.views.decorators.http import require_POST
from ..models import Employee, Department, Shift, BiometricLog, AttendanceSummary, Attendance
from ..services.attendance_service import AttendanceService
from ..services.attendance_summary_service import AttendanceSummaryService

__all__ = [
    'attendance_list',
    'attendance_check_in',
    'attendance_check_out',
    'attendance_summary_detail',
    'approve_attendance_summary',
    'recalculate_attendance_summary',
]


@login_required
def attendance_list(request):
    """قائمة الحضور - محلل ذكي من BiometricLog"""
    from collections import defaultdict
    
    # الفلاتر
    # التاريخ - افتراضي الشهر الحالي
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if not date_from:
        # أول يوم في الشهر الحالي
        date_from = date.today().replace(day=1).strftime('%Y-%m-%d')
    if not date_to:
        # اليوم الحالي
        date_to = date.today().strftime('%Y-%m-%d')
    
    date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
    date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
    
    # فلتر القسم
    department_id = request.GET.get('department')
    
    # فلتر الموظف
    employee_id = request.GET.get('employee')
    
    # جلب سجلات البصمة للفترة المحددة
    logs = BiometricLog.objects.filter(
        timestamp__date__gte=date_from_obj,
        timestamp__date__lte=date_to_obj,
        employee__isnull=False
    ).select_related('employee', 'employee__department')
    
    # تطبيق فلتر القسم
    if department_id:
        logs = logs.filter(employee__department_id=department_id)
    
    # تطبيق فلتر الموظف
    if employee_id:
        logs = logs.filter(employee_id=employee_id)
    
    logs = logs.order_by('employee', 'timestamp')
    
    # تجميع السجلات حسب الموظف واليوم
    employee_daily_logs = defaultdict(lambda: defaultdict(list))
    for log in logs:
        log_date = log.timestamp.date()
        employee_daily_logs[log.employee.id][log_date].append(log)
    
    # تحليل الحضور لكل موظف في كل يوم
    attendance_data = []
    
    for emp_id, daily_logs in employee_daily_logs.items():
        # معالجة كل يوم على حدة
        for log_date, day_logs in sorted(daily_logs.items()):
            if not day_logs:
                continue
            
            # ترتيب السجلات حسب الوقت
            day_logs.sort(key=lambda x: x.timestamp)
            
            employee = day_logs[0].employee
            total_movements = len(day_logs)
            movements = [log.timestamp for log in day_logs]
            
            # أول حركة = حضور
            check_in = movements[0]
            check_out = None
            
            # منطق ذكي للانصراف
            if total_movements == 1:
                # بصمة واحدة فقط - نعتبرها حضور بدون انصراف
                check_out = None
            elif total_movements == 2:
                # بصمتين - الثانية انصراف
                check_out = movements[1]
            else:
                # أكثر من بصمتين - نحلل
                # نبحث عن أكبر فجوة زمنية (تدل على خروج ثم عودة)
                max_gap = timedelta(0)
                potential_checkout = None
                
                for i in range(len(movements) - 1):
                    gap = movements[i + 1] - movements[i]
                    # لو الفجوة أكبر من ساعتين، نعتبرها خروج
                    if gap > timedelta(hours=2) and gap > max_gap:
                        max_gap = gap
                        potential_checkout = movements[i]
                
                # لو لقينا فجوة كبيرة، نستخدمها كانصراف
                # لو مافيش، نستخدم آخر بصمة
                if potential_checkout and max_gap > timedelta(hours=2):
                    check_out = potential_checkout
                else:
                    check_out = movements[-1]
            
            # حساب ساعات العمل
            work_hours = 0
            late_minutes = 0
            early_leave_minutes = 0
            status = 'present'
            
            if check_in and check_out:
                work_duration = check_out - check_in
                work_hours = round(work_duration.total_seconds() / 3600, 2)
                
                # الحصول على الوردية المربوطة بالموظف
                employee_shift = employee.shift if hasattr(employee, 'shift') and employee.shift else None
                
                if employee_shift:
                    # استخدام أوقات الوردية
                    work_start = datetime.combine(log_date, employee_shift.start_time)
                    work_start = timezone.make_aware(work_start)
                    
                    work_end = datetime.combine(log_date, employee_shift.end_time)
                    work_end = timezone.make_aware(work_end)
                else:
                    # افتراضي: 9 صباحاً - 5 مساءً
                    work_start = datetime.combine(log_date, datetime.strptime('09:00', '%H:%M').time())
                    work_start = timezone.make_aware(work_start)
                    
                    work_end = datetime.combine(log_date, datetime.strptime('17:00', '%H:%M').time())
                    work_end = timezone.make_aware(work_end)
                
                # حساب التأخير
                if check_in > work_start:
                    late_duration = check_in - work_start
                    late_minutes = int(late_duration.total_seconds() / 60)
                    if late_minutes > 15:
                        status = 'late'
                
                # حساب الانصراف المبكر
                if check_out < work_end:
                    early_duration = work_end - check_out
                    early_leave_minutes = int(early_duration.total_seconds() / 60)
                    if early_leave_minutes > 15:
                        if status == 'late':
                            status = 'late'  # يبقى متأخر
                        else:
                            status = 'early_leave'
            
            summary, _ = AttendanceSummary.objects.get_or_create(
                employee=employee,
                month=log_date.replace(day=1)
            )

            attendance_data.append({
                'employee': employee,
                'date': log_date,
                'check_in': check_in,
                'check_out': check_out,
                'work_hours': work_hours,
                'late_minutes': late_minutes,
                'early_leave_minutes': early_leave_minutes,
                'status': status,
                'total_movements': total_movements,
                'movements': movements,
                'summary_id': summary.id
            })
    
    # ترتيب حسب التاريخ ثم اسم الموظف
    attendance_data.sort(key=lambda x: (x['date'], x['employee'].get_full_name_ar()), reverse=True)
    
    # حساب الإحصائيات
    present_count = sum(1 for a in attendance_data if a['status'] == 'present')
    late_count = sum(1 for a in attendance_data if a['status'] == 'late')
    absent_count = 0  # سيتم حسابه لاحقاً من قائمة الموظفين
    on_leave_count = 0  # من نظام الإجازات
    
    # جلب قوائم الفلاتر
    departments = Department.objects.filter(is_active=True).order_by('name_ar')
    employees = Employee.objects.filter(status='active').order_by('first_name_ar')
    
    # إعداد headers للجدول الموحد
    headers = [
        {'key': 'date', 'label': 'التاريخ', 'sortable': True, 'width': '9%', 'template': 'hr/attendance/cells/date.html'},
        {'key': 'employee', 'label': 'الموظف', 'sortable': True, 'width': '13%', 'template': 'hr/attendance/cells/employee.html'},
        {'key': 'department', 'label': 'القسم', 'sortable': True, 'width': '10%', 'template': 'hr/attendance/cells/department.html'},
        {'key': 'check_in', 'label': 'الحضور', 'sortable': True, 'width': '9%', 'class': 'text-center', 'template': 'hr/attendance/cells/check_in.html'},
        {'key': 'check_out', 'label': 'الانصراف', 'sortable': True, 'width': '9%', 'class': 'text-center', 'template': 'hr/attendance/cells/check_out.html'},
        {'key': 'work_hours', 'label': 'ساعات العمل', 'sortable': True, 'width': '9%', 'class': 'text-center', 'template': 'hr/attendance/cells/work_hours.html'},
        {'key': 'late_minutes', 'label': 'التأخير', 'sortable': True, 'width': '7%', 'class': 'text-center', 'template': 'hr/attendance/cells/late_minutes.html'},
        {'key': 'early_leave_minutes', 'label': 'انصراف مبكر', 'sortable': True, 'width': '8%', 'class': 'text-center', 'template': 'hr/attendance/cells/early_leave.html'},
        {'key': 'total_movements', 'label': 'الحركات', 'sortable': True, 'width': '7%', 'class': 'text-center', 'template': 'hr/attendance/cells/movements.html'},
        {'key': 'status', 'label': 'الحالة', 'sortable': True, 'width': '8%', 'class': 'text-center', 'template': 'hr/attendance/cells/status.html'},
        {'key': 'actions', 'label': 'التفاصيل', 'sortable': False, 'width': '8%', 'class': 'text-center', 'template': 'hr/attendance/cells/actions.html'},
    ]
    
    context = {
        'attendance_data': attendance_data,
        'headers': headers,
        'date_from': date_from,
        'date_to': date_to,
        'date_from_display': date_from_obj,
        'date_to_display': date_to_obj,
        'today': date.today(),
        'present_count': present_count,
        'late_count': late_count,
        'absent_count': absent_count,
        'on_leave_count': on_leave_count,
        'departments': departments,
        'employees': employees,
        
        # بيانات الهيدر الموحد
        'page_title': 'سجل الحضور',
        'page_subtitle': f'متابعة حضور وانصراف الموظفين من نظام البصمة ({date_from_obj.strftime("%d/%m/%Y")} - {date_to_obj.strftime("%d/%m/%Y")})',
        'page_icon': 'fas fa-clock',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users-cog'},
            {'title': 'سجل الحضور', 'active': True},
        ],
    }
    return render(request, 'hr/attendance/list.html', context)


@login_required
def attendance_check_in(request):
    """تسجيل الحضور"""
    if request.method == 'POST':
        employee_id = request.POST.get('employee_id')
        shift_id = request.POST.get('shift_id')
        
        if employee_id:
            try:
                employee = Employee.objects.get(pk=employee_id)
                shift = Shift.objects.get(pk=shift_id) if shift_id else None
                
                attendance = AttendanceService.check_in(employee, shift)
                messages.success(request, f'تم تسجيل حضور {employee.get_full_name_ar()} بنجاح')
                return redirect('hr:attendance_list')
            except Exception as e:
                messages.error(request, f'خطأ: {str(e)}')
        else:
            messages.error(request, 'يرجى اختيار الموظف')
    
    context = {
        'employees': Employee.objects.filter(status='active'),
        'shifts': Shift.objects.filter(is_active=True)
    }
    return render(request, 'hr/attendance/check_in.html', context)


@login_required
def attendance_summary_detail(request, pk):
    """
    عرض تفاصيل ملخص الحضور لموظف معين في شهر معين.
    """
    summary = get_object_or_404(AttendanceSummary, pk=pk)

    # تحديد بداية ونهاية الشهر بناءً على حقل month في الملخص
    start_date = summary.month.replace(day=1)
    if summary.month.month == 12:
        end_date = summary.month.replace(year=summary.month.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        end_date = summary.month.replace(month=summary.month.month + 1, day=1) - timedelta(days=1)

    # السجلات اليومية من نموذج Attendance
    daily_records = Attendance.objects.filter(
        employee=summary.employee,
        date__gte=start_date,
        date__lte=end_date,
    ).select_related("shift").order_by("date")

    # إحصائيات جاهزة من نموذج AttendanceSummary نفسه
    stats = {
        "total_working_days": summary.total_working_days,
        "present_days": summary.present_days,
        "absent_days": summary.absent_days,
        "late_days": summary.late_days,
        "total_work_hours": summary.total_work_hours,
        "total_late_minutes": summary.total_late_minutes,
        "total_early_leave_minutes": summary.total_early_leave_minutes,
    }

    context = {
        'summary': summary,
        'employee': summary.employee,
        'daily_records': daily_records,
        'stats': stats,
        'page_title': f'ملخص الحضور - {summary.employee.get_full_name_ar()}',
        'page_subtitle': f'تقرير مفصل لشهر {summary.month.strftime("%B %Y")}',
        'page_icon': 'fas fa-calendar-check',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard')},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard')},
            {'title': 'سجل الحضور', 'url': reverse('hr:attendance_list')},
            {'title': 'تفاصيل الملخص', 'active': True},
        ],
    }
    return render(request, 'hr/attendance/attendance_summary_detail.html', context)


@login_required
@require_POST
def approve_attendance_summary(request, pk):
    """اعتماد ملخص الحضور."""
    summary = get_object_or_404(AttendanceSummary, pk=pk)
    try:
        AttendanceSummaryService.approve_summary(summary, request.user)
        messages.success(request, 'تم اعتماد ملخص الحضور بنجاح.')
    except Exception as e:
        messages.error(request, f'حدث خطأ أثناء اعتماد الملخص: {e}')
    return redirect('hr:attendance_summary_detail', pk=pk)


@login_required
@require_POST
def recalculate_attendance_summary(request, pk):
    """إعادة حساب ملخص الحضور."""
    summary = get_object_or_404(AttendanceSummary, pk=pk)
    try:
        AttendanceSummaryService.recalculate_summary(summary)
        messages.success(request, 'تمت إعادة حساب ملخص الحضور بنجاح.')
    except Exception as e:
        messages.error(request, f'حدث خطأ أثناء إعادة الحساب: {e}')
    return redirect('hr:attendance_summary_detail', pk=pk)


@login_required
def attendance_check_out(request):
    """تسجيل الانصراف"""
    if request.method == 'POST':
        employee_id = request.POST.get('employee_id')
        
        if employee_id:
            try:
                employee = Employee.objects.get(pk=employee_id)
                attendance = AttendanceService.check_out(employee)
                messages.success(request, f'تم تسجيل انصراف {employee.get_full_name_ar()} بنجاح')
                return redirect('hr:attendance_list')
            except Exception as e:
                messages.error(request, f'خطأ: {str(e)}')
        else:
            messages.error(request, 'يرجى اختيار الموظف')
    
    context = {
        'employees': Employee.objects.filter(status='active')
    }
    return render(request, 'hr/attendance/check_out.html', context)
