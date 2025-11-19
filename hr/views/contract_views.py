"""
Views إدارة العقود - النظام الموحد
دمج: contract_views.py + contract_form_views.py + contract_unified_views.py
"""
from .base_imports import *
from ..models import Contract, Employee, Department, SalaryComponent, ContractSalaryComponent
from ..models.contract import ContractDocument, ContractAmendment, ContractIncrease
from ..decorators import can_manage_contracts, hr_manager_required
from ..services.unified_contract_service import UnifiedContractService
from ..services.unified_salary_component_service import UnifiedSalaryComponentService
from ..services.smart_contract_analyzer import SmartContractAnalyzer
from ..forms.contract_forms import ContractForm
from core.models import SystemSetting
from core.utils import get_default_currency
from django.core.paginator import Paginator
from datetime import date, timedelta
from django.views.decorators.http import require_POST, require_http_methods
from django.http import JsonResponse
from ..models import SalaryComponentTemplate, BiometricUserMapping
from django.views import View
from django.utils.decorators import method_decorator
from django.db import transaction
from decimal import Decimal
import json
import logging

logger = logging.getLogger(__name__)

__all__ = [
    # CRUD Operations
    'contract_list',
    'contract_detail',
    'contract_form',
    
    # Activation & Preview
    'contract_activate',
    'contract_activation_preview',
    'contract_activate_with_components',
    'contract_smart_activate',
    
    # Component Management
    'contract_preview_components',
    'contract_apply_component_selection',
    'contract_optimize_components',
    'contract_components_unified',
    'sync_component',
    'sync_contract_components',
    
    # Lifecycle Management
    'contract_renew',
    'contract_terminate',
    'contract_expiring',
    
    # Documents & Amendments
    'contract_document_upload',
    'contract_document_delete',
    'contract_amendment_create',
    
    # Scheduled Increases
    'contract_create_increase_schedule',
    'contract_increase_action',
    'contract_increase_apply',
    'contract_increase_cancel',
    
    # API Helpers
    'get_salary_component_templates',
]


@login_required
@hr_manager_required
def contract_list(request):
    """قائمة العقود"""
    # Query Optimization - تقليل عدد الـ queries
    contracts = Contract.objects.select_related(
        'employee',
        'employee__department',
        'employee__job_title',
        'job_title',
        'department'
    ).prefetch_related(
        'scheduled_increases',
        'amendments'
    ).order_by('-created_at')  # ✅ ترتيب بالأحدث أولاً
    
    # إحصائيات
    stats = {
        'total': contracts.count(),
        'active': contracts.filter(status='active').count(),
        'draft': contracts.filter(status='draft').count(),
        'suspended': contracts.filter(status='suspended').count(),
        'expiring_soon': contracts.filter(
            status='active',
            end_date__isnull=False,
            end_date__lte=date.today() + timedelta(days=30)
        ).count(),
    }
    
    # تعريف رؤوس الجدول
    headers = [
        {'key': 'contract_number', 'label': 'رقم العقد', 'sortable': True, 'class': 'text-center'},
        {'key': 'employee', 'label': 'الموظف', 'sortable': True, 'template': 'hr/contract/cells/employee.html'},
        {'key': 'contract_type', 'label': 'نوع العقد', 'sortable': True, 'template': 'hr/contract/cells/contract_type.html', 'class': 'text-center'},
        {'key': 'start_date', 'label': 'تاريخ البداية', 'sortable': True, 'format': 'date', 'class': 'text-center'},
        {'key': 'end_date', 'label': 'تاريخ النهاية', 'sortable': True, 'template': 'hr/contract/cells/end_date.html', 'class': 'text-center'},
        {'key': 'basic_salary', 'label': 'الراتب الأساسي', 'sortable': True, 'format': 'currency', 'class': 'text-center'},
        {'key': 'status', 'label': 'الحالة', 'sortable': True, 'template': 'hr/contract/cells/status.html', 'class': 'text-center'},
    ]
    
    # أزرار الإجراءات
    action_buttons = [
        {'url': 'hr:contract_detail', 'icon': 'fa-eye', 'label': 'عرض', 'class': 'action-view'},
        {'url': 'hr:contract_form_edit', 'icon': 'fa-edit', 'label': 'تعديل', 'class': 'action-edit'},
    ]
    
    # Pagination - 30 عقد لكل صفحة
    paginator = Paginator(contracts, 30)
    page = request.GET.get('page', 1)
    contracts_page = paginator.get_page(page)
    
    context = {
        'headers': headers,
        'data': contracts_page,
        'action_buttons': action_buttons,
        'table_id': 'contracts-table',
        'primary_key': 'pk',
        'empty_message': 'لا توجد عقود',
        'currency_symbol': 'جنيه',
        'clickable_rows': True,
        'row_click_url': '/hr/contracts/0/',
        **{f'{k}_contracts': v for k, v in stats.items()},
        'show_stats': True,
        'employees': Employee.objects.filter(status='active'),
        
        # بيانات الهيدر
        'page_title': 'العقود',
        'page_subtitle': 'إدارة عقود الموظفين والتجديدات',
        'page_icon': 'fas fa-file-contract',
        
        # أزرار الهيدر
        'header_buttons': [
            {
                'url': reverse('hr:contract_form'),
                'icon': 'fa-plus',
                'text': 'إضافة عقد',
                'class': 'btn-primary',
            },
        ],
        
        # البريدكرمب
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users-cog'},
            {'title': 'العقود', 'active': True},
        ],
    }
    
    return render(request, 'hr/contract/list.html', context)


