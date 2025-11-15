"""
Views موحدة للعقود مع النظام الذكي
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from django.db import transaction
from django.urls import reverse

from ..models import Contract, Employee
from ..forms import ContractForm
from ..services.unified_contract_service import UnifiedContractService
from ..services.smart_contract_analyzer import SmartContractAnalyzer
from ..services.unified_salary_component_service import UnifiedSalaryComponentService
from ..decorators import hr_manager_required

import json
import logging

logger = logging.getLogger(__name__)


@login_required
@hr_manager_required
def contract_create_unified(request):
    """إنشاء عقد جديد مع النظام الموحد"""
    
    unified_service = UnifiedContractService()
    
    if request.method == 'POST':
        form = ContractForm(request.POST)
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    # إنشاء العقد مع التحليل
                    result = unified_service.create_contract_with_analysis(
                        employee=form.cleaned_data['employee'],
                        contract_data=form.cleaned_data,
                        user=request.user
                    )
                    
                    contract = result['contract']
                    
                    # التحقق من نوع الطلب
                    action = request.POST.get('action', 'save_draft')
                    
                    if action == 'save_activate':
                        # تفعيل ذكي للعقد
                        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                            # جلب البنود المحددة من المعاينة
                            selected_components = request.POST.get('selected_components')
                            user_selections = None
                            if selected_components:
                                try:
                                    user_selections = json.loads(selected_components)
                                    logger.info(f"البنود المحددة للنقل: {user_selections}")
                                except json.JSONDecodeError:
                                    logger.warning("خطأ في تحليل البنود المحددة")
                            
                            # طلب AJAX للتفعيل الذكي
                            activation_result = unified_service.smart_activate_contract(
                                contract, user_selections=user_selections, user=request.user
                            )
                            
                            return JsonResponse({
                                'success': True,
                                'contract_id': contract.id,
                                'summary': activation_result['summary']['message'],
                                'redirect_url': reverse('hr:contract_detail', args=[contract.id])
                            })
                        else:
                            # تفعيل عادي
                            try:
                                activation_result = unified_service.smart_activate_contract(
                                    contract, user_selections=None, user=request.user
                                )
                                messages.success(
                                    request, 
                                    f"تم إنشاء وتفعيل العقد بنجاح. {activation_result['summary']['message']}"
                                )
                            except Exception as e:
                                messages.warning(
                                    request,
                                    f"تم إنشاء العقد ولكن حدث خطأ في التفعيل: {str(e)}"
                                )
                    else:
                        # حفظ كمسودة فقط
                        messages.success(request, 'تم إنشاء العقد كمسودة بنجاح')
                    
                    # إرجاع JSON للطلبات AJAX
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'success': True,
                            'contract_id': contract.id,
                            'redirect_url': reverse('hr:contract_detail', args=[contract.id])
                        })
                    
                    return redirect('hr:contract_detail', pk=contract.id)
                    
            except Exception as e:
                logger.error(f"خطأ في إنشاء العقد: {str(e)}")
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'message': str(e)
                    }, status=400)
                
                messages.error(request, f'حدث خطأ في إنشاء العقد: {str(e)}')
        else:
            # أخطاء النموذج
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'errors': form.errors,
                    'message': 'يرجى تصحيح الأخطاء في النموذج'
                }, status=400)
    else:
        form = ContractForm()
        
        # إذا كان هناك موظف محدد مسبقاً
        employee_id = request.GET.get('employee')
        if employee_id:
            try:
                employee = Employee.objects.get(id=employee_id)
                form.fields['employee'].initial = employee
            except Employee.DoesNotExist:
                pass
    
    context = {
        'form': form,
        'title': 'إضافة عقد جديد',
        'page_title': 'إضافة عقد جديد',
        'is_create': True,
    }
    
    return render(request, 'hr/contract/form.html', context)


@login_required
@hr_manager_required
def contract_edit_unified(request, pk):
    """تعديل عقد موجود"""
    
    contract = get_object_or_404(Contract, pk=pk)
    
    if request.method == 'POST':
        # تسجيل معلومات الطلب للتشخيص
        logger.info(f"طلب تعديل العقد - AJAX: {request.headers.get('X-Requested-With')}")
        logger.info(f"Action: {request.POST.get('action')}")
        logger.info(f"Selected components: {request.POST.get('selected_components')}")
        
        form = ContractForm(request.POST, instance=contract)
        
        if form.is_valid():
            try:
                contract = form.save()
                
                # التحقق من نوع الطلب
                action = request.POST.get('action', 'save_draft')
                
                if action == 'save_activate':
                    # تفعيل العقد
                    unified_service = UnifiedContractService()
                    
                    # جلب البنود المحددة من المعاينة
                    selected_components = request.POST.get('selected_components')
                    user_selections = None
                    if selected_components:
                        try:
                            user_selections = json.loads(selected_components)
                            logger.info(f"البنود المحددة للنقل: {user_selections}")
                        except json.JSONDecodeError:
                            logger.warning("خطأ في تحليل البنود المحددة")
                    
                    # تفعيل العقد
                    activation_result = unified_service.smart_activate_contract(
                        contract, user_selections=user_selections, user=request.user
                    )
                    
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'success': True,
                            'contract_id': contract.id,
                            'summary': activation_result['summary']['message'],
                            'redirect_url': reverse('hr:contract_detail', args=[contract.id])
                        })
                    else:
                        messages.success(request, f'تم تحديث وتفعيل العقد بنجاح. {activation_result["summary"]["message"]}')
                else:
                    # حفظ عادي
                    messages.success(request, 'تم تحديث العقد بنجاح')
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True,
                        'contract_id': contract.id,
                        'redirect_url': reverse('hr:contract_detail', args=[contract.id])
                    })
                
                return redirect('hr:contract_detail', pk=contract.id)
                
            except Exception as e:
                logger.error(f"خطأ في تحديث العقد: {str(e)}")
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'message': str(e)
                    }, status=400)
                
                messages.error(request, f'حدث خطأ في تحديث العقد: {str(e)}')
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'errors': form.errors
                }, status=400)
    else:
        form = ContractForm(instance=contract)
    
    context = {
        'form': form,
        'contract': contract,
        'title': f'تعديل العقد - {contract.employee.name}',
        'page_title': f'تعديل العقد - {contract.employee.name}',
        'is_edit': True,
    }
    
    return render(request, 'hr/contract/form.html', context)


@method_decorator([login_required, hr_manager_required], name='dispatch')
class SmartContractActivationView(View):
    """تفعيل ذكي للعقد"""
    
    def __init__(self):
        super().__init__()
        self.unified_service = UnifiedContractService()
    
    def post(self, request, contract_id):
        """تفعيل العقد بذكاء"""
        
        try:
            contract = get_object_or_404(Contract, id=contract_id)
            
            # التحقق من حالة العقد
            if contract.status != 'draft':
                return JsonResponse({
                    'success': False,
                    'message': 'يمكن تفعيل العقود المسودة فقط'
                }, status=400)
            
            # جلب اختيارات المستخدم (إن وجدت)
            user_selections = None
            if request.content_type == 'application/json':
                data = json.loads(request.body)
                user_selections = data.get('user_selections')
            
            # تفعيل العقد
            result = self.unified_service.smart_activate_contract(
                contract, user_selections, request.user
            )
            
            return JsonResponse({
                'success': True,
                'contract': {
                    'id': contract.id,
                    'status': contract.status,
                    'activation_date': contract.activation_date.isoformat() if contract.activation_date else None
                },
                'summary': result['summary']['message'],
                'transfer_results': {
                    'transferred_count': len(result['transfer_results']['transferred']),
                    'archived_count': len(result['transfer_results']['archived']),
                    'errors_count': len(result['transfer_results']['errors'])
                },
                'redirect_url': reverse('hr:contract_detail', args=[contract.id])
            })
            
        except Exception as e:
            logger.error(f"خطأ في تفعيل العقد {contract_id}: {str(e)}")
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=500)


@method_decorator([login_required, hr_manager_required], name='dispatch')
class ContractActivationPreviewView(View):
    """معاينة تفعيل العقد"""
    
    def __init__(self):
        super().__init__()
        self.unified_service = UnifiedContractService()
    
    def post(self, request, contract_id=None):
        """معاينة تفعيل العقد"""
        
        try:
            if contract_id:
                # معاينة عقد موجود
                contract = get_object_or_404(Contract, id=contract_id)
            else:
                # معاينة عقد جديد من النموذج
                form_data = request.POST
                
                # إنشاء عقد مؤقت للمعاينة
                employee = get_object_or_404(Employee, id=form_data.get('employee'))
                
                # إنشاء كائن عقد مؤقت (بدون حفظ)
                from decimal import Decimal, InvalidOperation
                from datetime import datetime
                
                # تحويل البيانات إلى الأنواع الصحيحة مع معالجة الأخطاء
                try:
                    basic_salary_str = form_data.get('basic_salary', '0').strip()
                    if not basic_salary_str or basic_salary_str == '':
                        basic_salary_str = '0'
                    basic_salary = Decimal(basic_salary_str)
                except (ValueError, TypeError, InvalidOperation):
                    basic_salary = Decimal('0')
                
                try:
                    start_date_str = form_data.get('start_date')
                    if start_date_str:
                        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                    else:
                        start_date = None
                except (ValueError, TypeError):
                    start_date = None
                
                try:
                    job_title_str = form_data.get('job_title')
                    job_title_id = int(job_title_str) if job_title_str else None
                except (ValueError, TypeError):
                    job_title_id = None
                
                try:
                    department_str = form_data.get('department')
                    department_id = int(department_str) if department_str else None
                except (ValueError, TypeError):
                    department_id = None
                
                contract = Contract(
                    employee=employee,
                    basic_salary=basic_salary,
                    start_date=start_date,
                    job_title_id=job_title_id,
                    department_id=department_id
                )
            
            # جلب اختيارات المستخدم
            user_selections = None
            if request.content_type == 'application/json':
                data = json.loads(request.body)
                user_selections = data.get('user_selections')
            
            # معاينة التفعيل
            preview = self.unified_service.preview_contract_activation(
                contract, user_selections
            )
            
            # تسلسل البيانات للـ JSON
            from ..views.admin_maintenance_views import _serialize_analysis_data
            
            serialized_preview = {
                'total_components': preview['transfer_preview']['total_components'],
                'auto_transfer_count': preview['transfer_preview']['auto_transfer_count'],
                'manual_review_count': preview['transfer_preview']['manual_review_count'],
                'estimated_impact': _serialize_analysis_data(preview['estimated_impact'])
            }
            
            # معالجة التوصيات كقائمة
            recommendations = preview['analysis']['recommendations'][:3]
            serialized_recommendations = []
            for rec in recommendations:
                if isinstance(rec, dict):
                    serialized_recommendations.append(_serialize_analysis_data(rec))
                else:
                    serialized_recommendations.append(rec)
            
            serialized_analysis = {
                'financial_impact': _serialize_analysis_data(preview['analysis']['financial_impact']),
                'recommendations': serialized_recommendations
            }
            
            return JsonResponse({
                'success': True,
                'preview': serialized_preview,
                'analysis': serialized_analysis
            })
            
        except Exception as e:
            logger.error(f"خطأ في معاينة تفعيل العقد: {str(e)}")
            return JsonResponse({
                'success': False,
                'message': f'حدث خطأ في المعاينة: {str(e)}'
            }, status=500)


@login_required
@hr_manager_required
def contract_preview_components(request, contract_id):
    """معاينة بنود العقد للنسخ (النهج الجديد)"""
    
    contract = get_object_or_404(Contract, pk=contract_id)
    
    if request.method == 'GET':
        try:
            # استخدام الخدمة الموحدة الجديدة
            salary_service = UnifiedSalaryComponentService()
            
            # الحصول على معاينة البنود
            preview_data = salary_service.preview_contract_components(contract)
            
            return JsonResponse({
                'success': True,
                'preview': preview_data
            })
            
        except Exception as e:
            logger.error(f"خطأ في معاينة بنود العقد: {str(e)}")
            return JsonResponse({
                'success': False,
                'message': f'حدث خطأ في المعاينة: {str(e)}'
            }, status=500)
    
    return JsonResponse({
        'success': False,
        'message': 'طريقة طلب غير مدعومة'
    }, status=405)


@login_required
@hr_manager_required
def contract_apply_component_selection(request, contract_id):
    """تطبيق اختيار البنود من المعاينة (النهج الجديد)"""
    
    contract = get_object_or_404(Contract, pk=contract_id)
    
    if request.method == 'POST':
        try:
            # جلب البنود المحددة
            selected_components = request.POST.get('selected_components', '[]')
            selected_ids = json.loads(selected_components)
            
            # استخدام الخدمة الموحدة
            salary_service = UnifiedSalaryComponentService()
            
            # تطبيق الاختيار
            copied_components = salary_service.apply_preview_selection(
                contract=contract,
                selected_component_ids=selected_ids
            )
            
            return JsonResponse({
                'success': True,
                'message': f'تم نسخ {len(copied_components)} بند بنجاح',
                'copied_count': len(copied_components)
            })
            
        except Exception as e:
            logger.error(f"خطأ في تطبيق اختيار البنود: {str(e)}")
            return JsonResponse({
                'success': False,
                'message': f'حدث خطأ في التطبيق: {str(e)}'
            }, status=500)
    
    return JsonResponse({
        'success': False,
        'message': 'طريقة طلب غير مدعومة'
    }, status=405)


@login_required
@require_http_methods(["POST"])
def contract_optimize_components(request, employee_id):
    """تحسين بنود الموظف تلقائياً"""
    
    try:
        employee = get_object_or_404(Employee, id=employee_id)
        unified_service = UnifiedContractService()
        
        # تحسين البنود
        result = unified_service.optimize_employee_components(
            employee, 
            optimization_options={'execute': True}
        )
        
        return JsonResponse({
            'success': True,
            'results': {
                'cleaned_count': len(result['results']['cleaned']),
                'reclassified_count': len(result['results']['reclassified']),
                'errors_count': len(result['results']['errors'])
            },
            'message': 'تم تحسين البنود بنجاح'
        })
        
    except Exception as e:
        logger.error(f"خطأ في تحسين بنود الموظف {employee_id}: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)


# دمج النظام المحسن مع النظام الأساسي
@login_required
def contract_components_unified(request, employee_id):
    """صفحة بنود الراتب الموحدة"""
    
    employee = get_object_or_404(Employee, id=employee_id)
    unified_service = UnifiedContractService()
    
    # تحليل شامل للموظف
    analysis = unified_service.get_employee_component_analysis(employee)
    
    context = {
        'employee': employee,
        'analysis': analysis,
        'basic_analysis': analysis['basic_analysis'],
        'pattern_analysis': analysis['pattern_analysis'],
        'renewal_analysis': analysis['renewal_analysis'],
        'health_assessment': analysis['overall_health'],
        'title': f'بنود راتب {employee.name}',
        'page_title': f'بنود راتب {employee.name}',
    }
    
    # استخدام نفس template النظام المحسن
    return render(request, 'hr/employee/salary_components_enhanced.html', context)
