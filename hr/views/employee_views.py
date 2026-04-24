"""
Views إدارة الموظفين
"""
from .base_imports import *
from ..models import Employee, Department, JobTitle, Shift, Contract, BiometricLog, BiometricUserMapping
from ..forms.employee_forms import EmployeeForm
from ..decorators import hr_manager_required, _is_hr_manager, require_hr
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST
from django.http import JsonResponse
import json
from ..models import SalaryComponent, Advance
from ..models.payroll import Payroll
from django.db.models import Sum, Q, Count, Prefetch
from ..services.user_employee_service import UserEmployeeService
from core.models import SystemSetting

__all__ = [
    'employee_list',
    'employee_detail',
    'employee_form',
    'employee_delete',
    'employee_reinstate',
    'check_component_code',
    'employee_export',
]


@login_required
def employee_list(request):
    """
    قائمة الموظفين مع Query Optimization
    Issue #11: N+1 queries in employee list
    """
    # جلب جميع الموظفين مع العلاقات - Optimized Query
    employees = Employee.objects.select_related(
        'department',
        'job_title',
        'direct_manager',
        'direct_manager__user',
        'shift',
        'user',
        'created_by',
    ).prefetch_related(
        Prefetch(
            'contracts',
            queryset=Contract.objects.filter(status='active').select_related('job_title', 'department', 'created_by'),
            to_attr='active_contracts'
        )
    ).all()
    
    # الفلترة حسب البحث
    search = request.GET.get('search', '')
    if search:
        employees = employees.filter(
            Q(name__icontains=search) |
            Q(employee_number__icontains=search)
        )
    
    # الفلترة حسب القسم
    department = request.GET.get('department', '')
    if department:
        employees = employees.filter(department_id=department)
    
    # الفلترة حسب الحالة - افتراضياً يُخفى منتهو الخدمة إلا لو فُلتر عليهم صراحةً
    status = request.GET.get('status', '')
    if status:
        employees = employees.filter(status=status)
    else:
        employees = employees.exclude(status='terminated')
    
    # الفلترة حسب المسمى الوظيفي
    job_title = request.GET.get('job_title', '')
    if job_title:
        employees = employees.filter(job_title_id=job_title)
        
    # الفلترة حسب التأمينات
    insurance_status = request.GET.get('insurance_status', '')
    if insurance_status == 'insured':
        employees = employees.filter(
            Q(is_insurance_only=True) | 
            Q(contracts__status='active', contracts__is_social_insurance_enrolled=True)
        ).distinct()
    elif insurance_status == 'uninsured':
        employees = employees.exclude(
            Q(is_insurance_only=True) | 
            Q(contracts__status='active', contracts__is_social_insurance_enrolled=True)
        ).distinct()
    
    # جلب الأقسام والمسميات الوظيفية للفلترة - Optimized
    departments = Department.objects.filter(is_active=True).only('id', 'name_ar')
    job_titles = JobTitle.objects.filter(is_active=True).only('id', 'title_ar')
    
    # الإحصائيات - query واحدة بدل 4
    stats = Employee.objects.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(status='active'))
    )
    total_employees = stats['total']
    active_employees = stats['active']
    total_departments = Department.objects.filter(is_active=True).count()
    total_job_titles = JobTitle.objects.filter(is_active=True).count()
    
    # تعريف رؤوس الجدول
    table_headers = [
        {'key': 'employee_number', 'label': 'رقم الموظف', 'sortable': True, 'class': 'text-center'},
        {'key': 'photo_display', 'label': 'الصورة', 'format': 'html', 'class': 'text-center'},
        {'key': 'full_name_display', 'label': 'الاسم', 'sortable': True, 'class': 'text-center fw-bold'},
        {'key': 'job_title_name', 'label': 'المسمى الوظيفي', 'sortable': True, 'class': 'text-center'},
        {'key': 'insurance_status', 'label': 'التأمينات', 'sortable': False, 'format': 'html', 'class': 'text-center'},
        {'key': 'hire_date', 'label': 'تاريخ التعيين', 'sortable': True, 'format': 'date', 'class': 'text-center'},
        {'key': 'years_of_service_display', 'label': 'سنوات الخدمة', 'sortable': True, 'class': 'text-center'},
        {'key': 'status_display', 'label': 'الحالة', 'sortable': True, 'format': 'html', 'class': 'text-center'},
        {'key': 'actions', 'label': 'الإجراءات', 'class': 'text-center'},
    ]
    
    # إزالة table_actions العامة - الأزرار ستُبنى per-row أدناه
    
    # حساب URLs مرة واحدة قبل الـ loop لتجنب N+1
    url_detail   = 'hr:employee_detail'
    url_edit     = 'hr:employee_form_edit'
    url_delete   = 'hr:employee_delete'

    # إضافة بيانات إضافية للعرض في الجدول
    can_edit = _is_hr_manager(request.user) or (hasattr(request.user, 'role') and request.user.role and request.user.role.name == 'hr') or request.user.has_perm('hr.change_employee')
    can_delete = request.user.is_superuser or getattr(request.user, 'is_admin', False) or \
        request.user.has_perm('hr.delete_employee') or \
        (hasattr(request.user, 'role') and request.user.role and
         request.user.role.permissions.filter(codename='delete_employee').exists())

    for employee in employees:
        # عرض الصورة في عمود منفصل
        if employee.photo:
            employee.photo_display = f'<img src="{employee.photo.url}" class="rounded-circle" width="40" height="40">'
        else:
            first_letter = employee.name[0] if employee.name else 'م'
            employee.photo_display = f'<div class="avatar-placeholder rounded-circle bg-primary text-white d-inline-flex align-items-center justify-content-center" style="width: 40px; height: 40px; font-size: 1.1rem; font-weight: 600;">{first_letter}</div>'
        
        # عرض الاسم الكامل
        employee.full_name_display = employee.get_full_name_ar()
        
        # اسم القسم
        employee.department_name = employee.department.name_ar if employee.department else '-'
        
        # اسم المسمى الوظيفي
        employee.job_title_name = employee.job_title.title_ar if employee.job_title else '-'
        
        # التأمينات
        if employee.is_insurance_only:
            employee.insurance_status = '<span class="badge bg-danger">مؤمن فقط</span>'
        else:
            active_contract = employee.active_contracts[0] if hasattr(employee, 'active_contracts') and employee.active_contracts else None
            if active_contract and active_contract.is_social_insurance_enrolled:
                employee.insurance_status = '<span class="badge bg-warning text-dark">موظف مؤمن</span>'
            else:
                employee.insurance_status = '<span class="text-muted">-</span>'
        
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
        
        # أزرار الإجراءات - الموظف المنتهي خدمته لا يظهر له زر التعديل أو الحذف
        employee.actions = [
            {'url': reverse(url_detail, kwargs={'pk': employee.pk}), 'icon': 'fas fa-eye', 'label': 'عرض', 'class': 'btn-outline-info btn-sm'},
        ]
        if employee.status != 'terminated':
            if can_edit:
                employee.actions.append(
                    {'url': reverse(url_edit, kwargs={'pk': employee.pk}), 'icon': 'fas fa-edit', 'label': 'تعديل', 'class': 'btn-outline-primary btn-sm'}
                )
            if can_delete:
                employee.actions.append(
                    {'url': reverse(url_delete, kwargs={'pk': employee.pk}), 'icon': 'fas fa-trash', 'label': 'حذف', 'class': 'btn-outline-danger btn-sm'}
                )
        else:
            if can_edit:
                employee.actions.append(
                    {'onclick': f'reinstateEmployee({employee.pk}, "{employee.get_full_name_ar()}")', 'icon': 'fas fa-undo', 'label': 'إعادة للخدمة', 'class': 'btn-outline-success btn-sm'}
                )
    
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
        
        # بيانات الهيدر
        'page_title': 'قائمة الموظفين',
        'page_subtitle': 'إدارة وعرض جميع الموظفين في النظام',
        'page_icon': 'fas fa-users',
        
        # أزرار الهيدر
        'header_buttons': [
            {
                'url': f"{reverse('hr:employee_export')}?format=xlsx&{request.GET.urlencode()}",
                'icon': 'fa-file-excel',
                'text': 'تصدير Excel',
                'class': 'btn-outline-success',
            },
            *([
                {
                    'url': '#',
                    'icon': 'fa-file-import',
                    'text': 'استيراد',
                    'class': 'btn-outline-primary',
                    'toggle': 'modal',
                    'target': '#importModal',
                },
                {
                    'url': reverse('hr:employee_form'),
                    'icon': 'fa-plus',
                    'text': 'إضافة موظف',
                    'class': 'btn-primary',
                },
            ] if can_edit else []),
        ],
        
        # البريدكرمب
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'قائمة الموظفين', 'active': True},
        ],
    }
    return render(request, 'hr/employee/list.html', context)