@login_required
def contract_detail(request, pk):
    """تفاصيل العقد"""
    contract = get_object_or_404(Contract, pk=pk)
    
    # جلب رمز العملة
    try:
        currency_symbol = SystemSetting.get_currency_symbol()
    except:
        currency_symbol = 'جنيه'
    
    # جلب الزيادات المجدولة
    scheduled_increases = contract.scheduled_increases.all().order_by('increase_number')
    pending_increases = scheduled_increases.filter(status='pending')
    applied_increases = scheduled_increases.filter(status='applied')
    
    # تصنيف بنود الراتب (حل مشكلة التكرار)
    employee_components = contract.employee.salary_components.filter(
        is_active=True
    ).select_related('source_contract_component').order_by('order')
    
    # تصنيف البنود لمنع التكرار
    contract_synced_components = []
    manual_components = []
    
    for component in employee_components:
        if component.is_from_contract and component.contract == contract:
            # بند منسوخ من هذا العقد
            contract_synced_components.append({
                'component': component,
                'source': component.source_contract_component,
                'is_synced': (
                    component.source_contract_component and 
                    component.amount == component.source_contract_component.amount
                )
            })
        elif not component.is_from_contract:
            # بند يدوي
            manual_components.append(component)
    
    # تعريف رؤوس جدول المرفقات
    documents_headers = [
        {'key': 'file', 'label': '', 'template': 'hr/contract/cells/document_icon.html', 'class': 'text-center', 'width': '40', 'searchable': False},
        {'key': 'document_type', 'label': 'النوع', 'template': 'hr/contract/cells/document_type.html', 'searchable': True},
        {'key': 'title', 'label': 'العنوان', 'template': 'hr/contract/cells/document_title.html', 'searchable': True},
        {'key': 'file_size_mb', 'label': 'الحجم', 'template': 'hr/contract/cells/document_size.html', 'class': 'text-center', 'searchable': False},
        {'key': 'uploaded_at', 'label': 'تاريخ الرفع', 'template': 'hr/contract/cells/document_date.html', 'class': 'text-center', 'searchable': True},
        {'key': 'uploaded_by', 'label': 'رفع بواسطة', 'template': 'hr/contract/cells/document_uploader.html', 'searchable': True},
        {'key': 'actions', 'label': 'إجراءات', 'template': 'hr/contract/cells/document_actions.html', 'class': 'text-center', 'width': '100', 'searchable': False},
    ]
    
    # تحديد حالة العقد كـ badge
    status_badge = {
        'draft': {'text': 'مسودة', 'class': 'bg-secondary', 'icon': 'fa-file'},
        'active': {'text': 'نشط', 'class': 'bg-success', 'icon': 'fa-check-circle'},
        'suspended': {'text': 'موقوف', 'class': 'bg-warning', 'icon': 'fa-pause-circle'},
        'terminated': {'text': 'منتهي', 'class': 'bg-danger', 'icon': 'fa-times-circle'},
        'renewed': {'text': 'مجدد', 'class': 'bg-info', 'icon': 'fa-redo'},
    }.get(contract.status, {'text': contract.get_status_display(), 'class': 'bg-secondary', 'icon': 'fa-circle'})
    
    # تحديد الأزرار حسب حالة العقد
    header_buttons = [
        {
            'text': status_badge['text'],
            'icon': status_badge['icon'],
            'class': status_badge['class'],
            'is_badge': True,
        },
        {
            'url': f'/hr/contracts/{contract.pk}/form/',
            'icon': 'fa-edit',
            'text': 'تعديل',
            'class': 'btn-warning',
        },
    ]
    
    # أزرار حسب الحالة
    if contract.status == 'draft':
        # عقد مسودة - يمكن تفعيله
        header_buttons.append({
            'url': f'/hr/contracts/{contract.pk}/activate/',
            'icon': 'fa-check-circle',
            'text': 'تفعيل العقد',
            'class': 'btn-success',
        })
    elif contract.status == 'active':
        # عقد نشط - يمكن إيقافه أو إنهاؤه أو تجديده
        # TODO: إضافة وظيفة إيقاف العقد
        # header_buttons.append({
        #     'url': f'/hr/contracts/{contract.pk}/suspend/',
        #     'icon': 'fa-pause-circle',
        #     'text': 'إيقاف العقد',
        #     'class': 'btn-warning',
        # })
        if contract.end_date:
            header_buttons.append({
                'url': f'/hr/contracts/{contract.pk}/renew/',
                'icon': 'fa-redo',
                'text': 'تجديد',
                'class': 'btn-info',
            })
        header_buttons.append({
            'url': f'/hr/contracts/{contract.pk}/terminate/',
            'icon': 'fa-ban',
            'text': 'إنهاء',
            'class': 'btn-danger',
        })
    elif contract.status == 'suspended':
        # عقد موقوف - يمكن إعادة تفعيله أو تجديده
        header_buttons.extend([
            {
                'url': f'/hr/contracts/{contract.pk}/activate/',
                'icon': 'fa-play-circle',
                'text': 'إعادة تفعيل',
                'class': 'btn-success',
            },
            {
                'url': f'/hr/contracts/{contract.pk}/renew/',
                'icon': 'fa-redo',
                'text': 'تجديد',
                'class': 'btn-info',
            },
        ])
    elif contract.status in ['expired', 'terminated']:
        # عقد منتهي - يمكن تجديده فقط
        header_buttons.append({
            'url': f'/hr/contracts/{contract.pk}/renew/',
            'icon': 'fa-redo',
            'text': 'تجديد',
            'class': 'btn-info',
        })
    
    context = {
        'contract': contract,
        'system_settings': {'currency_symbol': currency_symbol},
        'documents_headers': documents_headers,
        'primary_key': 'id',
        'scheduled_increases': scheduled_increases,
        'pending_increases': pending_increases,
        'applied_increases': applied_increases,
        'contract_synced_components': contract_synced_components,
        'manual_components': manual_components,
        'page_title': f'عقد رقم {contract.contract_number}',
        'page_subtitle': f'{contract.employee.get_full_name_ar()} - {contract.employee.employee_number} • من تاريخ {contract.start_date.strftime("%d/%m/%Y")}' + (f' → {contract.end_date.strftime("%d/%m/%Y")}' if contract.end_date else ''),
        'page_icon': 'fas fa-file-contract',
        'header_buttons': header_buttons,
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': '/dashboard/', 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': '/hr/', 'icon': 'fas fa-users-cog'},
            {'title': 'العقود', 'url': '/hr/contracts/', 'icon': 'fas fa-file-contract'},
            {'title': contract.employee.get_full_name_ar(), 'url': f'/hr/employees/{contract.employee.pk}/', 'icon': 'fas fa-user'},
            {'title': contract.contract_number, 'active': True},
        ],
    }
    
    return render(request, 'hr/contract/detail.html', context)


