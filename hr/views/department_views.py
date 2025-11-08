"""
Views إدارة الأقسام
"""
from .base_imports import *
from ..models import Employee, Department
from ..forms.employee_forms import DepartmentForm

__all__ = [
    'department_list',
    'department_delete',
    'department_form',
]


@login_required
def department_list(request):
    """قائمة الأقسام"""
    from django.urls import reverse
    
    departments = Department.objects.all().select_related('manager', 'parent')
    total_departments = departments.count()
    active_departments = departments.filter(is_active=True).count()
    total_employees = Employee.objects.filter(status='active').count()
    
    context = {
        'departments': departments,
        'total_departments': total_departments,
        'active_departments': active_departments,
        'total_employees': total_employees,
        
        # بيانات الهيدر
        'page_title': 'الأقسام',
        'page_subtitle': 'إدارة الأقسام والهيكل التنظيمي',
        'page_icon': 'fas fa-building',
        
        # أزرار الهيدر
        'header_buttons': [
            {
                'url': reverse('hr:department_form'),
                'icon': 'fa-plus',
                'text': 'إضافة قسم',
                'class': 'btn-primary',
            },
        ],
        
        # البريدكرمب
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users-cog'},
            {'title': 'الإعدادات', 'url': reverse('hr:hr_settings'), 'icon': 'fas fa-cog'},
            {'title': 'الأقسام', 'active': True},
        ],
    }
    return render(request, 'hr/department/list.html', context)


@login_required
def department_delete(request, pk):
    """حذف قسم"""
    department = get_object_or_404(Department, pk=pk)
    
    if request.method == 'POST':
        dept_name = department.name_ar
        department.delete()
        messages.success(request, f'تم حذف القسم "{dept_name}" بنجاح')
        return redirect('hr:department_list')
    
    # تجهيز البيانات للمودال الموحد
    employees_count = department.employees.count()
    sub_departments_count = department.sub_departments.count()
    total_related = employees_count + sub_departments_count
    
    item_fields = [
        {'label': 'الاسم (عربي)', 'value': department.name_ar},
        {'label': 'الاسم (إنجليزي)', 'value': department.name_en or '-'},
        {'label': 'الكود', 'value': department.code},
        {'label': 'القسم الرئيسي', 'value': department.parent or '-'},
        {'label': 'المدير', 'value': department.manager.get_full_name_ar() if department.manager else '-'},
        {'label': 'الحالة', 'value': 'نشط' if department.is_active else 'غير نشط'},
    ]
    
    # بناء رسالة التحذير
    warning_parts = []
    if employees_count > 0:
        warning_parts.append(f'يوجد {employees_count} موظف مرتبط بهذا القسم')
    if sub_departments_count > 0:
        warning_parts.append(f'يوجد {sub_departments_count} قسم فرعي تابع لهذا القسم')
    
    warning_message = '<ul class="mb-0">' + ''.join([f'<li>{part}</li>' for part in warning_parts]) + '</ul>'
    
    context = {
        'department': department,
        'item_fields': item_fields,
        'total_related': total_related,
        'warning_message': warning_message,
        'show_final_warning': total_related > 0,
    }
    return render(request, 'hr/department/delete_modal.html', context)


@login_required
def department_form(request, pk=None):
    """نموذج موحد لإضافة/تعديل قسم"""
    department = get_object_or_404(Department, pk=pk) if pk else None
    
    # توليد الكود التلقائي (للإضافة فقط)
    next_code = None
    if not pk:
        last_dept = Department.objects.order_by('-id').first()
        if last_dept and last_dept.code.startswith('DEPT'):
            try:
                last_num = int(last_dept.code.replace('DEPT', ''))
                next_code = f'DEPT{str(last_num + 1).zfill(3)}'
            except:
                next_code = 'DEPT001'
        else:
            next_code = 'DEPT001'
    
    if request.method == 'POST':
        if not pk:
            # للإضافة: التأكد من عدم تكرار الكود
            code = request.POST.get('code', next_code)
            if Department.objects.filter(code=code).exists():
                last_dept = Department.objects.order_by('-id').first()
                if last_dept and last_dept.code.startswith('DEPT'):
                    try:
                        last_num = int(last_dept.code.replace('DEPT', ''))
                        code = f'DEPT{str(last_num + 1).zfill(3)}'
                    except:
                        code = f'DEPT{str(Department.objects.count() + 1).zfill(3)}'
                else:
                    code = f'DEPT{str(Department.objects.count() + 1).zfill(3)}'
            
            post_data = request.POST.copy()
            post_data['code'] = code
            form = DepartmentForm(post_data)
        else:
            # للتعديل
            form = DepartmentForm(request.POST, instance=department)
        
        if form.is_valid():
            dept = form.save()
            if pk:
                messages.success(request, 'تم تحديث القسم بنجاح')
            else:
                messages.success(request, f'تم إضافة القسم بنجاح - الكود: {dept.code}')
            return redirect('hr:department_list')
        else:
            messages.error(request, 'يرجى تصحيح الأخطاء في النموذج')
    else:
        form = DepartmentForm(instance=department)
    
    # استبعاد القسم الحالي من قائمة الأقسام الرئيسية (للتعديل)
    if pk:
        departments = Department.objects.filter(is_active=True).exclude(pk=pk)
    else:
        departments = Department.objects.filter(is_active=True)
    
    context = {
        'form': form,
        'department': department,
        'next_code': next_code,
        'departments': departments,
        'employees': Employee.objects.filter(status='active'),
        
        # بيانات الهيدر
        'page_title': 'تعديل قسم' if pk else 'إضافة قسم جديد',
        'page_subtitle': department.name_ar if pk else 'إدخال بيانات القسم',
        'page_icon': 'fas fa-building',
        'header_buttons': [
            {
                'url': reverse('hr:department_list'),
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users-cog'},
            {'title': 'الأقسام', 'url': reverse('hr:department_list'), 'icon': 'fas fa-building'},
            {'title': 'تعديل قسم' if pk else 'إضافة قسم', 'active': True},
        ],
    }
    return render(request, 'hr/department/form.html', context)
