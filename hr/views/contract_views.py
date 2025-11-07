"""
Views إدارة العقود (الجزء الأول - الدوال الأساسية)
"""
from .base_imports import *
from ..models import Contract, Employee, Department
from ..models.contract import ContractDocument, ContractAmendment, ContractIncrease
from core.models import SystemSetting
from datetime import date, timedelta

__all__ = [
    'contract_list',
    'contract_detail',
    'contract_activate',
    'contract_suspend',
    'contract_reactivate',
    'contract_document_upload',
    'contract_document_delete',
    'contract_amendment_create',
]


@login_required
def contract_list(request):
    """قائمة العقود"""
    contracts = Contract.objects.select_related('employee', 'employee__department').all()
    
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
    
    context = {
        'headers': headers,
        'data': contracts,
        'action_buttons': action_buttons,
        'table_id': 'contracts-table',
        'primary_key': 'pk',
        'empty_message': 'لا توجد عقود',
        'currency_symbol': 'جنيه',
        'clickable_rows': True,
        'row_click_url': '/hr/contracts/0/',
        **{f'{k}_contracts': v for k, v in stats.items()},
        'show_stats': True,
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
    
    context = {
        'contract': contract,
        'system_settings': {'currency_symbol': currency_symbol},
        'documents_headers': documents_headers,
        'primary_key': 'id',
        'scheduled_increases': scheduled_increases,
        'pending_increases': pending_increases,
        'applied_increases': applied_increases,
    }
    
    return render(request, 'hr/contract/detail.html', context)


@login_required
def contract_activate(request, pk):
    """تفعيل العقد (draft → active)"""
    contract = get_object_or_404(Contract, pk=pk)
    
    if contract.status == 'draft':
        contract.status = 'active'
        contract.save()
        messages.success(request, f'تم تفعيل العقد {contract.contract_number} بنجاح')
    else:
        messages.warning(request, 'لا يمكن تفعيل هذا العقد')
    
    return redirect('hr:contract_detail', pk=pk)


@login_required
def contract_suspend(request, pk):
    """إيقاف العقد مؤقتاً (active → suspended)"""
    contract = get_object_or_404(Contract, pk=pk)
    
    if contract.status == 'active':
        contract.status = 'suspended'
        contract.save()
        messages.warning(request, f'تم إيقاف العقد {contract.contract_number} مؤقتاً')
    else:
        messages.warning(request, 'لا يمكن إيقاف هذا العقد')
    
    return redirect('hr:contract_detail', pk=pk)


@login_required
def contract_reactivate(request, pk):
    """إعادة تفعيل العقد (suspended → active)"""
    contract = get_object_or_404(Contract, pk=pk)
    
    if contract.status == 'suspended':
        contract.status = 'active'
        contract.save()
        messages.success(request, f'تم إعادة تفعيل العقد {contract.contract_number} بنجاح')
    else:
        messages.warning(request, 'لا يمكن إعادة تفعيل هذا العقد')
    
    return redirect('hr:contract_detail', pk=pk)


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
    from django.http import JsonResponse
    from ..models import SalaryComponentTemplate
    
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
    from datetime import datetime, timedelta, date
    from ..forms.contract_forms import ContractForm
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
        from ..models import BiometricUserMapping
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
    return render(request, 'hr/contract/terminate.html', {'contract': contract})


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
    from ..models import ContractIncrease
    from django.http import JsonResponse
    
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
    
    return render(request, 'hr/contract/expiring.html', {'contracts': contracts})