@login_required
@require_POST
def sync_component(request, pk):
    """مزامنة بند واحد مع مصدره"""
    
    try:
        component = get_object_or_404(SalaryComponent, pk=pk)
        
        if component.source_contract_component:
            source = component.source_contract_component
            component.name = source.name
            component.amount = source.amount
            component.percentage = source.percentage
            component.formula = source.formula
            component.save()
            
            return JsonResponse({
                'success': True, 
                'message': 'تم التزامن بنجاح',
                'new_amount': str(component.amount)
            })
        else:
            return JsonResponse({
                'success': False, 
                'message': 'لا يوجد مصدر للمزامنة'
            })
            
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required
@require_POST
def sync_contract_components(request, pk):
    """مزامنة جميع بنود العقد"""
    
    try:
        contract = get_object_or_404(Contract, pk=pk)
        
        synced_count = 0
        components = contract.employee.salary_components.filter(
            is_from_contract=True, 
            contract=contract,
            is_active=True
        )
        
        for component in components:
            if component.source_contract_component:
                source = component.source_contract_component
                component.name = source.name
                component.amount = source.amount
                component.percentage = source.percentage
                component.formula = source.formula
                component.save()
                synced_count += 1
        
        return JsonResponse({
            'success': True, 
            'message': f'تم تزامن {synced_count} بند بنجاح'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)




@login_required
def contract_document_upload(request, pk):
    """رفع مرفق للعقد"""
    contract = get_object_or_404(Contract, pk=pk)
    
    if request.method == 'POST':
        document_type = request.POST.get('document_type')
        title = request.POST.get('title')
        description = request.POST.get('description', '')
        file = request.FILES.get('file')
        
        if not all([document_type, title, file]):
            messages.error(request, 'يرجى ملء جميع الحقول المطلوبة')
            return redirect('hr:contract_detail', pk=pk)
        
        try:
            document = ContractDocument.objects.create(
                contract=contract,
                document_type=document_type,
                title=title,
                description=description,
                file=file,
                uploaded_by=request.user
            )
            messages.success(request, f'تم رفع المرفق "{title}" بنجاح')
        except Exception as e:
            messages.error(request, f'خطأ في رفع المرفق: {str(e)}')
    
    return redirect('hr:contract_detail', pk=pk)


@login_required
def contract_document_delete(request, pk, doc_id):
    """حذف مرفق من العقد"""
    contract = get_object_or_404(Contract, pk=pk)
    document = get_object_or_404(ContractDocument, pk=doc_id, contract=contract)
    
    if request.method == 'POST':
        title = document.title
        document.delete()
        messages.success(request, f'تم حذف المرفق "{title}" بنجاح')
    
    return redirect('hr:contract_detail', pk=pk)


@login_required
def contract_amendment_create(request, pk):
    """إضافة تعديل على العقد"""
    contract = get_object_or_404(Contract, pk=pk)
    
    if request.method == 'POST':
        try:
            # توليد رقم تعديل تلقائي
            last_amendment = ContractAmendment.objects.filter(
                contract=contract
            ).order_by('-amendment_number').first()
            
            if last_amendment:
                # استخراج الرقم من آخر تعديل
                last_num = int(last_amendment.amendment_number.split('-')[-1])
                amendment_number = f"{contract.contract_number}-AMD-{last_num + 1:03d}"
            else:
                amendment_number = f"{contract.contract_number}-AMD-001"
            
            # إنشاء التعديل
            amendment = ContractAmendment.objects.create(
                contract=contract,
                amendment_number=amendment_number,
                amendment_type=request.POST.get('amendment_type'),
                effective_date=request.POST.get('effective_date'),
                description=request.POST.get('description'),
                old_value=request.POST.get('old_value', ''),
                new_value=request.POST.get('new_value', ''),
                created_by=request.user
            )
            
            messages.success(request, f'تم إضافة التعديل "{amendment.get_amendment_type_display()}" بنجاح')
            
        except Exception as e:
            messages.error(request, f'حدث خطأ أثناء إضافة التعديل: {str(e)}')
    
    return redirect('hr:contract_detail', pk=pk)


# ==================== دوال العقود الإضافية ====================

@login_required
def get_salary_component_templates(request):
    """API لجلب قوالب مكونات الراتب"""
    
    component_type = request.GET.get('type', 'earning')
    
    templates = SalaryComponentTemplate.objects.filter(
        component_type=component_type,
        is_active=True
    ).order_by('order', 'name')
    
    data = [{
        'id': t.id,
        'name': t.name,
        'formula': t.formula,
        'default_amount': str(t.default_amount),
        'description': t.description
    } for t in templates]
    
    return JsonResponse({'success': True, 'templates': data})


@login_required
def contract_renew(request, pk):
    """تجديد العقد - يفتح form كامل للتعديل"""
    old_contract = get_object_or_404(Contract, pk=pk)
    
    if request.method == 'POST':
        form = ContractForm(request.POST)
        
        # إضافة الموظف يدوياً لأن الحقل disabled
        if form.data.get('employee') is None:
            mutable_post = request.POST.copy()
            mutable_post['employee'] = old_contract.employee.id
            form = ContractForm(mutable_post)
        
        if form.is_valid():
            new_contract = form.save(commit=False)
            new_contract.employee = old_contract.employee
            new_contract.created_by = request.user
            new_contract.save()
            
            # تحديث العقد القديم
            old_contract.status = 'renewed'
            old_contract.renewed_to = new_contract
            old_contract.save()
            
            messages.success(request, f'تم تجديد العقد بنجاح. رقم العقد الجديد: {new_contract.contract_number}')
            return redirect('hr:contract_detail', pk=new_contract.pk)
    else:
        # تحديد تاريخ بداية العقد الجديد
        if old_contract.end_date:
            new_start_date = old_contract.end_date + timedelta(days=1)
        else:
            new_start_date = date.today()
        
        # جلب رقم البصمة من BiometricUserMapping
        biometric_mapping = BiometricUserMapping.objects.filter(
            employee=old_contract.employee,
            is_active=True
        ).first()
        biometric_id = biometric_mapping.biometric_user_id if biometric_mapping else None
        
        # إنشاء form مع بيانات العقد القديم
        initial_data = {
            'employee': old_contract.employee,
            'contract_type': old_contract.contract_type,
            'job_title': old_contract.job_title,
            'department': old_contract.department,
            'biometric_user_id': biometric_id,
            'start_date': new_start_date,
            'basic_salary': old_contract.basic_salary,
            'probation_period_months': 0,
            'terms_and_conditions': old_contract.terms_and_conditions,
            'auto_renew': old_contract.auto_renew,
            'renewal_notice_days': old_contract.renewal_notice_days,
            'status': 'active',
            'has_annual_increase': old_contract.has_annual_increase,
            'annual_increase_percentage': old_contract.annual_increase_percentage,
            'increase_frequency': old_contract.increase_frequency,
            'increase_start_reference': old_contract.increase_start_reference,
        }
        form = ContractForm(initial=initial_data)
        
        # تعطيل حقل الموظف
        form.fields['employee'].disabled = True
        form.fields['employee'].widget.attrs['readonly'] = 'readonly'
        form.fields['employee'].widget.attrs['style'] = 'background-color: #e9ecef; pointer-events: none;'
    
    context = {
        'form': form,
        'old_contract': old_contract,
        'is_renewal': True,
        'page_title': f'تجديد العقد: {old_contract.contract_number}',
        'page_subtitle': f'تجديد عقد الموظف {old_contract.employee.get_full_name_ar()}',
        'page_icon': 'fas fa-redo',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users'},
            {'title': 'العقود', 'url': reverse('hr:contract_list'), 'icon': 'fas fa-file-contract'},
            {'title': 'تجديد عقد', 'active': True},
        ],
    }
    return render(request, 'hr/contract/form.html', context)