@login_required
def employee_detail(request, pk):
    """تفاصيل الموظف"""
    
    employee = get_object_or_404(Employee, pk=pk)

    can_edit = _is_hr_manager(request.user) or (hasattr(request.user, 'role') and request.user.role and request.user.role.name == 'hr') or request.user.has_perm('hr.change_employee')
    can_delete = request.user.is_superuser or getattr(request.user, 'is_admin', False) or \
        request.user.has_perm('hr.delete_employee') or \
        (hasattr(request.user, 'role') and request.user.role and
         request.user.role.permissions.filter(codename='delete_employee').exists())

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
    
    # جلب بنود الراتب (أول 5 بنود مرتبة: مستحقات ثم خصومات)
    salary_components_preview = employee.salary_components.filter(
        is_active=True
    ).order_by('component_type', 'order')[:5]
    
    # جلب قسائم الراتب (آخر 6 قسائم)
    payroll_slips = Payroll.objects.filter(
        employee=employee
    ).select_related('contract').order_by('-month')[:6]

    # إضافة correct_net و correct_gross لكل قسيمة — استخدام property من الـ model
    for _p in payroll_slips:
        _p._correct_net = _p.correct_net_salary
        _p._correct_gross = _p.correct_gross_salary
    
    # إحصائيات قسائم الراتب
    total_payrolls = employee.payrolls.count()
    paid_payrolls = employee.payrolls.filter(status='paid').count()
    approved_payrolls = employee.payrolls.filter(status='approved').count()

    # جلب السلف (آخر 6 سلف)
    advances = Advance.objects.filter(
        employee=employee
    ).order_by('-requested_at')[:6]

    # إحصائيات السلف
    total_advances = employee.advances.count()
    paid_advances = employee.advances.filter(status='paid').count()
    approved_advances_count = employee.advances.filter(status='approved').count()
    total_advances_amount = employee.advances.filter(status__in=['approved', 'paid']).aggregate(total=Sum('amount'))['total'] or 0

    
    context = {
        'employee': employee,
        'is_hr_only': hasattr(request.user, 'role') and request.user.role and request.user.role.name == 'hr',
        'unlinked_users': unlinked_users,
        'biometric_logs_count': biometric_logs_count,
        'biometric_logs_last_30_days': biometric_logs_last_30_days,
        'recent_biometric_logs': recent_biometric_logs,
        'biometric_mappings': biometric_mappings,
        'contracts': contracts,
        'active_contract': active_contract,
        'salary_components_preview': salary_components_preview,
        'payroll_slips': payroll_slips,
        'total_payrolls': total_payrolls,
        'paid_payrolls': paid_payrolls,
        'approved_payrolls': approved_payrolls,
        'advances': advances,
        'total_advances': total_advances,
        'paid_advances': paid_advances,
        'approved_advances_count': approved_advances_count,
        'total_advances_amount': total_advances_amount,
        
        # بيانات التأمين للموظفين الخارجيين
        'insurance_component': (
            employee.salary_components.filter(code='INSURANCE_TOTAL', is_active=True).first()
            if employee.is_insurance_only else None
        ),
        'insurance_settings': {
            'employee_share': SystemSetting.get_setting('hr_insurance_employee_share', 0),
            'employer_share': SystemSetting.get_setting('hr_insurance_employer_share', 0),
        },

        # بيانات الهيدر
        'page_title': employee.get_full_name_ar(),
        'page_subtitle': f'{employee.job_title.title_ar} - {employee.department.name_ar}',
        'page_icon': 'fas fa-user',
        'page_subtitle': f'{employee.job_title.title_ar} - {employee.department.name_ar}',
        'page_icon': 'fas fa-user',
        
        # أزرار الهيدر - الموظف المنتهي خدمته لا يظهر له زر التعديل
        'header_buttons': [
            *(
                [
                    {
                        'url': reverse('hr:employee_form_edit', kwargs={'pk': employee.pk}),
                        'icon': 'fa-edit',
                        'text': 'تعديل',
                        'class': 'btn-warning',
                    },
                    *(
                        [{
                            'toggle': 'modal',
                            'target': '#terminateEmployeeModal',
                            'icon': 'fa-user-times',
                            'text': 'إنهاء الخدمة',
                            'class': 'btn-danger',
                        }] if can_edit else []
                    ),
                ] if employee.status != 'terminated' else [
                    *(
                        [{
                            'onclick': f'reinstateEmployee({employee.pk}, "{employee.get_full_name_ar()}")',
                            'icon': 'fa-undo',
                            'text': 'إعادة للخدمة',
                            'class': 'btn-success',
                        }] if can_edit else []
                    )
                ]
            ),
            {
                'url': reverse('hr:employee_list'),
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary',
            },
        ],
        
        # البريدكرمب
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'الموظفين', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users'},
            {'title': employee.get_full_name_ar(), 'active': True},
        ],
    }
    return render(request, 'hr/employee/detail.html', context)


