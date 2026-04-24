"""
Views إدارة أرصدة الإجازات
"""
from .base_imports import *
from ..models import LeaveBalance, Employee, LeaveType, Leave
from ..services.leave_accrual_service import LeaveAccrualService
from core.models import SystemSetting
from datetime import date
from collections import defaultdict
from django.db.models import Sum, Avg, Count

__all__ = [
    'leave_balance_list',
    'leave_balance_employee',
    'leave_balance_update',
    'leave_balance_update_all',
    'leave_balance_rollover',
    'leave_balance_accrual_status',
    'leave_encashment_process',
    'leave_balance_get_api',
]


@login_required
def leave_balance_list(request):
    """قائمة أرصدة الإجازات"""
    current_year = date.today().year
    year = request.GET.get('year', current_year)
    year = int(year)

    # الإجازات اللي ليها رصيد (annual, emergency)
    balances_with_quota = LeaveBalance.objects.filter(
        year=year,
        leave_type__category__in=['annual', 'emergency']
    ).exclude(
        employee__status='terminated'
    ).exclude(
        employee__is_insurance_only=True
    ).select_related(
        'employee', 'employee__department', 'employee__job_title', 'leave_type'
    ).order_by('employee__employee_number')

    # الإجازات اللي مالهاش رصيد (sick, exceptional, unpaid) — نجيب الاستهلاك من جدول الطلبات
    no_quota_types = LeaveType.objects.filter(
        category__in=['sick', 'exceptional', 'unpaid'],
        is_active=True
    )

    # جمع الأيام المستخدمة من طلبات الإجازة المعتمدة لكل موظف ونوع
    no_quota_usage = (
        Leave.objects.filter(
            status='approved',
            leave_type__category__in=['sick', 'exceptional', 'unpaid'],
            start_date__year=year,
        )
        .exclude(employee__status='terminated')
        .exclude(employee__is_insurance_only=True)
        .values('employee_id', 'leave_type_id')
        .annotate(total_used=Sum('days_count'))
    )

    # بناء dict سريع: {(employee_id, leave_type_id): total_used}
    no_quota_map = {
        (r['employee_id'], r['leave_type_id']): r['total_used']
        for r in no_quota_usage
    }

    # تجميع الأرصدة حسب الموظف
    employees_balances = defaultdict(list)
    for balance in balances_with_quota:
        employees_balances[balance.employee].append({
            'leave_type': balance.leave_type,
            'has_quota': True,
            'total_days': balance.total_days,
            'accrued_days': balance.accrued_days,
            'used_days': balance.used_days,
            'remaining_days': balance.remaining_days,
        })

    # إضافة الإجازات بدون رصيد لكل موظف ظهر في الأرصدة
    employees_in_balances = {emp for emp in employees_balances.keys()}

    # نجيب كمان الموظفين اللي عندهم استهلاك في الإجازات بدون رصيد حتى لو مش في الأرصدة
    employees_with_no_quota_usage = Employee.objects.filter(
        id__in={r['employee_id'] for r in no_quota_usage}
    ).exclude(status='terminated').exclude(is_insurance_only=True).select_related('department', 'job_title')

    all_employees = employees_in_balances | set(employees_with_no_quota_usage)

    for emp in all_employees:
        for lt in no_quota_types:
            used = no_quota_map.get((emp.id, lt.id), 0)
            if used and used > 0:
                employees_balances[emp].append({
                    'leave_type': lt,
                    'has_quota': False,
                    'total_days': None,
                    'accrued_days': None,
                    'used_days': used,
                    'remaining_days': None,
                })

    # تحويل إلى قائمة مرتبة
    grouped_balances = []
    for employee, emp_balances in employees_balances.items():
        quota_balances = [b for b in emp_balances if b['has_quota']]
        no_quota_balances = [b for b in emp_balances if not b['has_quota']]
        grouped_balances.append({
            'employee': employee,
            'quota_balances': quota_balances,
            'no_quota_balances': no_quota_balances,
            'total_remaining': sum(b['remaining_days'] for b in quota_balances),
            'total_used': sum(b['used_days'] for b in emp_balances),
        })

    # ترتيب حسب رقم الموظف
    grouped_balances.sort(key=lambda x: x['employee'].employee_number)

    # للإحصائيات نستخدم الأرصدة الأصلية
    balances = balances_with_quota
    
    # إحصائيات
    stats = balances.aggregate(
        total_employees=Count('employee', distinct=True),
        total_days=Sum('total_days'),
        total_used=Sum('used_days'),
        total_remaining=Sum('remaining_days'),
        avg_remaining=Avg('remaining_days')
    )
    
    # جلب إعدادات الترحيل
    rollover_enabled = SystemSetting.get_setting('leave_rollover_enabled', False)
    encashment_enabled = SystemSetting.get_setting('leave_encashment_enabled', False)

    # إعداد الأزرار
    header_buttons = [
        {
            'onclick': 'updateAllBalances()',
            'icon': 'fa-sync',
            'text': 'تحديث الأرصدة',
            'class': 'btn-success',
            'title': 'تحديث أرصدة جميع الموظفين تلقائياً',
        },
        {
            'url': reverse('hr:leave_balance_update'),
            'icon': 'fa-edit',
            'text': 'تعديل',
            'class': 'btn-primary',
        },
    ]
    
    if rollover_enabled:
        header_buttons.append({
            'url': reverse('hr:leave_balance_rollover'),
            'icon': 'fa-sync',
            'text': 'ترحيل',
            'class': 'btn-success',
            'title': 'ترحيل الأرصدة للسنة الجديدة',
        })

    if encashment_enabled:
        header_buttons.append({
            'url': reverse('hr:leave_encashment_process'),
            'icon': 'fa-coins',
            'text': 'تحويل الإجازات لمقابل مالي',
            'class': 'btn-warning',
            'title': 'تحويل الأيام المتبقية لمقابل مالي على الراتب',
        })
    
    context = {
        'balances': balances,
        'grouped_balances': grouped_balances,
        'stats': stats,
        'current_year': current_year,
        'selected_year': int(year),
        'years': range(current_year, current_year + 2),
        'rollover_enabled': rollover_enabled,
        'encashment_enabled': encashment_enabled,
        
        # بيانات الهيدر الموحد
        'page_title': f'أرصدة الإجازات - {year}',
        'page_subtitle': 'متابعة أرصدة إجازات الموظفين',
        'page_icon': 'fas fa-chart-pie',
        'header_buttons': header_buttons,
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'الإعدادات', 'url': reverse('hr:hr_settings'), 'icon': 'fas fa-cog'},
            {'title': 'أرصدة الإجازات', 'active': True},
        ],
    }
    return render(request, 'hr/leave_balance/list.html', context)