@login_required
def contract_terminate(request, pk):
    """إنهاء العقد"""
    contract = get_object_or_404(Contract, pk=pk)
    if request.method == 'POST':
        termination_date = request.POST.get('termination_date')
        contract.terminate(termination_date)
        messages.success(request, 'تم إنهاء العقد بنجاح')
        return redirect('hr:contract_detail', pk=pk)
    
    context = {
        'contract': contract,
        
        # بيانات الهيدر الموحد
        'page_title': f'إنهاء العقد: {contract.contract_number}',
        'page_subtitle': 'إنهاء عقد الموظف',
        'page_icon': 'fas fa-ban',
        'header_buttons': [
            {
                'url': reverse('hr:contract_list'),
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users-cog'},
            {'title': 'العقود', 'url': reverse('hr:contract_list'), 'icon': 'fas fa-file-contract'},
            {'title': 'إنهاء عقد', 'active': True},
        ],
    }
    return render(request, 'hr/contract/terminate.html', context)


@login_required
def contract_create_increase_schedule(request, pk):
    """إنشاء جدول زيادات مجدولة للعقد"""
    contract = get_object_or_404(Contract, pk=pk)
    
    if request.method == 'POST':
        try:
            annual_percentage = float(request.POST.get('annual_percentage'))
            installments = int(request.POST.get('installments'))
            interval_months = int(request.POST.get('interval_months'))
            
            increases = contract.create_increase_schedule(
                annual_percentage=annual_percentage,
                installments=installments,
                interval_months=interval_months,
                created_by=request.user
            )
            
            messages.success(request, f'تم إنشاء جدول الزيادات بنجاح ({len(increases)} زيادة مجدولة)')
        except Exception as e:
            messages.error(request, f'حدث خطأ: {str(e)}')
    
    return redirect('hr:contract_detail', pk=pk)


@login_required
@require_http_methods(["POST"])
def contract_increase_action(request, increase_id, action):
    """دالة موحدة لإجراءات الزيادات (تطبيق/إلغاء)"""
    
    increase = get_object_or_404(ContractIncrease, pk=increase_id)
    
    if action == 'apply':
        success, message = increase.apply_increase(applied_by=request.user)
    elif action == 'cancel':
        success, message = increase.cancel_increase()
    else:
        return JsonResponse({
            'success': False,
            'message': 'إجراء غير صحيح'
        }, status=400)
    
    return JsonResponse({
        'success': success,
        'message': message
    })


@login_required
@require_http_methods(["POST"])
def contract_increase_apply(request, increase_id):
    """تطبيق زيادة مجدولة"""
    return contract_increase_action(request, increase_id, 'apply')


@login_required
@require_http_methods(["POST"])
def contract_increase_cancel(request, increase_id):
    """إلغاء زيادة مجدولة"""
    return contract_increase_action(request, increase_id, 'cancel')


@login_required
def contract_expiring(request):
    """العقود قرب الانتهاء"""
    expiry_date = date.today() + timedelta(days=60)
    contracts = Contract.objects.filter(
        status='active',
        end_date__lte=expiry_date,
        end_date__gte=date.today()
    ).select_related('employee').order_by('end_date')
    
    context = {
        'contracts': contracts,
        
        # بيانات الهيدر الموحد
        'page_title': 'عقود قرب الانتهاء',
        'page_subtitle': 'العقود التي ستنتهي خلال 60 يوم',
        'page_icon': 'fas fa-exclamation-triangle',
        'header_buttons': [
            {
                'url': reverse('hr:contract_list'),
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users-cog'},
            {'title': 'العقود', 'url': reverse('hr:contract_list'), 'icon': 'fas fa-file-contract'},
            {'title': 'قرب الانتهاء', 'active': True},
        ],
    }
    return render(request, 'hr/contract/expiring.html', context)


@login_required
@hr_manager_required
def contract_activate(request, pk):
    """
    تفعيل العقد ونسخ البنود تلقائياً
    
    يستخدم UnifiedContractService لـ:
    - تعطيل العقد القديم (إن وجد)
    - تفعيل العقد الجديد
    - نسخ جميع البنود من ContractSalaryComponent إلى SalaryComponent
    - ربط البصمة
    - تحديث بيانات الموظف
    """
    contract = get_object_or_404(Contract, pk=pk)
    
    # التحقق من أن العقد في حالة مسودة
    if contract.status != 'draft':
        messages.warning(request, 'العقد مفعّل بالفعل أو في حالة أخرى')
        return redirect('hr:contract_detail', pk=pk)
    
    if request.method == 'POST':
        try:
            # استخدام UnifiedContractService
            unified_service = UnifiedContractService()
            result = unified_service.smart_activate_contract(
                contract=contract,
                user_selections=None,
                user=request.user
            )
            
            if result['success']:
                messages.success(request, result['summary']['message'])
                return redirect('hr:contract_detail', pk=pk)
            else:
                messages.error(request, 'فشل في تفعيل العقد')
        except Exception as e:
            messages.error(request, f'حدث خطأ أثناء تفعيل العقد: {str(e)}')
    
    # عرض صفحة التأكيد
    components_count = contract.salary_components.count()
    
    context = {
        'contract': contract,
        'components_count': components_count,
        'earnings_count': contract.salary_components.filter(component_type='earning').count(),
        'deductions_count': contract.salary_components.filter(component_type='deduction').count(),
        'page_title': f'تفعيل العقد: {contract.contract_number}',
        'page_subtitle': f'الموظف: {contract.employee.get_full_name_ar()}',
        'page_icon': 'fas fa-check-circle',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users-cog'},
            {'title': 'العقود', 'url': reverse('hr:contract_list'), 'icon': 'fas fa-file-contract'},
            {'title': contract.contract_number, 'url': reverse('hr:contract_detail', args=[pk]), 'icon': 'fas fa-file-contract'},
            {'title': 'تفعيل', 'active': True},
        ],
    }
    return render(request, 'hr/contract/activate_confirm.html', context)


@login_required
@hr_manager_required
def contract_activation_preview(request, pk):
    """معاينة تأثير تفعيل العقد على بنود الموظف - محدثة"""
    contract = get_object_or_404(Contract, pk=pk)
    
    if contract.status != 'draft':
        return JsonResponse({
            'success': False,
            'message': 'العقد مفعّل بالفعل أو في حالة أخرى'
        })
    
    try:
        # استخدام UnifiedContractService للمعاينة
        unified_service = UnifiedContractService()
        preview = unified_service.preview_contract_activation(contract, user_selections=None)
        
        # تسلسل البيانات للـ JSON
        from .admin_maintenance_views import _serialize_analysis_data
        
        serialized_preview = {
            'total_components': preview['transfer_preview']['total_components'],
            'auto_transfer_count': preview['transfer_preview']['auto_transfer_count'],
            'manual_review_count': preview['transfer_preview']['manual_review_count'],
            'estimated_impact': _serialize_analysis_data(preview['estimated_impact'])
        }
        
        return JsonResponse({
            'success': True,
            'preview': serialized_preview
        })
        
    except Exception as e:
        logger.error(f"خطأ في معاينة تفعيل العقد: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ في تحليل العقد: {str(e)}'
        })


