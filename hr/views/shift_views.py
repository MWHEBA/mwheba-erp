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
    all_shifts = Shift.objects.prefetch_related('employees').all().order_by('start_time')
    academic_shifts = all_shifts.filter(shift_type='academic_year')
    summer_shifts = all_shifts.filter(shift_type='summer')

    # إحصائيات
    stats = {
        'total_shifts': all_shifts.count(),
        'active_shifts': all_shifts.filter(is_active=True).count(),
        'academic_year_shifts': academic_shifts.count(),
        'summer_shifts': summer_shifts.count(),
    }

    context = {
        'academic_shifts': academic_shifts,
        'summer_shifts': summer_shifts,
        'stats': stats,
        
        # بيانات الهيدر
        'page_title': 'الورديات',
        'page_subtitle': 'إدارة ورديات العمل ومواعيدها',
        'page_icon': 'fas fa-business-time',
        'header_buttons': [
            {
                'url': reverse('hr:shift_form'),
                'icon': 'fa-plus',
                'text': 'إضافة وردية',
                'class': 'btn-primary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'الورديات', 'active': True},
        ],
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
        
        # إزالة الوردية من جميع الموظفين المعينين سابقاً
        Employee.objects.filter(shift=shift).update(shift=None)
        
        # تعيين الوردية للموظفين المختارين
        if employee_ids:
            Employee.objects.filter(id__in=employee_ids).update(shift=shift)
            messages.success(request, f'تم تعيين {len(employee_ids)} موظف للوردية بنجاح')
        else:
            messages.warning(request, 'لم يتم اختيار أي موظف')
        
        return redirect('hr:shift_list')
    
    # فلترة حسب القسم
    department_id = request.GET.get('department')
    
    # جلب جميع الموظفين النشطين
    employees = Employee.objects.filter(status='active', is_insurance_only=False).select_related('department', 'job_title')
    
    if department_id:
        employees = employees.filter(department_id=department_id)
    
    # جلب جميع الأقسام للفلترة
    from ..models import Department
    departments = Department.objects.filter(is_active=True).order_by('name_ar')
    
    # جلب IDs الموظفين المعينين حالياً لهذه الوردية
    assigned_employee_ids = list(shift.employees.values_list('id', flat=True))
    
    context = {
        'shift': shift,
        'employees': employees,
        'assigned_employee_ids': assigned_employee_ids,
        'departments': departments,
        'selected_department': department_id,

        # بيانات الهيدر الموحد
        'title': f'تعيين موظفين: {shift.name}',
        'subtitle': 'اختيار الموظفين المخصصين لهذه الوردية',
        'icon': 'fas fa-users',
        'header_buttons': [
            {
                'url': reverse('hr:shift_list'),
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'الورديات', 'url': reverse('hr:shift_list'), 'icon': 'fas fa-business-time'},
            {'title': 'تعيين موظفين', 'active': True},
        ],
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
    
    context = {
        'form': form,
        'shift': shift,
        
        # بيانات الهيدر
        'page_title': 'تعديل وردية' if pk else 'إضافة وردية جديدة',
        'page_subtitle': shift.name if pk and shift else 'إدخال بيانات الوردية',
        'page_icon': 'fas fa-business-time',
        'header_buttons': [
            {
                'url': reverse('hr:shift_list'),
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'الورديات', 'url': reverse('hr:shift_list'), 'icon': 'fas fa-business-time'},
            {'title': 'تعديل وردية' if pk else 'إضافة وردية', 'active': True},
        ],
    }
    return render(request, 'hr/shift/form.html', context)
