"""
Views متنوعة للموارد البشرية
"""
from .base_imports import *
from ..models import Employee, Department, JobTitle, LeaveType, LeaveBalance, Shift, BiometricDevice
from ..models import SalaryComponentTemplate
from core.models import SystemSetting
from datetime import date, timedelta

__all__ = [
    'organization_chart',
    'hr_settings',
    'employee_create_user',
    'employee_link_user',
    'employee_unlink_user',
    'check_employee_email',
    'check_employee_mobile',
    'check_employee_national_id',
    'salary_component_templates_list',
    'salary_component_template_form',
    'salary_component_template_delete',
    'employee_detail_api',
    'contract_check_overlap',
]


# ==================== الهيكل التنظيمي ====================

@login_required
def organization_chart(request):
    """عرض الهيكل التنظيمي"""
    root_departments = Department.objects.filter(parent=None, is_active=True).prefetch_related('sub_departments')
    
    context = {
        'root_departments': root_departments,
        'total_departments': Department.objects.filter(is_active=True).count(),
        'total_employees': Employee.objects.filter(status='active').count(),
        'total_job_titles': JobTitle.objects.filter(is_active=True).count(),
        
        # بيانات الهيدر الموحد
        'page_title': 'الهيكل التنظيمي',
        'page_subtitle': 'عرض الهيكل التنظيمي للشركة',
        'page_icon': 'fas fa-sitemap',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users-cog'},
            {'title': 'الإعدادات', 'url': reverse('hr:hr_settings'), 'icon': 'fas fa-cog'},
            {'title': 'الهيكل التنظيمي', 'active': True},
        ],
    }
    return render(request, 'hr/organization/chart.html', context)


# ==================== إعدادات الموارد البشرية ====================

@login_required
def hr_settings(request):
    """صفحة إعدادات الموارد البشرية"""
    if request.method == 'POST':
        # حفظ إعدادات الإجازات
        numeric_settings = [
            'leave_accrual_probation_months',
            'leave_accrual_partial_percentage',
            'leave_accrual_full_months',
            'leave_rollover_max_days',
        ]
        
        for setting_key in numeric_settings:
            if setting_key in request.POST:
                value = request.POST.get(setting_key)
                SystemSetting.objects.filter(key=setting_key).update(value=value)
        
        # الـ checkboxes
        checkbox_settings = [
            'leave_auto_create_balances',
            'leave_rollover_enabled',
        ]
        
        for setting_key in checkbox_settings:
            value = 'true' if setting_key in request.POST else 'false'
            SystemSetting.objects.filter(key=setting_key).update(value=value)
        
        # حفظ عدد أيام أنواع الإجازات
        leave_types = LeaveType.objects.filter(is_active=True)
        for leave_type in leave_types:
            field_name = f'leave_type_{leave_type.id}_days'
            if field_name in request.POST:
                new_days = int(request.POST.get(field_name))
                if new_days != leave_type.max_days_per_year:
                    leave_type.max_days_per_year = new_days
                    leave_type.save()
        
        messages.success(request, 'تم حفظ إعدادات الإجازات بنجاح')
        return redirect('hr:hr_settings')
    
    # جلب إعدادات الإجازات
    leave_settings = {
        'probation_months': SystemSetting.get_setting('leave_accrual_probation_months', 3),
        'partial_percentage': SystemSetting.get_setting('leave_accrual_partial_percentage', 25),
        'full_months': SystemSetting.get_setting('leave_accrual_full_months', 6),
        'auto_create': SystemSetting.get_setting('leave_auto_create_balances', True),
        'rollover_enabled': SystemSetting.get_setting('leave_rollover_enabled', False),
        'rollover_max_days': SystemSetting.get_setting('leave_rollover_max_days', 7),
    }
    
    leave_types = LeaveType.objects.filter(is_active=True).order_by('code')
    
    # إحصائيات قوالب مكونات الراتب
    salary_templates_earnings = SalaryComponentTemplate.objects.filter(component_type='earning', is_active=True).count()
    salary_templates_deductions = SalaryComponentTemplate.objects.filter(component_type='deduction', is_active=True).count()
    
    context = {
        'active_menu': 'hr',
        'leave_settings': leave_settings,
        'leave_types': leave_types,
        'departments_count': Department.objects.filter(is_active=True).count(),
        'total_departments': Department.objects.count(),
        'job_titles_count': JobTitle.objects.filter(is_active=True).count(),
        'total_job_titles': JobTitle.objects.count(),
        'shifts_count': Shift.objects.filter(is_active=True).count(),
        'total_shifts': Shift.objects.count(),
        'biometric_devices_count': BiometricDevice.objects.filter(is_active=True).count(),
        'total_biometric_devices': BiometricDevice.objects.count(),
        'leave_balances_count': LeaveBalance.objects.count(),
        'employees_with_balance': LeaveBalance.objects.values('employee').distinct().count(),
        'salary_templates_earnings': salary_templates_earnings,
        'salary_templates_deductions': salary_templates_deductions,
        
        # بيانات الهيدر الموحد
        'page_title': 'إعدادات الموارد البشرية',
        'page_subtitle': 'إدارة وتكوين إعدادات نظام الموارد البشرية',
        'page_icon': 'fas fa-cog',
        'header_buttons': [
            {
                'url': reverse('hr:dashboard'),
                'icon': 'fa-arrow-right',
                'text': 'العودة للوحة التحكم',
                'class': 'btn-outline-secondary',
            }
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users-cog'},
            {'title': 'الإعدادات', 'active': True},
        ],
    }
    return render(request, 'hr/settings.html', context)