@login_required
@hr_manager_required
def contract_activate_with_components(request, pk):
    """تفعيل العقد مع نقل البنود المختارة"""
    contract = get_object_or_404(Contract, pk=pk)
    
    if contract.status != 'draft':
        return JsonResponse({
            'success': False,
            'message': 'العقد مفعّل بالفعل أو في حالة أخرى'
        })
    
    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'message': 'طريقة الطلب غير صحيحة'
        })
    
    try:
        # الحصول على البنود المختارة للنقل
        transfer_components = request.POST.getlist('transfer_components', [])
        transfer_components = [int(id) for id in transfer_components if id.isdigit()]
        
        # تفعيل العقد مع نقل البنود
        success, message, details = ContractActivationService.activate_contract(
            contract=contract,
            activated_by=request.user,
            transfer_components=transfer_components
        )
        
        if success:
            return JsonResponse({
                'success': True,
                'message': message,
                'details': details,
                'redirect_url': reverse('hr:contract_detail', args=[pk])
            })
        else:
            return JsonResponse({
                'success': False,
                'message': message
            })
            
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ أثناء تفعيل العقد: {str(e)}'
        })



# ==================== Contract Form (Unified) ====================

@login_required
def contract_form(request, pk=None):
    """نموذج موحد لإضافة/تعديل عقد - مبسط باستخدام UnifiedContractService"""
    contract = get_object_or_404(Contract, pk=pk) if pk else None
    unified_service = UnifiedContractService()
    
    if request.method == 'POST':
        form = ContractForm(request.POST, instance=contract)
        if form.is_valid():
            contract_obj = form.save(commit=False)
            
            # توليد رقم العقد تلقائياً إذا لم يتم إدخاله (للإضافة فقط)
            if not pk and not contract_obj.contract_number:
                contract_obj.contract_number = ContractForm.generate_contract_number()
            
            # تعيين المستخدم الذي أنشأ السجل (للإضافة فقط)
            if not pk:
                contract_obj.created_by = request.user
                if not contract_obj.contract_type:
                    contract_obj.contract_type = 'contract'
            
            # تحديد الإجراء: حفظ كمسودة أو حفظ وتفعيل
            action = request.POST.get('action', 'save_draft')
            
            # إذا كان عقد جديد، تحديد الحالة حسب الإجراء
            if not pk:
                if action == 'save_activate':
                    contract_obj.status = 'active'
                else:
                    contract_obj.status = 'draft'
            elif action == 'save_activate':
                contract_obj.status = 'active'
            
            contract_obj.save()
            
            # إضافة بند الراتب الأساسي تلقائياً (للعقود الجديدة فقط)
            if not pk and contract_obj.basic_salary and contract_obj.basic_salary > 0:
                basic_exists = ContractSalaryComponent.objects.filter(
                    contract=contract_obj,
                    is_basic=True
                ).exists()
                
                if not basic_exists:
                    basic_component = ContractSalaryComponent.objects.create(
                        contract=contract_obj,
                        component_type='earning',
                        code='BASIC_SALARY',
                        name='الراتب الأساسي',
                        calculation_method='fixed',
                        amount=contract_obj.basic_salary,
                        is_basic=True,
                        is_taxable=True,
                        is_fixed=True,
                        affects_overtime=True,
                        order=0,
                        show_in_payslip=True,
                        notes='تم إضافته تلقائياً من العقد'
                    )
                    logger.info(f"تم إضافة بند الراتب الأساسي تلقائياً: {contract_obj.basic_salary} ج.م")
                    
                    # إذا تم التفعيل مباشرة، انسخ للموظف
                    if action == 'save_activate':
                        emp_comp = basic_component.copy_to_employee_component(contract_obj.employee)
                        logger.info(f"  → تم نسخ الراتب الأساسي إلى SalaryComponent - ID={emp_comp.id}")
            
            # حفظ مكونات الراتب
            _save_contract_components(request, contract_obj, pk, action)
            
            if pk:
                messages.success(request, 'تم تحديث العقد بنجاح')
            else:
                messages.success(request, f'تم إضافة العقد بنجاح - الرقم: {contract_obj.contract_number}')
            return redirect('hr:contract_list')
        else:
            messages.error(request, 'يرجى تصحيح الأخطاء في النموذج')
    else:
        form = ContractForm(instance=contract)
    
    # توليد رقم العقد المقترح (للإضافة فقط)
    next_contract_number = ContractForm.generate_contract_number() if not pk else None
    
    # جلب مكونات الراتب الموجودة (للتعديل)
    earnings = []
    deductions = []
    if contract:
        earnings = contract.salary_components.filter(component_type='earning', is_basic=False)
        deductions = contract.salary_components.filter(component_type='deduction')
    
    # جلب إعدادات النظام
    try:
        currency_symbol = get_default_currency()
        system_settings = {'currency_symbol': currency_symbol}
    except:
        system_settings = {'currency_symbol': 'ج.م'}
    
    context = {
        'form': form,
        'contract': contract,
        'next_contract_number': next_contract_number,
        'earnings': earnings,
        'deductions': deductions,
        'system_settings': system_settings,
        'page_title': f'تعديل عقد: {contract.contract_number}' if contract else 'إضافة عقد جديد',
        'page_subtitle': 'تعديل بيانات العقد' if contract else 'إضافة عقد موظف جديد',
        'page_icon': 'fas fa-file-contract',
        'header_buttons': [
            {
                'url': '/hr/contracts/',
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': '/dashboard/', 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': '/hr/', 'icon': 'fas fa-users'},
            {'title': 'العقود', 'url': '/hr/contracts/', 'icon': 'fas fa-file-contract'},
            {'title': 'تعديل عقد' if contract else 'إضافة عقد', 'active': True},
        ],
    }
    return render(request, 'hr/contract/form.html', context)