@login_required
def leave_balance_employee(request, employee_id):
    """أرصدة إجازات موظف محدد"""
    employee = get_object_or_404(Employee, pk=employee_id)

    # منع عرض بيانات الموظفين المنهي خدمتهم
    if employee.status == 'terminated':
        messages.error(request, 'لا يمكن عرض بيانات موظف منتهي الخدمة')
        return redirect('hr:leave_balance_list')
    current_year = date.today().year
    
    balances = LeaveBalance.objects.filter(
        employee=employee,
        year=current_year,
        leave_type__category__in=['annual', 'emergency']
    ).select_related('leave_type')
    
    # سجل الإجازات
    leaves = Leave.objects.filter(
        employee=employee,
        start_date__year=current_year
    ).select_related('leave_type').order_by('-start_date')
    
    context = {
        'employee': employee,
        'balances': balances,
        'leaves': leaves,
        'current_year': current_year,
        
        # بيانات الهيدر الموحد
        'page_title': f'أرصدة إجازات: {employee.get_full_name_ar()}',
        'page_subtitle': f'{employee.employee_number} - {employee.department.name_ar if employee.department else ""}',
        'page_icon': 'fas fa-user-clock',
        'header_buttons': [
            {
                'url': reverse('hr:leave_balance_list'),
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'أرصدة الإجازات', 'url': reverse('hr:leave_balance_list'), 'icon': 'fas fa-chart-pie'},
            {'title': employee.get_full_name_ar(), 'active': True},
        ],
    }
    return render(request, 'hr/leave_balance/employee.html', context)