# ==================== ربط الموظفين بالمستخدمين ====================

@login_required
def employee_create_user(request, pk):
    """إنشاء حساب مستخدم لموظف"""
    from ..services.user_employee_service import UserEmployeeService
    
    employee = get_object_or_404(Employee, pk=pk)
    
    if employee.user:
        messages.warning(request, 'الموظف مرتبط بمستخدم بالفعل')
        return redirect('hr:employee_detail', pk=pk)
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        send_email = request.POST.get('send_email') == 'on'
        
        try:
            user, created_password = UserEmployeeService.create_user_for_employee(
                employee=employee,
                username=username,
                password=password,
                send_email=send_email
            )
            
            if send_email:
                messages.success(request, f'تم إنشاء الحساب بنجاح وإرسال البيانات للبريد: {employee.work_email}')
            else:
                messages.success(request, f'تم إنشاء الحساب بنجاح - اسم المستخدم: {username}')
            
        except Exception as e:
            messages.error(request, f'خطأ: {str(e)}')
    
    return redirect('hr:employee_detail', pk=pk)


@login_required
def employee_link_user(request, pk):
    """ربط موظف بمستخدم موجود"""
    from ..services.user_employee_service import UserEmployeeService
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    employee = get_object_or_404(Employee, pk=pk)
    
    if employee.user:
        messages.warning(request, 'الموظف مرتبط بمستخدم بالفعل')
        return redirect('hr:employee_detail', pk=pk)
    
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        
        try:
            user = User.objects.get(pk=user_id)
            UserEmployeeService.link_existing_user_to_employee(employee, user)
            messages.success(request, f'تم ربط الموظف بالمستخدم: {user.username}')
        except User.DoesNotExist:
            messages.error(request, 'المستخدم غير موجود')
        except Exception as e:
            messages.error(request, f'خطأ: {str(e)}')
    
    return redirect('hr:employee_detail', pk=pk)


@login_required
def employee_unlink_user(request, pk):
    """فك ربط موظف من مستخدم"""
    employee = get_object_or_404(Employee, pk=pk)
    
    if not employee.user:
        messages.warning(request, 'الموظف غير مرتبط بمستخدم')
        return redirect('hr:employee_detail', pk=pk)
    
    if request.method == 'POST':
        username = employee.user.username
        employee.user = None
        employee.save()
        messages.success(request, f'تم فك الربط من المستخدم: {username}')
    
    return redirect('hr:employee_detail', pk=pk)


# ==================== API للتحقق من التكرار ====================

