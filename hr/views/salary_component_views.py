"""
Views لإدارة بنود الراتب
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from hr.models import Employee, SalaryComponent, SalaryComponentTemplate, Contract
from hr.forms.salary_component_forms import UnifiedSalaryComponentForm
from hr.services import SalaryComponentService
from hr.services.component_classification_service import ComponentClassificationService
from datetime import date
from decimal import Decimal
import json


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
    
    # استخدام النظام الجديد للتصنيف
    components_by_source = ComponentClassificationService.get_components_by_source(employee)
    
    # البنود حسب المصدر
    contract_components = components_by_source['contract']
    temporary_components = components_by_source['temporary']
    personal_components = components_by_source['personal']
    exceptional_components = components_by_source['exceptional']
    adjustment_components = components_by_source['adjustment']
    inactive_components = components_by_source['inactive']
    
    # تصنيف حسب النوع (للتوافق مع الكود القديم)
    active_components = components.filter(is_active=True)
    earnings = active_components.filter(component_type='earning')
    deductions = active_components.filter(component_type='deduction')
    
    # البنود القابلة للتجديد والمنتهية قريباً
    expiring_components = ComponentClassificationService.get_expiring_components().filter(employee=employee)
    renewable_components = [c for c in ComponentClassificationService.get_renewable_components() if c.employee == employee]

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
        
        # البنود حسب المصدر الجديد
        'contract_components': contract_components,
        'temporary_components': temporary_components,
        'personal_components': personal_components,
        'exceptional_components': exceptional_components,
        'adjustment_components': adjustment_components,
        
        # البنود المنتهية والقابلة للتجديد
        'expiring_components': expiring_components,
        'renewable_components': renewable_components,
        
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
                'onclick': 'openUnifiedModal()',
                'icon': 'fa-plus',
                'text': 'إضافة بند جديد',
                'class': 'btn-primary'
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


# ==================== النظام الموحد الجديد ====================

class UnifiedSalaryComponentView(LoginRequiredMixin, View):
    """View موحد لإدارة بنود الراتب"""
    
    def get(self, request, employee_id, component_id=None):
        """عرض النموذج الموحد"""
        employee = get_object_or_404(Employee, pk=employee_id)
        active_contract = employee.contracts.filter(status='active').first()
        
        # تحديد ما إذا كان تعديل أم إضافة
        is_edit = component_id is not None
        component = None
        
        if is_edit:
            component = get_object_or_404(SalaryComponent, pk=component_id, employee=employee)
        
        # إنشاء النموذج
        form = UnifiedSalaryComponentForm(
            instance=component,
            employee=employee,
            contract=active_contract,
            is_edit=is_edit
        )
        
        # جلب القوالب النشطة للاستخدام في JavaScript
        templates = SalaryComponentTemplate.objects.filter(is_active=True).order_by('component_type', 'order', 'name')
        
        # جلب القوالب المستخدمة بالفعل للموظف (إلا إذا كان تعديل)
        used_template_ids = []
        if not is_edit:
            used_template_ids = list(
                employee.salary_components.filter(template__isnull=False)
                .values_list('template_id', flat=True)
            )
        elif component and component.template:
            # في حالة التعديل، استثناء القالب الحالي
            used_template_ids = list(
                employee.salary_components.filter(template__isnull=False)
                .exclude(id=component.id)
                .values_list('template_id', flat=True)
            )
        
        templates_data = []
        for template in templates:
            templates_data.append({
                'id': template.id,
                'name': template.name,
                'component_type': template.component_type,
                'component_type_display': template.get_component_type_display(),
                'default_amount': float(template.default_amount),
                'formula': template.formula,
                'description': template.description,
                'code': template.code,
                'is_used': template.id in used_template_ids  # إضافة معلومة الاستخدام
            })
        
        context = {
            'form': form,
            'employee': employee,
            'component': component,
            'is_edit': is_edit,
            'templates_data': json.dumps(templates_data),
            'active_contract': active_contract
        }
        
        return render(request, 'hr/salary_component/unified_form.html', context)
    
    def post(self, request, employee_id, component_id=None):
        """معالجة إرسال النموذج"""
        employee = get_object_or_404(Employee, pk=employee_id)
        active_contract = employee.contracts.filter(status='active').first()
        
        # تحديد ما إذا كان تعديل أم إضافة
        is_edit = component_id is not None
        component = None
        
        if is_edit:
            component = get_object_or_404(SalaryComponent, pk=component_id, employee=employee)
        
        # إنشاء النموذج مع البيانات المرسلة
        form = UnifiedSalaryComponentForm(
            request.POST,
            instance=component,
            employee=employee,
            contract=active_contract,
            is_edit=is_edit
        )
        
        if form.is_valid():
            try:
                # حفظ البند
                saved_component = form.save()
                
                # رسالة النجاح
                action = 'تحديث' if is_edit else 'إضافة'
                success_message = f'تم {action} بند "{saved_component.name}" بنجاح'
                
                # استجابة AJAX
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True,
                        'message': success_message,
                        'component_id': saved_component.id,
                        'component_name': saved_component.name,
                        'redirect_url': reverse('hr:employee_salary_components', kwargs={'employee_id': employee_id})
                    })
                
                # استجابة عادية
                messages.success(request, success_message)
                return redirect('hr:employee_salary_components', employee_id=employee_id)
                
            except Exception as e:
                error_message = f'حدث خطأ أثناء الحفظ: {str(e)}'
                
                # استجابة AJAX للخطأ
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'message': error_message
                    }, status=400)
                
                messages.error(request, error_message)
        else:
            # أخطاء التحقق
            print(f"أخطاء النموذج: {form.errors}")
            print(f"البيانات المرسلة: {request.POST}")
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'errors': form.errors,
                    'message': 'يرجى تصحيح الأخطاء أدناه'
                }, status=400)
        
        # إعادة عرض النموذج مع الأخطاء
        templates = SalaryComponentTemplate.objects.filter(is_active=True).order_by('component_type', 'order', 'name')
        templates_data = []
        for template in templates:
            templates_data.append({
                'id': template.id,
                'name': template.name,
                'component_type': template.component_type,
                'component_type_display': template.get_component_type_display(),
                'default_amount': float(template.default_amount),
                'formula': template.formula,
                'description': template.description,
                'code': template.code
            })
        
        context = {
            'form': form,
            'employee': employee,
            'component': component,
            'is_edit': is_edit,
            'templates_data': json.dumps(templates_data),
            'active_contract': active_contract
        }
        
        return render(request, 'hr/salary_component/unified_form.html', context)


@login_required
@require_http_methods(["POST"])
def get_template_details(request):
    """جلب تفاصيل قالب معين عبر AJAX"""
    template_id = request.POST.get('template_id')
    
    if not template_id:
        return JsonResponse({'success': False, 'message': 'معرف القالب مطلوب'}, status=400)
    
    try:
        template = SalaryComponentTemplate.objects.get(id=template_id, is_active=True)
        
        # حساب المبلغ للموظف إذا كان هناك راتب أساسي
        employee_id = request.POST.get('employee_id')
        calculated_amount = float(template.default_amount)
        
        if employee_id:
            try:
                employee = Employee.objects.get(id=employee_id)
                active_contract = employee.contracts.filter(status='active').first()
                if active_contract and active_contract.basic_salary:
                    calculated_amount = float(template.get_calculated_amount(active_contract.basic_salary))
            except Employee.DoesNotExist:
                pass
        
        return JsonResponse({
            'success': True,
            'template': {
                'id': template.id,
                'name': template.name,
                'component_type': template.component_type,
                'component_type_display': template.get_component_type_display(),
                'default_amount': float(template.default_amount),
                'calculated_amount': calculated_amount,
                'formula': template.formula,
                'description': template.description,
                'code': template.code,
                'default_account_code': template.default_account_code
            }
        })
        
    except SalaryComponentTemplate.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'القالب غير موجود'}, status=404)


@login_required
@require_http_methods(["POST"])
def get_form_preview(request):
    """إنشاء معاينة للبند قبل الحفظ"""
    employee_id = request.POST.get('employee_id')
    
    if not employee_id:
        return JsonResponse({'success': False, 'message': 'معرف الموظف مطلوب'}, status=400)
    
    try:
        employee = get_object_or_404(Employee, pk=employee_id)
        active_contract = employee.contracts.filter(status='active').first()
        
        # إنشاء نموذج مؤقت للمعاينة
        form = UnifiedSalaryComponentForm(
            request.POST,
            employee=employee,
            contract=active_contract
        )
        
        # الحصول على بيانات المعاينة
        preview_data = form.get_preview_data()
        
        # حساب التأثير على الراتب
        current_salary = 0
        salary_change = 0
        current_earnings = 0
        current_deductions = 0
        
        if active_contract:
            current_salary = float(active_contract.basic_salary or 0)
            
            # حساب إجمالي المستحقات والاستقطاعات الحالية
            from django.db import models
            current_earnings = employee.salary_components.filter(
                component_type='earning'
            ).aggregate(total=models.Sum('amount'))['total'] or 0
            
            current_deductions = employee.salary_components.filter(
                component_type='deduction'
            ).aggregate(total=models.Sum('amount'))['total'] or 0
            
            current_salary = float(current_salary) + float(current_earnings) - float(current_deductions)
        
        # حساب التغيير من البند الجديد
        if preview_data.get('amount') and isinstance(preview_data['amount'], (int, float)):
            amount = float(preview_data['amount'])
            component_type_display = preview_data.get('component_type', '')
            
            # التحقق من نوع البند بالنص المعروض
            if 'مستحق' in component_type_display or 'بدل' in component_type_display or 'حافز' in component_type_display:
                salary_change = amount  # إضافة للراتب
            elif 'استقطاع' in component_type_display or 'خصم' in component_type_display:
                salary_change = -amount  # خصم من الراتب
            else:
                # التحقق من القالب إذا كان متاحاً
                template_id = form.data.get('template')
                if template_id:
                    try:
                        template = SalaryComponentTemplate.objects.get(id=template_id)
                        if template.component_type == 'earning':
                            salary_change = amount
                        else:
                            salary_change = -amount
                    except SalaryComponentTemplate.DoesNotExist:
                        salary_change = amount  # افتراضي: مستحق
                else:
                    salary_change = amount  # افتراضي: مستحق
        
        new_salary = current_salary + salary_change
        
        return JsonResponse({
            'success': True,
            'preview': preview_data,
            'salary_impact': {
                'current_salary': current_salary,
                'salary_change': salary_change,
                'new_salary': new_salary
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ في إنشاء المعاينة: {str(e)}'
        }, status=500)


@login_required
@require_http_methods(["POST"])
def validate_component_name(request):
    """التحقق من عدم تكرار اسم البند للموظف"""
    employee_id = request.POST.get('employee_id')
    component_name = request.POST.get('component_name')
    component_id = request.POST.get('component_id')  # للتعديل
    
    if not employee_id or not component_name:
        return JsonResponse({'success': False, 'message': 'البيانات المطلوبة مفقودة'}, status=400)
    
    try:
        employee = get_object_or_404(Employee, pk=employee_id)
        
        # البحث عن بند بنفس الاسم
        query = employee.salary_components.filter(name__iexact=component_name)
        
        # استبعاد البند الحالي في حالة التعديل
        if component_id:
            query = query.exclude(id=component_id)
        
        exists = query.exists()
        
        return JsonResponse({
            'success': True,
            'exists': exists,
            'message': 'يوجد بند بنفس الاسم بالفعل' if exists else 'الاسم متاح'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ في التحقق: {str(e)}'
        }, status=500)


# ==================== النظام القديم (للتوافق) ====================

@login_required
def salary_component_create(request, employee_id):
    """إنشاء بند راتب جديد - إعادة توجيه للنظام الموحد"""
    return UnifiedSalaryComponentView.as_view()(request, employee_id)


@login_required
def salary_component_edit(request, employee_id, component_id):
    """تعديل بند راتب - إعادة توجيه للنظام الموحد"""
    return UnifiedSalaryComponentView.as_view()(request, employee_id, component_id)


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
        from django.db.models import ProtectedError
        
        component_name = component.name
        
        try:
            # فحص إذا كان البند مستخدم في PayrollLines
            payroll_lines_count = component.payrollline_set.count()
            
            if payroll_lines_count > 0:
                # بدلاً من الحذف، إلغاء التفعيل
                component.is_active = False
                component.save()
                
                message = f'تم إلغاء تفعيل بند "{component_name}" لأنه مستخدم في {payroll_lines_count} قسيمة راتب. لا يمكن حذفه نهائياً.'
                messages.warning(request, message)
                
                # AJAX response
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'action': 'deactivated'
                    })
            else:
                # حذف البند إذا لم يكن مستخدم
                component.delete()
                
                message = f'تم حذف بند "{component_name}" بنجاح'
                messages.success(request, message)
                
                # AJAX response
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'action': 'deleted'
                    })
        
        except ProtectedError as e:
            # معالجة خطأ الحماية
            message = f'لا يمكن حذف بند "{component_name}" لأنه مستخدم في قسائم رواتب. تم إلغاء تفعيله بدلاً من ذلك.'
            
            # إلغاء التفعيل بدلاً من الحذف
            component.is_active = False
            component.save()
            
            messages.warning(request, message)
            
            # AJAX response
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': message,
                    'action': 'deactivated'
                })
        
        except Exception as e:
            error_message = f'حدث خطأ أثناء حذف البند: {str(e)}'
            messages.error(request, error_message)
            
            # AJAX response
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': error_message
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


# تم حذف salary_component_quick_add - يستخدم النظام الموحد الآن




@login_required
def salary_component_classify(request, employee_id):
    """تصنيف بنود الراتب تلقائياً"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'طريقة غير مسموحة'}, status=405)
    
    employee = get_object_or_404(Employee, pk=employee_id)
    
    try:
        updated_count = ComponentClassificationService.classify_all_existing_components()
        
        return JsonResponse({
            'success': True,
            'message': f'تم تصنيف {updated_count} بند بنجاح',
            'updated_count': updated_count
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ أثناء التصنيف: {str(e)}'
        }, status=500)


