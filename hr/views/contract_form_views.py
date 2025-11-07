"""
Views نموذج العقود - Contract Form
"""
from .base_imports import *
from ..models import Contract, SalaryComponent
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
            
            contract_obj.save()
            
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
            
            if pk:
                # للتعديل: استخدام ID tracking
                logger.info("=" * 80)
                logger.info(f"معالجة التعديل - العقد: {contract_obj.contract_number}")
                logger.info(f"عدد المستحقات في POST: {len(new_earnings)}")
                logger.info(f"عدد الاستقطاعات في POST: {len(new_deductions)}")
                
                # فصل البنود الموجودة عن الجديدة
                existing_earning_ids = []
                new_earnings_data = []
                
                for idx, item in enumerate(new_earnings):
                    logger.info(f"معالجة مستحق {idx+1}: ID={item['id']}, Name={item['name']}")
                    if item['id']:
                        existing_earning_ids.append(item['id'])
                        # تحديث الموجود مباشرة
                        try:
                            obj = SalaryComponent.objects.get(
                                id=item['id'],
                                employee=contract_obj.employee,
                                component_type='earning'
                            )
                            obj.name = item['name']
                            obj.formula = item['formula']
                            obj.amount = item['amount']
                            obj.order = item['order']
                            obj.save()
                            logger.info(f"  → تم تحديث ID={item['id']}")
                        except SalaryComponent.DoesNotExist:
                            logger.error(f"  → خطأ: ID={item['id']} غير موجود!")
                    else:
                        new_earnings_data.append(item)
                        logger.info(f"  → سيتم إنشاء جديد: {item['name']}")
                
                # إنشاء المستحقات الجديدة
                logger.info(f"إنشاء {len(new_earnings_data)} مستحق جديد...")
                created_earning_ids = []
                for data in new_earnings_data:
                    new_obj = SalaryComponent.objects.create(
                        employee=contract_obj.employee,
                        contract=contract_obj,
                        component_type='earning',
                        name=data['name'],
                        formula=data['formula'],
                        amount=data['amount'],
                        order=data['order']
                    )
                    created_earning_ids.append(new_obj.id)
                    logger.info(f"  → تم إنشاء: {data['name']} - ID={new_obj.id}")
                
                # حذف المستحقات المحذوفة (اللي مش موجودة في الـ POST)
                all_earning_ids = existing_earning_ids + created_earning_ids
                logger.info(f"IDs المحفوظة: {all_earning_ids}")
                # البنود تتبع الموظف الآن
                deleted_earnings = contract_obj.employee.salary_components.filter(
                    component_type='earning',
                    is_basic=False
                ).exclude(id__in=all_earning_ids)
                if deleted_earnings.exists():
                    logger.info(f"حذف {deleted_earnings.count()} مستحق...")
                    for item in deleted_earnings:
                        logger.info(f"  → حذف: {item.name} - ID={item.id}")
                    deleted_earnings.delete()
                logger.info("=" * 80)
                
                # معالجة الاستقطاعات
                existing_deduction_ids = []
                new_deductions_data = []
                
                for item in new_deductions:
                    if item['id']:
                        existing_deduction_ids.append(item['id'])
                        # تحديث الموجود مباشرة
                        try:
                            obj = SalaryComponent.objects.get(
                                id=item['id'],
                                employee=contract_obj.employee,
                                component_type='deduction'
                            )
                            obj.name = item['name']
                            obj.formula = item['formula']
                            obj.amount = item['amount']
                            obj.order = item['order']
                            obj.save()
                        except SalaryComponent.DoesNotExist:
                            pass  # تجاهل لو الـ ID مش موجود
                    else:
                        new_deductions_data.append(item)
                
                # إنشاء الاستقطاعات الجديدة
                created_deduction_ids = []
                for data in new_deductions_data:
                    new_obj = SalaryComponent.objects.create(
                        employee=contract_obj.employee,
                        contract=contract_obj,
                        component_type='deduction',
                        name=data['name'],
                        formula=data['formula'],
                        amount=data['amount'],
                        order=data['order']
                    )
                    created_deduction_ids.append(new_obj.id)
                
                # حذف الاستقطاعات المحذوفة (اللي مش موجودة في الـ POST)
                all_deduction_ids = existing_deduction_ids + created_deduction_ids
                # البنود تتبع الموظف الآن
                contract_obj.employee.salary_components.filter(
                    component_type='deduction'
                ).exclude(id__in=all_deduction_ids).delete()
            else:
                # للإضافة: إنشاء جديد
                for data in new_earnings:
                    data.pop('id', None)  # إزالة ID لو موجود
                    SalaryComponent.objects.create(
                        employee=contract_obj.employee,
                        contract=contract_obj,
                        component_type='earning',
                        **data
                    )
                
                for data in new_deductions:
                    data.pop('id', None)  # إزالة ID لو موجود
                    SalaryComponent.objects.create(
                        employee=contract_obj.employee,
                        contract=contract_obj,
                        component_type='deduction',
                        **data
                    )
            
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
        # البنود تتبع الموظف الآن
        earnings = contract.employee.salary_components.filter(component_type='earning', is_basic=False)
        deductions = contract.employee.salary_components.filter(component_type='deduction')
    
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
    }
    return render(request, 'hr/contract/form.html', context)
