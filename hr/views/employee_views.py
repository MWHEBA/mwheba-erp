"""
Views إدارة الموظفين
"""
from .base_imports import *
from ..models import Employee, Department, JobTitle, Shift, Contract, BiometricLog, BiometricUserMapping
from ..forms.employee_forms import EmployeeForm

__all__ = [
    'employee_list',
    'employee_detail',
    'employee_form',
    'employee_delete',
]


@login_required
def employee_list(request):
    """قائمة الموظفين"""
    # جلب جميع الموظفين مع العلاقات
    employees = Employee.objects.select_related('department', 'job_title').all()
    
    # الفلترة حسب البحث
    search = request.GET.get('search', '')
    if search:
        employees = employees.filter(
            Q(first_name_ar__icontains=search) |
            Q(last_name_ar__icontains=search) |
            Q(employee_number__icontains=search)
        )
    
    # الفلترة حسب القسم
    department = request.GET.get('department', '')
    if department:
        employees = employees.filter(department_id=department)
    
    # الفلترة حسب الحالة
    status = request.GET.get('status', '')
    if status:
        employees = employees.filter(status=status)
    
    # الفلترة حسب المسمى الوظيفي
    job_title = request.GET.get('job_title', '')
    if job_title:
        employees = employees.filter(job_title_id=job_title)
    
    # جلب الأقسام والمسميات الوظيفية للفلترة
    departments = Department.objects.filter(is_active=True)
    job_titles = JobTitle.objects.filter(is_active=True)
    
    # الإحصائيات
    total_employees = Employee.objects.count()
    active_employees = Employee.objects.filter(status='active').count()
    total_departments = Department.objects.filter(is_active=True).count()
    total_job_titles = JobTitle.objects.filter(is_active=True).count()
    
    # تعريف رؤوس الجدول
    table_headers = [
        {'key': 'employee_number', 'label': 'رقم الموظف', 'sortable': True, 'class': 'text-center'},
        {'key': 'photo_display', 'label': 'الصورة', 'format': 'html', 'class': 'text-center'},
        {'key': 'full_name_display', 'label': 'الاسم', 'sortable': True, 'class': 'text-center fw-bold'},
        {'key': 'department_name', 'label': 'القسم', 'sortable': True, 'class': 'text-center'},
        {'key': 'job_title_name', 'label': 'المسمى الوظيفي', 'sortable': True, 'class': 'text-center'},
        {'key': 'hire_date', 'label': 'تاريخ التعيين', 'sortable': True, 'format': 'date', 'class': 'text-center'},
        {'key': 'years_of_service_display', 'label': 'سنوات الخدمة', 'sortable': True, 'class': 'text-center'},
        {'key': 'status_display', 'label': 'الحالة', 'sortable': True, 'format': 'html', 'class': 'text-center'},
    ]
    
    # تعريف أزرار الإجراءات
    table_actions = [
        {'url': 'hr:employee_detail', 'icon': 'fa-eye', 'label': 'عرض', 'class': 'action-view'},
        {'url': 'hr:employee_form_edit', 'icon': 'fa-edit', 'label': 'تعديل', 'class': 'action-edit'},
        {'url': 'hr:employee_delete', 'icon': 'fa-trash', 'label': 'حذف', 'class': 'action-delete'},
    ]
    
    # إضافة بيانات إضافية للعرض في الجدول
    for employee in employees:
        # عرض الصورة في عمود منفصل
        if employee.photo:
            employee.photo_display = f'<img src="{employee.photo.url}" class="rounded-circle" width="40" height="40">'
        else:
            first_letter = employee.first_name_ar[0] if employee.first_name_ar else 'م'
            employee.photo_display = f'<div class="avatar-placeholder rounded-circle bg-primary text-white d-inline-flex align-items-center justify-content-center" style="width: 40px; height: 40px; font-size: 1.1rem; font-weight: 600;">{first_letter}</div>'
        
        # عرض الاسم الكامل
        employee.full_name_display = employee.get_full_name_ar()
        
        # اسم القسم
        employee.department_name = employee.department.name_ar if employee.department else '-'
        
        # اسم المسمى الوظيفي
        employee.job_title_name = employee.job_title.title_ar if employee.job_title else '-'
        
        # سنوات الخدمة
        years = employee.years_of_service
        if years == 0:
            employee.years_of_service_display = 'أقل من سنة'
        elif years == 1:
            employee.years_of_service_display = 'سنة واحدة'
        elif years == 2:
            employee.years_of_service_display = 'سنتان'
        elif years <= 10:
            employee.years_of_service_display = f'{years} سنوات'
        else:
            employee.years_of_service_display = f'{years} سنة'
        
        # عرض الحالة
        status_badges = {
            'active': '<span class="badge bg-success">نشط</span>',
            'on_leave': '<span class="badge bg-warning text-dark">في إجازة</span>',
            'suspended': '<span class="badge bg-secondary">موقوف</span>',
            'terminated': '<span class="badge bg-danger">منتهي الخدمة</span>',
        }
        employee.status_display = status_badges.get(employee.status, '<span class="badge bg-secondary">غير محدد</span>')
    
    # معالجة التصدير
    export_format = request.GET.get('export', '')
    if export_format in ['csv', 'xlsx']:
        from .employee_import import export_employees
        return export_employees(employees, export_format)
    
    context = {
        'employees': employees,
        'departments': departments,
        'job_titles': job_titles,
        'total_employees': total_employees,
        'active_employees': active_employees,
        'total_departments': total_departments,
        'total_job_titles': total_job_titles,
        'show_stats': True,
        'table_headers': table_headers,
        'table_actions': table_actions,
    }
    return render(request, 'hr/employee/list.html', context)