def _save_contract_components(request, contract_obj, pk, action):
    """دالة مساعدة لحفظ بنود العقد"""
    # جمع المستحقات
    new_earnings = []
    earning_counters = sorted([
        key.split('_')[-1] for key in request.POST.keys() 
        if key.startswith('earning_name_')
    ], key=lambda x: int(x) if x.isdigit() else 0)
    
    for counter in earning_counters:
        name = request.POST.get(f'earning_name_{counter}')
        formula = request.POST.get(f'earning_formula_{counter}', '')
        amount = request.POST.get(f'earning_amount_{counter}')
        order = request.POST.get(f'earning_order_{counter}', 0)
        component_id = request.POST.get(f'earning_id_{counter}', '')
        
        if name and amount:
            clean_id = None
            if component_id and component_id.strip():
                try:
                    clean_id = int(component_id)
                except (ValueError, TypeError):
                    clean_id = None
            
            new_earnings.append({
                'id': clean_id,
                'name': name,
                'formula': formula,
                'amount': Decimal(amount),
                'order': int(order) if order else 0
            })
    
    # جمع الاستقطاعات
    new_deductions = []
    deduction_counters = sorted([
        key.split('_')[-1] for key in request.POST.keys() 
        if key.startswith('deduction_name_')
    ], key=lambda x: int(x) if x.isdigit() else 0)
    
    for counter in deduction_counters:
        name = request.POST.get(f'deduction_name_{counter}')
        formula = request.POST.get(f'deduction_formula_{counter}', '')
        amount = request.POST.get(f'deduction_amount_{counter}')
        order = request.POST.get(f'deduction_order_{counter}', 0)
        component_id = request.POST.get(f'deduction_id_{counter}', '')
        
        if name and amount:
            clean_id = None
            if component_id and component_id.strip():
                try:
                    clean_id = int(component_id)
                except (ValueError, TypeError):
                    clean_id = None
            
            new_deductions.append({
                'id': clean_id,
                'name': name,
                'formula': formula,
                'amount': Decimal(amount),
                'order': int(order) if order else 0
            })
    
    # حفظ البنود
    if pk:
        # للتعديل: تحديث ContractSalaryComponent
        _update_contract_components(contract_obj, new_earnings, new_deductions, action)
    else:
        # للإضافة: إنشاء في ContractSalaryComponent
        _create_contract_components(contract_obj, new_earnings, new_deductions, action)


