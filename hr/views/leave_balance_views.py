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
    'leave_balance_rollover',
    'leave_balance_accrual_status',
]


@login_required
def leave_balance_list(request):
    """قائمة أرصدة الإجازات"""
    current_year = date.today().year
    year = request.GET.get('year', current_year)
    
    balances = LeaveBalance.objects.filter(year=year).select_related(
        'employee', 'employee__department', 'employee__job_title', 'leave_type'
    ).order_by('employee__employee_number')
    
    # تجميع الأرصدة حسب الموظف
    employees_balances = defaultdict(list)
    for balance in balances:
        employees_balances[balance.employee].append(balance)
    
    # تحويل إلى قائمة مرتبة
    grouped_balances = [
        {
            'employee': employee,
            'balances': employee_balances,
            'total_remaining': sum(b.remaining_days for b in employee_balances),
            'total_used': sum(b.used_days for b in employee_balances),
        }
        for employee, employee_balances in employees_balances.items()
    ]
    
    # ترتيب حسب رقم الموظف
    grouped_balances.sort(key=lambda x: x['employee'].employee_number)
    
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
    
    context = {
        'balances': balances,
        'grouped_balances': grouped_balances,
        'stats': stats,
        'current_year': current_year,
        'selected_year': int(year),
        'years': range(current_year - 2, current_year + 2),
        'rollover_enabled': rollover_enabled,
    }
    return render(request, 'hr/leave_balance/list.html', context)


@login_required
def leave_balance_employee(request, employee_id):
    """أرصدة إجازات موظف محدد"""
    employee = get_object_or_404(Employee, pk=employee_id)
    current_year = date.today().year
    
    balances = LeaveBalance.objects.filter(
        employee=employee,
        year=current_year
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
    }
    return render(request, 'hr/leave_balance/employee.html', context)


@login_required
def leave_balance_update(request):
    """تحديث أرصدة الإجازات"""
    if request.method == 'POST':
        employee_id = request.POST.get('employee_id')
        leave_type_id = request.POST.get('leave_type_id')
        year = request.POST.get('year', date.today().year)
        total_days = request.POST.get('total_days')
        
        try:
            balance, created = LeaveBalance.objects.get_or_create(
                employee_id=employee_id,
                leave_type_id=leave_type_id,
                year=year,
                defaults={'total_days': total_days, 'remaining_days': total_days}
            )
            
            if not created:
                balance.total_days = int(total_days)
                balance.update_balance()
            
            messages.success(request, 'تم تحديث الرصيد بنجاح')
        except Exception as e:
            messages.error(request, f'خطأ: {str(e)}')
        
        return redirect('hr:leave_balance_list')
    
    employees = Employee.objects.filter(status='active')
    leave_types = LeaveType.objects.filter(is_active=True)
    
    context = {
        'employees': employees,
        'leave_types': leave_types,
        'current_year': date.today().year,
    }
    return render(request, 'hr/leave_balance/update.html', context)


@login_required
def leave_balance_rollover(request):
    """ترحيل أرصدة الإجازات للسنة الجديدة"""
    
    # التحقق من تفعيل الترحيل في الإعدادات
    rollover_enabled = SystemSetting.get_setting('leave_rollover_enabled', False)
    max_rollover_days = SystemSetting.get_setting('leave_rollover_max_days', 7)
    
    # جلب نوع الإجازة السنوية للأمثلة (أو أي نوع نشط)
    annual_leave = LeaveType.objects.filter(code='ANNUAL', is_active=True).first()
    if not annual_leave:
        # إذا لم توجد إجازة سنوية، خذ أول نوع نشط
        annual_leave = LeaveType.objects.filter(is_active=True).first()
    annual_days = annual_leave.max_days_per_year if annual_leave else 0
    
    if request.method == 'POST':
        if not rollover_enabled:
            messages.warning(request, 'ترحيل الإجازات غير مفعل في الإعدادات. يرجى تفعيله من إعدادات الموارد البشرية.')
            return redirect('hr:leave_balance_list')
        
        from_year = int(request.POST.get('from_year'))
        to_year = int(request.POST.get('to_year'))
        rollover_unused = request.POST.get('rollover_unused') == 'on'
        
        try:
            employees = Employee.objects.filter(status='active')
            leave_types = LeaveType.objects.filter(is_active=True)
            created_count = 0
            total_rollover_days = 0
            
            for employee in employees:
                for leave_type in leave_types:
                    # الحصول على الرصيد القديم
                    old_balance = LeaveBalance.objects.filter(
                        employee=employee,
                        leave_type=leave_type,
                        year=from_year
                    ).first()
                    
                    # حساب الرصيد الجديد
                    total_days = leave_type.max_days_per_year
                    if rollover_unused and old_balance and old_balance.remaining_days > 0:
                        # تطبيق الحد الأقصى للأيام المرحلة
                        rollover_days = min(old_balance.remaining_days, max_rollover_days)
                        total_days += rollover_days
                        total_rollover_days += rollover_days
                    
                    # إنشاء الرصيد الجديد
                    LeaveBalance.objects.get_or_create(
                        employee=employee,
                        leave_type=leave_type,
                        year=to_year,
                        defaults={
                            'total_days': total_days,
                            'remaining_days': total_days
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
        'current_year': current_year,
        'years': range(current_year - 2, current_year + 3),
        'rollover_enabled': rollover_enabled,
        'max_rollover_days': max_rollover_days,
        'annual_days': annual_days,
    }
    return render(request, 'hr/leave_balance/rollover.html', context)


@login_required
def leave_balance_accrual_status(request, employee_id):
    """عرض حالة استحقاق إجازات موظف محدد"""
    
    employee = get_object_or_404(Employee, pk=employee_id)
    status = LeaveAccrualService.get_employee_accrual_status(employee)
    
    # جلب الإعدادات للعرض في الـ template
    leave_settings = {
        'probation_months': SystemSetting.get_setting('leave_accrual_probation_months', 3),
        'partial_percentage': SystemSetting.get_setting('leave_accrual_partial_percentage', 25),
        'full_months': SystemSetting.get_setting('leave_accrual_full_months', 6),
    }
    
    context = {
        'employee': employee,
        'status': status,
        'leave_settings': leave_settings,
    }
    return render(request, 'hr/leave_balance/accrual_status.html', context)