@login_required
@hr_manager_required
def employee_delete(request, pk):
    """حذف موظف"""
    employee = get_object_or_404(Employee, pk=pk)
    if request.method == 'POST':
        from django.utils import timezone
        employee.status = 'terminated'
        if not employee.termination_date:
            employee.termination_date = timezone.now().date()
        try:
            employee.save()
            messages.success(request, 'تم إنهاء خدمة الموظف بنجاح')
        except Exception as e:
            messages.error(request, f'حدث خطأ أثناء إنهاء الخدمة: {str(e)}')
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
@require_hr
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
        
        # بيانات الهيدر
        'page_title': 'تعديل موظف' if pk else 'إضافة موظف جديد',
        'page_subtitle': employee.get_full_name_ar() if pk else 'إدخال بيانات الموظف الأساسية',
        'page_icon': 'fas fa-user-edit' if pk else 'fas fa-user-plus',
        
        # أزرار الهيدر
        'header_buttons': [
            {
                'url': reverse('hr:employee_list'),
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary',
            },
        ],
        
        # البريدكرمب
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'الموظفين', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users'},
            {'title': 'تعديل موظف' if pk else 'إضافة موظف', 'active': True},
        ],
    }
    return render(request, 'hr/employee/form.html', context)


@login_required
@require_POST
def check_component_code(request, employee_id):
    """التحقق من وجود كود البند للموظف"""
    
    try:
        employee = get_object_or_404(Employee, id=employee_id)
        data = json.loads(request.body)
        code = data.get('code', '').strip()
        
        if not code:
            return JsonResponse({'exists': False})
        
        existing = SalaryComponent.objects.filter(
            employee=employee,
            code=code
        ).first()
        
        if existing:
            return JsonResponse({
                'exists': True,
                'component_id': existing.id,
                'existing_name': existing.name,
                'amount': str(existing.amount),
                'is_from_contract': existing.is_from_contract,
                'component_type': existing.get_component_type_display()
            })
        else:
            return JsonResponse({'exists': False})
            
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@hr_manager_required
@require_POST
def employee_reinstate(request, pk):
    """إعادة الموظف للخدمة"""
    from ..services.employee_service import EmployeeService
    employee = get_object_or_404(Employee, pk=pk)
    
    if employee.status != 'terminated':
        messages.warning(request, 'الموظف ليس في حالة منتهي الخدمة')
        return redirect('hr:employee_detail', pk=pk)
    
    try:
        EmployeeService.reinstate_employee(employee, request.user)
        messages.success(request, f'تم إعادة {employee.get_full_name_ar()} للخدمة بنجاح')
    except Exception as e:
        messages.error(request, f'حدث خطأ: {str(e)}')
    
    return redirect('hr:employee_detail', pk=pk)


@login_required
def employee_export(request):
    """تصدير الموظفين إلى CSV أو Excel"""
    from .employee_import import export_employees
    
    export_format = request.GET.get('format', 'xlsx')
    
    # جلب الموظفين مع نفس الفلاتر المطبقة في القائمة
    employees = Employee.objects.select_related(
        'department',
        'job_title',
        'user'
    ).all()
    
    # تطبيق الفلاتر
    search = request.GET.get('search', '')
    if search:
        employees = employees.filter(
            Q(name__icontains=search) |
            Q(employee_number__icontains=search)
        )
    
    department = request.GET.get('department', '')
    if department:
        employees = employees.filter(department_id=department)
    
    status = request.GET.get('status', '')
    if status:
        employees = employees.filter(status=status)
    else:
        employees = employees.exclude(status='terminated')

    job_title = request.GET.get('job_title', '')
    if job_title:
        employees = employees.filter(job_title_id=job_title)

    return export_employees(employees, export_format)