@login_required
def leave_balance_update_all(request):
    """تحديث أرصدة الإجازات لجميع الموظفين تلقائياً"""
    if request.method == 'POST':
        try:
            current_year = date.today().year
            employees    = Employee.objects.filter(status='active', is_insurance_only=False)
            leave_types  = LeaveType.objects.filter(is_active=True, category__in=['annual', 'emergency'])

            created_count = 0
            updated_count = 0

            for employee in employees:
                for leave_type in leave_types:
                    # single source of truth
                    total_days = LeaveAccrualService.get_entitlement_for_employee(employee, leave_type)

                    balance, created = LeaveBalance.objects.get_or_create(
                        employee=employee,
                        leave_type=leave_type,
                        year=current_year,
                        defaults={
                            'total_days':    total_days,
                            'accrued_days':  total_days,
                            'used_days':     0,
                            'remaining_days': total_days,
                            'accrual_phase': LeaveAccrualService.get_accrual_phase(employee, leave_type),
                        }
                    )

                    if created:
                        created_count += 1
                    elif not balance.is_manually_adjusted:
                        new_phase = LeaveAccrualService.get_accrual_phase(employee, leave_type)
                        if balance.total_days != total_days or balance.accrual_phase != new_phase:
                            balance.total_days     = total_days
                            balance.accrued_days   = total_days
                            balance.remaining_days = max(0, total_days - balance.used_days)
                            balance.accrual_phase  = new_phase
                            balance.save()
                            updated_count += 1

            if created_count > 0 or updated_count > 0:
                messages.success(request, f'تم تحديث الأرصدة: {created_count} جديد، {updated_count} محدث — الأرصدة المعدلة يدوياً لم تتأثر')
            else:
                messages.info(request, 'جميع الأرصدة محدثة بالفعل')

        except Exception as e:
            messages.error(request, f'خطأ في تحديث الأرصدة: {str(e)}')

        return redirect('hr:leave_balance_list')

    return redirect('hr:leave_balance_list')


@login_required
def leave_balance_get_api(request):
    """API: جلب رصيد موظف في نوع إجازة معين (بدون تقييد بالسنة)"""
    from django.http import JsonResponse
    employee_id = request.GET.get('employee_id')
    leave_type_id = request.GET.get('leave_type_id')

    if not employee_id or not leave_type_id:
        return JsonResponse({'found': False})

    # جلب آخر رصيد موجود للموظف في هذا النوع (بغض النظر عن السنة)
    balance = LeaveBalance.objects.filter(
        employee_id=employee_id,
        leave_type_id=leave_type_id,
    ).order_by('-year').first()

    if balance:
        return JsonResponse({
            'found': True,
            'year': balance.year,
            'total_days': balance.total_days,
            'accrued_days': balance.accrued_days,
            'used_days': balance.used_days,
            'remaining_days': balance.remaining_days,
        })
    return JsonResponse({'found': False})