@login_required
def check_employee_email(request):
    """التحقق من تكرار البريد الإلكتروني"""
    email = request.GET.get('email', '')
    employee_id = request.GET.get('employee_id', None)
    
    if not email:
        return JsonResponse({'available': True})
    
    query = Employee.objects.filter(work_email=email)
    if employee_id:
        query = query.exclude(pk=employee_id)
    
    exists = query.exists()
    
    return JsonResponse({
        'available': not exists,
        'message': 'هذا البريد الإلكتروني مستخدم بالفعل' if exists else 'البريد الإلكتروني متاح'
    })


@login_required
def check_employee_mobile(request):
    """التحقق من تكرار رقم الموبايل"""
    mobile = request.GET.get('mobile', '')
    employee_id = request.GET.get('employee_id', None)
    
    if not mobile:
        return JsonResponse({'available': True})
    
    query = Employee.objects.filter(mobile_phone=mobile)
    if employee_id:
        query = query.exclude(pk=employee_id)
    
    exists = query.exists()
    
    return JsonResponse({
        'available': not exists,
        'message': 'رقم الموبايل مستخدم بالفعل' if exists else 'رقم الموبايل متاح'
    })


@login_required
def check_employee_national_id(request):
    """التحقق من تكرار الرقم القومي"""
    national_id = request.GET.get('national_id', '')
    employee_id = request.GET.get('employee_id', None)
    
    if not national_id:
        return JsonResponse({'available': True})
    
    query = Employee.objects.filter(national_id=national_id)
    if employee_id:
        query = query.exclude(pk=employee_id)
    
    exists = query.exists()
    
    return JsonResponse({
        'available': not exists,
        'message': 'هذا الرقم القومي مستخدم بالفعل' if exists else 'الرقم القومي متاح'
    })


# ==================== Salary Component Templates ====================

@login_required
def salary_component_templates_list(request):
    """قائمة قوالب مكونات الراتب"""
    from django.urls import reverse
    
    templates = SalaryComponentTemplate.objects.all().order_by('component_type', 'order', 'name')
    
    context = {
        'templates': templates,
        'earnings': templates.filter(component_type='earning'),
        'deductions': templates.filter(component_type='deduction'),
        'page_title': 'قوالب مكونات الراتب',
        'page_subtitle': 'إدارة بنود المستحقات والاستقطاعات',
        'page_icon': 'fas fa-clipboard-list',
        'header_buttons': [
            {
                'url': reverse('hr:salary_component_template_form'),
                'icon': 'fa-plus',
                'text': 'إضافة قالب جديد',
                'class': 'btn-primary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users'},
            {'title': 'الإعدادات', 'url': reverse('hr:hr_settings'), 'icon': 'fas fa-cog'},
            {'title': 'قوالب مكونات الراتب', 'active': True},
        ],
    }
    return render(request, 'hr/salary_component_templates/list.html', context)