def _update_contract_components(contract_obj, new_earnings, new_deductions, action):
    """تحديث بنود العقد الموجود"""
    # معالجة المستحقات
    existing_earning_ids = []
    for item in new_earnings:
        if item['id']:
            existing_earning_ids.append(item['id'])
            try:
                obj = ContractSalaryComponent.objects.get(
                    id=item['id'],
                    contract=contract_obj,
                    component_type='earning'
                )
                obj.name = item['name']
                obj.formula = item['formula']
                obj.amount = item['amount']
                obj.order = item['order']
                obj.save()
                
                # إذا العقد active، حدث SalaryComponent المنسوخة
                if contract_obj.status == 'active':
                    try:
                        emp_comp = SalaryComponent.objects.get(
                            employee=contract_obj.employee,
                            source_contract_component=obj,
                            is_from_contract=True
                        )
                        emp_comp.name = item['name']
                        emp_comp.formula = item['formula']
                        emp_comp.amount = item['amount']
                        emp_comp.order = item['order']
                        emp_comp.save()
                    except SalaryComponent.DoesNotExist:
                        pass
            except ContractSalaryComponent.DoesNotExist:
                pass
        else:
            # إنشاء بند جديد
            code = item['name'].upper().replace(' ', '_')[:50]
            new_obj, created = ContractSalaryComponent.objects.get_or_create(
                contract=contract_obj,
                code=code,
                defaults={
                    'component_type': 'earning',
                    'name': item['name'],
                    'formula': item['formula'],
                    'amount': item['amount'],
                    'order': item['order'],
                    'calculation_method': 'formula' if item['formula'] else 'fixed'
                }
            )
            if not created:
                new_obj.name = item['name']
                new_obj.formula = item['formula']
                new_obj.amount = item['amount']
                new_obj.order = item['order']
                new_obj.calculation_method = 'formula' if item['formula'] else 'fixed'
                new_obj.save()
            
            existing_earning_ids.append(new_obj.id)
            
            if contract_obj.status == 'active':
                new_obj.copy_to_employee_component(contract_obj.employee)
    
    # حذف المستحقات المحذوفة
    deleted_earnings = contract_obj.salary_components.filter(
        component_type='earning',
        is_basic=False
    ).exclude(id__in=existing_earning_ids)
    if deleted_earnings.exists():
        for item in deleted_earnings:
            if contract_obj.status == 'active':
                SalaryComponent.objects.filter(
                    source_contract_component=item,
                    is_from_contract=True
                ).delete()
        deleted_earnings.delete()
    
    # معالجة الاستقطاعات (نفس المنطق)
    existing_deduction_ids = []
    for item in new_deductions:
        if item['id']:
            existing_deduction_ids.append(item['id'])
            try:
                obj = ContractSalaryComponent.objects.get(
                    id=item['id'],
                    contract=contract_obj,
                    component_type='deduction'
                )
                obj.name = item['name']
                obj.formula = item['formula']
                obj.amount = item['amount']
                obj.order = item['order']
                obj.save()
                
                if contract_obj.status == 'active':
                    try:
                        emp_comp = SalaryComponent.objects.get(
                            employee=contract_obj.employee,
                            source_contract_component=obj,
                            is_from_contract=True
                        )
                        emp_comp.name = item['name']
                        emp_comp.formula = item['formula']
                        emp_comp.amount = item['amount']
                        emp_comp.order = item['order']
                        emp_comp.save()
                    except SalaryComponent.DoesNotExist:
                        pass
            except ContractSalaryComponent.DoesNotExist:
                pass
        else:
            code = item['name'].upper().replace(' ', '_')[:50]
            new_obj, created = ContractSalaryComponent.objects.get_or_create(
                contract=contract_obj,
                code=code,
                defaults={
                    'component_type': 'deduction',
                    'name': item['name'],
                    'formula': item['formula'],
                    'amount': item['amount'],
                    'order': item['order'],
                    'calculation_method': 'formula' if item['formula'] else 'fixed'
                }
            )
            if not created:
                new_obj.name = item['name']
                new_obj.formula = item['formula']
                new_obj.amount = item['amount']
                new_obj.order = item['order']
                new_obj.calculation_method = 'formula' if item['formula'] else 'fixed'
                new_obj.save()
            
            existing_deduction_ids.append(new_obj.id)
            
            if contract_obj.status == 'active':
                new_obj.copy_to_employee_component(contract_obj.employee)
    
    # حذف الاستقطاعات المحذوفة
    deleted_deductions = contract_obj.salary_components.filter(
        component_type='deduction'
    ).exclude(id__in=existing_deduction_ids)
    if deleted_deductions.exists():
        for item in deleted_deductions:
            if contract_obj.status == 'active':
                SalaryComponent.objects.filter(
                    source_contract_component=item,
                    is_from_contract=True
                ).delete()
        deleted_deductions.delete()


