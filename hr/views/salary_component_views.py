"""
Views لإدارة بنود الراتب
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.urls import reverse
from django.db.models import Q
from datetime import date

from ..models import Employee, SalaryComponent, SalaryComponentTemplate, Contract
from ..forms.salary_component_forms import SalaryComponentForm, SalaryComponentQuickForm
from ..services import SalaryComponentService

__all__ = [
    'employee_salary_components',
    'salary_component_create',
    'salary_component_edit',
    'salary_component_delete',
    'salary_component_toggle_active',
    'salary_component_quick_add',
]


@login_required
def employee_salary_components(request, employee_id):
    """عرض بنود راتب الموظف - منفصلة حسب المصدر"""
    employee = get_object_or_404(Employee, pk=employee_id)
    
    # الحصول على العقد النشط
    active_contract = employee.contracts.filter(status='active').first()
    
    # جلب جميع البنود
    components = employee.salary_components.select_related(
        'template', 'contract', 'source_contract_component'
    ).order_by('component_type', 'order', 'name')
    
    # تصنيف البنود حسب المصدر
    active_components = components.filter(is_active=True)
    
    # بنود العقد (منسوخة من العقد - للقراءة فقط)
    contract_components = active_components.filter(is_from_contract=True)
    contract_earnings = contract_components.filter(component_type='earning')
    contract_deductions = contract_components.filter(component_type='deduction')
    
    # بنود الموظف المتغيرة (قابلة للتعديل)
    employee_components = active_components.filter(is_from_contract=False)
    employee_earnings = employee_components.filter(component_type='earning')
    employee_deductions = employee_components.filter(component_type='deduction')
    
    # البنود غير النشطة
    inactive_components = components.filter(is_active=False)
    
    # للتوافق مع الكود القديم
    earnings = active_components.filter(component_type='earning')
    deductions = active_components.filter(component_type='deduction')
    
    # حساب الإجماليات (الراتب الأساسي بيتحسب من العقد النشط في الـ service)
    salary_summary = SalaryComponentService.calculate_total_salary(employee)
    
    # القوالب المتاحة
    available_templates = SalaryComponentTemplate.objects.filter(is_active=True).order_by(
        'component_type', 'order'
    )
    
    context = {
        'employee': employee,
        'active_contract': active_contract,
        'components': components,
        'active_components': active_components,
        'inactive_components': inactive_components,
        
        # بنود العقد (للقراءة فقط)
        'contract_components': contract_components,
        'contract_earnings': contract_earnings,
        'contract_deductions': contract_deductions,
        
        # بنود الموظف (قابلة للتعديل)
        'employee_components': employee_components,
        'employee_earnings': employee_earnings,
        'employee_deductions': employee_deductions,
        
        # للتوافق مع الكود القديم
        'earnings': earnings,
        'deductions': deductions,
        'salary_summary': salary_summary,
        'available_templates': available_templates,
        
        # Header
        'page_title': f'بنود راتب {employee.get_full_name_ar()}',
        'page_subtitle': 'إدارة المستحقات والاستقطاعات',
        'page_icon': 'fas fa-money-bill-wave',
        'header_buttons': [
            {
                'url': '#',
                'icon': 'fa-plus',
                'text': 'إضافة بند جديد',
                'class': 'btn-primary',
                'data_attrs': 'data-bs-toggle="modal" data-bs-target="#addComponentModal"'
            },
            {
                'url': '#',
                'icon': 'fa-bolt',
                'text': 'إضافة سريعة من قالب',
                'class': 'btn-success',
                'data_attrs': 'data-bs-toggle="modal" data-bs-target="#quickAddModal"'
            },
            {
                'url': reverse('hr:employee_detail', kwargs={'pk': employee_id}),
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary'
            }
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users'},
            {'title': 'الموظفين', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-user-tie'},
            {'title': employee.get_full_name_ar(), 'url': reverse('hr:employee_detail', kwargs={'pk': employee_id})},
            {'title': 'بنود الراتب', 'active': True},
        ],
    }
    
    return render(request, 'hr/employee/salary_components.html', context)


@login_required
def salary_component_create(request, employee_id):
    """إنشاء بند راتب جديد"""
    employee = get_object_or_404(Employee, pk=employee_id)
    active_contract = employee.contracts.filter(status='active').first()
    
    if request.method == 'POST':
        form = SalaryComponentForm(
            request.POST,
            employee=employee,
            contract=active_contract
        )
        
        if form.is_valid():
            component = form.save()
            
            # رسالة نجاح
            messages.success(
                request,
                f'تم إضافة بند "{component.name}" بنجاح'
            )
            
            # AJAX response
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': f'تم إضافة بند "{component.name}" بنجاح',
                    'component_id': component.id
                })
            
            return redirect('hr:employee_salary_components', employee_id=employee_id)
        else:
            # AJAX error response
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'errors': form.errors
                }, status=400)
    else:
        form = SalaryComponentForm(
            employee=employee,
            contract=active_contract,
            initial={
                'is_active': True,
                'effective_from': date.today(),
                'show_in_payslip': True
            }
        )
    
    context = {
        'form': form,
        'employee': employee,
        'is_edit': False
    }
    
    return render(request, 'hr/salary_component/form_modal.html', context)


@login_required
def salary_component_edit(request, employee_id, component_id):
    """تعديل بند راتب"""
    employee = get_object_or_404(Employee, pk=employee_id)
    component = get_object_or_404(
        SalaryComponent,
        pk=component_id,
        employee=employee
    )
    
    if request.method == 'POST':
        form = SalaryComponentForm(
            request.POST,
            instance=component,
            employee=employee,
            contract=component.contract
        )
        
        if form.is_valid():
            component = form.save()
            
            messages.success(
                request,
                f'تم تعديل بند "{component.name}" بنجاح'
            )
            
            # AJAX response
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': f'تم تعديل بند "{component.name}" بنجاح'
                })
            
            return redirect('hr:employee_salary_components', employee_id=employee_id)
        else:
            # AJAX error response
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'errors': form.errors
                }, status=400)
    else:
        form = SalaryComponentForm(
            instance=component,
            employee=employee,
            contract=component.contract
        )
    
    context = {
        'form': form,
        'employee': employee,
        'component': component,
        'is_edit': True
    }
    
    return render(request, 'hr/salary_component/form_modal.html', context)


@login_required
def salary_component_delete(request, employee_id, component_id):
    """حذف بند راتب"""
    employee = get_object_or_404(Employee, pk=employee_id)
    component = get_object_or_404(
        SalaryComponent,
        pk=component_id,
        employee=employee
    )
    
    if request.method == 'POST':
        component_name = component.name
        component.delete()
        
        messages.success(
            request,
            f'تم حذف بند "{component_name}" بنجاح'
        )
        
        # AJAX response
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'message': f'تم حذف بند "{component_name}" بنجاح'
            })
        
        return redirect('hr:employee_salary_components', employee_id=employee_id)
    
    context = {
        'employee': employee,
        'component': component
    }
    
    return render(request, 'hr/salary_component/delete_modal.html', context)


@login_required
def salary_component_toggle_active(request, employee_id, component_id):
    """تفعيل/إلغاء تفعيل بند"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'طريقة غير مسموحة'}, status=405)
    
    employee = get_object_or_404(Employee, pk=employee_id)
    component = get_object_or_404(
        SalaryComponent,
        pk=component_id,
        employee=employee
    )
    
    # عكس الحالة
    component.is_active = not component.is_active
    component.save()
    
    status_text = 'تفعيل' if component.is_active else 'إلغاء تفعيل'
    
    return JsonResponse({
        'success': True,
        'message': f'تم {status_text} بند "{component.name}" بنجاح',
        'is_active': component.is_active
    })


@login_required
def salary_component_quick_add(request, employee_id):
    """إضافة سريعة من قالب"""
    employee = get_object_or_404(Employee, pk=employee_id)
    active_contract = employee.contracts.filter(status='active').first()
    
    if request.method == 'POST':
        form = SalaryComponentQuickForm(
            request.POST,
            employee=employee,
            contract=active_contract
        )
        
        if form.is_valid():
            component = form.save()
            
            messages.success(
                request,
                f'تم إضافة بند "{component.name}" من القالب بنجاح'
            )
            
            # AJAX response
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': f'تم إضافة بند "{component.name}" من القالب بنجاح',
                    'component_id': component.id
                })
            
            return redirect('hr:employee_salary_components', employee_id=employee_id)
        else:
            # AJAX error response
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'errors': form.errors
                }, status=400)
    else:
        form = SalaryComponentQuickForm(
            employee=employee,
            contract=active_contract,
            initial={'effective_from': date.today()}
        )
    
    context = {
        'form': form,
        'employee': employee
    }
    
    return render(request, 'hr/salary_component/quick_add_modal.html', context)