def leave_balance_update(request):
    """تحديث أرصدة الإجازات"""
    from django.urls import reverse

    if request.method == 'POST':
        employee_id       = request.POST.get('employee_id')
        leave_type_id     = request.POST.get('leave_type_id')
        total_days        = request.POST.get('total_days')
        adjustment_reason = request.POST.get('adjustment_reason', '').strip()

        try:
            days = int(total_days)
            # جيب الرصيد الموجود أو أنشئه بالسنة الحالية
            existing = LeaveBalance.objects.filter(
                employee_id=employee_id,
                leave_type_id=leave_type_id,
            ).order_by('-year').first()

            if existing:
                existing.total_days        = days
                existing.accrued_days      = days
                existing.remaining_days    = max(0, days - (existing.used_days or 0))
                existing.is_manually_adjusted = True
                existing.adjustment_reason = adjustment_reason
                existing.save()
            else:
                LeaveBalance.objects.create(
                    employee_id=employee_id,
                    leave_type_id=leave_type_id,
                    year=date.today().year,
                    total_days=days,
                    accrued_days=days,
                    used_days=0,
                    remaining_days=days,
                    is_manually_adjusted=True,
                    adjustment_reason=adjustment_reason,
                )

            messages.success(request, 'تم تحديث الرصيد بنجاح')
        except Exception as e:
            messages.error(request, f'خطأ: {str(e)}')

        return redirect('hr:leave_balance_update')
    
    employees = Employee.objects.filter(status='active', is_insurance_only=False)
    leave_types = LeaveType.objects.filter(is_active=True, category__in=['annual', 'emergency'])

    context = {
        'employees': employees,
        'leave_types': leave_types,
        'page_title': 'تحديث أرصدة الإجازات',
        'page_subtitle': 'تحديث رصيد إجازة موظف',
        'page_icon': 'fas fa-edit',
        'header_buttons': [
            {
                'url': reverse('hr:leave_balance_list'),
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users'},
            {'title': 'أرصدة الإجازات', 'url': reverse('hr:leave_balance_list'), 'icon': 'fas fa-chart-pie'},
            {'title': 'تحديث', 'active': True},
        ],
    }
    return render(request, 'hr/leave_balance/update.html', context)


@login_required
def leave_balance_rollover(request):
    """ترحيل أرصدة الإجازات للسنة الجديدة"""

    rollover_enabled  = SystemSetting.get_setting('leave_rollover_enabled', False)
    max_rollover_days = SystemSetting.get_setting('leave_rollover_max_days', 7)

    # تحديد السنوات الافتراضية من دورة الإجازات
    cycle_start, cycle_end = LeaveAccrualService.get_leave_cycle_dates()
    default_from_year = cycle_start.year
    default_to_year   = cycle_end.year + 1 if cycle_end.month >= 9 else cycle_end.year

    annual_leave = LeaveType.objects.filter(code='ANNUAL', is_active=True).first()
    if not annual_leave:
        annual_leave = LeaveType.objects.filter(is_active=True).first()
    annual_days = annual_leave.max_days_per_year if annual_leave else 0

    if request.method == 'POST':
        if not rollover_enabled:
            messages.warning(request, 'ترحيل الإجازات غير مفعل في الإعدادات. يرجى تفعيله من إعدادات الموارد البشرية.')
            return redirect('hr:leave_balance_list')

        from_year      = int(request.POST.get('from_year', default_from_year))
        to_year        = int(request.POST.get('to_year', default_to_year))
        rollover_unused = request.POST.get('rollover_unused') == 'on'

        try:
            employees     = Employee.objects.filter(status='active', is_insurance_only=False)
            leave_types   = LeaveType.objects.filter(is_active=True, category__in=['annual', 'emergency'])
            created_count = 0
            total_rollover_days = 0

            for employee in employees:
                for leave_type in leave_types:
                    old_balance = LeaveBalance.objects.filter(
                        employee=employee,
                        leave_type=leave_type,
                        year=from_year
                    ).first()

                    # single source of truth للرصيد الأساسي في السنة الجديدة
                    base_days = LeaveAccrualService.get_entitlement_for_employee(employee, leave_type)

                    rollover_days = 0
                    if rollover_unused and old_balance and old_balance.remaining_days > 0:
                        rollover_days = min(old_balance.remaining_days, max_rollover_days)
                        total_rollover_days += rollover_days

                    total_days = base_days + rollover_days

                    LeaveBalance.objects.get_or_create(
                        employee=employee,
                        leave_type=leave_type,
                        year=to_year,
                        defaults={
                            'total_days':    total_days,
                            'accrued_days':  total_days,
                            'used_days':     0,
                            'remaining_days': total_days,
                        }
                    )
                    created_count += 1

            if total_rollover_days > 0:
                messages.success(request, f'تم ترحيل {created_count} رصيد بنجاح (تم ترحيل {total_rollover_days} يوم بحد أقصى {max_rollover_days} يوم لكل رصيد)')
            else:
                messages.success(request, f'تم إنشاء {created_count} رصيد جديد بنجاح')
            return redirect('hr:leave_balance_list')
        except Exception as e:
            messages.error(request, f'خطأ: {str(e)}')

    current_year = date.today().year
    context = {
        'current_year':     current_year,
        'default_from_year': default_from_year,
        'default_to_year':  default_to_year,
        'years':            range(current_year - 2, current_year + 3),
        'rollover_enabled': rollover_enabled,
        'max_rollover_days': max_rollover_days,
        'annual_days':      annual_days,

        'page_title':    'ترحيل أرصدة الإجازات',
        'page_subtitle': 'ترحيل الأرصدة للسنة الجديدة',
        'page_icon':     'fas fa-sync',
        'header_buttons': [
            {
                'url':   reverse('hr:leave_balance_list'),
                'icon':  'fa-arrow-right',
                'text':  'رجوع',
                'class': 'btn-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية',       'url': reverse('core:dashboard'),       'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'),     'icon': 'fas fa-users-cog'},
            {'title': 'أرصدة الإجازات', 'url': reverse('hr:leave_balance_list'), 'icon': 'fas fa-chart-pie'},
            {'title': 'ترحيل', 'active': True},
        ],
    }
    return render(request, 'hr/leave_balance/rollover.html', context)


