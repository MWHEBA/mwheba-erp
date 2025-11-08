"""
Views إدارة المسميات الوظيفية
"""
from .base_imports import *
from ..models import JobTitle, Department
from ..forms.employee_forms import JobTitleForm

__all__ = [
    'job_title_list',
    'job_title_delete',
    'job_title_form',
]


@login_required
def job_title_list(request):
    """قائمة المسميات الوظيفية"""
    from django.urls import reverse
    
    job_titles = JobTitle.objects.select_related('department').filter(is_active=True)
    
    context = {
        'job_titles': job_titles,
        
        # بيانات الهيدر
        'page_title': 'المسميات الوظيفية',
        'page_subtitle': 'إدارة المسميات والمناصب الوظيفية',
        'page_icon': 'fas fa-briefcase',
        
        # أزرار الهيدر
        'header_buttons': [
            {
                'url': reverse('hr:job_title_form'),
                'icon': 'fa-plus',
                'text': 'إضافة مسمى وظيفي',
                'class': 'btn-primary',
            },
        ],
        
        # البريدكرمب
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users-cog'},
            {'title': 'الإعدادات', 'url': reverse('hr:hr_settings'), 'icon': 'fas fa-cog'},
            {'title': 'المسميات الوظيفية', 'active': True},
        ],
    }
    return render(request, 'hr/job_title/list.html', context)


@login_required
def job_title_delete(request, pk):
    """حذف مسمى وظيفي"""
    job_title = get_object_or_404(JobTitle, pk=pk)
    if request.method == 'POST':
        # التحقق من عدم وجود موظفين مرتبطين بهذه الوظيفة
        if job_title.employees.exists():
            messages.error(request, 'لا يمكن حذف هذه الوظيفة لأن هناك موظفين مرتبطين بها')
            return redirect('hr:job_title_list')
        
        # حذف نهائي (Hard Delete)
        job_title.delete()
        messages.success(request, 'تم حذف المسمى الوظيفي نهائياً')
        return redirect('hr:job_title_list')
    
    # تجهيز البيانات للمودال الموحد
    employees_count = job_title.employees.count()
    
    item_fields = [
        {'label': 'الكود', 'value': job_title.code},
        {'label': 'المسمى (عربي)', 'value': job_title.title_ar},
        {'label': 'المسمى (إنجليزي)', 'value': job_title.title_en or '-'},
        {'label': 'القسم', 'value': job_title.department.name_ar},
        {'label': 'عدد الموظفين', 'value': employees_count},
    ]
    
    warning_message = f'تحذير: يوجد {employees_count} موظف مرتبط بهذا المسمى الوظيفي. سيتم إلغاء تفعيل المسمى فقط وليس حذفه نهائياً.'
    
    context = {
        'job_title': job_title,
        'item_fields': item_fields,
        'employees_count': employees_count,
        'warning_message': warning_message,
    }
    return render(request, 'hr/job_title/delete_modal.html', context)


@login_required
def job_title_form(request, pk=None):
    """نموذج موحد لإضافة/تعديل مسمى وظيفي"""
    job_title = get_object_or_404(JobTitle, pk=pk) if pk else None
    
    if request.method == 'POST':
        form = JobTitleForm(request.POST, instance=job_title)
        if form.is_valid():
            form.save()
            if pk:
                messages.success(request, 'تم تحديث المسمى الوظيفي بنجاح')
            else:
                messages.success(request, 'تم إضافة المسمى الوظيفي بنجاح')
            return redirect('hr:job_title_list')
        else:
            messages.error(request, 'يرجى تصحيح الأخطاء في النموذج')
    else:
        form = JobTitleForm(instance=job_title)
    
    context = {
        'form': form,
        'job_title': job_title,
        
        # بيانات الهيدر
        'page_title': 'تعديل مسمى وظيفي' if pk else 'إضافة مسمى وظيفي جديد',
        'page_subtitle': job_title.title_ar if pk and job_title else 'إدخال بيانات المسمى الوظيفي',
        'page_icon': 'fas fa-briefcase',
        'header_buttons': [
            {
                'url': reverse('hr:job_title_list'),
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users-cog'},
            {'title': 'المسميات الوظيفية', 'url': reverse('hr:job_title_list'), 'icon': 'fas fa-briefcase'},
            {'title': 'تعديل مسمى' if pk else 'إضافة مسمى', 'active': True},
        ],
    }
    return render(request, 'hr/job_title/form.html', context)
