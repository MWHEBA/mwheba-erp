"""
Views نموذج العقود - Contract Form
"""
from .base_imports import *
from ..models import Contract, SalaryComponent, ContractSalaryComponent
from ..services.unified_salary_component_service import UnifiedSalaryComponentService
from ..forms.contract_forms import ContractForm
from core.utils import get_default_currency
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

__all__ = [
    'contract_form',
]


@login_required
def contract_form(request, pk=None):
    """نموذج موحد لإضافة/تعديل عقد"""
    contract = get_object_or_404(Contract, pk=pk) if pk else None
    
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
                # تعيين نوع العقد الافتراضي (عقد محدد المدة)
                if not contract_obj.contract_type:
                    contract_obj.contract_type = 'contract'
            
            # تحديد الإجراء: حفظ كمسودة أو حفظ وتفعيل
            action = request.POST.get('action', 'save_draft')
            print(f"DEBUG: Action received: {action}, pk: {pk}")
            
            # إذا كان عقد جديد، تحديد الحالة حسب الإجراء
            if not pk:
                if action == 'save_activate':
                    contract_obj.status = 'active'
                else:
                    # أي إجراء آخر (save_draft أو فارغ) = مسودة
                    contract_obj.status = 'draft'
            elif action == 'save_activate':
                contract_obj.status = 'active'
            # للعقود الموجودة، لا نغير الحالة إلا إذا كان تفعيل صريح
            
            contract_obj.save()
            
            # إضافة بند الراتب الأساسي تلقائياً (للعقود الجديدة فقط)
            if not pk and contract_obj.basic_salary and contract_obj.basic_salary > 0:
                    # التحقق من عدم وجود بند راتب أساسي بالفعل
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
            
            # حفظ مكونات الراتب بطريقة ذكية (update or create)
            # جمع البيانات الجديدة من الـ POST مع IDs
            new_earnings = []
            new_deductions = []
            
            # طباعة POST data للتحليل
            logger.info("=" * 80)
            logger.info("POST DATA للمستحقات:")
            for key in sorted(request.POST.keys()):
                if 'earning' in key:
                    logger.info(f"{key} = {request.POST.get(key)}")
            logger.info("=" * 80)
            
            # جمع المستحقات - نرتبهم حسب counter
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
                    # تنظيف ID - تحويل string فاضي لـ None
                    clean_id = None
                    if component_id and component_id.strip():
                        try:
                            clean_id = int(component_id)
                        except (ValueError, TypeError):
                            clean_id = None
                    
                    earning_item = {
                        'id': clean_id,
                        'name': name,
                        'formula': formula,
                        'amount': Decimal(amount),
                        'order': int(order) if order else 0
                    }
                    new_earnings.append(earning_item)
                    logger.info(f"Counter {counter}: {earning_item}")
            
            # جمع الاستقطاعات - نرتبهم حسب counter
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
                    # تنظيف ID - تحويل string فاضي لـ None
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
            
            # ============================================
            # حفظ البنود في ContractSalaryComponent
            # ============================================
            if pk:
                # للتعديل: تحديث ContractSalaryComponent
                logger.info("=" * 80)
                logger.info(f"معالجة التعديل - العقد: {contract_obj.contract_number}")
                logger.info(f"عدد المستحقات في POST: {len(new_earnings)}")
                logger.info(f"عدد الاستقطاعات في POST: {len(new_deductions)}")
                
                # معالجة المستحقات
                existing_earning_ids = []
                new_earnings_data = []
                
                for idx, item in enumerate(new_earnings):
                    logger.info(f"معالجة مستحق {idx+1}: ID={item['id']}, Name={item['name']}")
                    if item['id']:
                        existing_earning_ids.append(item['id'])
                        # تحديث في ContractSalaryComponent
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
                            logger.info(f"  → تم تحديث ContractSalaryComponent ID={item['id']}")
                            
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
                                    logger.info(f"  → تم تحديث SalaryComponent المنسوخة")
                                except SalaryComponent.DoesNotExist:
                                    logger.warning(f"  → SalaryComponent المنسوخة غير موجودة")
                        except ContractSalaryComponent.DoesNotExist:
                            logger.error(f"  → خطأ: ContractSalaryComponent ID={item['id']} غير موجود!")
                    else:
                        new_earnings_data.append(item)
                        logger.info(f"  → سيتم إنشاء جديد: {item['name']}")
                
                # إنشاء المستحقات الجديدة في ContractSalaryComponent
                logger.info(f"إنشاء {len(new_earnings_data)} مستحق جديد...")
                created_earning_ids = []
                for data in new_earnings_data:
                    # إنشاء كود تلقائي
                    code = data['name'].upper().replace(' ', '_')[:50]
                    
                    # استخدام get_or_create لتجنب UNIQUE constraint error
                    new_obj, created = ContractSalaryComponent.objects.get_or_create(
                        contract=contract_obj,
                        code=code,
                        defaults={
                            'component_type': 'earning',
                            'name': data['name'],
                            'formula': data['formula'],
                            'amount': data['amount'],
                            'order': data['order'],
                            'calculation_method': 'formula' if data['formula'] else 'fixed'
                        }
                    )
                    
                    if not created:
                        # تحديث البند الموجود
                        new_obj.name = data['name']
                        new_obj.formula = data['formula']
                        new_obj.amount = data['amount']
                        new_obj.order = data['order']
                        new_obj.calculation_method = 'formula' if data['formula'] else 'fixed'
                        new_obj.save()
                        logger.info(f"  → تم تحديث ContractSalaryComponent: {data['name']} - ID={new_obj.id}")
                    else:
                        logger.info(f"  → تم إنشاء ContractSalaryComponent: {data['name']} - ID={new_obj.id}")
                    
                    created_earning_ids.append(new_obj.id)
                    
                    # إذا العقد active، انسخ للموظف
                    if contract_obj.status == 'active':
                        emp_comp = new_obj.copy_to_employee_component(contract_obj.employee)
                        logger.info(f"  → تم نسخ إلى SalaryComponent - ID={emp_comp.id}")
                
                # حذف المستحقات المحذوفة
                all_earning_ids = existing_earning_ids + created_earning_ids
                logger.info(f"IDs المحفوظة: {all_earning_ids}")
                deleted_earnings = contract_obj.salary_components.filter(
                    component_type='earning',
                    is_basic=False
                ).exclude(id__in=all_earning_ids)
                if deleted_earnings.exists():
                    logger.info(f"حذف {deleted_earnings.count()} مستحق...")
                    for item in deleted_earnings:
                        logger.info(f"  → حذف ContractSalaryComponent: {item.name} - ID={item.id}")
                        # حذف SalaryComponent المنسوخة إذا كان العقد active
                        if contract_obj.status == 'active':
                            SalaryComponent.objects.filter(
                                source_contract_component=item,
                                is_from_contract=True
                            ).delete()
                    deleted_earnings.delete()
                logger.info("=" * 80)
                
                # معالجة الاستقطاعات (نفس المنطق)
                existing_deduction_ids = []
                new_deductions_data = []
                
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
                        new_deductions_data.append(item)
                
                # إنشاء الاستقطاعات الجديدة
                created_deduction_ids = []
                for data in new_deductions_data:
                    code = data['name'].upper().replace(' ', '_')[:50]
                    
                    # استخدام get_or_create لتجنب UNIQUE constraint error
                    new_obj, created = ContractSalaryComponent.objects.get_or_create(
                        contract=contract_obj,
                        code=code,
                        defaults={
                            'component_type': 'deduction',
                            'name': data['name'],
                            'formula': data['formula'],
                            'amount': data['amount'],
                            'order': data['order'],
                            'calculation_method': 'formula' if data['formula'] else 'fixed'
                        }
                    )
                    
                    if not created:
                        # تحديث البند الموجود
                        new_obj.name = data['name']
                        new_obj.formula = data['formula']
                        new_obj.amount = data['amount']
                        new_obj.order = data['order']
                        new_obj.calculation_method = 'formula' if data['formula'] else 'fixed'
                        new_obj.save()
                    
                    created_deduction_ids.append(new_obj.id)
                    
                    if contract_obj.status == 'active':
                        new_obj.copy_to_employee_component(contract_obj.employee)
                
                # حذف الاستقطاعات المحذوفة
                all_deduction_ids = existing_deduction_ids + created_deduction_ids
                deleted_deductions = contract_obj.salary_components.filter(
                    component_type='deduction'
                ).exclude(id__in=all_deduction_ids)
                if deleted_deductions.exists():
                    for item in deleted_deductions:
                        if contract_obj.status == 'active':
                            SalaryComponent.objects.filter(
                                source_contract_component=item,
                                is_from_contract=True
                            ).delete()
                    deleted_deductions.delete()
            else:
                # للإضافة: إنشاء في ContractSalaryComponent
                logger.info("=" * 80)
                logger.info(f"إضافة عقد جديد - Action: {action}")
                logger.info(f"عدد المستحقات: {len(new_earnings)}")
                logger.info(f"عدد الاستقطاعات: {len(new_deductions)}")
                
                for data in new_earnings:
                    data.pop('id', None)
                    code = data['name'].upper().replace(' ', '_')[:50]
                    
                    # استخدام get_or_create لتجنب UNIQUE constraint error
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
                        # تحديث البند الموجود
                        for key, value in data.items():
                            setattr(new_obj, key, value)
                        new_obj.calculation_method = 'formula' if data['formula'] else 'fixed'
                        new_obj.save()
                        logger.info(f"تم تحديث ContractSalaryComponent: {data['name']} - ID={new_obj.id}")
                    else:
                        logger.info(f"تم إنشاء ContractSalaryComponent: {data['name']} - ID={new_obj.id}")
                    
                    # إذا تم التفعيل مباشرة، انسخ للموظف
                    if action == 'save_activate':
                        emp_comp = new_obj.copy_to_employee_component(contract_obj.employee)
                        logger.info(f"  → تم نسخ إلى SalaryComponent - ID={emp_comp.id}")
                    else:
                        logger.info(f"  → لم يتم النسخ (Action={action})")
                
                for data in new_deductions:
                    data.pop('id', None)
                    code = data['name'].upper().replace(' ', '_')[:50]
                    
                    # استخدام get_or_create لتجنب UNIQUE constraint error
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
                        # تحديث البند الموجود
                        for key, value in data.items():
                            setattr(new_obj, key, value)
                        new_obj.calculation_method = 'formula' if data['formula'] else 'fixed'
                        new_obj.save()
                        logger.info(f"تم تحديث ContractSalaryComponent: {data['name']} - ID={new_obj.id}")
                    else:
                        logger.info(f"تم إنشاء ContractSalaryComponent: {data['name']} - ID={new_obj.id}")
                    
                    # إذا تم التفعيل مباشرة، انسخ للموظف
                    if action == 'save_activate':
                        emp_comp = new_obj.copy_to_employee_component(contract_obj.employee)
                        logger.info(f"  → تم نسخ إلى SalaryComponent - ID={emp_comp.id}")
                    else:
                        logger.info(f"  → لم يتم النسخ (Action={action})")
                
                logger.info("=" * 80)
            
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
        # جلب البنود من ContractSalaryComponent
        earnings = contract.salary_components.filter(component_type='earning', is_basic=False)
        deductions = contract.salary_components.filter(component_type='deduction')
    
    # جلب إعدادات النظام
    try:
        currency_symbol = get_default_currency()
        system_settings = {
            'currency_symbol': currency_symbol
        }
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