@login_required
def salary_component_renew(request, employee_id, component_id):
    """تجديد بند راتب"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'طريقة غير مسموحة'}, status=405)
    
    employee = get_object_or_404(Employee, pk=employee_id)
    component = get_object_or_404(
        SalaryComponent,
        pk=component_id,
        employee=employee
    )
    
    try:
        success, message = ComponentClassificationService.renew_component(component)
        
        return JsonResponse({
            'success': success,
            'message': message
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ أثناء التجديد: {str(e)}'
        }, status=500)


@login_required
def salary_component_bulk_renew(request, employee_id):
    """تجديد جميع البنود القابلة للتجديد"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'طريقة غير مسموحة'}, status=405)
    
    employee = get_object_or_404(Employee, pk=employee_id)
    
    try:
        success_count, errors = ComponentClassificationService.bulk_renew_components()
        
        if errors:
            return JsonResponse({
                'success': False,
                'message': f'تم تجديد {success_count} بند، لكن حدثت أخطاء في {len(errors)} بند',
                'errors': errors,
                'success_count': success_count
            })
        else:
            return JsonResponse({
                'success': True,
                'message': f'تم تجديد {success_count} بند بنجاح',
                'success_count': success_count
            })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ أثناء التجديد الجماعي: {str(e)}'
        }, status=500)