@login_required
def employee_detail(request, pk):
    """تفاصيل الموظف"""
    from ..services.user_employee_service import UserEmployeeService
    
    employee = get_object_or_404(Employee, pk=pk)
    
    # جلب المستخدمين غير المرتبطين للربط
    unlinked_users = UserEmployeeService.get_unlinked_users()
    
    # إحصائيات البصمة
    biometric_logs_count = BiometricLog.objects.filter(employee=employee).count()
    biometric_logs_last_30_days = BiometricLog.objects.filter(
        employee=employee,
        timestamp__gte=timezone.now() - timedelta(days=30)
    ).count()
    
    # آخر 5 سجلات بصمة
    recent_biometric_logs = BiometricLog.objects.filter(
        employee=employee
    ).select_related('device').order_by('-timestamp')[:5]
    
    # الحصول على ربط البصمة
    biometric_mappings = BiometricUserMapping.objects.filter(
        employee=employee,
        is_active=True
    ).select_related('device')
    
    # جلب العقود الخاصة بالموظف
    contracts = Contract.objects.filter(
        employee=employee
    ).order_by('-start_date')
    
    # تحديد العقد النشط
    active_contract = contracts.filter(status='active').first()
    
    context = {
        'employee': employee,
        'unlinked_users': unlinked_users,
        'biometric_logs_count': biometric_logs_count,
        'biometric_logs_last_30_days': biometric_logs_last_30_days,
        'recent_biometric_logs': recent_biometric_logs,
        'biometric_mappings': biometric_mappings,
        'contracts': contracts,
        'active_contract': active_contract,
    }
    return render(request, 'hr/employee/detail.html', context)


@login_required
def employee_delete(request, pk):
    """حذف موظف"""
    employee = get_object_or_404(Employee, pk=pk)
    if request.method == 'POST':
        employee.status = 'terminated'
        employee.save()
        messages.success(request, 'تم إنهاء خدمة الموظف')
        return redirect('hr:employee_list')
    
    # تجهيز البيانات للمودال الموحد
    item_fields = [
        {'label': 'الاسم', 'value': employee.get_full_name_ar()},
        {'label': 'رقم الموظف', 'value': employee.employee_number},
        {'label': 'القسم', 'value': employee.department.name_ar},
        {'label': 'الوظيفة', 'value': employee.job_title.title_ar},
    ]
    
    context = {
        'employee': employee,
        'item_fields': item_fields,
    }
    return render(request, 'hr/employee/delete_modal.html', context)


@login_required
def employee_form(request, pk=None):
    """نموذج موحد لإضافة/تعديل موظف"""
    employee = get_object_or_404(Employee, pk=pk) if pk else None
    
    if request.method == 'POST':
        form = EmployeeForm(request.POST, request.FILES, instance=employee)
        if form.is_valid():
            employee_obj = form.save(commit=False)
            
            # توليد رقم الموظف تلقائياً إذا لم يتم إدخاله (للإضافة فقط)
            if not pk and not employee_obj.employee_number:
                employee_obj.employee_number = EmployeeForm.generate_employee_number()
            
            # تعيين المستخدم الذي أنشأ السجل (للإضافة فقط)
            if not pk:
                employee_obj.created_by = request.user
            
            employee_obj.save()
            
            if pk:
                messages.success(request, 'تم تحديث بيانات الموظف بنجاح')
            else:
                messages.success(request, f'تم إضافة الموظف بنجاح - الرقم: {employee_obj.employee_number}')
            
            return redirect('hr:employee_detail', pk=employee_obj.pk)
        else:
            messages.error(request, 'يرجى تصحيح الأخطاء في النموذج')
    else:
        form = EmployeeForm(instance=employee)
    
    # جلب الأقسام والمسميات الوظيفية والورديات
    departments = Department.objects.filter(is_active=True)
    job_titles = JobTitle.objects.filter(is_active=True)
    shifts = Shift.objects.filter(is_active=True)
    
    # توليد رقم الموظف المقترح (للإضافة فقط)
    next_employee_number = EmployeeForm.generate_employee_number() if not pk else None
    
    context = {
        'form': form,
        'employee': employee,
        'departments': departments,
        'job_titles': job_titles,
        'shifts': shifts,
        'next_employee_number': next_employee_number,
    }
    return render(request, 'hr/employee/form.html', context)