@login_required
def leave_balance_accrual_status(request, employee_id):
    """عرض حالة استحقاق إجازات موظف محدد"""

    employee = get_object_or_404(Employee, pk=employee_id)

    # منع عرض بيانات الموظفين المنهي خدمتهم
    if employee.status == 'terminated':
        messages.error(request, 'لا يمكن عرض بيانات موظف منتهي الخدمة')
        return redirect('hr:leave_balance_list')
    status   = LeaveAccrualService.get_employee_accrual_status(employee)

    s = SystemSetting.get_setting
    leave_settings = {
        'partial_after_months':   s('leave_partial_after_months', 6),
        'annual_partial_days':    s('leave_annual_partial_days', 7),
        'emergency_partial_days': s('leave_emergency_partial_days', 3),
        'annual_full_days':       s('leave_annual_full_days', 21),
        'emergency_full_days':    s('leave_emergency_full_days', 7),
        'senior_age_threshold':   s('leave_senior_age_threshold', 50),
        'senior_service_years':   s('leave_senior_service_years', 10),
        'senior_annual_days':     s('leave_senior_annual_days', 30),
        'senior_emergency_days':  s('leave_senior_emergency_days', 10),
    }

    context = {
        'employee':      employee,
        'status':        status,
        'leave_settings': leave_settings,
        'page_title':    f'حالة استحقاق: {employee.get_full_name_ar()}',
        'page_subtitle': f'{employee.employee_number} — {employee.department.name_ar if employee.department else ""}',
        'page_icon':     'fas fa-hourglass-half',
        'header_buttons': [
            {
                'url':   reverse('hr:leave_balance_list'),
                'icon':  'fa-arrow-right',
                'text':  'رجوع',
                'class': 'btn-outline-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية',       'url': reverse('core:dashboard'),        'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'),      'icon': 'fas fa-users-cog'},
            {'title': 'أرصدة الإجازات', 'url': reverse('hr:leave_balance_list'),  'icon': 'fas fa-chart-pie'},
            {'title': 'حالة الاستحقاق', 'active': True},
        ],
    }
    return render(request, 'hr/leave_balance/accrual_status.html', context)