@login_required
def salary_component_template_form(request, pk=None):
    """نموذج إضافة/تعديل قالب مكون الراتب"""
    from django.urls import reverse
    from ..forms.salary_component_template_forms import SalaryComponentTemplateForm
    
    template = None
    if pk:
        template = get_object_or_404(SalaryComponentTemplate, pk=pk)
    
    if request.method == 'POST':
        form = SalaryComponentTemplateForm(request.POST, instance=template)
        if form.is_valid():
            template = form.save()
            messages.success(request, f'تم {"تعديل" if pk else "إضافة"} القالب بنجاح')
            return redirect('hr:salary_component_templates_list')
    else:
        form = SalaryComponentTemplateForm(instance=template)
    
    is_edit = pk is not None
    context = {
        'form': form,
        'template': template,
        'is_edit': is_edit,
        'page_title': f'{"تعديل" if is_edit else "إضافة"} قالب مكون الراتب',
        'page_subtitle': f'{"تعديل بيانات القالب" if is_edit else "إضافة قالب جديد للمستحقات أو الاستقطاعات"}',
        'page_icon': f'fas fa-{"edit" if is_edit else "plus"}',
        'header_buttons': [
            {
                'url': reverse('hr:salary_component_templates_list'),
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users'},
            {'title': 'الإعدادات', 'url': reverse('hr:hr_settings'), 'icon': 'fas fa-cog'},
            {'title': 'قوالب مكونات الراتب', 'url': reverse('hr:salary_component_templates_list'), 'icon': 'fas fa-clipboard-list'},
            {'title': 'تعديل' if is_edit else 'إضافة', 'active': True},
        ],
    }
    return render(request, 'hr/salary_component_templates/form.html', context)


@login_required
def salary_component_template_delete(request, pk):
    """حذف قالب مكون الراتب"""
    template = get_object_or_404(SalaryComponentTemplate, pk=pk)
    
    if request.method == 'POST':
        template_name = template.name
        template.delete()
        messages.success(request, f'تم حذف القالب "{template_name}" بنجاح')
        return redirect('hr:salary_component_templates_list')
    
    item_fields = [
        {'label': 'الاسم', 'value': template.name},
        {'label': 'النوع', 'value': template.get_component_type_display()},
    ]
    
    if template.formula:
        item_fields.append({'label': 'الصيغة', 'value': template.formula})
    if template.default_amount:
        item_fields.append({'label': 'المبلغ', 'value': template.default_amount})
    
    context = {
        'template': template,
        'item_fields': item_fields,
    }
    return render(request, 'hr/salary_component_templates/delete_modal.html', context)


# ==================== APIs متنوعة ====================

@login_required
@require_http_methods(["GET"])
def employee_detail_api(request, pk):
    """API لجلب بيانات الموظف"""
    import logging
    import traceback
    logger = logging.getLogger(__name__)
    
    try:
        employee = Employee.objects.select_related('job_title', 'department').get(pk=pk)
        
        data = {
            'id': employee.id,
            'employee_number': employee.employee_number,
            'name': f"{employee.first_name_ar} {employee.last_name_ar}",
        }
        
        # جلب رقم البصمة
        from ..models import BiometricUserMapping
        biometric_mapping = BiometricUserMapping.objects.filter(employee=employee, is_active=True).first()
        data['biometric_user_id'] = biometric_mapping.biometric_user_id if biometric_mapping else None
        
        # الوظيفة
        data['job_title'] = employee.job_title.id if employee.job_title else None
        data['job_title_name'] = str(employee.job_title) if employee.job_title else None
        
        # القسم
        data['department'] = employee.department.id if employee.department else None
        data['department_name'] = str(employee.department) if employee.department else None
        
        return JsonResponse(data)
        
    except Employee.DoesNotExist:
        return JsonResponse({'error': 'الموظف غير موجود'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def contract_check_overlap(request):
    """التحقق من تداخل العقود عبر AJAX"""
    from datetime import datetime
    from ..models import Contract
    
    try:
        employee_id = request.POST.get('employee_id')
        start_date_str = request.POST.get('start_date')
        end_date_str = request.POST.get('end_date')
        contract_id = request.POST.get('contract_id')
        
        if not employee_id or not start_date_str:
            return JsonResponse({'has_overlap': False, 'message': ''})
        
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = None
        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        
        allowed_statuses = ['expired', 'terminated', 'suspended']
        overlapping_contracts = Contract.objects.filter(
            employee_id=employee_id
        ).exclude(status__in=allowed_statuses)
        
        if contract_id:
            overlapping_contracts = overlapping_contracts.exclude(pk=contract_id)
        
        for contract in overlapping_contracts:
            if not contract.end_date:
                return JsonResponse({
                    'has_overlap': True,
                    'message': f'يوجد عقد ساري للموظف بدون تاريخ نهاية: {contract.contract_number}'
                })
            
            if not end_date:
                return JsonResponse({
                    'has_overlap': True,
                    'message': f'يوجد عقد ساري للموظف: {contract.contract_number}'
                })
            
            if start_date <= contract.end_date and end_date >= contract.start_date:
                return JsonResponse({
                    'has_overlap': True,
                    'message': f'يوجد تداخل مع عقد ساري: {contract.contract_number}'
                })
        
        return JsonResponse({'has_overlap': False, 'message': ''})
    
    except Exception as e:
        return JsonResponse({'has_overlap': False, 'message': '', 'error': str(e)}, status=500)
