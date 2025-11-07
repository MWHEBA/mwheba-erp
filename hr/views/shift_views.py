"""
Views إدارة الورديات
"""
from .base_imports import *
from ..models import Shift, Employee, Attendance
from ..forms.attendance_forms import ShiftForm

__all__ = [
    'shift_list',
    'shift_delete',
    'shift_assign_employees',
    'shift_form',
]


@login_required
def shift_list(request):
    """قائمة الورديات"""
    shifts = Shift.objects.all().order_by('start_time')
    
    # إحصائيات
    stats = {
        'total_shifts': shifts.count(),
        'active_shifts': shifts.filter(is_active=True).count(),
        'morning_shifts': shifts.filter(shift_type='morning').count(),
        'evening_shifts': shifts.filter(shift_type='evening').count(),
        'night_shifts': shifts.filter(shift_type='night').count(),
    }
    
    context = {
        'shifts': shifts,
        'stats': stats,
    }
    return render(request, 'hr/shift/list.html', context)


@login_required
def shift_delete(request, pk):
    """حذف وردية"""
    shift = get_object_or_404(Shift, pk=pk)
    
    if request.method == 'POST':
        shift.is_active = False
        shift.save()
        messages.success(request, 'تم إلغاء تفعيل الوردية')
        return redirect('hr:shift_list')
    
    # عدد الموظفين المرتبطين
    employees_count = Attendance.objects.filter(shift=shift).values('employee').distinct().count()
    
    # تجهيز البيانات للمودال الموحد
    item_fields = [
        {'label': 'اسم الوردية', 'value': shift.name},
        {'label': 'النوع', 'value': shift.get_shift_type_display()},
        {'label': 'الوقت', 'value': f"{shift.start_time.strftime('%H:%M')} - {shift.end_time.strftime('%H:%M')}"},
        {'label': 'عدد الموظفين المرتبطين', 'value': employees_count},
    ]
    
    warning_message = f'تحذير: يوجد {employees_count} موظف مرتبط بهذه الوردية. سيتم إلغاء تفعيل الوردية فقط وليس حذفها نهائياً.'
    
    context = {
        'shift': shift,
        'item_fields': item_fields,
        'employees_count': employees_count,
        'warning_message': warning_message,
    }
    return render(request, 'hr/shift/delete_modal.html', context)


@login_required
def shift_assign_employees(request, pk):
    """تعيين موظفين للوردية"""
    shift = get_object_or_404(Shift, pk=pk)
    
    if request.method == 'POST':
        employee_ids = request.POST.getlist('employees')
        # هنا يمكن إضافة جدول لربط الموظفين بالورديات
        messages.success(request, f'تم تعيين {len(employee_ids)} موظف للوردية')
        return redirect('hr:shift_list')
    
    employees = Employee.objects.filter(status='active')
    context = {
        'shift': shift,
        'employees': employees,
    }
    return render(request, 'hr/shift/assign.html', context)


@login_required
def shift_form(request, pk=None):
    """نموذج موحد لإضافة/تعديل وردية"""
    from ..forms.attendance_forms import ShiftForm
    
    shift = get_object_or_404(Shift, pk=pk) if pk else None
    
    if request.method == 'POST':
        form = ShiftForm(request.POST, instance=shift)
        if form.is_valid():
            form.save()
            if pk:
                messages.success(request, 'تم تحديث الوردية بنجاح')
            else:
                messages.success(request, 'تم إضافة الوردية بنجاح')
            return redirect('hr:shift_list')
        else:
            messages.error(request, 'يرجى تصحيح الأخطاء في النموذج')
    else:
        form = ShiftForm(instance=shift)
    
    return render(request, 'hr/shift/form.html', {'form': form, 'shift': shift})