def _create_contract_components(contract_obj, new_earnings, new_deductions, action):
    """إنشاء بنود العقد الجديد"""
    for data in new_earnings:
        data.pop('id', None)
        code = data['name'].upper().replace(' ', '_')[:50]
        
        new_obj, created = ContractSalaryComponent.objects.get_or_create(
            contract=contract_obj,
            code=code,
            defaults={
                'component_type': 'earning',
                'calculation_method': 'formula' if data['formula'] else 'fixed',
                **data
            }
        )
        
        if not created:
            for key, value in data.items():
                setattr(new_obj, key, value)
            new_obj.calculation_method = 'formula' if data['formula'] else 'fixed'
            new_obj.save()
        
        # إذا تم التفعيل مباشرة، انسخ للموظف
        if action == 'save_activate':
            new_obj.copy_to_employee_component(contract_obj.employee)
    
    for data in new_deductions:
        data.pop('id', None)
        code = data['name'].upper().replace(' ', '_')[:50]
        
        new_obj, created = ContractSalaryComponent.objects.get_or_create(
            contract=contract_obj,
            code=code,
            defaults={
                'component_type': 'deduction',
                'calculation_method': 'formula' if data['formula'] else 'fixed',
                **data
            }
        )
        
        if not created:
            for key, value in data.items():
                setattr(new_obj, key, value)
            new_obj.calculation_method = 'formula' if data['formula'] else 'fixed'
            new_obj.save()
        
        if action == 'save_activate':
            new_obj.copy_to_employee_component(contract_obj.employee)



# ==================== Smart Activation & Preview (من contract_unified_views) ====================

@login_required
@hr_manager_required
@require_http_methods(["POST"])
def contract_smart_activate(request, contract_id):
    """تفعيل ذكي للعقد (من SmartContractActivationView)"""
    
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
        unified_service = UnifiedContractService()
        result = unified_service.smart_activate_contract(
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


@login_required
@hr_manager_required
def contract_preview_components(request, contract_id):
    """معاينة بنود العقد للنسخ (من contract_unified_views)"""
    
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
    """تطبيق اختيار البنود من المعاينة (من contract_unified_views)"""
    
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
    """تحسين بنود الموظف تلقائياً (من contract_unified_views)"""
    
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


@login_required
def contract_components_unified(request, employee_id):
    """صفحة بنود الراتب الموحدة (من contract_unified_views)"""
    
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
    
    return render(request, 'hr/employee/salary_components_enhanced.html', context)