@login_required
def leave_encashment_process(request):
    """
    صفحة تحويل الإجازات المتبقية لمقابل مالي.

    GET:  عرض معاينة — كل موظف + أيامه المتبقية + المبلغ + حالة الراتب المستهدف
    POST: تنفيذ inject_into_payroll() للموظفين المحددين
    """
    from ..services.leave_encashment_service import LeaveEncashmentService
    from ..services.leave_accrual_service import LeaveAccrualService

    encashment_enabled = SystemSetting.get_setting('leave_encashment_enabled', False)
    if not encashment_enabled:
        messages.warning(request, 'تحويل الإجازات لمقابل مالي غير مفعل. فعّله من إعدادات سياسة الإجازات.')
        return redirect('hr:leave_balance_list')

    # تحديد شهر الـ encashment والسنة ديناميكياً
    encashment_month = LeaveAccrualService.get_encashment_month()
    cycle_start, _   = LeaveAccrualService.get_leave_cycle_dates()
    year             = cycle_start.year

    employees = Employee.objects.filter(
        status='active', is_insurance_only=False
    ).select_related('department', 'job_title')

    previews = []
    for employee in employees:
        preview = LeaveEncashmentService.calculate_encashment_preview(employee, year)
        if not preview['can_encash'] and preview['total_amount'] == 0 and not preview['details']:
            # موظف بدون أيام متبقية — لا نعرضه
            if preview['reason'] == '':
                continue

        payroll = Payroll.objects.filter(
            employee=employee, month=encashment_month
        ).first()

        can_inject = (
            preview['can_encash']
            and preview['total_amount'] > 0
            and payroll is not None
            and payroll.status in ('draft', 'calculated')
        )

        payroll_warning = None
        if preview['can_encash'] and preview['total_amount'] > 0:
            if not payroll:
                payroll_warning = f'لا يوجد راتب لشهر {encashment_month.strftime("%Y-%m")} — يجب حسابه أولاً'
            elif payroll.status in ('approved', 'paid'):
                payroll_warning = f'الراتب في حالة "{payroll.get_status_display()}" — يجب إعادته لحالة محسوب'

        previews.append({
            'employee':       employee,
            'can_encash':     preview['can_encash'],
            'reason':         preview['reason'],
            'total_amount':   preview['total_amount'],
            'daily_rate':     preview['daily_rate'],
            'details':        preview['details'],
            'payroll':        payroll,
            'payroll_status': payroll.get_status_display() if payroll else None,
            'can_inject':     can_inject,
            'payroll_warning': payroll_warning,
        })

    if request.method == 'POST':
        selected_ids = request.POST.getlist('employee_ids')
        if not selected_ids:
            messages.warning(request, 'لم يتم اختيار أي موظف.')
            return redirect('hr:leave_encashment_process')

        success_count = 0
        failed_msgs   = []

        for emp_id in selected_ids:
            try:
                employee = Employee.objects.get(pk=emp_id)
                LeaveEncashmentService.inject_into_payroll(
                    employee, year, encashment_month, request.user
                )
                success_count += 1
            except Employee.DoesNotExist:
                failed_msgs.append(f'موظف #{emp_id}: غير موجود')
            except ValueError as e:
                failed_msgs.append(str(e))
            except Exception as e:
                failed_msgs.append(f'خطأ غير متوقع: {str(e)}')

        if success_count:
            messages.success(
                request,
                f'تم تحويل إجازات {success_count} موظف بنجاح على راتب '
                f'{encashment_month.strftime("%B %Y")}'
            )
        for msg in failed_msgs:
            messages.warning(request, msg)

        return redirect('hr:leave_balance_list')

    # إحصائيات سريعة
    total_employees  = len(previews)
    ready_count      = sum(1 for p in previews if p['can_inject'])
    blocked_count    = sum(1 for p in previews if p['can_encash'] and not p['can_inject'])
    total_amount_all = sum(p['total_amount'] for p in previews if p['can_inject'])

    context = {
        'previews':         previews,
        'year':             year,
        'encashment_month': encashment_month,
        'total_employees':  total_employees,
        'ready_count':      ready_count,
        'blocked_count':    blocked_count,
        'total_amount_all': total_amount_all,

        'page_title':    f'تحويل الإجازات لمقابل مالي — {encashment_month.strftime("%B %Y")}',
        'page_subtitle': f'سنة الإجازات: {year} | شهر الإضافة: {encashment_month.strftime("%B %Y")}',
        'page_icon':     'fas fa-coins',
        'header_buttons': [
            {
                'url':   reverse('hr:leave_balance_list'),
                'icon':  'fa-arrow-right',
                'text':  'رجوع',
                'class': 'btn-outline-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية',       'url': reverse('core:dashboard'),        'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'),      'icon': 'fas fa-users-cog'},
            {'title': 'أرصدة الإجازات', 'url': reverse('hr:leave_balance_list'),  'icon': 'fas fa-chart-pie'},
            {'title': 'تحويل لمقابل مالي', 'active': True},
        ],
    }
    return render(request, 'hr/leave_balance/encashment.html', context)
